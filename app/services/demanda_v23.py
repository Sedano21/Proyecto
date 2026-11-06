"""V23 (06-nov-2026): análisis de la demanda proyectada para Jefatura de Operaciones, Jefatura Comercial, Jefatura de
Administración y Finanzas y Gerencias, con informe para el Directorio (pantalla, PDF y Excel).

1. Cumplimiento de la demanda por semana (o día/mes) del periodo:
   - proyectado del periodo = proyección del mes × días del periodo ÷ días del mes (por producto);
   - pedido = cantidad de las OV cuya fecha comprometida cae en el periodo (sin anuladas ni borradores);
   - despachado = lo que salió de esas OV;
   - cumplimiento de la demanda = despachado ÷ proyectado; avance del pedido = pedido ÷ proyectado.
2. Comparación del mes proyectado con lo vendido: promedio de los 3 meses anteriores, mismo mes del año anterior y mes
   más alto del año (historial de ventas), por tipo (granel, materia prima, producto terminado, marca blanca).
3. Requerimiento de materiales: explosión de la lista de materiales (producto terminado → materia prima, granel,
   envases, etiquetas y suministros) con el stock, lo que llega en el mes y lo que falta comprar (servicio
   demand_plan.analyze, el mismo de la preprogramación).
4. Carga de trabajo:
   - Producción: kg a producir del mes vs la capacidad real de cada línea (kg/día × días hábiles que quedan). Si no
     alcanza: horas extra = kg sin capacidad ÷ (kg/día ÷ «demanda_jornada_horas»), repartidas en los días hábiles; si
     superan «demanda_horas_extra_max_dia» por día, se recomienda un tercero (maquila) o un turno adicional.
   - Distribución: kg por despachar en lo que queda del mes vs la capacidad de la flota propia (un viaje diario por
     unidad con su capacidad real o el peso permitido, o «distribucion_kg_viaje_ref»). Si no alcanza, se estima cuántos
     viajes de tercero o días con segundo viaje hacen falta.
5. Mensajes clave y puntos a validar, en el estilo del informe de requerimiento para Gerencia.
"""
import calendar as cal
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import DemandForecast, Product, SalesHistory, SalesOrder, Vehicle
from .core import param

EXCLUIDAS = ("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")
SEGMENTOS = ("Granel", "Materia prima", "Producto terminado", "Marca blanca")


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def _kg(p, q):
    if p is None:
        return 0.0
    return q if (p.um or "").upper().startswith("K") else q * (p.peso_kg or 0)


def _mes(d):
    return f"{d:%Y-%m}"


def _mes_rel(mes, k):
    y, m = int(mes[:4]), int(mes[5:7]) + k
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}-{m:02d}"


def _rango_mes(mes):
    y, m = int(mes[:4]), int(mes[5:7])
    return date(y, m, 1), date(y, m, cal.monthrange(y, m)[1])


def segmento(p):
    from .stock import product_kind
    tipo = product_kind(p)
    if tipo == "GR":
        return "Granel"
    if tipo == "MP":
        return "Materia prima"
    propias = {m.strip().upper() for m in (param("marcas_propias", []) or []) if m.strip()}
    marca = ((p.marca if p else "") or "").upper()
    return "Marca blanca" if propias and marca and marca not in propias else "Producto terminado"


def _proyeccion(mes):
    out = defaultdict(float)
    for f in db().execute(select(DemandForecast).where(DemandForecast.mes == mes)).scalars():
        out[f.product_code] += f.cantidad
    return out


def _buckets(desde, hasta, gran):
    """[(etiqueta, ini, fin)] por día, semana (lunes a domingo) o mes."""
    out = []
    d = desde
    while d <= hasta:
        if gran == "DIA":
            fin = d
            et = f"{d:%d/%m}"
        elif gran == "MES":
            fin = min(_rango_mes(_mes(d))[1], hasta)
            et = f"{d:%m/%Y}"
        else:
            fin = min(d + timedelta(days=6 - d.weekday()), hasta)
            et = f"Sem {d:%d/%m}–{fin:%d/%m}"
        out.append((et, d, fin))
        d = fin + timedelta(days=1)
    return out


def cumplimiento(desde, hasta, gran="SEMANA", hoy=None):
    """Proyectado vs pedido vs despachado por periodo y por producto. Los periodos que aún no empiezan no tienen
    cumplimiento (solo el avance del pedido); el total compara lo despachado con lo proyectado hasta hoy."""
    hoy = hoy or date.today()
    s = db()
    prods = {p.code: p for p in s.execute(select(Product)).scalars()}
    proy_mes = {}
    ovs = list(s.execute(select(SalesOrder).where(SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= hasta,
                                                  SalesOrder.estado.notin_(EXCLUIDAS))).scalars())
    filas = []
    por_prod = defaultdict(lambda: {"proy": 0.0, "pedido": 0.0, "desp": 0.0})
    for et, ini, fin in _buckets(desde, hasta, gran):
        proy = defaultdict(float)
        d = ini
        while d <= fin:
            m = _mes(d)
            if m not in proy_mes:
                proy_mes[m] = _proyeccion(m)
            dias = cal.monthrange(d.year, d.month)[1]
            for code, q in proy_mes[m].items():
                proy[code] += q / dias
            d += timedelta(days=1)
        ped, desp = defaultdict(float), defaultdict(float)
        for o in ovs:
            if ini <= o.fecha_compromiso <= fin:
                for l in o.lines:
                    if l.activa:
                        ped[l.product_code] += l.cantidad
                        desp[l.product_code] += min(l.despachado or 0, l.cantidad)
        kg = lambda dct: sum(_kg(prods.get(c), q) for c, q in dct.items())  # noqa: E731
        f = {"periodo": et, "desde": ini, "hasta": fin, "proyectado_kg": round(kg(proy), 1), "pedido_kg": round(kg(ped), 1),
             "despachado_kg": round(kg(desp), 1)}
        f["avance_pedido"] = _pct(f["pedido_kg"], f["proyectado_kg"])
        if ini > hoy:
            f["estado"], f["cumplimiento"], f["proyectado_a_hoy_kg"] = "Por venir", None, 0.0
        else:
            transc = ((min(fin, hoy) - ini).days + 1) / ((fin - ini).days + 1)
            f["proyectado_a_hoy_kg"] = round(f["proyectado_kg"] * transc, 1)
            f["estado"] = "Cerrado" if fin < hoy else "En curso"
            f["cumplimiento"] = _pct(f["despachado_kg"], f["proyectado_a_hoy_kg"])
        filas.append(f)
        for c in set(proy) | set(ped):
            por_prod[c]["proy"] += proy.get(c, 0)
            por_prod[c]["pedido"] += ped.get(c, 0)
            por_prod[c]["desp"] += desp.get(c, 0)
    productos = []
    for c, x in por_prod.items():
        p = prods.get(c)
        productos.append({"code": c, "descripcion": p.descripcion if p else "", "segmento": segmento(p) if p else "",
                          "proyectado": round(x["proy"], 1), "pedido": round(x["pedido"], 1), "despachado": round(x["desp"], 1),
                          "proyectado_kg": round(_kg(p, x["proy"]), 1), "despachado_kg": round(_kg(p, x["desp"]), 1),
                          "cumplimiento": _pct(x["desp"], x["proy"]), "brecha": round(x["proy"] - x["desp"], 1)})
    productos.sort(key=lambda r: (r["cumplimiento"] if r["cumplimiento"] is not None else 999))
    tot = {k: round(sum(f[k] for f in filas), 1) for k in ("proyectado_kg", "pedido_kg", "despachado_kg")}
    tot["proyectado_a_hoy_kg"] = round(sum(f["proyectado_a_hoy_kg"] for f in filas), 1)
    tot["cumplimiento"] = _pct(tot["despachado_kg"], tot["proyectado_a_hoy_kg"])
    tot["cumplimiento_mes"] = _pct(tot["despachado_kg"], tot["proyectado_kg"])
    tot["avance_pedido"] = _pct(tot["pedido_kg"], tot["proyectado_kg"])
    return {"filas": filas, "productos": productos, "total": tot}


def comparativo(mes):
    """Proyección del mes por tipo vs prom. 3 meses anteriores, mismo mes del año anterior y mes más alto del año."""
    s = db()
    prods = {p.code: p for p in s.execute(select(Product)).scalars()}
    proy = _proyeccion(mes)
    ini_hist, _ = _rango_mes(_mes_rel(mes, -12))
    fin_hist = _rango_mes(_mes_rel(mes, -1))[1]
    ventas = defaultdict(lambda: defaultdict(float))  # mes -> segmento -> kg
    for h in s.execute(select(SalesHistory).where(SalesHistory.fecha >= ini_hist, SalesHistory.fecha <= fin_hist)).scalars():
        p = prods.get(h.product_code)
        ventas[_mes(h.fecha)][segmento(p) if p else "Producto terminado"] += _kg(p, h.cantidad)
    m3 = [_mes_rel(mes, -k) for k in (1, 2, 3)]
    m12 = _mes_rel(mes, -12)
    seg_proy = defaultdict(float)
    n_sku = defaultdict(int)
    for c, q in proy.items():
        p = prods.get(c)
        sg = segmento(p) if p else "Producto terminado"
        seg_proy[sg] += _kg(p, q)
        n_sku[sg] += 1
    filas = []
    for sg in SEGMENTOS:
        prom3 = sum(ventas[m][sg] for m in m3) / 3
        f = {"segmento": sg, "sku": n_sku[sg], "proyectado_kg": round(seg_proy[sg], 1), "prom3_kg": round(prom3, 1),
             "anio_ant_kg": round(ventas[m12][sg], 1)}
        f["var_prom3"] = _pct(f["proyectado_kg"] - prom3, prom3)
        f["var_anio"] = _pct(f["proyectado_kg"] - f["anio_ant_kg"], f["anio_ant_kg"])
        if f["proyectado_kg"] or prom3:
            filas.append(f)
    total = sum(seg_proy.values())
    prom3 = sum(sum(ventas[m].values()) for m in m3) / 3
    anio = sum(ventas[m12].values())
    meses = [(m, sum(v.values())) for m, v in ventas.items()]
    maximo = max(meses, key=lambda x: x[1]) if meses else (None, 0)
    for f in filas:
        f["pct"] = _pct(f["proyectado_kg"], total)
    top = sorted(((c, prods.get(c), q) for c, q in proy.items()), key=lambda x: -_kg(x[1], x[2]))[:10]
    return {"mes": mes, "total_kg": round(total, 1), "sku": len(proy), "prom3_kg": round(prom3, 1),
            "var_prom3": _pct(total - prom3, prom3), "anio_ant_kg": round(anio, 1), "var_anio": _pct(total - anio, anio),
            "max_mes": maximo[0], "max_kg": round(maximo[1], 1), "filas": filas,
            "top": [{"code": c, "descripcion": p.descripcion if p else "", "segmento": segmento(p) if p else "",
                     "cantidad": round(q, 1), "kg": round(_kg(p, q), 1)} for c, p, q in top]}


def requerimiento(mes, hoy=None):
    """Explosión de la lista de materiales con stock, llegadas y faltantes, agrupada por tipo de ítem."""
    from .demand_plan import analyze
    a = analyze(mes, hoy)
    prods = {p.code: p for p in db().execute(select(Product)).scalars()}

    def tipo(code):
        p = prods.get(code)
        c = code.upper()
        if c.startswith("GR"):
            return "Granel"
        if c.startswith("MP"):
            return "Materia prima"
        if c.startswith("EN"):
            return "Envase / lámina"
        if c.startswith(("SU", "ET")):
            return "Suministro / etiqueta"
        if c.startswith("RE"):
            return "Otros insumos"
        return segmento(p) if p else "Otros"
    grupos = defaultdict(lambda: {"items": 0, "requerido": 0.0, "faltante": 0.0})
    for x in a["presolicitudes"]:
        g = grupos[tipo(x["code"])]
        g["items"] += 1
        g["requerido"] += x["requerido"]
        g["faltante"] += x["faltante"]
    return {"analisis": a, "por_tipo": [dict(tipo=k, **{kk: round(vv, 1) if isinstance(vv, float) else vv for kk, vv in v.items()})
                                        for k, v in sorted(grupos.items())],
            "a_producir": [f for f in a["filas"] if f.get("a_producir")],
            "unidades_a_producir": round(sum(f["a_producir"] for f in a["filas"]), 1),
            "faltantes": sorted(a["presolicitudes"], key=lambda x: -x["faltante"])[:20]}


def _habiles_restantes(desde, hasta):
    from .calendar import day_factor, holidays
    fer = holidays()
    return sum(day_factor(d, fer) for d in (desde + timedelta(days=i) for i in range((hasta - desde).days + 1)))


def carga_produccion(req, hoy):
    jornada = float(param("demanda_jornada_horas", 8) or 8)
    max_extra = float(param("demanda_horas_extra_max_dia", 2) or 0)
    a = req["analisis"]
    dias = _habiles_restantes(a["necesidad"], a["fin"]) or 1
    from .demand_plan import _cap_linea
    cap = _cap_linea()
    lineas = []
    for u in a["uso_lineas"]:
        l = u["linea"]
        kg_dia = cap.get(l, 0)
        kg_asig = sum(p["kg_programable"] for p in a["programa"] if p["linea"] == l)
        kg_sin = sum(p["kg_sin_capacidad"] for p in a["programa"] if p["linea"] == l)
        horas_extra = kg_sin / (kg_dia / jornada) if kg_dia else 0
        por_dia = horas_extra / dias if dias else 0
        reco = ("Capacidad suficiente" if not kg_sin else
                f"Extender jornada {por_dia:.1f} h/día" if por_dia <= max_extra else
                "Tercero (maquila) o turno adicional: las horas extra superan el máximo diario")
        lineas.append({"linea": l, "kg_dia": round(kg_dia), "kg_asignado": round(kg_asig), "kg_sin_capacidad": round(kg_sin),
                       "uso_pct": u["uso_pct"], "horas_extra": round(horas_extra, 1), "horas_extra_dia": round(por_dia, 1),
                       "recomendacion": reco})
    # V23: si otra línea del mismo proceso tiene holgura, primero se recomienda pasar allí la producción
    proceso = {}
    for gq in param("capacidad_lineas", []) or []:
        for ln in gq.get("lineas") or []:
            proceso[ln] = gq.get("proceso")
    for l in lineas:
        if not l["kg_sin_capacidad"]:
            continue
        hol = [(o["linea"], o["kg_dia"] * dias - o["kg_asignado"]) for o in lineas
               if o is not l and proceso.get(o["linea"]) == proceso.get(l["linea"]) and not o["kg_sin_capacidad"]]
        hol = [(n, k) for n, k in hol if k > 0]
        if hol:
            n, k = max(hol, key=lambda x: x[1])
            mover = min(k, l["kg_sin_capacidad"])
            l["recomendacion"] = (f"Pasar {mover:,.0f} kg a {n} (tiene holgura)" +
                                  ("" if mover >= l["kg_sin_capacidad"] else f"; el resto: {l['recomendacion'].lower()}"))
    kg_total = sum(p["kg"] for p in a["programa"])
    return {"dias_habiles": round(dias, 1), "kg_a_producir": round(kg_total), "kg_sin_capacidad": a["kg_deficit"],
            "lineas": lineas, "jornada": jornada, "max_extra": max_extra,
            "deficit": a["deficit"]}


def carga_distribucion(mes, hoy):
    """kg por despachar en lo que queda del mes (proyección restante y OV abiertas, lo mayor) vs flota propia."""
    s = db()
    ini, fin = _rango_mes(mes)
    desde = max(ini, hoy)
    dias = _habiles_restantes(desde, fin) or 1
    prods = {p.code: p for p in s.execute(select(Product)).scalars()}
    proy = _proyeccion(mes)
    dias_mes = (fin - ini).days + 1
    restante_proy = sum(_kg(prods.get(c), q) for c, q in proy.items()) * ((fin - desde).days + 1) / dias_mes
    abiertas = 0.0
    for o in s.execute(select(SalesOrder).where(SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= fin,
                                                SalesOrder.estado.notin_(EXCLUIDAS), SalesOrder.salida_ts.is_(None))).scalars():
        abiertas += sum(_kg(l.product, l.cantidad) for l in o.lines if l.activa)
    kg = max(restante_proy, abiertas)
    ref = param("distribucion_kg_viaje_ref", {}) or {}
    flota = []
    for v in s.execute(select(Vehicle).where(Vehicle.propio.is_(True))).scalars():
        if getattr(v, "disponible", True) is False:
            continue
        c = float(ref.get(v.placa) or v.capacidad_real_kg or v.capacidad_kg or 0)
        if c:
            flota.append((v.placa, c))
    cap_dia = sum(c for _, c in flota)
    cap = cap_dia * dias
    falta = max(kg - cap, 0)
    viaje_tercero = float(param("distribucion_kg_viaje_tercero", 2000) or 2000)
    reco = ("La flota propia cubre la carga proyectada" if not falta else
            f"Faltan {falta:,.0f} kg: ~{falta / viaje_tercero:.0f} viajes de tercero de {viaje_tercero:,.0f} kg o "
            f"{falta / cap_dia:.1f} días con segundo viaje de toda la flota" if cap_dia else
            "Sin flota propia con capacidad registrada")
    return {"dias_habiles": round(dias, 1), "kg_proyeccion_restante": round(restante_proy), "kg_ov_abiertas": round(abiertas),
            "kg_por_despachar": round(kg), "flota": flota, "capacidad_dia": round(cap_dia), "capacidad_periodo": round(cap),
            "uso_pct": _pct(kg, cap), "faltante_kg": round(falta), "recomendacion": reco}


def informe(mes=None, desde=None, hasta=None, gran="SEMANA", hoy=None):
    hoy = hoy or date.today()
    mes = mes or _mes(hoy)
    ini, fin = _rango_mes(mes)
    desde = desde or ini
    hasta = hasta or fin
    comp = comparativo(mes)
    cum = cumplimiento(desde, hasta, gran, hoy)
    req = requerimiento(mes, hoy)
    prod = carga_produccion(req, hoy)
    dist = carga_distribucion(mes, hoy)
    mensajes, validar = [], []
    if comp["total_kg"]:
        mensajes.append(f"Comercial proyecta {comp['total_kg']:,.0f} kg para {mes} ({comp['sku']} SKU)"
                        + (f", {comp['var_prom3']:+.0f} % frente al promedio de los 3 meses anteriores" if comp["var_prom3"] is not None else "")
                        + (f" y {comp['var_anio']:+.0f} % frente al mismo mes del año anterior." if comp["var_anio"] is not None else "."))
    else:
        mensajes.append(f"No hay proyección de demanda cargada para {mes}: Comercial debe registrarla para planificar.")
    if cum["total"]["cumplimiento"] is not None:
        mensajes.append(f"Cumplimiento de la demanda a la fecha: {cum['total']['cumplimiento']} % (despachado "
                        f"{cum['total']['despachado_kg']:,.0f} kg de {cum['total']['proyectado_a_hoy_kg']:,.0f} kg proyectados hasta hoy); "
                        f"del periodo completo va {cum['total']['cumplimiento_mes'] or 0} % y los pedidos cubren "
                        f"{cum['total']['avance_pedido'] or 0} % de lo proyectado.")
    if req["faltantes"]:
        falt = sum(x["faltante"] for x in req["faltantes"])
        venc = [x for x in req["faltantes"] if x["vencida"]]
        mensajes.append(f"Faltan comprar {len(req['analisis']['presolicitudes'])} ítems de materia prima, granel e insumos "
                        f"(los 20 mayores suman {falt:,.0f} en su unidad)" + (f"; {len(venc)} ya pasaron su fecha máxima de pedido."
                                                                              if venc else "."))
    if prod["kg_sin_capacidad"]:
        mensajes.append(f"Producción no alcanza con la capacidad actual: {prod['kg_sin_capacidad']:,.0f} kg sin capacidad en el mes. "
                        + "; ".join(f"{l['linea']}: {l['recomendacion']}" for l in prod["lineas"] if l["kg_sin_capacidad"]))
    else:
        mensajes.append(f"Producción: la capacidad de las líneas cubre los {prod['kg_a_producir']:,.0f} kg a producir.")
    mensajes.append(f"Distribución: {dist['kg_por_despachar']:,.0f} kg por despachar en {dist['dias_habiles']:g} días hábiles "
                    f"(uso de la flota propia {dist['uso_pct'] or 0} %). {dist['recomendacion']}.")
    for f in comp["filas"]:
        if f["var_prom3"] is not None and abs(f["var_prom3"]) >= 50:
            validar.append(("Crecimiento fuerte" if f["var_prom3"] > 0 else "Caída fuerte",
                            f"{f['segmento']}: {f['var_prom3']:+.0f} % vs promedio de 3 meses. Comercial debe sustentar el volumen "
                            "y Producción confirmar capacidad antes de comprometer compras."))
    sin_bom = [f["code"] for f in req["analisis"]["filas"] if f["tipo"] == "PT" and f.get("a_producir") and
               not any(p["code"] == f["code"] for p in req["analisis"]["programa"])]
    if sin_bom:
        validar.append(("Lista de materiales", f"Sin lista de materiales o sin línea: {', '.join(sin_bom[:8])}."))
    sin_plazo = [x["code"] for x in req["analisis"]["presolicitudes"] if x["sin_plazo"]]
    if sin_plazo:
        validar.append(("Plazos de reposición", f"{len(sin_plazo)} ítem(s) sin tiempo de reposición configurado: "
                        + ", ".join(sin_plazo[:8]) + "."))
    pasos = ["Inventario: confirmar el stock contado; la necesidad neta y lo que falta comprar se recalculan solos.",
             "Comercial: sustentar las variaciones fuertes y actualizar la proyección si cambia.",
             "Producción: validar la capacidad por línea y programar horas extra o tercero donde se indica.",
             "Compras e Importaciones: emitir órdenes priorizando los ítems con fecha máxima de pedido más próxima.",
             "Distribución: reservar transporte tercero o segundos viajes si la flota propia no cubre la carga."]
    return {"mes": mes, "desde": desde, "hasta": hasta, "gran": gran, "hoy": hoy, "comparativo": comp, "cumplimiento": cum,
            "requerimiento": req, "produccion": prod, "distribucion": dist, "mensajes": mensajes, "validar": validar,
            "pasos": pasos}
