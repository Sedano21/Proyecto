"""Análisis de Producción por línea y por persona (V12, 29-oct-2026).

- Merma y remanente de MP (materia prima utilizable que no se usó porque se completó el pedido; antes «pucho» o
  sobrante) por línea y, en las líneas manuales, por persona.
- Desempeño por persona: kg, horas, kg/h, comparación con el promedio de su línea, tasa de ausencia (Asistencia).
- Recomendaciones con reglas explícitas y umbrales configurables. Cada recomendación dice el dato que la sustenta;
  son sugerencias para el responsable, no decisiones. Se exige un mínimo de partes para no sacar conclusiones con
  muestras pequeñas.

La merma por persona se toma de lo que se registró en el parte (líneas manuales). Si un parte no la tiene por persona,
se reparte la merma del parte según los kg de cada colaborador y se indica como «estimada».
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean

from sqlalchemy import select

from ..db import db
from ..models import Attendance, ProductionReport, Worker
from .core import param

CERRADOS_EXCLUIR = ("PROGRAMADO", "ANULADO", "EN PROCESO", "PAUSADO")
LINEAS_MANUALES = ("SEL_MANUAL", "ENV_MANUAL")


def _merma_kg(r):
    if r.desmedro_kg:
        return r.desmedro_kg
    return (r.desmedro_pct or 0) * (r.peso_entrada_kg or 0) / 100


def _horas(r, c):
    from .parte import _dt, _min
    ini, fin = _dt(r.fecha, c.get("inicio")), _dt(r.fecha, c.get("fin"))
    if not (ini and fin):
        return 0.0
    if fin < ini:
        fin += timedelta(days=1)
    return max(_min(ini, fin) - float(c.get("refrigerio_min") or 0), 0) / 60.0


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def analyze(desde=None, hasta=None, lineas=None):
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=29)
    partes = [r for r in db().execute(select(ProductionReport).where(ProductionReport.fecha >= desde,
                                                                     ProductionReport.fecha <= hasta)).scalars()
              if r.estado not in CERRADOS_EXCLUIR and (lineas is None or r.linea in lineas)]
    # --- por línea
    L = defaultdict(lambda: {"partes": 0, "entrada": 0.0, "salida": 0.0, "merma": 0.0, "remanente": 0.0, "horas": 0.0})
    serie = defaultdict(lambda: {"merma": 0.0, "remanente": 0.0, "entrada": 0.0})
    for r in partes:
        x = L[r.linea]
        x["partes"] += 1
        x["entrada"] += r.peso_entrada_kg or 0
        x["salida"] += r.granel_kg or 0
        x["merma"] += _merma_kg(r)
        x["remanente"] += r.sobrante_kg or 0
        x["horas"] += (r.indicadores or {}).get("horas_efectivas") or r.horas or 0
        sm = serie[r.fecha]
        sm["merma"] += _merma_kg(r)
        sm["remanente"] += r.sobrante_kg or 0
        sm["entrada"] += r.peso_entrada_kg or 0
    lineas_rows = []
    for k, x in sorted(L.items()):
        lineas_rows.append({"linea": k, **{a: round(b, 1) if isinstance(b, float) else b for a, b in x.items()},
                            "merma_pct": round(100 * x["merma"] / x["entrada"], 2) if x["entrada"] else None,
                            "kg_h": round(x["salida"] / x["horas"], 1) if x["horas"] else None})
    # --- por persona (colaboradores registrados en los partes)
    P = defaultdict(lambda: {"partes": 0, "kg": 0.0, "horas": 0.0, "merma": 0.0, "remanente": 0.0, "estimada": False,
                             "por_linea": defaultdict(lambda: {"kg": 0.0, "horas": 0.0, "partes": 0}), "worker_id": None})
    for r in partes:
        cs = r.colaboradores or []
        if not cs:
            continue
        kg_tot = sum(_f(c.get("kg")) or 0 for c in cs)
        for c in cs:
            p = P[c.get("nombre") or "?"]
            p["worker_id"] = c.get("worker_id")
            kg = _f(c.get("kg")) or 0
            h = _horas(r, c)
            p["partes"] += 1
            p["kg"] += kg
            p["horas"] += h
            pl = p["por_linea"][r.linea]
            pl["kg"] += kg
            pl["horas"] += h
            pl["partes"] += 1
            if r.linea in LINEAS_MANUALES:
                if _f(c.get("merma_kg")) is not None:
                    p["merma"] += _f(c["merma_kg"])
                elif kg_tot:
                    p["merma"] += _merma_kg(r) * kg / kg_tot
                    p["estimada"] = True
                if _f(c.get("remanente_kg")) is not None:
                    p["remanente"] += _f(c["remanente_kg"])
    # asistencia de los colaboradores (tasa de ausencia = faltas / días registrados)
    asis = defaultdict(Counter)
    for a in db().execute(select(Attendance).where(Attendance.fecha >= desde, Attendance.fecha <= hasta)).scalars():
        if (a.worker.area or "Producción") == "Producción":
            asis[a.worker.nombre][a.estado] += 1
    personas = []
    for n, p in P.items():
        a = asis.get(n, Counter())
        dias = sum(a.values())
        personas.append({"nombre": n, "partes": p["partes"], "kg": round(p["kg"], 1), "horas": round(p["horas"], 1),
                         "kg_h": round(p["kg"] / p["horas"], 1) if p["horas"] and p["kg"] else None,
                         "merma": round(p["merma"], 1), "merma_pct": round(100 * p["merma"] / p["kg"], 2) if p["kg"] else None,
                         "remanente": round(p["remanente"], 1), "merma_estimada": p["estimada"],
                         "faltas": a.get("FALTA", 0), "tardanzas": a.get("TARDANZA", 0), "dias": dias,
                         "ausencia_pct": round(100 * a.get("FALTA", 0) / dias, 1) if dias else None,
                         "por_linea": {k: {"kg_h": round(v["kg"] / v["horas"], 1) if v["horas"] and v["kg"] else None,
                                           "partes": v["partes"]} for k, v in p["por_linea"].items()}})
    # personas sin partes pero con asistencia (para la tasa de ausencia)
    for n, a in asis.items():
        if n not in P:
            dias = sum(a.values())
            personas.append({"nombre": n, "partes": 0, "kg": 0, "horas": 0, "kg_h": None, "merma": 0, "merma_pct": None,
                             "remanente": 0, "merma_estimada": False, "faltas": a.get("FALTA", 0),
                             "tardanzas": a.get("TARDANZA", 0), "dias": dias,
                             "ausencia_pct": round(100 * a.get("FALTA", 0) / dias, 1) if dias else None, "por_linea": {}})
    personas.sort(key=lambda x: -(x["kg_h"] or 0))
    tot_ent = sum(x["entrada"] for x in L.values())
    res = {"desde": desde, "hasta": hasta, "lineas": lineas_rows, "personas": personas,
           "merma_kg": round(sum(x["merma"] for x in L.values()), 1),
           "remanente_kg": round(sum(x["remanente"] for x in L.values()), 1),
           "merma_pct": round(100 * sum(x["merma"] for x in L.values()) / tot_ent, 2) if tot_ent else None,
           "entrada_kg": round(tot_ent, 1), "salida_kg": round(sum(x["salida"] for x in L.values()), 1),
           "partes": len(partes),
           "serie": [(f"{d:%d/%m}", round(v["merma"], 1), round(v["remanente"], 1)) for d, v in sorted(serie.items())]}
    res["recomendaciones"] = recommendations(res)
    return res


def recommendations(res):
    """Reglas (umbrales en el parámetro «reglas_recomendacion_produccion»)."""
    cfg = {"bajo_promedio_pct": 15, "merma_sobre_promedio_pct": 30, "ausencia_alta_pct": 10, "mejor_linea_pct": 20,
           "capacidad_baja_pct": 60, "min_partes": 3}
    cfg.update(param("reglas_recomendacion_produccion", {}) or {})
    out = []
    personas = [p for p in res["personas"] if p["partes"] >= cfg["min_partes"]]
    # 1) rendimiento por debajo del promedio de su línea
    por_linea = defaultdict(list)
    for p in personas:
        for l, v in p["por_linea"].items():
            if v["kg_h"] and v["partes"] >= cfg["min_partes"]:
                por_linea[l].append((p["nombre"], v["kg_h"]))
    for l, xs in por_linea.items():
        if len(xs) < 2:
            continue
        prom = mean(v for _, v in xs)
        for n, v in xs:
            if v < prom * (1 - cfg["bajo_promedio_pct"] / 100):
                out.append(("MEDIA", f"{n} rinde {v:g} kg/h en {l}, {round(100 * (1 - v / prom))} % por debajo del promedio "
                                     f"de la línea ({prom:.1f} kg/h). Se recomienda capacitación o acompañamiento."))
    # 2) persona más rápida en una línea que en otra: recomendar permanencia
    for p in personas:
        ls = [(l, v["kg_h"]) for l, v in p["por_linea"].items() if v["kg_h"] and v["partes"] >= cfg["min_partes"]]
        if len(ls) >= 2:
            ls.sort(key=lambda x: -x[1])
            (la, va), (lb, vb) = ls[0], ls[-1]
            if va > vb * (1 + cfg["mejor_linea_pct"] / 100):
                out.append(("INFO", f"{p['nombre']} es más rápido en {la} ({va:g} kg/h) que en {lb} ({vb:g} kg/h). "
                                    f"Se recomienda su permanencia en {la}."))
    # 3) merma por persona superior al promedio
    con_merma = [p for p in personas if p["merma_pct"] is not None and p["kg"]]
    if len(con_merma) >= 2:
        prom = mean(p["merma_pct"] for p in con_merma)
        for p in con_merma:
            if prom and p["merma_pct"] > prom * (1 + cfg["merma_sobre_promedio_pct"] / 100):
                out.append(("MEDIA", f"{p['nombre']} genera {p['merma_pct']} % de merma frente al {prom:.2f} % promedio"
                                     f"{' (estimada)' if p['merma_estimada'] else ''}. Se recomienda prestar más atención a su "
                                     "trabajo en la línea."))
    # 4) ausencias
    aus = [p for p in res["personas"] if p["ausencia_pct"] is not None and p["dias"] >= 5]
    if aus:
        peor = max(aus, key=lambda p: p["ausencia_pct"])
        if peor["ausencia_pct"] >= cfg["ausencia_alta_pct"]:
            out.append(("ALTA", f"{peor['nombre']} tiene la tasa de faltas más alta ({peor['ausencia_pct']} %: "
                                f"{peor['faltas']} de {peor['dias']} días). Se recomienda conversar y analizar su permanencia."))
    # 5) líneas con merma alta y remanente pendiente de destino
    umbral = float(param("umbral_merma_pct", 5) or 5)
    for l in res["lineas"]:
        if l["merma_pct"] is not None and l["merma_pct"] > umbral and l["partes"] >= cfg["min_partes"]:
            out.append(("MEDIA", f"La línea {l['linea']} tiene {l['merma_pct']} % de merma (umbral {umbral:g} %): revisar "
                                 "calibración, materia prima y método de trabajo."))
    if res["remanente_kg"]:
        out.append(("INFO", f"Hay {res['remanente_kg']:,.0f} kg de remanente de MP en el periodo: Calidad, Operaciones y "
                            "Logística deben definir su destino (reproceso, reingreso a almacén o uso en el próximo lote)."))
    return out


def capacity_recommendations(desde, hasta):
    """Líneas no aprovechadas en su capacidad (uso por debajo del umbral)."""
    from . import reports as rsvc
    cfg = {"capacidad_baja_pct": 60}
    cfg.update(param("reglas_recomendacion_produccion", {}) or {})
    cap = rsvc.produccion_capacidad(desde, hasta)
    out = []
    if any(f["producido"] for f in cap["filas"]):
        for f in cap["filas"]:
            if f["capacidad"] and f["uso"] is not None and f["uso"] < cfg["capacidad_baja_pct"]:
                out.append(("MEDIA", f"La línea {f['grupo']} usa {f['uso']} % de su capacidad: no se está aprovechando; "
                                     "revisar y contrastar con la planificación."))
    return out, cap
