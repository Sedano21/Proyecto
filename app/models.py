"""Modelo de datos del Módulo de Operaciones.

Cada tabla indica en su docstring la sección del Informe Funcional (IF) o el
formato operativo que la origina. Ver docs/MODELO_DATOS.md.
"""
from datetime import datetime, date

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now().replace(microsecond=0)


# ---------------------------------------------------------------------------
# Seguridad, roles, auditoría, configuración (IF §15, §16, §19)
# ---------------------------------------------------------------------------
class Role(Base):
    """Rol/perfil (IF §15)."""
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    area: Mapped[str] = mapped_column(String(40))
    fuente: Mapped[str] = mapped_column(String(200), default="")
    observacion: Mapped[str] = mapped_column(Text, default="")


class Permission(Base):
    """Permiso atómico; tipo = consulta/edicion/aprobacion/administracion (IF §19)."""
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    modulo: Mapped[str] = mapped_column(String(40))
    tipo: Mapped[str] = mapped_column(String(20))


class RolePermission(Base):
    """Matriz rol-permiso. origen: DEFINIDO (regla expresa) o PROPUESTO (derivado del alcance por área, requiere validación)."""
    __tablename__ = "role_permissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    role_code: Mapped[str] = mapped_column(ForeignKey("roles.code"))
    perm_code: Mapped[str] = mapped_column(ForeignKey("permissions.code"))
    origen: Mapped[str] = mapped_column(String(12), default="PROPUESTO")
    fuente: Mapped[str] = mapped_column(String(200), default="")
    __table_args__ = (UniqueConstraint("role_code", "perm_code"),)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), default="")
    role_code: Mapped[str] = mapped_column(ForeignKey("roles.code"))
    password_hash: Mapped[str] = mapped_column(String(255))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, default=False)
    role = relationship("Role")


class AuditLog(Base):
    """Trazabilidad de cambios, aprobaciones, cargas, etc. (IF §2, §19)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accion: Mapped[str] = mapped_column(String(80))
    entidad: Mapped[str] = mapped_column(String(60))
    entidad_id: Mapped[str] = mapped_column(String(60), default="")
    detalle: Mapped[dict] = mapped_column(JSON, default=dict)
    user = relationship("User")


class Param(Base):
    """Parámetro configurable (IF §16). estado: DEFINIDO / PROPUESTO / PENDIENTE / DEMO."""
    __tablename__ = "params"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSON)  # {"v": valor}
    tipo: Mapped[str] = mapped_column(String(20))  # int, float, bool, str, list, dict
    grupo: Mapped[str] = mapped_column(String(40))
    descripcion: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(12))
    fuente: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)


class ParamHistory(Base):
    """Versiones de configuración (IF §19 'Guardar versiones de listas y configuraciones')."""
    __tablename__ = "param_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    valor: Mapped[dict] = mapped_column(JSON)
    estado: Mapped[str] = mapped_column(String(12))
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


# ---------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------
class Warehouse(Base):
    """Almacén (IF §6.2). uso: PT / MP_INSUMOS / ALTERNATIVO / OTRO."""
    __tablename__ = "warehouses"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)  # código SAP (ALM-001, EXT-001...)
    nombre: Mapped[str] = mapped_column(String(80))  # nombre operativo (1560, 767...)
    uso: Mapped[str] = mapped_column(String(20), default="OTRO")
    prioridad: Mapped[int] = mapped_column(Integer, default=99)
    reservable: Mapped[bool] = mapped_column(Boolean, default=False)
    fuente: Mapped[str] = mapped_column(String(200), default="")
    observacion: Mapped[str] = mapped_column(Text, default="")


class Product(Base):
    """Artículo (formato TABLA_DATA de 'PCP 2026 - J.xlsm' y columnas de OVS/BOM)."""
    __tablename__ = "products"
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(200))
    um: Mapped[str] = mapped_column(String(20), default="UNIDAD")  # UNIDAD / KILOGRAMO
    peso_kg: Mapped[float | None] = mapped_column(Float, nullable=True)  # PPB: peso por unidad
    tipo: Mapped[str] = mapped_column(String(10), default="")  # PT, MP, GR, EN, SU, ...
    calidad: Mapped[str] = mapped_column(String(30), default="")  # SUPERIOR / EXTRA
    maquina: Mapped[str] = mapped_column(String(30), default="")  # MAQ (E2000, T1000...)
    marca: Mapped[str] = mapped_column(String(60), default="")
    familia: Mapped[str] = mapped_column(String(60), default="")
    subfamilia: Mapped[str] = mapped_column(String(60), default="")
    producto_base: Mapped[str] = mapped_column(String(120), default="")  # p.ej. ARVEJA VERDE PARTIDA
    presentacion: Mapped[str] = mapped_column(String(40), default="")
    categoria_reposicion: Mapped[str] = mapped_column(String(60), default="")  # vincula plazos de compra
    grupo_humedad: Mapped[str] = mapped_column(String(60), default="")  # PCC1
    stock_minimo: Mapped[float | None] = mapped_column(Float, nullable=True)
    periodo_analisis_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    margen_seguridad_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    merma_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    tiempo_max_almacen_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origen: Mapped[str] = mapped_column(String(40), default="")


class LeadTime(Base):
    """Plazos de reposición comunicados por Compras (IF §7) – días naturales."""
    __tablename__ = "lead_times"
    id: Mapped[int] = mapped_column(primary_key=True)
    categoria: Mapped[str] = mapped_column(String(60))
    dias_min: Mapped[int] = mapped_column(Integer)
    dias_max: Mapped[int] = mapped_column(Integer)
    mes_desde: Mapped[int | None] = mapped_column(Integer, nullable=True)  # excepción estacional
    mes_hasta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    descripcion: Mapped[str] = mapped_column(String(200), default="")
    fuente: Mapped[str] = mapped_column(String(200), default="")


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    ruc: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    grupo: Mapped[str] = mapped_column(String(60), default="")
    direccion: Mapped[str] = mapped_column(String(250), default="")
    distrito: Mapped[str] = mapped_column(String(80), default="")
    provincia: Mapped[str] = mapped_column(String(80), default="")
    horario_recepcion: Mapped[str] = mapped_column(String(60), default="")  # p.ej. 08:00-12:00
    requiere_cita: Mapped[bool] = mapped_column(Boolean, default=False)
    vida_util_min_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)  # condición del cliente


# ---------------------------------------------------------------------------
# Stock, cargas y conteos (IF §6)
# ---------------------------------------------------------------------------
STOCK_ESTADOS = ["DISPONIBLE", "RESERVADO", "NO_UTILIZABLE", "DANADO", "EN_FUMIGACION", "PENDIENTE_REVISION"]


class StockLot(Base):
    """Existencia por artículo/lote/almacén (formato STOCK_LOTE de SAP)."""
    __tablename__ = "stock_lots"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    warehouse_code: Mapped[str] = mapped_column(ForeignKey("warehouses.code"))
    lote: Mapped[str] = mapped_column(String(60))
    cantidad: Mapped[float] = mapped_column(Float, default=0)
    fecha_venc: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fab: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_admision: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Estado de uso (IF §6.1). RESERVADO se deriva de reservas activas; el estado físico se guarda aquí.
    estado: Mapped[str] = mapped_column(String(24), default="DISPONIBLE")
    estado_anterior: Mapped[str] = mapped_column(String(24), default="")
    motivo_estado: Mapped[str] = mapped_column(Text, default="")
    verificado: Mapped[bool] = mapped_column(Boolean, default=False)
    cantidad_verificada: Mapped[float | None] = mapped_column(Float, nullable=True)
    fecha_verificacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    origen: Mapped[str] = mapped_column(String(60), default="")
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    product = relationship("Product")
    warehouse = relationship("Warehouse")
    reservations = relationship("Reservation", back_populates="lot")
    # Un mismo lote SAP puede tener segmentos en distintos estados (p.ej. parte devuelta pendiente de revisión).
    __table_args__ = (UniqueConstraint("product_code", "warehouse_code", "lote", "estado", name="uq_lote_estado"),)


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    ov_line_id: Mapped[int] = mapped_column(ForeignKey("sales_order_lines.id"))
    lot_id: Mapped[int] = mapped_column(ForeignKey("stock_lots.id"))
    cantidad: Mapped[float] = mapped_column(Float)
    estado: Mapped[str] = mapped_column(String(12), default="ACTIVA")  # ACTIVA / LIBERADA / CONSUMIDA
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    motivo_liberacion: Mapped[str] = mapped_column(String(200), default="")
    lot = relationship("StockLot", back_populates="reservations")
    line = relationship("SalesOrderLine", back_populates="reservations")


class UploadBatch(Base):
    """Carga de archivo con validación previa (IF §6.4, §8.1, §19).
    tipo: STOCK, BOM, OV, LIQUIDACION, PRODUCTOS, SALIDAS.
    estado: VALIDADO_CON_ERRORES / LISTO / CONFIRMADO / DESCARTADO."""
    __tablename__ = "upload_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))
    archivo: Mapped[str] = mapped_column(String(250))
    hoja: Mapped[str] = mapped_column(String(80), default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    estado: Mapped[str] = mapped_column(String(30), default="LISTO")
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)
    errores_generales: Mapped[list] = mapped_column(JSON, default=list)
    opciones: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rows = relationship("UploadRow", back_populates="batch", order_by="UploadRow.fila",
                        cascade="all, delete-orphan")
    user = relationship("User", foreign_keys=[user_id])


class UploadRow(Base):
    __tablename__ = "upload_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id"))
    fila: Mapped[int] = mapped_column(Integer)
    datos: Mapped[dict] = mapped_column(JSON)
    errores: Mapped[list] = mapped_column(JSON, default=list)
    advertencias: Mapped[list] = mapped_column(JSON, default=list)
    excluida: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_exclusion: Mapped[str] = mapped_column(String(250), default="")
    editada: Mapped[bool] = mapped_column(Boolean, default=False)
    batch = relationship("UploadBatch", back_populates="rows")


class PhysicalCount(Base):
    """Conteo físico periódico (IF §6.3/§6.4; formato 'Inven. bobinas 1524.xlsx')."""
    __tablename__ = "physical_counts"
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_code: Mapped[str] = mapped_column(ForeignKey("warehouses.code"))
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    estado: Mapped[str] = mapped_column(String(20), default="ABIERTO")  # ABIERTO / CERRADO
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    observacion: Mapped[str] = mapped_column(Text, default="")
    lines = relationship("PhysicalCountLine", back_populates="count", cascade="all, delete-orphan")
    warehouse = relationship("Warehouse")


class PhysicalCountLine(Base):
    __tablename__ = "physical_count_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    count_id: Mapped[int] = mapped_column(ForeignKey("physical_counts.id"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lots.id"), nullable=True)
    product_code: Mapped[str] = mapped_column(String(30))
    lote: Mapped[str] = mapped_column(String(60), default="")
    sap: Mapped[float] = mapped_column(Float, default=0)
    peso_unitario: Mapped[float | None] = mapped_column(Float, nullable=True)
    conteo: Mapped[float | None] = mapped_column(Float, nullable=True)
    fisico: Mapped[float | None] = mapped_column(Float, nullable=True)
    faltante: Mapped[float] = mapped_column(Float, default=0)
    sobrante: Mapped[float] = mapped_column(Float, default=0)
    comentario: Mapped[str] = mapped_column(String(250), default="")
    count = relationship("PhysicalCount", back_populates="lines")


class SalesHistory(Base):
    """Historial de salidas/ventas para análisis de reposición (formato hoja 'Qy' de Rotación de inventario)."""
    __tablename__ = "sales_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(30), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    cantidad: Mapped[float] = mapped_column(Float)
    documento: Mapped[str] = mapped_column(String(40), default="")
    origen: Mapped[str] = mapped_column(String(30), default="CARGA")  # CARGA / DESPACHO / CONSUMO_PRODUCCION
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)


# ---------------------------------------------------------------------------
# Órdenes de venta (IF §5, §6.3)
# ---------------------------------------------------------------------------
class SalesOrder(Base):
    __tablename__ = "sales_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vendedor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    vendedor_nombre: Mapped[str] = mapped_column(String(120), default="")
    fecha_emision: Mapped[date] = mapped_column(Date, default=date.today)
    fecha_compromiso: Mapped[date] = mapped_column(Date)  # fecha comprometida de despacho
    urgente: Mapped[bool] = mapped_column(Boolean, default=False)
    direccion: Mapped[str] = mapped_column(String(250), default="")
    distrito: Mapped[str] = mapped_column(String(80), default="")
    hora_cita: Mapped[str] = mapped_column(String(20), default="")
    cita_confirmada: Mapped[bool] = mapped_column(Boolean, default=False)
    comentarios: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(24), default="REGISTRADA")
    estado_stock: Mapped[str] = mapped_column(String(20), default="SIN_EVALUAR")  # COMPLETA / INCOMPLETA / SIN_STOCK
    cobertura_unidades: Mapped[float] = mapped_column(Float, default=0)
    cobertura_lineas: Mapped[float] = mapped_column(Float, default=0)
    decision_parcial: Mapped[str] = mapped_column(String(20), default="")  # "" / PENDIENTE / APROBADA / RECHAZADA
    motivo_detencion: Mapped[str] = mapped_column(String(250), default="")
    origen: Mapped[str] = mapped_column(String(20), default="MODULO")  # MODULO / CARGA_SAP
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    creado_ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    evaluado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prep_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prep_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    salida_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entrega_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    corte: Mapped[str] = mapped_column(String(10), default="")
    alerta80_emitida: Mapped[bool] = mapped_column(Boolean, default=False)
    # Despacho parcial (decisión Q3, 11-oct-2026): aprobación de Gerencia de Operaciones y Jefatura de Logística;
    # el saldo no despachado se reprograma en una OV de saldo.
    parcial_aprobaciones: Mapped[dict] = mapped_column(JSON, default=dict)
    fecha_saldo: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    completa_notificada: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_picking_validado: Mapped[bool] = mapped_column(Boolean, default=False)
    customer = relationship("Customer")
    lines = relationship("SalesOrderLine", back_populates="order", cascade="all, delete-orphan",
                         order_by="SalesOrderLine.id")
    parent = relationship("SalesOrder", remote_side="SalesOrder.id")


class SalesOrderLine(Base):
    __tablename__ = "sales_order_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"))
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    cantidad: Mapped[float] = mapped_column(Float)
    precio_unitario: Mapped[float] = mapped_column(Float, default=0)
    preparado: Mapped[float] = mapped_column(Float, default=0)
    despachado: Mapped[float] = mapped_column(Float, default=0)
    entregado: Mapped[float] = mapped_column(Float, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    order = relationship("SalesOrder", back_populates="lines")
    product = relationship("Product")
    reservations = relationship("Reservation", back_populates="line")


class OVChangeRequest(Base):
    """Modificación de OV por Asistente de Ventas que requiere autorización (IF §5)."""
    __tablename__ = "ov_change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"))
    solicitado_por: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    motivo: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE")
    resuelto_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resuelto_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    order = relationship("SalesOrder")


class OVDecision(Base):
    """Decisiones humanas ante faltantes (IF §4.5, §5, §6.3): despacho parcial, renegociación de fecha,
    cambio de producto, uso de almacén alternativo."""
    __tablename__ = "ov_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"))
    tipo: Mapped[str] = mapped_column(String(30))
    estado: Mapped[str] = mapped_column(String(12), default="REGISTRADA")
    detalle: Mapped[dict] = mapped_column(JSON, default=dict)
    comentario: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User")


# ---------------------------------------------------------------------------
# Traslados (IF §6.2, §13)
# ---------------------------------------------------------------------------
class Transfer(Base):
    __tablename__ = "transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    origen_lot_id: Mapped[int] = mapped_column(ForeignKey("stock_lots.id"))
    destino_code: Mapped[str] = mapped_column(ForeignKey("warehouses.code"))
    cantidad: Mapped[float] = mapped_column(Float)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="SOLICITADO")
    # SOLICITADO / AUTORIZADO / RECHAZADO / EN_TRANSITO / RECIBIDO / RECIBIDO_CON_DIFERENCIA
    solicitado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    autorizado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    autorizado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    salida_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    salida_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recibido_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recibido_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cantidad_recibida: Mapped[float | None] = mapped_column(Float, nullable=True)
    diferencia: Mapped[float] = mapped_column(Float, default=0)
    observacion: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    lot = relationship("StockLot")
    order = relationship("SalesOrder")


# ---------------------------------------------------------------------------
# Producción, BOM, liquidación (IF §8)
# ---------------------------------------------------------------------------
class BOMVersion(Base):
    __tablename__ = "bom_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    archivo: Mapped[str] = mapped_column(String(250))
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    # ¿El Excel ya incorpora pérdidas? SI / NO / NO_VERIFICADO (IF §8.1, §20)
    incluye_merma: Mapped[str] = mapped_column(String(15), default="NO_VERIFICADO")
    cambios: Mapped[dict] = mapped_column(JSON, default=dict)
    lines = relationship("BOMLine", back_populates="version_obj", cascade="all, delete-orphan")


class BOMLine(Base):
    """Fila del Excel 'LISTA DE MATERIALES 2026.xlsx' (Hoja1)."""
    __tablename__ = "bom_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("bom_versions.id"))
    padre: Mapped[str] = mapped_column(String(30), index=True)
    padre_desc: Mapped[str] = mapped_column(String(200))
    tipo_bom: Mapped[str] = mapped_column(String(5), default="P")
    cantidad_bom: Mapped[float] = mapped_column(Float, default=1)
    almacen_pt: Mapped[str] = mapped_column(String(20), default="")
    orden: Mapped[int | None] = mapped_column(Integer, nullable=True)
    componente: Mapped[str] = mapped_column(String(30))
    componente_desc: Mapped[str] = mapped_column(String(200))
    cantidad: Mapped[float] = mapped_column(Float)
    almacen_comp: Mapped[str] = mapped_column(String(20), default="")
    um: Mapped[str] = mapped_column(String(20), default="")
    metodo_emision: Mapped[str] = mapped_column(String(5), default="")
    version_obj = relationship("BOMVersion", back_populates="lines")


class ProductionLine(Base):
    """Líneas de producción (formatos PDF: Envasado R1-R2-R3, Truer, Cimbria, Selección manual)."""
    __tablename__ = "production_lines"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    capacidad_kg_dia: Mapped[float | None] = mapped_column(Float, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    fuente: Mapped[str] = mapped_column(String(200), default="")


class ProductionRequest(Base):
    """Solicitud preliminar de producción (IF §8.2)."""
    __tablename__ = "production_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    cantidad: Mapped[float] = mapped_column(Float)
    fecha_requerida: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR")
    # BORRADOR / ENVIADA / VALIDADA / RECHAZADA / PROGRAMADA / EN_PROCESO / FINALIZADA / LIQUIDADA
    origen: Mapped[str] = mapped_column(String(20), default="OV")  # OV / REEMPAQUE / MANUAL
    repack_id: Mapped[int | None] = mapped_column(ForeignKey("repack_requests.id"), nullable=True)
    analisis: Mapped[dict] = mapped_column(JSON, default=dict)
    bom_version_id: Mapped[int | None] = mapped_column(ForeignKey("bom_versions.id"), nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    enviado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validacion: Mapped[dict] = mapped_column(JSON, default=dict)  # lista, disponibilidad real, capacidad, plazo
    line_code: Mapped[str | None] = mapped_column(ForeignKey("production_lines.code"), nullable=True)
    fecha_programada: Mapped[date | None] = mapped_column(Date, nullable=True)
    inicio_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fin_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observacion: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    product = relationship("Product")
    order = relationship("SalesOrder")
    line = relationship("ProductionLine")


class Liquidation(Base):
    """Liquidación de producción (IF §8.3). Formato SAP: hoja 'Dat.Prod' de 'Recep. pt.xlsx'."""
    __tablename__ = "liquidations"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero_documento: Mapped[str] = mapped_column(String(30), index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("production_requests.id"), nullable=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    almacen: Mapped[str] = mapped_column(String(60), default="")
    warehouse_code: Mapped[str | None] = mapped_column(ForeignKey("warehouses.code"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    cantidad_planificada: Mapped[float] = mapped_column(Float, default=0)
    cantidad_completada: Mapped[float] = mapped_column(Float, default=0)
    lote: Mapped[str] = mapped_column(String(60))
    fecha_fab: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_venc: Mapped[date | None] = mapped_column(Date, nullable=True)
    valorizado: Mapped[float | None] = mapped_column(Float, nullable=True)
    realizado_por: Mapped[str] = mapped_column(String(120), default="")
    origen: Mapped[str] = mapped_column(String(10), default="MANUAL")  # MANUAL / EXCEL / SAP
    merma_mp_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    merma_insumos: Mapped[dict] = mapped_column(JSON, default=dict)  # {codigo: cantidad}
    merma_granel_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String(25), default="REGISTRADA")
    # REGISTRADA / RECIBIDA_COMPLETA / RECIBIDA_FALTANTE / RECIBIDA_SOBRANTE
    cantidad_recibida: Mapped[float | None] = mapped_column(Float, nullable=True)
    diferencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    presentacion_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recibido_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recibido_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observacion: Mapped[str] = mapped_column(Text, default="")
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lots.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    product = relationship("Product")
    request = relationship("ProductionRequest")
    # Clave documento+lote: los archivos reales traen documentos con más de un lote (pendiente de validar con SAP)
    __table_args__ = (UniqueConstraint("numero_documento", "lote", name="uq_liq_doc_lote"),)


# ---------------------------------------------------------------------------
# Reempaque (IF §9)
# ---------------------------------------------------------------------------
class RepackRequest(Base):
    __tablename__ = "repack_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))  # ACTUALIZACION_FECHA / CAMBIO_PRESENTACION / CONVERSION_CALIDAD
    lot_id: Mapped[int] = mapped_column(ForeignKey("stock_lots.id"))
    cantidad: Mapped[float] = mapped_column(Float)
    producto_destino: Mapped[str | None] = mapped_column(ForeignKey("products.code"), nullable=True)
    cantidad_destino: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    motivo: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(20), default="SOLICITADA")
    # SOLICITADA / APROBADA / DESAPROBADA / EN_EJECUCION / EJECUTADA
    solicitado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    evaluado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    evaluado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resultado_calidad: Mapped[str] = mapped_column(Text, default="")
    ejecutado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ejecucion_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ejecucion_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lote_resultante: Mapped[str] = mapped_column(String(60), default="")
    nueva_fecha_fab: Mapped[date | None] = mapped_column(Date, nullable=True)
    nueva_fecha_venc: Mapped[date | None] = mapped_column(Date, nullable=True)
    lot_resultante_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lots.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    lot = relationship("StockLot", foreign_keys=[lot_id])
    order = relationship("SalesOrder")


# ---------------------------------------------------------------------------
# Calidad (IF §9.3, §9.4 y formatos REG-*)
# ---------------------------------------------------------------------------
class QualityRecord(Base):
    """Registro de Calidad genérico por formato:
    MUESTREO (REG-CAL-002 / CP-FOR-CAL-10), RECEPCION_MP (REG-HACCP-CAL-002), FUMIGACION (REG-BPM-CAL-005),
    NO_CONFORME (REG-BPM-CAL-013), QUEJA (REG-HACCP-CAL-003), NC_ACCION (REG-HACCP-CAL-006),
    CONTROL_PESOS (REG-CAL-003), CONTROL_GRANOS (REG-CAL-014), RECEPCION_IMPORTADO (REG-CAL-005),
    VEHICULO (REG-BPM-CAL-011), DISENO_BOBINA, PROCESO."""
    __tablename__ = "quality_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    formato: Mapped[str] = mapped_column(String(30), index=True)
    codigo_formato: Mapped[str] = mapped_column(String(30), default="")
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    product_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    lote: Mapped[str] = mapped_column(String(60), default="")
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lots.id"), nullable=True)
    referencia_tipo: Mapped[str] = mapped_column(String(30), default="")  # COMPRA / IMPORTACION / REEMPAQUE / OV / RUTA
    referencia_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    resultado: Mapped[str] = mapped_column(String(20), default="")  # CONFORME / NO_CONFORME / APROBADO / DESAPROBADO
    observaciones: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(20), default="REGISTRADO")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User")


class Certificate(Base):
    """Certificado de calidad autogenerado (IF §9.4; modelos N°CP2026-PT3756 / MP276 / CA0764)."""
    __tablename__ = "certificates"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), unique=True)
    serie: Mapped[str] = mapped_column(String(10))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lots.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    product_code: Mapped[str] = mapped_column(String(30))
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR")  # BORRADOR / APROBADO / ANULADO
    generado_ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    revisado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revisado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cambios: Mapped[list] = mapped_column(JSON, default=list)


# ---------------------------------------------------------------------------
# Compras e importaciones (IF §7, §10, §11)
# ---------------------------------------------------------------------------
class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    cantidad: Mapped[float] = mapped_column(Float)
    fecha_necesidad: Mapped[date | None] = mapped_column(Date, nullable=True)
    origen: Mapped[str] = mapped_column(String(20), default="ALMACEN")  # ALMACEN / REPOSICION / OV
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    analisis: Mapped[dict] = mapped_column(JSON, default=dict)
    estado: Mapped[str] = mapped_column(String(30), default="BORRADOR")
    # BORRADOR / SOLICITADA / EN_COTIZACION / MUESTRA_EN_CALIDAD / MUESTRA_RECHAZADA / PENDIENTE_APROBACION /
    # ORDEN_GENERADA / RECIBIDA / RECIBIDA_CON_DIFERENCIAS / RECIBIDA_BAJO_OBSERVACION / CERRADA / ANULADA
    requiere_muestra: Mapped[bool] = mapped_column(Boolean, default=False)
    resultado_muestra: Mapped[str] = mapped_column(String(20), default="")
    mayor_volumen: Mapped[bool] = mapped_column(Boolean, default=False)
    aprobado_gerencia_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    proveedor: Mapped[str] = mapped_column(String(160), default="")
    cotizacion: Mapped[str] = mapped_column(Text, default="")
    precio: Mapped[float | None] = mapped_column(Float, nullable=True)
    numero_oc: Mapped[str] = mapped_column(String(40), default="")
    fecha_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    warehouse_code: Mapped[str | None] = mapped_column(ForeignKey("warehouses.code"), nullable=True)
    cantidad_recibida: Mapped[float | None] = mapped_column(Float, nullable=True)
    diferencias: Mapped[str] = mapped_column(Text, default="")
    autorizacion_observacion_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    observaciones_recepcion: Mapped[str] = mapped_column(Text, default="")
    lote_recibido: Mapped[str] = mapped_column(String(60), default="")
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    product = relationship("Product")


class DateChange(Base):
    """Historial de cambios de fecha prevista (compras nacionales e importaciones)."""
    __tablename__ = "date_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(20))  # COMPRA / IMPORTACION / FASE
    entidad_id: Mapped[int] = mapped_column(Integer)
    anterior: Mapped[date | None] = mapped_column(Date, nullable=True)
    nueva: Mapped[date | None] = mapped_column(Date, nullable=True)
    motivo: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


class ImportPhaseTemplate(Base):
    """Fases configurables de importación (IF §11, §16). Las fases concretas están pendientes de definición."""
    __tablename__ = "import_phase_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    orden: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(String(80))
    dias_desde_inicio: Mapped[int] = mapped_column(Integer, default=0)
    recordatorio_dias: Mapped[int] = mapped_column(Integer, default=0)
    responsable_rol: Mapped[str] = mapped_column(String(40), default="IMPORTACIONES")
    estado_def: Mapped[str] = mapped_column(String(12), default="DEMO")


class ImportShipment(Base):
    __tablename__ = "import_shipments"
    id: Mapped[int] = mapped_column(primary_key=True)
    referencia: Mapped[str] = mapped_column(String(60), unique=True)
    proveedor: Mapped[str] = mapped_column(String(160))
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    cantidad: Mapped[float] = mapped_column(Float)
    fecha_llegada_estimada: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="EN_CURSO")  # EN_CURSO / RECIBIDA / RECIBIDA_CON_DIFERENCIAS / CERRADA
    warehouse_code: Mapped[str | None] = mapped_column(ForeignKey("warehouses.code"), nullable=True)
    cantidad_recibida: Mapped[float | None] = mapped_column(Float, nullable=True)
    lote_recibido: Mapped[str] = mapped_column(String(60), default="")
    diferencias: Mapped[str] = mapped_column(Text, default="")
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    product = relationship("Product")
    phases = relationship("ImportPhase", back_populates="shipment", order_by="ImportPhase.orden",
                          cascade="all, delete-orphan")


class ImportPhase(Base):
    __tablename__ = "import_phases"
    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("import_shipments.id"))
    orden: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(String(80))
    fecha_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_real: Mapped[date | None] = mapped_column(Date, nullable=True)
    recordatorio_dias: Mapped[int] = mapped_column(Integer, default=0)
    responsable_rol: Mapped[str] = mapped_column(String(40), default="IMPORTACIONES")
    shipment = relationship("ImportShipment", back_populates="phases")


# ---------------------------------------------------------------------------
# Distribución y despacho (IF §12)
# ---------------------------------------------------------------------------
class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    placa: Mapped[str] = mapped_column(String(20), unique=True)
    descripcion: Mapped[str] = mapped_column(String(80), default="")
    propio: Mapped[bool] = mapped_column(Boolean, default=True)
    capacidad_kg: Mapped[float] = mapped_column(Float)
    volumen_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)
    conductor_habitual_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    observacion: Mapped[str] = mapped_column(String(250), default="")


class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    licencia: Mapped[str] = mapped_column(String(30), default="")
    externo: Mapped[bool] = mapped_column(Boolean, default=False)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    requiere_externo: Mapped[bool] = mapped_column(Boolean, default=False)
    zona: Mapped[str] = mapped_column(String(120), default="")
    estado: Mapped[str] = mapped_column(String(20), default="PROPUESTA")
    # PROPUESTA / CONFIRMADA / EN_RUTA / CERRADA / ANULADA
    peso_total: Mapped[float] = mapped_column(Float, default=0)
    advertencias: Mapped[list] = mapped_column(JSON, default=list)
    checklist: Mapped[dict] = mapped_column(JSON, default=dict)  # verificación de salida
    # Etapa de carga (TO-BE): fotos, validación del auxiliar, autorización de Seguridad, retorno
    fotos: Mapped[dict] = mapped_column(JSON, default=dict)  # {etapa: [{archivo, user, ts, nota}]}
    carga: Mapped[dict] = mapped_column(JSON, default=dict)  # validación de productos vs pre-guía
    carga_validada: Mapped[bool] = mapped_column(Boolean, default=False)
    autorizacion_seguridad: Mapped[dict] = mapped_column(JSON, default=dict)
    retorno_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    guia_numero: Mapped[str] = mapped_column(String(40), default="")
    seguridad: Mapped[dict] = mapped_column(JSON, default=dict)  # validación carga vs guía
    salida_confirmada_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    salida_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cierre_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    vehicle = relationship("Vehicle")
    driver = relationship("Driver")
    stops = relationship("RouteStop", back_populates="route", order_by="RouteStop.orden",
                         cascade="all, delete-orphan")


class RouteStop(Base):
    __tablename__ = "route_stops"
    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"))
    orden: Mapped[int] = mapped_column(Integer, default=1)
    peso_kg: Mapped[float] = mapped_column(Float, default=0)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    # PENDIENTE / EN_CAMINO / LLEGADA / ENTREGADO / ENTREGA_PARCIAL / RECHAZADO / DEVUELTO / NO_ENTREGADO
    llegada_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entrega_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    foto_path: Mapped[str] = mapped_column(String(250), default="")
    guia_firmada_path: Mapped[str] = mapped_column(String(250), default="")
    # Documentos del pedido (TO-BE: guía en SAP o en el sistema, factura, certificados)
    guia_numero: Mapped[str] = mapped_column(String(40), default="")
    guia_origen: Mapped[str] = mapped_column(String(10), default="")  # SAP / SISTEMA
    guia_path: Mapped[str] = mapped_column(String(250), default="")
    factura_numero: Mapped[str] = mapped_column(String(40), default="")
    factura_path: Mapped[str] = mapped_column(String(250), default="")
    factura_con_modificaciones: Mapped[bool] = mapped_column(Boolean, default=False)
    factura_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observacion: Mapped[str] = mapped_column(Text, default="")
    route = relationship("Route", back_populates="stops")
    order = relationship("SalesOrder")


class Incident(Base):
    """Incidencias de distribución (IF §12.3)."""
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    stop_id: Mapped[int | None] = mapped_column(ForeignKey("route_stops.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    cantidad_afectada: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default="ABIERTA")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    order = relationship("SalesOrder")


# ---------------------------------------------------------------------------
# Alertas (IF §14)
# ---------------------------------------------------------------------------
class AlertType(Base):
    __tablename__ = "alert_types"
    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(160))
    area: Mapped[str] = mapped_column(String(40))
    grupo: Mapped[str] = mapped_column(String(60))  # agrupación para Gerencia General
    prioridad: Mapped[str] = mapped_column(String(10), default="MEDIA")  # ALTA / MEDIA / BAJA
    roles: Mapped[list] = mapped_column(JSON, default=list)
    usuarios: Mapped[list] = mapped_column(JSON, default=list)  # ids de usuario adicionales autorizados
    enviar_correo: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    origen_destinatarios: Mapped[str] = mapped_column(String(12), default="PROPUESTO")
    fuente: Mapped[str] = mapped_column(String(200), default="")
    condicion: Mapped[str] = mapped_column(Text, default="")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    type_code: Mapped[str] = mapped_column(ForeignKey("alert_types.code"))
    titulo: Mapped[str] = mapped_column(String(250))
    mensaje: Mapped[str] = mapped_column(Text, default="")
    prioridad: Mapped[str] = mapped_column(String(10))
    area: Mapped[str] = mapped_column(String(40))
    entidad: Mapped[str] = mapped_column(String(40), default="")
    entidad_id: Mapped[str] = mapped_column(String(40), default="")
    estado: Mapped[str] = mapped_column(String(15), default="NUEVA")  # NUEVA / ASIGNADA / EN_ATENCION / CERRADA
    roles: Mapped[list] = mapped_column(JSON, default=list)
    usuarios: Mapped[list] = mapped_column(JSON, default=list)
    asignado_a: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    creado_ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cerrado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cerrado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    motivo_cierre: Mapped[str] = mapped_column(Text, default="")
    accion_tomada: Mapped[str] = mapped_column(Text, default="")
    dedup_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    type = relationship("AlertType")
    asignado = relationship("User", foreign_keys=[asignado_a])
    events = relationship("AlertEvent", back_populates="alert", order_by="AlertEvent.ts",
                          cascade="all, delete-orphan")


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"))
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accion: Mapped[str] = mapped_column(String(30))
    comentario: Mapped[str] = mapped_column(Text, default="")
    alert = relationship("Alert", back_populates="events")
    user = relationship("User")


class GGAlertPreference(Base):
    """Gerencia General configura qué alertas recibe directamente por correo (IF §14)."""
    __tablename__ = "gg_alert_prefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type_code: Mapped[str] = mapped_column(ForeignKey("alert_types.code"))
    recibir_directo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("user_id", "type_code"),)


class EmailOutbox(Base):
    """Bandeja de salida de correo. Si no hay SMTP configurado, queda en estado SIN_SMTP (no se simula el envío)."""
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    destinatario: Mapped[str] = mapped_column(String(160))
    asunto: Mapped[str] = mapped_column(String(250))
    cuerpo: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE")  # PENDIENTE / ENVIADO / ERROR / SIN_SMTP
    error: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    enviado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
