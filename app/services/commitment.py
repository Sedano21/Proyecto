"""Compromiso de entrega (ronda 23-oct-2026): al registrarse una OV, Operaciones responde CUMPLE / NO CUMPLE dentro del
plazo configurado (plazo_respuesta_cumplimiento_horas). Con stock completo reservado el sistema responde CUMPLE solo.
NO CUMPLE (o el aviso posterior de que no se llegará) alerta a Comercial para que negocie con el cliente; sin respuesta
en el plazo se alerta a Operaciones y a Comercial."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import SalesOrder, now
from . import alerts
from .core import BusinessError, audit, has_perm, param
from .stock import ORDEN_ESTADOS_CERRADOS

ESTADOS = {"PENDIENTE": "Pendiente de respuesta", "CUMPLE": "Cumple", "NO_CUMPLE": "No cumple"}


def _iso(ts):
    return ts.isoformat(timespec="minutes")


def open_commitment(order, ahora=None):
    """Abre el compromiso al registrar o activar la OV. Con stock completo se responde CUMPLE automáticamente."""
    if order.estado in ORDEN_ESTADOS_CERRADOS or order.estado in ("BORRADOR", "REGULARIZADA"):
        return
    ahora = ahora or now()
    horas = float(param("plazo_respuesta_cumplimiento_horas", 24) or 24)
    if order.estado_stock == "COMPLETA":
        order.compromiso = {"estado": "CUMPLE", "automatico": True, "ts": _iso(ahora),
                            "detalle": "Stock completo reservado al evaluar la OV.", "historial": []}
        return
    order.compromiso = {"estado": "PENDIENTE", "desde": _iso(ahora), "vence": _iso(ahora + timedelta(hours=horas)),
                        "historial": []}


def respond(order, user, cumple, motivo="", fecha_estimada=None):
    """Operaciones (Almacén, Logística o Producción) responde. Se puede cambiar a NO CUMPLE después (aviso de que no se
    llegará)."""
    if not has_perm(user, "ov.compromiso"):
        raise BusinessError("Responden Almacén, Logística o Producción.")
    if order.estado in ORDEN_ESTADOS_CERRADOS or order.estado == "BORRADOR":
        raise BusinessError(f"La OV está {order.estado}.")
    motivo = (motivo or "").strip()
    if not cumple and not motivo:
        raise BusinessError("Indique por qué no se cumplirá (falta de stock, producción, compra…) para que Comercial negocie.")
    if isinstance(fecha_estimada, str):
        fecha_estimada = date.fromisoformat(fecha_estimada) if fecha_estimada else None
    previo = dict(order.compromiso or {})
    hist = list(previo.get("historial") or [])
    if previo.get("estado") and previo.get("estado") != "PENDIENTE":
        hist.append({k: previo.get(k) for k in ("estado", "ts", "user", "motivo", "fecha_estimada")})
    order.compromiso = {"estado": "CUMPLE" if cumple else "NO_CUMPLE", "ts": _iso(now()), "user": user.nombre,
                        "user_id": user.id, "motivo": motivo,
                        "fecha_estimada": fecha_estimada.isoformat() if fecha_estimada else None,
                        "desde": previo.get("desde"), "vence": previo.get("vence"), "historial": hist}
    alerts.close_by_system(f"OV_SIN_COMPROMISO:{order.id}", "Operaciones respondió")
    if not cumple:
        alerts.emit("OV_NO_CUMPLE", f"OV {order.numero}: Operaciones NO cumplirá la fecha {order.fecha_compromiso:%d/%m/%Y}",
                    f"{order.customer.nombre}. Motivo: {motivo}"
                    + (f". Fecha estimada: {fecha_estimada:%d/%m/%Y}" if fecha_estimada else "") + f". Respondió {user.nombre}.",
                    "SalesOrder", order.id, extra_users=[order.vendedor_id] if order.vendedor_id else None,
                    dedup_key=f"OV_NO_CUMPLE:{order.id}:{len(hist)}", creado_por=user)
    audit(user, "OV_COMPROMISO", "SalesOrder", order.numero, {"cumple": cumple, "motivo": motivo,
                                                               "fecha_estimada": fecha_estimada})
    return order


def refresh_auto(order):
    """Si una OV pendiente queda con stock completo, se marca CUMPLE automáticamente."""
    c = order.compromiso or {}
    if c.get("estado") == "PENDIENTE" and order.estado_stock == "COMPLETA":
        order.compromiso = dict(c, estado="CUMPLE", automatico=True, ts=_iso(now()),
                                detalle="Stock completo reservado en una nueva evaluación.")
        alerts.close_by_system(f"OV_SIN_COMPROMISO:{order.id}", "Stock completo")


def check_pending(ahora=None):
    """Tarea periódica: OV sin respuesta en el plazo → alerta a Operaciones y a Comercial (una vez por OV)."""
    ahora = ahora or now()
    n = 0
    for o in db().execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS + ("BORRADOR",)))).scalars():
        c = o.compromiso or {}
        if c.get("estado") != "PENDIENTE":
            continue
        refresh_auto(o)
        if (o.compromiso or {}).get("estado") != "PENDIENTE" or not c.get("vence"):
            continue
        if datetime.fromisoformat(c["vence"]) > ahora:
            continue
        from .shifts import _avisado
        if _avisado(f"OV_SIN_COMPROMISO:{o.id}"):
            continue
        if alerts.emit("OV_SIN_COMPROMISO", f"OV {o.numero} sin respuesta CUMPLE / NO CUMPLE",
                       f"{o.customer.nombre}; despacho {o.fecha_compromiso:%d/%m/%Y}. Plazo vencido el "
                       f"{datetime.fromisoformat(c['vence']):%d/%m/%Y %H:%M}. Cobertura {o.cobertura_unidades}%.",
                       "SalesOrder", o.id, extra_roles=["JEFE_VENTAS", "COORD_VENTAS"],
                       extra_users=[o.vendedor_id] if o.vendedor_id else None,
                       dedup_key=f"OV_SIN_COMPROMISO:{o.id}") is not None:
            n += 1
    return n


def production_days():
    return param("dias_produccion_por_tipo", {}) or {}
