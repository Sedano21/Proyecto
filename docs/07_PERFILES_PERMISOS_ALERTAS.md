# Perfiles, permisos y alertas (generado desde `app/catalogs.py`)

Origen: **D** = definido expresamente en la documentación; **P** = propuesto (derivado del alcance por área, IF §3), requiere validación; **PEND** = pendiente. Todo es editable en *Usuarios y permisos* y *Configurar alertas* y queda auditado.

## Roles

| Código | Rol | Área | Fuente | Observación |
|---|---|---|---|---|
| GERENCIA_GENERAL | Gerencia General | Gerencia | Informe Funcional §3, §14, §15 | Acceso a todas las áreas; 'acceso completo' pendiente de precisar (IF §15). |
| GERENCIA_OPERACIONES | Gerencia de Operaciones | Gerencia | Informe Funcional §3, §15 | Vista y autorizaciones de su ámbito. |
| SISTEMAS | Sistemas | Sistemas | Informe Funcional §3, §15, §16 | Se indicó acceso completo; administración y configuración. |
| GERENTE_COMERCIAL | Gerente Comercial | Comercial | Informe Funcional §15 |  |
| JEFE_VENTAS | Jefe de Ventas | Comercial | Informe Funcional §5, §15 |  |
| COORD_VENTAS | Coordinador de Ventas | Comercial | Informe Funcional §5, §15 |  |
| ASIST_VENTAS | Asistente de Ventas | Comercial | Informe Funcional §5, §15 | Modifica OV solo con autorización. |
| EJECUTIVO_VENTAS | Ejecutivo de Ventas (vendedor por canal) | Comercial | Informe Funcional §5, §15 | Vendedor responsable de la OV. |
| COORD_ALMACEN | Coordinación de Almacén | Almacén | Informe Funcional §6, §15 |  |
| SUPERV_ALMACEN | Supervisión de Almacén (por almacén) | Almacén | Informe Funcional §15 |  |
| LIDER_ALMACEN | Líder Operativo de Almacén | Almacén | Informe Funcional §15; diagrama AS-IS L5 |  |
| AUX_ALMACEN | Auxiliar / Asistente de Almacén | Almacén | Informe Funcional §6.2, §15 |  |
| MONTACARGUISTA | Montacarguista | Almacén | Informe Funcional §8.3, §15 |  |
| COORD_DISTRIBUCION | Coordinador de Distribución | Distribución | Informe Funcional §12, §15 |  |
| ASIST_DISTRIBUCION | Asistente de Distribución | Distribución | Informe Funcional §15 |  |
| CONDUCTOR | Conductor | Distribución | Informe Funcional §15 |  |
| AUX_DESPACHO | Auxiliar de Despacho | Distribución | Informe Funcional §12.3, §15 |  |
| JEFE_LOGISTICA | Jefatura de Logística | Logística | Informe Funcional §6.2, §13, §15 |  |
| COORD_LOGISTICA | Coordinación de Logística | Logística | Informe Funcional §15 |  |
| JEFE_PRODUCCION | Jefatura de Producción | Producción | Informe Funcional §8, §15 |  |
| COORD_PRODUCCION | Coordinación de Producción (por validar) | Producción | Informe Funcional §15 | La existencia del rol está 'por validar' (IF §15). |
| ASIST_PRODUCCION | Asistente de Producción | Producción | Informe Funcional §15 |  |
| JEFE_CALIDAD | Jefatura de Calidad | Calidad | Informe Funcional §9, §15 |  |
| SUPERV_CALIDAD | Supervisor de Calidad | Calidad | Informe Funcional §9.3, §15 |  |
| ASIST_CALIDAD | Asistente de Calidad | Calidad | Informe Funcional §9.3, §15 |  |
| COMPRAS | Coordinador de Compras | Compras | Informe Funcional §10, §15 |  |
| IMPORTACIONES | Importaciones | Importaciones | Informe Funcional §11, §15 |  |
| SEGURIDAD | Seguridad | Seguridad | Informe Funcional §12.2, §13, §15 |  |

## Permisos (separación consulta / edición / aprobación / administración, IF §19)

| Permiso | Descripción | Módulo | Tipo |
|---|---|---|---|
| dashboard.ver | Ver tablero de indicadores | Gerencial | consulta |
| ov.ver | Consultar órdenes de venta | Comercial | consulta |
| ov.crear | Registrar OV | Comercial | edicion |
| ov.modificar | Modificar OV directamente | Comercial | edicion |
| ov.solicitar_modificacion | Solicitar modificación de OV (requiere autorización) | Comercial | edicion |
| ov.autorizar_modificacion | Autorizar modificación de OV solicitada por Asistente | Comercial | aprobacion |
| ov.cancelar | Cancelar OV | Comercial | aprobacion |
| ov.renegociar | Registrar renegociación de fecha / cambio de producto | Comercial | edicion |
| ov.aprobar_parcial | Decidir despacho parcial | Logística | aprobacion |
| ov.decidir_alternativa | Decidir uso de stock de otros almacenes | Logística | aprobacion |
| ov.importar | Importar OV desde exportación SAP | Comercial | edicion |
| stock.ver | Consultar stock y reservas | Almacén | consulta |
| stock.cargar | Cargar archivos de stock/movimientos (validación previa) | Almacén | edicion |
| stock.autorizar_carga | Autorizar/confirmar carga de stock | Almacén | aprobacion |
| stock.cambiar_estado | Cambiar estado de stock (dañado, no utilizable, etc.) | Almacén | edicion |
| stock.conteo | Registrar conteos físicos | Almacén | edicion |
| preparacion.registrar | Registrar preparación/picking | Almacén | edicion |
| traslados.ver | Consultar traslados | Logística | consulta |
| traslado.solicitar | Solicitar traslado | Logística | edicion |
| traslado.autorizar | Autorizar traslado | Logística | aprobacion |
| traslado.salida | Registrar salida de traslado | Almacén | edicion |
| traslado.recibir | Confirmar recepción de traslado en destino | Almacén | edicion |
| reempaque.ver | Consultar reempaques | Calidad | consulta |
| reempaque.solicitar | Solicitar reempaque | Almacén | edicion |
| reempaque.evaluar | Evaluar y aprobar/desaprobar reempaque | Calidad | aprobacion |
| reempaque.ejecutar | Ejecutar y registrar reempaque | Producción | edicion |
| produccion.ver | Consultar producción | Producción | consulta |
| produccion.bom_cargar | Cargar lista de materiales (Excel) | Producción | edicion |
| produccion.solicitud | Crear/revisar/enviar solicitud preliminar de producción | Almacén | edicion |
| produccion.validar | Validar solicitud (lista, disponibilidad real, capacidad, plazo) | Producción | aprobacion |
| produccion.programar | Programar producción | Producción | edicion |
| produccion.registrar | Registrar inicio/fin de producción | Producción | edicion |
| produccion.liquidar | Registrar/cargar liquidación | Producción | edicion |
| produccion.recibir_pt | Validar recepción de PT y diferencias | Almacén | edicion |
| calidad.ver | Consultar registros de Calidad | Calidad | consulta |
| calidad.registrar | Registrar datos de Calidad (formatos) | Calidad | edicion |
| calidad.liberar | Liberar producto / cambiar estado por Calidad | Calidad | aprobacion |
| calidad.certificado_revisar | Revisar, corregir y aprobar certificados | Calidad | aprobacion |
| calidad.evaluar_muestra | Evaluar muestras de compras/importaciones | Calidad | aprobacion |
| compras.ver | Consultar compras | Compras | consulta |
| compras.solicitar | Originar solicitud de compra | Almacén | edicion |
| compras.gestionar | Cotizar, generar orden y actualizar fechas | Compras | edicion |
| compras.aprobar_mayor_volumen | Aprobar compra de mayor volumen | Gerencia | aprobacion |
| compras.recibir | Registrar recepción de compra | Almacén | edicion |
| compras.autorizar_bajo_observacion | Autorizar recepción bajo observaciones | Gerencia | aprobacion |
| importaciones.ver | Consultar importaciones | Importaciones | consulta |
| importaciones.gestionar | Registrar importaciones, fases y fechas | Importaciones | edicion |
| importaciones.recibir | Registrar recepción de importación | Almacén | edicion |
| distribucion.ver | Consultar distribución | Distribución | consulta |
| distribucion.programar | Generar/ajustar programación de rutas | Distribución | edicion |
| distribucion.flota | Mantener flota y conductores | Distribución | edicion |
| distribucion.confirmar_salida | Confirmar salida de despacho | Distribución | aprobacion |
| distribucion.seguridad | Control de Seguridad: ingreso, inspección y carga vs guía | Seguridad | edicion |
| distribucion.entrega | Registrar avance y entrega con evidencia | Distribución | edicion |
| distribucion.incidencia | Registrar incidencias | Distribución | edicion |
| alertas.ver | Ver alertas propias/del rol | Alertas | consulta |
| alertas.gestionar | Asignar, atender, comentar y cerrar alertas | Alertas | edicion |
| alertas.ver_todas | Ver alertas de todas las áreas | Alertas | consulta |
| alertas.configurar | Configurar destinatarios/canales/urgencia de alertas | Alertas | administracion |
| config.ver | Consultar configuración | Configuración | consulta |
| config.editar | Editar configuración y catálogos | Configuración | administracion |
| usuarios.administrar | Administrar usuarios y matriz de permisos | Configuración | administracion |
| auditoria.ver | Consultar bitácora de auditoría | Configuración | consulta |
| export.datos | Exportar registros | General | consulta |

## Permisos por rol

### Gerencia General

Todos los permisos (64) — D: Informe Funcional §15 'acceso a todas las áreas' / 'acceso completo'. Las aprobaciones no se omiten; quedan auditadas (decisión pendiente IF §15).

### Sistemas

Todos los permisos (64) — D: Informe Funcional §15 'Sistemas: acceso completo'; §16 administra configuración. Las aprobaciones no se omiten; quedan auditadas (decisión pendiente IF §15).

### Gerencia de Operaciones

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.aprobar_mayor_volumen` – Aprobar compra de mayor volumen (**P**; Informe Funcional §7 – participación de GO requiere validación)
- `compras.autorizar_bajo_observacion` – Autorizar recepción bajo observaciones (**D**; Informe Funcional §10.8)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `config.ver` – Consultar configuración (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.aprobar_parcial` – Decidir despacho parcial (**D**; Informe Funcional §4.5, §5 (participa en renegociación y despacho parcial))
- `ov.renegociar` – Registrar renegociación de fecha / cambio de producto (**D**; Informe Funcional §4.5, §5 (participa en renegociación y despacho parcial))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Gerente Comercial

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Jefe de Ventas

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.aprobar_parcial` – Decidir despacho parcial (**D**; Informe Funcional §4.5, §5, §6.3 (Comercial participa))
- `ov.autorizar_modificacion` – Autorizar modificación de OV solicitada por Asistente (**D**; Informe Funcional §5)
- `ov.cancelar` – Cancelar OV (**D**; Informe Funcional §5)
- `ov.crear` – Registrar OV (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.importar` – Importar OV desde exportación SAP (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.modificar` – Modificar OV directamente (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.renegociar` – Registrar renegociación de fecha / cambio de producto (**D**; Informe Funcional §4.5, §5, §6.3 (Comercial participa))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Coordinador de Ventas

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.aprobar_parcial` – Decidir despacho parcial (**D**; Informe Funcional §4.5, §5, §6.3 (Comercial participa))
- `ov.autorizar_modificacion` – Autorizar modificación de OV solicitada por Asistente (**D**; Informe Funcional §5)
- `ov.cancelar` – Cancelar OV (**D**; Informe Funcional §5)
- `ov.crear` – Registrar OV (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.importar` – Importar OV desde exportación SAP (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.modificar` – Modificar OV directamente (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.renegociar` – Registrar renegociación de fecha / cambio de producto (**D**; Informe Funcional §4.5, §5, §6.3 (Comercial participa))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Asistente de Ventas

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.crear` – Registrar OV (**D**; Diagrama AS-IS L5 (Asistente comercial ingresa la OV))
- `ov.solicitar_modificacion` – Solicitar modificación de OV (requiere autorización) (**D**; Informe Funcional §5 (modifica con autorización))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Ejecutivo de Ventas (vendedor por canal)

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.autorizar_modificacion` – Autorizar modificación de OV solicitada por Asistente (**D**; Informe Funcional §5 (vendedor responsable autoriza; solo sus OV))
- `ov.crear` – Registrar OV (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.modificar` – Modificar OV directamente (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.renegociar` – Registrar renegociación de fecha / cambio de producto (**D**; Informe Funcional §5 (Comercial puede renegociar))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Coordinación de Almacén

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.recibir` – Registrar recepción de compra (**D**; Informe Funcional §8.3, §10.6-10.7)
- `compras.solicitar` – Originar solicitud de compra (**D**; Informe Funcional §7, §10.1)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.recibir` – Registrar recepción de importación (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `preparacion.registrar` – Registrar preparación/picking (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.recibir_pt` – Validar recepción de PT y diferencias (**D**; Informe Funcional §8.3, §10.6-10.7)
- `produccion.solicitud` – Crear/revisar/enviar solicitud preliminar de producción (**D**; Informe Funcional §8.2 (Almacén revisa y envía))
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.solicitar` – Solicitar reempaque (**D**; Informe Funcional §9.1)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.autorizar_carga` – Autorizar/confirmar carga de stock (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.cambiar_estado` – Cambiar estado de stock (dañado, no utilizable, etc.) (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.cargar` – Cargar archivos de stock/movimientos (validación previa) (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.conteo` – Registrar conteos físicos (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.recibir` – Confirmar recepción de traslado en destino (**D**; Informe Funcional §6.2, §13)
- `traslado.salida` – Registrar salida de traslado (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Supervisión de Almacén (por almacén)

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.recibir` – Registrar recepción de compra (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.solicitar` – Originar solicitud de compra (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.recibir` – Registrar recepción de importación (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `preparacion.registrar` – Registrar preparación/picking (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.recibir_pt` – Validar recepción de PT y diferencias (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.solicitud` – Crear/revisar/enviar solicitud preliminar de producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.solicitar` – Solicitar reempaque (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.cambiar_estado` – Cambiar estado de stock (dañado, no utilizable, etc.) (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.cargar` – Cargar archivos de stock/movimientos (validación previa) (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.conteo` – Registrar conteos físicos (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.recibir` – Confirmar recepción de traslado en destino (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.salida` – Registrar salida de traslado (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Líder Operativo de Almacén

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `preparacion.registrar` – Registrar preparación/picking (**D**; Diagrama AS-IS L5 (Líder operativo designa y verifica picking))
- `stock.conteo` – Registrar conteos físicos (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Auxiliar / Asistente de Almacén

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `preparacion.registrar` – Registrar preparación/picking (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.conteo` – Registrar conteos físicos (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.recibir` – Confirmar recepción de traslado en destino (**D**; Informe Funcional §6.2 (Coordinador de Almacén o asistente confirma recepción))
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Montacarguista

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §8.3 (recibe alerta de liquidación) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §8.3 (recibe alerta de liquidación) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §8.3 (recibe alerta de liquidación) – propuesto)

### Coordinador de Distribución

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.confirmar_salida` – Confirmar salida de despacho (**D**; Informe Funcional §4.11, §12.2)
- `distribucion.entrega` – Registrar avance y entrega con evidencia (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.flota` – Mantener flota y conductores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.incidencia` – Registrar incidencias (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.programar` – Generar/ajustar programación de rutas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Asistente de Distribución

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.entrega` – Registrar avance y entrega con evidencia (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.flota` – Mantener flota y conductores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.incidencia` – Registrar incidencias (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.programar` – Generar/ajustar programación de rutas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Conductor

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.entrega` – Registrar avance y entrega con evidencia (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.incidencia` – Registrar incidencias (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Auxiliar de Despacho

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.entrega` – Registrar avance y entrega con evidencia (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.incidencia` – Registrar incidencias (**D**; Informe Funcional §12.3)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Jefatura de Logística

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.aprobar_parcial` – Decidir despacho parcial (**D**; Informe Funcional §6.3)
- `ov.decidir_alternativa` – Decidir uso de stock de otros almacenes (**D**; Informe Funcional §4.5, §6.2, §13)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.autorizar` – Autorizar traslado (**D**; Informe Funcional §4.5, §6.2, §13)
- `traslado.solicitar` – Solicitar traslado (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Coordinación de Logística

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.decidir_alternativa` – Decidir uso de stock de otros almacenes (**D**; Informe Funcional §4.5, §6.2 (Logística decide))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.solicitar` – Solicitar traslado (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Jefatura de Producción

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.bom_cargar` – Cargar lista de materiales (Excel) (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.liquidar` – Registrar/cargar liquidación (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.programar` – Programar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.registrar` – Registrar inicio/fin de producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.validar` – Validar solicitud (lista, disponibilidad real, capacidad, plazo) (**D**; Informe Funcional §8.2)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ejecutar` – Ejecutar y registrar reempaque (**D**; Informe Funcional §9.1)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Coordinación de Producción (por validar)

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §15 – rol por validar)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §15 – rol por validar)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §15 – rol por validar)
- `produccion.liquidar` – Registrar/cargar liquidación (**P**; Informe Funcional §15 – rol por validar)
- `produccion.programar` – Programar producción (**P**; Informe Funcional §15 – rol por validar)
- `produccion.registrar` – Registrar inicio/fin de producción (**P**; Informe Funcional §15 – rol por validar)
- `produccion.validar` – Validar solicitud (lista, disponibilidad real, capacidad, plazo) (**P**; Informe Funcional §15 – rol por validar)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §15 – rol por validar)
- `reempaque.ejecutar` – Ejecutar y registrar reempaque (**P**; Informe Funcional §15 – rol por validar)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §15 – rol por validar)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §15 – rol por validar)

### Asistente de Producción

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.liquidar` – Registrar/cargar liquidación (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.registrar` – Registrar inicio/fin de producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ejecutar` – Ejecutar y registrar reempaque (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Jefatura de Calidad

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.certificado_revisar` – Revisar, corregir y aprobar certificados (**D**; Informe Funcional §9.3, §9.4)
- `calidad.evaluar_muestra` – Evaluar muestras de compras/importaciones (**D**; Informe Funcional §9.1, §9.3, §10.3)
- `calidad.liberar` – Liberar producto / cambiar estado por Calidad (**D**; Informe Funcional §9.1, §9.3, §10.3)
- `calidad.registrar` – Registrar datos de Calidad (formatos) (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.evaluar` – Evaluar y aprobar/desaprobar reempaque (**D**; Informe Funcional §9.1, §9.3, §10.3)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Supervisor de Calidad

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.certificado_revisar` – Revisar, corregir y aprobar certificados (**D**; Informe Funcional §9.3, §9.4)
- `calidad.evaluar_muestra` – Evaluar muestras de compras/importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.liberar` – Liberar producto / cambiar estado por Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.registrar` – Registrar datos de Calidad (formatos) (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.evaluar` – Evaluar y aprobar/desaprobar reempaque (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Asistente de Calidad

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.registrar` – Registrar datos de Calidad (formatos) (**D**; Informe Funcional §9.3 (registro de datos de proceso por el asistente))
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Coordinador de Compras

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.gestionar` – Cotizar, generar orden y actualizar fechas (**D**; Informe Funcional §10)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Importaciones

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.gestionar` – Registrar importaciones, fases y fechas (**D**; Informe Funcional §11)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Seguridad

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.seguridad` – Control de Seguridad: ingreso, inspección y carga vs guía (**D**; Informe Funcional §12.2, §13)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

## Tipos de alerta

Canales: panel del módulo y correo (si hay SMTP). Ciclo: Nueva → Asignada → En atención → Cerrada (motivo y acción obligatorios). Gerencia General ve todo y elige qué recibe por correo; Gerencia de Operaciones ve las áreas de su ámbito (parámetro).

| Código | Alerta | Área / grupo | Prioridad | Destinatarios (roles) | Origen dest. | Correo | Condición | Fuente |
|---|---|---|---|---|---|---|---|---|
| OV_FALTANTE | Faltante de stock en OV | Almacén / Faltantes y cobertura | ALTA | COORD_ALMACEN, JEFE_LOGISTICA, COORD_LOGISTICA, GERENCIA_OPERACIONES | DEFINIDO | sí | Al evaluar una OV nueva o modificada con cobertura < 100 %. | Informe Funcional §6.3 |
| OV_DECISION_PARCIAL | Decisión de despacho parcial requerida | Logística / Faltantes y cobertura | ALTA | JEFE_LOGISTICA, GERENCIA_OPERACIONES, JEFE_VENTAS, COORD_VENTAS | DEFINIDO | sí | OV con faltante y stock reservado parcial. | Informe Funcional §6.3 |
| OV_PARCIAL_APROBADO | Despacho parcial aprobado | Distribución / Rutas | ALTA | COORD_DISTRIBUCION, ASIST_DISTRIBUCION | DEFINIDO | sí | Se aprueba entrega parcial; se genera propuesta de ruta. | Informe Funcional §6.3 |
| OV_CAMBIO | Cambio de OV con reserva existente | Comercial / Cambios de OV | MEDIA | JEFE_LOGISTICA, COORD_LOGISTICA, COORD_ALMACEN, GERENCIA_OPERACIONES | DEFINIDO | sí | Modificación de una OV que ya tenía reservas. | Informe Funcional §6.3, §14 |
| OV_MODIF_SOLICITUD | Solicitud de modificación de OV (Asistente) | Comercial / Cambios de OV | MEDIA | JEFE_VENTAS, COORD_VENTAS | DEFINIDO | sí | El Asistente de Ventas solicita modificar una OV; autorizan Coord./Jefe de Ventas o vendedor responsable. | Informe Funcional §5 |
| OV_CANCELADA | OV cancelada (reserva y ruta liberadas) | Comercial / Cambios de OV | MEDIA | COORD_ALMACEN, COORD_DISTRIBUCION, ASIST_DISTRIBUCION, JEFE_LOGISTICA | PROPUESTO | sí | Cancelación por Coordinador o Jefe de Ventas. | Informe Funcional §5, §14 |
| OV_ESTADO | Cambio de estado de pedido | Comercial / Estados de pedidos | BAJA | COORD_VENTAS | PROPUESTO | no | Cambio de estado relevante de la OV (preparada, despachada, entregada). | Informe Funcional §14 |
| OV_80_PREPARACION | Pedido al 80 % de preparación | Almacén / Estados de pedidos | MEDIA | COORD_DISTRIBUCION, ASIST_DISTRIBUCION, COORD_VENTAS | PROPUESTO | no | Avance de preparación ≥ umbral configurado (80 %). | Informe Funcional §14 (condición definida; destinatarios propuestos) |
| OV_PREPARADA | Pedido preparado y listo para despacho | Almacén / Estados de pedidos | MEDIA | COORD_DISTRIBUCION, ASIST_DISTRIBUCION, COORD_VENTAS | PROPUESTO | no | Preparación al 100 %. | Diagrama AS-IS L5 ('Aviso a Distribución: pedido completo') |
| OV_RETRASO | OV no despachada en la fecha comprometida | Distribución / Retrasos | ALTA | GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_VENTAS | PROPUESTO | sí | Fecha comprometida vencida sin salida registrada. | Informe Funcional §14 ('retrasos') |
| RESERVA_AFECTADA | Reserva afectada por actualización de stock | Almacén / Faltantes y cobertura | ALTA | COORD_ALMACEN, JEFE_LOGISTICA | PROPUESTO | sí | La nueva carga reduce un lote por debajo de lo reservado. | Informe Funcional §14 ('reservas') |
| STOCK_CARGA_DIFERENCIAS | Diferencias/errores en carga de stock | Sistemas / Diferencias de inventario | MEDIA | SISTEMAS, COORD_ALMACEN | DEFINIDO | sí | Carga confirmada con filas corregidas/excluidas o diferencias. | Informe Funcional §6.4 (alertar a Sistemas) |
| INVENTARIO_DIFERENCIA | Diferencia de inventario en conteo físico | Almacén / Diferencias de inventario | MEDIA | SISTEMAS, COORD_ALMACEN, GERENCIA_OPERACIONES | PROPUESTO | sí | Conteo cerrado con faltantes o sobrantes. | Informe Funcional §6.4, §14 |
| STOCK_PENDIENTE_REVISION | Carga recibida pendiente de revisión de Calidad | Calidad / Calidad | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD | PROPUESTO | no | Nuevo lote en estado Pendiente de revisión. | Informe Funcional §6.1, §9.4 |
| STOCK_NO_UTILIZABLE | Producto no utilizable / requiere fumigación | Calidad / Fumigación y no utilizables | ALTA | JEFE_CALIDAD, SUPERV_CALIDAD, COORD_ALMACEN, JEFE_LOGISTICA | PROPUESTO | sí | Lote pasa a No utilizable o supera tiempo máximo de almacenamiento configurado. | Informe Funcional §6.1, §14 |
| FUMIGACION | Fumigación iniciada/finalizada | Calidad / Fumigación y no utilizables | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD, COORD_ALMACEN | PROPUESTO | no | Registro de inicio/fin de fumigación. | Informe Funcional §14; REG-BPM-CAL-005 |
| VENCIMIENTO_PROXIMO | Lote próximo a vencer | Almacén / Faltantes y cobertura | MEDIA | COORD_ALMACEN, COORD_VENTAS | PENDIENTE | no | Solo si se configura 'dias_vencimiento_proximo'. | Informe Funcional §21 (caso 'vencimiento'); umbral no definido |
| TRASLADO_SOLICITADO | Traslado pendiente de autorización | Logística / Traslados | MEDIA | JEFE_LOGISTICA | DEFINIDO | sí | Se solicita traslado desde almacén alternativo. | Informe Funcional §6.2, §13 |
| TRASLADO_AUTORIZADO | Traslado autorizado | Almacén / Traslados | MEDIA | COORD_ALMACEN, AUX_ALMACEN | PROPUESTO | no | Logística autoriza el traslado. | Informe Funcional §13 |
| TRASLADO_DIFERENCIA | Diferencia en recepción de traslado | Logística / Traslados | ALTA | JEFE_LOGISTICA, COORD_ALMACEN, GERENCIA_OPERACIONES | PROPUESTO | sí | Cantidad recibida distinta a la enviada. | Informe Funcional §13 |
| PRODUCCION_SOLICITUD | Solicitud de producción enviada | Producción / Solicitudes | ALTA | JEFE_PRODUCCION, COORD_PRODUCCION | DEFINIDO | sí | Almacén envía solicitud preliminar. | Informe Funcional §8.2, §14 |
| PRODUCCION_RESPUESTA | Solicitud de producción validada/rechazada | Producción / Solicitudes | MEDIA | COORD_ALMACEN, COORD_VENTAS | PROPUESTO | sí | Producción valida o rechaza. | Informe Funcional §8.2 |
| LIQUIDACION_MONTACARGUISTA | Liquidación registrada: mover producto terminado | Almacén / Solicitudes | ALTA | MONTACARGUISTA, COORD_ALMACEN | DEFINIDO | no | Al registrar una liquidación. | Informe Funcional §8.3 |
| LIQUIDACION_DIFERENCIA | Diferencia entre liquidación y recepción de PT | Almacén / Diferencias de inventario | ALTA | JEFE_PRODUCCION, COORD_PRODUCCION, COORD_ALMACEN | PROPUESTO | sí | Recepción física ≠ cantidad completada. | Informe Funcional §8.3; hoja 'Cruce' de Recep. pt.xlsx |
| MERMA_FUERA_PARAMETRO | Merma fuera de parámetros | Producción / Merma | ALTA | JEFE_PRODUCCION, COORD_PRODUCCION, GERENCIA_OPERACIONES | PENDIENTE | sí | Solo si se configura 'umbral_merma_pct'. | Informe Funcional §14 ('cuando se defina el umbral') |
| REEMPAQUE_SOLICITUD | Solicitud de reempaque para evaluación | Calidad / Solicitudes | ALTA | JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Almacén inicia solicitud. | Informe Funcional §9.1 |
| REEMPAQUE_APROBADO | Reempaque aprobado: ejecutar | Producción / Solicitudes | ALTA | COORD_ALMACEN, JEFE_PRODUCCION, COORD_PRODUCCION | DEFINIDO | sí | Calidad aprueba. | Informe Funcional §9.1 (notifica a Almacén y envía a Producción) |
| REEMPAQUE_DESAPROBADO | Reempaque desaprobado | Almacén / Solicitudes | MEDIA | COORD_ALMACEN | PROPUESTO | sí | Calidad desaprueba. | Informe Funcional §9.1 |
| COMPRA_SOLICITUD | Solicitud de compra originada en Almacén | Compras / Solicitudes | MEDIA | COMPRAS | DEFINIDO | sí | Almacén envía solicitud. | Informe Funcional §10.1, §14 |
| COMPRA_MUESTRA | Muestra de compra para evaluación | Calidad / Solicitudes | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Compras lleva muestra a Calidad. | Informe Funcional §10.2-10.3 |
| COMPRA_APROBACION_GERENCIA | Compra de mayor volumen requiere aprobación | Gerencia / Solicitudes | ALTA | GERENCIA_OPERACIONES | PENDIENTE | sí | Cantidad ≥ umbral configurado. | Informe Funcional §7 (umbral y participación por validar) |
| COMPRA_RECEPCION_PROGRAMAR | Programar recepción de compra | Almacén / Cambios de fechas | MEDIA | COORD_ALMACEN | DEFINIDO | sí | Compras registra fecha prevista de recepción. | Informe Funcional §10.6 |
| COMPRA_FECHA_CAMBIO | Cambio de fecha de compra nacional | Compras / Cambios de fechas | MEDIA | COORD_ALMACEN, GERENCIA_OPERACIONES | DEFINIDO | sí | Compras modifica la fecha prevista. | Informe Funcional §10 (cambios generan alerta a Almacén y GO) |
| COMPRA_DIFERENCIA | Diferencias en recepción de compra | Compras / Diferencias de inventario | ALTA | COMPRAS, JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Almacén/Calidad detectan diferencias. | Informe Funcional §10.7 |
| REPOSICION_SUGERIDA | Reposición sugerida | Almacén / Solicitudes | MEDIA | COORD_ALMACEN, COMPRAS | PROPUESTO | sí | Análisis de reposición detecta necesidad. | Informe Funcional §7 (alerta, cantidad sugerida, fecha estimada) |
| IMPORT_LLEGADA | Llegada estimada de importación | Importaciones / Cambios de fechas | MEDIA | COORD_ALMACEN, JEFE_LOGISTICA, COORD_LOGISTICA | DEFINIDO | sí | Registro o actualización de la llegada estimada. | Informe Funcional §11 |
| IMPORT_MODIFICACION | Modificación de fechas de importación | Importaciones / Cambios de fechas | ALTA | GERENCIA_OPERACIONES, COORD_ALMACEN, JEFE_LOGISTICA, COORD_LOGISTICA | DEFINIDO | sí | Cambio de fecha de llegada o fase. | Informe Funcional §11 |
| IMPORT_FASE_VENCIDA | Fase de importación fuera de fecha | Importaciones / Retrasos | ALTA | IMPORTACIONES | DEFINIDO | sí | Fecha prevista de fase vencida sin fecha real. | Informe Funcional §11 |
| IMPORT_RECORDATORIO | Recordatorio de fase de importación | Importaciones / Cambios de fechas | BAJA | IMPORTACIONES | DEFINIDO | no | Faltan N días para la fecha prevista de una fase. | Informe Funcional §11 (recordatorios configurables) |
| IMPORT_DIFERENCIA | Diferencias en recepción de importación | Importaciones / Diferencias de inventario | ALTA | IMPORTACIONES, JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Recepción con diferencias. | Informe Funcional §11 |
| DIST_PROGRAMACION | Programación de distribución generada | Distribución / Rutas | MEDIA | COORD_DISTRIBUCION, ASIST_DISTRIBUCION, JEFE_LOGISTICA, COORD_LOGISTICA, GERENCIA_OPERACIONES, JEFE_VENTAS, COORD_VENTAS | DEFINIDO | sí | Se genera/confirma la programación de rutas. | Informe Funcional §12.1 |
| DIST_AVANCE_RUTA | Avance de ruta | Distribución / Rutas | BAJA | JEFE_VENTAS, COORD_VENTAS, JEFE_LOGISTICA, COORD_LOGISTICA, COORD_DISTRIBUCION | DEFINIDO | no | Salida, llegada, entrega. | Informe Funcional §12.3 |
| GUIA_DISCREPANCIA | Discrepancia entre carga y guía | Seguridad / Guías | ALTA | COORD_DISTRIBUCION, SEGURIDAD, JEFE_LOGISTICA | PROPUESTO | sí | Cantidad cargada ≠ guía o presentación no coincide. | Informe Funcional §12.2, §14 |
| INC_RECHAZO_CALIDAD | Rechazo por calidad | Distribución / Incidencias | ALTA | GERENCIA_GENERAL, GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_LOGISTICA, COORD_ALMACEN, JEFE_VENTAS, COORD_VENTAS | DEFINIDO | sí | Incidencia tipo rechazo por calidad. | Informe Funcional §12.3 (tabla de destinatarios) |
| INC_GENERAL | Incidencia de distribución (llegada tarde u otra condición) | Distribución / Incidencias | ALTA | GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_LOGISTICA, COORD_ALMACEN, JEFE_VENTAS, COORD_VENTAS | DEFINIDO | sí | Retraso, ausente, parcial, devolución, vehículo esperando, etc. | Informe Funcional §12.3 (tabla de destinatarios) |
| CERTIFICADO_REVISION | Certificado autogenerado pendiente de revisión | Calidad / Certificados | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | no | Se genera un certificado para lote de pedido listo para despacho. | Informe Funcional §9.3, §9.4 |
| CALIDAD_NO_CONFORME | Producto/registro no conforme | Calidad / Calidad | ALTA | JEFE_CALIDAD, SUPERV_CALIDAD, GERENCIA_OPERACIONES | PROPUESTO | sí | Registro de Calidad con resultado No conforme. | REG-BPM-CAL-013, REG-HACCP-CAL-002 |

## Tipos de incidencia (IF §12.3)

- RETRASO: Retraso
- LLEGADA_TARDE: Llegada tarde
- CLIENTE_AUSENTE: Cliente ausente
- RECHAZO_CALIDAD: Rechazo por calidad
- RECHAZO_OTRO: Rechazo (otro motivo)
- ENTREGA_PARCIAL: Entrega parcial
- DEVOLUCION: Devolución
- CANCELACION: Cancelación
- CAMBIO_RUTA: Cambio de ruta
- VEHICULO_ESPERANDO: Vehículo esperando
- CLIENTE_NO_RETIRA: Cliente que no retira pedido
- CONDUCTOR_NO_DISPONIBLE: Falta de disponibilidad del conductor

## Parámetros configurables (IF §16)

| Parámetro | Valor inicial | Estado | Descripción | Fuente |
|---|---|---|---|---|
| margen_reposicion_dias | `None` | PENDIENTE | Margen adicional (días naturales) por posibles atrasos; aplicable por producto/material (campo en catálogo) o global. | Informe Funcional §7, §16, §20 |
| periodo_analisis_dias | `15` | AS-IS | Período de análisis por defecto para consumo promedio (cada producto puede tener el suyo). | Macro VBA 'TraerLotesStock' (PROM_15D) en PCP 2026 - J.xlsm |
| factor_stock_seguridad | `0.3` | AS-IS | Stock de seguridad como % del consumo mensual promedio observado en el Excel actual. Solo se aplica si 'usar_stock_seguridad' = sí. | Rotacion de inventario - Almacenes.xlsx, hoja Reporte ('30% stk seg') |
| usar_stock_seguridad | `False` | PENDIENTE | Aplicar el factor de stock de seguridad AS-IS en el análisis de reposición. | Informe Funcional §16 (stock mínimo configurable) |
| umbral_mayor_volumen | `None` | PENDIENTE | Cantidad a partir de la cual una compra se considera de mayor volumen. | Informe Funcional §7, §20 |
| mayor_volumen_requiere_go | `True` | PENDIENTE | Si la compra de mayor volumen requiere aprobación de Gerencia de Operaciones. | Informe Funcional §7, §20 |
| merma_pct_global | `None` | PENDIENTE | Porcentaje de merma por defecto (el catálogo de producto/material puede tener uno propio). | Informe Funcional §8.1, §16, §20 |
| prefijos_no_material_bom | `['RE-']` | PROPUESTO | Prefijos de componentes BOM que no son materiales inventariables (mano de obra, costo CIF). No se verifican contra stock. | LISTA DE MATERIALES 2026.xlsx (RE-xxx = 'MANO DE OBRA' / 'COSTO CIF') |
| umbral_merma_pct | `None` | PENDIENTE | Merma real (%) a partir de la cual se alerta 'merma fuera de parámetros'. | Informe Funcional §14 |
| cortes_preparacion | `[]` | PENDIENTE | Horarios de corte (HH:MM) que organizan la preparación. | Informe Funcional §4.9, §16 |
| tiempos_preparacion | `{'PEQUENO': '20-30 min', 'MEDIANO': '1 h - 1 h 30', 'GRANDE': '4 h (requiere 2 días de anticipación)'}` | AS-IS | Tiempos de preparación iniciales por tamaño de pedido (provisionales; medir y ajustar). | Diagrama AS-IS L5 (Revisar el stock físico vs. lo solicitado); IF §20 |
| umbrales_tamano_pedido_kg | `None` | PENDIENTE | Límites en kg para clasificar pedido pequeño/mediano/grande. | No definido en la documentación |
| umbral_alerta_preparacion_pct | `80` | DEFINIDO | Avance de preparación que dispara la alerta. | Informe Funcional §14 |
| orden_prioridad | `['fecha_compromiso', 'completitud', 'urgencia']` | PROPUESTO | Criterios de prioridad en el orden aplicado (los criterios están definidos; el orden de desempate es propuesto). | Informe Funcional §1, §5, §12.1 |
| uso_almacen_por_tipo | `{'PT': 'PT', 'GR': 'MP_INSUMOS', 'MP': 'MP_INSUMOS', 'INSUMO': 'MP_INSUMOS'}` | DEFINIDO | Almacén principal según tipo de artículo (TIPO de la tabla DATA: PT/GR/MP; insumos EN-/SU- = INSUMO). | Informe Funcional §6.2 (1560 = PT; 1524 = materia prima, granel e insumos) |
| politica_lotes | `FEFO` | PROPUESTO | Orden de consumo de lotes al reservar (FEFO = primero en vencer, primero en salir). | Informe Funcional §22 (respetar lote y vencimiento) |
| dias_vencimiento_proximo | `None` | PENDIENTE | Días previos al vencimiento para alertar. | No definido |
| estado_lote_nuevo_carga | `DISPONIBLE` | PENDIENTE | Estado asignado a lotes nuevos que aparecen en una carga SAP (DISPONIBLE o PENDIENTE_REVISION). | Informe Funcional §6.1 (Pendiente de revisión = carga recibida) vs. base inicial |
| carga_autorizada_verifica | `True` | PROPUESTO | Una carga revisada y autorizada marca los lotes como verificados (hasta que un conteo registre diferencias). | Informe Funcional §6.3-6.4 |
| reevaluar_tras_carga | `True` | PROPUESTO | Reevaluar automáticamente OV con faltantes (por prioridad) al ingresar stock. | Informe Funcional §1, §6.3 |
| bloquear_salida_con_discrepancia | `False` | PENDIENTE | Bloquear la confirmación de salida si hay discrepancias carga vs guía (si no, solo advierte y alerta). | Informe Funcional §12.2, §20 |
| zonas_distrito | `{}` | PENDIENTE | Agrupación de distritos en zonas de reparto (si está vacío se agrupa por distrito). | Informe Funcional §12.1 |
| capacidad_externo_kg | `[2000, 25000]` | AS-IS | Rango de capacidad de transportes externos (kg). | Imagen tabla de transportes (2 TN a 25 TN) |
| otif_definicion | `AMBAS` | PENDIENTE | SALIDA (pedido completo que salió a tiempo), ENTREGA (completo y a tiempo en destino) o AMBAS. | Informe Funcional §17, §20 |
| ambito_gerencia_operaciones | `['Almacén', 'Distribución', 'Logística', 'Producción', 'Calidad', 'Compras', 'Importaciones', 'Seguridad', 'Comercial', 'Gerencia']` | PENDIENTE | Áreas cuyas alertas ve Gerencia de Operaciones. | Informe Funcional §14 ('alertas de su ámbito') |
| acceso_completo_omite_aprobaciones | `False` | PENDIENTE | Si GG/Sistemas pueden omitir pasos de aprobación. Por defecto NO: pueden aprobar, pero ningún paso se salta y todo queda auditado. | Informe Funcional §15, §20 |
| empresa_razon_social | `CORPORACION PRODUCTIVA S.A.C.` | DEFINIDO | Procesado por (certificados). | Certificados N°CP2026-PT3756 / MP276 / CA0764 |
| empresa_ruc | `20517540341` | DEFINIDO | RUC del emisor (certificados). | Certificados N°CP2026-* |
| autorizacion_sanitaria | `Nº000502- MIDAGRI-SENASA-LIMA CALLAO` | PENDIENTE | Autorización sanitaria (los modelos muestran 'MIDAGRI' y 'MINAGRI'; confirmar). | Certificados N°CP2026-MP276 y PT3756 |
| series_certificado | `{'PT': 'PT', 'MQ': 'PT', 'AB': 'PT', 'MP': 'MP', 'GR': 'MP'}` | PENDIENTE | Serie de numeración por tipo de artículo (CP{año}-{serie}{correlativo}). La serie 'CA' existe en los modelos pero su criterio no está documentado. | Certificados N°CP2026-PT3756 / MP276 / CA0764 |
| muestreo_tiempo_min_por_lote | `30` | AS-IS | Tiempo orientativo de muestreo por lote en reempaque. | Informe Funcional §9.2 (orientativo) |

Valores de demostración aplicados por `seed_demo` (estado DEMO): `cortes_preparacion` = 09:00/13:00/16:00, `dias_vencimiento_proximo` = 30. Plantilla de fases de importación: DEMO.

## Almacenes iniciales

| SAP | Nombre | Uso | Prioridad | Fuente | Observación |
|---|---|---|---|---|---|
| ALM-001 | 1560 | PT | 1 | Informe Funcional §6.2; Rotacion de inventario (1560 = ALM-001) | Prioridad para stock actual de producto terminado. |
| EXT-002 | 1524 | MP_INSUMOS | 1 | Informe Funcional §6.2; Rotacion de inventario (1524 = EXT-002) | Materia prima, granel e insumos. |
| EXT-001 | 767 | ALTERNATIVO | 2 | Informe Funcional §6.2 (Ext-001 = almacén 767) | Alternativo: Logística decide; no hay traslado automático. |
| EXT-005 | Trujillo 1 | ALTERNATIVO | 3 | Informe Funcional §6.2 | En el Excel de rotación figura como 'Atsac 1' (nombre a confirmar). |
| EXT-010 | Trujillo 2 | ALTERNATIVO | 4 | Informe Funcional §6.2 | En el Excel de rotación figura como 'Atsac 2' (nombre a confirmar). |
| EXT-014 | Isabelita | ALTERNATIVO | 5 | Informe Funcional §6.2 |  |

## Plazos de reposición (IF §7, días naturales)

| Categoría | Mín | Máx | Meses | Descripción |
|---|---|---|---|---|
| Bobinas | 25 | 30 | todo el año | Bobinas |
| Bobinas | 30 | 40 | 11-12 | Bobinas en campaña de canastería (noviembre–diciembre) |
| GR y MP | 5 | 7 | todo el año | Granel y materia prima |
| Harinas | 7 | 10 | todo el año | Harinas |
| Film | 2 | 5 | todo el año | Film |
| Sacos sin estampado | 1 | 2 | todo el año | Sacos sin estampado |
| Sacos con estampado | 5 | 7 | todo el año | Sacos con estampado |
| Ribbons | 2 | 5 | todo el año | Ribbons |
| Etiquetas adhesivas | 2 | 5 | todo el año | Etiquetas adhesivas |