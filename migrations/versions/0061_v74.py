"""V74 (25-nov-2026): Calidad — etiquetas con lote y vencimiento, flujo de fumigación por espacio y programación,
validación de la fumigación de unidades y controles de calidad en el parte de producción.

Revision ID: 0061
Revises: 0060
Create Date: 2026-11-25 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0061'
down_revision = '0060'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('label_specs') as b:
        b.add_column(sa.Column('lote', sa.String(60), nullable=False, server_default=''))
        b.add_column(sa.Column('fecha_vencimiento', sa.Date(), nullable=True))
    with op.batch_alter_table('fumigation_requests') as b:
        b.add_column(sa.Column('flujo', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('sanitation_logs') as b:
        b.add_column(sa.Column('validacion', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('production_reports') as b:
        b.add_column(sa.Column('controles_calidad', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('production_reports') as b:
        b.drop_column('controles_calidad')
    with op.batch_alter_table('sanitation_logs') as b:
        b.drop_column('validacion')
    with op.batch_alter_table('fumigation_requests') as b:
        b.drop_column('flujo')
    with op.batch_alter_table('label_specs') as b:
        b.drop_column('fecha_vencimiento')
        b.drop_column('lote')
