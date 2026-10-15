"""Seguridad (obs. demo v0.7): cuadro de llegadas de compras nacionales e importaciones para validar lo que ingresa,
con foto y notificación ante cualquier incidente."""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import ArrivalCheck, ImportShipment, PurchaseRequest, now
from . import alerts
from .core import BusinessError, audit, has_perm

ESTADOS_IMPORT_CERRADOS = ("RECIBIDA", "RECIBIDA_CON_DIFERENCIAS", "CERRADA", "ANULADA")


def arrivals(dias=7, hoy=None):
    """Llegadas previstas (hasta 'dias' hacia adelante, más las atrasadas): compras con orden generada pendientes de
    recepción e importaciones en curso."""
    hoy = hoy or date.today()
    hasta = hoy + timedelta(days=dias)
    out = []
    for r in db().execute(select(PurchaseRequest).where(PurchaseRequest.estado == "ORDEN_GENERADA")).scalars():
        if r.fecha_prevista and r.fecha_prevista <= hasta:
            out.append({"tipo": "COMPRA", "id": r.id, "doc": f"OC {r.numero_oc}", "proveedor": r.proveedor,
                        "product_code": r.product_code, "cantidad": r.cantidad, "fecha": r.fecha_prevista,
                        "almacen": r.warehouse_code, "atrasada": r.fecha_prevista < hoy, "checks": checks_of("COMPRA", r.id)})
    for x in db().execute(select(ImportShipment)).scalars():
        if x.estado in ESTADOS_IMPORT_CERRADOS or not x.fecha_llegada_estimada or x.fecha_llegada_estimada > hasta:
            continue
        out.append({"tipo": "IMPORTACION", "id": x.id, "doc": f"Importación {x.referencia}", "proveedor": x.proveedor,
                    "product_code": x.product_code, "cantidad": x.cantidad, "fecha": x.fecha_llegada_estimada,
                    "almacen": getattr(x, "warehouse_code", "") or "", "atrasada": x.fecha_llegada_estimada < hoy,
                    "checks": checks_of("IMPORTACION", x.id)})
    return sorted(out, key=lambda a: (a["fecha"], a["doc"]))


def checks_of(tipo, entidad_id):
    return list(db().execute(select(ArrivalCheck).where(ArrivalCheck.tipo == tipo, ArrivalCheck.entidad_id == int(entidad_id))
                             .order_by(ArrivalCheck.id)).scalars())


def register_arrival_check(user, tipo, entidad_id, cantidad_ingresa, conforme, motivo="", foto="", placa="", chofer="",
                           hora=""):
    """Seguridad valida lo que va ingresando; ante cualquier incidente (no conforme) notifica a Almacén, Compras o
    Importaciones y Logística."""
    if not has_perm(user, "seguridad.llegadas"):
        raise BusinessError("El control de llegadas lo registra Seguridad.")
    if tipo == "COMPRA":
        doc = db().get(PurchaseRequest, int(entidad_id))
        ref = f"OC {doc.numero_oc}" if doc else ""
    elif tipo == "IMPORTACION":
        doc = db().get(ImportShipment, int(entidad_id))
        ref = f"importación {doc.referencia}" if doc else ""
    else:
        raise BusinessError("Tipo de llegada no válido.")
    if doc is None:
        raise BusinessError("Documento no encontrado.")
    if not conforme and not (motivo or "").strip():
        raise BusinessError("Indique el incidente o motivo de la no conformidad.")
    if cantidad_ingresa is not None and cantidad_ingresa < 0:
        raise BusinessError("Cantidad inválida.")
    c = ArrivalCheck(tipo=tipo, entidad_id=doc.id, product_code=doc.product_code, cantidad_esperada=doc.cantidad,
                     cantidad_ingresa=cantidad_ingresa, placa=(placa or "").strip().upper(), chofer=(chofer or "").strip(),
                     conforme=bool(conforme), motivo=(motivo or "").strip(), foto=foto or "",
                     hora=(hora or "").strip() or f"{now():%H:%M}", user_id=user.id)
    db().add(c)
    db().flush()
    if not conforme:
        alerts.emit("LLEGADA_INCIDENTE", f"Incidente en la llegada de {ref} ({doc.product_code})",
                    f"Seguridad: {c.motivo}. Ingresa {cantidad_ingresa if cantidad_ingresa is not None else '-'} de "
                    f"{doc.cantidad:g}." + (f" Placa {c.placa}." if c.placa else "") + (" Con foto." if foto else ""),
                    "PurchaseRequest" if tipo == "COMPRA" else "ImportShipment", doc.id, creado_por=user)
    audit(user, "SEGURIDAD_LLEGADA", tipo, doc.id, {"conforme": c.conforme, "motivo": c.motivo, "cantidad": cantidad_ingresa,
                                                    "foto": foto})
    return c
