"""V24 (06-nov-2026): perfil Costos y Presupuestos: costo por SKU frente al costo de reposición y al precio de venta.

Por cada SKU (en S/ por kg, con el tipo de cambio SUNAT del día para lo que se compra en dólares):
- costo registrado: el que carga Costos y Presupuestos (tabla de costos vigentes);
- costo de reposición: lo que costaría comprarlo hoy. Para granel y materia prima, la cotización nacional elegida (o la
  última) y el precio de las importaciones con sus gastos extra prorrateados; se toma el menor disponible. Para producto
  terminado, la suma de sus componentes de la lista de materiales con su costo de reposición (o su costo registrado si
  no hay reposición);
- precio de venta realizado: promedio de las OV de los últimos «dias» días.
Lectura: si la reposición supera al costo registrado más «costo_reposicion_tolerancia_pct», se recomienda actualizar el
costo o revisar el precio de venta; si bajó, ese producto «compensa». El impacto en S/ = diferencia por kg × kg vendidos
en el periodo; se suma lo que sube y lo que baja para ver si se compensa entre productos.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import BOMLine, ImportFollowup, Product, SalesOrder, SalesOrderLine, SupplierQuote
from . import alerts
from .core import param


def _kg_unit(p):
    return 1.0 if (p.um or "").upper().startswith("K") else float(p.peso_kg or 0)


def reposicion_mp(code, tc=None):
    """Costo de reposición por kg de granel / MP: (origen, S/ por kg) o (None, None)."""
    from .compras_v24 import precio_soles
    from .importaciones_v24 import total_gastos
    from .tipo_cambio import rate
    tc = tc or rate()
    cands = []
    qs = list(db().execute(select(SupplierQuote).where(SupplierQuote.product_code == code)
                           .order_by(SupplierQuote.elegida.desc(), SupplierQuote.fecha.desc(), SupplierQuote.id.desc())).scalars())
    for q in qs:
        if (q.um or "").upper() in ("KG", "KILOGRAMO", "TM", "T"):
            ps = precio_soles(q)
            if ps:
                cands.append((f"Cotización nacional {q.proveedor} ({q.fecha:%d/%m})", ps / (1000 if (q.um or "").upper() in ("TM", "T") else 1)))
                break
    f = db().execute(select(ImportFollowup).where(ImportFollowup.codigo_sap == code, ImportFollowup.precio.isnot(None))
                     .order_by(ImportFollowup.id.desc())).scalars().first()
    if f is not None and tc:
        factor = 1000 if (f.um or "TM").upper() in ("TM", "T", "TON") else 1
        mon = 1 if (f.moneda or "USD") in ("PEN", "S/") else tc
        extra = total_gastos(f, tc) / f.kg if f.kg else 0
        cands.append((f"Importación {f.contrato}", (f.precio / factor + extra) * mon))
    if not cands:
        return None, None
    return min(cands, key=lambda x: x[1])


def reposicion(p, tc=None, _prof=0):
    """(origen, S/ por kg) del SKU."""
    from .costs import cost_per_kg
    if p.code.startswith(("GR", "MP")) or (p.tipo or "") in ("GR", "MP"):
        return reposicion_mp(p.code, tc)
    if _prof > 3:
        return None, None
    from .production import active_bom
    v = active_bom()
    if v is None:
        return None, None
    comps = list(db().execute(select(BOMLine).where(BOMLine.version_id == v.id, BOMLine.padre == p.code)).scalars())
    if not comps:
        return None, None
    total, usados = 0.0, 0
    for b in comps:
        cp = db().get(Product, b.componente)
        if cp is None:
            continue
        ratio = (b.cantidad or 0) / (b.cantidad_bom or 1)
        _o, rk = reposicion(cp, tc, _prof + 1) if cp.code.startswith(("GR", "MP")) else (None, None)
        ck = rk if rk is not None else cost_per_kg(cp) if _kg_unit(cp) else None
        if ck is None:
            from .costs import current_cost
            c = current_cost(cp.code)
            unit = c.get("UND")
            if unit is not None:
                total += unit.costo * ratio
                usados += 1
            continue
        total += ck * ratio * (_kg_unit(cp) or 1)
        usados += 1
    kg = _kg_unit(p)
    if not usados or not kg:
        return None, None
    return "Lista de materiales con costos de reposición", total / kg


def precio_venta_kg(p, desde, hasta):
    v = kg = 0.0
    for l in db().execute(select(SalesOrderLine).join(SalesOrder).where(
            SalesOrderLine.product_code == p.code, SalesOrderLine.activa.is_(True), SalesOrder.fecha_emision >= desde,
            SalesOrder.fecha_emision <= hasta, SalesOrder.estado.notin_(("CANCELADA", "BORRADOR")))).scalars():
        v += l.cantidad * (l.precio_unitario or 0)
        kg += l.cantidad * _kg_unit(p)
    return (v / kg if kg else None), kg


def analisis(dias=30, hoy=None):
    from .costs import cost_per_kg
    from .orders import condicion_vendible
    from .tipo_cambio import rate, ultimo
    hoy = hoy or date.today()
    desde = hoy - timedelta(days=dias)
    tc = rate()
    tol = float(param("costo_reposicion_tolerancia_pct", 5) or 0)
    filas = []
    for p in db().execute(select(Product).where(condicion_vendible(True)).order_by(Product.code)).scalars():
        costo = cost_per_kg(p) if _kg_unit(p) else None
        origen, rep = reposicion(p, tc)
        pv, kg = precio_venta_kg(p, desde, hoy)
        if costo is None and rep is None and pv is None:
            continue
        var = round(100 * (rep - costo) / costo, 1) if rep is not None and costo else None
        f = {"code": p.code, "descripcion": p.descripcion, "costo_kg": round(costo, 3) if costo else None,
             "reposicion_kg": round(rep, 3) if rep is not None else None, "origen": origen or "",
             "precio_kg": round(pv, 3) if pv else None, "kg": round(kg, 1), "var_pct": var,
             "margen_costo": round(100 * (pv - costo) / pv, 1) if pv and costo else None,
             "margen_reposicion": round(100 * (pv - rep) / pv, 1) if pv and rep is not None else None,
             "impacto": round((rep - costo) * kg, 2) if rep is not None and costo and kg else 0.0}
        if var is None:
            f["lectura"], f["nivel"] = ("Falta el costo registrado" if costo is None and rep is not None else
                                        "Sin costo de reposición (sin cotizaciones ni importaciones)" if rep is None else ""), "info"
        elif var > tol:
            f["lectura"], f["nivel"] = (f"Reponer cuesta {var:g} % más que el costo registrado: actualizar el costo y revisar el "
                                        "precio de venta" + (f" (margen con reposición {f['margen_reposicion']:g} %)"
                                                             if f["margen_reposicion"] is not None else "") + "."), "err"
        elif var < -tol:
            f["lectura"], f["nivel"] = f"Reponer cuesta {abs(var):g} % menos: este producto compensa a los que subieron.", "ok"
        else:
            f["lectura"], f["nivel"] = "Costo y reposición alineados.", ""
        filas.append(f)
    sube = [f for f in filas if f["impacto"] > 0]
    baja = [f for f in filas if f["impacto"] < 0]
    s_sube = round(sum(f["impacto"] for f in sube), 2)
    s_baja = round(sum(f["impacto"] for f in baja), 2)
    neto = round(s_sube + s_baja, 2)
    if not sube and not baja:
        resumen = "Sin diferencias entre costo y reposición en productos con venta en el periodo."
    elif neto > 0:
        resumen = (f"Las subidas ({', '.join(f['code'] for f in sube[:5])}) cuestan S/ {s_sube:,.0f} en el periodo; "
                   f"las bajas compensan S/ {abs(s_baja):,.0f}. Falta cubrir S/ {neto:,.0f}: revisar precio de venta o costo "
                   "de los productos que subieron.")
    else:
        resumen = (f"Las bajas ({', '.join(f['code'] for f in baja[:5])}) compensan S/ {abs(s_baja):,.0f}, más que las subidas "
                   f"(S/ {s_sube:,.0f}). Neto a favor S/ {abs(neto):,.0f}.")
    filas.sort(key=lambda f: (-(f["var_pct"] or -999)))
    u = ultimo()
    return {"filas": filas, "tc": tc, "tc_fecha": u.fecha if u else None, "tc_fuente": u.fuente if u else "",
            "sube": s_sube, "baja": s_baja, "neto": neto, "resumen": resumen, "tolerancia": tol, "dias": dias,
            "desde": desde, "hasta": hoy}


def check_alerts(hoy=None):
    hoy = hoy or date.today()
    n = 0
    for f in analisis(hoy=hoy)["filas"]:
        if f["nivel"] == "err":
            alerts.emit("COSTO_REPOSICION_ALTO", f"{f['code']}: reponer cuesta {f['var_pct']:g} % más que su costo",
                        f"Costo S/ {f['costo_kg']}/kg · reposición S/ {f['reposicion_kg']}/kg ({f['origen']}) · precio de "
                        f"venta S/ {f['precio_kg'] or '-'}/kg.", "Product", f["code"], dedup_key=f"COSREP:{f['code']}:{hoy:%Y-%m}")
            n += 1
    return n


def guardar_costo(user, code, costo, unidad="KG"):
    from .costs import replace_costs
    p = db().get(Product, (code or "").strip().upper())
    if p is None:
        from .core import BusinessError
        raise BusinessError("Producto no existe.")
    return replace_costs([{"product_code": p.code, "descripcion": p.descripcion, "costo": costo, "unidad": unidad}], user,
                         "Costos y Presupuestos (manual)")


def import_excel(user, path):
    """V24 (07-nov): carga el costo por SKU con el formato que usa Costos y Presupuestos: uno o varios bloques lado a lado
    con las columnas SKU | DESCRIPCIÓN | COSTO EMPRESA. Granel y materia prima (GR-, MP-) se toman por kg; producto
    terminado y maquila (PT-, MQ-), por unidad. Solo se versionan los costos que cambian."""
    from openpyxl import load_workbook
    from .core import BusinessError
    from .costs import replace_costs
    ws = load_workbook(path, data_only=True).active
    filas = [list(r) for r in ws.iter_rows(values_only=True)]
    bloques = []  # (fila_cabecera, col_sku, col_desc, col_costo)
    for i, r in enumerate(filas[:15]):
        for j, c in enumerate(r):
            if str(c or "").strip().upper() == "SKU":
                resto = [str(x or "").strip().upper() for x in r[j + 1:j + 4]]
                k_desc = next((j + 1 + n for n, x in enumerate(resto) if x.startswith("DESCRIP")), None)
                k_cost = next((j + 1 + n for n, x in enumerate(resto) if "COSTO" in x), None)
                if k_cost is not None:
                    bloques.append((i, j, k_desc, k_cost))
    if not bloques:
        raise BusinessError("No se encontró la cabecera SKU | DESCRIPCIÓN | COSTO EMPRESA.")
    items, omitidos = [], []
    for i, js, jd, jc in bloques:
        for r in filas[i + 1:]:
            if js >= len(r) or not r[js]:
                continue
            code = str(r[js]).strip().upper()
            try:
                costo = float(r[jc]) if jc < len(r) and r[jc] not in (None, "") else None
            except (TypeError, ValueError):
                costo = None
            if costo is None or costo <= 0:
                continue
            if db().get(Product, code) is None:
                omitidos.append(code)
                continue
            items.append({"product_code": code, "descripcion": str(r[jd] or "")[:250] if jd is not None and jd < len(r) else "",
                          "costo": costo, "unidad": "KG" if code.startswith(("GR", "MP")) else "UND"})
    res = replace_costs(items, user, "Excel de costo empresa")
    res["omitidos"] = sorted(set(omitidos))
    res["leidos"] = len(items)
    return res
