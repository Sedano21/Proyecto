"""Verificaciones periódicas que generan alertas automáticas (IF §14).
Se ejecutan con el botón 'Ejecutar verificaciones', con `python -m app.cli verificar` (para programar con cron /
Programador de tareas) o con un hilo en segundo plano cada CHECK_INTERVAL_MIN minutos (1 por defecto; 0 lo desactiva)."""
import os
import threading
import time
from datetime import date, timedelta

from sqlalchemy import select

from ..db import SessionLocal, db
from ..models import Product, SalesOrder, StockLot
from . import alerts
from .core import param
from .imports import check_phases
from .mailer import flush_outbox
from .purchasing import run_replenishment
from .stock import ORDEN_ESTADOS_CERRADOS, expiring_lots


def run_checks(user=None, today=None):
    today = today or date.today()
    out = {}
    out["fases_importacion"] = check_phases(today)
    # OV con fecha comprometida vencida y sin salida
    n = 0
    for o in db().execute(select(SalesOrder).where(SalesOrder.fecha_compromiso < today,
                                                   SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS + ("EN_RUTA",)))).scalars():
        alerts.emit("OV_RETRASO", f"OV {o.numero} sin despachar (comprometida {o.fecha_compromiso:%d/%m/%Y})",
                    f"Estado {o.estado}; cobertura {o.cobertura_unidades}%. {o.motivo_detencion}", "SalesOrder", o.id,
                    extra_users=[o.vendedor_id] if o.vendedor_id else None, dedup_key=f"OV_RETRASO:{o.id}")
        n += 1
    out["ov_retrasadas"] = n
    # Vencimiento próximo (solo si el umbral está configurado)
    dias = param("dias_vencimiento_proximo")
    n = 0
    if dias is not None:
        for lot in expiring_lots(int(dias)):
            alerts.emit("VENCIMIENTO_PROXIMO", f"Lote {lot.lote} de {lot.product_code} vence el {lot.fecha_venc:%d/%m/%Y}",
                        f"Almacén {lot.warehouse_code}; cantidad {lot.cantidad:g}.", "StockLot", lot.id,
                        dedup_key=f"VENC:{lot.id}")
            n += 1
    out["lotes_por_vencer"] = n if dias is not None else "umbral no configurado"
    # Tiempo máximo de almacenamiento (riesgo de infestación) – configurable por producto
    n = 0
    for p in db().execute(select(Product).where(Product.tiempo_max_almacen_dias.is_not(None))).scalars():
        lim = today - timedelta(days=p.tiempo_max_almacen_dias)
        for lot in db().execute(select(StockLot).where(StockLot.product_code == p.code, StockLot.cantidad > 0,
                                                       StockLot.estado == "DISPONIBLE",
                                                       StockLot.fecha_admision.is_not(None),
                                                       StockLot.fecha_admision < lim)).scalars():
            alerts.emit("STOCK_NO_UTILIZABLE", f"Lote {lot.lote} supera el tiempo máximo de almacenamiento",
                        f"{p.code}: ingreso {lot.fecha_admision:%d/%m/%Y}, máximo {p.tiempo_max_almacen_dias} días. "
                        "Evaluar fumigación/estado No utilizable.", "StockLot", lot.id, dedup_key=f"TMAX:{lot.id}")
            n += 1
    out["lotes_tiempo_maximo"] = n
    out["reposicion_solicitudes"] = len(run_replenishment(user, ref=today))
    from .prices import check_validity
    out["listas_precio_por_vencer"] = check_validity(today)
    out["cargas_desactualizadas"] = check_upload_freshness()
    from .stock import activate_deferred, check_expired_reservations
    out["ov_reserva_activada"] = activate_deferred(user, today)
    out["reservas_vencidas"] = check_expired_reservations(user, today)
    from .maps import check_active_routes
    out["rutas_trafico"] = check_active_routes(today)
    from .quality import fumigation_alerts
    out["avisos_fumigacion"] = fumigation_alerts(today)
    from .transfers import remind_arrivals
    out["traslados_llegan_hoy"] = remind_arrivals(today)
    from .costs import check_market_alerts
    out["costo_vs_mercado"] = check_market_alerts(user)
    from .customer_behavior import check_purchase_variations
    out["variacion_compra_clientes"] = check_purchase_variations(user, today)
    from .fleet import check_alerts as fleet_alerts
    out["flota"] = fleet_alerts(today)
    from .supply import check_no_rotation, check_order_risk
    out["ov_riesgo_48_24h"] = check_order_risk()
    out["stock_sin_rotacion_mensual"] = check_no_rotation(today)
    from .maintenance import check_alerts as mant_alerts
    out["mantenimiento_saneamiento"] = mant_alerts(today)
    from .shifts import check_overdue
    out["tareas_incumplidas_aviso_jefe"] = check_overdue()
    from .shifts import check_end_of_shift
    out["tareas_pendientes_fin_turno"] = check_end_of_shift()
    from .commitment import check_pending
    out["ov_sin_compromiso"] = check_pending()
    from .finance import check_overdue as facturas_vencidas
    out["facturas_vencidas"] = facturas_vencidas(today)
    out["correo"] = flush_outbox()
    return out


def check_upload_freshness(ahora=None):
    """Cada área exporta de SAP a diario, con 2 cortes al día como mínimo: alerta si la última carga autorizada de un
    tipo supera las horas configuradas (al área responsable y a Sistemas)."""
    from datetime import datetime
    from ..models import UploadBatch
    ahora = ahora or datetime.now()
    resp = param("responsable_carga", {}) or {}
    n = 0
    for tipo, horas in (param("horas_max_sin_carga", {}) or {}).items():
        if not horas:
            continue
        ult = db().execute(select(UploadBatch).where(UploadBatch.tipo == tipo, UploadBatch.estado == "CONFIRMADO")
                           .order_by(UploadBatch.confirmado_ts.desc())).scalars().first()
        if ult is not None and ult.confirmado_ts and (ahora - ult.confirmado_ts).total_seconds() <= float(horas) * 3600:
            alerts.close_by_system(f"CARGA_VIEJA:{tipo}", "Carga actualizada")
            continue
        desde = f"última carga {ult.confirmado_ts:%d/%m/%Y %H:%M}" if ult is not None and ult.confirmado_ts else "sin cargas autorizadas"
        alerts.emit("CARGA_SAP_DESACTUALIZADA", f"Carga de {tipo} sin actualizar ({desde})",
                    f"Se esperan al menos 2 cortes al día (máximo {horas} h entre cargas).", "UploadBatch", "",
                    extra_roles=resp.get(tipo) or [], dedup_key=f"CARGA_VIEJA:{tipo}")
        n += 1
    return n


def _lock(path):
    """Candado de archivo para que, con varios procesos del servidor, solo uno ejecute cada ronda de verificaciones."""
    if not path:
        return None
    try:
        fh = open(path, "a+")
    except OSError:
        return None
    try:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:  # Windows
        try:
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            fh.close()
            return False
    except OSError:
        fh.close()
        return False
    return fh


def start_background(app_factory_session_commit, interval_min, lock_path=None):
    def loop():
        while True:
            time.sleep(interval_min * 60)
            fh = _lock(lock_path)
            if fh is False:  # otro proceso tiene el candado y ejecuta las verificaciones
                continue
            if fh:  # otro proceso ya ejecutó esta ronda
                fh.seek(0)
                try:
                    ultima = float(fh.read().strip() or 0)
                except ValueError:
                    ultima = 0
                if time.time() - ultima < interval_min * 60 - 5:
                    fh.close()
                    continue
                fh.seek(0)
                fh.truncate()
                fh.write(str(time.time()))
                fh.flush()
            try:
                run_checks()
                SessionLocal().commit()
            except Exception:  # noqa: BLE001
                SessionLocal().rollback()
            finally:
                SessionLocal.remove()
                if fh:
                    fh.close()
    t = threading.Thread(target=loop, daemon=True, name="verificaciones")
    t.start()
    return t
