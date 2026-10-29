"""Mantenimiento integral (ronda UX del 24-oct-2026).

- Flota: plan de mantenimiento preventivo por unidad (frecuencia por kilometraje o días; vence lo que llegue primero) y
  mantenimiento correctivo (avería reportada → programada → en reparación → cerrada).
- Saneamiento y bioseguridad: bitácora de limpieza, desinfección, fumigación y mantenimiento de zonas físicas con su
  frecuencia, y control fitosanitario de las unidades vehiculares (fumigación para prevenir plagas como el gorgojo) con
  alerta de vencimiento.
Las frecuencias y los días de aviso son configurables; no se inventan valores de mantenimiento: los define cada plan.
"""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Breakdown, MaintenancePlan, SanitationLog, SanitationZone, Vehicle, VehicleMaintenance, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

ESTADOS_AVERIA = ["REPORTADA", "PROGRAMADA", "EN_REPARACION", "CERRADA"]
TIPOS_SANEAMIENTO = {"LIMPIEZA": "Limpieza", "DESINFECCION": "Desinfección", "FUMIGACION": "Fumigación",
                     "MANTENIMIENTO": "Mantenimiento de la zona"}


def _flota(user):
    if not has_perm(user, "mantenimiento.flota"):
        raise BusinessError("El mantenimiento de la flota lo registra Distribución / Logística.")


def _san(user):
    if not has_perm(user, "saneamiento.registrar"):
        raise BusinessError("La bitácora de saneamiento la registra Calidad.")


def _num(v):
    v = str(v if v is not None else "").replace(",", ".").strip()
    return float(v) if v else None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def _date(v):
    if isinstance(v, date) or v is None:
        return v
    return date.fromisoformat(v) if str(v).strip() else None


# ------------------------------------------------------------------ preventivo
def save_plan(user, vehicle, datos, plan=None):
    _flota(user)
    tarea = (datos.get("tarea") or "").strip()
    if not tarea:
        raise BusinessError("Indique la tarea (p. ej. cambio de aceite, revisión de frenos).")
    km, dias = _num(datos.get("cada_km")), _int(datos.get("cada_dias"))
    if not km and not dias:
        raise BusinessError("Indique la frecuencia: cada cuántos km, cada cuántos días o ambas.")
    if (km is not None and km <= 0) or (dias is not None and dias <= 0):
        raise BusinessError("La frecuencia debe ser mayor que cero.")
    if plan is None:
        plan = MaintenancePlan(vehicle_id=vehicle.id, tarea=tarea, user_id=user.id)
        db().add(plan)
    plan.tarea, plan.cada_km, plan.cada_dias = tarea, km, dias
    plan.ultimo_km = _num(datos.get("ultimo_km")) if datos.get("ultimo_km") not in (None, "") else plan.ultimo_km
    plan.ultima_fecha = _date(datos.get("ultima_fecha")) or plan.ultima_fecha or date.today()
    plan.activo = str(datos.get("activo", "1")) in ("1", "on", "true")
    db().flush()
    audit(user, "MANT_PLAN_GUARDADO", "MaintenancePlan", plan.id, {"placa": vehicle.placa, "tarea": tarea, "km": km, "dias": dias})
    return plan


def due(plan, hoy=None):
    """Próximo vencimiento del plan: por km y por fecha; estado VENCIDO / PROXIMO / AL_DIA."""
    hoy = hoy or date.today()
    v = plan.vehicle
    prox_km = (plan.ultimo_km or 0) + plan.cada_km if plan.cada_km and plan.ultimo_km is not None else None
    prox_fecha = plan.ultima_fecha + timedelta(days=plan.cada_dias) if plan.cada_dias and plan.ultima_fecha else None
    km_rest = prox_km - v.km_actual if prox_km is not None and v.km_actual is not None else None
    dias_rest = (prox_fecha - hoy).days if prox_fecha else None
    margen_km = float(param("margen_km_mantenimiento", 500) or 500)
    aviso = int(param("dias_aviso_mantenimiento", 7) or 7)
    if (km_rest is not None and km_rest <= 0) or (dias_rest is not None and dias_rest < 0):
        estado = "VENCIDO"
    elif (km_rest is not None and km_rest <= margen_km) or (dias_rest is not None and dias_rest <= aviso):
        estado = "PROXIMO"
    else:
        estado = "AL_DIA"
    return {"prox_km": prox_km, "prox_fecha": prox_fecha, "km_rest": km_rest, "dias_rest": dias_rest, "estado": estado}


def complete_plan(user, plan, fecha=None, km=None, costo=None, nota=""):
    """Registra el preventivo realizado: reinicia el contador y deja el historial en la ficha del vehículo."""
    from .fleet import add_maintenance
    fecha = _date(fecha) or date.today()
    km = _num(km)
    v = plan.vehicle
    if km is not None and v.km_actual is not None and km < v.km_actual - 1e-9:
        raise BusinessError(f"El kilometraje ({km:g}) es menor al último registrado ({v.km_actual:g}).")
    add_maintenance(user, v, fecha, "PREVENTIVO", km, f"{plan.tarea}. {nota}".strip(), _num(costo),
                    (km or v.km_actual or 0) + plan.cada_km if plan.cada_km and (km or v.km_actual) else None,
                    fecha + timedelta(days=plan.cada_dias) if plan.cada_dias else None)
    plan.ultima_fecha, plan.ultimo_km = fecha, km if km is not None else v.km_actual
    alerts.close_by_system(f"MANT_PREV:{plan.id}", "Mantenimiento realizado")
    audit(user, "MANT_PREVENTIVO_REALIZADO", "MaintenancePlan", plan.id, {"placa": v.placa, "km": km, "fecha": fecha})
    return plan


# ------------------------------------------------------------------ correctivo
def report_breakdown(user, vehicle, descripcion, severidad="MEDIA", km=None, foto=""):
    if not (has_perm(user, "mantenimiento.flota") or has_perm(user, "distribucion.entrega")
            or has_perm(user, "distribucion.conformidad")):
        raise BusinessError("Reportan averías Distribución y los choferes.")
    if not (descripcion or "").strip():
        raise BusinessError("Describa la avería.")
    severidad = (severidad or "MEDIA").upper()
    if severidad not in ("ALTA", "MEDIA", "BAJA"):
        raise BusinessError("Severidad no válida.")
    b = Breakdown(vehicle_id=vehicle.id, descripcion=descripcion.strip(), severidad=severidad, km=_num(km), foto=foto or "",
                  user_id=user.id, historial=[{"estado": "REPORTADA", "user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                                               "nota": descripcion.strip()}])
    db().add(b)
    db().flush()
    if severidad == "ALTA":  # una avería grave saca la unidad de servicio hasta cerrarla
        vehicle.disponible = False
    alerts.emit("MANT_CORRECTIVO", f"Avería {severidad.lower()} en {vehicle.placa}", descripcion.strip(), "Breakdown", b.id,
                prioridad="ALTA" if severidad == "ALTA" else None, dedup_key=f"AVERIA:{b.id}", creado_por=user)
    audit(user, "AVERIA_REPORTADA", "Breakdown", b.id, {"placa": vehicle.placa, "severidad": severidad})
    return b


def update_breakdown(user, b, estado, nota="", fecha_programada=None, taller="", costo=None):
    _flota(user)
    estado = (estado or "").upper()
    if estado not in ESTADOS_AVERIA:
        raise BusinessError("Estado no válido.")
    if b.estado == "CERRADA":
        raise BusinessError("La avería ya está cerrada.")
    if ESTADOS_AVERIA.index(estado) < ESTADOS_AVERIA.index(b.estado):
        raise BusinessError("La avería no puede volver a un estado anterior.")
    if estado == "PROGRAMADA" and not (fecha_programada or b.fecha_programada):
        raise BusinessError("Indique la fecha programada de la reparación.")
    if estado == "CERRADA" and not (nota or "").strip():
        raise BusinessError("Describa la reparación realizada para cerrar la avería.")
    b.fecha_programada = _date(fecha_programada) or b.fecha_programada
    b.taller = (taller or b.taller or "").strip()
    if costo not in (None, ""):
        b.costo = _num(costo)
    b.estado = estado
    b.historial = list(b.historial or []) + [{"estado": estado, "user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                                              "nota": (nota or "").strip()}]
    if estado == "CERRADA":
        b.solucion, b.cierre_ts = nota.strip(), now()
        db().add(VehicleMaintenance(vehicle_id=b.vehicle_id, fecha=date.today(), tipo="CORRECTIVO", km=b.km,
                                    descripcion=f"{b.descripcion} → {b.solucion}", costo=b.costo, user_id=user.id))
        if not db().execute(select(Breakdown).where(Breakdown.vehicle_id == b.vehicle_id, Breakdown.id != b.id,
                                                    Breakdown.severidad == "ALTA", Breakdown.estado != "CERRADA")).first():
            b.vehicle.disponible = True
        alerts.close_by_system(f"AVERIA:{b.id}", "Avería cerrada")
    audit(user, "AVERIA_ACTUALIZADA", "Breakdown", b.id, {"estado": estado, "nota": nota})
    return b


# ------------------------------------------------------------------ saneamiento y bioseguridad
def save_zone(user, datos, z=None):
    _san(user)
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise BusinessError("Indique el nombre de la zona.")
    if z is None:
        z = SanitationZone(nombre=nombre)
        db().add(z)
    z.nombre, z.area, z.almacen = nombre, (datos.get("area") or "").strip(), (datos.get("almacen") or "").strip()
    z.frecuencia_limpieza_dias = _int(datos.get("frecuencia_limpieza_dias"))
    z.frecuencia_fumigacion_dias = _int(datos.get("frecuencia_fumigacion_dias"))
    z.activo = str(datos.get("activo", "1")) in ("1", "on", "true")
    db().flush()
    audit(user, "ZONA_GUARDADA", "SanitationZone", z.id, {"nombre": nombre})
    return z


def log_sanitation(user, tipo, fecha=None, zone=None, vehicle=None, responsable="", producto="", certificado="", vence=None,
                   observacion="", evidencia=""):
    _san(user)
    tipo = (tipo or "").upper()
    if tipo not in TIPOS_SANEAMIENTO:
        raise BusinessError("Tipo de registro no válido.")
    if (zone is None) == (vehicle is None):
        raise BusinessError("Elija la zona o la unidad.")
    if vehicle is not None and tipo != "FUMIGACION":
        raise BusinessError("En las unidades se registra la fumigación (control fitosanitario).")
    fecha = _date(fecha) or date.today()
    if fecha > date.today():
        raise BusinessError("La fecha no puede ser futura.")
    if not (responsable or "").strip():
        raise BusinessError("Indique quién lo realizó (persona o empresa).")
    if tipo == "FUMIGACION" and not (producto or "").strip():
        raise BusinessError("Indique el producto utilizado en la fumigación.")
    vence = _date(vence)
    if vence is None:
        dias = None
        if vehicle is not None:
            dias = param("vigencia_fumigacion_unidad_dias")
        elif tipo == "FUMIGACION":
            dias = zone.frecuencia_fumigacion_dias
        elif tipo in ("LIMPIEZA", "DESINFECCION"):
            dias = zone.frecuencia_limpieza_dias
        vence = fecha + timedelta(days=int(dias)) if dias else None
    if vehicle is not None and vence is None:
        raise BusinessError("Indique la vigencia de la fumigación de la unidad (o configure vigencia_fumigacion_unidad_dias).")
    if vence is not None and vence < fecha:
        raise BusinessError("La vigencia no puede ser anterior a la fecha.")
    lg = SanitationLog(zone_id=zone.id if zone else None, vehicle_id=vehicle.id if vehicle else None, tipo=tipo, fecha=fecha,
                       responsable=responsable.strip(), producto=(producto or "").strip(), certificado=(certificado or "").strip(),
                       vence=vence, observacion=(observacion or "").strip(), evidencia=evidencia or "", user_id=user.id)
    db().add(lg)
    db().flush()
    key = f"SAN:V{vehicle.id}" if vehicle else f"SAN:Z{zone.id}:{'LIMPIEZA' if tipo == 'DESINFECCION' else tipo}"
    alerts.close_by_system(key, "Registro realizado")
    audit(user, "SANEAMIENTO_REGISTRADO", "SanitationLog", lg.id,
          {"tipo": tipo, "zona": zone.nombre if zone else None, "placa": vehicle.placa if vehicle else None, "vence": vence})
    return lg


def _last(zone=None, vehicle=None, tipos=None):
    q = select(SanitationLog)
    q = q.where(SanitationLog.zone_id == zone.id) if zone is not None else q.where(SanitationLog.vehicle_id == vehicle.id)
    if tipos:
        q = q.where(SanitationLog.tipo.in_(tipos))
    return db().execute(q.order_by(SanitationLog.fecha.desc(), SanitationLog.id.desc())).scalars().first()


def _estado(vence, hoy):
    if vence is None:
        return "SIN_REGISTRO", None
    d = (vence - hoy).days
    aviso = int(param("dias_aviso_saneamiento", 3) or 3)
    return ("VENCIDO" if d < 0 else "PROXIMO" if d <= aviso else "AL_DIA"), d


def zone_status(zone, hoy=None):
    hoy = hoy or date.today()
    out = {}
    for clave, tipos, freq in (("limpieza", ("LIMPIEZA", "DESINFECCION"), zone.frecuencia_limpieza_dias),
                               ("fumigacion", ("FUMIGACION",), zone.frecuencia_fumigacion_dias)):
        lg = _last(zone=zone, tipos=tipos)
        vence = lg.vence if lg and lg.vence else (lg.fecha + timedelta(days=freq) if lg and freq else None)
        est, dias = _estado(vence, hoy)
        if lg is None and freq:
            est = "VENCIDO"
        out[clave] = {"ultimo": lg, "vence": vence, "estado": est if freq or lg else "NO_APLICA", "dias": dias}
    return out


def vehicle_fumigation(vehicle, hoy=None):
    hoy = hoy or date.today()
    lg = _last(vehicle=vehicle, tipos=("FUMIGACION",))
    est, dias = _estado(lg.vence if lg else None, hoy)
    return {"ultimo": lg, "vence": lg.vence if lg else None, "estado": est, "dias": dias}


def board(hoy=None):
    hoy = hoy or date.today()
    vehs = list(db().execute(select(Vehicle).order_by(Vehicle.propio.desc(), Vehicle.placa)).scalars())
    planes = list(db().execute(select(MaintenancePlan).where(MaintenancePlan.activo.is_(True))
                               .order_by(MaintenancePlan.vehicle_id)).scalars())
    averias = list(db().execute(select(Breakdown).order_by(Breakdown.estado == "CERRADA", Breakdown.ts.desc()).limit(100)).scalars())
    zonas = list(db().execute(select(SanitationZone).where(SanitationZone.activo.is_(True)).order_by(SanitationZone.area,
                                                                                                       SanitationZone.nombre)).scalars())
    bitacora = list(db().execute(select(SanitationLog).order_by(SanitationLog.fecha.desc(), SanitationLog.id.desc()).limit(60)).scalars())
    return {"vehiculos": vehs, "planes": [(p, due(p, hoy)) for p in planes], "averias": averias,
            "zonas": [(z, zone_status(z, hoy)) for z in zonas], "fumigacion": [(v, vehicle_fumigation(v, hoy)) for v in vehs],
            "bitacora": bitacora}


def check_alerts(hoy=None):
    """Tarea programada: preventivos vencidos o próximos, zonas sin limpieza o fumigación al día y fumigación de unidades."""
    hoy = hoy or date.today()
    n = 0
    for p in db().execute(select(MaintenancePlan).where(MaintenancePlan.activo.is_(True))).scalars():
        d = due(p, hoy)
        if d["estado"] in ("VENCIDO", "PROXIMO"):
            det = []
            if d["prox_km"] is not None:
                det.append(f"a los {d['prox_km']:,.0f} km (actual {p.vehicle.km_actual or 0:,.0f})")
            if d["prox_fecha"]:
                det.append(f"el {d['prox_fecha']:%d/%m/%Y}")
            alerts.emit("MANT_PREVENTIVO", f"Preventivo {'vencido' if d['estado'] == 'VENCIDO' else 'próximo'}: {p.tarea} · "
                        f"{p.vehicle.placa}", "Programado " + " o ".join(det) + ".", "MaintenancePlan", p.id,
                        prioridad="ALTA" if d["estado"] == "VENCIDO" else None, dedup_key=f"MANT_PREV:{p.id}")
            n += 1
    for z in db().execute(select(SanitationZone).where(SanitationZone.activo.is_(True))).scalars():
        st = zone_status(z, hoy)
        for clave, tipo in (("limpieza", "LIMPIEZA"), ("fumigacion", "FUMIGACION")):
            x = st[clave]
            if x["estado"] in ("VENCIDO", "PROXIMO"):
                alerts.emit("SANEAMIENTO_VENCIDO", f"{TIPOS_SANEAMIENTO[tipo]} {'vencida' if x['estado'] == 'VENCIDO' else 'próxima'}: "
                            f"{z.nombre}", f"Zona {z.nombre} ({z.area}). " + (f"Vence el {x['vence']:%d/%m/%Y}." if x["vence"]
                                                                             else "Sin registro previo."),
                            "SanitationZone", z.id, prioridad="ALTA" if x["estado"] == "VENCIDO" else None,
                            dedup_key=f"SAN:Z{z.id}:{tipo}")
                n += 1
    for v in db().execute(select(Vehicle)).scalars():
        x = vehicle_fumigation(v, hoy)
        if x["estado"] in ("VENCIDO", "PROXIMO") or (x["estado"] == "SIN_REGISTRO" and v.propio
                                                     and param("vigencia_fumigacion_unidad_dias")):
            alerts.emit("FUMIGACION_UNIDAD", f"Fumigación de la unidad {v.placa} "
                        f"{'vencida' if x['estado'] == 'VENCIDO' else 'por vencer' if x['estado'] == 'PROXIMO' else 'sin registrar'}",
                        "Control fitosanitario (prevención de gorgojo) de la unidad que transporta producto." +
                        (f" Vence el {x['vence']:%d/%m/%Y}." if x["vence"] else ""), "Vehicle", v.id,
                        prioridad="ALTA" if x["estado"] == "VENCIDO" else None, dedup_key=f"SAN:V{v.id}")
            n += 1
    return n


# ------------------------------------------------------------------ V12: documentos e incidencias con el taller
def attach_document(user, obj, tipo, numero="", archivo=""):
    """Informe del taller o factura de un mantenimiento preventivo (VehicleMaintenance) o correctivo (Breakdown).
    La factura la puede registrar también Compras."""
    tipo = (tipo or "").upper()
    if tipo not in ("INFORME", "FACTURA"):
        raise BusinessError("Adjunte el informe o la factura.")
    if tipo == "FACTURA" and not (has_perm(user, "mantenimiento.factura") or has_perm(user, "mantenimiento.flota")):
        raise BusinessError("La factura la registran Distribución o Compras.")
    if tipo == "INFORME" and not (has_perm(user, "mantenimiento.flota") or has_perm(user, "distribucion.flota")):
        raise BusinessError("El informe lo adjunta Distribución.")
    if not archivo:
        raise BusinessError("Adjunte el archivo.")
    if tipo == "FACTURA" and not (numero or "").strip():
        raise BusinessError("Indique el número de la factura.")
    obj.documentos = list(obj.documentos or []) + [{"tipo": tipo, "numero": (numero or "").strip(), "archivo": archivo,
                                                    "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]
    audit(user, f"MANT_{tipo}", type(obj).__name__, obj.id, {"numero": numero})
    return obj


def workshop_incident(user, obj, motivo, dias_fuera=None, detalle="", taller=""):
    """Incidencia con el taller: motivo, tiempo del vehículo fuera de servicio y detalle."""
    if not (has_perm(user, "mantenimiento.flota") or has_perm(user, "distribucion.flota")):
        raise BusinessError("Registra la incidencia con el taller Distribución.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo de la incidencia con el taller.")
    d = _num(dias_fuera)
    if d is not None and d < 0:
        raise BusinessError("El tiempo fuera de servicio no puede ser negativo.")
    obj.incidencias_taller = list(obj.incidencias_taller or []) + [{
        "motivo": motivo.strip(), "dias_fuera": d, "detalle": (detalle or "").strip(),
        "taller": (taller or getattr(obj, "taller", "") or "").strip(), "user": user.nombre,
        "ts": now().isoformat(timespec="minutes")}]
    audit(user, "MANT_INCIDENCIA_TALLER", type(obj).__name__, obj.id, {"motivo": motivo, "dias_fuera": d})
    return obj
