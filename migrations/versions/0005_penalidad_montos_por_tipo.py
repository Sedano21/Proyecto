"""montos de penalidad por tipo en condiciones del cliente

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customer_conditions', sa.Column('penalidad_montos', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('customer_conditions') as b:
        b.drop_column('penalidad_montos')
