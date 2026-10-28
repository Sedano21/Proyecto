"""Ronda V10 (28-oct-2026): la OV del módulo se crea en SAP; número y estado del envío.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-28 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sales_orders', sa.Column('sap_docnum', sa.String(length=20), server_default='', nullable=False))
    op.add_column('sales_orders', sa.Column('sap_docentry', sa.Integer(), nullable=True))
    op.add_column('sales_orders', sa.Column('sap_envio', sa.JSON(), server_default='{}', nullable=False))
    op.create_index('ix_sales_orders_sap_docnum', 'sales_orders', ['sap_docnum'], unique=False)


def downgrade():
    op.drop_index('ix_sales_orders_sap_docnum', table_name='sales_orders')
    op.drop_column('sales_orders', 'sap_envio')
    op.drop_column('sales_orders', 'sap_docentry')
    op.drop_column('sales_orders', 'sap_docnum')
