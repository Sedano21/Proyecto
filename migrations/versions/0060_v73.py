"""V73 (24-nov-2026): hitos de la entrega en el cliente y gastos del trayecto.

Revision ID: 0060
Revises: 0059
Create Date: 2026-11-24 20:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0060'
down_revision = '0059'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('route_stops') as b:
        b.add_column(sa.Column('hitos', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('routes') as b:
        b.add_column(sa.Column('gastos', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('routes') as b:
        b.drop_column('gastos')
    with op.batch_alter_table('route_stops') as b:
        b.drop_column('hitos')
