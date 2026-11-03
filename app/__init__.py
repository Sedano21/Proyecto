"""Módulo de Operaciones – Corporación Productiva (prototipo funcional)."""
import os
import secrets

from flask import Flask, g, session

from .db import SessionLocal, create_all, init_engine


def _set_timezone():
    """V19: el sistema trabaja con la hora de Perú (America/Lima), no con la del servidor (que suele estar en UTC).
    Afecta a datetime.now() y date.today() de todo el proceso: registros, cargas, alertas, cortes y plazos.
    Se cambia con la variable APP_TZ."""
    import time
    tz = os.environ.get("APP_TZ", "America/Lima").strip() or "America/Lima"
    if os.environ.get("TZ") != tz:
        os.environ["TZ"] = tz
    if hasattr(time, "tzset"):
        time.tzset()


_set_timezone()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or _instance_secret(app.instance_path),
        DATABASE_URL=os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(app.instance_path, 'operaciones.db')}",
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR") or os.path.join(app.instance_path, "uploads"),
        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_UPLOAD_MB", "40")) * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        DEMO_MODE=os.environ.get("DEMO_MODE", "1") == "1",
        APP_VERSION=os.environ.get("APP_VERSION", "1.0.0-mb") + _git_version(),  # versión que se muestra y queda en las observaciones
    )
    if config:
        app.config.update(config)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    init_engine(app.config["DATABASE_URL"])
    if os.environ.get("SCHEMA_AUTO_CREATE", "1") != "0":  # en producción el esquema se gestiona con Alembic
        create_all()

    @app.teardown_appcontext
    def _remove_session(exc=None):
        s = SessionLocal()
        if exc is not None:
            s.rollback()
        SessionLocal.remove()

    from .views import register_views
    register_views(app)
    from .services.audit_trail import install as install_audit_trail
    install_audit_trail()  # trazabilidad de todo cambio hecho por un usuario (ronda 23-oct-2026)

    # verificaciones automáticas cada minuto por defecto (ronda 23-oct-2026); CHECK_INTERVAL_MIN=0 las desactiva
    interval = int(os.environ.get("CHECK_INTERVAL_MIN", "1") or 0)
    if interval > 0 and not app.config.get("TESTING"):
        from .services.scheduler import start_background
        start_background(None, interval, os.path.join(app.instance_path, "verificaciones.lock"))
    return app


def _git_version():
    """V16: commit instalado y su fecha (p. ej. « · a1b2c3d 02/11 16:40»), para comprobar que el servidor tomó la última
    actualización del repositorio. Vacío si no hay git."""
    import subprocess
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        r = subprocess.run(["git", "-C", raiz, "log", "-1", "--format=%h %cd", "--date=format:%d/%m %H:%M"],
                           capture_output=True, text=True, timeout=3)
        return f" · {r.stdout.strip()}" if r.returncode == 0 and r.stdout.strip() else ""
    except Exception:  # noqa: BLE001
        return ""


def _instance_secret(path):
    f = os.path.join(path, "secret_key")
    if not os.path.exists(f):
        with open(f, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(f) as fh:
        return fh.read().strip()
