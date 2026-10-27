"""Conteos físicos periódicos y registro de diferencias (IF §6.3, §6.4).
Cálculo como en 'Inven. bobinas 1524.xlsx': Físico = Peso × Conteo (si se usa peso unitario);
Faltante = MAX(SAP − Físico, 0); Sobrante = MAX(Físico − SAP, 0)."""
from sqlalchemy import select

from ..db import db
from ..models import PhysicalCount, PhysicalCountLine, StockLot, now
from . import alerts
from .core import BusinessError, audit, check_warehouse_scope, has_perm


def open_count(user, warehouse_code, product_prefix="", observacion="", base=None, codigos=None):
    """base: conteo anterior cuya lista de productos se repite; codigos: lista de productos preexistente (ronda UX)."""
    if not has_perm(user, "stock.conteo"):
        raise BusinessError("Su rol no registra conteos.")
    if base is not None:
        warehouse_code = warehouse_code or base.warehouse_code
        codigos = sorted({l.product_code for l in base.lines})
        observacion = observacion or f"Sobre la lista del conteo #{base.id}"
    check_warehouse_scope(user, warehouse_code)
    c = PhysicalCount(warehouse_code=warehouse_code, user_id=user.id, observacion=observacion)
    q = select(StockLot).where(StockLot.warehouse_code == warehouse_code, StockLot.cantidad > 0)
    if product_prefix:
        q = q.where(StockLot.product_code.like(f"{product_prefix}%"))
    if codigos:
        q = q.where(StockLot.product_code.in_([x.strip().upper() for x in codigos if x.strip()]))
    for lot in db().execute(q.order_by(StockLot.product_code, StockLot.lote)).scalars():
        c.lines.append(PhysicalCountLine(lot_id=lot.id, product_code=lot.product_code, lote=lot.lote, sap=lot.cantidad))
    if not c.lines:
        raise BusinessError("No hay stock registrado para contar con ese filtro.")
    db().add(c)
    db().flush()
    audit(user, "CONTEO_ABIERTO", "PhysicalCount", c.id, {"almacen": warehouse_code, "lineas": len(c.lines)})
    return c


def compute_line(line):
    conteo = line.recuento if line.recuento is not None else line.conteo  # el recuento reemplaza al primer conteo
    if conteo is None:
        line.fisico = None
        line.faltante = line.sobrante = 0
        return
    line.fisico = conteo * line.peso_unitario if line.peso_unitario else conteo
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
        if "recuento" in v:
            line.recuento = float(v["recuento"]) if v.get("recuento") not in (None, "") else None
        compute_line(line)


def needs_recount(line):
    """A06: la diferencia supera la tolerancia (1 % o 5 kg, configurables) y aún no se recontó."""
    if line.recuento is not None or line.fisico is None:
        return False
    from .core import param
    from ..models import Product
    dif = abs(line.fisico - line.sap)
    if dif <= 1e-9:
        return False
    pct = float(param("conteo_tolerancia_pct", 1) or 0)
    kg_tol = float(param("conteo_tolerancia_kg", 5) or 0)
    p = db().get(Product, line.product_code)
    kg_u = (p.peso_kg or (1.0 if (p.um or "").upper().startswith("K") else 0)) if p else 0
    supera_pct = line.sap > 0 and dif / line.sap * 100 > pct
    supera_kg = kg_u > 0 and dif * kg_u > kg_tol
    return supera_pct or supera_kg or line.sap <= 0


def close_count(c, user):
    if c.estado != "ABIERTO":
        raise BusinessError("El conteo ya está cerrado.")
    sin = [l for l in c.lines if l.conteo is None]
    if sin:
        raise BusinessError(f"Hay {len(sin)} líneas sin conteo.")
    recontar = [l for l in c.lines if needs_recount(l)]
    if recontar:
        raise BusinessError("Recuente antes de cerrar (diferencia mayor a la tolerancia): "
                            + ", ".join(f"{l.product_code} lote {l.lote}" for l in recontar[:10]) + ".")
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


def check_cycle_counts(hoy=None):
    """A06: conteo cíclico quincenal. Avisa por almacén habilitado cuando pasaron N días desde el último conteo cerrado."""
    from datetime import date
    from sqlalchemy import func
    from .core import param
    from ..models import Warehouse
    hoy = hoy or date.today()
    dias = int(param("conteo_ciclico_dias", 15) or 0)
    if not dias:
        return 0
    n = 0
    for w in db().execute(select(Warehouse).where(Warehouse.habilitado.is_(True))).scalars():
        ult = db().execute(select(func.max(PhysicalCount.fecha)).where(PhysicalCount.warehouse_code == w.code,
                                                                       PhysicalCount.estado == "CERRADO")).scalar()
        if ult is None or (hoy - ult).days >= dias:
            alerts.emit("CONTEO_CICLICO", f"Toca el conteo cíclico de {w.code}",
                        f"Último conteo cerrado: {ult:%d/%m/%Y}." if ult else "Aún no hay conteos cerrados en este almacén.",
                        "Warehouse", w.code,
                        dedup_key=f"CONTEO_CICLICO:{w.code}:{hoy.toordinal() // dias}")  # una vez por periodo
            n += 1
    return n
