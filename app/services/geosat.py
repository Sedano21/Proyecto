"""Integración con GEOSATELITAL (rastreo de unidades), ronda UX del 24-oct-2026.

El servicio del proveedor se conecta solo cuando Sistemas lo configura; sin configuración no se hace ninguna conexión:
- GEOSAT_API_URL (variable de entorno del servidor): servicio que devuelve en JSON las posiciones de las unidades.
- GEOSAT_TOKEN (variable de entorno): credencial del proveedor; se envía como «Authorization: Bearer …». Si el proveedor
  da cuenta y contraseña en lugar de un token: GEOSAT_USER y GEOSAT_PASSWORD (autenticación básica). Nunca se guardan en
  la base ni en el repositorio.
- Parámetro geosatelital_url_panel: dirección del panel web del proveedor para mostrarlo embebido (si lo permite).
El formato exacto de la respuesta del proveedor está pendiente de su documentación: se reconocen los nombres de campo más
comunes (placa / plate, lat / latitude, lng / lon / longitude, velocidad / speed, fecha / timestamp, motor / ignition).
"""
import json
import os
import urllib.request
from datetime import datetime

from .core import param

ALIAS = {"placa": ("placa", "plate", "patente", "unidad", "vehiculo", "name"),
         "lat": ("lat", "latitud", "latitude"), "lng": ("lng", "lon", "long", "longitud", "longitude"),
         "velocidad": ("velocidad", "speed", "vel"), "fecha": ("fecha", "timestamp", "datetime", "gps_time", "time"),
         "motor": ("motor", "ignition", "encendido"), "direccion": ("direccion", "address", "ubicacion")}


def api_url():
    return os.environ.get("GEOSAT_API_URL", "").strip()


def panel_url():
    return (param("geosatelital_url_panel", "") or "").strip()


def configured():
    return bool(api_url() or panel_url())


def _pick(d, key):
    for k in ALIAS[key]:
        for kk in (k, k.upper(), k.capitalize()):
            if kk in d and d[kk] not in (None, ""):
                return d[kk]
    return None


def normalize(data):
    """Convierte la respuesta del proveedor en [{placa, lat, lng, velocidad, fecha, motor, direccion}]."""
    if isinstance(data, dict):
        for k in ("data", "unidades", "vehicles", "items", "result", "positions"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            data = [data]
    out = []
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict):
            continue
        placa = str(_pick(d, "placa") or "").strip().upper().replace(" ", "")
        try:
            lat, lng = float(_pick(d, "lat")), float(_pick(d, "lng"))
        except (TypeError, ValueError):
            continue
        vel = _pick(d, "velocidad")
        try:
            vel = float(vel) if vel is not None else None
        except (TypeError, ValueError):
            vel = None
        out.append({"placa": placa, "lat": lat, "lng": lng, "velocidad": vel, "fecha": str(_pick(d, "fecha") or ""),
                    "motor": _pick(d, "motor"), "direccion": str(_pick(d, "direccion") or ""),
                    "en_movimiento": bool(vel and vel > 3)})
    return out


def positions(opener=None):
    """Posiciones actuales: None si no está configurado; lanza RuntimeError con el motivo si el proveedor falla."""
    url = api_url()
    if not url:
        return None
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    token = os.environ.get("GEOSAT_TOKEN", "").strip()
    usuario, clave = os.environ.get("GEOSAT_USER", "").strip(), os.environ.get("GEOSAT_PASSWORD", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    elif usuario and clave:  # cuenta del proveedor (autenticación básica) si su servicio la acepta
        import base64
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode())
    try:
        with (opener or urllib.request.urlopen)(req, timeout=15) as r:
            return normalize(json.loads(r.read().decode("utf-8")))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"No se pudo consultar GEOSATELITAL: {e}") from e


def tracking_board(vehicles, opener=None):
    """Tablero: cada unidad de la flota con su última posición (si el proveedor la informa)."""
    error = None
    try:
        pos = positions(opener)
    except RuntimeError as e:
        pos, error = [], str(e)
    por_placa = {p["placa"]: p for p in (pos or [])}
    filas = [{"v": v, "pos": por_placa.get(v.placa.replace(" ", "").upper())} for v in vehicles]
    return {"filas": filas, "configurado": configured(), "api": bool(api_url()), "panel": panel_url(), "error": error,
            "consulta": datetime.now(), "sin_flota": [p for p in (pos or []) if p["placa"] not in
                                                     {v.placa.replace(" ", "").upper() for v in vehicles}]}


def set_vehicle_link(vehicle, user, link, horas=None):
    """V7: enlace de seguimiento de la unidad que genera el panel de GEOSATELITAL («compartir ubicación»). Sin API del
    proveedor es la forma de ver cada unidad desde el módulo. Solo enlaces https; no se guardan usuario ni contraseña."""
    from .core import BusinessError, audit, has_perm
    if not has_perm(user, "distribucion.programar"):
        raise BusinessError("El enlace de seguimiento lo registra Distribución.")
    link = (link or "").strip()
    if link and not link.lower().startswith("https://"):
        raise BusinessError("El enlace debe empezar con https://")
    if link and ("password=" in link.lower() or "clave=" in link.lower() or "@" in link.split("/")[2]):
        raise BusinessError("No registre enlaces con usuario o contraseña: use el enlace de «compartir ubicación».")
    vehicle.geosat_link = link[:500]
    # V8 (D03): el enlace del proveedor dura entre 15 minutos y 24 horas
    from datetime import timedelta
    from ..models import now
    try:
        h = float(horas) if horas not in (None, "") else float(param("geosatelital_link_horas", 24) or 24)
    except ValueError:
        raise BusinessError("Vigencia inválida.")
    if link and not (0.25 <= h <= 24):
        raise BusinessError("La vigencia del enlace va de 15 minutos (0.25 h) a 24 horas.")
    vehicle.geosat_link_vence = now() + timedelta(hours=h) if link else None
    audit(user, "VEHICULO_GEOSAT_LINK", "Vehicle", vehicle.placa, {"link": bool(link), "horas": h if link else None})


def link_status(vehicle, ahora=None):
    """(vigente: bool, texto) del enlace de seguimiento de la unidad."""
    from ..models import now
    if not vehicle.geosat_link:
        return False, "Sin enlace"
    if vehicle.geosat_link_vence is None:
        return True, "Vigencia no registrada"
    resto = (vehicle.geosat_link_vence - (ahora or now())).total_seconds()
    if resto <= 0:
        return False, f"Venció el {vehicle.geosat_link_vence:%d/%m %H:%M}: genere uno nuevo en GEOSATELITAL"
    return True, f"Vigente hasta {vehicle.geosat_link_vence:%d/%m %H:%M} ({int(resto // 3600)} h {int(resto % 3600 // 60)} min)"
