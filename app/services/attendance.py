"""Personal de Producción y asistencia (ronda 23-oct-2026): el Jefe de Producción y el asistente que lo tenga en su alcance
registran asistencia, falta, vacaciones, descanso médico o tardanza (la marcación de entrada y salida está en otro sistema)."""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Attendance, Worker
from .core import BusinessError, audit, has_perm, param, user_scope


def area_of(user):
    """Área cuyo personal ve y registra el usuario: Producción, o la propia (p. ej. el Jefe de Logística, sección 5)."""
    if has_perm(user, "produccion.asistencia"):
        return "Producción"
    from .alerts import user_area
    return user_area(user) if has_perm(user, "asistencia.area") else None


def workers_of(user, activos=False):
    area = area_of(user)
    q = select(Worker).order_by(Worker.linea, Worker.nombre)
    if activos:
        q = q.where(Worker.activo.is_(True))
    return [w for w in db().execute(q).scalars() if (w.area or "Producción") == area] if area else []


def can_register(user):
    if has_perm(user, "asistencia.area") and not has_perm(user, "produccion.asistencia"):
        return True
    if not has_perm(user, "produccion.asistencia"):
        return False
    if user.role_code == "ASIST_PRODUCCION":
        sc = user_scope(user)
        return bool(sc.get("asistencia") or sc.get("permisos_de") == "JEFE_PRODUCCION")
    return True


def _require(user):
    if not can_register(user):
        raise BusinessError("Registra la asistencia el Jefe de Producción o el asistente designado.")


def states():
    return param("asistencia_estados", []) or []


def save_worker(user, datos, w=None):
    _require(user)
    nombre = (datos.get("nombre") or "").strip().upper()
    if not nombre:
        raise BusinessError("Indique el nombre del colaborador.")
    doc = (datos.get("documento") or "").strip()
    if doc and (not doc.isalnum() or len(doc) > 15):
        raise BusinessError("Documento inválido.")
    if w is None:
        w = Worker(nombre=nombre)
        db().add(w)
    w.nombre, w.documento = nombre, doc
    w.area = area_of(user) or "Producción"
    w.linea = (datos.get("linea") or "").strip()
    w.sublinea = (datos.get("sublinea") or "").strip()
    w.externo = str(datos.get("externo", "")) in ("1", "on", "true")
    w.activo = str(datos.get("activo", "1")) in ("1", "on", "true")
    db().flush()
    audit(user, "COLABORADOR_GUARDADO", "Worker", w.id, {"nombre": nombre, "linea": w.linea})
    return w


def register_day(user, fecha, marcas, observaciones=None):
    """marcas: {worker_id: estado}. Reemplaza el estado del día de cada colaborador."""
    _require(user)
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    if fecha > date.today():
        raise BusinessError("No se registra asistencia de días futuros.")
    validos = set(states())
    n = 0
    for wid, estado in marcas.items():
        if not estado:
            continue
        if estado not in validos:
            raise BusinessError(f"Estado de asistencia no válido: {estado}.")
        w = db().get(Worker, int(wid))
        if w is None or (w.area or "Producción") != area_of(user):
            continue
        a = db().execute(select(Attendance).where(Attendance.worker_id == w.id, Attendance.fecha == fecha)).scalars().first()
        if a is None:
            a = Attendance(worker_id=w.id, fecha=fecha, estado=estado)
            db().add(a)
        a.estado = estado
        a.observacion = ((observaciones or {}).get(str(wid)) or "").strip()[:250]
        a.user_id = user.id
        n += 1
    audit(user, "ASISTENCIA_REGISTRADA", "Attendance", fecha.isoformat(), {"registros": n})
    return n


def day(fecha):
    return {a.worker_id: a for a in db().execute(select(Attendance).where(Attendance.fecha == fecha)).scalars()}


def summary(desde=None, hasta=None, linea="", area="Producción"):
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=29)
    rows = [a for a in db().execute(select(Attendance).where(Attendance.fecha >= desde, Attendance.fecha <= hasta)).scalars()
            if (a.worker.area or "Producción") == area]
    por = defaultdict(Counter)
    for a in rows:
        if linea and a.worker.linea != linea:
            continue
        por[a.worker][a.estado] += 1
    total = Counter(a.estado for a in rows if not linea or a.worker.linea == linea)
    return {"desde": desde, "hasta": hasta, "por_persona": sorted(por.items(), key=lambda x: x[0].nombre), "total": total,
            "estados": states()}
