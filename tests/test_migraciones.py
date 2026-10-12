"""Las migraciones de Alembic deben reflejar exactamente el modelo de datos (evita desplegar un esquema desactualizado)."""
import os


def test_migraciones_al_dia(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    url = os.environ.get("TEST_MIGRATIONS_URL") or f"sqlite:///{tmp_path}/mig.db"
    monkeypatch.setenv("DATABASE_URL", url)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    command.upgrade(cfg, "head")
    command.check(cfg)  # falla si el modelo tiene cambios sin migración
