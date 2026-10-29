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


def register(user, route, momento, valores, km=None, observaciones=""):
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
                         nn_fallidos=nn, registrado_por=user.id)
    db().add(c)
    db().flush()
    malos = [item for code, zona, item, _ in items() if vals[code] == "M"]
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
        alerts.emit("CHECKLIST_OBSERVADO", f"Seguridad observó el checklist de {c.momento.lower()}: {v.placa if v else ''}",
                    nota, "Route", c.route_id, prioridad="ALTA", dedup_key=f"CHK_SEG:{c.id}", creado_por=user)
    audit(user, "CHECKLIST_VALIDADO" if aprobar else "CHECKLIST_OBSERVADO", "Route", c.route_id,
          {"momento": c.momento, "km": km, "nota": nota})
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
