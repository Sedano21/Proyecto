"""V22 (06-nov-2026): limpieza programada.

El Jefe de Mantenimiento programa a su personal: qué zonas limpia cada persona en su jornada y cuántas veces. La persona
ve sus zonas del día en su celular y marca cada limpieza (opcionalmente con foto). El Jefe modifica asignaciones, ve el
desempeño por persona y por zona, agrega o renombra zonas y mantiene al personal (datos y asistencia).
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import CleaningAssignment, SanitationZone, Worker, now
from . import alerts
from .core import BusinessError, audit, has_perm


def _req(user):
    if not has_perm(user, "limpieza.gestionar"):
        raise BusinessError("La limpieza la programa el Jefe de Mantenimiento.")


def staff(activos=True):
    q = select(Worker).where(Worker.area == "Mantenimiento")
    if activos:
        q = q.where(Worker.activo.is_(True))
    return list(db().execute(q.order_by(Worker.puesto, Worker.nombre)).scalars())


def zones(activas=True):
    q = select(SanitationZone)
    if activas:
        q = q.where(SanitationZone.activo.is_(True))
    return list(db().execute(q.order_by(SanitationZone.grupo, SanitationZone.nombre)).scalars())


def save_zone(user, datos, z=None):
    """Agregar una zona o cambiar su nombre, grupo o área."""
    if not (has_perm(user, "limpieza.gestionar") or has_perm(user, "mantenimiento.gestionar")):
        raise BusinessError("Las zonas las mantiene el Jefe de Mantenimiento.")
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise BusinessError("Indique el nombre de la zona.")
    otra = db().execute(select(SanitationZone).where(SanitationZone.nombre == nombre)).scalars().first()
    if otra is not None and (z is None or otra.id != z.id):
        raise BusinessError("Ya existe una zona con ese nombre.")
    nueva = z is None
    if nueva:
        z = SanitationZone(nombre=nombre)
        db().add(z)
    anterior = z.nombre
    z.nombre = nombre
    z.grupo = (datos.get("grupo") or "").strip()
    z.area = (datos.get("area") or z.area or "").strip()
    if "activo" in datos:
        z.activo = str(datos.get("activo")) in ("1", "true", "on")
    db().flush()
    audit(user, "ZONA_GUARDADA", "SanitationZone", z.id, {"nombre": nombre, "anterior": None if nueva else anterior})
    return z


def save_person(user, datos, w=None):
    """Alta o cambio de datos del personal de mantenimiento y limpieza."""
    if not (has_perm(user, "limpieza.gestionar") or has_perm(user, "mantenimiento.gestionar")):
        raise BusinessError("El personal de mantenimiento lo registra el Jefe de Mantenimiento.")
    nombre = " ".join((datos.get("nombre") or "").split()).upper()
    if not nombre:
        raise BusinessError("Indique el nombre.")
    if w is None:
        w = Worker(nombre=nombre, area="Mantenimiento")
        db().add(w)
    w.nombre = nombre
    w.area = "Mantenimiento"
    w.documento = (datos.get("documento") or "").strip()
    w.puesto = (datos.get("puesto") or "").strip()
    w.telefono = (datos.get("telefono") or "").strip()
    if datos.get("user_id") not in (None, ""):
        w.user_id = int(datos["user_id"]) or None
    if "activo" in datos:
        w.activo = str(datos.get("activo")) in ("1", "true", "on")
    db().flush()
    audit(user, "PERSONAL_MANT", "Worker", w.id, {"nombre": nombre, "puesto": w.puesto})
    return w


def assign(user, fecha, worker_id, zone_ids, veces=1, turno="", nota=""):
    _req(user)
    w = db().get(Worker, int(worker_id))
    if w is None or not w.activo:
        raise BusinessError("Elija a la persona.")
    from .ausencias import ausencia_de, texto
    a = ausencia_de("WORKER", w.id, fecha)
    if a is not None:
        raise BusinessError(f"{w.nombre} no está disponible el {fecha:%d/%m/%Y}: {texto(a)}.")
    try:
        veces = max(1, int(veces or 1))
    except ValueError:
        raise BusinessError("Número de veces inválido.") from None
    hechas = []
    for zid in zone_ids:
        z = db().get(SanitationZone, int(zid))
        if z is None:
            continue
        ya = db().execute(select(CleaningAssignment).where(CleaningAssignment.fecha == fecha,
                                                           CleaningAssignment.worker_id == w.id,
                                                           CleaningAssignment.zone_id == z.id)).scalars().first()
        if ya is None:
            ya = CleaningAssignment(fecha=fecha, worker_id=w.id, zone_id=z.id, user_id=user.id)
            db().add(ya)
        ya.veces, ya.turno, ya.nota = veces, (turno or "").strip(), (nota or "").strip()
        hechas.append(ya)
    if not hechas:
        raise BusinessError("Elija al menos una zona.")
    db().flush()
    audit(user, "LIMPIEZA_ASIGNADA", "Worker", w.id, {"fecha": str(fecha), "zonas": [h.zone_id for h in hechas],
                                                      "veces": veces})
    return hechas


def copy_day(user, desde_fecha, a_fecha):
    """Repite las asignaciones de un día en otro (programación semanal rápida)."""
    _req(user)
    n = 0
    for c in day(desde_fecha):
        if not db().execute(select(CleaningAssignment).where(CleaningAssignment.fecha == a_fecha,
                                                             CleaningAssignment.worker_id == c.worker_id,
                                                             CleaningAssignment.zone_id == c.zone_id)).first():
            db().add(CleaningAssignment(fecha=a_fecha, worker_id=c.worker_id, zone_id=c.zone_id, veces=c.veces,
                                        turno=c.turno, nota=c.nota, user_id=user.id))
            n += 1
    return n


def remove(user, c):
    _req(user)
    if c.checks:
        raise BusinessError("Ya tiene limpiezas marcadas: no se quita.")
    db().delete(c)


def day(fecha, worker_id=None):
    q = select(CleaningAssignment).where(CleaningAssignment.fecha == fecha)
    if worker_id:
        q = q.where(CleaningAssignment.worker_id == worker_id)
    return list(db().execute(q.order_by(CleaningAssignment.worker_id, CleaningAssignment.zone_id)).scalars())


def mine(user, fecha=None):
    w = db().execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
    return (w, day(fecha or date.today(), w.id)) if w is not None else (None, [])


def mark(user, c, foto=""):
    w = db().execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
    if not ((w is not None and c.worker_id == w.id and has_perm(user, "limpieza.marcar")) or has_perm(user, "limpieza.gestionar")):
        raise BusinessError("Marca la limpieza la persona asignada.")
    if c.fecha != date.today() and not has_perm(user, "limpieza.gestionar"):
        raise BusinessError("Solo se marcan las limpiezas del día.")
    if len(c.checks or []) >= c.veces:
        raise BusinessError("Ya marcó todas las limpiezas programadas de esta zona.")
    c.checks = list(c.checks or []) + [{"ts": now().isoformat(timespec="minutes"), "user": user.nombre, "foto": foto or ""}]
    audit(user, "LIMPIEZA_MARCADA", "CleaningAssignment", c.id, {"zona": c.zone.nombre, "n": len(c.checks)})
    return c


def performance(desde, hasta):
    """Cumplimiento por persona y por zona: limpiezas hechas / programadas en el periodo."""
    rows = list(db().execute(select(CleaningAssignment).where(CleaningAssignment.fecha >= desde,
                                                              CleaningAssignment.fecha <= hasta)).scalars())
    per = defaultdict(lambda: {"programadas": 0, "hechas": 0, "dias": set()})
    zon = defaultdict(lambda: {"programadas": 0, "hechas": 0})
    for c in rows:
        p = per[c.worker.nombre]
        p["programadas"] += c.veces
        p["hechas"] += min(len(c.checks or []), c.veces)
        p["dias"].add(c.fecha)
        z = zon[c.zone.nombre]
        z["programadas"] += c.veces
        z["hechas"] += min(len(c.checks or []), c.veces)
    fmt = lambda d: [{"nombre": k, **{kk: vv for kk, vv in v.items() if kk != "dias"}, "dias": len(v.get("dias", [])),  # noqa: E731
                      "pct": round(100 * v["hechas"] / v["programadas"], 1) if v["programadas"] else None}
                     for k, v in sorted(d.items())]
    return {"personas": fmt(per), "zonas": fmt(zon)}


def check_unfinished(hoy=None):
    """Tarea programada (al día siguiente): limpiezas que quedaron sin marcar."""
    ayer = (hoy or date.today()) - timedelta(days=1)
    faltan = [c for c in day(ayer) if len(c.checks or []) < c.veces]
    if faltan:
        alerts.emit("LIMPIEZA_INCUMPLIDA", f"Limpiezas del {ayer:%d/%m} sin marcar: {len(faltan)}",
                    "; ".join(f"{c.worker.nombre} · {c.zone.nombre} ({len(c.checks or [])}/{c.veces})" for c in faltan[:20]),
                    "CleaningAssignment", faltan[0].id, dedup_key=f"LIMP_INC:{ayer}")
    return len(faltan)
