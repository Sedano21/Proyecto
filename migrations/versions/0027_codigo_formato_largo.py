"""quality_records.codigo_formato de 30 a 80 caracteres: los códigos de algunos formatos («REG-BPM-CAL-011 (parte de
Seguridad)», «Registro del sistema (obs. demo v0.7)», «Gestión de higiene y saneamiento») superan 30 y PostgreSQL los
rechaza.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa


revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('quality_records') as b:
        b.alter_column('codigo_formato', existing_type=sa.String(length=30), type_=sa.String(length=80),
                       existing_nullable=False)


def downgrade():
    with op.batch_alter_table('quality_records') as b:
        b.alter_column('codigo_formato', existing_type=sa.String(length=80), type_=sa.String(length=30),
                       existing_nullable=False)
