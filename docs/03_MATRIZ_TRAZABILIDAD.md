# Matriz de trazabilidad de requerimientos

**Estados:** ✅ Implementado y probado (prueba automatizada) · ☑️ Implementado, verificado en pantalla (sin prueba automatizada específica) ·
🟡 Parcial · ⏸️ Pendiente de decisión (implementado configurable/inactivo) · ⛔ Bloqueado (requiere acceso/autorización externa) · 🔜 Etapa futura (así lo indica el IF).

**Tipo:** D = definido · P = propuesto · PEND = pendiente · AS = AS-IS observado.
**Pruebas:** `F:` tests/test_flujos.py · `C:` tests/test_controles.py · `W:` tests/test_web.py · `K:` tests/test_config.py · `T:` tests/test_tobe.py · `R:` tests/test_respuestas_12oct.py.
**Fuentes nuevas:** `TO-BE` = diagrama TO-BE-COPROD-ONE (L5) · `Q3`/`Q4` = decisiones del 11-oct-2026 · `Q2`…`Q17` del 12-oct-2026 (`11_DECISIONES_12OCT.md`).
Código: `svc/` = `app/services/`, `vw/` = `app/views/`.

## Generales y controles (IF §1, §2, §19)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| GEN-01 | Mostrar fecha y origen de la última actualización de stock; no presentarlo como tiempo real | IF §1, §2, §19 | D | Barra superior en todas las pantallas (`base.html`, `svc/stock.stock_freshness`) | W: recorrido | ☑️ |
| GEN-02 | Trazabilidad de cambios, aprobaciones, versiones, incidencias y cargas | IF §2, §19 | D | `audit_log` en cada acción de servicio; pantalla Auditoría; historial en OV | K: parámetros; F: varios | ✅ |
| GEN-03 | Validar archivos antes de incorporar; mostrar errores; quien carga corrige | IF §2, §6.4, §19 | D | `svc/uploads.py` (validar → corregir/excluir → autorizar) | C: carga stock con errores | ✅ |
| GEN-04 | Guardar versiones de listas y configuraciones | IF §19 | D | `bom_versions`, `param_history` | C: BOM versión; K: parámetros | ✅ |
| GEN-05 | Evitar duplicados al recargar archivos | IF §19 | D (claves PEND) | Claves por tipo: stock artículo/lote/almacén; BOM padre/componente; OV OV/producto; liquidación documento+lote; salidas documento/producto/fecha/cantidad | C: liquidación duplicada, salidas | ✅ (claves a validar, Q9) |
| GEN-06 | Separar consulta, edición, aprobación y administración | IF §19 | D | 64 permisos tipificados; matriz rol-permiso editable | C: matriz; W: permiso por pantalla | ✅ |
| GEN-07 | Exportar registros | IF §19 | D (formato PEND) | Exportación .xlsx de 10 registros | K: exportaciones | ✅ |
| GEN-08 | Alertas por panel y correo | IF §2, §14 | D | Panel + `email_outbox` + SMTP | C: correo sin SMTP | ✅ / ⛔ envío real requiere SMTP corporativo |
| GEN-09 | Notificación al celular | IF §2, §14 | — | No implementado | — | 🔜 |
| GEN-10 | No integración directa con SAP en la primera etapa; carga de archivos | IF "Cómo leer" | D | Solo cargas de archivo | C: cargas | ✅ |
| GEN-11 | Configuración por producto, material, proceso, categoría o fase | IF §2 | D | Catálogo de artículos (categoría, mínimo, período, margen, merma, tiempo máx., PCC1), plazos por categoría, fases | K, C: reposición | ✅ |

## Comercial / OV (IF §4, §5)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| OV-01 | Registrar OV | IF §4.1, §5 | D | `svc/orders.create_order`, `/ov/nueva` | F: pedido completo; W: flujo web | ✅ |
| OV-02 | Evaluar al registrar o modificar (los cortes no afectan evaluación ni reserva) | IF §5 | D | `evaluate_order` en creación/modificación/importación | F: cambio de OV | ✅ |
| OV-03 | Prioridad por fecha comprometida, completitud y urgencia | IF §1, §5 | D (orden de desempate P) | `priority_key` + parámetro `orden_prioridad` | F: faltante (reevaluación) | ✅ |
| OV-04 | Asistente modifica con autorización de Coord., Jefe de Ventas o vendedor responsable | IF §5 | D | `request_change` / `resolve_change` | F: asistente | ✅ |
| OV-05 | Renegociar fecha o proponer producto disponible; GO participa | IF §5 | D | `renegotiate_date`, `change_product`, `ov_decisions` | F: renegociar | ✅ |
| OV-06 | Cancelación por Coord./Jefe de Ventas libera reserva y ruta | IF §5 | D | `cancel_order` | F: cancelación | ✅ |
| OV-07 | Campos de OV contrastados con formato real | IF §5 | PEND | Campos de exportación OVS SAP; "Fecha de Vencimiento" = fecha comprometida (K13) | C: importar OV | 🟡 (confirmar Q11) |
| OV-08 | Importar OV desde exportación | IF §18 | D | Carga tipo OV (consolida líneas repetidas, omite cerradas) | C: importar OV; real 194 OV | ✅ |
| OV-09 | Monto y volumen por OV | IF §1, §17 | D | Precio unitario opcional; kg por peso del artículo | F: pedido completo (KPI) | 🟡 (fuente de precio, Q11) |

## Almacén, stock y reservas (IF §6, §22)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| ALM-01 | Estados Disponible, Reservado, No utilizable, Dañado, En fumigación, Pendiente de revisión | IF §2, §6.1, §9.4 | D | `stock_lots.estado` + reservado derivado | C: estados | ✅ |
| ALM-02 | No usar "Observado" | IF §6.1 | D | Rechazado por validación | C: estados | ✅ |
| ALM-03 | 1560 prioridad para PT | IF §6.2 | D | Almacén ALM-001 uso PT | F: varios | ✅ |
| ALM-04 | 1524 materia prima, granel e insumos | IF §6.2; Q5 | D | EXT-002 uso MP_INSUMOS; ALM-003 tránsito de Producción y ALM-010 no utilizado (no reservables) | R: Q5 | ✅ (resto de almacenes, Q5) |
| ALM-05 | Stock alternativo Ext-001/005/010/014 solo como opción; Logística decide; sin traslado automático | IF §6.2 | D | `alternatives_for_order`; traslado solo por solicitud | F: faltante, almacén alternativo | ✅ |
| ALM-06 | Reservar solo stock físico verificado y utilizable | IF §6.3, §22 | D | `lot_usable` (estado, verificado, vencimiento, vida útil del cliente) | F: vencimiento; C: estados | ✅ |
| ALM-07 | Cobertura % unidades y % líneas totalmente cubiertas | IF §6.3, §22 | D | `evaluate_order` | F: faltante | ✅ |
| ALM-08 | Faltante: alerta inmediata a Coord. Almacén, Logística y GO | IF §6.3 | D | Alerta OV_FALTANTE | F: faltante | ✅ |
| ALM-09 | Decidir despacho parcial: alerta a Jefatura Log., GO y Comercial; aprueba GO o Jefatura de Logística | IF §6.3, Q3 | D | OV_DECISION_PARCIAL + `decide_partial` (`parcial_modo` = CUALQUIERA; GG en nombre de) | F: parcial y saldo; F: GG | ✅ |
| ALM-10 | Parcial aprobado: alerta a Distribución y propuesta de ruta | IF §6.3 | D | OV_PARCIAL_APROBADO + `propose_routes` | F: parcial conjunta y saldo | ✅ |
| ALM-18 | Lo que falta despachar se reprograma | Q3 | D | `create_saldo`: OV `<OV>-S1` con la fecha de saldo, al confirmar la salida; alerta OV_SALDO_REPROGRAMADO | F: parcial conjunta y saldo | ✅ |
| ALM-11 | Cambio de OV tras reserva: conservar válidas, recalcular, alertar Log./Alm./GO | IF §6.3 | D | `_apply_changes` + OV_CAMBIO | F: cambio de OV | ✅ |
| ALM-12 | Base inicial y cargas de stock SAP | IF §6.4 | D | Carga STOCK (formato STOCK_LOTE) | C: cargas; real 1 234 lotes | ✅ |
| ALM-13 | Validar formato, duplicados y diferencias antes de confirmar; quien carga corrige y autoriza | IF §6.4 | D | Resumen de diferencias (nuevos, modificados, ausentes, reservas afectadas) | C: carga con errores, reducción | ✅ |
| ALM-14 | Diferencias alertan a Sistemas y son rastreables | IF §6.4 | D | STOCK_CARGA_DIFERENCIAS, INVENTARIO_DIFERENCIA | C: carga; conteo | ✅ |
| ALM-15 | Conteos periódicos y registro de diferencias | IF §6.3-6.4 | D | Conteos (fórmula Inven. bobinas) | C: conteo | ✅ |
| ALM-16 | Respetar lote y vencimiento | IF §22 | D | FEFO (P) + exclusión de vencidos y vida útil | F: vencimiento | ✅ |
| ALM-17 | Preparación por prioridades y horarios de corte | IF §4.9, §16 | D (horarios PEND) | Cola por corte; picking por lote reservado | C: 80 %; F: pedido completo | ✅ (cortes DEMO) |
| ALM-18 | Alerta de pedido al 80 % de preparación | IF §14 | D (destinatarios P) | OV_80_PREPARACION | C: alerta 80 % | ✅ |
| ALM-19 | Stock/movimientos descargados de SAP como historial | IF §6.4, §7 | D | Carga SALIDAS (formato Qy) | C: salidas; real 41 663 líneas | ✅ |

## Reposición y compras (IF §7, §10)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| REP-01 | Plazos por categoría en días naturales, con campaña de canastería nov–dic | IF §7 | D | `lead_times` + excepción estacional | C: reposición | ✅ |
| REP-02 | Margen adicional configurable (valor no fijado) | IF §7, §16 | PEND | Parámetro global y por artículo | C: reposición | ⏸️ |
| REP-03 | Período de análisis por producto/agrupación/insumo | IF §7 | D | Campo por artículo; defecto 15 días (AS) | C: reposición | ✅ |
| REP-04 | Análisis con salidas, consumo, stock, plazo, OV pendientes, reservado, disponible (rotación si hay datos) | IF §7 | D | `analyze_product` | C: reposición | 🟡 (rotación A/B/C no implementada) |
| REP-05 | Alerta, cantidad sugerida, fecha estimada de necesidad, solicitud preliminar | IF §7 | D | `run_replenishment` → borrador + REPOSICION_SUGERIDA | C: reposición | ✅ |
| REP-06 | Umbral de compra de mayor volumen configurable; participación de GO por validar | IF §7, §20 | PEND | Parámetros; aprobación GO si umbral definido | F: compra | ⏸️ |
| REP-07 | Solicitudes nacen en Almacén | IF §7, §10.1 | D | Permiso `compras.solicitar` solo Almacén | F: compra | ✅ |
| COM-01 | Compras cotiza y lleva muestra a Calidad | IF §10.2 | D | `quote` + COMPRA_MUESTRA | F: compra | ✅ |
| COM-02 | Calidad evalúa la muestra | IF §10.3 | D | `evaluate_sample` | F: compra | ✅ |
| COM-03 | Compras genera la orden tras validaciones | IF §10.4 | D | `generate_order` bloquea sin muestra/aprobación | F: compra | ✅ |
| COM-04 | Fecha prevista y alerta a Almacén para programar recepción | IF §10.5-10.6 | D | COMPRA_RECEPCION_PROGRAMAR | F: compra | ✅ |
| COM-05 | Diferencias: Almacén y Calidad validan e informan a Compras | IF §10.7 | D | `receive` + COMPRA_DIFERENCIA; subsanación | F: compra | ✅ |
| COM-06 | GO autoriza recibir bajo observaciones (registro de autorización y observaciones) | IF §10.8 | D (formato PEND) | `authorize_under_observation` | F: compra | ✅ |
| COM-07 | Cambio de fechas alerta a Almacén y GO | IF §10 | D | COMPRA_FECHA_CAMBIO + historial | F: compra | ✅ |
| COM-08 | Margen por proveedor si se aprueba | IF §16 | PEND | No implementado (solo por artículo/global) | — | ⏸️ |

## Producción (IF §8)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| PRD-01 | BOM desde Excel por producto y presentación; cálculo proporcional | IF §8.1 | D | Carga BOM + `material_requirements` | F: producción; real PT-005 | ✅ |
| PRD-02 | Validar estructura, productos, presentaciones, materiales, duplicados, obligatorios | IF §8.1 | D | `_v_bom` | C: BOM (y real: 3 errores detectados) | ✅ |
| PRD-03 | Versión y registro de cambios de la lista | IF §8.1 | D | `bom_versions.cambios` | C: BOM | ✅ |
| PRD-04 | Merma % configurable y apartado para otras reglas | IF §8.1, §16 | D (valor PEND) | Merma material > producto > global; reglas adicionales: no definidas | F: merma | 🟡 (otras reglas sin definición) |
| PRD-05 | Verificar si el Excel ya incluye pérdidas (sin doble conteo) | IF §8.1, §22 | D | Pregunta obligatoria al autorizar cada versión | F: merma no duplicada | ✅ |
| PRD-06 | Solicitud preliminar con producto, cantidad, presentación, disponibilidad MP/granel, materiales, faltantes, OV, fecha | IF §8.2, §22 | D | `create_request` + pantalla | F: producción | ✅ |
| PRD-07 | Almacén revisa y envía; Producción valida lista, disponibilidad real, capacidad y plazo | IF §8.2 | D | `send_request` / `validate_request` | F: producción | ✅ |
| PRD-08 | Ayuda a programación diaria con capacidad y plazos | IF §8.2 | D (capacidades PEND) | Programa semanal por línea; control de capacidad | F: producción | ✅ (capacidades a cargar) |
| PRD-09 | Registrar inicio, fin y liquidación | IF §8.3 | D | `start`, `finish`, `register_liquidation` | F: producción | ✅ |
| PRD-10 | Liquidación desde Excel o SAP | IF §8.3 | D (modelo PEND) | Carga LIQUIDACION (formato Dat.Prod) | C: importar liquidación | ✅ (clave Q9) |
| PRD-11 | Datos de lote alimentan certificados | IF §8.3 | D | `certificate_data` usa liquidación | C: certificado | ✅ |
| PRD-12 | Registrar merma de insumos y granel; cargar desde SAP | IF §8.3 | D | Campos de merma MP/granel/insumos en liquidación (manual) | K: merma | 🟡 (carga SAP de merma: formato no recibido) |
| PRD-13 | Liquidación alerta al montacarguista | IF §8.3 | D | LIQUIDACION_MONTACARGUISTA | F: producción | ✅ |
| PRD-14 | Almacén valida cantidades/presentación y registra diferencias | IF §8.3 | D | `receive_pt` (cruce FALTANTE/COMPLETO/SOBRANTE) | F: producción | ✅ |
| PRD-15 | Excepciones a la proporcionalidad lineal | IF §20 | PEND | No implementado | — | ⏸️ |

## Reempaque y Calidad (IF §9)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| RMP-01 | Almacén inicia, Calidad aprueba/desaprueba, notifica a Almacén y Producción, Producción ejecuta | IF §9.1 | D | `svc/repack.py` | F: reempaque | ✅ |
| RMP-02 | Tres tipos con tiempos orientativos | IF §9.2 | D | Catálogo REPACK_TYPES | F: reempaque | ✅ |
| RMP-03 | Criterios de conversión de calidad, SKU, lote, fecha, disposición | IF §9.2, §20 | PEND | Registro libre del resultado de Calidad | — | ⏸️ |
| CAL-01 | Liberación de productos y revisión de muestras | IF §9.3 | D | `release_lot`, muestreo | C: estados; F: reempaque | ✅ |
| CAL-02 | Validación de materiales de compras e importaciones | IF §9.3 | D | Muestra de compra; formato REG-CAL-005 | F: compra | ✅ |
| CAL-03 | Validación de diseños de bobinas | IF §9.3 | D | Formato DISENO_BOBINA | W: recorrido | ☑️ |
| CAL-04 | Inspección de la carga en el despacho | IF §9.3 | D | Formato INSPECCION_CARGA | W: recorrido | ☑️ |
| CAL-05 | Registro de datos de proceso por el asistente | IF §9.3 | D | Formato PROCESO | W: recorrido | ☑️ |
| CAL-06 | Certificados autogenerados (Calidad + lote + pedido listo); Supervisor/Jefatura revisa y corrige | IF §9.3-9.4 | D | Generación al quedar PREPARADA; revisión con registro de cambios; impresión | F: pedido completo; C: certificado | ✅ |
| CAL-F01 | Ficha de muestreo (REG-CAL-002 / CP-FOR-CAL-10) | Formato | D | Formato MUESTREO + evaluación vs "Calidad superior" | C: certificado | ✅ |
| CAL-F02 | Recepción MP con PCC1 de humedad | REG-HACCP-CAL-002 | D | Formato RECEPCION_MP con evaluación automática | C: PCC1 | ✅ |
| CAL-F03 | Fumigación | REG-BPM-CAL-005 | D | Formato FUMIGACION → estados En fumigación / Pendiente de revisión | C: estados | ✅ |
| CAL-F04 | Producto no conforme | REG-BPM-CAL-013 | D | Formato NO_CONFORME + alerta | W: recorrido | ☑️ |
| CAL-F05 | Quejas del cliente | REG-HACCP-CAL-003 | D | Formato QUEJA | W: recorrido | ☑️ |
| CAL-F06 | No conformidades y acciones correctivas | REG-HACCP-CAL-006 | D | Formato NC_ACCION | W: recorrido | ☑️ |
| CAL-F07 | Control de pesos, rotulado y sellado | REG-CAL-003 | D (50 kg PEND) | Formato CONTROL_PESOS con criterios | C: PCC1 y pesos | ✅ |
| CAL-F08 | Ficha de control de calidad de granos | REG-CAL-014 | D | Formato CONTROL_GRANOS | W: recorrido | ☑️ |
| CAL-F09 | Informe de recepción de importados | REG-CAL-005 | D | Formato RECEPCION_IMPORTADO | W: recorrido | ☑️ |
| CAL-F10 | Control de vehículos | REG-BPM-CAL-011 | D | Formato VEHICULO (Seguridad o Calidad) | W: recorrido | ☑️ |
| CAL-F11 | Adjuntar fotos/evidencias en formatos de Calidad (p.ej. informe 082-2026) | PDF informe | P | No implementado (solo evidencia de entrega) | — | 🟡 pendiente |

## Importaciones (IF §11)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| IMP-01 | Seguimiento por fases configurables (no automatización integral) | IF §11 | D (fases PEND) | Plantilla de fases (DEMO) | F: importación | ⏸️ fases reales |
| IMP-02 | Fechas y recordatorios configurables; alerta de fase fuera de fecha | IF §11 | D | `check_phases` | F: importación | ✅ |
| IMP-03 | Importaciones actualiza fechas y llegada | IF §11 | D | `change_arrival`, `change_phase_date` | F: importación | ✅ |
| IMP-04 | Alertar Almacén y Logística (llegada) y GO (modificaciones) | IF §11 | D | IMPORT_LLEGADA, IMPORT_MODIFICACION | F: importación | ✅ |
| IMP-05 | Recepción con Almacén y Calidad; diferencias al responsable | IF §11 | D | `receive` + IMPORT_DIFERENCIA | F: importación | ✅ |

## Distribución, Seguridad y traslados (IF §12, §13)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| DIS-01 | Priorizar por fecha, pedidos completos y urgencia | IF §12.1 | D | `propose_routes` usa `priority_key` | K: rutas | ✅ |
| DIS-02 | Considerar dirección, fecha, volumen/peso, capacidad, horario y confirmación de cita | IF §12.1, §22 | D | Zona/distrito, peso, capacidad kg, orden por cita, advertencia de cita | K: rutas, cita | ✅ (volumen m³ solo registrado; geocodificación no) |
| DIS-03 | Alertar programación a Distribución, Logística, GO y Comercial | IF §12.1 | D | DIST_PROGRAMACION | F: despacho parcial | ✅ |
| DIS-04 | Propuesta automática de asignación con unidades, conductores, capacidades y disponibilidad | IF §12.1 | D | Asignación propios → terceros → externo; conductor habitual | K: rutas | ✅ |
| DIS-05 | Capacidades de terceros; evaluar contratación externa | IF §12.1 | D | Unidades de terceros; ruta "requiere externo" | K: rutas | ✅ |
| DIS-06 | Reglas de flota y asignación modificables | IF §12.1 | D | Flota editable; zonas por parámetro | W: recorrido | 🟡 (algoritmo fijo, datos configurables) |
| DIS-07 | Verificar cantidades, documentos, carga, vehículo, conductor antes de salir; autoriza el Líder Operativo | IF §12.2; Q16 | D | `confirm_departure` exige 5 controles; permiso del Líder Operativo | R: Q16 | ✅ |
| DIS-08 | Seguridad: ingreso, inspección, autorización de salida, validación vs guía | IF §12.2, §13 | D | `register_security_check` + formato VEHICULO | F: pedido completo | ✅ |
| DIS-09 | Discrepancia carga-guía bloquea la salida; Jefe o Coord. de Logística puede aprobarla mientras se resuelve la guía | IF §12.2; Q8 | D (tolerancia PEND) | GUIA_DISCREPANCIA, `approve_exit_with_discrepancy`, `resolve_guide_discrepancy`, SALIDA_CON_DISCREPANCIA | R: Q8 (2 pruebas) | ✅ |
| DIS-10 | Informar avance de ruta a Comercial, Logística y Distribución | IF §12.3 | D | DIST_AVANCE_RUTA (salida, llegada, entrega) | F: pedido completo | ✅ |
| DIS-11 | Evidencia de entrega: fotografía y guía firmada | IF §12.3, §22 | D | Carga de archivos obligatoria | F: pedido completo | ✅ |
| DIS-12 | Auxiliar de Despacho registra incidencias (incluye falta de conductor) | IF §12.3 | D | `register_incident` | F: rechazo | ✅ |
| DIS-13 | Tipos de incidencia (retraso, ausente, rechazo, parcial, devolución, cancelación, cambio de ruta, vehículo esperando, cliente no retira) | IF §12.3 | D | 12 tipos | F: rechazo, devolución | ✅ |
| DIS-14 | Rechazo por calidad → GG, GO, Logística, Almacén, Comercial | IF §12.3 | D | INC_RECHAZO_CALIDAD | F: rechazo | ✅ |
| DIS-15 | Llegada tarde u otra → GO, Logística, Almacén, Comercial | IF §12.3 | D | INC_GENERAL | F: devolución | ✅ |
| TRS-01 | Jefe o Coordinador de Logística autoriza traslados | IF §6.2, §13; Q13 | D | `authorize` | F: alternativo | ✅ |
| TRS-02 | Coord. Almacén o asistente confirma recepción | IF §6.2, §13 | D | `receive` | F: alternativo | ✅ |
| TRS-03 | Registrar origen, destino, producto, cantidad, autorización, salida, recepción y diferencias | IF §13 | D | Tabla `transfers` | F: traslado con diferencia | ✅ |

## TO-BE L5 Gestión de pedidos y despachos (recibido 11-oct-2026)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| TB-01 | Asistente de ventas carga el consolidado de OV; cambios a OV existentes requieren autorización | TO-BE | D | Carga OV con `ov.importar`; sin `ov.modificar` crea solicitudes de modificación | T: asistente carga consolidado | ✅ |
| TB-02 | OV completa: aviso a Jefe de logística, Jefe de ventas y Coord. almacén | TO-BE | D | Alerta OV_COMPLETA | T: OV completa | ✅ |
| TB-03 | Certificado elaborado antes del picking y aviso al aprobarse | TO-BE | D | Certificados BORRADOR al quedar reservada; CERTIFICADO_LISTO | T: OV completa | ✅ |
| TB-04 | Programación de ruta automática al completar la OV | TO-BE | D | `sync_order_route` (parámetro `programar_ruta_automatica`) | T: OV completa | ✅ |
| TB-05 | Líder de almacén valida o modifica el plan de picking (cambio de lote) | TO-BE | D | `validate_picking_plan`, `reassign_pick_lot`; anula certificado del lote anterior | T: modificar plan | ✅ |
| TB-06 | Ruta asignada: aviso al auxiliar/conductor y al montacarguista | TO-BE | D | RUTA_ASIGNADA, MONTACARGUISTA_DESPACHO | T: carga incongruente | ✅ |
| TB-07 | Fotos: vehículo antes de cargar, inicio de carga (Seguridad), mercadería cargada | TO-BE | D | `despacho.add_photo` por etapa y rol | T: carga incongruente | ✅ |
| TB-08 | Incidencias en carga con foto y hora | TO-BE | D | INCIDENCIA_CARGA + INC_CARGA | T: carga incongruente | ✅ |
| TB-09 | Validar carga vs pedido; incongruencia avisa a Líder y Coord. almacén; camión cargado avisa a Facturación | TO-BE | D | `validate_load`; CARGA_INCONGRUENCIA, CAMION_CARGADO | T: carga incongruente | ✅ |
| TB-10 | Guía de remisión (sistema o SAP con archivo) y pre-guía/folio imprimible | TO-BE | D | `set_guide`, `/distribucion/ruta/<id>/folio` | T, W: ruta y folio | ✅ |
| TB-11 | Facturación carga la factura; indica modificaciones si el pedido va incompleto | TO-BE | D | Rol FACTURACION, `set_invoice` | T: factura con modificaciones | ✅ |
| TB-12 | Seguridad revisa documentos impresos; faltantes avisan a las áreas | TO-BE; Q16 | D | `review_documents`; DOCUMENTOS_FALTANTES; la salida exige la revisión | T: carga incongruente | ✅ |
| TB-13 | Llegada y entrega avisan a Distribución, Logística y GO; rechazo por cita | TO-BE | D | DIST_LLEGADA, DIST_ENTREGADO, incidencia RECHAZO_CITA | T: carga incongruente | ✅ |
| TB-14 | Retorno a base | TO-BE | D | `register_return` | E2E navegador | ☑️ |
| TB-15 | Reempaque: el sistema pre-solicita; el Coordinador de Almacén aprueba y envía a Calidad | TO-BE; Q12 | D | Estado PRE_SOLICITUD, `approve_presolicitud` | R: Q12 | ✅ |
| TB-16 | Traslado aprobado por Jefe o Coordinador de Logística | TO-BE; Q13 | D | `traslado.autorizar` a ambos | F: alternativo; R: Q15 | ✅ |
| TB-17 | Jefe de Logística aprueba la solicitud de compra antes de Compras | TO-BE; Q14 | D | Estado PENDIENTE_LOGISTICA, `approve_logistics` | F: compra; C: reposición | ✅ |
| TB-18 | Pre-solicitudes automáticas en orden producir → reempaque → traslado → compra | TO-BE; Q15 | D | `services/presolicitudes.py` | R: Q15 | ✅ |

## Decisiones del 12-oct-2026 (nuevas)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| D12-01 | Fill rate a la salida: % unidades, % líneas, % pedidos al 100 %, rechazo posterior y motivo | Q2 | D | `kpis.fill_rate`, tablero | R: Q2 | ✅ |
| D12-02 | Ubicar en qué etapa del proceso están los mayores errores | Q2 | D (asignación P) | Tabla por etapa; parámetro `etapa_por_incidencia` | R: Q2 | ✅ |
| D12-03 | PT terminado pasa por el tránsito ALM-003 hasta la validación de Almacén y luego a ALM-001 | Q5 | D | `register_liquidation` / `receive_pt` | F: producción | ✅ |
| D12-04 | Dos coordinadores de almacén (1560 y 1524), cada uno con su almacén | Q17 | D | Rol COORD_ALMACEN_MP; `alcance_almacen_por_rol`; `check_warehouse_scope` | C: conteo; F: compra; R: Q17 | ✅ |
| D12-05 | Alertas de almacén dirigidas al coordinador del almacén involucrado | Q17 | D (derivado) | `alerts._filter_by_warehouse` | R: Q15, Q17; F: compra, importación | ✅ |
| D12-06 | La guía observada se registra como resuelta después de la salida | Q8 | D | `resolve_guide_discrepancy` | R: Q8 | ✅ |

## Alertas (IF §14)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| ALR-01 | Asignar, marcar en atención, comentar y cerrar con responsable, hora, motivo y acción | IF §14, §22 | D | `svc/alerts.py` + historial de eventos | C: ciclo | ✅ |
| ALR-02 | GO ve su ámbito; GG ve todas | IF §14 | D (ámbito PEND) | `can_see` + parámetro de ámbito | C: visibilidad | ✅ |
| ALR-03 | GG agrupa por área/tipo y urgencia | IF §14, §15 | D | `/alertas?agrupar=…` | W: recorrido; C: filtros | ✅ |
| ALR-04 | GG configura cuáles recibe directamente | IF §14 | D | Preferencias GG | K: preferencias; F: rechazo | ✅ |
| ALR-05 | Destinatarios y reglas de correo configurables por alerta, rol y usuario | IF §14 | D | Configurar alertas | W: recorrido | ☑️ |
| ALR-06 | Alertas contempladas (cambios/estados OV, 80 %, faltantes, cobertura, reservas, diferencias, retrasos, cancelaciones, rutas, incidencias, solicitudes, fechas, fumigación, no utilizables, certificados, guías, vehículo esperando, traslados, devoluciones, rechazos, cliente no retira, merma) | IF §14 | D | 62 tipos (ver doc 07) | F/C/K | ✅ |
| ALR-07 | Matriz exacta de destinatarios, prioridad y condición a validar | IF §14, §20 | PEND | Marcados DEFINIDO/PROPUESTO/PENDIENTE | — | ⏸️ |

## Roles, configuración e indicadores (IF §15-§17)

| ID | Requerimiento | Fuente | Tipo | Implementación | Prueba | Estado |
|---|---|---|---|---|---|---|
| ROL-01 | GG acceso a todas las áreas | IF §15 | D | Todos los permisos | C: matriz | ✅ |
| ROL-02 | GO información y acciones de Operaciones | IF §15 | D (detalle P) | Permisos propuestos + aprobaciones definidas | C: matriz | ✅ |
| ROL-03 | Sistemas acceso completo sin aprobar en nombre de otros roles | IF §15, Q4 | D | Todos los permisos salvo los de aprobación | C: matriz; T: Sistemas no aprueba | ✅ |
| ROL-04 | Roles operativos detallados en la matriz (Comercial, Almacén, Distribución, Logística, Producción, Calidad, Compras, Importaciones, Seguridad; Facturación por TO-BE; dos coordinadores de almacén por Q17) | IF §15, TO-BE, Q17 | D (permisos P) | 30 roles (27 operativos + GG, GO, Sistemas) y matriz editable | C: matriz | ✅ |
| ROL-05 | Significado de "acceso completo" y auditoría de acciones críticas | IF §15, Q4 | D | GG aprueba (auditado "en nombre de"); Sistemas no aprueba; parámetro `acceso_completo_omite_aprobaciones` DEFINIDO | T: Sistemas no aprueba | ✅ |
| CFG-01..10 | Márgenes, plazos y estacionalidad, stock mínimo/períodos/umbrales, cortes y tiempos, merma, versiones de BOM, fases, flota, alertas, otras reglas | IF §16 | D | Pantalla Configuración + catálogo + flota + alertas | K: parámetros | ✅ |
| CFG-11 | Reparto de responsabilidades de configuración entre Sistemas y GG | IF §16 | PEND | Ambos con `config.editar` | — | ⏸️ |
| KPI-01 | Pedidos pendientes, completos e incompletos | IF §17 | D | Tablero | F: pedido completo | ✅ |
| KPI-02 | OTIF = salió completo y a tiempo; fill rate con rechazos y causas por etapa | IF §17; Q2 | D (etapas P) | `kpis.fill_rate`; tablero | R: Q2 | ✅ |
| KPI-03 | Faltantes y cobertura por unidades y líneas | IF §17 | D | Tablero | W: recorrido | ☑️ |
| KPI-04 | Pedidos detenidos y motivo | IF §17 | D | Tablero | W: recorrido | ☑️ |
| KPI-05 | Tiempos de preparación y despacho | IF §17 | D | Tablero | W: recorrido | ☑️ |
| KPI-06 | Compras y producción pendientes | IF §17 | D | Tablero | W | ☑️ |
| KPI-07 | Diferencias de inventario | IF §17 | D | Tablero (conteos y recepción de PT) | W | ☑️ |
| KPI-08 | Incidencias, rechazos, devoluciones, entregas parciales | IF §17 | D | Tablero | F: devolución | ☑️ |
| KPI-09 | Merma prevista vs real | IF §17 | D (si hay datos) | Tablero | K: merma | ☑️ |
| KPI-10 | Monto y volumen de las OV | IF §17 | D | Tablero | F | 🟡 (precios, Q11) |
| KPI-11 | Filtrar por área, estado y urgencia | IF §22 | D | Filtros de alertas, OV y fecha en tablero | W | ✅ |

## Resumen

Ver `05_ESTADO_FUNCIONALIDADES.md` para el conteo por estado y la lista de pendientes y bloqueos.
