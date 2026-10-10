"""Indicadores operativos y gerenciales (IF §17)."""
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import (Incident, Liquidation, PhysicalCountLine, ProductionRequest, PurchaseRequest, SalesOrder)
from .core import param
from .orders import order_amount, order_weight_kg
from .production import merma_comparison


def _between(o, desde, hasta):
    f = o.fecha_compromiso
    return (desde is None or f >= desde) and (hasta is None or f <= hasta)


def compute(desde=None, hasta=None):
    s = db()
    orders = [o for o in s.execute(select(SalesOrder)).scalars() if _between(o, desde, hasta)]
    activas = [o for o in orders if o.estado != "CANCELADA"]
    k = {}
    estados = Counter(o.estado for o in orders)
    k["estados"] = dict(estados)
    abiertas = [o for o in activas if o.estado not in ("DESPACHADA", "ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA", "DEVUELTA")]
    k["pendientes"] = len(abiertas)
    k["completos"] = sum(1 for o in abiertas if o.estado_stock == "COMPLETA")
    k["incompletos"] = sum(1 for o in abiertas if o.estado_stock in ("INCOMPLETA", "SIN_STOCK"))
    # OTIF – definición pendiente: se muestran ambas variantes (IF §17)
    salida_base = [o for o in activas if o.salida_ts is not None]
    salida_ok = [o for o in salida_base if o.salida_ts.date() <= o.fecha_compromiso and
                 all(l.despachado >= l.cantidad - 1e-9 for l in o.lines if l.activa)]
    entrega_base = [o for o in activas if o.estado in ("ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA", "DEVUELTA")]
    entrega_ok = [o for o in entrega_base if o.estado == "ENTREGADA" and o.entrega_ts and
                  o.entrega_ts.date() <= o.fecha_compromiso]
    k["otif_definicion"] = param("otif_definicion", "AMBAS")
    k["otif_salida"] = (round(100 * len(salida_ok) / len(salida_base), 1), len(salida_ok), len(salida_base)) if salida_base else None
    k["otif_entrega"] = (round(100 * len(entrega_ok) / len(entrega_base), 1), len(entrega_ok), len(entrega_base)) if entrega_base else None
    evaluadas = [o for o in abiertas if o.estado_stock != "SIN_EVALUAR"]
    k["cobertura_unidades_prom"] = round(sum(o.cobertura_unidades for o in evaluadas) / len(evaluadas), 1) if evaluadas else None
    k["cobertura_lineas_prom"] = round(sum(o.cobertura_lineas for o in evaluadas) / len(evaluadas), 1) if evaluadas else None
    faltantes = defaultdict(float)
    from .stock import line_reserved
    for o in abiertas:
        for l in o.lines:
            if l.activa:
                f = max(l.cantidad - l.despachado - line_reserved(l), 0)
                if f > 0:
                    faltantes[l.product_code] += f
    k["faltantes"] = sorted(faltantes.items(), key=lambda x: -x[1])[:15]
    k["detenidos"] = [(o.numero, o.customer.nombre, o.motivo_detencion) for o in abiertas if o.motivo_detencion]
    prep = [(o.prep_fin - o.prep_inicio).total_seconds() / 3600 for o in orders if o.prep_inicio and o.prep_fin]
    desp = [(o.salida_ts - o.prep_fin).total_seconds() / 3600 for o in orders if o.prep_fin and o.salida_ts]
    k["tiempo_preparacion_h"] = round(sum(prep) / len(prep), 2) if prep else None
    k["tiempo_despacho_h"] = round(sum(desp) / len(desp), 2) if desp else None
    k["compras_pendientes"] = s.query(PurchaseRequest).filter(PurchaseRequest.estado.in_(
        ["BORRADOR", "SOLICITADA", "EN_COTIZACION", "MUESTRA_EN_CALIDAD", "PENDIENTE_APROBACION", "ORDEN_GENERADA"])).count()
    k["produccion_pendiente"] = s.query(ProductionRequest).filter(ProductionRequest.estado.in_(
        ["BORRADOR", "ENVIADA", "VALIDADA", "PROGRAMADA", "EN_PROCESO"])).count()
    difs = s.query(PhysicalCountLine).filter((PhysicalCountLine.faltante > 0) | (PhysicalCountLine.sobrante > 0)).all()
    k["diferencias_inventario"] = len(difs)
    k["diferencias_inventario_faltante"] = sum(d.faltante for d in difs)
    k["diferencias_inventario_sobrante"] = sum(d.sobrante for d in difs)
    liq_dif = s.query(Liquidation).filter(Liquidation.estado.in_(["RECIBIDA_FALTANTE", "RECIBIDA_SOBRANTE"])).count()
    k["diferencias_liquidacion"] = liq_dif
    inc = Counter(i.tipo for i in s.execute(select(Incident)).scalars()
                  if i.order is None or _between(i.order, desde, hasta))
    k["incidencias"] = dict(inc)
    k["rechazos"] = inc.get("RECHAZO_CALIDAD", 0) + inc.get("RECHAZO_OTRO", 0)
    k["devoluciones"] = inc.get("DEVOLUCION", 0)
    k["entregas_parciales"] = inc.get("ENTREGA_PARCIAL", 0)
    mc = [m for m in merma_comparison() if m["real"] is not None]
    k["merma"] = [(m["liq"].numero_documento, m["liq"].product_code, m["prevista"], m["real"]) for m in mc[:15]]
    k["monto_total"] = round(sum(order_amount(o) for o in activas), 2)
    k["volumen_kg"] = round(sum(order_weight_kg(o, "solicitado")[0] for o in activas), 1)
    k["monto_pendiente"] = round(sum(order_amount(o) for o in abiertas), 2)
    k["volumen_pendiente_kg"] = round(sum(order_weight_kg(o, "solicitado")[0] for o in abiertas), 1)
    k["n_ordenes"] = len(orders)
    return k
