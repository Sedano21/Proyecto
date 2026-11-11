"""V26 (11-nov-2026): seguimiento de producto ya fumigado que sigue almacenado.

Regla de la empresa: el producto fumigado puede estar almacenado como máximo «fumigado_dias_max» días (20) desde que
terminó la fumigación. Calidad y Almacén reciben un aviso a los «fumigado_dias_aviso» días (15) y una alerta al llegar
al máximo, para que no se quede producto fumigado estancado (despacharlo, usarlo o evaluar una nueva fumigación).
"""
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import StockLot
from . import alerts
from .core import param

ESTADOS_EXCLUIDOS = ("EN_FUMIGACION", "AGOTADO", "NO_UTILIZABLE", "DANADO")


def _fecha(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def fin_fumigacion(lot, hoy=None):
    """Fecha en que el lote quedó fumigado: fin registrado, liberación por Calidad o liberación prevista ya pasada."""
    hoy = hoy or date.today()
    f = lot.fumigacion or {}
    fin = _fecha(f.get("fin")) or _fecha(f.get("liberado"))
    if fin is None:
        prev = _fecha(f.get("liberacion"))
        fin = prev if prev and prev <= hoy else None
    return fin


def listar(hoy=None):
    hoy = hoy or date.today()
    maximo = int(param("fumigado_dias_max", 20) or 20)
    aviso = int(param("fumigado_dias_aviso", 15) or 15)
    filas = []
    q = select(StockLot).where(StockLot.cantidad > 0, StockLot.estado.notin_(ESTADOS_EXCLUIDOS))
    for lot in db().execute(q).scalars():
        fin = fin_fumigacion(lot, hoy)
        if fin is None:
            continue
        dias = (hoy - fin).days
        nivel = "VENCIDO" if dias >= maximo else ("AVISO" if dias >= aviso else "OK")
        filas.append({"lot": lot, "fin": fin, "dias": dias, "restan": maximo - dias, "nivel": nivel})
    filas.sort(key=lambda x: -x["dias"])
    return {"filas": filas, "maximo": maximo, "aviso": aviso}


def revisar(hoy=None):
    """Tarea diaria: aviso y alerta por lote (una vez por nivel)."""
    res = listar(hoy)
    n = 0
    for x in res["filas"]:
        if x["nivel"] == "OK":
            continue
        lot = x["lot"]
        if x["nivel"] == "VENCIDO":
            titulo = f"Fumigado hace {x['dias']} días: lote {lot.lote} sigue almacenado (máximo {res['maximo']})"
        else:
            titulo = f"Fumigado hace {x['dias']} días: lote {lot.lote} (quedan {x['restan']} de {res['maximo']})"
        alerts.emit("FUMIGADO_ESTANCADO", titulo,
                    f"{lot.product_code} · {lot.cantidad:g} en {lot.warehouse_code}. Terminó la fumigación el "
                    f"{x['fin']:%d/%m/%Y}. Priorice su despacho o uso; si no saldrá, Calidad evalúa una nueva fumigación.",
                    "StockLot", lot.id, dedup_key=f"FUMI_ESTANCADO:{lot.id}:{x['fin'].isoformat()}:{x['nivel']}")
        n += 1
    return n
