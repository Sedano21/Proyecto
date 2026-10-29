"""V12 (29-oct-2026): checklist vehicular, transporte tercero y tarifario, incidencias de proveedores, presupuesto del
área, pre-guía y fecha de la guía, flujo de incidencias y documentos de mantenimiento.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-29 20:39:28.816941
"""
from alembic import op
import sqlalchemy as sa


revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('area_budgets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('area', sa.String(length=40), nullable=False),
    sa.Column('anio', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('aprobacion', sa.JSON(), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['creado_por'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('area', 'anio', name='uq_area_budget')
    )
    op.create_table('transport_rates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proveedor', sa.String(length=160), nullable=False),
    sa.Column('tipo_vehiculo', sa.String(length=60), nullable=False),
    sa.Column('origen', sa.String(length=120), nullable=False),
    sa.Column('destino', sa.String(length=120), nullable=False),
    sa.Column('precio', sa.Float(), nullable=False),
    sa.Column('vigente', sa.Boolean(), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('budget_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('budget_id', sa.Integer(), nullable=False),
    sa.Column('categoria', sa.String(length=80), nullable=False),
    sa.Column('concepto', sa.String(length=160), nullable=False),
    sa.Column('glosa', sa.String(length=80), nullable=False),
    sa.Column('placa', sa.String(length=20), nullable=False),
    sa.Column('fuente_real', sa.String(length=30), nullable=False),
    sa.Column('presupuesto', sa.JSON(), nullable=False),
    sa.Column('real', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['budget_id'], ['area_budgets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_budget_lines_budget_id'), 'budget_lines', ['budget_id'], unique=False)
    op.create_table('third_party_transports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('proveedor', sa.String(length=160), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('motivo', sa.String(length=40), nullable=False),
    sa.Column('tipo_vehiculo', sa.String(length=60), nullable=False),
    sa.Column('origen', sa.String(length=120), nullable=False),
    sa.Column('destino', sa.String(length=120), nullable=False),
    sa.Column('fecha_servicio', sa.Date(), nullable=True),
    sa.Column('toneladas', sa.Float(), nullable=True),
    sa.Column('monto', sa.Float(), nullable=True),
    sa.Column('tarifa', sa.Float(), nullable=True),
    sa.Column('motivo_sobre_tarifa', sa.Text(), nullable=False),
    sa.Column('route_id', sa.Integer(), nullable=True),
    sa.Column('aprobacion', sa.JSON(), nullable=False),
    sa.Column('factura_numero', sa.String(length=40), nullable=False),
    sa.Column('factura_archivo', sa.String(length=250), nullable=False),
    sa.Column('centro_costo', sa.String(length=60), nullable=False),
    sa.Column('tipo_servicio', sa.String(length=60), nullable=False),
    sa.Column('subtipo_servicio', sa.String(length=80), nullable=False),
    sa.Column('guia_numero', sa.String(length=40), nullable=False),
    sa.Column('guia', sa.JSON(), nullable=False),
    sa.Column('oc_numero', sa.String(length=40), nullable=False),
    sa.Column('oc_archivo', sa.String(length=250), nullable=False),
    sa.Column('finanzas', sa.JSON(), nullable=False),
    sa.Column('pagos', sa.JSON(), nullable=False),
    sa.Column('documentos', sa.JSON(), nullable=False),
    sa.Column('historial', sa.JSON(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['creado_por'], ['users.id'], ),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['route_id'], ['routes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('vehicle_checklists',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False),
    sa.Column('route_id', sa.Integer(), nullable=True),
    sa.Column('momento', sa.String(length=10), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('driver_id', sa.Integer(), nullable=True),
    sa.Column('items', sa.JSON(), nullable=False),
    sa.Column('observaciones', sa.Text(), nullable=False),
    sa.Column('km', sa.Float(), nullable=True),
    sa.Column('nn_fallidos', sa.JSON(), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('registrado_por', sa.Integer(), nullable=True),
    sa.Column('registrado_ts', sa.DateTime(), nullable=False),
    sa.Column('validado_por', sa.Integer(), nullable=True),
    sa.Column('validado_ts', sa.DateTime(), nullable=True),
    sa.Column('km_seguridad', sa.Float(), nullable=True),
    sa.Column('nota_seguridad', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], ),
    sa.ForeignKeyConstraint(['registrado_por'], ['users.id'], ),
    sa.ForeignKeyConstraint(['route_id'], ['routes.id'], ),
    sa.ForeignKeyConstraint(['validado_por'], ['users.id'], ),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vehicle_checklists_route_id'), 'vehicle_checklists', ['route_id'], unique=False)
    op.create_index(op.f('ix_vehicle_checklists_vehicle_id'), 'vehicle_checklists', ['vehicle_id'], unique=False)
    op.create_table('provider_incidents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proveedor', sa.String(length=160), nullable=False),
    sa.Column('servicio_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['servicio_id'], ['third_party_transports.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_provider_incidents_proveedor'), 'provider_incidents', ['proveedor'], unique=False)
    op.add_column('breakdowns', sa.Column('documentos', sa.JSON(), server_default='[]', nullable=False))
    op.add_column('breakdowns', sa.Column('incidencias_taller', sa.JSON(), server_default='[]', nullable=False))
    op.add_column('incidents', sa.Column('parte2', sa.JSON(), server_default='{}', nullable=False))
    op.add_column('incidents', sa.Column('flujo', sa.JSON(), server_default='{}', nullable=False))
    op.add_column('incidents', sa.Column('historial', sa.JSON(), server_default='[]', nullable=False))
    op.add_column('route_stops', sa.Column('fecha_guia', sa.Date(), nullable=True))
    op.add_column('route_stops', sa.Column('guia_sap_docentry', sa.Integer(), nullable=True))
    op.add_column('route_stops', sa.Column('guia_cambios', sa.JSON(), server_default='[]', nullable=False))
    op.add_column('sales_orders', sa.Column('preguia', sa.JSON(), server_default='{}', nullable=False))
    op.add_column('vehicle_maintenances', sa.Column('taller', sa.String(length=120), server_default='', nullable=False))
    op.add_column('vehicle_maintenances', sa.Column('documentos', sa.JSON(), server_default='[]', nullable=False))
    op.add_column('vehicle_maintenances', sa.Column('incidencias_taller', sa.JSON(), server_default='[]', nullable=False))


def downgrade():
    op.drop_column('vehicle_maintenances', 'incidencias_taller')
    op.drop_column('vehicle_maintenances', 'documentos')
    op.drop_column('vehicle_maintenances', 'taller')
    op.drop_column('sales_orders', 'preguia')
    op.drop_column('route_stops', 'guia_cambios')
    op.drop_column('route_stops', 'guia_sap_docentry')
    op.drop_column('route_stops', 'fecha_guia')
    op.drop_column('incidents', 'historial')
    op.drop_column('incidents', 'flujo')
    op.drop_column('incidents', 'parte2')
    op.drop_column('breakdowns', 'incidencias_taller')
    op.drop_column('breakdowns', 'documentos')
    op.drop_index(op.f('ix_provider_incidents_proveedor'), table_name='provider_incidents')
    op.drop_table('provider_incidents')
    op.drop_index(op.f('ix_vehicle_checklists_vehicle_id'), table_name='vehicle_checklists')
    op.drop_index(op.f('ix_vehicle_checklists_route_id'), table_name='vehicle_checklists')
    op.drop_table('vehicle_checklists')
    op.drop_table('third_party_transports')
    op.drop_index(op.f('ix_budget_lines_budget_id'), table_name='budget_lines')
    op.drop_table('budget_lines')
    op.drop_table('transport_rates')
    op.drop_table('area_budgets')
