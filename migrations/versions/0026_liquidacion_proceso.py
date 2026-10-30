"""Liquidación de proceso CP-OPE-004 (30-oct-2026, solo Producción): tabla process_liquidations.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-30 16:50:54.370813
"""
from alembic import op
import sqlalchemy as sa


revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('process_liquidations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('variante', sa.String(length=4), nullable=False),
    sa.Column('product_code', sa.String(length=40), nullable=False),
    sa.Column('lote', sa.String(length=60), nullable=False),
    sa.Column('linea', sa.String(length=80), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('servicio', sa.JSON(), nullable=False),
    sa.Column('producto', sa.JSON(), nullable=False),
    sa.Column('procesos', sa.JSON(), nullable=False),
    sa.Column('costos', sa.JSON(), nullable=False),
    sa.Column('fotos', sa.JSON(), nullable=False),
    sa.Column('observaciones', sa.Text(), nullable=False),
    sa.Column('report_ids', sa.JSON(), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('numero')
    )
    op.create_index(op.f('ix_process_liquidations_linea'), 'process_liquidations', ['linea'], unique=False)
    op.create_index(op.f('ix_process_liquidations_lote'), 'process_liquidations', ['lote'], unique=False)
    op.create_index(op.f('ix_process_liquidations_product_code'), 'process_liquidations', ['product_code'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_process_liquidations_product_code'), table_name='process_liquidations')
    op.drop_index(op.f('ix_process_liquidations_lote'), table_name='process_liquidations')
    op.drop_index(op.f('ix_process_liquidations_linea'), table_name='process_liquidations')
    op.drop_table('process_liquidations')
