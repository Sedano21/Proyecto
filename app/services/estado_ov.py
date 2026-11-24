"""V27 (11-nov-2026): «Estado de OV»: en qué etapa está cada OV del módulo, con indicadores por etapa (mismo estilo
de la pantalla «OV abiertas vs guías de SAP»). Solo consulta."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import CustomerInvoice, PickingTask, Route, RouteStop, SalesOrder

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
    # V64: cerrada (cuenta como pedido; el saldo es venta perdida) y cancelada (el cliente no lo quiso) van aparte
    ("CERRADA", "Cerrada", ("CERRADA", "DEVUELTA", "REGULARIZADA", "REGULARIZADA_CERRADA", "REGULARIZACION_OBSERVADA")),
    ("CANCELADA", "Cancelada", ("CANCELADA",)),
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


def kilos(o):
    """V64: kg pedidos y kg despachados de la OV (envasados con su peso por unidad; granel y MP ya en kilos)."""
    from .orders import kg_unidad
    ls = [l for l in o.lines if l.activa]
    return (round(sum((l.cantidad or 0) * kg_unidad(l.product) for l in ls), 2),
            round(sum(min(l.despachado or 0, l.cantidad or 0) * kg_unidad(l.product) for l in ls), 2))


def fecha_despacho(o, parada, guias):
    """V69: cuándo sale la OV. Si ya salió: la fecha de su guía (SAP o SUNAT) o de la salida registrada (REAL).
    Si no: la fecha de la ruta en que está programada (PROGRAMADA). Si no tiene ruta: None."""
    fechas = sorted(g["fecha"] for g in (guias or []) if g.get("fecha"))
    if fechas:
        f = fechas[0]
        return {"fecha": f.date() if isinstance(f, datetime) else f, "tipo": "REAL", "ultima": fechas[-1]}
    if o.salida_ts:
        return {"fecha": o.salida_ts.date(), "tipo": "REAL", "ultima": None}
    if parada is not None:
        r = db().get(Route, parada.route_id)
        if r is not None and r.fecha:
            return {"fecha": r.fecha, "tipo": "PROGRAMADA", "ultima": None}
    return None


def tablero(desde=None, hasta=None, q="", vendedor_id=None, etapa_f=""):
    hoy = date.today()
    desde = desde or hoy - timedelta(days=15)
    hasta = hasta or hoy + timedelta(days=15)
    s = db()
    qry = select(SalesOrder).where(SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= hasta)
    if vendedor_id:
        qry = qry.where(__import__("app.services.orders", fromlist=["x"]).clausula_vendedor(vendedor_id))
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
        atrasada = o.fecha_compromiso < hoy and e not in ("DESPACHADA", "ENTREGADA", "CERRADA", "CANCELADA")
        kp, kd = kilos(o)
        fd = fecha_despacho(o, paradas.get(o.id), guias.get(o.id))
        filas.append({"o": o, "etapa": e, "despacho": fd, "guias": guias.get(o.id) or [], "kg_pedido": kp, "kg_despachado": kd, "avance": round(100 * kd / kp, 1) if kp else None,
                      "pasos": pasos(o, picks.get(o.id, []), paradas.get(o.id), facts.get(o.id, []),
                                                         guias.get(o.id)),
                      "atrasada": atrasada, "motivo": (o.bloqueo_ov or {}).get("motivo") if o.estado == "BLOQUEADA"
                      else (o.motivo_detencion if o.retenida_precio else "")})
    tot["ATRASADAS"] = sum(1 for o in ords if o.fecha_compromiso < hoy
                           and etapa(o) not in ("DESPACHADA", "ENTREGADA", "CERRADA", "CANCELADA"))
    return {"filas": filas, "tot": tot, "total": len(ords), "desde": desde, "hasta": hasta, "etapas": ETAPAS,
            "kg_pedido": round(sum(f["kg_pedido"] for f in filas), 2), "kg_despachado": round(sum(f["kg_despachado"] for f in filas), 2),
            "filtrado": bool(etapa_f)}
