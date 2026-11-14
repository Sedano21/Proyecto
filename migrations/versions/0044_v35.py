"""V35 (14-nov-2026): préstamo de la guía SUNAT e ingresos de mercadería a SAP.

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-14 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sunat_guides') as b:
        b.add_column(sa.Column('prestamo', sa.JSON(), nullable=False, server_default='{}'))
    op.create_table(
        'ingresos_mercaderia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('almacen', sa.String(20), nullable=False, server_default=''),
        sa.Column('motivo', sa.Text(), nullable=False, server_default=''),
        sa.Column('lineas', sa.JSON(), nullable=False),
        sa.Column('guia_id', sa.Integer(), sa.ForeignKey('sunat_guides.id'), nullable=True),
        sa.Column('estado', sa.String(15), nullable=False, server_default='REGISTRADO'),
        sa.Column('sap', sa.JSON(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('ingresos_mercaderia')
    with op.batch_alter_table('sunat_guides') as b:
        b.drop_column('prestamo')
