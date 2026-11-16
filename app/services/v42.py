"""V42 (14-nov-2026): alerta de capacidad de producción por línea y planeamiento agrupado por línea."""
from collections import defaultdict
from datetime import timedelta

from . import alerts
from .core import param


def check_capacidad_lineas(hoy):
    """Avisa a la Jefatura de Operaciones y de Producción cuando una línea (grupo de capacidad) usa menos del
    «capacidad_alerta_umbral» (80 %) de su capacidad: lo ejecutado en los últimos «capacidad_alerta_dias» días
    (hasta ayer) y lo programado para los próximos días. Una alerta por línea y semana."""
    from .production import capacity_vs_plan
    umbral = float(param("capacidad_alerta_umbral", 80) or 80)
    dias = int(param("capacidad_alerta_dias", 7) or 7)
    atras = capacity_vs_plan(hoy - timedelta(days=dias), hoy - timedelta(days=1))
    adelante = {f["grupo"]: f for f in capacity_vs_plan(hoy, hoy + timedelta(days=dias - 1))["filas"]}
    semana = hoy.isocalendar()
    n = 0
    for f in atras["filas"]:
        if not f["capacidad"]:
            continue
        prox = adelante.get(f["grupo"]) or {}
        bajo_ej = f["pct_ejecutada"] is not None and f["pct_ejecutada"] < umbral
        bajo_pr = prox.get("pct_programada") is not None and prox["pct_programada"] < umbral and prox.get("capacidad")
        if not (bajo_ej or bajo_pr):
            continue
        partes = []
        if bajo_ej:
            partes.append(f"últimos {dias} días: {f['pct_ejecutada']:g} % ejecutado ({f['ejecutada']:,.0f} de "
                          f"{f['capacidad']:,.0f} kg)")
        if bajo_pr:
            partes.append(f"próximos {dias} días: {prox['pct_programada']:g} % programado ({prox['programada']:,.0f} de "
                          f"{prox['capacidad']:,.0f} kg)")
        alerts.emit("CAPACIDAD_BAJA", f"Línea {f['grupo']} por debajo del {umbral:g} % de su capacidad",
                    "; ".join(partes) + ". Revise la programación, la demanda y las paradas de la línea.",
                    "Linea", f["grupo"], dedup_key=f"CAPACIDAD_BAJA:{f['grupo']}:{semana[0]}-{semana[1]}")
        n += 1
    return f"{n} línea(s) bajo {umbral:g} %"


def plan_por_linea(entradas, capa, dia=None):
    """Agrupa la programación por línea (grupo de capacidad). V48: el % de cada línea es lo **programado del día frente a
    su capacidad diaria** (kg/día × jornada del día), para ver qué líneas necesitan atención; además, el % de cada día
    programado."""
    from datetime import date as _date
    from .production import day_factor, kg_de
    dia = dia or _date.today()
    grupos = param("capacidad_lineas", []) or []
    grupo_de = {l: g["grupo"] for g in grupos for l in g.get("lineas", [])}
    kg_dia = {g["grupo"]: float(g.get("kg_dia") or 0) for g in grupos}
    por = defaultdict(list)
    for e in entradas:
        por[grupo_de.get(e.line_code, e.line_code or "Sin línea")].append(e)

    def dias_de(grupo, es):
        kg = defaultdict(float)
        for e in es:
            kg[e.fecha] += kg_de(e.product_code, e.cantidad)
        out = []
        for f in sorted(kg):
            cap = kg_dia.get(grupo, 0) * day_factor(f)
            out.append({"fecha": f, "kg": round(kg[f], 1), "capacidad": round(cap, 1),
                        "pct": round(100 * kg[f] / cap, 1) if cap else None})
        return out
    out = []
    for f in capa["filas"]:
        es = por.pop(f["grupo"], [])
        dias = dias_de(f["grupo"], es)
        hoy_ = next((x for x in dias if x["fecha"] == dia), None)
        cap_dia = kg_dia.get(f["grupo"], 0) * day_factor(dia)
        out.append(dict(f, entradas=es, del_dia=[e for e in es if e.fecha == dia], lineas=f.get("lineas") or [],
                        dias=dias, dia=dia, kg_dia_prog=hoy_["kg"] if hoy_ else 0.0, cap_dia=round(cap_dia, 1),
                        pct_dia=(round(100 * (hoy_["kg"] if hoy_ else 0) / cap_dia, 1) if cap_dia else None)))
    for g, es in sorted(por.items()):
        out.append({"grupo": g, "proceso": "", "capacidad": 0, "programada": 0, "ejecutada": 0, "pct_programada": None,
                    "pct_ejecutada": None, "cumplimiento": None, "entradas": es, "del_dia": [e for e in es if e.fecha == dia],
                    "lineas": [g] if g != "Sin línea" else [], "dias": dias_de(g, es), "dia": dia,
                    "kg_dia_prog": 0, "cap_dia": 0, "pct_dia": None})
    return out


def guardar_linea(user, dia, filas, nuevas, motivo="", linea_def=None):
    """V49: cuadro de una línea para un día: modificar cantidad, fecha o línea de lo programado, quitarlo (cantidad 0 o
    «quitar») y agregar productos. Cambios con motivo; los de un asistente quedan para validación del Jefe de Producción
    (mismas reglas del plan). filas: [{id, cantidad, fecha, linea, quitar}]; nuevas: [{producto, cantidad, linea, comentario}]."""
    from ..db import db
    from ..models import ProductionPlan
    from .core import BusinessError
    from .production import add_plan, update_plan
    cambios = 0
    for f in filas:
        pl = db().get(ProductionPlan, int(f["id"]))
        if pl is None:
            continue
        q = 0.0 if f.get("quitar") else f.get("cantidad")
        fecha, linea = f.get("fecha"), (f.get("linea") or "").strip() or None
        if q is None:
            raise BusinessError(f"{pl.product_code}: indique la cantidad.")
        if abs(q - (pl.cantidad or 0)) < 1e-9 and (not fecha or fecha == pl.fecha) and (not linea or linea == pl.line_code):
            continue
        if not (motivo or "").strip():
            raise BusinessError("Indique el motivo del cambio (p. ej. falta de materia prima, parada de línea, pedido urgente).")
        update_plan(user, pl, q, motivo, fecha, linea)
        cambios += 1
    for n in nuevas:
        code = (n.get("producto") or "").strip().upper().split(" ")[0]
        if not code and not n.get("cantidad"):
            continue
        add_plan(user, "DIA", dia, code, n.get("cantidad"), (n.get("linea") or linea_def or None),
                 (n.get("comentario") or "").strip() or (f"Agregado en el cuadro de la línea: {motivo}".strip(": ") if motivo else ""))
        cambios += 1
    if not cambios:
        raise BusinessError("No hay cambios que guardar.")
    return cambios
