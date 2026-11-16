"""V45 (16-nov-2026): actualizar el planeamiento de producción subiendo un Excel.

Se aceptan dos formas comunes (se reconocen los encabezados por su nombre, sin importar mayúsculas ni tildes):
1. Una fila por producto y fecha: Fecha · Código (artículo, producto, SKU) · Cantidad (plan, programado) · Línea
   (opcional) · Comentario (opcional).
2. Una fila por producto con una columna por día: Código · Línea (opcional) · columnas con fechas (dd/mm/aaaa o celdas
   de fecha) con la cantidad de cada día.
Por cada producto, fecha y línea: si ya hay una entrada del plan sin liquidar, se actualiza su cantidad; si no, se crea.
Las filas vacías o con cantidad 0 se omiten. Las reglas del plan son las de siempre (validación del Jefe de Producción
para los cambios de un asistente)."""
import re
import unicodedata
from datetime import date, datetime

from sqlalchemy import select

from ..db import db
from ..models import ProductionPlan
from .core import BusinessError, audit

SINONIMOS = {
    "fecha": ("fecha", "dia", "fecha de produccion", "fecha programada", "fecha plan"),
    "producto": ("codigo", "codigo de producto", "codigo producto", "cod", "articulo", "producto", "sku", "item",
                 "codigo articulo", "cod. articulo"),
    "cantidad": ("cantidad", "cant", "plan", "programado", "cantidad programada", "cantidad plan", "unidades", "qty"),
    "linea": ("linea", "linea de produccion", "maquina", "line"),
    "comentario": ("comentario", "comentarios", "observacion", "observaciones", "nota"),
}


def _norm(t):
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s+", " ", t.replace("°", "").replace(":", ""))


def _fecha(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.match(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*$", str(v or ""))
    if m:
        d, mth, y = (int(x) for x in m.groups())
        try:
            return date(y + 2000 if y < 100 else y, mth, d)
        except ValueError:
            return None
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _linea(v):
    from ..catalogs import PRODUCTION_LINES
    t = _norm(v)
    if not t:
        return None
    for code, nombre, _ in PRODUCTION_LINES:
        if t in (_norm(code), _norm(nombre)) or _norm(code) in t.replace(" ", "_") or t in _norm(nombre):
            return code
    raise BusinessError(f"Línea «{v}» no reconocida (líneas: {', '.join(c for c, _, _ in PRODUCTION_LINES)}).")


def leer(path):
    """Filas del plan: [{fecha, product_code, cantidad, line_code, comentario, fila}]."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    filas = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    for h, cab in enumerate(filas[:15]):  # el encabezado puede no estar en la primera fila
        cols = {}
        fechas = {}
        for j, c in enumerate(cab):
            n = _norm(c)
            for k, opciones in SINONIMOS.items():
                if n in opciones and k not in cols:
                    cols[k] = j
            f = _fecha(c) if c not in (None, "") and not n.isalpha() else None
            if f:
                fechas[j] = f
        if "producto" in cols and ("cantidad" in cols and "fecha" in cols or len(fechas) >= 1):
            break
    else:
        raise BusinessError("No se encontró el encabezado: se espera Código (o Artículo/Producto) y Cantidad con Fecha, "
                            "o Código con una columna por día.")
    out = []
    for i, r in enumerate(filas[h + 1:], start=h + 2):
        def val(k):
            return r[cols[k]] if k in cols and cols[k] < len(r) else None
        code = str(val("producto") or "").strip().upper().split(" ")[0]
        if not code:
            continue
        linea = _linea(val("linea")) if "linea" in cols else None
        com = str(val("comentario") or "").strip()
        if "cantidad" in cols and "fecha" in cols:
            q, f = _num(val("cantidad")), _fecha(val("fecha"))
            if q and f:
                out.append({"fila": i, "fecha": f, "product_code": code, "cantidad": q, "line_code": linea, "comentario": com})
            elif q and not f:
                raise BusinessError(f"Fila {i}: fecha no válida ({val('fecha')}).")
        else:
            for j, f in fechas.items():
                q = _num(r[j]) if j < len(r) else None
                if q:
                    out.append({"fila": i, "fecha": f, "product_code": code, "cantidad": q, "line_code": linea,
                                "comentario": com})
    if not out:
        raise BusinessError("El Excel no tiene filas con producto, fecha y cantidad.")
    return out


def importar(user, periodo, path, nombre=""):
    """Crea o actualiza el plan con las filas del Excel. Devuelve {creadas, actualizadas, iguales}."""
    from . import production as prod
    periodo = (periodo or "DIA").upper()
    filas = leer(path)
    # en el plan semanal o mensual, varias fechas del mismo periodo se suman en una sola entrada
    junt = {}
    for f in filas:
        k = (prod._inicio(periodo, f["fecha"]), f["product_code"], f["line_code"])
        if k in junt:
            junt[k]["cantidad"] += f["cantidad"]
        else:
            junt[k] = dict(f, fecha=k[0])
    filas = list(junt.values())
    res = {"creadas": 0, "actualizadas": 0, "iguales": 0, "pendientes": 0}
    for f in filas:
        try:
            pl = db().execute(select(ProductionPlan).where(
                ProductionPlan.periodo == periodo, ProductionPlan.fecha == f["fecha"],
                ProductionPlan.product_code == f["product_code"],
                (ProductionPlan.line_code == f["line_code"]) if f["line_code"] else ProductionPlan.line_code.is_(None)
            ).order_by(ProductionPlan.id.desc())).scalars().first()
            if pl is None:
                prod.add_plan(user, periodo, f["fecha"], f["product_code"], f["cantidad"], f["line_code"],
                              f["comentario"] or f"Cargado desde Excel {nombre}".strip())
                res["creadas"] += 1
            elif abs((pl.cantidad or 0) - f["cantidad"]) < 1e-9:
                res["iguales"] += 1
            else:
                r = prod.update_plan(user, pl, f["cantidad"], f"Actualizado desde Excel {nombre}".strip())
                res["pendientes" if r is not None else "actualizadas"] += 1
        except BusinessError as e:
            raise BusinessError(f"Fila {f['fila']} ({f['product_code']} {f['fecha']:%d/%m/%Y}): {e}")
    audit(user, "PLAN_EXCEL", "ProductionPlan", nombre[:60], dict(res, periodo=periodo, filas=len(filas)))
    return res
