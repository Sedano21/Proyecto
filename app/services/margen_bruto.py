"""V24c (07-nov-2026): margen bruto con la metodología de los cierres de margen de la empresa (MB · SEM xx · cierre).

Base: lo despachado en el periodo (OV con salida en el rango), valorizado:
- Venta = cantidad despachada × precio de venta de la línea; las notas de crédito del periodo (rebates) entran como
  venta negativa sin costo, en la subfamilia «REBATE / NOTA DE CRÉDITO».
- Costo de venta = cantidad despachada × costo empresa vigente del SKU (lo carga Costos y Presupuestos).
- Margen bruto = venta − costo de venta; % MB = margen ÷ venta; % CV = costo ÷ venta; kilos = cantidad × peso.
Cortes, como en el Excel: por canal, subfamilia, sub-subfamilia (producto base), cliente y producto (código).
Evolución semanal del % MB por canal (semanas del año) con el cierre de cada mes, y la proyección por canal: PV/kg, CV/kg,
kilos y el precio por kg que se necesitaría para llegar al % MB objetivo del canal («mb_objetivo_por_canal»).
Las líneas sin costo cargado se cuentan aparte (no se inventa el costo).
"""
from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import db
from ..models import CustomerInvoice, SalesOrder, SalesOrderLine
from .core import param

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE",
         "DICIEMBRE"]


def _acc():
    return {"venta": 0.0, "costo": 0.0, "kilos": 0.0, "sin_costo": 0}


def _cierra(nombre, a):
    v, c = a["venta"], a["costo"]
    m = v - c
    return {"nombre": nombre, "venta": round(v, 2), "costo": round(c, 2), "margen": round(m, 2), "kilos": round(a["kilos"], 1),
            "mb_pct": round(100 * m / v, 1) if v else None, "cv_pct": round(100 * c / v, 1) if v else None,
            "pv_kg": round(v / a["kilos"], 3) if a["kilos"] else None, "cv_kg": round(c / a["kilos"], 3) if a["kilos"] else None,
            "sin_costo": a["sin_costo"]}


def _lineas(desde, hasta):
    """(fecha, orden, línea, cantidad despachada) del periodo."""
    d0, d1 = datetime.combine(desde, time.min), datetime.combine(hasta, time.max)
    q = select(SalesOrder).options(selectinload(SalesOrder.lines).selectinload(SalesOrderLine.product),
                                   selectinload(SalesOrder.customer)).where(
        SalesOrder.salida_ts >= d0, SalesOrder.salida_ts <= d1, SalesOrder.estado != "CANCELADA")
    for o in db().execute(q).scalars():
        for l in o.lines:
            if l.activa and (l.despachado or 0) > 0:
                yield o.salida_ts.date(), o, l, min(l.despachado, l.cantidad) if l.cantidad else l.despachado


def _venta(l, q):
    """Venta de lo despachado, neta del descuento de la línea en proporción a lo despachado."""
    desc = (l.descuento or 0) * (q / l.cantidad) if l.cantidad else 0
    return q * (l.precio_unitario or 0) - desc


def calcular(desde=None, hasta=None, canal=""):
    from .costs import cost_for_line
    from .reports import order_channel
    hoy = date.today()
    desde = desde or hoy.replace(day=1)
    hasta = hasta or hoy
    grupos = {k: defaultdict(_acc) for k in ("canal", "subfamilia", "subsubfamilia", "cliente", "producto")}
    total = _acc()
    for _f, o, l, q in _lineas(desde, hasta):
        can = order_channel(o) or "(sin canal)"
        if canal and can != canal:
            continue
        p = l.product
        venta = _venta(l, q)
        cu = cost_for_line(l)
        costo = q * cu if cu is not None else 0.0
        kg = q * ((p.peso_kg or (1 if (p.um or "").upper().startswith("K") else 0)) if p else 0)
        claves = {"canal": can, "subfamilia": ((p.subfamilia or p.familia) if p else "") or "(en blanco)",
                  "subsubfamilia": (p.producto_base if p else "") or "(en blanco)", "cliente": o.customer.nombre,
                  "producto": f"{l.product_code} · {(p.descripcion if p else '')[:40]}"}
        for k, v in claves.items():
            a = grupos[k][v]
            a["venta"] += venta
            a["costo"] += costo
            a["kilos"] += kg
            a["sin_costo"] += cu is None
        total["venta"] += venta
        total["costo"] += costo
        total["kilos"] += kg
        total["sin_costo"] += cu is None
    # rebates / notas de crédito del periodo: venta negativa sin costo
    for nc in db().execute(select(CustomerInvoice).where(CustomerInvoice.tipo == "NOTA_CREDITO", CustomerInvoice.estado != "ANULADA",
                                                         CustomerInvoice.fecha >= desde, CustomerInvoice.fecha <= hasta)).scalars():
        from .prices import channel_of
        can = channel_of(nc.customer) or "(sin canal)"
        if canal and can != canal:
            continue
        for k, v in {"canal": can, "subfamilia": "REBATE / NOTA DE CRÉDITO", "subsubfamilia": "REBATE / NOTA DE CRÉDITO",
                     "cliente": nc.customer.nombre, "producto": "REBATE / NOTA DE CRÉDITO"}.items():
            grupos[k][v]["venta"] -= nc.monto
        total["venta"] -= nc.monto
    out = {k: sorted((_cierra(n, a) for n, a in g.items()), key=lambda x: -x["margen"]) for k, g in grupos.items()}
    return {"desde": desde, "hasta": hasta, "filtro_canal": canal, "total": _cierra("TOTAL", total), **out}


def evolucion(anio=None, hasta=None):
    """% MB por canal y semana del año, con el cierre de cada mes (como la hoja EV-MB)."""
    from .costs import cost_for_line
    from .reports import order_channel
    hasta = hasta or date.today()
    anio = anio or hasta.year
    sem = defaultdict(lambda: defaultdict(_acc))
    mes = defaultdict(lambda: defaultdict(_acc))
    for f, o, l, q in _lineas(date(anio, 1, 1), hasta):
        cu = cost_for_line(l)
        if cu is None:
            continue
        can = order_channel(o) or "(sin canal)"
        for d in (sem[f.isocalendar()[1]][can], mes[f.month][can]):
            d["venta"] += _venta(l, q)
            d["costo"] += q * cu
    canales = sorted({c for s in sem.values() for c in s} | {c for m in mes.values() for c in m})
    columnas = []
    for m in range(1, hasta.month + 1):
        semanas = sorted({w for w in sem if date.fromisocalendar(anio, w, 1).month == m})
        columnas += [("SEM %02d" % w, "S", w) for w in semanas] + [(f"C. {MESES[m - 1]}", "M", m)]

    def pct(a):
        return round(100 * (a["venta"] - a["costo"]) / a["venta"], 1) if a["venta"] else None
    filas = []
    for c in canales:
        filas.append({"canal": c, "valores": [pct((sem if t == "S" else mes)[k].get(c, _acc())) for _n, t, k in columnas]})
    return {"anio": anio, "columnas": [n for n, _t, _k in columnas], "tipos": [t for _n, t, _k in columnas], "filas": filas}


def proyeccion(d):
    """Por canal: PV/kg y CV/kg actuales, % MB actual, objetivo y PV/kg necesario para alcanzarlo."""
    obj = param("mb_objetivo_por_canal", {}) or {}
    filas = []
    for c in d["canal"]:
        o = obj.get(c["nombre"])
        nec = round(c["cv_kg"] / (1 - float(o) / 100), 3) if o is not None and c["cv_kg"] and float(o) < 100 else None
        filas.append(dict(c, objetivo=o, pv_kg_objetivo=nec,
                          brecha_pv_kg=round(nec - c["pv_kg"], 3) if nec is not None and c["pv_kg"] else None))
    return filas


def excel(d, ev):
    """Excel con las hojas RESULTADOS (los cinco cortes lado a lado) y EV-MB."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "RESULTADOS"
    cortes = [("canal", "CANAL"), ("subfamilia", "SUB FAMILIA"), ("subsubfamilia", "SUB SUB FAMILIA"), ("cliente", "CLIENTE"),
              ("producto", "PRODUCTO")]
    col = 1
    azul = PatternFill("solid", fgColor="1F3864")
    for k, titulo in cortes:
        ws.cell(1, col, f"MARGEN BRUTO POR {titulo}").font = Font(bold=True)
        for j, h in enumerate([titulo, "VENTA", "COSTO VENTA", "MARGEN", "KILOS", "% MB", "% CV"]):
            c = ws.cell(2, col + j, h)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), azul
        for i, r in enumerate(d[k] + [d["total"]], start=3):
            for j, v in enumerate([r["nombre"], r["venta"], r["costo"], r["margen"], r["kilos"],
                                   (r["mb_pct"] or 0) / 100, (r["cv_pct"] or 0) / 100]):
                c = ws.cell(i, col + j, v)
                if j >= 5:
                    c.number_format = "0.0%"
        col += 8
    w2 = wb.create_sheet("EV-MB")
    w2.append(["EVOLUCIÓN SEMANAL DEL % MB POR CANAL", ev["anio"]])
    w2.append(["CANAL"] + ev["columnas"])
    for f in ev["filas"]:
        w2.append([f["canal"]] + [(v / 100 if v is not None else None) for v in f["valores"]])
        for c in w2[w2.max_row][1:]:
            c.number_format = "0.0%"
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
