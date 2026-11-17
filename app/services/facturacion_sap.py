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
