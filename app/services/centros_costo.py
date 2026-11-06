"""V24 (07-nov-2026): centros de costo y rendiciones / planillas de movilidad de Compras nacionales.

El centro de costo es OPCIONAL: se puede indicar al registrar una solicitud u OC de compra nacional, una rendición de
facturas o una planilla de movilidad. El catálogo se carga desde el Excel de centros de costo de la empresa (columnas
GRUPO | ÁREA (número, descripción) | CENTRO DE COSTO (número, descripción) | SUB-CENTRO DE COSTO (número,
descripción); las celdas en blanco repiten el valor de arriba). Se elige el subcentro (o el centro si no tiene).
"""
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import CostCenter, ExpenseReport
from .core import BusinessError, audit, has_perm

TIPOS_GASTO = {"RENDICION": "Rendición de facturas", "MOVILIDAD": "Planilla de movilidad"}


def lista(activos=True):
    q = select(CostCenter).order_by(CostCenter.codigo)
    if activos:
        q = q.where(CostCenter.activo.is_(True))
    return list(db().execute(q).scalars())


def etiqueta(codigo):
    if not codigo:
        return ""
    c = db().execute(select(CostCenter).where(CostCenter.codigo == codigo)).scalars().first()
    return f"{c.codigo} · {c.area} / {c.centro} / {c.descripcion}" if c else codigo


def validar(codigo):
    """Vacío es válido (no es obligatorio); si se indica, debe existir."""
    codigo = (codigo or "").strip()
    if not codigo:
        return ""
    if lista() and not db().execute(select(CostCenter).where(CostCenter.codigo == codigo)).first():
        raise BusinessError(f"Centro de costo no válido: {codigo}.")
    return codigo


def import_excel(user, path):
    from openpyxl import load_workbook
    if not (has_perm(user, "centros_costo.cargar")):
        raise BusinessError("Cargan los centros de costo Compras, Costos y Presupuestos o Finanzas.")
    ws = load_workbook(path, data_only=True).active
    filas = [list(r) for r in ws.iter_rows(values_only=True)]

    def t(v):
        return " ".join(str(v or "").split()).upper()
    cab = next((i for i, r in enumerate(filas[:20]) if any(t(c).startswith("GRUPO") for c in r)), None)
    if cab is None:
        raise BusinessError("No se encontró la cabecera GRUPO | ÁREA | CENTRO DE COSTO | SUB-CENTRO DE COSTO.")
    h = [t(c) for c in filas[cab]]
    col = {"grupo": next(i for i, c in enumerate(h) if c.startswith("GRUPO")),
           "area": next((i for i, c in enumerate(h) if c.startswith("AREA") or c.startswith("ÁREA")), None),
           "centro": next((i for i, c in enumerate(h) if c.startswith("CENTRO DE COSTO")), None),
           "sub": next((i for i, c in enumerate(h) if c.startswith("SUB")), None)}
    if None in col.values():
        raise BusinessError("Faltan columnas: se esperan GRUPO, ÁREA, CENTRO DE COSTO y SUB-CENTRO DE COSTO.")
    actual = {"grupo": "", "area_codigo": "", "area": "", "centro_codigo": "", "centro": ""}
    nuevos = act = 0
    vistos = set()

    def num(v):
        if v in (None, ""):
            return ""
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()
    for r in filas[cab + 2:]:
        r = r + [None] * 12
        if r[col["grupo"]]:
            actual["grupo"] = " ".join(str(r[col["grupo"]]).split())
        if r[col["area"]] not in (None, ""):
            actual["area_codigo"], actual["area"] = num(r[col["area"]]), " ".join(str(r[col["area"] + 1] or "").split())
        if r[col["centro"]] not in (None, ""):
            actual["centro_codigo"], actual["centro"] = num(r[col["centro"]]), " ".join(str(r[col["centro"] + 1] or "").split())
            if r[col["sub"]] in (None, ""):  # centro sin subcentros
                codigo, desc = actual["centro_codigo"], actual["centro"]
            else:
                codigo = None
        else:
            codigo = None
        if r[col["sub"]] not in (None, ""):
            codigo, desc = num(r[col["sub"]]), " ".join(str(r[col["sub"] + 1] or "").split())
        if not codigo or codigo in vistos:
            continue
        vistos.add(codigo)
        c = db().execute(select(CostCenter).where(CostCenter.codigo == codigo)).scalars().first()
        if c is None:
            c = CostCenter(codigo=codigo, descripcion=desc[:160])
            db().add(c)
            nuevos += 1
        else:
            act += 1
        c.descripcion = desc[:160] or c.descripcion
        c.grupo, c.area_codigo, c.area = actual["grupo"][:80], actual["area_codigo"], actual["area"][:120]
        c.centro_codigo, c.centro, c.activo = actual["centro_codigo"], actual["centro"][:120], True
    db().flush()
    audit(user, "CENTROS_COSTO_CARGADOS", "CostCenter", "", {"nuevos": nuevos, "actualizados": act})
    return nuevos, act


def registrar_gasto(user, datos, archivo=""):
    if not has_perm(user, "compras.rendiciones"):
        raise BusinessError("Registra rendiciones y planillas de movilidad Compras nacionales.")
    tipo = (datos.get("tipo") or "").upper()
    if tipo not in TIPOS_GASTO:
        raise BusinessError("Elija rendición de facturas o planilla de movilidad.")
    concepto = (datos.get("concepto") or "").strip()
    responsable = (datos.get("responsable") or user.nombre).strip()
    if not concepto:
        raise BusinessError("Indique el concepto.")
    try:
        monto = float(str(datos.get("monto") or "").replace(",", "."))
    except ValueError:
        raise BusinessError("Monto inválido.") from None
    if monto <= 0:
        raise BusinessError("Monto inválido.")
    f = datos.get("fecha") or date.today()
    if isinstance(f, str):
        f = date.fromisoformat(f[:10])
    e = ExpenseReport(tipo=tipo, fecha=f, responsable=responsable[:160], concepto=concepto[:250],
                      comprobante=(datos.get("comprobante") or "").strip()[:60], proveedor=(datos.get("proveedor") or "").strip()[:160],
                      monto=monto, moneda=(datos.get("moneda") or "PEN").upper()[:5],
                      centro_costo=validar(datos.get("centro_costo")), archivo=archivo or "", user_id=user.id)
    db().add(e)
    db().flush()
    audit(user, "GASTO_REGISTRADO", "ExpenseReport", e.id, {"tipo": tipo, "monto": monto, "centro_costo": e.centro_costo})
    return e


def gastos(desde=None, hasta=None):
    q = select(ExpenseReport).order_by(ExpenseReport.fecha.desc(), ExpenseReport.id.desc())
    if desde:
        q = q.where(ExpenseReport.fecha >= desde)
    if hasta:
        q = q.where(ExpenseReport.fecha <= hasta)
    return list(db().execute(q).scalars())


def resumen_por_centro(desde=None, hasta=None):
    """S/ por centro de costo (rendiciones, movilidad y compras con OC)."""
    from collections import defaultdict
    from ..models import PurchaseRequest
    acc = defaultdict(lambda: {"rendicion": 0.0, "movilidad": 0.0, "compras": 0.0})
    for e in gastos(desde, hasta):
        acc[e.centro_costo or "(sin centro)"]["rendicion" if e.tipo == "RENDICION" else "movilidad"] += e.monto
    for r in db().execute(select(PurchaseRequest).where(PurchaseRequest.numero_oc != "")).scalars():
        if desde and r.ts.date() < desde or hasta and r.ts.date() > hasta:
            continue
        acc[r.centro_costo or "(sin centro)"]["compras"] += (r.precio or 0) * (r.cantidad or 0)
    return sorted(((k, etiqueta(k) if k != "(sin centro)" else k, v) for k, v in acc.items()),
                  key=lambda x: -(sum(x[2].values())))
