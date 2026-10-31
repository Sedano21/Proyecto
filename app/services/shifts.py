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
from ..models import Alert, AlertType, AuditLog, PickingTask, Shift, User, UserShift
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


def managed_areas(user):
    """V7: cada responsable gestiona los turnos de su propia área (Logística incluye Almacén y Distribución);
    Gerencias y Sistemas, todas. None = todas."""
    if user.role_code in ("GERENCIA_GENERAL", "GERENTE_GENERAL_ADJUNTO", "GERENCIA_OPERACIONES", "SISTEMAS"):
        return None
    area = user.role.area if user.role else ""
    extra = (param("turnos_areas_a_cargo", {}) or {}).get(area, [])
    return {area, *extra}


def _check_area(user, persona=None, area=None):
    areas = managed_areas(user)
    if areas is None:
        return
    a = area if persona is None else (persona.role.area if persona.role else "")
    if a not in areas:
        raise BusinessError(f"Solo gestiona los turnos de su área ({', '.join(sorted(areas))}).")


def people_of(user):
    areas = managed_areas(user)
    rows = list(db().execute(select(User).where(User.activo.is_(True)).order_by(User.role_code, User.nombre)).scalars())
    return rows if areas is None else [u for u in rows if u.role and u.role.area in areas]


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
    _check_area(user, p)
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


def add_reinforcement(user, persona_id, desde, hasta, inicio, fin, motivo, tercero=None, costo_hora=None, area=""):
    """Refuerzo de emergencia: personal adicional en turno en un rango de fechas y horario. Puede ser personal de la
    empresa (persona_id) o de un tercero (tercero = {nombre, empresa, doc}); el costo por hora es obligatorio para el
    tercero y opcional para la empresa (horas extra), y da el costo de horas extra del refuerzo."""
    _check_perm(user)
    p = db().get(User, int(persona_id)) if str(persona_id or "").isdigit() else None
    tercero = {k: " ".join(str(v or "").split()) for k, v in (tercero or {}).items()}
    if p is None and not tercero.get("nombre"):
        raise BusinessError("Elija la persona de la empresa o registre los datos del tercero.")
    try:
        costo = float(costo_hora) if costo_hora not in (None, "") else None
    except ValueError:
        raise BusinessError("Costo por hora inválido.")
    if costo is not None and costo < 0:
        raise BusinessError("Costo por hora inválido.")
    if p is None:
        if costo is None:
            raise BusinessError("Indique el costo por hora del personal del tercero.")
        area = area or (user.role.area if user.role else "")
        _check_area(user, area=area)
    else:
        _check_area(user, p)
        area = p.role.area if p.role else area
    if desde is None or (hasta and hasta < desde):
        raise BusinessError("Indique el rango de fechas del refuerzo.")
    if not (HORA.match(inicio or "") and HORA.match(fin or "")) or inicio == fin:
        raise BusinessError("Indique el horario del refuerzo (HH:MM).")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo (emergencia que se atiende).")
    us = UserShift(user_id=p.id if p else None, desde=desde, hasta=hasta or desde, tipo="REFUERZO", inicio=inicio, fin=fin,
                   motivo=motivo.strip(), creado_por=user.id, area=area or "", costo_hora=costo,
                   tercero_nombre=tercero.get("nombre", "") if p is None else "",
                   tercero_empresa=tercero.get("empresa", "") if p is None else "",
                   tercero_doc=tercero.get("doc", "") if p is None else "")
    db().add(us)
    db().flush()
    audit(user, "REFUERZO_AGREGADO", "User", p.username if p else us.persona,
          {"desde": desde, "hasta": us.hasta, "horario": f"{inicio}-{fin}", "motivo": motivo, "costo_hora": costo,
           "tercero": tercero if p is None else None})
    return us


def reinforcement_costs(desde, hasta, areas=None):
    """Costo de horas extra de los refuerzos: horas del refuerzo (días × horario) × costo por hora."""
    rows = []
    for us in db().execute(select(UserShift).where(UserShift.tipo == "REFUERZO", UserShift.desde <= hasta)).scalars():
        fin = us.hasta or us.desde
        if fin < desde or (areas is not None and us.area not in areas):
            continue
        dias = (min(fin, hasta) - max(us.desde, desde)).days + 1
        horas = round(minutes(us.inicio, us.fin) / 60.0 * dias, 2)
        rows.append({"us": us, "persona": us.persona, "tercero": us.user_id is None, "dias": dias, "horas": horas,
                     "costo_hora": us.costo_hora, "costo": round(horas * us.costo_hora, 2) if us.costo_hora is not None else None})
    return {"filas": rows, "horas": round(sum(r["horas"] for r in rows), 2),
            "costo": round(sum(r["costo"] or 0 for r in rows), 2),
            "costo_terceros": round(sum(r["costo"] or 0 for r in rows if r["tercero"]), 2),
            "sin_costo": sum(1 for r in rows if r["costo"] is None)}


def remove_assignment(user, us):
    _check_perm(user)
    if us.user is not None:
        _check_area(user, us.user)
    else:
        _check_area(user, area=us.area)
    audit(user, "TURNO_RETIRADO", "User", us.user.username if us.user else us.persona, {"tipo": us.tipo, "turno": us.shift.nombre if us.shift else "",
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


def schedule_table(d, users=None):
    """Quién trabaja el día d (para la pantalla de turnos)."""
    out = []
    users = users if users is not None else db().execute(select(User).where(User.activo.is_(True))
                                                         .order_by(User.role_code, User.nombre)).scalars()
    for u in users:
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


PRIORIDADES = ("ALTA", "MEDIA", "BAJA")


def deadlines():
    """Plazos de atención en minutos: {área: {urgencia: minutos}} más el plazo general (en horas) para las áreas sin
    plazo propio."""
    general = {k: float(v) * 60 for k, v in (param("horas_plazo_tarea", {}) or {}).items() if v}
    por_area = param("minutos_plazo_tarea_por_area", {}) or {}
    areas = {t.code: t.area for t in db().execute(select(AlertType)).scalars()}
    return general, por_area, areas


def deadline_minutes(alert, plazos=None):
    general, por_area, areas = plazos or deadlines()
    propio = (por_area.get(areas.get(alert.type_code)) or {}).get(alert.prioridad)
    return float(propio) if propio else general.get(alert.prioridad)


def fmt_plazo(minutos):
    return f"{minutos:g} min" if minutos < 60 else f"{minutos / 60:g} h"


def save_deadlines(user, form):
    """Guarda desde el panel de alertas el plazo general (horas) y los plazos por área (minutos; vacío = general)."""
    general, por_area = {}, {}
    for p in PRIORIDADES:
        v = (form.get(f"general_{p}") or "").strip()
        try:
            general[p] = float(v) if v else None
        except ValueError:
            raise BusinessError(f"Plazo general {p}: indique horas en número.")
        if not general[p] or general[p] <= 0:
            raise BusinessError(f"Plazo general {p}: debe ser mayor que cero.")
        general[p] = int(general[p]) if general[p] == int(general[p]) else general[p]
    for area in form.getlist("areas"):
        fila = {}
        for p in PRIORIDADES:
            v = (form.get(f"area_{area}_{p}") or "").strip()
            if not v:
                continue
            try:
                m = int(v)
            except ValueError:
                raise BusinessError(f"{area} {p}: indique minutos en número entero.")
            if m <= 0:
                raise BusinessError(f"{area} {p}: debe ser mayor que cero.")
            fila[p] = m
        if fila:
            por_area[area] = fila
    fin_turno = {}
    for area in ["*"] + form.getlist("areas"):
        v = (form.get(f"finturno_{area}") or "").strip()
        if v:
            try:
                m = int(v)
            except ValueError:
                raise BusinessError(f"{area}: minutos antes del fin de turno en número entero.")
            if m < 0:
                raise BusinessError("Los minutos antes del fin de turno no pueden ser negativos.")
            fin_turno[area] = m
    from .core import set_param
    if fin_turno and fin_turno != (param("minutos_antes_fin_turno_por_area", {}) or {}):
        set_param("minutos_antes_fin_turno_por_area", fin_turno, user)
    if general != (param("horas_plazo_tarea", {}) or {}):
        set_param("horas_plazo_tarea", general, user)
    if por_area != (param("minutos_plazo_tarea_por_area", {}) or {}):
        set_param("minutos_plazo_tarea_por_area", por_area, user)


def check_overdue(ahora=None):
    """Tareas (alertas que son tareas) y pickings que vencieron su plazo sin completarse: se alerta al jefe del
    responsable (una sola vez por tarea)."""
    ahora = ahora or now()
    plazos = deadlines()
    n = 0
    for a in db().execute(select(Alert).where(Alert.estado.in_(["PENDIENTE", "EN_EJECUCION", "INCIDENCIA"]),
                                              Alert.type_code != "TAREA_INCUMPLIDA")).scalars():
        if not alerts.is_task(a):
            continue
        minutos = deadline_minutes(a, plazos)
        if not minutos or (ahora - a.creado_ts).total_seconds() < minutos * 60:
            continue
        resp = db().get(User, a.asignado_a) if a.asignado_a else None
        roles = [resp.role_code] if resp else ([a.asignado_rol] if a.asignado_rol else list(a.roles or []))
        jefes = [j for j in _bosses(roles) if j not in roles]
        if not jefes or _avisado(f"INCUMPLIDA:A{a.id}"):
            continue
        quien = resp.nombre if resp else ", ".join(roles)
        if alerts.emit("TAREA_INCUMPLIDA", f"Tarea vencida sin completar: {a.titulo}"[:250],
                       f"Responsable: {quien}. Creada {a.creado_ts:%d/%m/%Y %H:%M}; plazo {fmt_plazo(minutos)} (urgencia {a.prioridad}). "
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


def compliance(desde, hasta, user=None):
    """Cumplimiento por persona (V12, 29-oct-2026): solo el personal del área de quien consulta (Gerencia y Sistemas,
    todas) y solo lo que tiene que ver con sus funciones: tareas recibidas, cerradas a tiempo o fuera de plazo y
    vencidas abiertas (la interacción general con el sistema no se muestra). Además, por área:
    - Almacén: pickings asignados, listos, tarde y atrasados;
    - Producción: tasa de ausencia, rendimiento (kg/h), merma y remanente por persona (partes y Asistencia);
    - Distribución: rutas, entregas y entregas con incidencia por chofer;
    - cualquier área con personal en Asistencia: tasa de ausencia."""
    s = db()
    plazos = deadlines()
    areas = managed_areas(user) if user is not None else None
    t0, t1 = datetime.combine(desde, time.min), datetime.combine(hasta, time.max)
    users = {u.id: u for u in s.execute(select(User)).scalars()
             if areas is None or (u.role and u.role.area in areas)}
    acc = defaultdict(Counter)
    for a in s.execute(select(Alert).where(Alert.creado_ts >= t0, Alert.creado_ts <= t1)).scalars():
        if not alerts.is_task(a):
            continue
        uid = a.asignado_a or a.cerrado_por
        if not uid or uid not in users:
            continue
        c = acc[uid]
        c["tareas"] += 1
        minutos = deadline_minutes(a, plazos)
        lim = a.creado_ts + timedelta(minutes=minutos) if minutos else None
        if a.cerrado_ts:
            c["a_tiempo" if (lim is None or a.cerrado_ts <= lim) else "fuera_plazo"] += 1
        elif lim and now() > lim:
            c["vencidas"] += 1
    ver_picking = areas is None or "Almacén" in areas
    if ver_picking:
        for t in s.execute(select(PickingTask).where(PickingTask.fecha >= desde, PickingTask.fecha <= hasta)).scalars():
            for uid in t.asignados or []:
                if uid not in users:
                    continue
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
        u = users[uid]
        cerr = c["a_tiempo"] + c["fuera_plazo"]
        filas.append({"user": u, "tareas": c["tareas"], "a_tiempo": c["a_tiempo"], "fuera_plazo": c["fuera_plazo"],
                      "vencidas": c["vencidas"], "cumplimiento": round(100.0 * c["a_tiempo"] / cerr, 1) if cerr else None,
                      "picking": c["picking"], "picking_listo": c["picking_listo"], "picking_tarde": c["picking_tarde"],
                      "picking_atrasado": c["picking_atrasado"]})
    filas.sort(key=lambda x: (x["user"].role_code, x["user"].nombre))
    reco = []
    venc = [f for f in filas if f["vencidas"] or f["picking_atrasado"]]
    if venc:
        reco.append(("MEDIA", f"{len(venc)} persona(s) con tareas vencidas o pickings atrasados: "
                              + ", ".join(f["user"].nombre for f in venc[:4]) + ". Revisar carga de trabajo y turnos."))
    bajos = [f for f in filas if f["cumplimiento"] is not None and f["cumplimiento"] < 70 and f["tareas"] >= 3]
    for f in bajos[:3]:
        reco.append(("MEDIA", f"{f['user'].nombre} cierra a tiempo solo el {f['cumplimiento']} % de sus tareas: conversar "
                              "sobre prioridades y plazos."))
    out = {"desde": desde, "hasta": hasta, "filas": filas, "plazos": param("horas_plazo_tarea", {}) or {},
           "plazos_area": {a: {k: fmt_plazo(float(v)) for k, v in f.items()} for a, f in plazos[1].items()},
           "areas": sorted(areas) if areas is not None else None, "ver_picking": ver_picking,
           "produccion": None, "distribucion": None, "asistencia": None}
    # Producción: personal operativo (no son usuarios del sistema)
    if areas is None or "Producción" in areas:
        from .prod_analytics import analyze
        pa = analyze(desde, hasta)
        out["produccion"] = pa["personas"]
        reco += [x for x in pa["recomendaciones"] if not x[1].startswith(("La línea", "Hay "))]
    # Distribución: desempeño por chofer
    if areas is None or "Distribución" in areas:
        from ..models import Incident, Route, RouteStop
        por = defaultdict(lambda: {"rutas": 0, "paradas": 0, "entregadas": 0, "con_incidencia": 0})
        for r in s.execute(select(Route).where(Route.fecha >= desde, Route.fecha <= hasta)).scalars():
            if not r.driver_id:
                continue
            x = por[r.driver.nombre if r.driver else str(r.driver_id)]
            x["rutas"] += 1
            for st in r.stops:
                x["paradas"] += 1
                x["entregadas"] += st.estado in ("ENTREGADA", "ENTREGADO")
                x["con_incidencia"] += bool(s.execute(select(Incident.id).where(Incident.order_id == st.order_id)).first())
        out["distribucion"] = [{"chofer": k, **v, "efectividad": round(100 * v["entregadas"] / v["paradas"], 1) if v["paradas"] else None}
                               for k, v in sorted(por.items())]
    # asistencia del personal de las demás áreas registradas en Asistencia
    from ..models import Attendance
    asis = defaultdict(Counter)
    for a in s.execute(select(Attendance).where(Attendance.fecha >= desde, Attendance.fecha <= hasta)).scalars():
        ar = a.worker.area or "Producción"
        if ar != "Producción" and (areas is None or ar in areas):
            asis[(ar, a.worker.nombre)][a.estado] += 1
    if asis:
        out["asistencia"] = [{"area": ar, "nombre": n, "dias": sum(c.values()), "faltas": c.get("FALTA", 0),
                              "ausencia_pct": round(100 * c.get("FALTA", 0) / sum(c.values()), 1)} for (ar, n), c in sorted(asis.items())]
    out["recomendaciones"] = reco
    return out


# ------------------------------------------------------------------ cierre de turno (ronda 23-oct-2026, decisión 7)
def _open_tasks_of(u):
    out = []
    for a in db().execute(select(Alert).where(Alert.estado.in_(["PENDIENTE", "EN_EJECUCION", "INCIDENCIA"]),
                                              Alert.asignado_a == u.id)).scalars():
        if alerts.is_task(a):
            out.append(a)
    return out


def minutes_before_end(u):
    cfg = param("minutos_antes_fin_turno_por_area", {}) or {}
    area = u.role.area if u.role else ""
    v = cfg.get(area, cfg.get("*"))
    return float(v) if v not in (None, "") else None


def check_end_of_shift(ahora=None):
    """X minutos antes del fin del turno (configurable por área), si la persona tiene tareas abiertas se avisa a su jefe
    (una vez por persona y turno)."""
    ahora = ahora or now()
    n = 0
    for u in db().execute(select(User).where(User.activo.is_(True))).scalars():
        mins = minutes_before_end(u)
        if mins is None:
            continue
        for d in (ahora.date(), ahora.date() - timedelta(days=1)):
            for _a, fin, _r, etiqueta in windows(u.id, d):
                if not (fin - timedelta(minutes=mins) <= ahora <= fin + timedelta(hours=2)):
                    continue
                tareas = _open_tasks_of(u)
                jefes = [j for j in _bosses([u.role_code]) if j != u.role_code]
                if not tareas or not jefes or _avisado(f"FIN_TURNO:{u.id}:{fin:%Y%m%d%H%M}"):
                    continue
                if alerts.emit("TAREAS_PENDIENTES_FIN_TURNO", f"{u.nombre}: {len(tareas)} tarea(s) abierta(s) al cierre del turno",
                               f"Turno {etiqueta} termina {fin:%d/%m %H:%M}. Pendientes: "
                               + "; ".join(a.titulo[:60] for a in tareas[:5]) + ("…" if len(tareas) > 5 else ""),
                               "User", u.id, extra_roles=jefes, dedup_key=f"FIN_TURNO:{u.id}:{fin:%Y%m%d%H%M}") is not None:
                    n += 1
    return n


def pending_carryover(user, ahora=None):
    """Tareas que la persona dejó abiertas de días anteriores (se muestran primero al iniciar el día) con su tiempo de
    atención, y su indicador de los últimos 30 días (% atendidas dentro del plazo y tiempo promedio de atención)."""
    ahora = ahora or now()
    hoy = datetime.combine(ahora.date(), time.min)
    plazos = deadlines()
    abiertas = [a for a in db().execute(select(Alert).where(Alert.estado.in_(["PENDIENTE", "EN_EJECUCION", "INCIDENCIA"]),
                                                            Alert.creado_ts < hoy)).scalars()
                if alerts.is_task(a) and alerts.is_assignee(user, a)]
    filas = []
    for a in sorted(abiertas, key=lambda x: x.creado_ts):
        lim = deadline_minutes(a, plazos)
        edad = (ahora - a.creado_ts).total_seconds() / 60.0
        filas.append({"alerta": a, "horas": round(edad / 60.0, 1), "plazo": fmt_plazo(lim) if lim else "-",
                      "vencida": bool(lim and edad > lim)})
    desde = ahora - timedelta(days=30)
    cerradas = [a for a in db().execute(select(Alert).where(Alert.creado_ts >= desde, Alert.cerrado_ts.isnot(None))).scalars()
                if alerts.is_task(a) and (a.asignado_a == user.id or a.cerrado_por == user.id)]
    a_tiempo, tiempos = 0, []
    for a in cerradas:
        lim = deadline_minutes(a, plazos)
        m = (a.cerrado_ts - a.creado_ts).total_seconds() / 60.0
        tiempos.append(m)
        if not lim or m <= lim:
            a_tiempo += 1
    return {"filas": filas, "cerradas_30d": len(cerradas),
            "a_tiempo_pct": round(100.0 * a_tiempo / len(cerradas), 1) if cerradas else None,
            "atencion_prom": fmt_plazo(sum(tiempos) / len(tiempos)) if tiempos else None}
