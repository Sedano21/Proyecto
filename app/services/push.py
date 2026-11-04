"""V20: notificaciones push (Web Push) al celular o la computadora de cada usuario.

- Cada dispositivo se suscribe una vez («Activar notificaciones en este dispositivo»). La suscripción queda en la tabla
  push_subscriptions.
- Al crearse una alerta (prioridades del parámetro «push_prioridades», ALTA y MEDIA por defecto), sus destinatarios
  reciben una notificación del sistema operativo: aparece aunque la pantalla esté apagada o el navegador cerrado.
- Se envía DESPUÉS de guardar (si la acción se deshace, no se avisa) y en segundo plano (no demora la pantalla).
- Claves VAPID: se generan solas la primera vez en instance/vapid_privada.pem (fuera del repositorio). El contacto VAPID
  sale de la variable VAPID_SUB (mailto: o https://); si falta, se usa la dirección del sistema.
"""
import json
import logging
import os
import threading

from sqlalchemy import event, select

from ..db import db
from ..models import PushSubscription, now

log = logging.getLogger("operaciones")
_APP = None
_lock = threading.Lock()


def init(app):
    """Se llama al crear la aplicación: guarda la referencia para enviar desde hilos y prepara las claves."""
    global _APP
    _APP = app
    from ..db import SessionLocal
    if not getattr(init, "_enganchado", False):
        event.listen(SessionLocal, "after_commit", _al_confirmar)
        event.listen(SessionLocal, "after_rollback", _al_deshacer)
        init._enganchado = True


def _ruta_clave():
    return os.path.join(_APP.instance_path, "vapid_privada.pem")


def _vapid():
    """Objeto Vapid con la clave privada (la crea la primera vez)."""
    from py_vapid import Vapid01
    ruta = _ruta_clave()
    with _lock:
        if not os.path.exists(ruta):
            v = Vapid01()
            v.generate_keys()
            v.save_key(ruta)
            os.chmod(ruta, 0o600)
    return Vapid01.from_file(ruta)


def public_key():
    """Clave pública en base64url (formato applicationServerKey del navegador)."""
    import base64
    from cryptography.hazmat.primitives import serialization
    v = _vapid()
    crudo = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(crudo).decode().rstrip("=")


def disponible():
    try:
        import pywebpush  # noqa: F401
        import py_vapid  # noqa: F401
        return _APP is not None
    except ImportError:
        return False


# ------------------------------------------------------------------ suscripciones
def subscribe(user, datos, dispositivo=""):
    endpoint = (datos or {}).get("endpoint") or ""
    claves = (datos or {}).get("keys") or {}
    if not endpoint.startswith("https://") or not claves.get("p256dh") or not claves.get("auth"):
        from .core import BusinessError
        raise BusinessError("Suscripción de notificaciones no válida.")
    s = db()
    sub = s.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).scalars().first()
    if sub is None:
        sub = PushSubscription(endpoint=endpoint, user_id=user.id, p256dh="", auth="")
        s.add(sub)
    sub.user_id = user.id  # el mismo navegador puede pasar a otro usuario al cambiar de sesión
    sub.p256dh, sub.auth = claves["p256dh"][:200], claves["auth"][:100]
    sub.dispositivo = (dispositivo or "")[:200]
    sub.fallos = 0
    s.flush()
    return sub


def unsubscribe(user, endpoint):
    s = db()
    sub = s.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint,
                                                   PushSubscription.user_id == user.id)).scalars().first()
    if sub is not None:
        s.delete(sub)
    return sub is not None


def devices(user):
    return list(db().execute(select(PushSubscription).where(PushSubscription.user_id == user.id)
                             .order_by(PushSubscription.id.desc())).scalars())


# ------------------------------------------------------------------ envío
def encolar(alert, user_ids, url=None):
    """Prepara la notificación de una alerta; se envía cuando la transacción se confirma."""
    if not user_ids or not disponible():
        return 0
    s = db()
    subs = list(s.execute(select(PushSubscription).where(PushSubscription.user_id.in_(list(user_ids)))).scalars())
    if not subs:
        return 0
    cuerpo = (alert.mensaje or "").strip().replace("\n", " ")
    datos = {"title": f"{'🔴 ' if alert.prioridad == 'ALTA' else ''}{alert.titulo}"[:120],
             "body": (cuerpo[:180] + "…") if len(cuerpo) > 180 else cuerpo,
             "url": url or f"/alertas/{alert.id}", "tag": f"alerta-{alert.id}",
             "urgente": alert.prioridad == "ALTA"}
    pend = s.info.setdefault("push_pendientes", [])
    pend.extend((sub.id, sub.endpoint, sub.p256dh, sub.auth, datos) for sub in subs)
    return len(subs)


def enviar_a_usuario(user, titulo, cuerpo, url="/"):
    """Notificación directa (p. ej. la prueba «Enviar una notificación de prueba»)."""
    s = db()
    subs = devices(user)
    datos = {"title": titulo[:120], "body": cuerpo[:200], "url": url, "tag": "prueba", "urgente": False}
    s.info.setdefault("push_pendientes", []).extend((x.id, x.endpoint, x.p256dh, x.auth, datos) for x in subs)
    return len(subs)


def _al_deshacer(session):
    session.info.pop("push_pendientes", None)


def _al_confirmar(session):
    pend = session.info.pop("push_pendientes", None)
    if not pend:
        return
    if _APP is not None and _APP.config.get("TESTING"):
        _APP.config.setdefault("PUSH_ENVIADOS", []).extend(pend)  # en pruebas no se sale a internet
        return
    threading.Thread(target=_enviar, args=(pend,), daemon=True).start()


def _contacto():
    sub = (os.environ.get("VAPID_SUB") or "").strip()
    if sub.startswith(("mailto:", "https://")):
        return sub
    return "mailto:sistemas@corporacionproductiva.local"


def _enviar(pend):
    from pywebpush import WebPushException, webpush
    caducadas, enviadas, fallidas = [], [], []
    try:
        clave = _ruta_clave()
        _vapid()
        for sid, endpoint, p256dh, auth, datos in pend:
            try:
                webpush(subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                        data=json.dumps(datos, ensure_ascii=False), vapid_private_key=clave,
                        vapid_claims={"sub": _contacto()}, ttl=24 * 3600,
                        headers={"Urgency": "high" if datos.get("urgente") else "normal"}, timeout=10)
                enviadas.append(sid)
            except WebPushException as e:
                codigo = getattr(getattr(e, "response", None), "status_code", None)
                (caducadas if codigo in (404, 410) else fallidas).append(sid)
                if codigo not in (404, 410):
                    log.warning("Notificación push no enviada (%s): %s", codigo, str(e)[:200])
            except Exception as e:  # noqa: BLE001
                fallidas.append(sid)
                log.warning("Notificación push no enviada: %s", str(e)[:200])
    finally:
        _registrar(caducadas, enviadas, fallidas)


def _registrar(caducadas, enviadas, fallidas):
    """Quita los dispositivos que ya no existen (el usuario borró datos o desinstaló) y anota los envíos."""
    if not (caducadas or enviadas or fallidas) or _APP is None:
        return
    from ..db import SessionLocal
    with _APP.app_context():
        s = SessionLocal()
        try:
            for sid in caducadas:
                x = s.get(PushSubscription, sid)
                if x is not None:
                    s.delete(x)
            for sid in enviadas:
                x = s.get(PushSubscription, sid)
                if x is not None:
                    x.ultimo_envio_ts, x.fallos = now(), 0
            for sid in fallidas:
                x = s.get(PushSubscription, sid)
                if x is not None:
                    x.fallos = (x.fallos or 0) + 1
                    if x.fallos >= 20:
                        s.delete(x)
            s.commit()
        except Exception:  # noqa: BLE001
            s.rollback()
        finally:
            SessionLocal.remove()
