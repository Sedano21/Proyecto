"""V12 (29-oct-2026): tipo de carga del movimiento (pallet de PT, merma, remanente de MP, muestra, pallet).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-29 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('move_requests', sa.Column('carga', sa.JSON(), server_default='{}', nullable=False))


def downgrade():
    op.drop_column('move_requests', 'carga')
