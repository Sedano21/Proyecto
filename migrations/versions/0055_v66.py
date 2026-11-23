"""V66 (23-nov-2026): marcha blanca de almacén: equipo en movimientos, traslados a SAP, validación de almacén de pedidos
grandes de última hora y etiquetas de Calidad.

Revision ID: 0055
Revises: 0054
Create Date: 2026-11-23 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('move_requests') as b:
        b.add_column(sa.Column('equipo', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('transfers') as b:
        b.add_column(sa.Column('sap', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('sales_orders') as b:
        b.add_column(sa.Column('validacion_almacen', sa.JSON(), nullable=False, server_default='{}'))
    op.create_table(
        'label_specs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_code', sa.String(40), nullable=False, index=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True, index=True),
        sa.Column('marca', sa.String(120), nullable=False, server_default=''),
        sa.Column('instrucciones', sa.Text(), nullable=False, server_default=''),
        sa.Column('foto', sa.String(250), nullable=False, server_default=''),
        sa.Column('activa', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('label_specs')
    with op.batch_alter_table('sales_orders') as b:
        b.drop_column('validacion_almacen')
    with op.batch_alter_table('transfers') as b:
        b.drop_column('sap')
    with op.batch_alter_table('move_requests') as b:
        b.drop_column('equipo')
