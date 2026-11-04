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
