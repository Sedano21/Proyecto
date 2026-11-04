"""V20 (04-nov-2026): dispositivos con notificaciones push (Web Push).

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-04 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False, unique=True),
        sa.Column('p256dh', sa.String(length=200), nullable=False),
        sa.Column('auth', sa.String(length=100), nullable=False),
        sa.Column('dispositivo', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('creado_ts', sa.DateTime(), nullable=False),
        sa.Column('ultimo_envio_ts', sa.DateTime(), nullable=True),
        sa.Column('fallos', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id'])


def downgrade():
    op.drop_index('ix_push_subscriptions_user_id', 'push_subscriptions')
    op.drop_table('push_subscriptions')
