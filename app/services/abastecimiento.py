"""V59 (19-nov-2026): abastecimiento de granel, MP e insumos: cuándo se quiebra el stock y de dónde conviene traerlo.

- **Proyección día a día.** Para cada producto que se compra, parte del stock libre de hoy (lo ya reservado para OV
  no cuenta) y recorre los próximos días:
  - resta lo que sale con las OV pendientes en su fecha comprometida (lo no reservado aún);
  - suma lo pendiente de ingresar de las órdenes de compra abiertas de SAP en su fecha de entrega;
  - pasada la última OV conocida, resta el consumo diario histórico.

  El **quiebre** es el primer día en que el saldo baja del stock de reserva (stock mínimo + stock de seguridad). Se
  muestran las OV de ese día que «se comen» la reserva y el día en que se llegaría a cero. El objetivo es no llegar a
  cero.
- **Origen sugerido** (nacional o importado), con el historial de órdenes de compra de SAP del último año: el país del
  proveedor, el costo unitario en soles y el plazo (fecha de entrega − fecha de la OC).
  - Si una sola vía llega antes del quiebre, esa.
  - Si llegan las dos, la más barata.
  - Si ninguna llega a tiempo, la más rápida.
  - La materia prima (MP) la compra solo Compras nacionales.

  Responsable: Coordinador de Compras (nacional) o Coordinador de Importación (importado).
- **Lo que ya está en SAP por ingresar** (OC abiertas con saldo) y lo que ya ingresó (entradas de mercancías), para no
  pedir de más o de menos.

Es un análisis de apoyo: nada se pide solo."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select

from ..db import db
from ..models import Product, PurchaseRequest, SalesOrder, SapPurchaseLine
from .core import param

NACIONAL, IMPORTADO = "NACIONAL", "IMPORTADO"
RESPONSABLE = {NACIONAL: "Coordinador de Compras", IMPORTADO: "Coordinador de Importación"}
ANTES_DE_OC = ("BORRADOR", "PENDIENTE_LOGISTICA", "SOLICITADA", "EN_COTIZACION", "MUESTRA_EN_CALIDAD", "PENDIENTE_APROBACION")


def origen_de(pais):
    if not pais:
        return ""
    return NACIONAL if pais.upper() == str(param("pais_empresa", "PE") or "PE").upper() else IMPORTADO


def es_mp(p):
    return (p.code or "").upper().startswith("MP")


def hay_compras_sap():
    return db().execute(select(SapPurchaseLine.id).limit(1)).first() is not None


# ------------------------------------------------------------------ historial y pendientes de SAP
def historial(codes, ref=None, dias=365):
    """{código: {origen: {ordenes, cantidad, costo_unit, plazo_dias, ultima, proveedores}}} de las OC de SAP."""
    ref = ref or date.today()
    acc = defaultdict(lambda: defaultdict(lambda: {"ordenes": set(), "cantidad": 0.0, "total": 0.0, "plazos": [],
                                                   "ultima": None, "proveedores": set()}))
    codes = list(codes)
    for i in range(0, len(codes), 500):
        q = select(SapPurchaseLine).where(SapPurchaseLine.tipo == "OC", SapPurchaseLine.estado != "CANCELADA",
                                          SapPurchaseLine.fecha >= ref - timedelta(days=dias),
                                          SapPurchaseLine.product_code.in_(codes[i:i + 500]))
        for ln in db().execute(q).scalars():
            o = origen_de(ln.pais) or "SIN_PAIS"
            h = acc[ln.product_code][o]
            h["ordenes"].add(ln.docnum)
            h["cantidad"] += ln.cantidad or 0
            h["total"] += ln.total or 0
            if ln.fecha and ln.fecha_entrega and ln.fecha_entrega >= ln.fecha:
                h["plazos"].append((ln.fecha_entrega - ln.fecha).days)
            h["ultima"] = max(filter(None, [h["ultima"], ln.fecha]), default=None)
            h["proveedores"].add(ln.proveedor)
    out = {}
    for c, por in acc.items():
        out[c] = {o: {"ordenes": len(h["ordenes"]), "cantidad": h["cantidad"],
                      "costo_unit": round(h["total"] / h["cantidad"], 4) if h["cantidad"] else None,
                      "plazo_dias": round(sum(h["plazos"]) / len(h["plazos"])) if h["plazos"] else None,
                      "ultima": h["ultima"], "proveedores": sorted(x for x in h["proveedores"] if x)}
                  for o, h in por.items()}
    return out


def pendientes(codes=None, ref=None):
    """Líneas de OC abiertas de SAP con saldo por ingresar: {código: [{docnum, proveedor, origen, pendiente, fecha,
    entrega, vencida}]}."""
    ref = ref or date.today()
    q = select(SapPurchaseLine).where(SapPurchaseLine.tipo == "OC", SapPurchaseLine.estado == "ABIERTA")
    if codes is not None:
        q = q.where(SapPurchaseLine.product_code.in_(list(codes) or [""]))
    out = defaultdict(list)
    for ln in db().execute(q).scalars():
        pend = (ln.cantidad or 0) - (ln.recibido or 0)
        if pend <= 1e-9:
            continue
        out[ln.product_code].append({"docnum": ln.docnum, "proveedor": ln.proveedor, "origen": origen_de(ln.pais),
                                     "pais": ln.pais, "pendiente": pend, "cantidad": ln.cantidad, "recibido": ln.recibido,
                                     "fecha": ln.fecha, "entrega": ln.fecha_entrega, "descripcion": ln.descripcion,
                                     "vencida": bool(ln.fecha_entrega and ln.fecha_entrega < ref)})
    return out


# ------------------------------------------------------------------ proyección
def _candidatos():
    """Lo que se compra: granel e insumos y la MP (solo Compras nacionales), más todo lo que tenga OC en SAP. Nunca el PT."""
    from .purchasing import es_no_comprable
    from .stock import product_kind
    s = db()
    con_oc = {c for (c,) in s.execute(select(SapPurchaseLine.product_code).where(SapPurchaseLine.tipo == "OC").distinct())}
    out = []
    for p in s.execute(select(Product)).scalars():
        if es_no_comprable(p):
            continue
        if product_kind(p) in ("GR", "MP", "INSUMO") or p.code in con_oc:
            out.append(p)
    return out


def _ov_por_fecha(ref):
    """{código: [(fecha, cantidad, OV)]} de lo que falta salir de las OV abiertas del módulo (sin lo ya reservado)."""
    from .stock import ORDEN_ESTADOS_CERRADOS, line_reserved
    out = defaultdict(list)
    for o in db().execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS + ("BORRADOR",)))).scalars():
        for ln in o.lines:
            if not ln.activa:
                continue
            falta = (ln.cantidad or 0) - (ln.despachado or 0) - line_reserved(ln)
            if falta > 1e-9:
                out[ln.product_code].append((max(o.fecha_compromiso or ref, ref), falta, o.numero))
    return out


def _libre(code):
    from .stock import free_qty, lot_usable, lots_of
    t = 0.0
    for lot in lots_of(code):
        ok, _ = lot_usable(lot)
        if ok:
            t += free_qty(lot)
    return t


def _consumo_diario(p, ref):
    from .purchasing import _salidas_periodo
    periodo = int(p.periodo_analisis_dias or param("periodo_analisis_dias", 15) or 15)
    salidas, fuente = _salidas_periodo(p.code, ref - timedelta(days=periodo), ref)
    return (salidas / periodo if periodo else 0.0), fuente


def _ya_solicitado(codes):
    """Solicitudes de compra del módulo que aún no tienen OC (lo que ya tiene OC está en SAP)."""
    out = defaultdict(float)
    for r in db().execute(select(PurchaseRequest).where(PurchaseRequest.estado.in_(ANTES_DE_OC),
                                                        PurchaseRequest.product_code.in_(list(codes) or [""]))).scalars():
        out[r.product_code] += r.cantidad or 0
    return out


def recomendar(p, hist, dias_quiebre):
    """(origen, motivo) sugerido para traer el producto."""
    if es_mp(p):
        return NACIONAL, "Materia prima: la compra solo Compras nacionales."
    h = {o: x for o, x in (hist or {}).items() if o in (NACIONAL, IMPORTADO)}
    if not h:
        return "", "Sin órdenes de compra en SAP del último año con país del proveedor: definir de dónde traerlo."
    if len(h) == 1:
        o = next(iter(h))
        x = h[o]
        txt = f"Solo se ha comprado {o.lower()} ({x['ordenes']} OC"
        txt += f", plazo {x['plazo_dias']} días" if x["plazo_dias"] is not None else ""
        return o, txt + ")."
    llegan = {o: x for o, x in h.items() if dias_quiebre is None or x["plazo_dias"] is None or x["plazo_dias"] <= dias_quiebre}

    def costo(x):
        return x["costo_unit"] if x["costo_unit"] is not None else float("inf")
    n, i = h[NACIONAL], h[IMPORTADO]
    comp = (f"nacional S/ {n['costo_unit'] or 0:,.4f}/u en {n['plazo_dias'] if n['plazo_dias'] is not None else '—'} días; "
            f"importado S/ {i['costo_unit'] or 0:,.4f}/u en {i['plazo_dias'] if i['plazo_dias'] is not None else '—'} días")
    if len(llegan) == 1:
        o = next(iter(llegan))
        return o, f"Solo {o.lower()} llega antes del quiebre ({dias_quiebre} días): {comp}."
    if llegan:
        o = min(llegan, key=lambda k: costo(llegan[k]))
        return o, f"Las dos llegan a tiempo; {o.lower()} cuesta menos: {comp}."
    o = min(h, key=lambda k: h[k]["plazo_dias"] if h[k]["plazo_dias"] is not None else 10 ** 6)
    return o, f"Ninguna llega antes del quiebre ({dias_quiebre} días); {o.lower()} es la más rápida: {comp}."


def proyeccion(p, ref=None, horizonte=None, ov=None, pend=None, hist=None, solicitado=0.0):
    ref = ref or date.today()
    horizonte = int(horizonte or param("abastecimiento_horizonte_dias", 60) or 60)
    ov = ov if ov is not None else _ov_por_fecha(ref).get(p.code, [])
    pend = pend if pend is not None else pendientes([p.code], ref).get(p.code, [])
    libre = _libre(p.code)
    consumo, fuente = _consumo_diario(p, ref)
    seg = consumo * 30 * float(param("factor_stock_seguridad", 0.3) or 0) if param("usar_stock_seguridad", False) else 0.0
    reserva = (p.stock_minimo or 0) + seg
    salidas, entradas = defaultdict(float), defaultdict(float)
    ovs_dia = defaultdict(list)
    for f, q, num in ov:
        salidas[f] += q
        ovs_dia[f].append((num, q))
    for x in pend:
        entradas[max(x["entrega"] or ref, ref)] += x["pendiente"]
    ultima_ov = max((f for f, _, _ in ov), default=ref)
    saldo, minimo = libre, libre
    quiebre = agotado = None
    serie = []
    for d in range(horizonte + 1):
        dia = ref + timedelta(days=d)
        saldo += entradas.get(dia, 0.0) - salidas.get(dia, 0.0)
        if dia > ultima_ov:
            saldo -= consumo
        minimo = min(minimo, saldo)
        if quiebre is None and saldo < reserva - 1e-9:
            quiebre = dia
        if agotado is None and saldo < -1e-9:
            agotado = dia
        serie.append((dia, round(saldo, 3)))
    dias_q = (quiebre - ref).days if quiebre else None
    org, motivo = recomendar(p, hist, dias_q)
    plazo = ((hist or {}).get(org) or {}).get("plazo_dias") if org else None
    culpables = ovs_dia.get(quiebre, []) if quiebre else []
    if quiebre and not culpables:  # el saldo pudo cruzar la reserva por el consumo diario o por varias OV previas
        culpables = [x for f in sorted(ovs_dia) if f <= quiebre for x in ovs_dia[f]][-3:]
    return {"producto": p, "libre": libre, "reserva": reserva, "stock_minimo": p.stock_minimo or 0, "seguridad": seg,
            "consumo_diario": consumo, "fuente_consumo": fuente, "ov_total": sum(q for _, q, _ in ov), "n_ov": len(ov),
            "por_ingresar": sum(x["pendiente"] for x in pend), "oc_abiertas": pend, "ya_solicitado": solicitado,
            "quiebre": quiebre, "dias_quiebre": dias_q, "agotado": agotado, "saldo_minimo": minimo,
            "ov_quiebre": culpables, "origen": org, "motivo_origen": motivo, "responsable": RESPONSABLE.get(org, "Por definir"),
            "plazo_dias": plazo, "fecha_limite": (quiebre - timedelta(days=plazo)) if quiebre and plazo is not None else None,
            "sugerido": max(round(reserva - minimo - solicitado, 3), 0.0) if quiebre else 0.0,
            "historial": hist or {}, "serie": serie, "horizonte": horizonte}


def tablero(ref=None, origen="", q="", solo_riesgo=True):
    ref = ref or date.today()
    prods = _candidatos()
    if q:
        qq = q.upper()
        prods = [p for p in prods if qq in p.code.upper() or qq in (p.descripcion or "").upper()]
    codes = [p.code for p in prods]
    ov = _ov_por_fecha(ref)
    pend = pendientes(codes, ref)
    hist = historial(codes, ref)
    sol = _ya_solicitado(codes)
    filas = []
    for p in prods:
        if not (ov.get(p.code) or pend.get(p.code) or hist.get(p.code) or p.stock_minimo):
            continue  # sin OV, sin compras y sin mínimo: nada que proyectar
        r = proyeccion(p, ref, ov=ov.get(p.code, []), pend=pend.get(p.code, []), hist=hist.get(p.code), solicitado=sol[p.code])
        if solo_riesgo and not r["quiebre"]:
            continue
        if origen and r["origen"] != origen:
            continue
        filas.append(r)
    filas.sort(key=lambda r: (r["quiebre"] or date.max, r["producto"].code))
    return filas


def ingresos(desde, hasta, origen="", q="", ver="pendientes"):
    """Lo registrado en SAP: OC abiertas con saldo por ingresar (ver=pendientes) o entradas de mercancías del periodo
    (ver=ingresados)."""
    ref = date.today()
    if ver == "ingresados":
        qy = select(SapPurchaseLine).where(SapPurchaseLine.tipo == "RECEPCION", SapPurchaseLine.estado != "CANCELADA",
                                           SapPurchaseLine.fecha >= desde, SapPurchaseLine.fecha <= hasta)
        filas = [{"docnum": x.docnum, "fecha": x.fecha, "proveedor": x.proveedor, "origen": origen_de(x.pais), "pais": x.pais,
                  "codigo": x.product_code, "descripcion": x.descripcion, "cantidad": x.cantidad, "pendiente": 0.0,
                  "entrega": x.fecha, "vencida": False, "valor": (x.total or 0) + (x.igv or 0)}
                 for x in db().execute(qy.order_by(SapPurchaseLine.fecha.desc())).scalars()]
    else:
        filas = []
        for code, xs in pendientes(None, ref).items():
            for x in xs:
                filas.append({"docnum": x["docnum"], "fecha": x["fecha"], "proveedor": x["proveedor"], "origen": x["origen"],
                              "pais": x["pais"], "codigo": code, "descripcion": x["descripcion"], "cantidad": x["cantidad"],
                              "recibido": x["recibido"], "pendiente": x["pendiente"], "entrega": x["entrega"],
                              "vencida": x["vencida"], "valor": None})
        filas.sort(key=lambda f: (f["entrega"] or date.max, f["docnum"]))
    if origen:
        filas = [f for f in filas if f["origen"] == origen]
    if q:
        qq = q.upper()
        filas = [f for f in filas if qq in f["codigo"].upper() or qq in (f["descripcion"] or "").upper()
                 or qq in (f["proveedor"] or "").upper() or qq in f["docnum"]]
    return filas


def origen_por_rol(user):
    """Vista por defecto: Compras ve lo nacional; Importación y su asistente, lo importado."""
    rol = getattr(user, "role_code", "")
    return NACIONAL if rol == "COMPRAS" else IMPORTADO if rol in ("IMPORTACIONES", "ASIST_IMPORTACIONES") else ""
