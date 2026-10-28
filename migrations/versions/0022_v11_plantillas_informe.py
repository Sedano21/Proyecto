"""V11 (28-oct-2026): plantillas de informe personalizado (personales y compartidas por área).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-28 21:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('report_templates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=80), nullable=False),
    sa.Column('alcance', sa.String(length=12), nullable=False),
    sa.Column('area', sa.String(length=40), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('creado_ts', sa.DateTime(), nullable=False),
    sa.Column('actualizado_ts', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('report_templates')
