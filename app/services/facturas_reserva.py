"""V30 (12-nov-2026): facturas de reserva de SAP con mercadería aún sin entregar.

- Se leen de SAP (solo lectura): facturas de reserva abiertas, no anuladas, con las líneas que aún tienen saldo por
  entregar y su OV de origen.
- Las ven las jefaturas de Almacén, Logística, Ventas, Operaciones y Producción.
- La Jefatura de Producción aprueba cuáles entran a la preprogramación de producción (si su OV no está ya abierta en el
  módulo, para no contarla dos veces).
- Mientras una OV tenga una factura de reserva con saldo por entregar, el módulo no la cierra aunque SAP cierre la OV.
"""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import SapReserveInvoiceLine, now
from .core import BusinessError, audit, has_perm, param


def _folio(d):
    return f"{d.get('FolioPrefixString') or ''}-{d.get('FolioNumber')}" if d.get("FolioNumber") else str(d.get("DocNum") or "")


def rows(sl, desde=None):
    """Líneas con saldo de las facturas de reserva abiertas de los últimos «sap_reservas_dias» (180) días."""
    from .sap_v29 import _por_entry
    desde = desde or (date.today() - timedelta(days=int(param("sap_reservas_dias", 180) or 180)))
    docs = sl.get_all("Invoices", {"$filter": f"ReserveInvoice eq 'tYES' and Cancelled eq 'tNO' and "
                                              f"DocumentStatus eq 'bost_Open' and DocDate ge '{desde.isoformat()}'",
                                   "$select": "DocEntry,DocNum,FolioPrefixString,FolioNumber,DocDate,DocDueDate,CardCode,"
                                              "CardName,DocumentLines"})
    ovs = _por_entry(sl, "Orders", [l.get("BaseEntry") for d in docs for l in d.get("DocumentLines") or []
                                    if l.get("BaseType") == 17], "DocEntry,DocNum")
    out = []
    for d in docs:
        for ln in d.get("DocumentLines") or []:
            pend = float(ln.get("RemainingOpenQuantity") or 0)
            if pend <= 1e-9 or not ln.get("ItemCode"):
                continue
            ov = ovs.get(ln.get("BaseEntry"), {}).get("DocNum") if ln.get("BaseType") == 17 else ""
            out.append({"clave": f"{d['DocEntry']}:{ln.get('LineNum', 0)}", "numero": _folio(d), "docnum": str(d.get("DocNum") or ""),
                        "fecha": str(d.get("DocDate") or "")[:10], "fecha_entrega": str(d.get("DocDueDate") or "")[:10],
                        "cliente": (d.get("CardName") or "")[:200], "codigo_cliente": (d.get("CardCode") or "")[:30],
                        "ov": str(ov or ""), "producto": ln.get("ItemCode")[:30], "descripcion": (ln.get("ItemDescription") or "")[:200],
                        "cantidad": float(ln.get("Quantity") or 0), "pendiente": pend})
    return out


def _f(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def guardar(filas):
    """Reemplaza la fotografía: actualiza las líneas que siguen con saldo (conservando la aprobación), agrega las nuevas
    y marca como no vigentes las que ya no tienen saldo."""
    s = db()
    act = {x.clave: x for x in s.execute(select(SapReserveInvoiceLine)).scalars()}
    vistas = set()
    for f in filas:
        x = act.get(f["clave"])
        if x is None:
            x = SapReserveInvoiceLine(clave=f["clave"], aprobacion={})
            s.add(x)
        x.numero, x.docnum, x.fecha, x.fecha_entrega = f["numero"], f["docnum"], _f(f["fecha"]), _f(f["fecha_entrega"])
        x.cliente, x.codigo_cliente, x.ov_numero = f["cliente"], f["codigo_cliente"], f["ov"]
        x.product_code, x.descripcion, x.cantidad, x.pendiente = f["producto"], f["descripcion"], f["cantidad"], f["pendiente"]
        x.vigente = True
        x.ts = now()
        vistas.add(f["clave"])
    for k, x in act.items():
        if k not in vistas:
            x.vigente = False
    s.flush()


def sync(user, sl=None):
    from .core import set_param
    from .sap_sl import ServiceLayer
    propio = sl is None
    sl = sl or ServiceLayer()
    try:
        if propio:
            sl.login()
        filas = rows(sl)
    finally:
        if propio:
            sl.logout()
    guardar(filas)
    res = {"lineas": len(filas), "facturas": len({f["numero"] for f in filas})}
    set_param("sap_reservas_ultimo", dict(res, ts=now().isoformat(timespec="minutes")), user)
    audit(user, "SAP_FACTURAS_RESERVA", "SapReserveInvoiceLine", "", res)
    return res


def vigentes():
    return list(db().execute(select(SapReserveInvoiceLine).where(SapReserveInvoiceLine.vigente.is_(True))
                             .order_by(SapReserveInvoiceLine.fecha_entrega, SapReserveInvoiceLine.numero,
                                       SapReserveInvoiceLine.id)).scalars())


def ov_con_reserva_pendiente():
    """Números de OV de SAP con una factura de reserva con saldo por entregar."""
    return {x.ov_numero for x in vigentes() if x.ov_numero and x.pendiente > 1e-9}


def decidir(user, lineas, aprobar, motivo=""):
    """La Jefatura de Producción aprueba (o no) usar estas líneas en la preprogramación de producción."""
    if not has_perm(user, "facturas_reserva.aprobar"):
        raise BusinessError("La aprobación para la preprogramación la da la Jefatura de Producción.")
    if not lineas:
        raise BusinessError("Elija al menos una línea.")
    if not aprobar and not (motivo or "").strip():
        raise BusinessError("Indique el motivo para no considerarla.")
    for x in lineas:
        x.aprobacion = {"estado": "APROBADA" if aprobar else "RECHAZADA", "user": user.nombre,
                        "ts": now().isoformat(timespec="minutes"), "motivo": (motivo or "").strip()[:300]}
    audit(user, "FACTURA_RESERVA_" + ("APROBADA" if aprobar else "RECHAZADA"), "SapReserveInvoiceLine",
          ",".join(x.clave for x in lineas), {"motivo": motivo})
    return len(lineas)


def para_preprogramacion():
    """Líneas aprobadas por la Jefatura de Producción cuya OV no está abierta en el módulo (si lo está, su faltante ya
    entra a la preprogramación por la OV)."""
    from ..models import SalesOrder
    from .stock import ORDEN_ESTADOS_CERRADOS
    abiertas = set()
    for numero, sap in db().execute(select(SalesOrder.numero, SalesOrder.sap_docnum).where(
            SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS))):
        abiertas |= {numero, sap}
    return [x for x in vigentes() if (x.aprobacion or {}).get("estado") == "APROBADA" and x.pendiente > 1e-9
            and x.ov_numero not in abiertas]
