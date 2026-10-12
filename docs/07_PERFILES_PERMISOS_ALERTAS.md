# Perfiles, permisos y alertas (generado desde `app/catalogs.py`)

Origen: **D** = definido expresamente en la documentación; **P** = propuesto (derivado del alcance por área, IF §3), requiere validación; **PEND** = pendiente. Todo es editable en *Usuarios y permisos* y *Configurar alertas* y queda auditado.

## Roles

| Código | Rol | Área | Fuente | Observación |
|---|---|---|---|---|
| GERENCIA_GENERAL | Gerencia General | Gerencia | Informe Funcional §3, §14, §15 | Acceso completo; puede aprobar en nombre de otros roles (Q4). |
| GERENCIA_OPERACIONES | Gerencia de Operaciones | Gerencia | Informe Funcional §3, §15 | Vista y autorizaciones de su ámbito. |
| SISTEMAS | Sistemas | Sistemas | Informe Funcional §3, §15, §16 | Acceso completo sin aprobar en nombre de otros roles (Q4). |
| GERENTE_COMERCIAL | Gerente Comercial | Comercial | Informe Funcional §15 |  |
| JEFE_VENTAS | Jefe Comercial (Jefe de Ventas) | Comercial | Informe Funcional §5, §15; Decisión del usuario (13-oct-2026) | Único rol que modifica las listas de precios (Q11). |
| COORD_VENTAS | Coordinador de Ventas | Comercial | Informe Funcional §5, §15 |  |
| ASIST_VENTAS | Asistente de Ventas | Comercial | Informe Funcional §5, §15 | Modifica OV solo con autorización. |
| EJECUTIVO_VENTAS | Ejecutivo de Ventas (vendedor por canal) | Comercial | Informe Funcional §5, §15 | Vendedor responsable de la OV. |
| COORD_ALMACEN | Coordinación de Almacén 1560 (producto terminado) | Almacén | Informe Funcional §6, §15; decisión Q17 (12-oct-2026) | Maneja el almacén 1560 (ALM-001) y el tránsito de Producción ALM-003. |
| COORD_ALMACEN_MP | Coordinación de Almacén 1524 (materia prima, granel e insumos) | Almacén | TO-BE COPROD-ONE (L5) (dos coordinadores); decisión Q17 (12-oct-2026) | Maneja el almacén 1524 (EXT-002). |
| SUPERV_ALMACEN | Supervisión de Almacén (por almacén) | Almacén | Informe Funcional §15 |  |
| LIDER_ALMACEN | Líder Operativo de Almacén | Almacén | Informe Funcional §15; diagrama AS-IS L5 | Autoriza la salida del camión (Q16). |
| AUX_ALMACEN | Auxiliar / Asistente de Almacén | Almacén | Informe Funcional §6.2, §15 |  |
| MONTACARGUISTA | Montacarguista | Almacén | Informe Funcional §8.3, §15 |  |
| COORD_DISTRIBUCION | Coordinador de Distribución | Distribución | Informe Funcional §12, §15 |  |
| ASIST_DISTRIBUCION | Asistente de Distribución | Distribución | Informe Funcional §15 |  |
| CONDUCTOR | Conductor | Distribución | Informe Funcional §15 |  |
| AUX_DESPACHO | Auxiliar de Despacho | Distribución | Informe Funcional §12.3, §15 |  |
| JEFE_LOGISTICA | Jefatura de Logística | Logística | Informe Funcional §6.2, §13, §15 |  |
| COORD_LOGISTICA | Coordinación de Logística | Logística | Informe Funcional §15 |  |
| JEFE_PRODUCCION | Jefatura de Producción | Producción | Informe Funcional §8, §15 |  |
| ASIST_PRODUCCION | Asistente de Producción | Producción | Informe Funcional §15; Decisión del usuario (13-oct-2026, segunda parte) | Hoy son dos asistentes; no existe Coordinación de Producción. |
| JEFE_CALIDAD | Jefatura de Calidad | Calidad | Informe Funcional §9, §15 |  |
| SUPERV_CALIDAD | Supervisor de Calidad | Calidad | Informe Funcional §9.3, §15 |  |
| ASIST_CALIDAD | Asistente de Calidad | Calidad | Informe Funcional §9.3, §15 |  |
| COMPRAS | Coordinador de Compras | Compras | Informe Funcional §10, §15 |  |
| IMPORTACIONES | Coordinador de Importación | Importaciones | Informe Funcional §11, §15; Decisión del usuario (13-oct-2026) Q10 | Responsable de las fases de importación. |
| SEGURIDAD | Seguridad | Seguridad | Informe Funcional §12.2, §13, §15 |  |
| FACTURACION | Facturación | Facturación | TO-BE COPROD-ONE (carril Facturación) | Evalúa el pedido validado y carga la factura. |

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
| ov.aprobar_parcial | Aprobar despacho parcial | Logística | aprobacion |
| ov.decidir_alternativa | Decidir uso de stock de otros almacenes | Logística | aprobacion |
| ov.importar | Importar OV desde exportación SAP | Comercial | edicion |
| precios.ver | Consultar listas de precios | Comercial | consulta |
| precios.editar | Cargar y modificar listas de precios mínimos y su vigencia (solo Jefe Comercial) | Comercial | exclusivo |
| ov.aprobar_precio | Liberar una OV retenida por precio en el límite o bajo el mínimo | Comercial | exclusivo |
| clientes.canal | Asignar canal de precios y cargar condiciones de clientes (penalidades, lotes) | Comercial | exclusivo |
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
| reempaque.solicitar | Solicitar reempaque y aprobar/enviar la pre-solicitud a Calidad | Almacén | aprobacion |
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
| compras.aprobar_solicitud | Aprobar la solicitud de compra antes de pasar a Compras | Logística | aprobacion |
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
| distribucion.confirmar_salida | Autorizar y confirmar la salida del camión | Almacén | aprobacion |
| distribucion.visto_bueno_salida | Dar visto bueno a la salida del camión (Auxiliar de Despacho) | Distribución | aprobacion |
| distribucion.aprobar_salida_discrepancia | Aprobar la salida con discrepancia de guía mientras se resuelve | Logística | aprobacion |
| distribucion.seguridad | Control de Seguridad: ingreso, inspección, carga vs guía y revisión de documentos | Seguridad | edicion |
| distribucion.entrega | Registrar avance y entrega con evidencia | Distribución | edicion |
| distribucion.incidencia | Registrar incidencias | Distribución | edicion |
| distribucion.documentos | Generar/cargar guía y emitir folio de documentos | Distribución | edicion |
| distribucion.carga | Registrar fotos y validación de la carga (auxiliar y chofer) | Distribución | edicion |
| facturacion.cargar | Evaluar pedido validado y cargar factura | Facturación | edicion |
| alertas.ver | Ver alertas propias/del rol | Alertas | consulta |
| alertas.gestionar | Asignar, atender, comentar y cerrar alertas | Alertas | edicion |
| alertas.ver_todas | Ver alertas de todas las áreas | Alertas | consulta |
| alertas.configurar | Configurar destinatarios/canales/urgencia de alertas | Alertas | administracion |
| config.ver | Consultar configuración | Configuración | consulta |
| config.editar | Editar configuración y catálogos (solo Sistemas) | Configuración | exclusivo |
| usuarios.administrar | Administrar usuarios y matriz de permisos | Configuración | administracion |
| auditoria.ver | Consultar bitácora de auditoría | Configuración | consulta |
| export.datos | Exportar registros | General | consulta |

## Permisos por rol

### Gerencia General

Todos los permisos (70) — D: Informe Funcional §15; Decisión del usuario Q4 (11-oct-2026): acceso completo, incluso aprobar en nombre de otros roles (salvo los permisos exclusivos: precios y venta bajo mínimo del Jefe Comercial, Decisión del usuario (13-oct-2026) Q11; configuración de Sistemas, Decisión del usuario (13-oct-2026, segunda parte)). Las aprobaciones no se omiten; quedan auditadas (decisión pendiente IF §15).

### Sistemas

Todos los permisos (54) — D: Decisión del usuario (13-oct-2026, segunda parte): Sistemas tiene todo el panel de configuración. Las aprobaciones no se omiten; quedan auditadas (decisión pendiente IF §15).

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
- `ov.aprobar_parcial` – Aprobar despacho parcial (**D**; Decisión del usuario Q3 (11 y 12-oct-2026): aprueba Gerencia de Operaciones o Jefatura de Logística)
- `ov.renegociar` – Registrar renegociación de fecha / cambio de producto (**D**; Informe Funcional §4.5, §5 (participa en renegociación))
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
- `precios.ver` – Consultar listas de precios (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Jefe Comercial (Jefe de Ventas)

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `clientes.canal` – Asignar canal de precios y cargar condiciones de clientes (penalidades, lotes) (**D**; Decisión del usuario (13-oct-2026, segunda parte): el Jefe Comercial asigna y traslada clientes de canal)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.aprobar_precio` – Liberar una OV retenida por precio en el límite o bajo el mínimo (**D**; Decisión del usuario (13-oct-2026, segunda parte): la OV bajo el mínimo queda detenida hasta la confirmación del Coordinador Comercial o Jefe Comercial)
- `ov.autorizar_modificacion` – Autorizar modificación de OV solicitada por Asistente (**D**; Informe Funcional §5)
- `ov.cancelar` – Cancelar OV (**D**; Informe Funcional §5)
- `ov.crear` – Registrar OV (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.importar` – Importar OV desde exportación SAP (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.modificar` – Modificar OV directamente (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.renegociar` – Registrar renegociación de fecha / cambio de producto (**D**; Informe Funcional §4.5, §5 (Comercial participa))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `precios.editar` – Cargar y modificar listas de precios mínimos y su vigencia (solo Jefe Comercial) (**D**; Decisión del usuario (13-oct-2026) Q11: único con autorización para modificar precios)
- `precios.ver` – Consultar listas de precios (**D**; Decisión del usuario (13-oct-2026) Q11: único con autorización para modificar precios)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Coordinador de Ventas

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.aprobar_precio` – Liberar una OV retenida por precio en el límite o bajo el mínimo (**D**; Decisión del usuario (13-oct-2026, segunda parte): confirma OV detenida por precio (Coordinador Comercial))
- `ov.autorizar_modificacion` – Autorizar modificación de OV solicitada por Asistente (**D**; Informe Funcional §5)
- `ov.cancelar` – Cancelar OV (**D**; Informe Funcional §5)
- `ov.crear` – Registrar OV (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.importar` – Importar OV desde exportación SAP (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.modificar` – Modificar OV directamente (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.renegociar` – Registrar renegociación de fecha / cambio de producto (**D**; Informe Funcional §4.5, §5 (Comercial participa))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `precios.ver` – Consultar listas de precios (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Asistente de Ventas

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.crear` – Registrar OV (**D**; Diagrama AS-IS L5 (Asistente comercial ingresa la OV))
- `ov.importar` – Importar OV desde exportación SAP (**D**; TO-BE COPROD-ONE (L5): el asistente carga el consolidado de OV emitidas y cambios)
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

### Coordinación de Almacén 1560 (producto terminado)

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
- `reempaque.solicitar` – Solicitar reempaque y aprobar/enviar la pre-solicitud a Calidad (**D**; Informe Funcional §9.1; Decisión del usuario (12-oct-2026) Q12: aprueba la pre-solicitud)
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
- `reempaque.solicitar` – Solicitar reempaque y aprobar/enviar la pre-solicitud a Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
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
- `distribucion.confirmar_salida` – Autorizar y confirmar la salida del camión (**D**; Decisión del usuario (12-oct-2026) Q16: el Líder Operativo autoriza la salida)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
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
- `distribucion.documentos` – Generar/cargar guía y emitir folio de documentos (**D**; TO-BE COPROD-ONE (L5): Distribución genera/carga guía e imprime folio)
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
- `distribucion.documentos` – Generar/cargar guía y emitir folio de documentos (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.entrega` – Registrar avance y entrega con evidencia (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.flota` – Mantener flota y conductores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.incidencia` – Registrar incidencias (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.programar` – Generar/ajustar programación de rutas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Conductor

- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.carga` – Registrar fotos y validación de la carga (auxiliar y chofer) (**D**; TO-BE COPROD-ONE (L5): validación de carga y foto (auxiliar y chofer))
- `distribucion.entrega` – Registrar avance y entrega con evidencia (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.incidencia` – Registrar incidencias (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Auxiliar de Despacho

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.carga` – Registrar fotos y validación de la carga (auxiliar y chofer) (**D**; TO-BE COPROD-ONE (L5): fotos, validación de carga, entrega con foto y guía firmada)
- `distribucion.entrega` – Registrar avance y entrega con evidencia (**D**; TO-BE COPROD-ONE (L5): fotos, validación de carga, entrega con foto y guía firmada)
- `distribucion.incidencia` – Registrar incidencias (**D**; Informe Funcional §12.3)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.visto_bueno_salida` – Dar visto bueno a la salida del camión (Auxiliar de Despacho) (**D**; Decisión del usuario (13-oct-2026) Q16: visto bueno de Seguridad, Líder Operativo y Auxiliar de Despacho)

### Jefatura de Logística

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.aprobar_solicitud` – Aprobar la solicitud de compra antes de pasar a Compras (**D**; Decisión del usuario (12-oct-2026) Q14: el Jefe de Logística aprueba la solicitud de compra)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.aprobar_salida_discrepancia` – Aprobar la salida con discrepancia de guía mientras se resuelve (**D**; Decisión del usuario (12-oct-2026) Q8)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.aprobar_parcial` – Aprobar despacho parcial (**D**; Decisión del usuario Q3 (11 y 12-oct-2026): aprueba Gerencia de Operaciones o Jefatura de Logística)
- `ov.decidir_alternativa` – Decidir uso de stock de otros almacenes (**D**; Informe Funcional §4.5, §6.2, §13; Decisión del usuario (12-oct-2026) Q13)
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.cambiar_estado` – Cambiar estado de stock (dañado, no utilizable, etc.) (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
- `stock.conteo` – Registrar conteos físicos (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.autorizar` – Autorizar traslado (**D**; Informe Funcional §4.5, §6.2, §13; Decisión del usuario (12-oct-2026) Q13)
- `traslado.recibir` – Confirmar recepción de traslado en destino (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
- `traslado.salida` – Registrar salida de traslado (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
- `traslado.solicitar` – Solicitar traslado (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Coordinación de Logística

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `calidad.ver` – Consultar registros de Calidad (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.aprobar_salida_discrepancia` – Aprobar la salida con discrepancia de guía mientras se resuelve (**D**; Decisión del usuario (12-oct-2026) Q8)
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `export.datos` – Exportar registros (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `ov.decidir_alternativa` – Decidir uso de stock de otros almacenes (**D**; Informe Funcional §4.5, §6.2 (Logística decide))
- `ov.ver` – Consultar órdenes de venta (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `produccion.ver` – Consultar producción (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `reempaque.ver` – Consultar reempaques (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.cambiar_estado` – Cambiar estado de stock (dañado, no utilizable, etc.) (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
- `stock.conteo` – Registrar conteos físicos (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslado.autorizar` – Autorizar traslado (**D**; Decisión del usuario (12-oct-2026) Q13: aprueba el Jefe o el Coordinador de Logística)
- `traslado.recibir` – Confirmar recepción de traslado en destino (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
- `traslado.salida` – Registrar salida de traslado (**D**; Decisión del usuario (13-oct-2026) Q5: maneja los almacenes virtuales (solo esos))
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

### Coordinador de Importación

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `compras.ver` – Consultar compras (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `importaciones.gestionar` – Registrar importaciones, fases y fechas (**D**; Informe Funcional §11)
- `importaciones.ver` – Consultar importaciones (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `stock.ver` – Consultar stock y reservas (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Seguridad

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `distribucion.seguridad` – Control de Seguridad: ingreso, inspección, carga vs guía y revisión de documentos (**D**; Informe Funcional §12.2, §13; TO-BE COPROD-ONE (L5): revisa documentos completos (la salida la autoriza el Líder Operativo, Q16))
- `distribucion.ver` – Consultar distribución (**P**; Informe Funcional §3 (alcance por área) – propuesto)
- `traslados.ver` – Consultar traslados (**P**; Informe Funcional §3 (alcance por área) – propuesto)

### Facturación

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; TO-BE COPROD-ONE (L5))
- `alertas.ver` – Ver alertas propias/del rol (**P**; TO-BE COPROD-ONE (L5))
- `distribucion.ver` – Consultar distribución (**P**; TO-BE COPROD-ONE (L5))
- `facturacion.cargar` – Evaluar pedido validado y cargar factura (**D**; TO-BE COPROD-ONE (L5): evaluar pedido validado, generar factura en SAP y cargarla al sistema)
- `ov.ver` – Consultar órdenes de venta (**P**; TO-BE COPROD-ONE (L5))

### Coordinación de Almacén 1524 (materia prima, granel e insumos)

- `alertas.gestionar` – Asignar, atender, comentar y cerrar alertas (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `alertas.ver` – Ver alertas propias/del rol (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `calidad.ver` – Consultar registros de Calidad (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `compras.recibir` – Registrar recepción de compra (**D**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `compras.solicitar` – Originar solicitud de compra (**D**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `compras.ver` – Consultar compras (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `dashboard.ver` – Ver tablero de indicadores (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `distribucion.ver` – Consultar distribución (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `export.datos` – Exportar registros (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `importaciones.recibir` – Registrar recepción de importación (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `importaciones.ver` – Consultar importaciones (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `ov.ver` – Consultar órdenes de venta (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `preparacion.registrar` – Registrar preparación/picking (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `produccion.recibir_pt` – Validar recepción de PT y diferencias (**D**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `produccion.solicitud` – Crear/revisar/enviar solicitud preliminar de producción (**D**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `produccion.ver` – Consultar producción (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `reempaque.solicitar` – Solicitar reempaque y aprobar/enviar la pre-solicitud a Calidad (**D**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `reempaque.ver` – Consultar reempaques (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `stock.autorizar_carga` – Autorizar/confirmar carga de stock (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `stock.cambiar_estado` – Cambiar estado de stock (dañado, no utilizable, etc.) (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `stock.cargar` – Cargar archivos de stock/movimientos (validación previa) (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `stock.conteo` – Registrar conteos físicos (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `stock.ver` – Consultar stock y reservas (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `traslado.recibir` – Confirmar recepción de traslado en destino (**D**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `traslado.salida` – Registrar salida de traslado (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)
- `traslados.ver` – Consultar traslados (**P**; Decisión del usuario (12-oct-2026) Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524)

## Tipos de alerta

Canales: panel del módulo y correo (si hay SMTP). Ciclo: Nueva → Asignada → En atención → Cerrada (motivo y acción obligatorios). Gerencia General ve todo y elige qué recibe por correo; Gerencia de Operaciones ve las áreas de su ámbito (parámetro).

| Código | Alerta | Área / grupo | Prioridad | Destinatarios (roles) | Origen dest. | Correo | Condición | Fuente |
|---|---|---|---|---|---|---|---|---|
| OV_FALTANTE | Faltante de stock en OV | Almacén / Faltantes y cobertura | ALTA | COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_LOGISTICA, COORD_LOGISTICA, GERENCIA_OPERACIONES | DEFINIDO | sí | Al evaluar una OV nueva o modificada con cobertura < 100 %. | Informe Funcional §6.3 |
| OV_DECISION_PARCIAL | Decisión de despacho parcial requerida | Logística / Faltantes y cobertura | ALTA | JEFE_LOGISTICA, GERENCIA_OPERACIONES, JEFE_VENTAS, COORD_VENTAS | DEFINIDO | sí | OV con faltante y stock reservado parcial. Comercial es informado; aprueba GO o Jefatura de Logística. | Informe Funcional §6.3; aprueba GO o Jefatura de Logística (Q3) |
| OV_COMPLETA | OV completa con stock reservado | Almacén / Estados de pedidos | MEDIA | JEFE_LOGISTICA, JEFE_VENTAS, COORD_ALMACEN, COORD_ALMACEN_MP | DEFINIDO | no | La evaluación reserva el 100 % de la OV. | TO-BE COPROD-ONE: 'Avisar (Jefe de logística, Jefe comercial, coordinador almacén)' |
| OV_SALDO_REPROGRAMADO | Saldo de despacho parcial reprogramado | Comercial / Faltantes y cobertura | ALTA | JEFE_VENTAS, COORD_VENTAS, COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_LOGISTICA, GERENCIA_OPERACIONES | PROPUESTO | sí | Al salir un despacho parcial se crea la OV de saldo con la fecha reprogramada. | Decisión Q3 (11-oct-2026): lo que falta despachar se reprograma |
| OV_PARCIAL_APROBADO | Despacho parcial aprobado | Distribución / Rutas | ALTA | COORD_DISTRIBUCION, ASIST_DISTRIBUCION | DEFINIDO | sí | Se aprueba entrega parcial; se genera propuesta de ruta. | Informe Funcional §6.3 |
| OV_CAMBIO | Cambio de OV con reserva existente | Comercial / Cambios de OV | MEDIA | JEFE_LOGISTICA, COORD_LOGISTICA, COORD_ALMACEN, COORD_ALMACEN_MP, GERENCIA_OPERACIONES | DEFINIDO | sí | Modificación de una OV que ya tenía reservas. | Informe Funcional §6.3, §14 |
| OV_MODIF_SOLICITUD | Solicitud de modificación de OV (Asistente) | Comercial / Cambios de OV | MEDIA | JEFE_VENTAS, COORD_VENTAS | DEFINIDO | sí | El Asistente de Ventas solicita modificar una OV; autorizan Coord./Jefe de Ventas o vendedor responsable. | Informe Funcional §5 |
| OV_CANCELADA | OV cancelada (reserva y ruta liberadas) | Comercial / Cambios de OV | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP, COORD_DISTRIBUCION, ASIST_DISTRIBUCION, JEFE_LOGISTICA | PROPUESTO | sí | Cancelación por Coordinador o Jefe de Ventas. | Informe Funcional §5, §14 |
| OV_ESTADO | Cambio de estado de pedido | Comercial / Estados de pedidos | BAJA | COORD_VENTAS | PROPUESTO | no | Cambio de estado relevante de la OV (preparada, despachada, entregada). | Informe Funcional §14 |
| OV_80_PREPARACION | Pedido al 80 % de preparación | Almacén / Estados de pedidos | MEDIA | COORD_DISTRIBUCION, ASIST_DISTRIBUCION, COORD_VENTAS | PROPUESTO | no | Avance de preparación ≥ umbral configurado (80 %). | Informe Funcional §14 (condición definida; destinatarios propuestos) |
| OV_PREPARADA | Término del picking: pedido listo para despacho | Almacén / Estados de pedidos | MEDIA | JEFE_VENTAS, COORD_VENTAS, GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_DISTRIBUCION, ASIST_DISTRIBUCION, JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Preparación al 100 %. | TO-BE COPROD-ONE: 'Generar alerta (comercial, GO, jefe de logística) y documentos para calidad, distribución' |
| OV_RETRASO | OV no despachada en la fecha comprometida | Distribución / Retrasos | ALTA | GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_VENTAS | PROPUESTO | sí | Fecha comprometida vencida sin salida registrada. | Informe Funcional §14 ('retrasos') |
| RESERVA_AFECTADA | Reserva afectada por actualización de stock | Almacén / Faltantes y cobertura | ALTA | COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_LOGISTICA | PROPUESTO | sí | La nueva carga reduce un lote por debajo de lo reservado. | Informe Funcional §14 ('reservas') |
| STOCK_CARGA_DIFERENCIAS | Diferencias/errores en carga de stock | Sistemas / Diferencias de inventario | MEDIA | SISTEMAS, COORD_ALMACEN, COORD_ALMACEN_MP | DEFINIDO | sí | Carga confirmada con filas corregidas/excluidas o diferencias. | Informe Funcional §6.4 (alertar a Sistemas) |
| INVENTARIO_DIFERENCIA | Diferencia de inventario en conteo físico | Almacén / Diferencias de inventario | MEDIA | SISTEMAS, COORD_ALMACEN, COORD_ALMACEN_MP, GERENCIA_OPERACIONES | PROPUESTO | sí | Conteo cerrado con faltantes o sobrantes. | Informe Funcional §6.4, §14 |
| STOCK_PENDIENTE_REVISION | Carga recibida pendiente de revisión de Calidad | Calidad / Calidad | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD | PROPUESTO | no | Nuevo lote en estado Pendiente de revisión. | Informe Funcional §6.1, §9.4 |
| STOCK_NO_UTILIZABLE | Producto no utilizable / requiere fumigación | Calidad / Fumigación y no utilizables | ALTA | JEFE_CALIDAD, SUPERV_CALIDAD, COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_LOGISTICA | PROPUESTO | sí | Lote pasa a No utilizable o supera tiempo máximo de almacenamiento configurado. | Informe Funcional §6.1, §14 |
| FUMIGACION | Fumigación iniciada/finalizada | Calidad / Fumigación y no utilizables | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD, COORD_ALMACEN, COORD_ALMACEN_MP | PROPUESTO | no | Registro de inicio/fin de fumigación. | Informe Funcional §14; REG-BPM-CAL-005 |
| VENCIMIENTO_PROXIMO | Lote próximo a vencer | Almacén / Faltantes y cobertura | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP, COORD_VENTAS | PENDIENTE | no | Solo si se configura 'dias_vencimiento_proximo'. | Informe Funcional §21 (caso 'vencimiento'); umbral no definido |
| TRASLADO_SOLICITADO | Traslado pendiente de autorización | Logística / Traslados | MEDIA | JEFE_LOGISTICA, COORD_LOGISTICA | DEFINIDO | sí | Se solicita (o el sistema pre-solicita) un traslado desde almacén alternativo. | Informe Funcional §6.2, §13; Decisión del usuario (12-oct-2026) Q13 |
| TRASLADO_AUTORIZADO | Traslado autorizado | Almacén / Traslados | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP, AUX_ALMACEN | PROPUESTO | no | Logística autoriza el traslado. | Informe Funcional §13 |
| TRASLADO_DIFERENCIA | Diferencia en recepción de traslado | Logística / Traslados | ALTA | JEFE_LOGISTICA, COORD_ALMACEN, COORD_ALMACEN_MP, GERENCIA_OPERACIONES | PROPUESTO | sí | Cantidad recibida distinta a la enviada. | Informe Funcional §13 |
| OV_PRECIO_BAJO_MINIMO | OV detenida: precio en el límite o por debajo de la lista | Comercial / Cambios de OV | ALTA | JEFE_VENTAS, COORD_VENTAS, GERENTE_COMERCIAL | DEFINIDO | sí | Línea de OV (incluidas las muestras comerciales) con precio igual o menor al mínimo de lista del canal. También se avisa al vendedor de la OV. | Decisión del usuario (13-oct-2026) Q11; Decisión del usuario (13-oct-2026, segunda parte): se alerta y queda detenida hasta la confirmación del Coordinador o Jefe Comercial |
| PRECIO_FALTANTE | Producto o cliente sin precio mínimo | Comercial / Cambios de OV | MEDIA | JEFE_VENTAS | DEFINIDO | sí | Una OV trae un producto sin precio mínimo para el canal del cliente, o un cliente sin canal de precios asignado. | Decisión del usuario (13-oct-2026, segunda parte): 'el sistema debe botar una alerta y en base a eso ir completando' |
| LISTA_PRECIOS_VENCIDA | Lista de precios vencida o por vencer | Comercial / Cambios de fechas | MEDIA | JEFE_VENTAS | DEFINIDO | sí | Fecha de vencimiento de la lista alcanzada (o dentro del aviso). | Decisión del usuario (13-oct-2026, segunda parte): 'se avisa pero no se bloquea' |
| CARGA_SAP_DESACTUALIZADA | Carga de SAP sin actualizar | Sistemas / Diferencias de inventario | ALTA | SISTEMAS | DEFINIDO | no | La última carga autorizada de un tipo supera las horas configuradas; se avisa al área responsable y a Sistemas. | Decisión del usuario (13-oct-2026, segunda parte): cada área exporta a diario, con cortes de 2 veces al día como mínimo |
| PRESOLICITUD_AUTOMATICA | Pre-solicitudes generadas por faltante | Almacén / Solicitudes | ALTA | COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_LOGISTICA, COORD_LOGISTICA | DEFINIDO | sí | La OV queda con faltante y el sistema genera la pre-solicitud de la primera opción viable. | TO-BE COPROD-ONE (L5); Decisión del usuario (12-oct-2026) Q15 (orden: producir, reempaque, traslado, compra) |
| PRODUCCION_SOLICITUD | Solicitud de producción enviada | Producción / Solicitudes | ALTA | JEFE_PRODUCCION, ASIST_PRODUCCION | DEFINIDO | sí | Almacén envía solicitud preliminar. | Informe Funcional §8.2, §14 |
| PRODUCCION_RESPUESTA | Solicitud de producción validada/rechazada | Producción / Solicitudes | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP, COORD_VENTAS | PROPUESTO | sí | Producción valida o rechaza. | Informe Funcional §8.2 |
| LIQUIDACION_MONTACARGUISTA | Liquidación registrada: mover producto terminado | Almacén / Solicitudes | ALTA | MONTACARGUISTA, COORD_ALMACEN, COORD_ALMACEN_MP | DEFINIDO | no | Al registrar una liquidación. | Informe Funcional §8.3 |
| LIQUIDACION_DIFERENCIA | Diferencia entre liquidación y recepción de PT | Almacén / Diferencias de inventario | ALTA | JEFE_PRODUCCION, ASIST_PRODUCCION, COORD_ALMACEN, COORD_ALMACEN_MP | PROPUESTO | sí | Recepción física ≠ cantidad completada. | Informe Funcional §8.3; hoja 'Cruce' de Recep. pt.xlsx |
| MERMA_FUERA_PARAMETRO | Merma fuera de parámetros | Producción / Merma | ALTA | JEFE_PRODUCCION, ASIST_PRODUCCION, GERENCIA_OPERACIONES | PENDIENTE | sí | Solo si se configura 'umbral_merma_pct'. | Informe Funcional §14 ('cuando se defina el umbral') |
| REEMPAQUE_PRESOLICITUD | Pre-solicitud de reempaque por aprobar | Almacén / Solicitudes | ALTA | COORD_ALMACEN, COORD_ALMACEN_MP | DEFINIDO | sí | El sistema genera la pre-solicitud; el Coordinador de Almacén la aprueba y envía a Calidad. | TO-BE COPROD-ONE (L5); Decisión del usuario (12-oct-2026) Q12 |
| REEMPAQUE_SOLICITUD | Solicitud de reempaque para evaluación | Calidad / Solicitudes | ALTA | JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | El Coordinador de Almacén aprueba y envía la solicitud. | Informe Funcional §9.1; Decisión del usuario (12-oct-2026) Q12 |
| REEMPAQUE_APROBADO | Reempaque aprobado: ejecutar | Producción / Solicitudes | ALTA | COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_PRODUCCION, ASIST_PRODUCCION | DEFINIDO | sí | Calidad aprueba. | Informe Funcional §9.1 (notifica a Almacén y envía a Producción) |
| REEMPAQUE_DESAPROBADO | Reempaque desaprobado | Almacén / Solicitudes | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP | PROPUESTO | sí | Calidad desaprueba. | Informe Funcional §9.1 |
| COMPRA_APROBACION_LOGISTICA | Solicitud de compra por aprobar (Jefe de Logística) | Logística / Solicitudes | ALTA | JEFE_LOGISTICA | DEFINIDO | sí | Almacén envía la solicitud o el sistema genera la pre-solicitud. | TO-BE COPROD-ONE (L5); Decisión del usuario (12-oct-2026) Q14 |
| COMPRA_SOLICITUD | Solicitud de compra aprobada por Logística | Compras / Solicitudes | MEDIA | COMPRAS | DEFINIDO | sí | El Jefe de Logística aprueba la solicitud. | Informe Funcional §10.1, §14; Decisión del usuario (12-oct-2026) Q14 |
| COMPRA_MUESTRA | Muestra de compra para evaluación | Calidad / Solicitudes | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Compras lleva muestra a Calidad. | Informe Funcional §10.2-10.3 |
| COMPRA_APROBACION_GERENCIA | Compra de mayor volumen requiere aprobación | Gerencia / Solicitudes | ALTA | GERENCIA_OPERACIONES | PENDIENTE | sí | Cantidad ≥ umbral configurado. | Informe Funcional §7 (umbral y participación por validar) |
| COMPRA_RECEPCION_PROGRAMAR | Programar recepción de compra | Almacén / Cambios de fechas | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP | DEFINIDO | sí | Compras registra fecha prevista de recepción. | Informe Funcional §10.6 |
| COMPRA_FECHA_CAMBIO | Cambio de fecha de compra nacional | Compras / Cambios de fechas | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP, GERENCIA_OPERACIONES | DEFINIDO | sí | Compras modifica la fecha prevista. | Informe Funcional §10 (cambios generan alerta a Almacén y GO) |
| COMPRA_DIFERENCIA | Diferencias en recepción de compra | Compras / Diferencias de inventario | ALTA | COMPRAS, JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Almacén/Calidad detectan diferencias. | Informe Funcional §10.7 |
| REPOSICION_SUGERIDA | Reposición sugerida | Almacén / Solicitudes | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP, COMPRAS | PROPUESTO | sí | Análisis de reposición detecta necesidad. | Informe Funcional §7 (alerta, cantidad sugerida, fecha estimada) |
| IMPORT_LLEGADA | Llegada estimada de importación | Importaciones / Cambios de fechas | MEDIA | COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_LOGISTICA, COORD_LOGISTICA | DEFINIDO | sí | Registro o actualización de la llegada estimada. | Informe Funcional §11 |
| IMPORT_MODIFICACION | Modificación de fechas de importación | Importaciones / Cambios de fechas | ALTA | GERENCIA_OPERACIONES, COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_LOGISTICA, COORD_LOGISTICA | DEFINIDO | sí | Cambio de fecha de llegada o fase. | Informe Funcional §11 |
| IMPORT_FASE_VENCIDA | Fase de importación fuera de fecha | Importaciones / Retrasos | ALTA | IMPORTACIONES | DEFINIDO | sí | Fecha prevista de fase vencida sin fecha real. | Informe Funcional §11 |
| IMPORT_RECORDATORIO | Recordatorio de fase de importación | Importaciones / Cambios de fechas | BAJA | IMPORTACIONES | DEFINIDO | no | Faltan N días para la fecha prevista de una fase. | Informe Funcional §11 (recordatorios configurables) |
| IMPORT_DIFERENCIA | Diferencias en recepción de importación | Importaciones / Diferencias de inventario | ALTA | IMPORTACIONES, JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Recepción con diferencias. | Informe Funcional §11 |
| DIST_PROGRAMACION | Programación de distribución generada | Distribución / Rutas | MEDIA | COORD_DISTRIBUCION, ASIST_DISTRIBUCION, JEFE_LOGISTICA, COORD_LOGISTICA, GERENCIA_OPERACIONES, JEFE_VENTAS, COORD_VENTAS, JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | sí | Se genera/confirma la programación de rutas. | Informe Funcional §12.1; TO-BE: notificar a todas las áreas (calidad, comercial, GO, jefe de logística) |
| RUTA_ASIGNADA | Ruta asignada (chofer y auxiliar) | Distribución / Rutas | MEDIA | AUX_DESPACHO, CONDUCTOR | DEFINIDO | no | Distribución aprueba la ruta. | TO-BE COPROD-ONE: 'Generar alerta para chofer y auxiliar de las rutas que le fueron asignadas' |
| MONTACARGUISTA_DESPACHO | Trasladar mercadería a la zona de despacho | Almacén / Rutas | MEDIA | MONTACARGUISTA | DEFINIDO | no | Ruta aprobada con pedidos preparados. | TO-BE COPROD-ONE: 'Generar alerta para el traslado del montacarguista' |
| CARGA_INCONGRUENCIA | Incongruencia en la carga: validación cruzada | Almacén / Guías | ALTA | LIDER_ALMACEN, COORD_ALMACEN | DEFINIDO | sí | El auxiliar detecta productos incorrectos o incompletos frente a la pre-guía. | TO-BE COPROD-ONE: 'Avisar a almacenero asignado para la validación cruzada' |
| CAMION_CARGADO | Camión cargado y validado | Distribución / Rutas | MEDIA | JEFE_VENTAS, COORD_VENTAS, GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_DISTRIBUCION, FACTURACION | DEFINIDO | sí | Carga validada completa y correcta con foto. | TO-BE COPROD-ONE: 'Generar alerta de camión cargado (comercial, GO, jefe de logística, distribución, facturación)' |
| INC_CARGA | Incidencia durante la carga (Seguridad) | Seguridad / Incidencias | ALTA | COORD_DISTRIBUCION, JEFE_LOGISTICA, GERENCIA_OPERACIONES | PROPUESTO | sí | Seguridad registra una incidencia con foto, motivo y hora. | TO-BE COPROD-ONE: 'Subir foto de la incidencia ocurrida mientras se despachaba' |
| DOCUMENTOS_FALTANTES | Documentos faltantes para la salida | Seguridad / Guías | ALTA | COORD_DISTRIBUCION, FACTURACION, JEFE_LOGISTICA, JEFE_CALIDAD, SUPERV_CALIDAD, GERENCIA_OPERACIONES | DEFINIDO | sí | Seguridad revisa y faltan guía, factura o certificado aprobado. | TO-BE COPROD-ONE: 'Reportar documentos faltantes (distribución, facturación, calidad, jefe logística, GO)' |
| DIST_LLEGADA | Llegada al punto de entrega | Distribución / Rutas | BAJA | COORD_DISTRIBUCION, JEFE_LOGISTICA, GERENCIA_OPERACIONES | DEFINIDO | no | Llegada registrada. | TO-BE COPROD-ONE: 'Notificar a coordinador de distribución, jefe de logística, GO que se llegó' |
| DIST_ENTREGADO | Pedido entregado con conformidad | Distribución / Rutas | BAJA | COORD_DISTRIBUCION, JEFE_LOGISTICA, GERENCIA_OPERACIONES, JEFE_VENTAS, COORD_VENTAS | DEFINIDO | no | Entrega con foto y guía firmada. | TO-BE COPROD-ONE: 'Notificar a coordinador de distribución, jefe de logística, GO, comercial que se entregó' |
| DIST_AVANCE_RUTA | Avance de ruta | Distribución / Rutas | BAJA | JEFE_VENTAS, COORD_VENTAS, JEFE_LOGISTICA, COORD_LOGISTICA, COORD_DISTRIBUCION | DEFINIDO | no | Salida, llegada, entrega. | Informe Funcional §12.3 |
| GUIA_DISCREPANCIA | Discrepancia entre carga y guía: salida bloqueada | Seguridad / Guías | ALTA | COORD_DISTRIBUCION, SEGURIDAD, JEFE_LOGISTICA, COORD_LOGISTICA | DEFINIDO | sí | Cantidad cargada ≠ guía o presentación no coincide. Bloquea la salida salvo aprobación de Logística. | Informe Funcional §12.2, §14; Decisión del usuario (12-oct-2026) Q8 |
| SALIDA_CON_DISCREPANCIA | Salida aprobada con guía por resolver | Logística / Guías | ALTA | COORD_DISTRIBUCION, SEGURIDAD, LIDER_ALMACEN, JEFE_LOGISTICA, COORD_LOGISTICA, GERENCIA_OPERACIONES | DEFINIDO | sí | Jefe o Coordinador de Logística aprueba la salida mientras se resuelve la guía. | Decisión del usuario (12-oct-2026) Q8 |
| INC_RECHAZO_CALIDAD | Rechazo por calidad | Distribución / Incidencias | ALTA | GERENCIA_GENERAL, GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_LOGISTICA, COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_VENTAS, COORD_VENTAS, COORD_DISTRIBUCION | DEFINIDO | sí | Incidencia tipo rechazo por calidad. | Informe Funcional §12.3 (tabla de destinatarios); TO-BE (coord. distribución) |
| INC_GENERAL | Incidencia de distribución (llegada tarde u otra condición) | Distribución / Incidencias | ALTA | GERENCIA_OPERACIONES, JEFE_LOGISTICA, COORD_LOGISTICA, COORD_ALMACEN, COORD_ALMACEN_MP, JEFE_VENTAS, COORD_VENTAS, COORD_DISTRIBUCION | DEFINIDO | sí | Retraso, rechazo por cita, devolución, parcial, vehículo esperando, etc. | Informe Funcional §12.3 (tabla de destinatarios); TO-BE (coord. distribución) |
| CERTIFICADO_REVISION | Certificado pre-elaborado pendiente de revisión | Calidad / Certificados | MEDIA | JEFE_CALIDAD, SUPERV_CALIDAD | DEFINIDO | no | Se genera el certificado cuando la OV queda completa (TO-BE) o al terminar la preparación. | Informe Funcional §9.3, §9.4; TO-BE: 'Informar a Calidad para la validación del certificado pre-elaborado' |
| CERTIFICADO_LISTO | Certificado aprobado y cargado | Calidad / Certificados | MEDIA | COORD_DISTRIBUCION, GERENCIA_OPERACIONES, JEFE_LOGISTICA | DEFINIDO | no | Calidad aprueba el certificado. | TO-BE COPROD-ONE: 'Notifica a distribución, GO, jefe de logística que el certificado fue cargado' |
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
- RECHAZO_CITA: Rechazo por cita fuera de hora (TO-BE)
- PARTICULARIDAD_DESCARGA: Particularidad detectada en la mercadería en la misma descarga (TO-BE)
- INCIDENCIA_CARGA: Incidencia durante la carga, registrada por Seguridad (TO-BE)

## Parámetros configurables (IF §16)

| Parámetro | Valor inicial | Estado | Descripción | Fuente |
|---|---|---|---|---|
| margen_reposicion_dias | `None` | PENDIENTE | Margen adicional (días naturales) por posibles atrasos; aplicable por producto/material (campo en catálogo) o global. | Informe Funcional §7, §16, §20 |
| periodo_analisis_dias | `15` | AS-IS | Período de análisis por defecto para consumo promedio (cada producto puede tener el suyo). | Macro VBA 'TraerLotesStock' (PROM_15D) en PCP 2026 - J.xlsm |
| factor_stock_seguridad | `0.3` | AS-IS | Stock de seguridad como % del consumo mensual promedio observado en el Excel actual. Solo se aplica si 'usar_stock_seguridad' = sí. | Rotacion de inventario - Almacenes.xlsx, hoja Reporte ('30% stk seg') |
| usar_stock_seguridad | `False` | PENDIENTE | Aplicar el factor de stock de seguridad AS-IS en el análisis de reposición. | Informe Funcional §16 (stock mínimo configurable) |
| umbral_mayor_volumen | `None` | PENDIENTE | Valor a partir del cual una compra se considera de mayor volumen (en la unidad elegida abajo). | Informe Funcional §7, §20; Decisión del usuario (13-oct-2026, segunda parte) |
| umbral_mayor_volumen_unidad | `KG` | DEFINIDO | Unidad del umbral: KG (cantidad × peso del artículo), UNIDADES o SOLES (cantidad × precio cotizado). | Decisión del usuario (13-oct-2026, segunda parte): se configura en el panel |
| mayor_volumen_requiere_go | `True` | DEFINIDO | La compra de mayor volumen requiere aprobación de Gerencia de Operaciones (además del Jefe de Logística). | Informe Funcional §7; Decisión del usuario (13-oct-2026, segunda parte): configuración automática Gerencia de Operaciones |
| merma_pct_global | `None` | PENDIENTE | Porcentaje de merma por defecto (el catálogo de producto/material puede tener uno propio). | Informe Funcional §8.1, §16, §20 |
| prefijos_no_material_bom | `['RE-']` | PROPUESTO | Prefijos de componentes BOM que no son materiales inventariables (mano de obra, costo CIF). No se verifican contra stock. | LISTA DE MATERIALES 2026.xlsx (RE-xxx = 'MANO DE OBRA' / 'COSTO CIF') |
| umbral_merma_pct | `None` | PENDIENTE | Merma real (%) a partir de la cual se alerta 'merma fuera de parámetros'. | Informe Funcional §14 |
| cortes_preparacion | `[]` | PENDIENTE | Horarios de corte (HH:MM) que organizan la preparación. | Informe Funcional §4.9, §16 |
| tiempos_preparacion | `{'PEQUENO': '20-30 min', 'MEDIANO': '1 h - 1 h 30', 'GRANDE': '4 h (requiere 2 días de anticipación)'}` | AS-IS | Tiempos de preparación iniciales por tamaño de pedido (provisionales; medir y ajustar). | Diagrama AS-IS L5 (Revisar el stock físico vs. lo solicitado); IF §20 |
| umbrales_tamano_pedido_kg | `None` | PENDIENTE | Límites en kg para clasificar pedido pequeño/mediano/grande. | No definido en la documentación |
| umbral_alerta_preparacion_pct | `80` | DEFINIDO | Avance de preparación que dispara la alerta. | Informe Funcional §14 |
| orden_prioridad | `['fecha_compromiso', 'penalidad', 'completitud', 'urgencia']` | PROPUESTO | Criterios de prioridad en el orden aplicado. 'penalidad': a igual fecha, primero el cliente con penalidades más severas (lista de clientes con penalidades). El orden de desempate es propuesto. | Informe Funcional §1, §5, §12.1; Decisión del usuario (13-oct-2026, segunda parte) (lista de clientes con penalidades para priorizar) |
| peso_penalidad | `{'RETIRO_PROVEEDOR': 5, 'FECHA_ENTREGA': 4, 'FILL_RATE': 4, 'ENTREGA_PARCIAL': 3, 'RUPTURA_STOCK': 3, 'VENTANA_HORARIA': 2, 'PESO': 2, 'PALETIZADO': 2, 'DOCUMENTOS': 1, 'NO_CONFORMIDADES': 1}` | PROPUESTO | Peso de cada tipo de penalidad del cliente para la prioridad (suma). Valores propuestos para validar con Comercial. | Decisión del usuario (13-oct-2026, segunda parte) |
| aplicar_vida_util_cliente | `False` | PENDIENTE | Si 'vida útil 12 meses' de la lista de clientes significa vida útil RESTANTE mínima al despacho, activar: la reserva excluye lotes con menos meses de vida. Pendiente de confirmar. | Decisión del usuario (13-oct-2026, segunda parte) |
| almacen_transito_produccion | `ALM-003` | DEFINIDO | Almacén virtual de tránsito donde Producción deja el producto terminado hasta la validación de Almacén. | Decisión del usuario (12-oct-2026) Q5 |
| uso_almacen_por_tipo | `{'PT': 'PT', 'GR': 'MP_INSUMOS', 'MP': 'MP_INSUMOS', 'INSUMO': 'MP_INSUMOS'}` | DEFINIDO | Almacén principal según tipo de artículo (TIPO de la tabla DATA: PT/GR/MP; insumos EN-/SU- = INSUMO). | Informe Funcional §6.2 (1560 = PT; 1524 = materia prima, granel e insumos) |
| politica_lotes | `FEFO` | PROPUESTO | Orden de consumo de lotes al reservar (FEFO = primero en vencer, primero en salir). | Informe Funcional §22 (respetar lote y vencimiento) |
| dias_vencimiento_proximo | `None` | PENDIENTE | Días previos al vencimiento para alertar. | No definido |
| estado_lote_nuevo_carga | `PENDIENTE_REVISION` | DEFINIDO | Estado de los lotes nuevos que trae una carga SAP posterior a la base inicial: quedan pendientes de revisión de Calidad (no se reservan hasta liberarse). | Informe Funcional §6.1; Decisión del usuario (13-oct-2026) Q6 |
| carga_autorizada_verifica | `True` | PROPUESTO | Una carga revisada y autorizada marca los lotes como verificados (hasta que un conteo registre diferencias). | Informe Funcional §6.3-6.4 |
| reevaluar_tras_carga | `True` | PROPUESTO | Reevaluar automáticamente OV con faltantes (por prioridad) al ingresar stock. | Informe Funcional §1, §6.3 |
| bloquear_salida_con_discrepancia | `True` | DEFINIDO | Una discrepancia carga vs guía bloquea la salida; el Jefe o el Coordinador de Logística puede aprobar la salida mientras se resuelve la guía. | Informe Funcional §12.2; Decisión del usuario (12-oct-2026) Q8 |
| margen_por_proveedor | `{}` | DEFINIDO | Días de margen adicional por proveedor habitual del artículo ({proveedor: días}); prevalece sobre el margen global. | Informe Funcional §16; Decisión del usuario (13-oct-2026, segunda parte): configurable en el panel |
| excepciones_bom | `{}` | DEFINIDO | Excepciones a la proporcionalidad lineal: {producto: {componente: cantidad fija por orden}}; esa cantidad no se escala con el tamaño de la orden. | Informe Funcional §20; Decisión del usuario (13-oct-2026, segunda parte): configurable en el panel |
| conversiones_calidad_permitidas | `[]` | DEFINIDO | Conversiones de calidad permitidas en reempaque, como 'EXTRA>SUPERIOR'. Vacío = todas se proponen para evaluación de Calidad. | Informe Funcional §9.2; Decisión del usuario (13-oct-2026, segunda parte): configurable en el panel |
| clasificacion_abc_pct | `{'A': 80, 'B': 95}` | PROPUESTO | Clasificación ABC por consumo acumulado del período de análisis: A hasta el % indicado, B hasta su %, C el resto. | Excel de rotación (A/B/C); Decisión del usuario (13-oct-2026, segunda parte): configurable en el panel |
| orden_asignacion_flota | `['PROPIO', 'TERCERO', 'EXTERNO']` | DEFINIDO | Orden en que la propuesta de rutas asigna unidades (propias, de terceros, transporte externo). | Informe Funcional §12.1; Decisión del usuario (13-oct-2026, segunda parte): configurable en el panel |
| vehiculos_por_zona | `{}` | DEFINIDO | Restricción opcional de unidades por zona: {zona o distrito: [placas]}. Vacío = cualquier unidad. | Informe Funcional §12.1; Decisión del usuario (13-oct-2026, segunda parte): configurable en el panel |
| horas_max_sin_carga | `{'STOCK': 12, 'OV': 12, 'LIQUIDACION': 12, 'SALIDAS': 24}` | DEFINIDO | Horas máximas desde la última carga autorizada de cada tipo antes de alertar (2 cortes al día = 12 h). | Decisión del usuario (13-oct-2026, segunda parte): diario, 2 cortes al día como mínimo |
| responsable_carga | `{'STOCK': ['COORD_ALMACEN', 'COORD_ALMACEN_MP'], 'OV': ['ASIST_VENTAS'], 'LIQUIDACION': ['ASIST_PRODUCCION'], 'SALIDAS': ['COORD_ALMACEN']}` | PROPUESTO | Área (roles) que genera y sube cada exportación de SAP; recibe la alerta de carga desactualizada. | Decisión del usuario (13-oct-2026, segunda parte): 'cada área' |
| correo_habilitado | `False` | DEFINIDO | Enviar alertas por correo. Hoy no hay servidor de correo: las alertas quedan en el sistema. | Decisión del usuario (13-oct-2026, segunda parte) |
| retencion_datos_personales_dias | `None` | PENDIENTE | Días que se conservan fotos de entrega y datos personales de conductores antes de depurarlos. Vacío = no se depura. Debe fijarse según lo que permita la Ley 29733 y las normas aplicables (validación legal). | Decisión del usuario (13-oct-2026, segunda parte) |
| tolerancia_discrepancia_guia | `0` | PENDIENTE | Diferencia (unidades) entre guía y carga que se tolera sin considerarla discrepancia. | Decisión del usuario (12-oct-2026) Q8 (tolerancia no indicada) |
| zonas_distrito | `{}` | PENDIENTE | Agrupación de distritos en zonas de reparto (si está vacío se agrupa por distrito). | Informe Funcional §12.1 |
| capacidad_externo_kg | `[2000, 25000]` | AS-IS | Rango de capacidad de transportes externos (kg). | Imagen tabla de transportes (2 TN a 25 TN) |
| otif_definicion | `SALIDA` | DEFINIDO | OTIF = pedido que sale del almacén completo y a tiempo (la variante ENTREGA queda como referencia). | Informe Funcional §17; Decisión del usuario (12-oct-2026) Q2 |
| etapa_por_incidencia | `{'SALIDA_INCOMPLETA': 'Abastecimiento (stock, producción, compras)', 'SALIDA_TARDIA': 'Preparación y despacho', 'RECHAZO_CALIDAD': 'Calidad', 'PARTICULARIDAD_DESCARGA': 'Almacén (preparación/carga)', 'INCIDENCIA_CARGA': 'Almacén (preparación/carga)', 'RECHAZO_CITA': 'Distribución', 'LLEGADA_TARDE': 'Distribución', 'RETRASO': 'Distribución', 'VEHICULO_ESPERANDO': 'Distribución', 'CAMBIO_RUTA': 'Distribución', 'CONDUCTOR_NO_DISPONIBLE': 'Distribución', 'CLIENTE_AUSENTE': 'Cliente / Comercial', 'CLIENTE_NO_RETIRA': 'Cliente / Comercial', 'CANCELACION': 'Cliente / Comercial', 'ENTREGA_PARCIAL': 'Distribución', 'DEVOLUCION': 'Sin clasificar', 'RECHAZO_OTRO': 'Sin clasificar'}` | PROPUESTO | Etapa del proceso a la que se atribuye cada motivo de rechazo/incidencia en el análisis del fill rate. | Decisión del usuario (12-oct-2026) Q2 ('identificar en qué parte del proceso están los mayores errores') |
| ambito_gerencia_operaciones | `['Almacén', 'Distribución', 'Logística', 'Producción', 'Calidad', 'Compras', 'Importaciones', 'Seguridad', 'Comercial', 'Gerencia']` | PENDIENTE | Áreas cuyas alertas ve Gerencia de Operaciones. | Informe Funcional §14 ('alertas de su ámbito') |
| acceso_completo_omite_aprobaciones | `False` | DEFINIDO | Gerencia General tiene acceso completo y puede aprobar en nombre de otros roles (queda auditado como tal); Sistemas tiene acceso completo pero no aprueba. Ningún paso se omite. | Informe Funcional §15; Decisión del usuario Q4 (11-oct-2026) |
| parcial_aprobadores | `['GERENCIA_OPERACIONES', 'JEFE_LOGISTICA']` | DEFINIDO | Roles que pueden aprobar el despacho parcial. Gerencia General puede aprobar en nombre de ellos. | Decisión del usuario Q3 (11 y 12-oct-2026) |
| parcial_modo | `CUALQUIERA` | DEFINIDO | CUALQUIERA: basta la aprobación de uno de los roles; TODOS: deben aprobar todos. | Decisión del usuario Q3 (11 y 12-oct-2026): 'Gerencia de Operaciones o Jefe de Logística' (12-oct) |
| presolicitudes_automaticas | `True` | DEFINIDO | Ante un faltante el sistema genera la pre-solicitud de la primera opción viable (las personas aprueban). | TO-BE COPROD-ONE (L5); Decisión del usuario (12-oct-2026) Q15 |
| orden_presolicitudes | `['PRODUCCION', 'REEMPAQUE', 'TRASLADO', 'COMPRA']` | DEFINIDO | Orden de preferencia de la pre-solicitud automática; si la primera opción no cubre todo, el saldo pasa a la siguiente. | Decisión del usuario (12-oct-2026) Q15: producir, reempaque, traslado desde almacén externo, compra |
| alcance_almacen_por_rol | `{'COORD_ALMACEN': ['ALM-001', 'ALM-003', 'ALM-002', 'ALM-004', 'ALM-005', 'ALM-006', 'ALM-007', 'ALM-012', 'EXT-007', 'EXT-013', 'PRO-*'], 'COORD_ALMACEN_MP': ['EXT-002'], 'COORD_LOGISTICA': ['ALM-002', 'ALM-004', 'ALM-005', 'ALM-006', 'ALM-007', 'ALM-012', 'EXT-007', 'EXT-013', 'PRO-*'], 'JEFE_LOGISTICA': ['ALM-002', 'ALM-004', 'ALM-005', 'ALM-006', 'ALM-007', 'ALM-012', 'EXT-007', 'EXT-013', 'PRO-*']}` | DEFINIDO | Almacenes que maneja cada rol: solo actúa sobre los suyos (los no asignados, como los alternativos, los opera cualquier coordinador). 'PRO-*' abarca todos los códigos que empiezan con PRO-. Las alertas de almacén se dirigen al coordinador del almacén involucrado. | Decisión del usuario (12-oct-2026) Q17 (1560 y 1524); Decisión del usuario (13-oct-2026) Q5 (virtuales: Coord. 1560, Coord. y Jefe de Logística) y Q17 (alternativos: cualquiera) |
| vistos_buenos_salida | `['SEGURIDAD', 'AUX_DESPACHO', 'LIDER_ALMACEN']` | DEFINIDO | Roles cuya autorización y visto bueno requiere la salida del camión (el Líder Operativo da el último). | Decisión del usuario (13-oct-2026) Q16 |
| canal_precio_por_grupo | `{'MAYORISTA': 'MAYORISTA', 'INSTITUCIONAL': 'INSTITUCIONAL', 'CUENTAS CLAVE': 'CUENTAS CLAVE', 'MARCA BLANCA': 'MARCA BLANCA', 'CATERING': 'CATERING', 'HOTELES - RESTAURANTES': 'HOTELES - RESTAURANTES', 'AUTOSERVICIOS': 'AUTOSERVICIOS', 'ENTRETENIMIENTO': 'ENTRETENIMIENTO', 'E-COMMERCE': 'E-COMMERCE', 'DISTRIBUIDORES': 'DISTRIBUIDORES'}` | PROPUESTO | Columna de la lista de precios mínimos que corresponde a cada grupo de cliente. OFICINA, CANASTERIA y MINORISTA (presentes en las OV) no tienen columna en la lista: sus OV quedan sin precio hasta definirlo. | Decisión del usuario (13-oct-2026) Q11; columnas de PRICE_LIST_OCT-NOV_26 y 'Grupo de cliente' de la exportación OVS |
| margen_alerta_precio_pct | `0` | PENDIENTE | La alerta salta si el precio de venta está por debajo del mínimo de lista o a menos de este % por encima ('en el límite'). Con 0 se alerta solo si es igual o menor al mínimo. | Decisión del usuario (13-oct-2026) Q11 ('alertar si está en el límite o por debajo') |
| lista_granel_canales | `['MAYORISTA GRANEL']` | DEFINIDO | Canales de precio que usan la lista 'Mayorista granel' (mínimo por kg y por saco). La lista se elige por el canal del cliente: granel (sin proceso de empaque) o presentaciones (lista por canal). | Decisión del usuario (13-oct-2026, segunda parte): 'son por el tipo de canal' |
| aviso_vencimiento_lista_dias | `7` | PROPUESTO | Días antes del vencimiento de una lista de precios en que se avisa al Jefe Comercial (no se bloquea su uso). | Decisión del usuario (13-oct-2026, segunda parte) |
| retener_ov_bajo_minimo | `True` | DEFINIDO | La OV con precio en el límite o bajo el mínimo queda detenida (no se prepara ni despacha) hasta su confirmación. | Decisión del usuario (13-oct-2026, segunda parte) |
| programar_ruta_automatica | `True` | DEFINIDO | Al quedar una OV completa (o con parcial aprobado) el sistema la programa automáticamente en la mejor ruta propuesta. | TO-BE COPROD-ONE: 'Programar automáticamente la mejor ruta para el despacho' |
| certificado_previo_al_picking | `True` | DEFINIDO | Pre-elaborar los certificados al quedar la OV completa (antes del picking) para validación de Calidad. | TO-BE COPROD-ONE: 'Informar a Calidad para la validación del certificado pre-elaborado' |
| documentos_salida | `['GUIA', 'FACTURA', 'CERTIFICADO']` | DEFINIDO | Documentos que Seguridad verifica por pedido antes de autorizar la salida (certificado = aprobado por Calidad). | TO-BE COPROD-ONE: Seguridad 'Documentos completos?' / reportar faltantes a distribución, facturación y calidad |
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
| ALM-003 | Tránsito de Producción | TRANSITO_PRODUCCION | 90 | Decisión del usuario (12-oct-2026) Q5 | Almacén virtual: producto terminado por Producción hasta que Almacén lo valida y pasa a ALM-001. |
| ALM-010 | No se utiliza | NO_UTILIZADO | 99 | Decisión del usuario (12-oct-2026) Q5 | Almacén virtual no utilizado. |
| ALM-002 | Virtual ALM-002 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |
| ALM-004 | Virtual ALM-004 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |
| ALM-005 | Virtual ALM-005 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |
| ALM-006 | Virtual ALM-006 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |
| ALM-007 | Virtual ALM-007 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |
| ALM-012 | Virtual ALM-012 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |
| EXT-007 | Virtual EXT-007 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |
| EXT-013 | Virtual EXT-013 | VIRTUAL | 95 | Decisión del usuario (13-oct-2026) Q5 | Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística. |

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