"""V52 (17-nov-2026): facturación del mes desde SAP.

«Cómo va la empresa» mostraba como «Venta del mes» la suma de las OV del módulo, que no es la facturación que reporta
Comercial (facturas − notas de crédito de SAP). Además, las facturas de SAP solo quedaban en el módulo si el cliente ya
existía en su maestro. Aquí se leen de SAP todas las facturas y notas de crédito (no anuladas) con su total en soles
(DocTotal, moneda local) y su IGV (VatSum), sin depender del maestro de clientes."""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import SapBilling, now
from .core import param


def sync(user, sl=None, desde=None):
    from . import sap_sl
    from .sap_v31 import historial_desde
    hay = db().execute(select(SapBilling.id).limit(1)).first() is not None
    hoy = date.today()
    # la primera vez, desde el inicio del historial (para comparar con el año anterior); luego, el mes en curso y el
    # anterior (las notas de crédito o anulaciones tardías)
    desde = desde or ((hoy.replace(day=1) - timedelta(days=1)).replace(day=1) if hay else historial_desde())
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    try:
        if propio:
            sl.login()
        docs = []
        for tipo, ent in (("FACTURA", "Invoices"), ("NOTA_CREDITO", "CreditNotes")):
            for d in sl.get_all(ent, {"$filter": f"DocDate ge '{desde.isoformat()}'",
                                      "$select": "DocEntry,DocNum,FolioPrefixString,FolioNumber,CardCode,CardName,DocDate,"
                                                 "DocCurrency,DocTotal,VatSum,Cancelled"}):
                docs.append((tipo, d))
    finally:
        if propio:
            sl.logout()
    existentes = {x.clave: x for x in db().execute(select(SapBilling).where(SapBilling.fecha >= desde)).scalars()}
    nuevas = act = anuladas = 0
    vistos = set()
    for tipo, d in docs:
        clave = f"{tipo}:{d.get('DocEntry')}"
        vistos.add(clave)
        if d.get("Cancelled") in ("tYES", "csYes", "Y"):
            if clave in existentes:
                db().delete(existentes.pop(clave))
                anuladas += 1
            continue
        try:
            fecha = sap_sl._d(d.get("DocDate"))
        except ValueError:
            fecha = None
        if fecha is None:
            continue
        datos = {"tipo": tipo, "numero": sap_sl._folio(d), "fecha": fecha, "cardcode": (d.get("CardCode") or "")[:30],
                 "cliente": (d.get("CardName") or "")[:200], "moneda": (d.get("DocCurrency") or "")[:10],
                 "total": float(d.get("DocTotal") or 0), "igv": float(d.get("VatSum") or 0)}
        x = existentes.get(clave)
        if x is None:
            db().add(SapBilling(clave=clave, ts=now(), **datos))
            nuevas += 1
        elif any(getattr(x, k) != v for k, v in datos.items()):
            for k, v in datos.items():
                setattr(x, k, v)
            act += 1
    db().flush()
    return {"desde": desde.isoformat(), "leidas": len(docs), "nuevas": nuevas, "actualizadas": act, "anuladas": anuladas}


def resumen(desde, hasta, canal=""):
    """Facturación del periodo: facturas, notas de crédito y neto, con y sin IGV. None si no hay datos de SAP."""
    q = select(SapBilling).where(SapBilling.fecha >= desde, SapBilling.fecha <= hasta)
    docs = list(db().execute(q).scalars())
    if not docs and db().execute(select(SapBilling.id).limit(1)).first() is None:
        return None
    if canal:
        from ..models import Customer
        from .margin import channel
        nombres = {d.cliente for d in docs}
        canal_de = {c.nombre: channel(c) for c in db().execute(select(Customer).where(Customer.nombre.in_(list(nombres) or [""])))
                    .scalars()}
        docs = [d for d in docs if canal_de.get(d.cliente) == canal]
    fac = [d for d in docs if d.tipo == "FACTURA"]
    nc = [d for d in docs if d.tipo == "NOTA_CREDITO"]
    t = lambda xs: round(sum(x.total for x in xs), 2)  # noqa: E731
    b = lambda xs: round(sum(x.total - x.igv for x in xs), 2)  # noqa: E731
    return {"facturas": t(fac), "notas_credito": t(nc), "neto": round(t(fac) - t(nc), 2), "n_facturas": len(fac),
            "n_notas": len(nc), "facturas_sin_igv": b(fac), "notas_sin_igv": b(nc), "neto_sin_igv": round(b(fac) - b(nc), 2),
            "desde": desde, "hasta": hasta, "ultima": max((d.fecha for d in docs), default=None)}


def ov_del_periodo(desde, hasta, canal=""):
    """V55: las OV de SAP con despacho (fecha de entrega) en el periodo, sin las anuladas: su valor en soles con y sin
    IGV (líneas de la OV), lo ya despachado (proporcional a lo entregado) y lo que falta despachar; además, las que
    se ingresaron (emitieron) en el periodo. None si las OV de SAP aún no traen su valor (se completa en la próxima
    lectura del historial)."""
    from ..models import SapOrderLine
    if db().execute(select(SapOrderLine.id).where(SapOrderLine.total != 0).limit(1)).first() is None:
        return None
    lineas = list(db().execute(select(SapOrderLine).where(SapOrderLine.fecha_entrega >= desde,
                                                          SapOrderLine.fecha_entrega <= hasta,
                                                          SapOrderLine.estado != "CANCELADA")).scalars())
    ingresadas = list(db().execute(select(SapOrderLine).where(SapOrderLine.fecha >= desde, SapOrderLine.fecha <= hasta,
                                                              SapOrderLine.estado != "CANCELADA")).scalars())
    if canal:
        from ..models import Customer
        from .margin import channel
        nombres = {x.cliente for x in lineas + ingresadas}
        canal_de = {c.nombre: channel(c) for c in db().execute(select(Customer).where(Customer.nombre.in_(list(nombres) or [""])))
                    .scalars()}
        lineas = [x for x in lineas if canal_de.get(x.cliente) == canal]
        ingresadas = [x for x in ingresadas if canal_de.get(x.cliente) == canal]
    con = lambda x: (x.total or 0) + (x.igv or 0)  # noqa: E731
    frac = lambda x: min((x.entregado or 0) / x.cantidad, 1.0) if x.cantidad else 0.0  # noqa: E731
    total = sum(con(x) for x in lineas)
    desp = sum(con(x) * frac(x) for x in lineas)
    return {"total": round(total, 2), "sin_igv": round(sum(x.total or 0 for x in lineas), 2),
            "despachado": round(desp, 2), "por_despachar": round(total - desp, 2), "n": len({x.docnum for x in lineas}),
            "ingresadas": round(sum(con(x) for x in ingresadas), 2), "n_ingresadas": len({x.docnum for x in ingresadas}),
            "desde": desde, "hasta": hasta}


def detalle(desde, hasta, tipo=""):
    """V55: documentos de SAP del periodo (facturas y notas de crédito), con el resumen y el neto por cliente."""
    q = select(SapBilling).where(SapBilling.fecha >= desde, SapBilling.fecha <= hasta)
    docs = list(db().execute(q.order_by(SapBilling.fecha.desc(), SapBilling.numero)).scalars())
    por_cli = {}
    for d in docs:
        c = por_cli.setdefault(d.cliente or d.cardcode, {"cliente": d.cliente or d.cardcode, "facturas": 0.0, "notas": 0.0,
                                                          "n_facturas": 0, "n_notas": 0})
        if d.tipo == "FACTURA":
            c["facturas"] += d.total
            c["n_facturas"] += 1
        else:
            c["notas"] += d.total
            c["n_notas"] += 1
    for c in por_cli.values():
        c["neto"] = round(c["facturas"] - c["notas"], 2)
    lista = [d for d in docs if not tipo or d.tipo == tipo]
    return {"resumen": resumen(desde, hasta), "docs": lista,
            "clientes": sorted(por_cli.values(), key=lambda c: -c["neto"])}


def ov_detalle(desde, hasta):
    """V55: OV de SAP con despacho en el periodo, una fila por OV: cliente, fecha, estado, valor, despachado y saldo."""
    from ..models import SapOrderLine
    lineas = list(db().execute(select(SapOrderLine).where(SapOrderLine.fecha_entrega >= desde,
                                                          SapOrderLine.fecha_entrega <= hasta,
                                                          SapOrderLine.estado != "CANCELADA")).scalars())
    ovs = {}
    for x in lineas:
        con = (x.total or 0) + (x.igv or 0)
        frac = min((x.entregado or 0) / x.cantidad, 1.0) if x.cantidad else 0.0
        o = ovs.setdefault(x.docnum, {"docnum": x.docnum, "cliente": x.cliente, "fecha": x.fecha, "entrega": x.fecha_entrega,
                                      "estado": x.estado, "clase": x.clase, "total": 0.0, "despachado": 0.0, "lineas": 0})
        o["total"] += con
        o["despachado"] += con * frac
        o["lineas"] += 1
    for o in ovs.values():
        o["saldo"] = round(o["total"] - o["despachado"], 2)
    return sorted(ovs.values(), key=lambda o: (o["entrega"] or date.min, o["docnum"]))
