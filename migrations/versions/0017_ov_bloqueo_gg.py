"""ronda del 26-oct-2026: OV bloqueada sin opción que cumpla la fecha (decisión de Gerencia General) y límite de emisión

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-26 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sales_orders', sa.Column('bloqueo_ov', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('sales_orders', 'bloqueo_ov')
