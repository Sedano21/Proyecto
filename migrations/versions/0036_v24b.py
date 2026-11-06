"""V24b (07-nov-2026): centros de costo, rendiciones de facturas y planillas de movilidad; centro de costo (opcional)
en las solicitudes / OC de compras nacionales.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-07 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('purchase_requests') as b:
        b.add_column(sa.Column('centro_costo', sa.String(length=20), nullable=False, server_default=''))
    op.create_table(
        'cost_centers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('descripcion', sa.String(length=160), nullable=False),
        sa.Column('grupo', sa.String(length=80), nullable=False),
        sa.Column('area_codigo', sa.String(length=20), nullable=False),
        sa.Column('area', sa.String(length=120), nullable=False),
        sa.Column('centro_codigo', sa.String(length=20), nullable=False),
        sa.Column('centro', sa.String(length=120), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cost_centers_codigo', 'cost_centers', ['codigo'], unique=True)
    op.create_table(
        'expense_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tipo', sa.String(length=15), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('responsable', sa.String(length=160), nullable=False),
        sa.Column('concepto', sa.String(length=250), nullable=False),
        sa.Column('comprobante', sa.String(length=60), nullable=False),
        sa.Column('proveedor', sa.String(length=160), nullable=False),
        sa.Column('monto', sa.Float(), nullable=False),
        sa.Column('moneda', sa.String(length=5), nullable=False),
        sa.Column('centro_costo', sa.String(length=20), nullable=False),
        sa.Column('archivo', sa.String(length=250), nullable=False),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_expense_reports_fecha', 'expense_reports', ['fecha'])


def downgrade():
    op.drop_table('expense_reports')
    op.drop_table('cost_centers')
    with op.batch_alter_table('purchase_requests') as b:
        b.drop_column('centro_costo')
