"""V13 (30-oct-2026, Calidad): solicitudes de revisión, observaciones en línea, validación de merma, inspecciones,
visitas a almacenes externos; lote observado, fechas de producción, fumigación y liberación solicitada; adjuntos de los
registros de Calidad; proyección por producto de las oportunidades.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-30 01:08:04.978979
"""
from alembic import op
import sqlalchemy as sa


revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('external_visits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('warehouse_code', sa.String(length=20), nullable=False),
    sa.Column('tipo', sa.String(length=12), nullable=False),
    sa.Column('propuesta', sa.DateTime(), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('confirmacion', sa.JSON(), nullable=False),
    sa.Column('hallazgos', sa.JSON(), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['warehouse_code'], ['warehouses.code'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('inspections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('cliente', sa.String(length=160), nullable=False),
    sa.Column('empresa', sa.String(length=160), nullable=False),
    sa.Column('alcance', sa.Text(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('hora_inicio', sa.String(length=5), nullable=False),
    sa.Column('fase', sa.String(length=15), nullable=False),
    sa.Column('n_hallazgos', sa.Integer(), nullable=True),
    sa.Column('puntaje', sa.Float(), nullable=True),
    sa.Column('resultado', sa.String(length=15), nullable=False),
    sa.Column('fotos_resultado', sa.JSON(), nullable=False),
    sa.Column('fotos_hallazgos', sa.JSON(), nullable=False),
    sa.Column('hallazgos', sa.JSON(), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('line_observations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=True),
    sa.Column('linea', sa.String(length=20), nullable=False),
    sa.Column('pallets', sa.JSON(), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('fase', sa.String(length=15), nullable=False),
    sa.Column('motivo_cierre', sa.Text(), nullable=False),
    sa.Column('fotos', sa.JSON(), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['report_id'], ['production_reports.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_line_observations_report_id'), 'line_observations', ['report_id'], unique=False)
    op.create_table('merma_validations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('merma_pct', sa.Float(), nullable=True),
    sa.Column('limite_pct', sa.Float(), nullable=True),
    sa.Column('grano_bueno_kg', sa.Float(), nullable=True),
    sa.Column('grano_danado_kg', sa.Float(), nullable=True),
    sa.Column('fotos', sa.JSON(), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('validado_por', sa.Integer(), nullable=True),
    sa.Column('validado_ts', sa.DateTime(), nullable=True),
    sa.Column('reproceso', sa.JSON(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['report_id'], ['production_reports.id'], ),
    sa.ForeignKeyConstraint(['validado_por'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_merma_validations_report_id'), 'merma_validations', ['report_id'], unique=False)
    op.create_table('review_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lot_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('resultado', sa.String(length=20), nullable=False),
    sa.Column('comentario', sa.Text(), nullable=False),
    sa.Column('solicitado_por', sa.Integer(), nullable=True),
    sa.Column('resuelto_por', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('resuelto_ts', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['lot_id'], ['stock_lots.id'], ),
    sa.ForeignKeyConstraint(['resuelto_por'], ['users.id'], ),
    sa.ForeignKeyConstraint(['solicitado_por'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_review_requests_lot_id'), 'review_requests', ['lot_id'], unique=False)
    op.add_column('opportunities', sa.Column('detalle_productos', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('quality_records', sa.Column('adjuntos', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('stock_lots', sa.Column('observacion', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('stock_lots', sa.Column('fechas_produccion', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('stock_lots', sa.Column('fumigacion', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('stock_lots', sa.Column('liberacion_solicitada', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('stock_lots', 'liberacion_solicitada')
    op.drop_column('stock_lots', 'fumigacion')
    op.drop_column('stock_lots', 'fechas_produccion')
    op.drop_column('stock_lots', 'observacion')
    op.drop_column('quality_records', 'adjuntos')
    op.drop_column('opportunities', 'detalle_productos')
    op.drop_index(op.f('ix_review_requests_lot_id'), table_name='review_requests')
    op.drop_table('review_requests')
    op.drop_index(op.f('ix_merma_validations_report_id'), table_name='merma_validations')
    op.drop_table('merma_validations')
    op.drop_index(op.f('ix_line_observations_report_id'), table_name='line_observations')
    op.drop_table('line_observations')
    op.drop_table('inspections')
    op.drop_table('external_visits')
