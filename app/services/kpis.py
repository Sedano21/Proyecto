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


RECHAZOS = ("RECHAZO_CALIDAD", "RECHAZO_OTRO", "RECHAZO_CITA", "DEVOLUCION", "ENTREGA_PARCIAL", "CLIENTE_NO_RETIRA",
            "CLIENTE_AUSENTE", "PARTICULARIDAD_DESCARGA")


def fill_rate(salidas):
    """Fill rate a la salida del vehículo (decisión Q2, 12-oct-2026): cuánto del pedido salió (unidades, líneas y pedidos
    al 100 %), si un pedido que salió al 100 % tuvo después rechazo y su motivo, y en qué etapa del proceso se
    concentran las fallas (incompletos, salidas tardías y rechazos), para ubicar los mayores errores."""
    from ..catalogs import INCIDENT_TYPES
    nombres = dict(INCIDENT_TYPES)
    etapas = param("etapa_por_incidencia", {}) or {}
    s = db()
    out = {"fill_rate_unidades": None, "fill_rate_lineas": None, "fill_rate_pedidos": None, "fill_detalle": [],
           "fill_causas": []}
    if not salidas:
        return out
    pedido = despachado = 0.0
    lineas = lineas_ok = pedidos_ok = 0
    causas = Counter()
    for o in sorted(salidas, key=lambda x: x.salida_ts, reverse=True):
        act = [l for l in o.lines if l.activa]
        q = sum(l.cantidad for l in act)
        d = sum(min(l.despachado, l.cantidad) for l in act)
        pedido += q
        despachado += d
        lineas += len(act)
        ok_l = sum(1 for l in act if l.despachado >= l.cantidad - 1e-9)
        lineas_ok += ok_l
        completo = ok_l == len(act)
        a_tiempo = o.salida_ts.date() <= o.fecha_compromiso
        pedidos_ok += completo
        incs = list(s.execute(select(Incident).where(Incident.order_id == o.id, Incident.tipo.in_(RECHAZOS))).scalars())
        motivos = [f"{nombres.get(i.tipo, i.tipo)}" + (f": {i.descripcion}" if i.descripcion else "") for i in incs]
        if not completo:
            causas[(etapas.get("SALIDA_INCOMPLETA", "Sin clasificar"), "Salió incompleto (faltante)")] += 1
        if not a_tiempo:
            causas[(etapas.get("SALIDA_TARDIA", "Sin clasificar"), "Salió después de la fecha comprometida")] += 1
        for i in incs:
            causas[(etapas.get(i.tipo, "Sin clasificar"), nombres.get(i.tipo, i.tipo))] += 1
        out["fill_detalle"].append({"numero": o.numero, "cliente": o.customer.nombre, "fecha": o.fecha_compromiso,
                                    "salida": o.salida_ts, "fill": round(100 * d / q, 1) if q else None,
                                    "completo": completo, "a_tiempo": a_tiempo, "rechazo": bool(incs), "motivos": motivos})
    out["fill_rate_unidades"] = round(100 * despachado / pedido, 1) if pedido else None
    out["fill_rate_lineas"] = round(100 * lineas_ok / lineas, 1) if lineas else None
    out["fill_rate_pedidos"] = (round(100 * pedidos_ok / len(salidas), 1), pedidos_ok, len(salidas))
    completos = [x for x in out["fill_detalle"] if x["completo"]]
    out["completos_con_rechazo"] = (sum(1 for x in completos if x["rechazo"]), len(completos))
    out["fill_causas"] = [(e, m, n) for (e, m), n in causas.most_common()]
    por_etapa = Counter()
    for (e, _), n in causas.items():
        por_etapa[e] += n
    out["fill_por_etapa"] = por_etapa.most_common()
    return out


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
    k["otif_definicion"] = param("otif_definicion", "SALIDA")
    k["otif_salida"] = (round(100 * len(salida_ok) / len(salida_base), 1), len(salida_ok), len(salida_base)) if salida_base else None
    k["otif_entrega"] = (round(100 * len(entrega_ok) / len(entrega_base), 1), len(entrega_ok), len(entrega_base)) if entrega_base else None
    k.update(fill_rate(salida_base))
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
        ["BORRADOR", "PENDIENTE_LOGISTICA", "SOLICITADA", "EN_COTIZACION", "MUESTRA_EN_CALIDAD", "PENDIENTE_APROBACION", "ORDEN_GENERADA"])).count()
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
