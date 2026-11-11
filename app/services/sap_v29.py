"""V29 (11-nov-2026): lecturas de SAP para
1. separar las órdenes de VENTA de las órdenes de SERVICIO (según la serie del documento en SAP);
2. las notas de crédito que afectan a una OV todavía por despachar;
3. la fotografía de las órdenes (de venta y de servicio) del periodo, abiertas y cerradas, para la desviación de la demanda;
4. el balance de peso de las órdenes de fabricación y sus liquidaciones (insumos = producto + merma o desmedro).

Todo es SOLO LECTURA en SAP.
"""
from datetime import date, datetime, timedelta

from .core import BusinessError, param



# ------------------------------------------------------------------ 1. clase de la orden (venta / servicio)
def series_ordenes(sl):
    """{código de serie: nombre} de las órdenes de venta (documento 17). Si SAP no lo permite, {}.
    Es un método de servicio (POST) que solo lee: se usa únicamente en el comando «sap-series»; la sincronización solo
    hace consultas GET y clasifica por el código de la serie."""
    try:
        r = sl._req("POST", "SeriesService_GetDocumentSeries", {"DocumentTypeParams": {"Document": "17"}})
    except BusinessError:
        return {}
    return {x.get("Series"): str(x.get("Name") or "") for x in (r or {}).get("value", []) if x.get("Series") is not None}


def _series_servicio():
    return {str(x).strip().upper() for x in (param("sap_series_orden_servicio", []) or []) if str(x).strip()}


def clase_de(doc, series=None):
    """SERVICIO si el documento es de tipo servicio en SAP o su serie (código o nombre) está en
    «sap_series_orden_servicio»; si no, VENTA."""
    if doc.get("DocType") == "dDocument_Service":
        return "SERVICIO"
    cfg = _series_servicio()
    if cfg and doc.get("Series") is not None:
        nombre = (series or {}).get(doc.get("Series"), "")
        if str(doc.get("Series")).upper() in cfg or (nombre and nombre.strip().upper() in cfg):
            return "SERVICIO"
    return "VENTA"


def nombre_serie(doc, series=None):
    s = doc.get("Series")
    return (series or {}).get(s) or ("" if s is None else str(s))


# ------------------------------------------------------------------ 2. notas de crédito sobre OV
def _por_entry(sl, entidad, entries, sel):
    out = {}
    entries = sorted({int(e) for e in entries if e})
    for i in range(0, len(entries), 20):
        filtro = " or ".join(f"DocEntry eq {e}" for e in entries[i:i + 20])
        for d in sl.get_all(entidad, {"$filter": filtro, "$select": sel}):
            out[d["DocEntry"]] = d
    return out


def _folio(doc):
    return f"{doc.get('FolioPrefixString') or ''}-{doc.get('FolioNumber')}" if doc.get("FolioNumber") else str(doc.get("DocNum") or "")


def rows_nc_ov(sl, desde=None):
    """Líneas de notas de crédito de artículos (no anuladas) de los últimos «sap_facturas_dias» días basadas en una
    factura, con la OV de esa factura:
    - FACTURA_RESERVA / FACTURA_OV: la factura se hizo desde la OV (antes de la guía): la nota cambia lo que se despacha;
    - FACTURA_GUIA: la factura se hizo desde la guía: la mercadería ya salió (devolución o descuento): no cambia el picking.
    [{clave, nc_numero, factura, fecha, ov, producto, cantidad, origen, comentario}]"""
    desde = desde or (date.today() - timedelta(days=int(param("sap_facturas_dias", 60) or 60)))
    ncs = sl.get_all("CreditNotes", {"$filter": f"DocDate ge '{desde.isoformat()}' and Cancelled eq 'tNO' and "
                                                "DocType eq 'dDocument_Items'",
                                     "$select": "DocEntry,DocNum,FolioPrefixString,FolioNumber,DocDate,Comments,DocumentLines"})
    inv_e = [ln.get("BaseEntry") for nc in ncs for ln in nc.get("DocumentLines") or [] if ln.get("BaseType") == 13]
    facturas = _por_entry(sl, "Invoices", inv_e, "DocEntry,DocNum,FolioPrefixString,FolioNumber,ReserveInvoice,DocumentLines")
    ent_e = [l.get("BaseEntry") for f in facturas.values() for l in f.get("DocumentLines") or [] if l.get("BaseType") == 15]
    entregas = _por_entry(sl, "DeliveryNotes", ent_e, "DocEntry,DocNum,DocumentLines")
    ov_e = [l.get("BaseEntry") for f in list(facturas.values()) + list(entregas.values())
            for l in f.get("DocumentLines") or [] if l.get("BaseType") == 17]
    ovs = _por_entry(sl, "Orders", ov_e, "DocEntry,DocNum")
    out = []
    for nc in ncs:
        for ln in nc.get("DocumentLines") or []:
            if ln.get("BaseType") != 13 or ln.get("BaseEntry") not in facturas:
                continue  # nota manual o basada en una devolución: no se puede unir a una OV
            fac = facturas[ln["BaseEntry"]]
            fl = next((l for l in fac.get("DocumentLines") or [] if l.get("LineNum") == ln.get("BaseLine")), None) or \
                next((l for l in fac.get("DocumentLines") or [] if l.get("ItemCode") == ln.get("ItemCode")), None)
            if fl is None:
                continue
            ov, origen = "", ""
            if fl.get("BaseType") == 17 and fl.get("BaseEntry") in ovs:
                ov = ovs[fl["BaseEntry"]].get("DocNum")
                origen = "FACTURA_RESERVA" if fac.get("ReserveInvoice") == "tYES" else "FACTURA_OV"
            elif fl.get("BaseType") == 15 and fl.get("BaseEntry") in entregas:
                el = next((l for l in entregas[fl["BaseEntry"]].get("DocumentLines") or []
                           if l.get("BaseType") == 17 and l.get("BaseEntry") in ovs), None)
                ov = ovs[el["BaseEntry"]].get("DocNum") if el else ""
                origen = "FACTURA_GUIA"
            if not ov:
                continue
            out.append({"clave": f"{nc['DocEntry']}:{ln.get('LineNum', 0)}", "nc_numero": _folio(nc), "factura": _folio(fac),
                        "fecha": str(nc.get("DocDate") or "")[:10], "ov": str(ov), "producto": ln.get("ItemCode") or "",
                        "cantidad": float(ln.get("Quantity") or 0), "origen": origen,
                        "comentario": (nc.get("Comments") or "")[:500]})
    return out


# ------------------------------------------------------------------ 3. órdenes del periodo (abiertas y cerradas)
def rango_ordenes(hoy=None):
    """Desde el primer día de hace «sap_ordenes_meses» − 1 meses hasta el último día del mes siguiente."""
    hoy = hoy or date.today()
    meses = max(int(param("sap_ordenes_meses", 3) or 3), 1)
    y, m = hoy.year, hoy.month - (meses - 1)
    while m < 1:
        y, m = y - 1, m + 12
    desde = date(y, m, 1)
    y2, m2 = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
    hasta = (date(y2 + 1, 1, 1) if m2 == 12 else date(y2, m2 + 1, 1)) - timedelta(days=1)
    return desde, hasta


def rows_ordenes(sl, desde, hasta):
    """Órdenes de venta y de servicio de SAP con fecha de entrega en el rango, en cualquier estado."""
    series = {}
    out = []
    for o in sl.get_all("Orders", {"$filter": f"DocDueDate ge '{desde.isoformat()}' and DocDueDate le '{hasta.isoformat()}'",
                                   "$select": "DocNum,DocDate,DocDueDate,CardName,DocumentStatus,Cancelled,DocType,Series,"
                                              "DocumentLines"}):
        estado = "CANCELADA" if o.get("Cancelled") == "tYES" else ("CERRADA" if o.get("DocumentStatus") == "bost_Close"
                                                                    else "ABIERTA")
        clase, serie = clase_de(o, series), nombre_serie(o, series)
        for ln in o.get("DocumentLines") or []:
            q = float(ln.get("Quantity") or 0)
            pend = float(ln.get("RemainingOpenQuantity") or 0)
            out.append({"docnum": str(o.get("DocNum")), "clase": clase, "serie": serie[:40],
                        "fecha": str(o.get("DocDate") or "")[:10], "fecha_entrega": str(o.get("DocDueDate") or "")[:10],
                        "cliente": (o.get("CardName") or "")[:200], "estado": estado,
                        "producto": (ln.get("ItemCode") or "")[:30], "descripcion": (ln.get("ItemDescription") or "")[:200],
                        "cantidad": q, "entregado": max(q - pend, 0.0) if estado != "CANCELADA" else 0.0,
                        "linea_cerrada": ln.get("LineStatus") == "bost_Close"})
    return out


def guardar_ordenes(filas, desde, hasta):
    from sqlalchemy import delete
    from ..db import db
    from ..models import SapOrderLine
    s = db()
    s.execute(delete(SapOrderLine).where(SapOrderLine.fecha_entrega >= desde, SapOrderLine.fecha_entrega <= hasta))
    for f in filas:
        s.add(SapOrderLine(docnum=f["docnum"], clase=f["clase"], serie=f["serie"],
                           fecha=date.fromisoformat(f["fecha"]) if f["fecha"] else None,
                           fecha_entrega=date.fromisoformat(f["fecha_entrega"]) if f["fecha_entrega"] else None,
                           cliente=f["cliente"], estado=f["estado"], product_code=f["producto"], descripcion=f["descripcion"],
                           cantidad=f["cantidad"], entregado=f["entregado"], linea_cerrada=bool(f["linea_cerrada"])))
    s.flush()


def sync_ordenes(user, sl=None):
    from .core import audit, set_param
    from .sap_sl import ServiceLayer
    desde, hasta = rango_ordenes()
    propio = sl is None
    sl = sl or ServiceLayer()
    try:
        if propio:
            sl.login()
        filas = rows_ordenes(sl, desde, hasta)
    finally:
        if propio:
            sl.logout()
    guardar_ordenes(filas, desde, hasta)
    docs = {(f["docnum"]) for f in filas}
    res = {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "ordenes": len(docs), "lineas": len(filas),
           "servicio": len({f["docnum"] for f in filas if f["clase"] == "SERVICIO"})}
    set_param("sap_ordenes_ultimo", dict(res, ts=datetime.now().isoformat(timespec="minutes")), user)
    audit(user, "SAP_ORDENES_PERIODO", "SapOrderLine", "", res)
    return res


# ------------------------------------------------------------------ 4. órdenes de fabricación para el balance de peso
def rows_ordenes_fabricacion(sl, desde=None):
    """Órdenes de fabricación de SAP (no canceladas) de los últimos «sap_liquidacion_dias» días con sus componentes:
    lo planificado y lo emitido de cada componente, y lo planificado, completado y rechazado del producto."""
    desde = desde or (date.today() - timedelta(days=int(param("sap_liquidacion_dias", 30) or 30)))
    est = {"boposPlanned": "PLANIFICADA", "boposReleased": "LIBERADA", "boposClosed": "CERRADA"}
    out = []
    for po in sl.get_all("ProductionOrders", {
            "$filter": f"PostingDate ge '{desde.isoformat()}' and ProductionOrderStatus ne 'boposCancelled'",
            "$select": "AbsoluteEntry,DocumentNumber,ItemNo,ProductDescription,PlannedQuantity,CompletedQuantity,"
                       "RejectedQuantity,ProductionOrderStatus,PostingDate,ProductionOrderLines"}):
        comps = []
        for ln in po.get("ProductionOrderLines") or []:
            if ln.get("ItemType") not in (None, "pit_Item"):
                continue  # recursos (horas, máquinas) y textos no pesan
            comps.append({"producto": ln.get("ItemNo") or "", "planificado": float(ln.get("PlannedQuantity") or 0),
                          "emitido": float(ln.get("IssuedQuantity") or 0)})
        out.append({"orden": str(po.get("DocumentNumber") or po.get("AbsoluteEntry")), "producto": po.get("ItemNo") or "",
                    "descripcion": po.get("ProductDescription") or "", "estado": est.get(po.get("ProductionOrderStatus"),
                                                                                       po.get("ProductionOrderStatus") or ""),
                    "fecha": str(po.get("PostingDate") or "")[:10], "planificado": float(po.get("PlannedQuantity") or 0),
                    "completado": float(po.get("CompletedQuantity") or 0), "rechazado": float(po.get("RejectedQuantity") or 0),
                    "componentes": comps})
    return out
