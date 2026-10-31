"""V14 (31-oct-2026): uno o varios contactos (nombre, teléfono y correo) por lugar de entrega del cliente.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-31 00:55:22.269269
"""
from alembic import op
import sqlalchemy as sa


revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customer_sites', sa.Column('contactos', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    op.drop_column('customer_sites', 'contactos')
