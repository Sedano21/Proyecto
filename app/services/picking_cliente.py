"""V43 (14-nov-2026): un solo picking por cliente, fecha de despacho y almacén.

Las reglas no cambian: cada OV sigue con su tarea de picking (asignación, foto de inicio, registro por lote y foto de
listo). Aquí se hacen juntas: se asigna una vez, se inicia una vez, el auxiliar ve una sola lista consolidada por
producto y lote (la suma de todas las OV del cliente para ese despacho) y registra lo que pickeó; el sistema lo reparte
entre las OV en orden. Al final, una sola foto marca listas todas las OV."""
from collections import OrderedDict

from sqlalchemy import select

from ..db import db
from ..models import PickingRecord, PickingTask, SalesOrder
from . import lotes
from . import picking as pk
from .core import BusinessError


def tareas(customer_id, fecha, almacen):
    """Tareas de picking de las OV del cliente con esa fecha de despacho (comprometida) en ese almacén."""
    q = (select(PickingTask).join(SalesOrder, PickingTask.order_id == SalesOrder.id)
         .where(SalesOrder.customer_id == int(customer_id), SalesOrder.fecha_compromiso == fecha,
                PickingTask.warehouse_code == almacen)
         .order_by(SalesOrder.fecha_compromiso, SalesOrder.numero))
    return list(db().execute(q).scalars())


def consolidado(ts):
    """Filas por producto y lote: total a pickear (lo reservado), lo ya registrado y el detalle por OV."""
    db().flush()  # lo registrado en esta misma operación también cuenta
    filas = OrderedDict()
    for t in ts:
        recs = list(db().execute(select(PickingRecord).where(PickingRecord.task_id == t.id)).scalars())
        for l in t.order.lines:
            if not l.activa:
                continue
            res = [r for r in l.reservations if r.estado == "ACTIVA" and r.lot and r.lot.warehouse_code == t.warehouse_code]
            for r in res:
                hecho = sum(x.cantidad or 0 for x in recs if x.line_id == l.id and lotes.misma(x.lote, r.lot.lote))
                k = (l.product_code, r.lot.lote.upper())
                f = filas.setdefault(k, {"producto": l.product_code, "descripcion": l.product.descripcion if l.product else "",
                                         "lote": r.lot.lote, "fp": r.lot.fecha_fab, "fv": r.lot.fecha_venc,
                                         "ubicacion": getattr(r.lot, "ubicacion", "") or "",
                                         "total": 0.0, "hecho": 0.0, "detalle": [], "product": l.product})
                f["total"] += r.cantidad or 0
                f["hecho"] += hecho
                f["detalle"].append({"tarea": t, "ov": t.order.numero, "line_id": l.id, "cantidad": r.cantidad or 0,
                                     "hecho": hecho})
    out = list(filas.values())
    for f in out:
        f["pendiente"] = round(max(f["total"] - f["hecho"], 0), 6)
        f["bultos"] = pk.bultos_de(f["product"], f["total"])
    return out


def resumen(ts):
    estados = {t.estado for t in ts}
    return {"n": len(ts), "estado": "LISTO" if estados == {"LISTO"} else ("EN_PROCESO" if "EN_PROCESO" in estados or
                                                                          "LISTO" in estados else "PROGRAMADO"),
            "asignados": sorted({i for t in ts for i in (t.asignados or [])}),
            "sin_validar": [t.order.numero for t in ts if not t.order.plan_picking_validado and t.estado != "LISTO"]}


def _activas(ts):
    xs = [t for t in ts if t.estado != "LISTO"]
    if not xs:
        raise BusinessError("Todas las OV de este picking ya están listas.")
    return xs


def validar_plan(user, ts):
    """La planificación pre-asignada (lotes reservados) de todas las OV, validada una sola vez."""
    from .orders import validate_picking_plan
    xs = [t for t in _activas(ts) if not t.order.plan_picking_validado]
    if not xs:
        raise BusinessError("La planificación de estas OV ya está validada.")
    for t in xs:
        validate_picking_plan(t.order, user)


def asignar(user, ts, user_ids, fecha=None, comentario="", reportantes=None):
    for t in _activas(ts):
        pk.assign(t, user, user_ids, fecha, comentario, reportantes)


def iniciar(user, ts, foto):
    xs = [t for t in _activas(ts) if t.estado == "PROGRAMADO"]
    if not xs:
        raise BusinessError("El picking ya fue iniciado.")
    for t in xs:
        pk.start(t, user, foto)


def registrar(user, ts, producto, lote, cantidad, bultos=None):
    """Lo pickeado de un producto y lote para todo el cliente: se reparte entre las OV en orden (fecha y número)."""
    if cantidad is None or cantidad <= 0:
        raise BusinessError("Indique la cantidad pickeada.")
    fila = next((f for f in consolidado(ts) if f["producto"] == producto and lotes.misma(f["lote"], lote)), None)
    if fila is None:
        raise BusinessError("Ese producto y lote no está en este picking.")
    if cantidad > fila["pendiente"] + 1e-9:
        raise BusinessError(f"Se pickeó {cantidad:g} pero solo faltan {fila['pendiente']:g} de {producto} lote {fila['lote']} "
                            "para las OV de este cliente. Si sobra, no lo cargue al despacho.")
    resto = cantidad
    for d in fila["detalle"]:
        falta = max(d["cantidad"] - d["hecho"], 0)
        if resto <= 1e-9 or falta <= 1e-9:
            continue
        q = min(resto, falta)
        b = round(bultos * q / cantidad, 2) if bultos else None
        pk.record(d["tarea"], user, d["line_id"], q, fila["lote"], bultos=b)
        resto -= q
    return cantidad


def finalizar(user, ts, foto, observacion=""):
    from .orders import prep_progress
    xs = _activas(ts)
    faltan = [t.order.numero for t in xs if prep_progress(t.order) < 100 - 1e-9]
    if faltan:
        raise BusinessError("Aún hay productos pendientes en las OV " + ", ".join(faltan) + ".")
    for t in xs:
        pk.finish(t, user, foto, observacion)
