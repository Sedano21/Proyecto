"""V24 (06-nov-2026): canal del vendedor, compras nacionales por OV/cliente/motivo, cotizaciones de proveedores,
seguimiento de importaciones y tipo de cambio SUNAT.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-06 22:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0035'
down_revision = '0034'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workers') as b:
        b.add_column(sa.Column('canal', sa.String(length=60), nullable=False, server_default=''))
    with op.batch_alter_table('purchase_requests') as b:
        b.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('motivo_tipo', sa.String(length=20), nullable=False, server_default=''))
        b.create_foreign_key('fk_purchase_customer', 'customers', ['customer_id'], ['id'])
    op.create_table(
        'supplier_quotes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_code', sa.String(length=40), nullable=False),
        sa.Column('request_ids', sa.JSON(), nullable=False),
        sa.Column('origen', sa.String(length=80), nullable=False),
        sa.Column('proveedor', sa.String(length=160), nullable=False),
        sa.Column('fecha_entrega', sa.Date(), nullable=True),
        sa.Column('calidad', sa.String(length=160), nullable=False),
        sa.Column('precio', sa.Float(), nullable=False),
        sa.Column('moneda', sa.String(length=5), nullable=False),
        sa.Column('um', sa.String(length=20), nullable=False),
        sa.Column('cantidad', sa.Float(), nullable=True),
        sa.Column('archivo', sa.String(length=250), nullable=False),
        sa.Column('observacion', sa.Text(), nullable=False),
        sa.Column('elegida', sa.Boolean(), nullable=False),
        sa.Column('tipo_cambio', sa.Float(), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_supplier_quotes_product_code', 'supplier_quotes', ['product_code'])
    op.create_index('ix_supplier_quotes_fecha', 'supplier_quotes', ['fecha'])
    op.create_table(
        'import_followups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('codigo_sap', sa.String(length=40), nullable=False),
        sa.Column('contrato', sa.String(length=60), nullable=False),
        sa.Column('proveedor', sa.String(length=160), nullable=False),
        sa.Column('item', sa.String(length=160), nullable=False),
        sa.Column('pais_origen', sa.String(length=60), nullable=False),
        sa.Column('contenedores', sa.Integer(), nullable=False),
        sa.Column('kg', sa.Float(), nullable=True),
        sa.Column('fecha_llegada', sa.Date(), nullable=True),
        sa.Column('dias_libres', sa.Integer(), nullable=False),
        sa.Column('status_senasa', sa.String(length=60), nullable=False),
        sa.Column('status_bl', sa.String(length=80), nullable=False),
        sa.Column('retiro_fecha', sa.Date(), nullable=True),
        sa.Column('retiro_real', sa.Boolean(), nullable=False),
        sa.Column('almacen_info', sa.String(length=160), nullable=False),
        sa.Column('precio', sa.Float(), nullable=True),
        sa.Column('moneda', sa.String(length=5), nullable=False),
        sa.Column('um', sa.String(length=20), nullable=False),
        sa.Column('fecha_entrega_contrato', sa.Date(), nullable=True),
        sa.Column('penalidad_dia', sa.Float(), nullable=True),
        sa.Column('sobreestadia_dia', sa.Float(), nullable=True),
        sa.Column('contrato_archivo', sa.String(length=250), nullable=False),
        sa.Column('gastos', sa.JSON(), nullable=False),
        sa.Column('incidencias', sa.JSON(), nullable=False),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('shipment_id', sa.Integer(), sa.ForeignKey('import_shipments.id'), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_import_followups_contrato', 'import_followups', ['contrato'])
    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('compra', sa.Float(), nullable=False),
        sa.Column('venta', sa.Float(), nullable=False),
        sa.Column('fuente', sa.String(length=40), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_exchange_rates_fecha', 'exchange_rates', ['fecha'], unique=True)


def downgrade():
    op.drop_table('exchange_rates')
    op.drop_table('import_followups')
    op.drop_table('supplier_quotes')
    with op.batch_alter_table('purchase_requests') as b:
        b.drop_constraint('fk_purchase_customer', type_='foreignkey')
        b.drop_column('motivo_tipo')
        b.drop_column('customer_id')
    with op.batch_alter_table('workers') as b:
        b.drop_column('canal')
