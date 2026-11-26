"""V76 (26-nov-2026): historial de correcciones del parte de producción y granel o MP a utilizar en el plan.

Revision ID: 0062
Revises: 0061
Create Date: 2026-11-26 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0062'
down_revision = '0061'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('production_reports') as b:
        b.add_column(sa.Column('correcciones', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('production_plans') as b:
        b.add_column(sa.Column('insumo', sa.String(60), nullable=False, server_default=''))
    with op.batch_alter_table('liquidations') as b:
        b.add_column(sa.Column('sap', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('liquidations') as b:
        b.drop_column('sap')
    with op.batch_alter_table('production_plans') as b:
        b.drop_column('insumo')
    with op.batch_alter_table('production_reports') as b:
        b.drop_column('correcciones')
