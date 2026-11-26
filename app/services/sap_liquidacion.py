"""V76 (26-nov-2026): liquidaciones de producción con SAP, desde la pantalla de Liquidaciones.

- Traer de SAP: las entradas por producción (recibos de producción contra la orden de fabricación) de los últimos
  «sap_liquidacion_dias» días, con el flujo normal de carga (validación y confirmación). Así se ven en el módulo con el
  mismo contenido que en SAP: OF, tipo, almacén, fecha, producto, cantidades planificada y completada, UM, estado, lote,
  fechas de fabricación y vencimiento y el número de la entrada en SAP.
- Enviar a SAP: una liquidación registrada en el módulo se registra en SAP como recibo de producción
  (InventoryGenEntries con la línea basada en la orden de fabricación, BaseType 202), con su lote y fechas.

Seguridad: solo escribe si «sap_escritura_liquidacion» está activado y la base está en «sap_escritura_empresas» (la
misma lista que usan las OV). Apagado por defecto: se prueba primero en la base de pruebas de SAP.
"""
from ..models import now
from .core import BusinessError, audit, has_perm, param


def escritura_habilitada(cfg):
    if not param("sap_escritura_liquidacion", False):
        return "El envío de liquidaciones a SAP está desactivado (parámetro «sap_escritura_liquidacion»)."
    empresas = [e.strip().upper() for e in (param("sap_escritura_empresas", []) or [])]
    if (cfg.get("company") or "").upper() not in empresas:
        return f"La escritura en SAP no está autorizada para la base «{cfg.get('company') or '-'}» («sap_escritura_empresas»)."
    return None


def traer(user, upload_dir):
    if not has_perm(user, "produccion.liquidar"):
        raise BusinessError("Traen las liquidaciones de SAP el Jefe y los Asistentes de Producción.")
    from .sap_sl import sync
    b = sync("LIQUIDACION", user, upload_dir, autoconfirmar=True)
    audit(user, "SAP_LIQUIDACIONES_TRAIDAS", "UploadBatch", b.id if b else "", {})
    return b


def payload(liq, abs_entry, almacen):
    lote = {"BatchNumber": liq.lote, "Quantity": liq.cantidad_completada}
    if liq.fecha_fab:
        lote["ManufacturingDate"] = liq.fecha_fab.isoformat()
    if liq.fecha_venc:
        lote["ExpiryDate"] = liq.fecha_venc.isoformat()
    linea = {"BaseType": 202, "BaseEntry": abs_entry, "Quantity": liq.cantidad_completada, "BatchNumbers": [lote]}
    if almacen:
        linea["WarehouseCode"] = almacen
    return {"DocDate": liq.fecha.isoformat(),
            "Comments": f"Liquidación {liq.numero_documento} registrada en el módulo de operaciones"[:254],
            "DocumentLines": [linea]}


def enviar(user, liq, sl=None):
    """Registra la liquidación en SAP. Devuelve el número de la entrada en SAP. Deja el resultado (o el error) en liq.sap."""
    from .sap_sl import ServiceLayer
    if not has_perm(user, "produccion.liquidar"):
        raise BusinessError("Envían la liquidación a SAP el Jefe y los Asistentes de Producción.")
    if (liq.sap or {}).get("docnum"):
        raise BusinessError(f"La liquidación ya está en SAP (entrada {liq.sap['docnum']}).")
    if liq.origen == "SAP":
        raise BusinessError("Esta liquidación vino de SAP: ya está registrada allí.")
    if (liq.bloqueo or {}).get("motivos") and not (liq.bloqueo or {}).get("resuelto_ts"):
        raise BusinessError("La liquidación está bloqueada: corríjala antes de enviarla a SAP.")
    if not liq.lote or not liq.cantidad_completada:
        raise BusinessError("Faltan el lote o la cantidad completada.")
    propio = sl is None
    sl = sl or ServiceLayer()
    try:
        if propio:
            sl.login()
        motivo = escritura_habilitada(sl.cfg)
        if motivo:
            raise BusinessError(motivo)
        of = sl.get_all("ProductionOrders", {"$filter": f"DocumentNumber eq {int(liq.numero_documento)}",
                                             "$select": "AbsoluteEntry,DocumentNumber,ItemNo,Warehouse,ProductionOrderStatus"}) \
            if str(liq.numero_documento).isdigit() else []
        if not of:
            raise BusinessError(f"No se encontró en SAP la orden de fabricación {liq.numero_documento}.")
        of = of[0]
        if of.get("ItemNo") and of["ItemNo"] != liq.product_code:
            raise BusinessError(f"La OF {liq.numero_documento} es de {of['ItemNo']}, no de {liq.product_code}.")
        if of.get("ProductionOrderStatus") not in (None, "boposReleased"):
            raise BusinessError(f"La OF {liq.numero_documento} no está liberada en SAP ({of.get('ProductionOrderStatus')}).")
        r = sl._req("POST", "InventoryGenEntries", payload(liq, of["AbsoluteEntry"], liq.warehouse_code or of.get("Warehouse")))
    except BusinessError as e:
        liq.sap = {"error": str(e)[:500], "ts": now().isoformat(timespec="minutes"), "user": user.nombre}
        audit(user, "LIQUIDACION_SAP_ERROR", "Liquidation", liq.id, liq.sap)
        raise
    finally:
        if propio:
            try:
                sl.logout()
            except BusinessError:
                pass
    liq.sap = {"docnum": (r or {}).get("DocNum"), "docentry": (r or {}).get("DocEntry"), "ts": now().isoformat(timespec="minutes"),
               "user": user.nombre}
    audit(user, "LIQUIDACION_SAP", "Liquidation", liq.id, liq.sap)
    return liq.sap["docnum"]
