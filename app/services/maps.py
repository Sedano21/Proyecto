"""Mapa de ruta, tiempo estimado y alertas de tráfico (observaciones al demo v0.5, 13-oct).

- Sin configuración: enlace a Google Maps con el origen (dirección de la empresa) y las paradas en orden, y un tiempo
  estimado aproximado (traslado base + tiempo por parada; parámetros propuestos). No usa tráfico.
- Con GOOGLE_MAPS_API_KEY en el servidor: mapa embebido, distancia y duración con tráfico (Distance Matrix,
  departure_time=now) y alerta RUTA_TRAFICO cuando el tráfico agrega más del umbral configurado o compromete una cita.
La clave se guarda solo como variable de entorno del servidor (no en la base ni en el repositorio).
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from . import alerts
from .core import audit, param

API = "https://maps.googleapis.com/maps/api/distancematrix/json"


def api_key():
    return os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()


def _addr(*partes):
    return ", ".join(p for p in partes if p) + ", Perú"


def origin():
    return _addr(*(param("empresa_direccion", []) or []))


def stops_addresses(route):
    return [_addr(st.order.direccion, st.order.distrito, st.order.provincia) for st in sorted(route.stops, key=lambda x: x.orden)]


def gmaps_link(route):
    dest = stops_addresses(route)
    if not dest:
        return ""
    q = {"api": "1", "origin": origin(), "destination": dest[-1], "travelmode": "driving"}
    if len(dest) > 1:
        q["waypoints"] = "|".join(dest[:-1])
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(q)


def embed_url(route):
    key = api_key()
    dest = stops_addresses(route)
    if not key or not dest:
        return ""
    q = {"key": key, "origin": origin(), "destination": dest[-1], "mode": "driving"}
    if len(dest) > 1:
        q["waypoints"] = "|".join(dest[:-1])
    return "https://www.google.com/maps/embed/v1/directions?" + urllib.parse.urlencode(q)


def _fetch(params, opener=None):
    url = API + "?" + urllib.parse.urlencode(params)
    with (opener or urllib.request.urlopen)(url, timeout=15) as r:
        return json.loads(r.read().decode())


def estimate(route, opener=None):
    """Tramos origen → parada 1 → … → última parada. Devuelve minutos sin y con tráfico, km y la fuente."""
    dest = stops_addresses(route)
    n = len(dest)
    por_parada = float(param("tiempo_por_parada_min", 30) or 30)
    if not n:
        return None
    if not api_key():
        base = float(param("tiempo_traslado_base_min", 45) or 45)
        return {"fuente": "estimación sin tráfico (configure el servicio de mapas para el cálculo real)",
                "min_sin_trafico": base * n + por_parada * n, "min_con_trafico": None, "km": None, "tramos": []}
    puntos = [origin()] + dest
    tramos, km, sin, con = [], 0.0, 0.0, 0.0
    for a, b in zip(puntos, puntos[1:]):
        data = _fetch({"origins": a, "destinations": b, "mode": "driving", "departure_time": "now", "language": "es",
                       "key": api_key()}, opener)
        el = data["rows"][0]["elements"][0]
        if el.get("status") != "OK":
            return {"fuente": f"servicio de mapas: {el.get('status')}", "min_sin_trafico": None, "min_con_trafico": None,
                    "km": None, "tramos": []}
        d = el["distance"]["value"] / 1000
        t0 = el["duration"]["value"] / 60
        t1 = el.get("duration_in_traffic", el["duration"])["value"] / 60
        tramos.append({"desde": a, "hasta": b, "km": round(d, 1), "min": round(t0), "min_trafico": round(t1)})
        km, sin, con = km + d, sin + t0, con + t1
    return {"fuente": "Google Maps (con tráfico)", "km": round(km, 1), "min_sin_trafico": round(sin + por_parada * n),
            "min_con_trafico": round(con + por_parada * n), "tramos": tramos}


def check_traffic(route, user=None, opener=None, ahora=None):
    """Consulta el tráfico y alerta si compromete la entrega (más del umbral o una cita que ya no se alcanza)."""
    est = estimate(route, opener)
    if not est or est.get("min_con_trafico") is None:
        return None
    ahora = ahora or datetime.now()
    route.distancia_km = est["km"]
    route.tiempo_estimado_min = est["min_con_trafico"]
    extra = est["min_con_trafico"] - est["min_sin_trafico"]
    umbral = float(param("umbral_trafico_pct", 25) or 25)
    riesgo = []
    if est["min_sin_trafico"] and extra / est["min_sin_trafico"] * 100 > umbral:
        riesgo.append(f"el tráfico agrega {extra:.0f} min (+{extra / est['min_sin_trafico'] * 100:.0f} %)")
    acumulado = 0.0
    por_parada = float(param("tiempo_por_parada_min", 30) or 30)
    for st, tr in zip(sorted(route.stops, key=lambda x: x.orden), est["tramos"]):
        acumulado += tr["min_trafico"]
        cita = (st.order.hora_cita or "")[:5]
        if len(cita) == 5 and cita[2] == ":" and route.fecha == ahora.date():
            llegada = ahora + timedelta(minutes=acumulado)
            limite = datetime.combine(route.fecha, datetime.strptime(cita, "%H:%M").time())
            if llegada > limite:
                riesgo.append(f"OV {st.order.numero} ({st.order.customer.nombre}) llegaría {llegada:%H:%M}, cita {cita}")
        acumulado += por_parada
    route.trafico = {"ts": ahora.isoformat(timespec="minutes"), "extra_min": round(extra), "riesgo": riesgo, **{
        k: est[k] for k in ("km", "min_sin_trafico", "min_con_trafico")}}
    key = f"TRAFICO:{route.id}:{ahora:%Y%m%d}"
    if riesgo:
        alerts.emit("RUTA_TRAFICO", f"Ruta #{route.id}: el tráfico puede comprometer la entrega",
                    "; ".join(riesgo) + ".", "Route", route.id, dedup_key=key, creado_por=user,
                    extra_users=[st.order.vendedor_id for st in route.stops if st.order.vendedor_id] or None)
    audit(user, "RUTA_TRAFICO_CONSULTADO", "Route", route.id, route.trafico)
    return route.trafico


def check_active_routes(hoy=None):
    """Tarea programada: rutas confirmadas o en ruta del día (solo con el servicio de mapas configurado)."""
    from sqlalchemy import select

    from ..db import db
    from ..models import Route
    if not api_key():
        return 0
    hoy = hoy or datetime.now().date()
    n = 0
    for r in db().execute(select(Route).where(Route.fecha == hoy, Route.estado.in_(("CONFIRMADA", "EN_RUTA")))).scalars():
        try:
            if check_traffic(r):
                n += 1
        except Exception:  # noqa: BLE001 – un fallo del servicio externo no detiene las demás tareas
            continue
    return n
