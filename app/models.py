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
    fuente: Mapped[str] = mapped_column(Text, default="")
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
    fuente: Mapped[str] = mapped_column(Text, default="")
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
    # almacén donde trabaja el personal operativo (auxiliares, líderes, montacarguistas) para programar el picking
    almacen: Mapped[str] = mapped_column(String(20), default="")
    # marcha blanca (22-oct-2026): aviso de datos personales aceptado {version, ts, ip}, vigencia de la contraseña y
    # bloqueo por intentos fallidos
    aviso_aceptado: Mapped[dict] = mapped_column(JSON, default=dict)
    clave_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    fuente: Mapped[str] = mapped_column(Text, default="")
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
    # ronda 23-oct-2026: solo los almacenes habilitados en Configuración se cargan desde SAP y se usan en el módulo
    habilitado: Mapped[bool] = mapped_column(Boolean, default=True)
    fuente: Mapped[str] = mapped_column(Text, default="")
    observacion: Mapped[str] = mapped_column(Text, default="")


class Product(Base):
    """Artículo (formato TABLA_DATA de 'PCP 2026 - J.xlsm' y columnas de OVS/BOM)."""
    __tablename__ = "products"
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(200))
    um: Mapped[str] = mapped_column(String(20), default="UNIDAD")  # UNIDAD / KILOGRAMO
    peso_kg: Mapped[float | None] = mapped_column(Float, nullable=True)  # PPB: peso por unidad
    # unidades por caja o bulto: el picking registra los bultos para el seguimiento del stock y los certificados
    unidades_por_bulto: Mapped[float | None] = mapped_column(Float, nullable=True)
    tipo: Mapped[str] = mapped_column(String(10), default="")  # PT, MP, GR, EN, SU, ...
    foto: Mapped[str] = mapped_column(String(250), default="")  # foto del catálogo (ronda 23-oct-2026)
    # V7: destacado del catálogo: MES (producto del mes) o TEMPORADA, con nota y vigencia
    destacado: Mapped[str] = mapped_column(String(12), default="", server_default="")
    destacado_nota: Mapped[str] = mapped_column(String(200), default="", server_default="")
    destacado_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
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
    proveedor_habitual: Mapped[str] = mapped_column(String(160), default="")  # para el margen por proveedor
    merma_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    tiempo_max_almacen_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    costo_max_compra: Mapped[float | None] = mapped_column(Float, nullable=True)  # S/ por UM: tope para no comprar a pérdida
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
    fuente: Mapped[str] = mapped_column(Text, default="")


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
    canal_precio: Mapped[str] = mapped_column(String(60), default="")  # canal de la lista de precios (lo asigna el Jefe Comercial)
    # Ficha de cliente (observaciones al demo v0.5, 13-oct)
    contacto: Mapped[str] = mapped_column(String(120), default="")
    telefono: Mapped[str] = mapped_column(String(60), default="")
    correo: Mapped[str] = mapped_column(String(160), default="")
    codigo_sap: Mapped[str] = mapped_column(String(30), default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")
    # Observaciones al demo v0.6: hasta 3 celulares y 3 correos, contrato, certificaciones, penalidades, vendedor
    celulares: Mapped[list] = mapped_column(JSON, default=list)
    correos: Mapped[list] = mapped_column(JSON, default=list)
    tiene_contrato: Mapped[bool] = mapped_column(Boolean, default=False)
    contrato_archivo: Mapped[str] = mapped_column(String(200), default="")
    certificaciones: Mapped[str] = mapped_column(Text, default="")  # certificaciones que pide el cliente
    penalidades: Mapped[str] = mapped_column(Text, default="")  # penalidades establecidas con el cliente
    requiere_auxiliar: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # V8 (D01)
    vendedor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # vendedor responsable
    # Ronda 23-oct-2026: ubigeo (guía), condición de pago aprobada por Finanzas y prospecto (módulo de oportunidades)
    ubigeo: Mapped[str] = mapped_column(String(10), default="")
    condicion_pago: Mapped[str] = mapped_column(String(10), default="")  # CONTADO / CREDITO
    credito_monto: Mapped[float | None] = mapped_column(Float, nullable=True)  # línea de crédito solicitada (S/)
    credito_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # SIN_SOLICITAR / PENDIENTE / APROBADA / OBSERVADA / RECHAZADA. Los clientes existentes y los cargados desde SAP ya
    # tienen su condición en SAP (APROBADA); los creados en el módulo empiezan SIN_SOLICITAR.
    condicion_estado: Mapped[str] = mapped_column(String(15), default="APROBADA")
    condicion_docs: Mapped[dict] = mapped_column(JSON, default=dict)  # {documento: archivo}
    condicion_historial: Mapped[list] = mapped_column(JSON, default=list)
    es_prospecto: Mapped[bool] = mapped_column(Boolean, default=False)
    convertido: Mapped[dict] = mapped_column(JSON, default=dict)  # paso de prospecto a cliente (OC, usuario, fecha)
    vendedor = relationship("User", foreign_keys=[vendedor_id])
    sites = relationship("CustomerSite", back_populates="customer", order_by="CustomerSite.id")


class CustomerSite(Base):
    """Lugar de entrega del cliente (almacén, tienda, sede). La OV elige uno o registra 'otro' con su dirección."""
    __tablename__ = "customer_sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    nombre: Mapped[str] = mapped_column(String(120))
    direccion: Mapped[str] = mapped_column(String(250), default="")
    distrito: Mapped[str] = mapped_column(String(80), default="")
    provincia: Mapped[str] = mapped_column(String(80), default="")
    referencia: Mapped[str] = mapped_column(String(250), default="")
    ubigeo: Mapped[str] = mapped_column(String(10), default="")
    horario_recepcion: Mapped[str] = mapped_column(String(60), default="")
    contacto: Mapped[str] = mapped_column(String(120), default="")
    telefono: Mapped[str] = mapped_column(String(60), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    customer = relationship("Customer", back_populates="sites")


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
    fumigacion_programada: Mapped[date | None] = mapped_column(Date, nullable=True)  # planeamiento de fumigación
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
    recuento: Mapped[float | None] = mapped_column(Float, nullable=True)  # V8 (A06): segundo conteo si supera la tolerancia
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
    # ronda UX 24-oct-2026: aviso de Logística de que la OV no llegará a tiempo {motivo, user, ts, nueva_fecha}
    aviso_atraso: Mapped[dict] = mapped_column(JSON, default=dict)
    # ronda 26-oct-2026: OV BLOQUEADA (no compromete stock) cuando ninguna opción cumple la fecha o se emitió con menos
    # de un día de anticipación. {tipo, estado, lineas, solicitud, decision, historial}
    bloqueo_ov: Mapped[dict] = mapped_column(JSON, default=dict)
    urgente: Mapped[bool] = mapped_column(Boolean, default=False)
    direccion: Mapped[str] = mapped_column(String(250), default="")
    distrito: Mapped[str] = mapped_column(String(80), default="")
    provincia: Mapped[str] = mapped_column(String(80), default="")
    lugar_entrega: Mapped[str] = mapped_column(String(120), default="")  # almacén/punto de entrega del cliente
    site_id: Mapped[int | None] = mapped_column(ForeignKey("customer_sites.id"), nullable=True)
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
    tipo_venta: Mapped[str] = mapped_column(String(40), default="")  # Orden de venta / Muestra comercial / PAE (SAP)
    forma_pago: Mapped[str] = mapped_column(String(60), default="")  # p.ej. "Crédito 30 días" (formato de OV)
    moneda: Mapped[str] = mapped_column(String(10), default="SOLES")
    retenida_precio: Mapped[bool] = mapped_column(Boolean, default=False)  # detenida por precio bajo el mínimo
    precio_observado: Mapped[list] = mapped_column(JSON, default=list)  # líneas observadas en la última validación
    aprobacion_precio: Mapped[dict] = mapped_column(JSON, default=dict)  # confirmación del Coord./Jefe Comercial
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    creado_ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    evaluado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prep_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prep_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    salida_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entrega_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    corte: Mapped[str] = mapped_column(String(20), default="")
    alerta80_emitida: Mapped[bool] = mapped_column(Boolean, default=False)
    # Despacho parcial (decisión Q3, 11-oct-2026): aprobación de Gerencia de Operaciones y Jefatura de Logística;
    # el saldo no despachado se reprograma en una OV de saldo.
    parcial_aprobaciones: Mapped[dict] = mapped_column(JSON, default=dict)
    fecha_saldo: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    completa_notificada: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_picking_validado: Mapped[bool] = mapped_column(Boolean, default=False)
    # obs. demo v0.7: OV registrada con fecha pasada u hora transcurrida (no reserva stock) {motivo, user, ts, ...}
    regularizacion: Mapped[dict] = mapped_column(JSON, default=dict)
    # V10 (28-oct-2026): la OV registrada en el módulo se crea en SAP (Orders). sap_envio: {estado, hash, error, ts,
    # intentos, cancelada}; sap_docnum es el número que SAP le asigna (las cargas de SAP la reconocen por él).
    sap_docnum: Mapped[str] = mapped_column(String(20), default="", server_default="", index=True)
    sap_docentry: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sap_envio: Mapped[dict] = mapped_column(JSON, default=dict)
    customer = relationship("Customer")
    # canal / grupo de precios elegido al registrar (el mínimo varía por canal; observaciones al demo v0.6)
    canal_precio: Mapped[str] = mapped_column(String(60), default="")
    # Ronda 23-oct-2026: orden de compra del cliente (obligatoria en las OV del módulo; sin ella queda en BORRADOR) y
    # compromiso de Operaciones (CUMPLE / NO_CUMPLE) dentro del plazo configurado
    oc_archivo: Mapped[str] = mapped_column(String(250), default="")
    oc_numero: Mapped[str] = mapped_column(String(60), default="")
    compromiso: Mapped[dict] = mapped_column(JSON, default=dict)
    cancelacion_motivo: Mapped[str] = mapped_column(Text, default="")
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
    precio_minimo: Mapped[float | None] = mapped_column(Float, nullable=True)  # precio mínimo de lista del canal (Q11)
    precio_origen: Mapped[str] = mapped_column(String(160), default="")  # resultado de la validación contra la lista
    descuento: Mapped[float] = mapped_column(Float, default=0)  # descuento de la línea (S/), formato de OV
    tax_code: Mapped[str] = mapped_column(String(10), default="")  # código de impuesto SAP (EXO / IGV)
    um_venta: Mapped[str] = mapped_column(String(10), default="")  # unidad de venta: UND / KG / SACO (granel)
    cantidad_venta: Mapped[float | None] = mapped_column(Float, nullable=True)  # cantidad en la unidad de venta (sacos)
    preparado: Mapped[float] = mapped_column(Float, default=0)
    despachado: Mapped[float] = mapped_column(Float, default=0)
    entregado: Mapped[float] = mapped_column(Float, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    order = relationship("SalesOrder", back_populates="lines")
    product = relationship("Product")
    reservations = relationship("Reservation", back_populates="line")


class PickingTask(Base):
    """Programación del picking de una OV en un almacén (observaciones al demo v0.6): el sistema la preprograma, el
    Líder Operativo o el Coordinador la asigna a una persona o grupo y la modifica; el auxiliar la ejecuta con fotos."""
    __tablename__ = "picking_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"))
    warehouse_code: Mapped[str] = mapped_column(String(20))
    fecha: Mapped[date] = mapped_column(Date)
    asignados: Mapped[list] = mapped_column(JSON, default=list)  # ids de usuario (persona o grupo)
    asignado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default="PROGRAMADO")  # PROGRAMADO / EN_PROCESO / LISTO
    inicio_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fin_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    foto_inicio: Mapped[str] = mapped_column(String(200), default="")
    foto_listo: Mapped[str] = mapped_column(String(200), default="")
    observacion: Mapped[str] = mapped_column(Text, default="")
    verificador: Mapped[str] = mapped_column(String(120), default="")  # verificador del pedido (formato)
    # obs. demo v0.7: cambios de lote durante el picking [{ts, user, lote_anterior, lote_nuevo, cantidad, motivo, ...}]
    cambios_lote: Mapped[list] = mapped_column(JSON, default=list)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    order = relationship("SalesOrder")


class PickingRecord(Base):
    """Lo que llena a mano el auxiliar en el formato 'Seguimiento de control de despacho de producto terminado':
    cantidad despachada, lote, fecha de producción y fecha de vencimiento (por línea y lote)."""
    __tablename__ = "picking_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"))
    line_id: Mapped[int] = mapped_column(ForeignKey("sales_order_lines.id"))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("picking_tasks.id"), nullable=True)
    lote: Mapped[str] = mapped_column(String(60))
    cantidad: Mapped[float] = mapped_column(Float)
    bultos: Mapped[float | None] = mapped_column(Float, nullable=True)  # cajas / bultos (dato escrito a mano en el formato)
    fecha_produccion: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_venc: Mapped[date | None] = mapped_column(Date, nullable=True)
    comentario: Mapped[str] = mapped_column(String(250), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    line = relationship("SalesOrderLine")
    user = relationship("User")


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
    estado: Mapped[str] = mapped_column(String(30), default="REGISTRADA")
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
    estado: Mapped[str] = mapped_column(String(30), default="SOLICITADO")
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
    llegada_estimada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # alerta a Calidad y Almacén
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
    fuente: Mapped[str] = mapped_column(Text, default="")


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
    bom_revision: Mapped[dict] = mapped_column(JSON, default=dict)  # Producción confirma u observa la lista de materiales
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
    # Ronda 23-oct-2026: horas y operarios (SAP los exige), kg de MP para el balance de masa y bloqueo
    horas: Mapped[float | None] = mapped_column(Float, nullable=True)
    operarios: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mp_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    bloqueo: Mapped[dict] = mapped_column(JSON, default=dict)  # {motivos: [...], ts, resuelto_ts}
    estado: Mapped[str] = mapped_column(String(25), default="REGISTRADA")
    # REGISTRADA / RECIBIDA_COMPLETA / RECIBIDA_FALTANTE / RECIBIDA_SOBRANTE
    cantidad_recibida: Mapped[float | None] = mapped_column(Float, nullable=True)
    diferencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    presentacion_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recibido_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recibido_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observacion: Mapped[str] = mapped_column(Text, default="")
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lots.id"), nullable=True)
    parcial: Mapped[bool] = mapped_column(Boolean, default=False)  # liquidación parcial de la solicitud (ronda UX)
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
    # PRE_SOLICITUD / DESESTIMADA / SOLICITADA / APROBADA / DESAPROBADA / EN_EJECUCION / EJECUTADA
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
    # BORRADOR / PENDIENTE_LOGISTICA / SOLICITADA / EN_COTIZACION / MUESTRA_EN_CALIDAD / MUESTRA_RECHAZADA / PENDIENTE_APROBACION /
    # ORDEN_GENERADA / RECIBIDA / RECIBIDA_CON_DIFERENCIAS / RECIBIDA_BAJO_OBSERVACION / CERRADA / ANULADA
    requiere_muestra: Mapped[bool] = mapped_column(Boolean, default=False)
    resultado_muestra: Mapped[str] = mapped_column(String(20), default="")
    mayor_volumen: Mapped[bool] = mapped_column(Boolean, default=False)
    aprobado_gerencia_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    aprobado_logistica_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # Q14
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
    # obs. demo v0.7: presolicitud agrupada (mismo producto y fecha) con sus OV de origen [{order_id, numero, cantidad}],
    # motivo detallado (quiebre de stock, pedidos similares) y cotizaciones [{proveedor, precio, plazo, archivo, ...}]
    ordenes: Mapped[list] = mapped_column(JSON, default=list)
    motivo: Mapped[str] = mapped_column(Text, default="")
    cotizaciones: Mapped[list] = mapped_column(JSON, default=list)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    product = relationship("Product")
    order = relationship("SalesOrder")


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
    estado: Mapped[str] = mapped_column(String(30), default="EN_CURSO")  # EN_CURSO / RECIBIDA / RECIBIDA_CON_DIFERENCIAS / CERRADA
    warehouse_code: Mapped[str | None] = mapped_column(ForeignKey("warehouses.code"), nullable=True)
    cantidad_recibida: Mapped[float | None] = mapped_column(Float, nullable=True)
    lote_recibido: Mapped[str] = mapped_column(String(60), default="")
    diferencias: Mapped[str] = mapped_column(Text, default="")
    # cotización / valor de la mercadería (para el costo puesto en almacén y el análisis de impacto en precios)
    valor_mercaderia: Mapped[float | None] = mapped_column(Float, nullable=True)
    moneda_mercaderia: Mapped[str] = mapped_column(String(5), default="USD")
    tipo_cambio_mercaderia: Mapped[float | None] = mapped_column(Float, nullable=True)
    contenedor: Mapped[str] = mapped_column(String(40), default="")  # número de contenedor
    tipo_contenedor: Mapped[str] = mapped_column(String(20), default="")  # 20' / 40' / 40' HC / carga suelta
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    product = relationship("Product")
    costs = relationship("ImportCost", order_by="ImportCost.id", cascade="all, delete-orphan")
    phases = relationship("ImportPhase", back_populates="shipment", order_by="ImportPhase.orden",
                          cascade="all, delete-orphan")


class ImportCost(Base):
    """Costos asociados a la importación (flete, seguro, aduana, almacenaje, transporte local, otros)."""
    __tablename__ = "import_costs"
    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("import_shipments.id"))
    concepto: Mapped[str] = mapped_column(String(60))
    monto: Mapped[float] = mapped_column(Float)
    moneda: Mapped[str] = mapped_column(String(5), default="USD")
    tipo_cambio: Mapped[float | None] = mapped_column(Float, nullable=True)
    documento: Mapped[str] = mapped_column(String(80), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


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
    km_actual: Mapped[float | None] = mapped_column(Float, nullable=True)  # último kilometraje registrado
    # V7: enlace de seguimiento compartido por GEOSATELITAL para esta unidad (sin API: se muestra embebido o en ventana)
    geosat_link: Mapped[str] = mapped_column(String(500), default="", server_default="")
    geosat_link_vence: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # V8: el enlace dura 15 min a 24 h
    # V8: datos de la unidad como figuran en GEOSATELITAL (Nombre, Flota, Marca, Modelo, Año, Tipo, Odómetro)
    nombre_geosat: Mapped[str] = mapped_column(String(60), default="", server_default="")
    flota: Mapped[str] = mapped_column(String(60), default="", server_default="")
    marca: Mapped[str] = mapped_column(String(60), default="", server_default="")
    modelo: Mapped[str] = mapped_column(String(60), default="", server_default="")
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_unidad: Mapped[str] = mapped_column(String(30), default="", server_default="")


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
    # V7: el chofer valida primero la carga (cantidad, lote, presentación, producto); luego el auxiliar acompañante
    carga_chofer: Mapped[dict] = mapped_column(JSON, default=dict)
    auxiliar_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    autorizacion_seguridad: Mapped[dict] = mapped_column(JSON, default=dict)  # revisión de documentos por Seguridad
    aprobacion_discrepancia: Mapped[dict] = mapped_column(JSON, default=dict)  # Q8: salida aprobada por Logística
    vistos_buenos: Mapped[dict] = mapped_column(JSON, default=dict)  # Q16: {rol: {user, ts}} Seguridad, Auxiliar, Líder
    retorno_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Transporte externo asignado por el sistema: lo valida el Coordinador de Distribución (13-oct)
    externo_validacion: Mapped[dict] = mapped_column(JSON, default=dict)
    distancia_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    tiempo_estimado_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    trafico: Mapped[dict] = mapped_column(JSON, default=dict)  # última consulta de tráfico (si hay servicio configurado)
    guia_numero: Mapped[str] = mapped_column(String(40), default="")
    seguridad: Mapped[dict] = mapped_column(JSON, default=dict)  # validación carga vs guía
    salida_confirmada_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    salida_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cierre_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    # Observaciones al demo v0.6: salida programada, kilometraje y costos de transporte externo y estiba
    hora_salida_prog: Mapped[str] = mapped_column(String(5), default="")
    km_salida: Mapped[float | None] = mapped_column(Float, nullable=True)
    km_retorno: Mapped[float | None] = mapped_column(Float, nullable=True)
    costo_transporte: Mapped[float | None] = mapped_column(Float, nullable=True)  # S/ transporte externo
    costo_estiba: Mapped[float | None] = mapped_column(Float, nullable=True)  # S/ estiba
    # obs. demo v0.7: horas que registra Seguridad {inicio_despacho|partida|retorno: {hora, user, ts}}
    horas_seguridad: Mapped[dict] = mapped_column(JSON, default=dict)
    vehicle = relationship("Vehicle")
    driver = relationship("Driver")
    stops = relationship("RouteStop", back_populates="route", order_by="RouteStop.orden",
                         cascade="all, delete-orphan")
    auxiliar = relationship("User", foreign_keys=[auxiliar_id])

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
    # obs. demo v0.7: la guía la aprueba el Coordinador o el Asistente de Distribución {user, rol, ts, comentario}
    guia_aprobada: Mapped[dict] = mapped_column(JSON, default=dict)
    observacion: Mapped[str] = mapped_column(Text, default="")
    # ronda UX 24-oct-2026: conformidad digital registrada por el chofer
    guia_estado: Mapped[str] = mapped_column(String(20), default="")  # estado reportado de la guía de remisión
    guia_estado_hist: Mapped[list] = mapped_column(JSON, default=list)  # [{estado, nota, user, ts}]
    receptor_nombre: Mapped[str] = mapped_column(String(120), default="")
    receptor_dni: Mapped[str] = mapped_column(String(15), default="")
    # V8 (D05): tipo de documento de quien recibe (DNI / CE / PASAPORTE / SIN_DOCUMENTO); sin documento: foto y motivo
    receptor_tipo_doc: Mapped[str] = mapped_column(String(12), default="DNI", server_default="DNI")
    receptor_foto: Mapped[str] = mapped_column(String(250), default="", server_default="")
    receptor_motivo: Mapped[str] = mapped_column(String(250), default="", server_default="")
    firma_path: Mapped[str] = mapped_column(String(250), default="")
    route = relationship("Route", back_populates="stops")
    order = relationship("SalesOrder")


class ArrivalCheck(Base):
    """Validación de Seguridad de lo que ingresa por compras nacionales o importaciones (obs. demo v0.7)."""
    __tablename__ = "arrival_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(12))  # COMPRA / IMPORTACION
    entidad_id: Mapped[int] = mapped_column(Integer)
    product_code: Mapped[str] = mapped_column(String(40), default="")
    cantidad_esperada: Mapped[float | None] = mapped_column(Float, nullable=True)
    cantidad_ingresa: Mapped[float | None] = mapped_column(Float, nullable=True)
    placa: Mapped[str] = mapped_column(String(20), default="")
    chofer: Mapped[str] = mapped_column(String(120), default="")
    conforme: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo: Mapped[str] = mapped_column(Text, default="")
    foto: Mapped[str] = mapped_column(String(250), default="")
    hora: Mapped[str] = mapped_column(String(5), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User")


class VehicleDocument(Base):
    """Seguimiento de documentos y obligaciones del vehículo: SOAT, revisión técnica, impuesto vehicular, multas, etc."""
    __tablename__ = "vehicle_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    tipo: Mapped[str] = mapped_column(String(30))  # SOAT / REVISION_TECNICA / IMPUESTO_VEHICULAR / MULTA / OTRO
    numero: Mapped[str] = mapped_column(String(60), default="")
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)  # emisión o fecha del evento (multa)
    hora: Mapped[str] = mapped_column(String(5), default="")
    vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    monto: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default="VIGENTE")  # VIGENTE / PENDIENTE / PAGADO / VENCIDO
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)  # quién lo tenía (multa)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    archivo: Mapped[str] = mapped_column(String(200), default="")
    observacion: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    vehicle = relationship("Vehicle")
    driver = relationship("Driver")


class FuelLog(Base):
    """Consumo de combustible por vehículo."""
    __tablename__ = "fuel_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    fecha: Mapped[date] = mapped_column(Date)
    km: Mapped[float] = mapped_column(Float)
    galones: Mapped[float] = mapped_column(Float)
    monto: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    vehicle = relationship("Vehicle")


class VehicleMaintenance(Base):
    """Mantenimientos del vehículo y el próximo por kilometraje o fecha."""
    __tablename__ = "vehicle_maintenances"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    fecha: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(15), default="PREVENTIVO")  # PREVENTIVO / CORRECTIVO
    km: Mapped[float | None] = mapped_column(Float, nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    costo: Mapped[float | None] = mapped_column(Float, nullable=True)
    proximo_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    proxima_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    vehicle = relationship("Vehicle")


class Incident(Base):
    """Incidencias de distribución (IF §12.3), clasificadas por tipo y subtipo (observaciones al demo v0.5)."""
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))  # subtipo (código detallado, p. ej. INFESTACION_INTERNA)
    grupo: Mapped[str] = mapped_column(String(20), default="")  # tipo: CALIDAD / LOGISTICA / CLIENTE
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    stop_id: Mapped[int | None] = mapped_column(ForeignKey("route_stops.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    cantidad_afectada: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default="ABIERTA")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    # Observaciones al demo v0.6: entrega total o parcial y, si es parcial, qué productos se devolvieron y por qué
    entrega: Mapped[str] = mapped_column(String(10), default="")  # TOTAL / PARCIAL / NINGUNA
    lineas: Mapped[list] = mapped_column(JSON, default=list)  # [{line_id, producto, recibido, devuelto, motivo}]
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
    fuente: Mapped[str] = mapped_column(Text, default="")
    condicion: Mapped[str] = mapped_column(Text, default="")
    # TAREA (requiere aprobación/atención) o INFORMATIVA (solo se reconoce) – observaciones al demo v0.6
    naturaleza: Mapped[str] = mapped_column(String(12), default="TAREA")


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
    # PENDIENTE / EN_EJECUCION / INCIDENCIA / COMPLETADA / DESAPROBADA (tareas) · PENDIENTE / RECONOCIDA (informativas)
    estado: Mapped[str] = mapped_column(String(15), default="PENDIENTE")
    roles: Mapped[list] = mapped_column(JSON, default=list)
    usuarios: Mapped[list] = mapped_column(JSON, default=list)
    asignado_a: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    asignado_rol: Mapped[str] = mapped_column(String(40), default="")  # designación a un cargo de la misma área
    asignado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resultado: Mapped[str] = mapped_column(String(20), default="")  # APROBADA / DESAPROBADA / ATENDIDA / SISTEMA
    evidencia: Mapped[str] = mapped_column(String(200), default="")
    foto_inicio: Mapped[str] = mapped_column(String(200), default="")  # foto al iniciar la tarea (montacarguista)
    proceso_pendiente: Mapped[str] = mapped_column(Text, default="")  # p. ej. recepción o contabilización pendiente
    creado_ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cerrado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cerrado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    motivo_cierre: Mapped[str] = mapped_column(Text, default="")
    accion_tomada: Mapped[str] = mapped_column(Text, default="")
    dedup_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    # tareas que el sistema derivó a otra área al aprobar o completar esta (obs. demo v0.7: «pendiente Calidad»)
    derivadas: Mapped[list] = mapped_column(JSON, default=list)
    type = relationship("AlertType")
    asignado = relationship("User", foreign_keys=[asignado_a])
    events = relationship("AlertEvent", back_populates="alert", order_by="AlertEvent.ts",
                          cascade="all, delete-orphan")
    incidents = relationship("AlertIncident", back_populates="alert", order_by="AlertIncident.id",
                             cascade="all, delete-orphan")


class AlertIncident(Base):
    """Incidencia de una tarea: situación, acciones, responsable y resolución; no cierra la tarea original."""
    __tablename__ = "alert_incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"))
    situacion: Mapped[str] = mapped_column(Text)
    acciones: Mapped[str] = mapped_column(Text, default="")
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolucion: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(10), default="ABIERTA")  # ABIERTA / RESUELTA
    estado_previo: Mapped[str] = mapped_column(String(15), default="PENDIENTE")
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    resuelto_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resuelto_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    alert = relationship("Alert", back_populates="incidents")
    responsable = relationship("User", foreign_keys=[responsable_id])


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


class PriceItem(Base):
    """Lista de precios (decisión Q11, 13-oct-2026). Cada cambio crea una versión nueva; la anterior queda con 'hasta'.
    lista GENERAL: precio por canal (columnas de PRICE_LIST); lista GRANEL: precio por kg y por saco (mayorista granel).
    El costo de la empresa se guarda aparte (ProductCost, visibilidad restringida; respuestas del 13-oct)."""
    __tablename__ = "price_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    lista: Mapped[str] = mapped_column(String(10))  # GENERAL / GRANEL
    product_code: Mapped[str] = mapped_column(String(40), index=True)  # puede no estar aún en el catálogo
    descripcion: Mapped[str] = mapped_column(String(250), default="")
    canal: Mapped[str] = mapped_column(String(60), default="")  # GENERAL: canal; GRANEL: vacío
    precio: Mapped[float | None] = mapped_column(Float, nullable=True)  # GENERAL
    precio_kg: Mapped[float | None] = mapped_column(Float, nullable=True)  # GRANEL
    precio_saco: Mapped[float | None] = mapped_column(Float, nullable=True)
    kg_saco: Mapped[float | None] = mapped_column(Float, nullable=True)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    desde: Mapped[datetime] = mapped_column(DateTime, default=now)
    hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    origen: Mapped[str] = mapped_column(String(160), default="")  # archivo o 'edición manual'
    motivo: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ProductCost(Base):
    """Costo de la empresa por artículo (R4 y observaciones del 13-oct): sirve para (1) impedir ventas por debajo del
    costo y (2) compararlo automáticamente con precios de mercado y su tendencia. Versionado como los precios."""
    __tablename__ = "product_costs"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(40), index=True)
    descripcion: Mapped[str] = mapped_column(String(250), default="")
    costo: Mapped[float] = mapped_column(Float)
    unidad: Mapped[str] = mapped_column(String(10), default="UND")  # UND (presentación) / KG (granel)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    desde: Mapped[datetime] = mapped_column(DateTime, default=now)
    hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    origen: Mapped[str] = mapped_column(String(160), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class MarketPrice(Base):
    """Precio de mercado de referencia (R5, 13-oct): mayorista / minorista / importación, con fuente y fecha del dato."""
    __tablename__ = "market_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto: Mapped[str] = mapped_column(String(120), index=True)  # producto base normalizado (p. ej. LENTEJA)
    variedad: Mapped[str] = mapped_column(String(120), default="")
    precio_kg: Mapped[float] = mapped_column(Float)  # S/ por kg
    tipo_precio: Mapped[str] = mapped_column(String(20), default="MAYORISTA")  # MAYORISTA / MINORISTA / IMPORTACION
    mercado: Mapped[str] = mapped_column(String(160), default="")
    fecha: Mapped[date] = mapped_column(Date)
    fuente: Mapped[str] = mapped_column(String(250), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    origen: Mapped[str] = mapped_column(String(160), default="")  # archivo cargado o 'alta manual'
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    # Observaciones al demo v0.6: quién registra y qué representa el precio (compra nacional, importación, competencia
    # directa, sustituto o referencia de mercado), con la marca/empresa y el producto nuestro compatible.
    categoria: Mapped[str] = mapped_column(String(20), default="MERCADO")
    competidor: Mapped[str] = mapped_column(String(160), default="")
    # ronda 23-oct-2026: lo registra cada vendedor y lo aprueba el Jefe Comercial (APROBADO / PENDIENTE / RECHAZADO)
    estado: Mapped[str] = mapped_column(String(12), default="APROBADO")
    aprobado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    aprobado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    presentacion: Mapped[str] = mapped_column(String(60), default="")
    product_code: Mapped[str] = mapped_column(String(40), default="")


class ProductSubstitute(Base):
    """Producto sustituto de un producto base que ofrecemos (lo registra Comercial, uno a uno o por Excel)."""
    __tablename__ = "product_substitutes"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_base: Mapped[str] = mapped_column(String(120), index=True)  # p. ej. LENTEJA
    sustituto: Mapped[str] = mapped_column(String(120))  # texto con el que aparece en los informes
    observacion: Mapped[str] = mapped_column(String(250), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    origen: Mapped[str] = mapped_column(String(160), default="")  # alta manual o archivo
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


class PurchaseVariationRule(Base):
    """Alerta de variación de compra configurada por canal o por cliente (panel de configuración, 15-oct-2026).
    Precedencia: cliente > canal > parámetros generales. Un valor vacío hereda el del nivel siguiente."""
    __tablename__ = "purchase_variation_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    alcance: Mapped[str] = mapped_column(String(10))  # CANAL | CLIENTE
    canal: Mapped[str] = mapped_column(String(60), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    umbral_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alerta: Mapped[bool] = mapped_column(Boolean, default=True)  # False: no genera alerta para este canal o cliente
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    customer: Mapped["Customer | None"] = relationship()


class PriceListMeta(Base):
    """Vigencia de cada lista de precios (se avisa al vencer; no se bloquea)."""
    __tablename__ = "price_lists"
    lista: Mapped[str] = mapped_column(String(10), primary_key=True)  # GENERAL / GRANEL
    archivo: Mapped[str] = mapped_column(String(200), default="")
    vigencia_desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


class ProductionReport(Base):
    """Parte de producción por línea (formatos LINEA TRUER, LINEA CIMBRIA, ENVASADOS R1 R2 Y R3, SEL-MANUAL). El
    'desmedro' de estos formatos es la merma (decisión del 13-oct-2026); se liga a la liquidación por el número de OF."""
    __tablename__ = "production_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    linea: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(12))  # SELECCION / ENVASADO
    fecha: Mapped[date] = mapped_column(Date)
    op: Mapped[str] = mapped_column(String(20), default="")  # número de operación del formato
    of: Mapped[str] = mapped_column(String(30), default="", index=True)  # orden de fabricación = documento de liquidación
    turno: Mapped[str] = mapped_column(String(20), default="")
    hora_inicio: Mapped[str] = mapped_column(String(8), default="")
    hora_fin: Mapped[str] = mapped_column(String(8), default="")
    horas: Mapped[float | None] = mapped_column(Float, nullable=True)
    operarios: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cliente: Mapped[str] = mapped_column(String(120), default="")
    product_code: Mapped[str] = mapped_column(String(40))
    mp_codigo: Mapped[str] = mapped_column(String(40), default="")
    lote: Mapped[str] = mapped_column(String(60), default="")
    peso_entrada_kg: Mapped[float] = mapped_column(Float)
    granel_kg: Mapped[float] = mapped_column(Float, default=0)  # salida buena (selección) / kg envasados
    mp_kg: Mapped[float] = mapped_column(Float, default=0)
    cal3_kg: Mapped[float] = mapped_column(Float, default=0)
    desmedro_kg: Mapped[float] = mapped_column(Float, default=0)
    presentacion_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    unidades: Mapped[float | None] = mapped_column(Float, nullable=True)
    sobrante_kg: Mapped[float] = mapped_column(Float, default=0)
    rendimiento_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    desmedro_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    diferencia_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    ratio_kg_hora: Mapped[float | None] = mapped_column(Float, nullable=True)
    parada_min: Mapped[int | None] = mapped_column(Integer, nullable=True)  # paradas de línea (obs. demo v0.6)
    motivo_parada: Mapped[str] = mapped_column(String(160), default="")
    estado: Mapped[str] = mapped_column(String(20), default="EN PROCESO")  # lista cerrada: production.ESTADOS_PARTE
    observacion: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    # Ronda 23-oct-2026: parte en línea como el control de producción (pallets, MP, colaboradores, pausas, defectos, OEE)
    maquina: Mapped[str] = mapped_column(String(30), default="")  # máquina para la velocidad nominal (R1, ENFARDADO_500…)
    maquinista: Mapped[str] = mapped_column(String(120), default="")
    ean: Mapped[str] = mapped_column(String(20), default="")
    ean_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    lote_pt: Mapped[str] = mapped_column(String(60), default="")
    fv_pt: Mapped[date | None] = mapped_column(Date, nullable=True)
    fv_mp: Mapped[date | None] = mapped_column(Date, nullable=True)
    und_paquete: Mapped[float | None] = mapped_column(Float, nullable=True)
    sacos: Mapped[float | None] = mapped_column(Float, nullable=True)
    peso_saco_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    saldo_mp_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    refrigerio_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pallets: Mapped[list] = mapped_column(JSON, default=list)  # [{destino, cantidad}]
    colaboradores: Mapped[list] = mapped_column(JSON, default=list)  # [{nombre, inicio, fin, refrigerio_min, kg}]
    pausas: Mapped[list] = mapped_column(JSON, default=list)  # [{inicio, fin, causa, foto, user}]
    defectos: Mapped[dict] = mapped_column(JSON, default=dict)  # {causa: unidades}
    indicadores: Mapped[dict] = mapped_column(JSON, default=dict)  # OEE, peso promedio, desviación, horas efectivas…
    inicio_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fin_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bloqueo: Mapped[dict] = mapped_column(JSON, default=dict)  # BLOQUEADO por Calidad: {motivo, user, ts}
    # ronda UX 24-oct-2026: «Pendiente de: motivo» y horario previsto del parte programado
    motivo_estado: Mapped[str] = mapped_column(String(200), default="")
    programa: Mapped[dict] = mapped_column(JSON, default=dict)  # {fecha, kg, hora_inicio, hora_fin}
    product = relationship("Product", primaryjoin="foreign(ProductionReport.product_code) == Product.code", viewonly=True)


class ProductionPlan(Base):
    """Planeamiento de producción ingresado por Producción (día, semana o mes) para contrastarlo con la liquidación."""
    __tablename__ = "production_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    periodo: Mapped[str] = mapped_column(String(10), default="DIA")  # DIA / SEMANA / MES
    fecha: Mapped[date] = mapped_column(Date, index=True)  # día, lunes de la semana o primer día del mes
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"))
    cantidad: Mapped[float] = mapped_column(Float)
    line_code: Mapped[str | None] = mapped_column(ForeignKey("production_lines.code"), nullable=True)
    comentario: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    # obs. demo v0.7: MANUAL (lo registra Producción) o SISTEMA (preprogramado con los requerimientos; lo edita el Jefe)
    origen: Mapped[str] = mapped_column(String(10), default="MANUAL")
    # ronda 23-oct-2026: el cambio que propone un asistente queda pendiente hasta que lo valida el Jefe de Producción
    cambio_pendiente: Mapped[dict] = mapped_column(JSON, default=dict)
    product = relationship("Product")


class CustomerCondition(Base):
    """Condiciones comerciales del cliente (LISTA DE CLIENTES - CON PENALIDADES Y LOTES): ejecutivo, canal, tipo de
    solicitud, lotes por SKU, vida útil y penalidades. Se vincula por RUC si la fila lo trae; si no, por nombre normalizado."""
    __tablename__ = "customer_conditions"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(250))
    nombre_norm: Mapped[str] = mapped_column(String(250), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    ruc: Mapped[str] = mapped_column(String(20), default="", index=True)  # opcional (se agregará a la lista, R2 13-oct)
    ejecutivo: Mapped[str] = mapped_column(String(120), default="")
    canal_comercial: Mapped[str] = mapped_column(String(80), default="")
    solicitud: Mapped[str] = mapped_column(String(60), default="")  # PRODUCTO TERMINADO / MATERIA PRIMA
    lotes_texto: Mapped[str] = mapped_column(String(60), default="")
    max_lotes_por_sku: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vida_util_texto: Mapped[str] = mapped_column(String(120), default="")
    vida_util_meses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    penalidades: Mapped[str] = mapped_column(Text, default="")
    penalidad_tipos: Mapped[list] = mapped_column(JSON, default=list)
    # monto por tipo de penalidad cuando la lista no lo trae: {"VENTANA_HORARIA": {"modo": "FIJO"|"PCT_OV", "valor": n}}
    penalidad_montos: Mapped[dict] = mapped_column(JSON, default=dict)
    fill_rate_min_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    origen: Mapped[str] = mapped_column(String(200), default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    customer = relationship("Customer")


# ------------------------------ marcha blanca (22-oct-2026) ------------------------------
class Observation(Base):
    """Observación reportada por un usuario desde cualquier pantalla (botón «Reportar observación»)."""
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    url: Mapped[str] = mapped_column(String(400), default="")
    pantalla: Mapped[str] = mapped_column(String(200), default="")
    tipo: Mapped[str] = mapped_column(String(20), default="ERROR")  # ERROR / MEJORA / DUDA
    comentario: Mapped[str] = mapped_column(Text, default="")
    captura: Mapped[str] = mapped_column(String(250), default="")
    # SIN_CLASIFICAR / BLOQUEANTE / MAYOR / MENOR / MEJORA
    clasificacion: Mapped[str] = mapped_column(String(20), default="SIN_CLASIFICAR")
    estado: Mapped[str] = mapped_column(String(20), default="ABIERTA")  # ABIERTA / EN_CURSO / CORREGIDA / DESCARTADA
    respuesta: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[str] = mapped_column(String(40), default="")
    atendido_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    atendido_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user = relationship("User", foreign_keys=[user_id])
    atendido = relationship("User", foreign_keys=[atendido_por])


class Shift(Base):
    """Turno de trabajo: días de la semana (0 = lunes), hora de inicio y fin (si fin < inicio, termina al día siguiente)
    y minutos de refrigerio que se descuentan."""
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    dias: Mapped[list] = mapped_column(JSON, default=list)
    inicio: Mapped[str] = mapped_column(String(5))
    fin: Mapped[str] = mapped_column(String(5))
    refrigerio_min: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class UserShift(Base):
    """Turno asignado a una persona en un rango de fechas. Rotación semanal: aplica a las semanas en que
    (n.° de semana ISO) mod ciclo == semana. Una persona puede tener varios turnos. REFUERZO: personal agregado para
    atender una emergencia (también cuenta como «en turno»)."""
    __tablename__ = "user_shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # vacío: refuerzo de un tercero
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True)
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    ciclo: Mapped[int] = mapped_column(Integer, default=1)
    semana: Mapped[int] = mapped_column(Integer, default=0)
    tipo: Mapped[str] = mapped_column(String(10), default="REGULAR")  # REGULAR / REFUERZO
    inicio: Mapped[str] = mapped_column(String(5), default="")  # refuerzo sin turno: horario propio
    fin: Mapped[str] = mapped_column(String(5), default="")
    motivo: Mapped[str] = mapped_column(Text, default="")
    # V7: refuerzo de emergencia con personal de la empresa o de un tercero (costo por hora → costo de horas extra)
    area: Mapped[str] = mapped_column(String(40), default="", server_default="")
    tercero_nombre: Mapped[str] = mapped_column(String(120), default="", server_default="")
    tercero_empresa: Mapped[str] = mapped_column(String(120), default="", server_default="")
    tercero_doc: Mapped[str] = mapped_column(String(20), default="", server_default="")
    costo_hora: Mapped[float | None] = mapped_column(Float, nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User", foreign_keys=[user_id])
    shift = relationship("Shift")

    @property
    def persona(self):
        return self.user.nombre if self.user else f"{self.tercero_nombre} ({self.tercero_empresa or 'tercero'})"


class SapDiscrepancy(Base):
    """Diferencia entre lo cargado desde SAP y lo registrado en el módulo (marcha blanca en paralelo). Se regulariza
    o se levanta la observación con motivo."""
    __tablename__ = "sap_discrepancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    origen: Mapped[str] = mapped_column(String(20))  # STOCK / OV / LIQUIDACION / DESPACHO / FACTURA
    area: Mapped[str] = mapped_column(String(40))
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    referencia: Mapped[str] = mapped_column(String(80), default="")  # OV, OF, guía, factura
    product_code: Mapped[str] = mapped_column(String(40), default="")
    lote: Mapped[str] = mapped_column(String(60), default="")
    almacen: Mapped[str] = mapped_column(String(20), default="")
    campo: Mapped[str] = mapped_column(String(60), default="")
    valor_sap: Mapped[str] = mapped_column(String(200), default="")
    valor_modulo: Mapped[str] = mapped_column(String(200), default="")
    detalle: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(15), default="PENDIENTE")  # PENDIENTE / REGULARIZADA / LEVANTADA
    motivo: Mapped[str] = mapped_column(Text, default="")
    resuelto_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resuelto_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resuelto = relationship("User", foreign_keys=[resuelto_por])


# ---------------------------------------------------------------------------
# Ronda 23-oct-2026: Finanzas, expediente, margen, objetivos, incentivos, oportunidades, GS1, personal y asistencia
# ---------------------------------------------------------------------------
class CustomerInvoice(Base):
    """Factura o nota de crédito del cliente (carga SAP en Excel, PDF o registro de Finanzas). El saldo se actualiza con
    los pagos confirmados por Finanzas."""
    __tablename__ = "customer_invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(15), default="FACTURA")  # FACTURA / NOTA_CREDITO
    numero: Mapped[str] = mapped_column(String(40), index=True)
    referencia: Mapped[str] = mapped_column(String(40), default="")  # factura que afecta la nota de crédito
    fecha: Mapped[date] = mapped_column(Date)
    vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    moneda: Mapped[str] = mapped_column(String(10), default="SOLES")
    monto: Mapped[float] = mapped_column(Float, default=0)
    saldo: Mapped[float] = mapped_column(Float, default=0)
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE")  # PENDIENTE / PARCIAL / PAGADA / ANULADA
    archivo: Mapped[str] = mapped_column(String(250), default="")
    origen: Mapped[str] = mapped_column(String(20), default="MANUAL")  # MANUAL / EXCEL / PDF / SAP
    observacion: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    customer = relationship("Customer")
    order = relationship("SalesOrder")
    __table_args__ = (UniqueConstraint("tipo", "numero", name="uq_invoice_tipo_numero"),)


class CustomerPayment(Base):
    """Comprobante de pago subido por Comercial o Finanzas; Finanzas lo confirma y se aplica al saldo de la factura."""
    __tablename__ = "customer_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("customer_invoices.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date)
    monto: Mapped[float] = mapped_column(Float)
    medio: Mapped[str] = mapped_column(String(40), default="")
    operacion: Mapped[str] = mapped_column(String(60), default="")
    archivo: Mapped[str] = mapped_column(String(250), default="")
    estado: Mapped[str] = mapped_column(String(12), default="REPORTADO")  # REPORTADO / CONFIRMADO / OBSERVADO
    observacion: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    confirmado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    customer = relationship("Customer")
    invoice = relationship("CustomerInvoice")
    user = relationship("User", foreign_keys=[user_id])


class OrderAttachment(Base):
    """Documentos del expediente de la OV: orden de compra, constancia de devolución, nota de crédito, otros."""
    __tablename__ = "order_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # OC / DEVOLUCION / NOTA_CREDITO / OTRO
    nombre: Mapped[str] = mapped_column(String(200), default="")
    archivo: Mapped[str] = mapped_column(String(250))
    observacion: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User")


class MarginInvestment(Base):
    """Inversión adicional (mercaderismo u otra) por cliente y mes, para el margen de contribución variable."""
    __tablename__ = "margin_investments"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    mes: Mapped[str] = mapped_column(String(7), index=True)  # AAAA-MM
    concepto: Mapped[str] = mapped_column(String(60), default="MERCADERISMO")
    monto: Mapped[float] = mapped_column(Float, default=0)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    customer = relationship("Customer")


class SalesTarget(Base):
    """Objetivo de ventas mensual: GENERAL, por CANAL o por VENDEDOR (soles y, opcionalmente, kg)."""
    __tablename__ = "sales_targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    mes: Mapped[str] = mapped_column(String(7), index=True)
    alcance: Mapped[str] = mapped_column(String(10))  # GENERAL / CANAL / VENDEDOR
    clave: Mapped[str] = mapped_column(String(120), default="")  # canal o id del vendedor
    soles: Mapped[float] = mapped_column(Float, default=0)
    kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    nuevos_clientes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # V7
    nuevos_sku: Mapped[int | None] = mapped_column(Integer, nullable=True)  # V7: SKU nuevos en clientes existentes
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("mes", "alcance", "clave", name="uq_target"),)


class IncentiveRule(Base):
    """Regla de incentivo de vendedores (varía por canal y vendedor). Precedencia: vendedor+canal > vendedor > canal >
    general."""
    __tablename__ = "incentive_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    canal: Mapped[str] = mapped_column(String(60), default="")  # vacío = todos
    vendedor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # vacío = todos
    base: Mapped[str] = mapped_column(String(15), default="VENTA")  # VENTA / MARGEN_BRUTO / MARGEN_CONTRIB
    pct: Mapped[float] = mapped_column(Float, default=0)
    cumplimiento_min_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # vs objetivo del vendedor
    tope: Mapped[float | None] = mapped_column(Float, nullable=True)
    desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    observacion: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    vendedor = relationship("User", foreign_keys=[vendedor_id])


class Opportunity(Base):
    """Oportunidad comercial (reemplaza el módulo de oportunidades de SAP)."""
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vendedor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    titulo: Mapped[str] = mapped_column(String(200))
    productos: Mapped[str] = mapped_column(Text, default="")  # productos de interés
    proyeccion_mensual: Mapped[float | None] = mapped_column(Float, nullable=True)  # S/ por mes
    proyeccion_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default="ABIERTA")  # ABIERTA / COTIZADA / NEGOCIACION / GANADA / PERDIDA
    tipo: Mapped[str] = mapped_column(String(15), default="NUEVO")  # NUEVO (cliente nuevo) / ADICIONAL (venta adicional)
    motivo_cierre: Mapped[str] = mapped_column(Text, default="")
    creado_ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    cerrado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    customer = relationship("Customer")
    vendedor = relationship("User")
    actions = relationship("CustomerAction", back_populates="opportunity", order_by="CustomerAction.fecha.desc()")


class CustomerAction(Base):
    """Acción con el cliente: visita, llamada, reunión virtual, mensajería, carta u oficio, etc."""
    __tablename__ = "customer_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(30))
    fecha: Mapped[date] = mapped_column(Date)
    gasto: Mapped[float | None] = mapped_column(Float, nullable=True)
    resultado: Mapped[str] = mapped_column(Text, default="")
    proxima_accion: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    customer = relationship("Customer")
    opportunity = relationship("Opportunity", back_populates="actions")
    user = relationship("User")


class Quote(Base):
    """Cotización (oferta de venta) a un cliente o prospecto."""
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date)
    vigencia: Mapped[date | None] = mapped_column(Date, nullable=True)
    lineas: Mapped[list] = mapped_column(JSON, default=list)  # [{product_code, descripcion, cantidad, precio}]
    total: Mapped[float] = mapped_column(Float, default=0)
    estado: Mapped[str] = mapped_column(String(12), default="EMITIDA")  # EMITIDA / ACEPTADA / RECHAZADA / VENCIDA
    observacion: Mapped[str] = mapped_column(Text, default="")
    origen: Mapped[str] = mapped_column(String(10), default="MODULO", server_default="MODULO")  # MODULO / SAP (V7)
    sap_docnum: Mapped[str] = mapped_column(String(20), default="", server_default="")  # N° de la oferta en SAP
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    customer = relationship("Customer")
    opportunity = relationship("Opportunity")
    user = relationship("User")


class ProductGTIN(Base):
    """Relación GS1 (EAN13 / EAN14) ↔ código SAP; se carga en Configuración."""
    __tablename__ = "product_gtins"
    gtin: Mapped[str] = mapped_column(String(20), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10), default="")  # EAN13 / EAN14
    product_code: Mapped[str] = mapped_column(String(40), index=True)
    marca: Mapped[str] = mapped_column(String(80), default="")
    descripcion: Mapped[str] = mapped_column(String(250), default="")
    envase: Mapped[str] = mapped_column(String(60), default="")
    contenido: Mapped[str] = mapped_column(String(30), default="")
    unidad: Mapped[str] = mapped_column(String(20), default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


class Worker(Base):
    """Personal operativo de Producción (no son usuarios del sistema): asistencia y productividad."""
    __tablename__ = "workers"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(160))
    documento: Mapped[str] = mapped_column(String(20), default="")
    area: Mapped[str] = mapped_column(String(40), default="Producción")  # área a la que pertenece (asistencia por área)
    linea: Mapped[str] = mapped_column(String(20), default="")
    sublinea: Mapped[str] = mapped_column(String(40), default="")
    externo: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


class Attendance(Base):
    __tablename__ = "attendance"
    id: Mapped[int] = mapped_column(primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    estado: Mapped[str] = mapped_column(String(20))  # lista configurable: asistencia_estados
    observacion: Mapped[str] = mapped_column(String(250), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    worker = relationship("Worker")
    __table_args__ = (UniqueConstraint("worker_id", "fecha", name="uq_attendance"),)


# ---------------------------------------------------------------------------
# Mantenimiento integral (ronda UX 24-oct-2026)
# ---------------------------------------------------------------------------
class MaintenancePlan(Base):
    """Plan de mantenimiento preventivo de una unidad: tarea con frecuencia por kilometraje y/o por días."""
    __tablename__ = "maintenance_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    tarea: Mapped[str] = mapped_column(String(120))
    cada_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    cada_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ultimo_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    ultima_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    vehicle = relationship("Vehicle")


class Breakdown(Base):
    """Mantenimiento correctivo: avería reportada, programada, en reparación y cerrada."""
    __tablename__ = "breakdowns"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    descripcion: Mapped[str] = mapped_column(Text)
    severidad: Mapped[str] = mapped_column(String(10), default="MEDIA")  # ALTA / MEDIA / BAJA
    estado: Mapped[str] = mapped_column(String(15), default="REPORTADA")  # REPORTADA / PROGRAMADA / EN_REPARACION / CERRADA
    km: Mapped[float | None] = mapped_column(Float, nullable=True)
    fecha_programada: Mapped[date | None] = mapped_column(Date, nullable=True)
    taller: Mapped[str] = mapped_column(String(120), default="")
    costo: Mapped[float | None] = mapped_column(Float, nullable=True)
    solucion: Mapped[str] = mapped_column(Text, default="")
    historial: Mapped[list] = mapped_column(JSON, default=list)  # [{estado, user, ts, nota}]
    foto: Mapped[str] = mapped_column(String(250), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    cierre_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    vehicle = relationship("Vehicle")


class SanitationZone(Base):
    """Zona física para limpieza, desinfección y fumigación periódicas."""
    __tablename__ = "sanitation_zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    area: Mapped[str] = mapped_column(String(40), default="")  # Almacén, Producción, Oficinas…
    almacen: Mapped[str] = mapped_column(String(20), default="")
    frecuencia_limpieza_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frecuencia_fumigacion_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


class SanitationLog(Base):
    """Bitácora de saneamiento: limpieza, desinfección, fumigación o mantenimiento de una zona, o fumigación de una
    unidad vehicular (control fitosanitario de plagas, p. ej. gorgojo)."""
    __tablename__ = "sanitation_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("sanitation_zones.id"), nullable=True, index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # LIMPIEZA / DESINFECCION / FUMIGACION / MANTENIMIENTO
    fecha: Mapped[date] = mapped_column(Date)
    responsable: Mapped[str] = mapped_column(String(120), default="")  # persona o empresa que lo realizó
    producto: Mapped[str] = mapped_column(String(120), default="")
    certificado: Mapped[str] = mapped_column(String(60), default="")
    vence: Mapped[date | None] = mapped_column(Date, nullable=True)  # próxima fecha / vigencia
    observacion: Mapped[str] = mapped_column(Text, default="")
    evidencia: Mapped[str] = mapped_column(String(250), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    zone = relationship("SanitationZone")
    vehicle = relationship("Vehicle")


# ---------------------------------------------------------------------------
# Cadena de suministro (ronda UX 24-oct-2026)
# ---------------------------------------------------------------------------
class DemandForecast(Base):
    """Proyección de demanda cargada por Comercial (por producto y mes; opcionalmente por canal o cliente)."""
    __tablename__ = "demand_forecasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    mes: Mapped[str] = mapped_column(String(7), index=True)  # AAAA-MM
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"), index=True)
    cantidad: Mapped[float] = mapped_column(Float)
    canal: Mapped[str] = mapped_column(String(60), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    observacion: Mapped[str] = mapped_column(String(250), default="")
    # V7: cambio solicitado sobre una proyección ya registrada; lo autoriza Gerencia General
    cambio: Mapped[dict] = mapped_column(JSON, default=dict)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    product = relationship("Product")
    customer = relationship("Customer")


class MoveRequest(Base):
    """Solicitud de movimiento punto a punto para el montacarguista (de cualquier área), con foto de validación."""
    __tablename__ = "move_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    area: Mapped[str] = mapped_column(String(40), default="")  # área que solicita
    almacen: Mapped[str] = mapped_column(String(20), default="")
    origen: Mapped[str] = mapped_column(String(120))
    destino: Mapped[str] = mapped_column(String(120))
    detalle: Mapped[str] = mapped_column(String(250), default="")  # producto / lote / pallets
    cantidad: Mapped[str] = mapped_column(String(40), default="")
    prioridad: Mapped[str] = mapped_column(String(10), default="MEDIA")
    # V7: inmediato o programado para una fecha y hora
    tipo: Mapped[str] = mapped_column(String(10), default="INMEDIATO", server_default="INMEDIATO")
    programado_para: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    aviso_min: Mapped[int | None] = mapped_column(Integer, nullable=True)  # V8 (A04): aviso antes de la hora programada
    avisado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    historial: Mapped[list] = mapped_column(JSON, default=list)  # V8 (A05): reasignaciones con rastro
    estado: Mapped[str] = mapped_column(String(15), default="SOLICITADA")  # SOLICITADA / EN_CURSO / COMPLETADA / ANULADA
    solicitado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    asignado_a: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    foto_inicio: Mapped[str] = mapped_column(String(250), default="")
    foto_fin: Mapped[str] = mapped_column(String(250), default="")
    observacion: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    inicio_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fin_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    solicitante = relationship("User", foreign_keys=[solicitado_por])
    operador = relationship("User", foreign_keys=[asignado_a])


# ---------------------------------------------------------------------------
# Observaciones del módulo V7 (26-oct-2026)
# ---------------------------------------------------------------------------
class CustomerPenalty(Base):
    """Penalidad de un cliente: la detecta el sistema al registrar la entrega (fecha, entrega parcial, fill rate) o la
    registra Comercial. Se resuelve como PAGADA (con el monto pagado) o DESESTIMADA (con el motivo)."""
    __tablename__ = "customer_penalties"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(60))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    origen: Mapped[str] = mapped_column(String(10), default="SISTEMA")  # SISTEMA / MANUAL
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    monto_calculado: Mapped[float] = mapped_column(Float, default=0)
    base_calculo: Mapped[str] = mapped_column(String(250), default="")
    monto_pagado: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default="PENDIENTE")  # PENDIENTE / PAGADA / DESESTIMADA
    comentario: Mapped[str] = mapped_column(Text, default="")
    vendedor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resuelto_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resuelto_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    customer = relationship("Customer")
    order = relationship("SalesOrder")
    vendedor = relationship("User", foreign_keys=[vendedor_id])


class ProductDocument(Base):
    """Carpeta del producto (V7): ficha técnica, fotos, certificados, recetas y estrategias comerciales."""
    __tablename__ = "product_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code"), index=True)
    carpeta: Mapped[str] = mapped_column(String(20))  # FICHA_TECNICA / FOTOS / CERTIFICADOS / RECETAS / ESTRATEGIAS
    nombre: Mapped[str] = mapped_column(String(200), default="")
    archivo: Mapped[str] = mapped_column(String(250))
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User")


class SapOrderHeader(Base):
    """V8: cabecera de una OV tal como la exporta SAP (lista de pedidos). Las OV abiertas esperan aquí su detalle
    (exportación de líneas de cada OV); al llegar, se crea la OV del módulo. Se identifica por el número de SAP."""
    __tablename__ = "sap_order_headers"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_venc: Mapped[date | None] = mapped_column(Date, nullable=True)
    cliente: Mapped[str] = mapped_column(String(200), default="")
    card_code: Mapped[str] = mapped_column(String(30), default="")
    ruc: Mapped[str] = mapped_column(String(20), default="")
    vendedor: Mapped[str] = mapped_column(String(120), default="")
    comentario: Mapped[str] = mapped_column(Text, default="")
    destino: Mapped[str] = mapped_column(String(250), default="")
    peso_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado_sap: Mapped[str] = mapped_column(String(20), default="")  # Abiertos / Cerrado
    cancelado: Mapped[bool] = mapped_column(Boolean, default=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    actualizado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    order = relationship("SalesOrder")


class ReportTemplate(Base):
    """V11 (28-oct-2026): configuración guardada de un informe personalizado. PERSONAL (solo su dueño) o COMPARTIDA
    (la publica una jefatura para su área). Al usarla se vuelven a aplicar las reglas de visibilidad del perfil que la
    abre: una plantilla nunca muestra indicadores o columnas que ese perfil no puede ver."""
    __tablename__ = "report_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    alcance: Mapped[str] = mapped_column(String(12), default="PERSONAL")  # PERSONAL / COMPARTIDA
    area: Mapped[str] = mapped_column(String(40), default="")  # área a la que se comparte
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # {fuente, col, desde_dias, q, agrupar, elem, ind, ...}
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    creado_ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    actualizado_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user = relationship("User")
