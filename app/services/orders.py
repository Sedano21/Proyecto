"""Órdenes de venta: registro, modificación (con autorización), cancelación, decisiones ante faltante y
preparación por prioridad y cortes (IF §4, §5, §6.3, §14)."""
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Alert, Customer, OVChangeRequest, OVDecision, Product, RouteStop, SalesHistory, SalesOrder,
                      SalesOrderLine, User, now)
from . import alerts
from .core import BusinessError, audit, can_self_approve, has_perm, param
from .stock import (ORDEN_ESTADOS_CERRADOS, evaluate_order, line_reserved, priority_key, release_order)

EDITABLE_ESTADOS = ("BORRADOR", "REGISTRADA", "EVALUADA", "EN_PREPARACION", "PREPARADA")


def _validate_header(customer_id, fecha_compromiso):
    if not customer_id or db().get(Customer, int(customer_id)) is None:
        raise BusinessError("Cliente no válido.")
    if not isinstance(fecha_compromiso, date):
        raise BusinessError("La fecha comprometida de despacho es obligatoria.")


def check_not_past(fecha, hora_cita="", hoy=None, ahora=None):
    """Obs. demo v0.7: no se registra ni se reprograma una OV con fecha pasada u hora ya transcurrida (no se puede
    reservar); esos casos van por la Regularización de OV."""
    hoy = hoy or date.today()
    if isinstance(fecha, date) and fecha < hoy:
        raise BusinessError(f"La fecha comprometida {fecha:%d/%m/%Y} ya pasó: no se puede registrar ni reservar. "
                            "Si el pedido ya se atendió o debe registrarse con esa fecha, use «Regularización de OV».")
    h = (hora_cita or "").strip()[:5]
    if isinstance(fecha, date) and fecha == hoy and HORA_RE.match(h or "x"):
        ahora = ahora or datetime.now()
        if h < f"{ahora:%H:%M}":
            raise BusinessError(f"La hora de cita {h} de hoy ya transcurrió: no se puede registrar ni reservar. "
                                "Use «Regularización de OV» o indique una fecha u hora vigente.")


def check_cutoff(fecha, ahora=None, productos=None):
    """Hora de corte de las OV (ronda 23-oct-2026; precisada el 28-oct-2026): después de las 12:00 no se registra una OV
    de PRODUCTO TERMINADO para despachar al día siguiente. No aplica a materia prima ni granel (`tipos_ov_despues_corte`)
    ni a otras fechas de despacho. La OV fuera del corte queda en borrador (no se pierde lo digitado).
    productos: códigos de la OV; sin productos se aplica a toda OV que se despacha mañana."""
    corte = (param("hora_corte_ov_dia_siguiente", "") or "").strip()[:5]
    if not corte or not isinstance(fecha, date):
        return
    ahora = ahora or datetime.now()
    if f"{ahora:%H:%M}" <= corte or fecha != ahora.date() + timedelta(days=1):
        return
    if productos is None:
        raise BusinessError(f"Después de las {corte} no se registra una OV para despachar mañana ({fecha:%d/%m/%Y}). "
                            "Elija otra fecha de despacho.")
    from .stock import product_kind
    exentos = [t.upper() for t in (param("tipos_ov_despues_corte", ["MP", "GR"]) or [])]
    fuera = [c for c in dict.fromkeys(productos) if product_kind(db().get(Product, c)) not in exentos]
    if fuera:
        raise BusinessError(f"Después de las {corte} no se registra producto terminado para despachar mañana "
                            f"({fecha:%d/%m/%Y}): {', '.join(fuera[:5])}. La materia prima y el granel sí. "
                            "Cambie la fecha de despacho o regístrela mañana antes de las " + corte + ".")


def order_by_number(numero):
    """OV por su número del módulo o por el número que SAP le asignó al crearla (V10)."""
    from sqlalchemy import or_
    numero = (numero or "").strip()
    if not numero:
        return None
    return db().execute(select(SalesOrder).where(or_(SalesOrder.numero == numero, SalesOrder.sap_docnum == numero))
                        .order_by(SalesOrder.id)).scalars().first()


def unit_for(product):
    """Unidad de venta fija según el prefijo del código (ronda 23-oct-2026): KG o UND."""
    mapa = {k.upper(): v for k, v in (param("um_por_prefijo", {}) or {}).items()}
    letras = re.match(r"[A-Za-z]+", product.code or "")
    pref = letras.group(0).upper() if letras else ""
    for n in (3, 2):
        if pref[:n] in mapa and len(pref) >= n:
            return mapa[pref[:n]]
    return "KG" if (product.um or "").upper().startswith("K") else "UND"


def apply_unit_rule(lines):
    """La unidad no se elige: KG (permite vender por saco el granel) o UND según el código."""
    out = []
    for ln in lines:
        code = (ln.get("product_code") or "").strip().upper()
        p = db().get(Product, code) if code else None
        if p is None:
            out.append(ln)
            continue
        um = unit_for(p)
        pedido = (ln.get("um_venta") or "").upper()
        if um == "UND" and pedido in ("KG", "SACO"):
            raise BusinessError(f"{code} se vende por unidades (la unidad la fija el código del producto).")
        if um == "KG" and pedido in ("UND", "UNIDAD"):
            raise BusinessError(f"{code} se vende por kilos (la unidad la fija el código del producto).")
        out.append(dict(ln, um_venta=pedido if pedido == "SACO" else um))
    return out


def customer_can_order(customer, muestra=False):
    """Ronda 23-oct-2026: un prospecto o un cliente sin condición de pago aprobada por Finanzas solo tiene OV de muestra."""
    if muestra:
        return
    if customer.es_prospecto:
        raise BusinessError(f"{customer.nombre} es un prospecto: solo admite OV de muestra hasta que pase a cliente "
                            "(acción registrada y orden de compra, en Oportunidades).")
    if param("condicion_pago_requerida", True) and customer.condicion_estado != "APROBADA":
        raise BusinessError(f"{customer.nombre} no tiene condición de pago aprobada por Finanzas "
                            f"(estado: {customer.condicion_estado.replace('_', ' ').lower()}). Solo puede registrar OV de muestra.")


HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(-([01]\d|2[0-3]):[0-5]\d)?$")


def horas_cita(desde=6, hasta=20, paso=30):
    """Opciones de hora de cita en formato 24 h (lista desplegable: evita mezclar 12 h y 24 h)."""
    out = []
    for m in range(desde * 60, hasta * 60 + 1, paso):
        out.append(f"{m // 60:02d}:{m % 60:02d}")
    return out


def normalize_hour(h):
    h = (h or "").strip()
    if not h:
        return ""
    if not HORA_RE.match(h):
        raise BusinessError(f"Hora de cita '{h}' inválida: use el formato de 24 horas HH:MM (p. ej. 14:30).")
    return h


def kg_por_saco(product_code):
    from ..models import PriceItem
    it = db().execute(select(PriceItem).where(PriceItem.lista == "GRANEL", PriceItem.vigente.is_(True),
                                              PriceItem.product_code == product_code)).scalars().first()
    return it.kg_saco if it and it.kg_saco else None


def convert_sale_units(ln):
    """Venta por saco: cantidad y precio se guardan por kg (UM del stock y de la lista granel); se conservan la cantidad
    en sacos y la unidad de venta para la OV impresa."""
    um = (ln.get("um_venta") or "").upper()
    if um != "SACO":
        return ln
    code = (ln.get("product_code") or "").strip().upper()
    kg = kg_por_saco(code)
    if not kg:
        raise BusinessError(f"{code}: no hay kg por saco en la lista mayorista granel para vender por saco.")
    try:
        sacos = float(ln.get("cantidad"))
    except (TypeError, ValueError):
        raise BusinessError(f"Cantidad inválida para {code}.")
    precio = float(ln.get("precio_unitario") or 0)
    return dict(ln, cantidad=sacos * kg, cantidad_venta=sacos, precio_unitario=precio / kg if precio else 0)


def resolve_delivery(customer, site_id=None, lugar="", direccion="", distrito="", provincia="", guardar=False, user=None,
                     exigir=True):
    """Lugar de entrega de la OV: un lugar registrado del cliente u 'otro' con su dirección. Dirección, distrito y
    provincia son obligatorios para calcular la ruta (observaciones al demo v0.5)."""
    from ..models import CustomerSite
    site = db().get(CustomerSite, int(site_id)) if site_id and str(site_id).isdigit() else None
    if site is not None and site.customer_id != customer.id:
        raise BusinessError("El lugar de entrega no pertenece al cliente.")
    if site is not None:
        datos = {"site_id": site.id, "lugar_entrega": site.nombre, "direccion": site.direccion, "distrito": site.distrito,
                 "provincia": site.provincia}
    elif (lugar or "").strip():  # "otro" lugar: su dirección se ingresa completa (no se toma la fiscal)
        datos = {"site_id": None, "lugar_entrega": lugar.strip(), "direccion": (direccion or "").strip(),
                 "distrito": (distrito or "").strip(), "provincia": (provincia or "").strip()}
    else:
        datos = {"site_id": None, "lugar_entrega": "",
                 "direccion": (direccion or customer.direccion or "").strip(),
                 "distrito": (distrito or customer.distrito or "").strip(),
                 "provincia": (provincia or customer.provincia or "").strip()}
    falta = [k for k in ("direccion", "distrito", "provincia") if not datos[k]]
    if falta and exigir:
        raise BusinessError("Complete " + ", ".join(falta) + " del lugar de entrega (necesarios para calcular la ruta).")
    if site is None and guardar and not falta:
        # V7: otra dirección de entrega se agrega sola a la ficha como «Dirección N» sin borrar las anteriores; si ya
        # existe (misma dirección y distrito) se reutiliza. La dirección fiscal es la «Dirección 1».
        def _k(d, di):
            return (" ".join((d or "").upper().split()), " ".join((di or "").upper().split()))
        clave = _k(datos["direccion"], datos["distrito"])
        if clave == _k(customer.direccion, customer.distrito):
            return datos
        existente = next((x for x in customer.sites if x.activo and _k(x.direccion, x.distrito) == clave), None)
        if existente is not None:
            datos.update({"site_id": existente.id, "lugar_entrega": datos["lugar_entrega"] or existente.nombre})
            return datos
        n = len(customer.sites) + 2
        site = CustomerSite(customer_id=customer.id, nombre=datos["lugar_entrega"] or f"Dirección {n}",
                            direccion=datos["direccion"], distrito=datos["distrito"], provincia=datos["provincia"])
        db().add(site)
        db().flush()
        datos["site_id"] = site.id
        datos["lugar_entrega"] = site.nombre
        audit(user, "CLIENTE_LUGAR_AGREGADO", "Customer", customer.ruc, {"lugar": site.nombre, "direccion": site.direccion})
    return datos


def _validate_lines(lines, exigir_precio=False):
    if not lines:
        raise BusinessError("La OV debe tener al menos una línea con producto, cantidad y precio.")
    seen = set()
    for i, ln in enumerate(lines, start=1):
        code = (ln.get("product_code") or "").strip()
        if not code:
            raise BusinessError(f"Línea {i}: falta el producto.")
        if db().get(Product, code) is None:
            raise BusinessError(f"Producto '{code}' no existe en el catálogo.")
        if exigir_precio:  # obs. demo v0.7: producto, cantidad y precio son obligatorios en el módulo
            try:
                pr = float(ln.get("precio_unitario"))
            except (TypeError, ValueError):
                pr = 0.0
            if pr <= 0:
                raise BusinessError(f"Línea {i} ({code}): falta el precio unitario.")
        if code in seen:
            raise BusinessError(f"Producto {code} repetido en la OV; consolide la cantidad en una línea.")
        seen.add(code)
        try:
            q = float(ln.get("cantidad"))
        except (TypeError, ValueError):
            raise BusinessError(f"Cantidad inválida para {code}.")
        if q <= 0:
            raise BusinessError(f"La cantidad de {code} debe ser mayor que cero.")


def next_cutoff(ts=None):
    cortes = sorted(param("cortes_preparacion", []) or [])
    if not cortes:
        return ""
    t = (ts or datetime.now()).strftime("%H:%M")
    for c in cortes:
        if t <= c:
            return c
    return cortes[0] + " (+1d)"


def create_order(user, numero, customer_id, fecha_compromiso, lines, urgente=False, comentarios="", hora_cita="",
                 cita_confirmada=False, vendedor_id=None, fecha_emision=None, origen="MODULO", evaluar=True,
                 tipo_venta="", vendedor_nombre="", entrega=None, canal_precio="", regularizacion="", oc_archivo="", oc_numero=""):
    """entrega: dict de resolve_delivery (lugar, dirección, distrito, provincia). En el módulo es obligatorio.
    regularizacion: motivo; registra una OV con fecha pasada u hora transcurrida sin reservar stock (obs. demo v0.7)."""
    regularizacion = (regularizacion or "").strip()
    if regularizacion and not has_perm(user, "ov.regularizar"):
        raise BusinessError("Su rol no registra regularizaciones de OV.")
    if origen == "MODULO" and not has_perm(user, "ov.crear"):
        raise BusinessError("Su rol no puede registrar OV.")
    numero = (numero or "").strip()
    if not numero:
        raise BusinessError("El número de OV es obligatorio.")
    if db().execute(select(SalesOrder).where(SalesOrder.numero == numero)).scalars().first():
        raise BusinessError(f"La OV {numero} ya existe.")
    _validate_header(customer_id, fecha_compromiso)
    muestra = "MUESTRA" in (tipo_venta or "").upper()
    fuera_de_corte = ""
    if origen == "MODULO" and not regularizacion:
        check_not_past(fecha_compromiso, hora_cita)
        try:
            check_cutoff(fecha_compromiso, productos=[ln["product_code"].strip() for ln in lines])
        except BusinessError as e:  # V7: no se pierde lo digitado; queda como borrador
            fuera_de_corte = str(e)
        customer_can_order(db().get(Customer, int(customer_id)), muestra)
    if origen == "MODULO":
        lines = apply_unit_rule(lines)
    lines = [convert_sale_units(ln) for ln in lines]
    # precio obligatorio en el módulo (obs. demo v0.7), salvo la muestra comercial (decisión 13-oct: precio 0 y la OV
    # queda detenida hasta la confirmación del Coordinador o Jefe Comercial)
    _validate_lines(lines, exigir_precio=origen == "MODULO" and "MUESTRA" not in (tipo_venta or "").upper())
    c = db().get(Customer, int(customer_id))
    if origen == "MODULO":
        hora_cita = normalize_hour(hora_cita)
    entrega = entrega or resolve_delivery(c, exigir=False)
    vend = db().get(User, int(vendedor_id)) if vendedor_id else (user if user and user.role_code == "EJECUTIVO_VENTAS" else None)
    o = SalesOrder(numero=numero, customer_id=c.id, fecha_compromiso=fecha_compromiso, urgente=bool(urgente),
                   comentarios=comentarios, hora_cita=hora_cita or c.horario_recepcion, cita_confirmada=bool(cita_confirmada),
                   direccion=entrega["direccion"], distrito=entrega["distrito"], provincia=entrega["provincia"],
                   lugar_entrega=entrega["lugar_entrega"], site_id=entrega["site_id"], vendedor_id=vend.id if vend else None,
                   vendedor_nombre=vend.nombre if vend else vendedor_nombre, fecha_emision=fecha_emision or date.today(),
                   tipo_venta=tipo_venta or "", canal_precio=(canal_precio or "").strip(),
                   origen=origen, creado_por=user.id if user else None, corte=next_cutoff(),
                   oc_archivo=oc_archivo or "", oc_numero=(oc_numero or "").strip())
    for ln in lines:
        o.lines.append(SalesOrderLine(product_code=ln["product_code"].strip(), cantidad=float(ln["cantidad"]),
                                      precio_unitario=float(ln.get("precio_unitario") or 0),
                                      descuento=float(ln.get("descuento") or 0), tax_code=ln.get("tax_code") or "",
                                      um_venta=ln.get("um_venta") or "", cantidad_venta=ln.get("cantidad_venta")))
    db().add(o)
    db().flush()
    if regularizacion:
        o.estado = "REGULARIZADA"
        o.estado_stock = ""
        o.regularizacion = {"motivo": regularizacion, "user": user.nombre, "user_id": user.id, "ts": now().isoformat()}
        if fecha_compromiso >= date.today():
            # V7: una regularización solo registra pedidos de fechas PASADAS; con fecha de hoy o posterior es una OV
            # normal. No se descarta lo digitado: queda como borrador observado y se alerta a quien la registró.
            o.estado = "REGULARIZACION_OBSERVADA"
            o.motivo_detencion = ("Borrador: la regularización exige una fecha anterior a hoy. Corrija la fecha o "
                                  "registre una OV normal.")
            audit(user, "OV_REGULARIZACION_OBSERVADA", "SalesOrder", o.numero, {"fecha_compromiso": fecha_compromiso})
            alerts.emit("OV_REGULARIZACION_FECHA", f"Regularización {o.numero}: corrija la fecha",
                        f"La fecha {fecha_compromiso:%d/%m/%Y} no es anterior a hoy. Se guardó como borrador; corrija "
                        "la fecha o regístrela como OV normal.", "SalesOrder", o.id, prioridad="ALTA",
                        extra_users=[user.id], creado_por=user, dedup_key=f"OV_REG_FECHA:{o.id}")
            return o
        audit(user, "OV_REGULARIZACION", "SalesOrder", o.numero, {"lineas": lines, "fecha_compromiso": fecha_compromiso,
                                                                   "motivo": regularizacion})
        alerts.emit("OV_REGULARIZACION", f"OV {o.numero} registrada como regularización",
                    f"Fecha comprometida {fecha_compromiso:%d/%m/%Y}. Motivo: {regularizacion}. No reserva stock.",
                    "SalesOrder", o.id, creado_por=user)
        return o
    if oc_archivo:
        from ..models import OrderAttachment
        db().add(OrderAttachment(order_id=o.id, tipo="OC", nombre=o.oc_numero or "Orden de compra", archivo=oc_archivo,
                                 user_id=user.id if user else None))
    if origen == "MODULO" and not fuera_de_corte:
        from .guides import alert_after_cutoff  # V12: pedido para mañana después del corte de rutas
        alert_after_cutoff(o, "Pedido registrado", user)
    audit(user, "OV_CREADA", "SalesOrder", o.numero, {"lineas": lines, "fecha_compromiso": fecha_compromiso,
                                                      "urgente": urgente, "canal_precio": o.canal_precio,
                                                      "oc": bool(oc_archivo)})
    if fuera_de_corte:
        o.estado = "BORRADOR"
        o.estado_stock = ""
        o.motivo_detencion = ("Borrador: " + fuera_de_corte)[:250]
        audit(user, "OV_BORRADOR_CORTE", "SalesOrder", o.numero, {"fecha_compromiso": fecha_compromiso})
        return o
    if origen == "MODULO" and not muestra and not oc_archivo and param("exigir_oc_ov_modulo", True):
        # ronda 23-oct-2026 (decisión 2): sin orden de compra la OV se guarda como borrador y no se ejecuta
        o.estado = "BORRADOR"
        o.estado_stock = ""
        o.motivo_detencion = "Borrador: falta adjuntar la orden de compra del cliente"
        return o
    _activate(o, user, evaluar)
    return o


def _activate(o, user, evaluar=True):
    from .prices import check_order_prices
    check_order_prices(o, user)  # Q11: la lista es el precio mínimo; alerta si la OV está en el límite o debajo
    if o.origen == "MODULO" and not check_emission_window(o, user):
        return  # emitida con menos anticipación que la mínima: se renegocia la fecha antes de ejecutarla
    if evaluar:
        evaluate_order(o, user, "CREACION")
        if check_feasibility(o, user):
            return  # ninguna opción cumple la fecha: bloqueada hasta renegociar o hasta la decisión de Gerencia General
    from .commitment import open_commitment
    open_commitment(o)


# ---------------- OV bloqueada: sin opción que cumpla la fecha y límite de emisión (ronda 26-oct-2026) ----------------
def _hist(order, evento, user, **extra):
    b = dict(order.bloqueo_ov or {})
    b["historial"] = list(b.get("historial") or []) + [dict({"evento": evento, "user": user.nombre if user else "Sistema",
                                                             "ts": now().isoformat(timespec="minutes")}, **extra)]
    return b


def _block(order, user, tipo, estado, motivo, **extra):
    """Bloquea la OV: libera sus reservas (no compromete stock) y la detiene hasta que se resuelva."""
    release_order(order, f"OV bloqueada: {motivo}")
    order.estado = "BLOQUEADA"
    order.motivo_detencion = motivo
    b = _hist(order, f"BLOQUEO_{tipo}", user, motivo=motivo)
    b.update({"tipo": tipo, "estado": estado, "motivo": motivo}, **extra)
    order.bloqueo_ov = b
    db().flush()


def check_emission_window(order, user, hoy=None):
    """La OV se emite como mínimo `dias_minimos_emision_ov` (1) día antes de la fecha de entrega; si no, se bloquea y se
    alerta a Comercial para renegociar la fecha. Devuelve True si está dentro del plazo."""
    hoy = hoy or date.today()
    dias = int(param("dias_minimos_emision_ov", 1) or 0)
    if not dias or order.fecha_compromiso >= hoy + timedelta(days=dias):
        return True
    motivo = (f"Se emitió el {hoy:%d/%m/%Y} para entregar el {order.fecha_compromiso:%d/%m/%Y}: el límite es {dias} día(s) "
              "antes de la fecha de entrega. Renegocie la fecha con el cliente.")
    _block(order, user, "EMISION", "RENEGOCIAR", motivo)
    alerts.emit("OV_RENEGOCIAR_FECHA", f"OV {order.numero}: renegociar la fecha de entrega", motivo, "SalesOrder", order.id,
                prioridad="ALTA", extra_users=[order.vendedor_id] if order.vendedor_id else None,
                dedup_key=f"OV_RENEG:{order.id}:{order.fecha_compromiso.isoformat()}", creado_por=user)
    audit(user, "OV_BLOQUEADA_EMISION", "SalesOrder", order.numero, {"fecha": order.fecha_compromiso, "dias_minimos": dias})
    return False


def unfeasible_lines(order):
    """Líneas para las que el análisis de opciones no encuentra ninguna combinación viable que llegue a la fecha."""
    from .options import evaluate
    out = []
    for x in evaluate(order):
        ok = [o for o in x["opciones"] if o["viable"] and o["cumple"] and (o["vida"] is None or o["vida"]["cumple"] is not False)]
        cubre = sum(o["cantidad"] for o in ok)
        if cubre < x["pendiente"] - 1e-9:
            out.append({"line_id": x["line"].id, "producto": x["line"].product_code, "pendiente": round(x["pendiente"], 3),
                        "cubre_a_tiempo": round(cubre, 3), "analisis": x["porque"],
                        "opciones": [{"ruta": o["nombre"], "fecha": o["fecha"].isoformat() if o["fecha"] else None,
                                      "viable": o["viable"], "cumple": o["cumple"]} for o in x["opciones"]]})
    return out


def check_feasibility(order, user):
    """Si el sistema ya analizó que ninguna opción de Operaciones cumple la fecha, la OV se bloquea (no compromete stock)
    y Comercial decide: renegociar la fecha o mantenerla y pedir la decisión de Gerencia General. Devuelve True si bloqueó."""
    if not param("bloquear_ov_sin_opcion", True) or (order.bloqueo_ov or {}).get("estado") == "APROBADA":
        return False
    falta = unfeasible_lines(order)
    if not falta:
        return False
    det = "; ".join(f"{x['producto']}: a tiempo {x['cubre_a_tiempo']:g} de {x['pendiente']:g}" for x in falta)
    motivo = f"Ninguna opción de Operaciones cumple la fecha {order.fecha_compromiso:%d/%m/%Y} ({det})."
    _block(order, user, "SIN_OPCION", "SIN_OPCION", motivo, lineas=falta)
    alerts.emit("OV_SIN_OPCION", f"OV {order.numero} bloqueada: ninguna opción cumple la fecha",
                motivo + " Renegocie la fecha con el cliente o, si debe entregarse en esa fecha, solicite la decisión de "
                "Gerencia General.", "SalesOrder", order.id, prioridad="ALTA",
                extra_users=[order.vendedor_id] if order.vendedor_id else None,
                dedup_key=f"OV_SIN_OPCION:{order.id}:{order.fecha_compromiso.isoformat()}", creado_por=user)
    audit(user, "OV_BLOQUEADA_SIN_OPCION", "SalesOrder", order.numero, {"lineas": falta})
    return True


def request_gg_decision(order, user, justificacion):
    """Comercial mantiene la fecha («sí o sí»): la OV sigue bloqueada y se pide la decisión de Gerencia General."""
    if not (has_perm(user, "ov.renegociar") or has_perm(user, "ov.modificar")):
        raise BusinessError("La decisión la solicita Comercial.")
    b = order.bloqueo_ov or {}
    if order.estado != "BLOQUEADA" or b.get("estado") != "SIN_OPCION":
        raise BusinessError("La OV no está bloqueada por falta de opción.")
    if not (justificacion or "").strip():
        raise BusinessError("Explique por qué el cliente necesita esa fecha.")
    nb = _hist(order, "SOLICITUD_GG", user, justificacion=justificacion.strip())
    nb.update({"estado": "PENDIENTE_GG", "solicitud": {"user": user.nombre, "user_id": user.id,
                                                       "ts": now().isoformat(timespec="minutes"),
                                                       "justificacion": justificacion.strip()}})
    order.bloqueo_ov = nb
    alerts.close_by_system(f"OV_SIN_OPCION:{order.id}:{order.fecha_compromiso.isoformat()}", "Se pidió la decisión de Gerencia General")
    alerts.emit("OV_DECISION_GG", f"Decidir OV {order.numero}: ninguna opción cumple el {order.fecha_compromiso:%d/%m/%Y}",
                f"{order.customer.nombre}. {b.get('motivo', '')} Comercial: {justificacion.strip()}", "SalesOrder", order.id,
                prioridad="ALTA", dedup_key=f"OV_DECISION_GG:{order.id}:{nb['solicitud']['ts']}", creado_por=user)
    audit(user, "OV_DECISION_GG_SOLICITADA", "SalesOrder", order.numero, {"justificacion": justificacion})
    return order


PRIORIDADES_GG = {"NORMAL": "Normal", "ALTA": "Prioritaria (se atiende antes que las demás)"}


def decide_gg(order, user, aprobar, comentario="", prioridad="NORMAL"):
    """Gerencia General aprueba (va, con su prioridad) o no (Comercial renegocia la fecha con el cliente)."""
    if not has_perm(user, "ov.decision_gg"):
        raise BusinessError("Esta decisión la toma Gerencia General.")
    b = order.bloqueo_ov or {}
    if order.estado != "BLOQUEADA" or b.get("estado") != "PENDIENTE_GG":
        raise BusinessError("La OV no está pendiente de la decisión de Gerencia General.")
    if not aprobar and not (comentario or "").strip():
        raise BusinessError("Indique por qué no procede.")
    prioridad = (prioridad or "NORMAL").upper()
    if prioridad not in PRIORIDADES_GG:
        raise BusinessError("Prioridad no válida.")
    ts = (b.get("solicitud") or {}).get("ts", "")
    alerts.close_by_system(f"OV_DECISION_GG:{order.id}:{ts}", "Decidida por Gerencia General")
    nb = _hist(order, "DECISION_GG", user, aprobada=bool(aprobar), prioridad=prioridad, comentario=(comentario or "").strip())
    nb["decision"] = {"aprobada": bool(aprobar), "prioridad": prioridad, "comentario": (comentario or "").strip(),
                      "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    destinatarios = [order.vendedor_id] if order.vendedor_id else None
    if not aprobar:
        nb["estado"] = "RENEGOCIAR"
        order.bloqueo_ov = nb
        order.motivo_detencion = "Gerencia General no aprobó la fecha: renegociar con el cliente."
        alerts.emit("OV_DECISION_GG_RESUELTA", f"OV {order.numero}: Gerencia General NO aprueba la fecha — renegociar",
                    f"{comentario.strip()}. Renegocie la fecha de entrega con el cliente.", "SalesOrder", order.id,
                    prioridad="ALTA", extra_users=destinatarios, creado_por=user)
        audit(user, "OV_DECISION_GG", "SalesOrder", order.numero, nb["decision"])
        return order
    nb["estado"] = "APROBADA"
    order.bloqueo_ov = nb
    order.estado = "REGISTRADA"
    order.motivo_detencion = ""
    if prioridad == "ALTA":
        order.urgente = True  # se prioriza en reservas, preparación y rutas
    evaluate_order(order, user, "DECISION_GG")
    from .commitment import open_commitment
    open_commitment(order)
    alerts.emit("OV_DECISION_GG_RESUELTA", f"OV {order.numero}: Gerencia General aprueba la fecha"
                + (" — PRIORITARIA" if prioridad == "ALTA" else ""),
                f"Entregar el {order.fecha_compromiso:%d/%m/%Y}. {comentario or ''} Operaciones: organizar las opciones "
                "(producción, compra, traslado) para cumplir.", "SalesOrder", order.id,
                prioridad="ALTA" if prioridad == "ALTA" else None, extra_users=destinatarios,
                extra_roles=["JEFE_LOGISTICA", "JEFE_PRODUCCION", "COORD_ALMACEN"], creado_por=user)
    audit(user, "OV_DECISION_GG", "SalesOrder", order.numero, nb["decision"])
    return order


def attach_oc(order, user, archivo, numero=""):
    """Adjunta la orden de compra; si la OV estaba en borrador, se registra y se evalúa (ronda 23-oct-2026)."""
    from ..models import OrderAttachment
    if not archivo:
        raise BusinessError("Adjunte el archivo de la orden de compra (PDF, imagen o la plantilla del pedido).")
    if order.estado in ORDEN_ESTADOS_CERRADOS:
        raise BusinessError(f"La OV está {order.estado}.")
    db().add(OrderAttachment(order_id=order.id, tipo="OC", nombre=(numero or "").strip() or "Orden de compra", archivo=archivo,
                             user_id=user.id))
    order.oc_archivo = archivo
    order.oc_numero = (numero or order.oc_numero or "").strip()
    audit(user, "OV_OC_ADJUNTA", "SalesOrder", order.numero, {"archivo": archivo, "numero": order.oc_numero})
    if order.estado == "BORRADOR":
        _complete_draft(order, user)
    return order


def complete_draft(order, user):
    """Registra un borrador que ya cumple todo (p. ej. el que quedó fuera del corte, al día siguiente antes de las 12:00)."""
    if not (has_perm(user, "ov.crear") or has_perm(user, "ov.modificar")):
        raise BusinessError("Su rol no registra OV.")
    if order.estado != "BORRADOR":
        raise BusinessError("La OV no está en borrador.")
    if not _complete_draft(order, user):
        raise BusinessError(order.motivo_detencion or "La OV aún no cumple lo necesario para registrarse.")
    audit(user, "OV_BORRADOR_REGISTRADA", "SalesOrder", order.numero, {})
    return order


def _complete_draft(order, user):
    """Registra y evalúa un borrador cuando ya cumple todo: orden de compra (si se exige), fecha vigente y fuera del
    corte de las 12:00 (V7: la OV fuera de corte queda en borrador hasta corregir la fecha)."""
    muestra = "MUESTRA" in (order.tipo_venta or "").upper()
    if not order.oc_archivo and not muestra and order.origen == "MODULO" and param("exigir_oc_ov_modulo", True):
        order.motivo_detencion = "Borrador: falta adjuntar la orden de compra del cliente"
        return False
    check_not_past(order.fecha_compromiso, order.hora_cita)
    if order.origen == "MODULO":
        try:
            check_cutoff(order.fecha_compromiso, productos=[l.product_code for l in order.lines if l.activa])
        except BusinessError as e:  # se conservan los cambios; sigue en borrador hasta el horario permitido
            order.motivo_detencion = ("Borrador: " + str(e))[:250]
            return False
    customer_can_order(order.customer, muestra)
    order.estado = "REGISTRADA"
    order.estado_stock = "SIN_EVALUAR"
    order.motivo_detencion = ""
    order.creado_ts = now()
    _activate(order, user)
    return True


def _apply_changes(order, user, changes):
    """changes: {fecha_compromiso, urgente, comentarios, hora_cita, cita_confirmada, lines:[{product_code,cantidad,precio_unitario}]}"""
    if order.estado not in EDITABLE_ESTADOS:
        raise BusinessError(f"La OV está {order.estado}; ya no se puede modificar.")
    antes = snapshot(order)
    if "fecha_compromiso" in changes and changes["fecha_compromiso"]:
        fc = changes["fecha_compromiso"]
        prods = [l.product_code for l in order.lines if l.activa] if order.origen == "MODULO" else None
        if order.estado == "BORRADOR":
            pass  # el corte se revisa al registrar el borrador (_complete_draft); se conservan los cambios
        elif isinstance(fc, str) and fc and date.fromisoformat(fc[:10]) != order.fecha_compromiso:
            check_cutoff(date.fromisoformat(fc[:10]), productos=prods)
        elif isinstance(fc, date) and fc != order.fecha_compromiso:
            check_cutoff(fc, productos=prods)
        if isinstance(fc, str):
            fc = date.fromisoformat(fc)
        if fc != order.fecha_compromiso:
            check_not_past(fc)
        order.fecha_compromiso = fc
    for k in ("urgente", "cita_confirmada"):
        if k in changes:
            setattr(order, k, bool(changes[k]))
    if changes.get("hora_cita"):
        changes["hora_cita"] = normalize_hour(changes["hora_cita"])
    for k in ("comentarios", "hora_cita"):
        if k in changes and changes[k] is not None:
            setattr(order, k, changes[k])
    if "lines" in changes and changes["lines"] is not None:
        if order.origen == "MODULO":
            changes["lines"] = apply_unit_rule(changes["lines"])
        changes["lines"] = [convert_sale_units(ln) for ln in changes["lines"]]
        _validate_lines(changes["lines"])
        if order.origen == "MODULO":  # las líneas nuevas requieren precio (las existentes conservan el suyo)
            actuales = {l.product_code for l in order.lines if l.activa}
            nuevas = [ln for ln in changes["lines"] if ln["product_code"].strip() not in actuales]
            if nuevas:
                _validate_lines(nuevas, exigir_precio=True)
        nuevas = {ln["product_code"].strip(): ln for ln in changes["lines"]}
        for line in order.lines:
            if line.product_code in nuevas:
                ln = nuevas.pop(line.product_code)
                if float(ln["cantidad"]) < line.preparado - 1e-9:
                    raise BusinessError(f"{line.product_code}: no puede ser menor a lo ya preparado ({line.preparado:g}).")
                line.cantidad = float(ln["cantidad"])
                if ln.get("precio_unitario") not in (None, ""):
                    line.precio_unitario = float(ln["precio_unitario"])
                for k in ("tax_code", "um_venta"):
                    if ln.get(k):
                        setattr(line, k, ln[k])
                if ln.get("descuento") not in (None, ""):
                    line.descuento = float(ln["descuento"])
                line.activa = True
            elif line.activa:
                if line.preparado > 0:
                    raise BusinessError(f"{line.product_code} ya tiene preparación registrada; no se puede eliminar.")
                line.activa = False
        for code, ln in nuevas.items():
            order.lines.append(SalesOrderLine(product_code=code, cantidad=float(ln["cantidad"]),
                                              precio_unitario=float(ln.get("precio_unitario") or 0),
                                              descuento=float(ln.get("descuento") or 0), tax_code=ln.get("tax_code") or "",
                                              um_venta=ln.get("um_venta") or ""))
    order.version += 1
    db().flush()
    audit(user, "OV_MODIFICADA", "SalesOrder", order.numero, {"antes": antes, "despues": snapshot(order)})
    if order.estado == "BORRADOR":  # se registra y evalúa cuando cumple todo (orden de compra, fecha, corte)
        _complete_draft(order, user)
        return
    from .prices import check_order_prices
    check_order_prices(order, user)
    evaluate_order(order, user, "MODIFICACION")


def snapshot(order):
    return {"fecha_compromiso": order.fecha_compromiso.isoformat() if order.fecha_compromiso else None,
            "urgente": order.urgente, "lineas": [{"producto": l.product_code, "cantidad": l.cantidad, "precio": l.precio_unitario or 0}
                                                 for l in order.lines if l.activa]}


def modify_order(order, user, changes):
    if not has_perm(user, "ov.modificar"):
        raise BusinessError("Su rol no modifica OV directamente; use 'solicitar modificación' (IF §5).")
    if user.role_code == "EJECUTIVO_VENTAS" and order.vendedor_id != user.id:
        raise BusinessError("Solo puede modificar las OV de las que es vendedor responsable.")
    _apply_changes(order, user, changes)


def request_change(order, user, changes, motivo=""):
    """Asistente de Ventas: la modificación queda pendiente de autorización (IF §5)."""
    if not has_perm(user, "ov.solicitar_modificacion"):
        raise BusinessError("Su rol no puede solicitar modificaciones.")
    if order.estado not in EDITABLE_ESTADOS:
        raise BusinessError(f"La OV está {order.estado}; ya no se puede modificar.")
    payload = dict(changes)
    if isinstance(payload.get("fecha_compromiso"), date):
        payload["fecha_compromiso"] = payload["fecha_compromiso"].isoformat()
    if "lines" in payload and payload["lines"] is not None:
        _validate_lines(payload["lines"])
    req = OVChangeRequest(order_id=order.id, solicitado_por=user.id, payload=payload, motivo=motivo)
    db().add(req)
    db().flush()
    alerts.emit("OV_MODIF_SOLICITUD", f"Autorizar modificación de OV {order.numero}",
                f"Solicitada por {user.nombre}. Motivo: {motivo or '-'}", "OVChangeRequest", req.id,
                extra_users=[order.vendedor_id] if order.vendedor_id else None,
                dedup_key=f"OV_MODIF:{req.id}", creado_por=user)
    audit(user, "OV_MODIF_SOLICITADA", "SalesOrder", order.numero, payload)
    return req


def can_authorize_change(user, order):
    if not has_perm(user, "ov.autorizar_modificacion"):
        return False
    if user.role_code == "EJECUTIVO_VENTAS":
        return order.vendedor_id == user.id
    return True


def resolve_change(req, user, aprobar, comentario=""):
    if req.estado != "PENDIENTE":
        raise BusinessError("La solicitud ya fue resuelta.")
    order = req.order
    if not can_authorize_change(user, order):
        raise BusinessError("Solo autorizan el Coordinador de Ventas, el Jefe de Ventas o el vendedor responsable (IF §5).")
    if req.solicitado_por == user.id and not can_self_approve(user):
        raise BusinessError("No puede autorizar su propia solicitud.")
    req.estado = "APROBADA" if aprobar else "RECHAZADA"
    req.resuelto_por = user.id
    req.resuelto_ts = now()
    audit(user, f"OV_MODIF_{req.estado}", "SalesOrder", order.numero, {"solicitud": req.id, "comentario": comentario})
    if aprobar:
        _apply_changes(order, user, req.payload)
    alerts.close_by_system(f"OV_MODIF:{req.id}", "Resuelta")


def cancel_order(order, user, motivo):
    if not has_perm(user, "ov.cancelar"):
        raise BusinessError("Solo el Coordinador de Ventas o el Jefe de Ventas pueden cancelar una OV (IF §5).")
    if order.estado in ORDEN_ESTADOS_CERRADOS or order.estado == "EN_RUTA":
        raise BusinessError(f"La OV está {order.estado}; no se puede cancelar.")
    if not motivo.strip():
        raise BusinessError("Indique el motivo de la cancelación.")
    liberadas = release_order(order, f"OV cancelada: {motivo}")
    paradas = 0
    for stop in list(db().execute(select(RouteStop).where(RouteStop.order_id == order.id)).scalars()):
        if stop.route.estado in ("PROPUESTA", "CONFIRMADA"):
            route = stop.route
            route.stops.remove(stop)
            db().delete(stop)
            route.peso_total = sum(s.peso_kg for s in route.stops)
            paradas += 1
    order.estado = "CANCELADA"
    order.motivo_detencion = f"Cancelada: {motivo}"
    order.cancelacion_motivo = motivo.strip()
    alerts.close_by_system(f"OV_FALTANTE:{order.id}", "OV cancelada")
    alerts.close_by_system(f"OV_DECISION_PARCIAL:{order.id}", "OV cancelada")
    alerts.emit("OV_CANCELADA", f"OV {order.numero} cancelada", f"Motivo: {motivo}. Reservas liberadas: {liberadas}; "
                f"paradas de ruta retiradas: {paradas}.", "SalesOrder", order.id, creado_por=user)
    audit(user, "OV_CANCELADA", "SalesOrder", order.numero, {"motivo": motivo, "reservas_liberadas": liberadas,
                                                             "paradas_retiradas": paradas})
    # el stock liberado puede cubrir otras OV
    from .stock import reevaluate_pending
    if param("reevaluar_tras_carga", True):
        reevaluate_pending(user, [l.product_code for l in order.lines])


# ------------------------------ decisiones ----------------------------------
def partial_approvers():
    return list(param("parcial_aprobadores", ["GERENCIA_OPERACIONES", "JEFE_LOGISTICA"]) or [])


def partial_pending_roles(order):
    hechas = order.parcial_aprobaciones or {}
    if hechas and str(param("parcial_modo", "CUALQUIERA")).upper() != "TODOS":
        return []  # Q3 (12-oct-2026): basta Gerencia de Operaciones o Jefatura de Logística
    return [r for r in partial_approvers() if r not in hechas]


def decide_partial(order, user, aprobar, comentario="", fecha_saldo=None):
    """Despacho parcial (IF §6.3; decisión Q3): aprueba Gerencia de Operaciones o Jefatura de Logística (parámetro
    'parcial_modo' = CUALQUIERA; con TODOS se exige la aprobación de cada rol). Gerencia General (acceso completo, Q4)
    puede aprobar en nombre de ellos. Cualquier aprobador puede rechazar. El saldo no despachado se reprograma en una
    OV de saldo para una próxima entrega (fecha obligatoria)."""
    if not has_perm(user, "ov.aprobar_parcial"):
        raise BusinessError("El despacho parcial lo aprueba Gerencia de Operaciones o Jefatura de Logística (Q3).")
    if order.estado_stock == "COMPLETA":
        raise BusinessError("La OV está completa; no requiere despacho parcial.")
    if order.decision_parcial == "APROBADA":
        raise BusinessError("El despacho parcial ya fue aprobado.")
    pendientes = partial_pending_roles(order)
    if user.role_code == "GERENCIA_GENERAL":
        en_nombre = pendientes if str(param("parcial_modo", "CUALQUIERA")).upper() == "TODOS" else pendientes[:1]
    elif user.role_code in pendientes:
        en_nombre = [user.role_code]
    elif user.role_code in partial_approvers():
        raise BusinessError("Su rol ya registró su aprobación; falta: " + ", ".join(pendientes))
    else:
        raise BusinessError("Su rol no figura entre los aprobadores del despacho parcial.")
    if not aprobar:
        if not comentario.strip():
            raise BusinessError("Indique el motivo del rechazo.")
        order.decision_parcial = "RECHAZADA"
        order.parcial_aprobaciones = {}
        order.motivo_detencion = "Despacho parcial rechazado: requiere renegociación, alternativa o reposición."
        db().add(OVDecision(order_id=order.id, tipo="DESPACHO_PARCIAL", estado="RECHAZADA", comentario=comentario,
                            detalle={"rol": user.role_code}, user_id=user.id))
        alerts.close_by_system(f"OV_DECISION_PARCIAL:{order.id}", "Despacho parcial rechazado")
        audit(user, "OV_PARCIAL_RECHAZADA", "SalesOrder", order.numero, {"comentario": comentario})
        return []
    if order.cobertura_unidades <= 0:
        raise BusinessError("No hay stock reservado para un despacho parcial.")
    if fecha_saldo is None and order.fecha_saldo is None:
        raise BusinessError("Indique la fecha a la que se reprograma el saldo no despachado (Q3).")
    if fecha_saldo is not None:
        if fecha_saldo < date.today():
            raise BusinessError("La fecha reprogramada del saldo no puede ser anterior a hoy.")
        order.fecha_saldo = fecha_saldo
    aprob = dict(order.parcial_aprobaciones or {})
    for rol in en_nombre:
        aprob[rol] = {"user": user.nombre, "user_id": user.id, "rol_usuario": user.role_code,
                      "ts": now().isoformat(), "comentario": comentario}
    order.parcial_aprobaciones = aprob
    faltan = partial_pending_roles(order)
    db().add(OVDecision(order_id=order.id, tipo="DESPACHO_PARCIAL", estado="APROBACION_REGISTRADA",
                        detalle={"en_nombre_de": en_nombre, "faltan": faltan, "fecha_saldo": order.fecha_saldo.isoformat(),
                                 "cobertura_unidades": order.cobertura_unidades}, comentario=comentario, user_id=user.id))
    audit(user, "OV_PARCIAL_APROBACION", "SalesOrder", order.numero, {"en_nombre_de": en_nombre, "faltan": faltan,
                                                                      "fecha_saldo": order.fecha_saldo})
    if faltan:
        order.decision_parcial = "PENDIENTE"
        a = db().execute(select(Alert).where(Alert.dedup_key == f"OV_DECISION_PARCIAL:{order.id}",
                                             Alert.estado.notin_(alerts.CERRADOS))).scalars().first()
        if a is not None:
            from ..models import AlertEvent
            db().add(AlertEvent(alert_id=a.id, user_id=user.id, accion="APROBACION_PARCIAL",
                                comentario=f"Aprobó {user.nombre} ({', '.join(en_nombre)}). Falta: {', '.join(faltan)}."))
        return []
    order.decision_parcial = "APROBADA"
    order.motivo_detencion = ""
    alerts.close_by_system(f"OV_DECISION_PARCIAL:{order.id}", "Despacho parcial aprobado por " + ", ".join(aprob))
    alerts.emit("OV_PARCIAL_APROBADO", f"Despacho parcial aprobado: OV {order.numero}",
                f"Cobertura {order.cobertura_unidades}% unidades. Saldo reprogramado al {order.fecha_saldo:%d/%m/%Y}. "
                "Se generó propuesta de ruta.", "SalesOrder", order.id, creado_por=user)
    from .distribution import active_stop, propose_routes
    from .stock import _after_evaluation
    _after_evaluation(order, user)  # certificado pre-elaborado y programación automática (TO-BE)
    st = active_stop(order)
    if st is not None:
        return [st.route]
    return propose_routes(order.fecha_compromiso, user, orders=[order], require_prepared=False)


def create_saldo(order, user):
    """Crea la OV de saldo con lo no despachado de un despacho parcial (decisión Q3)."""
    s = db()
    lines = [{"product_code": l.product_code, "cantidad": l.cantidad - l.despachado, "precio_unitario": l.precio_unitario}
             for l in order.lines if l.activa and l.cantidad - l.despachado > 1e-9]
    if not lines:
        return None
    n = s.execute(select(SalesOrder).where(SalesOrder.parent_id == order.id)).scalars().all()
    numero = f"{order.numero}-S{len(n) + 1}"
    fecha = order.fecha_saldo or order.fecha_compromiso
    saldo = create_order(user, numero, order.customer_id, fecha, lines, urgente=order.urgente,
                         comentarios=f"Saldo reprogramado del despacho parcial de la OV {order.numero}",
                         hora_cita=order.hora_cita, vendedor_id=order.vendedor_id, origen="SALDO", evaluar=False)
    saldo.parent_id = order.id
    saldo.vendedor_nombre = order.vendedor_nombre
    s.flush()
    from .stock import evaluate_order
    evaluate_order(saldo, user, "CREACION")
    alerts.emit("OV_SALDO_REPROGRAMADO", f"Saldo de OV {order.numero} reprogramado: OV {numero} para el {fecha:%d/%m/%Y}",
                "; ".join("%s × %g" % (l["product_code"], l["cantidad"]) for l in lines)
                + f". Cobertura actual del saldo: {saldo.cobertura_unidades}%.", "SalesOrder", saldo.id,
                extra_users=[order.vendedor_id] if order.vendedor_id else None, creado_por=user)
    audit(user, "OV_SALDO_CREADA", "SalesOrder", numero, {"origen": order.numero, "lineas": lines})
    return saldo


def renegotiate_date(order, user, nueva_fecha, comentario=""):
    if not has_perm(user, "ov.renegociar"):
        raise BusinessError("Su rol no registra renegociaciones.")
    bloqueada = order.estado == "BLOQUEADA"
    if bloqueada and (order.bloqueo_ov or {}).get("estado") == "PENDIENTE_GG":
        raise BusinessError("La OV espera la decisión de Gerencia General.")
    if bloqueada and nueva_fecha == order.fecha_compromiso:
        raise BusinessError("Indique la nueva fecha acordada con el cliente.")
    db().add(OVDecision(order_id=order.id, tipo="RENEGOCIAR_FECHA", detalle={"anterior": order.fecha_compromiso.isoformat(),
                                                                               "nueva": nueva_fecha.isoformat()},
                        comentario=comentario, user_id=user.id, estado="APLICADA"))
    if not bloqueada:
        _apply_changes(order, user, {"fecha_compromiso": nueva_fecha})
        return
    # OV bloqueada: con la nueva fecha se vuelve a analizar (puede quedar activa o volver a bloquearse)
    b = _hist(order, "RENEGOCIADA", user, anterior=order.fecha_compromiso.isoformat(), nueva=nueva_fecha.isoformat())
    b["estado"] = "RENEGOCIADA"
    order.bloqueo_ov = b
    order.estado = "REGISTRADA"
    order.motivo_detencion = ""
    _apply_changes(order, user, {"fecha_compromiso": nueva_fecha})
    if order.origen == "MODULO" and not check_emission_window(order, user):
        return
    if not check_feasibility(order, user):
        from .commitment import open_commitment
        open_commitment(order)


def change_product(order, user, line_id, nuevo_codigo, cantidad, comentario=""):
    if not has_perm(user, "ov.renegociar"):
        raise BusinessError("Su rol no registra cambios de producto.")
    lines = []
    found = False
    for l in order.lines:
        if not l.activa:
            continue
        if l.id == int(line_id):
            found = True
            lines.append({"product_code": nuevo_codigo, "cantidad": cantidad})
        else:
            lines.append({"product_code": l.product_code, "cantidad": l.cantidad, "precio_unitario": l.precio_unitario})
    if not found:
        raise BusinessError("Línea no encontrada.")
    db().add(OVDecision(order_id=order.id, tipo="CAMBIO_PRODUCTO", detalle={"line_id": int(line_id), "nuevo": nuevo_codigo,
                                                                              "cantidad": cantidad},
                        comentario=comentario, user_id=user.id, estado="APLICADA"))
    _apply_changes(order, user, {"lines": lines})


# ------------------------------ preparación ---------------------------------
def ready_for_preparation(order):
    if order.retenida_precio:
        return False  # detenida por precio hasta la confirmación comercial
    return order.estado in ("EVALUADA", "EN_PREPARACION") and (
        order.estado_stock == "COMPLETA" or order.decision_parcial == "APROBADA")


def preparation_queue():
    """Cola de preparación ordenada por prioridad y agrupada por corte (IF §4.9)."""
    orders = list(db().execute(select(SalesOrder).where(SalesOrder.estado.in_(["EVALUADA", "EN_PREPARACION"]))).scalars())
    orders = [o for o in orders if ready_for_preparation(o)]
    orders.sort(key=priority_key)
    return orders


def prep_progress(order):
    obj = sum(_prep_target(l) for l in order.lines if l.activa)
    done = sum(l.preparado for l in order.lines if l.activa)
    return round(100.0 * done / obj, 1) if obj else 0.0


def _prep_target(line):
    """Cantidad a preparar: lo reservado (completo o parcial aprobado)."""
    return line_reserved(line) + 0.0


def validate_picking_plan(order, user):
    """TO-BE: el sistema pre-asigna el picking (lotes reservados) y el Líder Operativo lo valida."""
    if not has_perm(user, "preparacion.registrar"):
        raise BusinessError("Su rol no valida la planificación del picking.")
    if not ready_for_preparation(order):
        raise BusinessError("La OV no está lista para preparar (requiere cobertura completa o despacho parcial aprobado).")
    order.plan_picking_validado = True
    audit(user, "PLAN_PICKING_VALIDADO", "SalesOrder", order.numero,
          {"lotes": [(l.product_code, r.lot.lote, r.cantidad) for l in order.lines for r in l.reservations if r.estado == "ACTIVA"]})


def reassign_pick_lot(order, user, reservation_id, new_lot_id, cantidad=None):
    """TO-BE: 'Modificar planificación del picking' — cambia el lote pre-asignado por otro apto del mismo artículo."""
    from ..models import Reservation, StockLot
    from .stock import _release, free_qty, lot_usable
    if not has_perm(user, "preparacion.registrar"):
        raise BusinessError("Su rol no modifica la planificación del picking.")
    res = db().get(Reservation, int(reservation_id))
    if res is None or res.estado != "ACTIVA" or res.line.order_id != order.id:
        raise BusinessError("Reserva no válida.")
    if res.line.preparado > 1e-9:
        raise BusinessError("La línea ya tiene picking registrado; no se puede cambiar el lote.")
    lot = db().get(StockLot, int(new_lot_id))
    if lot is None or lot.product_code != res.lot.product_code or lot.id == res.lot_id:
        raise BusinessError("Seleccione otro lote del mismo artículo.")
    ok, why = lot_usable(lot, order.fecha_compromiso, order.customer)
    if not ok:
        raise BusinessError(f"Lote no apto: {why}")
    q = res.cantidad if cantidad in (None, "") else float(cantidad)
    if q <= 0 or q > res.cantidad + 1e-9:
        raise BusinessError("Cantidad inválida.")
    if q > free_qty(lot) + 1e-9:
        raise BusinessError(f"El lote {lot.lote} solo tiene {free_qty(lot):g} libres.")
    from .customer_conditions import max_lots
    maxl = max_lots(order.customer)
    if maxl:
        lotes = {r.lot_id for r in res.line.reservations if r.estado == "ACTIVA"}
        if abs(q - res.cantidad) < 1e-9:
            lotes.discard(res.lot_id)
        lotes.add(lot.id)
        if len(lotes) > maxl:
            raise BusinessError(f"El cliente acepta máximo {maxl} lote(s) por SKU.")
    if abs(q - res.cantidad) < 1e-9:
        _release(res, f"Cambio de lote en planificación de picking → {lot.lote}")
    else:
        res.cantidad -= q
    nueva = Reservation(ov_line_id=res.ov_line_id, lot_id=lot.id, cantidad=q, estado="ACTIVA")
    db().add(nueva)
    res.line.reservations.append(nueva)
    lot.reservations.append(nueva)
    order.plan_picking_validado = False
    audit(user, "PLAN_PICKING_MODIFICADO", "SalesOrder", order.numero, {"de": res.lot.lote, "a": lot.lote, "cantidad": q})
    from .quality import autogenerate_for_order
    if param("certificado_previo_al_picking", True):
        autogenerate_for_order(order, user)


def register_picking(order, user, line_id, cantidad, lote):
    if not has_perm(user, "preparacion.registrar"):
        raise BusinessError("Su rol no registra preparación.")
    if not ready_for_preparation(order):
        raise BusinessError("La OV no está lista para preparar (requiere cobertura completa o despacho parcial aprobado).")
    if not order.plan_picking_validado:
        raise BusinessError("Primero valide la planificación de picking pre-asignada por el sistema.")
    line = next((l for l in order.lines if l.id == int(line_id) and l.activa), None)
    if line is None:
        raise BusinessError("Línea no encontrada.")
    lotes_reservados = {r.lot.lote: r for r in line.reservations if r.estado == "ACTIVA"}
    if lote not in lotes_reservados:
        raise BusinessError(f"El lote {lote} no corresponde a los lotes reservados ({', '.join(lotes_reservados) or '-'}). "
                            "Verifique lote/vencimiento (IF §22).")
    if cantidad <= 0:
        raise BusinessError("Cantidad inválida.")
    objetivo = _prep_target(line)
    if line.preparado + cantidad > objetivo + 1e-9:
        raise BusinessError(f"Se excede lo reservado para la línea ({objetivo:g}).")
    line.preparado += cantidad
    if order.estado == "EVALUADA":
        order.estado = "EN_PREPARACION"
        order.prep_inicio = now()
    audit(user, "PICKING", "SalesOrder", order.numero, {"producto": line.product_code, "lote": lote, "cantidad": cantidad})
    avance = prep_progress(order)
    umbral = param("umbral_alerta_preparacion_pct", 80) or 80
    if avance >= umbral and not order.alerta80_emitida and avance < 100:
        order.alerta80_emitida = True
        alerts.emit("OV_80_PREPARACION", f"OV {order.numero} al {avance:.0f}% de preparación",
                    f"Cliente {order.customer.nombre}. Fecha comprometida {order.fecha_compromiso:%d/%m/%Y}.",
                    "SalesOrder", order.id, extra_users=[order.vendedor_id] if order.vendedor_id else None, creado_por=user)
    if avance >= 100 - 1e-9:
        finish_preparation(order, user)
    return avance


def finish_preparation(order, user):
    order.estado = "PREPARADA"
    order.prep_fin = now()
    if not order.alerta80_emitida:
        order.alerta80_emitida = True
    alerts.emit("OV_PREPARADA", f"OV {order.numero} preparada y lista para despacho",
                f"Cliente {order.customer.nombre}; {'parcial' if order.decision_parcial == 'APROBADA' else 'completa'}.",
                "SalesOrder", order.id, extra_users=[order.vendedor_id] if order.vendedor_id else None, creado_por=user)
    from .quality import autogenerate_for_order
    autogenerate_for_order(order, user)
    from . import guides  # V12: pre-guía para Distribución y aviso si se prepara para mañana después del corte de rutas
    guides.generate(order, user)
    guides.alert_after_cutoff(order, "Picking terminado", user)


def order_weight_kg(order, base="reservado"):
    total = 0.0
    sin_peso = []
    for l in order.lines:
        if not l.activa:
            continue
        if base == "preparado":
            q = l.preparado
        elif base == "solicitado":
            q = l.cantidad
        else:
            q = line_reserved(l) if l.preparado <= 0 else l.preparado
        p = l.product
        if p.um == "KILOGRAMO":
            total += q
        elif p.peso_kg:
            total += q * p.peso_kg
        else:
            sin_peso.append(p.code)
    return total, sin_peso


def order_amount(order):
    return sum(l.cantidad * (l.precio_unitario or 0) for l in order.lines if l.activa)


def regularize_release(order, user, nueva_fecha, comentario=""):
    """Regularización: la OV pasa al flujo normal con una fecha vigente (se evalúa y reserva stock)."""
    if not has_perm(user, "ov.regularizar"):
        raise BusinessError("Su rol no gestiona regularizaciones de OV.")
    if order.estado != "REGULARIZADA":
        raise BusinessError("La OV no está en regularización.")
    check_not_past(nueva_fecha)
    anterior = order.fecha_compromiso
    order.fecha_compromiso = nueva_fecha
    order.estado = "REGISTRADA"
    reg = dict(order.regularizacion or {})
    reg.update({"liberada_por": user.nombre, "liberada_ts": now().isoformat(), "fecha_anterior": anterior.isoformat(),
                "comentario": comentario})
    order.regularizacion = reg
    audit(user, "OV_REGULARIZACION_LIBERADA", "SalesOrder", order.numero, {"anterior": anterior, "nueva": nueva_fecha,
                                                                           "comentario": comentario})
    from .prices import check_order_prices
    check_order_prices(order, user)
    evaluate_order(order, user, "REGULARIZACION")


def regularize_fix_date(order, user, nueva_fecha):
    """V7: corrige la fecha de una regularización observada (borrador) y la deja lista para gestionar."""
    if not has_perm(user, "ov.regularizar"):
        raise BusinessError("Su rol no gestiona regularizaciones de OV.")
    if order.estado != "REGULARIZACION_OBSERVADA":
        raise BusinessError("La OV no está observada por fecha.")
    if isinstance(nueva_fecha, str):
        nueva_fecha = date.fromisoformat(nueva_fecha)
    if nueva_fecha >= date.today():
        raise BusinessError("La regularización debe tener una fecha anterior a hoy. Si el pedido aún no se atiende, "
                            "regístrelo como OV normal.")
    anterior = order.fecha_compromiso
    order.fecha_compromiso = nueva_fecha
    order.estado = "REGULARIZADA"
    order.motivo_detencion = ""
    audit(user, "OV_REGULARIZACION_FECHA_CORREGIDA", "SalesOrder", order.numero, {"anterior": anterior, "nueva": nueva_fecha})
    alerts.close_by_system(f"OV_REG_FECHA:{order.id}", f"Fecha corregida por {user.nombre}")
    alerts.emit("OV_REGULARIZACION", f"OV {order.numero} registrada como regularización",
                f"Fecha comprometida {nueva_fecha:%d/%m/%Y}. Motivo: {(order.regularizacion or {}).get('motivo', '')}.",
                "SalesOrder", order.id, creado_por=user)


def regularization_exits(order):
    """Propuesta de salida por línea para cerrar una regularización: lotes FEFO con stock libre (sin tocar reservas
    de otras OV) en los almacenes principales del producto. [{line, lots:[(lot, libre)], propuesta:[(lot, q)], falta}]"""
    from .stock import _sort_lots, free_qty, lots_of, principal_warehouses
    out = []
    for line in order.lines:
        if not line.activa:
            continue
        whs = [w.code for w in principal_warehouses(line.product)] or None
        lots = [l for l in _sort_lots(lots_of(line.product_code, whs)) if l.estado == "DISPONIBLE" and free_qty(l) > 0]
        falta, prop = line.cantidad - line.despachado, []
        for l in lots:
            if falta <= 1e-9:
                break
            q = min(free_qty(l), falta)
            prop.append((l, q))
            falta -= q
        out.append({"line": line, "lots": [(l, free_qty(l)) for l in lots], "propuesta": prop, "falta": max(falta, 0),
                    "por_lote": {l.id: q for l, q in prop}})
    return out


def regularize_close(order, user, comentario, salidas=None, descontar=True):
    """Regularización «la mercadería ya salió»: descuenta del inventario lo que salió físicamente (FEFO por defecto o
    los lotes que indique el usuario), registra la venta en el historial y cierra la OV como registro.
    salidas: [{"line_id", "lot_id", "cantidad"}]; None = propuesta FEFO. descontar=False solo si el stock ya se
    descontó en SAP y la próxima carga lo reflejará (se registra el motivo)."""
    from ..models import StockLot
    from .stock import free_qty
    if not has_perm(user, "ov.regularizar_cerrar"):  # V9 (C02): cierran el Coordinador, el Jefe o el Gerente Comercial
        raise BusinessError("La regularización la cierran el Coordinador, el Jefe o el Gerente Comercial.")
    if order.estado != "REGULARIZADA":
        raise BusinessError("La OV no está en regularización.")
    if param("regularizacion_exige_guia", True) and not (order.regularizacion or {}).get("guia"):
        # V9 (C01): sin la guía de lo que realmente salió no se descuenta: queda en borrador hasta adjuntarla
        raise BusinessError("Adjunte la guía de remisión de lo que salió (o pídala a Distribución) antes de cerrar: "
                            "sin guía no se descuenta el inventario.")
    if not (comentario or "").strip():
        raise BusinessError("Indique cómo se regularizó el pedido.")
    movs = []
    if descontar:
        if salidas is None:
            salidas = [{"line_id": r["line"].id, "lot_id": l.id, "cantidad": q}
                       for r in regularization_exits(order) for l, q in r["propuesta"]]
        lineas = {l.id: l for l in order.lines if l.activa}
        por_linea = {}
        for sl in salidas:
            q = float(sl.get("cantidad") or 0)
            if q <= 0:
                continue
            line = lineas.get(int(sl["line_id"]))
            lot = db().get(StockLot, int(sl["lot_id"]))
            if line is None or lot is None or lot.product_code != line.product_code:
                raise BusinessError("Lote no válido para la línea.")
            if q > free_qty(lot) + 1e-6:
                raise BusinessError(f"El lote {lot.lote} solo tiene {free_qty(lot):g} libres de {line.product_code}.")
            por_linea[line.id] = por_linea.get(line.id, 0) + q
            if por_linea[line.id] > line.cantidad - line.despachado + 1e-6:
                raise BusinessError(f"La salida de {line.product_code} supera la cantidad de la OV.")
            movs.append((line, lot, q))
        if not movs:
            raise BusinessError("No hay stock libre para descontar. Si la salida ya está descontada en SAP, marque "
                                "«ya descontado en SAP».")
        for line, lot, q in movs:
            lot.cantidad = max(lot.cantidad - q, 0)
            if lot.cantidad_verificada is not None:
                lot.cantidad_verificada = max(lot.cantidad_verificada - q, 0)
            line.despachado += q
            line.entregado += q
            db().add(SalesHistory(product_code=line.product_code, fecha=order.fecha_compromiso, cantidad=q,
                                  documento=order.numero, origen="REGULARIZACION"))
    reg = dict(order.regularizacion or {})
    reg.update({"cerrada_por": user.nombre, "cerrada_ts": now().isoformat(), "cierre": comentario.strip(),
                "descontado": descontar,
                "salidas": [{"producto": ln.product_code, "lote": lt.lote, "almacen": lt.warehouse_code, "cantidad": q}
                            for ln, lt, q in movs]})
    order.regularizacion = reg
    order.estado = "REGULARIZADA_CERRADA"
    audit(user, "OV_REGULARIZACION_CERRADA", "SalesOrder", order.numero, {"comentario": comentario,
                                                                          "salidas": reg["salidas"],
                                                                          "descontado": descontar})


def attach_regularization_guide(order, user, numero, archivo):
    """V9 (C01): la guía de remisión de lo que salió la adjunta quien regulariza o Distribución."""
    if not (has_perm(user, "ov.regularizar") or has_perm(user, "distribucion.documentos")):
        raise BusinessError("Adjuntan la guía Comercial (quien regulariza) o Distribución.")
    if order.estado not in ("REGULARIZADA", "REGULARIZACION_OBSERVADA"):
        raise BusinessError("La OV no está en regularización.")
    numero = (numero or "").strip().upper()
    if not numero or not archivo:
        raise BusinessError("Indique el número de la guía y adjunte el archivo.")
    reg = dict(order.regularizacion or {})
    reg["guia"] = {"numero": numero[:40], "archivo": archivo, "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    order.regularizacion = reg
    alerts.close_by_system(f"REG_GUIA:{order.id}", f"Guía {numero} adjuntada por {user.nombre}")
    audit(user, "OV_REGULARIZACION_GUIA", "SalesOrder", order.numero, reg["guia"])


def request_regularization_guide(order, user):
    """V9 (C01): pide a Distribución que adjunte la guía de la regularización."""
    if not has_perm(user, "ov.regularizar"):
        raise BusinessError("Su rol no gestiona regularizaciones de OV.")
    if order.estado != "REGULARIZADA":
        raise BusinessError("La OV no está en regularización.")
    alerts.emit("REGULARIZACION_GUIA", f"Adjuntar la guía de la regularización {order.numero}",
                f"{order.customer.nombre} · pedido del {order.fecha_compromiso:%d/%m/%Y}. Comercial necesita la guía de lo que "
                "salió para descontar el inventario.", "SalesOrder", order.id, dedup_key=f"REG_GUIA:{order.id}",
                creado_por=user)


def request_date_change(order, user, nueva_fecha, motivo):
    """Ronda 23-oct-2026: Logística o Distribución solicita cambiar la fecha de despacho; Comercial aprueba o desaprueba."""
    if not has_perm(user, "ov.solicitar_cambio_fecha"):
        raise BusinessError("Solicitan el cambio de fecha Logística o Distribución.")
    if order.estado not in EDITABLE_ESTADOS:
        raise BusinessError(f"La OV está {order.estado}; ya no se puede modificar.")
    if isinstance(nueva_fecha, str):
        nueva_fecha = date.fromisoformat(nueva_fecha)
    if not isinstance(nueva_fecha, date) or nueva_fecha == order.fecha_compromiso:
        raise BusinessError("Indique una fecha de despacho distinta de la actual.")
    check_not_past(nueva_fecha)
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo del cambio de fecha.")
    req = OVChangeRequest(order_id=order.id, solicitado_por=user.id, payload={"fecha_compromiso": nueva_fecha.isoformat()},
                          motivo=motivo.strip())
    db().add(req)
    db().flush()
    alerts.emit("OV_CAMBIO_FECHA_SOLICITUD", f"Cambio de fecha de la OV {order.numero}: {order.fecha_compromiso:%d/%m/%Y} → "
                f"{nueva_fecha:%d/%m/%Y}", f"Solicitado por {user.nombre}. Motivo: {motivo.strip()}", "OVChangeRequest", req.id,
                extra_users=[order.vendedor_id] if order.vendedor_id else None, dedup_key=f"OV_MODIF:{req.id}", creado_por=user)
    audit(user, "OV_CAMBIO_FECHA_SOLICITADO", "SalesOrder", order.numero, {"nueva_fecha": nueva_fecha, "motivo": motivo})
    return req
