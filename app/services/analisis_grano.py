"""V76 (26-nov-2026): comportamiento de Producción por grano.

Con los partes de producción (cerrados o en curso con horas registradas) responde:
- ¿Cuánto nos toma procesar cada grano en cada línea? (kg por hora, kg por hora-operario, minutos por 100 kg)
- ¿Qué rendimiento y qué desmedro tiene cada grano en cada línea?
- ¿Cómo evolucionan semana a semana?
- ¿Cómo se comparan los granos entre sí?
Y propone mejoras. Las sugerencias son hipótesis para revisar con Producción, no causas comprobadas: el sistema
señala dónde mirar y con qué evidencia.

El grano sale de la descripción del producto (parámetro «abastecimiento_granos», el mismo del plan por grano).
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Product, ProductionReport
from .plan_granos import granos_config, grano_de
from .plan_produccion_v72 import _horas


def _semana(d):
    return d - timedelta(days=d.weekday())


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def partes(desde, hasta, linea="", grano="", producto=""):
    """Partes del periodo con su grano y horas efectivas."""
    q = select(ProductionReport).where(ProductionReport.fecha >= desde, ProductionReport.fecha <= hasta,
                                       ProductionReport.estado.notin_(("PROGRAMADO", "ANULADO")))
    if linea:
        q = q.where(ProductionReport.linea == linea)
    if producto:
        q = q.where(ProductionReport.product_code == producto)
    cfg = granos_config()
    prods = {p.code: p for p in db().execute(select(Product)).scalars()}
    out = []
    for r in db().execute(q).scalars():
        p = prods.get(r.product_code)
        g = grano_de(p.descripcion if p else r.product_code, cfg)
        if grano and g != grano:
            continue
        kg = _num(r.peso_entrada_kg) or 0
        if kg <= 0:
            continue
        out.append({"r": r, "grano": g, "kg": kg, "horas": _horas(r), "operarios": r.operarios or None,
                    "rend": _num(r.rendimiento_pct), "desm": _num(r.desmedro_pct), "producto": r.product_code,
                    "descripcion": p.descripcion if p else ""})
    return out


def _agrega(filas):
    kg = sum(f["kg"] for f in filas)
    con_h = [f for f in filas if f["horas"]]
    kg_h, horas = sum(f["kg"] for f in con_h), sum(f["horas"] for f in con_h)
    hh = sum(f["horas"] * (f["operarios"] or 1) for f in con_h)
    con_r = [f for f in filas if f["rend"] is not None]
    con_d = [f for f in filas if f["desm"] is not None]
    pond = lambda lst, k: round(sum(f[k] * f["kg"] for f in lst) / sum(f["kg"] for f in lst), 1) if lst and sum(f["kg"] for f in lst) else None
    return {"partes": len(filas), "kg": round(kg, 1), "horas": round(horas, 1),
            "kg_hora": round(kg_h / horas, 1) if horas else None, "kg_hora_op": round(kg_h / hh, 1) if hh else None,
            "min_100kg": round(60 * horas / kg_h * 100, 1) if kg_h else None,
            "rendimiento": pond(con_r, "rend"), "desmedro": pond(con_d, "desm")}


def analisis(desde=None, hasta=None, linea="", grano=""):
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=180)
    fs = partes(desde, hasta, linea, grano)
    por_grano, por_gl, por_sem = defaultdict(list), defaultdict(list), defaultdict(lambda: defaultdict(list))
    for f in fs:
        por_grano[f["grano"]].append(f)
        por_gl[(f["grano"], f["r"].linea)].append(f)
        por_sem[f["grano"]][_semana(f["r"].fecha)].append(f)
    granos = sorted(({"grano": g, **_agrega(l)} for g, l in por_grano.items()), key=lambda x: -x["kg"])
    lineas = sorted(({"grano": g, "linea": l, **_agrega(x)} for (g, l), x in por_gl.items()),
                    key=lambda x: (x["grano"], -(x["kg_hora"] or 0)))
    semanas = sorted({s for d in por_sem.values() for s in d})
    evol = {}
    for g in [x["grano"] for x in granos[:6]]:
        evol[g] = [(s, _agrega(por_sem[g][s]) if por_sem[g].get(s) else None) for s in semanas]
    return {"desde": desde, "hasta": hasta, "linea": linea, "grano": grano, "granos": granos, "lineas": lineas,
            "semanas": semanas, "evolucion": evol, "partes": len(fs), "sugerencias": sugerencias(granos, lineas, evol),
            "todos_granos": sorted({x["grano"] for x in granos} | {g["grano"] for g in granos_config()}),
            "sin_horas": sum(1 for f in fs if not f["horas"])}


def sugerencias(granos, lineas, evol):
    """Propuestas con evidencia. Se indica siempre que son hipótesis por revisar."""
    out = []
    # 1. el mismo grano rinde distinto según la línea
    por_g = defaultdict(list)
    for x in lineas:
        if x["kg_hora"] and x["partes"] >= 2:
            por_g[x["grano"]].append(x)
    for g, xs in por_g.items():
        if len(xs) < 2:
            continue
        mejor, peor = max(xs, key=lambda x: x["kg_hora"]), min(xs, key=lambda x: x["kg_hora"])
        if peor["kg_hora"] < mejor["kg_hora"] * 0.75:
            out.append({"grano": g, "tipo": "Tiempo",
                        "texto": f"{g}: en {mejor['linea']} se procesa a {mejor['kg_hora']:g} kg/h y en {peor['linea']} a "
                                 f"{peor['kg_hora']:g} kg/h ({100 * (1 - peor['kg_hora'] / mejor['kg_hora']):.0f} % menos).",
                        "accion": f"Evaluar programar {g} de preferencia en {mejor['linea']}, o revisar en {peor['linea']} "
                                  "la calibración, el método y la capacitación del personal (hipótesis por verificar)."})
    # 2. granos con desmedro alto frente al resto
    con_d = [x for x in granos if x["desmedro"] is not None and x["partes"] >= 3]
    if len(con_d) >= 3:
        med = sorted(x["desmedro"] for x in con_d)[len(con_d) // 2]
        for x in con_d:
            if med and x["desmedro"] > med * 1.5 and x["desmedro"] - med >= 1:
                out.append({"grano": x["grano"], "tipo": "Desmedro",
                            "texto": f"{x['grano']}: desmedro de {x['desmedro']:g} % frente a {med:g} % de mediana de los "
                                     f"granos ({x['partes']} partes, {x['kg']:,.0f} kg).",
                            "accion": "Revisar la calidad de la materia prima de origen (informe de recepción) y el ajuste de "
                                      "la selección; si viene del proveedor, llevarlo a la negociación (hipótesis)."})
    # 3. rendimiento que cae en las últimas semanas
    for g, serie in evol.items():
        vals = [a["rendimiento"] for _, a in serie if a and a["rendimiento"] is not None]
        if len(vals) >= 6:
            ant, rec = sum(vals[-6:-3]) / 3, sum(vals[-3:]) / 3
            if ant and rec < ant - 2:
                out.append({"grano": g, "tipo": "Rendimiento",
                            "texto": f"{g}: el rendimiento bajó de {ant:.1f} % a {rec:.1f} % en las últimas 3 semanas.",
                            "accion": "Comparar los lotes de materia prima de esas semanas y las paradas registradas; "
                                      "confirmar si es la materia prima o el proceso antes de actuar."})
    # 4. selección manual lenta
    for x in lineas:
        if "MANUAL" in (x["linea"] or "").upper() and x["kg_hora_op"] and x["partes"] >= 2:
            otros = [y["kg_hora_op"] for y in lineas if y["grano"] == x["grano"] and y is not x and y["kg_hora_op"]]
            if otros and x["kg_hora_op"] < min(otros) * 0.5:
                out.append({"grano": x["grano"], "tipo": "Tiempo",
                            "texto": f"{x['grano']}: la selección manual rinde {x['kg_hora_op']:g} kg/h por operario frente a "
                                     f"{min(otros):g} en las líneas mecanizadas.",
                            "accion": "Evaluar pasar a la línea óptica la parte que lo permita y dejar en manual solo lo "
                                      "que lo necesita (hipótesis por validar con Calidad)."})
    return out


# ------------------------------------------------------------------ rotación para el planeamiento
def _anio_antes(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def rotacion_plan(codes, desde, hasta):
    """V76: para el planeamiento (diario, semanal o mensual): cuánto se vendió (salió) del producto y de su grano en el
    periodo y en el mismo periodo del año anterior. Fuente: guías de SAP o, si no hay, el historial cargado.
    Devuelve ({code: {act, ant, var}}, {grano: {act_kg, ant_kg, var}}, fuente, (desde_ant, hasta_ant))."""
    from .orders import kg_unidad
    from .semaforo import salidas
    hasta_act = min(hasta, date.today())
    d_ant, h_ant = _anio_antes(desde), _anio_antes(hasta)
    cfg = granos_config()
    prods = {p.code: p for p in db().execute(select(Product)).scalars()}
    grano = {c: grano_de(p.descripcion, cfg) for c, p in prods.items()}
    act, fuente = salidas(desde, hasta_act) if hasta_act >= desde else ([], "")
    ant, fuente_ant = salidas(d_ant, h_ant)
    por_p = defaultdict(lambda: [0.0, 0.0])
    por_g = defaultdict(lambda: [0.0, 0.0])
    for i, filas in ((0, act), (1, ant)):
        for _f, code, q, _c in filas:
            por_p[code][i] += q or 0
            p = prods.get(code)
            por_g[grano.get(code, "OTROS")][i] += (q or 0) * (kg_unidad(p) if p else 0)
    var = lambda a, b: round(100 * (a - b) / b, 1) if b else None
    res_p = {c: {"act": round(por_p[c][0], 1), "ant": round(por_p[c][1], 1), "var": var(*por_p[c]),
                 "grano": grano.get(c, "OTROS")} for c in codes}
    gs = {grano.get(c, "OTROS") for c in codes}
    res_g = {g: {"act_kg": round(por_g[g][0], 1), "ant_kg": round(por_g[g][1], 1), "var": var(*por_g[g])} for g in gs}
    return res_p, res_g, fuente or fuente_ant, (d_ant, h_ant)
