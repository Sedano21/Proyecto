"""V27 (11-nov-2026): días no laborables por área, guías emitidas en SUNAT, solicitudes de fumigación y fotos del
checklist vehicular diario.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-11 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'area_days_off',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('area', sa.String(length=40), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('replanificado', sa.JSON(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_area_days_off_area', 'area_days_off', ['area'])
    op.create_index('ix_area_days_off_fecha', 'area_days_off', ['fecha'])
    op.create_table(
        'sunat_guides',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('serie', sa.String(length=8), nullable=False),
        sa.Column('numero', sa.String(length=12), nullable=False),
        sa.Column('fecha_emision', sa.Date(), nullable=True),
        sa.Column('fecha_traslado', sa.Date(), nullable=True),
        sa.Column('motivo', sa.String(length=60), nullable=False),
        sa.Column('destinatario_ruc', sa.String(length=15), nullable=False),
        sa.Column('destinatario', sa.String(length=200), nullable=False),
        sa.Column('llegada', sa.String(length=250), nullable=False),
        sa.Column('placa', sa.String(length=15), nullable=False),
        sa.Column('lineas', sa.JSON(), nullable=False),
        sa.Column('archivo', sa.String(length=250), nullable=False),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('sales_orders.id'), nullable=True),
        sa.Column('sap_ov', sa.String(length=20), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('inventario', sa.JSON(), nullable=False),
        sa.Column('sap', sa.JSON(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_sunat_guides_order_id', 'sunat_guides', ['order_id'])
    op.create_table(
        'fumigation_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('area', sa.String(length=30), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('lineas', sa.JSON(), nullable=False),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('lugar', sa.String(length=60), nullable=False),
        sa.Column('inicio', sa.Date(), nullable=True),
        sa.Column('liberacion', sa.Date(), nullable=True),
        sa.Column('aprobacion', sa.JSON(), nullable=False),
        sa.Column('ingreso', sa.JSON(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table('vehicle_checklists') as b:
        b.add_column(sa.Column('fotos', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('vehicle_checklists') as b:
        b.drop_column('fotos')
    op.drop_table('fumigation_requests')
    op.drop_table('sunat_guides')
    op.drop_table('area_days_off')
