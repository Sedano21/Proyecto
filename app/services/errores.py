"""V19: fallos del sistema con código. Cada error inesperado (500, base de datos que rechaza un dato) recibe un código
corto que el usuario ve en una ventana emergente y envía a Sistemas; el detalle completo (traza) queda en el registro
del servidor y en instance/errores.log, buscable por ese código en Sistemas → Errores del sistema."""
import json
import logging
import os
import secrets
import traceback
from datetime import datetime

log = logging.getLogger("operaciones")


def nuevo_codigo():
    return f"E{datetime.now():%y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def _archivo():
    from flask import current_app
    return os.path.join(current_app.instance_path, "errores.log")


def registrar(exc, codigo=None, contexto=None):
    """Registra el fallo y devuelve (código, resumen de una línea)."""
    codigo = codigo or nuevo_codigo()
    orig = getattr(exc, "original_exception", None) or exc
    base = getattr(orig, "orig", None) or orig
    texto = str(base).strip().splitlines()[0][:300] if str(base).strip() else ""
    resumen = f"{type(base).__name__}: {texto}" if texto else type(base).__name__
    log.error("Fallo %s: %s", codigo, resumen, exc_info=(type(orig), orig, orig.__traceback__))
    try:
        from flask import g, has_request_context, request
        ctx = dict(contexto or {})
        if has_request_context():
            ctx.update({"metodo": request.method, "ruta": request.path,
                        "usuario": getattr(getattr(g, "user", None), "username", None)})
        linea = {"codigo": codigo, "ts": datetime.now().isoformat(timespec="seconds"), "resumen": resumen, **ctx,
                 "traza": "".join(traceback.format_exception(type(orig), orig, orig.__traceback__))[-6000:]}
        with open(_archivo(), "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001  (registrar nunca debe provocar otro error)
        pass
    return codigo, resumen


def ultimos(n=100, buscar=""):
    try:
        with open(_archivo(), encoding="utf-8") as f:
            filas = f.readlines()[-2000:]
    except OSError:
        return []
    out = []
    for l in reversed(filas):
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if buscar and buscar.upper() not in (d.get("codigo", "") + d.get("resumen", "") + (d.get("ruta") or "")).upper():
            continue
        out.append(d)
        if len(out) >= n:
            break
    return out
