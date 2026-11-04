"""V20: límite de peticiones contra abusos (un script o una persona que recarga sin parar), por proceso de gunicorn.

- Usuarios con sesión: hasta LIMITE_USUARIO_MIN peticiones por minuto cada uno (por defecto 240: 4 por segundo).
- Sin sesión (por IP): hasta LIMITE_IP_MIN por minuto (por defecto 600). Es alto a propósito: toda la oficina puede salir a
  internet con la misma IP pública.
- Ingreso (POST /login): hasta LIMITE_LOGIN_MIN por minuto por IP (por defecto 20), además del bloqueo por intentos fallidos.
No reemplaza a una protección de red (Cloudflare) contra ataques masivos: ver docs/35."""
import os
import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_ventanas = defaultdict(deque)


def _limite(nombre, defecto):
    try:
        return int(os.environ.get(nombre) or defecto)
    except ValueError:
        return defecto


def permitido(clave, maximo, ventana=60.0):
    """Ventana deslizante: True si la clave hizo menos de «maximo» peticiones en los últimos «ventana» segundos."""
    if maximo <= 0:
        return True
    ahora = time.monotonic()
    with _lock:
        q = _ventanas[clave]
        while q and ahora - q[0] > ventana:
            q.popleft()
        if len(q) >= maximo:
            return False
        q.append(ahora)
        if len(_ventanas) > 20000:  # memoria acotada
            for k in [k for k, v in _ventanas.items() if not v or ahora - v[-1] > ventana][:10000]:
                _ventanas.pop(k, None)
        return True


def revisar(request, user):
    """Devuelve None si la petición pasa, o el motivo si se excede el límite."""
    if request.path.startswith("/static/"):
        return None
    ip = request.remote_addr or "?"
    if request.path == "/login" and request.method == "POST":
        if not permitido(("login", ip), _limite("LIMITE_LOGIN_MIN", 20)):
            return "Demasiados intentos de ingreso desde esta conexión. Espere un minuto."
    if user is not None:
        if not permitido(("u", user.id), _limite("LIMITE_USUARIO_MIN", 240)):
            return "Demasiadas peticiones seguidas. Espere unos segundos y vuelva a intentar."
        return None
    if not permitido(("ip", ip), _limite("LIMITE_IP_MIN", 600)):
        return "Demasiadas peticiones desde esta conexión. Espere un minuto."
    return None


def reiniciar():
    with _lock:
        _ventanas.clear()
