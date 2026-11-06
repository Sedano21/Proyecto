"""V22 (06-nov-2026): rutas manuales y edición, traslados en ruta, capacidad real y carga habitual, varios auxiliares,
transporte por otro trabajador, pernocte, ausencias del personal, recepción de devoluciones, tickets de averías y
solicitudes a Sistemas, órdenes de trabajo de mantenimiento, bitácora de máquinas y limpieza programada.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-06 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vehicles') as b:
        b.add_column(sa.Column('capacidad_real_kg', sa.Float(), nullable=True))
        b.add_column(sa.Column('carga_habitual_kg', sa.Float(), nullable=True))
        b.add_column(sa.Column('imagen_checklist', sa.String(length=20), nullable=False, server_default=''))
    with op.batch_alter_table('drivers') as b:
        b.add_column(sa.Column('documento', sa.String(length=20), nullable=False, server_default=''))
        b.add_column(sa.Column('telefono', sa.String(length=30), nullable=False, server_default=''))
    with op.batch_alter_table('routes') as b:
        b.add_column(sa.Column('manual', sa.Boolean(), nullable=False, server_default='0'))
        b.add_column(sa.Column('auxiliares', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('transportista', sa.JSON(), nullable=False, server_default='{}'))
        b.add_column(sa.Column('peso_real_kg', sa.Float(), nullable=True))
        b.add_column(sa.Column('pernocte', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('cambios', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('workers') as b:
        b.add_column(sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_workers_user'), nullable=True))
        b.add_column(sa.Column('puesto', sa.String(length=60), nullable=False, server_default=''))
        b.add_column(sa.Column('telefono', sa.String(length=30), nullable=False, server_default=''))
    with op.batch_alter_table('sanitation_zones') as b:
        b.add_column(sa.Column('grupo', sa.String(length=60), nullable=False, server_default=''))

    op.create_table(
        'route_transfers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('route_id', sa.Integer(), sa.ForeignKey('routes.id'), nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('transfers.id'), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('peso_kg', sa.Float(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_route_transfers_route_id', 'route_transfers', ['route_id'])
    op.create_index('ix_route_transfers_transfer_id', 'route_transfers', ['transfer_id'])
    op.create_table(
        'absences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('persona_tipo', sa.String(length=10), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=160), nullable=False),
        sa.Column('area', sa.String(length=40), nullable=False),
        sa.Column('tipo', sa.String(length=25), nullable=False),
        sa.Column('desde', sa.Date(), nullable=False),
        sa.Column('hasta', sa.Date(), nullable=False),
        sa.Column('motivo', sa.String(length=250), nullable=False),
        sa.Column('archivo', sa.String(length=250), nullable=False),
        sa.Column('anulada', sa.Boolean(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_absences_persona_id', 'absences', ['persona_id'])
    op.create_index('ix_absences_desde', 'absences', ['desde'])
    op.create_index('ix_absences_hasta', 'absences', ['hasta'])
    op.create_table(
        'return_receipts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('sales_orders.id'), nullable=False),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id'), nullable=True),
        sa.Column('route_id', sa.Integer(), sa.ForeignKey('routes.id'), nullable=True),
        sa.Column('tipo', sa.String(length=10), nullable=False),
        sa.Column('guia_numero', sa.String(length=40), nullable=False),
        sa.Column('esperado', sa.JSON(), nullable=False),
        sa.Column('recibido', sa.JSON(), nullable=False),
        sa.Column('plazo', sa.Date(), nullable=False),
        sa.Column('estado', sa.String(length=12), nullable=False),
        sa.Column('observacion', sa.Text(), nullable=False),
        sa.Column('evidencias', sa.JSON(), nullable=False),
        sa.Column('recibido_por', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('recibido_ts', sa.DateTime(), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_return_receipts_order_id', 'return_receipts', ['order_id'])
    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('destino', sa.String(length=15), nullable=False),
        sa.Column('categoria', sa.String(length=40), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('lugar', sa.String(length=160), nullable=False),
        sa.Column('urgente', sa.Boolean(), nullable=False),
        sa.Column('evidencias', sa.JSON(), nullable=False),
        sa.Column('area_origen', sa.String(length=40), nullable=False),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('asignado_worker_id', sa.Integer(), sa.ForeignKey('workers.id'), nullable=True),
        sa.Column('asignado_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('work_order_id', sa.Integer(), nullable=True),
        sa.Column('solucion', sa.Text(), nullable=False),
        sa.Column('historial', sa.JSON(), nullable=False),
        sa.Column('creado_por', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('atendido_ts', sa.DateTime(), nullable=True),
        sa.Column('resuelto_ts', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'work_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tipo', sa.String(length=12), nullable=False),
        sa.Column('titulo', sa.String(length=160), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('zone_id', sa.Integer(), sa.ForeignKey('sanitation_zones.id'), nullable=True),
        sa.Column('maquina', sa.String(length=60), nullable=False),
        sa.Column('fecha_programada', sa.Date(), nullable=False),
        sa.Column('asignado_worker_id', sa.Integer(), sa.ForeignKey('workers.id'), nullable=True),
        sa.Column('asignacion', sa.String(length=12), nullable=False),
        sa.Column('estado', sa.String(length=12), nullable=False),
        sa.Column('origen', sa.String(length=12), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=True),
        sa.Column('fotos_antes', sa.JSON(), nullable=False),
        sa.Column('fotos_despues', sa.JSON(), nullable=False),
        sa.Column('repuestos', sa.JSON(), nullable=False),
        sa.Column('costo', sa.Float(), nullable=True),
        sa.Column('observacion', sa.Text(), nullable=False),
        sa.Column('con_calidad', sa.Boolean(), nullable=False),
        sa.Column('avisos', sa.JSON(), nullable=False),
        sa.Column('inicio_ts', sa.DateTime(), nullable=True),
        sa.Column('fin_ts', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_work_orders_zone_id', 'work_orders', ['zone_id'])
    op.create_index('ix_work_orders_fecha_programada', 'work_orders', ['fecha_programada'])
    op.create_table(
        'machine_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('maquina', sa.String(length=60), nullable=False),
        sa.Column('tipo', sa.String(length=15), nullable=False),
        sa.Column('detalle', sa.Text(), nullable=False),
        sa.Column('parametros', sa.JSON(), nullable=False),
        sa.Column('pieza', sa.String(length=120), nullable=False),
        sa.Column('costo', sa.Float(), nullable=True),
        sa.Column('evidencias', sa.JSON(), nullable=False),
        sa.Column('proxima', sa.Date(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_machine_logs_maquina', 'machine_logs', ['maquina'])
    op.create_table(
        'cleaning_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('worker_id', sa.Integer(), sa.ForeignKey('workers.id'), nullable=False),
        sa.Column('zone_id', sa.Integer(), sa.ForeignKey('sanitation_zones.id'), nullable=False),
        sa.Column('veces', sa.Integer(), nullable=False),
        sa.Column('turno', sa.String(length=20), nullable=False),
        sa.Column('checks', sa.JSON(), nullable=False),
        sa.Column('nota', sa.String(length=250), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cleaning_assignments_fecha', 'cleaning_assignments', ['fecha'])
    op.create_index('ix_cleaning_assignments_worker_id', 'cleaning_assignments', ['worker_id'])
    op.create_index('ix_cleaning_assignments_zone_id', 'cleaning_assignments', ['zone_id'])


def downgrade():
    for t in ('cleaning_assignments', 'machine_logs', 'work_orders', 'tickets', 'return_receipts', 'absences',
              'route_transfers'):
        op.drop_table(t)
    with op.batch_alter_table('sanitation_zones') as b:
        b.drop_column('grupo')
    with op.batch_alter_table('workers') as b:
        for c in ('telefono', 'puesto', 'user_id'):
            b.drop_column(c)
    with op.batch_alter_table('routes') as b:
        for c in ('cambios', 'pernocte', 'peso_real_kg', 'transportista', 'auxiliares', 'manual'):
            b.drop_column(c)
    with op.batch_alter_table('drivers') as b:
        for c in ('telefono', 'documento'):
            b.drop_column(c)
    with op.batch_alter_table('vehicles') as b:
        for c in ('imagen_checklist', 'carga_habitual_kg', 'capacidad_real_kg'):
            b.drop_column(c)
