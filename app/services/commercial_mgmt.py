"""Informe de gestión comercial (observaciones del módulo V7, 26-oct-2026).

Para el Coordinador, el Jefe y el Gerente Comercial (y Gerencia): avance de metas por vendedor, canal y total en S/ y
kg; OV ingresadas, atendidas, pendientes y facturación; nivel de servicio (On time, In full, OTIF y fill rate) con su
fórmula; desempeño por persona; embudo comercial; productos y presentaciones con menos venta o sin movimiento; margen
por canal; estado de pago por cliente; penalidades; y recomendaciones. Filtros múltiples: canales (incluir o excluir),
granel o envasado, vendedores y clientes.

Fórmulas (base: OV que salieron del almacén en el periodo):
- On time   = OV que salieron hasta su fecha comprometida / OV que salieron.
- In full   = OV que salieron con todas sus líneas completas / OV que salieron.
- OTIF      = OV a tiempo Y completas / OV que salieron.
- Fill rate = unidades despachadas (hasta lo pedido) / unidades pedidas (también por líneas completas / líneas).
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (AuditLog, Customer, CustomerInvoice, Opportunity, Product, Quote, SalesOrder, SalesTarget,
                      StockLot, User)
from .core import param

ABIERTAS = ("BORRADOR", "BLOQUEADA", "REGISTRADA", "EVALUADA", "EN_PREPARACION", "PREPARADA", "PROGRAMADA", "EN_RUTA")
ATENDIDAS = ("DESPACHADA", "ENTREGADA", "ENTREGA_PARCIAL", "CERRADA", "REGULARIZADA_CERRADA")
FORMULAS = {
    "on_time": "OV que salieron hasta su fecha comprometida ÷ OV que salieron",
    "in_full": "OV que salieron con todas sus líneas completas ÷ OV que salieron",
    "otif": "OV a tiempo y completas ÷ OV que salieron",
    "fill_unidades": "Unidades despachadas (hasta lo pedido) ÷ unidades pedidas",
    "fill_lineas": "Líneas despachadas completas ÷ líneas pedidas",
}


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def _kg(line):
    p = line.product
    if p is None:
        return 0.0
    return line.cantidad * (p.peso_kg or (1 if (p.um or "").upper().startswith("K") else 0))


def _kg_q(line, q):
    p = line.product
    return q * ((p.peso_kg or (1 if (p.um or "").upper().startswith("K") else 0)) if p else 0)


def options():
    """Valores para los filtros múltiples."""
    from .prices import canales, channel_of
    s = db()
    clientes = list(s.execute(select(Customer).order_by(Customer.nombre)).scalars())
    vend = list(s.execute(select(User).where(User.role_code.in_(("EJECUTIVO_VENTAS", "COORD_VENTAS", "JEFE_VENTAS")),
                                             User.activo.is_(True)).order_by(User.nombre)).scalars())
    chs = set(canales()) | {channel_of(c) for c in clientes} | set(param("lista_granel_canales", []) or [])
    return {"canales": sorted(c for c in chs if c), "clientes": clientes, "vendedores": vend}


def _filtrar(ovs, f):
    from .reports import order_channel
    canales = set(f.get("canales") or [])
    if canales:
        if f.get("modo_canal") == "excluir":
            ovs = [o for o in ovs if order_channel(o) not in canales]
        else:
            ovs = [o for o in ovs if order_channel(o) in canales]
    vs = {str(v) for v in (f.get("vendedores") or [])}
    if vs:
        ovs = [o for o in ovs if str(o.vendedor_id or "") in vs]
    cs = {str(c) for c in (f.get("clientes") or [])}
    if cs:
        ovs = [o for o in ovs if str(o.customer_id) in cs]
    return ovs


def _lineas(o, tipo):
    from .reports import line_kind
    return [l for l in o.lines if l.activa and (not tipo or line_kind(l.product) == tipo)]


def _nivel(ovs, tipo):
    """On time, In full, OTIF y fill rate de las OV que salieron."""
    base = [o for o in ovs if o.salida_ts is not None and _lineas(o, tipo)]
    ot = inf = otif = 0
    ped = desp = 0.0
    lin = lin_ok = 0
    for o in base:
        ls = _lineas(o, tipo)
        a_tiempo = o.salida_ts.date() <= o.fecha_compromiso
        completo = all(l.despachado >= l.cantidad - 1e-9 for l in ls)
        ot += a_tiempo
        inf += completo
        otif += a_tiempo and completo
        for l in ls:
            ped += l.cantidad
            desp += min(l.despachado, l.cantidad)
            lin += 1
            lin_ok += l.despachado >= l.cantidad - 1e-9
    n = len(base)
    return {"n": n, "on_time": _pct(ot, n), "in_full": _pct(inf, n), "otif": _pct(otif, n),
            "fill_unidades": _pct(desp, ped), "fill_lineas": _pct(lin_ok, lin), "conteos": (ot, inf, otif, n)}


def _metas(mes, ovs_mes, tipo, usuarios):
    """Avance de los objetivos del mes (S/ y kg) vs lo esperado a la fecha."""
    from .reports import order_channel
    ini = date(int(mes[:4]), int(mes[5:7]), 1)
    fin = (ini.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    hoy = date.today()
    esperado = _pct(max(min(hoy, fin) - ini + timedelta(days=1), timedelta(0)).days, (fin - ini).days + 1) or 0.0
    real = {"GENERAL": defaultdict(lambda: [0.0, 0.0]), "CANAL": defaultdict(lambda: [0.0, 0.0]),
            "VENDEDOR": defaultdict(lambda: [0.0, 0.0])}
    for o in ovs_mes:
        ls = _lineas(o, tipo)
        so = sum(l.cantidad * (l.precio_unitario or 0) for l in ls)
        kg = sum(_kg(l) for l in ls)
        for alc, k in (("GENERAL", ""), ("CANAL", order_channel(o)), ("VENDEDOR", str(o.vendedor_id or ""))):
            real[alc][k][0] += so
            real[alc][k][1] += kg
    nuevos = new_customers_and_skus(ini, fin, ovs_mes)
    filas = []
    for t in db().execute(select(SalesTarget).where(SalesTarget.mes == mes)).scalars():
        so, kg = real[t.alcance][t.clave] if t.clave in real.get(t.alcance, {}) else (0.0, 0.0)
        av_s = _pct(so, t.soles) if t.soles else None
        av_k = _pct(kg, t.kg) if t.kg else None
        atrasada = any(a is not None and a < esperado - float(param("tolerancia_meta_pct", 10) or 0) for a in (av_s, av_k))
        filas.append({"alcance": t.alcance, "nombre": usuarios.get(t.clave, t.clave) if t.alcance == "VENDEDOR" else (t.clave or "Total"),
                      "meta_soles": t.soles, "meta_kg": t.kg, "soles": round(so, 2), "kg": round(kg, 1),
                      "avance_soles": av_s, "avance_kg": av_k, "atrasada": atrasada,
                      "falta_soles": round(max(t.soles - so, 0), 2) if t.soles else None,
                      "meta_nuevos_clientes": t.nuevos_clientes, "meta_nuevos_sku": t.nuevos_sku,
                      "nuevos_clientes": len(nuevos["clientes"].get((t.alcance, t.clave), set())),
                      "nuevos_sku": len(nuevos["sku"].get((t.alcance, t.clave), set()))})
    filas.sort(key=lambda x: ({"GENERAL": 0, "CANAL": 1, "VENDEDOR": 2}[x["alcance"]], x["nombre"]))
    return {"mes": mes, "esperado": esperado, "filas": filas, "atrasadas": [f for f in filas if f["atrasada"]]}


def gestion(desde=None, hasta=None, filtros=None, ver_costos=False, user=None):
    from .finance import statement
    from .orders import order_amount
    from .penalties import indicator
    from .reports import line_kind, order_channel
    f = dict(filtros or {})
    tipo = f.get("tipo") or ""
    hoy = date.today()
    desde = desde or hoy.replace(day=1)
    hasta = hasta or hoy
    s = db()
    usuarios = {str(u.id): u.nombre for u in s.execute(select(User)).scalars()}
    todas = [o for o in s.execute(select(SalesOrder).where(SalesOrder.fecha_emision >= desde,
                                                           SalesOrder.fecha_emision <= hasta)).scalars()]
    todas = [o for o in _filtrar(todas, f) if _lineas(o, tipo)]
    ovs = [o for o in todas if o.estado not in ("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")]

    def monto(o):
        return sum(l.cantidad * (l.precio_unitario or 0) for l in _lineas(o, tipo)) if tipo else order_amount(o)

    def kg(o):
        return sum(_kg(l) for l in _lineas(o, tipo))

    def atendido(o):
        ls = _lineas(o, tipo)
        return (sum(min(l.despachado, l.cantidad) * (l.precio_unitario or 0) for l in ls),
                sum(_kg_q(l, min(l.despachado, l.cantidad)) for l in ls))
    ingresadas = {"n": len(ovs), "soles": round(sum(monto(o) for o in ovs), 2), "kg": round(sum(kg(o) for o in ovs), 1)}
    at = [atendido(o) for o in ovs]
    atendidas = {"n": sum(1 for o in ovs if o.estado in ATENDIDAS), "soles": round(sum(a for a, _ in at), 2),
                 "kg": round(sum(k for _, k in at), 1)}
    pend = [o for o in ovs if o.estado in ABIERTAS]
    pendientes = {"n": len(pend), "soles": round(sum(monto(o) - atendido(o)[0] for o in pend), 2),
                  "kg": round(sum(kg(o) - atendido(o)[1] for o in pend), 1),
                  "vencidas": sum(1 for o in pend if o.fecha_compromiso < hoy),
                  "mes": sum(1 for o in pend if o.fecha_compromiso <= (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))}
    ids = {o.customer_id for o in ovs}
    facts = [i for i in s.execute(select(CustomerInvoice).where(CustomerInvoice.fecha >= desde, CustomerInvoice.fecha <= hasta,
                                                                CustomerInvoice.estado != "ANULADA")).scalars()
             if not (f.get("clientes") or f.get("canales") or f.get("vendedores")) or i.customer_id in ids]
    facturacion = {"soles": round(sum(i.monto if i.tipo == "FACTURA" else -i.monto for i in facts), 2), "docs": len(facts),
                   "fuente": "Facturas cargadas (SAP o Finanzas)" if facts else
                   "Sin facturas cargadas en el periodo: se muestra lo atendido valorizado"}
    if not facts:
        facturacion["soles"] = atendidas["soles"]
    nivel = _nivel(ovs, tipo)
    # por vendedor, canal y cliente
    grupos = {"vendedor": defaultdict(list), "canal": defaultdict(list), "cliente": defaultdict(list)}
    for o in ovs:
        grupos["vendedor"][o.vendedor.nombre if o.vendedor else (o.vendedor_nombre or "(sin vendedor)")].append(o)
        grupos["canal"][order_channel(o) or "(sin canal)"].append(o)
        grupos["cliente"][o.customer.nombre].append(o)
    mods = Counter(m.entidad_id for m in s.execute(select(AuditLog).where(
        AuditLog.accion == "OV_MODIFICADA", AuditLog.ts >= desde, AuditLog.ts < hasta + timedelta(days=1))).scalars())
    opps = list(s.execute(select(Opportunity)).scalars())
    opps = [x for x in opps if desde <= x.creado_ts.date() <= hasta]
    pen = indicator(desde, hasta)["por_vendedor"]

    def resumen(lst, nombre=None):
        so = sum(monto(o) for o in lst)
        r = {"ovs": len(lst), "soles": round(so, 2), "kg": round(sum(kg(o) for o in lst), 1),
             "ticket": round(so / len(lst), 2) if lst else 0, "nivel": _nivel(lst, tipo),
             "modificadas": sum(1 for o in lst if o.numero in mods)}
        r["pct_modificadas"] = _pct(r["modificadas"], len(lst))
        return r
    por = {k: sorted(((n, resumen(v)) for n, v in g.items()), key=lambda x: -x[1]["soles"]) for k, g in grupos.items()}
    metas = _metas(f"{hasta:%Y-%m}", [o for o in ovs if o.fecha_emision >= hasta.replace(day=1)], tipo, usuarios)
    meta_v = {m["nombre"]: m for m in metas["filas"] if m["alcance"] == "VENDEDOR"}
    personas = []
    for n, r in por["vendedor"]:
        op = [x for x in opps if (x.vendedor.nombre if x.vendedor else "") == n]
        p = pen.get(n, {})
        personas.append(dict(r, nombre=n, meta=meta_v.get(n), oportunidades=len(op),
                             ganadas=sum(1 for x in op if x.estado == "GANADA"),
                             perdidas=sum(1 for x in op if x.estado == "PERDIDA"),
                             penalidad_calc=p.get("calculada", 0), penalidad_pag=p.get("pagada", 0)))
    # embudo comercial: oportunidades → cotizaciones → OV
    quotes = [q for q in s.execute(select(Quote)).scalars() if desde <= q.fecha <= hasta]
    et = Counter(x.estado for x in opps)
    embudo = [("Oportunidades", len(opps)), ("Cotizadas / en negociación", et["COTIZADA"] + et["NEGOCIACION"] + et["GANADA"]),
              ("Cotizaciones emitidas", len(quotes)), ("Cotizaciones aceptadas", sum(1 for q in quotes if q.estado == "ACEPTADA")),
              ("Ganadas", et["GANADA"]), ("OV del periodo", len(ovs))]
    # productos y presentaciones con menos venta o sin movimiento
    vend_p = defaultdict(float)
    vend_pres = defaultdict(float)
    for o in ovs:
        for l in _lineas(o, tipo):
            vend_p[l.product_code] += l.cantidad * (l.precio_unitario or 0)
            if l.product:
                vend_pres[l.product.presentacion or l.product.um or "-"] += l.cantidad
    catalogo = [p for p in s.execute(select(Product).where(Product.tipo.in_(("PT", "GR")))).scalars()
                if not tipo or line_kind(p) == tipo]
    con_stock = {c for c, in s.execute(select(StockLot.product_code).where(StockLot.cantidad > 0)).all()}
    menos = sorted(((p, vend_p[p.code]) for p in catalogo if vend_p.get(p.code)), key=lambda x: x[1])[:15]
    sin_mov = [p for p in catalogo if not vend_p.get(p.code)]
    sin_mov.sort(key=lambda p: (p.code not in con_stock, p.code))
    pres_cat = {p.presentacion or p.um or "-" for p in catalogo}
    pres_sin = sorted(pres_cat - {k for k, v in vend_pres.items() if v})
    # estado de pago por cliente (deuda y días de atraso)
    pagos = []
    for n, r in por["cliente"][:40]:
        c = grupos["cliente"][n][0].customer
        st = statement(c)
        atraso = max([(hoy - i.vencimiento).days for i in st["vencidas"]] or [0])
        pagos.append({"cliente": c, "soles": r["soles"], "deuda": st["deuda"], "vencida": st["deuda_vencida"],
                      "estado": st["estado_pago"], "dias_atraso": atraso})
    pagos.sort(key=lambda x: (-x["dias_atraso"], -x["vencida"]))
    margen = None
    if ver_costos:
        from .margin import margin
        margen = margin(desde, hasta, "CANAL", "PEDIDO")
    mercado = _mercado(desde, hasta, ver_costos)
    reco = _recomendaciones(nivel, metas, personas, pendientes, sin_mov, con_stock, pagos, ingresadas)
    return {"desde": desde, "hasta": hasta, "filtros": f, "ingresadas": ingresadas, "atendidas": atendidas,
            "pendientes": pendientes, "facturacion": facturacion, "nivel": nivel, "formulas": FORMULAS, "por": por,
            "metas": metas, "personas": personas, "embudo": embudo, "menos_vendidos": menos,
            "sin_movimiento": sin_mov[:30], "sin_movimiento_con_stock": [p for p in sin_mov if p.code in con_stock][:30],
            "presentaciones_sin_mov": pres_sin, "pagos": pagos, "margen": margen, "mercado": mercado,
            "canceladas": sum(1 for o in todas if o.estado == "CANCELADA"), "recomendaciones": reco,
            "penalidades": indicator(desde, hasta)["total"]}


def _recomendaciones(nivel, metas, personas, pend, sin_mov, con_stock, pagos, ing):
    """[(nivel ALTA/MEDIA/INFO, texto)] ordenadas por prioridad."""
    out = []
    meta_otif = float(param("meta_otif_pct", 95) or 95)
    if nivel["otif"] is not None and nivel["otif"] < meta_otif:
        peor = "a tiempo" if (nivel["on_time"] or 0) < (nivel["in_full"] or 0) else "completas"
        out.append(("ALTA", f"OTIF {nivel['otif']} % bajo la meta de {meta_otif:g} %: el mayor problema son las entregas "
                            f"no {peor}. Revise con Almacén y Distribución las OV afectadas."))
    for m in metas["atrasadas"][:5]:
        out.append(("ALTA", f"Meta de {m['nombre']} atrasada: {m['avance_soles'] or 0} % en S/ vs {metas['esperado']} % "
                            f"esperado a la fecha (faltan S/ {m['falta_soles'] or 0:,.0f})."))
    if pend["vencidas"]:
        out.append(("ALTA", f"{pend['vencidas']} OV pendientes con fecha vencida: renegocie la fecha o priorice su atención."))
    deudores = [p for p in pagos if p["dias_atraso"] > 30]
    if deudores:
        out.append(("ALTA", f"{len(deudores)} cliente(s) con deuda vencida de más de 30 días "
                            f"({', '.join(p['cliente'].nombre for p in deudores[:3])}): coordine la cobranza antes de nuevas OV."))
    mod = [p for p in personas if (p["pct_modificadas"] or 0) > 20]
    if mod:
        out.append(("MEDIA", f"{', '.join(p['nombre'] for p in mod[:3])}: más del 20 % de sus OV se modificaron; revise la "
                             "toma de pedidos."))
    sm = [p.code for p in sin_mov if p.code in con_stock]
    if sm:
        out.append(("MEDIA", f"{len(sm)} producto(s) con stock y sin venta en el periodo ({', '.join(sm[:5])}): "
                             "proponga una campaña o «producto del mes»."))
    if not out and ing["n"]:
        out.append(("INFO", "Sin alertas en el periodo: mantenga el seguimiento semanal de metas y nivel de servicio."))
    orden = {"ALTA": 0, "MEDIA": 1, "INFO": 2}
    return sorted(out, key=lambda x: orden[x[0]])


def home_summary(user):
    """Resumen para la portada del Coordinador, Jefe y Gerente Comercial: metas del mes y totales."""
    hoy = date.today()
    d = gestion(hoy.replace(day=1), hoy, {}, False, user)
    return {"metas": d["metas"], "ingresadas": d["ingresadas"], "atendidas": d["atendidas"], "pendientes": d["pendientes"],
            "facturacion": d["facturacion"], "nivel": d["nivel"], "recomendaciones": d["recomendaciones"][:3]}


def check_goal_alerts(hoy=None):
    """V7: alerta (una por semana y meta) cuando el avance de una meta está por debajo de lo esperado a la fecha."""
    from . import alerts
    hoy = hoy or date.today()
    mes = f"{hoy:%Y-%m}"
    if not db().execute(select(SalesTarget).where(SalesTarget.mes == mes)).scalars().first():
        return 0
    ovs = [o for o in db().execute(select(SalesOrder).where(SalesOrder.fecha_emision >= hoy.replace(day=1),
                                                            SalesOrder.fecha_emision <= hoy)).scalars()
           if o.estado not in ("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")]
    usuarios = {str(u.id): u for u in db().execute(select(User)).scalars()}
    m = _metas(mes, ovs, "", {k: u.nombre for k, u in usuarios.items()})
    n = 0
    semana = hoy.isocalendar()[1]
    for f in m["atrasadas"]:
        extra = []
        if f["alcance"] == "VENDEDOR":
            u = next((u for u in usuarios.values() if u.nombre == f["nombre"]), None)
            extra = [u.id] if u else []
        alerts.emit("META_ATRASADA", f"Meta {f['alcance'].lower()} {f['nombre']}: {f['avance_soles'] or 0} % (esperado {m['esperado']} %)",
                    f"Real S/ {f['soles']:,.0f} de S/ {f['meta_soles']:,.0f}; faltan S/ {f['falta_soles'] or 0:,.0f}.",
                    "SalesTarget", f"{mes}/{f['alcance']}/{f['nombre']}", extra_users=extra,
                    dedup_key=f"META:{mes}:{semana}:{f['alcance']}:{f['nombre']}")
        n += 1
    return n


def new_customers_and_skus(ini, fin, ovs_mes):
    """Clientes nuevos (su primera OV es del mes) y SKU nuevos en clientes existentes (primera vez que el cliente compra
    ese producto), por alcance: GENERAL, CANAL y VENDEDOR."""
    from .reports import order_channel
    previas = list(db().execute(select(SalesOrder).where(SalesOrder.fecha_emision < ini,
                                                         SalesOrder.estado != "CANCELADA")).scalars())
    con_compra = {o.customer_id for o in previas}
    compro = {(o.customer_id, l.product_code) for o in previas for l in o.lines if l.activa}
    clientes, sku = defaultdict(set), defaultdict(set)
    for o in ovs_mes:
        claves = [("GENERAL", ""), ("CANAL", order_channel(o)), ("VENDEDOR", str(o.vendedor_id or ""))]
        for k in claves:
            if o.customer_id not in con_compra:
                clientes[k].add(o.customer_id)
            else:
                for l in o.lines:
                    if l.activa and (o.customer_id, l.product_code) not in compro:
                        sku[k].add((o.customer_id, l.product_code))
    return {"clientes": clientes, "sku": sku}


def _mercado(desde, hasta, ver_costos):
    """Precio y costo frente al mercado (competencia directa y sustitutos registrados por Comercial), por producto base."""
    from .costs import cost_per_kg
    from .market import analysis
    filas = [f for f in analysis(max((hasta - desde).days, 30))["venta"] if f["prom_competencia"] or f["prom_sustitutos"]]
    if ver_costos:
        por_base = defaultdict(list)
        for p in db().execute(select(Product).where(Product.tipo.in_(("PT", "GR")))).scalars():
            base = ((p.producto_base or p.descripcion or "").upper().split("*")[0]).strip()
            c = cost_per_kg(p)
            if c:
                por_base[base].append(c)
        for f in filas:
            cs = por_base.get(f["producto"])
            f["costo_kg"] = round(sum(cs) / len(cs), 4) if cs else None
            ref = f["prom_competencia"] or f["prom_sustitutos"]
            f["costo_vs_mercado"] = round((f["costo_kg"] - ref) / ref * 100, 1) if f["costo_kg"] and ref else None
    return filas
