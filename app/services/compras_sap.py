"""V55 (17-nov-2026): órdenes de compra de SAP (PurchaseOrders) para el indicador de compras y su detalle.

Se lee qué se compró, a qué proveedor, cuánto, cuánto ya se recibió y su valor en soles (LineTotal y TaxTotal de la
línea, en moneda local). La primera lectura trae desde el inicio del historial; luego, lo creado o modificado en SAP
desde el día anterior a la última lectura (incluye recepciones y cierres). Solo lee: no cambia nada en SAP."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

from ..db import db
from ..models import SapPurchaseLine, now
from .core import param, set_param


def _estado(d):
    if d.get("Cancelled") in ("tYES", "csYes", "Y"):
        return "CANCELADA"
    return "CERRADA" if d.get("DocumentStatus") == "bost_Close" else "ABIERTA"


def rows(sl, desde=None, cambios_desde=None):
    from . import sap_sl
    filtro = f"DocDate ge '{desde.isoformat()}'" if desde else ""
    if cambios_desde:
        filtro = (filtro + " and " if filtro else "") + f"UpdateDate ge '{cambios_desde.isoformat()}'"
    out = []
    for d in sl.get_all("PurchaseOrders", {"$filter": filtro,
                                           "$select": "DocEntry,DocNum,DocDate,DocDueDate,CardCode,CardName,DocCurrency,"
                                                      "DocumentStatus,Cancelled,DocumentLines"}):
        est = _estado(d)
        for ln in d.get("DocumentLines") or []:
            q = float(ln.get("Quantity") or 0)
            pend = float(ln.get("RemainingOpenQuantity") or 0)
            cerrada = ln.get("LineStatus") == "bost_Close"
            if est == "CANCELADA":
                recibido = 0.0
            elif "RemainingOpenQuantity" in ln:
                recibido = max(q - pend, 0.0)
            else:
                recibido = q if cerrada else 0.0
            try:
                fecha, entrega = sap_sl._d(d.get("DocDate")), sap_sl._d(d.get("DocDueDate"))
            except ValueError:
                fecha = entrega = None
            out.append({"clave": f"{d['DocEntry']}:{ln.get('LineNum', 0)}", "docentry": int(d["DocEntry"]),
                        "docnum": str(d.get("DocNum") or ""), "fecha": fecha, "fecha_entrega": entrega,
                        "cardcode": (d.get("CardCode") or "")[:30], "proveedor": (d.get("CardName") or "")[:200],
                        "estado": est, "moneda": (d.get("DocCurrency") or "")[:10],
                        "product_code": (ln.get("ItemCode") or "SERVICIO")[:30],
                        "descripcion": (ln.get("ItemDescription") or "")[:200], "cantidad": q, "recibido": recibido,
                        "total": float(ln.get("LineTotal") or 0), "igv": float(ln.get("TaxTotal") or 0)})
    return out


def sync(user, sl=None):
    from . import sap_sl
    from .sap_v31 import historial_desde
    ult = param("sap_compras_ultimo", {}) or {}
    hay = db().execute(select(SapPurchaseLine.id).limit(1)).first() is not None
    cambios = None
    if hay and ult.get("ts"):
        cambios = datetime.fromisoformat(ult["ts"]).date() - timedelta(days=1)
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    try:
        if propio:
            sl.login()
        filas = rows(sl, None if cambios else historial_desde(), cambios)
    finally:
        if propio:
            sl.logout()
    docs = sorted({f["docentry"] for f in filas})
    for i in range(0, len(docs), 500):
        db().execute(delete(SapPurchaseLine).where(SapPurchaseLine.docentry.in_(docs[i:i + 500])))
    for f in filas:
        db().add(SapPurchaseLine(ts=now(), **f))
    db().flush()
    res = {"ts": datetime.now().isoformat(timespec="minutes"), "modo": f"cambios desde {cambios:%d/%m/%Y}" if cambios
           else "completa", "ordenes": len(docs), "lineas": len(filas)}
    set_param("sap_compras_ultimo", res, user)
    return res


def sync_seguro(user, sl=None):
    """Para el vigilante: un error inesperado al leer las compras no debe frenar el resto de la revisión."""
    from .core import BusinessError
    from .sap_sl import SapConnectionError
    try:
        return sync(user, sl=sl)
    except (BusinessError, SapConnectionError):
        raise
    except Exception as e:  # noqa: BLE001
        raise BusinessError(f"No se pudieron leer las órdenes de compra de SAP: {str(e)[:200]}") from e


def resumen(desde, hasta):
    """Órdenes de compra de SAP emitidas en el periodo (sin las anuladas): valor total (con y sin IGV), recibido y por
    recibir (proporcional a la cantidad), por moneda del documento y por proveedor. None si nunca se leyó SAP."""
    if db().execute(select(SapPurchaseLine.id).limit(1)).first() is None:
        return None
    lineas = list(db().execute(select(SapPurchaseLine).where(SapPurchaseLine.fecha >= desde, SapPurchaseLine.fecha <= hasta,
                                                             SapPurchaseLine.estado != "CANCELADA")).scalars())
    tot = sin = rec = 0.0
    por_moneda, por_prov, por_prod = defaultdict(float), defaultdict(lambda: {"total": 0.0, "ordenes": set()}), \
        defaultdict(lambda: {"descripcion": "", "cantidad": 0.0, "recibido": 0.0, "total": 0.0})
    ordenes = defaultdict(lambda: {"lineas": [], "total": 0.0, "recibido": 0.0})
    for ln in lineas:
        con = (ln.total or 0) + (ln.igv or 0)
        tot += con
        sin += ln.total or 0
        frac = min((ln.recibido or 0) / ln.cantidad, 1.0) if ln.cantidad else (1.0 if ln.estado == "CERRADA" else 0.0)
        rec += con * frac
        por_moneda[ln.moneda or "—"] += con
        pv = por_prov[ln.proveedor or ln.cardcode]
        pv["total"] += con
        pv["ordenes"].add(ln.docnum)
        pp = por_prod[ln.product_code]
        pp["descripcion"] = pp["descripcion"] or ln.descripcion
        pp["cantidad"] += ln.cantidad or 0
        pp["recibido"] += ln.recibido or 0
        pp["total"] += con
        o = ordenes[ln.docnum]
        o.update({"docnum": ln.docnum, "fecha": ln.fecha, "proveedor": ln.proveedor, "estado": ln.estado,
                  "moneda": ln.moneda, "entrega": ln.fecha_entrega})
        o["lineas"].append(ln)
        o["total"] += con
        o["recibido"] += con * frac
    return {"total": round(tot, 2), "sin_igv": round(sin, 2), "recibido": round(rec, 2), "por_recibir": round(tot - rec, 2),
            "n_ordenes": len(ordenes), "abiertas": sum(1 for o in ordenes.values() if o["estado"] == "ABIERTA"),
            "por_moneda": dict(por_moneda),
            "proveedores": sorted(({"proveedor": k, "total": round(v["total"], 2), "ordenes": len(v["ordenes"])}
                                   for k, v in por_prov.items()), key=lambda x: -x["total"]),
            "productos": sorted(({"codigo": k, **v} for k, v in por_prod.items()), key=lambda x: -x["total"]),
            "ordenes": sorted(ordenes.values(), key=lambda o: (o["fecha"] or date.min, o["docnum"]), reverse=True),
            "ultima": (param("sap_compras_ultimo", {}) or {}).get("ts")}
