"""V53 (17-nov-2026): las compras por OV se actualizan solas cuando la OV ya se atendió.

Una presolicitud de compra nacida de una OV deja de «faltar» cuando esa OV ya se atendió en SAP o en el módulo:
- la OV está cerrada o anulada en SAP (historial de SAP), o
- sus guías de SAP ya cubren lo pedido de ese producto, o
- la OV del módulo está despachada, entregada o cancelada.
Lo atendido se quita de la presolicitud (y del consolidado de compras). Si la presolicitud aún no pasó a Compras
(borrador o pendiente de Logística) se reduce o se cancela sola; si ya está en Compras (cotización, orden…), no se
toca y se avisa a Compras y Logística para que la revisen."""
from collections import defaultdict

from sqlalchemy import select

from ..db import db
from ..models import PurchaseRequest, SalesOrder, SapMovement, SapOrderLine
from . import alerts
from .core import audit

ATENDIDA_MODULO = ("DESPACHADA", "ENTREGADA", "CANCELADA")


def _numeros(numero):
    """El número de la OV en el módulo y en SAP (pueden diferir)."""
    nums = {str(numero or "").strip()}
    o = db().execute(select(SalesOrder).where(SalesOrder.numero == str(numero))).scalars().first()
    if o is not None and o.sap_docnum:
        nums.add(o.sap_docnum)
    o2 = db().execute(select(SalesOrder).where(SalesOrder.sap_docnum == str(numero))).scalars().first()
    return {n for n in nums if n}, (o or o2)


def atendida(numero, product_code):
    """(True/False, motivo): si la OV ya no necesita lo comprado de ese producto."""
    nums, o = _numeros(numero)
    if o is not None and o.estado in ATENDIDA_MODULO:
        return True, f"OV {numero} {o.estado.lower()} en el módulo"
    lineas = list(db().execute(select(SapOrderLine).where(SapOrderLine.docnum.in_(nums))).scalars())
    if lineas and all(l.estado in ("CERRADA", "CANCELADA") for l in lineas):
        return True, f"OV {numero} {'anulada' if lineas[0].estado == 'CANCELADA' else 'cerrada'} en SAP"
    pedido = sum(l.cantidad or 0 for l in lineas if l.product_code == product_code)
    guiado = sum(m.cantidad or 0 for m in db().execute(select(SapMovement).where(
        SapMovement.tipo == "GUIA", SapMovement.ov_numero.in_(nums), SapMovement.product_code == product_code)).scalars())
    if pedido and guiado >= pedido - 1e-9:
        return True, f"OV {numero}: sus guías de SAP ya cubren {product_code} ({guiado:g} de {pedido:g})"
    if o is not None:
        ls = [l for l in o.lines if l.activa and l.product_code == product_code]
        if ls and all((l.despachado or 0) >= l.cantidad - 1e-9 for l in ls):
            return True, f"OV {numero}: {product_code} ya despachado en el módulo"
    return False, ""


def revisar(user=None):
    """Revisa las presolicitudes de compra abiertas con OV. Devuelve cuántas se ajustaron y cuántas se avisaron."""
    from .compras_v24 import CERRADAS, _destinos
    from .purchasing import AGRUPABLES
    ajustadas = avisadas = 0
    for r in db().execute(select(PurchaseRequest).where(PurchaseRequest.estado.notin_(CERRADAS + ("ANULADA",)))).scalars():
        dest = _destinos(r)
        ovs = [d for d in dest if d.get("tipo") == "OV" and d.get("ov")]
        if not ovs:
            continue
        resueltas = []
        for d in ovs:
            ok, motivo = atendida(d["ov"], r.product_code)
            if ok:
                resueltas.append((d, motivo))
        if not resueltas:
            continue
        motivos = "; ".join(m for _, m in resueltas)
        if r.estado in AGRUPABLES:
            quitar = defaultdict(float)
            for d, _ in resueltas:
                quitar[d["ov"]] += float(d.get("cantidad") or 0)
            antes = r.cantidad
            r.cantidad = round(max(r.cantidad - sum(quitar.values()), 0), 6)
            r.ordenes = [x for x in (r.ordenes or []) if x.get("numero") not in quitar]
            an = dict(r.analisis or {})
            if an.get("destinos"):
                an["destinos"] = [d for d in an["destinos"] if not (d.get("tipo") == "OV" and d.get("ov") in quitar)]
            an["atendidas"] = list(an.get("atendidas") or []) + [{"ov": k, "cantidad": v} for k, v in quitar.items()]
            r.analisis = an
            if r.cantidad <= 1e-9:
                r.estado = "CANCELADA"
                alerts.close_by_system(f"COMPRA_LOG:{r.id}", "La OV ya se atendió")
            r.motivo = ((r.motivo or "") + f" · Actualizada: {motivos}.")[:2000]
            audit(user, "COMPRA_OV_ATENDIDA", "PurchaseRequest", r.id, {"antes": antes, "despues": r.cantidad,
                                                                       "motivo": motivos, "estado": r.estado})
            ajustadas += 1
        else:
            alerts.emit("COMPRA_REVISAR_OV_ATENDIDA", f"Compra #{r.id} {r.product_code}: su OV ya se atendió",
                        f"{motivos}. La solicitud ya está en Compras ({r.estado.replace('_', ' ').lower()}): revise si "
                        "aún hace falta comprar.", "PurchaseRequest", r.id,
                        dedup_key=f"COMPRA_OV_ATENDIDA:{r.id}:{','.join(sorted(d['ov'] for d, _ in resueltas))}")
            avisadas += 1
    db().flush()
    from .purchasing import limpiar_no_comprables  # V60: PT, MQ y MP (salvo harinas y quinua) no se compran
    nc = limpiar_no_comprables(user)
    return {"ajustadas": ajustadas + len(nc["canceladas"]), "avisadas": avisadas + len(nc["avisadas"])}
