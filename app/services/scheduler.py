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


def _ov_retrasadas(today):
    n = 0
    for o in db().execute(select(SalesOrder).where(SalesOrder.fecha_compromiso < today,
                                                   SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS + ("EN_RUTA",)))).scalars():
        alerts.emit("OV_RETRASO", f"OV {o.numero} sin despachar (comprometida {o.fecha_compromiso:%d/%m/%Y})",
                    f"Estado {o.estado}; cobertura {o.cobertura_unidades}%. {o.motivo_detencion}", "SalesOrder", o.id,
                    extra_users=[o.vendedor_id] if o.vendedor_id else None, dedup_key=f"OV_RETRASO:{o.id}")
        n += 1
    return n


def _por_vencer(today):
    dias = param("dias_vencimiento_proximo")
    if dias is None:
        return "umbral no configurado"
    n = 0
    for lot in expiring_lots(int(dias)):
        alerts.emit("VENCIMIENTO_PROXIMO", f"Lote {lot.lote} de {lot.product_code} vence el {lot.fecha_venc:%d/%m/%Y}",
                    f"Almacén {lot.warehouse_code}; cantidad {lot.cantidad:g}.", "StockLot", lot.id,
                    dedup_key=f"VENC:{lot.id}")
        n += 1
    return n


def _tiempo_maximo(today):
    """Tiempo máximo de almacenamiento (riesgo de infestación) – configurable por producto."""
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
    return n


def _pasos(user, today):
    """(nombre, función) de cada verificación. V16: SAP va primero, para que el estado de la conexión (aviso rojo) y la
    cola de OV no dependan de las demás verificaciones."""
    from . import (budget, commercial_mgmt, commitment, costs, customer_behavior, demand_plan, finance, fleet, guides,
                   inventory, maintenance, maps, penalties, prices, prod_home, quality, quality_v13, sap_sl, shifts,
                   stock, supply, third_party, transfers)
    return [
        ("sap_service_layer", lambda: sap_sl.scheduled_sync()),
        ("fases_importacion", lambda: check_phases(today)),
        ("ov_retrasadas", lambda: _ov_retrasadas(today)),
        ("avisos_ejecutivo", lambda: __import__("app.services.seguimiento", fromlist=["x"]).check_seller_delays(today)),
        ("paradas_prolongadas", lambda: prod_home.check_long_stops()),  # V12: paradas que superan el tiempo configurado
        ("proyeccion_compras", lambda: demand_plan.check_purchase_deadlines(today)),
        ("lotes_observados", lambda: quality_v13.check_observed(today)),
        ("fumigaciones_por_liberar", lambda: quality_v13.check_fumigation_release(today)),
        ("reprocesos_vencidos", lambda: quality_v13.check_reprocess()),
        ("terceros_pagos_vencidos", lambda: third_party.check_payments(today)),
        ("presupuesto_consumo", lambda: budget.check_consumption(today)),
        ("rutas_manana_sin_planificar", lambda: guides.check_route_planning()),
        ("lotes_por_vencer", lambda: _por_vencer(today)),
        ("lotes_tiempo_maximo", lambda: _tiempo_maximo(today)),
        ("reposicion_solicitudes", lambda: len(run_replenishment(user, ref=today))),
        ("penalidades_vencidas", lambda: penalties.check_overdue(today)),
        ("conteos_ciclicos", lambda: inventory.check_cycle_counts(today)),
        ("movimientos_programados", lambda: supply.check_scheduled_moves()),
        ("metas_atrasadas", lambda: commercial_mgmt.check_goal_alerts(today)),
        ("listas_precio_por_vencer", lambda: prices.check_validity(today)),
        ("cargas_desactualizadas", lambda: check_upload_freshness()),
        ("ov_reserva_activada", lambda: stock.activate_deferred(user, today)),
        ("reservas_vencidas", lambda: stock.check_expired_reservations(user, today)),
        ("rutas_trafico", lambda: maps.check_active_routes(today)),
        ("avisos_fumigacion", lambda: quality.fumigation_alerts(today)),
        ("traslados_llegan_hoy", lambda: transfers.remind_arrivals(today)),
        ("costo_vs_mercado", lambda: costs.check_market_alerts(user)),
        ("variacion_compra_clientes", lambda: customer_behavior.check_purchase_variations(user, today)),
        ("flota", lambda: fleet.check_alerts(today)),
        ("ov_riesgo_48_24h", lambda: supply.check_order_risk()),
        ("stock_sin_rotacion_mensual", lambda: supply.check_no_rotation(today)),
        ("mantenimiento_saneamiento", lambda: maintenance.check_alerts(today)),
        ("tareas_incumplidas_aviso_jefe", lambda: shifts.check_overdue()),
        ("tareas_pendientes_fin_turno", lambda: shifts.check_end_of_shift()),
        ("ov_sin_compromiso", lambda: commitment.check_pending()),
        ("facturas_vencidas", lambda: finance.check_overdue(today)),
        # V22: devoluciones sin recibir, avisos de preventivos (7/3/0 días) y limpiezas sin marcar
        ("devoluciones_vencidas", lambda: __import__("app.services.devoluciones", fromlist=["x"]).check_overdue(today)),
        ("mant_preventivos_proximos", lambda: __import__("app.services.mant_trabajos", fromlist=["x"]).check_alerts(today)),
        ("limpieza_incumplida", lambda: __import__("app.services.limpieza", fromlist=["x"]).check_unfinished(today)),
        # V24: tipo de cambio SUNAT, seguimiento de importaciones (retiro, sobreestadía, penalidades) y costo de reposición
        ("tipo_cambio_sunat", lambda: _tipo_cambio(today)),
        ("importaciones_seguimiento", lambda: __import__("app.services.importaciones_v24", fromlist=["x"]).check_alerts(today)),
        ("costo_reposicion", lambda: __import__("app.services.costos_v24", fromlist=["x"]).check_alerts(today)),
        ("ingreso_semanal", lambda: __import__("app.services.ingresos_semana", fromlist=["x"]).revisar_semana_cerrada(today)),
        ("correo", lambda: flush_outbox()),
    ]


def _tipo_cambio(today):
    """En pruebas no se sale a internet."""
    from flask import current_app
    if current_app and current_app.config.get("TESTING"):
        return "omitido en pruebas"
    r = __import__("app.services.tipo_cambio", fromlist=["x"]).actualizar(hoy=today)
    return f"{r.fecha} {r.venta}" if r else "sin conexión: registrar a mano"


def run_checks(user=None, today=None):
    """Ejecuta las verificaciones. V16: cada una se guarda por separado; si una falla, se deshace solo esa, queda en el
    registro del servidor (journalctl) con su detalle y las demás siguen (antes un error descartaba todas, también la
    sincronización con SAP y el estado de la conexión)."""
    import logging
    today = today or date.today()
    out = {}
    for nombre, fn in _pasos(user, today):
        try:
            out[nombre] = fn()
            db().commit()
        except Exception as e:  # noqa: BLE001
            db().rollback()
            logging.getLogger("verificaciones").exception("Verificación «%s» falló", nombre)
            out[nombre] = f"error: {type(e).__name__}: {str(e)[:200]}"
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
