"""V57 (18-nov-2026): forma de pago, vencimiento y orden de compra del cliente en la pre-factura.

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-18 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0051'
down_revision = '0050'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('prefacturas') as b:
        b.add_column(sa.Column('forma_pago', sa.String(80), nullable=False, server_default=''))
        b.add_column(sa.Column('forma_pago_codigo', sa.Integer(), nullable=True))
        b.add_column(sa.Column('vencimiento', sa.Date(), nullable=True))
        b.add_column(sa.Column('oc_cliente', sa.String(100), nullable=False, server_default=''))


def downgrade():
    with op.batch_alter_table('prefacturas') as b:
        b.drop_column('oc_cliente')
        b.drop_column('vencimiento')
        b.drop_column('forma_pago_codigo')
        b.drop_column('forma_pago')
