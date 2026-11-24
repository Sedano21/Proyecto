"""V70 (24-nov-2026, 2.ª parte): de qué guía y OV sale cada factura de SAP y cómo recibió el cliente cada entrega.

Revision ID: 0059
Revises: 0058
Create Date: 2026-11-24 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0059'
down_revision = '0058'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sap_facturacion') as b:
        b.add_column(sa.Column('origenes', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('route_stops') as b:
        b.add_column(sa.Column('recepcion', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('route_stops') as b:
        b.drop_column('recepcion')
    with op.batch_alter_table('sap_facturacion') as b:
        b.drop_column('origenes')
