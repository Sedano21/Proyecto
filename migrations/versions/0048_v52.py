"""V52 (17-nov-2026): facturación de SAP (facturas y notas de crédito) para los indicadores, sin depender del maestro de
clientes del módulo.

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-17 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0048'
down_revision = '0047'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sap_facturacion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clave', sa.String(40), nullable=False, unique=True),
        sa.Column('tipo', sa.String(15), nullable=False, index=True),
        sa.Column('numero', sa.String(40), nullable=False, server_default=''),
        sa.Column('fecha', sa.Date(), nullable=False, index=True),
        sa.Column('cardcode', sa.String(30), nullable=False, server_default=''),
        sa.Column('cliente', sa.String(200), nullable=False, server_default=''),
        sa.Column('moneda', sa.String(10), nullable=False, server_default=''),
        sa.Column('total', sa.Float(), nullable=False, server_default='0'),
        sa.Column('igv', sa.Float(), nullable=False, server_default='0'),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('sap_facturacion')
