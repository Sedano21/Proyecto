"""V69 (23-nov-2026): lo que falta despachar de las OV de venta abiertas de SAP, separado en vencido (fecha de
entrega ya pasada) y en plazo, en soles (con IGV) y en kilos, con el detalle por OV."""
from collections import defaultdict
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import Product, SapOrderLine


def _kg_u(p):
    from .orders import kg_unidad
    return kg_unidad(p) if p is not None else 0.0


def calcular(hoy=None, canal=""):
    """None si aún no hay OV de SAP con valor. Si no: {"VENCIDO": {...}, "EN_PLAZO": {...}, "ovs": [...]}."""
    hoy = hoy or date.today()
    if db().execute(select(SapOrderLine.id).limit(1)).first() is None:
        return None
    lineas = [x for x in db().execute(select(SapOrderLine).where(SapOrderLine.estado == "ABIERTA",
                                                                 SapOrderLine.clase == "VENTA")).scalars()
              if not x.linea_cerrada and (x.cantidad or 0) - (x.entregado or 0) > 1e-9]
    if canal:
        from ..models import Customer
        from .margin import channel
        nombres = {x.cliente for x in lineas}
        canal_de = {c.nombre: channel(c) for c in db().execute(select(Customer).where(Customer.nombre.in_(list(nombres) or [""])))
                    .scalars()}
        lineas = [x for x in lineas if canal_de.get(x.cliente) == canal]
    prods = {p.code: p for p in db().execute(select(Product).where(
        Product.code.in_(list({x.product_code for x in lineas}) or [""]))).scalars()}
    ovs = {}
    for x in lineas:
        saldo = (x.cantidad or 0) - (x.entregado or 0)
        valor = ((x.total or 0) + (x.igv or 0)) * saldo / x.cantidad if x.cantidad else 0.0
        o = ovs.setdefault(x.docnum, {"docnum": x.docnum, "cliente": x.cliente, "emision": x.fecha, "entrega": x.fecha_entrega,
                                      "tipo": "VENCIDO" if x.fecha_entrega and x.fecha_entrega < hoy else "EN_PLAZO",
                                      "soles": 0.0, "kg": 0.0, "lineas": []})
        kg = saldo * _kg_u(prods.get(x.product_code))
        o["soles"] += valor
        o["kg"] += kg
        o["lineas"].append({"code": x.product_code, "descripcion": x.descripcion, "pedido": x.cantidad,
                            "entregado": x.entregado or 0, "saldo": round(saldo, 2), "kg": round(kg, 1),
                            "soles": round(valor, 2)})
    tot = {t: {"soles": 0.0, "kg": 0.0, "n": 0} for t in ("VENCIDO", "EN_PLAZO")}
    for o in ovs.values():
        o["soles"], o["kg"] = round(o["soles"], 2), round(o["kg"], 1)
        o["dias"] = (hoy - o["entrega"]).days if o["entrega"] else None
        t = tot[o["tipo"]]
        t["soles"] += o["soles"]
        t["kg"] += o["kg"]
        t["n"] += 1
    for t in tot.values():
        t["soles"], t["kg"] = round(t["soles"], 2), round(t["kg"], 1)
    lista = sorted(ovs.values(), key=lambda o: (o["entrega"] or date.max, o["docnum"]))
    por_cliente = defaultdict(lambda: {"VENCIDO": 0.0, "EN_PLAZO": 0.0, "kg": 0.0})
    for o in lista:
        por_cliente[o["cliente"]][o["tipo"]] += o["soles"]
        por_cliente[o["cliente"]]["kg"] += o["kg"]
    return {"VENCIDO": tot["VENCIDO"], "EN_PLAZO": tot["EN_PLAZO"], "ovs": lista, "hoy": hoy,
            "total_soles": round(tot["VENCIDO"]["soles"] + tot["EN_PLAZO"]["soles"], 2),
            "total_kg": round(tot["VENCIDO"]["kg"] + tot["EN_PLAZO"]["kg"], 1)}
