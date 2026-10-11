# Modelo de datos (generado desde `app/models.py`)

Motor por defecto: SQLite (prototipo). Portable a PostgreSQL / SQL Server mediante `DATABASE_URL` (SQLAlchemy 2).
Las tablas se crean al iniciar la aplicación (`create_all`). Para producción se recomienda incorporar migraciones (Alembic).

## `alert_types`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| code | VARCHAR(50) | no | PK |
| nombre | VARCHAR(160) | no |  |
| area | VARCHAR(40) | no |  |
| grupo | VARCHAR(60) | no |  |
| prioridad | VARCHAR(10) | no |  |
| roles | JSON | no |  |
| usuarios | JSON | no |  |
| enviar_correo | BOOLEAN | no |  |
| activo | BOOLEAN | no |  |
| origen_destinatarios | VARCHAR(12) | no |  |
| fuente | VARCHAR(200) | no |  |
| condicion | TEXT | no |  |

## `customers`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| ruc | VARCHAR(20) | no |  |
| nombre | VARCHAR(200) | no |  |
| grupo | VARCHAR(60) | no |  |
| direccion | VARCHAR(250) | no |  |
| distrito | VARCHAR(80) | no |  |
| provincia | VARCHAR(80) | no |  |
| horario_recepcion | VARCHAR(60) | no |  |
| requiere_cita | BOOLEAN | no |  |
| vida_util_min_dias | INTEGER | sí |  |

Restricción única: (ruc)

## `import_phase_templates`

Fases configurables de importación (IF §11, §16). Las fases concretas están pendientes de definición.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| orden | INTEGER | no |  |
| nombre | VARCHAR(80) | no |  |
| dias_desde_inicio | INTEGER | no |  |
| recordatorio_dias | INTEGER | no |  |
| responsable_rol | VARCHAR(40) | no |  |
| estado_def | VARCHAR(12) | no |  |

## `lead_times`

Plazos de reposición comunicados por Compras (IF §7) – días naturales.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| categoria | VARCHAR(60) | no |  |
| dias_min | INTEGER | no |  |
| dias_max | INTEGER | no |  |
| mes_desde | INTEGER | sí |  |
| mes_hasta | INTEGER | sí |  |
| descripcion | VARCHAR(200) | no |  |
| fuente | VARCHAR(200) | no |  |

## `params`

Parámetro configurable (IF §16). estado: DEFINIDO / PROPUESTO / PENDIENTE / DEMO.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| key | VARCHAR(80) | no | PK |
| valor | JSON | no |  |
| tipo | VARCHAR(20) | no |  |
| grupo | VARCHAR(40) | no |  |
| descripcion | TEXT | no |  |
| estado | VARCHAR(12) | no |  |
| fuente | VARCHAR(200) | no |  |
| version | INTEGER | no |  |

## `permissions`

Permiso atómico; tipo = consulta/edicion/aprobacion/administracion (IF §19).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| code | VARCHAR(60) | no | PK |
| nombre | VARCHAR(200) | no |  |
| modulo | VARCHAR(40) | no |  |
| tipo | VARCHAR(20) | no |  |

## `production_lines`

Líneas de producción (formatos PDF: Envasado R1-R2-R3, Truer, Cimbria, Selección manual).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| code | VARCHAR(20) | no | PK |
| nombre | VARCHAR(80) | no |  |
| capacidad_kg_dia | FLOAT | sí |  |
| activa | BOOLEAN | no |  |
| fuente | VARCHAR(200) | no |  |

## `products`

Artículo (formato TABLA_DATA de 'PCP 2026 - J.xlsm' y columnas de OVS/BOM).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| code | VARCHAR(30) | no | PK |
| descripcion | VARCHAR(200) | no |  |
| um | VARCHAR(20) | no |  |
| peso_kg | FLOAT | sí |  |
| tipo | VARCHAR(10) | no |  |
| calidad | VARCHAR(30) | no |  |
| maquina | VARCHAR(30) | no |  |
| marca | VARCHAR(60) | no |  |
| familia | VARCHAR(60) | no |  |
| subfamilia | VARCHAR(60) | no |  |
| producto_base | VARCHAR(120) | no |  |
| presentacion | VARCHAR(40) | no |  |
| categoria_reposicion | VARCHAR(60) | no |  |
| grupo_humedad | VARCHAR(60) | no |  |
| stock_minimo | FLOAT | sí |  |
| periodo_analisis_dias | INTEGER | sí |  |
| margen_seguridad_dias | INTEGER | sí |  |
| merma_pct | FLOAT | sí |  |
| tiempo_max_almacen_dias | INTEGER | sí |  |
| origen | VARCHAR(40) | no |  |

## `roles`

Rol/perfil (IF §15).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| code | VARCHAR(40) | no | PK |
| nombre | VARCHAR(120) | no |  |
| area | VARCHAR(40) | no |  |
| fuente | VARCHAR(200) | no |  |
| observacion | TEXT | no |  |

## `warehouses`

Almacén (IF §6.2). uso: PT / MP_INSUMOS / ALTERNATIVO / OTRO.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| code | VARCHAR(20) | no | PK |
| nombre | VARCHAR(80) | no |  |
| uso | VARCHAR(20) | no |  |
| prioridad | INTEGER | no |  |
| reservable | BOOLEAN | no |  |
| fuente | VARCHAR(200) | no |  |
| observacion | TEXT | no |  |

## `role_permissions`

Matriz rol-permiso. origen: DEFINIDO (regla expresa) o PROPUESTO (derivado del alcance por área, requiere validación).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| role_code | VARCHAR(40) | no | → roles.code |
| perm_code | VARCHAR(60) | no | → permissions.code |
| origen | VARCHAR(12) | no |  |
| fuente | VARCHAR(200) | no |  |

Restricción única: (role_code, perm_code)

## `users`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| username | VARCHAR(60) | no |  |
| nombre | VARCHAR(120) | no |  |
| email | VARCHAR(160) | no |  |
| role_code | VARCHAR(40) | no | → roles.code |
| password_hash | VARCHAR(255) | no |  |
| activo | BOOLEAN | no |  |
| debe_cambiar_clave | BOOLEAN | no |  |

Restricción única: (username)

## `alerts`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| type_code | VARCHAR(50) | no | → alert_types.code |
| titulo | VARCHAR(250) | no |  |
| mensaje | TEXT | no |  |
| prioridad | VARCHAR(10) | no |  |
| area | VARCHAR(40) | no |  |
| entidad | VARCHAR(40) | no |  |
| entidad_id | VARCHAR(40) | no |  |
| estado | VARCHAR(15) | no |  |
| roles | JSON | no |  |
| usuarios | JSON | no |  |
| asignado_a | INTEGER | sí | → users.id |
| creado_ts | DATETIME | no |  |
| creado_por | INTEGER | sí | → users.id |
| cerrado_ts | DATETIME | sí |  |
| cerrado_por | INTEGER | sí | → users.id |
| motivo_cierre | TEXT | no |  |
| accion_tomada | TEXT | no |  |
| dedup_key | VARCHAR(160) | no |  |

## `audit_log`

Trazabilidad de cambios, aprobaciones, cargas, etc. (IF §2, §19).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| ts | DATETIME | no |  |
| user_id | INTEGER | sí | → users.id |
| accion | VARCHAR(80) | no |  |
| entidad | VARCHAR(60) | no |  |
| entidad_id | VARCHAR(60) | no |  |
| detalle | JSON | no |  |

## `date_changes`

Historial de cambios de fecha prevista (compras nacionales e importaciones).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| entidad | VARCHAR(20) | no |  |
| entidad_id | INTEGER | no |  |
| anterior | DATE | sí |  |
| nueva | DATE | sí |  |
| motivo | TEXT | no |  |
| user_id | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |

## `drivers`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| nombre | VARCHAR(120) | no |  |
| licencia | VARCHAR(30) | no |  |
| externo | BOOLEAN | no |  |
| disponible | BOOLEAN | no |  |
| user_id | INTEGER | sí | → users.id |

## `gg_alert_prefs`

Gerencia General configura qué alertas recibe directamente por correo (IF §14).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| user_id | INTEGER | no | → users.id |
| type_code | VARCHAR(50) | no | → alert_types.code |
| recibir_directo | BOOLEAN | no |  |

Restricción única: (user_id, type_code)

## `import_shipments`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| referencia | VARCHAR(60) | no |  |
| proveedor | VARCHAR(160) | no |  |
| product_code | VARCHAR(30) | no | → products.code |
| cantidad | FLOAT | no |  |
| fecha_llegada_estimada | DATE | sí |  |
| estado | VARCHAR(20) | no |  |
| warehouse_code | VARCHAR(20) | sí | → warehouses.code |
| cantidad_recibida | FLOAT | sí |  |
| lote_recibido | VARCHAR(60) | no |  |
| diferencias | TEXT | no |  |
| creado_por | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |

Restricción única: (referencia)

## `param_history`

Versiones de configuración (IF §19 'Guardar versiones de listas y configuraciones').

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| key | VARCHAR(80) | no |  |
| version | INTEGER | no |  |
| valor | JSON | no |  |
| estado | VARCHAR(12) | no |  |
| ts | DATETIME | no |  |
| user_id | INTEGER | sí | → users.id |

## `physical_counts`

Conteo físico periódico (IF §6.3/§6.4; formato 'Inven. bobinas 1524.xlsx').

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| warehouse_code | VARCHAR(20) | no | → warehouses.code |
| fecha | DATE | no |  |
| estado | VARCHAR(20) | no |  |
| user_id | INTEGER | sí | → users.id |
| observacion | TEXT | no |  |

## `sales_orders`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| numero | VARCHAR(30) | no |  |
| customer_id | INTEGER | no | → customers.id |
| vendedor_id | INTEGER | sí | → users.id |
| vendedor_nombre | VARCHAR(120) | no |  |
| fecha_emision | DATE | no |  |
| fecha_compromiso | DATE | no |  |
| urgente | BOOLEAN | no |  |
| direccion | VARCHAR(250) | no |  |
| distrito | VARCHAR(80) | no |  |
| hora_cita | VARCHAR(20) | no |  |
| cita_confirmada | BOOLEAN | no |  |
| comentarios | TEXT | no |  |
| estado | VARCHAR(24) | no |  |
| estado_stock | VARCHAR(20) | no |  |
| cobertura_unidades | FLOAT | no |  |
| cobertura_lineas | FLOAT | no |  |
| decision_parcial | VARCHAR(20) | no |  |
| motivo_detencion | VARCHAR(250) | no |  |
| origen | VARCHAR(20) | no |  |
| version | INTEGER | no |  |
| creado_por | INTEGER | sí | → users.id |
| creado_ts | DATETIME | no |  |
| evaluado_ts | DATETIME | sí |  |
| prep_inicio | DATETIME | sí |  |
| prep_fin | DATETIME | sí |  |
| salida_ts | DATETIME | sí |  |
| entrega_ts | DATETIME | sí |  |
| corte | VARCHAR(10) | no |  |
| alerta80_emitida | BOOLEAN | no |  |
| parcial_aprobaciones | JSON | no |  |
| fecha_saldo | DATE | sí |  |
| parent_id | INTEGER | sí | → sales_orders.id |
| completa_notificada | BOOLEAN | no |  |
| plan_picking_validado | BOOLEAN | no |  |

Restricción única: (numero)

## `upload_batches`

Carga de archivo con validación previa (IF §6.4, §8.1, §19). tipo: STOCK, BOM, OV, LIQUIDACION, PRODUCTOS, SALIDAS. estado: VALIDADO_CON_ERRORES / LISTO / CONFIRMADO / DESCARTADO.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| tipo | VARCHAR(20) | no |  |
| archivo | VARCHAR(250) | no |  |
| hoja | VARCHAR(80) | no |  |
| ts | DATETIME | no |  |
| user_id | INTEGER | sí | → users.id |
| estado | VARCHAR(30) | no |  |
| resumen | JSON | no |  |
| errores_generales | JSON | no |  |
| opciones | JSON | no |  |
| confirmado_ts | DATETIME | sí |  |
| confirmado_por | INTEGER | sí | → users.id |

## `alert_events`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| alert_id | INTEGER | no | → alerts.id |
| ts | DATETIME | no |  |
| user_id | INTEGER | sí | → users.id |
| accion | VARCHAR(30) | no |  |
| comentario | TEXT | no |  |

## `bom_versions`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| version | INTEGER | no |  |
| archivo | VARCHAR(250) | no |  |
| upload_id | INTEGER | sí | → upload_batches.id |
| user_id | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |
| activa | BOOLEAN | no |  |
| incluye_merma | VARCHAR(15) | no |  |
| cambios | JSON | no |  |

## `email_outbox`

Bandeja de salida de correo. Si no hay SMTP configurado, queda en estado SIN_SMTP (no se simula el envío).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| alert_id | INTEGER | sí | → alerts.id |
| destinatario | VARCHAR(160) | no |  |
| asunto | VARCHAR(250) | no |  |
| cuerpo | TEXT | no |  |
| estado | VARCHAR(12) | no |  |
| error | TEXT | no |  |
| ts | DATETIME | no |  |
| enviado_ts | DATETIME | sí |  |

## `import_phases`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| shipment_id | INTEGER | no | → import_shipments.id |
| orden | INTEGER | no |  |
| nombre | VARCHAR(80) | no |  |
| fecha_prevista | DATE | sí |  |
| fecha_real | DATE | sí |  |
| recordatorio_dias | INTEGER | no |  |
| responsable_rol | VARCHAR(40) | no |  |

## `ov_change_requests`

Modificación de OV por Asistente de Ventas que requiere autorización (IF §5).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| order_id | INTEGER | no | → sales_orders.id |
| solicitado_por | INTEGER | no | → users.id |
| payload | JSON | no |  |
| motivo | TEXT | no |  |
| estado | VARCHAR(12) | no |  |
| resuelto_por | INTEGER | sí | → users.id |
| resuelto_ts | DATETIME | sí |  |
| ts | DATETIME | no |  |

## `ov_decisions`

Decisiones humanas ante faltantes (IF §4.5, §5, §6.3): despacho parcial, renegociación de fecha, cambio de producto, uso de almacén alternativo.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| order_id | INTEGER | no | → sales_orders.id |
| tipo | VARCHAR(30) | no |  |
| estado | VARCHAR(12) | no |  |
| detalle | JSON | no |  |
| comentario | TEXT | no |  |
| user_id | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |

## `purchase_requests`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| product_code | VARCHAR(30) | no | → products.code |
| cantidad | FLOAT | no |  |
| fecha_necesidad | DATE | sí |  |
| origen | VARCHAR(20) | no |  |
| order_id | INTEGER | sí | → sales_orders.id |
| analisis | JSON | no |  |
| estado | VARCHAR(30) | no |  |
| requiere_muestra | BOOLEAN | no |  |
| resultado_muestra | VARCHAR(20) | no |  |
| mayor_volumen | BOOLEAN | no |  |
| aprobado_gerencia_por | INTEGER | sí | → users.id |
| proveedor | VARCHAR(160) | no |  |
| cotizacion | TEXT | no |  |
| precio | FLOAT | sí |  |
| numero_oc | VARCHAR(40) | no |  |
| fecha_prevista | DATE | sí |  |
| warehouse_code | VARCHAR(20) | sí | → warehouses.code |
| cantidad_recibida | FLOAT | sí |  |
| diferencias | TEXT | no |  |
| autorizacion_observacion_por | INTEGER | sí | → users.id |
| observaciones_recepcion | TEXT | no |  |
| lote_recibido | VARCHAR(60) | no |  |
| creado_por | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |

## `sales_history`

Historial de salidas/ventas para análisis de reposición (formato hoja 'Qy' de Rotación de inventario).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| product_code | VARCHAR(30) | no |  |
| fecha | DATE | no |  |
| cantidad | FLOAT | no |  |
| documento | VARCHAR(40) | no |  |
| origen | VARCHAR(30) | no |  |
| upload_id | INTEGER | sí | → upload_batches.id |

## `sales_order_lines`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| order_id | INTEGER | no | → sales_orders.id |
| product_code | VARCHAR(30) | no | → products.code |
| cantidad | FLOAT | no |  |
| precio_unitario | FLOAT | no |  |
| preparado | FLOAT | no |  |
| despachado | FLOAT | no |  |
| entregado | FLOAT | no |  |
| activa | BOOLEAN | no |  |

## `stock_lots`

Existencia por artículo/lote/almacén (formato STOCK_LOTE de SAP).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| product_code | VARCHAR(30) | no | → products.code |
| warehouse_code | VARCHAR(20) | no | → warehouses.code |
| lote | VARCHAR(60) | no |  |
| cantidad | FLOAT | no |  |
| fecha_venc | DATE | sí |  |
| fecha_fab | DATE | sí |  |
| fecha_admision | DATE | sí |  |
| estado | VARCHAR(24) | no |  |
| estado_anterior | VARCHAR(24) | no |  |
| motivo_estado | TEXT | no |  |
| verificado | BOOLEAN | no |  |
| cantidad_verificada | FLOAT | sí |  |
| fecha_verificacion | DATETIME | sí |  |
| origen | VARCHAR(60) | no |  |
| upload_id | INTEGER | sí | → upload_batches.id |

Restricción única: (product_code, warehouse_code, lote, estado)

## `upload_rows`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| batch_id | INTEGER | no | → upload_batches.id |
| fila | INTEGER | no |  |
| datos | JSON | no |  |
| errores | JSON | no |  |
| advertencias | JSON | no |  |
| excluida | BOOLEAN | no |  |
| motivo_exclusion | VARCHAR(250) | no |  |
| editada | BOOLEAN | no |  |

## `vehicles`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| placa | VARCHAR(20) | no |  |
| descripcion | VARCHAR(80) | no |  |
| propio | BOOLEAN | no |  |
| capacidad_kg | FLOAT | no |  |
| volumen_m3 | FLOAT | sí |  |
| disponible | BOOLEAN | no |  |
| conductor_habitual_id | INTEGER | sí | → drivers.id |
| observacion | VARCHAR(250) | no |  |

Restricción única: (placa)

## `bom_lines`

Fila del Excel 'LISTA DE MATERIALES 2026.xlsx' (Hoja1).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| version_id | INTEGER | no | → bom_versions.id |
| padre | VARCHAR(30) | no |  |
| padre_desc | VARCHAR(200) | no |  |
| tipo_bom | VARCHAR(5) | no |  |
| cantidad_bom | FLOAT | no |  |
| almacen_pt | VARCHAR(20) | no |  |
| orden | INTEGER | sí |  |
| componente | VARCHAR(30) | no |  |
| componente_desc | VARCHAR(200) | no |  |
| cantidad | FLOAT | no |  |
| almacen_comp | VARCHAR(20) | no |  |
| um | VARCHAR(20) | no |  |
| metodo_emision | VARCHAR(5) | no |  |

## `certificates`

Certificado de calidad autogenerado (IF §9.4; modelos N°CP2026-PT3756 / MP276 / CA0764).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| numero | VARCHAR(40) | no |  |
| serie | VARCHAR(10) | no |  |
| lot_id | INTEGER | sí | → stock_lots.id |
| order_id | INTEGER | sí | → sales_orders.id |
| product_code | VARCHAR(30) | no |  |
| datos | JSON | no |  |
| estado | VARCHAR(20) | no |  |
| generado_ts | DATETIME | no |  |
| revisado_por | INTEGER | sí | → users.id |
| revisado_ts | DATETIME | sí |  |
| cambios | JSON | no |  |

Restricción única: (numero)

## `physical_count_lines`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| count_id | INTEGER | no | → physical_counts.id |
| lot_id | INTEGER | sí | → stock_lots.id |
| product_code | VARCHAR(30) | no |  |
| lote | VARCHAR(60) | no |  |
| sap | FLOAT | no |  |
| peso_unitario | FLOAT | sí |  |
| conteo | FLOAT | sí |  |
| fisico | FLOAT | sí |  |
| faltante | FLOAT | no |  |
| sobrante | FLOAT | no |  |
| comentario | VARCHAR(250) | no |  |

## `quality_records`

Registro de Calidad genérico por formato: MUESTREO (REG-CAL-002 / CP-FOR-CAL-10), RECEPCION_MP (REG-HACCP-CAL-002), FUMIGACION (REG-BPM-CAL-005), NO_CONFORME (REG-BPM-CAL-013), QUEJA (REG-HACCP-CAL-003), NC_ACCION (REG-HACCP-CAL-006), CONTROL_PESOS (REG-CAL-003), CONTROL_GRANOS (REG-CAL-014), RECEPCION_IMPORTADO (REG-CAL-005), VEHICULO (REG-BPM-CAL-011), DISENO_BOBINA, PROCESO.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| formato | VARCHAR(30) | no |  |
| codigo_formato | VARCHAR(30) | no |  |
| fecha | DATE | no |  |
| product_code | VARCHAR(30) | sí |  |
| lote | VARCHAR(60) | no |  |
| lot_id | INTEGER | sí | → stock_lots.id |
| referencia_tipo | VARCHAR(30) | no |  |
| referencia_id | INTEGER | sí |  |
| datos | JSON | no |  |
| resultado | VARCHAR(20) | no |  |
| observaciones | TEXT | no |  |
| estado | VARCHAR(20) | no |  |
| user_id | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |

## `repack_requests`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| tipo | VARCHAR(30) | no |  |
| lot_id | INTEGER | no | → stock_lots.id |
| cantidad | FLOAT | no |  |
| producto_destino | VARCHAR(30) | sí | → products.code |
| cantidad_destino | FLOAT | sí |  |
| order_id | INTEGER | sí | → sales_orders.id |
| motivo | TEXT | no |  |
| estado | VARCHAR(20) | no |  |
| solicitado_por | INTEGER | sí | → users.id |
| evaluado_por | INTEGER | sí | → users.id |
| evaluado_ts | DATETIME | sí |  |
| resultado_calidad | TEXT | no |  |
| ejecutado_por | INTEGER | sí | → users.id |
| ejecucion_inicio | DATETIME | sí |  |
| ejecucion_fin | DATETIME | sí |  |
| lote_resultante | VARCHAR(60) | no |  |
| nueva_fecha_fab | DATE | sí |  |
| nueva_fecha_venc | DATE | sí |  |
| lot_resultante_id | INTEGER | sí | → stock_lots.id |
| ts | DATETIME | no |  |

## `reservations`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| ov_line_id | INTEGER | no | → sales_order_lines.id |
| lot_id | INTEGER | no | → stock_lots.id |
| cantidad | FLOAT | no |  |
| estado | VARCHAR(12) | no |  |
| ts | DATETIME | no |  |
| motivo_liberacion | VARCHAR(200) | no |  |

## `routes`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| fecha | DATE | no |  |
| vehicle_id | INTEGER | sí | → vehicles.id |
| driver_id | INTEGER | sí | → drivers.id |
| requiere_externo | BOOLEAN | no |  |
| zona | VARCHAR(120) | no |  |
| estado | VARCHAR(20) | no |  |
| peso_total | FLOAT | no |  |
| advertencias | JSON | no |  |
| checklist | JSON | no |  |
| fotos | JSON | no |  |
| carga | JSON | no |  |
| carga_validada | BOOLEAN | no |  |
| autorizacion_seguridad | JSON | no |  |
| retorno_ts | DATETIME | sí |  |
| guia_numero | VARCHAR(40) | no |  |
| seguridad | JSON | no |  |
| salida_confirmada_por | INTEGER | sí | → users.id |
| salida_ts | DATETIME | sí |  |
| cierre_ts | DATETIME | sí |  |
| creado_por | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |

## `transfers`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| origen_lot_id | INTEGER | no | → stock_lots.id |
| destino_code | VARCHAR(20) | no | → warehouses.code |
| cantidad | FLOAT | no |  |
| order_id | INTEGER | sí | → sales_orders.id |
| estado | VARCHAR(20) | no |  |
| solicitado_por | INTEGER | sí | → users.id |
| autorizado_por | INTEGER | sí | → users.id |
| autorizado_ts | DATETIME | sí |  |
| salida_ts | DATETIME | sí |  |
| salida_por | INTEGER | sí | → users.id |
| recibido_por | INTEGER | sí | → users.id |
| recibido_ts | DATETIME | sí |  |
| cantidad_recibida | FLOAT | sí |  |
| diferencia | FLOAT | no |  |
| observacion | TEXT | no |  |
| ts | DATETIME | no |  |

## `production_requests`

Solicitud preliminar de producción (IF §8.2).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| order_id | INTEGER | sí | → sales_orders.id |
| product_code | VARCHAR(30) | no | → products.code |
| cantidad | FLOAT | no |  |
| fecha_requerida | DATE | sí |  |
| estado | VARCHAR(20) | no |  |
| origen | VARCHAR(20) | no |  |
| repack_id | INTEGER | sí | → repack_requests.id |
| analisis | JSON | no |  |
| bom_version_id | INTEGER | sí | → bom_versions.id |
| creado_por | INTEGER | sí | → users.id |
| enviado_por | INTEGER | sí | → users.id |
| validado_por | INTEGER | sí | → users.id |
| validacion | JSON | no |  |
| line_code | VARCHAR(20) | sí | → production_lines.code |
| fecha_programada | DATE | sí |  |
| inicio_ts | DATETIME | sí |  |
| fin_ts | DATETIME | sí |  |
| observacion | TEXT | no |  |
| ts | DATETIME | no |  |

## `route_stops`



| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| route_id | INTEGER | no | → routes.id |
| order_id | INTEGER | no | → sales_orders.id |
| orden | INTEGER | no |  |
| peso_kg | FLOAT | no |  |
| estado | VARCHAR(20) | no |  |
| llegada_ts | DATETIME | sí |  |
| entrega_ts | DATETIME | sí |  |
| foto_path | VARCHAR(250) | no |  |
| guia_firmada_path | VARCHAR(250) | no |  |
| guia_numero | VARCHAR(40) | no |  |
| guia_origen | VARCHAR(10) | no |  |
| guia_path | VARCHAR(250) | no |  |
| factura_numero | VARCHAR(40) | no |  |
| factura_path | VARCHAR(250) | no |  |
| factura_con_modificaciones | BOOLEAN | no |  |
| factura_ts | DATETIME | sí |  |
| observacion | TEXT | no |  |

## `incidents`

Incidencias de distribución (IF §12.3).

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| tipo | VARCHAR(30) | no |  |
| route_id | INTEGER | sí | → routes.id |
| stop_id | INTEGER | sí | → route_stops.id |
| order_id | INTEGER | sí | → sales_orders.id |
| descripcion | TEXT | no |  |
| cantidad_afectada | FLOAT | sí |  |
| estado | VARCHAR(15) | no |  |
| user_id | INTEGER | sí | → users.id |
| ts | DATETIME | no |  |
| alert_id | INTEGER | sí | → alerts.id |

## `liquidations`

Liquidación de producción (IF §8.3). Formato SAP: hoja 'Dat.Prod' de 'Recep. pt.xlsx'.

| Columna | Tipo | Nulo | Clave / referencia |
|---|---|---|---|
| id | INTEGER | no | PK |
| numero_documento | VARCHAR(30) | no |  |
| request_id | INTEGER | sí | → production_requests.id |
| product_code | VARCHAR(30) | no | → products.code |
| almacen | VARCHAR(60) | no |  |
| warehouse_code | VARCHAR(20) | sí | → warehouses.code |
| fecha | DATE | no |  |
| cantidad_planificada | FLOAT | no |  |
| cantidad_completada | FLOAT | no |  |
| lote | VARCHAR(60) | no |  |
| fecha_fab | DATE | sí |  |
| fecha_venc | DATE | sí |  |
| valorizado | FLOAT | sí |  |
| realizado_por | VARCHAR(120) | no |  |
| origen | VARCHAR(10) | no |  |
| merma_mp_kg | FLOAT | sí |  |
| merma_insumos | JSON | no |  |
| merma_granel_kg | FLOAT | sí |  |
| estado | VARCHAR(25) | no |  |
| cantidad_recibida | FLOAT | sí |  |
| diferencia | FLOAT | sí |  |
| presentacion_ok | BOOLEAN | sí |  |
| recibido_por | INTEGER | sí | → users.id |
| recibido_ts | DATETIME | sí |  |
| observacion | TEXT | no |  |
| lot_id | INTEGER | sí | → stock_lots.id |
| ts | DATETIME | no |  |

Restricción única: (numero_documento, lote)
