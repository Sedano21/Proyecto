"""ronda UX del 24-oct-2026: parte unificado y liquidación parcial, conformidad de entrega del chofer y estado de guías,
mantenimiento (preventivo, correctivo, saneamiento, fumigación de unidades), proyección de demanda, movimientos punto a
punto, aviso de atraso de la OV y asistencia por área

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-24 00:17:52.024922
"""
from alembic import op
import sqlalchemy as sa


revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sanitation_zones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('area', sa.String(length=40), nullable=False),
    sa.Column('almacen', sa.String(length=20), nullable=False),
    sa.Column('frecuencia_limpieza_dias', sa.Integer(), nullable=True),
    sa.Column('frecuencia_fumigacion_dias', sa.Integer(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('move_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('area', sa.String(length=40), nullable=False),
    sa.Column('almacen', sa.String(length=20), nullable=False),
    sa.Column('origen', sa.String(length=120), nullable=False),
    sa.Column('destino', sa.String(length=120), nullable=False),
    sa.Column('detalle', sa.String(length=250), nullable=False),
    sa.Column('cantidad', sa.String(length=40), nullable=False),
    sa.Column('prioridad', sa.String(length=10), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('solicitado_por', sa.Integer(), nullable=True),
    sa.Column('asignado_a', sa.Integer(), nullable=True),
    sa.Column('foto_inicio', sa.String(length=250), nullable=False),
    sa.Column('foto_fin', sa.String(length=250), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('inicio_ts', sa.DateTime(), nullable=True),
    sa.Column('fin_ts', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['asignado_a'], ['users.id'], ),
    sa.ForeignKeyConstraint(['solicitado_por'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('demand_forecasts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('mes', sa.String(length=7), nullable=False),
    sa.Column('product_code', sa.String(length=30), nullable=False),
    sa.Column('cantidad', sa.Float(), nullable=False),
    sa.Column('canal', sa.String(length=60), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('observacion', sa.String(length=250), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['product_code'], ['products.code'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_demand_forecasts_mes'), 'demand_forecasts', ['mes'], unique=False)
    op.create_index(op.f('ix_demand_forecasts_product_code'), 'demand_forecasts', ['product_code'], unique=False)
    op.create_table('breakdowns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('severidad', sa.String(length=10), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('km', sa.Float(), nullable=True),
    sa.Column('fecha_programada', sa.Date(), nullable=True),
    sa.Column('taller', sa.String(length=120), nullable=False),
    sa.Column('costo', sa.Float(), nullable=True),
    sa.Column('solucion', sa.Text(), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('foto', sa.String(length=250), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('cierre_ts', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_breakdowns_vehicle_id'), 'breakdowns', ['vehicle_id'], unique=False)
    op.create_table('maintenance_plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False),
    sa.Column('tarea', sa.String(length=120), nullable=False),
    sa.Column('cada_km', sa.Float(), nullable=True),
    sa.Column('cada_dias', sa.Integer(), nullable=True),
    sa.Column('ultimo_km', sa.Float(), nullable=True),
    sa.Column('ultima_fecha', sa.Date(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_maintenance_plans_vehicle_id'), 'maintenance_plans', ['vehicle_id'], unique=False)
    op.create_table('sanitation_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('zone_id', sa.Integer(), nullable=True),
    sa.Column('vehicle_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('responsable', sa.String(length=120), nullable=False),
    sa.Column('producto', sa.String(length=120), nullable=False),
    sa.Column('certificado', sa.String(length=60), nullable=False),
    sa.Column('vence', sa.Date(), nullable=True),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('evidencia', sa.String(length=250), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['sanitation_zones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sanitation_logs_vehicle_id'), 'sanitation_logs', ['vehicle_id'], unique=False)
    op.create_index(op.f('ix_sanitation_logs_zone_id'), 'sanitation_logs', ['zone_id'], unique=False)
    op.add_column('liquidations', sa.Column('parcial', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('production_reports', sa.Column('motivo_estado', sa.String(length=200), nullable=False, server_default=''))
    op.add_column('production_reports', sa.Column('programa', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('route_stops', sa.Column('guia_estado', sa.String(length=20), nullable=False, server_default=''))
    op.add_column('route_stops', sa.Column('guia_estado_hist', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('route_stops', sa.Column('receptor_nombre', sa.String(length=120), nullable=False, server_default=''))
    op.add_column('route_stops', sa.Column('receptor_dni', sa.String(length=15), nullable=False, server_default=''))
    op.add_column('route_stops', sa.Column('firma_path', sa.String(length=250), nullable=False, server_default=''))
    op.add_column('sales_orders', sa.Column('aviso_atraso', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('workers', sa.Column('area', sa.String(length=40), nullable=False, server_default='Producción'))


def downgrade():
    op.drop_column('workers', 'area')
    op.drop_column('sales_orders', 'aviso_atraso')
    op.drop_column('route_stops', 'firma_path')
    op.drop_column('route_stops', 'receptor_dni')
    op.drop_column('route_stops', 'receptor_nombre')
    op.drop_column('route_stops', 'guia_estado_hist')
    op.drop_column('route_stops', 'guia_estado')
    op.drop_column('production_reports', 'programa')
    op.drop_column('production_reports', 'motivo_estado')
    op.drop_column('liquidations', 'parcial')
    op.drop_index(op.f('ix_sanitation_logs_zone_id'), table_name='sanitation_logs')
    op.drop_index(op.f('ix_sanitation_logs_vehicle_id'), table_name='sanitation_logs')
    op.drop_table('sanitation_logs')
    op.drop_index(op.f('ix_maintenance_plans_vehicle_id'), table_name='maintenance_plans')
    op.drop_table('maintenance_plans')
    op.drop_index(op.f('ix_breakdowns_vehicle_id'), table_name='breakdowns')
    op.drop_table('breakdowns')
    op.drop_index(op.f('ix_demand_forecasts_product_code'), table_name='demand_forecasts')
    op.drop_index(op.f('ix_demand_forecasts_mes'), table_name='demand_forecasts')
    op.drop_table('demand_forecasts')
    op.drop_table('move_requests')
    op.drop_table('sanitation_zones')
