"""V45 (16-nov-2026): actualizar el planeamiento de producción subiendo un Excel.
V47: formato PLANEAMIENTO de Producción (FECHA · # OP · LINEA · PLANIFICADO MP- KG · U.M · CODIGO vacío · PRODUCTO ·
DATOS DE GRANEL): el producto se reconoce por su nombre (en selección, por el granel) y las líneas por sus nombres
(«CIMBRIA + IQ», «BHULLER + TRUER», «R1&R2»…). Las filas cuyo producto no coincide con un artículo se informan.

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
    "codigo": ("codigo", "codigo de producto", "codigo producto", "cod", "sku", "item", "codigo articulo", "cod. articulo",
               "articulo"),
    "producto": ("producto", "descripcion", "descripcion de producto", "nombre del producto"),
    "granel": ("datos de granel", "granel", "descripcion granel"),
    "cantidad": ("cantidad", "cant", "plan", "programado kg", "cantidad programada", "cantidad plan", "unidades", "qty",
                 "planificado", "planificado mp- kg", "planificado mp - kg", "planificado mp-kg", "planificado kg"),
    "um": ("u.m", "um", "u. m.", "unidad", "unidad de medida"),
    "linea": ("linea", "linea de produccion", "maquina", "line"),
    "op": ("# op", "op", "n op", "orden de produccion"),
    "cliente": ("cliente",),
    "comentario": ("comentario", "comentarios", "observacion", "observaciones", "nota"),
}
# V47: nombres de línea del Excel de Producción (PLANEAMIENTO.xlsx) → línea del sistema
LINEAS_EXCEL = {"cimbria + iq": "CIMBRIA", "iq + cimbria": "CIMBRIA", "iq+cimb": "CIMBRIA", "bhuller + truer": "TRUER",
                "buhler + truer": "TRUER", "truer": "TRUER", "seleccion manual": "SEL_MANUAL", "sel. manual": "SEL_MANUAL",
                "envasado manual": "ENV_MANUAL", "env. manual": "ENV_MANUAL", "r1&r2": "R1", "r1 & r2": "R1",
                "r1 y r2": "R1", "raumak 1 y 2": "R1", "r1": "R1", "r2": "R2", "r3": "R3", "raumak 3": "R3"}


def _norm(t):
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s+", " ", t.replace("°", "").replace(":", ""))


def _clave_prod(t):
    """Nombre de producto comparable: sin tildes, mayúsculas, espacios ni signos (5 Kg = 5 KG; «X  * 5» = «X * 5»)."""
    return re.sub(r"[^a-z0-9]", "", _norm(t))


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
    if v in (None, "") or isinstance(v, bool):
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
    if t in LINEAS_EXCEL:
        return LINEAS_EXCEL[t]
    for code, nombre, _ in PRODUCTION_LINES:
        if t in (_norm(code), _norm(nombre)) or _norm(code) in t.replace(" ", "_") or t in _norm(nombre):
            return code
    raise BusinessError(f"Línea «{v}» no reconocida (líneas: {', '.join(c for c, _, _ in PRODUCTION_LINES)}).")


def _productos():
    from ..models import Product
    por = {}
    for p in db().execute(select(Product)).scalars():
        por.setdefault(_clave_prod(p.descripcion), p.code)
    return por


def _buscar_producto(por, *nombres):
    """Código del artículo cuyo nombre coincide con alguno de los nombres del Excel (sin importar tildes, mayúsculas,
    espacios ni signos). Si no hay coincidencia exacta, no se adivina: la fila queda «sin producto»."""
    for n in nombres:
        k = _clave_prod(n)
        if k and k in por:
            return por[k]
    # nombre corto (p. ej. «FRIJOL CANARIO» en «DATOS DE GRANEL»): solo si un único granel empieza así
    for n in nombres:
        k = _clave_prod(n)
        if len(k) < 6:
            continue
        cand = {c for kk, c in por.items() if kk.startswith(k + "granel")}
        if len(cand) == 1:
            return cand.pop()
    return None


def leer(path):
    """Filas del plan: [{fecha, product_code, cantidad, line_code, comentario, fila}] y las filas que no se pudieron
    reconocer: devuelve (filas, sin_producto)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    # V50: el Excel general de Producción tiene muchas pestañas: se usa «PROGRAMACION» (o la primera que tenga el
    # encabezado del plan), no necesariamente la primera
    hojas = sorted(wb.worksheets, key=lambda w: 0 if _norm(w.title).startswith("programacion") else 1)
    filas, h, cols, fechas = [], None, {}, {}
    for ws in hojas:
        filas = [list(r) for r in ws.iter_rows(values_only=True, max_row=4000)]
        h, cols, fechas = _encabezado(filas)
        if h is not None:
            break
    wb.close()
    if h is None:
        raise BusinessError("No se encontró el encabezado del plan en ninguna pestaña: se espera Código o Producto y "
                            "Cantidad con Fecha, o Código con una columna por día (pestaña «PROGRAMACION»).")
    return _filas_plan(filas, h, cols, fechas)


def _encabezado(filas):
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
        tiene_prod = "codigo" in cols or "producto" in cols
        if tiene_prod and ("cantidad" in cols and "fecha" in cols or len(fechas) >= 1):
            return h, cols, fechas
    return None, {}, {}


def _filas_plan(filas, h, cols, fechas):
    por = _productos()
    out, sin = [], []
    for i, r in enumerate(filas[h + 1:], start=h + 2):
        def val(k):
            return r[cols[k]] if k in cols and cols[k] < len(r) else None
        code = str(val("codigo") or "").strip().upper().split(" ")[0] if "codigo" in cols else ""
        nombre = str(val("producto") or "").strip()
        granel = str(val("granel") or "").strip()
        if not code and not nombre:
            continue
        um = _norm(val("um"))
        if code and code not in set(por.values()):
            code = ""  # V51: código que no está en el maestro de artículos: se intenta por el nombre
        if not code:
            # sin código: por el nombre; en selección (kg) el producto es el granel («DATOS DE GRANEL»)
            orden = (granel, nombre) if um.startswith("k") and granel else (nombre, granel)
            code = _buscar_producto(por, *orden) or ""
        try:
            linea = _linea(val("linea")) if "linea" in cols and val("linea") not in (None, "") else None
        except BusinessError:  # V70: una línea no reconocida no detiene la carga: la fila se informa
            sin.append({"fila": i, "producto": nombre or granel or code, "granel": granel, "fecha": _fecha(val("fecha")),
                        "cantidad": _num(val("cantidad")), "linea": None, "motivo": f"línea «{val('linea')}» no reconocida"})
            continue
        partes = [str(val("comentario") or "").strip()]
        if val("op") not in (None, ""):
            partes.append(f"OP {_num(val('op')) and int(_num(val('op'))) or val('op')}")
        if val("cliente") not in (None, ""):
            partes.append(f"Cliente {val('cliente')}")
        com = " · ".join(x for x in partes if x)
        if "cantidad" in cols and "fecha" in cols:
            q, f = _num(val("cantidad")), _fecha(val("fecha"))
            if not q:
                continue
            if not f:  # V70: fila con cantidad y sin fecha (p. ej. una fila a medio llenar): se informa y se sigue
                sin.append({"fila": i, "producto": nombre or granel or code, "granel": granel, "fecha": None,
                            "cantidad": q, "linea": linea, "motivo": "sin fecha"})
                continue
            if not code:
                sin.append({"fila": i, "producto": nombre or granel, "granel": granel, "fecha": f, "cantidad": q,
                            "linea": linea})
                continue
            out.append({"fila": i, "fecha": f, "product_code": code, "cantidad": q, "line_code": linea, "comentario": com})
        else:
            for j, f in fechas.items():
                q = _num(r[j]) if j < len(r) else None
                if q:
                    if not code:
                        sin.append({"fila": i, "producto": nombre, "granel": granel, "fecha": f, "cantidad": q, "linea": linea})
                        continue
                    out.append({"fila": i, "fecha": f, "product_code": code, "cantidad": q, "line_code": linea,
                                "comentario": com})
    if not out and not sin:
        raise BusinessError("El Excel no tiene filas con producto, fecha y cantidad.")
    return out, sin


def importar(user, periodo, path, nombre=""):
    """Crea o actualiza el plan con las filas del Excel. Devuelve {creadas, actualizadas, iguales}."""
    from . import production as prod
    periodo = (periodo or "DIA").upper()
    filas, sin = leer(path)
    # en el plan semanal o mensual, varias fechas del mismo periodo se suman en una sola entrada
    junt = {}
    for f in filas:
        k = (prod._inicio(periodo, f["fecha"]), f["product_code"], f["line_code"])
        if k in junt:
            junt[k]["cantidad"] += f["cantidad"]
        else:
            junt[k] = dict(f, fecha=k[0])
    filas = list(junt.values())
    res = {"creadas": 0, "actualizadas": 0, "iguales": 0, "pendientes": 0, "sin_producto": sin, "errores": [],
           "primer_dia": min((f["fecha"] for f in filas), default=None)}
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
        except BusinessError as e:  # V70: el error de una fila se informa y las demás se cargan
            res["errores"].append(f"fila {f['fila']} ({f['product_code']} {f['fecha']:%d/%m/%Y}): {e}")
    if periodo == "DIA" and filas:
        # V49: lo que antes se subió desde Excel como plan semanal o mensual se reemplaza por el plan diario (no se suma
        # dos veces en la vista semanal); no se toca lo registrado a mano ni lo ya liquidado
        borrados = 0
        for per in ("SEMANA", "MES"):
            claves = {(prod._inicio(per, f["fecha"]), f["product_code"]) for f in filas}
            for pl in db().execute(select(ProductionPlan).where(ProductionPlan.periodo == per,
                                                                ProductionPlan.comentario.like("%desde Excel%"))).scalars():
                if (pl.fecha, pl.product_code) in claves and prod.plan_status(pl)[0] != "LIQUIDADO":
                    db().delete(pl)
                    borrados += 1
        res["reemplazadas"] = borrados
    if not filas:
        raise BusinessError("Ninguna fila del Excel coincide con un artículo del sistema (por código o por nombre): "
                            + "; ".join(f"fila {x['fila']} «{x['producto']}»" for x in sin[:8]) + ".")
    audit(user, "PLAN_EXCEL", "ProductionPlan", nombre[:60], dict(res, periodo=periodo, filas=len(filas),
                                                                   sin_producto=[f"fila {x['fila']}: {x['producto']}"
                                                                                 for x in sin]))
    return res
