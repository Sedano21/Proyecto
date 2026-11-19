"""V59 (19-nov-2026): compras de SAP con tipo (orden de compra o entrada de mercancías) y país del proveedor.

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-19 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0053'
down_revision = '0052'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sap_compras') as b:
        b.add_column(sa.Column('tipo', sa.String(10), nullable=False, server_default='OC'))
        b.add_column(sa.Column('pais', sa.String(3), nullable=False, server_default=''))
        b.create_index('ix_sap_compras_tipo', ['tipo'])


def downgrade():
    with op.batch_alter_table('sap_compras') as b:
        b.drop_index('ix_sap_compras_tipo')
        b.drop_column('pais')
        b.drop_column('tipo')
