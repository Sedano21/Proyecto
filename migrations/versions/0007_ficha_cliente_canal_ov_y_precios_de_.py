"""ficha cliente canal ov y precios de mercado por origen

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14 23:28:47.127823
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('customers') as b:
        b.add_column(sa.Column('celulares', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('correos', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('tiene_contrato', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('contrato_archivo', sa.String(length=200), nullable=False, server_default=''))
        b.add_column(sa.Column('certificaciones', sa.Text(), nullable=False, server_default=''))
        b.add_column(sa.Column('penalidades', sa.Text(), nullable=False, server_default=''))
        b.add_column(sa.Column('vendedor_id', sa.Integer(), nullable=True))
        b.create_foreign_key('fk_customers_vendedor', 'users', ['vendedor_id'], ['id'])
    op.add_column('market_prices', sa.Column('categoria', sa.String(length=20), nullable=False, server_default='MERCADO'))
    op.add_column('market_prices', sa.Column('competidor', sa.String(length=160), nullable=False, server_default=''))
    op.add_column('market_prices', sa.Column('presentacion', sa.String(length=60), nullable=False, server_default=''))
    op.add_column('market_prices', sa.Column('product_code', sa.String(length=40), nullable=False, server_default=''))
    op.execute("UPDATE market_prices SET categoria='IMPORTACION' WHERE tipo_precio='IMPORTACION'")
    op.add_column('sales_orders', sa.Column('canal_precio', sa.String(length=60), nullable=False, server_default=''))
    # correo existente como primer correo de la lista
    expr = "'[\"' || correo || '\"]'"
    if op.get_bind().dialect.name == "postgresql":
        expr = f"CAST({expr} AS JSON)"
    op.execute(f"UPDATE customers SET correos = {expr} WHERE correo IS NOT NULL AND correo <> ''")


def downgrade():
    op.drop_column('sales_orders', 'canal_precio')
    for c in ('product_code', 'presentacion', 'competidor', 'categoria'):
        op.drop_column('market_prices', c)
    with op.batch_alter_table('customers') as b:
        b.drop_constraint('fk_customers_vendedor', type_='foreignkey')
        for c in ('vendedor_id', 'penalidades', 'certificaciones', 'contrato_archivo', 'tiene_contrato', 'correos', 'celulares'):
            b.drop_column(c)
