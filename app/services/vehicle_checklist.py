"""Checklist de inspección vehicular CP-OPE-004 a la salida y al retorno (V12, 29-oct-2026).

- El chofer (o Distribución por encargo de un chofer sin cuenta) marca cada ítem B (bien), M (mal) o NA (no aplica),
  el kilometraje y las observaciones de choques o raspaduras.
- Seguridad valida lo que subió el chofer y registra el kilometraje con el que sale y con el que vuelve el vehículo.
- Un punto NN (no negociable) en «M» impide la salida hasta corregirlo.
- Si hay ítems en «M» u observaciones, se alerta al Coordinador y al Asistente de Distribución con el enlace a la ficha.
- El checklist de retorno no se puede registrar mientras falte el paso 2 de las incidencias de la ruta (devoluciones,
  entregas parciales y cancelaciones).
"""
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import Incident, Route, VehicleChecklist, now
from . import alerts
from .core import BusinessError, audit, has_perm

VALORES = ("B", "M", "NA")


def items():
    from ..catalogs import CHECKLIST_VEHICULAR
    return CHECKLIST_VEHICULAR


def zonas():
    out = {}
    for code, zona, item, nn in items():
        out.setdefault(zona, []).append((code, item, nn))
    return out


def of_route(route, momento):
    return db().execute(select(VehicleChecklist).where(VehicleChecklist.route_id == route.id,
                                                       VehicleChecklist.momento == momento)
                        .order_by(VehicleChecklist.id.desc())).scalars().first()


def _es_chofer(route, user):
    return route.driver is not None and route.driver.user_id == user.id


def pending_part2(route):
    """Incidencias de la ruta que requieren el paso 2 (lo que realmente vuelve) y aún no lo tienen."""
    from .incidents_flow import needs_part2
    rows = db().execute(select(Incident).where(Incident.route_id == route.id)).scalars()
    stops = {st.id for st in route.stops}
    otros = db().execute(select(Incident).where(Incident.stop_id.in_(stops or {-1}))).scalars()
    vistos, out = set(), []
    for i in list(rows) + list(otros):
        if i.id not in vistos and needs_part2(i) and not (i.parte2 or {}).get("ts"):
            vistos.add(i.id)
            out.append(i)
    return out


def parse_marks(raw):
    """V18: marcas del dibujo del vehículo (JSON [{x, y, nota}]); cada marca necesita su nota."""
    import json
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else list(raw)
    except ValueError:
        raise BusinessError("Las marcas del vehículo no son válidas.")
    out = []
    for m in data[:30]:
        try:
            x, y = float(m.get("x")), float(m.get("y"))
        except (TypeError, ValueError, AttributeError):
            continue
        parte = str(m.get("parte") or "").strip()[:60]  # V22: parte del vehículo elegida sobre su imagen
        nota = str(m.get("nota") or "").strip()[:160]
        if not nota and not parte:
            raise BusinessError("Describa cada punto marcado en el dibujo del vehículo (qué defecto u observación hay).")
        marca = {"x": round(x, 1), "y": round(y, 1), "nota": nota or "falla"}
        if parte:
            marca["parte"] = parte
        if m.get("vista") not in (None, ""):
            try:
                marca["vista"] = int(m.get("vista"))
            except (TypeError, ValueError):
                pass
        out.append(marca)
    return out


def register(user, route, momento, valores, km=None, observaciones="", marcas=None):
    momento = (momento or "").upper()
    if momento not in ("SALIDA", "RETORNO"):
        raise BusinessError("Indique si es el checklist de salida o de retorno.")
    if not (has_perm(user, "distribucion.checklist") and (_es_chofer(route, user) or has_perm(user, "distribucion.programar"))):
        raise BusinessError("El checklist lo registra el chofer de la ruta (o Distribución por encargo).")
    if route.vehicle is None:
        raise BusinessError("La ruta no tiene vehículo asignado.")
    if momento == "RETORNO":
        if route.estado not in ("EN_RUTA", "CERRADA"):
            raise BusinessError("El checklist de retorno se registra cuando el vehículo vuelve de la ruta.")
        faltan = pending_part2(route)
        if faltan:
            raise BusinessError("Antes de terminar el checklist de retorno complete el paso 2 de las incidencias: "
                                + ", ".join(f"#{i.id}" for i in faltan) + " (devoluciones, entregas parciales o cancelaciones).")
    vals = {}
    falt = []
    for code, zona, item, nn in items():
        v = (valores.get(code) or "").upper()
        if v not in VALORES:
            falt.append(item)
        vals[code] = v
    if falt:
        raise BusinessError(f"Marque B, M o NA en todos los ítems (faltan {len(falt)}: {', '.join(falt[:4])}…).")
    try:
        km = float(km) if km not in (None, "") else None
    except ValueError:
        raise BusinessError("Kilometraje inválido.")
    if km is None:
        raise BusinessError("Indique el kilometraje.")
    nn = [item for code, zona, item, es_nn in items() if es_nn and vals[code] == "M"]
    c = VehicleChecklist(vehicle_id=route.vehicle_id, route_id=route.id, momento=momento, fecha=date.today(),
                         driver_id=route.driver_id, items=vals, observaciones=(observaciones or "").strip(), km=km,
                         nn_fallidos=nn, registrado_por=user.id, marcas=parse_marks(marcas))
    db().add(c)
    db().flush()
    malos = [item for code, zona, item, _ in items() if vals[code] == "M"]
    if c.marcas:  # V18: las marcas del dibujo cuentan como observaciones
        c.observaciones = (c.observaciones + "\n" if c.observaciones else "") + "; ".join(
            f"Punto {i + 1}: {m['nota']}" for i, m in enumerate(c.marcas))
    if malos or c.observaciones:
        alerts.emit("CHECKLIST_OBSERVADO", f"Checklist de {momento.lower()} con observaciones: {route.vehicle.placa}",
                    ("Puntos NN en mal estado (no puede salir): " + ", ".join(nn) + ". " if nn else "")
                    + (f"En mal estado: {', '.join(malos)}. " if malos else "")
                    + (f"Observaciones: {c.observaciones}" if c.observaciones else ""),
                    "Route", route.id, prioridad="ALTA" if nn else "MEDIA", dedup_key=f"CHK:{c.id}", creado_por=user)
    audit(user, "CHECKLIST_VEHICULAR", "Route", route.id, {"momento": momento, "malos": malos, "nn": nn, "km": km})
    return c


def validate(user, c, aprobar, km_seguridad=None, nota=""):
    """Seguridad valida el checklist del chofer y registra el kilometraje (salida o retorno)."""
    if not has_perm(user, "distribucion.checklist_validar"):
        raise BusinessError("El checklist lo valida Seguridad.")
    if c.estado != "REGISTRADO":
        raise BusinessError("El checklist ya fue revisado.")
    try:
        km = float(km_seguridad) if km_seguridad not in (None, "") else None
    except ValueError:
        raise BusinessError("Kilometraje inválido.")
    if km is None:
        raise BusinessError("Registre el kilometraje que ve en el tablero.")
    if not aprobar and not (nota or "").strip():
        raise BusinessError("Indique qué observa Seguridad.")
    r = c.route
    if c.route_id is None and c.momento == "FIN_DIA":  # V27: el final del día no puede ser menor que el inicio
        ini = daily_of(c.vehicle_id, c.driver_id, c.fecha, "INICIO_DIA")
        if ini is not None and ini.km_seguridad is not None and km < ini.km_seguridad:
            raise BusinessError("El kilometraje del fin del día no puede ser menor al del inicio.")
    if c.momento == "RETORNO" and r is not None and r.km_salida is not None and km < r.km_salida:
        raise BusinessError("El kilometraje de retorno no puede ser menor al de salida.")
    c.estado = "VALIDADO" if aprobar else "OBSERVADO"
    c.validado_por, c.validado_ts, c.km_seguridad, c.nota_seguridad = user.id, now(), km, (nota or "").strip()
    if r is not None:
        if c.momento == "SALIDA":
            r.km_salida = km
        else:
            r.km_retorno = km
    v = c.vehicle
    if v is not None and (v.km_actual is None or km > v.km_actual):
        v.km_actual = km
    if not aprobar:
        alerts.emit("CHECKLIST_OBSERVADO", f"Seguridad observó el checklist de {c.momento.lower().replace('_', ' ')}: {v.placa if v else ''}",
                    nota, "Route" if c.route_id else "Vehicle", c.route_id or c.vehicle_id, prioridad="ALTA",
                    dedup_key=f"CHK_SEG:{c.id}", creado_por=user)
    audit(user, "CHECKLIST_VALIDADO" if aprobar else "CHECKLIST_OBSERVADO", "Route" if c.route_id else "Vehicle",
          c.route_id or c.vehicle_id, {"momento": c.momento, "km": km, "nota": nota})
    return c


def can_depart(route):
    """None si la ruta puede salir; si no, el motivo (se usa al confirmar la salida)."""
    if route.vehicle is None or not route.vehicle.propio:
        return None  # el checklist es de la flota propia
    c = of_route(route, "SALIDA")
    if c is None:
        return "Falta el checklist vehicular de salida del chofer."
    if c.nn_fallidos:
        return "Checklist de salida con puntos NO NEGOCIABLES en mal estado: " + ", ".join(c.nn_fallidos) + "."
    if c.estado != "VALIDADO":
        return "Seguridad aún no valida el checklist de salida (ni registra el kilometraje)."
    return None


def can_close_return(route):
    if route.vehicle is None or not route.vehicle.propio:
        return None
    c = of_route(route, "RETORNO")
    if c is None:
        return "Falta el checklist vehicular de retorno."
    if c.estado != "VALIDADO":
        return "Seguridad aún no valida el checklist de retorno."
    return None


def driver_checklists(user, hoy=None):
    """V25 (08-nov-2026): rutas del chofer (de hoy en adelante y las que siguen en curso) con el estado de sus checklists
    de salida y retorno, para registrarlos desde su perfil («Mis entregas»)."""
    from datetime import date as _date
    from ..models import Driver, Route
    hoy = hoy or _date.today()
    ids = [d.id for d in db().execute(select(Driver).where(Driver.user_id == user.id)).scalars()]
    if not ids:
        return []
    q = select(Route).where(Route.driver_id.in_(ids), Route.vehicle_id.is_not(None),
                            ((Route.fecha >= hoy) & Route.estado.in_(("PROPUESTA", "CONFIRMADA", "EN_RUTA")))
                            | (Route.estado == "EN_RUTA")).order_by(Route.fecha, Route.id)
    out = []
    for r in db().execute(q).scalars():
        sal, ret = of_route(r, "SALIDA"), of_route(r, "RETORNO")
        out.append({"r": r, "salida": sal, "retorno": ret, "puede_retorno": r.estado in ("EN_RUTA", "CERRADA"),
                    "pendiente": (sal is None and r.estado != "EN_RUTA") or (r.estado == "EN_RUTA" and ret is None)})
    return out


# ------------------------------------------------------------------ V27 (11-nov-2026): checklist diario por vehículo
MOMENTOS_DIA = {"INICIO_DIA": "Inicio del día", "FIN_DIA": "Fin del día"}


def driver_of(user):
    from ..models import Driver
    d = db().execute(select(Driver).where(Driver.user_id == user.id)).scalars().first()
    if d is None and user.role_code == "CONDUCTOR":  # V28: el usuario conductor tiene su ficha sin pasos extra
        from .fleet import sync_conductor_users
        sync_conductor_users()
        d = db().execute(select(Driver).where(Driver.user_id == user.id)).scalars().first()
    return d


def daily_of(vehicle_id, driver_id, fecha, momento):
    return db().execute(select(VehicleChecklist).where(
        VehicleChecklist.vehicle_id == vehicle_id, VehicleChecklist.driver_id == driver_id, VehicleChecklist.fecha == fecha,
        VehicleChecklist.momento == momento, VehicleChecklist.route_id.is_(None)).order_by(VehicleChecklist.id.desc())).scalars().first()


def register_daily(user, vehicle, momento, valores, km=None, observaciones="", marcas=None, foto_adelante="", foto_atras="",
                   driver=None, fecha=None):
    """Checklist de inspección vehicular CP-OPE-004 al comienzo y al final del día, por vehículo. Un conductor puede
    manejar varios vehículos el mismo día: hace el de inicio y el de fin de cada uno. Fotos de adelante y de atrás."""
    from ..models import Driver
    momento = (momento or "").upper()
    if momento not in MOMENTOS_DIA:
        raise BusinessError("Indique si es el checklist del inicio o del fin del día.")
    if not has_perm(user, "distribucion.checklist"):
        raise BusinessError("El checklist lo registra el conductor.")
    driver = driver or driver_of(user)
    if driver is None:
        raise BusinessError("Su usuario no está vinculado a un conductor (Distribución → Flota y conductores).")
    if driver.user_id != user.id and not has_perm(user, "distribucion.programar"):
        raise BusinessError("Cada conductor registra su propio checklist.")
    if vehicle is None:
        raise BusinessError("Elija el vehículo.")
    fecha = fecha or date.today()
    if not foto_adelante or not foto_atras:
        raise BusinessError("Tome la foto de adelante y la de atrás del vehículo.")
    if daily_of(vehicle.id, driver.id, fecha, momento) is not None:
        raise BusinessError(f"Ya registró el checklist de {MOMENTOS_DIA[momento].lower()} de {vehicle.placa} hoy.")
    inicio = daily_of(vehicle.id, driver.id, fecha, "INICIO_DIA")
    if momento == "FIN_DIA" and inicio is None:
        raise BusinessError(f"Primero registre el checklist del inicio del día de {vehicle.placa}.")
    vals, falt = {}, []
    for code, zona, item, nn in items():
        v = (valores.get(code) or "").upper()
        if v not in VALORES:
            falt.append(item)
        vals[code] = v
    if falt:
        raise BusinessError(f"Marque B, M o NA en todos los ítems (faltan {len(falt)}: {', '.join(falt[:4])}…).")
    try:
        km = float(km) if km not in (None, "") else None
    except ValueError:
        raise BusinessError("Kilometraje inválido.") from None
    if km is None:
        raise BusinessError("Indique el kilometraje.")
    if momento == "FIN_DIA" and inicio.km is not None and km < inicio.km:
        raise BusinessError(f"El kilometraje final ({km:g}) no puede ser menor al del inicio del día ({inicio.km:g}).")
    nn = [item for code, zona, item, es_nn in items() if es_nn and vals[code] == "M"]
    c = VehicleChecklist(vehicle_id=vehicle.id, route_id=None, momento=momento, fecha=fecha, driver_id=driver.id, items=vals,
                         observaciones=(observaciones or "").strip(), km=km, nn_fallidos=nn, registrado_por=user.id,
                         marcas=parse_marks(marcas), fotos={"adelante": foto_adelante, "atras": foto_atras})
    db().add(c)
    db().flush()
    if c.marcas:
        c.observaciones = (c.observaciones + "\n" if c.observaciones else "") + "; ".join(
            f"Punto {i + 1}: {m['nota']}" for i, m in enumerate(c.marcas))
    malos = [item for code, zona, item, _ in items() if vals[code] == "M"]
    if malos or c.observaciones:
        alerts.emit("CHECKLIST_OBSERVADO", f"Checklist {MOMENTOS_DIA[momento].lower()} con observaciones: {vehicle.placa}",
                    ("Puntos NN en mal estado (no debe movilizarse): " + ", ".join(nn) + ". " if nn else "")
                    + (f"En mal estado: {', '.join(malos)}. " if malos else "")
                    + (f"Observaciones: {c.observaciones}" if c.observaciones else "") + f" Conductor: {driver.nombre}.",
                    "Vehicle", vehicle.id, prioridad="ALTA" if nn else "MEDIA", dedup_key=f"CHK:{c.id}", creado_por=user)
    if vehicle.km_actual is None or km > vehicle.km_actual:
        vehicle.km_actual = km
    audit(user, "CHECKLIST_DIARIO", "Vehicle", vehicle.id, {"momento": momento, "conductor": driver.nombre, "km": km,
                                                             "malos": malos, "nn": nn})
    return c


def daily_status(user, fecha=None):
    """Vehículos del conductor hoy: los que ya inspeccionó (inicio/fin) y los propios disponibles para empezar."""
    from ..models import Vehicle
    fecha = fecha or date.today()
    driver = driver_of(user)
    if driver is None:
        return {"driver": None, "filas": [], "vehiculos": []}
    hechos = list(db().execute(select(VehicleChecklist).where(VehicleChecklist.driver_id == driver.id,
                                                              VehicleChecklist.fecha == fecha,
                                                              VehicleChecklist.route_id.is_(None))).scalars())
    por_v = {}
    for c in hechos:
        por_v.setdefault(c.vehicle_id, {})[c.momento] = c
    filas = [{"vehicle": db().get(Vehicle, vid), "inicio": m.get("INICIO_DIA"), "fin": m.get("FIN_DIA")} for vid, m in por_v.items()]
    vehiculos = list(db().execute(select(Vehicle).where(Vehicle.propio.is_(True), Vehicle.disponible.is_(True))
                                  .order_by(Vehicle.placa)).scalars())
    return {"driver": driver, "filas": filas, "vehiculos": vehiculos}
