"""Informes con indicadores, tendencias y recomendaciones (observaciones al demo v0.5, 13-oct).

Cada informe trabaja sobre un periodo (desde/hasta) y devuelve: indicadores (KPI), series para gráficos, tablas y
recomendaciones automáticas. Las recomendaciones son reglas explícitas (umbral configurable) y se presentan como
sugerencias para revisión, no como decisiones.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean

from sqlalchemy import select

from ..db import db
from ..models import AuditLog, Product, SalesOrder, User
from .core import param

CERRADAS = ("DESPACHADA", "ENTREGADA")


def periodo(desde=None, hasta=None, dias=90):
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=dias)
    return desde, hasta


def semana(d):
    lunes = d - timedelta(days=d.weekday())
    return lunes


def _pct(a, b):
    return round(a / b * 100, 1) if b else None


def _var(serie):
    """Variación % entre la segunda mitad y la primera mitad de una serie de valores."""
    if len(serie) < 4:
        return None
    m = len(serie) // 2
    a, b = sum(serie[:m]) / m, sum(serie[m:]) / (len(serie) - m)
    return round((b - a) / a * 100, 1) if a else None


# ------------------------------------------------------------------ comercial
def order_channel(o):
    from .prices import channel_of
    return o.canal_precio or channel_of(o.customer) or ""


def filter_orders(ovs, canal="", customer_id=None, vendedor=""):
    """Filtros de los informes comerciales (ronda 23-oct-2026): canal, cliente y vendedor."""
    if canal:
        ovs = [o for o in ovs if order_channel(o) == canal]
    if customer_id:
        ovs = [o for o in ovs if o.customer_id == int(customer_id)]
    if vendedor:
        ovs = [o for o in ovs if (o.vendedor_nombre or "(sin vendedor)") == vendedor or str(o.vendedor_id or "") == str(vendedor)]
    return ovs


def line_kind(product):
    """GRANEL (se vende por kilos) o ENVASADO (por unidades), según el prefijo del código."""
    from .orders import unit_for
    return "GRANEL" if product is not None and unit_for(product) == "KG" else "ENVASADO"


def comercial(desde=None, hasta=None, ver_costos=False, canal="", customer_id=None, vendedor="", tipo=""):
    from .costs import cost_for_line
    from .orders import order_amount
    desde, hasta = periodo(desde, hasta)
    s = db()
    todas = filter_orders([o for o in s.execute(select(SalesOrder).where(SalesOrder.fecha_emision >= desde,
                                                                         SalesOrder.fecha_emision <= hasta)).scalars()
                           if o.estado != "BORRADOR"], canal, customer_id, vendedor)
    # venta real: OV abiertas y cerradas; las canceladas se muestran aparte con su motivo (ronda 23-oct-2026)
    ovs = [o for o in todas if o.estado != "CANCELADA"]
    canceladas = [o for o in todas if o.estado == "CANCELADA"]
    prod_kg = defaultdict(float)
    vend = defaultdict(lambda: {"soles": 0.0, "kg": 0.0, "ovs": 0})
    sem = defaultdict(float)
    prod_soles, prod_qty, pres = defaultdict(float), defaultdict(float), Counter()
    cli = defaultdict(lambda: {"soles": 0.0, "ovs": 0, "fechas": []})
    marg_prod = defaultdict(lambda: [0.0, 0.0])  # ventas, costo (solo líneas con costo)
    inc_qty = inc_soles = 0.0
    inc_ovs = 0
    def _lineas(o):
        return [l for l in o.lines if l.activa and (not tipo or line_kind(l.product) == tipo)]

    def _monto(o):
        return sum(l.cantidad * (l.precio_unitario or 0) for l in _lineas(o)) if tipo else order_amount(o)
    if tipo:
        ovs = [o for o in ovs if _lineas(o)]
    for o in ovs:
        monto = _monto(o)
        v = vend[o.vendedor_nombre or "(sin vendedor)"]
        v["soles"] += monto
        v["ovs"] += 1
        sem[semana(o.fecha_emision)] += monto
        c = cli[o.customer.nombre]
        c["soles"] += monto
        c["ovs"] += 1
        c["fechas"].append(o.fecha_emision)
        incompleta = False
        for l in _lineas(o):
            p = l.product
            kg = l.cantidad * (p.peso_kg or (1 if (p.um or "").upper().startswith("K") else 0)) if p else 0
            v["kg"] += kg
            prod_kg[l.product_code] += kg
            venta = l.cantidad * (l.precio_unitario or 0)
            prod_soles[l.product_code] += venta
            prod_qty[l.product_code] += l.cantidad
            pres[(p.presentacion or p.um or "-") if p else "-"] += l.cantidad
            costo = cost_for_line(l)
            if costo is not None and venta:
                marg_prod[l.product_code][0] += venta
                marg_prod[l.product_code][1] += costo * l.cantidad
            if o.estado in CERRADAS and l.despachado + 1e-9 < l.cantidad:
                falta = l.cantidad - l.despachado
                inc_qty += falta
                inc_soles += falta * (l.precio_unitario or 0)
                incompleta = True
        inc_ovs += incompleta
    pendientes = [o for o in s.execute(select(SalesOrder).where(SalesOrder.estado.not_in(("ENTREGADA", "CANCELADA"))))
                  .scalars()]
    # modificaciones de OV y su desviación (cantidad y soles) según la auditoría
    mods = list(s.execute(select(AuditLog).where(AuditLog.accion == "OV_MODIFICADA",
                                                 AuditLog.ts >= desde, AuditLog.ts < hasta + timedelta(days=1))).scalars())
    ov_mod = {m.entidad_id for m in mods}
    dq = dsoles = base_q = base_s = 0.0
    for m in mods:
        antes = {x["producto"]: x for x in (m.detalle or {}).get("antes", {}).get("lineas", [])}
        despues = {x["producto"]: x for x in (m.detalle or {}).get("despues", {}).get("lineas", [])}
        for k in set(antes) | set(despues):
            a, d = antes.get(k, {}), despues.get(k, {})
            qa, qd = a.get("cantidad", 0) or 0, d.get("cantidad", 0) or 0
            pa, pd = a.get("precio", d.get("precio", 0)) or 0, d.get("precio", a.get("precio", 0)) or 0
            dq += abs(qd - qa)
            dsoles += abs(qd * pd - qa * pa)
            base_q += qa
            base_s += qa * pa
    total_soles = sum(v["soles"] for v in vend.values())
    margen = {k: (vt - ct) / vt * 100 for k, (vt, ct) in marg_prod.items() if vt}
    margen_prom = ((sum(v for v, _ in marg_prod.values()) - sum(c for _, c in marg_prod.values()))
                   / sum(v for v, _ in marg_prod.values()) * 100) if marg_prod else None
    semanas = sorted(sem)
    serie_sem = [(f"{d:%d/%m}", round(sem[d], 2)) for d in semanas]
    # comportamiento de compra por cliente
    clientes = []
    for nombre, c in cli.items():
        f = sorted(c["fechas"])
        gaps = [(b - a).days for a, b in zip(f, f[1:])]
        frec = mean(gaps) if gaps else None
        dias_sin = (hasta - f[-1]).days
        riesgo = bool(frec and dias_sin > 2 * frec)
        clientes.append({"nombre": nombre, "soles": c["soles"], "ovs": c["ovs"], "frecuencia": round(frec, 1) if frec else None,
                         "ticket": round(c["soles"] / c["ovs"], 2) if c["ovs"] else 0,
                         "ultima": f[-1], "dias_sin_compra": dias_sin, "riesgo": riesgo})
    clientes.sort(key=lambda x: -x["soles"])
    nombres = {p.code: p.descripcion for p in s.execute(select(Product).where(Product.code.in_(list(prod_soles) or [""]))).scalars()}
    top = sorted(prod_soles.items(), key=lambda x: -x[1])[:15]
    top_kg = sorted(prod_kg.items(), key=lambda x: -x[1])[:15]
    nombres.update({p.code: p.descripcion for p in s.execute(select(Product).where(Product.code.in_(list(prod_kg) or [""]))).scalars()})
    motivos = Counter((o.cancelacion_motivo or o.motivo_detencion.replace("Cancelada: ", "") or "(sin motivo)") for o in canceladas)
    reco = []
    var_sem = _var([v for _, v in serie_sem])
    if var_sem is not None and var_sem <= -10:
        reco.append(f"Las ventas semanales caen {var_sem:+.1f} % (segunda mitad vs primera mitad del periodo): revisar cartera y clientes en riesgo.")
    elif var_sem is not None and var_sem >= 10:
        reco.append(f"Las ventas semanales crecen {var_sem:+.1f} %: asegurar stock y capacidad de producción para los productos líderes.")
    riesgo = [c["nombre"] for c in clientes if c["riesgo"]]
    if riesgo:
        reco.append(f"{len(riesgo)} cliente(s) superan el doble de su frecuencia habitual sin comprar: {', '.join(riesgo[:5])}.")
    umbral_m = float(param("margen_minimo_reporte_pct", 10) or 10)
    bajos = [k for k, m in margen.items() if m < umbral_m]
    if ver_costos and bajos:
        reco.append(f"{len(bajos)} producto(s) con margen menor a {umbral_m:g} %: {', '.join(bajos[:6])}. Revisar precio mínimo o costo.")
    if ovs and inc_ovs / len(ovs) > 0.05:
        reco.append(f"{_pct(inc_ovs, len(ovs))} % de las OV se entregaron incompletas (S/ {inc_soles:,.0f}): revisar faltantes y reposición.")
    if ovs and len(ov_mod) / len(ovs) > 0.15:
        reco.append(f"{_pct(len(ov_mod), len(ovs))} % de las OV fueron modificadas: revisar la toma de pedidos con los ejecutivos.")
    return {
        "desde": desde, "hasta": hasta, "ovs": len(ovs), "soles": total_soles,
        "kg": sum(v["kg"] for v in vend.values()),
        "vendedores": sorted(vend.items(), key=lambda x: -x[1]["soles"]),
        "serie_semanal": serie_sem, "var_semanal": var_sem,
        "top_productos": [(k, nombres.get(k, ""), v, prod_qty[k]) for k, v in top],
        "top_kg": [(k, nombres.get(k, ""), v, prod_soles.get(k, 0)) for k, v in top_kg],
        "canceladas": {"ovs": len(canceladas), "soles": round(sum(order_amount(o) for o in canceladas), 2),
                       "pct": _pct(len(canceladas), len(todas)), "motivos": motivos.most_common(10)},
        "filtros": {"canal": canal, "customer_id": customer_id, "vendedor": vendedor, "tipo": tipo},
        "presentaciones": pres.most_common(10),
        "clientes": clientes[:30],
        "margen_promedio": round(margen_prom, 1) if margen_prom is not None and ver_costos else None,
        "margen_producto": sorted(((k, nombres.get(k, ""), round(m, 1)) for k, m in margen.items()), key=lambda x: x[2])
        if ver_costos else [],
        "incompletas": {"ovs": inc_ovs, "unidades": inc_qty, "soles": inc_soles},
        "pendientes": len(pendientes),
        "pendientes_vencidas": len([o for o in pendientes if o.fecha_compromiso < date.today()]),
        "modificadas": {"ovs": len(ov_mod), "pct": _pct(len(ov_mod), len(ovs)), "eventos": len(mods),
                        "desv_cantidad_pct": _pct(dq, base_q), "desv_soles_pct": _pct(dsoles, base_s),
                        "desv_cantidad": dq, "desv_soles": dsoles},
        "recomendaciones": reco,
    }


# ------------------------------------------------------------------ reempaque
def _horas(a, b):
    return (b - a).total_seconds() / 3600 if a and b else None


def reempaque(desde=None, hasta=None):
    """Evolución de solicitudes de reempaque, tasas de aprobación/desestimación, motivos y tiempos de respuesta
    (Almacén, Calidad y Comercial)."""
    from ..catalogs import REPACK_TYPES
    from ..models import OVDecision, RepackRequest
    desde, hasta = periodo(desde, hasta)
    s = db()
    rows = [r for r in s.execute(select(RepackRequest).order_by(RepackRequest.ts)).scalars()
            if desde <= r.ts.date() <= hasta]
    tipos = dict((k, n) for k, n, _ in REPACK_TYPES)
    por_estado = Counter(r.estado for r in rows)
    por_tipo = Counter(tipos.get(r.tipo, r.tipo) for r in rows)
    evaluadas = [r for r in rows if r.estado not in ("PRE_SOLICITUD", "SOLICITADA", "DESESTIMADA")]
    aprobadas = [r for r in evaluadas if r.estado != "DESAPROBADA"]
    # semanas: solicitudes y tasa de aprobación
    sem_n, sem_ok, sem_ev = defaultdict(int), defaultdict(int), defaultdict(int)
    for r in rows:
        w = semana(r.ts.date())
        sem_n[w] += 1
        if r.estado not in ("PRE_SOLICITUD", "SOLICITADA", "DESESTIMADA"):
            sem_ev[w] += 1
            sem_ok[w] += r.estado != "DESAPROBADA"
    semanas = sorted(sem_n)
    # motivos de desaprobación (Calidad) y desestimación (Almacén)
    motivos = Counter()
    for r in rows:
        if r.estado == "DESAPROBADA":
            motivos[("Calidad: " + (r.resultado_calidad or "sin detalle").strip().split("\n")[0])[:90]] += 1
        elif r.estado == "DESESTIMADA":
            m = [x for x in (r.motivo or "").split("\n") if x.startswith("Desestimada:")]
            motivos[("Almacén: " + (m[-1][12:].strip() if m else "sin detalle"))[:90]] += 1
    # tiempos de respuesta
    audits = {}
    for a in s.execute(select(AuditLog).where(AuditLog.entidad == "RepackRequest",
                                              AuditLog.accion.like("REEMPAQUE_PRESOLICITUD%"))).scalars():
        audits.setdefault(str(a.entidad_id), a.ts)
    t_alm = [h for r in rows if (h := _horas(r.ts, audits.get(str(r.id)))) is not None]
    t_cal = [h for r in rows if r.evaluado_ts and (h := _horas(audits.get(str(r.id)) or r.ts, r.evaluado_ts)) is not None]
    # Comercial: desde que la OV queda con faltante hasta la primera decisión comercial registrada
    t_com = []
    for oid in {r.order_id for r in rows if r.order_id}:
        o = s.get(SalesOrder, oid)
        dec = s.execute(select(OVDecision).where(OVDecision.order_id == oid).order_by(OVDecision.ts)).scalars().first()
        if o and o.evaluado_ts and dec and dec.ts >= o.evaluado_ts:
            t_com.append(_horas(o.evaluado_ts, dec.ts))
    tasa_ap = _pct(len(aprobadas), len(evaluadas))
    tasa_des = _pct(por_estado.get("DESESTIMADA", 0), len(rows))
    reco = []
    if tasa_ap is not None and tasa_ap < 70:
        reco.append(f"Solo {tasa_ap} % de los reempaques evaluados se aprueban: revisar los motivos de Calidad y la "
                    "selección de lotes candidatos antes de solicitar.")
    if tasa_des and tasa_des > 30:
        reco.append(f"{tasa_des} % de las solicitudes se desestiman: ajustar los criterios de la pre-solicitud automática.")
    if t_cal and mean(t_cal) > 24:
        reco.append(f"Calidad responde en {mean(t_cal):.1f} h promedio: programar el muestreo de reempaques el mismo día.")
    if t_com and mean(t_com) > 24:
        reco.append(f"Comercial tarda {mean(t_com):.1f} h promedio en decidir ante faltantes: acordar un plazo máximo de respuesta.")
    if motivos:
        m, n = motivos.most_common(1)[0]
        reco.append(f"Motivo más frecuente ({n}): {m}.")
    return {"desde": desde, "hasta": hasta, "total": len(rows), "por_estado": dict(por_estado), "por_tipo": por_tipo.most_common(),
            "tasa_aprobacion": tasa_ap, "tasa_desestimacion": tasa_des, "evaluadas": len(evaluadas),
            "serie_solicitudes": [(f"{w:%d/%m}", sem_n[w]) for w in semanas],
            "serie_aprobacion": [(f"{w:%d/%m}", _pct(sem_ok[w], sem_ev[w])) for w in semanas],
            "motivos": motivos.most_common(10),
            "t_almacen": round(mean(t_alm), 1) if t_alm else None, "t_calidad": round(mean(t_cal), 1) if t_cal else None,
            "t_comercial": round(mean(t_com), 1) if t_com else None, "n_comercial": len(t_com),
            "filas": list(reversed(rows))[:50], "tipos": tipos, "recomendaciones": reco}


# ------------------------------------------------------------------ producción
def produccion(desde=None, hasta=None):
    """Cuánto se produjo por día/periodo (liquidaciones y partes), rendimiento y desmedro por línea, cumplimiento del
    plan y merma proyectada vs ejecutada."""
    from ..models import Liquidation, ProductionReport
    from .production import is_desmedro, merma_comparison, plan_vs_real
    desde, hasta = periodo(desde, hasta, dias=30)
    s = db()
    liqs = [l for l in s.execute(select(Liquidation).where(Liquidation.fecha >= desde, Liquidation.fecha <= hasta)).scalars()
            if not is_desmedro(l.product_code)]
    partes = list(s.execute(select(ProductionReport).where(ProductionReport.fecha >= desde, ProductionReport.fecha <= hasta,
                                                           ProductionReport.estado != "PROGRAMADO")).scalars())
    programados = list(s.execute(select(ProductionReport).where(ProductionReport.fecha >= desde, ProductionReport.fecha <= hasta,
                                                                ProductionReport.estado == "PROGRAMADO")).scalars())
    dia_kg, dia_und = defaultdict(float), defaultdict(float)
    prod = defaultdict(lambda: [0.0, 0.0])
    for l in liqs:
        p = l.product
        kg = l.cantidad_completada * (p.peso_kg or (1 if p and (p.um or "").upper().startswith("K") else 0)) if p else 0
        dia_kg[l.fecha] += kg
        dia_und[l.fecha] += l.cantidad_completada
        prod[l.product_code][0] += l.cantidad_completada
        prod[l.product_code][1] += kg
    lineas = defaultdict(lambda: {"entrada": 0.0, "salida": 0.0, "desmedro": 0.0, "partes": 0, "horas": 0.0})
    for r in partes:
        x = lineas[r.linea]
        x["entrada"] += r.peso_entrada_kg
        x["salida"] += r.granel_kg or 0
        x["desmedro"] += (r.desmedro_pct or 0) * r.peso_entrada_kg / 100
        x["partes"] += 1
        x["horas"] += r.horas or 0
    lin = [{"linea": k, **v, "rend": _pct(v["salida"], v["entrada"]), "desm": _pct(v["desmedro"], v["entrada"]),
            "kg_hora": round(v["salida"] / v["horas"], 1) if v["horas"] else None} for k, v in sorted(lineas.items())]
    dias = sorted(set(dia_kg))
    plan = plan_vs_real("DIA", desde, hasta)
    merma = merma_comparison(desde, hasta)
    fuera = [m for m in merma if m["fuera"]]
    reco = []
    if plan["tasa"] is not None and plan["tasa"] < 90:
        reco.append(f"Cumplimiento del plan diario {plan['tasa']} %: revisar capacidad, abastecimiento de materiales y paradas.")
    sin_plan = [f for f in plan["filas"] if f["sin_plan"]]
    if sin_plan:
        reco.append(f"{len(sin_plan)} producción(es) sin plan registrado: ingresar el planeamiento para medir el cumplimiento.")
    if fuera:
        reco.append(f"{len(fuera)} liquidación(es) con merma ejecutada fuera de la proyectada (± tolerancia): "
                    + ", ".join(f"{m['liq'].numero_documento} ({m['desviacion']:+.1f} pp)" for m in fuera[:5]) + ".")
    peor = max(lin, key=lambda x: x["desm"] or 0) if lin else None
    if peor and peor["desm"] and peor["desm"] > float(param("umbral_merma_pct", 5) or 5):
        reco.append(f"La línea {peor['linea']} tiene el mayor desmedro ({peor['desm']} %): revisar calibración y materia prima.")
    if programados:
        reco.append(f"{len(programados)} parte(s) programado(s) sin completar en el periodo.")
    return {"desde": desde, "hasta": hasta, "unidades": sum(dia_und.values()), "kg": sum(dia_kg.values()),
            "liquidaciones": len(liqs), "serie_kg": [(f"{d:%d/%m}", round(dia_kg[d], 1)) for d in dias],
            "serie_und": [(f"{d:%d/%m}", dia_und[d]) for d in dias],
            "productos": sorted(((k, v[0], v[1]) for k, v in prod.items()), key=lambda x: -x[2])[:15],
            "lineas": lin, "plan": plan, "merma": merma[:40], "programados": programados, "recomendaciones": reco}


# ------------------------------------------------------------------ distribución
def distribucion(desde=None, hasta=None):
    """Rutas con transporte propio vs externo (con su validación), carga y pedidos, incidencias por tipo y subtipo."""
    from ..models import Incident, Route
    from .catalogs_helpers import incident_group_name, incident_type_name
    desde, hasta = periodo(desde, hasta, dias=30)
    s = db()
    rutas = [r for r in s.execute(select(Route).where(Route.fecha >= desde, Route.fecha <= hasta, Route.estado != "ANULADA")).scalars()]
    tot = {"PROPIO": {"rutas": 0, "kg": 0.0, "pedidos": 0}, "EXTERNO": {"rutas": 0, "kg": 0.0, "pedidos": 0}}
    sem = defaultdict(lambda: {"PROPIO": 0, "EXTERNO": 0})
    sin_validar, rechazadas = [], 0
    for r in rutas:
        k = "EXTERNO" if r.requiere_externo else "PROPIO"
        tot[k]["rutas"] += 1
        tot[k]["kg"] += r.peso_total or 0
        tot[k]["pedidos"] += len(r.stops)
        sem[semana(r.fecha)][k] += 1
        if r.requiere_externo:
            ev = r.externo_validacion or {}
            if not ev:
                sin_validar.append(r)
            elif not ev.get("validado"):
                rechazadas += 1
    incs = [i for i in s.execute(select(Incident)).scalars() if desde <= i.ts.date() <= hasta]
    por_tipo = Counter(incident_group_name(i.tipo) or "Sin tipo" for i in incs)
    por_sub = Counter(f"{incident_group_name(i.tipo)} · {incident_type_name(i.tipo)}" for i in incs)
    n = len(rutas)
    pct_ext = _pct(tot["EXTERNO"]["rutas"], n)
    reco = []
    if pct_ext is not None and pct_ext > float(param("pct_externo_alerta", 30) or 30):
        reco.append(f"{pct_ext} % de las rutas usan transporte externo: revisar disponibilidad y capacidad de la flota propia.")
    if sin_validar:
        reco.append(f"{len(sin_validar)} ruta(s) con transporte externo sin validar por el Coordinador de Distribución.")
    if incs:
        k, v = por_sub.most_common(1)[0]
        reco.append(f"Incidencia más frecuente: {k} ({v}). Atacar su causa reduce rechazos y reprogramaciones.")
    # Observaciones al demo v0.6: salidas a tiempo, plan vs ejecutado y costos de transporte externo y estiba
    from datetime import datetime as _dt
    salieron = [r for r in rutas if r.salida_ts]
    a_tiempo = 0
    desv = []
    for r in salieron:
        if r.hora_salida_prog:
            try:
                prog = _dt.combine(r.fecha, _dt.strptime(r.hora_salida_prog, "%H:%M").time())
            except ValueError:
                prog = None
        else:
            prog = None
        ok = (r.salida_ts <= prog) if prog else (r.salida_ts.date() <= r.fecha)
        a_tiempo += ok
        entregadas = sum(1 for st in r.stops if st.estado == "ENTREGADO")
        real_min = round((r.retorno_ts - r.salida_ts).total_seconds() / 60) if r.retorno_ts else None
        km_real = (r.km_retorno - r.km_salida) if r.km_retorno is not None and r.km_salida is not None else None
        desv.append({"route": r, "a_tiempo": ok, "retraso_min": round((r.salida_ts - prog).total_seconds() / 60) if prog else None,
                     "paradas_plan": len(r.stops), "paradas_ok": entregadas,
                     "min_plan": r.tiempo_estimado_min, "min_real": real_min,
                     "desv_min_pct": _pct((real_min or 0) - r.tiempo_estimado_min, r.tiempo_estimado_min) if real_min and r.tiempo_estimado_min else None,
                     "km_plan": r.distancia_km, "km_real": km_real,
                     "desv_km_pct": _pct((km_real or 0) - r.distancia_km, r.distancia_km) if km_real and r.distancia_km else None})
    costo_ext = sum(r.costo_transporte or 0 for r in rutas if r.requiere_externo)
    costo_est = sum(r.costo_estiba or 0 for r in rutas)
    kg_ext = tot["EXTERNO"]["kg"]
    if salieron and a_tiempo / len(salieron) < 0.9:
        reco.append(f"Solo {_pct(a_tiempo, len(salieron))} % de los transportes salió a tiempo: revisar preparación, carga y documentos.")
    if any(r.requiere_externo and r.costo_transporte is None for r in rutas):
        reco.append("Hay rutas con transporte externo sin costo registrado: registrar el costo para medir el gasto.")
    semanas = sorted(sem)
    return {"desde": desde, "hasta": hasta, "rutas": n, "tot": tot, "pct_externo": pct_ext,
            "salieron": len(salieron), "a_tiempo": a_tiempo, "pct_a_tiempo": _pct(a_tiempo, len(salieron)), "desviacion": desv,
            "costo_externo": round(costo_ext, 2), "costo_estiba": round(costo_est, 2),
            "costo_externo_kg": round(costo_ext / kg_ext, 4) if kg_ext and costo_ext else None,
            "serie_propio": [(f"{w:%d/%m}", sem[w]["PROPIO"]) for w in semanas],
            "serie_externo": [(f"{w:%d/%m}", sem[w]["EXTERNO"]) for w in semanas],
            "sin_validar": sin_validar, "externo_no_validado": rechazadas, "incidencias": len(incs),
            "por_tipo": por_tipo.most_common(), "por_subtipo": por_sub.most_common(12), "recomendaciones": reco}


# ------------------------------------------------------------------ almacén (obs. demo v0.6)
def almacen(desde=None, hasta=None, warehouse=None, almacenes=None):
    """Movimiento de stock del almacén: evolución del stock en cada carga de SAP (picos y bajas), demoras (traslados,
    picking), productos que se acercan al stock de reserva considerando el plazo de compra, y detalle de incidencias
    (diferencias de conteo, de traslado y tareas con incidencia)."""
    from ..models import (Alert, AlertIncident, PhysicalCount, PickingTask, Product as P, StockLot, Transfer,
                          UploadBatch, UploadRow)
    from .purchasing import analyze_product
    desde, hasta = periodo(desde, hasta, 60)
    s = db()
    whs = [warehouse] if warehouse else list(almacenes or [])
    # 1) evolución del stock por carga confirmada de SAP
    batches = list(s.execute(select(UploadBatch).where(UploadBatch.tipo == "STOCK", UploadBatch.estado == "CONFIRMADO",
                                                       UploadBatch.confirmado_ts >= desde,
                                                       UploadBatch.confirmado_ts < hasta + timedelta(days=1))
                             .order_by(UploadBatch.confirmado_ts)).scalars())
    serie, por_prod = [], defaultdict(list)
    for b in batches:
        tot = 0.0
        prods = defaultdict(float)
        for r in s.execute(select(UploadRow).where(UploadRow.batch_id == b.id, UploadRow.excluida.is_(False))).scalars():
            d = r.datos or {}
            if whs and str(d.get("almacen") or "").strip() not in whs:
                continue
            try:
                q = float(d.get("cantidad") or 0)
            except (TypeError, ValueError):
                q = 0.0
            tot += q
            prods[str(d.get("articulo") or "").strip()] += q
        serie.append((f"{b.confirmado_ts:%d/%m %H:%M}", round(tot, 2)))
        for k, v in prods.items():
            por_prod[k].append(v)
    pico = max(serie, key=lambda x: x[1]) if serie else None
    bajas = []
    for k, vals in por_prod.items():
        if len(vals) >= 2 and vals[0] > 0:
            var = (vals[-1] - vals[0]) / vals[0] * 100
            if var <= -20:
                bajas.append((k, vals[0], vals[-1], round(var, 1)))
    bajas.sort(key=lambda x: x[3])
    # 2) demoras
    hoy = date.today()
    traslados = [t for t in s.execute(select(Transfer).where(Transfer.estado.in_(("AUTORIZADO", "EN_TRANSITO")))).scalars()
                 if t.llegada_estimada and t.llegada_estimada.date() < hoy
                 and (not whs or t.destino_code in whs or t.lot.warehouse_code in whs)]
    picking = [t for t in s.execute(select(PickingTask).where(PickingTask.estado != "LISTO", PickingTask.fecha < hoy)).scalars()
               if not whs or t.warehouse_code in whs]
    preps = [(o.prep_fin - o.prep_inicio).total_seconds() / 3600 for o in s.execute(
        select(SalesOrder).where(SalesOrder.prep_fin.is_not(None), SalesOrder.prep_inicio.is_not(None),
                                 SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= hasta)).scalars()]
    # 3) stock de reserva considerando el plazo de compra
    codes = {l.product_code for l in s.execute(select(StockLot).where(StockLot.cantidad > 0)).scalars()
             if not whs or l.warehouse_code in whs}
    reserva = []
    for p in s.execute(select(P).where(P.code.in_(list(codes) or [""]))).scalars():
        if not (p.categoria_reposicion or p.stock_minimo):
            continue
        a = analyze_product(p)
        if a["requiere_compra"] or (a.get("dias_cobertura") is not None and a.get("lead_total") and a["dias_cobertura"] <= a["lead_total"]):
            reserva.append(a)
    # 4) incidencias con detalle
    conteos = [c for c in s.execute(select(PhysicalCount).where(PhysicalCount.fecha >= desde)).scalars()
               if not whs or c.warehouse_code in whs]
    dif_conteo = [(c, [x for x in c.lines if (x.faltante or 0) > 1e-9 or (x.sobrante or 0) > 1e-9]) for c in conteos]
    dif_conteo = [(c, xs) for c, xs in dif_conteo if xs]
    dif_traslado = [t for t in s.execute(select(Transfer).where(Transfer.diferencia != 0, Transfer.ts >= desde)).scalars()
                    if not whs or t.destino_code in whs]
    inc_tareas = list(s.execute(select(AlertIncident).join(Alert, AlertIncident.alert_id == Alert.id)
                                .where(Alert.area == "Almacén", AlertIncident.ts >= desde)).scalars())
    reco = []
    if reserva:
        reco.append(f"{len(reserva)} producto(s) llegan a su stock de reserva antes de que una compra pueda reponerlos: revisar reposición.")
    if traslados:
        reco.append(f"{len(traslados)} traslado(s) con llegada vencida sin recibir.")
    if picking:
        reco.append(f"{len(picking)} picking(s) programados en días pasados siguen sin terminar.")
    if bajas:
        reco.append(f"{len(bajas)} producto(s) con caída de stock mayor al 20 % en el periodo.")
    return {"desde": desde, "hasta": hasta, "almacen": warehouse, "almacenes": whs, "serie": serie, "pico": pico,
            "bajas": bajas[:20], "traslados_demorados": traslados, "picking_atrasado": picking,
            "prep_prom_h": round(mean(preps), 1) if preps else None, "reserva": reserva, "dif_conteo": dif_conteo,
            "dif_traslado": dif_traslado, "inc_tareas": inc_tareas, "recomendaciones": reco}


def _bucket(d, agrupar, n, desde):
    if agrupar == "MES":
        return date(d.year, d.month, 1)
    if agrupar == "N":
        return desde + timedelta(days=((d - desde).days // n) * n)
    return d


def produccion_capacidad(desde=None, hasta=None, agrupar="DIA", n=7):
    """Capacidad vs producido y programado vs ejecutado por línea (grupo de capacidad) y por proceso, por día, por cada
    N días o por mes; evolución, caídas, demoras y tiempo de atención de solicitudes y paradas de línea."""
    from ..models import ProductionPlan, ProductionReport, ProductionRequest
    desde, hasta = periodo(desde, hasta, dias=30)
    agrupar = agrupar if agrupar in ("DIA", "N", "MES") else "DIA"
    n = max(int(n or 7), 1)
    s = db()
    grupos = param("capacidad_lineas", []) or []
    jornada = {int(k): float(v) for k, v in (param("dias_operacion", {}) or {}).items()}
    from .calendar import day_factor, holidays
    feriados = holidays()
    linea_grupo = {l: g["grupo"] for g in grupos for l in g.get("lineas", [])}
    dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    buckets = sorted({_bucket(d, agrupar, n, desde) for d in dias})
    cap = defaultdict(float)
    for d in dias:
        f = day_factor(d, feriados, jornada)
        if f <= 0:
            continue
        for g in grupos:
            cap[(g["grupo"], _bucket(d, agrupar, n, desde))] += float(g.get("kg_dia") or 0) * f
    hechos = list(s.execute(select(ProductionReport).where(ProductionReport.fecha >= desde, ProductionReport.fecha <= hasta)).scalars())
    prod, prog_partes, paradas = defaultdict(float), defaultdict(float), []
    for r in hechos:
        g = linea_grupo.get(r.linea, r.linea)
        b = _bucket(r.fecha, agrupar, n, desde)
        if r.estado == "PROGRAMADO":
            prog_partes[(g, b)] += r.peso_entrada_kg or 0
        else:
            prod[(g, b)] += r.peso_entrada_kg or 0
        if r.parada_min:
            paradas.append(r)
    # programación (plan de producción con línea) en kg
    plan = defaultdict(float)
    for pl in s.execute(select(ProductionPlan).where(ProductionPlan.periodo == "DIA", ProductionPlan.fecha >= desde,
                                                     ProductionPlan.fecha <= hasta)).scalars():
        p = s.get(Product, pl.product_code)
        kg = pl.cantidad * ((p.peso_kg if p and p.peso_kg else (1 if p and (p.um or "").upper().startswith("K") else 0)))
        g = linea_grupo.get(pl.line_code, pl.line_code or "(sin línea)")
        plan[(g, _bucket(pl.fecha, agrupar, n, desde))] += kg
    filas = []
    for g in [x["grupo"] for x in grupos] + sorted({k[0] for k in list(prod) + list(plan)} - {x["grupo"] for x in grupos}):
        proceso = next((x["proceso"] for x in grupos if x["grupo"] == g), "")
        serie = []
        for b in buckets:
            c, pr = cap.get((g, b), 0.0), prod.get((g, b), 0.0)
            pl = plan.get((g, b), 0.0) + prog_partes.get((g, b), 0.0)
            serie.append({"bucket": b, "capacidad": c, "producido": pr, "uso": _pct(pr, c), "programado": pl,
                          "cumplimiento": _pct(min(pr, pl), pl) if pl else None})
        caidas = [x for a, x in zip(serie, serie[1:]) if a["producido"] > 0 and x["producido"] < a["producido"] * 0.8]
        tot_c, tot_p, tot_pl = sum(x["capacidad"] for x in serie), sum(x["producido"] for x in serie), sum(x["programado"] for x in serie)
        filas.append({"grupo": g, "proceso": proceso, "serie": serie, "capacidad": tot_c, "producido": tot_p,
                      "uso": _pct(tot_p, tot_c), "programado": tot_pl, "cumplimiento": _pct(min(tot_p, tot_pl), tot_pl) if tot_pl else None,
                      "caidas": caidas})
    por_proceso = defaultdict(lambda: {"capacidad": 0.0, "producido": 0.0, "programado": 0.0})
    for f in filas:
        x = por_proceso[f["proceso"] or "(sin proceso)"]
        x["capacidad"] += f["capacidad"]
        x["producido"] += f["producido"]
        x["programado"] += f["programado"]
    # demoras y tiempo de atención de solicitudes
    reqs = list(s.execute(select(ProductionRequest).where(ProductionRequest.ts >= desde,
                                                          ProductionRequest.ts < hasta + timedelta(days=1))).scalars())
    atencion = [((r.inicio_ts or r.fin_ts) - r.ts).total_seconds() / 3600 for r in reqs if (r.inicio_ts or r.fin_ts)]
    demoradas = [r for r in reqs if r.fecha_requerida and ((r.fin_ts and r.fin_ts.date() > r.fecha_requerida)
                                                           or (not r.fin_ts and r.fecha_requerida < date.today()
                                                               and r.estado not in ("RECHAZADA", "CANCELADA")))]
    reco = []
    for f in filas:
        if f["uso"] is not None and f["capacidad"] and f["uso"] < 50:
            reco.append(f"{f['grupo']}: uso de capacidad {f['uso']} % en el periodo.")
        if f["caidas"]:
            reco.append(f"{f['grupo']}: {len(f['caidas'])} caída(s) de producción mayores al 20 %: revisar paradas, materiales y demoras.")
    if demoradas:
        reco.append(f"{len(demoradas)} solicitud(es) de producción atendidas después de la fecha requerida o vencidas.")
    return {"desde": desde, "hasta": hasta, "agrupar": agrupar, "n": n, "buckets": buckets, "filas": filas,
            "por_proceso": dict(por_proceso), "paradas": paradas, "paradas_min": sum(r.parada_min or 0 for r in paradas),
            "atencion_h": round(mean(atencion), 1) if atencion else None, "demoradas": demoradas, "recomendaciones": reco}
