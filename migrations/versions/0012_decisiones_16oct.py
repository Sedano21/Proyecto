"""decisiones del 16-oct: 3 cotizaciones, datos de la guía y feriados con «se trabaja»

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-16
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

D = "Decisión del usuario (16-oct-2026)"


def _set(bind, key, valor, fuente, solo_si_vacio=False):
    fila = bind.execute(sa.text("SELECT valor FROM params WHERE key = :k"), {"k": key}).first()
    if fila is None:
        return  # la sincronización de catálogos (app.cli init) lo crea con el valor nuevo
    actual = fila[0] if isinstance(fila[0], dict) else json.loads(fila[0] or "{}")
    if solo_si_vacio and actual.get("v"):
        return  # no se pisa lo que ya se configuró
    bind.execute(sa.text("UPDATE params SET valor = :v, estado = 'DEFINIDO', fuente = :f WHERE key = :k"),
                 {"v": json.dumps({"v": valor}), "f": fuente, "k": key})


def upgrade():
    bind = op.get_bind()
    _set(bind, "cotizaciones_minimas_compra", 3, f"{D}: 3 cotizaciones")
    _set(bind, "empresa_correo_documentos", "facturacion2@corporacionproductiva.com",
         f"{D}: usar el del formato de guía, modificable en Configuración", solo_si_vacio=True)
    _set(bind, "empresa_web", "www.corporacionproductiva.com", f"{D}: usar el del formato de guía, modificable en Configuración",
         solo_si_vacio=True)
    _set(bind, "direccion_partida_por_almacen", {"EXT-002": "AV. AVIACION NRO. 1524 LA VICTORIA LIMA LIMA LIMA"},
         f"{D}: usar el del formato de guía, modificable en Configuración", solo_si_vacio=True)


def downgrade():
    pass
