"""Inicio del Jefe de Producción (V12, 29-oct-2026): la operación del día de un vistazo.

Qué responde:
- ¿Qué líneas están produciendo, cuáles están paradas y por qué (y desde hace cuánto)?
- ¿A qué ritmo va cada línea, cuándo termina lo programado y cuánto peso habrá producido al cierre del turno?
- ¿Llegaremos a producir todo lo planificado hoy? ¿Hay desviación entre lo planificado y lo que se está produciendo?
- ¿Qué está pendiente: solicitudes de producción y reempaques ya aprobados por Calidad?
- ¿Cuánta merma lleva el día frente al umbral?

Los cálculos son estimaciones con el ritmo real del parte en curso (kg producidos / minutos efectivos). Si el parte no
tiene avance registrado aún, no se inventa un ritmo: se usa la capacidad nominal de la línea (kg/día de la tabla de
capacidades) y se indica así.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Product, ProductionPlan, ProductionReport, ProductionRequest, RepackRequest, now
from . import alerts
from .core import param

ACTIVOS = ("EN PROCESO", "PAUSADO")
SOL_PENDIENTES = ("ENVIADA", "VALIDADA", "PROGRAMADA", "EN_PROCESO")


def _hhmm_dt(d, hhmm):
    try:
        h, m = [int(x) for x in str(hhmm).split(":")[:2]]
        return datetime.combine(d, datetime.min.time()).replace(hour=h, minute=m)
    except (TypeError, ValueError):
        return None


def _open_pause(r):
    for p in reversed(r.pausas or []):
        if not p.get("fin"):
            return p
    return None


def _kg_of(code, cantidad):
    p = db().get(Product, code)
    if p is None:
        return 0.0
    if (p.um or "").upper().startswith("K"):
        return cantidad
    return cantidad * (p.peso_kg or 0)


def _capacidad_linea():
    """kg/hora nominal por línea a partir de la tabla de capacidades (kg/día del grupo repartido entre sus líneas)."""
    horas = float(param("horas_jornada_produccion", 8) or 8)
    out = {}
    for g in param("capacidad_lineas", []) or []:
        lineas = g.get("lineas") or []
        if lineas and g.get("kg_dia"):
            for l in lineas:
                out[l] = float(g["kg_dia"]) / len(lineas) / horas
    return out


def line_status(ahora=None):
    """Una fila por línea: estado, parte, avance, ritmo, fin estimado, kg al cierre del turno y paradas."""
    from ..catalogs import PRODUCTION_LINES
    from .parte import _min, live
    ahora = ahora or now()
    hoy = ahora.date()
    fin_turno = _hhmm_dt(hoy, param("hora_fin_produccion", "17:00")) or ahora
    prolongada = int(param("parada_prolongada_min", 30) or 30)
    cap_h = _capacidad_linea()
    partes = list(db().execute(select(ProductionReport).where(
        (ProductionReport.estado.in_(ACTIVOS)) | ((ProductionReport.fecha == hoy) &
                                                   (ProductionReport.estado == "PROGRAMADO")))).scalars())
    por_linea = defaultdict(list)
    for r in partes:
        por_linea[r.linea].append(r)
    filas = []
    for code, nombre, _ in PRODUCTION_LINES:
        rs = por_linea.get(code, [])
        activo = next((r for r in rs if r.estado in ACTIVOS), None)
        programados = [r for r in rs if r.estado == "PROGRAMADO"]
        f = {"linea": code, "nombre": nombre, "estado": "SIN PROGRAMA", "parte": activo, "programados": programados,
             "kg_programado": sum(r.peso_entrada_kg or 0 for r in programados), "producto": "", "avance_kg": 0.0,
             "objetivo_kg": 0.0, "ritmo_kg_h": None, "ritmo_fuente": "", "fin_estimado": None, "restante_min": None,
             "kg_al_cierre": None, "termina": None, "parada": None}
        if activo is not None:
            lv = live(activo)
            f["producto"] = activo.product_code
            f["avance_kg"] = lv.get("salida_kg") or 0.0
            f["objetivo_kg"] = activo.peso_entrada_kg or 0.0
            pausa = _open_pause(activo)
            efectivos = max(_min(activo.inicio_ts, ahora) - _pausado_min(activo, ahora), 0) if activo.inicio_ts else 0
            if f["avance_kg"] and efectivos >= 10:
                f["ritmo_kg_h"], f["ritmo_fuente"] = round(f["avance_kg"] / efectivos * 60, 1), "real"
            elif cap_h.get(code):
                f["ritmo_kg_h"], f["ritmo_fuente"] = round(cap_h[code], 1), "nominal"
            restante = max(f["objetivo_kg"] - f["avance_kg"], 0)
            if f["ritmo_kg_h"]:
                f["restante_min"] = round(restante / f["ritmo_kg_h"] * 60)
                # en pausa no avanza: se estima como si reanudara ahora (el fin se corre mientras dure la parada)
                f["fin_estimado"] = ahora + timedelta(minutes=f["restante_min"])
                horas_disp = max((fin_turno - ahora).total_seconds() / 3600, 0)
                f["kg_al_cierre"] = round(min(f["avance_kg"] + f["ritmo_kg_h"] * horas_disp, f["objetivo_kg"] or 1e12), 1)
                f["termina"] = f["fin_estimado"] <= fin_turno
            if activo.estado == "PAUSADO" and pausa:
                desde = datetime.fromisoformat(pausa["inicio"])
                m = round(_min(desde, ahora))
                f["estado"] = "PARADA"
                f["parada"] = {"causa": pausa.get("causa") or "sin motivo", "minutos": m, "desde": desde,
                               "prolongada": m >= prolongada}
            else:
                f["estado"] = "EN PROCESO"
        elif programados:
            f["estado"] = "PROGRAMADA"
            f["objetivo_kg"] = f["kg_programado"]
            if cap_h.get(code):
                f["ritmo_kg_h"], f["ritmo_fuente"] = round(cap_h[code], 1), "nominal"
                horas_disp = max((fin_turno - ahora).total_seconds() / 3600, 0)
                f["kg_al_cierre"] = round(min(cap_h[code] * horas_disp, f["objetivo_kg"]), 1)
                f["termina"] = cap_h[code] * horas_disp >= f["objetivo_kg"]
        filas.append(f)
    return filas, fin_turno


def _pausado_min(r, ahora):
    from .parte import _min
    t = 0.0
    for p in r.pausas or []:
        ini = datetime.fromisoformat(p["inicio"])
        fin = datetime.fromisoformat(p["fin"]) if p.get("fin") else ahora
        t += _min(ini, fin)
    return t


def summary(ahora=None):
    """Datos del inicio de Producción."""
    ahora = ahora or now()
    hoy = ahora.date()
    filas, fin_turno = line_status(ahora)
    # planificado (plan diario + partes programados de hoy) vs ejecutado (partes de hoy, en curso o cerrados)
    plan_kg = sum(_kg_of(p.product_code, p.cantidad) for p in db().execute(select(ProductionPlan).where(
        ProductionPlan.periodo == "DIA", ProductionPlan.fecha == hoy)).scalars())
    partes_hoy = [r for r in db().execute(select(ProductionReport).where(ProductionReport.fecha == hoy)).scalars()
                  if r.estado != "ANULADO"]
    programado_kg = sum(r.peso_entrada_kg or 0 for r in partes_hoy) if not plan_kg else 0
    plan_total = plan_kg or programado_kg
    from .parte import live
    ejecutado = sum((live(r).get("salida_kg") or 0) for r in partes_hoy if r.estado not in ("PROGRAMADO",))
    al_cierre = sum((f["kg_al_cierre"] or f["avance_kg"] or 0) for f in filas) + \
        sum((r.granel_kg or 0) for r in partes_hoy if r.estado not in ("PROGRAMADO",) + ACTIVOS)
    esperado_ahora = None
    ini_turno = _hhmm_dt(hoy, param("hora_inicio_produccion", "08:00"))
    if plan_total and ini_turno and fin_turno > ini_turno:
        avance_t = min(max((ahora - ini_turno).total_seconds() / (fin_turno - ini_turno).total_seconds(), 0), 1)
        esperado_ahora = round(plan_total * avance_t, 1)
    desviacion = round(100 * (ejecutado - esperado_ahora) / esperado_ahora, 1) if esperado_ahora else None
    # merma del día (partes cerrados) y de los últimos 7 días
    cerrados = [r for r in db().execute(select(ProductionReport).where(
        ProductionReport.fecha >= hoy - timedelta(days=6), ProductionReport.fecha <= hoy)).scalars()
        if r.estado not in ("PROGRAMADO", "ANULADO") + ACTIVOS and r.peso_entrada_kg]
    def merma(rs):
        ent = sum(r.peso_entrada_kg for r in rs)
        return round(100 * sum((r.desmedro_pct or 0) * r.peso_entrada_kg / 100 for r in rs) / ent, 1) if ent else None
    solicitudes = list(db().execute(select(ProductionRequest).where(ProductionRequest.estado.in_(SOL_PENDIENTES))
                                    .order_by(ProductionRequest.fecha_requerida)).scalars())
    pendientes = defaultdict(lambda: {"cantidad": 0.0, "kg": 0.0, "requerida": None, "n": 0, "vencidas": 0})
    for s in solicitudes:
        x = pendientes[s.product_code]
        x["cantidad"] += s.cantidad
        x["kg"] += _kg_of(s.product_code, s.cantidad)
        x["n"] += 1
        if s.fecha_requerida and (x["requerida"] is None or s.fecha_requerida < x["requerida"]):
            x["requerida"] = s.fecha_requerida
        if s.fecha_requerida and s.fecha_requerida < hoy:
            x["vencidas"] += 1
    # reempaques: solo los aprobados por Calidad (los demás no le competen a Producción)
    reempaques = list(db().execute(select(RepackRequest).where(RepackRequest.estado.in_(("APROBADA", "EN_EJECUCION")))
                                   .order_by(RepackRequest.evaluado_ts)).scalars())
    alertas = []
    for f in filas:
        if f["parada"] and f["parada"]["prolongada"]:
            alertas.append(("ALTA", f"{f['nombre']}: parada hace {f['parada']['minutos']} min por «{f['parada']['causa']}»."))
        elif f["termina"] is False:
            alertas.append(("MEDIA", f"{f['nombre']}: con el ritmo actual no termina lo programado antes de las "
                                     f"{fin_turno:%H:%M} (fin estimado {f['fin_estimado']:%H:%M})." if f["fin_estimado"] else
                                     f"{f['nombre']}: con la capacidad nominal no alcanza lo programado antes de las {fin_turno:%H:%M}."))
    if desviacion is not None and desviacion < -float(param("desviacion_plan_alerta_pct", 10) or 10):
        alertas.append(("ALTA", f"Producción {abs(desviacion)} % por debajo de lo esperado a esta hora "
                                f"({ejecutado:,.0f} de {esperado_ahora:,.0f} kg)."))
    vencidas = sum(x["vencidas"] for x in pendientes.values())
    if vencidas:
        alertas.append(("MEDIA", f"{vencidas} solicitud(es) de producción con fecha requerida vencida."))
    return {"ahora": ahora, "fin_turno": fin_turno, "lineas": filas, "plan_kg": round(plan_total, 1),
            "plan_fuente": "plan diario" if plan_kg else ("partes programados" if programado_kg else ""),
            "ejecutado_kg": round(ejecutado, 1), "al_cierre_kg": round(al_cierre, 1), "esperado_ahora": esperado_ahora,
            "desviacion": desviacion, "cumplira": (al_cierre >= plan_total * 0.98) if plan_total else None,
            "en_proceso": sum(1 for f in filas if f["estado"] == "EN PROCESO"),
            "paradas": [f for f in filas if f["estado"] == "PARADA"],
            "merma_hoy": merma([r for r in cerrados if r.fecha == hoy]), "merma_7d": merma(cerrados),
            "umbral_merma": float(param("umbral_merma_pct", 5) or 5),
            "solicitudes": solicitudes, "solicitudes_por_estado": _count(s.estado for s in solicitudes),
            "pendientes": sorted(pendientes.items(), key=lambda kv: (kv[1]["requerida"] or date.max)),
            "reempaques": reempaques, "alertas": alertas}


def _count(it):
    out = defaultdict(int)
    for x in it:
        out[x] += 1
    return dict(out)


def check_long_stops(ahora=None):
    """Verificación periódica: alerta al Jefe de Producción y a Gerencia de Operaciones por cada parada que supera
    `parada_prolongada_min` (una vez por parada)."""
    filas, _ = line_status(ahora)
    n = 0
    for f in filas:
        p = f["parada"]
        if p and p["prolongada"]:
            alerts.emit("PARADA_PROLONGADA", f"Parada prolongada en {f['nombre']}: {p['minutos']} min",
                        f"Motivo: {p['causa']}. Producto {f['producto']}. Parada desde las {p['desde']:%H:%M}.",
                        "ProductionReport", f["parte"].id, prioridad="ALTA",
                        dedup_key=f"PARADA_PROL:{f['parte'].id}:{p['desde']:%Y%m%d%H%M}")
            n += 1
    return n
