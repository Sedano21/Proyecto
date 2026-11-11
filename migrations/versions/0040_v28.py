"""V28 (11-nov-2026): historial de status y retrasos del seguimiento de importaciones.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-11 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0040'
down_revision = '0039'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('import_followups') as b:
        b.add_column(sa.Column('historial_status', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('retrasos', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('import_followups') as b:
        b.drop_column('retrasos')
        b.drop_column('historial_status')
