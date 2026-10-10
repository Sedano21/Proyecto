# Inventario de la documentación fuente

Archivo recibido: `CONSULTA - copia.rar` (30 archivos). Se extrajeron y procesaron **todos**, incluidas todas las hojas
(visibles y ocultas) de cada Excel, las macros VBA del `.xlsm`, encabezados de los Word, todas las páginas de los PDF y
las imágenes. Los originales **no se modificaron** ni se incorporaron al repositorio (contienen datos reales de clientes,
RUC, precios, conductores y placas); solo se leyeron.

| # | Archivo | Tipo | Contenido identificado | Uso en el sistema |
|---|---|---|---|---|
| 1 | Informe_Funcional_Modulo_Operaciones_Corporacion_Productiva.docx | Word (23 secciones, 327 párrafos/tablas) | Especificación: alcance por área, flujo integral (TO-BE), OV, stock y estados, almacenes, reservas, cargas, plazos de compra, producción y BOM, reempaque, calidad, compras, importaciones, distribución, traslados, alertas, roles, configuración, KPI, archivos, controles, pendientes, etapas y criterios de aceptación | **Fuente principal**; todos los requerimientos RQ-* |
| 2 | WhatsApp Image 2026-10-09 at 6.19.58 PM.jpeg | Diagrama BPMN | **AS-IS "L5 – SUBPROCESO Gestión de Pedidos y Despachos"** con carriles Comercial, Coordinador de almacén, Líder operativo, Producción, Calidad, Distribución, Auxiliar distribución, Montacarguista, Vigilancia, Chofer y Cliente; tiempos (recepción de OV 4-5 veces, picking pequeño 20-30 min, mediano 1-1h30, grande 4 h y 2 días de anticipación), avisos por WhatsApp, reempaque, solicitud de compra, guías, rechazo por cita | Situación actual; tiempos provisionales; roles; contraste con TO-BE |
| 3 | WhatsApp Image 2026-10-09 at 6.22.24 PM.jpeg y (1).jpeg | Fotos de guías electrónicas | Guía de remisión: cliente, RUC, punto de partida/llegada, código, descripción con LOTE/FP/FV, cantidad, peso, placa, licencia del conductor, motivo de traslado, firma de recepción | Campos de validación carga vs guía y evidencia de entrega |
| 4 | WhatsApp Image 2026-10-09 at 6.28.48 PM.jpeg | Foto tabla de transportes | 4 unidades con conductor y capacidad (450; 4.5 TN; 10 TN; 25 TN) y "transportes externos 2 TN a 25 TN cuando las unidades propias no están disponibles" | Modelo de flota; capacidades de la demo (placas y nombres reemplazados por ficticios) |
| 5 | image (28).png | Foto ficha llenada | Ficha de muestreo CP-FOR-CAL-10 (granel): humedad, defectos, calibre, "% merma estimado", aprobado Sí/No | Campos del formato MUESTREO |
| 6 | PCP 2026 - J.xlsm | Excel con macros, 15 hojas | `OVS` (exportación SAP de OV, 42 col.), `STOCK_LOTE` (stock por artículo/lote/almacén), `STOCK_ALM`/`STOCK` (oculta) (stock por almacén), `DATA` (oculta; maestro con PPB, MAQ, TIPO PT/GR/MP, CALIDAD), `Ped. acum.`, `Ruta` (seguimiento de despachos: cliente, peso, dirección, hora cita, status picking/despacho), `BD - Seg.`, `OV - PROD`, `TD - FORM - PROD`, `TD_SEGUIMIENTO`, `TD_PICKING`, `PICKING` (RBPM-012 control de despacho de PT: lote, FP, FV), `pegar CD`, `CD`. Macros: `Seguimiento_OV`, `CrearOActualizarTABLA_OVS`, `TD_DETALLE`, `TD_COMPACTADO`, `TraerLotesStock` (usa **PROM_15D** = promedio de venta 15 días) | Formatos de carga OV, STOCK y PRODUCTOS; campos de OV; período de análisis AS-IS 15 días |
| 7 | LISTA DE MATERIALES 2026.xlsx | Excel, 1 hoja, 2 065 filas | BOM: Artículo/Descripción padre, Tipo BOM (P), Cantidad BOM (=1), Almacén PT, fechas, Orden (vacío = componente principal), Artículo/Descripción/Cantidad/Almacén componente, UM (vacía), Método emisión; 398 productos padre; componentes RE- (mano de obra / costo CIF) | Formato de carga BOM y cálculo proporcional |
| 8 | Recep. pt.xlsx | Excel, 5 hojas | `Recep. Pt` (conteo físico de PT por lote), `Consol. Recep`, `Dat.Prod` (órdenes de fabricación SAP: documento, cantidades planificada/completada, lote, fechas), `Ingre. Sap`, `Cruce` (SAP vs físico → FALTANTE/COMPLETO/SOBRANTE) | Formato de carga de liquidación; regla de cruce en recepción de PT |
| 9 | Rotacion de inventario - Almacenes.xlsx | Excel, 16 hojas (19 MB) | `Qy` (42 141 líneas de ventas), `TD`, `Evidencia NC`, `info`, `stock almacenes` (**correspondencia 1560=ALM-001, 767=EXT-001, 1524=EXT-002, Atsac 1=EXT-005, Atsac 2=EXT-010, Isabelita=EXT-014**), `Hoja4/5/1/3`, `Reporte` (rotación: X Mes, X Sem, **stock de seguridad 30 %**, cobertura, "Producir"), `Qy - OTIF`, `TD - OTIF`, `Resumen`, `Consolidado - OTIF`, `Sodexo` (oculta) | Mapeo de almacenes; historial de salidas para reposición; OTIF AS-IS |
| 10 | Inven. bobinas 1524.xlsx | Excel | Conteo de bobinas: Peso × Conteo = Físico; SAP; Faltante = MAX(SAP−Físico,0); Sobrante = MAX(Físico−SAP,0); comentarios por almacén | Regla de conteos físicos |
| 11 | REG-BPM-CAL-005 Registro de control de fumigación del grano.xlsx | Formato | Inicio/fin (desactivación) con fecha/operario/hora, producto, lote, tipo (BL/CTNR), sacos, peso, químico, dosis, lote | Formato FUMIGACION y cambio de estado de stock |
| 12 | REG-HACCP-CAL-006 Reporte de no conformidades y acciones correctivas.xlsx | Formato | Origen, reclamo, producto/lote/fechas, etapas, 5 porqués, plan de acción, estado de la acción | Formato NC_ACCION |
| 13 | REG-BPM-CAL-011 Control de vehículos de transporte de MP y PT.docx | Formato | Chofer, placa, MP/PT, limpieza/desinfección, plagas, contaminantes, contenedor, pallets, estiba (C/NC); repetir higiene si no cumple | Formato VEHICULO (Seguridad) |
| 14 | REG-BPM-CAL-013 Reporte de producto no conforme.docx | Formato | Identificación, motivo, acciones, destino (separación/contención/devolución/suspensión), informe al cliente, concesión | Formato NO_CONFORME |
| 15 | REG-CAL-002 Ficha de muestreo de producto.docx | Formato | Humedad y 16 defectos, materias extrañas, piedras, insectos | Formato MUESTREO |
| 16 | REG-CAL-003 Control de pesos, rotulado y sellado de PT.docx | Formato | 4 pesos, balanza, máquina, operario, rotulado, sellado H/V; criterios de peso 250 g / 500 g / 5 kg (50 kg inconsistente) | Formato CONTROL_PESOS con evaluación automática |
| 17 | REG-CAL-005 Informe de recepción de MP – productos importados.docx | Formato | Datos del producto, revisión documentaria, humedad máx. 15 %, defectos "Calidad superior" (enfermo 0, picado 2, partido 2, arrugado 2, materias extrañas 0.08, contrastante 2, total 8.08; NTP 205.015:2015) | Formato RECEPCION_IMPORTADO; especificación de referencia |
| 18 | REG-CAL-014 Ficha de control de calidad – granos.docx | Formato | Control en proceso por hora: muestra, humedad y defectos | Formato CONTROL_GRANOS |
| 19-20 | REG-HACCP-CAL-002 Control de recepción de materia prima.docx (y copia "(1)", idéntica: mismo MD5) | Formato | **Límites críticos PCC1 de humedad** por grupo (12.5 / 10 / 14.5 / 14.0 / 15 %), proveedor, N/I, lote, sacos/kg, impurezas, plaga | Formato RECEPCION_MP con evaluación PCC1 |
| 21 | REG-HACCP-CAL-003 Quejas del cliente.docx | Formato | Cliente, producto, motivo, disposición | Formato QUEJA |
| 22 | INFORME N° 082-2026 Recepción arveja verde partida … importado.pdf (6 p.) | Informe real | Ejemplo diligenciado de REG-CAL-005 con fotos | Validación del formato |
| 23-25 | N°CP2026-PT3756.pdf, N°CP2026-MP276.pdf, N°CP2026-CA0764.pdf | Certificados reales | Estructura: datos del producto (declarado, lote, FP, FV, marca/grado, procesado por, RUC, autorización sanitaria, presentación, país de origen, tamaño de lote, fecha de análisis), organoléptico, fisicoquímico (humedad), sanidad y aspecto, inocuidad, conclusiones; series PT / MP / CA | Plantilla de certificados autogenerados |
| 26 | ENVASADOS R1 R2 Y R3.pdf | Formato de producción | Línea envasado automático: OP, horas, turno, cantidad, lote PT/MP, sobrante, cal 3, % rendimiento, horas efectivas, ratio | Líneas de producción R1-R3; campos de liquidación (referencia) |
| 27 | LINEA TRUER.pdf | Formato de producción | Granel/MP/CAL3/desmedro, % rendimiento, % desmedro óptica/Buhler | Línea TRUER |
| 28 | Linea cimbria.pdf | Formato de producción | Ídem con tipo de saco/etiqueta, % desmedro | Línea CIMBRIA |
| 29 | SEL-MANUAL.pdf | Formato de producción | Selección manual por turno, operario, horas, kg | Línea SEL_MANUAL |

## Observaciones de la inspección

- **No se recibió un archivo TO-BE independiente.** El TO-BE se tomó del Informe Funcional (§4 flujo integral y §5-§14).
  El único AS-IS gráfico es el diagrama L5 (pedidos y despachos). Ver consulta Q1 en la especificación.
- REG-HACCP-CAL-002 está duplicado (copia idéntica).
- El `.xlsm` contiene macros que referencian hojas inexistentes (`TD_COMPACTADO`, `PROM_VTA`, `TD_STOCK_LOTE`, `TD_DETALLE`).
- Los archivos Excel reales contienen datos personales y comerciales; por eso las pruebas y la demo usan datos ficticios
  generados con la misma estructura (`sample_data/`).
- Validación de compatibilidad con los archivos reales: ver `04_RESULTADOS_PRUEBAS.md` §3.
