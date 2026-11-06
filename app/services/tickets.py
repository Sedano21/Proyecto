"""V22 (06-nov-2026): «Reportar avería» desde cualquier perfil (botón superior).

- MANTENIMIENTO: luz, gasfitería, infraestructura, máquinas, montacargas… lo atiende el Jefe de Mantenimiento, que lo
  asigna a un técnico o lo convierte en un trabajo correctivo.
- SISTEMAS: tintas, laptops, celulares, impresoras, red… lo atiende Sistemas.
Cada ticket lleva motivo, lugar, foto (o video) e indica si es urgente; se miden los tiempos de atención y solución.
"""
from datetime import timedelta

from sqlalchemy import select

from ..db import db
from ..models import Ticket, Worker, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

DESTINOS = {"MANTENIMIENTO": "Mantenimiento", "SISTEMAS": "Sistemas"}
ESTADOS = {"ABIERTO": "Abierto", "ASIGNADO": "Asignado", "EN_PROCESO": "En proceso", "RESUELTO": "Resuelto",
           "RECHAZADO": "Rechazado"}
PERM = {"MANTENIMIENTO": "tickets.mantenimiento", "SISTEMAS": "tickets.sistemas"}


def categorias():
    return param("ticket_categorias", {}) or {}


def create(user, destino, categoria, descripcion, lugar="", urgente=False, evidencias=None):
    destino = (destino or "").upper()
    if destino not in DESTINOS:
        raise BusinessError("Indique si es para Mantenimiento o para Sistemas.")
    if categoria not in (categorias().get(destino) or []):
        raise BusinessError("Elija la categoría de la lista.")
    descripcion = (descripcion or "").strip()
    if len(descripcion) < 5:
        raise BusinessError("Describa el problema o lo que necesita.")
    lugar = (lugar or "").strip()
    if destino == "MANTENIMIENTO" and not lugar:
        raise BusinessError("Indique el lugar de la avería.")
    from .alerts import user_area
    t = Ticket(destino=destino, categoria=categoria, descripcion=descripcion, lugar=lugar, urgente=bool(urgente),
               evidencias=[x for x in (evidencias or []) if x], area_origen=user_area(user), creado_por=user.id,
               historial=[{"estado": "ABIERTO", "user": user.nombre, "ts": now().isoformat(timespec="minutes"), "nota": ""}])
    db().add(t)
    db().flush()
    alerts.emit("TICKET_MANTENIMIENTO" if destino == "MANTENIMIENTO" else "TICKET_SISTEMAS",
                f"{'URGENTE · ' if urgente else ''}{categoria}: {descripcion[:80]}",
                f"Reportado por {user.nombre} ({t.area_origen or '-'})" + (f" en {lugar}" if lugar else "") + ".",
                "Ticket", t.id, prioridad="ALTA" if urgente else None, dedup_key=f"TICKET:{t.id}", creado_por=user)
    audit(user, "TICKET", "Ticket", t.id, {"destino": destino, "categoria": categoria, "urgente": bool(urgente)})
    return t


def can_attend(user, t):
    return has_perm(user, PERM[t.destino])


def visible(user, destino=None, estado=None):
    q = select(Ticket).order_by(Ticket.urgente.desc(), Ticket.ts.desc())
    if destino:
        q = q.where(Ticket.destino == destino)
    if estado == "ABIERTOS":
        q = q.where(Ticket.estado.in_(("ABIERTO", "ASIGNADO", "EN_PROCESO")))
    elif estado:
        q = q.where(Ticket.estado == estado)
    rows = list(db().execute(q).scalars())
    if has_perm(user, "tickets.ver_todos"):
        return rows
    propios = {d for d, p in PERM.items() if has_perm(user, p)}
    w = db().execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
    return [t for t in rows if t.destino in propios or t.creado_por == user.id
            or (w is not None and t.asignado_worker_id == w.id) or t.asignado_user_id == user.id]


def _hist(t, user, estado, nota=""):
    t.historial = list(t.historial or []) + [{"estado": estado, "user": user.nombre,
                                              "ts": now().isoformat(timespec="minutes"), "nota": (nota or "").strip()}]


def assign(user, t, worker_id=None, nota=""):
    if not can_attend(user, t):
        raise BusinessError("Este ticket lo atiende " + DESTINOS[t.destino] + ".")
    if t.estado in ("RESUELTO", "RECHAZADO"):
        raise BusinessError("El ticket ya está cerrado.")
    if worker_id:
        w = db().get(Worker, int(worker_id))
        if w is None or not w.activo:
            raise BusinessError("Elija un técnico activo.")
        t.asignado_worker_id = w.id
        if w.user_id:
            alerts.emit("TRABAJO_ASIGNADO", f"Ticket #{t.id} asignado: {t.categoria}", f"{t.descripcion[:160]} · {t.lugar}",
                        "Ticket", t.id, extra_users=[w.user_id], creado_por=user)
    else:
        t.asignado_user_id = user.id
    t.estado = "ASIGNADO"
    t.atendido_ts = t.atendido_ts or now()
    _hist(t, user, "ASIGNADO", nota)
    audit(user, "TICKET_ASIGNADO", "Ticket", t.id, {"worker": worker_id})


def set_state(user, t, estado, nota="", evidencias=None):
    estado = (estado or "").upper()
    if estado not in ESTADOS:
        raise BusinessError("Estado no válido.")
    w = db().execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
    es_asignado = w is not None and t.asignado_worker_id == w.id
    if not (can_attend(user, t) or es_asignado):
        raise BusinessError("Solo quien atiende el ticket cambia su estado.")
    if estado in ("RESUELTO", "RECHAZADO") and not (nota or "").strip():
        raise BusinessError("Indique la solución o el motivo del rechazo.")
    t.estado = estado
    t.atendido_ts = t.atendido_ts or now()
    if estado in ("RESUELTO", "RECHAZADO"):
        t.resuelto_ts = now()
        t.solucion = (nota or "").strip()
        alerts.close_by_system(f"TICKET:{t.id}", f"{ESTADOS[estado]} por {user.nombre}")
    if evidencias:
        t.evidencias = list(t.evidencias or []) + [x for x in evidencias if x]
    _hist(t, user, estado, nota)
    audit(user, "TICKET_ESTADO", "Ticket", t.id, {"estado": estado})


def to_work_order(user, t, fecha=None, worker_id=None):
    """El Jefe de Mantenimiento convierte el ticket en un trabajo correctivo programado."""
    from . import mant_trabajos
    if t.destino != "MANTENIMIENTO" or not has_perm(user, "mantenimiento.gestionar"):
        raise BusinessError("Solo el Jefe de Mantenimiento programa trabajos desde un ticket.")
    from ..models import SanitationZone
    zona = db().execute(select(SanitationZone).where(SanitationZone.nombre == (t.lugar or "").strip())).scalars().first()
    from ..catalogs import PRODUCTION_LINES
    maq = next((c for c, n, _ in PRODUCTION_LINES if c.upper() in (t.lugar or "").upper() or
                (t.lugar or "").upper().endswith(c.upper())), "")
    wo = mant_trabajos.save(user, {"tipo": "CORRECTIVO", "titulo": f"Ticket #{t.id}: {t.categoria}",
                                   "descripcion": f"{t.descripcion}\nLugar: {t.lugar}", "fecha_programada": fecha,
                                   "zone_id": zona.id if zona else None, "maquina": "" if zona else maq,
                                   "asignado_worker_id": worker_id, "origen": "TICKET", "ticket_id": t.id})
    t.work_order_id = wo.id
    t.estado = "ASIGNADO" if worker_id else "EN_PROCESO"
    t.atendido_ts = t.atendido_ts or now()
    _hist(t, user, t.estado, f"Trabajo correctivo #{wo.id}")
    return wo


def _horas(a, b):
    return round((b - a).total_seconds() / 3600, 1) if a and b else None


def response_times(desde, hasta, destino=None):
    """Tiempos de atención (hasta asignar o atender) y de solución, en horas, por destino y categoría."""
    q = select(Ticket).where(Ticket.ts >= desde, Ticket.ts < hasta + timedelta(days=1))
    if destino:
        q = q.where(Ticket.destino == destino)
    filas = {}
    for t in db().execute(q).scalars():
        k = (t.destino, t.categoria)
        f = filas.setdefault(k, {"destino": t.destino, "categoria": t.categoria, "total": 0, "resueltos": 0, "urgentes": 0,
                                 "atencion": [], "solucion": []})
        f["total"] += 1
        f["urgentes"] += 1 if t.urgente else 0
        if t.estado == "RESUELTO":
            f["resueltos"] += 1
        if _horas(t.ts, t.atendido_ts) is not None:
            f["atencion"].append(_horas(t.ts, t.atendido_ts))
        if _horas(t.ts, t.resuelto_ts) is not None:
            f["solucion"].append(_horas(t.ts, t.resuelto_ts))
    out = []
    for f in filas.values():
        f["atencion_h"] = round(sum(f["atencion"]) / len(f["atencion"]), 1) if f["atencion"] else None
        f["solucion_h"] = round(sum(f["solucion"]) / len(f["solucion"]), 1) if f["solucion"] else None
        out.append(f)
    return sorted(out, key=lambda x: (x["destino"], -x["total"]))
