"""V58 (18-nov-2026): valor de las líneas de las guías de SAP (lo entregado del mes).

Revision ID: 0052
Revises: 0051
Create Date: 2026-11-18 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0052'
down_revision = '0051'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sap_movimientos') as b:
        b.add_column(sa.Column('total', sa.Float(), nullable=False, server_default='0'))
        b.add_column(sa.Column('igv', sa.Float(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('sap_movimientos') as b:
        b.drop_column('igv')
        b.drop_column('total')
