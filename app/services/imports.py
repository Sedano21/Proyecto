"""Importaciones (IF §11): seguimiento por fases configurables, fechas, recordatorios y alertas."""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import DateChange, ImportPhase, ImportPhaseTemplate, ImportShipment, Product
from . import alerts
from .core import BusinessError, audit, has_perm
from .stock import add_or_increase_lot


def _req(user):
    if not has_perm(user, "importaciones.gestionar"):
        raise BusinessError("Gestiona el área de Importaciones (IF §11).")


def create_shipment(user, referencia, proveedor, product_code, cantidad, fecha_inicio, fecha_llegada=None, warehouse_code=None):
    _req(user)
    if not referencia.strip() or db().get(Product, product_code) is None or not cantidad or cantidad <= 0:
        raise BusinessError("Referencia, producto y cantidad son obligatorios.")
    if db().execute(select(ImportShipment).where(ImportShipment.referencia == referencia.strip())).scalars().first():
        raise BusinessError("La referencia ya existe.")
    sh = ImportShipment(referencia=referencia.strip(), proveedor=proveedor, product_code=product_code, cantidad=cantidad,
                        warehouse_code=warehouse_code, creado_por=user.id)
    templates = list(db().execute(select(ImportPhaseTemplate).order_by(ImportPhaseTemplate.orden)).scalars())
    for t in templates:
        sh.phases.append(ImportPhase(orden=t.orden, nombre=t.nombre, fecha_prevista=fecha_inicio + timedelta(days=t.dias_desde_inicio),
                                     recordatorio_dias=t.recordatorio_dias, responsable_rol=t.responsable_rol))
    sh.fecha_llegada_estimada = fecha_llegada or (sh.phases[-1].fecha_prevista if sh.phases else None)
    db().add(sh)
    db().flush()
    alerts.emit("IMPORT_LLEGADA", f"Importación {sh.referencia}: llegada estimada {sh.fecha_llegada_estimada or '-'}",
                f"{product_code} × {cantidad:g} de {proveedor}.", "ImportShipment", sh.id, creado_por=user)
    audit(user, "IMPORTACION_CREADA", "ImportShipment", sh.id, {"referencia": referencia, "fases": len(sh.phases)})
    return sh


def change_arrival(sh, user, nueva, motivo):
    _req(user)
    if not motivo.strip():
        raise BusinessError("Indique el motivo del cambio.")
    anterior = sh.fecha_llegada_estimada
    sh.fecha_llegada_estimada = nueva
    db().add(DateChange(entidad="IMPORTACION", entidad_id=sh.id, anterior=anterior, nueva=nueva, motivo=motivo, user_id=user.id))
    alerts.emit("IMPORT_MODIFICACION", f"Importación {sh.referencia}: llegada {anterior or '-'} → {nueva}",
                f"Motivo: {motivo}", "ImportShipment", sh.id, creado_por=user)
    audit(user, "IMPORTACION_LLEGADA_CAMBIO", "ImportShipment", sh.id, {"anterior": anterior, "nueva": nueva})


def change_phase_date(phase, user, nueva, motivo):
    _req(user)
    if not motivo.strip():
        raise BusinessError("Indique el motivo del cambio.")
    anterior = phase.fecha_prevista
    phase.fecha_prevista = nueva
    db().add(DateChange(entidad="FASE", entidad_id=phase.id, anterior=anterior, nueva=nueva, motivo=motivo, user_id=user.id))
    alerts.emit("IMPORT_MODIFICACION", f"Importación {phase.shipment.referencia}: fase '{phase.nombre}' {anterior} → {nueva}",
                f"Motivo: {motivo}", "ImportShipment", phase.shipment_id, creado_por=user)
    alerts.close_by_system(f"IMPORT_FASE:{phase.id}", "Fecha reprogramada")


def complete_phase(phase, user, fecha_real=None):
    _req(user)
    phase.fecha_real = fecha_real or date.today()
    alerts.close_by_system(f"IMPORT_FASE:{phase.id}", "Fase completada")
    alerts.close_by_system(f"IMPORT_REC:{phase.id}", "Fase completada")
    audit(user, "IMPORTACION_FASE_COMPLETADA", "ImportShipment", phase.shipment_id, {"fase": phase.nombre})


def check_phases(today=None):
    """Alerta fases fuera de fecha y recordatorios (ejecución periódica)."""
    today = today or date.today()
    n = 0
    q = select(ImportPhase).join(ImportShipment).where(ImportShipment.estado == "EN_CURSO", ImportPhase.fecha_real.is_(None))
    for ph in db().execute(q).scalars():
        if ph.fecha_prevista and ph.fecha_prevista < today:
            alerts.emit("IMPORT_FASE_VENCIDA", f"Fase '{ph.nombre}' de {ph.shipment.referencia} fuera de fecha",
                        f"Prevista {ph.fecha_prevista:%d/%m/%Y}. Responsable: {ph.responsable_rol}.", "ImportShipment",
                        ph.shipment_id, extra_roles=[ph.responsable_rol], dedup_key=f"IMPORT_FASE:{ph.id}")
            n += 1
        elif ph.fecha_prevista and ph.recordatorio_dias and 0 <= (ph.fecha_prevista - today).days <= ph.recordatorio_dias:
            alerts.emit("IMPORT_RECORDATORIO", f"Recordatorio: fase '{ph.nombre}' de {ph.shipment.referencia}",
                        f"Fecha prevista {ph.fecha_prevista:%d/%m/%Y}.", "ImportShipment", ph.shipment_id,
                        extra_roles=[ph.responsable_rol], dedup_key=f"IMPORT_REC:{ph.id}")
            n += 1
    return n


def receive(sh, user, cantidad, lote, warehouse_code, fecha_venc=None, diferencias=""):
    if not has_perm(user, "importaciones.recibir") and not has_perm(user, "compras.recibir"):
        raise BusinessError("Almacén registra la recepción (con Calidad).")
    if sh.estado != "EN_CURSO":
        raise BusinessError("La importación ya fue recibida.")
    if cantidad is None or cantidad < 0 or not lote or not warehouse_code:
        raise BusinessError("Cantidad, lote y almacén son obligatorios.")
    from .core import check_warehouse_scope
    check_warehouse_scope(user, warehouse_code)
    sh.cantidad_recibida = cantidad
    sh.lote_recibido = lote
    sh.warehouse_code = warehouse_code
    hay_dif = abs(cantidad - sh.cantidad) > 1e-9 or bool(diferencias.strip())
    sh.diferencias = diferencias or (f"Recibido {cantidad:g} vs esperado {sh.cantidad:g}" if hay_dif else "")
    sh.estado = "RECIBIDA_CON_DIFERENCIAS" if hay_dif else "RECIBIDA"
    for ph in sh.phases:
        if ph.fecha_real is None:
            ph.fecha_real = date.today()
            alerts.close_by_system(f"IMPORT_FASE:{ph.id}", "Importación recibida")
    if cantidad > 0:
        lot = add_or_increase_lot(sh.product_code, warehouse_code, lote, cantidad, "PENDIENTE_REVISION", fecha_venc,
                                  origen=f"IMPORT-{sh.referencia}")
        alerts.emit("STOCK_PENDIENTE_REVISION", f"Importación {sh.referencia} recibida: lote {lote} pendiente de revisión",
                    f"{sh.product_code} × {cantidad:g}. Registrar informe REG-CAL-005.", "StockLot", lot.id, creado_por=user)
    if hay_dif:
        alerts.emit("IMPORT_DIFERENCIA", f"Diferencias en recepción de importación {sh.referencia}", sh.diferencias,
                    "ImportShipment", sh.id, creado_por=user)
    audit(user, f"IMPORTACION_{sh.estado}", "ImportShipment", sh.id, {"cantidad": cantidad, "lote": lote})
