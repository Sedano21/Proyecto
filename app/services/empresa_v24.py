"""V24 (06-nov-2026): tablero «Cómo va la empresa» e informe consolidado de reposición, escritos para leerse rápido.

Tablero (Jefatura Comercial, Jefatura de Operaciones, Jefatura de Administración y Finanzas, Costos y Presupuestos y
Gerencias): venta del mes frente a la meta y al mes anterior, nivel de servicio, cumplimiento de la demanda, cobranza,
margen por costo de reposición, producción, compras e importaciones; cada tarjeta con semáforo y una frase. Arriba, la
lista «A qué prestarle atención», ordenada por gravedad. Gráficos: venta semanal (8 semanas), OTIF por semana, cobranza
por antigüedad y proyectado vs despachado.

Informe de reposición: el análisis de reposición de cada producto agrupado en «Comprar ya», «Comprar esta semana»,
«Programar» y «Cubierto», con una frase por producto («Comprar 1 200 kg de … antes del 10/11: el stock alcanza 4 días y
el proveedor tarda 7»), y los productos sin datos suficientes aparte.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Product, PurchaseRequest, SalesOrder


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def _card(area, titulo, valor, frase, nivel="", url=None):
    return {"area": area, "titulo": titulo, "valor": valor, "frase": frase, "nivel": nivel, "url": url}


def tablero(hoy=None, ver_costos=False, canal=""):
    from .comercial_v23 import nivel_periodo
    from .commercial_mgmt import _metas
    from .finance import collection_board
    from .orders import order_amount
    hoy = hoy or date.today()
    ini = hoy.replace(day=1)
    ant_fin = ini - timedelta(days=1)
    ant_ini = ant_fin.replace(day=1)
    s = db()
    excl = ("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")

    from .margin import channel

    def del_canal(lst):  # V30: indicadores por canal o en general
        return [o for o in lst if not canal or channel(o.customer, o) == canal]

    def venta(desde, hasta):
        return sum(order_amount(o) for o in del_canal(s.execute(select(SalesOrder).where(
            SalesOrder.fecha_emision >= desde, SalesOrder.fecha_emision <= hasta, SalesOrder.estado.notin_(excl))).scalars()))
    v_mes = venta(ini, hoy)
    dia_eq = min(hoy.day, ant_fin.day)
    v_ant = venta(ant_ini, ant_ini.replace(day=dia_eq))
    ovs_mes = del_canal(s.execute(select(SalesOrder).where(SalesOrder.fecha_emision >= ini, SalesOrder.fecha_emision <= hoy,
                                                           SalesOrder.estado.notin_(excl))).scalars())
    metas = _metas(f"{hoy:%Y-%m}", ovs_mes, "", {})
    if canal:
        gen = next((m for m in metas["filas"] if m["alcance"] == "CANAL" and str(m.get("nombre", "")).upper() == canal.upper()), None)
    else:
        gen = next((m for m in metas["filas"] if m["alcance"] == "GENERAL"), None)
    cards, atencion = [], []
    var_ant = _pct(v_mes - v_ant, v_ant)
    if gen and gen["avance_soles"] is not None:
        niv = "err" if gen["atrasada"] else "ok"
        cards.append(_card("Comercial", "Venta del mes", f"S/ {v_mes:,.0f}",
                           f"{gen['avance_soles']} % de la meta (esperado {metas['esperado']} % a la fecha)" +
                           (f"; {var_ant:+.0f} % vs el mismo corte del mes anterior" if var_ant is not None else ""), niv))
        if gen["atrasada"]:
            atencion.append(("ALTA", "Comercial", f"La venta va {gen['avance_soles']} % de la meta y a la fecha debería ir "
                                                  f"{metas['esperado']} %: faltan S/ {gen['falta_soles'] or 0:,.0f}."))
    else:
        cards.append(_card("Comercial", "Venta del mes", f"S/ {v_mes:,.0f}",
                           (f"{var_ant:+.0f} % vs el mismo corte del mes anterior" if var_ant is not None else "sin meta cargada"),
                           "warn" if var_ant is not None and var_ant < -10 else ""))
    if canal:
        from .comercial_v23 import base_mes, fin_de_mes, nivel
        n = nivel(del_canal(base_mes(ini, fin_de_mes(ini))), hoy=hoy)
    else:
        n = nivel_periodo(ini, None, hoy)
    otif = n["otif"]
    cards.append(_card("Logística", "OTIF del mes", f"{otif} %" if otif is not None else "—",
                       f"{n['conteos'][2]} de {n['n']} OV a tiempo y completas; {n['en_plazo']} aún en plazo",
                       "" if otif is None else ("ok" if otif >= 95 else "warn" if otif >= 85 else "err")))
    vencidas_fuera = [f for f in n["fallas"] if f["fecha"] < hoy and not f["salida"]]
    if vencidas_fuera:
        atencion.append(("ALTA", "Logística", f"{len(vencidas_fuera)} OV con fecha vencida que aún no salen "
                                              f"({', '.join(f['numero'] for f in vencidas_fuera[:4])})."))
    cb = collection_board(hoy)
    cards.append(_card("Finanzas", "Cobranza vencida", f"S/ {cb['total_vencido']:,.0f}",
                       f"de S/ {cb['total_abierto']:,.0f} por cobrar; S/ {cb['total_por_vencer']:,.0f} vence pronto",
                       "err" if cb["total_vencido"] > 0.2 * (cb["total_abierto"] or 1) else ("warn" if cb["total_vencido"] else "ok")))
    if cb["por_cliente"]:
        top = [f"{c.nombre} (S/ {v['vencido']:,.0f})" for c, v in cb["por_cliente"][:3] if v["vencido"]]
        if top:
            atencion.append(("MEDIA", "Finanzas", "Mayor deuda vencida: " + ", ".join(top) + "."))
    # demanda
    try:
        from .demanda_v23 import cumplimiento
        from .demanda_v23 import _rango_mes as _rm
        cu = cumplimiento(ini, _rm(f"{hoy:%Y-%m}")[1], "SEMANA", hoy)["total"]
        c_val = cu["cumplimiento"]
        cards.append(_card("Operaciones", "Cumplimiento de la demanda", f"{c_val} %" if c_val is not None else "—",
                           f"despachado {cu['despachado_kg']:,.0f} kg de {cu['proyectado_a_hoy_kg']:,.0f} kg proyectados a hoy",
                           "" if c_val is None else ("ok" if c_val >= 90 else "warn" if c_val >= 75 else "err")))
        if c_val is not None and c_val < 75:
            atencion.append(("ALTA", "Operaciones", f"Se despachó {c_val} % de lo proyectado a la fecha: revisar con Comercial "
                                                    "si la proyección sigue vigente y con Producción la capacidad."))
    except Exception:  # noqa: BLE001  sin proyección cargada
        pass
    # producción: partes del mes (kg que entraron a línea, rendimiento y paradas)
    from ..models import ProductionReport
    partes = [r for r in s.execute(select(ProductionReport).where(ProductionReport.fecha >= ini, ProductionReport.fecha <= hoy,
                                                                  ProductionReport.estado != "PROGRAMADO")).scalars()]
    kg_p = sum(r.peso_entrada_kg or 0 for r in partes)
    rend = [r.rendimiento_pct for r in partes if r.rendimiento_pct]
    par = sum(r.parada_min or 0 for r in partes)
    r_prom = round(sum(rend) / len(rend), 1) if rend else None
    cards.append(_card("Producción", "Producción del mes", f"{kg_p:,.0f} kg",
                       f"{len(partes)} partes; rendimiento {r_prom if r_prom is not None else '—'} %; {par:,} min de parada",
                       "" if r_prom is None else ("ok" if r_prom >= 95 else "warn")))
    from .indicators import production_summary
    try:
        for nivel, texto in production_summary(ini, hoy)["alertas"][:2]:
            atencion.append((nivel, "Producción", texto))
    except Exception:  # noqa: BLE001
        pass
    # compras e importaciones
    abiertas = list(s.execute(select(PurchaseRequest).where(PurchaseRequest.estado.notin_(
        ("RECIBIDA", "RECIBIDA_CON_DIFERENCIAS", "RECIBIDA_BAJO_OBSERVACION", "CERRADA", "RECHAZADA", "CANCELADA")))).scalars())
    atrasadas = [r for r in abiertas if r.fecha_necesidad and r.fecha_necesidad < hoy]
    cards.append(_card("Compras", "Compras nacionales abiertas", len(abiertas),
                       f"{len(atrasadas)} con fecha de necesidad vencida", "warn" if atrasadas else ""))
    if atrasadas:
        atencion.append(("MEDIA", "Compras", f"{len(atrasadas)} compra(s) nacional(es) pasaron su fecha de necesidad."))
    from .importaciones_v24 import board as imp_board
    ib = imp_board(hoy)
    cards.append(_card("Importaciones", "Contenedores por retirar", ib["tot"]["por_retirar"],
                       f"{ib['tot']['en_riesgo']} en riesgo de sobreestadía; gastos extra USD {ib['tot']['gastos_usd']:,.0f}",
                       "err" if ib["tot"]["sobreestadia"] else ("warn" if ib["tot"]["en_riesgo"] else "")))
    if ib["tot"]["sobreestadia"]:
        atencion.append(("ALTA", "Importaciones", f"{ib['tot']['sobreestadia']} importación(es) con días libres vencidos: "
                                                  f"riesgo USD {ib['tot']['riesgo_usd']:,.0f}."))
    if ver_costos:
        from .costos_v24 import analisis
        ca = analisis(hoy=hoy)
        cards.append(_card("Costos", "Reponer vs costo registrado",
                           f"S/ {abs(ca['neto']):,.0f} {'en contra' if ca['neto'] > 0 else 'a favor'}",
                           ca["resumen"][:160], "err" if ca["neto"] > 0 else "ok"))
        if ca["neto"] > 0:
            atencion.append(("MEDIA", "Costos", ca["resumen"]))
    orden = {"ALTA": 0, "MEDIA": 1, "INFO": 2}
    atencion.sort(key=lambda x: orden.get(x[0], 9))
    # V25: venta vs meta (mes) y stock sin rotación valorizado
    meta_mes = {"venta": round(v_mes, 2), "meta": gen["meta_soles"] if gen else None,
                "avance": gen["avance_soles"] if gen else None, "esperado": metas.get("esperado"),
                "falta": gen["falta_soles"] if gen else None, "atrasada": bool(gen and gen["atrasada"])}
    from .supply import rotation_summary
    try:
        rot = rotation_summary(hoy)
    except Exception:  # noqa: BLE001
        rot = None
    if rot and rot["productos"]:
        cards.append(_card("Almacén", "Stock sin rotación", f"{rot['productos']} productos",
                           f"{rot['kg']:,.0f} kg sin salida en {rot['dias']} días" +
                           (f"; S/ {rot['valor_costo']:,.0f} al costo" if ver_costos and rot["valor_costo"] else "") +
                           (f"; venta S/ {rot['valor_min']:,.0f} a S/ {rot['valor_max']:,.0f}" if rot["valor_min"] else ""),
                           "warn", url="/suministro/rotacion"))
    return {"hoy": hoy, "cards": cards, "atencion": atencion, "graficos": _series(hoy, cb), "meta_mes": meta_mes, "rot": rot}


def _series(hoy, cb):
    from .comercial_v23 import base_mes, nivel
    from .orders import order_amount
    s = db()
    semanas = []
    lunes = hoy - timedelta(days=hoy.weekday())
    for k in range(7, -1, -1):
        ini = lunes - timedelta(weeks=k)
        fin = ini + timedelta(days=6)
        v = sum(order_amount(o) for o in s.execute(select(SalesOrder).where(
            SalesOrder.fecha_emision >= ini, SalesOrder.fecha_emision <= fin,
            SalesOrder.estado.notin_(("CANCELADA", "BORRADOR")))).scalars())
        ot = nivel(base_mes(ini, min(fin, hoy)), hoy=hoy)["otif"] if ini <= hoy else None
        semanas.append((f"{ini:%d/%m}", round(v, 2), ot))
    tramos = [(k, round(sum(i.saldo for i, _ in v), 2)) for k, v in cb["tramos"].items()]
    return {"semanas": semanas, "cobranza": tramos}


# ------------------------------------------------------------------ informe consolidado de reposición
def reposicion(hoy=None):
    from .purchasing import analyze_product
    from .stock import product_kind
    hoy = hoy or date.today()
    prods = list(db().execute(select(Product).where((Product.categoria_reposicion != "") | (Product.stock_minimo.is_not(None)))
                              .order_by(Product.code)).scalars())
    grupos = {"YA": [], "SEMANA": [], "PROGRAMAR": [], "CUBIERTO": [], "SIN_DATOS": []}
    por_tipo = defaultdict(lambda: {"productos": 0, "comprar": 0, "cantidad": 0.0})
    for p in prods:
        a = analyze_product(p, hoy)
        tipo = {"GR": "Granel", "MP": "Materia prima", "PT": "Producto terminado"}.get(product_kind(p), "Insumos")
        um = "kg" if (p.um or "").upper().startswith("K") else (p.um or "und").lower()
        limite = a.get("fecha_limite_pedido")
        cant = a["cantidad_sugerida"]
        cob = a.get("dias_cobertura")
        item = {"code": p.code, "descripcion": p.descripcion, "tipo": tipo, "cantidad": cant, "um": um, "limite": limite,
                "cobertura": cob, "plazo": a.get("plazo_dias"), "disponible": a["disponible"], "faltante_ov": a["faltante_ov"],
                "en_camino": a["en_camino"]}
        por_tipo[tipo]["productos"] += 1
        if a.get("plazo_dias") is None and a["consumo_diario"] == 0 and not cant:
            item["frase"] = "Sin plazo de reposición ni ventas recientes: completar datos del producto."
            grupos["SIN_DATOS"].append(item)
            continue
        if cant <= 0:
            item["frase"] = (f"Cubierto: alcanza {cob:g} días con el stock y lo que llega." if cob is not None
                             else "Cubierto con el stock y lo que está en camino.")
            grupos["CUBIERTO"].append(item)
            continue
        por_tipo[tipo]["comprar"] += 1
        por_tipo[tipo]["cantidad"] += cant
        partes = [f"Comprar {cant:,.0f} {um}"]
        if limite:
            partes.append(f"antes del {limite:%d/%m}")
        razones = []
        if cob is not None:
            razones.append(f"el stock alcanza {cob:g} días")
        if a.get("plazo_dias") is not None:
            razones.append(f"el proveedor tarda {a['plazo_dias']} días (+{a['margen_dias']} de margen)")
        if a["faltante_ov"]:
            razones.append(f"faltan {a['faltante_ov']:,.0f} para OV ya registradas")
        if a["en_camino"]:
            razones.append(f"ya hay {a['en_camino']:,.0f} en camino")
        item["frase"] = " ".join(partes) + (": " + "; ".join(razones) if razones else "") + "."
        if limite is None or limite <= hoy:
            grupos["YA"].append(item)
        elif limite <= hoy + timedelta(days=7):
            grupos["SEMANA"].append(item)
        else:
            grupos["PROGRAMAR"].append(item)
    for k in ("YA", "SEMANA", "PROGRAMAR"):
        grupos[k].sort(key=lambda x: (x["limite"] or date.min, x["code"]))
    resumen = (f"{len(grupos['YA'])} producto(s) hay que comprarlos ya, {len(grupos['SEMANA'])} esta semana y "
               f"{len(grupos['PROGRAMAR'])} se pueden programar; {len(grupos['CUBIERTO'])} están cubiertos"
               + (f" y {len(grupos['SIN_DATOS'])} no tienen datos suficientes." if grupos["SIN_DATOS"] else "."))
    return {"hoy": hoy, "grupos": grupos, "por_tipo": dict(por_tipo), "resumen": resumen}
