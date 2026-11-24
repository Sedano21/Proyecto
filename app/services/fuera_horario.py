"""V70 (24-nov-2026): OV ingresadas fuera del horario permitido (después de la hora de corte, producto terminado para
despachar al día siguiente).

1. La OV queda en borrador (como antes) y Comercial solicita la aprobación con un motivo.
2. El Jefe de Operaciones aprueba o desestima.
   - Si aprueba, la OV se registra y sigue su curso normal.
   - Si la desestima (con motivo), Comercial puede elevarla a Gerencia General.
3. Gerencia General decide en última instancia.
Almacén ve en «Pedidos de última hora» las OV fuera de horario aprobadas y las que están por decidir."""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import SalesOrder, now
from . import alerts
from .core import BusinessError, audit, has_perm

NOMBRE = {"PENDIENTE": "Por aprobar (Jefe de Operaciones)", "APROBADA": "Aprobada por el Jefe de Operaciones",
          "DESESTIMADA": "Desestimada por el Jefe de Operaciones", "ELEVADA": "Elevada a Gerencia General",
          "APROBADA_GG": "Aprobada por Gerencia General", "RECHAZADA_GG": "Rechazada por Gerencia General"}


def es_fuera_de_corte(o):
    from .orders import check_cutoff
    if o.estado != "BORRADOR" or o.origen != "MODULO":
        return False
    try:
        check_cutoff(o.fecha_compromiso, productos=[l.product_code for l in o.lines if l.activa])
    except BusinessError:
        return True
    return False


def _hist(o, accion, user, comentario="", estado=None):
    fh = dict(o.fuera_horario or {})
    fh.setdefault("historial", [])
    fh["historial"] = list(fh["historial"]) + [{"accion": accion, "user": user.nombre, "user_id": user.id,
                                               "ts": now().isoformat(timespec="minutes"), "comentario": comentario}]
    if estado:
        fh["estado"] = estado
    o.fuera_horario = fh
    return fh


def solicitar(user, o, motivo):
    if not (has_perm(user, "ov.crear") or has_perm(user, "ov.modificar")):
        raise BusinessError("Solicita la aprobación Comercial.")
    if not es_fuera_de_corte(o):
        raise BusinessError("La OV no está detenida por la hora de corte.")
    if (o.fuera_horario or {}).get("estado") in ("PENDIENTE", "ELEVADA"):
        raise BusinessError("Ya hay una solicitud en curso.")
    if not (motivo or "").strip():
        raise BusinessError("Indique por qué se ingresa fuera de horario.")
    fh = _hist(o, "SOLICITADA", user, motivo.strip(), "PENDIENTE")
    fh["motivo"] = motivo.strip()[:300]
    fh["solicitada_por"] = user.nombre
    o.fuera_horario = fh
    alerts.emit("OV_FUERA_HORARIO", f"OV {o.numero} fuera de horario: aprobar", f"{o.customer.nombre} · despacho "
                f"{o.fecha_compromiso:%d/%m/%Y}. Motivo: {motivo.strip()}", "SalesOrder", o.id, prioridad="ALTA",
                dedup_key=f"OV_FH:{o.id}:{len(fh['historial'])}", creado_por=user)
    audit(user, "OV_FUERA_HORARIO_SOLICITADA", "SalesOrder", o.numero, {"motivo": motivo})


def _registrar(o, user):
    from .orders import _complete_draft
    if not _complete_draft(o, user):
        raise BusinessError(o.motivo_detencion or "La OV aún no cumple lo necesario para registrarse.")


def decidir_jo(user, o, aprobar, comentario=""):
    if not has_perm(user, "ov.aprobar_fuera_horario"):
        raise BusinessError("Aprueba el Jefe de Operaciones.")
    if (o.fuera_horario or {}).get("estado") != "PENDIENTE":
        raise BusinessError("La OV no está por aprobar.")
    if not aprobar and not (comentario or "").strip():
        raise BusinessError("Indique por qué la desestima.")
    _hist(o, "APROBADA" if aprobar else "DESESTIMADA", user, (comentario or "").strip(),
          "APROBADA" if aprobar else "DESESTIMADA")
    if aprobar:
        _registrar(o, user)
    _avisar(o, user, "aprobó" if aprobar else "desestimó", comentario)
    audit(user, "OV_FUERA_HORARIO_" + ("APROBADA" if aprobar else "DESESTIMADA"), "SalesOrder", o.numero,
          {"comentario": comentario})


def elevar(user, o, motivo):
    if not (has_perm(user, "ov.crear") or has_perm(user, "ov.modificar")):
        raise BusinessError("Eleva Comercial.")
    if (o.fuera_horario or {}).get("estado") != "DESESTIMADA":
        raise BusinessError("Solo se eleva una OV que el Jefe de Operaciones desestimó.")
    if not (motivo or "").strip():
        raise BusinessError("Indique por qué la eleva a Gerencia General.")
    _hist(o, "ELEVADA", user, motivo.strip(), "ELEVADA")
    alerts.emit("OV_FUERA_HORARIO_GG", f"OV {o.numero} fuera de horario elevada a Gerencia General",
                f"{o.customer.nombre} · despacho {o.fecha_compromiso:%d/%m/%Y}. El Jefe de Operaciones la desestimó. "
                f"Motivo de Comercial: {motivo.strip()}", "SalesOrder", o.id, prioridad="ALTA", creado_por=user)
    audit(user, "OV_FUERA_HORARIO_ELEVADA", "SalesOrder", o.numero, {"motivo": motivo})


def decidir_gg(user, o, aprobar, comentario=""):
    if not has_perm(user, "ov.decision_gg"):
        raise BusinessError("Decide Gerencia General.")
    if (o.fuera_horario or {}).get("estado") != "ELEVADA":
        raise BusinessError("La OV no está elevada a Gerencia General.")
    if not aprobar and not (comentario or "").strip():
        raise BusinessError("Indique el motivo.")
    _hist(o, "APROBADA_GG" if aprobar else "RECHAZADA_GG", user, (comentario or "").strip(),
          "APROBADA_GG" if aprobar else "RECHAZADA_GG")
    if aprobar:
        _registrar(o, user)
    _avisar(o, user, "aprobó (Gerencia General)" if aprobar else "rechazó (Gerencia General)", comentario)
    audit(user, "OV_FUERA_HORARIO_GG", "SalesOrder", o.numero, {"aprobada": aprobar, "comentario": comentario})


def _avisar(o, user, verbo, comentario):
    destino = [o.vendedor_id] if o.vendedor_id else []
    solicitantes = [h.get("user_id") for h in (o.fuera_horario or {}).get("historial", []) if h.get("accion") == "SOLICITADA"]
    alerts.emit("OV_FUERA_HORARIO_RESPUESTA", f"OV {o.numero} fuera de horario: {verbo}", comentario or "", "SalesOrder", o.id,
                extra_users=destino + [x for x in solicitantes if x], creado_por=user)


def listado(dias=7):
    """OV con solicitud fuera de horario (por decidir y aprobadas recientes) y las detenidas por el corte sin solicitud."""
    desde = date.today() - timedelta(days=dias)
    con = [o for o in db().execute(select(SalesOrder).where(SalesOrder.fecha_compromiso >= desde)).scalars()
           if (o.fuera_horario or {}).get("estado")]
    sin = [o for o in db().execute(select(SalesOrder).where(SalesOrder.estado == "BORRADOR", SalesOrder.fecha_compromiso >= date.today()))
           .scalars() if not (o.fuera_horario or {}).get("estado") and es_fuera_de_corte(o)]
    orden = {"PENDIENTE": 0, "ELEVADA": 1, "DESESTIMADA": 2, "APROBADA": 3, "APROBADA_GG": 3, "RECHAZADA_GG": 4}
    con.sort(key=lambda o: (orden.get(o.fuera_horario.get("estado"), 9), o.fecha_compromiso))
    return {"con": con, "sin": sin}
