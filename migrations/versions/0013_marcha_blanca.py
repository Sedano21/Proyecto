"""marcha blanca (respuestas del 22-oct-2026): aviso de datos y política de contraseñas, observaciones de usuarios,
turnos del personal y conciliación con SAP

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-22
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

D = "Marcha blanca (respuestas del 22-oct-2026)"


def upgrade():
    op.add_column('users', sa.Column('aviso_aceptado', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('users', sa.Column('clave_ts', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('intentos_fallidos', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('bloqueado_hasta', sa.DateTime(), nullable=True))
    op.create_table('observations',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('ts', sa.DateTime(), nullable=False),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
                    sa.Column('url', sa.String(length=400), nullable=False),
                    sa.Column('pantalla', sa.String(length=200), nullable=False),
                    sa.Column('tipo', sa.String(length=20), nullable=False),
                    sa.Column('comentario', sa.Text(), nullable=False),
                    sa.Column('captura', sa.String(length=250), nullable=False),
                    sa.Column('clasificacion', sa.String(length=20), nullable=False),
                    sa.Column('estado', sa.String(length=20), nullable=False),
                    sa.Column('respuesta', sa.Text(), nullable=False),
                    sa.Column('version', sa.String(length=40), nullable=False),
                    sa.Column('atendido_por', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
                    sa.Column('atendido_ts', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id'))
    op.create_table('shifts',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('nombre', sa.String(length=80), nullable=False),
                    sa.Column('dias', sa.JSON(), nullable=False),
                    sa.Column('inicio', sa.String(length=5), nullable=False),
                    sa.Column('fin', sa.String(length=5), nullable=False),
                    sa.Column('refrigerio_min', sa.Integer(), nullable=False),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    sa.PrimaryKeyConstraint('id'))
    op.create_table('user_shifts',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('shift_id', sa.Integer(), sa.ForeignKey('shifts.id'), nullable=True),
                    sa.Column('desde', sa.Date(), nullable=False),
                    sa.Column('hasta', sa.Date(), nullable=True),
                    sa.Column('ciclo', sa.Integer(), nullable=False),
                    sa.Column('semana', sa.Integer(), nullable=False),
                    sa.Column('tipo', sa.String(length=10), nullable=False),
                    sa.Column('inicio', sa.String(length=5), nullable=False),
                    sa.Column('fin', sa.String(length=5), nullable=False),
                    sa.Column('motivo', sa.Text(), nullable=False),
                    sa.Column('creado_por', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
                    sa.Column('ts', sa.DateTime(), nullable=False),
                    sa.PrimaryKeyConstraint('id'))
    op.create_table('sap_discrepancies',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('ts', sa.DateTime(), nullable=False),
                    sa.Column('origen', sa.String(length=20), nullable=False),
                    sa.Column('area', sa.String(length=40), nullable=False),
                    sa.Column('upload_id', sa.Integer(), sa.ForeignKey('upload_batches.id'), nullable=True),
                    sa.Column('referencia', sa.String(length=80), nullable=False),
                    sa.Column('product_code', sa.String(length=40), nullable=False),
                    sa.Column('lote', sa.String(length=60), nullable=False),
                    sa.Column('almacen', sa.String(length=20), nullable=False),
                    sa.Column('campo', sa.String(length=60), nullable=False),
                    sa.Column('valor_sap', sa.String(length=200), nullable=False),
                    sa.Column('valor_modulo', sa.String(length=200), nullable=False),
                    sa.Column('detalle', sa.Text(), nullable=False),
                    sa.Column('estado', sa.String(length=15), nullable=False),
                    sa.Column('motivo', sa.Text(), nullable=False),
                    sa.Column('resuelto_por', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
                    sa.Column('resuelto_ts', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id'))
    bind = op.get_bind()
    fila = bind.execute(sa.text("SELECT valor FROM params WHERE key = 'horas_max_sin_carga'")).first()
    if fila is not None:  # tres cortes al día; se agrega la carga de despachos de SAP sin pisar lo configurado
        actual = fila[0] if isinstance(fila[0], dict) else json.loads(fila[0] or "{}")
        v = dict(actual.get("v") or {})
        v.setdefault("DESPACHOS", 8)
        bind.execute(sa.text("UPDATE params SET valor = :v WHERE key = 'horas_max_sin_carga'"), {"v": json.dumps({"v": v})})
    # usuarios existentes: la contraseña vigente cuenta desde hoy (no se bloquea a nadie por vencimiento al migrar)
    bind.execute(sa.text("UPDATE users SET clave_ts = CURRENT_TIMESTAMP WHERE clave_ts IS NULL"))


def downgrade():
    op.drop_table('sap_discrepancies')
    op.drop_table('user_shifts')
    op.drop_table('shifts')
    op.drop_table('observations')
    for c in ('bloqueado_hasta', 'intentos_fallidos', 'clave_ts', 'aviso_aceptado'):
        op.drop_column('users', c)
