"""Comportamiento del cliente (observaciones al demo v0.6, Asistente de Ventas y Jefe Comercial).

Por cliente y periodo: pedidos realizados, atendidos y % de cumplimiento (atendidos / pedidos × 100), pedidos completos,
retrasos, rechazos, modificaciones, penalidad estimada y variaciones de compra por producto y presentación (pide más o
menos que en la primera mitad del periodo), con su consolidado y el detalle por OV.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import AuditLog, Customer, Incident, SalesOrder
from .core import param

SALIO = ("DESPACHADA", "EN_RUTA", "ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA", "DEVUELTA")
RECHAZO_TIPOS = ("RECHAZO_CALIDAD", "RECHAZO_OTRO", "RECHAZO_CITA", "DEVOLUCION", "CLIENTE_NO_RETIRA",
                 "INFESTACION_INTERNA", "INFESTACION_EXTERNA", "FUERA_CARACTERISTICAS", "PRODUCTO_ROTO")


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def _ovs(desde, hasta, customer_id=None):
    q = select(SalesOrder).where(SalesOrder.fecha_emision >= desde, SalesOrder.fecha_emision <= hasta,
                                 SalesOrder.estado != "CANCELADA")
    if customer_id:
        q = q.where(SalesOrder.customer_id == int(customer_id))
    return list(db().execute(q.order_by(SalesOrder.fecha_emision)).scalars())


def _order_row(o, hoy, mods, rechazos):
    from .customer_conditions import penalty_estimate
    from .orders import order_amount
    atendido = o.estado in SALIO or o.salida_ts is not None
    completo = atendido and all(l.despachado + 1e-9 >= l.cantidad for l in o.lines if l.activa)
    if o.salida_ts is not None:
        retraso = o.salida_ts.date() > o.fecha_compromiso
    else:
        retraso = o.fecha_compromiso < hoy
    pen = penalty_estimate(o)
    return {"o": o, "monto": order_amount(o), "atendido": atendido, "completo": completo, "retraso": retraso,
            "modificaciones": mods.get(o.numero, 0), "rechazos": rechazos.get(o.id, []),
            "penalidad": round(sum(x["monto"] or 0 for x in pen if x["riesgo"]), 2),
            "penalidad_riesgo": [x["texto"] for x in pen if x["riesgo"]]}


def _variaciones(ovs, desde, hasta, umbral):
    """Cantidad por producto y presentación en la segunda mitad del periodo frente a la primera."""
    medio = desde + (hasta - desde) / 2
    a, b = defaultdict(float), defaultdict(float)
    pa, pb = defaultdict(float), defaultdict(float)
    for o in ovs:
        for l in o.lines:
            if not l.activa:
                continue
            pres = (l.product.presentacion or l.product.um or "-") if l.product else "-"
            if o.fecha_emision <= medio:
                a[l.product_code] += l.cantidad
                pa[pres] += l.cantidad
            else:
                b[l.product_code] += l.cantidad
                pb[pres] += l.cantidad

    def comp(x, y, tipo):
        out = []
        for k in sorted(set(x) | set(y)):
            antes, ahora = x.get(k, 0.0), y.get(k, 0.0)
            var = _pct(ahora - antes, antes) if antes else (100.0 if ahora else 0.0)
            if var is not None and abs(var) >= umbral:
                out.append({"tipo": tipo, "clave": k, "antes": antes, "ahora": ahora, "var": var,
                            "texto": "pide más" if var > 0 else "pide menos"})
        return out
    return comp(a, b, "producto") + comp(pa, pb, "presentación")


def behavior(desde=None, hasta=None, customer_id=None):
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=90)
    hoy = date.today()
    s = db()
    ovs = _ovs(desde, hasta, customer_id)
    numeros = [o.numero for o in ovs] or [""]
    mods = defaultdict(int)
    for m in s.execute(select(AuditLog).where(AuditLog.accion.in_(("OV_MODIFICADA", "OV_MODIF_APROBADA")),
                                              AuditLog.entidad == "SalesOrder", AuditLog.entidad_id.in_(numeros))).scalars():
        mods[m.entidad_id] += 1
    rechazos = defaultdict(list)
    for i in s.execute(select(Incident).where(Incident.order_id.in_([o.id for o in ovs] or [0]),
                                              Incident.tipo.in_(RECHAZO_TIPOS))).scalars():
        rechazos[i.order_id].append(i.tipo.replace("_", " ").lower())
    umbral = float(param("variacion_compra_alerta_pct", 30) or 30)
    por_cliente = defaultdict(list)
    for o in ovs:
        por_cliente[o.customer_id].append(o)
    out = []
    for cid, lista in por_cliente.items():
        filas = [_order_row(o, hoy, mods, rechazos) for o in lista]
        n = len(filas)
        aten = sum(1 for f in filas if f["atendido"])
        c = s.get(Customer, cid)
        out.append({"customer": c, "pedidos": n, "atendidos": aten, "cumplimiento": _pct(aten, n),
                    "completos": sum(1 for f in filas if f["completo"]),
                    "retrasos": sum(1 for f in filas if f["retraso"]),
                    "rechazos": sum(1 for f in filas if f["rechazos"]),
                    "modificaciones": sum(f["modificaciones"] for f in filas),
                    "penalidad": round(sum(f["penalidad"] for f in filas), 2),
                    "monto": sum(f["monto"] for f in filas),
                    "variaciones": _variaciones(lista, desde, hasta, umbral), "detalle": filas})
    out.sort(key=lambda x: -x["monto"])
    return {"desde": desde, "hasta": hasta, "clientes": out, "umbral": umbral,
            "penalidad_total": round(sum(x["penalidad"] for x in out), 2)}


def check_purchase_variations(user=None, hoy=None):
    """Tarea programada: alerta a Comercial cuando un cliente pide más o menos de lo habitual de un producto o
    presentación (umbral 'variacion_compra_alerta_pct')."""
    from . import alerts
    hoy = hoy or date.today()
    d = behavior(hoy - timedelta(days=int(param("variacion_compra_dias", 90) or 90)), hoy)
    n = 0
    for c in d["clientes"]:
        for v in c["variaciones"]:
            alerts.emit("CLIENTE_VARIACION_COMPRA",
                        f"{c['customer'].nombre} {v['texto']} de {v['tipo']} {v['clave']} ({v['var']:+.0f} %)",
                        f"Cantidad en la segunda mitad del periodo {v['ahora']:g} frente a {v['antes']:g} en la primera.",
                        "Customer", c["customer"].id, creado_por=user,
                        extra_users=[c["customer"].vendedor_id] if c["customer"].vendedor_id else None,
                        dedup_key=f"VAR_COMPRA:{c['customer'].id}:{v['tipo']}:{v['clave']}:{hoy:%Y%m}")
            n += 1
    return n
