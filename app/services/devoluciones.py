"""V22 (06-nov-2026): recepción de devoluciones en almacén.

Cuando una entrega vuelve total o parcialmente (devolución, rechazo, cliente ausente o entrega parcial), queda una
recepción PENDIENTE para Almacén. Almacén la contrasta con la guía cuando llega: cantidad, presentación y si llegó dañado.
Si hay observaciones adjunta foto o video. Lo devuelto ya ingresó como «Pendiente de revisión» (flujo existente); esta
recepción confirma lo que llegó.

V23 (06-nov-2026): no hay hora de corte. Si al volver no hay personal de almacén para recibir, el chofer o Distribución
lo reporta («sin personal para recibir»): la recepción pasa a EN_VEHICULO, la mercadería queda en el vehículo y Almacén
y Logística reciben una alerta hasta que la reciban. «plazo» queda como la fecha en que se registró la devolución.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import ReturnReceipt, now
from . import alerts
from .core import BusinessError, audit, has_perm, param


POR_RECIBIR = ("PENDIENTE", "EN_VEHICULO")


def _plazo(momento=None):
    """V23: sin hora de corte; la fecha de referencia es el día en que se registra la devolución."""
    return (momento or now()).date()


def create_for(order, user, tipo="TOTAL", incident=None, stop=None, lineas=None):
    """Crea la recepción pendiente (una por incidencia). lineas: [{line_id, devuelto}] para parciales."""
    if incident is not None and db().execute(select(ReturnReceipt).where(ReturnReceipt.incident_id == incident.id)).first():
        return None
    por_id = {l.id: l for l in order.lines}
    esperado = []
    if lineas:
        for x in lineas:
            l = por_id.get(int(x.get("line_id") or 0))
            q = float(x.get("devuelto") or 0)
            if l is not None and q > 0:
                esperado.append(_linea(l, q))
    else:
        for l in order.lines:
            q = (l.despachado or 0) - (l.entregado or 0)
            if q > 1e-9:
                esperado.append(_linea(l, q))
    if not esperado:
        return None
    r = ReturnReceipt(order_id=order.id, incident_id=incident.id if incident is not None else None,
                      route_id=stop.route_id if stop is not None else None, tipo=tipo,
                      guia_numero=(stop.guia_numero if stop is not None else "") or "", esperado=esperado, plazo=_plazo())
    db().add(r)
    db().flush()
    alerts.emit("DEVOLUCION_POR_RECIBIR", f"Devolución {tipo.lower()} de OV {order.numero} por recibir",
                f"{order.customer.nombre}: " + "; ".join(f"{e['producto']} {e['cantidad']:g}" for e in esperado)
                + f". Contrastar con la guía {r.guia_numero or '-'} cuando llegue el vehículo.",
                "ReturnReceipt", r.id, dedup_key=f"DEVREC:{r.id}", creado_por=user)
    return r


def _linea(l, q):
    p = l.product
    return {"line_id": l.id, "producto": l.product_code, "descripcion": (p.descripcion if p else "")[:120],
            "presentacion": (p.presentacion if p else "") or (p.um if p else ""), "cantidad": round(q, 4)}


def receive(user, r, datos, evidencias=None, observacion=""):
    """datos: {line_id: {cantidad, presentacion_ok, danado, detalle}}."""
    if not has_perm(user, "devoluciones.recibir"):
        raise BusinessError("Las devoluciones las recibe Almacén.")
    if r.estado not in POR_RECIBIR:
        raise BusinessError("La devolución ya fue recibida.")
    recibido, difs = [], []
    for e in r.esperado:
        d = datos.get(str(e["line_id"])) or {}
        try:
            q = float(d.get("cantidad")) if d.get("cantidad") not in (None, "") else None
        except (TypeError, ValueError):
            raise BusinessError(f"{e['producto']}: cantidad recibida inválida.") from None
        if q is None or q < 0:
            raise BusinessError(f"{e['producto']}: indique la cantidad que llegó.")
        pres_ok = str(d.get("presentacion_ok", "1")) == "1"
        danado = str(d.get("danado", "0")) == "1"
        detalle = (d.get("detalle") or "").strip()
        if abs(q - float(e["cantidad"])) > 1e-6:
            difs.append(f"{e['producto']}: guía {e['cantidad']:g}, llegó {q:g}")
        if not pres_ok:
            difs.append(f"{e['producto']}: presentación distinta")
        if danado:
            difs.append(f"{e['producto']}: dañado")
        if (danado or not pres_ok) and not detalle:
            raise BusinessError(f"{e['producto']}: describa el daño o la diferencia de presentación.")
        recibido.append({"line_id": e["line_id"], "cantidad": q, "presentacion_ok": pres_ok, "danado": danado,
                         "detalle": detalle})
    evidencias = [x for x in (evidencias or []) if x]
    observacion = (observacion or "").strip()
    if (difs or observacion) and not evidencias:
        raise BusinessError("Hay observaciones: adjunte foto o video de la evidencia.")
    r.recibido = recibido
    r.evidencias = evidencias
    r.observacion = observacion
    r.estado = "OBSERVADA" if difs else "CONFORME"
    r.recibido_por = user.id
    r.recibido_ts = now()
    alerts.close_by_system(f"DEVREC:{r.id}", f"Recibida por {user.nombre}")
    alerts.close_by_system(f"DEVVEH:{r.id}", f"Recibida por {user.nombre}")
    if difs:
        alerts.emit("DEVOLUCION_OBSERVADA", f"Devolución de OV {r.order.numero} con observaciones",
                    "; ".join(difs) + (f". {observacion}" if observacion else ""), "ReturnReceipt", r.id,
                    dedup_key=f"DEVOBS:{r.id}", creado_por=user)
    audit(user, "DEVOLUCION_RECIBIDA", "ReturnReceipt", r.id, {"estado": r.estado, "diferencias": difs,
                                                                "evidencias": len(evidencias)})
    return difs


def leave_in_vehicle(user, r, motivo, evidencias=None):
    """V23: no hay personal de almacén para recibir; la mercadería queda en el vehículo hasta que Almacén la reciba."""
    from ..models import Route
    if not has_perm(user, "devoluciones.dejar_en_vehiculo"):
        raise BusinessError("Lo reporta el chofer, Distribución o Almacén.")
    if r.estado != "PENDIENTE":
        raise BusinessError("Solo una devolución por recibir puede quedar en el vehículo.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise BusinessError("Indique el motivo (p. ej. «no hay personal de almacén disponible para recibir»).")
    rt = db().get(Route, r.route_id) if r.route_id else None
    veh = ""
    if rt is not None:
        veh = (rt.vehicle.placa if rt.vehicle is not None else "") or (rt.transportista or {}).get("placa", "")
    r.estado = "EN_VEHICULO"
    r.en_vehiculo = {"motivo": motivo, "user": user.nombre, "user_id": user.id, "ts": now().isoformat(timespec="minutes"),
                     "vehiculo": veh, "evidencias": [x for x in (evidencias or []) if x]}
    alerts.emit("DEVOLUCION_EN_VEHICULO", f"Devolución de OV {r.order.numero} quedó en el vehículo {veh or ''}".strip(),
                f"{user.nombre}: {motivo}. Recibir y contrastar con la guía {r.guia_numero or '-'} en cuanto haya personal.",
                "ReturnReceipt", r.id, dedup_key=f"DEVVEH:{r.id}", creado_por=user)
    audit(user, "DEVOLUCION_EN_VEHICULO", "ReturnReceipt", r.id, {"motivo": motivo, "vehiculo": veh})
    return r


def pending(hoy=None):
    return list(db().execute(select(ReturnReceipt).where(ReturnReceipt.estado.in_(POR_RECIBIR))
                             .order_by(ReturnReceipt.plazo, ReturnReceipt.id)).scalars())


def check_overdue(hoy=None):
    """V23: sin hora de corte ni plazo de recepción; las que quedan en el vehículo mantienen su alerta abierta hasta que
    Almacén las reciba. Se conserva la función para la tarea programada (no emite alertas)."""
    return 0
