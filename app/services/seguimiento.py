"""V17 (02-nov-2026): seguimiento de pedidos e indicadores operativos.

- Inicio del ejecutivo comercial: sus OV con estado, área donde está, avance de productos y líneas y retrasos (con
  alerta inmediata al ejecutivo).
- Expedientes agrupados por cliente y fecha de despacho (p. ej. «cliente X, despacho 02/11: 20 OV»), para Comercial,
  Almacén, Calidad, Distribución y las demás áreas.
- Nivel de servicio del mes (OTIF, fill rate y a tiempo) sobre el universo de OV cargadas que se deben despachar dentro
  del mes en curso, con el detalle de cada OV; y el cumplimiento de un cliente (para decidir «no cumple»).
- Tiempos de respuesta por tipo de solicitud (movimientos y traslados) y desempeño del equipo operativo.
- Recojo en almacén y cierre o envío posterior de las líneas pendientes de un despacho incompleto."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import db
from ..models import Alert, AlertEvent, MoveRequest, PickingRecord, PickingTask, SalesOrder, SalesOrderLine, Transfer, User, now


def _con_lineas(q):
    """V20: líneas y reservas de las OV en pocas consultas (antes, una consulta por OV y por línea)."""
    return q.options(selectinload(SalesOrder.lines).selectinload(SalesOrderLine.reservations), selectinload(SalesOrder.customer))
from . import alerts
from .core import BusinessError, audit, has_perm, param

CERRADAS = ("CANCELADA", "CERRADA", "DESPACHADA", "ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA", "DEVUELTA")

# dónde está la OV según su estado (para el seguimiento del ejecutivo)
AREA_POR_ESTADO = {
    "BORRADOR": "Comercial", "BLOQUEADA": "Comercial / Finanzas", "REGULARIZACION_OBSERVADA": "Comercial",
    "REGISTRADA": "Logística (evaluación)", "EVALUADA": "Logística / Almacén", "EN_PREPARACION": "Almacén (picking)",
    "PREPARADA": "Distribución (por programar)", "PROGRAMADA": "Distribución (programada)", "EN_RUTA": "Distribución (en ruta)",
    "DESPACHADA": "Distribución (en ruta)", "ENTREGADA": "Entregada", "ENTREGA_PARCIAL": "Entregada en parte",
    "RECHAZADA": "Rechazada", "DEVUELTA": "Devuelta", "CANCELADA": "Cancelada", "CERRADA": "Cerrada",
}


def order_area(o):
    if o.estado in ("EVALUADA", "REGISTRADA") and o.estado_stock in ("INCOMPLETA", "SIN_STOCK"):
        return "Logística (faltante: producción, compra o traslado)"
    if o.retenida_precio:
        return "Comercial (precio por confirmar)"
    return AREA_POR_ESTADO.get(o.estado, o.estado)


def progress(o):
    """Avance de productos (unidades) y líneas: despachado si ya salió; si no, lo preparado (picking) o reservado."""
    from .stock import line_reserved
    act = [l for l in o.lines if l.activa]
    if not act:
        return {"unidades": 0, "lineas": 0}
    tot = sum(l.cantidad for l in act) or 1
    if o.salida_ts:
        hecho = [min(l.despachado or 0, l.cantidad) for l in act]
    else:
        hecho = [min(max(l.preparado or 0, line_reserved(l)), l.cantidad) for l in act]
    lineas_ok = sum(1 for l, h in zip(act, hecho) if h >= l.cantidad - 1e-9)
    return {"unidades": round(100 * sum(hecho) / tot, 1), "lineas": round(100 * lineas_ok / len(act), 1)}


def delay(o, hoy=None):
    """Texto del retraso o riesgo de la OV (vacío si va bien)."""
    hoy = hoy or date.today()
    if o.estado in CERRADAS:
        return ""
    if o.fecha_compromiso and o.fecha_compromiso < hoy:
        return f"Atrasada {(hoy - o.fecha_compromiso).days} día(s): comprometida {o.fecha_compromiso:%d/%m}"
    if o.motivo_detencion:
        return f"Detenida: {o.motivo_detencion}"
    if o.fecha_compromiso == hoy and o.estado not in ("PREPARADA", "PROGRAMADA", "EN_RUTA"):
        return "Sale hoy y aún no está preparada"
    return ""


def seller_orders(user, incluir_cerradas_dias=7):
    """OV del ejecutivo comercial (abiertas y las cerradas en los últimos días) con área, avance y retraso."""
    desde = date.today() - timedelta(days=incluir_cerradas_dias)
    q = _con_lineas(select(SalesOrder)).where(SalesOrder.vendedor_id == user.id).order_by(SalesOrder.fecha_compromiso)
    out = []
    for o in db().execute(q).scalars():
        if o.estado in CERRADAS and (o.fecha_compromiso or date.min) < desde:
            continue
        out.append({"o": o, "area": order_area(o), "avance": progress(o), "retraso": delay(o)})
    return out


def check_seller_delays(hoy=None):
    """Aviso inmediato al ejecutivo a cargo cuando su OV se atrasa o se detiene (una vez por OV y día)."""
    hoy = hoy or date.today()
    n = 0
    for o in db().execute(select(SalesOrder).where(SalesOrder.vendedor_id.is_not(None),
                                                   SalesOrder.estado.notin_(CERRADAS))).scalars():
        motivo = delay(o, hoy)
        if not motivo:
            continue
        if alerts.emit("OV_RETRASO_EJECUTIVO", f"OV {o.numero} ({o.customer.nombre if o.customer else ''}): {motivo}"[:250],
                       f"Área: {order_area(o)}. Avance {progress(o)['unidades']} % productos.", "SalesOrder", o.id,
                       extra_users=[o.vendedor_id], dedup_key=f"OV_RETRASO_EJ:{o.id}:{hoy:%Y%m%d}") is not None:
            n += 1
    return n


# ------------------------------------------------------------------ expedientes agrupados (cliente + despacho)
def groups(desde=None, hasta=None, customer_id=None, vendedor_id=None, solo_abiertas=True):
    """[(cliente, fecha de despacho, [OV])]: las OV de un mismo cliente que salen el mismo día."""
    desde = desde or date.today() - timedelta(days=7)
    hasta = hasta or date.today() + timedelta(days=30)
    q = _con_lineas(select(SalesOrder)).where(SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= hasta)
    if customer_id:
        q = q.where(SalesOrder.customer_id == int(customer_id))
    if vendedor_id:
        q = q.where(SalesOrder.vendedor_id == int(vendedor_id))
    por = defaultdict(list)
    for o in db().execute(q).scalars():
        if solo_abiertas and o.estado in ("CANCELADA", "CERRADA"):
            continue
        por[(o.customer_id, o.fecha_compromiso)].append(o)
    out = []
    for (cid, f), ovs in por.items():
        cli = ovs[0].customer
        kg = sum((l.cantidad or 0) * ((l.product.peso_kg or 1) if l.product else 1) for o in ovs for l in o.lines if l.activa)
        av = [progress(o)["unidades"] for o in ovs]
        out.append({"cliente": cli, "fecha": f, "ovs": sorted(ovs, key=lambda o: o.numero), "kg": round(kg, 1),
                    "avance": round(sum(av) / len(av), 1) if av else 0,
                    "retrasos": sum(1 for o in ovs if delay(o)), "estados": Counter(o.estado for o in ovs)})
    return sorted(out, key=lambda g: (g["fecha"], g["cliente"].nombre if g["cliente"] else ""))


def group_detail(customer_id, fecha):
    ovs = list(db().execute(_con_lineas(select(SalesOrder)).where(SalesOrder.customer_id == customer_id,
                                                     SalesOrder.fecha_compromiso == fecha)
                            .order_by(SalesOrder.numero)).scalars())
    return [o for o in ovs if o.estado != "CANCELADA"]


def group_certificates(ovs, por_producto=True):
    """Certificados de las OV del grupo: uno por producto (lista) o todos juntos en un solo documento (consolidado)."""
    from ..models import Certificate
    ids = [o.id for o in ovs]
    certs = list(db().execute(select(Certificate).where(Certificate.order_id.in_(ids or [0]))
                              .order_by(Certificate.product_code)).scalars())
    if por_producto:
        return certs
    por = defaultdict(list)
    for c in certs:
        por[c.product_code].append(c)
    return sorted(por.items())


# ------------------------------------------------------------------ nivel de servicio del mes
def month_bounds(ref=None):
    ref = ref or date.today()
    ini = ref.replace(day=1)
    fin = (ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return ini, fin


def service_month(ref=None, customer_id=None, vendedor_id=None, desde=None, hasta=None):
    """OTIF, fill rate y a tiempo (on time) sobre el universo de OV cargadas cuya fecha comprometida cae en el mes en
    curso (o en el rango dado), sin las canceladas. Cada indicador trae el detalle de sus OV.
    V23 (fórmula de la empresa): la base de los tres indicadores son todas las OV que se subieron y corresponden
    despacharse en el periodo (fecha comprometida dentro).
    - On time: OV que salieron hasta su fecha comprometida / OV del universo.
    - In full: OV que salieron con todas sus líneas completas / OV del universo.
    - OTIF: OV que salieron a tiempo y completas / OV del universo.
    - Fill rate (unidades): unidades despachadas / unidades pedidas de las OV con salida; también por líneas."""
    ini, fin = (desde, hasta) if desde and hasta else month_bounds(ref)
    q = _con_lineas(select(SalesOrder)).where(SalesOrder.fecha_compromiso >= ini, SalesOrder.fecha_compromiso <= fin,
                                 SalesOrder.estado.notin_(("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")))
    if customer_id:
        q = q.where(SalesOrder.customer_id == int(customer_id))
    if vendedor_id:
        q = q.where(SalesOrder.vendedor_id == int(vendedor_id))
    universo = list(db().execute(q).scalars())
    hoy = date.today()
    filas = []
    for o in universo:
        act = [l for l in o.lines if l.activa]
        ped = sum(l.cantidad for l in act)
        des = sum(min(l.despachado or 0, l.cantidad) for l in act) if o.salida_ts else 0
        completo = bool(o.salida_ts) and all((l.despachado or 0) >= l.cantidad - 1e-9 for l in act)
        a_tiempo = bool(o.salida_ts) and o.salida_ts.date() <= o.fecha_compromiso
        vencida = o.fecha_compromiso < hoy or bool(o.salida_ts)
        filas.append({"o": o, "pedido": ped, "despachado": des, "completo": completo, "a_tiempo": a_tiempo,
                      "salio": bool(o.salida_ts), "evaluable": vencida, "otif": completo and a_tiempo,
                      "lineas": len(act), "lineas_ok": sum(1 for l in act if o.salida_ts and (l.despachado or 0) >= l.cantidad - 1e-9)})
    salieron = [f for f in filas if f["salio"]]
    evaluables = [f for f in filas if f["evaluable"]]

    def pct(a, b):
        return round(100 * a / b, 1) if b else None
    return {"desde": ini, "hasta": fin, "universo": len(filas), "filas": filas,
            "otif": pct(sum(1 for f in filas if f["otif"]), len(filas)), "otif_n": (sum(1 for f in filas if f["otif"]), len(filas)),
            "on_time": pct(sum(1 for f in filas if f["a_tiempo"]), len(filas)), "on_time_n": (sum(1 for f in filas if f["a_tiempo"]), len(filas)),
            "in_full": pct(sum(1 for f in filas if f["completo"]), len(filas)), "in_full_n": (sum(1 for f in filas if f["completo"]), len(filas)),
            "en_plazo": sum(1 for f in filas if not f["salio"] and not f["evaluable"]),
            "evaluables": len(evaluables),
            "fill_rate": pct(sum(f["despachado"] for f in salieron), sum(f["pedido"] for f in salieron)),
            "fill_rate_lineas": pct(sum(f["lineas_ok"] for f in salieron), sum(f["lineas"] for f in salieron)),
            "pendientes": sum(1 for f in filas if not f["salio"])}


def customer_compliance(customer_id, dias=90):
    """Cumplimiento con el cliente (últimos «dias»): para que Logística y Almacén lo vean antes de responder «no cumple»."""
    hasta = date.today()
    d = service_month(customer_id=customer_id, desde=hasta - timedelta(days=dias), hasta=hasta + timedelta(days=30))
    ult = sorted([f for f in d["filas"] if f["salio"]], key=lambda f: f["o"].salida_ts, reverse=True)[:8]
    no_cumple = sum(1 for f in d["filas"] if (f["o"].compromiso or {}).get("estado") == "NO_CUMPLE")
    return {"dias": dias, "otif": d["otif"], "otif_n": d["otif_n"], "on_time": d["on_time"], "fill_rate": d["fill_rate"],
            "ultimas": ult, "no_cumple": no_cumple, "universo": d["universo"]}


# ------------------------------------------------------------------ tiempos de respuesta y desempeño
def _min(a, b):
    return (b - a).total_seconds() / 60 if a and b else None


def response_times(desde=None, hasta=None):
    """Tiempo de respuesta por tipo de solicitud: movimientos (por área solicitante y tipo de carga: solicitud →
    terminado) y traslados entre almacenes (solicitud → autorización → recepción)."""
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=30)
    d0, d1 = datetime.combine(desde, datetime.min.time()), datetime.combine(hasta, datetime.max.time())
    from .supply import TIPOS_CARGA
    grupos = defaultdict(list)
    detalle = []
    for m in db().execute(select(MoveRequest).where(MoveRequest.ts >= d0, MoveRequest.ts <= d1)).scalars():
        base = m.programado_para or m.ts
        t = _min(base, m.fin_ts)
        tipo = TIPOS_CARGA.get((m.carga or {}).get("tipo"), "Sin tipo de carga")
        clave = (f"Movimiento · {m.area or 'sin área'}", tipo)
        if t is not None:
            grupos[clave].append(t)
        detalle.append({"tipo": clave[0], "subtipo": tipo, "id": m.id, "desde": f"{m.origen} → {m.destino}",
                        "solicitado": base, "atendido": m.fin_ts, "min": round(t) if t is not None else None,
                        "estado": m.estado})
    for tr in db().execute(select(Transfer).where(Transfer.ts >= d0, Transfer.ts <= d1)).scalars():
        t = _min(tr.ts, tr.recibido_ts)
        clave = ("Traslado entre almacenes", tr.destino_code)
        if t is not None:
            grupos[clave].append(t)
        detalle.append({"tipo": clave[0], "subtipo": f"a {tr.destino_code}", "id": tr.id, "desde": "",
                        "solicitado": tr.ts, "atendido": tr.recibido_ts, "min": round(t) if t is not None else None,
                        "estado": tr.estado})
    resumen = [{"tipo": k[0], "subtipo": k[1], "n": len(v), "prom_min": round(sum(v) / len(v)), "max_min": round(max(v))}
               for k, v in sorted(grupos.items())]
    return {"desde": desde, "hasta": hasta, "resumen": resumen, "detalle": sorted(detalle, key=lambda x: x["solicitado"] or now(), reverse=True)}


def team_performance(desde=None, hasta=None, areas=None):
    """Desempeño del personal operativo: picking (clientes atendidos, unidades y kg), movimientos ejecutados y tareas
    (alertas) completadas, por persona."""
    hasta = hasta or date.today()
    desde = desde or hasta
    d0, d1 = datetime.combine(desde, datetime.min.time()), datetime.combine(hasta, datetime.max.time())
    por = defaultdict(lambda: {"clientes": set(), "ov": set(), "unidades": 0.0, "kg": 0.0, "movimientos": 0,
                               "mov_min": [], "tareas": 0})
    for r in db().execute(select(PickingRecord).where(PickingRecord.ts >= d0, PickingRecord.ts <= d1)).scalars() \
            if hasattr(PickingRecord, "ts") else []:
        if not r.user_id:
            continue
        p = por[r.user_id]
        o = db().get(SalesOrder, r.order_id)
        p["ov"].add(r.order_id)
        if o is not None:
            p["clientes"].add(o.customer_id)
        p["unidades"] += r.cantidad or 0
        ln = next((l for l in (o.lines if o else []) if l.id == r.line_id), None)
        p["kg"] += (r.cantidad or 0) * ((ln.product.peso_kg or 0) if ln and ln.product else 0)
    for m in db().execute(select(MoveRequest).where(MoveRequest.fin_ts >= d0, MoveRequest.fin_ts <= d1)).scalars():
        if m.asignado_a:
            por[m.asignado_a]["movimientos"] += 1
            t = _min(m.inicio_ts, m.fin_ts)
            if t is not None:
                por[m.asignado_a]["mov_min"].append(t)
    for ev in db().execute(select(AlertEvent).where(AlertEvent.accion == "COMPLETADA", AlertEvent.ts >= d0,
                                                    AlertEvent.ts <= d1)).scalars():
        if ev.user_id:
            por[ev.user_id]["tareas"] += 1
    filas = []
    for uid, p in por.items():
        u = db().get(User, uid)
        if u is None or (areas is not None and (u.role.area if u.role else "") not in areas):
            continue
        filas.append({"user": u, "clientes": len(p["clientes"]), "ov": len(p["ov"]), "unidades": round(p["unidades"], 1),
                      "kg": round(p["kg"], 1), "movimientos": p["movimientos"],
                      "mov_prom_min": round(sum(p["mov_min"]) / len(p["mov_min"])) if p["mov_min"] else None,
                      "tareas": p["tareas"]})
    return {"desde": desde, "hasta": hasta,
            "filas": sorted(filas, key=lambda f: (-(f["unidades"] + f["movimientos"] + f["tareas"]), f["user"].nombre))}


# ------------------------------------------------------------------ recojo en almacén y saldo pendiente
def register_pickup(order, user, receptor="", documento="", foto=""):
    """El cliente recoge en el almacén de la empresa (OV con modalidad RECOJO): se registra la entrega sin ruta."""
    if not (has_perm(user, "distribucion.confirmar_salida") or has_perm(user, "picking.asignar")):
        raise BusinessError("La entrega en almacén la registran el Líder Operativo o el Supervisor de Almacén.")
    if order.modalidad_entrega != "RECOJO":
        raise BusinessError("La OV no es de recojo en almacén.")
    if order.estado != "PREPARADA":
        raise BusinessError("La OV debe estar preparada (picking completo) para entregarla.")
    if not (receptor or "").strip():
        raise BusinessError("Indique quién recoge el pedido.")
    from .stock import consume_order
    consume_order(order, user)
    order.estado = "ENTREGADA"
    order.salida_ts = order.entrega_ts = now()
    if order.decision_parcial == "APROBADA":
        from .orders import create_saldo
        create_saldo(order, user)
    order.motivo_detencion = ""
    audit(user, "OV_RECOJO_ENTREGADA", "SalesOrder", order.numero, {"receptor": receptor.strip(), "documento": documento,
                                                                    "foto": foto})


def pending_lines(order):
    """Líneas con saldo pendiente: las de las OV de saldo de esta OV (o de la propia, si es un saldo)."""
    saldos = [order] if order.origen == "SALDO" else list(
        db().execute(select(SalesOrder).where(SalesOrder.parent_id == order.id)).scalars())
    return [(s, l) for s in saldos if s.estado not in ("CANCELADA", "CERRADA", "DESPACHADA", "ENTREGADA")
            for l in s.lines if l.activa and l.cantidad - (l.despachado or 0) > 1e-9]


def resolve_balance(saldo, user, cerrar_ids, fecha=None, motivo=""):
    """Comercial decide qué líneas del despacho incompleto se envían después (en «fecha») y cuáles se cierran."""
    if not (has_perm(user, "ov.modificar") or has_perm(user, "ov.renegociar")):
        raise BusinessError("Esta decisión la toma Comercial (ejecutivo, coordinador o jefe).")
    if saldo.origen != "SALDO":
        raise BusinessError("Solo se decide sobre la OV de saldo.")
    cerrar = {int(x) for x in cerrar_ids or [] if str(x).strip()}
    if cerrar and not (motivo or "").strip():
        raise BusinessError("Indique el motivo para cerrar líneas (no se enviarán).")
    from .stock import _release
    for l in saldo.lines:
        if l.id in cerrar and l.activa:
            for r in [r for r in l.reservations if r.estado == "ACTIVA"]:
                _release(r, f"Línea cerrada por Comercial: {motivo.strip()}")
            l.activa = False
    if fecha is not None:
        if fecha < date.today():
            raise BusinessError("La fecha de envío no puede ser anterior a hoy.")
        saldo.fecha_compromiso = fecha
    if not any(l.activa for l in saldo.lines):
        saldo.estado = "CERRADA"
        saldo.motivo_detencion = f"Saldo cerrado por Comercial: {motivo.strip()}"[:250]
    audit(user, "OV_SALDO_RESUELTO", "SalesOrder", saldo.numero, {"cerradas": sorted(cerrar), "fecha": fecha,
                                                                   "motivo": motivo})
    return saldo


# ------------------------------------------------------------------ V18: despachos por cliente y fecha en el Inicio
def dispatch_board(user, dias=7):
    """Agrupado por cliente y fecha de despacho (de ayer a «dias» adelante) con el pronóstico de cumplimiento, las
    modificaciones y los problemas, para gestionar a tiempo. Gerencias, Logística, Operaciones y Comercial ven todo;
    el ejecutivo comercial, solo sus clientes y OV."""
    from ..models import AuditLog, Incident
    hoy = date.today()
    vend = user.id if user.role_code == "EJECUTIVO_VENTAS" else None
    out = []
    grupos = [(g, [o for o in g["ovs"] if o.estado not in ("CANCELADA", "CERRADA")])
              for g in groups(hoy - timedelta(days=1), hoy + timedelta(days=dias), vendedor_id=vend)]
    grupos = [(g, ovs) for g, ovs in grupos if ovs]
    # V20: modificaciones e incidencias de todas las OV en dos consultas (antes, dos por grupo)
    from sqlalchemy import func
    todas = [o for _, ovs in grupos for o in ovs]
    mods_por = dict(db().execute(select(AuditLog.entidad_id, func.count()).where(
        AuditLog.entidad == "SalesOrder", AuditLog.entidad_id.in_([o.numero for o in todas] or [""]),
        AuditLog.accion.in_(("OV_MODIFICADA", "OV_MODIF_SOLICITADA", "OV_CAMBIO_FECHA_SOLICITADO", "OV_RENEGOCIADA",
                             "OV_FECHA_RENEGOCIADA", "OV_PRODUCTO_CAMBIADO"))).group_by(AuditLog.entidad_id)).all())
    incs_por = dict(db().execute(select(Incident.order_id, func.count()).where(
        Incident.order_id.in_([o.id for o in todas] or [0])).group_by(Incident.order_id)).all())
    for g, ovs in grupos:
        mods = sum(mods_por.get(o.numero, 0) for o in ovs)
        incs = sum(incs_por.get(o.id, 0) for o in ovs)
        problemas = [f"OV {o.numero}: {delay(o)}" for o in ovs if delay(o)]
        problemas += [f"OV {o.numero}: faltante de stock" for o in ovs
                      if o.estado_stock in ("INCOMPLETA", "SIN_STOCK") and o.estado not in CERRADAS and not delay(o)]
        listas = sum(1 for o in ovs if o.estado in ("PREPARADA", "PROGRAMADA", "EN_RUTA") or o.estado in CERRADAS)
        if all(o.estado in CERRADAS for o in ovs):
            pron = ("CUMPLIDO", "Despachado")
        elif problemas:
            pron = ("RIESGO", "En riesgo")
        elif listas == len(ovs) or g["fecha"] > hoy:
            pron = ("A_TIEMPO", "A tiempo")
        else:
            pron = ("VIGILAR", "Vigilar")
        out.append(dict(g, ovs=ovs, modificaciones=mods, incidencias=incs, problemas=problemas, pronostico=pron,
                        listas=listas))
    orden = {"RIESGO": 0, "VIGILAR": 1, "A_TIEMPO": 2, "CUMPLIDO": 3}
    return sorted(out, key=lambda g: (g["fecha"] < hoy, orden[g["pronostico"][0]], g["fecha"]))


def func_count():
    from sqlalchemy import func
    return func.count()
