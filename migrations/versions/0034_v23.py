"""V23 (06-nov-2026): devoluciones sin hora de corte; registro de «sin personal para recibir, queda en el vehículo».

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-06 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('return_receipts') as b:
        b.add_column(sa.Column('en_vehiculo', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('return_receipts') as b:
        b.drop_column('en_vehiculo')
