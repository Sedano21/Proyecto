"""Reempaque (IF §9): Almacén solicita -> Calidad evalúa -> notifica a Almacén y Producción -> Producción ejecuta."""
from ..db import db
from ..models import Product, RepackRequest, StockLot, now
from . import alerts
from .catalogs_helpers import repack_type_name
from .core import BusinessError, audit, has_perm
from sqlalchemy import select

from .stock import add_or_increase_lot, change_lot_state, free_qty


def _segment(lot, estado):
    if lot.estado == estado:
        return lot
    return db().execute(select(StockLot).where(StockLot.product_code == lot.product_code,
                                               StockLot.warehouse_code == lot.warehouse_code, StockLot.lote == lot.lote,
                                               StockLot.estado == estado)).scalars().first() or lot

TIPOS = ("ACTUALIZACION_FECHA", "CAMBIO_PRESENTACION", "CONVERSION_CALIDAD")


def request(user, tipo, lot_id, cantidad, producto_destino=None, cantidad_destino=None, order=None, motivo=""):
    if not has_perm(user, "reempaque.solicitar"):
        raise BusinessError("La solicitud de reempaque la inicia Almacén (IF §9.1).")
    if tipo not in TIPOS:
        raise BusinessError("Tipo de reempaque no válido.")
    lot = db().get(StockLot, int(lot_id))
    if lot is None:
        raise BusinessError("Lote no encontrado.")
    if lot.estado not in ("DISPONIBLE", "PENDIENTE_REVISION"):
        raise BusinessError(f"El lote está {lot.estado}; no puede seleccionarse para reempaque.")
    libre = free_qty(lot) if lot.estado == "DISPONIBLE" else lot.cantidad
    if cantidad <= 0 or cantidad > libre + 1e-9:
        raise BusinessError(f"Cantidad inválida (libre en el lote: {libre:g}).")
    if tipo in ("CAMBIO_PRESENTACION", "CONVERSION_CALIDAD"):
        if not producto_destino or db().get(Product, producto_destino) is None:
            raise BusinessError("Indique el producto destino (SKU resultante).")
    r = RepackRequest(tipo=tipo, lot_id=lot.id, cantidad=cantidad, producto_destino=producto_destino or lot.product_code,
                      cantidad_destino=cantidad_destino, order_id=order.id if order else None, motivo=motivo,
                      solicitado_por=user.id)
    db().add(r)
    # El producto seleccionado para reempaque queda 'Pendiente de revisión' (IF §6.1). Si se selecciona todo el
    # lote cambia su estado; si es una parte, esa cantidad queda retenida (no reservable) hasta la evaluación.
    db().flush()
    if lot.estado == "DISPONIBLE" and abs(cantidad - lot.cantidad) < 1e-9:
        change_lot_state(lot, "PENDIENTE_REVISION", user, f"Seleccionado para reempaque ({repack_type_name(tipo)})")
        r.lot_id = _segment(lot, "PENDIENTE_REVISION").id
    alerts.emit("REEMPAQUE_SOLICITUD", f"Evaluar reempaque #{r.id}: {repack_type_name(tipo)}",
                f"Lote {lot.lote} ({lot.product_code}) × {cantidad:g}. Destino: {r.producto_destino}. Motivo: {motivo}",
                "RepackRequest", r.id, dedup_key=f"REEMPAQUE_SOL:{r.id}", creado_por=user)
    audit(user, "REEMPAQUE_SOLICITADO", "RepackRequest", r.id, {"tipo": tipo, "lote": lot.lote, "cantidad": cantidad})
    return r


def evaluate(r, user, aprobar, resultado):
    if not has_perm(user, "reempaque.evaluar"):
        raise BusinessError("Calidad evalúa y aprueba el reempaque (IF §9.1).")
    if r.estado != "SOLICITADA":
        raise BusinessError("La solicitud no está pendiente de evaluación.")
    if not resultado.strip():
        raise BusinessError("Registre el resultado de la evaluación/muestreo.")
    r.estado = "APROBADA" if aprobar else "DESAPROBADA"
    r.evaluado_por = user.id
    r.evaluado_ts = now()
    r.resultado_calidad = resultado
    alerts.close_by_system(f"REEMPAQUE_SOL:{r.id}", f"Evaluado: {r.estado}")
    lot = r.lot
    if aprobar:
        alerts.emit("REEMPAQUE_APROBADO", f"Reempaque #{r.id} aprobado: ejecutar",
                    f"{repack_type_name(r.tipo)}. Lote {lot.lote} × {r.cantidad:g} → {r.producto_destino}. {resultado}",
                    "RepackRequest", r.id, creado_por=user)
    else:
        if lot.estado == "PENDIENTE_REVISION" and lot.estado_anterior:
            change_lot_state(lot, lot.estado_anterior, user, f"Reempaque #{r.id} desaprobado")
        alerts.emit("REEMPAQUE_DESAPROBADO", f"Reempaque #{r.id} desaprobado", resultado, "RepackRequest", r.id,
                    creado_por=user)
    audit(user, f"REEMPAQUE_{r.estado}", "RepackRequest", r.id, {"resultado": resultado})


def start(r, user):
    if not has_perm(user, "reempaque.ejecutar"):
        raise BusinessError("Producción ejecuta el reempaque (IF §9.1).")
    if r.estado != "APROBADA":
        raise BusinessError("Solo se ejecutan reempaques aprobados.")
    r.estado = "EN_EJECUCION"
    r.ejecucion_inicio = now()
    r.ejecutado_por = user.id
    audit(user, "REEMPAQUE_INICIO", "RepackRequest", r.id)


def finish(r, user, lote_resultante, cantidad_resultante, nueva_fecha_fab=None, nueva_fecha_venc=None):
    if not has_perm(user, "reempaque.ejecutar"):
        raise BusinessError("Producción registra el reempaque.")
    if r.estado != "EN_EJECUCION":
        raise BusinessError("El reempaque no está en ejecución.")
    if not lote_resultante or cantidad_resultante is None or cantidad_resultante <= 0:
        raise BusinessError("Indique lote y cantidad resultante.")
    lot = r.lot
    if r.cantidad > lot.cantidad + 1e-9:
        raise BusinessError("El lote origen ya no tiene la cantidad del reempaque.")
    lot.cantidad -= r.cantidad
    if lot.cantidad_verificada is not None:
        lot.cantidad_verificada = max(lot.cantidad_verificada - r.cantidad, 0)
    if lot.estado == "PENDIENTE_REVISION" and lot.estado_anterior and lot.cantidad > 1e-9:
        # saldo remanente vuelve a su estado anterior
        change_lot_state(lot, lot.estado_anterior, user, f"Saldo de reempaque #{r.id}")
    nuevo = add_or_increase_lot(r.producto_destino, lot.warehouse_code, lote_resultante, cantidad_resultante,
                                "PENDIENTE_REVISION", nueva_fecha_venc or lot.fecha_venc, nueva_fecha_fab or lot.fecha_fab,
                                origen=f"REEMPAQUE-{r.id}")
    r.estado = "EJECUTADA"
    r.ejecucion_fin = now()
    r.lote_resultante = lote_resultante
    r.cantidad_destino = cantidad_resultante
    r.nueva_fecha_fab = nueva_fecha_fab
    r.nueva_fecha_venc = nueva_fecha_venc
    r.lot_resultante_id = nuevo.id
    alerts.emit("STOCK_PENDIENTE_REVISION", f"Lote reempacado {lote_resultante} pendiente de liberación",
                f"{r.producto_destino} × {cantidad_resultante:g} (reempaque #{r.id}).", "StockLot", nuevo.id, creado_por=user)
    audit(user, "REEMPAQUE_EJECUTADO", "RepackRequest", r.id, {"lote": lote_resultante, "cantidad": cantidad_resultante})
    return nuevo
