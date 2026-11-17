"""V55 (17-nov-2026): valor de las líneas de OV de SAP y órdenes de compra de SAP.

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-17 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0049'
down_revision = '0048'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sap_ordenes') as b:
        b.add_column(sa.Column('total', sa.Float(), nullable=False, server_default='0'))
        b.add_column(sa.Column('igv', sa.Float(), nullable=False, server_default='0'))
    op.create_table(
        'sap_compras',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clave', sa.String(40), nullable=False, unique=True),
        sa.Column('docentry', sa.Integer(), nullable=False, index=True),
        sa.Column('docnum', sa.String(20), nullable=False, server_default=''),
        sa.Column('fecha', sa.Date(), nullable=True, index=True),
        sa.Column('fecha_entrega', sa.Date(), nullable=True),
        sa.Column('cardcode', sa.String(30), nullable=False, server_default=''),
        sa.Column('proveedor', sa.String(200), nullable=False, server_default=''),
        sa.Column('estado', sa.String(12), nullable=False, server_default='ABIERTA'),
        sa.Column('moneda', sa.String(10), nullable=False, server_default=''),
        sa.Column('product_code', sa.String(30), nullable=False, server_default=''),
        sa.Column('descripcion', sa.String(200), nullable=False, server_default=''),
        sa.Column('cantidad', sa.Float(), nullable=False, server_default='0'),
        sa.Column('recibido', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total', sa.Float(), nullable=False, server_default='0'),
        sa.Column('igv', sa.Float(), nullable=False, server_default='0'),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('sap_compras')
    with op.batch_alter_table('sap_ordenes') as b:
        b.drop_column('igv')
        b.drop_column('total')
