"""V29 (11-nov-2026), ajustado en V30 (12-nov-2026): balance de peso de las órdenes de fabricación y sus liquidaciones
registradas en SAP.

Regla de la empresa: la cantidad de materia ingresada (granel o materia prima) más el desmedro debe ser igual en peso a
la suma del producto (producto terminado o materia prima, según el proceso). En kg:

    granel + materia prima  +  desmedro  =  producto (completado + rechazado)

El desmedro es la merma (decisión del 13-oct-2026): en las órdenes de SAP es el componente «X - DESMEDRO» de la lista de
materiales, con los prefijos de «prefijos_desmedro_bom» (ME-), o un código de «liquidacion_items_merma», o el que dice
DESMEDRO o MERMA en su descripción. Cada cantidad se toma con el signo que tiene en SAP (un subproducto que se recibe
tiene cantidad negativa). Envases, etiquetas, suministros, recursos y textos no pesan en el balance.

Se valida dos veces:
- al REGISTRAR la orden de fabricación (lo planificado): componentes planificados vs producto planificado;
- al LIQUIDAR (lo real): lo emitido de cada componente vs lo completado y rechazado, cuando la orden está cerrada o ya
  se completó lo planificado (antes, la liquidación puede estar en curso).
Si la diferencia supera «balance_of_tolerancia_pct» (% de lo ingresado) se alerta a la Jefatura de Operaciones y a la
Jefatura de Producción.
"""
from datetime import datetime

from ..db import db
from ..models import Product
from . import alerts
from .core import audit, param, set_param

TOL = 1e-6
PALABRAS_MERMA = ("MERMA", "DESMEDRO")


def _kg(p, q):
    if p is None:
        return None
    if (p.um or "").upper().startswith("K"):
        return q
    return q * p.peso_kg if p.peso_kg else None


def _es_merma(code, p):
    """Desmedro (= merma): prefijos de la lista de materiales (ME-), códigos configurados o la palabra en la descripción."""
    code = (code or "").upper()
    pref = [str(x).strip().upper() for x in (param("prefijos_desmedro_bom", ["ME-"]) or []) if str(x).strip()]
    cods = {str(x).strip().upper() for x in (param("liquidacion_items_merma", []) or []) if str(x).strip()}
    desc = ((p.descripcion if p else "") or "").upper()
    return any(code.startswith(x) for x in pref) or code in cods or any(w in desc for w in PALABRAS_MERMA)


def _es_insumo(p):
    from .stock import product_kind
    return product_kind(p) in ("GR", "MP")


def evaluar(orden, etapa):
    """Balance de una orden ({orden, producto, planificado, completado, rechazado, estado, componentes}) en la etapa
    PLAN o LIQUIDACION. None si no aplica (sin insumos o la liquidación aún en curso)."""
    s = db()
    campo = "planificado" if etapa == "PLAN" else "emitido"
    prod = s.get(Product, orden["producto"])
    if etapa == "PLAN":
        q_prod = orden["planificado"]
    else:
        q_prod = orden["completado"] + orden["rechazado"]
        if q_prod <= TOL or not (orden["estado"] == "CERRADA" or orden["completado"] + TOL >= orden["planificado"]):
            return None
    insumos = merma = 0.0
    sin_peso = []
    for c in orden["componentes"]:
        q = c[campo]
        if abs(q) <= TOL:
            continue
        p = s.get(Product, c["producto"])
        es_merma = _es_merma(c["producto"], p)
        if not es_merma and not _es_insumo(p):
            continue
        kg = _kg(p, q)  # con el signo de SAP
        if kg is None:
            sin_peso.append(c["producto"])
        elif es_merma:
            merma += kg
        else:
            insumos += kg
    if insumos <= TOL:
        return None
    kg_prod = _kg(prod, q_prod)
    if kg_prod is None:
        sin_peso.append(orden["producto"])
        kg_prod = 0.0
    entrada = insumos + merma
    dif = entrada - kg_prod
    pct = 100.0 * dif / insumos
    tol = float(param("balance_of_tolerancia_pct", 0.5) or 0)
    return {"orden": orden["orden"], "producto": orden["producto"], "descripcion": orden.get("descripcion", ""),
            "estado": orden["estado"], "fecha": orden.get("fecha", ""), "etapa": etapa,
            "insumos_kg": round(insumos, 3), "producto_kg": round(kg_prod, 3), "merma_kg": round(merma, 3),
            "dif_kg": round(dif, 3), "dif_pct": round(pct, 2), "sin_peso": sorted(set(sin_peso)),
            "ok": not sin_peso and abs(pct) <= tol + 1e-9}


def revisar(user, ordenes):
    """Evalúa las órdenes leídas de SAP, alerta las que no cuadran (una vez por orden, etapa y diferencia) y guarda el
    resultado para la pantalla. Devuelve el resumen."""
    filas = []
    for o in ordenes:
        for etapa in ("PLAN", "LIQUIDACION"):
            r = evaluar(o, etapa)
            if r is not None:
                filas.append(r)
    malas = [r for r in filas if not r["ok"]]
    for r in malas:
        que = "registro de la orden (planificado)" if r["etapa"] == "PLAN" else "liquidación (real)"
        if r["sin_peso"]:
            msg = (f"No se puede validar el peso: falta el peso por unidad de {', '.join(r['sin_peso'])} en el maestro de "
                   f"artículos del módulo.")
        else:
            msg = (f"Granel/MP {r['insumos_kg']:,.2f} kg + desmedro {r['merma_kg']:,.2f} kg = "
                   f"{r['insumos_kg'] + r['merma_kg']:,.2f} kg ≠ producto {r['producto_kg']:,.2f} kg. Diferencia "
                   f"{r['dif_kg']:,.2f} kg ({r['dif_pct']:+.2f} %; tolerancia "
                   f"{float(param('balance_of_tolerancia_pct', 0.5) or 0):g} %). "
                   + ("Lo ingresado más el desmedro supera al producto: ¿falta registrar producto o el desmedro está de más?"
                      if r["dif_kg"] > 0 else
                      "El producto supera lo ingresado más el desmedro: ¿falta emitir insumos o desmedro, o la cantidad "
                      "completada está de más?"))
        alerts.emit("BALANCE_OF", f"OF {r['orden']} ({r['producto']}): el balance de peso no cuadra en el {que}",
                    msg + " Revise la orden en SAP.", "ProductionOrderSAP", r["orden"],
                    dedup_key=f"BALANCE_OF:{r['orden']}:{r['etapa']}:{r['dif_kg']:.1f}", creado_por=user)
    res = {"ordenes": len(ordenes), "evaluadas": len(filas), "no_cuadran": len(malas)}
    set_param("sap_balance_of_ultimo", {"ts": datetime.now().isoformat(timespec="minutes"), "filas": filas}, user)
    audit(user, "BALANCE_OF_SAP", "ProductionOrderSAP", "", res)
    return res


def sync(user, sl=None):
    from .sap_sl import ServiceLayer
    from .sap_v29 import rows_ordenes_fabricacion
    propio = sl is None
    sl = sl or ServiceLayer()
    try:
        if propio:
            sl.login()
        ordenes = rows_ordenes_fabricacion(sl)
    finally:
        if propio:
            sl.logout()
    return revisar(user, ordenes)


def ultimo():
    return param("sap_balance_of_ultimo", {}) or {}
