"""Verificaciones periódicas que generan alertas automáticas (IF §14).
Se ejecutan con el botón 'Ejecutar verificaciones', con `python -m app.cli verificar` (para programar con cron /
Programador de tareas) o con un hilo en segundo plano si CHECK_INTERVAL_MIN > 0."""
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
    out["correo"] = flush_outbox()
    return out


def start_background(app_factory_session_commit, interval_min):
    def loop():
        while True:
            time.sleep(interval_min * 60)
            try:
                run_checks()
                SessionLocal().commit()
            except Exception:  # noqa: BLE001
                SessionLocal().rollback()
            finally:
                SessionLocal.remove()
    t = threading.Thread(target=loop, daemon=True, name="verificaciones")
    t.start()
    return t
