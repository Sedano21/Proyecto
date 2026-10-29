"""Transporte tercero (V12, 29-oct-2026).

Flujo:
1. Antes de contratar, Distribución registra el servicio (proveedor, cliente para quien se contrata, origen, destino,
   tipo de vehículo, toneladas y monto con IGV) y Gerencia de Operaciones lo aprueba; Finanzas es informada.
2. El monto se compara con el tarifario. Si es mayor, el Coordinador de Distribución indica el motivo: se permite y
   se alerta a Gerencia de Operaciones y a Administración y Finanzas.
3. Distribución registra la factura del proveedor con centro de costo y tipo de servicio (fletes y estibas con sus
   subcategorías; de SAP cuando se conecte) y la guía de remisión remitente indicada en la factura, que se trae de SAP
   y valida. La fecha del servicio es la de la guía.
4. Compras recibe la tarea de elaborar la OC; con la OC, el expediente (factura + guía + OC) queda completo.
5. Administración y Finanzas valida el expediente, programa el pago (también pagos parciales), registra
   observaciones y sube el comprobante. Se alerta si un pago programado vence sin registrarse.
6. Por proveedor se registran incidencias y se calculan sus indicadores.

El tarifario lo mantiene el Coordinador de Distribución (cambio parcial o total); cada cambio alerta a Gerencia de
Operaciones y a Administración y Finanzas.
"""
from collections import defaultdict
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import ProviderIncident, ThirdPartyTransport, TransportRate, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

ESTADOS = ["POR_APROBAR", "RECHAZADO", "APROBADO", "FACTURADO", "OC_GENERADA", "VALIDADO", "PAGO_PARCIAL", "PAGADO"]
MOTIVOS = ["DESPACHO VENTA", "RECOJO DE COMPRAS", "TRASLADO", "DEVOLUCION"]


def _f(v, txt, obligatorio=True, minimo=0):
    if v in (None, ""):
        if obligatorio:
            raise BusinessError(f"Indique {txt}.")
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise BusinessError(f"{txt[0].upper() + txt[1:]}: valor inválido.")
    if x < minimo:
        raise BusinessError(f"{txt[0].upper() + txt[1:]} no puede ser negativo.")
    return x


def _log(t, user, evento, **extra):
    t.historial = list(t.historial or []) + [{"evento": evento, "user": user.nombre, "ts": now().isoformat(timespec="minutes"), **extra}]


# ------------------------------------------------------------------ tarifario
def rate_for(proveedor, destino, tipo_vehiculo="", origen=""):
    """Tarifa vigente más específica: proveedor + destino + vehículo, luego sin proveedor o sin vehículo."""
    rows = list(db().execute(select(TransportRate).where(TransportRate.vigente.is_(True))).scalars())
    d, p, v, o = (destino or "").strip().upper(), (proveedor or "").strip().upper(), (tipo_vehiculo or "").strip().upper(), \
        (origen or "").strip().upper()

    def score(r):
        if r.destino.strip().upper() != d:
            return -1
        s = 0
        for campo, val, peso in ((r.proveedor, p, 4), (r.tipo_vehiculo, v, 2), (r.origen, o, 1)):
            cv = (campo or "").strip().upper()
            if cv and cv != val:
                return -1
            s += peso if cv else 0
        return s
    best = max(rows, key=score, default=None)
    return best if best is not None and score(best) >= 0 else None


def save_rates(user, filas, motivo=""):
    """Alta o modificación (parcial o total) del tarifario. filas: [{id?, proveedor, tipo_vehiculo, origen, destino, precio,
    vigente}]. Cada cambio queda en el historial de la tarifa y se alerta a Gerencia de Operaciones y a Finanzas."""
    if not has_perm(user, "terceros.tarifario"):
        raise BusinessError("El tarifario lo modifica el Coordinador de Distribución.")
    cambios = []
    for x in filas:
        if not (x.get("destino") or "").strip():
            continue
        precio = _f(x.get("precio"), "el precio")
        r = db().get(TransportRate, int(x["id"])) if str(x.get("id") or "").isdigit() else None
        if r is None:
            r = TransportRate(destino=x["destino"].strip(), precio=precio, user_id=user.id)
            db().add(r)
            antes = None
        else:
            antes = {"precio": r.precio, "vigente": r.vigente}
        for k in ("proveedor", "tipo_vehiculo", "origen", "destino"):
            setattr(r, k, (x.get(k) or "").strip())
        vig = x.get("vigente")
        r.vigente = True if vig is None else (vig in (True, "1", "on", "true"))
        if antes is None or antes["precio"] != precio or antes["vigente"] != r.vigente:
            r.precio = precio
            r.historial = list(r.historial or []) + [{"antes": antes, "precio": precio, "vigente": r.vigente,
                                                      "motivo": (motivo or "").strip(), "user": user.nombre,
                                                      "ts": now().isoformat(timespec="minutes")}]
            cambios.append(f"{r.destino}{' / ' + r.proveedor if r.proveedor else ''}: "
                           f"{'nuevo' if antes is None else 'S/ ' + format(antes['precio'], ',.2f')} → S/ {precio:,.2f}"
                           + ("" if r.vigente else " (no vigente)"))
    if not cambios:
        raise BusinessError("No hay cambios en el tarifario.")
    db().flush()
    alerts.emit("TARIFARIO_MODIFICADO", f"Tarifario de transporte tercero modificado ({len(cambios)} tarifa(s))",
                "; ".join(cambios[:10]) + (f". Motivo: {motivo}" if motivo else ""), "TransportRate", "",
                dedup_key=f"TARIFARIO:{now():%Y%m%d%H%M%S}", creado_por=user)
    audit(user, "TARIFARIO_MODIFICADO", "TransportRate", "", {"cambios": cambios, "motivo": motivo})
    return cambios


# ------------------------------------------------------------------ servicio
def request_service(user, datos):
    """Distribución solicita contratar un transporte tercero; queda por aprobar por Gerencia de Operaciones."""
    if not has_perm(user, "terceros.registrar"):
        raise BusinessError("Registra el transporte tercero el Coordinador o el Asistente de Distribución.")
    prov = (datos.get("proveedor") or "").strip()
    if not prov:
        raise BusinessError("Indique el proveedor.")
    if not (datos.get("destino") or "").strip():
        raise BusinessError("Indique el destino.")
    monto = _f(datos.get("monto"), "el monto con IGV")
    tarifa = rate_for(prov, datos.get("destino"), datos.get("tipo_vehiculo"), datos.get("origen"))
    motivo_sobre = (datos.get("motivo_sobre_tarifa") or "").strip()
    sobre = tarifa is not None and monto > tarifa.precio + 1e-6
    if sobre and not motivo_sobre:
        raise BusinessError(f"El monto (S/ {monto:,.2f}) supera el tarifario (S/ {tarifa.precio:,.2f}): indique el motivo.")
    cid = datos.get("customer_id")
    t = ThirdPartyTransport(proveedor=prov, customer_id=int(cid) if str(cid or "").isdigit() else None,
                            motivo=(datos.get("motivo") or "DESPACHO VENTA").strip().upper(),
                            tipo_vehiculo=(datos.get("tipo_vehiculo") or "").strip(), origen=(datos.get("origen") or "").strip(),
                            destino=datos["destino"].strip(), toneladas=_f(datos.get("toneladas"), "las toneladas", False),
                            monto=monto, tarifa=tarifa.precio if tarifa else None, motivo_sobre_tarifa=motivo_sobre,
                            route_id=int(datos["route_id"]) if str(datos.get("route_id") or "").isdigit() else None,
                            creado_por=user.id)
    db().add(t)
    db().flush()
    _log(t, user, "SOLICITADO", monto=monto, tarifa=t.tarifa)
    alerts.emit("TERCERO_POR_APROBAR", f"Aprobar transporte tercero #{t.id}: {prov} → {t.destino}",
                f"Monto S/ {monto:,.2f} con IGV" + (f" (tarifario S/ {t.tarifa:,.2f})" if t.tarifa else " (sin tarifa registrada)")
                + (f". Cliente: {t.customer.nombre}" if t.customer else "") + ". Finanzas queda informada.",
                "ThirdPartyTransport", t.id, extra_roles=["COORD_FINANZAS"], dedup_key=f"TERC_APROB:{t.id}", creado_por=user)
    if sobre:
        alerts.emit("TERCERO_SOBRE_TARIFA", f"Transporte tercero #{t.id} sobre el tarifario: {prov}",
                    f"S/ {monto:,.2f} frente a S/ {tarifa.precio:,.2f} del tarifario. Motivo: {motivo_sobre}",
                    "ThirdPartyTransport", t.id, prioridad="ALTA", dedup_key=f"TERC_SOBRE:{t.id}", creado_por=user)
    audit(user, "TERCERO_SOLICITADO", "ThirdPartyTransport", t.id, {"proveedor": prov, "monto": monto, "sobre_tarifa": sobre})
    return t


def approve(user, t, aprobar, comentario=""):
    if not has_perm(user, "terceros.aprobar"):
        raise BusinessError("La contratación de transporte tercero la aprueba Gerencia de Operaciones.")
    if t.estado != "POR_APROBAR":
        raise BusinessError("El servicio no está por aprobar.")
    if not aprobar and not (comentario or "").strip():
        raise BusinessError("Indique por qué no se aprueba.")
    t.estado = "APROBADO" if aprobar else "RECHAZADO"
    t.aprobacion = {"aprobado": aprobar, "user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                    "comentario": (comentario or "").strip()}
    _log(t, user, t.estado, comentario=comentario)
    alerts.close_by_system(f"TERC_APROB:{t.id}", t.estado.lower())
    audit(user, "TERCERO_" + t.estado, "ThirdPartyTransport", t.id, t.aprobacion)
    return t


def register_invoice(user, t, datos, archivo=""):
    """Factura del proveedor: número, centro de costo, tipo de servicio y subtipo, guía remitente (de SAP)."""
    if not has_perm(user, "terceros.registrar"):
        raise BusinessError("La factura la registran el Coordinador o el Asistente de Distribución.")
    if t.estado not in ("APROBADO", "FACTURADO"):
        raise BusinessError("Primero debe estar aprobada la contratación por Gerencia de Operaciones.")
    numero = (datos.get("factura_numero") or "").strip().upper()
    if not numero or not (archivo or t.factura_archivo):
        raise BusinessError("Indique el número de la factura y adjunte el archivo.")
    tipos = param("terceros_tipos_servicio", {}) or {}
    tipo, sub = (datos.get("tipo_servicio") or "").strip(), (datos.get("subtipo_servicio") or "").strip()
    if tipo not in tipos:
        raise BusinessError("Elija el tipo de servicio (fletes o estibas).")
    if sub and sub not in (tipos.get(tipo) or []):
        raise BusinessError("La subcategoría no corresponde al tipo de servicio.")
    cc = (datos.get("centro_costo") or "").strip()
    if not cc:
        raise BusinessError("Indique el centro de costo.")
    t.factura_numero, t.centro_costo, t.tipo_servicio, t.subtipo_servicio = numero, cc, tipo, sub
    if archivo:
        t.factura_archivo = archivo
    if datos.get("monto") not in (None, ""):
        t.monto = _f(datos.get("monto"), "el monto con IGV")
    t.toneladas = _f(datos.get("toneladas"), "las toneladas", False) or t.toneladas
    guia = (datos.get("guia_numero") or "").strip().upper()
    if guia:
        fetch_guide(user, t, guia)
    t.estado = "FACTURADO"
    _log(t, user, "FACTURA", numero=numero)
    alerts.emit("TERCERO_OC", f"Elaborar OC: transporte tercero #{t.id} ({t.proveedor}, factura {numero})",
                f"S/ {t.monto:,.2f} con IGV · {tipo}{' / ' + sub if sub else ''} · centro de costo {cc}.",
                "ThirdPartyTransport", t.id, dedup_key=f"TERC_OC:{t.id}", creado_por=user)
    audit(user, "TERCERO_FACTURA", "ThirdPartyTransport", t.id, {"factura": numero, "guia": guia})
    return t


def fetch_guide(user, t, numero):
    """Trae la guía de remisión remitente de SAP (despachos sincronizados o la guía de la ruta) para el expediente;
    Distribución luego valida que sea la correcta. La fecha del servicio toma la fecha de la guía."""
    from ..models import RouteStop
    st = db().execute(select(RouteStop).where(RouteStop.guia_numero == numero)).scalars().first()
    info = {"numero": numero, "encontrada": st is not None, "validada": False, "ts": now().isoformat(timespec="minutes")}
    if st is not None:
        fg = st.fecha_guia or (st.route.fecha if st.route else None)
        info.update({"ov": st.order.numero, "cliente": st.order.customer.nombre, "fecha": fg.isoformat() if fg else "",
                     "archivo": st.guia_path or ""})
        if fg:
            t.fecha_servicio = fg
        if t.customer_id is None:
            t.customer_id = st.order.customer_id
    t.guia_numero, t.guia = numero, info
    return info


def validate_guide(user, t, correcta, fecha=None):
    if not has_perm(user, "terceros.registrar"):
        raise BusinessError("Valida la guía Distribución.")
    if not t.guia_numero:
        raise BusinessError("El servicio no tiene guía remitente.")
    g = dict(t.guia or {})
    g.update({"validada": bool(correcta), "validada_por": user.nombre, "validada_ts": now().isoformat(timespec="minutes")})
    if fecha:
        t.fecha_servicio = fecha if isinstance(fecha, date) else date.fromisoformat(str(fecha)[:10])
        g["fecha"] = t.fecha_servicio.isoformat()
    if not correcta:
        t.guia_numero = ""
        g["observacion"] = "Guía no corresponde: registrar la correcta."
    t.guia = g
    _log(t, user, "GUIA_VALIDADA" if correcta else "GUIA_RECHAZADA")
    _check_complete(t, user)
    return t


def register_po(user, t, numero, archivo=""):
    if not has_perm(user, "terceros.oc"):
        raise BusinessError("La orden de compra la registra Compras.")
    if t.estado != "FACTURADO":
        raise BusinessError("Primero Distribución registra la factura.")
    if not (numero or "").strip():
        raise BusinessError("Indique el número de la OC.")
    t.oc_numero, t.oc_archivo = numero.strip().upper(), archivo or t.oc_archivo
    t.estado = "OC_GENERADA"
    _log(t, user, "OC", numero=t.oc_numero)
    alerts.close_by_system(f"TERC_OC:{t.id}", f"OC {t.oc_numero}")
    _check_complete(t, user)
    audit(user, "TERCERO_OC", "ThirdPartyTransport", t.id, {"oc": t.oc_numero})
    return t


def expediente(t):
    """Documentos del expediente y si está completo (factura, guía validada y OC)."""
    docs = [("Factura", t.factura_numero, t.factura_archivo), ("Guía remitente", t.guia_numero, (t.guia or {}).get("archivo", "")),
            ("Orden de compra", t.oc_numero, t.oc_archivo)]
    faltan = [n for n, num, _ in docs if not num]
    if t.guia_numero and not (t.guia or {}).get("validada"):
        faltan.append("validar la guía")
    return {"documentos": docs, "faltan": faltan, "completo": not faltan}


def _check_complete(t, user):
    if t.estado == "OC_GENERADA" and expediente(t)["completo"]:
        alerts.emit("TERCERO_EXPEDIENTE", f"Expediente completo: transporte tercero #{t.id} ({t.proveedor})",
                    f"Factura {t.factura_numero}, guía {t.guia_numero}, OC {t.oc_numero}. S/ {t.monto:,.2f} con IGV.",
                    "ThirdPartyTransport", t.id, dedup_key=f"TERC_EXP:{t.id}", creado_por=user)


def finance_validate(user, t, observacion=""):
    if not has_perm(user, "terceros.finanzas"):
        raise BusinessError("Valida el expediente Administración y Finanzas.")
    exp = expediente(t)
    if not exp["completo"]:
        raise BusinessError("El expediente está incompleto: " + ", ".join(exp["faltan"]) + ".")
    t.finanzas = {"validado_por": user.nombre, "ts": now().isoformat(timespec="minutes"), "observaciones": (observacion or "").strip()}
    t.estado = "VALIDADO"
    _log(t, user, "VALIDADO_FINANZAS", observacion=observacion)
    alerts.close_by_system(f"TERC_EXP:{t.id}", "Validado por Finanzas")
    audit(user, "TERCERO_VALIDADO", "ThirdPartyTransport", t.id, t.finanzas)
    return t


def schedule_payment(user, t, fecha, monto, observacion=""):
    """Programa un pago (total o parcial). La suma programada no puede superar el monto del servicio."""
    if not has_perm(user, "terceros.finanzas"):
        raise BusinessError("Programa los pagos Administración y Finanzas.")
    if t.estado not in ("VALIDADO", "PAGO_PARCIAL"):
        raise BusinessError("Primero Finanzas valida el expediente.")
    fecha = fecha if isinstance(fecha, date) else date.fromisoformat(str(fecha)[:10])
    m = _f(monto, "el monto del pago")
    if m <= 0:
        raise BusinessError("El monto del pago debe ser mayor que cero.")
    prog = sum(p["monto"] for p in t.pagos or [] if p["estado"] != "ANULADO")
    if prog + m > (t.monto or 0) + 0.005:
        raise BusinessError(f"Lo programado (S/ {prog + m:,.2f}) supera el monto del servicio (S/ {t.monto:,.2f}).")
    t.pagos = list(t.pagos or []) + [{"n": len(t.pagos or []) + 1, "fecha_programada": fecha.isoformat(), "monto": m,
                                      "estado": "PROGRAMADO", "observacion": (observacion or "").strip(),
                                      "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]
    _log(t, user, "PAGO_PROGRAMADO", monto=m, fecha=fecha.isoformat())
    return t


def register_payment(user, t, n, comprobante, fecha_pago=None, observacion=""):
    if not has_perm(user, "terceros.finanzas"):
        raise BusinessError("Registra el pago Administración y Finanzas.")
    if not comprobante:
        raise BusinessError("Adjunte el comprobante de pago.")
    pagos = [dict(p) for p in t.pagos or []]
    p = next((x for x in pagos if x["n"] == int(n)), None)
    if p is None or p["estado"] != "PROGRAMADO":
        raise BusinessError("Pago no encontrado o ya registrado.")
    p.update({"estado": "PAGADO", "comprobante": comprobante, "pagado": (fecha_pago or date.today()).isoformat()
              if isinstance(fecha_pago or date.today(), date) else str(fecha_pago), "obs_pago": (observacion or "").strip(),
              "registrado_por": user.nombre})
    t.pagos = pagos
    pagado = sum(x["monto"] for x in pagos if x["estado"] == "PAGADO")
    t.estado = "PAGADO" if pagado >= (t.monto or 0) - 0.005 else "PAGO_PARCIAL"
    alerts.close_by_system(f"TERC_PAGO:{t.id}:{p['n']}", "Pago registrado")
    _log(t, user, "PAGO", n=p["n"], monto=p["monto"])
    audit(user, "TERCERO_PAGO", "ThirdPartyTransport", t.id, {"n": p["n"], "monto": p["monto"], "estado": t.estado})
    return t


def check_payments(hoy=None):
    """Alerta los pagos programados vencidos sin registrar (fuera de la programación)."""
    hoy = hoy or date.today()
    n = 0
    for t in db().execute(select(ThirdPartyTransport).where(ThirdPartyTransport.estado.in_(("VALIDADO", "PAGO_PARCIAL")))).scalars():
        for p in t.pagos or []:
            if p["estado"] == "PROGRAMADO" and date.fromisoformat(p["fecha_programada"]) < hoy:
                alerts.emit("TERCERO_PAGO_VENCIDO", f"Pago vencido: transporte tercero #{t.id} ({t.proveedor})",
                            f"Pago {p['n']} de S/ {p['monto']:,.2f} programado para el {p['fecha_programada']}.",
                            "ThirdPartyTransport", t.id, dedup_key=f"TERC_PAGO:{t.id}:{p['n']}")
                n += 1
    return n


# ------------------------------------------------------------------ incidencias e indicadores por proveedor
def register_incident(user, proveedor, tipo, descripcion, servicio=None, fecha=None):
    if not has_perm(user, "terceros.registrar"):
        raise BusinessError("Registra incidencias de proveedores Distribución.")
    if not (proveedor or "").strip() or not (tipo or "").strip() or not (descripcion or "").strip():
        raise BusinessError("Indique el proveedor, el tipo y la descripción de la incidencia.")
    i = ProviderIncident(proveedor=proveedor.strip(), tipo=tipo.strip().upper(), descripcion=descripcion.strip(),
                         servicio_id=servicio.id if servicio else None, fecha=fecha or date.today(), user_id=user.id)
    db().add(i)
    db().flush()
    audit(user, "PROVEEDOR_INCIDENCIA", "ProviderIncident", i.id, {"proveedor": proveedor, "tipo": tipo})
    return i


def provider_indicators(desde=None, hasta=None):
    """Por proveedor: servicios, toneladas, monto, costo por tonelada, servicios sobre tarifa, incidencias y su tasa."""
    q = select(ThirdPartyTransport).where(ThirdPartyTransport.estado != "RECHAZADO")
    acc = defaultdict(lambda: {"servicios": 0, "toneladas": 0.0, "monto": 0.0, "sobre_tarifa": 0, "incidencias": 0,
                               "pagado": 0.0})
    for t in db().execute(q).scalars():
        f = t.fecha_servicio or t.ts.date()
        if (desde and f < desde) or (hasta and f > hasta):
            continue
        a = acc[t.proveedor]
        a["servicios"] += 1
        a["toneladas"] += t.toneladas or 0
        a["monto"] += t.monto or 0
        a["sobre_tarifa"] += bool(t.tarifa and (t.monto or 0) > t.tarifa + 1e-6)
        a["pagado"] += sum(p["monto"] for p in t.pagos or [] if p["estado"] == "PAGADO")
    for i in db().execute(select(ProviderIncident)).scalars():
        if (desde and i.fecha < desde) or (hasta and i.fecha > hasta):
            continue
        acc[i.proveedor]["incidencias"] += 1
    out = []
    for p, a in sorted(acc.items()):
        out.append({"proveedor": p, **{k: round(v, 2) if isinstance(v, float) else v for k, v in a.items()},
                    "costo_tn": round(a["monto"] / a["toneladas"], 2) if a["toneladas"] else None,
                    "tasa_incidencias": round(100 * a["incidencias"] / a["servicios"], 1) if a["servicios"] else None})
    return out


def services_for(user):
    q = select(ThirdPartyTransport).order_by(ThirdPartyTransport.id.desc()).limit(300)
    return list(db().execute(q).scalars())
