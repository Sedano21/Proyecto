"""V22 (06-nov-2026): disponibilidad del personal.

Vacaciones y descanso médico con rango de fechas; falta justificada (con motivo, p. ej. duelo familiar) o injustificada.
Vale para choferes (DRIVER), personal con cuenta (USER: auxiliares de despacho, almacén, etc.) y personal sin cuenta
(WORKER: producción, mantenimiento, limpieza). Una ausencia:
- impide asignar a la persona en una ruta o un trabajo en esas fechas;
- avisa a Distribución si la persona ya tenía rutas asignadas (para reasignar los clientes que lleva);
- se refleja en la asistencia del día (el estado se completa solo) y en el análisis.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import or_, select

from ..catalogs import AUSENCIA_TIPOS
from ..db import db
from ..models import Absence, Driver, Route, User, Worker
from . import alerts
from .core import BusinessError, audit, has_perm

PERSONAS = {"DRIVER": "Chofer", "USER": "Usuario", "WORKER": "Colaborador"}


def _persona(tipo, pid):
    m = {"DRIVER": Driver, "USER": User, "WORKER": Worker}.get(tipo)
    if m is None:
        raise BusinessError("Persona no válida.")
    p = db().get(m, int(pid))
    if p is None:
        raise BusinessError("Persona no encontrada.")
    return p


def _area(tipo, p):
    if tipo == "DRIVER":
        return "Distribución"
    if tipo == "USER":
        return p.role.area if p.role else ""
    return p.area or ""


def personas(user=None):
    """Lista para elegir: choferes, usuarios operativos y colaboradores, con su clave «TIPO:id»."""
    out = []
    for d in db().execute(select(Driver).order_by(Driver.nombre)).scalars():
        out.append((f"DRIVER:{d.id}", f"{d.nombre} · chofer{' externo' if d.externo else ''}", "Distribución"))
    for u in db().execute(select(User).where(User.activo.is_(True)).order_by(User.nombre)).scalars():
        if u.role_code in ("CONDUCTOR",):
            continue  # el chofer se registra como chofer
        out.append((f"USER:{u.id}", f"{u.nombre} · {u.role.nombre if u.role else u.role_code}", u.role.area if u.role else ""))
    for w in db().execute(select(Worker).where(Worker.activo.is_(True)).order_by(Worker.area, Worker.nombre)).scalars():
        out.append((f"WORKER:{w.id}", f"{w.nombre} · {w.area}{' · ' + w.puesto if w.puesto else ''}", w.area))
    return out


def register(user, clave, tipo, desde, hasta=None, motivo="", archivo=""):
    if not has_perm(user, "personal.ausencias"):
        raise BusinessError("Su perfil no registra la disponibilidad del personal.")
    try:
        ptipo, pid = (clave or "").split(":")
    except ValueError:
        raise BusinessError("Elija a la persona.") from None
    p = _persona(ptipo, pid)
    tipo = (tipo or "").upper()
    if tipo not in AUSENCIA_TIPOS:
        raise BusinessError("Tipo de ausencia no válido.")
    if desde is None:
        raise BusinessError("Indique desde cuándo.")
    hasta = hasta or desde
    if hasta < desde:
        raise BusinessError("La fecha «hasta» es anterior a «desde».")
    motivo = (motivo or "").strip()
    if tipo == "FALTA_JUSTIFICADA" and not motivo:
        raise BusinessError("Indique el motivo de la falta justificada (p. ej. duelo familiar).")
    solapa = db().execute(select(Absence).where(Absence.persona_tipo == ptipo, Absence.persona_id == p.id,
                                                Absence.anulada.is_(False), Absence.desde <= hasta,
                                                Absence.hasta >= desde)).scalars().first()
    if solapa is not None:
        raise BusinessError(f"Ya hay una ausencia registrada que se cruza: {texto(solapa)}.")
    a = Absence(persona_tipo=ptipo, persona_id=p.id, nombre=p.nombre, area=_area(ptipo, p), tipo=tipo, desde=desde,
                hasta=hasta, motivo=motivo, archivo=archivo or "", user_id=user.id)
    db().add(a)
    db().flush()
    _avisar_asignaciones(a, user)
    _marcar_asistencia(a, user)
    audit(user, "AUSENCIA", "Absence", a.id, {"persona": p.nombre, "tipo": tipo, "desde": str(desde), "hasta": str(hasta),
                                              "motivo": motivo})
    return a


def cancel(user, a, motivo=""):
    if not has_perm(user, "personal.ausencias"):
        raise BusinessError("Su perfil no registra la disponibilidad del personal.")
    a.anulada = True
    audit(user, "AUSENCIA_ANULADA", "Absence", a.id, {"motivo": motivo})


def texto(a):
    t = AUSENCIA_TIPOS.get(a.tipo, a.tipo)
    rango = f"{a.desde:%d/%m}" + (f" al {a.hasta:%d/%m}" if a.hasta != a.desde else "")
    return f"{t} ({rango}){' – ' + a.motivo if a.motivo else ''}"


def ausencia_de(ptipo, pid, fecha):
    if pid is None:
        return None
    return db().execute(select(Absence).where(Absence.persona_tipo == ptipo, Absence.persona_id == int(pid),
                                              Absence.anulada.is_(False), Absence.desde <= fecha,
                                              Absence.hasta >= fecha)).scalars().first()


def activas(fecha=None, desde=None, hasta=None, area=None):
    fecha = fecha or date.today()
    desde, hasta = desde or fecha, hasta or fecha
    q = select(Absence).where(Absence.anulada.is_(False), Absence.desde <= hasta, Absence.hasta >= desde)
    if area:
        q = q.where(Absence.area == area)
    return list(db().execute(q.order_by(Absence.desde, Absence.nombre)).scalars())


def _avisar_asignaciones(a, user):
    """Rutas ya asignadas a la persona en esas fechas: aviso a Distribución con los clientes que lleva."""
    q = select(Route).where(Route.fecha >= a.desde, Route.fecha <= a.hasta, Route.estado.in_(("PROPUESTA", "CONFIRMADA")))
    if a.persona_tipo == "DRIVER":
        q = q.where(Route.driver_id == a.persona_id)
    elif a.persona_tipo == "USER":
        drv = db().execute(select(Driver).where(Driver.user_id == a.persona_id)).scalars().first()
        rutas = [r for r in db().execute(select(Route).where(Route.fecha >= a.desde, Route.fecha <= a.hasta,
                                                              Route.estado.in_(("PROPUESTA", "CONFIRMADA")))).scalars()
                 if a.persona_id in (r.auxiliares or []) or r.auxiliar_id == a.persona_id
                 or (drv is not None and r.driver_id == drv.id)]
        return _emit(a, rutas, user)
    else:
        return []
    return _emit(a, list(db().execute(q).scalars()), user)


def _emit(a, rutas, user):
    for r in rutas:
        clientes = sorted({st.order.customer.nombre for st in r.stops})
        alerts.emit("PERSONAL_NO_DISPONIBLE", f"Ruta #{r.id} del {r.fecha:%d/%m}: {a.nombre} no estará disponible",
                    f"{texto(a)}. Clientes de la ruta: {', '.join(clientes) or '-'}. Reasigne el chofer o el auxiliar.",
                    "Route", r.id, dedup_key=f"AUSENCIA:{a.id}:{r.id}", creado_por=user)
    return rutas


def _marcar_asistencia(a, user):
    """Colaboradores: la asistencia de los días de la ausencia se completa con su estado (si no estaba marcada)."""
    if a.persona_tipo != "WORKER":
        return
    from ..catalogs import AUSENCIA_A_ASISTENCIA
    from ..models import Attendance
    est = AUSENCIA_A_ASISTENCIA.get(a.tipo)
    d = a.desde
    while d <= a.hasta and d <= date.today() + timedelta(days=60):
        ya = db().execute(select(Attendance).where(Attendance.worker_id == a.persona_id, Attendance.fecha == d)).scalars().first()
        if ya is None:
            db().add(Attendance(worker_id=a.persona_id, fecha=d, estado=est, observacion=a.motivo[:250], user_id=user.id))
        d += timedelta(days=1)


def estado_dia(worker_id, fecha):
    """Estado de asistencia sugerido por una ausencia registrada (o None)."""
    from ..catalogs import AUSENCIA_A_ASISTENCIA
    a = ausencia_de("WORKER", worker_id, fecha)
    return (AUSENCIA_A_ASISTENCIA.get(a.tipo), a) if a else (None, None)


def summary(desde, hasta):
    """Resumen por área y tipo (días hábiles calendario en el periodo) para el análisis."""
    out = defaultdict(lambda: defaultdict(int))
    for a in activas(desde=desde, hasta=hasta):
        ini, fin = max(a.desde, desde), min(a.hasta, hasta)
        out[a.area or "-"][a.tipo] += (fin - ini).days + 1
    return {k: dict(v) for k, v in out.items()}


def unavailable_driver_ids(fecha):
    """Choferes con ausencia ese día (incluye la de su cuenta de usuario)."""
    ids = set()
    for a in db().execute(select(Absence).where(Absence.anulada.is_(False), Absence.desde <= fecha, Absence.hasta >= fecha,
                                                or_(Absence.persona_tipo == "DRIVER", Absence.persona_tipo == "USER"))).scalars():
        if a.persona_tipo == "DRIVER":
            ids.add(a.persona_id)
        else:
            d = db().execute(select(Driver).where(Driver.user_id == a.persona_id)).scalars().first()
            if d is not None:
                ids.add(d.id)
    return ids
