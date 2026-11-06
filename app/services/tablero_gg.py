"""V22 (06-nov-2026): principales indicadores de cada área para el inicio de Gerencia General y del Gerente General
Adjunto; gastos por área para el Jefe de Administración y Finanzas; embudo comercial.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select

from ..db import db
from ..models import (Absence, Attendance, AreaBudget, CleaningAssignment, Opportunity, ProductionReport, Quote,
                      ReturnReceipt, Route, SalesOrder, StockLot, Ticket, WorkOrder)


def _mes(hoy):
    return hoy.replace(day=1), hoy


def _card(etiqueta, valor, sub="", url=None, nivel=""):
    return {"etiqueta": etiqueta, "valor": valor, "sub": sub, "url": url, "nivel": nivel}


def area_cards(hoy=None, perms=frozenset()):
    """[{area, items:[card]}] con lo más importante de cada área (mes en curso y hoy)."""
    from flask import url_for
    from .orders import order_amount

    def u(ep, perm=None, **kw):
        try:
            return url_for(ep, **kw) if perm is None or perm in perms else None
        except Exception:  # noqa: BLE001
            return None
    hoy = hoy or date.today()
    ini, fin = _mes(hoy)
    out = []
    # Comercial
    ovs = list(db().execute(select(SalesOrder).where(SalesOrder.fecha_emision >= ini, SalesOrder.fecha_emision <= fin,
                                                     SalesOrder.estado != "CANCELADA")).scalars())
    venta = sum(order_amount(o) for o in ovs)
    abiertas = db().execute(select(func.count(SalesOrder.id)).where(SalesOrder.estado.notin_(
        ("CANCELADA", "ENTREGADA", "DESPACHADA", "BORRADOR")))).scalar() or 0
    detenidas = db().execute(select(func.count(SalesOrder.id)).where(SalesOrder.estado.in_(("BLOQUEADA",)))).scalar() or 0
    out.append({"area": "Comercial", "tarjetas": [
        _card("Venta del mes (OV)", f"S/ {venta:,.0f}", f"{len(ovs)} OV", u("com.orders", "ov.ver")),
        _card("OV abiertas", abiertas, "por atender", u("com.orders", "ov.ver")),
        _card("OV bloqueadas", detenidas, "requieren decisión", u("com.orders", "ov.ver"), "alto" if detenidas else "")]})
    # Logística: nivel de servicio del mes
    try:
        from .seguimiento import service_month
        s = service_month(hoy)
        otif = s.get("otif") if isinstance(s, dict) else None
        fill = s.get("fill_rate") if isinstance(s, dict) else None
    except Exception:  # noqa: BLE001
        otif = fill = None
    observados = db().execute(select(func.count(StockLot.id)).where(StockLot.estado.in_(("OBSERVADO", "BLOQUEADO")),
                                                                   StockLot.cantidad > 0)).scalar() or 0
    dev_pend = db().execute(select(func.count(ReturnReceipt.id)).where(ReturnReceipt.estado == "PENDIENTE")).scalar() or 0
    out.append({"area": "Logística y Almacén", "tarjetas": [
        _card("OTIF del mes", f"{otif} %" if otif is not None else "—", "a tiempo y completo", u("seg.service")),
        _card("Fill rate", f"{fill} %" if fill is not None else "—", "", u("seg.service")),
        _card("Lotes observados o bloqueados", observados, "", u("alm.stock", "stock.ver"), "alto" if observados else ""),
        _card("Devoluciones por recibir", dev_pend, "", u("v22.returns", "devoluciones.ver"), "medio" if dev_pend else "")]})
    # Distribución: hoy
    rutas = list(db().execute(select(Route).where(Route.fecha == hoy, Route.estado != "ANULADA")).scalars())
    from .rutas_manual import overload
    sobre = sum(1 for r in rutas if overload(r))
    terceros = sum(1 for r in rutas if r.requiere_externo)
    out.append({"area": "Distribución (hoy)", "tarjetas": [
        _card("Rutas", len(rutas), f"{sum(len(r.stops) for r in rutas)} entregas", u("v22.board", "distribucion.ver")),
        _card("Con sobrecarga", sobre, "peso sobre lo permitido", u("v22.board", "distribucion.ver"), "alto" if sobre else ""),
        _card("Con transporte tercero", terceros, "", u("v22.board", "distribucion.ver"))]})
    # Producción: mes
    partes = list(db().execute(select(ProductionReport).where(ProductionReport.fecha >= ini,
                                                              ProductionReport.fecha <= fin)).scalars())
    rend = [p.rendimiento_pct for p in partes if p.rendimiento_pct]
    en_linea = sum(1 for p in partes if p.fecha == hoy and p.estado in ("EN PROCESO", "PAUSADO"))
    paradas = sum(len(p.pausas or []) for p in partes if p.fecha == hoy)
    out.append({"area": "Producción", "tarjetas": [
        _card("Rendimiento promedio del mes", f"{sum(rend) / len(rend):.1f} %" if rend else "—", f"{len(partes)} partes",
              u("prod.reports", "produccion.ver")),
        _card("Líneas trabajando hoy", en_linea, "", u("prod.reports", "produccion.ver")),
        _card("Paradas hoy", paradas, "", u("prod.reports", "produccion.ver"), "medio" if paradas else "")]})
    # Mantenimiento
    t_abiertos = list(db().execute(select(Ticket).where(Ticket.estado.in_(("ABIERTO", "ASIGNADO", "EN_PROCESO")))).scalars())
    venc = db().execute(select(func.count(WorkOrder.id)).where(WorkOrder.estado.in_(("PROGRAMADA", "ASIGNADA", "EN_PROCESO")),
                                                               WorkOrder.fecha_programada < hoy)).scalar() or 0
    limp = list(db().execute(select(CleaningAssignment).where(CleaningAssignment.fecha == hoy)).scalars())
    prog = sum(c.veces for c in limp)
    hechas = sum(min(len(c.checks or []), c.veces) for c in limp)
    out.append({"area": "Mantenimiento y Limpieza", "tarjetas": [
        _card("Tickets abiertos", len(t_abiertos), f"{sum(1 for t in t_abiertos if t.urgente)} urgentes",
              u("v22.tickets"), "alto" if any(t.urgente for t in t_abiertos) else ""),
        _card("Trabajos vencidos", venc, "", u("mant2.works"), "alto" if venc else ""),
        _card("Limpieza de hoy", f"{hechas}/{prog}" if prog else "—", "realizadas / programadas", u("mant2.cleaning"))]})
    # Personal
    aus = list(db().execute(select(Absence).where(Absence.anulada.is_(False), Absence.desde <= hoy,
                                                  Absence.hasta >= hoy)).scalars())
    tipos = Counter(a.tipo for a in aus)
    marcas = list(db().execute(select(Attendance).where(Attendance.fecha == hoy)).scalars())
    presentes = sum(1 for m in marcas if m.estado in ("ASISTENCIA", "TARDANZA"))
    out.append({"area": "Personal (hoy)", "tarjetas": [
        _card("Asistencia registrada", f"{presentes}/{len(marcas)}" if marcas else "—", "presentes / registrados",
              u("prod.attendance")),
        _card("No disponibles", len(aus), ", ".join(f"{v} {k.replace('_', ' ').lower()}" for k, v in tipos.items()) or "",
              u("v22.absences"), "medio" if aus else "")]})
    # Finanzas: presupuesto
    cons = budget_by_area(hoy)
    sobre_p = [c for c in cons if (c["pct"] or 0) >= 100]
    out.append({"area": "Finanzas", "tarjetas": [
        _card("Presupuesto ejecutado", f"{sum(c['real'] for c in cons):,.0f} / {sum(c['presupuesto'] for c in cons):,.0f}"
              if cons else "—", "S/ real / presupuesto al mes", u("v22.area_spending", "finanzas.gastos_areas")),
        _card("Áreas sobre su presupuesto", len(sobre_p), ", ".join(c["area"] for c in sobre_p),
              u("v22.area_spending", "finanzas.gastos_areas"), "alto" if sobre_p else "")]})
    return out


def budget_by_area(hoy=None):
    from .budget import consumption
    hoy = hoy or date.today()
    out = []
    for b in db().execute(select(AreaBudget).where(AreaBudget.anio == hoy.year).order_by(AreaBudget.area)).scalars():
        c = consumption(b, hoy.month)
        out.append({"budget": b, "area": b.area, "estado": b.estado, "presupuesto": c["presupuesto"], "real": c["real"],
                    "pct": c["pct"], "categorias": c["categorias"]})
    return out


# ------------------------------------------------------------------ embudo comercial
ETAPAS = [("OPORTUNIDADES", "Oportunidades (prospectos)"), ("CONTACTADAS", "Contactadas (visita, llamada o reunión)"),
          ("COTIZADAS", "Cotizadas"), ("NEGOCIACION", "En negociación"), ("GANADAS", "Ganadas"),
          ("OV", "OV registradas"), ("ENTREGADAS", "OV entregadas")]


def funnel(desde, hasta, vendedor_id=None):
    """Embudo comercial: de la oportunidad a la OV entregada, con conversión entre etapas, valor proyectado y motivos
    de pérdida; por ejecutivo."""
    from .orders import order_amount
    q = select(Opportunity).where(func.date(Opportunity.creado_ts) >= desde, func.date(Opportunity.creado_ts) <= hasta)
    if vendedor_id:
        q = q.where(Opportunity.vendedor_id == int(vendedor_id))
    opps = list(db().execute(q).scalars())
    con_cot = {x for x, in db().execute(select(Quote.opportunity_id).where(Quote.opportunity_id.isnot(None))).all()}
    etapa = {
        "OPORTUNIDADES": opps,
        "CONTACTADAS": [o for o in opps if o.actions],
        "COTIZADAS": [o for o in opps if o.estado in ("COTIZADA", "NEGOCIACION", "GANADA") or o.id in con_cot],
        "NEGOCIACION": [o for o in opps if o.estado in ("NEGOCIACION", "GANADA")],
        "GANADAS": [o for o in opps if o.estado == "GANADA"],
    }
    qo = select(SalesOrder).where(SalesOrder.fecha_emision >= desde, SalesOrder.fecha_emision <= hasta,
                                  SalesOrder.estado != "CANCELADA")
    if vendedor_id:
        qo = qo.where(SalesOrder.vendedor_id == int(vendedor_id))
    ovs = list(db().execute(qo).scalars())
    entregadas = [o for o in ovs if o.estado in ("ENTREGADA", "ENTREGA_PARCIAL")]
    filas = []
    prev = None
    for code, nombre in ETAPAS:
        if code == "OV":
            n, valor = len(ovs), sum(order_amount(o) for o in ovs)
        elif code == "ENTREGADAS":
            n, valor = len(entregadas), sum(order_amount(o) for o in entregadas)
        else:
            n, valor = len(etapa[code]), sum(o.proyeccion_mensual or 0 for o in etapa[code])
        # la OV es otro universo (no todas nacen de una oportunidad): no se calcula conversión desde «Ganadas»
        filas.append({"code": code, "nombre": nombre, "n": n, "valor": round(valor, 2),
                      "conv": round(100 * n / prev, 1) if prev and code != "OV" else None})
        prev = n if n else prev
    perdidas = [o for o in opps if o.estado == "PERDIDA"]
    motivos = Counter((o.motivo_cierre or "Sin motivo").strip()[:60] for o in perdidas).most_common(6)
    por_vend = defaultdict(lambda: {"oportunidades": 0, "ganadas": 0, "perdidas": 0, "ov": 0, "venta": 0.0})
    for o in opps:
        k = o.vendedor.nombre if o.vendedor else "Sin ejecutivo"
        por_vend[k]["oportunidades"] += 1
        por_vend[k]["ganadas"] += 1 if o.estado == "GANADA" else 0
        por_vend[k]["perdidas"] += 1 if o.estado == "PERDIDA" else 0
    for o in ovs:
        k = o.vendedor.nombre if getattr(o, "vendedor", None) else "Sin ejecutivo"
        por_vend[k]["ov"] += 1
        por_vend[k]["venta"] += order_amount(o)
    vend = [{"nombre": k, **v, "tasa": round(100 * v["ganadas"] / v["oportunidades"], 1) if v["oportunidades"] else None}
            for k, v in sorted(por_vend.items(), key=lambda x: -x[1]["venta"])]
    tasa = round(100 * len(etapa["GANADAS"]) / len(opps), 1) if opps else None
    return {"filas": filas, "perdidas": len(perdidas), "motivos": motivos, "vendedores": vend, "tasa_cierre": tasa,
            "desde": desde, "hasta": hasta, "tablero": _tablero_embudo(opps, desde, hasta, vendedor_id)}


def _tablero_embudo(opps, desde, hasta, vendedor_id=None):
    """V23: datos del tablero del embudo (adaptado del tablero de prospectos que compartió la empresa): oportunidades
    por producto, por etapa, por ejecutivo, por tipo de cliente (canal), motivo de cierre y oportunidades por día y
    ejecutivo; cada bloque con su lectura («mayor …»)."""
    from .prices import channel_of
    dias = max((hasta - desde).days + 1, 1)
    qq = select(Quote).where(Quote.fecha >= desde, Quote.fecha <= hasta)
    cot = list(db().execute(qq).scalars())
    if vendedor_id:
        ids = {o.id for o in opps}
        cot = [q for q in cot if q.opportunity_id in ids]
    prods = Counter()
    sin_prod = 0
    for o in opps:
        cods = [x.get("product_code") for x in (o.detalle_productos or []) if x.get("product_code")]
        if not cods and (o.productos or "").strip():
            cods = [t.strip()[:30] for t in o.productos.split(",") if t.strip()]
        if not cods:
            sin_prod += 1
        for c in cods:
            prods[c] += 1
    nombres = {}
    from ..models import Product
    for c in prods:
        p = db().get(Product, c)
        nombres[c] = f"{c} {p.descripcion[:22]}" if p else c
    por_producto = [(nombres[c], n) for c, n in prods.most_common(8)]
    estados = ["ABIERTA", "COTIZADA", "NEGOCIACION", "GANADA", "PERDIDA"]
    por_ej = defaultdict(Counter)
    for o in opps:
        por_ej[o.vendedor.nombre if o.vendedor else "Sin ejecutivo"][o.estado] += 1
    ejecutivos = sorted(por_ej)
    canales = Counter((channel_of(o.customer) if o.customer else "") or "Sin canal" for o in opps)
    tipos = Counter({"NUEVO": "Cliente nuevo", "ADICIONAL": "Venta adicional"}.get(o.tipo, o.tipo or "—") for o in opps)
    cierres = Counter()
    for o in opps:
        if o.estado in ("GANADA", "PERDIDA"):
            cierres[("Ganada: " if o.estado == "GANADA" else "Perdida: ") + ((o.motivo_cierre or "sin motivo").strip()[:40])] += 1
    serie_dias = [desde + timedelta(days=i) for i in range(dias)] if dias <= 62 else []
    por_dia = defaultdict(Counter)
    for o in opps:
        por_dia[o.vendedor.nombre if o.vendedor else "Sin ejecutivo"][o.creado_ts.date()] += 1

    def mayor(cnt, total, que):
        if not cnt or not total:
            return ""
        k, v = max(cnt, key=lambda x: x[1]) if isinstance(cnt, list) else cnt.most_common(1)[0]
        return f"Mayor {que}: {k} con {v} ({100 * v / total:.1f} % de {total})."
    total = len(opps)
    return {
        "kpis": {"oportunidades": total, "por_dia": round(total / dias, 1),
                 "proyectado": round(sum(o.proyeccion_mensual or 0 for o in opps), 2), "cotizaciones": len(cot),
                 "ganadas": sum(1 for o in opps if o.estado == "GANADA"),
                 "abiertas": sum(1 for o in opps if o.estado in ("ABIERTA", "COTIZADA", "NEGOCIACION"))},
        "por_producto": por_producto, "sin_producto": sin_prod,
        "lectura_producto": mayor(por_producto, sum(prods.values()), "producto") +
        (f" Alerta: {sin_prod} oportunidad(es) sin producto registrado no se cuentan." if sin_prod else ""),
        "por_ejecutivo": {"labels": ejecutivos, "series": [(e.title(), [por_ej[v][e] for v in ejecutivos]) for e in estados
                                                           if any(por_ej[v][e] for v in ejecutivos)]},
        "lectura_ejecutivo": mayor(Counter({v: sum(c.values()) for v, c in por_ej.items()}), total, "ejecutivo"),
        "canales": canales.most_common(8), "lectura_canal": mayor(canales, total, "tipo de cliente"),
        "tipos": tipos.most_common(), "cierres": cierres.most_common(8),
        "lectura_cierre": mayor(cierres, sum(cierres.values()), "motivo"),
        "por_dia": [(v, [(f"{d:%d}", c[d]) for d in serie_dias]) for v, c in sorted(por_dia.items())] if serie_dias else [],
    }
