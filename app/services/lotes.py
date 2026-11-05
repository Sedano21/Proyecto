"""V20: lotes con variantes por puntos (regla de Producción, 04-nov-2026).

Producción numera el lote por su origen (p. ej. 000863FA). Si el mismo lote se vuelve a producir en otra fecha (cambia
la fecha de producción y/o de vencimiento), en SAP se registra con un punto más: 000863FA. (2.ª producción),
000863FA.. (3.ª), etc. Para SAP son lotes distintos, cada uno con sus fechas.

En el módulo:
- el lote se guarda EXACTO como en SAP (las guías y entregas lo exigen así);
- en pantalla se muestra el lote base y su variante («000863FA · 3.ª prod.») con sus fechas;
- buscar «000863FA» encuentra todas sus variantes;
- en la carga de stock se avisa solo lo que parece un error: comas en lugar de puntos, o dos variantes del mismo lote con
  las mismas fechas (posible duplicado).
"""
import re

_FIN = re.compile(r"[.,\s]+$")


def base(lote):
    return _FIN.sub("", (lote or "").strip())


def variante(lote):
    """0 = lote original; 1 = primer punto (2.ª producción); 2 = dos puntos (3.ª)…"""
    lote = (lote or "").strip()
    return len(lote) - len(base(lote))


def tiene_coma(lote):
    return "," in _FIN.search((lote or "").strip()).group(0) if _FIN.search((lote or "").strip()) else False


def etiqueta(lote):
    v = variante(lote)
    return base(lote) if not v else f"{base(lote)} · {v + 1}.ª prod."


# ------------------------------------------------------------------ V21: el módulo asigna el código del lote para SAP
def _variantes_registradas(product_code, base_lote):
    """Todas las variantes conocidas de un lote base del producto: las del stock (traído de SAP) y las asignadas en
    partes de producción que aún no llegan a SAP. [(codigo, fecha_fab, fecha_venc, origen)]."""
    from sqlalchemy import select
    from ..db import db
    from ..models import ProductionReport, StockLot
    out = {}
    patron = f"{base_lote}%"
    for l in db().execute(select(StockLot).where(StockLot.product_code == product_code, StockLot.lote.like(patron))).scalars():
        if base(l.lote) == base_lote:
            out.setdefault(l.lote, (l.lote, l.fecha_fab, l.fecha_venc, "SAP"))
    for r in db().execute(select(ProductionReport).where(ProductionReport.product_code == product_code,
                                                          ProductionReport.lote_pt.like(patron))).scalars():
        if base(r.lote_pt) == base_lote and r.lote_pt not in out:
            out[r.lote_pt] = (r.lote_pt, r.fecha, r.fv_pt, "PARTE")
    return list(out.values())


def asignar(product_code, lote_escrito, fecha_fab, fecha_venc=None):
    """Código del lote para SAP según la regla de Producción (un punto más por cada nueva producción del mismo lote),
    calculado por el sistema para que nadie escriba los puntos a mano:
    - si ya existe una variante de ese lote con la misma fecha de producción (y vencimiento), se usa esa misma;
    - si no, la siguiente variante libre (000863FA → 000863FA. → 000863FA..).
    Devuelve (codigo, nueva, explicacion)."""
    b = base(lote_escrito)
    if not b:
        return "", False, ""
    vs = _variantes_registradas(product_code, b)
    for cod, fp, fv, _o in vs:
        if fp and fecha_fab and fp == fecha_fab and (not fecha_venc or not fv or fv == fecha_venc):
            return cod, False, f"Mismo lote y fecha de producción ya registrados: se usa {cod}."
    if not vs:
        return b, True, "Primera producción de este lote."
    usadas = {variante(c) for c, *_ in vs}
    n = next(i for i in range(0, 200) if i not in usadas)
    cod = b + "." * n
    return cod, True, f"{n + 1}.ª producción del lote {b}: en SAP se registra como «{cod}»."


def anomalias(product_codes=None):
    """Revisión de lotes del stock: comas en lugar de puntos, variantes con las mismas fechas, variantes sin fechas y
    caracteres no válidos. Para limpiar en SAP (p. ej. en el inventario)."""
    import re as _re
    from collections import defaultdict
    from sqlalchemy import select
    from ..db import db
    from ..models import StockLot
    q = select(StockLot).where(StockLot.cantidad > 0)
    if product_codes:
        q = q.where(StockLot.product_code.in_(product_codes))
    grupos = defaultdict(list)
    out = []
    for l in db().execute(q).scalars():
        grupos[(l.product_code, base(l.lote))].append(l)
        if tiene_coma(l.lote):
            out.append({"tipo": "Coma en lugar de punto", "producto": l.product_code, "lote": l.lote, "almacen": l.warehouse_code,
                        "detalle": f"Debería ser «{base(l.lote) + '.' * variante(l.lote)}»", "lot_id": l.id})
        elif not _re.match(r"^[A-Za-z0-9/\-]+(\.+|\.\d{3})?$", l.lote or ""):
            out.append({"tipo": "Caracteres no válidos", "producto": l.product_code, "lote": l.lote, "almacen": l.warehouse_code,
                        "detalle": "Revise el número del lote en SAP", "lot_id": l.id})
    for (pc, b), ls in grupos.items():
        codigos = {l.lote for l in ls}
        if len(codigos) < 2:
            continue
        por_fecha = defaultdict(set)
        for l in ls:
            if l.fecha_fab or l.fecha_venc:
                por_fecha[(l.fecha_fab, l.fecha_venc)].add(l.lote)
        for (fp, fv), cods in por_fecha.items():
            if len(cods) > 1:
                out.append({"tipo": "Variantes con las mismas fechas", "producto": pc, "lote": ", ".join(sorted(cods, key=len)),
                            "almacen": "", "detalle": f"FP {fp or '—'} · FV {fv or '—'}: deberían ser un solo lote", "lot_id": None})
        sin_fecha = sorted(l.lote for l in ls if not l.fecha_fab and not l.fecha_venc)
        if sin_fecha:
            out.append({"tipo": "Variante sin fechas", "producto": pc, "lote": ", ".join(sin_fecha), "almacen": "",
                        "detalle": "Sin fecha de producción ni de vencimiento no se distingue de las otras variantes",
                        "lot_id": None})
    orden = {"Coma en lugar de punto": 0, "Variantes con las mismas fechas": 1, "Variante sin fechas": 2, "Caracteres no válidos": 3}
    return sorted(out, key=lambda x: (orden.get(x["tipo"], 9), x["producto"], x["lote"]))
