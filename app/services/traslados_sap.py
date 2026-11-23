"""V66 (marcha blanca almacén): el traslado entre almacenes hecho en el módulo se registra también en SAP.

Cuando el almacén destino confirma la recepción, el traslado queda «PENDIENTE» de registrar en SAP como transferencia
de stock (StockTransfers) con lo recibido, el lote y los almacenes (con la equivalencia «sap_almacenes_equivalencia» si
los códigos no son iguales). El vigilante de SAP lo envía; solo se escribe en las bases autorizadas
(«sap_escritura_empresas»). Los traslados hechos en SAP ya se ven en el módulo (el vigilante los lee).
"""
from datetime import datetime

from sqlalchemy import select

from ..db import db
from ..models import Transfer
from .core import BusinessError, audit, param

SIN_LOTE = ("", "SIN LOTE", "SIN_LOTE", "-")


def _alm(code):
    eq = param("sap_almacenes_equivalencia", {}) or {}
    return str(eq.get(code) or code)


def marcar(t):
    """Al recibir el traslado: queda pendiente de registrar en SAP."""
    if not param("sap_traslados_activo", True) or not (t.cantidad_recibida or 0) > 0:
        return
    t.sap = {"estado": "PENDIENTE", "ts": datetime.now().isoformat(timespec="seconds")}


def payload(t):
    lot = t.lot
    linea = {"ItemCode": lot.product_code, "Quantity": round(float(t.cantidad_recibida or 0), 6),
             "FromWarehouseCode": _alm(lot.warehouse_code), "WarehouseCode": _alm(t.destino_code)}
    if (lot.lote or "").strip().upper() not in SIN_LOTE:
        linea["BatchNumbers"] = [{"BatchNumber": lot.lote, "Quantity": linea["Quantity"]}]
    return {"DocDate": (t.recibido_ts or datetime.now()).date().isoformat(), "FromWarehouse": linea["FromWarehouseCode"],
            "ToWarehouse": linea["WarehouseCode"],
            "Comments": f"Traslado #{t.id} del módulo de operaciones ({lot.warehouse_code} → {t.destino_code}).",
            "StockTransferLines": [linea]}


def push(t, sl):
    from .sap_sl import write_enabled
    motivo = write_enabled(sl.cfg)
    if motivo:
        raise BusinessError(motivo)
    sap = dict(t.sap or {})
    try:
        r = sl._req("POST", "StockTransfers", payload(t))
        sap.update({"estado": "ENVIADO", "docentry": r.get("DocEntry"), "docnum": str(r.get("DocNum") or ""), "error": ""})
        audit(None, "SAP_TRASLADO_CREADO", "Transfer", t.id, {"docnum": sap["docnum"]})
    except BusinessError as e:
        sap.update({"estado": "ERROR", "error": str(e)[:300], "intentos": int(sap.get("intentos") or 0) + 1})
    sap["ts"] = datetime.now().isoformat(timespec="seconds")
    t.sap = sap
    return sap["estado"]


def push_pendientes(sl=None):
    """Envía a SAP los traslados recibidos pendientes (en la cola del vigilante)."""
    from .sap_sl import configured, write_enabled
    if sl is None or write_enabled(sl.cfg) or not configured():
        return 0
    n = 0
    for t in db().execute(select(Transfer).where(Transfer.estado.in_(("RECIBIDO", "RECIBIDO_CON_DIFERENCIA")))).scalars():
        if (t.sap or {}).get("estado") in ("PENDIENTE", "ERROR") and int((t.sap or {}).get("intentos") or 0) < 5:
            if push(t, sl) == "ENVIADO":
                n += 1
    return n
