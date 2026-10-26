"""Margen, objetivos de venta e incentivos (ronda 23-oct-2026; archivo de ventas y margen 2026).

Cascada por cliente y mes (las tasas se configuran por defecto, por canal y por cliente en Configuración comercial; el
cliente prevalece sobre el canal):
  VENTA – COSTO DE VENTA = MARGEN BRUTO
  – rebate comercial – logística centralizada – B2B – no devolución (% de la venta) = inversión fija
  – mercaderismo y otras inversiones (monto mensual) = MARGEN DE CONTRIBUCIÓN VARIABLE
  – gasto administrativo – gasto de venta – gasto financiero (% de la venta) = UTILIDAD ANTES DE IMPUESTOS
  – impuesto a la renta (solo si es positiva) = UTILIDAD NETA
La venta es lo facturado (facturas menos notas de crédito); si se elige la base «pedido», la venta real de las OV
(abiertas y cerradas, sin canceladas). El costo sale del costo empresa vigente de cada línea de la OV."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Customer, CustomerInvoice, IncentiveRule, MarginInvestment, SalesOrder, SalesTarget, User)
from .core import BusinessError, audit, has_perm, param, set_param

TASAS = [("rebate_comercial_pct", "Rebate comercial"), ("logistica_pct", "Logística centralizada"), ("b2b_pct", "B2B"),
         ("no_devolucion_pct", "No devolución")]
GASTOS = [("gasto_adm_pct", "Gasto administrativo"), ("gasto_venta_pct", "Gasto de venta"),
          ("gasto_fin_pct", "Gasto financiero")]
CLAVES = [k for k, _ in TASAS + GASTOS]
BASES = {"FACTURADO": "Facturado (facturas – notas de crédito)", "PEDIDO": "Venta real de las OV (sin canceladas)"}


def config():
    c = param("margen_config", {}) or {}
    c.setdefault("defecto", {})
    c.setdefault("canales", {})
    c.setdefault("clientes", {})
    c.setdefault("ir_pct", 29.5)
    return c


def channel(customer, order=None):
    from .prices import channel_of
    return (order.canal_precio if order is not None and order.canal_precio else channel_of(customer)) or "(sin canal)"


def rates_for(customer, canal):
    c = config()
    out = {k: float(c["defecto"].get(k) or 0) for k in CLAVES}
    for nivel in (c["canales"].get(canal) or {}, c["clientes"].get(customer.ruc) or {}):
        for k in CLAVES:
            if nivel.get(k) not in (None, ""):
                out[k] = float(nivel[k])
    return out


def save_rates(user, alcance, clave, valores, ir_pct=None):
    """alcance: DEFECTO / CANAL / CLIENTE. valores: {clave: % o vacío (hereda)}."""
    if not has_perm(user, "comercial.configurar"):
        raise BusinessError("La configuración comercial la edita el Jefe Comercial.")
    c = config()
    fila = {}
    for k in CLAVES:
        v = valores.get(k)
        if v in (None, ""):
            continue
        try:
            v = float(str(v).replace(",", "."))
        except ValueError:
            raise BusinessError(f"{k}: indique un porcentaje numérico.")
        if v < 0 or v > 100:
            raise BusinessError(f"{k}: el porcentaje debe estar entre 0 y 100.")
        fila[k] = v
    if alcance == "DEFECTO":
        c["defecto"] = {k: fila.get(k, 0) for k in CLAVES}
    elif alcance == "CANAL":
        if not clave:
            raise BusinessError("Elija el canal.")
        if fila:
            c["canales"][clave] = fila
        else:
            c["canales"].pop(clave, None)
    elif alcance == "CLIENTE":
        cust = db().get(Customer, int(clave)) if str(clave or "").isdigit() else None
        if cust is None:
            raise BusinessError("Elija el cliente.")
        if fila:
            c["clientes"][cust.ruc] = fila
        else:
            c["clientes"].pop(cust.ruc, None)
    else:
        raise BusinessError("Alcance inválido.")
    if ir_pct not in (None, ""):
        c["ir_pct"] = float(ir_pct)
    set_param("margen_config", c, user)
    return c


def save_investment(user, customer_id, mes, monto, concepto="MERCADERISMO"):
    if not has_perm(user, "comercial.configurar"):
        raise BusinessError("La configuración comercial la edita el Jefe Comercial.")
    cust = db().get(Customer, int(customer_id or 0))
    if cust is None:
        raise BusinessError("Elija el cliente.")
    if not mes or len(mes) != 7:
        raise BusinessError("Indique el mes (AAAA-MM).")
    concepto = (concepto or "MERCADERISMO").strip().upper()
    inv = db().execute(select(MarginInvestment).where(MarginInvestment.customer_id == cust.id, MarginInvestment.mes == mes,
                                                      MarginInvestment.concepto == concepto)).scalars().first()
    monto = float(monto or 0)
    if inv is None:
        inv = MarginInvestment(customer_id=cust.id, mes=mes, concepto=concepto, monto=monto, user_id=user.id)
        db().add(inv)
    inv.monto = monto
    inv.user_id = user.id
    audit(user, "MARGEN_INVERSION", "Customer", cust.ruc, {"mes": mes, "concepto": concepto, "monto": monto})
    return inv


def _order_cost_ratio(o):
    """Costo / venta de la OV (líneas con costo vigente). None si no hay costo."""
    from .costs import cost_for_line
    venta = costo = 0.0
    sin = False
    for l in o.lines:
        if not l.activa:
            continue
        c = cost_for_line(l)
        v = l.cantidad * (l.precio_unitario or 0)
        if c is None:
            sin = True
            continue
        venta += v
        costo += c * l.cantidad
    return (costo / venta if venta else None), sin


def _base_rows(desde, hasta, base):
    """Filas (cliente, OV|None, mes, venta, costo, sin_costo) según la base."""
    rows = []
    if base == "PEDIDO":
        from .orders import order_amount
        for o in db().execute(select(SalesOrder).where(SalesOrder.fecha_emision >= desde, SalesOrder.fecha_emision <= hasta,
                                                       SalesOrder.estado.notin_(["CANCELADA", "BORRADOR"]))).scalars():
            venta = order_amount(o)
            ratio, sin = _order_cost_ratio(o)
            rows.append((o.customer, o, f"{o.fecha_emision:%Y-%m}", venta, venta * ratio if ratio is not None else 0,
                         sin or ratio is None))
        return rows
    for i in db().execute(select(CustomerInvoice).where(CustomerInvoice.fecha >= desde, CustomerInvoice.fecha <= hasta,
                                                        CustomerInvoice.estado != "ANULADA")).scalars():
        signo = -1 if i.tipo == "NOTA_CREDITO" else 1
        ratio, sin = _order_cost_ratio(i.order) if i.order is not None else (None, True)
        venta = signo * i.monto
        rows.append((i.customer, i.order, f"{i.fecha:%Y-%m}", venta, venta * ratio if ratio is not None else 0,
                     sin or ratio is None))
    return rows


def _vendedor(customer, order):
    if order is not None and (order.vendedor_nombre or order.vendedor_id):
        if order.vendedor_id:
            u = db().get(User, order.vendedor_id)
            return u.nombre if u else order.vendedor_nombre
        return order.vendedor_nombre
    return customer.vendedor.nombre if customer.vendedor else "(sin vendedor)"


def _cascade(acc, ir_pct):
    v = acc["venta"]
    mb = v - acc["costo"]
    fija = sum(acc[k] for k, _ in TASAS)
    mcv = mb - fija - acc["inversion"]
    gastos = sum(acc[k] for k, _ in GASTOS)
    uai = mcv - gastos
    ir = max(0.0, uai * ir_pct / 100.0)
    un = uai - ir

    def pct(x):
        return round(100.0 * x / v, 2) if v else None
    return dict(acc, margen_bruto=round(mb, 2), inversion_fija=round(fija, 2), mcv=round(mcv, 2), gastos=round(gastos, 2),
                uai=round(uai, 2), ir=round(ir, 2), utilidad_neta=round(un, 2), pct_mb=pct(mb), pct_mcv=pct(mcv),
                pct_un=pct(un), pct_costo=pct(acc["costo"]))


def margin(desde=None, hasta=None, agrupar="CANAL", base="FACTURADO", canal="", customer_id=None, vendedor=""):
    """Cascada agrupada por CANAL, CLIENTE, VENDEDOR o MES."""
    hoy = date.today()
    desde = desde or hoy.replace(day=1)
    hasta = hasta or hoy
    base = base if base in BASES else "FACTURADO"
    ir_pct = float(config().get("ir_pct") or 0)
    grupos = defaultdict(lambda: defaultdict(float))
    meses_cliente = set()
    sin_costo = 0
    for cust, order, mes, venta, costo, sin in _base_rows(desde, hasta, base):
        can = channel(cust, order)
        ven = _vendedor(cust, order)
        if canal and can != canal or customer_id and cust.id != int(customer_id) or vendedor and ven != vendedor:
            continue
        clave = {"CANAL": can, "CLIENTE": cust.nombre, "VENDEDOR": ven, "MES": mes}.get(agrupar, can)
        r = rates_for(cust, can)
        g = grupos[clave]
        g["venta"] += venta
        g["costo"] += costo
        for k in CLAVES:
            g[k] += venta * r[k] / 100.0
        g["docs"] += 1
        sin_costo += 1 if sin else 0
        meses_cliente.add((cust.id, mes, clave))
    # inversión adicional (mercaderismo) de los clientes y meses con venta en el grupo
    meses = sorted({m for _, m, _ in meses_cliente})
    if meses:
        invs = defaultdict(float)
        for x in db().execute(select(MarginInvestment).where(MarginInvestment.mes.in_(meses))).scalars():
            invs[(x.customer_id, x.mes)] += x.monto
        vistos = set()
        for cid, mes, clave in meses_cliente:
            if (cid, mes, clave) in vistos:
                continue
            vistos.add((cid, mes, clave))
            grupos[clave]["inversion"] += invs.get((cid, mes), 0.0)
    filas = []
    total = defaultdict(float)
    for clave, acc in grupos.items():
        acc.setdefault("inversion", 0.0)
        filas.append(dict(_cascade(acc, ir_pct), clave=clave))
        for k, v in acc.items():
            total[k] += v
    filas.sort(key=lambda f: -f["venta"])
    tot = _cascade(dict(total, inversion=total.get("inversion", 0.0)), ir_pct) if filas else None
    return {"desde": desde, "hasta": hasta, "agrupar": agrupar, "base": base, "filas": filas, "total": tot,
            "sin_costo": sin_costo, "ir_pct": ir_pct, "tasas": TASAS, "gastos": GASTOS}


# ------------------------------------------------------------------ objetivos de venta
def save_target(user, mes, alcance, clave, soles, kg=None, nuevos_clientes=None, nuevos_sku=None):
    if not (has_perm(user, "comercial.configurar") or has_perm(user, "objetivos.registrar")):
        raise BusinessError("Los objetivos los registran el Coordinador, el Jefe o el Gerente Comercial.")
    alcance = (alcance or "").upper()
    if alcance not in ("GENERAL", "CANAL", "VENDEDOR"):
        raise BusinessError("Alcance inválido.")
    if not mes or len(mes) != 7:
        raise BusinessError("Indique el mes (AAAA-MM).")
    clave = "" if alcance == "GENERAL" else str(clave or "").strip()
    if alcance != "GENERAL" and not clave:
        raise BusinessError("Elija el canal o el vendedor.")
    t = db().execute(select(SalesTarget).where(SalesTarget.mes == mes, SalesTarget.alcance == alcance,
                                               SalesTarget.clave == clave)).scalars().first()
    if t is None:
        t = SalesTarget(mes=mes, alcance=alcance, clave=clave)
        db().add(t)
    try:
        t.soles = float(soles or 0)
        t.kg = float(kg) if kg not in (None, "") else None
        t.nuevos_clientes = int(nuevos_clientes) if nuevos_clientes not in (None, "") else None
        t.nuevos_sku = int(nuevos_sku) if nuevos_sku not in (None, "") else None
    except ValueError:
        raise BusinessError("Valores del objetivo inválidos.")
    if t.soles < 0 or (t.kg or 0) < 0 or (t.nuevos_clientes or 0) < 0 or (t.nuevos_sku or 0) < 0:
        raise BusinessError("Los objetivos no pueden ser negativos.")
    t.user_id = user.id
    audit(user, "OBJETIVO_VENTA", "SalesTarget", f"{mes}/{alcance}/{clave}",
          {"soles": t.soles, "kg": t.kg, "nuevos_clientes": t.nuevos_clientes, "nuevos_sku": t.nuevos_sku})
    return t


def _month_bounds(mes):
    y, m = int(mes[:4]), int(mes[5:7])
    ini = date(y, m, 1)
    fin = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return ini, fin


def targets_progress(mes=None):
    """Avance contra objetivo por general, canal y vendedor: facturado y venta real (pedidos) del mes, por semana."""
    mes = mes or f"{date.today():%Y-%m}"
    ini, fin = _month_bounds(mes)
    fact = margin(ini, fin, "CANAL", "FACTURADO")
    ped = margin(ini, fin, "CANAL", "PEDIDO")
    fact_v = margin(ini, fin, "VENDEDOR", "FACTURADO")
    ped_v = margin(ini, fin, "VENDEDOR", "PEDIDO")
    usuarios = {str(u.id): u.nombre for u in db().execute(select(User)).scalars()}
    objetivos = list(db().execute(select(SalesTarget).where(SalesTarget.mes == mes)).scalars())
    real = {"GENERAL": {"": ((fact["total"] or {}).get("venta", 0), (ped["total"] or {}).get("venta", 0))},
            "CANAL": {f["clave"]: (f["venta"], 0) for f in fact["filas"]},
            "VENDEDOR": {f["clave"]: (f["venta"], 0) for f in fact_v["filas"]}}
    for f in ped["filas"]:
        a = real["CANAL"].get(f["clave"], (0, 0))
        real["CANAL"][f["clave"]] = (a[0], f["venta"])
    for f in ped_v["filas"]:
        a = real["VENDEDOR"].get(f["clave"], (0, 0))
        real["VENDEDOR"][f["clave"]] = (a[0], f["venta"])
    filas = []
    for t in sorted(objetivos, key=lambda x: ({"GENERAL": 0, "CANAL": 1, "VENDEDOR": 2}[x.alcance], x.clave)):
        nombre = usuarios.get(t.clave, t.clave) if t.alcance == "VENDEDOR" else (t.clave or "General")
        f, p = real[t.alcance].get(nombre if t.alcance == "VENDEDOR" else t.clave, (0, 0))
        filas.append({"t": t, "nombre": nombre, "facturado": round(f, 2), "pedido": round(p, 2),
                      "avance": round(100 * f / t.soles, 1) if t.soles else None,
                      "avance_pedido": round(100 * p / t.soles, 1) if t.soles else None})
    dias = (min(date.today(), fin) - ini).days + 1
    esperado = round(100.0 * max(dias, 0) / ((fin - ini).days + 1), 1)
    semanas = []
    d = ini
    while d <= fin:
        h = min(d + timedelta(days=6 - d.weekday()), fin)
        semanas.append((d, h, (margin(d, h, "CANAL", "FACTURADO")["total"] or {}).get("venta", 0)))
        d = h + timedelta(days=1)
    return {"mes": mes, "filas": filas, "esperado_pct": esperado, "semanas": semanas}


# ------------------------------------------------------------------ incentivos
def save_rule(user, datos, rule=None):
    if not has_perm(user, "comercial.configurar"):
        raise BusinessError("Las reglas de incentivo las configura el Jefe Comercial.")
    base = (datos.get("base") or "VENTA").upper()
    if base not in ("VENTA", "MARGEN_BRUTO", "MARGEN_CONTRIB"):
        raise BusinessError("Base inválida.")
    try:
        pct = float(datos.get("pct"))
    except (TypeError, ValueError):
        raise BusinessError("Indique el % de incentivo.")
    if pct < 0 or pct > 100:
        raise BusinessError("El % debe estar entre 0 y 100.")

    def _num(k):
        v = str(datos.get(k) or "").strip()
        return float(v) if v else None

    def _fecha(k):
        v = str(datos.get(k) or "").strip()
        return date.fromisoformat(v) if v else None
    if rule is None:
        rule = IncentiveRule()
        db().add(rule)
    rule.canal = (datos.get("canal") or "").strip()
    v = str(datos.get("vendedor_id") or "").strip()
    rule.vendedor_id = int(v) if v else None
    rule.base, rule.pct = base, pct
    rule.cumplimiento_min_pct = _num("cumplimiento_min_pct")
    rule.tope = _num("tope")
    rule.desde, rule.hasta = _fecha("desde"), _fecha("hasta")
    rule.activo = str(datos.get("activo", "1")) in ("1", "on", "true")
    rule.observacion = (datos.get("observacion") or "").strip()
    rule.user_id = user.id
    db().flush()
    audit(user, "INCENTIVO_REGLA", "IncentiveRule", rule.id, {"canal": rule.canal, "vendedor": rule.vendedor_id, "base": base,
                                                               "pct": pct, "min": rule.cumplimiento_min_pct, "tope": rule.tope})
    return rule


def _rule_for(rules, vendedor_id, canal, dia):
    vigentes = [r for r in rules if r.activo and (r.desde is None or r.desde <= dia) and (r.hasta is None or r.hasta >= dia)]
    for cond in ((lambda r: r.vendedor_id == vendedor_id and r.canal == canal),
                 (lambda r: r.vendedor_id == vendedor_id and not r.canal),
                 (lambda r: r.vendedor_id is None and r.canal == canal),
                 (lambda r: r.vendedor_id is None and not r.canal)):
        m = [r for r in vigentes if cond(r)]
        if m:
            return m[0]
    return None


def incentives(mes=None):
    """Incentivo por vendedor y canal del mes, según las reglas configuradas (sin reglas no hay incentivo)."""
    mes = mes or f"{date.today():%Y-%m}"
    ini, fin = _month_bounds(mes)
    rules = list(db().execute(select(IncentiveRule).order_by(IncentiveRule.id)).scalars())
    usuarios = {u.nombre: u for u in db().execute(select(User)).scalars()}
    ir_pct = float(config().get("ir_pct") or 0)
    acc = defaultdict(lambda: defaultdict(float))
    for cust, order, _, venta, costo, _ in _base_rows(ini, fin, "FACTURADO"):
        can = channel(cust, order)
        ven = _vendedor(cust, order)
        r = rates_for(cust, can)
        a = acc[(ven, can)]
        a["venta"] += venta
        a["costo"] += costo
        for k in CLAVES:
            a[k] += venta * r[k] / 100.0
        a.setdefault("inversion", 0.0)
    objetivos = {t.clave: t.soles for t in db().execute(select(SalesTarget).where(SalesTarget.mes == mes,
                                                                                   SalesTarget.alcance == "VENDEDOR")).scalars()}
    venta_vend = defaultdict(float)
    for (ven, _), a in acc.items():
        venta_vend[ven] += a["venta"]
    filas = []
    for (ven, can), a in sorted(acc.items()):
        u = usuarios.get(ven)
        c = _cascade(a, ir_pct)
        regla = _rule_for(rules, u.id if u else None, can, fin)
        obj = objetivos.get(str(u.id)) if u else None
        cumpl = round(100 * venta_vend[ven] / obj, 1) if obj else None
        base = {"VENTA": c["venta"], "MARGEN_BRUTO": c["margen_bruto"], "MARGEN_CONTRIB": c["mcv"]}[regla.base] if regla else 0
        monto, nota = 0.0, ""
        if regla is None:
            nota = "Sin regla configurada"
        elif regla.cumplimiento_min_pct and (cumpl is None or cumpl < regla.cumplimiento_min_pct):
            nota = f"No alcanza el {regla.cumplimiento_min_pct:g} % del objetivo"
        else:
            monto = max(base, 0) * regla.pct / 100.0
            if regla.tope is not None and monto > regla.tope:
                monto, nota = regla.tope, "Con tope"
        filas.append({"vendedor": ven, "canal": can, "venta": c["venta"], "base": base, "regla": regla,
                      "cumplimiento": cumpl, "incentivo": round(monto, 2), "nota": nota})
    return {"mes": mes, "filas": filas, "total": round(sum(f["incentivo"] for f in filas), 2), "reglas": rules}
