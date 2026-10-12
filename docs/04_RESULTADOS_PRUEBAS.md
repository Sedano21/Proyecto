# Resultados de las pruebas

Fecha de ejecución: 13-oct-2026 (versión 0.5: decisiones del 13-oct, segunda parte, y lista de clientes con penalidades) · Python 3.13 · SQLite · datos **ficticios** (`app/demo_data.py`).
Comando: `python -m pytest tests -v` → **104 pruebas, 104 aprobadas, 0 fallidas** en SQLite (≈68 s). Las 103 pruebas funcionales también pasan sobre **PostgreSQL 16** (`TEST_DATABASE_URL`, ≈125 s); la prueba restante verifica que las migraciones de Alembic coincidan con el modelo.

## 1. Pruebas automatizadas

Cada prueba crea una base nueva, carga catálogos y datos de demostración **a través del mismo flujo de carga
con validación** que usará la organización, y ejecuta la lógica real (no hay simulaciones de servicios).

### 1.1 Casos de prueba exigidos por el IF §21 (punto 8)

| Caso IF §21 | Prueba | Qué verifica |
|---|---|---|
| Pedido completo | `test_pedido_completo_flujo_hasta_entrega` | Reserva 100 %, picking por lote, certificado autogenerado, ruta, Seguridad, salida con descarga de stock, entrega con foto + guía, OTIF |
| Faltante | `test_faltante_cobertura_alertas_y_alternativas`, `test_despacho_parcial_aprobacion_y_saldo` | FEFO, cobertura unidades/líneas, alertas y destinatarios, pre-solicitudes automáticas (nada se ejecuta solo); parcial aprobado por GO **o** Jefatura de Logística (Q3; con `parcial_modo` = TODOS se exigen ambos), Comercial/Sistemas/Coord. Logística no aprueban, ruta y OV de saldo reprogramada al salir |
| Cambio de OV | `test_cambio_ov_conserva_reservas_y_alerta`, `test_asistente_modifica_solo_con_autorizacion`, `test_cancelacion_libera_reserva_y_ruta` | Reservas válidas conservadas, recálculo, alerta OV_CAMBIO; autorización del Asistente; cancelación libera reserva y ruta |
| Almacén alternativo | `test_almacen_alternativo_traslado_autorizado`, `test_traslado_con_diferencia` | Solo Jefatura de Logística autoriza; recepción en destino; reevaluación de la OV; diferencias alertadas |
| Vencimiento | `test_vencimiento_y_vida_util_cliente` | No reserva vencidos; respeta vida útil mínima del cliente; propone actualización de fecha |
| Reempaque | `test_reempaque_flujo_completo` | Almacén → Calidad → Producción; retención de cantidad; lote resultante pendiente de revisión; liberación y reevaluación automática |
| Producción | `test_produccion_bom_merma_y_liquidacion`, `test_merma_no_se_duplica_si_no_verificado` | Cálculo proporcional, merma solo si el Excel no la incluye, validación de 4 condiciones, capacidad de línea, liquidación, alerta al montacarguista, cruce de recepción |
| Compra | `test_compra_nacional_flujo` | Origen en Almacén, muestra a Calidad, aprobación GO por mayor volumen, OC, cambio de fecha, recepción con diferencias, autorización bajo observación solo por GO |
| Rechazo | `test_rechazo_por_calidad_alerta_gerencia_general` | Destinatarios definidos (incluye GG), estado de OV, reingreso como pendiente de revisión, correo directo a GG según preferencia |
| Devolución | `test_devolucion_y_entrega_parcial` | INC_GENERAL sin GG; entrega parcial con incidencia automática |
| TO-BE / Q4 (nuevo) | `test_tobe.py` (6 pruebas) | OV completa → aviso, certificado previo y ruta automática; cambio de lote en el plan de picking; fotos por etapa, incidencia de carga, carga incongruente, guía, factura, documentos faltantes, autorización de Seguridad, llegada y rechazo por cita; factura con modificaciones; Sistemas no aprueba y GG sí; carga del consolidado por el Asistente con cambios sujetos a autorización |
| Decisiones 12-oct (nuevo) | `test_respuestas_12oct.py` (8 pruebas) | Q16 Líder Operativo autoriza la salida (Distribución, Seguridad y Sistemas no); Q8 discrepancia bloquea, Logística aprueba con motivo, guía resuelta cierra la alerta, revalidar sin diferencias desbloquea; Q2 OTIF por salida, fill rate, rechazo posterior y causas por etapa; Q15 orden producir → reempaque → traslado → compra con cascada y sin duplicar; Q12 pre-solicitud de reempaque aprobada por el coordinador; Q17 alertas y acciones por almacén; Q5 ALM-003/ALM-010 |
| Decisiones 13-oct (nuevo) | `test_respuestas_13oct.py` (9 pruebas) | Q11 lista de precios mínimos cargada (fórmulas recalculadas, sin costo), solo el Jefe Comercial modifica (GG, Sistemas y Comercial no), historial; alerta de OV en el límite o por debajo al vendedor y Comercial, cierre al corregir; OV sin precio o canal sin columna; lista granel para mayorista; Q16 tres vistos buenos; Q5 almacenes virtuales; Q6 lote nuevo pendiente de revisión; Q9 reparto de liquidación con corrección; Q10 fases del Coordinador de Importación |
| Decisiones 13-oct, 2.ª parte (nuevo) | `test_respuestas_13oct_b.py` (17) y nuevas en `test_respuestas_13oct.py` | OV detenida por precio (muestra comercial incluida) y confirmación del Coord./Jefe Comercial; canal de cliente; granel por kg y saco; precios faltantes; vigencia; configuración solo de Sistemas; umbral de compras en kg/soles; margen por proveedor; excepciones BOM; conversiones de calidad; ABC; flota; partes de producción con las fórmulas de sus formatos; carga SAP desactualizada; correo deshabilitado; depuración de fotos; Microsoft 365 (simulado); redirección segura; lotes por SKU; prioridad por penalidad; aviso de fill rate |
| Cambio de fecha | `test_importacion_fases_y_cambio_fecha`, `test_renegociar_fecha_ov`, (compra) | Fases, recordatorios, fase vencida sin duplicar alertas, alerta a GO, recepción con diferencias; renegociación de fecha |

### 1.2 Detalle de ejecución

```
test_config.py::test_parametros_versionados_y_auditados ✔
test_config.py::test_merma_fuera_de_parametro ✔
test_config.py::test_gg_preferencias_por_web ✔
test_config.py::test_exportaciones ✔
test_config.py::test_ruta_automatica_capacidad_y_externo ✔
test_config.py::test_cita_no_confirmada_advierte ✔
test_config.py::test_salida_exige_pedidos_preparados ✔
test_controles.py::test_carga_stock_con_errores_se_corrige_antes_de_autorizar ✔
test_controles.py::test_carga_stock_reduce_reserva_y_reevalua ✔
test_controles.py::test_carga_bom_validacion_y_version ✔
test_controles.py::test_importar_ov_sap_y_liquidacion ✔
test_controles.py::test_parse_presentation ✔
test_controles.py::test_estados_stock_y_reservas ✔
test_controles.py::test_calidad_pcc1_y_no_conforme ✔
test_controles.py::test_certificado_revision_y_aprobacion ✔
test_controles.py::test_conteo_fisico_diferencias ✔
test_controles.py::test_alerta_ciclo_y_visibilidad ✔
test_controles.py::test_correo_sin_smtp_no_se_simula ✔
test_controles.py::test_alerta_80_por_ciento ✔
test_controles.py::test_reposicion_calculo ✔
test_controles.py::test_verificaciones_periodicas ✔
test_controles.py::test_matriz_permisos_reglas_documentadas ✔
test_controles.py::test_salidas_no_descarta_lineas_legitimas_y_evita_recarga ✔
test_controles.py::test_fechas_de_carga ✔
test_flujos.py::test_pedido_completo_flujo_hasta_entrega ✔
test_flujos.py::test_faltante_cobertura_alertas_y_alternativas ✔
test_flujos.py::test_despacho_parcial_aprobacion_y_saldo ✔
test_flujos.py::test_gerencia_general_aprueba_en_nombre_y_rechazo ✔
test_flujos.py::test_vencimiento_y_vida_util_cliente ✔
test_flujos.py::test_cambio_ov_conserva_reservas_y_alerta ✔
test_flujos.py::test_asistente_modifica_solo_con_autorizacion ✔
test_flujos.py::test_cancelacion_libera_reserva_y_ruta ✔
test_flujos.py::test_almacen_alternativo_traslado_autorizado ✔
test_flujos.py::test_traslado_con_diferencia ✔
test_flujos.py::test_reempaque_flujo_completo ✔
test_flujos.py::test_produccion_bom_merma_y_liquidacion ✔
test_flujos.py::test_merma_no_se_duplica_si_no_verificado ✔
test_flujos.py::test_compra_nacional_flujo ✔
test_flujos.py::test_rechazo_por_calidad_alerta_gerencia_general ✔
test_flujos.py::test_devolucion_y_entrega_parcial ✔
test_flujos.py::test_importacion_fases_y_cambio_fecha ✔
test_flujos.py::test_renegociar_fecha_ov ✔
test_migraciones.py::test_migraciones_al_dia ✔
test_respuestas_12oct.py::test_q16_lider_operativo_autoriza_salida ✔
test_respuestas_12oct.py::test_q8_discrepancia_bloquea_y_logistica_aprueba ✔
test_respuestas_12oct.py::test_q8_corregir_y_validar_de_nuevo_desbloquea ✔
test_respuestas_12oct.py::test_q2_otif_por_salida_y_fill_rate ✔
test_respuestas_12oct.py::test_q15_presolicitudes_en_orden_producir_reempaque_traslado_compra ✔
test_respuestas_12oct.py::test_q12_reempaque_presolicitud_aprobada_por_coordinador ✔
test_respuestas_12oct.py::test_q17_alertas_y_acciones_por_almacen ✔
test_respuestas_12oct.py::test_q5_transito_produccion_y_almacen_no_utilizado ✔
test_respuestas_13oct.py::test_q11_lista_cargada_formula_recalculada_y_solo_jefe_comercial_modifica ✔
test_respuestas_13oct.py::test_q11_alerta_si_la_ov_esta_en_el_limite_o_por_debajo ✔
test_respuestas_13oct.py::test_q11_ov_sin_precio_o_muestra_comercial_queda_detenida ✔
test_respuestas_13oct.py::test_q11_productos_o_clientes_sin_precio_alertan_para_completar ✔
test_respuestas_13oct.py::test_q11_lista_granel_por_canal_y_compara_kg_y_saco ✔
test_respuestas_13oct.py::test_q11_vigencia_de_lista_avisa_sin_bloquear ✔
test_respuestas_13oct.py::test_q16_salida_requiere_tres_vistos_buenos ✔
test_respuestas_13oct.py::test_q5_almacenes_virtuales_los_manejan_coord_1560_y_logistica ✔
test_respuestas_13oct.py::test_q6_lote_nuevo_en_carga_posterior_queda_pendiente_de_revision ✔
test_respuestas_13oct.py::test_q9_liquidacion_con_varios_lotes_reparte_la_cantidad ✔
test_respuestas_13oct.py::test_q10_fases_de_importacion_a_cargo_del_coordinador_de_importacion ✔
test_respuestas_13oct_b.py::test_roles_y_configuracion ✔
test_respuestas_13oct_b.py::test_umbral_mayor_volumen_en_kg_o_soles ✔
test_respuestas_13oct_b.py::test_margen_por_proveedor ✔
test_respuestas_13oct_b.py::test_excepcion_a_la_proporcionalidad ✔
test_respuestas_13oct_b.py::test_conversiones_de_calidad_configurables ✔
test_respuestas_13oct_b.py::test_clasificacion_abc ✔
test_respuestas_13oct_b.py::test_reglas_de_flota_configurables ✔
test_respuestas_13oct_b.py::test_partes_de_produccion_con_formulas_de_los_formatos ✔
test_respuestas_13oct_b.py::test_alerta_si_las_cargas_de_sap_no_se_actualizan ✔
test_respuestas_13oct_b.py::test_correo_deshabilitado_alertas_solo_en_sistema ✔
test_respuestas_13oct_b.py::test_depuracion_de_fotos_segun_retencion ✔
test_respuestas_13oct_b.py::test_login_microsoft_365 ✔
test_respuestas_13oct_b.py::test_login_no_redirige_a_sitios_externos ✔
test_respuestas_13oct_b.py::test_condiciones_de_clientes_cargadas_y_vinculadas_por_nombre ✔
test_respuestas_13oct_b.py::test_regla_de_lotes_por_sku_en_la_reserva ✔
test_respuestas_13oct_b.py::test_prioridad_por_penalidad_a_igual_fecha ✔
test_respuestas_13oct_b.py::test_aviso_fill_rate_en_decision_de_parcial ✔
test_tobe.py::test_ov_completa_avisa_certifica_y_programa_ruta ✔
test_tobe.py::test_modificar_plan_de_picking_cambia_lote ✔
test_tobe.py::test_carga_incongruente_y_documentos_faltantes ✔
test_tobe.py::test_factura_con_modificaciones_si_incompleto ✔
test_tobe.py::test_sistemas_no_aprueba_gerencia_general_si ✔
test_tobe.py::test_asistente_carga_consolidado_cambios_requieren_autorizacion ✔
test_web.py::test_login_y_bloqueo ✔
test_web.py::test_csrf_obligatorio ✔
test_web.py::test_permiso_por_pantalla ✔
test_web.py::test_recorrido_pantallas_sin_errores[gerente.general] ✔
test_web.py::test_recorrido_pantallas_sin_errores[sistemas] ✔
test_web.py::test_recorrido_pantallas_sin_errores[coord.almacen] ✔
test_web.py::test_recorrido_pantallas_sin_errores[jefe.calidad] ✔
test_web.py::test_recorrido_pantallas_sin_errores[coord.distribucion] ✔
test_web.py::test_recorrido_pantallas_sin_errores[compras] ✔
test_web.py::test_recorrido_pantallas_sin_errores[jefe.produccion] ✔
test_web.py::test_recorrido_pantallas_sin_errores[seguridad] ✔
test_web.py::test_recorrido_pantallas_sin_errores[vendedor1] ✔
test_web.py::test_recorrido_pantallas_sin_errores[jefe.ventas] ✔
test_web.py::test_recorrido_pantallas_sin_errores[coord.almacen.mp] ✔
test_web.py::test_recorrido_pantallas_sin_errores[lider.almacen] ✔
test_web.py::test_recorrido_pantallas_sin_errores[aux.despacho] ✔
test_web.py::test_flujo_web_ov_y_detalles ✔
test_web.py::test_carga_por_web_y_entrega_con_evidencia ✔
test_web.py::test_pantallas_ruta_y_folio_en_cada_etapa ✔
======================== 104 passed in 67.61s (0:01:07) ========================
```

## 2. Recorrido de la aplicación en ejecución (navegador)

Servidor iniciado con `python -m app.cli demo` + `python run.py`; recorrido automatizado con Chromium (Playwright):
registro de una OV con faltante desde el formulario, tablero de Gerencia General, alertas agrupadas, stock, carga de un
Excel con errores (mostró 4 filas con error y bloqueó la autorización), calculadora de BOM, matriz de permisos,
configuración, reposición y 11 pantallas adicionales: **todas respondieron 200, sin errores de servidor**.
La prueba `test_recorrido_pantallas_sin_errores` repite el recorrido de 46 pantallas para 9 perfiles distintos
(respuesta 200 o 403 según permiso; nunca 500).

### 2.1 Guion de demostración ejecutado de punta a punta por la interfaz

Con 9 usuarios distintos en el navegador: `coord.ventas` registra OV DEMO-001 (cobertura 70,42 % / 33,33 %) →
`coord.logistica` solicita traslado desde 767 → `jefe.logistica` autoriza → `coord.almacen` registra salida y recepción
(cobertura sube a 78,87 %) → `jefe.logistica` aprueba despacho parcial (se genera la ruta) → `lider.almacen` registra el
picking por lote hasta 100 % → se generan 3 certificados → `coord.distribucion` confirma la ruta → `seguridad` valida la
guía → `coord.distribucion` confirma la salida con los 5 controles → `aux.despacho` registra la entrega con foto y guía
firmada → la ruta queda CERRADA y la OV en ENTREGA PARCIAL; el tablero de Gerencia General muestra OTIF 0 % (entrega
incompleta, correcto). **0 respuestas 500 en el registro del servidor.**
Hallazgo corregido: en preparación, el formulario de una línea ya completa seguía visible; ahora se oculta.

### 2.2 Recorrido TO-BE con las decisiones Q3/Q4 (11-oct-2026)

Con 13 usuarios en Chromium: `coord.ventas` registra DEMO-001 (no ve el botón de aprobar parcial) → `coord.logistica`
solicita traslado → `sistemas` **no** ve "Autorizar" → `jefe.logistica` autoriza, `coord.almacen` recibe →
`jefe.logistica` aprueba el parcial con fecha de saldo (queda pendiente GO) → `gerente.operaciones` aprueba (parcial
aprobado) → `lider.almacen` valida el plan y registra el picking → `coord.distribucion` confirma la ruta →
`aux.despacho` foto del vehículo → `seguridad` foto de inicio de carga y validación vs guía → `aux.despacho` foto de
mercadería y valida la carga (aviso a Facturación) → `coord.distribucion` registra la guía → `facturacion` carga la
factura (marcada "con modificaciones" por ir incompleta) → `seguridad` revisa documentos: faltan certificados (aviso a
las áreas) → `superv.calidad` aprueba los certificados → `seguridad` autoriza la salida → `coord.distribucion` confirma
la salida → `aux.despacho` llegada, entrega con evidencia y retorno a base → la OV muestra el saldo **DEMO-001-S1**
reprogramado. **0 respuestas 500.** Hallazgo corregido: el formulario de Seguridad quedaba bloqueado por el número de
guía vacío; ahora se precarga la pre-guía `PRE-GUIA-<ruta>`.

### 2.3 Recorrido con las decisiones del 12-oct-2026

Base de demostración nueva y 14 usuarios en Chromium: `coord.ventas` registra DEMO-001 → la OV lista las
pre-solicitudes generadas por el sistema (producción, por ser la primera opción viable) → `jefe.logistica` aprueba solo
el parcial (Q3: Gerencia de Operaciones ya no ve el botón) → picking y carga → `seguridad` registra la validación con 1
unidad de diferencia → `lider.almacen` intenta autorizar: **"Salida bloqueada: discrepancias entre carga y guía"** →
`coord.logistica` aprueba la salida con motivo → `lider.almacen` autoriza la salida (Q16; `coord.distribucion` ya no ve
el botón) → `coord.distribucion` registra la guía resuelta → entrega, retorno y saldo DEMO-001-S1 → `coord.ventas`
registra DEMO-002 de un insumo (EN-903) → el sistema pre-solicita la compra → `jefe.logistica` la aprueba y pasa a
Compras (Q14) → el tablero de Gerencia General muestra OTIF por salida, fill rate 78,9 % y la tabla de causas por
etapa. **0 respuestas 500.**

### 2.4 Recorrido de precios mínimos (13-oct-2026)

`jefe.ventas` modifica un precio mínimo con motivo (queda en el historial) → `gerente.general` consulta la lista pero
no ve el botón para modificarla → `coord.ventas` registra una OV de un cliente CATERING a S/ 3,00 cuando el mínimo es
S/ 3,00 → la OV muestra "EN EL LÍMITE del mínimo" y el Jefe Comercial recibe la alerta. **0 respuestas 500.**

### 2.5 Recorrido de la versión 0.5 (13-oct-2026)

`coord.ventas` registra una OV sin precio para el cliente institucional: queda **detenida por precio** y muestra sus
condiciones ("máx. 1 lote por SKU; penalidades: fecha de entrega"). La confirma con motivo y queda liberada.
`jefe.ventas` ve el selector de canal de precios habilitado; `gerente.general` lo ve deshabilitado.
`asist.produccion` registra un parte de Cimbria con los datos de su formato: rendimiento 96,33 %, desmedro 2,78 %.
**0 respuestas 500.**

### 2.6 PostgreSQL, migraciones y respaldos
- La suite completa se ejecutó sobre PostgreSQL 16 (servidor temporal de prueba). Aparecieron 4 columnas demasiado cortas
  que SQLite no controlaba; se corrigieron.
- La migración inicial de Alembic se generó y aplicó. `alembic check` no encuentra diferencias con el modelo, y la
  demostración se creó sobre ese esquema.
- `scripts/respaldo_postgres.sh`: respaldo cifrado con GPG, sumas SHA-256 y rotación.
- `scripts/restaurar_prueba.sh`: verificación y restauración en una base temporal; ambas correctas.

## 3. Compatibilidad con los archivos reales (solo lectura, base temporal descartada)

Se procesaron los archivos originales con los lectores del sistema para comprobar que los formatos se reconocen y que
la validación detecta problemas reales. Nada se guardó en el repositorio.

| Archivo / hoja | Filas | Resultado de la validación | Incorporación (excluyendo filas con error) |
|---|---|---|---|
| PCP 2026 - J.xlsm / DATA | 634 | 2 errores: código **GR-256 duplicado** | 632 artículos |
| PCP 2026 - J.xlsm / STOCK_LOTE | 1 236 | 2 duplicados (GR-086 / lote 70817 / EXT-005); 1 fecha inválida ("01/01/0026"); fechas como número de serie de Excel convertidas; advertencias: 339 lotes con caracteres inusuales (p.ej. `821001MV..`), almacenes sin uso definido (ALM-010 210 filas, ALM-003 112, …), 33 artículos fuera del maestro | 1 233 lotes en 16 almacenes |
| LISTA DE MATERIALES 2026.xlsx | 2 065 | 2 filas duplicadas (C3-041 / ME-041), 1 componente con cantidad 0; 565 descripciones sin presentación identificable | Versión 1: 2 062 líneas, 398 productos |
| PCP 2026 - J.xlsm / OVS | 769 | 53 líneas de OV cerradas (omitidas), 6 productos repetidos en la misma OV (consolidados), 11 productos fuera del maestro | 194 OV evaluadas en 4,4 s: 53 completas, 96 incompletas, 45 sin stock |
| Recep. pt.xlsx / Dat.Prod | 118 | 4 sin lote; 3 documentos con 2 lotes (clave a validar, Q9); 17 lotes con caracteres inusuales | (no confirmado) |
| PRICE_LIST_OCT-NOV_26.xlsx | 350 | 0 errores; 10 canales; 2 SKU repetidos idénticos; fórmulas leídas | 3 480 precios mínimos (base temporal) |
| PRICE_LIST_GRANEL_OCT-DIC26.xlsx | 20 | 0 errores; GR-041 con precio por kg menor al costo; 2 SKU también en la lista general | 20 precios (base temporal) |
| LISTA DE CLIENTES - CON PENALIDADES Y LOTES.xlsx | 103 | 0 errores; 93 con 1 lote/SKU y 10 con 2; 75 sin coincidencia por nombre (sin RUC) | 103 condiciones; 28 vinculadas, que concentran 137 de 194 OV reales |
| PRICE_LIST_GRANEL (nueva versión) | 20 | Idéntica a la anterior | — |
| Rotacion de inventario / Qy | 42 141 | 396 líneas sin producto (servicios) se omiten | 41 663 registros de historial |

Cálculo de materiales con la BOM real (PT-005 × 100): MP-001 50 kg (ALM-003), EN-021 0,5, EN-096 0,18; aviso de merma no aplicada hasta confirmar si el Excel la incluye.
Hallazgo corregido durante esta prueba: la primera versión de la deduplicación de salidas descartaba 478 líneas legítimas
(mismo documento y producto en varias líneas); se corrigió y se agregó la prueba `test_salidas_no_descarta_lineas_legitimas_y_evita_recarga`.

## 4. Errores encontrados y corregidos durante el desarrollo

| Error | Corrección |
|---|---|
| El token CSRF no llegaba a los macros de plantilla (pantallas con error 500) | Token registrado como global de Jinja |
| El token CSRF se perdía al iniciar sesión | Se conserva el token al regenerar la sesión |
| Formularios dentro de filas de tabla no enviaban sus campos | Tablas editables convertidas a filas-formulario |
| Consumo diario incluía un día de menos en la ventana de análisis | Ventana = días completos anteriores a la fecha de análisis |
| Fechas del stock real como número de serie de Excel se rechazaban | Conversión de número de serie |
| La fecha real "01/01/0026" se aceptaba como año 26 | Rechazo de fechas fuera de 1990–2100 (prueba `test_fechas_de_carga`) |
| Liquidaciones reales con documento repetido en dos lotes se rechazaban | Clave documento + lote con advertencia |
| Deduplicación de salidas descartaba líneas legítimas | Deduplicación solo contra cargas anteriores |
| Se podía confirmar la salida de una ruta con pedidos aún no preparados | Validación agregada (prueba `test_salida_exige_pedidos_preparados`) |
| Formulario de picking visible en líneas ya completas | Se oculta y se marca "completa" |
| (TO-BE) Una parada nueva en una ruta existente se creaba sin la OV asociada | Se crea con la OV |
| (Q3) El saldo no se generaba al salir la ruta | `confirm_departure` crea la OV de saldo |
| (TO-BE) Reservas nuevas sin estado antes de guardarse no se contaban | Estado ACTIVA explícito |
| (TO-BE) Validación de Seguridad bloqueada por guía vacía | Pre-guía precargada |
| (13-oct) Columnas demasiado cortas detectadas en PostgreSQL (fuente, corte, estados) | Ampliadas; prueba de migraciones |
| (13-oct) Tras ingresar se podía redirigir a `//sitio-externo` | Solo rutas internas |
| (12-oct) Mensajes de pantalla aún decían "aprobado por todos" y "autoriza Jefatura de Logística" | Textos actualizados a Q3/Q13 |

## 5. Limitaciones de las pruebas

- No se probó envío real de correo (no hay servidor SMTP autorizado); se verificó que los correos quedan en bandeja como SIN_SMTP.
- No se probó con PostgreSQL/SQL Server (solo SQLite); la capa ORM es compatible pero requiere prueba en el entorno destino.
- No hay pruebas de carga concurrente ni de rendimiento con varios usuarios simultáneos.
- No se probó en dispositivos móviles (la interfaz es web adaptable básica).
- Las reglas marcadas PROPUESTO/PENDIENTE se probaron con los valores configurados, no constituyen validación de negocio.

## 6. Capturas de pantalla (datos ficticios)

| Captura | Contenido |
|---|---|
| [01](capturas/01_ov_faltante_alternativas.png) | OV con faltante: reservas FEFO, cobertura y alternativas |
| [03](capturas/03_tablero.png) / [12](capturas/12_tablero_post.png) | Tablero gerencial antes y después del despacho |
| [04](capturas/04_alertas_agrupadas.png) | Alertas agrupadas por área y urgencia |
| [06](capturas/06_carga_con_errores.png) | Carga de stock con errores bloqueada hasta corregir |
| [07](capturas/07_bom_calculo.png) | Calculadora de materiales con merma |
| [08](capturas/08_matriz_permisos.png) | Matriz de permisos D/P |
| [11](capturas/11_ruta_entregada.png) | Ruta cerrada con evidencia de entrega |
| [13](capturas/13_ruta_tobe.png) | Ruta con las etapas TO-BE: fotos, validación de carga, documentos, autorización de Seguridad, retorno |
| [14](capturas/14_ov_con_saldo.png) | OV con aprobación conjunta del parcial y saldo reprogramado |
| [15](capturas/15_alertas_tobe.png) | Alertas TO-BE vistas por Gerencia General |
| [16](capturas/16_tablero_fillrate.png) | Tablero con OTIF por salida, fill rate y causas por etapa (Q2) |
| [17](capturas/17_ov_presolicitud.png) | OV de insumo con pre-solicitud de compra automática (Q15) |
| [18](capturas/18_lista_precios.png) | Lista de precios mínimos con historial (Q11) |
| [19](capturas/19_ov_precio_bajo_minimo.png) | OV con precio en el límite del mínimo (Q11) |
| [20](capturas/20_ov_detenida_condiciones.png) | OV detenida por precio con las condiciones del cliente |
| [21](capturas/21_partes_produccion.png) | Parte de producción (Cimbria) con rendimiento y desmedro |
