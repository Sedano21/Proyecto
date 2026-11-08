"""V25 (08-nov-2026): documentos e informe de Calidad de importaciones, necesidad semanal de ingresos y chat interno.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-08 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('import_followups') as b:
        b.add_column(sa.Column('documentos', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('informe_calidad', sa.JSON(), nullable=False, server_default='{}'))
    op.create_table(
        'weekly_revenue_needs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('semana', sa.Date(), nullable=False),
        sa.Column('monto', sa.Float(), nullable=False),
        sa.Column('nota', sa.Text(), nullable=False),
        sa.Column('variacion_motivo', sa.Text(), nullable=False),
        sa.Column('historial', sa.JSON(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_weekly_revenue_needs_semana', 'weekly_revenue_needs', ['semana'], unique=True)
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('de_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('para_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('texto', sa.Text(), nullable=False),
        sa.Column('ref_url', sa.String(length=300), nullable=False),
        sa.Column('ref_titulo', sa.String(length=160), nullable=False),
        sa.Column('leido_ts', sa.DateTime(), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_chat_messages_de_id', 'chat_messages', ['de_id'])
    op.create_index('ix_chat_messages_para_id', 'chat_messages', ['para_id'])
    op.create_index('ix_chat_messages_ts', 'chat_messages', ['ts'])


def downgrade():
    op.drop_table('chat_messages')
    op.drop_table('weekly_revenue_needs')
    with op.batch_alter_table('import_followups') as b:
        b.drop_column('informe_calidad')
        b.drop_column('documentos')
