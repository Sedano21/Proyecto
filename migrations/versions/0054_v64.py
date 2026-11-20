"""V64 (20-nov-2026): marcha blanca comercial: total de la OC, cierre/cancelación con causal, auxiliar y estiba en la OV,
correos por uso y notas de deuda del cliente, tramos de precio por cantidad y vendedores de SAP por usuario.

Revision ID: 0054
Revises: 0053
Create Date: 2026-11-20 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0054'
down_revision = '0053'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('vendedores_sap', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('customers') as b:
        b.add_column(sa.Column('correo_envio', sa.String(250), nullable=False, server_default=''))
        b.add_column(sa.Column('correo_facturacion', sa.String(250), nullable=False, server_default=''))
        b.add_column(sa.Column('correo_logistica', sa.String(250), nullable=False, server_default=''))
        b.add_column(sa.Column('requiere_estiba', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('notas_deuda', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('sales_orders') as b:
        b.add_column(sa.Column('oc_total', sa.Float(), nullable=True))
        b.add_column(sa.Column('cierre', sa.JSON(), nullable=False, server_default='{}'))
        b.add_column(sa.Column('requiere_auxiliar', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('requiere_estiba', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('price_items') as b:
        b.add_column(sa.Column('cantidad_desde', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('price_items') as b:
        b.drop_column('cantidad_desde')
    with op.batch_alter_table('sales_orders') as b:
        for c in ('requiere_estiba', 'requiere_auxiliar', 'cierre', 'oc_total'):
            b.drop_column(c)
    with op.batch_alter_table('customers') as b:
        for c in ('notas_deuda', 'requiere_estiba', 'correo_logistica', 'correo_facturacion', 'correo_envio'):
            b.drop_column(c)
    with op.batch_alter_table('users') as b:
        b.drop_column('vendedores_sap')
