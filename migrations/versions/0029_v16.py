"""V16 (02-nov-2026): clientes del extranjero: tipo de documento (RUC, DNI o EXTRANJERO) y país.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-02 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customers', sa.Column('tipo_documento', sa.String(length=12), nullable=False, server_default='RUC'))
    op.add_column('customers', sa.Column('pais', sa.String(length=60), nullable=False, server_default='PERÚ'))


def downgrade():
    op.drop_column('customers', 'pais')
    op.drop_column('customers', 'tipo_documento')
