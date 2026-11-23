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


_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre",
          "noviembre", "diciembre"]


_PEND_OV = " · el valor de las OV de SAP con despacho en el mes se muestra aquí apenas se relea el historial de SAP"


def _url(endpoint, por_defecto):
    try:
        from flask import url_for
        return url_for(endpoint)
    except Exception:  # noqa: BLE001 - fuera de una petición (informe PDF, pruebas)
        return por_defecto


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
        cards.append(_card("Comercial", "OV ingresadas del mes", f"S/ {v_mes:,.0f}",
                           f"{gen['avance_soles']} % de la meta (esperado {metas['esperado']} % a la fecha)" +
                           (f"; {var_ant:+.0f} % vs el mismo corte del mes anterior" if var_ant is not None else "")
                           + _PEND_OV, niv, _url("com.orders", "/ov/")))
        if gen["atrasada"]:
            atencion.append(("ALTA", "Comercial", f"La venta va {gen['avance_soles']} % de la meta y a la fecha debería ir "
                                                  f"{metas['esperado']} %: faltan S/ {gen['falta_soles'] or 0:,.0f}."))
    else:
        cards.append(_card("Comercial", "OV ingresadas del mes", f"S/ {v_mes:,.0f}",
                           (f"{var_ant:+.0f} % vs el mismo corte del mes anterior" if var_ant is not None else "sin meta cargada")
                           + _PEND_OV, "warn" if var_ant is not None and var_ant < -10 else "", _url("com.orders", "/ov/")))
    # V52/V55: la facturación del mes es la de SAP, solo el neto (facturas − notas de crédito); las notas de crédito van
    # en su propia tarjeta
    from .comercial_v23 import fin_de_mes as _fm
    from .facturacion_sap import ov_del_periodo, resumen as _fact
    fx = _fact(ini, hoy, canal)
    fa = _fact(ant_ini, ant_ini.replace(day=dia_eq), canal) if fx is not None else None
    # V55: «OV del mes» son las OV de SAP con despacho en el mes (abiertas y cerradas, sin anuladas), con su valor
    ovm = ov_del_periodo(ini, _fm(ini), canal)
    if ovm is not None:
        meta = (f"; {gen['avance_soles']} % de la meta" if gen and gen["avance_soles"] is not None else "")
        cards = [c for c in cards if c["titulo"] != "OV ingresadas del mes"]
        cards.insert(0, _card("Comercial", f"OV con despacho en {_MESES[ini.month - 1]} (SAP)", f"S/ {ovm['total']:,.0f}",
                              f"{ovm['n']} OV · despachado S/ {ovm['despachado']:,.0f} · por despachar S/ {ovm['por_despachar']:,.0f}"
                              f" · sin IGV S/ {ovm['sin_igv']:,.0f} · ingresadas en el mes: {ovm['n_ingresadas']} OV por "
                              f"S/ {ovm['ingresadas']:,.0f}{meta}", "", _url("v24.ov_mes_sap", "/gestion/ov-mes-sap")))
    if fx is not None:
        var_f = _pct(fx["neto"] - fa["neto"], fa["neto"]) if fa and fa["neto"] else None
        extra = ""
        if ovm is not None and fx["neto"] > ovm["despachado"] + 1:
            extra = (" · incluye lo facturado en el mes de OV de meses anteriores y documentos sin OV (servicios, "
                     "ajustes)")
        cards.insert(0, _card("Comercial", "Facturación del mes (SAP)", f"S/ {fx['neto']:,.0f}",
                              f"facturado S/ {fx['facturas']:,.0f} − notas de crédito S/ {fx['notas_credito']:,.0f}"
                              f" = S/ {fx['neto']:,.0f} · sin IGV S/ {fx['neto_sin_igv']:,.0f}"
                              + (f" · {var_f:+.0f} % vs el mismo corte del mes anterior" if var_f is not None else "")
                              + (f" · hasta el {fx['ultima']:%d/%m}" if fx.get("ultima") else "") + extra, "",
                              _url("v24.facturacion_sap", "/gestion/facturacion-sap")))
        var_nc = _pct(fx["notas_credito"] - fa["notas_credito"], fa["notas_credito"]) if fa and fa["notas_credito"] else None
        pct_nc = _pct(fx["notas_credito"], fx["facturas"])
        cards.insert(1, _card("Comercial", "Notas de crédito del mes (SAP)", f"S/ {fx['notas_credito']:,.0f}",
                              f"{fx['n_notas']} nota(s) · sin IGV S/ {fx['notas_sin_igv']:,.0f}"
                              + (f" · {pct_nc:.1f} % de lo facturado" if pct_nc is not None else "")
                              + (f" · {var_nc:+.0f} % vs el mismo corte del mes anterior" if var_nc is not None else ""),
                              "warn" if pct_nc is not None and pct_nc > 10 else "",
                              _url("v24.facturacion_sap", "/gestion/facturacion-sap") + "?ver=notas"))
    # V58: lo entregado del mes (todas las guías de SAP: despachos completos, parciales y sin OV), valorizado con SAP
    from .facturacion_sap import entregado as _entregado
    en = _entregado(ini, hoy, canal)
    if en is not None:
        ea = _entregado(ant_ini, ant_ini.replace(day=dia_eq), canal)
        var_e = _pct(en["total"] - ea["total"], ea["total"]) if ea and ea["total"] else None
        pt, nt = en["por_tipo"], en["n_tipo"]
        partes = [f"completas S/ {pt['COMPLETA']:,.0f} ({nt['COMPLETA']} OV)",
                  f"parciales S/ {pt['PARCIAL']:,.0f} ({nt['PARCIAL']} OV)"]
        if pt["CERRADA_PARCIAL"]:
            partes.append(f"parciales ya cerradas S/ {pt['CERRADA_PARCIAL']:,.0f} ({nt['CERRADA_PARCIAL']} OV)")
        if pt["SIN_OV"]:
            partes.append(f"sin OV S/ {pt['SIN_OV']:,.0f}")
        pos = next((i + 1 for i, c in enumerate(cards) if c["titulo"].startswith("OV con despacho")), min(2, len(cards)))
        cards.insert(pos, _card("Comercial", f"Entregado en {_MESES[ini.month - 1]} (SAP)", f"S/ {en['total']:,.0f}",
                                f"{en['guias']} guía(s) de {en['ovs']} OV · " + " · ".join(partes)
                                + f" · sin IGV S/ {en['sin_igv']:,.0f}"
                                + (f" · {var_e:+.0f} % vs el mismo corte del mes anterior" if var_e is not None else "")
                                + (f" · {en['estimadas']} línea(s) valorizadas con el precio de su OV hasta releer SAP"
                                   if en["estimadas"] else ""), "", _url("v24.entregado_sap", "/gestion/entregado-sap")))
    # V69: diferencia por despachar de las OV abiertas de SAP: cuánto está vencido y cuánto en plazo
    from .por_despachar import calcular as _por_desp
    pd = _por_desp(hoy, canal)
    if pd is not None and (pd["VENCIDO"]["n"] or pd["EN_PLAZO"]["n"]):
        v, e = pd["VENCIDO"], pd["EN_PLAZO"]
        pos = next((i + 1 for i, c in enumerate(cards) if c["titulo"].startswith("OV con despacho")), min(3, len(cards)))
        cards.insert(pos, _card("Comercial", "Por despachar (OV abiertas SAP)", f"S/ {pd['total_soles']:,.0f}",
                                f"vencido S/ {v['soles']:,.0f} ({v['n']} OV · {v['kg']:,.0f} kg) · en plazo "
                                f"S/ {e['soles']:,.0f} ({e['n']} OV · {e['kg']:,.0f} kg)",
                                "err" if v["n"] else "", _url("v24.por_despachar", "/gestion/por-despachar")))
    if canal:
        from .comercial_v23 import base_mes, fin_de_mes, nivel
        n = nivel(del_canal(base_mes(ini, fin_de_mes(ini))), hoy=hoy)
    else:
        n = nivel_periodo(ini, None, hoy)
    # V44: con el historial de SAP, el OTIF del mes es el de las OV de SAP frente a sus guías (se actualiza con SAP)
    from .comercial_v23 import fin_de_mes as _fdm
    from .seguimiento import nivel_comercial_sap
    n = nivel_comercial_sap(ini, _fdm(ini), canal) or n
    otif = n["otif"]
    cards.append(_card("Logística", "OTIF del mes", f"{otif} %" if otif is not None else "—",
                       f"{n['conteos'][2]} de {n['n']} OV a tiempo y completas; {n['en_plazo']} aún en plazo",
                       "" if otif is None else ("ok" if otif >= 95 else "warn" if otif >= 85 else "err"),
                       _url("seg.service", "/seguimiento/servicio")))
    vencidas_fuera = [f for f in n["fallas"] if f["fecha"] and f["fecha"] < hoy and not f["salida"]]
    if vencidas_fuera:
        atencion.append(("ALTA", "Logística", f"{len(vencidas_fuera)} OV con fecha vencida que aún no salen "
                                              f"({', '.join(f['numero'] for f in vencidas_fuera[:4])})."))
    cb = collection_board(hoy)
    cards.append(_card("Finanzas", "Cobranza vencida", f"S/ {cb['total_vencido']:,.0f}",
                       f"de S/ {cb['total_abierto']:,.0f} por cobrar; S/ {cb['total_por_vencer']:,.0f} vence pronto",
                       "err" if cb["total_vencido"] > 0.2 * (cb["total_abierto"] or 1) else ("warn" if cb["total_vencido"] else "ok"),
                       _url("fin.board", "/finanzas/")))
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
                           "" if c_val is None else ("ok" if c_val >= 90 else "warn" if c_val >= 75 else "err"),
                           _url("v23.demand", "/analisis/demanda")))
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
                       "" if r_prom is None else ("ok" if r_prom >= 95 else "warn"), _url("prod.reports", "/produccion/partes")))
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
    # V55: las compras del mes salen de las órdenes de compra de SAP (valor y lo recibido); sin ellas, las solicitudes
    from .compras_sap import resumen as _compras
    cs = _compras(ini, hoy)
    if cs is not None:
        mon = " · ".join(f"{k}: S/ {v:,.0f}" for k, v in sorted(cs["por_moneda"].items())) if len(cs["por_moneda"]) > 1 else ""
        cards.append(_card("Compras", "Compras del mes (SAP)", f"S/ {cs['total']:,.0f}",
                           f"{cs['n_ordenes']} orden(es) de compra · recibido S/ {cs['recibido']:,.0f} · por recibir "
                           f"S/ {cs['por_recibir']:,.0f} · sin IGV S/ {cs['sin_igv']:,.0f}" + (f" · {mon}" if mon else "")
                           + f" · {len(atrasadas)} solicitud(es) del módulo con fecha vencida",
                           "warn" if atrasadas else "", _url("v24.compras_sap", "/gestion/compras-sap")))
    else:
        cards.append(_card("Compras", "Compras nacionales abiertas", len(abiertas),
                           f"{len(atrasadas)} con fecha de necesidad vencida · las órdenes de compra de SAP se muestran "
                           "aquí apenas el vigilante las lea", "warn" if atrasadas else "",
                           _url("v24.purchases", "/gestion/compras-nacionales")))
    if atrasadas:
        atencion.append(("MEDIA", "Compras", f"{len(atrasadas)} compra(s) nacional(es) pasaron su fecha de necesidad."))
    from .importaciones_v24 import board as imp_board
    ib = imp_board(hoy)
    cards.append(_card("Importaciones", "Contenedores por retirar", ib["tot"]["por_retirar"],
                       f"{ib['tot']['en_riesgo']} en riesgo de sobreestadía; gastos extra USD {ib['tot']['gastos_usd']:,.0f}",
                       "err" if ib["tot"]["sobreestadia"] else ("warn" if ib["tot"]["en_riesgo"] else ""),
                       _url("v24.imports", "/gestion/importaciones")))
    if ib["tot"]["sobreestadia"]:
        atencion.append(("ALTA", "Importaciones", f"{ib['tot']['sobreestadia']} importación(es) con días libres vencidos: "
                                                  f"riesgo USD {ib['tot']['riesgo_usd']:,.0f}."))
    if ver_costos:
        from .costos_v24 import analisis
        ca = analisis(hoy=hoy)
        cards.append(_card("Costos", "Reponer vs costo registrado",
                           f"S/ {abs(ca['neto']):,.0f} {'en contra' if ca['neto'] > 0 else 'a favor'}",
                           ca["resumen"][:160], "err" if ca["neto"] > 0 else "ok", _url("v24.costs", "/gestion/costos")))
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
                           "warn", url=_url("sup.rotation", "/suministro/rotacion")))
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
        if ini <= hoy:
            from .seguimiento import nivel_comercial_sap
            sap = nivel_comercial_sap(ini, min(fin, hoy))  # V44: con SAP si hay historial
            ot = sap["otif"] if sap else nivel(base_mes(ini, min(fin, hoy)), hoy=hoy)["otif"]
        else:
            ot = None
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
