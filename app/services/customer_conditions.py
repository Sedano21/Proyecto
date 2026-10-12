"""Condiciones comerciales por cliente (archivo 'LISTA DE CLIENTES - CON PENALIDADES Y LOTES', 13-oct-2026).

- Lotes por SKU ("1 LOTE POR SKU", "2 LOTES POR SKU"): la reserva no usa más lotes de los permitidos por producto.
- Penalidades: se clasifican por tipo (ventana horaria, fecha de entrega PAE, fill rate, paletizado, documentos, peso,
  ruptura de stock, no conformidades) y se muestran en la OV, la preparación y la ruta. Con el criterio 'penalidad' en el
  orden de prioridad, a igual fecha comprometida se atiende primero al cliente con penalidades más severas (pesos
  configurables, propuestos).
- Vida útil: se registra; solo se aplica a la reserva si se activa 'aplicar_vida_util_cliente' (pendiente de confirmar
  si significa vida útil restante mínima al despacho).
- El archivo no trae RUC: se vincula por nombre normalizado con los clientes existentes y con los que se creen después
  al importar OV.
"""
import re
import unicodedata

from sqlalchemy import select

from ..db import db
from ..models import Customer, CustomerCondition
from .core import param

TIPOS = [
    ("VENTANA_HORARIA", r"VENTANA HORARIA"),
    ("FECHA_ENTREGA", r"FECHA DE ENTREGA|PAE"),
    ("FILL_RATE", r"FILL RATE"),
    ("RETIRO_PROVEEDOR", r"RETIRO (DE )?PROVEEDOR|BLOQUEO"),
    ("PALETIZADO", r"PALETIZADO"),
    ("DOCUMENTOS", r"DOCUMENTOS"),
    ("PESO", r"PESO"),
    ("ENTREGA_PARCIAL", r"FALTA DE ENTREGA|PARCIAL"),
    ("RUPTURA_STOCK", r"RUPTURA"),
    ("NO_CONFORMIDADES", r"NO CONFORMIDADES"),
]
TIPO_TXT = {"VENTANA_HORARIA": "ventana horaria", "FECHA_ENTREGA": "fecha de entrega", "FILL_RATE": "fill rate",
            "RETIRO_PROVEEDOR": "bloqueo/retiro de proveedor", "PALETIZADO": "paletizado", "DOCUMENTOS": "documentos",
            "PESO": "peso", "ENTREGA_PARCIAL": "falta de entrega o parcial", "RUPTURA_STOCK": "ruptura de stock no informada",
            "NO_CONFORMIDADES": "no conformidades reiteradas"}


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(s.split())


def parse(lotes, vida, penalidades):
    out = {"max_lotes_por_sku": None, "vida_util_meses": None, "penalidad_tipos": [], "fill_rate_min_pct": None}
    m = re.search(r"(\d+)\s*LOTE", str(lotes or "").upper())
    if m:
        out["max_lotes_por_sku"] = int(m.group(1))
    m = re.search(r"(\d+)\s*MES", str(vida or "").upper())
    if m:
        out["vida_util_meses"] = int(m.group(1))
    txt = str(penalidades or "").upper()
    out["penalidad_tipos"] = [t for t, rx in TIPOS if re.search(rx, txt)]
    fr = [float(x) for x in re.findall(r"FILL RATE\s*<\s*(\d+(?:\.\d+)?)\s*%", txt)]
    if fr:
        out["fill_rate_min_pct"] = max(fr)
    return out


def for_customer(customer):
    if customer is None:
        return None
    s = db()
    c = s.execute(select(CustomerCondition).where(CustomerCondition.customer_id == customer.id)).scalars().first()
    if c is None:
        c = s.execute(select(CustomerCondition).where(CustomerCondition.nombre_norm == norm_name(customer.nombre))).scalars().first()
        if c is not None and c.customer_id is None:
            c.customer_id = customer.id  # vínculo por nombre
    return c


def max_lots(customer):
    c = for_customer(customer)
    return c.max_lotes_por_sku if c and c.max_lotes_por_sku else None


def penalty_score(customer):
    c = for_customer(customer)
    if c is None:
        return 0
    pesos = param("peso_penalidad", {}) or {}
    return sum(float(pesos.get(t, 0) or 0) for t in (c.penalidad_tipos or []))


def min_shelf_days(customer):
    if not param("aplicar_vida_util_cliente", False):
        return None
    c = for_customer(customer)
    return c.vida_util_meses * 30 if c and c.vida_util_meses else None


def summary(customer):
    c = for_customer(customer)
    if c is None:
        return ""
    partes = []
    if c.max_lotes_por_sku:
        partes.append(f"máx. {c.max_lotes_por_sku} lote(s) por SKU")
    if c.vida_util_texto:
        partes.append(f"vida útil {c.vida_util_texto.lower()}")
    if c.penalidad_tipos:
        partes.append("penalidades: " + ", ".join(TIPO_TXT.get(t, t) for t in c.penalidad_tipos))
    return "; ".join(partes)


def link_all():
    """Vincula condiciones pendientes con clientes existentes por nombre normalizado."""
    s = db()
    por_nombre = {norm_name(c.nombre): c for c in s.execute(select(Customer)).scalars()}
    n = 0
    for cond in s.execute(select(CustomerCondition).where(CustomerCondition.customer_id.is_(None))).scalars():
        cu = por_nombre.get(cond.nombre_norm)
        if cu is not None:
            cond.customer_id = cu.id
            n += 1
    return n
