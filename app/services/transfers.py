"""Traslados entre almacenes (IF §6.2, §13): Logística decide y la Jefatura autoriza; Almacén confirma recepción."""
from datetime import timedelta

from sqlalchemy import select

from ..db import db
from ..models import OVDecision, StockLot, Transfer, Warehouse, now
from . import alerts
from .core import can_self_approve, BusinessError, audit, check_warehouse_scope, has_perm
from .stock import add_or_increase_lot, free_qty, lot_usable, reevaluate_pending


def pending_transfer_qty(lot):
    """Cantidad comprometida en el origen por traslados AUTORIZADOS aún no despachados. Una solicitud o pre-solicitud
    sin autorizar no compromete stock (decisión del 14-oct): la disponibilidad se valida al autorizar."""
    q = select(Transfer).where(Transfer.origen_lot_id == lot.id, Transfer.estado == "AUTORIZADO")
    return sum(t.cantidad for t in db().execute(q).scalars())


def transferable_qty(lot):
    ok, _ = lot_usable(lot)
    if not ok:
        return 0.0
    return max(free_qty(lot) - pending_transfer_qty(lot), 0.0)


def request_transfer(user, lot_id, destino_code, cantidad, order=None, observacion="", sistema=False):
    """sistema=True: pre-solicitud automática (Q15); la aprueba el Jefe o el Coordinador de Logística (Q13)."""
    if not sistema and not (has_perm(user, "traslado.solicitar") or has_perm(user, "ov.decidir_alternativa")):
        raise BusinessError("Su rol no puede solicitar traslados (Logística decide, IF §6.2).")
    lot = db().get(StockLot, int(lot_id))
    if lot is None:
        raise BusinessError("Lote no encontrado.")
    if db().get(Warehouse, destino_code) is None:
        raise BusinessError("Almacén destino no válido.")
    if destino_code == lot.warehouse_code:
        raise BusinessError("Origen y destino son el mismo almacén.")
    disp = transferable_qty(lot)
    if cantidad <= 0 or cantidad > disp + 1e-9:
        raise BusinessError(f"Cantidad no disponible para traslado (máximo {disp:g}).")
    t = Transfer(origen_lot_id=lot.id, destino_code=destino_code, cantidad=cantidad, order_id=order.id if order else None,
                 solicitado_por=user.id if user else None, observacion=observacion)
    db().add(t)
    db().flush()
    if order is not None:
        db().add(OVDecision(order_id=order.id, tipo="USO_ALMACEN_ALTERNATIVO", estado="REGISTRADA",
                            detalle={"traslado": t.id, "lote": lot.lote, "origen": lot.warehouse_code,
                                     "destino": destino_code, "cantidad": cantidad, "automatica": sistema},
                            comentario=observacion, user_id=user.id if user else None))
    alerts.emit("TRASLADO_SOLICITADO", f"Autorizar traslado #{t.id}: {lot.product_code} × {cantidad:g}",
                f"{lot.warehouse_code} → {destino_code}, lote {lot.lote}. OV: {order.numero if order else '-'}.",
                "Transfer", t.id, dedup_key=f"TRASLADO_SOL:{t.id}", creado_por=user)
    audit(user, "TRASLADO_SOLICITADO", "Transfer", t.id, {"lote": lot.id, "destino": destino_code, "cantidad": cantidad})
    return t


def authorize(t, user, aprobar, observacion="", llegada=None):
    if not has_perm(user, "traslado.autorizar"):
        raise BusinessError("El traslado lo aprueba el Jefe o el Coordinador de Logística (IF §6.2, §13; Q13).")
    if t.estado != "SOLICITADO":
        raise BusinessError("El traslado no está pendiente de autorización.")
    if t.solicitado_por is not None and t.solicitado_por == user.id and not can_self_approve(user):
        raise BusinessError("No puede aprobar su propia solicitud de traslado: la aprueba el Jefe de Logística (decisión 13-oct).")
    if aprobar:
        disp = transferable_qty(t.lot)  # la solicitud aún no compromete stock: se valida contra lo libre hoy
        if t.cantidad > disp + 1e-9:
            raise BusinessError(f"El lote ya no tiene la cantidad disponible ({disp:g}).")
    t.estado = "AUTORIZADO" if aprobar else "RECHAZADO"
    t.autorizado_por = user.id
    t.autorizado_ts = now()
    if observacion:
        t.observacion = (t.observacion + "\n" if t.observacion else "") + f"Autorización: {observacion}"
    alerts.close_by_system(f"TRASLADO_SOL:{t.id}", f"Traslado {t.estado.lower()}")
    if aprobar:
        alerts.emit("TRASLADO_AUTORIZADO", f"Traslado #{t.id} autorizado", f"{t.lot.product_code} × {t.cantidad:g} "
                    f"{t.lot.warehouse_code} → {t.destino_code}.", "Transfer", t.id, creado_por=user)
    audit(user, f"TRASLADO_{t.estado}", "Transfer", t.id, {"observacion": observacion})
    if aprobar and llegada is not None:
        set_arrival(t, user, llegada)


def set_arrival(t, user, llegada):
    """Fecha y hora de llegada de la mercadería (observaciones al demo v0.5): alerta a Calidad para revisar y a Almacén
    para almacenar correctamente."""
    if not (has_perm(user, "traslado.autorizar") or has_perm(user, "traslado.salida")):
        raise BusinessError("La llegada la registra Logística o el almacén de origen.")
    if t.estado not in ("AUTORIZADO", "EN_TRANSITO"):
        raise BusinessError("Solo se programa la llegada de un traslado autorizado o en tránsito.")
    if llegada is None:
        raise BusinessError("Indique fecha y hora de llegada.")
    if llegada < now().replace(second=0, microsecond=0) - timedelta(minutes=1):
        raise BusinessError("La llegada no puede estar en el pasado.")
    antes = t.llegada_estimada
    t.llegada_estimada = llegada
    alerts.emit("TRASLADO_LLEGADA", f"Traslado #{t.id}: llega el {llegada:%d/%m/%Y %H:%M}",
                f"{t.lot.product_code} {t.lot.product.descripcion if t.lot.product else ''} lote {t.lot.lote} × {t.cantidad:g} "
                f"desde {t.lot.warehouse_code} hacia {t.destino_code}. Calidad: programar la revisión de la mercadería; "
                f"Almacén: preparar la ubicación." + (f" (antes: {antes:%d/%m %H:%M})" if antes else ""),
                "Transfer", t.id, dedup_key=f"TRASLADO_LLEGADA:{t.id}:{llegada:%Y%m%d%H%M}", creado_por=user)
    audit(user, "TRASLADO_LLEGADA_PROGRAMADA", "Transfer", t.id, {"llegada": llegada.isoformat(), "antes": antes.isoformat() if antes else None})


def remind_arrivals(hoy=None):
    """Tarea programada: el día de la llegada se recuerda a Calidad y Almacén si aún no se recibió."""
    hoy = hoy or now().date()
    n = 0
    for t in db().execute(select(Transfer).where(Transfer.estado.in_(("AUTORIZADO", "EN_TRANSITO")),
                                                 Transfer.llegada_estimada.is_not(None))).scalars():
        if t.llegada_estimada.date() == hoy:
            alerts.emit("TRASLADO_LLEGADA", f"Hoy llega el traslado #{t.id} ({t.llegada_estimada:%H:%M})",
                        f"{t.lot.product_code} lote {t.lot.lote} × {t.cantidad:g} hacia {t.destino_code}.", "Transfer", t.id,
                        dedup_key=f"TRASLADO_LLEGADA_HOY:{t.id}:{hoy}")
            n += 1
    return n


def ship(t, user):
    if not has_perm(user, "traslado.salida"):
        raise BusinessError("Su rol no registra salidas de traslado.")
    if t.estado != "AUTORIZADO":
        raise BusinessError("Solo se despachan traslados autorizados.")
    check_warehouse_scope(user, t.lot.warehouse_code)
    if t.cantidad > free_qty(t.lot) + 1e-9:
        raise BusinessError("El lote de origen ya no tiene la cantidad libre.")
    t.lot.cantidad -= t.cantidad
    if t.lot.cantidad_verificada is not None:
        t.lot.cantidad_verificada -= t.cantidad
    t.estado = "EN_TRANSITO"
    t.salida_ts = now()
    t.salida_por = user.id
    audit(user, "TRASLADO_SALIDA", "Transfer", t.id)


def receive(t, user, cantidad_recibida, observacion=""):
    if not has_perm(user, "traslado.recibir"):
        raise BusinessError("La recepción la confirma el Coordinador de Almacén o su asistente (IF §6.2).")
    if t.estado != "EN_TRANSITO":
        raise BusinessError("El traslado no está en tránsito.")
    check_warehouse_scope(user, t.destino_code)
    if cantidad_recibida < 0:
        raise BusinessError("Cantidad inválida.")
    t.cantidad_recibida = cantidad_recibida
    t.diferencia = t.cantidad - cantidad_recibida
    t.recibido_por = user.id
    t.recibido_ts = now()
    t.estado = "RECIBIDO" if abs(t.diferencia) < 1e-9 else "RECIBIDO_CON_DIFERENCIA"
    if observacion:
        t.observacion = (t.observacion + "\n" if t.observacion else "") + f"Recepción: {observacion}"
    if cantidad_recibida > 0:
        add_or_increase_lot(t.lot.product_code, t.destino_code, t.lot.lote, cantidad_recibida, t.lot.estado,
                            t.lot.fecha_venc, t.lot.fecha_fab, origen=f"TRASLADO-{t.id}")
    if t.estado == "RECIBIDO_CON_DIFERENCIA":
        alerts.emit("TRASLADO_DIFERENCIA", f"Diferencia en traslado #{t.id}",
                    f"Enviado {t.cantidad:g}, recibido {cantidad_recibida:g}. {observacion}", "Transfer", t.id, creado_por=user)
    audit(user, f"TRASLADO_{t.estado}", "Transfer", t.id, {"recibido": cantidad_recibida, "diferencia": t.diferencia})
    if t.order is not None and t.order.estado not in ("CANCELADA",):
        from .stock import evaluate_order, ORDEN_ESTADOS_CERRADOS
        if t.order.estado not in ORDEN_ESTADOS_CERRADOS:
            evaluate_order(t.order, user, "REEVALUACION")
    reevaluate_pending(user, [t.lot.product_code])
