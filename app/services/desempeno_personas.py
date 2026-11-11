"""V27 (11-nov-2026): desempeño por persona para Gestión Humana (y los jefes): lo que hizo cada persona en el periodo
(picking, movimientos, tareas completadas, picking a tiempo) junto con su disponibilidad (vacaciones, descansos médicos y
faltas). Solo consulta; usa los mismos registros que el desempeño del equipo."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Absence, PickingTask, User
from .seguimiento import team_performance

TIPOS_AUSENCIA = {"VACACIONES": "Vacaciones", "DESCANSO_MEDICO": "Descanso médico", "FALTA_JUSTIFICADA": "Falta justificada",
                  "FALTA_INJUSTIFICADA": "Falta injustificada"}


def _dias(a, desde, hasta):
    ini, fin = max(a.desde, desde), min(a.hasta, hasta)
    return max(0, (fin - ini).days + 1)


def por_persona(desde=None, hasta=None, area=""):
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=29)
    equipo = {f["user"].id: f for f in team_performance(desde, hasta)["filas"]}
    aus = defaultdict(lambda: defaultdict(int))
    for a in db().execute(select(Absence).where(Absence.persona_tipo == "USER", Absence.anulada.is_(False),
                                                Absence.desde <= hasta, Absence.hasta >= desde)).scalars():
        aus[a.persona_id][a.tipo] += _dias(a, desde, hasta)
    # picking terminado a tiempo: tareas LISTO cuyo cierre fue a más tardar en su fecha programada
    a_tiempo = defaultdict(lambda: [0, 0])
    for t in db().execute(select(PickingTask).where(PickingTask.fecha >= desde, PickingTask.fecha <= hasta,
                                                    PickingTask.estado == "LISTO")).scalars():
        fin = getattr(t, "fin_ts", None)
        for uid in t.asignados or []:
            a_tiempo[uid][1] += 1
            if fin is None or fin.date() <= t.fecha:
                a_tiempo[uid][0] += 1
    users = list(db().execute(select(User).where(User.activo.is_(True)).order_by(User.nombre)).scalars())
    filas = []
    for u in users:
        if u.username.startswith("sim."):
            continue
        ar = u.role.area if u.role else ""
        if area and ar != area:
            continue
        e = equipo.get(u.id, {})
        at = a_tiempo.get(u.id, [0, 0])
        ausencias = dict(aus.get(u.id, {}))
        actividad = (e.get("ov", 0) + e.get("movimientos", 0) + e.get("tareas", 0))
        if not actividad and not ausencias:
            continue
        filas.append({"user": u, "area": ar, "ov": e.get("ov", 0), "clientes": e.get("clientes", 0),
                      "unidades": e.get("unidades", 0), "kg": e.get("kg", 0), "movimientos": e.get("movimientos", 0),
                      "mov_prom_min": e.get("mov_prom_min"), "tareas": e.get("tareas", 0),
                      "picking_a_tiempo": round(100 * at[0] / at[1]) if at[1] else None, "picking_total": at[1],
                      "ausencias": ausencias, "faltas_injust": ausencias.get("FALTA_INJUSTIFICADA", 0)})
    filas.sort(key=lambda f: (f["area"], -(f["ov"] + f["movimientos"] + f["tareas"]), f["user"].nombre))
    areas = sorted({(u.role.area if u.role else "") for u in users} - {""})
    return {"desde": desde, "hasta": hasta, "filas": filas, "areas": areas, "tipos": TIPOS_AUSENCIA}
