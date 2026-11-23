"""V69 (23-nov-2026): análisis adjuntos al informe de reposición y ejecutivo de la proyección de demanda.

Revision ID: 0057
Revises: 0056
Create Date: 2026-11-23 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('demand_forecasts') as b:
        b.add_column(sa.Column('ejecutivo_id', sa.Integer(), nullable=True))
        b.create_foreign_key('fk_demand_forecasts_ejecutivo', 'users', ['ejecutivo_id'], ['id'])
    op.create_table(
        'analisis_reposicion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('titulo', sa.String(200), nullable=False),
        sa.Column('familia', sa.String(120), nullable=False),
        sa.Column('comentario', sa.String(2000), nullable=False),
        sa.Column('archivos', sa.JSON(), nullable=False),
        sa.Column('vigente', sa.Boolean(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('analisis_reposicion')
    with op.batch_alter_table('demand_forecasts') as b:
        b.drop_constraint('fk_demand_forecasts_ejecutivo', type_='foreignkey')
        b.drop_column('ejecutivo_id')
