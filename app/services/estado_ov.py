"""V27 (11-nov-2026): «Estado de OV»: en qué etapa está cada OV del módulo, con indicadores por etapa (mismo estilo
de la pantalla «OV abiertas vs guías de SAP»). Solo consulta."""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import CustomerInvoice, PickingTask, RouteStop, SalesOrder

# etapa visible → estados de la OV
ETAPAS = [
    ("BORRADOR", "Borrador", ("BORRADOR",)),
    ("DETENIDA", "Detenida", ("BLOQUEADA", "REGISTRADA", "EVALUADA")),
    ("EN_PREPARACION", "En preparación", ("PROGRAMADA", "EN_PREPARACION")),
    ("LISTA", "Lista para despacho", ("PREPARADA",)),
    ("DESPACHADA", "Despachada (en ruta)", ("DESPACHADA",)),
    ("ENTREGADA", "Entregada", ("ENTREGADA", "ENTREGA_PARCIAL")),
    ("CERRADA", "Cerrada / cancelada", ("CERRADA", "CANCELADA", "DEVUELTA", "REGULARIZADA", "REGULARIZADA_CERRADA",
                                        "REGULARIZACION_OBSERVADA")),
]
_DE = {e: k for k, _, ests in ETAPAS for e in ests}


def etapa(o):
    return _DE.get(o.estado, "DETENIDA")


def pasos(o, picking, parada, factura):
    """Línea de tiempo de la OV: [(nombre, hecho, detalle)]."""
    reservado = o.cobertura_unidades or 0
    return [
        ("Registrada", True, o.creado_ts.strftime("%d/%m") if o.creado_ts else ""),
        ("Stock", reservado >= 100, f"{reservado:g}% reservado"),
        ("Picking", bool(picking) and all(t.estado == "LISTO" for t in picking),
         ", ".join(t.estado.lower().replace("_", " ") for t in picking) if picking else "sin programar"),
        ("Ruta", parada is not None, f"ruta #{parada.route_id}" if parada is not None else ""),
        ("Guía", bool(parada is not None and parada.guia_numero), parada.guia_numero if parada is not None and parada.guia_numero else ""),
        ("Entrega", o.estado in ("ENTREGADA", "ENTREGA_PARCIAL") or (parada is not None and parada.estado in
                                                                    ("ENTREGADO", "ENTREGADA", "ENTREGA_PARCIAL")),
         (o.entrega_ts.strftime("%d/%m %H:%M") if o.entrega_ts else (parada.estado.lower().replace("_", " ")
                                                                    if parada is not None and parada.estado else ""))),
        ("Factura", bool(factura), ", ".join(factura)),
    ]


def tablero(desde=None, hasta=None, q="", vendedor_id=None, etapa_f=""):
    hoy = date.today()
    desde = desde or hoy - timedelta(days=15)
    hasta = hasta or hoy + timedelta(days=15)
    s = db()
    qry = select(SalesOrder).where(SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= hasta)
    if vendedor_id:
        qry = qry.where(SalesOrder.vendedor_id == int(vendedor_id))
    ords = list(s.execute(qry.order_by(SalesOrder.fecha_compromiso, SalesOrder.id)).scalars())
    if q:
        qq = q.upper()
        ords = [o for o in ords if qq in (o.numero or "").upper() or qq in (o.customer.nombre or "").upper()]
    ids = [o.id for o in ords] or [-1]
    picks, paradas, facts = {}, {}, {}
    for t in s.execute(select(PickingTask).where(PickingTask.order_id.in_(ids))).scalars():
        picks.setdefault(t.order_id, []).append(t)
    for st in s.execute(select(RouteStop).where(RouteStop.order_id.in_(ids)).order_by(RouteStop.id)).scalars():
        paradas[st.order_id] = st
    for inv in s.execute(select(CustomerInvoice).where(CustomerInvoice.order_id.in_(ids), CustomerInvoice.tipo == "FACTURA")).scalars():
        facts.setdefault(inv.order_id, []).append(inv.numero)
    tot = {k: 0 for k, _, _ in ETAPAS}
    filas = []
    for o in ords:
        e = etapa(o)
        tot[e] += 1
        if etapa_f and e != etapa_f:
            continue
        atrasada = o.fecha_compromiso < hoy and e not in ("ENTREGADA", "CERRADA")
        filas.append({"o": o, "etapa": e, "pasos": pasos(o, picks.get(o.id, []), paradas.get(o.id), facts.get(o.id, [])),
                      "atrasada": atrasada})
    tot["ATRASADAS"] = sum(1 for o in ords if o.fecha_compromiso < hoy and etapa(o) not in ("ENTREGADA", "CERRADA"))
    return {"filas": filas, "tot": tot, "total": len(ords), "desde": desde, "hasta": hasta, "etapas": ETAPAS}
