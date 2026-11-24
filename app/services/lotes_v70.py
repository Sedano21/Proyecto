"""V70 (24-nov-2026): cambio de estado total o parcial de un lote (la parte, con su cantidad y ubicación, queda como un
segmento aparte del mismo lote) y reglas de Calidad por cliente (el lote solo se despacha a ciertos clientes, o se
bloquea para ciertos clientes)."""
from sqlalchemy import select

from ..db import db
from ..models import Customer, StockLot, now
from .core import BusinessError, audit, has_perm

_NO_COPIAR = {"id", "cantidad", "cantidad_verificada", "estado", "estado_anterior", "motivo_estado", "ubicacion",
              "ubicacion_hist", "ubicaciones", "liberacion_solicitada"}


def cambiar_estado(user, lot, nuevo, motivo, alcance="TOTAL", cantidad=None, ubicacion=""):
    """TOTAL: todo el lote (como siempre). PARCIAL: solo «cantidad»; esa parte pasa a un segmento del mismo lote con
    el nuevo estado y la ubicación indicada (si ya hay un segmento en ese estado, se suma a él)."""
    from .stock import change_lot_state, free_qty
    if (alcance or "TOTAL").upper() != "PARCIAL":
        return change_lot_state(lot, nuevo, user, motivo or "")
    try:
        q = float(str(cantidad).replace(",", "."))
    except (TypeError, ValueError):
        raise BusinessError("Indique la cantidad del cambio parcial.")
    if q <= 0:
        raise BusinessError("La cantidad del cambio parcial debe ser mayor que 0.")
    if q >= (lot.cantidad or 0) - 1e-9:
        return change_lot_state(lot, nuevo, user, motivo or "")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo del cambio de estado.")
    if lot.estado == "DISPONIBLE" and q > free_qty(lot) + 1e-9:
        raise BusinessError(f"Solo hay {free_qty(lot):g} libre en el lote (el resto está reservado para OV). "
                            "Cambie una cantidad menor o libere primero la reserva.")
    from .stock import BLOQUEADOS
    if lot.estado in BLOQUEADOS and nuevo == "DISPONIBLE" and not has_perm(user, "calidad.liberar"):
        raise BusinessError("Un lote bloqueado solo lo libera Calidad: use «Solicitar liberación a Calidad».")
    if nuevo == lot.estado:
        raise BusinessError("La parte ya está en ese estado.")
    ubic = (ubicacion or "").strip().upper()[:80]
    seg = StockLot(**{c.name: getattr(lot, c.name) for c in StockLot.__table__.columns if c.name not in _NO_COPIAR})
    seg.cantidad = q
    seg.cantidad_verificada = q if lot.cantidad_verificada is not None else None
    seg.estado = "_PARCIAL"  # provisional (un lote no repite estado): change_lot_state lo pasa al nuevo o lo fusiona
    seg.ubicacion = ubic or lot.ubicacion
    seg.restriccion_clientes = dict(lot.restriccion_clientes or {})
    db().add(seg)
    lot.cantidad = round((lot.cantidad or 0) - q, 6)
    if lot.cantidad_verificada is not None:
        lot.cantidad_verificada = max(round(lot.cantidad_verificada - q, 6), 0)
    if ubic and lot.ubicaciones:  # el lote estaba en varios lugares: se descuenta de esa ubicación
        lot.ubicaciones = [dict(u, cantidad=max((u.get("cantidad") or 0) - q, 0)) if u.get("ubicacion") == ubic else u
                           for u in lot.ubicaciones]
    db().flush()
    audit(user, "LOTE_ESTADO_PARCIAL", "StockLot", lot.id, {"cantidad": q, "a": nuevo, "ubicacion": ubic,
                                                           "segmento": seg.id, "motivo": motivo})
    change_lot_state(seg, nuevo, user, f"Parcial ({q:g} de {q + lot.cantidad:g}): {motivo.strip()}")
    if seg.cantidad > 0:  # quedó como segmento propio
        seg.estado_anterior = lot.estado
        return seg
    # se sumó a un segmento que ya estaba en ese estado: ese segmento queda con la ubicación indicada
    twin = db().execute(select(StockLot).where(StockLot.product_code == lot.product_code,
                                               StockLot.warehouse_code == lot.warehouse_code, StockLot.lote == lot.lote,
                                               StockLot.estado == nuevo)).scalars().first()
    db().delete(seg)
    if twin is not None and ubic and not twin.ubicacion:
        twin.ubicacion = ubic
    return twin


def _segmentos(lot):
    return list(db().execute(select(StockLot).where(StockLot.product_code == lot.product_code,
                                                    StockLot.lote == lot.lote)).scalars())


def restringir_clientes(user, lot, modo, cliente_ids, motivo=""):
    """Calidad: modo SOLO (solo a estos clientes) o EXCEPTO (bloqueado para estos clientes). Se aplica a todos los
    segmentos del lote. Sin clientes, se quita la regla."""
    if not has_perm(user, "lote.reglas_clientes"):
        raise BusinessError("Las reglas de despacho por cliente las define Calidad.")
    ids = []
    for x in cliente_ids or []:
        if str(x).strip().isdigit() and int(x) not in ids:
            ids.append(int(x))
    regla = {}
    if ids:
        modo = (modo or "").upper()
        if modo not in ("SOLO", "EXCEPTO"):
            raise BusinessError("Elija si el lote es «solo para» o «bloqueado para» esos clientes.")
        if not (motivo or "").strip():
            raise BusinessError("Indique el motivo de la regla.")
        clientes = [db().get(Customer, i) for i in ids]
        if any(c is None for c in clientes):
            raise BusinessError("Cliente no encontrado.")
        regla = {"modo": modo, "clientes": [{"id": c.id, "nombre": c.nombre} for c in clientes],
                 "motivo": motivo.strip()[:300], "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    segs = _segmentos(lot)
    for s in segs:
        s.restriccion_clientes = regla
    audit(user, "LOTE_REGLA_CLIENTES", "StockLot", lot.id, regla or {"quitada": True})
    db().flush()
    # las reservas activas que la regla ya no permite se liberan y la OV se reevalúa
    if regla:
        from .stock import ORDEN_ESTADOS_CERRADOS, _release, evaluate_order, lot_usable
        for s in segs:
            for r in list(s.reservations):
                if r.estado != "ACTIVA":
                    continue
                o = r.line.order
                ok, why = lot_usable(s, o.fecha_compromiso, o.customer)
                if not ok and why.startswith("Calidad"):
                    _release(r, why)
                    if o.estado not in ORDEN_ESTADOS_CERRADOS:
                        evaluate_order(o, user, "REEVALUACION")
    return regla
