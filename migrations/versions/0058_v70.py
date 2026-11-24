"""V70 (24-nov-2026): reglas de Calidad por cliente en el lote, aviso de carga en la ruta y OV fuera de horario.

Revision ID: 0058
Revises: 0057
Create Date: 2026-11-24 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0058'
down_revision = '0057'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_lots') as b:
        b.add_column(sa.Column('restriccion_clientes', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('routes') as b:
        b.add_column(sa.Column('aviso_carga', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('sales_orders') as b:
        b.add_column(sa.Column('fuera_horario', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('sales_orders') as b:
        b.drop_column('fuera_horario')
    with op.batch_alter_table('routes') as b:
        b.drop_column('aviso_carga')
    with op.batch_alter_table('stock_lots') as b:
        b.drop_column('restriccion_clientes')
