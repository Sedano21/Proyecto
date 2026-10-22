"""Turnos del personal y cumplimiento de funciones (marcha blanca, respuestas del 22-oct-2026).

- Turnos con días, horario y refrigerio; una persona puede tener varios turnos y turnos rotativos por semana.
- Refuerzos de emergencia: personal agregado en Configuración para atender una emergencia (cuenta como «en turno»).
- Las tareas (picking) se proponen y asignan solo a personal en turno. La entrada y salida las mide otro sistema: el
  módulo solo registra las interacciones y el cumplimiento de las funciones dentro del módulo.
- Si una tarea no se cumple en su plazo, se alerta al jefe del responsable (organigrama configurable).
"""
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Alert, AuditLog, PickingTask, Shift, User, UserShift
from . import alerts
from ..models import now
from .core import BusinessError, audit, has_perm, param

HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _t(h):
    return time(int(h[:2]), int(h[3:5]))


def _check_perm(user):
    if not has_perm(user, "turnos.gestionar"):
        raise BusinessError("Su rol no configura turnos.")


# ------------------------------------------------------------------ turnos
def save_shift(user, nombre, dias, inicio, fin, refrigerio_min=0, shift=None, activo=True):
    _check_perm(user)
    nombre = (nombre or "").strip()
    if not nombre:
        raise BusinessError("Indique el nombre del turno.")
    dias = sorted({int(d) for d in dias if str(d).strip() != ""})
    if not dias or any(d < 0 or d > 6 for d in dias):
        raise BusinessError("Elija al menos un día del turno.")
    if not (HORA.match(inicio or "") and HORA.match(fin or "")) or inicio == fin:
        raise BusinessError("Indique la hora de inicio y de fin (HH:MM), distintas.")
    ref = int(refrigerio_min or 0)
    if ref < 0 or ref >= minutes(inicio, fin):
        raise BusinessError("El refrigerio debe ser menor que la duración del turno.")
    s = shift or Shift()
    s.nombre, s.dias, s.inicio, s.fin, s.refrigerio_min, s.activo = nombre, dias, inicio, fin, ref, bool(activo)
    if shift is None:
        db().add(s)
    db().flush()
    audit(user, "TURNO_GUARDADO", "Shift", s.id, {"nombre": nombre, "dias": dias, "inicio": inicio, "fin": fin,
                                                    "refrigerio_min": ref})
    return s


def minutes(inicio, fin):
    a = int(inicio[:2]) * 60 + int(inicio[3:])
    b = int(fin[:2]) * 60 + int(fin[3:])
    return (b - a) % (24 * 60)


def assign_shift(user, persona_id, shift_id, desde, hasta=None, ciclo=1, semana=0):
    _check_perm(user)
    p = db().get(User, int(persona_id))
    sh = db().get(Shift, int(shift_id)) if shift_id else None
    if p is None or sh is None:
        raise BusinessError("Elija la persona y el turno.")
    if desde is None:
        raise BusinessError("Indique desde qué fecha rige el turno.")
    if hasta and hasta < desde:
        raise BusinessError("La fecha final no puede ser anterior a la inicial.")
    ciclo = max(int(ciclo or 1), 1)
    semana = int(semana or 0)
    if not 0 <= semana < ciclo:
        raise BusinessError("La semana de rotación debe estar entre 0 y el ciclo − 1.")
    us = UserShift(user_id=p.id, shift_id=sh.id, desde=desde, hasta=hasta, ciclo=ciclo, semana=semana, tipo="REGULAR",
                   creado_por=user.id)
    db().add(us)
    db().flush()
    audit(user, "TURNO_ASIGNADO", "User", p.username, {"turno": sh.nombre, "desde": desde, "hasta": hasta,
                                                       "rotacion": f"{semana + 1} de {ciclo}" if ciclo > 1 else ""})
    return us


def add_reinforcement(user, persona_id, desde, hasta, inicio, fin, motivo):
    """Refuerzo de emergencia: personal adicional en turno en un rango de fechas y horario."""
    _check_perm(user)
    p = db().get(User, int(persona_id))
    if p is None:
        raise BusinessError("Elija la persona.")
    if desde is None or (hasta and hasta < desde):
        raise BusinessError("Indique el rango de fechas del refuerzo.")
    if not (HORA.match(inicio or "") and HORA.match(fin or "")) or inicio == fin:
        raise BusinessError("Indique el horario del refuerzo (HH:MM).")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo (emergencia que se atiende).")
    us = UserShift(user_id=p.id, desde=desde, hasta=hasta or desde, tipo="REFUERZO", inicio=inicio, fin=fin,
                   motivo=motivo.strip(), creado_por=user.id)
    db().add(us)
    db().flush()
    audit(user, "REFUERZO_AGREGADO", "User", p.username, {"desde": desde, "hasta": us.hasta, "horario": f"{inicio}-{fin}",
                                                          "motivo": motivo})
    return us


def remove_assignment(user, us):
    _check_perm(user)
    audit(user, "TURNO_RETIRADO", "User", us.user.username, {"tipo": us.tipo, "turno": us.shift.nombre if us.shift else "",
                                                             "desde": us.desde, "hasta": us.hasta})
    db().delete(us)


def _applies(us, d):
    if d < us.desde or (us.hasta and d > us.hasta):
        return False
    if us.tipo == "REFUERZO":
        return True
    if us.shift is None or not us.shift.activo:
        return False
    if us.ciclo > 1 and d.isocalendar()[1] % us.ciclo != us.semana:
        return False
    return d.weekday() in (us.shift.dias or [])


def windows(user_id, d, cache=None):
    """Ventanas de trabajo (inicio, fin, refrigerio_min, etiqueta) de la persona que comienzan el día d."""
    rows = cache.get(user_id, []) if cache is not None else list(db().execute(
        select(UserShift).where(UserShift.user_id == user_id)).scalars())
    out = []
    for us in rows:
        if not _applies(us, d):
            continue
        ini, fin = (us.inicio, us.fin) if us.tipo == "REFUERZO" else (us.shift.inicio, us.shift.fin)
        a = datetime.combine(d, _t(ini))
        b = datetime.combine(d, _t(fin))
        if b <= a:
            b += timedelta(days=1)  # turno nocturno
        out.append((a, b, 0 if us.tipo == "REFUERZO" else us.shift.refrigerio_min,
                    "Refuerzo" if us.tipo == "REFUERZO" else us.shift.nombre))
    return out


def has_config(user_ids):
    if not user_ids:
        return False
    return db().execute(select(UserShift.id).where(UserShift.user_id.in_(list(user_ids)))).first() is not None


def works_on(user_id, d, cache=None):
    """Trabaja el día d: tiene un turno que empieza ese día o uno nocturno del día anterior que termina ese día."""
    if windows(user_id, d, cache):
        return True
    return any(b.date() == d and b.time() > time(0, 0) for _a, b, _r, _l in windows(user_id, d - timedelta(days=1), cache))


def in_shift_at(user_id, ts, cache=None):
    for d in (ts.date(), ts.date() - timedelta(days=1)):
        for a, b, _r, _l in windows(user_id, d, cache):
            if a <= ts < b:
                return True
    return False


def filter_on_shift(users, d):
    """Personal en turno el día d. Si nadie del grupo tiene turno configurado (transición), devuelve a todos."""
    if not param("asignar_solo_personal_en_turno", True):
        return list(users)
    ids = [u.id for u in users]
    if not has_config(ids):
        return list(users)
    return [u for u in users if works_on(u.id, d)]


def schedule_table(d):
    """Quién trabaja el día d (para la pantalla de turnos)."""
    out = []
    for u in db().execute(select(User).where(User.activo.is_(True)).order_by(User.role_code, User.nombre)).scalars():
        w = windows(u.id, d)
        if w:
            out.append((u, w))
    return out


# ------------------------------------------------------------------ cumplimiento
def _bosses(role_codes):
    m = param("jefe_por_rol", {}) or {}
    out = []
    for r in role_codes:
        for j in m.get(r, []):
            if j not in out:
                out.append(j)
    return out


def _avisado(dedup_key):
    """El aviso al jefe se da una sola vez por tarea (aunque el jefe ya lo haya cerrado)."""
    return db().execute(select(Alert.id).where(Alert.dedup_key == dedup_key)).first() is not None


def check_overdue(ahora=None):
    """Tareas (alertas que son tareas) y pickings que vencieron su plazo sin completarse: se alerta al jefe del
    responsable (una sola vez por tarea)."""
    ahora = ahora or now()
    plazos = param("horas_plazo_tarea", {}) or {}
    n = 0
    for a in db().execute(select(Alert).where(Alert.estado.in_(["PENDIENTE", "EN_EJECUCION", "INCIDENCIA"]),
                                              Alert.type_code != "TAREA_INCUMPLIDA")).scalars():
        if not alerts.is_task(a):
            continue
        horas = plazos.get(a.prioridad)
        if not horas or (ahora - a.creado_ts).total_seconds() < float(horas) * 3600:
            continue
        resp = db().get(User, a.asignado_a) if a.asignado_a else None
        roles = [resp.role_code] if resp else ([a.asignado_rol] if a.asignado_rol else list(a.roles or []))
        jefes = [j for j in _bosses(roles) if j not in roles]
        if not jefes or _avisado(f"INCUMPLIDA:A{a.id}"):
            continue
        quien = resp.nombre if resp else ", ".join(roles)
        if alerts.emit("TAREA_INCUMPLIDA", f"Tarea vencida sin completar: {a.titulo}"[:250],
                       f"Responsable: {quien}. Creada {a.creado_ts:%d/%m/%Y %H:%M}; plazo {horas} h (urgencia {a.prioridad}). "
                       f"Estado: {a.estado}.", "Alert", a.id, extra_roles=jefes, dedup_key=f"INCUMPLIDA:A{a.id}") is not None:
            n += 1
    hoy = ahora.date()
    for t in db().execute(select(PickingTask).where(PickingTask.estado != "LISTO", PickingTask.fecha < hoy)).scalars():
        if t.order is None or t.order.estado in ("CANCELADA",):
            continue
        personas = [db().get(User, i) for i in (t.asignados or [])]
        roles = sorted({p.role_code for p in personas if p}) or ["AUX_ALMACEN"]
        jefes = [j for j in _bosses(roles) if j not in roles]
        if not jefes or _avisado(f"INCUMPLIDA:P{t.id}"):
            continue
        nombres = ", ".join(p.nombre for p in personas if p) or "sin asignar"
        if alerts.emit("TAREA_INCUMPLIDA", f"Picking atrasado: OV {t.order.numero} (programado {t.fecha:%d/%m/%Y})",
                       f"Asignado a: {nombres}. Estado {t.estado}. Almacén {t.warehouse_code}.", "SalesOrder", t.order_id,
                       extra_roles=jefes, dedup_key=f"INCUMPLIDA:P{t.id}") is not None:
            n += 1
    return n


def compliance(desde, hasta):
    """Interacciones y cumplimiento por persona en el periodo: acciones registradas (dentro y fuera de turno, solo para
    análisis), tareas recibidas, completadas a tiempo o fuera de plazo y vencidas abiertas, y pickings."""
    s = db()
    plazos = param("horas_plazo_tarea", {}) or {}
    t0, t1 = datetime.combine(desde, time.min), datetime.combine(hasta, time.max)
    users = {u.id: u for u in s.execute(select(User)).scalars()}
    cache = defaultdict(list)
    for us in s.execute(select(UserShift)).scalars():
        cache[us.user_id].append(us)
    acc = defaultdict(Counter)
    for a in s.execute(select(AuditLog).where(AuditLog.ts >= t0, AuditLog.ts <= t1, AuditLog.user_id.isnot(None))).scalars():
        c = acc[a.user_id]
        c["acciones"] += 1
        if cache.get(a.user_id):
            c["dentro" if in_shift_at(a.user_id, a.ts, cache) else "fuera"] += 1
    for a in s.execute(select(Alert).where(Alert.creado_ts >= t0, Alert.creado_ts <= t1)).scalars():
        if not alerts.is_task(a):
            continue
        uid = a.asignado_a or a.cerrado_por
        if not uid:
            continue
        c = acc[uid]
        c["tareas"] += 1
        horas = plazos.get(a.prioridad)
        lim = a.creado_ts + timedelta(hours=float(horas)) if horas else None
        if a.cerrado_ts:
            c["a_tiempo" if (lim is None or a.cerrado_ts <= lim) else "fuera_plazo"] += 1
        elif lim and now() > lim:
            c["vencidas"] += 1
    for t in s.execute(select(PickingTask).where(PickingTask.fecha >= desde, PickingTask.fecha <= hasta)).scalars():
        for uid in t.asignados or []:
            c = acc[uid]
            c["picking"] += 1
            if t.estado == "LISTO":
                c["picking_listo"] += 1
                if t.fin_ts and t.fin_ts.date() > t.fecha:
                    c["picking_tarde"] += 1
            elif t.fecha < date.today():
                c["picking_atrasado"] += 1
    filas = []
    for uid, c in acc.items():
        u = users.get(uid)
        if u is None:
            continue
        cerr = c["a_tiempo"] + c["fuera_plazo"]
        filas.append({"user": u, "acciones": c["acciones"], "dentro": c["dentro"], "fuera": c["fuera"],
                      "con_turno": bool(cache.get(uid)), "tareas": c["tareas"], "a_tiempo": c["a_tiempo"],
                      "fuera_plazo": c["fuera_plazo"], "vencidas": c["vencidas"],
                      "cumplimiento": round(100.0 * c["a_tiempo"] / cerr, 1) if cerr else None,
                      "picking": c["picking"], "picking_listo": c["picking_listo"], "picking_tarde": c["picking_tarde"],
                      "picking_atrasado": c["picking_atrasado"]})
    filas.sort(key=lambda x: (x["user"].role_code, x["user"].nombre))
    reco = []
    venc = [f for f in filas if f["vencidas"] or f["picking_atrasado"]]
    if venc:
        reco.append(f"{len(venc)} persona(s) con tareas vencidas o pickings atrasados: revisar carga de trabajo y turnos.")
    fuera = sorted((f for f in filas if f["fuera"]), key=lambda f: -f["fuera"])[:3]
    if fuera:
        reco.append("Más acciones fuera de su turno (solo análisis): " + ", ".join(f"{f['user'].nombre} ({f['fuera']})" for f in fuera) + ".")
    if not any(cache.values()):
        reco.append("Aún no hay turnos configurados: las acciones no se separan en dentro y fuera de turno.")
    return {"desde": desde, "hasta": hasta, "filas": filas, "plazos": plazos,
            "turnos_configurados": any(cache.values()), "recomendaciones": reco}
