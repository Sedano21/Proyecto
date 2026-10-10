"""Conexión a base de datos (SQLAlchemy 2.x sin dependencias adicionales).

La URL se toma de la variable de entorno DATABASE_URL. Por defecto se usa
SQLite en la carpeta ``instance/`` (prototipo). Para producción se recomienda
PostgreSQL o SQL Server (ver docs/SEGURIDAD_INFRAESTRUCTURA.md).
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = scoped_session(sessionmaker(autoflush=False, expire_on_commit=False))


def init_engine(url: str):
    global engine
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    SessionLocal.remove()
    SessionLocal.configure(bind=engine)
    return engine


def create_all():
    from . import models  # noqa: F401  (registra tablas)
    Base.metadata.create_all(engine)


def drop_all():
    from . import models  # noqa: F401
    Base.metadata.drop_all(engine)


def db():
    """Sesión de la solicitud/hilo actual."""
    return SessionLocal()
