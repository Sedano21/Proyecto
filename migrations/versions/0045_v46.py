"""V46 (16-nov-2026): la guía SUNAT se puede editar al subirla (observación e historial de cambios).

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-16 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0045'
down_revision = '0044'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sunat_guides') as b:
        b.add_column(sa.Column('observacion', sa.Text(), nullable=False, server_default=''))
        b.add_column(sa.Column('ediciones', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('sunat_guides') as b:
        b.drop_column('ediciones')
        b.drop_column('observacion')
