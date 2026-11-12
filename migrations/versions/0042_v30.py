"""V30 (12-nov-2026): ubicación del lote, revisión de clientes sin movimiento, filas de carga incluidas con motivo y
facturas de reserva de SAP sin entrega.

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-12 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_lots') as b:
        b.add_column(sa.Column('ubicacion', sa.String(80), nullable=False, server_default=''))
        b.add_column(sa.Column('ubicacion_hist', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('customers') as b:
        b.add_column(sa.Column('inactividad', sa.JSON(), nullable=False, server_default='{}'))
        b.add_column(sa.Column('excluido', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('upload_rows') as b:
        b.add_column(sa.Column('inclusion', sa.JSON(), nullable=False, server_default='{}'))
    op.create_table(
        'sap_facturas_reserva',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clave', sa.String(40), nullable=False, unique=True),
        sa.Column('numero', sa.String(40), nullable=False, server_default=''),
        sa.Column('docnum', sa.String(20), nullable=False, server_default=''),
        sa.Column('fecha', sa.Date(), nullable=True),
        sa.Column('fecha_entrega', sa.Date(), nullable=True),
        sa.Column('cliente', sa.String(200), nullable=False, server_default=''),
        sa.Column('codigo_cliente', sa.String(30), nullable=False, server_default=''),
        sa.Column('ov_numero', sa.String(30), nullable=False, server_default=''),
        sa.Column('product_code', sa.String(30), nullable=False, server_default=''),
        sa.Column('descripcion', sa.String(200), nullable=False, server_default=''),
        sa.Column('cantidad', sa.Float(), nullable=False, server_default='0'),
        sa.Column('pendiente', sa.Float(), nullable=False, server_default='0'),
        sa.Column('vigente', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('aprobacion', sa.JSON(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_sap_facturas_reserva_fecha_entrega', 'sap_facturas_reserva', ['fecha_entrega'])
    op.create_index('ix_sap_facturas_reserva_ov_numero', 'sap_facturas_reserva', ['ov_numero'])


def downgrade():
    op.drop_table('sap_facturas_reserva')
    with op.batch_alter_table('upload_rows') as b:
        b.drop_column('inclusion')
    with op.batch_alter_table('customers') as b:
        b.drop_column('excluido')
        b.drop_column('inactividad')
    with op.batch_alter_table('stock_lots') as b:
        b.drop_column('ubicacion_hist')
        b.drop_column('ubicacion')
