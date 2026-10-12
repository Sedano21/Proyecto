"""Entorno de Alembic: toma la URL de DATABASE_URL y el esquema de app.models."""
import os

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  (registra las tablas)
from app.db import Base

target_metadata = Base.metadata


def _url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL (p. ej. postgresql+psycopg://usuario:clave@servidor:5432/operaciones)")
    return url


def run_migrations_offline():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
