"""ronda del 23-oct-2026: reuniones con Producción y Comercial (Finanzas, expediente, margen, objetivos,
incentivos, oportunidades, GS1, parte en línea con OEE, personal y asistencia)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-23 15:59:44.819422
"""
from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('product_gtins',
    sa.Column('gtin', sa.String(length=20), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('product_code', sa.String(length=40), nullable=False),
    sa.Column('marca', sa.String(length=80), nullable=False),
    sa.Column('descripcion', sa.String(length=250), nullable=False),
    sa.Column('envase', sa.String(length=60), nullable=False),
    sa.Column('contenido', sa.String(length=30), nullable=False),
    sa.Column('unidad', sa.String(length=20), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('gtin')
    )
    op.create_index(op.f('ix_product_gtins_product_code'), 'product_gtins', ['product_code'], unique=False)
    op.create_table('workers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=160), nullable=False),
    sa.Column('documento', sa.String(length=20), nullable=False),
    sa.Column('linea', sa.String(length=20), nullable=False),
    sa.Column('sublinea', sa.String(length=40), nullable=False),
    sa.Column('externo', sa.Boolean(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('attendance',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('worker_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('observacion', sa.String(length=250), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('worker_id', 'fecha', name='uq_attendance')
    )
    op.create_index(op.f('ix_attendance_fecha'), 'attendance', ['fecha'], unique=False)
    op.create_index(op.f('ix_attendance_worker_id'), 'attendance', ['worker_id'], unique=False)
    op.create_table('incentive_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('canal', sa.String(length=60), nullable=False),
    sa.Column('vendedor_id', sa.Integer(), nullable=True),
    sa.Column('base', sa.String(length=15), nullable=False),
    sa.Column('pct', sa.Float(), nullable=False),
    sa.Column('cumplimiento_min_pct', sa.Float(), nullable=True),
    sa.Column('tope', sa.Float(), nullable=True),
    sa.Column('desde', sa.Date(), nullable=True),
    sa.Column('hasta', sa.Date(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['vendedor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sales_targets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('mes', sa.String(length=7), nullable=False),
    sa.Column('alcance', sa.String(length=10), nullable=False),
    sa.Column('clave', sa.String(length=120), nullable=False),
    sa.Column('soles', sa.Float(), nullable=False),
    sa.Column('kg', sa.Float(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('mes', 'alcance', 'clave', name='uq_target')
    )
    op.create_index(op.f('ix_sales_targets_mes'), 'sales_targets', ['mes'], unique=False)
    op.create_table('margin_investments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('mes', sa.String(length=7), nullable=False),
    sa.Column('concepto', sa.String(length=60), nullable=False),
    sa.Column('monto', sa.Float(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_margin_investments_customer_id'), 'margin_investments', ['customer_id'], unique=False)
    op.create_index(op.f('ix_margin_investments_mes'), 'margin_investments', ['mes'], unique=False)
    op.create_table('opportunities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('vendedor_id', sa.Integer(), nullable=True),
    sa.Column('titulo', sa.String(length=200), nullable=False),
    sa.Column('productos', sa.Text(), nullable=False),
    sa.Column('proyeccion_mensual', sa.Float(), nullable=True),
    sa.Column('proyeccion_kg', sa.Float(), nullable=True),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('tipo', sa.String(length=15), nullable=False),
    sa.Column('motivo_cierre', sa.Text(), nullable=False),
    sa.Column('creado_ts', sa.DateTime(), nullable=False),
    sa.Column('cerrado_ts', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['vendedor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_opportunities_customer_id'), 'opportunities', ['customer_id'], unique=False)
    op.create_table('customer_actions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('opportunity_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('gasto', sa.Float(), nullable=True),
    sa.Column('resultado', sa.Text(), nullable=False),
    sa.Column('proxima_accion', sa.Date(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_actions_customer_id'), 'customer_actions', ['customer_id'], unique=False)
    op.create_table('customer_invoices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=15), nullable=False),
    sa.Column('numero', sa.String(length=40), nullable=False),
    sa.Column('referencia', sa.String(length=40), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('vencimiento', sa.Date(), nullable=True),
    sa.Column('moneda', sa.String(length=10), nullable=False),
    sa.Column('monto', sa.Float(), nullable=False),
    sa.Column('saldo', sa.Float(), nullable=False),
    sa.Column('estado', sa.String(length=12), nullable=False),
    sa.Column('archivo', sa.String(length=250), nullable=False),
    sa.Column('origen', sa.String(length=20), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['sales_orders.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tipo', 'numero', name='uq_invoice_tipo_numero')
    )
    op.create_index(op.f('ix_customer_invoices_customer_id'), 'customer_invoices', ['customer_id'], unique=False)
    op.create_index(op.f('ix_customer_invoices_numero'), 'customer_invoices', ['numero'], unique=False)
    op.create_table('order_attachments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('archivo', sa.String(length=250), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['sales_orders.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_attachments_order_id'), 'order_attachments', ['order_id'], unique=False)
    op.create_table('quotes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.String(length=30), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('opportunity_id', sa.Integer(), nullable=True),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('vigencia', sa.Date(), nullable=True),
    sa.Column('lineas', sa.JSON(), nullable=False),
    sa.Column('total', sa.Float(), nullable=False),
    sa.Column('estado', sa.String(length=12), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['sales_orders.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('numero')
    )
    op.create_index(op.f('ix_quotes_customer_id'), 'quotes', ['customer_id'], unique=False)
    op.create_table('customer_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=True),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('monto', sa.Float(), nullable=False),
    sa.Column('medio', sa.String(length=40), nullable=False),
    sa.Column('operacion', sa.String(length=60), nullable=False),
    sa.Column('archivo', sa.String(length=250), nullable=False),
    sa.Column('estado', sa.String(length=12), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('confirmado_por', sa.Integer(), nullable=True),
    sa.Column('confirmado_ts', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['confirmado_por'], ['users.id'], ),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['invoice_id'], ['customer_invoices.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_payments_customer_id'), 'customer_payments', ['customer_id'], unique=False)
    op.add_column('customer_sites', sa.Column('ubigeo', sa.String(length=10), nullable=False, server_default=''))
    op.add_column('customers', sa.Column('ubigeo', sa.String(length=10), nullable=False, server_default=''))
    op.add_column('customers', sa.Column('condicion_pago', sa.String(length=10), nullable=False, server_default=''))
    op.add_column('customers', sa.Column('credito_monto', sa.Float(), nullable=True))
    op.add_column('customers', sa.Column('credito_dias', sa.Integer(), nullable=True))
    op.add_column('customers', sa.Column('condicion_estado', sa.String(length=15), nullable=False, server_default='APROBADA'))
    op.add_column('customers', sa.Column('condicion_docs', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('customers', sa.Column('condicion_historial', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('customers', sa.Column('es_prospecto', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('customers', sa.Column('convertido', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('liquidations', sa.Column('horas', sa.Float(), nullable=True))
    op.add_column('liquidations', sa.Column('operarios', sa.Integer(), nullable=True))
    op.add_column('liquidations', sa.Column('mp_kg', sa.Float(), nullable=True))
    op.add_column('liquidations', sa.Column('bloqueo', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('market_prices', sa.Column('estado', sa.String(length=12), nullable=False, server_default='APROBADO'))
    with op.batch_alter_table('market_prices') as b:  # modo lote: SQLite no altera restricciones en sitio
        b.add_column(sa.Column('aprobado_por', sa.Integer(), nullable=True))
        b.create_foreign_key('fk_market_prices_aprobado_por', 'users', ['aprobado_por'], ['id'])
    op.add_column('market_prices', sa.Column('aprobado_ts', sa.DateTime(), nullable=True))
    op.add_column('production_plans', sa.Column('cambio_pendiente', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('production_reports', sa.Column('maquina', sa.String(length=30), nullable=False, server_default=''))
    op.add_column('production_reports', sa.Column('maquinista', sa.String(length=120), nullable=False, server_default=''))
    op.add_column('production_reports', sa.Column('ean', sa.String(length=20), nullable=False, server_default=''))
    op.add_column('production_reports', sa.Column('ean_ok', sa.Boolean(), nullable=True))
    op.add_column('production_reports', sa.Column('lote_pt', sa.String(length=60), nullable=False, server_default=''))
    op.add_column('production_reports', sa.Column('fv_pt', sa.Date(), nullable=True))
    op.add_column('production_reports', sa.Column('fv_mp', sa.Date(), nullable=True))
    op.add_column('production_reports', sa.Column('und_paquete', sa.Float(), nullable=True))
    op.add_column('production_reports', sa.Column('sacos', sa.Float(), nullable=True))
    op.add_column('production_reports', sa.Column('peso_saco_kg', sa.Float(), nullable=True))
    op.add_column('production_reports', sa.Column('saldo_mp_kg', sa.Float(), nullable=True))
    op.add_column('production_reports', sa.Column('refrigerio_min', sa.Integer(), nullable=True))
    op.add_column('production_reports', sa.Column('pallets', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('production_reports', sa.Column('colaboradores', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('production_reports', sa.Column('pausas', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('production_reports', sa.Column('defectos', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('production_reports', sa.Column('indicadores', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('production_reports', sa.Column('inicio_ts', sa.DateTime(), nullable=True))
    op.add_column('production_reports', sa.Column('fin_ts', sa.DateTime(), nullable=True))
    op.add_column('production_reports', sa.Column('bloqueo', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('products', sa.Column('foto', sa.String(length=250), nullable=False, server_default=''))
    op.add_column('sales_orders', sa.Column('oc_archivo', sa.String(length=250), nullable=False, server_default=''))
    op.add_column('sales_orders', sa.Column('oc_numero', sa.String(length=60), nullable=False, server_default=''))
    op.add_column('sales_orders', sa.Column('compromiso', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('sales_orders', sa.Column('cancelacion_motivo', sa.Text(), nullable=False, server_default=''))


def downgrade():
    op.drop_column('sales_orders', 'cancelacion_motivo')
    op.drop_column('sales_orders', 'compromiso')
    op.drop_column('sales_orders', 'oc_numero')
    op.drop_column('sales_orders', 'oc_archivo')
    op.drop_column('products', 'foto')
    op.drop_column('production_reports', 'bloqueo')
    op.drop_column('production_reports', 'fin_ts')
    op.drop_column('production_reports', 'inicio_ts')
    op.drop_column('production_reports', 'indicadores')
    op.drop_column('production_reports', 'defectos')
    op.drop_column('production_reports', 'pausas')
    op.drop_column('production_reports', 'colaboradores')
    op.drop_column('production_reports', 'pallets')
    op.drop_column('production_reports', 'refrigerio_min')
    op.drop_column('production_reports', 'saldo_mp_kg')
    op.drop_column('production_reports', 'peso_saco_kg')
    op.drop_column('production_reports', 'sacos')
    op.drop_column('production_reports', 'und_paquete')
    op.drop_column('production_reports', 'fv_mp')
    op.drop_column('production_reports', 'fv_pt')
    op.drop_column('production_reports', 'lote_pt')
    op.drop_column('production_reports', 'ean_ok')
    op.drop_column('production_reports', 'ean')
    op.drop_column('production_reports', 'maquinista')
    op.drop_column('production_reports', 'maquina')
    op.drop_column('production_plans', 'cambio_pendiente')
    op.drop_column('market_prices', 'aprobado_ts')
    with op.batch_alter_table('market_prices') as b:
        b.drop_constraint('fk_market_prices_aprobado_por', type_='foreignkey')
        b.drop_column('aprobado_por')
    op.drop_column('market_prices', 'estado')
    op.drop_column('liquidations', 'bloqueo')
    op.drop_column('liquidations', 'mp_kg')
    op.drop_column('liquidations', 'operarios')
    op.drop_column('liquidations', 'horas')
    op.drop_column('customers', 'convertido')
    op.drop_column('customers', 'es_prospecto')
    op.drop_column('customers', 'condicion_historial')
    op.drop_column('customers', 'condicion_docs')
    op.drop_column('customers', 'condicion_estado')
    op.drop_column('customers', 'credito_dias')
    op.drop_column('customers', 'credito_monto')
    op.drop_column('customers', 'condicion_pago')
    op.drop_column('customers', 'ubigeo')
    op.drop_column('customer_sites', 'ubigeo')
    op.drop_index(op.f('ix_customer_payments_customer_id'), table_name='customer_payments')
    op.drop_table('customer_payments')
    op.drop_index(op.f('ix_quotes_customer_id'), table_name='quotes')
    op.drop_table('quotes')
    op.drop_index(op.f('ix_order_attachments_order_id'), table_name='order_attachments')
    op.drop_table('order_attachments')
    op.drop_index(op.f('ix_customer_invoices_numero'), table_name='customer_invoices')
    op.drop_index(op.f('ix_customer_invoices_customer_id'), table_name='customer_invoices')
    op.drop_table('customer_invoices')
    op.drop_index(op.f('ix_customer_actions_customer_id'), table_name='customer_actions')
    op.drop_table('customer_actions')
    op.drop_index(op.f('ix_opportunities_customer_id'), table_name='opportunities')
    op.drop_table('opportunities')
    op.drop_index(op.f('ix_margin_investments_mes'), table_name='margin_investments')
    op.drop_index(op.f('ix_margin_investments_customer_id'), table_name='margin_investments')
    op.drop_table('margin_investments')
    op.drop_index(op.f('ix_sales_targets_mes'), table_name='sales_targets')
    op.drop_table('sales_targets')
    op.drop_table('incentive_rules')
    op.drop_index(op.f('ix_attendance_worker_id'), table_name='attendance')
    op.drop_index(op.f('ix_attendance_fecha'), table_name='attendance')
    op.drop_table('attendance')
    op.drop_table('workers')
    op.drop_index(op.f('ix_product_gtins_product_code'), table_name='product_gtins')
    op.drop_table('product_gtins')
