"""Trazabilidad general de cambios (ronda 23-oct-2026): todo alta, cambio o baja de datos que realiza un usuario desde el
sistema queda en la auditoría con el valor anterior y el nuevo de cada campo (acciones DATOS_ALTA, DATOS_CAMBIO y DATOS_BAJA; las contraseñas no se registran), además de los
registros de negocio que ya se auditaban (aprobaciones, cargas, etc.). Se registra al confirmar cada operación del
usuario (solicitud web autenticada); las tareas automáticas quedan con usuario vacío ("Sistema")."""
from datetime import date, datetime

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

# tablas que ya son registro de auditoría o de alto volumen técnico (su efecto se audita por la acción de negocio)
EXCLUIDAS = {"AuditLog", "AlertEvent", "EmailOutbox", "UploadRow", "ParamHistory", "SalesHistory"}
# columnas sensibles: solo se registra que cambiaron, nunca su valor
OCULTAS = {"password_hash"}
MAX_TXT = 300
_KEY = "_audit_pendiente"


def _val(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    s = str(v) if not isinstance(v, (dict, list)) else v
    if isinstance(s, str) and len(s) > MAX_TXT:
        return s[:MAX_TXT] + "…"
    return s


def _user_id():
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return None, False
        u = g.get("user")
        return (u.id if u is not None else None), u is not None
    except Exception:  # noqa: BLE001
        return None, False


def _pk(obj):
    try:
        ident = inspect(obj).mapper.primary_key_from_instance(obj)
        return "/".join(str(x) for x in ident if x is not None)
    except Exception:  # noqa: BLE001
        return ""


def _changes(obj):
    out = {}
    st = inspect(obj)
    for attr in st.mapper.column_attrs:
        h = st.attrs[attr.key].history
        if h.has_changes():
            antes = h.deleted[0] if h.deleted else None
            despues = h.added[0] if h.added else None
            if antes != despues:
                out[attr.key] = ["***", "*** (modificada)"] if attr.key in OCULTAS else [_val(antes), _val(despues)]
    return out


def _snapshot(obj):
    st = inspect(obj)
    return {a.key: _val(getattr(obj, a.key)) for a in st.mapper.column_attrs
            if a.key not in OCULTAS and getattr(obj, a.key) not in (None, "", [], {})}


def _after_flush(session, _ctx):
    uid, autenticado = _user_id()
    if not autenticado or session.info.get("carga_masiva"):
        return
    pend = session.info.setdefault(_KEY, [])
    for obj, tipo in [(o, "ALTA") for o in session.new] + [(o, "CAMBIO") for o in session.dirty] + \
                     [(o, "BAJA") for o in session.deleted]:
        nombre = type(obj).__name__
        if nombre in EXCLUIDAS:
            continue
        if tipo == "CAMBIO":
            if not session.is_modified(obj, include_collections=False):
                continue
            det = _changes(obj)
            if not det:
                continue
            detalle = {"cambios": det}
        elif tipo == "ALTA":
            detalle = {"valores": _snapshot(obj)}
        else:
            detalle = {"valores": _snapshot(obj)}
        pend.append({"user_id": uid, "accion": f"DATOS_{tipo}", "entidad": nombre, "entidad_id": _pk(obj)[:60],
                     "detalle": detalle})


def _after_flush_postexec(session, _ctx):
    pend = session.info.pop(_KEY, None)
    if not pend:
        return
    from ..models import AuditLog
    for p in pend:
        session.add(AuditLog(**p))


_registrado = False


def install():
    global _registrado
    if _registrado:
        return
    event.listen(Session, "after_flush", _after_flush)
    event.listen(Session, "after_flush_postexec", _after_flush_postexec)
    _registrado = True
