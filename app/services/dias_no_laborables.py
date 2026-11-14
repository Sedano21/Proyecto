"""V27 (11-nov-2026): días en que un área no labora y replanificación de lo programado para ese día.

El jefe del área registra la fecha y el motivo. Desde ese momento la programación del área no usa esa fecha y lo que ya
estaba programado se muestra para replanificarlo, todo junto, al siguiente día hábil del área (o a la fecha que elija):
- Producción: solicitudes programadas en línea;
- Almacén: picking;
- Distribución: rutas propuestas o confirmadas;
- Mantenimiento: órdenes de trabajo;
- Limpieza: limpiezas asignadas.
Las OV no cambian su fecha comprometida (es compromiso con el cliente): si la replanificación la pone en riesgo, se avisa.
"""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import AreaDayOff, PickingTask, ProductionRequest, Route, now
from . import alerts
from .core import BusinessError, audit, has_perm, param, roles_of

# V33: también Comercial, Calidad, Logística, Compras y Administración y Finanzas (pueden registrarse varias a la vez)
AREAS = ("Producción", "Almacén", "Distribución", "Mantenimiento", "Limpieza", "Comercial", "Calidad", "Logística",
         "Compras", "Administración y Finanzas")


def areas_de(user):
    if user is None or not has_perm(user, "dias.no_laborables"):
        return []
    mapa = param("dias_no_laborables_areas_por_rol", {}) or {}
    out = []
    for r in roles_of(user):
        for a in mapa.get(r, []):
            if a == "*":
                return list(AREAS)
            if a in AREAS and a not in out:
                out.append(a)
    return out


def es_no_laborable(area, fecha):
    return db().execute(select(AreaDayOff.id).where(AreaDayOff.area == area, AreaDayOff.fecha == fecha,
                                                    AreaDayOff.activo.is_(True))).first() is not None


def siguiente_habil(area, fecha):
    from .calendar import day_factor, holidays
    fer = holidays()
    d = fecha + timedelta(days=1)
    for _ in range(60):
        if day_factor(d, fer) > 0 and not es_no_laborable(area, d):
            return d
        d += timedelta(days=1)
    raise BusinessError("No se encontró un día hábil en los próximos 60 días.")


def afectados(area, fecha):
    """[{tipo, id, texto, obj}] de lo programado ese día en el área."""
    s = db()
    out = []
    if area == "Producción":
        for r in s.execute(select(ProductionRequest).where(ProductionRequest.fecha_programada == fecha,
                                                           ProductionRequest.estado.in_(("PROGRAMADA", "VALIDADA")))).scalars():
            out.append({"tipo": "PRODUCCION", "id": r.id, "texto": f"Producción #{r.id} · {r.product_code} {r.cantidad:g}"
                        + (f" · línea {r.line_code}" if r.line_code else ""), "obj": r})
    elif area == "Almacén":
        for t in s.execute(select(PickingTask).where(PickingTask.fecha == fecha, PickingTask.estado != "LISTO")).scalars():
            out.append({"tipo": "PICKING", "id": t.id, "texto": f"Picking OV {t.order.numero} · {t.warehouse_code} · "
                        f"{t.order.customer.nombre}", "obj": t})
    elif area == "Distribución":
        for r in s.execute(select(Route).where(Route.fecha == fecha, Route.estado.in_(("PROPUESTA", "CONFIRMADA")))).scalars():
            out.append({"tipo": "RUTA", "id": r.id, "texto": f"Ruta #{r.id} · {r.zona or '—'} · {len(r.stops)} parada(s)", "obj": r})
    elif area == "Mantenimiento":
        from ..models import WorkOrder
        for w in s.execute(select(WorkOrder).where(WorkOrder.fecha_programada == fecha,
                                                   WorkOrder.estado.in_(("PROGRAMADA", "ASIGNADA")))).scalars():
            out.append({"tipo": "TRABAJO", "id": w.id, "texto": f"Orden de trabajo #{w.id} · {w.titulo}", "obj": w})
    elif area == "Limpieza":
        from ..models import CleaningAssignment
        for c in s.execute(select(CleaningAssignment).where(CleaningAssignment.fecha == fecha)).scalars():
            if not c.checks:
                out.append({"tipo": "LIMPIEZA", "id": c.id, "texto": f"Limpieza · {c.zone.nombre if c.zone else ''} · "
                            f"{c.worker.nombre if c.worker else ''}", "obj": c})
    return out


def _campo(tipo):
    return {"PRODUCCION": "fecha_programada", "PICKING": "fecha", "RUTA": "fecha", "TRABAJO": "fecha_programada",
            "LIMPIEZA": "fecha"}[tipo]


def registrar(user, area, fecha, motivo, avisar=True):
    if area not in areas_de(user):
        raise BusinessError("Su perfil no registra días no laborables para esa área.")
    if fecha is None:
        raise BusinessError("Indique la fecha.")
    if fecha < date.today():
        raise BusinessError("No se registran días no laborables en fechas pasadas.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise BusinessError("Indique el motivo (p. ej. inventario, mantenimiento general, capacitación).")
    if es_no_laborable(area, fecha):
        raise BusinessError(f"{area} ya tiene registrado el {fecha:%d/%m/%Y} como no laborable.")
    d = AreaDayOff(area=area, fecha=fecha, motivo=motivo, user_id=user.id, replanificado=[])
    db().add(d)
    db().flush()
    n = len(afectados(area, fecha))
    if not avisar:
        audit(user, "DIA_NO_LABORABLE", "AreaDayOff", d.id, {"area": area, "fecha": fecha.isoformat(), "motivo": motivo})
        return d
    alerts.emit("DIA_NO_LABORABLE", f"{area} no labora el {fecha:%d/%m/%Y}",
                f"Motivo: {motivo}. " + (f"Hay {n} programación(es) de ese día por replanificar." if n else
                                          "No había nada programado ese día."),
                "AreaDayOff", d.id, creado_por=user, dedup_key=f"DIA_OFF:{area}:{fecha.isoformat()}")
    audit(user, "DIA_NO_LABORABLE", "AreaDayOff", d.id, {"area": area, "fecha": fecha.isoformat(), "motivo": motivo})
    return d


def registrar_varios(user, areas, fecha, motivo):
    """V33: una o varias áreas (o todas las que el perfil gestiona) no laboran la misma fecha. Se avisa a todas las
    áreas, no solo a las afectadas, para que nadie programe ni registre OV para ese día."""
    propias = areas_de(user)
    if not areas:
        raise BusinessError("Elija al menos un área (o «Todas las áreas»).")
    if "*" in areas:
        areas = propias
    creados, ya = [], []
    for a in areas:
        if a not in propias:
            raise BusinessError(f"Su perfil no registra días no laborables para {a}.")
        if fecha is not None and es_no_laborable(a, fecha):
            ya.append(a)
            continue
        creados.append(registrar(user, a, fecha, motivo, avisar=False))
    if not creados:
        raise BusinessError("Esas áreas ya tienen registrado ese día como no laborable.")
    nombres = ", ".join(d.area for d in creados)
    todas = set(d.area for d in creados) >= set(AREAS)
    bloquea = [a for a in (param("dias_no_laborables_bloquean_ov", ["Almacén", "Distribución"]) or []) if a in nombres]
    titulo = f"La empresa no labora el {fecha:%d/%m/%Y}" if todas else f"{nombres}: no labora(n) el {fecha:%d/%m/%Y}"
    alerts.emit("DIA_NO_LABORABLE", titulo,
                f"Motivo: {(motivo or '').strip()}. Áreas: {nombres}."
                + (f" No se pueden registrar OV con despacho ese día ({', '.join(bloquea)} no labora)." if bloquea else "")
                + " Lo programado se replanifica en Días no laborables.",
                "AreaDayOff", creados[0].id, creado_por=user,
                extra_roles=list(param("dias_no_laborables_avisar_roles", []) or []),
                dedup_key=f"DIA_OFF:{fecha.isoformat()}:{nombres}"[:120])
    return creados


def bloquea_ov(fecha):
    """V33: motivo si no se puede comprometer un despacho ese día (un área de despacho no labora), o None."""
    if fecha is None:
        return None
    areas = param("dias_no_laborables_bloquean_ov", ["Almacén", "Distribución"]) or []
    for d in db().execute(select(AreaDayOff).where(AreaDayOff.fecha == fecha, AreaDayOff.activo.is_(True),
                                                   AreaDayOff.area.in_(areas))).scalars():
        return f"El {fecha:%d/%m/%Y} {d.area} no labora ({d.motivo}): elija otra fecha de despacho."
    return None


def anular(user, d):
    if d.area not in areas_de(user):
        raise BusinessError("Su perfil no gestiona los días no laborables de esa área.")
    d.activo = False
    audit(user, "DIA_NO_LABORABLE_ANULADO", "AreaDayOff", d.id, {"area": d.area, "fecha": d.fecha.isoformat()})


def replanificar(user, d, destino=None, ids=None):
    """Mueve lo programado del día no laborable a «destino» (por defecto, el siguiente día hábil del área)."""
    if d.area not in areas_de(user):
        raise BusinessError("Su perfil no replanifica esa área.")
    destino = destino or siguiente_habil(d.area, d.fecha)
    from .calendar import day_factor
    if day_factor(destino) <= 0 or es_no_laborable(d.area, destino):
        raise BusinessError(f"El {destino:%d/%m/%Y} tampoco es día hábil para {d.area}.")
    movidos, riesgo = [], []
    for x in afectados(d.area, d.fecha):
        if ids and f"{x['tipo']}:{x['id']}" not in ids:
            continue
        obj = x["obj"]
        setattr(obj, _campo(x["tipo"]), destino)
        movidos.append({"tipo": x["tipo"], "id": x["id"], "texto": x["texto"], "de": d.fecha.isoformat(),
                        "a": destino.isoformat(), "user": user.nombre, "ts": now().isoformat(timespec="minutes")})
        ovs = [obj.order] if x["tipo"] == "PICKING" else ([st.order for st in obj.stops] if x["tipo"] == "RUTA" else [])
        for o in ovs:
            if o.fecha_compromiso and o.fecha_compromiso < destino:
                riesgo.append(o.numero)
    if not movidos:
        raise BusinessError("No hay nada por replanificar en ese día.")
    d.replanificado = list(d.replanificado or []) + movidos
    if riesgo:
        alerts.emit("DIA_NO_LABORABLE", f"Replanificación del {d.fecha:%d/%m}: OV con fecha comprometida en riesgo",
                    f"Al pasar lo de {d.area} al {destino:%d/%m/%Y}, estas OV quedan después de su fecha comprometida: "
                    f"{', '.join(sorted(set(riesgo)))}. Coordine con Comercial la nueva fecha con el cliente.",
                    "AreaDayOff", d.id, creado_por=user, dedup_key=f"DIA_OFF_RIESGO:{d.id}:{destino.isoformat()}")
    audit(user, "REPLANIFICACION", "AreaDayOff", d.id, {"a": destino.isoformat(), "movidos": len(movidos), "ov_en_riesgo": riesgo})
    return {"movidos": len(movidos), "destino": destino, "riesgo": sorted(set(riesgo))}


def proximos(desde=None):
    desde = desde or date.today() - timedelta(days=7)
    return list(db().execute(select(AreaDayOff).where(AreaDayOff.fecha >= desde, AreaDayOff.activo.is_(True))
                             .order_by(AreaDayOff.fecha, AreaDayOff.area)).scalars())
