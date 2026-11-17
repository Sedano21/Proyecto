"""V27 (11-nov-2026): «Estado de OV»: en qué etapa está cada OV del módulo, con indicadores por etapa (mismo estilo
de la pantalla «OV abiertas vs guías de SAP»). Solo consulta."""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import CustomerInvoice, PickingTask, RouteStop, SalesOrder

# etapa visible → estados de la OV
ETAPAS = [
    ("BORRADOR", "Borrador", ("BORRADOR",)),
    # V54: «Detenida» es solo la OV bloqueada o retenida por precio; la evaluada sin problemas está «Por preparar»
    ("DETENIDA", "Detenida", ("BLOQUEADA",)),
    ("POR_PREPARAR", "Por preparar", ("REGISTRADA", "EVALUADA")),
    ("EN_PREPARACION", "En preparación", ("PROGRAMADA", "EN_PREPARACION")),
    ("LISTA", "Lista para despacho", ("PREPARADA",)),
    ("PARCIAL", "Despacho parcial (saldo pendiente)", ("DESPACHO_PARCIAL",)),
    ("DESPACHADA", "Despachada (con guía)", ("DESPACHADA",)),
    ("ENTREGADA", "Entregada", ("ENTREGADA", "ENTREGA_PARCIAL")),
    ("CERRADA", "Cerrada / cancelada", ("CERRADA", "CANCELADA", "DEVUELTA", "REGULARIZADA", "REGULARIZADA_CERRADA",
                                        "REGULARIZACION_OBSERVADA")),
]
_DE = {e: k for k, _, ests in ETAPAS for e in ests}


def etapa(o):
    if o.retenida_precio and o.estado in ("REGISTRADA", "EVALUADA"):
        return "DETENIDA"
    return _DE.get(o.estado, "DETENIDA")


def pasos(o, picking, parada, factura, guias=None):
    """Línea de tiempo de la OV: [(nombre, hecho, detalle)]. V54: con guía (de SAP o subida al módulo), el stock, el
    picking y la salida de lo guiado ya se cumplieron aunque no se hayan registrado en el módulo."""
    guias = guias or []
    reservado = o.cobertura_unidades or 0
    activas = [l for l in o.lines if l.activa]
    pedido = sum(l.cantidad or 0 for l in activas)
    guiado = sum(min(l.despachado or 0, l.cantidad or 0) for l in activas)
    pct_g = round(guiado * 100 / pedido, 1) if pedido else 0
    completo = bool(guias) and pct_g >= 100 - 1e-6
    docs = ", ".join(g["documento"] for g in guias)
    if guias:
        stock = ("Stock", completo, f"{pct_g:g}% despachado" + ("" if completo else f" · saldo {reservado:g}% reservado"))
        pick = ("Picking", completo, "cumplido (guía)" if completo else f"cumplido en lo guiado ({pct_g:g}%)")
        ruta = ("Ruta", True, f"ruta #{parada.route_id}" if parada is not None else
                "salió " + (guias[0]["fecha"].strftime("%d/%m") if guias[0]["fecha"] else "") + " (SAP)")
        guia = ("Guía", True, docs)
    else:
        stock = ("Stock", reservado >= 100, f"{reservado:g}% reservado")
        pick = ("Picking", bool(picking) and all(t.estado == "LISTO" for t in picking),
                ", ".join(t.estado.lower().replace("_", " ") for t in picking) if picking else "sin programar")
        ruta = ("Ruta", parada is not None, f"ruta #{parada.route_id}" if parada is not None else "")
        guia = ("Guía", bool(parada is not None and parada.guia_numero),
                parada.guia_numero if parada is not None and parada.guia_numero else "")
    return [
        ("Registrada", True, o.creado_ts.strftime("%d/%m") if o.creado_ts else ""),
        stock, pick, ruta, guia,
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
    from .ov_sap import guias_de
    guias = guias_de(ords)
    tot = {k: 0 for k, _, _ in ETAPAS}
    filas = []
    for o in ords:
        e = etapa(o)
        tot[e] += 1
        if etapa_f and e != etapa_f:
            continue
        atrasada = o.fecha_compromiso < hoy and e not in ("DESPACHADA", "ENTREGADA", "CERRADA")
        filas.append({"o": o, "etapa": e, "pasos": pasos(o, picks.get(o.id, []), paradas.get(o.id), facts.get(o.id, []),
                                                         guias.get(o.id)),
                      "atrasada": atrasada, "motivo": (o.bloqueo_ov or {}).get("motivo") if o.estado == "BLOQUEADA"
                      else (o.motivo_detencion if o.retenida_precio else "")})
    tot["ATRASADAS"] = sum(1 for o in ords if o.fecha_compromiso < hoy
                           and etapa(o) not in ("DESPACHADA", "ENTREGADA", "CERRADA"))
    return {"filas": filas, "tot": tot, "total": len(ords), "desde": desde, "hasta": hasta, "etapas": ETAPAS}
