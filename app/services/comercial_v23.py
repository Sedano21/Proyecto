"""V23 (06-nov-2026): nivel de servicio del mes e indicadores comerciales adicionales.

Nivel de servicio (fórmula indicada por la empresa). La base son las OV que se subieron al sistema y que corresponden
despacharse dentro del periodo, es decir, cuya fecha comprometida cae en él (sin anuladas, borradores ni
regularizaciones observadas):
- OTIF    = OV a tiempo y completas ÷ OV que corresponden despacharse en el periodo.
- On time = OV que salieron hasta su fecha comprometida ÷ OV que corresponden despacharse en el periodo.
- In full = OV que salieron con todas sus líneas completas ÷ OV que corresponden despacharse en el periodo.
Una OV que todavía no salió cuenta en la base y no en el numerador. Por transparencia se informa aparte cuántas aún
están dentro de su plazo (su fecha comprometida no llegó).

Indicadores comerciales adicionales:
- Tasa de recompra = clientes que vuelven a comprar dentro de su frecuencia habitual ÷ clientes activos.
  Cliente activo: con al menos una OV en los últimos «recompra_ventana_dias» días hasta el fin del periodo.
  Frecuencia habitual: promedio de días entre sus OV en esa ventana. Si solo tiene una OV, se usa
  «recompra_frecuencia_defecto_dias». Vuelve a comprar a tiempo si los días desde su última OV no superan la frecuencia
  × (1 + «recompra_tolerancia_pct» %).
- Venta por cliente nuevo (su primera OV es del periodo) y por SKU nuevo en clientes existentes.
- DSO comercial por ejecutivo = deuda de sus clientes ÷ venta diaria promedio de los últimos «dso_ventana_dias» días.
- Precio realizado vs precio base por canal: descuento efectivo = 1 − Σ(precio de venta × cantidad) ÷ Σ(precio de lista ×
  cantidad), solo en líneas con precio de lista.
- Margen de contribución por kg (solo perfiles con costos): margen de contribución de la cascada de margen ÷ kg vendidos.
- Lead time de pedido = días de la emisión de la OV a su entrega (o salida, si no hay entrega registrada).
- Tasa de renegociación = OV con fecha comprometida cambiada o con cambio de fecha solicitado ÷ OV del periodo.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import db
from ..models import AuditLog, Customer, SalesOrder, SalesOrderLine, User
from .core import param

EXCLUIDAS = ("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")
FORMULAS = {
    "otif": "OV a tiempo y completas ÷ OV que se subieron y corresponden despacharse en el periodo",
    "on_time": "OV que salieron hasta su fecha comprometida ÷ OV que corresponden despacharse en el periodo",
    "in_full": "OV que salieron con todas sus líneas completas ÷ OV que corresponden despacharse en el periodo",
    "fill_unidades": "Unidades despachadas (hasta lo pedido) ÷ unidades pedidas de esas OV",
    "fill_lineas": "Líneas despachadas completas ÷ líneas pedidas de esas OV",
}


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def fin_de_mes(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def base_mes(desde, hasta):
    """OV que corresponden despacharse en el periodo (fecha comprometida dentro), con líneas y productos cargados."""
    return [o for o in db().execute(select(SalesOrder).options(
        selectinload(SalesOrder.lines).selectinload(SalesOrderLine.product), selectinload(SalesOrder.customer)).where(
        SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= hasta,
        SalesOrder.estado.notin_(EXCLUIDAS))).scalars()]


def nivel(base, lineas=None, hoy=None):
    """OTIF, On time, In full y fill rate sobre la base (todas las OV que corresponden despacharse)."""
    hoy = hoy or date.today()
    lineas = lineas or (lambda o: [l for l in o.lines if l.activa])
    base = [o for o in base if lineas(o)]
    ot = inf = otif = salieron = en_plazo = 0
    ped = desp = 0.0
    lin = lin_ok = 0
    fallas = []
    for o in base:
        ls = lineas(o)
        salio = o.salida_ts is not None
        a_tiempo = salio and o.salida_ts.date() <= o.fecha_compromiso
        completo = salio and all(l.despachado >= l.cantidad - 1e-9 for l in ls)
        salieron += salio
        ot += a_tiempo
        inf += completo
        otif += a_tiempo and completo
        if not salio and o.fecha_compromiso >= hoy:
            en_plazo += 1
        elif not (a_tiempo and completo):
            fallas.append({"numero": o.numero, "id": o.id, "cliente": o.customer.nombre if o.customer else "",
                           "fecha": o.fecha_compromiso, "salida": o.salida_ts, "a_tiempo": a_tiempo, "completo": completo,
                           "estado": o.estado})
        for l in ls:
            ped += l.cantidad
            desp += min(l.despachado or 0, l.cantidad)
            lin += 1
            lin_ok += (l.despachado or 0) >= l.cantidad - 1e-9
    n = len(base)
    return {"n": n, "salieron": salieron, "en_plazo": en_plazo, "on_time": _pct(ot, n), "in_full": _pct(inf, n),
            "otif": _pct(otif, n), "fill_unidades": _pct(desp, ped), "fill_lineas": _pct(lin_ok, lin),
            "conteos": (ot, inf, otif, n), "fallas": sorted(fallas, key=lambda x: x["fecha"]), "base": "MES"}


def nivel_periodo(desde=None, hasta=None, hoy=None):
    """Nivel de servicio del mes (por defecto, el mes en curso completo)."""
    hoy = hoy or date.today()
    desde = desde or hoy.replace(day=1)
    hasta = hasta or fin_de_mes(desde)
    return nivel(base_mes(desde, hasta), hoy=hoy)


# ---------------------------------------------------------------- indicadores comerciales adicionales

def _kg(l):
    p = l.product
    if p is None:
        return 0.0
    return l.cantidad * (p.peso_kg or (1 if (p.um or "").upper().startswith("K") else 0))


def _vendedor(o, nombres):
    if o.vendedor_id:
        return nombres.get(o.vendedor_id, o.vendedor_nombre or "(sin ejecutivo comercial)")
    if o.vendedor_nombre:
        return o.vendedor_nombre
    if o.customer is not None and o.customer.vendedor_id:
        return nombres.get(o.customer.vendedor_id, "(sin ejecutivo comercial)")
    return "(sin ejecutivo comercial)"


def recompra(hasta, ovs_hist, nombres):
    ventana = int(param("recompra_ventana_dias", 365) or 365)
    defecto = float(param("recompra_frecuencia_defecto_dias", 30) or 30)
    tol = float(param("recompra_tolerancia_pct", 20) or 0)
    fechas = defaultdict(set)
    ejecutivo = {}
    for o in ovs_hist:
        if hasta - timedelta(days=ventana) <= o.fecha_emision <= hasta:
            fechas[o.customer_id].add(o.fecha_emision)
            ejecutivo[o.customer_id] = _vendedor(o, nombres)
    clientes = {c.id: c for c in db().execute(select(Customer).where(Customer.id.in_(list(fechas) or [0]))).scalars()}
    filas, ok = [], 0
    por_ej = defaultdict(lambda: [0, 0])
    for cid, fs in fechas.items():
        fs = sorted(fs)
        frec = (fs[-1] - fs[0]).days / (len(fs) - 1) if len(fs) > 1 else defecto
        frec = max(frec, 1.0)
        dias = (hasta - fs[-1]).days
        a_tiempo = dias <= frec * (1 + tol / 100)
        ok += a_tiempo
        por_ej[ejecutivo[cid]][0] += a_tiempo
        por_ej[ejecutivo[cid]][1] += 1
        if not a_tiempo:
            c = clientes.get(cid)
            filas.append({"cliente": c.nombre if c else cid, "ultima": fs[-1], "frecuencia": round(frec, 1), "dias": dias,
                          "ejecutivo": ejecutivo[cid], "atraso": round(dias - frec, 1)})
    filas.sort(key=lambda x: -x["atraso"])
    return {"tasa": _pct(ok, len(fechas)), "recompran": ok, "activos": len(fechas), "sin_recompra": filas[:30],
            "por_ejecutivo": sorted(((k, _pct(a, b), a, b) for k, (a, b) in por_ej.items()), key=lambda x: (x[1] or 0)),
            "ventana": ventana, "tolerancia": tol, "defecto": defecto}


def nuevos(desde, hasta, ovs_periodo, ovs_previas):
    con_compra = {o.customer_id for o in ovs_previas}
    compro = {(o.customer_id, l.product_code) for o in ovs_previas for l in o.lines if l.activa}
    cli, sku = defaultdict(float), defaultdict(float)
    vistos = set()
    for o in sorted(ovs_periodo, key=lambda x: x.fecha_emision):
        for l in o.lines:
            if not l.activa:
                continue
            v = l.cantidad * (l.precio_unitario or 0)
            if o.customer_id not in con_compra:
                cli[o.customer.nombre] += v
            elif (o.customer_id, l.product_code) not in compro:
                sku[(o.customer.nombre, l.product_code)] += v
                vistos.add((o.customer_id, l.product_code))
    total = sum(l.cantidad * (l.precio_unitario or 0) for o in ovs_periodo for l in o.lines if l.activa)
    sc, ss = sum(cli.values()), sum(sku.values())
    return {"clientes": sorted(cli.items(), key=lambda x: -x[1]), "sku": sorted(sku.items(), key=lambda x: -x[1])[:30],
            "soles_clientes": round(sc, 2), "soles_sku": round(ss, 2), "n_clientes": len(cli), "n_sku": len(sku),
            "pct_clientes": _pct(sc, total), "pct_sku": _pct(ss, total)}


def dso(hasta, nombres, ovs_hist):
    from .finance import statement
    ventana = int(param("dso_ventana_dias", 90) or 90)
    venta = defaultdict(float)
    ej_cliente = {}
    for o in ovs_hist:
        ej_cliente.setdefault(o.customer_id, _vendedor(o, nombres))
        if hasta - timedelta(days=ventana) < o.fecha_emision <= hasta:
            venta[_vendedor(o, nombres)] += sum(l.cantidad * (l.precio_unitario or 0) for l in o.lines if l.activa)
    deuda = defaultdict(float)
    vencida = defaultdict(float)
    for c in db().execute(select(Customer)).scalars():
        st = statement(c, hasta)
        if st["deuda"] <= 0:
            continue
        ej = (nombres.get(c.vendedor_id) if c.vendedor_id else None) or ej_cliente.get(c.id) or "(sin ejecutivo comercial)"
        deuda[ej] += st["deuda"]
        vencida[ej] += st["deuda_vencida"]
    filas = []
    for ej in sorted(set(venta) | set(deuda)):
        vd = venta[ej] / ventana
        filas.append({"ejecutivo": ej, "deuda": round(deuda[ej], 2), "vencida": round(vencida[ej], 2),
                      "venta_diaria": round(vd, 2), "dso": round(deuda[ej] / vd, 1) if vd else None})
    filas.sort(key=lambda x: -(x["dso"] or 0))
    td, tv = sum(deuda.values()), sum(venta.values()) / ventana
    return {"filas": filas, "total": round(td / tv, 1) if tv else None, "ventana": ventana}


def precio_realizado(ovs, ver_costos, desde, hasta):
    from .margin import channel, margin
    from .prices import price_for
    acc = defaultdict(lambda: {"real": 0.0, "lista": 0.0, "sin_lista": 0, "kg": 0.0, "lineas": 0})
    for o in ovs:
        can = channel(o.customer, o) or "(sin canal)"
        for l in o.lines:
            if not l.activa:
                continue
            a = acc[can]
            a["kg"] += _kg(l)
            a["lineas"] += 1
            base, _ = price_for(l.product, o.customer, o.canal_precio or None) if l.product is not None else (None, "")
            if not base:
                a["sin_lista"] += 1
                continue
            a["real"] += l.cantidad * (l.precio_unitario or 0)
            a["lista"] += l.cantidad * base
    mcv = {}
    if ver_costos:
        for x in margin(desde, hasta, "CANAL", "PEDIDO")["filas"]:
            mcv[x["clave"]] = x["mcv"]
    filas = []
    for can, a in sorted(acc.items()):
        f = {"canal": can, "real": round(a["real"], 2), "lista": round(a["lista"], 2), "kg": round(a["kg"], 1),
             "sin_lista": a["sin_lista"], "lineas": a["lineas"],
             "realizado_pct": _pct(a["real"], a["lista"]),
             "descuento_pct": round(100 - 100 * a["real"] / a["lista"], 1) if a["lista"] else None}
        if ver_costos:
            f["mcv"] = mcv.get(can)
            f["mcv_kg"] = round(mcv[can] / a["kg"], 3) if mcv.get(can) is not None and a["kg"] else None
        filas.append(f)
    return filas


def lead_time(ovs):
    nums = [o.numero for o in ovs]
    reneg = set()
    if nums:
        for a in db().execute(select(AuditLog).where(AuditLog.entidad == "SalesOrder", AuditLog.entidad_id.in_(nums),
                                                     AuditLog.accion.in_(("OV_CAMBIO_FECHA_SOLICITADO", "OV_MODIFICADA",
                                                                          "OV_REGULARIZACION_LIBERADA",
                                                                          "OV_REGULARIZACION_FECHA_CORREGIDA")))).scalars():
            d = a.detalle or {}
            if a.accion != "OV_MODIFICADA" or (d.get("antes") or {}).get("fecha_compromiso") != (d.get("despues") or {}).get("fecha_compromiso"):
                reneg.add(a.entidad_id)
    dias = []
    for o in ovs:
        fin = o.entrega_ts or o.salida_ts
        if fin is not None:
            dias.append((fin.date() - o.fecha_emision).days)
    dias.sort()
    return {"promedio": round(sum(dias) / len(dias), 1) if dias else None,
            "mediana": dias[len(dias) // 2] if dias else None, "n": len(dias),
            "renegociadas": len(reneg), "tasa_renegociacion": _pct(len(reneg), len(ovs)), "ovs": len(ovs),
            "lista_renegociadas": sorted(reneg)[:30]}


def indicadores(desde, hasta, filtrar=None, ver_costos=False):
    """Todos los indicadores adicionales del periodo. filtrar(lista_ov) aplica los filtros del informe."""
    filtrar = filtrar or (lambda x: x)
    nombres = {u.id: u.nombre for u in db().execute(select(User)).scalars()}
    hist = filtrar([o for o in db().execute(select(SalesOrder).options(
        selectinload(SalesOrder.lines), selectinload(SalesOrder.customer)).where(
        SalesOrder.fecha_emision <= hasta, SalesOrder.estado.notin_(EXCLUIDAS))).scalars()])
    periodo = [o for o in hist if o.fecha_emision >= desde]
    previas = [o for o in hist if o.fecha_emision < desde]
    return {"recompra": recompra(hasta, hist, nombres), "nuevos": nuevos(desde, hasta, periodo, previas),
            "dso": dso(hasta, nombres, hist), "precio": precio_realizado(periodo, ver_costos, desde, hasta),
            "lead": lead_time(periodo), "ver_costos": ver_costos}
