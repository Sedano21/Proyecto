"""V31 (13-nov-2026): historial de SAP desde julio («sap_historial_desde»), solo lectura.

- Órdenes de venta y de servicio ABIERTAS Y CERRADAS (con sus líneas, lo entregado y la clase), para la conciliación por
  mes y la ejecución de la demanda.
- Guías (entregas) con su OV y su factura, y consumos de producción (emisiones a órdenes de fabricación), para la
  conciliación y la rotación (venta y producción).

La primera lectura trae todo desde julio; las siguientes, solo lo creado o modificado en SAP desde la última lectura
(con un día de margen): así el botón «Actualizar con SAP» trae únicamente lo que falta.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

from ..db import db
from ..models import SapMovement, SapOrderLine, now
from .core import audit, param, set_param


def historial_desde():
    v = param("sap_historial_desde", "2026-07-01") or "2026-07-01"
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return date(2026, 7, 1)


HASTA_ABIERTO = date(2099, 12, 31)
# V33: al cambiar lo que se guarda (p. ej. las órdenes de servicio), la siguiente lectura vuelve a traer todo una vez
HISTORIAL_VERSION = 2


def _f(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _folio(d):
    return f"{d.get('FolioPrefixString') or ''}-{d.get('FolioNumber')}" if d.get("FolioNumber") else str(d.get("DocNum") or "")


# ------------------------------------------------------------------ órdenes (abiertas y cerradas)
def rows_ordenes(sl, desde, cambios_desde=None):
    from .sap_v29 import clase_de, nombre_serie
    filtro = f"(DocDate ge '{desde.isoformat()}' or DocDueDate ge '{desde.isoformat()}')"
    if cambios_desde:
        filtro += f" and UpdateDate ge '{cambios_desde.isoformat()}'"
    out = []
    for o in sl.get_all("Orders", {"$filter": filtro,
                                   "$select": "DocNum,DocDate,DocDueDate,CardName,DocumentStatus,Cancelled,DocType,Series,"
                                              "Comments,DocumentLines"}):
        estado = "CANCELADA" if o.get("Cancelled") == "tYES" else ("CERRADA" if o.get("DocumentStatus") == "bost_Close"
                                                                    else "ABIERTA")
        clase, serie = clase_de(o), nombre_serie(o)
        lineas = o.get("DocumentLines") or []
        servicio = o.get("DocType") == "dDocument_Service"
        for ln in lineas or [{}]:
            q = float(ln.get("Quantity") or 0)
            pend = float(ln.get("RemainingOpenQuantity") or 0)
            if servicio or not ln.get("ItemCode"):
                # V33: las órdenes de SERVICIO de SAP no tienen artículo (la línea es un servicio con su cuenta): se
                # guardan como «SERVICIO» con su descripción; se dan por atendidas cuando la línea o la orden se cierra
                q = q or 1.0
                cerrada = ln.get("LineStatus") == "bost_Close" or estado == "CERRADA"
                out.append({"docnum": str(o.get("DocNum")), "clase": "SERVICIO" if servicio else clase, "serie": serie[:40],
                            "fecha": str(o.get("DocDate") or "")[:10], "fecha_entrega": str(o.get("DocDueDate") or "")[:10],
                            "cliente": (o.get("CardName") or "")[:200], "estado": estado, "producto": "SERVICIO",
                            "descripcion": (ln.get("ItemDescription") or o.get("Comments") or "Servicio")[:200],
                            "cantidad": q, "entregado": q if cerrada and estado != "CANCELADA" else 0.0,
                            "linea_cerrada": cerrada})
                continue
            out.append({"docnum": str(o.get("DocNum")), "clase": clase, "serie": serie[:40],
                        "fecha": str(o.get("DocDate") or "")[:10], "fecha_entrega": str(o.get("DocDueDate") or "")[:10],
                        "cliente": (o.get("CardName") or "")[:200], "estado": estado,
                        "producto": (ln.get("ItemCode") or "")[:30], "descripcion": (ln.get("ItemDescription") or "")[:200],
                        "cantidad": q, "entregado": max(q - pend, 0.0) if estado != "CANCELADA" else 0.0,
                        "linea_cerrada": ln.get("LineStatus") == "bost_Close"})
    return out


def guardar_ordenes(filas, completo):
    s = db()
    if completo:
        s.execute(delete(SapOrderLine))
    else:
        docs = {f["docnum"] for f in filas}
        for i in range(0, len(docs), 500):
            s.execute(delete(SapOrderLine).where(SapOrderLine.docnum.in_(list(docs)[i:i + 500])))
    for f in filas:
        if not f["producto"]:
            continue
        s.add(SapOrderLine(docnum=f["docnum"], clase=f["clase"], serie=f["serie"], fecha=_f(f["fecha"]),
                           fecha_entrega=_f(f["fecha_entrega"]), cliente=f["cliente"], estado=f["estado"],
                           product_code=f["producto"], descripcion=f["descripcion"], cantidad=f["cantidad"],
                           entregado=f["entregado"], linea_cerrada=bool(f["linea_cerrada"])))
    s.flush()


# ------------------------------------------------------------------ guías y consumos de producción
def rows_guias(sl, desde, cambios_desde=None):
    from .sap_v29 import _por_entry
    filtro = f"DocDate ge '{desde.isoformat()}' and Cancelled eq 'tNO'"
    if cambios_desde:
        filtro += f" and UpdateDate ge '{cambios_desde.isoformat()}'"
    docs = sl.get_all("DeliveryNotes", {"$filter": filtro, "$select": "DocEntry,DocNum,FolioPrefixString,FolioNumber,DocDate,"
                                                                       "CardName,DocumentLines"})
    ovs = _por_entry(sl, "Orders", [l.get("BaseEntry") for d in docs for l in d.get("DocumentLines") or []
                                    if l.get("BaseType") == 17], "DocEntry,DocNum")
    out = []
    for d in docs:
        for ln in d.get("DocumentLines") or []:
            if not ln.get("ItemCode"):
                continue
            ov = ovs.get(ln.get("BaseEntry"), {}).get("DocNum") if ln.get("BaseType") == 17 else ""
            out.append({"clave": f"GUIA:{d['DocEntry']}:{ln.get('LineNum', 0)}", "tipo": "GUIA", "docentry": d["DocEntry"],
                        "documento": _folio(d), "fecha": str(d.get("DocDate") or "")[:10], "ov": str(ov or ""),
                        "of": "", "factura": "", "cliente": (d.get("CardName") or "")[:200], "producto": ln["ItemCode"][:30],
                        "cantidad": float(ln.get("Quantity") or 0)})
    return out


def rows_consumos(sl, desde, cambios_desde=None):
    """Emisiones para producción: salidas de mercancía con líneas basadas en una orden de fabricación (BaseType 202)."""
    filtro = f"DocDate ge '{desde.isoformat()}'"
    if cambios_desde:
        filtro += f" and UpdateDate ge '{cambios_desde.isoformat()}'"
    out = []
    for d in sl.get_all("InventoryGenExits", {"$filter": filtro, "$select": "DocEntry,DocNum,DocDate,DocumentLines"}):
        for ln in d.get("DocumentLines") or []:
            if ln.get("BaseType") != 202 or not ln.get("ItemCode"):
                continue
            out.append({"clave": f"CONSUMO:{d['DocEntry']}:{ln.get('LineNum', 0)}", "tipo": "CONSUMO", "docentry": d["DocEntry"],
                        "documento": str(d.get("DocNum") or ""), "fecha": str(d.get("DocDate") or "")[:10], "ov": "",
                        "of": str(ln.get("BaseEntry") or ""), "factura": "", "cliente": "", "producto": ln["ItemCode"][:30],
                        "cantidad": float(ln.get("Quantity") or 0)})
    return out


def guardar_movimientos(filas, completo, tipos=("GUIA", "CONSUMO")):
    s = db()
    if completo:
        s.execute(delete(SapMovement).where(SapMovement.tipo.in_(tipos)))
    else:
        for t in tipos:
            docs = sorted({f["docentry"] for f in filas if f["tipo"] == t})
            for i in range(0, len(docs), 500):
                s.execute(delete(SapMovement).where(SapMovement.tipo == t, SapMovement.docentry.in_(docs[i:i + 500])))
    for f in filas:
        s.add(SapMovement(clave=f["clave"][:50], tipo=f["tipo"], docentry=int(f["docentry"]), documento=f["documento"][:40],
                          fecha=_f(f["fecha"]), ov_numero=f["ov"][:30], orden_fabricacion=f["of"][:30],
                          factura=f["factura"][:40], cliente=f["cliente"], product_code=f["producto"],
                          cantidad=f["cantidad"]))
    s.flush()


# ------------------------------------------------------------------ lectura completa o incremental
def sync_historial(user, sl=None, completo=False):
    """Órdenes, guías y consumos de SAP desde julio. Incremental (solo lo creado o modificado desde la última lectura)
    salvo la primera vez, si se pide completo o si cambió la fecha de inicio del historial."""
    from .sap_sl import ServiceLayer
    desde = historial_desde()
    ult = param("sap_ordenes_ultimo", {}) or {}
    previo = _f(ult.get("desde"))
    completo = (completo or not ult.get("ts") or previo != desde or not ult.get("historial")
                or ult.get("version") != HISTORIAL_VERSION)
    cambios = None
    if not completo:
        try:
            cambios = datetime.fromisoformat(ult["ts"]).date() - timedelta(days=1)
        except (KeyError, ValueError):
            completo, cambios = True, None
    propio = sl is None
    sl = sl or ServiceLayer()
    try:
        if propio:
            sl.login()
        ordenes = rows_ordenes(sl, desde, cambios)
        movs = rows_guias(sl, desde, cambios)
        try:
            movs += rows_consumos(sl, desde, cambios)
            consumo_err = ""
        except Exception as e:  # noqa: BLE001  (sin permiso de lectura de salidas: las guías y órdenes se guardan igual)
            consumo_err = str(e)[:200]
    finally:
        if propio:
            sl.logout()
    guardar_ordenes(ordenes, completo)
    guardar_movimientos(movs, completo, ("GUIA", "CONSUMO") if not consumo_err else ("GUIA",))
    res = {"desde": desde.isoformat(), "hasta": HASTA_ABIERTO.isoformat(), "historial": True, "version": HISTORIAL_VERSION,
           "modo": "completa" if completo else f"cambios desde {cambios:%d/%m/%Y}",
           "ordenes": len({f["docnum"] for f in ordenes}), "lineas": len(ordenes),
           "servicio": len({f["docnum"] for f in ordenes if f["clase"] == "SERVICIO"}),
           "guias": len({m["docentry"] for m in movs if m["tipo"] == "GUIA"}),
           "consumos": len({m["docentry"] for m in movs if m["tipo"] == "CONSUMO"})}
    if consumo_err:
        res["consumos_error"] = consumo_err
    set_param("sap_ordenes_ultimo", dict(res, ts=now().isoformat(timespec="minutes")), user)
    audit(user, "SAP_HISTORIAL", "SapOrderLine", "", res)
    return res


def tiene_historial():
    return bool((param("sap_ordenes_ultimo", {}) or {}).get("historial")) and \
        db().execute(select(SapOrderLine.id).limit(1)).first() is not None
