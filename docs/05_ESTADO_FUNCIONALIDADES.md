# Estado de funcionalidades

Conteo sobre los 156 requerimientos (137 del IF + 18 del TO-BE + 1 de la decisión Q3) de `03_MATRIZ_TRAZABILIDAD.md`:

| Estado | Cantidad |
|---|---|
| ✅ Implementado y con prueba automatizada | 114 |
| ☑️ Implementado y verificado en pantalla (sin prueba automatizada específica) | 19 |
| 🟡 Parcial | 8 |
| ⏸️ Pendiente de decisión de negocio (implementado configurable o inactivo) | 14 |
| 🔜 Etapa futura según el IF | 1 |

> **El sistema NO está listo para producción.** Es una primera versión funcional para demostración en entorno
> controlado con datos ficticios. Antes de usarlo en la organización deben cerrarse las decisiones pendientes, validarse
> con usuarios clave y cumplirse los requisitos de `09_SEGURIDAD_INFRAESTRUCTURA.md`.

## 1. Implementado (resumen por módulo)

- **Comercial:** registro, importación SAP, modificación con versión, solicitud/autorización del Asistente, cancelación,
  renegociación, cambio de producto, despacho parcial aprobado por GO y Jefatura de Logística con OV de saldo
  reprogramada (Q3), carga del consolidado por el Asistente (TO-BE), aviso de OV completa, prioridad, historial.
- **Almacén:** 6 estados, reservas FEFO con lote/vencimiento/vida útil del cliente, cobertura, alternativas, cargas de
  stock con validación-corrección-autorización, conteos físicos, preparación por cortes con verificación de lote, alerta 80 %.
- **Traslados:** solicitud por Logística, autorización por Jefatura, salida, recepción con diferencias, reevaluación de OV.
- **Producción:** BOM versionada, calculadora, merma por niveles sin doble conteo, solicitud preliminar, validación,
  programa por línea con capacidad, inicio/fin, liquidación manual o por archivo, recepción de PT con cruce.
- **Reempaque:** 3 tipos, flujo completo con retención de stock y lote resultante a liberar.
- **Calidad:** 13 formatos (10 REG-* + bobinas, proceso, inspección de carga) con evaluación automática por límites
  documentados; liberación; fumigación ligada a estados; certificados autogenerados con revisión, correcciones registradas e impresión.
- **Compras y reposición:** análisis de reposición, solicitudes preliminares, cotización, muestra, aprobación GO, OC,
  cambio de fechas, recepción con diferencias, recepción bajo observación, subsanación.
- **Importaciones:** fases desde plantilla, fechas, recordatorios, fase vencida, cambios de llegada, recepción.
- **Distribución (IF + TO-BE):** ruta propuesta automáticamente al completar la OV, ajuste, confirmación con aviso al
  auxiliar y montacarguista, plan de picking validado/modificado por el Líder, fotos por etapa, incidencias de carga,
  validación de carga vs pedido, guía (sistema o SAP), pre-guía y folio imprimibles, factura (rol Facturación),
  revisión de documentos y autorización de Seguridad, verificación de salida, descarga de stock, llegada, entrega con
  foto y guía firmada, retorno a base, 15 tipos de incidencia (incluye rechazo por cita).
- **Alertas:** 58 tipos, destinatarios por rol/usuario, ciclo completo, deduplicación, cierre automático, visibilidad
  por rol/ámbito, agrupación para GG, preferencias de correo de GG, bandeja de correo.
- **Administración:** parámetros versionados, almacenes, plazos, líneas, fases, catálogo de artículos, clientes, flota,
  usuarios, matriz de permisos editable, auditoría, exportación a Excel, verificaciones periódicas (manual, CLI o cada N minutos).

## 2. Parcial

| ID | Qué falta | Motivo |
|---|---|---|
| OV-07 / OV-09 / KPI-10 | Confirmar campos de OV y fuente de precios (montos en 0 si la exportación no trae precio) | La exportación OVS no contiene precio (Q11) |
| PRD-04 | "Otras reglas de producción" | No están definidas en la documentación |
| PRD-12 | Carga de merma de insumos/granel desde SAP | No se recibió el formato SAP de merma; hoy se registra manualmente en la liquidación |
| DIS-06 | Reglas de asignación configurables (hoy el algoritmo es fijo; los datos de flota/zonas sí son configurables) | Reglas de flota no documentadas |
| CAL-F11 | Adjuntar fotos/evidencias a registros de Calidad | No exigido expresamente; observado en el informe 082-2026 |
| REP-04 | Rotación (clasificación A/B/C del Excel actual) en el análisis | Criterio de clasificación no documentado |

## 3. Pendiente de decisión (implementado de forma configurable o inactiva)

REP-02 margen de reposición · REP-06 umbral y rol de GO en compras de mayor volumen · COM-08 margen por proveedor ·
PRD-15 excepciones a la proporcionalidad · RMP-03 criterios de conversión de calidad · IMP-01 fases reales de importación ·
DIS-09 regla de bloqueo por discrepancia · ALR-07 matriz final de alertas · CFG-11 reparto de configuración Sistemas/GG ·
KPI-02 definición de OTIF · TB-15..18 contradicciones TO-BE vs IF (reempaque, aprobador de traslado, aprobación de
compra por Logística, pre-solicitudes automáticas). Ver Q2, Q5–Q17 en `02_ESPECIFICACION_CONSOLIDADA.md` y `10_ANALISIS_TO_BE.md`.
Resueltas el 11-oct-2026: Q1 (TO-BE recibido), Q3 (parcial y saldo) y Q4 (acceso completo; ROL-05).

## 4. Bloqueado / requiere autorización externa

| Funcionalidad | Dependencia | Situación |
|---|---|---|
| Envío real de correos | Servidor SMTP corporativo y cuenta autorizada | Implementado; sin SMTP los correos quedan en bandeja como SIN_SMTP (no se simula envío) |
| Integración directa con SAP | Fuera del alcance de la primera etapa (IF) | Solo carga de archivos exportados |
| Datos reales | Autorización para usar exportaciones reales en un entorno aprobado | Lectores verificados con los archivos recibidos (solo lectura); demo con datos ficticios |
| Inicio de sesión corporativo (SSO / Active Directory) | Datos del directorio y autorización de TI | Usuarios locales con contraseña |
| Notificaciones al celular | Etapa futura según el IF | No implementado |

## 5. Siguientes entregas recomendadas

1. Sesión de validación con usuarios clave usando el guion de demostración del README; registrar respuestas a Q2, Q5–Q17.
2. Cargar parámetros aprobados, matriz final de alertas y permisos; reemplazar valores DEMO.
3. Prueba piloto con exportaciones reales en un servidor aprobado por TI (PostgreSQL, HTTPS, SMTP).
4. Medir tiempos reales por etapa y ajustar cortes y tiempos de preparación.
5. Mejoras: múltiples viajes por unidad, adjuntos en Calidad, migraciones de base de datos (Alembic), SSO.
