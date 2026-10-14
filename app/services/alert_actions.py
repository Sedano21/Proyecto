"""Aprobar o desaprobar desde la alerta (observaciones al demo v0.6, Jefe Comercial).

Cada tipo de alerta que espera una aprobación se conecta con la misma regla de negocio de su pantalla, de modo que el
sistema deriva el siguiente paso al área que corresponde (p. ej. Comercial aprueba el precio -> se evalúa la OV ->
Almacén recibe las opciones). Desaprobar siempre exige motivo; aprobar algo por debajo o fuera del parámetro
establecido también.
"""
from ..db import db
from ..models import (OVChangeRequest, PurchaseRequest, RepackRequest, Route, SalesOrder, Transfer)
from .core import BusinessError, audit


def _get(model, alert):
    try:
        obj = db().get(model, int(alert.entidad_id))
    except (TypeError, ValueError):
        obj = None
    if obj is None:
        raise BusinessError("No se encontró el documento de la alerta.")
    return obj


def _precio(alert, user, aprobar, motivo):
    from . import prices
    o = _get(SalesOrder, alert)
    return prices.approve_price(o, user, motivo) if aprobar else prices.reject_price(o, user, motivo)


def _traslado(alert, user, aprobar, motivo):
    from . import transfers
    transfers.authorize(_get(Transfer, alert), user, aprobar, motivo)


def _reempaque_pre(alert, user, aprobar, motivo):
    from . import repack
    repack.approve_presolicitud(_get(RepackRequest, alert), user, aprobar, motivo)


def _reempaque_eval(alert, user, aprobar, motivo):
    from . import repack
    repack.evaluate(_get(RepackRequest, alert), user, aprobar, motivo)


def _compra_log(alert, user, aprobar, motivo):
    from . import purchasing
    purchasing.approve_logistics(_get(PurchaseRequest, alert), user, aprobar, motivo)


def _compra_go(alert, user, aprobar, motivo):
    from . import purchasing
    purchasing.approve_go(_get(PurchaseRequest, alert), user, aprobar, motivo)


def _modif(alert, user, aprobar, motivo):
    from . import orders
    orders.resolve_change(_get(OVChangeRequest, alert), user, aprobar, motivo)


def _externo(alert, user, aprobar, motivo):
    from . import distribution
    distribution.validate_external(_get(Route, alert), user, aprobar, motivo)


# tipo -> (función, ¿aprobar está fuera del parámetro establecido? -> motivo obligatorio)
HANDLERS = {
    "OV_PRECIO_BAJO_MINIMO": (_precio, True),
    "OV_PRECIO_BAJO_COSTO": (_precio, True),
    "TRASLADO_SOLICITADO": (_traslado, False),
    "REEMPAQUE_PRESOLICITUD": (_reempaque_pre, False),
    "REEMPAQUE_SOLICITUD": (_reempaque_eval, True),  # Calidad registra el resultado del muestreo
    "COMPRA_APROBACION_LOGISTICA": (_compra_log, False),
    "COMPRA_APROBACION_GERENCIA": (_compra_go, False),
    "OV_MODIF_SOLICITUD": (_modif, False),
    "RUTA_EXTERNO_VALIDAR": (_externo, False),
}


def can_decide(alert):
    return alert.type_code in HANDLERS and alert.estado not in ("COMPLETADA", "DESAPROBADA", "RECONOCIDA")


def motivo_obligatorio(alert, aprobar=True):
    return (not aprobar) or HANDLERS.get(alert.type_code, (None, False))[1]


def decide(alert, user, aprobar, motivo=""):
    """Confirmación/aprobación o desistimiento/desaprobación desde la alerta."""
    from . import alerts
    if not alerts.can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if not can_decide(alert):
        raise BusinessError("Esta alerta no tiene una aprobación asociada o ya está cerrada.")
    if alert.estado == "INCIDENCIA":
        raise BusinessError("La tarea tiene una incidencia abierta: resuélvala primero.")
    motivo = (motivo or "").strip()
    if motivo_obligatorio(alert, aprobar) and not motivo:
        raise BusinessError("Indique el motivo: " + ("se desaprueba o desiste." if not aprobar else
                                                     "se aprueba algo por debajo o fuera del parámetro establecido."))
    fn, _ = HANDLERS[alert.type_code]
    fn(alert, user, aprobar, motivo)
    db().flush()
    if alert.estado not in alerts.CERRADOS:  # si la regla no la cerró, se cierra con el resultado
        alerts._finish(alert, user, "COMPLETADA" if aprobar else "DESAPROBADA", motivo or "Aprobada",
                       "Aprobada desde la alerta" if aprobar else "Desaprobada desde la alerta",
                       "APROBADA" if aprobar else "DESAPROBADA")
    else:
        alert.estado = "COMPLETADA" if aprobar else "DESAPROBADA"
        alert.resultado = "APROBADA" if aprobar else "DESAPROBADA"
        alert.cerrado_por = user.id
    if not alert.asignado_a and not alert.asignado_rol:
        alert.asignado_a = user.id
    audit(user, "ALERTA_" + ("APROBADA" if aprobar else "DESAPROBADA"), "Alert", alert.id,
          {"tipo": alert.type_code, "entidad": alert.entidad, "entidad_id": alert.entidad_id, "motivo": motivo})
