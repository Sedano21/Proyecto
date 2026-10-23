"""almacenes habilitados en Configuración: solo se toma información de los almacenes marcados

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-23 20:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('warehouses') as b:
        b.add_column(sa.Column('habilitado', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('warehouses') as b:
        b.drop_column('habilitado')
