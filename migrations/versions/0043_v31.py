"""V31 (13-nov-2026): movimientos de SAP (guías y consumos de producción) desde julio.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-13 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sap_movimientos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clave', sa.String(50), nullable=False, unique=True),
        sa.Column('tipo', sa.String(10), nullable=False),
        sa.Column('docentry', sa.Integer(), nullable=False),
        sa.Column('documento', sa.String(40), nullable=False, server_default=''),
        sa.Column('fecha', sa.Date(), nullable=True),
        sa.Column('ov_numero', sa.String(30), nullable=False, server_default=''),
        sa.Column('orden_fabricacion', sa.String(30), nullable=False, server_default=''),
        sa.Column('factura', sa.String(40), nullable=False, server_default=''),
        sa.Column('cliente', sa.String(200), nullable=False, server_default=''),
        sa.Column('product_code', sa.String(30), nullable=False, server_default=''),
        sa.Column('cantidad', sa.Float(), nullable=False, server_default='0'),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    for c in ('tipo', 'docentry', 'fecha', 'ov_numero', 'product_code'):
        op.create_index(f'ix_sap_movimientos_{c}', 'sap_movimientos', [c])


def downgrade():
    op.drop_table('sap_movimientos')
