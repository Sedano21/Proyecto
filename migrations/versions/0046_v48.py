"""V48 (16-nov-2026): datos de transporte de la guía SUNAT (para el panel «Guía de remisión» de SAP).

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-16 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0046'
down_revision = '0045'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sunat_guides') as b:
        b.add_column(sa.Column('transporte', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('sunat_guides') as b:
        b.drop_column('transporte')
