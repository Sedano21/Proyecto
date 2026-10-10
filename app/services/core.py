"""Servicios transversales: parámetros, auditoría, permisos."""
from datetime import date, datetime

from sqlalchemy import select

from ..db import db
from ..models import AuditLog, Param, ParamHistory, RolePermission, User


class BusinessError(Exception):
    """Error de regla de negocio mostrado al usuario."""


# ------------------------------- parámetros -------------------------------
def param(key, default=None):
    p = db().get(Param, key)
    if p is None:
        return default
    v = (p.valor or {}).get("v")
    return default if v is None else v


def set_param(key, value, user=None, estado=None):
    p = db().get(Param, key)
    if p is None:
        raise BusinessError(f"Parámetro desconocido: {key}")
    p.version += 1
    p.valor = {"v": value}
    if estado:
        p.estado = estado
    db().add(ParamHistory(key=key, version=p.version, valor={"v": value}, estado=p.estado,
                          user_id=user.id if user else None))
    audit(user, "PARAM_EDITADO", "Param", key, {"valor": value, "version": p.version, "estado": p.estado})
    return p


def coerce_param(tipo, raw):
    """Convierte el texto de un formulario al tipo del parámetro. Vacío -> None."""
    import json
    raw = (raw or "").strip()
    if raw == "":
        return None
    if tipo == "int":
        return int(raw)
    if tipo == "float":
        return float(raw.replace(",", "."))
    if tipo == "bool":
        return raw.lower() in ("1", "true", "si", "sí", "on", "yes")
    if tipo in ("list", "dict"):
        val = json.loads(raw)
        if tipo == "list" and not isinstance(val, list):
            raise ValueError("Se esperaba una lista JSON")
        if tipo == "dict" and not isinstance(val, dict):
            raise ValueError("Se esperaba un objeto JSON")
        return val
    return raw


# ------------------------------- auditoría --------------------------------
def _jsonable(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def audit(user, accion, entidad, entidad_id="", detalle=None):
    db().add(AuditLog(user_id=user.id if user else None, accion=accion, entidad=entidad,
                      entidad_id=str(entidad_id), detalle=_jsonable(detalle or {})))


# ------------------------------- permisos ---------------------------------
def user_perms(user):
    if user is None:
        return set()
    rows = db().execute(select(RolePermission.perm_code).where(RolePermission.role_code == user.role_code)).scalars()
    return set(rows)


def has_perm(user, perm):
    if user is None:
        return False
    return perm in user_perms(user)


def require(user, perm):
    if not has_perm(user, perm):
        raise BusinessError(f"El rol {user.role_code if user else '-'} no tiene el permiso '{perm}'.")


def users_with_roles(roles):
    if not roles:
        return []
    return list(db().execute(select(User).where(User.role_code.in_(roles), User.activo.is_(True))).scalars())


def fmt_qty(x):
    if x is None:
        return ""
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.2f}".replace(",", " ")
