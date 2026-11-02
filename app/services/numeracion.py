"""V17 (02-nov-2026): los números de OV, orden de compra y guía no se escriben a mano: los asigna el sistema.

- OV del módulo: correlativo propio (OV-000001…). Al enviarse a SAP, la OV guarda el número que SAP le asigna
  (sap_docnum) y se muestra junto al del módulo; las OV que vienen de SAP conservan el número de SAP.
- Orden de compra: correlativo OC-000001…
- Guía: la de SAP se numera al enviar la pre-guía validada a SAP; la de contingencia (SAP no disponible), GS-000001…
Los prefijos se configuran en el parámetro «numeracion_prefijos»."""
import re

from sqlalchemy import select

from ..db import db
from .core import param

PREFIJOS = {"OV": "OV-", "OC": "OC-", "GUIA": "GS-"}


def prefijo(tipo):
    return (param("numeracion_prefijos", PREFIJOS) or PREFIJOS).get(tipo, PREFIJOS[tipo])


def _siguiente(tipo, columna, ancho=6):
    pre = prefijo(tipo)
    patron = re.compile(re.escape(pre) + r"(\d+)$")
    n = 0
    for v in db().execute(select(columna).where(columna.like(f"{pre}%"))).scalars():
        m = patron.match(v or "")
        if m:
            n = max(n, int(m.group(1)))
    return f"{pre}{n + 1:0{ancho}d}"


def next_order_number():
    from ..models import SalesOrder
    return _siguiente("OV", SalesOrder.numero)


def next_purchase_order_number():
    from ..models import PurchaseRequest
    return _siguiente("OC", PurchaseRequest.numero_oc)


def next_contingency_guide_number():
    from ..models import RouteStop
    return _siguiente("GUIA", RouteStop.guia_numero)
