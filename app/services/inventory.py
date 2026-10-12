"""Conteos físicos periódicos y registro de diferencias (IF §6.3, §6.4).
Cálculo como en 'Inven. bobinas 1524.xlsx': Físico = Peso × Conteo (si se usa peso unitario);
Faltante = MAX(SAP − Físico, 0); Sobrante = MAX(Físico − SAP, 0)."""
from sqlalchemy import select

from ..db import db
from ..models import PhysicalCount, PhysicalCountLine, StockLot, now
from . import alerts
from .core import BusinessError, audit, check_warehouse_scope, has_perm


def open_count(user, warehouse_code, product_prefix="", observacion=""):
    if not has_perm(user, "stock.conteo"):
        raise BusinessError("Su rol no registra conteos.")
    check_warehouse_scope(user, warehouse_code)
    c = PhysicalCount(warehouse_code=warehouse_code, user_id=user.id, observacion=observacion)
    q = select(StockLot).where(StockLot.warehouse_code == warehouse_code, StockLot.cantidad > 0)
    if product_prefix:
        q = q.where(StockLot.product_code.like(f"{product_prefix}%"))
    for lot in db().execute(q.order_by(StockLot.product_code, StockLot.lote)).scalars():
        c.lines.append(PhysicalCountLine(lot_id=lot.id, product_code=lot.product_code, lote=lot.lote, sap=lot.cantidad))
    if not c.lines:
        raise BusinessError("No hay stock registrado para contar con ese filtro.")
    db().add(c)
    db().flush()
    audit(user, "CONTEO_ABIERTO", "PhysicalCount", c.id, {"almacen": warehouse_code, "lineas": len(c.lines)})
    return c


def compute_line(line):
    if line.conteo is None:
        line.fisico = None
        line.faltante = line.sobrante = 0
        return
    line.fisico = line.conteo * line.peso_unitario if line.peso_unitario else line.conteo
    line.faltante = max(line.sap - line.fisico, 0)
    line.sobrante = max(line.fisico - line.sap, 0)


def save_lines(c, user, valores):
    """valores: {line_id: {conteo, peso_unitario, comentario}}"""
    if c.estado != "ABIERTO":
        raise BusinessError("El conteo está cerrado.")
    for line in c.lines:
        v = valores.get(str(line.id))
        if not v:
            continue
        line.conteo = float(v["conteo"]) if v.get("conteo") not in (None, "") else None
        line.peso_unitario = float(v["peso_unitario"]) if v.get("peso_unitario") not in (None, "") else None
        line.comentario = v.get("comentario", line.comentario) or ""
        compute_line(line)


def close_count(c, user):
    if c.estado != "ABIERTO":
        raise BusinessError("El conteo ya está cerrado.")
    sin = [l for l in c.lines if l.conteo is None]
    if sin:
        raise BusinessError(f"Hay {len(sin)} líneas sin conteo.")
    difs = []
    for line in c.lines:
        lot = db().get(StockLot, line.lot_id) if line.lot_id else None
        if lot is None:
            continue
        lot.verificado = True
        lot.fecha_verificacion = now()
        # La cantidad física verificada limita lo reservable si es menor a SAP (no se modifica el dato SAP).
        lot.cantidad_verificada = line.fisico
        if line.faltante or line.sobrante:
            difs.append(line)
    c.estado = "CERRADO"
    if difs:
        alerts.emit("INVENTARIO_DIFERENCIA", f"Conteo #{c.id} ({c.warehouse_code}): {len(difs)} diferencia(s)",
                    "; ".join(f"{l.product_code} lote {l.lote}: SAP {l.sap:g} / físico {l.fisico:g}" for l in difs[:20]),
                    "PhysicalCount", c.id, creado_por=user)
        # reservas por encima de lo físico: reevaluar OV afectadas
        from .stock import evaluate_order, free_qty, reserved_qty, ORDEN_ESTADOS_CERRADOS, _release
        for l in difs:
            lot = db().get(StockLot, l.lot_id)
            exceso = reserved_qty(lot) - min(lot.cantidad, lot.cantidad_verificada or 0)
            afectadas = set()
            for res in sorted([r for r in lot.reservations if r.estado == "ACTIVA"], key=lambda r: r.id, reverse=True):
                if exceso <= 1e-9:
                    break
                afectadas.add(res.line.order)
                if res.cantidad <= exceso + 1e-9:
                    exceso -= res.cantidad
                    _release(res, f"Conteo #{c.id}: físico menor a lo reservado")
                else:
                    res.cantidad -= exceso
                    exceso = 0
            for o in afectadas:
                alerts.emit("RESERVA_AFECTADA", f"Reserva ajustada en OV {o.numero} por conteo #{c.id}",
                            f"Lote {lot.lote}: físico {l.fisico:g}.", "SalesOrder", o.id, creado_por=user)
                if o.estado not in ORDEN_ESTADOS_CERRADOS:
                    evaluate_order(o, user, "REEVALUACION")
    audit(user, "CONTEO_CERRADO", "PhysicalCount", c.id, {"diferencias": len(difs)})
    return difs
