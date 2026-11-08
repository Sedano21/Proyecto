"""V25 (08-nov-2026): chat interno uno a uno. Cada persona elige a quién escribir; puede adjuntar la pantalla de la que
escribe («sobre esto») para que quien recibe vaya directo. El destinatario ve el contador de no leídos en la barra superior
y recibe una notificación en el celular si las activó. No hay grupos ni archivos adjuntos (para eso están las alertas)."""
from sqlalchemy import and_, func, or_, select

from ..db import db
from ..models import ChatMessage, User, now
from .core import BusinessError, has_perm

MAX = 2000


def _req(user):
    if not has_perm(user, "chat.usar"):
        raise BusinessError("Su perfil no usa el chat.")


def contactos(user):
    return [u for u in db().execute(select(User).where(User.activo.is_(True), User.id != user.id).order_by(User.nombre)).scalars()
            if not u.username.startswith("sim.")]


def enviar(user, para_id, texto, ref_url="", ref_titulo=""):
    _req(user)
    texto = (texto or "").strip()
    if not texto:
        raise BusinessError("Escriba el mensaje.")
    if len(texto) > MAX:
        raise BusinessError(f"El mensaje es muy largo (máximo {MAX} caracteres).")
    para = db().get(User, int(para_id or 0))
    if para is None or not para.activo or para.id == user.id:
        raise BusinessError("Elija a quién escribir.")
    ref_url = (ref_url or "").strip()
    if ref_url and not (ref_url.startswith("/") and not ref_url.startswith("//")):
        ref_url = ""  # solo enlaces internos del sistema
    m = ChatMessage(de_id=user.id, para_id=para.id, texto=texto, ref_url=ref_url[:300], ref_titulo=(ref_titulo or "").strip()[:160])
    db().add(m)
    db().flush()
    _notificar(m, user, para)
    return m


def _notificar(m, user, para):
    from . import push
    from .simulacion import bloqueo_externo
    if bloqueo_externo():
        return
    try:
        push.enviar_a_usuario(para, f"Mensaje de {user.nombre}"[:120], m.texto[:180], f"/chat?con={user.id}")
    except Exception:  # noqa: BLE001  (sin clave de notificaciones: el mensaje igual queda en el chat)
        pass


def conversacion(user, otro_id, marcar=True, limite=200):
    otro = db().get(User, int(otro_id))
    if otro is None:
        raise BusinessError("Contacto no encontrado.")
    q = select(ChatMessage).where(or_(and_(ChatMessage.de_id == user.id, ChatMessage.para_id == otro.id),
                                      and_(ChatMessage.de_id == otro.id, ChatMessage.para_id == user.id))
                                  ).order_by(ChatMessage.id.desc()).limit(limite)
    msgs = list(reversed(list(db().execute(q).scalars())))
    if marcar:
        t = now()
        for x in msgs:
            if x.para_id == user.id and x.leido_ts is None:
                x.leido_ts = t
    return otro, msgs


def conversaciones(user):
    """Personas con las que conversó, la más reciente primero, con el último mensaje y los no leídos."""
    s = db()
    ultimos = {}
    for x in s.execute(select(ChatMessage).where(or_(ChatMessage.de_id == user.id, ChatMessage.para_id == user.id))
                       .order_by(ChatMessage.id.desc()).limit(1000)).scalars():
        otro = x.para_id if x.de_id == user.id else x.de_id
        ultimos.setdefault(otro, x)
    no_leidos = dict(s.execute(select(ChatMessage.de_id, func.count()).where(ChatMessage.para_id == user.id,
                                                                            ChatMessage.leido_ts.is_(None))
                               .group_by(ChatMessage.de_id)).all())
    out = []
    for otro_id, x in ultimos.items():
        u = s.get(User, otro_id)
        if u is not None:
            out.append({"user": u, "ultimo": x, "no_leidos": no_leidos.get(otro_id, 0)})
    return out


def no_leidos(user):
    return db().execute(select(func.count()).select_from(ChatMessage).where(ChatMessage.para_id == user.id,
                                                                          ChatMessage.leido_ts.is_(None))).scalar() or 0
