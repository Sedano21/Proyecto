"""V56 (17-nov-2026): pre-facturas (desde las guías de SAP y regularización de facturas emitidas en SUNAT).

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-17 20:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0050'
down_revision = '0049'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'prefacturas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('origen', sa.String(10), nullable=False, server_default='SAP'),
        sa.Column('estado', sa.String(20), nullable=False, server_default='POR_VALIDAR', index=True),
        sa.Column('entrega_docentry', sa.Integer(), nullable=True, index=True),
        sa.Column('guia', sa.String(40), nullable=False, server_default=''),
        sa.Column('ov_numero', sa.String(30), nullable=False, server_default=''),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('sales_orders.id'), nullable=True, index=True),
        sa.Column('cardcode', sa.String(30), nullable=False, server_default=''),
        sa.Column('cliente', sa.String(200), nullable=False, server_default=''),
        sa.Column('ruc', sa.String(15), nullable=False, server_default=''),
        sa.Column('fecha', sa.Date(), nullable=True),
        sa.Column('moneda', sa.String(10), nullable=False, server_default=''),
        sa.Column('serie', sa.String(8), nullable=False, server_default=''),
        sa.Column('numero', sa.String(12), nullable=False, server_default=''),
        sa.Column('lineas', sa.JSON(), nullable=False),
        sa.Column('observacion', sa.Text(), nullable=False, server_default=''),
        sa.Column('ediciones', sa.JSON(), nullable=False),
        sa.Column('sap', sa.JSON(), nullable=False),
        sa.Column('archivo', sa.String(250), nullable=False, server_default=''),
        sa.Column('total_sunat', sa.Float(), nullable=True),
        sa.Column('validado_por', sa.String(120), nullable=False, server_default=''),
        sa.Column('validado_ts', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('prefacturas')
