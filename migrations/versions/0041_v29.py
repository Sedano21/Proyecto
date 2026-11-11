"""V29 (11-nov-2026): clase de la OV (venta/servicio), notas de crédito sobre OV y órdenes de SAP del periodo.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-11 20:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales_orders') as b:
        b.add_column(sa.Column('clase', sa.String(10), nullable=False, server_default='VENTA'))
        b.create_index('ix_sales_orders_clase', ['clase'])
    op.create_table(
        'ov_notas_credito',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clave', sa.String(40), nullable=False, unique=True),
        sa.Column('nc_numero', sa.String(40), nullable=False, server_default=''),
        sa.Column('factura', sa.String(40), nullable=False, server_default=''),
        sa.Column('fecha', sa.Date(), nullable=True),
        sa.Column('ov_numero', sa.String(30), nullable=False, server_default=''),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('sales_orders.id'), nullable=True),
        sa.Column('line_id', sa.Integer(), sa.ForeignKey('sales_order_lines.id'), nullable=True),
        sa.Column('product_code', sa.String(30), nullable=False, server_default=''),
        sa.Column('cantidad', sa.Float(), nullable=False, server_default='0'),
        sa.Column('aplicada', sa.Float(), nullable=False, server_default='0'),
        sa.Column('liberado', sa.Float(), nullable=False, server_default='0'),
        sa.Column('estado', sa.String(15), nullable=False, server_default='APLICADA'),
        sa.Column('origen', sa.String(20), nullable=False, server_default=''),
        sa.Column('comentario', sa.Text(), nullable=False, server_default=''),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_ov_notas_credito_ov_numero', 'ov_notas_credito', ['ov_numero'])
    op.create_index('ix_ov_notas_credito_order_id', 'ov_notas_credito', ['order_id'])
    op.create_table(
        'sap_ordenes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('docnum', sa.String(20), nullable=False),
        sa.Column('clase', sa.String(10), nullable=False, server_default='VENTA'),
        sa.Column('serie', sa.String(40), nullable=False, server_default=''),
        sa.Column('fecha', sa.Date(), nullable=True),
        sa.Column('fecha_entrega', sa.Date(), nullable=True),
        sa.Column('cliente', sa.String(200), nullable=False, server_default=''),
        sa.Column('estado', sa.String(12), nullable=False, server_default='ABIERTA'),
        sa.Column('product_code', sa.String(30), nullable=False, server_default=''),
        sa.Column('descripcion', sa.String(200), nullable=False, server_default=''),
        sa.Column('cantidad', sa.Float(), nullable=False, server_default='0'),
        sa.Column('entregado', sa.Float(), nullable=False, server_default='0'),
        sa.Column('linea_cerrada', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_sap_ordenes_docnum', 'sap_ordenes', ['docnum'])
    op.create_index('ix_sap_ordenes_fecha_entrega', 'sap_ordenes', ['fecha_entrega'])


def downgrade():
    op.drop_table('sap_ordenes')
    op.drop_table('ov_notas_credito')
    with op.batch_alter_table('sales_orders') as b:
        b.drop_index('ix_sales_orders_clase')
        b.drop_column('clase')
