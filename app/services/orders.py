"""Órdenes de venta: registro, modificación (con autorización), cancelación, decisiones ante faltante y
preparación por prioridad y cortes (IF §4, §5, §6.3, §14)."""
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Alert, Customer, OVChangeRequest, OVDecision, Product, RouteStop, SalesOrder, SalesOrderLine, User, now)
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


def check_cutoff(fecha, ahora=None):
    """Ronda 23-oct-2026: después de la hora de corte (12:00) no se registra ni se programa una OV para el día siguiente."""
    corte = (param("hora_corte_ov_dia_siguiente", "") or "").strip()[:5]
    if not corte or not isinstance(fecha, date):
        return
    ahora = ahora or datetime.now()
    if fecha == ahora.date() + timedelta(days=1) and f"{ahora:%H:%M}" > corte:
        raise BusinessError(f"Después de las {corte} no se registra una OV para despachar mañana ({fecha:%d/%m/%Y}). "
                            "Elija otra fecha de despacho.")


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
    if site is None and guardar and datos["lugar_entrega"]:
        site = CustomerSite(customer_id=customer.id, nombre=datos["lugar_entrega"], direccion=datos["direccion"],
                            distrito=datos["distrito"], provincia=datos["provincia"])
        db().add(site)
        db().flush()
        datos["site_id"] = site.id
        audit(user, "CLIENTE_LUGAR_AGREGADO", "Customer", customer.ruc, {"lugar": site.nombre})
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
    if origen == "MODULO" and not regularizacion:
        check_not_past(fecha_compromiso, hora_cita)
        check_cutoff(fecha_compromiso)
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
    audit(user, "OV_CREADA", "SalesOrder", o.numero, {"lineas": lines, "fecha_compromiso": fecha_compromiso,
                                                      "urgente": urgente, "canal_precio": o.canal_precio,
                                                      "oc": bool(oc_archivo)})
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
    if evaluar:
        evaluate_order(o, user, "CREACION")
    from .commitment import open_commitment
    open_commitment(o)


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
        check_not_past(order.fecha_compromiso, order.hora_cita)
        check_cutoff(order.fecha_compromiso)
        customer_can_order(order.customer)
        order.estado = "REGISTRADA"
        order.estado_stock = "SIN_EVALUAR"
        order.motivo_detencion = ""
        order.creado_ts = now()
        _activate(order, user)
    return order


def _apply_changes(order, user, changes):
    """changes: {fecha_compromiso, urgente, comentarios, hora_cita, cita_confirmada, lines:[{product_code,cantidad,precio_unitario}]}"""
    if order.estado not in EDITABLE_ESTADOS:
        raise BusinessError(f"La OV está {order.estado}; ya no se puede modificar.")
    antes = snapshot(order)
    if "fecha_compromiso" in changes and changes["fecha_compromiso"]:
        fc = changes["fecha_compromiso"]
        if isinstance(fc, str) and fc and date.fromisoformat(fc[:10]) != order.fecha_compromiso:
            check_cutoff(date.fromisoformat(fc[:10]))
        elif isinstance(fc, date) and fc != order.fecha_compromiso:
            check_cutoff(fc)
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
    if order.estado == "BORRADOR":  # se valida y evalúa al adjuntar la orden de compra
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
    db().add(OVDecision(order_id=order.id, tipo="RENEGOCIAR_FECHA", detalle={"anterior": order.fecha_compromiso.isoformat(),
                                                                               "nueva": nueva_fecha.isoformat()},
                        comentario=comentario, user_id=user.id, estado="APLICADA"))
    _apply_changes(order, user, {"fecha_compromiso": nueva_fecha})


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


def regularize_close(order, user, comentario):
    """Regularización: se deja como registro (p. ej. pedido ya atendido fuera del sistema), sin reservar stock."""
    if not has_perm(user, "ov.regularizar"):
        raise BusinessError("Su rol no gestiona regularizaciones de OV.")
    if order.estado != "REGULARIZADA":
        raise BusinessError("La OV no está en regularización.")
    if not (comentario or "").strip():
        raise BusinessError("Indique cómo se regularizó el pedido.")
    reg = dict(order.regularizacion or {})
    reg.update({"cerrada_por": user.nombre, "cerrada_ts": now().isoformat(), "cierre": comentario.strip()})
    order.regularizacion = reg
    order.estado = "REGULARIZADA_CERRADA"
    audit(user, "OV_REGULARIZACION_CERRADA", "SalesOrder", order.numero, {"comentario": comentario})


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
