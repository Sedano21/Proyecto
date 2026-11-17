"""V51 (17-nov-2026): histórico del Excel CONTROL DE PRODUCCION (movimientos y registros que no son partes).

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-17 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0047'
down_revision = '0046'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'historico_produccion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tipo', sa.String(30), nullable=False, index=True),
        sa.Column('fecha', sa.Date(), nullable=True, index=True),
        sa.Column('codigo', sa.String(40), nullable=False, server_default=''),
        sa.Column('descripcion', sa.String(250), nullable=False, server_default=''),
        sa.Column('lote', sa.String(60), nullable=False, server_default=''),
        sa.Column('linea', sa.String(40), nullable=False, server_default=''),
        sa.Column('cantidad', sa.Float(), nullable=True),
        sa.Column('um', sa.String(20), nullable=False, server_default=''),
        sa.Column('datos', sa.JSON(), nullable=False),
        sa.Column('hoja', sa.String(60), nullable=False, server_default=''),
        sa.Column('fila', sa.Integer(), nullable=True),
        sa.Column('clave', sa.String(120), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('historico_produccion')
