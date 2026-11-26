"""V72 (24-nov-2026): lo que se desprende del planeamiento de Producción.

1. **Materiales para Almacén.** Cada entrada del plan diario se explota con su lista de materiales (granel, MP, envases,
   etiquetas e insumos; sin mano de obra ni CIF). Así Almacén sabe **qué** entregar a Producción y **cuándo**: el día
   de producción menos «plan_almacen_anticipacion_dias» (1 día por defecto). Se muestra el stock disponible y lo que
   falta. Al cargar o cambiar el plan se avisa a Almacén.
2. **Revisión del plan** (aviso a Producción):
   - **capacidad baja**: líneas programadas por debajo de «plan_capacidad_minima_pct» (80 %) de su capacidad;
   - **entregas no incluidas**: lo que se debe entregar (OV con faltante, solicitudes de producción y facturas de
     reserva) y no está en el plan del periodo;
   - **horario extendido**: si lo programado supera la capacidad de la línea, las horas extra necesarias (en total y
     por día, con la jornada de «demanda_jornada_horas»). Si superan «demanda_horas_extra_max_dia», se recomienda un
     tercero o pasar a otra línea.
3. **Tiempos por producto**: con los partes de producción, qué productos toman más y menos tiempo (kg por hora y por
   operario), por línea; sobre todo en selección manual.
Es un apoyo para planificar: no cambia el plan ni mueve stock."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Product, ProductionPlan, ProductionReport
from . import alerts
from .core import param

ROLES_ALMACEN_MP = ["COORD_ALMACEN_MP", "SUPERV_ALMACEN", "LIDER_ALMACEN", "ASIST_ALMACEN"]


def _entradas(desde, hasta):
    from .production import plan_status
    out = []
    for pl in db().execute(select(ProductionPlan).where(ProductionPlan.periodo == "DIA", ProductionPlan.fecha >= desde,
                                                        ProductionPlan.fecha <= hasta)
                           .order_by(ProductionPlan.fecha)).scalars():
        if plan_status(pl)[0] != "LIQUIDADO":
            out.append(pl)
    # V76: el plan semanal o mensual también avisa a Almacén, para los productos que no tienen plan diario en el rango
    # (se toma el primer día de la semana o del mes como fecha de producción; sin doble conteo)
    con_dia = {pl.product_code for pl in out}
    for pl in db().execute(select(ProductionPlan).where(ProductionPlan.periodo.in_(("SEMANA", "MES")),
                                                        ProductionPlan.fecha >= desde, ProductionPlan.fecha <= hasta)
                           .order_by(ProductionPlan.fecha)).scalars():
        if pl.product_code not in con_dia and plan_status(pl)[0] != "LIQUIDADO":
            out.append(pl)
    return out


def materiales(desde=None, hasta=None):
    """Lo que Almacén debe entregar a Producción por día: [{entregar_el, fecha_produccion, componente, descripcion,
    requerido, disponible, faltante, almacen, para: [{producto, cantidad, linea}]}] y los productos sin lista de
    materiales."""
    from .production import material_requirements
    desde = desde or date.today()
    hasta = hasta or desde + timedelta(days=int(param("plan_almacen_horizonte_dias", 7) or 7))
    ant = int(param("plan_almacen_anticipacion_dias", 1) or 0)
    acc = {}
    sin_bom = []
    for pl in _entradas(desde, hasta):
        mr = material_requirements(pl.product_code, pl.cantidad)
        if not mr["bom_encontrada"]:
            sin_bom.append(pl)
            continue
        entregar = max(pl.fecha - timedelta(days=ant), date.today())
        for m in mr["materiales"]:
            k = (entregar, m["componente"])
            a = acc.setdefault(k, {"entregar_el": entregar, "fecha_produccion": pl.fecha, "componente": m["componente"],
                                   "descripcion": m["descripcion"], "requerido": 0.0, "disponible": m["disponible_total"],
                                   "almacen": m["almacen"] or "", "para": []})
            a["requerido"] += m["requerido"]
            a["fecha_produccion"] = min(a["fecha_produccion"], pl.fecha)
            a["para"].append({"producto": pl.product_code, "cantidad": pl.cantidad, "linea": pl.line_code or ""})
    filas = sorted(acc.values(), key=lambda a: (a["entregar_el"], a["componente"]))
    # el disponible se va consumiendo día a día
    usado = defaultdict(float)
    for a in filas:
        a["requerido"] = round(a["requerido"], 3)
        libre = max(a["disponible"] - usado[a["componente"]], 0)
        a["faltante"] = round(max(a["requerido"] - libre, 0), 3)
        usado[a["componente"]] += a["requerido"]
    return {"desde": desde, "hasta": hasta, "anticipacion": ant, "filas": filas, "sin_bom": sin_bom}


def revision(desde=None, hasta=None):
    from .production import capacity_vs_plan, requirements
    desde = desde or date.today()
    hasta = hasta or desde + timedelta(days=int(param("plan_almacen_horizonte_dias", 7) or 7))
    minimo = float(param("plan_capacidad_minima_pct", 80) or 80)
    jornada = float(param("demanda_jornada_horas", 8) or 8)
    max_extra = float(param("demanda_horas_extra_max_dia", 2) or 0)
    cap = capacity_vs_plan(desde, hasta)
    baja, extendido = [], []
    for f in cap["filas"]:
        if f["capacidad"] and f["pct_programada"] is not None and f["pct_programada"] < minimo:
            baja.append(f)
        if f["capacidad"] and f["programada"] > f["capacidad"] + 1e-6 and f.get("kg_dia"):
            kg_h = float(f["kg_dia"]) / jornada
            horas = (f["programada"] - f["capacidad"]) / kg_h if kg_h else 0
            dias = max(cap["jornadas"], 1)
            por_dia = horas / dias
            extendido.append(dict(f, horas_extra=round(horas, 1), horas_extra_dia=round(por_dia, 1),
                                  recomendacion=(f"Horario extendido: {por_dia:.1f} h extra por día" if por_dia <= max_extra
                                                 else f"Más de {max_extra:g} h extra por día: evaluar un tercero o pasar "
                                                      "parte a otra línea")))
    req = requirements("DIA", desde, hasta)
    no_incluido = [a for a in req["filas"] if a["por_planificar"] > 1e-6]
    return {"desde": desde, "hasta": hasta, "minimo": minimo, "capacidad": cap["filas"], "baja": baja,
            "extendido": extendido, "no_incluido": no_incluido, "jornada": jornada, "max_extra": max_extra}


def avisar(user=None, desde=None, hasta=None):
    """Tras cargar o cambiar el plan: avisa a Almacén qué entregar y a Producción lo que revisar. Devuelve el resumen."""
    m = materiales(desde, hasta)
    r = revision(desde, hasta)
    if m["filas"]:
        dias = sorted({a["entregar_el"] for a in m["filas"]})
        falt = [a for a in m["filas"] if a["faltante"] > 1e-6]
        alerts.emit("PLAN_MATERIALES_ALMACEN", f"Materiales para Producción: {len(m['filas'])} entrega(s) del "
                    f"{dias[0]:%d/%m} al {dias[-1]:%d/%m}",
                    "Según el planeamiento cargado. " + (f"{len(falt)} con faltante de stock: "
                                                         + ", ".join(f"{a['componente']} ({a['faltante']:g})" for a in falt[:6])
                                                         if falt else "Hay stock para todo."),
                    "ProductionPlan", f"{m['desde']}:{m['hasta']}",
                    dedup_key=f"PLAN_MAT:{m['desde']}:{m['hasta']}:{len(m['filas'])}:{len(falt)}", creado_por=user)
    avisos = []
    if r["baja"]:
        avisos.append("por debajo de la capacidad: " + ", ".join(f"{f['grupo']} {f['pct_programada']:g} %" for f in r["baja"]))
    if r["no_incluido"]:
        avisos.append(f"{len(r['no_incluido'])} producto(s) por entregar que no están en el plan: "
                      + ", ".join(f"{a['producto']} ({a['por_planificar']:g})" for a in r["no_incluido"][:6]))
    if r["extendido"]:
        avisos.append("requiere horario extendido: " + ", ".join(f"{f['grupo']} {f['horas_extra_dia']:g} h/día"
                                                                for f in r["extendido"]))
    if avisos:
        alerts.emit("PLAN_REVISION", f"Revise el plan de producción ({r['desde']:%d/%m}–{r['hasta']:%d/%m})",
                    "; ".join(avisos) + ".", "ProductionPlan", f"{r['desde']}:{r['hasta']}",
                    dedup_key=f"PLAN_REV:{r['desde']}:{r['hasta']}:{'|'.join(avisos)[:150]}", creado_por=user)
    return {"materiales": m, "revision": r, "avisos": avisos}


def _horas(r):
    if r.horas:
        return float(r.horas)
    try:
        h1, m1 = (int(x) for x in (r.hora_inicio or "")[:5].split(":"))
        h2, m2 = (int(x) for x in (r.hora_fin or "")[:5].split(":"))
    except ValueError:
        return None
    mins = (h2 * 60 + m2) - (h1 * 60 + m1)
    if mins <= 0:
        mins += 24 * 60
    mins -= (r.refrigerio_min or 0) + (r.parada_min or 0)
    return mins / 60 if mins > 0 else None


def tiempos(desde=None, hasta=None, linea=""):
    """Qué productos toman más y menos tiempo: por producto (y línea), kg procesados, horas, kg por hora y kg por hora y
    operario, con los partes de producción cerrados o en curso."""
    desde = desde or date.today() - timedelta(days=90)
    hasta = hasta or date.today()
    q = select(ProductionReport).where(ProductionReport.fecha >= desde, ProductionReport.fecha <= hasta,
                                       ProductionReport.estado.notin_(("PROGRAMADO", "ANULADO")))
    if linea:
        q = q.where(ProductionReport.linea == linea)
    acc = {}
    for r in db().execute(q).scalars():
        h = _horas(r)
        kg = float(r.peso_entrada_kg or 0)
        if not h or kg <= 0:
            continue
        a = acc.setdefault((r.product_code, r.linea), {"producto": r.product_code, "linea": r.linea, "partes": 0, "kg": 0.0,
                                                       "horas": 0.0, "horas_hombre": 0.0})
        a["partes"] += 1
        a["kg"] += kg
        a["horas"] += h
        a["horas_hombre"] += h * (r.operarios or 1)
    prods = {p.code: p for p in db().execute(select(Product).where(Product.code.in_([k[0] for k in acc] or [""]))).scalars()}
    filas = []
    for a in acc.values():
        a["descripcion"] = prods[a["producto"]].descripcion if a["producto"] in prods else ""
        a["kg_hora"] = round(a["kg"] / a["horas"], 1) if a["horas"] else None
        a["kg_hora_operario"] = round(a["kg"] / a["horas_hombre"], 1) if a["horas_hombre"] else None
        a["min_por_100kg"] = round(60 * a["horas"] / a["kg"] * 100, 1) if a["kg"] else None
        a["kg"], a["horas"] = round(a["kg"], 1), round(a["horas"], 1)
        filas.append(a)
    filas.sort(key=lambda a: (a["kg_hora"] or 0))  # primero los más lentos
    return {"desde": desde, "hasta": hasta, "linea": linea, "filas": filas,
            "lineas": sorted({r for (r,) in db().execute(select(ProductionReport.linea).distinct())})}
