"""Simulación integral de operaciones (ENTORNO DE PRUEBAS): corridas y registro de filas creadas o modificadas.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-07 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sim_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('dias', sa.Integer(), nullable=False),
        sa.Column('semilla', sa.Integer(), nullable=False),
        sa.Column('desde', sa.Date(), nullable=True),
        sa.Column('hasta', sa.Date(), nullable=True),
        sa.Column('resumen', sa.JSON(), nullable=False),
        sa.Column('validacion', sa.JSON(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('inicio_ts', sa.DateTime(), nullable=False),
        sa.Column('fin_ts', sa.DateTime(), nullable=True),
        sa.Column('limpiado_ts', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'sim_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('sim_runs.id'), nullable=False),
        sa.Column('tabla', sa.String(length=60), nullable=False),
        sa.Column('clave', sa.String(length=120), nullable=False),
        sa.Column('accion', sa.String(length=12), nullable=False),
        sa.Column('previos', sa.JSON(), nullable=False),
    )
    op.create_index('ix_sim_records_run_id', 'sim_records', ['run_id'])
    op.create_index('ix_sim_records_tabla', 'sim_records', ['tabla'])


def downgrade():
    op.drop_index('ix_sim_records_tabla', 'sim_records')
    op.drop_index('ix_sim_records_run_id', 'sim_records')
    op.drop_table('sim_records')
    op.drop_table('sim_runs')
