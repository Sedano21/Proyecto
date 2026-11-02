"""V18 (02-nov-2026): línea del día en la asistencia (reorganización del equipo) y marcas sobre la imagen del vehículo
en el checklist vehicular.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-02 23:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('attendance', sa.Column('linea', sa.String(length=20), nullable=False, server_default=''))
    op.add_column('vehicle_checklists', sa.Column('marcas', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    op.drop_column('vehicle_checklists', 'marcas')
    op.drop_column('attendance', 'linea')
