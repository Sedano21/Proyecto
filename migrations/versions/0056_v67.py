"""V67 (23-nov-2026): marcha blanca del montacarguista: un lote en varias ubicaciones y varias fotos por movimiento y foto en el chat.

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-23 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_lots') as b:
        b.add_column(sa.Column('ubicaciones', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('move_requests') as b:
        b.add_column(sa.Column('fotos', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('chat_messages') as b:
        b.add_column(sa.Column('archivo', sa.String(250), nullable=False, server_default=''))


def downgrade():
    with op.batch_alter_table('chat_messages') as b:
        b.drop_column('archivo')
    with op.batch_alter_table('move_requests') as b:
        b.drop_column('fotos')
    with op.batch_alter_table('stock_lots') as b:
        b.drop_column('ubicaciones')
