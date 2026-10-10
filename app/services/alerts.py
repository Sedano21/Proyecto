"""Motor de alertas (IF §14).

- Canales: panel del módulo y correo (correo real solo si hay SMTP configurado; si no, queda en bandeja
  con estado SIN_SMTP, sin simular el envío). Celular: etapa futura (no implementado).
- Ciclo: NUEVA -> ASIGNADA -> EN_ATENCION -> CERRADA, con comentarios; cada paso registra responsable,
  hora, motivo y acción.
- Visibilidad: destinatarios por rol/usuario; Gerencia General y Sistemas ven todo; Gerencia de Operaciones
  ve las áreas de su ámbito (parámetro).
"""
from sqlalchemy import select

from ..db import db
from ..models import Alert, AlertEvent, AlertType, EmailOutbox, GGAlertPreference, User, now
from .core import BusinessError, audit, has_perm, param, users_with_roles

ESTADOS = ["NUEVA", "ASIGNADA", "EN_ATENCION", "CERRADA"]
PRIORIDAD_ORDEN = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}


def emit(type_code, titulo, mensaje="", entidad="", entidad_id="", prioridad=None, extra_roles=None,
         extra_users=None, dedup_key="", creado_por=None):
    """Crea una alerta según la configuración de su tipo. Devuelve la alerta (o la existente si dedup)."""
    s = db()
    t = s.get(AlertType, type_code)
    if t is None:
        raise BusinessError(f"Tipo de alerta no configurado: {type_code}")
    if not t.activo:
        return None
    if dedup_key:
        existing = s.execute(select(Alert).where(Alert.dedup_key == dedup_key, Alert.estado != "CERRADA")).scalars().first()
        if existing:
            return existing
    roles = list(dict.fromkeys((t.roles or []) + (extra_roles or [])))
    usuarios = list(dict.fromkeys((t.usuarios or []) + [u for u in (extra_users or []) if u]))
    a = Alert(type_code=type_code, titulo=titulo[:250], mensaje=mensaje, prioridad=prioridad or t.prioridad,
              area=t.area, entidad=entidad, entidad_id=str(entidad_id), roles=roles, usuarios=usuarios,
              dedup_key=dedup_key, creado_por=creado_por.id if creado_por else None)
    s.add(a)
    s.flush()
    s.add(AlertEvent(alert_id=a.id, user_id=creado_por.id if creado_por else None, accion="CREADA",
                     comentario=f"Destinatarios: roles {', '.join(roles) or '-'}; usuarios {usuarios or '-'}"))
    if t.enviar_correo:
        _queue_emails(a, t, roles, usuarios)
    return a


def _queue_emails(alert, t, roles, usuarios):
    s = db()
    destinatarios = {u.id: u for u in users_with_roles(roles)}
    for uid in usuarios:
        u = s.get(User, uid)
        if u and u.activo:
            destinatarios[u.id] = u
    # Gerencia General recibe directamente solo los tipos configurados (IF §14)
    for u in list(destinatarios.values()):
        if u.role_code == "GERENCIA_GENERAL":
            pref = s.execute(select(GGAlertPreference).where(GGAlertPreference.user_id == u.id,
                                                             GGAlertPreference.type_code == t.code)).scalars().first()
            if not (pref and pref.recibir_directo):
                destinatarios.pop(u.id)
    for u in destinatarios.values():
        if not u.email:
            continue
        s.add(EmailOutbox(alert_id=alert.id, destinatario=u.email,
                          asunto=f"[{alert.prioridad}] {alert.titulo}",
                          cuerpo=f"{alert.mensaje}\n\nTipo: {t.nombre}\nÁrea: {alert.area}\nAlerta #{alert.id}"))


# ------------------------------ visibilidad --------------------------------
def visible_alerts(user, estado=None, area=None, prioridad=None, grupo=None, type_code=None, solo_abiertas=False):
    """Alertas visibles para el usuario con filtros (área, estado, urgencia, grupo/tipo). IF §14, §22."""
    q = select(Alert).order_by(Alert.creado_ts.desc(), Alert.id.desc())
    if estado:
        q = q.where(Alert.estado == estado)
    if solo_abiertas:
        q = q.where(Alert.estado != "CERRADA")
    if area:
        q = q.where(Alert.area == area)
    if prioridad:
        q = q.where(Alert.prioridad == prioridad)
    if type_code:
        q = q.where(Alert.type_code == type_code)
    rows = [a for a in db().execute(q).scalars() if can_see(user, a)]
    if grupo:
        rows = [a for a in rows if a.type and a.type.grupo == grupo]
    return rows


def can_see(user, alert):
    if user is None:
        return False
    if has_perm(user, "alertas.ver_todas") or user.role_code in ("GERENCIA_GENERAL", "SISTEMAS"):
        return True
    if user.role_code in (alert.roles or []) or user.id in (alert.usuarios or []) or alert.asignado_a == user.id:
        return True
    if user.role_code == "GERENCIA_OPERACIONES" and alert.area in (param("ambito_gerencia_operaciones", []) or []):
        return True
    return False


def _check(user, alert):
    if not can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if not has_perm(user, "alertas.gestionar"):
        raise BusinessError("Su rol no puede gestionar alertas.")


# ------------------------------- ciclo de vida -----------------------------
def assign(alert, user, assignee_id, comentario=""):
    _check(user, alert)
    if alert.estado == "CERRADA":
        raise BusinessError("La alerta ya está cerrada.")
    assignee = db().get(User, int(assignee_id))
    if assignee is None:
        raise BusinessError("Usuario no encontrado.")
    alert.asignado_a = assignee.id
    alert.estado = "ASIGNADA"
    if assignee.id not in (alert.usuarios or []):
        alert.usuarios = (alert.usuarios or []) + [assignee.id]
    db().add(AlertEvent(alert_id=alert.id, user_id=user.id, accion="ASIGNADA",
                        comentario=f"Asignada a {assignee.nombre}. {comentario}".strip()))
    audit(user, "ALERTA_ASIGNADA", "Alert", alert.id, {"asignado_a": assignee.id})


def attend(alert, user, comentario=""):
    _check(user, alert)
    if alert.estado == "CERRADA":
        raise BusinessError("La alerta ya está cerrada.")
    alert.estado = "EN_ATENCION"
    if not alert.asignado_a:
        alert.asignado_a = user.id
    db().add(AlertEvent(alert_id=alert.id, user_id=user.id, accion="EN_ATENCION", comentario=comentario))
    audit(user, "ALERTA_EN_ATENCION", "Alert", alert.id)


def comment(alert, user, texto):
    if not can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if not texto.strip():
        raise BusinessError("El comentario está vacío.")
    db().add(AlertEvent(alert_id=alert.id, user_id=user.id, accion="COMENTARIO", comentario=texto.strip()))


def close(alert, user, motivo, accion):
    _check(user, alert)
    if alert.estado == "CERRADA":
        raise BusinessError("La alerta ya está cerrada.")
    if not motivo.strip() or not accion.strip():
        raise BusinessError("Para cerrar una alerta se requiere motivo y acción tomada.")
    alert.estado = "CERRADA"
    alert.cerrado_ts = now()
    alert.cerrado_por = user.id
    alert.motivo_cierre = motivo.strip()
    alert.accion_tomada = accion.strip()
    db().add(AlertEvent(alert_id=alert.id, user_id=user.id, accion="CERRADA",
                        comentario=f"Motivo: {motivo.strip()} | Acción: {accion.strip()}"))
    audit(user, "ALERTA_CERRADA", "Alert", alert.id, {"motivo": motivo, "accion": accion})


def close_by_system(dedup_key, motivo):
    """Cierra automáticamente alertas abiertas cuya condición desapareció (p.ej. faltante cubierto)."""
    for a in db().execute(select(Alert).where(Alert.dedup_key == dedup_key, Alert.estado != "CERRADA")).scalars():
        a.estado = "CERRADA"
        a.cerrado_ts = now()
        a.motivo_cierre = motivo
        a.accion_tomada = "Cierre automático por el sistema: la condición ya no se cumple."
        db().add(AlertEvent(alert_id=a.id, accion="CERRADA", comentario=f"Sistema: {motivo}"))
