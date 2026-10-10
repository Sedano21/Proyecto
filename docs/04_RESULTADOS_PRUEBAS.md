# Resultados de las pruebas

Fecha de ejecución: 10-oct-2026 · Python 3.13 · SQLite · datos **ficticios** (`app/demo_data.py`).
Comando: `python -m pytest tests -v` → **55 pruebas, 55 aprobadas, 0 fallidas** (≈30 s).

## 1. Pruebas automatizadas

Cada prueba crea una base nueva, carga catálogos y datos de demostración **a través del mismo flujo de carga
con validación** que usará la organización, y ejecuta la lógica real (no hay simulaciones de servicios).

### 1.1 Casos de prueba exigidos por el IF §21 (punto 8)

| Caso IF §21 | Prueba | Qué verifica |
|---|---|---|
| Pedido completo | `test_pedido_completo_flujo_hasta_entrega` | Reserva 100 %, picking por lote, certificado autogenerado, ruta, Seguridad, salida con descarga de stock, entrega con foto + guía, OTIF |
| Faltante | `test_faltante_cobertura_alertas_y_alternativas`, `test_despacho_parcial_requiere_rol_y_genera_ruta` | FEFO, cobertura unidades/líneas, alertas y destinatarios, alternativas sin ejecución automática, decisión de parcial con rol y propuesta de ruta |
| Cambio de OV | `test_cambio_ov_conserva_reservas_y_alerta`, `test_asistente_modifica_solo_con_autorizacion`, `test_cancelacion_libera_reserva_y_ruta` | Reservas válidas conservadas, recálculo, alerta OV_CAMBIO; autorización del Asistente; cancelación libera reserva y ruta |
| Almacén alternativo | `test_almacen_alternativo_traslado_autorizado`, `test_traslado_con_diferencia` | Solo Jefatura de Logística autoriza; recepción en destino; reevaluación de la OV; diferencias alertadas |
| Vencimiento | `test_vencimiento_y_vida_util_cliente` | No reserva vencidos; respeta vida útil mínima del cliente; propone actualización de fecha |
| Reempaque | `test_reempaque_flujo_completo` | Almacén → Calidad → Producción; retención de cantidad; lote resultante pendiente de revisión; liberación y reevaluación automática |
| Producción | `test_produccion_bom_merma_y_liquidacion`, `test_merma_no_se_duplica_si_no_verificado` | Cálculo proporcional, merma solo si el Excel no la incluye, validación de 4 condiciones, capacidad de línea, liquidación, alerta al montacarguista, cruce de recepción |
| Compra | `test_compra_nacional_flujo` | Origen en Almacén, muestra a Calidad, aprobación GO por mayor volumen, OC, cambio de fecha, recepción con diferencias, autorización bajo observación solo por GO |
| Rechazo | `test_rechazo_por_calidad_alerta_gerencia_general` | Destinatarios definidos (incluye GG), estado de OV, reingreso como pendiente de revisión, correo directo a GG según preferencia |
| Devolución | `test_devolucion_y_entrega_parcial` | INC_GENERAL sin GG; entrega parcial con incidencia automática |
| Cambio de fecha | `test_importacion_fases_y_cambio_fecha`, `test_renegociar_fecha_ov`, (compra) | Fases, recordatorios, fase vencida sin duplicar alertas, alerta a GO, recepción con diferencias; renegociación de fecha |

### 1.2 Detalle de ejecución

```
test_config.py::test_parametros_versionados_y_auditados ✔
test_config.py::test_merma_fuera_de_parametro ✔
test_config.py::test_gg_preferencias_por_web ✔
test_config.py::test_exportaciones ✔
test_config.py::test_propuesta_rutas_capacidad_y_externo ✔
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
test_flujos.py::test_despacho_parcial_requiere_rol_y_genera_ruta ✔
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
test_web.py::test_flujo_web_ov_y_detalles ✔
test_web.py::test_carga_por_web_y_entrega_con_evidencia ✔
============================= 55 passed in 29.99s ==============================
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
