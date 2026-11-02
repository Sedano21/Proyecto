"""V17 (02-nov-2026): entrega o recojo de la OV, quién reporta en un grupo de picking, cliente relacionado en la
solicitud a Producción y validación del conteo físico por el Jefe de Logística.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-02 20:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sales_orders', sa.Column('modalidad_entrega', sa.String(length=10), nullable=False, server_default='ENTREGA'))
    op.add_column('picking_tasks', sa.Column('reportantes', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('physical_counts', sa.Column('validacion', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('production_requests') as b:
        b.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
        b.create_foreign_key('fk_production_requests_customer', 'customers', ['customer_id'], ['id'])


def downgrade():
    with op.batch_alter_table('production_requests') as b:
        b.drop_constraint('fk_production_requests_customer', type_='foreignkey')
        b.drop_column('customer_id')
    op.drop_column('physical_counts', 'validacion')
    op.drop_column('picking_tasks', 'reportantes')
    op.drop_column('sales_orders', 'modalidad_entrega')
