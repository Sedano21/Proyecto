"""Módulo de Operaciones – Corporación Productiva (prototipo funcional)."""
import os
import secrets

from flask import Flask, g, session

from .db import SessionLocal, create_all, init_engine


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

    interval = int(os.environ.get("CHECK_INTERVAL_MIN", "0") or 0)
    if interval > 0 and not app.config.get("TESTING"):
        from .services.scheduler import start_background
        start_background(None, interval)
    return app


def _instance_secret(path):
    f = os.path.join(path, "secret_key")
    if not os.path.exists(f):
        with open(f, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(f) as fh:
        return fh.read().strip()
