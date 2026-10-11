# Análisis del TO-BE "COPROD-ONE" y decisiones del 11-oct-2026

Fuente: `TO-BE-COPROD-ONE.drawio.zip` → `TO-BE-COPROD-ONE.drawio.png` (3 913 × 4 584 px). El PNG contiene el modelo
draw.io embebido; se decodificó completo: **1 página "L5 – SUBPROCESO Gestión de Pedidos y Despachos", 15 carriles,
298 elementos y 139 conexiones**. El original no se modificó ni se incluye en el repositorio.

Carriles: Comercial · **SISTEMA "Coprod-One"** · Líder Operativo · Distribución · Auxiliar de despacho · Seguridad ·
Cliente · Coordinador de almacén (Kevin) · Producción · Calidad · Coordinador de almacén (Gaiden) · Logística · Compras ·
**Facturación**.

## 1. Decisiones del usuario aplicadas

| Decisión | Texto | Implementación | Prueba |
|---|---|---|---|
| **Q3** | "Aprobación bajo gerencia de operaciones y jefe de logística. Lo que falta despachar se reprograma para algún día despachar lo faltante." | El despacho parcial requiere la aprobación de **ambos** (Gerencia de Operaciones y Jefatura de Logística; parámetro `parcial_aprobadores`). Comercial ya no aprueba (sigue recibiendo la alerta). Cualquiera de los dos puede rechazar con motivo. El primer aprobador fija la **fecha de reprogramación del saldo** (obligatoria). Al confirmar la salida del parcial se crea automáticamente la **OV de saldo** `<OV>-S1` con lo no despachado, la fecha reprogramada, evaluación de stock y alerta `OV_SALDO_REPROGRAMADO`. | `test_despacho_parcial_aprobacion_conjunta_y_saldo`, `test_gerencia_general_aprueba_en_nombre_y_rechazo` |
| **Q4** | "Acceso completo para gerencia general; Sistemas … puede tener acceso pero no puede aprobar." | Gerencia General conserva todos los permisos y puede aprobar **en nombre de** los roles pendientes (queda registrado "en nombre de"). Sistemas conserva consulta, edición y administración, pero se le retiraron **los 15 permisos de tipo aprobación** (cancelar/autorizar OV, despacho parcial, alternativas, autorizar cargas, traslados, reempaque, validar producción, liberar, certificados, muestras, compras de mayor volumen, recepción bajo observación, confirmar y autorizar salida). Las cargas de demostración ahora las autoriza el rol responsable. | `test_sistemas_no_aprueba_gerencia_general_si`, `test_matriz_permisos_reglas_documentadas` |

Interpretación a confirmar: en Q3 se entendió "GO **y** Jefe de Logística" como aprobación **conjunta** (ambos). Si basta
uno de los dos, se cambia el parámetro `parcial_aprobadores` (sin programar).

## 2. Actividades del TO-BE y su implementación

Estado: ✅ implementado y probado · ☑️ implementado (verificado en pantalla) · ◻️ fuera del sistema (acción en SAP/correo/cliente, se registra su resultado) · ❓ requiere decisión (contradice el Informe Funcional).

### Comercial
| Actividad TO-BE | Implementación | Estado |
|---|---|---|
| Asistente comercial ingresa la OV en SAP (por canal) | Fuera del sistema (SAP) | ◻️ |
| Subir evidencia por correo de la OV ingresada | Fuera del sistema (correo) | ◻️ |
| Cargar consolidado de OV emitidas, originales y cambios al módulo | Carga OVS: el Asistente ahora tiene `ov.importar`; crea OV nuevas y los **cambios a OV existentes quedan como solicitudes que autorizan Coord./Jefe de Ventas o vendedor responsable** (IF §5) | ✅ `test_asistente_carga_consolidado_cambios_requieren_autorizacion` |

### Sistema "Coprod-One"
| Actividad TO-BE | Implementación | Estado |
|---|---|---|
| Analizar información, cruzar con base de datos, reservar stock | `evaluate_order` (FEFO, verificado, vencimiento, vida útil) | ✅ |
| ¿OV completa? SÍ → Avisar (Jefe de logística, Jefe comercial, coordinador almacén) | Alerta `OV_COMPLETA` | ✅ |
| Programar automáticamente la mejor ruta para el despacho | `sync_order_route`: al quedar completa (o con parcial aprobado) se agrega a la ruta propuesta de la misma fecha y zona si hay capacidad, o se crea una nueva; si la OV deja de estar completa sale de la ruta propuesta | ✅ `test_ruta_automatica_capacidad_y_externo` |
| Informar a Calidad para validar el certificado pre-elaborado | Certificados generados al quedar la OV completa (antes del picking); alerta `CERTIFICADO_REVISION`; se anulan si cambia el lote | ✅ `test_ov_completa_avisa_certifica_y_programa_ruta` |
| Pre-asignar picking | Los lotes reservados constituyen el plan de picking | ✅ |
| ¿OV completa? NO → Analizar las opciones viables (producción, reempaque, traslado, compra) | `alternatives_for_order` presenta las 4 opciones con su viabilidad | ✅ |
| Generar pre-solicitud de producción con info de la OV y materiales | Solicitud preliminar con análisis de materiales (se crea con un clic desde la alternativa) | ☑️ / ❓ Q15 (generación automática) |
| Analizar stock existente y remitir solicitud de reempaque a Calidad | Hoy la inicia Almacén con un clic (IF §9.1) | ❓ Q12 |
| Generar pre-solicitud de traslado indicando SKU | Solicitud de traslado desde la alternativa; la cantidad queda comprometida | ☑️ / ❓ Q13 (aprobador) |
| Generar pre-solicitud de OC | Solicitud de compra desde la alternativa | ☑️ / ❓ Q14 (aprobación de Logística) |

### Líder Operativo y montacarguista
| Actividad TO-BE | Implementación | Estado |
|---|---|---|
| Validación del plan de picking (SÍ → ejecutar; NO → modificar planificación) | "Validar planificación" obligatorio antes del picking; "Cambiar lote" por otro apto | ✅ `test_modificar_plan_de_picking_cambia_lote`, `test_alerta_80_por_ciento` |
| Ejecutar picking e ingresar el término | Picking por lote; al 100 % la OV queda PREPARADA | ✅ |
| Generar alerta (comercial, GO, jefe de logística) y documentos para calidad y distribución | `OV_PREPARADA` con esos destinatarios + Calidad y Distribución | ✅ |
| Alerta para el traslado del montacarguista / traslado a despacho | `MONTACARGUISTA_DESPACHO` al aprobar la ruta | ✅ |
| Cambiar producto observado o regresar sobrante; retornar al despacho | Respuesta a `CARGA_INCONGRUENCIA`; se vuelve a validar la carga | ✅ |

### Distribución
| Actividad TO-BE | Implementación | Estado |
|---|---|---|
| ¿Aprobación de ruta? NO → modificar ruta | Ajustar unidad/conductor, mover paradas, confirmar | ✅ |
| Alerta al chofer y auxiliar de las rutas asignadas | `RUTA_ASIGNADA` (rol Auxiliar de despacho, Conductor y usuario del conductor) | ✅ |
| Notificar a todas las áreas (calidad, comercial, GO, jefe de logística) | `DIST_PROGRAMACION` (ahora incluye Calidad) | ✅ |
| Generar guía en SAP y cargarla, o generar guía en el sistema | Por pedido: guía del sistema (número automático, imprimible) o guía SAP con archivo | ✅ |
| Imprimir folio de documentos del pedido | Página imprimible de pre-guía/guía y folio (guía, factura, certificados) | ☑️ |

### Auxiliar de despacho, chofer y Seguridad
| Actividad TO-BE | Implementación | Estado |
|---|---|---|
| Foto del vehículo antes de la estiba | Obligatoria antes de validar la carga | ✅ |
| Generar pre-guía / Seguridad visualiza la pre-guía | Pre-guía imprimible con lotes, FP y FV | ☑️ |
| Seguridad: seguimiento y foto del inicio de carga | Foto por etapa (solo Seguridad) | ✅ |
| Seguridad: ¿incidencia? → foto, motivo y hora | `INCIDENCIA_CARGA` + alerta `INC_CARGA` | ✅ |
| Validar mercadería: ¿productos correctos o completos? NO → avisar al almacenero (validación cruzada) | `validate_load` + alerta `CARGA_INCONGRUENCIA` a Líder y Coordinación de Almacén | ✅ |
| Validar carga completa y correcta con foto de mercadería cargada (auxiliar y chofer) | Foto obligatoria; permiso también para Conductor | ✅ |
| Alerta de camión cargado (comercial, GO, jefe de logística, distribución, facturación) | `CAMION_CARGADO` | ✅ |
| Recibir folio de documentos impresos | Confirmación "documentos impresos" en la autorización de Seguridad | ✅ |
| Seguridad: ¿documentos completos? NO → reportar faltantes (distribución, facturación, calidad, JL, GO) | `missing_documents` (guía, factura, certificado aprobado; parámetro `documentos_salida`) + `DOCUMENTOS_FALTANTES` | ✅ |
| Seguridad: validar documentación y autorizar la salida | `authorize_exit`; sin ella no hay salida | ✅ |
| Salir a ruta (chofer) | Confirmación de salida (además del checklist del IF §12.2) | ✅ |
| Notificar llegada al punto de entrega (coord. distribución, JL, GO) | `DIST_LLEGADA` | ✅ |
| Rechazo por cita fuera de hora → reportar rechazo y motivo → notificar | Incidencia `RECHAZO_CITA` (parada no entregada, mercadería retorna a revisión) | ✅ |
| Desestibar; cliente valida transporte, certificados y mercadería | Acciones del cliente; se registra su resultado (entrega o incidencia) | ◻️ |
| ¿Incidencia? SÍ → reportar devolución y motivo → notificar | Incidencia `DEVOLUCION` | ✅ |
| Cliente firma conformidad → reportar entrega con foto y guía firmada → notificar (coord., JL, GO, comercial) | `register_delivery` (evidencias obligatorias) + `DIST_ENTREGADO` | ✅ |
| Detección de particularidad en la misma descarga | Incidencia `PARTICULARIDAD_DESCARGA` (también sobre rutas cerradas) | ✅ |
| Retornar a base (chofer) | "Registrar retorno a base" | ✅ |

### Coordinadores de almacén, Producción, Calidad, Logística, Compras, Facturación
| Actividad TO-BE | Implementación | Estado |
|---|---|---|
| Coord. almacén (Kevin) evalúa la pre-solicitud de producción y la aprueba | Revisar y "Enviar a Producción" (`produccion.solicitud`) | ✅ |
| Producción confirma lista de materiales; NO → solicita corrección al coord. almacén | Validación con 4 controles; rechazo con motivo vuelve a Almacén | ✅ |
| Producción programa la producción y la fecha de entrega del PT | Programación por línea y fecha | ✅ |
| Liquidar en SAP y subir al sistema; alerta al montacarguista | Carga de liquidación + `LIQUIDACION_MONTACARGUISTA` | ✅ |
| Calidad evalúa reempaque; NO → se desestima y se libera el stock comprometido | Desaprobación libera la cantidad retenida | ✅ |
| Calidad: SÍ → notifica a almacén y producción para programar el reempaque | `REEMPAQUE_APROBADO` | ✅ |
| Calidad evalúa el certificado pre-elaborado; NO → modificar manualmente | Revisión con correcciones registradas | ✅ |
| Calidad notifica a distribución, GO y JL que el certificado fue cargado | `CERTIFICADO_LISTO` | ✅ |
| Coord. almacén (Gaiden) aprueba el traslado; NO → se desestima y libera stock comprometido | Hoy autoriza la Jefatura de Logística (IF §6.2) | ❓ Q13 |
| Logística aprueba la pre-solicitud de OC → genera solicitud de compra | Hoy la solicitud nace en Almacén y va directo a Compras (IF §10) | ❓ Q14 |
| Compras ingresa la OC en SAP → subproceso 7.1 Gestionar compra | Flujo de compras del módulo (OC registrada) | ✅ |
| Facturación evalúa el pedido validado: ¿completo según la OV? → factura (con modificaciones si no) → cargar al sistema | Rol **Facturación** nuevo; carga de factura por pedido con detección automática de diferencias contra la OV | ✅ `test_factura_con_modificaciones_si_incompleto` |

## 3. Diferencias entre el TO-BE y el Informe Funcional que requieren su decisión

| # | Tema | Informe Funcional | TO-BE | Comportamiento actual |
|---|---|---|---|---|
| Q12 | Origen del reempaque | Almacén inicia la solicitud (§9.1) | El sistema analiza el stock y remite la solicitud a Calidad | Almacén la inicia con un clic desde las alternativas |
| Q13 | Aprobación del traslado | Jefatura de Logística autoriza (§6.2, §13) | Coordinador de almacén (Gaiden) aprueba | Jefatura de Logística (la matriz de permisos permite cambiarlo sin programar) |
| Q14 | Aprobación de la compra | Almacén origina; Compras cotiza (§7, §10) | El sistema genera la pre-solicitud y Logística la aprueba antes de Compras | Sin aprobación de Logística |
| Q15 | Pre-solicitudes automáticas | "El sistema realiza el análisis preliminar; Almacén revisa y envía" (§8.2) | El sistema genera la pre-solicitud de la opción viable | Las alternativas se presentan y una persona elige; ¿qué genera el sistema si hay varias opciones viables (orden de preferencia)? |
| Q16 | Quién autoriza la salida | Coordinador de Distribución confirma (§12.2) | Seguridad autoriza la salida al camión | Se exigen ambas (Seguridad autoriza; el Coordinador confirma con el checklist) |
| Q17 | Coordinadores "Kevin" y "Gaiden" | Un rol "Coordinación de Almacén" | Dos carriles distintos | Un solo rol; ¿son dos roles (p.ej. planta y almacenes externos)? |
