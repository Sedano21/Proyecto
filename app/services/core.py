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


def contingency():
    """Registro en contingencia (marcha blanca): {activa, desde, motivo, por} o {} si no está activo."""
    c = param("modo_contingencia", {}) or {}
    return c if c.get("activa") else {}


def audit(user, accion, entidad, entidad_id="", detalle=None):
    detalle = dict(detalle or {})
    if contingency():
        detalle["registrado_en_contingencia"] = True  # todo lo registrado mientras está activo queda marcado
    db().add(AuditLog(user_id=user.id if user else None, accion=accion, entidad=entidad,
                      entidad_id=str(entidad_id), detalle=_jsonable(detalle)))


# ------------------------------- permisos ---------------------------------
def user_scope(user):
    """Alcance por usuario (ronda 23-oct-2026): líneas de producción que ve, perfil adicional y si registra asistencia."""
    if user is None:
        return {}
    return (param("produccion_alcance_usuarios", {}) or {}).get(user.username) or {}


def roles_of(user):
    """Rol del usuario más el perfil adicional configurado («permisos_de»: ve y aprueba como ese rol)."""
    if user is None:
        return set()
    extra = user_scope(user).get("permisos_de")
    return {user.role_code} | ({extra} if extra else set())


def can_self_approve(user):
    """Roles que pueden aprobar sus propias solicitudes (ronda 23-oct-2026, decisión 4)."""
    return user is not None and bool(roles_of(user) & set(param("roles_autoaprobacion", []) or []))


def user_perms(user):
    if user is None:
        return set()
    rows = db().execute(select(RolePermission.perm_code).where(RolePermission.role_code.in_(sorted(roles_of(user))))).scalars()
    return set(rows)


def has_perm(user, perm):
    if user is None:
        return False
    return perm in user_perms(user)


def require(user, perm):
    if not has_perm(user, perm):
        raise BusinessError(f"El rol {user.role_code if user else '-'} no tiene el permiso '{perm}'.")


def warehouse_scopes():
    """{rol: [almacenes]} de los roles que manejan almacenes específicos (Q17: coordinadores 1560 y 1524)."""
    return {k: list(v or []) for k, v in (param("alcance_almacen_por_rol", {}) or {}).items()}


def wh_in(warehouse_code, codes):
    """El almacén está en la lista; 'PRO-*' abarca todos los códigos que empiezan con 'PRO-'."""
    return any(warehouse_code == c or (c.endswith("*") and warehouse_code.startswith(c[:-1])) for c in codes or [])


def check_warehouse_scope(user, warehouse_code):
    """Un rol con almacenes asignados solo actúa sobre ellos (Q5, Q17). Los almacenes que no están asignados a ningún
    rol (alternativos) los opera cualquiera con el permiso."""
    if user is None or not warehouse_code:
        return
    scopes = warehouse_scopes()
    mios = scopes.get(user.role_code)
    if mios is None or wh_in(warehouse_code, mios):
        return
    if any(wh_in(warehouse_code, v) for v in scopes.values()):
        raise BusinessError(f"El almacén {warehouse_code} no está asignado a su rol (maneja: {', '.join(mios)}) (Q5/Q17).")


def users_with_roles(roles):
    if not roles:
        return []
    out = list(db().execute(select(User).where(User.role_code.in_(roles), User.activo.is_(True))).scalars())
    extra = [u for u, sc in (param("produccion_alcance_usuarios", {}) or {}).items() if sc.get("permisos_de") in roles]
    if extra:  # perfil adicional (ronda 23-oct-2026)
        ids = {u.id for u in out}
        out += [u for u in db().execute(select(User).where(User.username.in_(extra), User.activo.is_(True))).scalars()
                if u.id not in ids]
    return out


def fmt_qty(x):
    if x is None:
        return ""
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.2f}".replace(",", " ")
