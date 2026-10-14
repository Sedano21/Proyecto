"""Programación del picking por persona (observaciones al demo v0.6, Líder Operativo y Coordinador de Almacén).

- Al quedar una OV lista para preparar, el sistema preprograma el picking por almacén (fecha y auxiliar propuesto
  según la carga del día) y avisa al Líder Operativo y al Coordinador del almacén, que ven el detalle (tipo, cantidad,
  lote, mercadería, auxiliar asignado) y pueden reasignarlo a otra persona o a un grupo.
- El auxiliar recibe su programación diaria y semanal; durante el picking registra lo que antes llenaba a mano en el
  formato 'Seguimiento de control de despacho de producto terminado' (despachado, lote, fecha de producción y fecha de
  vencimiento), sube foto al iniciar y al dejar todo listo para trasladar al despacho.
- La dotación por almacén sale de los usuarios activos con su almacén asignado (1560: auxiliares, líderes y
  montacarguistas; 1524: auxiliar y montacarguista).
"""
from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import PickingRecord, PickingTask, SalesOrder, User, now
from . import alerts
from .core import BusinessError, audit, has_perm, param, wh_in

ROLES_PICKING = ("AUX_ALMACEN", "LIDER_ALMACEN", "MONTACARGUISTA")


def staff(warehouse_code, roles=ROLES_PICKING):
    """Personal operativo activo del almacén."""
    q = select(User).where(User.activo.is_(True), User.role_code.in_(roles)).order_by(User.role_code, User.nombre)
    return [u for u in db().execute(q).scalars() if u.almacen and wh_in(warehouse_code, [u.almacen])]


def _fecha_programada(order, hoy=None):
    hoy = hoy or date.today()
    antes = int(param("dias_picking_antes_despacho", 1) or 0)
    return max(hoy, order.fecha_compromiso - timedelta(days=antes))


def _warehouses(order):
    whs = []
    for l in order.lines:
        for r in l.reservations:
            if r.estado == "ACTIVA" and r.lot.warehouse_code not in whs:
                whs.append(r.lot.warehouse_code)
    return whs


def tasks_of(order):
    return list(db().execute(select(PickingTask).where(PickingTask.order_id == order.id).order_by(PickingTask.id)).scalars())


def preschedule(order, user=None, hoy=None):
    """Preprograma el picking de la OV (una tarea por almacén) con el auxiliar de menor carga ese día."""
    from .orders import ready_for_preparation
    if not ready_for_preparation(order):
        return []
    existentes = {t.warehouse_code for t in tasks_of(order)}
    nuevas = []
    for wh in _warehouses(order):
        if wh in existentes:
            continue
        fecha = _fecha_programada(order, hoy)
        auxs = staff(wh, ("AUX_ALMACEN",))
        carga = Counter()
        for t in db().execute(select(PickingTask).where(PickingTask.fecha == fecha)).scalars():
            for uid in t.asignados or []:
                carga[uid] += 1
        propuesto = min(auxs, key=lambda u: (carga[u.id], u.id)) if auxs else None
        t = PickingTask(order_id=order.id, warehouse_code=wh, fecha=fecha, asignados=[propuesto.id] if propuesto else [])
        db().add(t)
        db().flush()
        nuevas.append(t)
        alerts.emit("PICKING_PROGRAMADO", f"Picking preprogramado: OV {order.numero} ({wh}) para el {fecha:%d/%m/%Y}",
                    f"Cliente {order.customer.nombre}. Auxiliar propuesto: {propuesto.nombre if propuesto else 'sin auxiliar con almacén asignado'}. "
                    "Revise el detalle y asigne o modifique.", "SalesOrder", order.id, creado_por=user,
                    dedup_key=f"PICKING_PROG:{t.id}")
        if propuesto:
            _avisar(t, [propuesto.id], user)
    return nuevas


def _avisar(t, ids, user):
    alerts.emit("PICKING_ASIGNADO", f"Picking asignado: OV {t.order.numero} el {t.fecha:%d/%m/%Y}",
                f"Almacén {t.warehouse_code}. Cliente {t.order.customer.nombre}.", "SalesOrder", t.order_id,
                extra_users=ids, creado_por=user, dedup_key=f"PICKING_ASIG:{t.id}:{','.join(map(str, sorted(ids)))}")


def assign(t, user, user_ids, fecha=None, comentario=""):
    """Asigna (o reasigna) el picking a una persona o a un grupo del mismo almacén."""
    from .core import check_warehouse_scope
    if not has_perm(user, "picking.asignar"):
        raise BusinessError("El picking lo asigna el Líder Operativo o el Coordinador de Almacén.")
    if t.estado == "LISTO":
        raise BusinessError("El picking ya está listo para despacho.")
    if user.role_code.startswith("COORD_ALMACEN"):
        check_warehouse_scope(user, t.warehouse_code)
    ids = sorted({int(x) for x in user_ids if str(x).strip()})
    if not ids:
        raise BusinessError("Seleccione al menos una persona.")
    validos = {u.id for u in staff(t.warehouse_code)}
    if any(i not in validos for i in ids):
        raise BusinessError("Solo puede asignar personal del almacén del picking.")
    antes = list(t.asignados or [])
    t.asignados = ids
    if fecha:
        t.fecha = fecha
    t.asignado_por = user.id
    if comentario:
        t.observacion = (t.observacion + "\n" if t.observacion else "") + f"{user.nombre}: {comentario}"
    alerts.close_by_system(f"PICKING_PROG:{t.id}", f"Asignado por {user.nombre}")
    _avisar(t, [i for i in ids if i not in antes] or ids, user)
    audit(user, "PICKING_ASIGNADO", "SalesOrder", t.order.numero, {"tarea": t.id, "antes": antes, "despues": ids,
                                                                   "fecha": t.fecha.isoformat()})


def _es_asignado(t, user):
    return user.id in (t.asignados or []) or has_perm(user, "picking.asignar")


def start(t, user, foto):
    if not _es_asignado(t, user):
        raise BusinessError("Este picking no le fue asignado.")
    if t.estado != "PROGRAMADO":
        raise BusinessError("El picking ya fue iniciado.")
    if not foto:
        raise BusinessError("Tome la foto al iniciar el picking.")
    t.estado, t.inicio_ts, t.foto_inicio = "EN_PROCESO", now(), foto
    audit(user, "PICKING_INICIADO", "SalesOrder", t.order.numero, {"tarea": t.id})


def record(t, user, line_id, cantidad, lote, fecha_produccion=None, fecha_venc=None, comentario=""):
    """Registro del picking como en el formato: despachado, lote, fecha de producción y de vencimiento."""
    from .orders import register_picking
    if not _es_asignado(t, user):
        raise BusinessError("Este picking no le fue asignado.")
    if t.estado == "PROGRAMADO":
        raise BusinessError("Inicie el picking con su foto antes de registrar.")
    if t.estado == "LISTO":
        raise BusinessError("El picking ya está listo para despacho.")
    order = t.order
    line = next((l for l in order.lines if l.id == int(line_id)), None)
    if line is None:
        raise BusinessError("Línea no encontrada.")
    lot = next((r.lot for r in line.reservations if r.estado == "ACTIVA" and r.lot.lote == lote), None)
    avance = register_picking(order, user, line_id, cantidad, lote)
    db().add(PickingRecord(order_id=order.id, line_id=line.id, task_id=t.id, lote=lote, cantidad=cantidad,
                           fecha_produccion=fecha_produccion or (lot.fecha_fab if lot else None),
                           fecha_venc=fecha_venc or (lot.fecha_venc if lot else None),
                           comentario=(comentario or "").strip(), user_id=user.id))
    if lot and fecha_venc and lot.fecha_venc and fecha_venc != lot.fecha_venc:
        alerts.emit("CARGA_INCONGRUENCIA", f"Picking OV {order.numero}: vencimiento distinto al del sistema",
                    f"Lote {lote}: registrado {fecha_venc:%d/%m/%Y}, sistema {lot.fecha_venc:%d/%m/%Y}.", "SalesOrder",
                    order.id, creado_por=user, dedup_key=f"PICK_VENC:{order.id}:{lote}")
    return avance


def finish(t, user, foto, observacion=""):
    """Todo listo para trasladar al despacho (con foto)."""
    from .orders import prep_progress
    if not _es_asignado(t, user):
        raise BusinessError("Este picking no le fue asignado.")
    if t.estado != "EN_PROCESO":
        raise BusinessError("El picking no está en proceso.")
    if prep_progress(t.order) < 100 - 1e-9:
        raise BusinessError("Aún hay líneas pendientes de picking.")
    if not foto:
        raise BusinessError("Tome la foto de la mercadería lista.")
    t.estado, t.fin_ts, t.foto_listo = "LISTO", now(), foto
    if observacion:
        t.observacion = (t.observacion + "\n" if t.observacion else "") + observacion
    alerts.emit("MONTACARGUISTA_DESPACHO", f"Picking listo: trasladar OV {t.order.numero} a la zona de despacho",
                f"Almacén {t.warehouse_code}. {observacion}".strip(), "SalesOrder", t.order_id, creado_por=user,
                dedup_key=f"PICK_LISTO:{t.id}")
    audit(user, "PICKING_LISTO", "SalesOrder", t.order.numero, {"tarea": t.id})


def schedule(user, desde, hasta, warehouse=None, solo_mios=False):
    q = select(PickingTask).where(PickingTask.fecha >= desde, PickingTask.fecha <= hasta).order_by(PickingTask.fecha, PickingTask.id)
    rows = list(db().execute(q).scalars())
    if warehouse:
        rows = [t for t in rows if t.warehouse_code == warehouse]
    if solo_mios:
        rows = [t for t in rows if user.id in (t.asignados or [])]
    return rows


def format_rows(tasks):
    """Filas del formato 'Seguimiento de control de despacho de producto terminado'."""
    out = []
    for t in tasks:
        o = t.order
        recs = list(db().execute(select(PickingRecord).where(PickingRecord.task_id == t.id)).scalars())
        for l in o.lines:
            if not l.activa:
                continue
            mios = [r for r in recs if r.line_id == l.id] or [None]
            for r in mios:
                out.append({"fecha": t.fecha, "ov": o.numero, "codigo": l.product_code, "cliente": o.customer.nombre,
                            "descripcion": l.product.descripcion if l.product else "", "solicitado": l.cantidad,
                            "despachado": r.cantidad if r else None, "lote": r.lote if r else "",
                            "fecha_produccion": r.fecha_produccion if r else None, "fecha_venc": r.fecha_venc if r else None,
                            "comentario": (r.comentario if r and r.comentario else o.lugar_entrega or o.distrito)})
    return out


def users_by_id():
    return {u.id: u for u in db().execute(select(User)).scalars()}
