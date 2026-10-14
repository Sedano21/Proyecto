# Diagnóstico y plan – Especificación funcional maestra (14-oct-2026)

Etapa 1 de la especificación: inspección del código y la documentación existentes (v0.6, 146 pruebas), matriz de
correspondencia, contradicciones, dependencias, datos pendientes y plan por etapas. **No se modificó código en esta
etapa.** Las etapas 2 a 7 esperan su autorización (§6).

Leyenda: ✅ operativa · ⚠️ existe pero incompleta · ❌ pendiente · 🔒 depende de una decisión o integración.

## 1. Matriz de correspondencia

### §4 Pedidos y planificación de la demanda

| Requisito | Estado | Lo que existe hoy (código) | Brecha |
|---|---|---|---|
| Incorporar el pedido a la planificación aunque falten más de 7 días | ⚠️ | La OV se registra y se evalúa al crearla; fuera de la ventana queda **DIFERIDA** con cobertura proyectada sobre stock libre y alerta de faltante proyectado (`stock._evaluate_deferred`, decisión del 14-oct). | No hay una **vista de planificación de demanda por fecha** (pedido × producto × día) que reúna producción, compras y traslados previstos. |
| Ventana de reserva de PT configurable con historial | ✅ | `plazo_max_reserva_dias` = 7 en Configuración, con historial de valores (`ParamHistory`); activación diaria (`activate_deferred`). | El historial de parámetros **no guarda el motivo** del cambio (§16). |
| Distinguir existencia física / comprometida / disponible / en tránsito | ⚠️ | Física = `StockLot.cantidad`; comprometida = reservas activas; disponible = `free_qty`; almacén virtual de tránsito de producción (ALM-003). | Los **traslados en tránsito** no aparecen como stock: al registrar la salida se descuenta del origen y no existe un saldo «en tránsito» consultable (§11.5). |
| Clasificación grande / mediano / pequeño | 🔒 | Solo existen los tiempos de preparación AS-IS por tamaño (`tiempos_preparacion`). Los **umbrales** para clasificar (`umbrales_tamano_pedido_kg`) están **sin definir** desde el inicio. | La especificación dice que la clasificación «ya existe en el sistema»: **no existe con criterios**. Ver C4. |
| §4.2 Impacto de cambios de pedido | ⚠️ | Al modificar una OV se reevalúa: reservas, faltantes, pre-solicitudes, ruta, certificado; alerta `OV_CAMBIO`; auditoría con antes/después. | No se muestra en un solo lugar el **impacto** sobre programación de producción, compras/traslados pendientes, picking y distribución. |

### §5 Inventario, abastecimiento y stock de reserva

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| §5.1 Proyección por artículo **y fecha** | ⚠️ | `purchasing.analyze_product`: consumo diario, disponible, reservado, faltante de OV, compras en camino, stock mínimo, fecha de necesidad. | Las compras en camino se suman **sin su fecha de llegada** (una compra que llega después de la necesidad se cuenta antes: contradice §5.1). No incluye producción ni traslados previstos con fecha. No hay serie diaria proyectada. |
| Stock de reserva por artículo | ⚠️ | `Product.stock_minimo` por artículo; stock de seguridad global opcional (`usar_stock_seguridad`, `factor_stock_seguridad`). | Falta confirmar si «stock de reserva» = `stock_minimo` (C3). |
| §5.2 Plazos (compra 5 d, traslado 2 d, producción 1–2 d, reempaque 2–3 d) | ⚠️ | Plazos de compra por familia (bobinas 25–30, GR/MP 5–7, harinas 7–10…). | No hay plazos configurados para **traslado, producción y reempaque**; no se distingue días calendario/laborables (no hay calendario laboral ni feriados). |
| §5.3 Alertas de reserva, desabastecimiento, abastecimiento tardío, riesgo de producción y de pedido | ⚠️ | `REPOSICION_SUGERIDA`, `OV_FALTANTE`, faltante proyectado, presolicitudes automáticas, alertas de fases de importación. | Sin «abastecimiento tardío» (llegada > necesidad), sin riesgo de material para producción programada; la alerta no muestra responsable, fecha límite ni proceso afectado en campos propios. |
| No duplicar notificaciones | ✅ | `alerts.emit` con `dedup_key`: actualiza la alerta abierta y deja evento «ACTUALIZADA». | — |

### §6 Rutas para atender un pedido

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Rutas A–E y recomendación | ⚠️ | `alternatives_for_order`: lotes en otros almacenes (traslado), reempaque, producción (con BOM), compra; pre-solicitudes automáticas en orden configurable (`orden_presolicitudes`). | No calcula **fecha estimada** de cada ruta (plazo) ni compara contra la fecha comprometida; no hay alerta de **riesgo de incumplimiento** cuando ninguna ruta llega a tiempo. |
| No asignar las mismas unidades dos veces | ⚠️ | Reservas con `free_qty`; traslados descuentan lo pendiente (`transferable_qty`). | **Sin bloqueo de concurrencia** (no hay `SELECT … FOR UPDATE`): dos usuarios simultáneos podrían reservar el mismo saldo en PostgreSQL (C12). Falta prueba de doble asignación concurrente. |

### §7 Planificación de producción

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Calendario por día y línea + necesidades futuras | ⚠️ | Programa de solicitudes por línea y día (`prod_list`), carga por línea en kg (`line_load_kg`), plan diario/semanal/mensual (`ProductionPlan`). | Dos objetos de planificación separados (solicitudes programadas y plan manual) (C11); sin proyección de necesidades futuras desde OV; `capacidad_kg_dia` de las líneas **vacía** (sin dato). |
| Distinguir fecha límite de materiales / inicio / término / despacho | ⚠️ | `fecha_requerida`, `fecha_programada`, `inicio_ts`, `fin_ts`, fecha de la OV. | No existe «fecha límite de materiales» ni fecha prevista de término. |
| §7.1 Ventana protegida 2–3 días laborables | ❌ 🔒 | — | Es una **propuesta por validar** (la especificación lo indica). |

### §8 Producción real y rendimiento

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Liquidaciones vinculadas al plan | ⚠️ | Liquidación (carga SAP/Excel o manual) ligada a la solicitud; plan vs liquidado y tasa de cumplimiento; partes con rendimiento y desmedro por línea; turno en el parte. | La liquidación SAP no trae línea, turno ni configuración; el vínculo parte↔liquidación es por número de OF. |
| §8.2 Estándar por producto / presentación / línea / configuración; «Sin estándar validado» | ❌ 🔒 | No existe el concepto de **configuración** ni tabla de estándares. | Requiere definir qué es «configuración» (C10) y cargar estándares validados. |
| §8.3 Informe (desviación absoluta, cumplimiento, rendimiento vs estándar, utilización, causas) | ⚠️ | Informe de producción: kg por día, plan vs real, rendimiento/desmedro por línea, merma proyectada vs ejecutada. | Sin desviación absoluta explícita, sin rendimiento vs estándar, sin utilización (no hay capacidad), sin causas registradas («Causa no registrada»). |

### §9 Picking

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Programar picking según tamaño (G: 2 días antes; M/P: 1 día antes) | ❌ 🔒 | Preparación por prioridad y cortes horarios; avance por línea; alerta al 80 %. | Sin fecha de picking programada; depende de la clasificación por tamaño (C4). |
| Distinguir reserva → picking → traslado a zona de despacho → validación → salida → descuento | ⚠️ | Reserva, preparación (inicio/fin), validación de carga, vistos buenos, salida, entrega con evidencia. | No existe el evento **«trasladado a zona de despacho»** ni la ubicación «Zona de despacho»; el **descuento de inventario ocurre al confirmar la salida** (C1). |

### §10 Distribución y salida de vehículos

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Plan aprobado por el coordinador como referencia | ⚠️ | Ruta propuesta por el sistema → **confirmada** (`confirm_route`), quién y cuándo en auditoría. | El permiso para confirmar (`distribucion.programar`) lo tiene también el **Asistente de Distribución** (propuesto) (C5). La ruta **no tiene hora planificada de salida** ni versiones del plan. |
| Regla 10:00 a. m. y entrega nocturna | ❌ | — | Nueva. Sin campo de excepción nocturna ligado al pedido. |
| Hora real de salida | ✅ | `Route.salida_ts` al confirmar la salida (Líder Operativo + vistos buenos). | — |
| §10.3 Alertas (sin plan, no listo, conflicto con 10:00, salida tarde, plan modificado…) | ❌ | Alertas de programación, tráfico y validación de externo. | Ninguna de las alertas de horario existe. |
| §10.4 Historial de versiones del plan | ❌ | Auditoría de ajustes. | Sin versión del plan ni re-aprobación. |
| Integración con «el sistema de distribución existente» | 🔒 | La programación de rutas está **dentro de este módulo**; no hay un sistema de distribución externo integrado (C6). | Confirmar si existe otro sistema. |

### §11 Traslados, montacargas y recepción

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| §11.1 Tareas de montacargas desde necesidades reales | ⚠️ | Solo **alertas** al montacarguista (liquidación → mover PT; ruta confirmada → llevar a despacho). | No hay tarea con origen/destino/cantidad/estado (C8). |
| §11.2 Ubicaciones generales configurables | ⚠️ | Almacenes (SAP) y almacenes virtuales. | No hay ubicaciones internas («Producción», «Zona de despacho»). |
| §11.4 Foto de origen y destino obligatorias | ⚠️ | Fotos por etapa de la **ruta** (carga, salida, etc.) y de la entrega. | No hay fotos por tarea de montacargas. |
| §11.5 Recepción por el almacén receptor, enviado vs recibido, diferencias | ⚠️ | Traslado: solicitud → autorización → salida (descuenta origen) → **recepción por el Coordinador de Almacén destino** con cantidad recibida, diferencia y alerta `TRASLADO_DIFERENCIA`; solo lo recibido entra al destino. | Recepción física y aceptación son el mismo acto; no hay estado «recibido pendiente de validación»; la diferencia no queda como incidencia pendiente de resolución; no hay anulación/reversión. Cómo registra SAP el tránsito: **sin verificar** (C7). |

### §12 Salidas de inventario y guías

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Descuento vinculado a la guía (módulo o SAP) | ❌ 🔒 | La guía (número, origen SAP/SISTEMA, archivo) se registra por parada como **documento**; el descuento ocurre al confirmar la salida (`consume_order`), independiente de la guía. Cada carga de stock SAP **reemplaza** las cantidades. | Ver C1: falta definir el punto autorizado de contabilización. El módulo **no puede consultar SAP** (solo recibe exportaciones Excel). |
| Validar guía (cantidades, duplicidad, estado) | ⚠️ | Seguridad valida carga vs guía (líneas y cantidades) y bloquea la salida con discrepancias (aprobación de Logística). | No se verifica **número de guía duplicado**; la guía no guarda sus cantidades propias; no hay registro de «procesada» que impida un segundo proceso. |

### §13–§14 Motor de tareas y alertas

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Motor común de tareas (Pendiente/En ejecución/Completada/Incidencia, cancelación con motivo, idempotencia, vista del responsable) | ❌ | Las «solicitudes» de cada proceso tienen su propio flujo (compras, traslados, reempaques, producción) y existe un **centro de alertas** (Nueva/Asignada/En atención/Cerrada, comentarios, historial, agrupación). | No hay entidad tarea común ni bandeja «mis tareas de hoy / futuras / completadas». |
| Catálogo §14 | ⚠️ | 76 tipos configurables (roles, prioridad, correo). | Faltan: stock de reserva por proyección, abastecimiento tardío, producción pendiente, desviación vs estándar, picking próximo/atrasado, recepción pendiente, riesgo de salida, plan pendiente, salida fuera de horario, guía con discrepancia (como alerta), posible movimiento duplicado. Falta distinguir **riesgo / incumplimiento / discrepancia** y escalamiento. |

### §15–§18 Informes, configuración, permisos y técnica

| Requisito | Estado | Hoy | Brecha |
|---|---|---|---|
| Centro de informes | ⚠️ | Informes Comercial, Reempaque, Producción, Distribución; tablero con OTIF y fill rate; exportación de 10 entidades. | Sin informes de inventario/abastecimiento, pedidos/despacho y tareas; sin vistas guardadas ni catálogo de indicadores con fórmulas; algunos valores ausentes se muestran como 0 o «-» en lugar de «No disponible». |
| Panel de configuración con historial | ⚠️ | Parámetros con estado (DEFINIDO/PROPUESTO/PENDIENTE), fuente e historial de valores. | El historial **no registra el motivo** del cambio. |
| Permisos verificados en servidor | ✅ | `perm_required` en vistas y `has_perm` en servicios; permisos exclusivos; alcance por almacén. | Revisar C5. |
| Concurrencia e integridad | ⚠️ | Transacción por acción con rollback ante error; auditoría. | Sin bloqueo de filas en reservas/movimientos (C12); sin claves de idempotencia por evento. |

## 2. Contradicciones y vacíos que necesitan su decisión

- **C1 – Punto de descuento de inventario (crítico).** Hoy el módulo descuenta el stock al confirmar la salida del camión, y cada carga del stock SAP reemplaza las cantidades. Si la foto de SAP es anterior a la contabilización de la guía en SAP, el stock descontado «reaparece» hasta la siguiente carga. La especificación pide vincular el descuento a la guía y al estado de contabilización en SAP, pero **el módulo no tiene acceso a SAP** (solo recibe Excel). Opciones: (a) mantener el descuento provisional a la salida y marcarlo «pendiente de contabilizar en SAP» hasta que una carga de SAP lo confirme; (b) no descontar en el módulo y esperar siempre la carga de SAP; (c) integrar consulta a SAP (requiere acceso técnico).
- **C3 – «Stock de reserva».** ¿Es el `stock mínimo` por artículo que ya existe, o un concepto distinto?
- **C4 – Clasificación de pedidos.** La especificación dice que la clasificación grande/mediano/pequeño ya existe; en el sistema y en los documentos solo hay tiempos de preparación por tamaño, **sin criterio** (kg, unidades, líneas o monto). Necesito el criterio y los límites.
- **C5 – Aprobación del plan de distribución.** La especificación asigna la aprobación al Coordinador de Distribución; hoy también puede confirmar rutas el Asistente de Distribución (permiso propuesto). ¿Se retira al asistente?
- **C6 – «Sistema de distribución existente».** La programación de rutas está dentro de este módulo. ¿Hay otro sistema de distribución con el que integrarse? Si lo hay, necesito su documentación o acceso.
- **C7 – Tránsito en SAP.** ¿Cómo registra SAP un traslado entre almacenes (descuenta el origen al enviar o al recibir; usa un almacén de tránsito)? Sin esto no puedo garantizar que el saldo del módulo cuadre con la siguiente carga de SAP.
- **C8 – Montacargas.** ¿Cuántos montacarguistas usarán el módulo y con qué dispositivo (celular/tablet) para tomar las fotos?
- **C10 – «Configuración» de línea.** ¿Qué es la configuración (máquina, formato, velocidad, presentación)? ¿Existen estándares de rendimiento validados por producto/línea/configuración? Si no existen, el informe mostrará «Sin estándar validado».
- **C11 – Dos planificaciones de producción.** Se propone unificar en un calendario: las solicitudes programadas (OV) y el plan manual se mostrarán juntos por día y línea, sin borrar ninguno.
- **C12 – Concurrencia.** En producción (PostgreSQL) se agregará bloqueo de filas en reservas y movimientos; es un cambio técnico sin efecto funcional.
- **Plazos de referencia (§5.2).** Traslado 2 días, producción 1–2, reempaque 2–3: ¿los registro como parámetros PROPUESTOS? ¿Días calendario o laborables? ¿Hay calendario de feriados?
- **Hora límite 10:00 y entrega nocturna.** ¿Quién autoriza la excepción nocturna (Coordinador de Distribución, Jefe Comercial)? ¿La salida «a tiempo» tiene tolerancia?
- **Capacidad de líneas.** Sin capacidad (kg/día o unidades/hora) por línea no se puede calcular la utilización.

## 3. Dependencias técnicas

- **SAP:** solo exportaciones Excel (stock, OV, liquidaciones, salidas, maestros). No hay API; la «verificación del estado de contabilización» (§12) no es posible sin acceso.
- **Distribución:** módulo propio; Google Maps opcional para tiempos/tráfico.
- **Almacenamiento de fotos:** carpeta del servidor con control de acceso por sesión y depuración por retención (ya existe para entregas y rutas); se reutiliza para montacargas.
- **Notificaciones:** dentro del sistema (sin correo, decisión anterior).

## 4. Plan de implementación propuesto (incremental, sin reconstruir)

| Etapa | Contenido | Cambios estructurales | Depende de |
|---|---|---|---|
| 2. Inventario, pedidos y abastecimiento | Proyección diaria por artículo con entradas fechadas (compras, traslados, producción programada) y salidas (OV por fecha); stock de reserva; alertas de reserva, abastecimiento tardío y riesgo de pedido con responsable/fecha límite; fecha estimada por ruta A–E y alerta de incumplimiento; bloqueo de concurrencia en reservas; vista de planificación de demanda. | Tablas: plazo por tipo de ruta (parámetros); campos en alertas (nivel riesgo/incumplimiento/discrepancia, responsable, fecha límite). | C3, plazos §5.2 |
| 3. Producción | Calendario único por día y línea; fechas límite de materiales/inicio/término; estándares por producto/presentación/línea/configuración; informe con desviación absoluta, cumplimiento, rendimiento vs estándar, «Sin estándar validado», causas registradas. | Tabla de estándares; campo de causa en parte/liquidación. | C10, capacidad |
| 4. Picking y distribución | Fecha de picking por tamaño; evento «en zona de despacho»; hora planificada y versiones aprobadas del plan; regla 10:00 y excepción nocturna; alertas preventivas y de incumplimiento. | Campos en ruta (hora planificada, versión), tabla de versiones del plan, excepción nocturna en OV. | C4, C5, C6 |
| 5. Traslados y montacargas | Motor común de tareas (estados, cancelación con motivo, idempotencia, bandeja del responsable); ubicaciones generales; fotos de origen y destino obligatorias; recepción en dos pasos (llegada física → aceptación) con stock en tránsito visible y diferencia como incidencia. | Tablas: tareas, ubicaciones, evidencias de tarea; estados nuevos de traslado. | C7, C8 |
| 6. Guías y salidas | Registro de guía con cantidades, unicidad y estado «procesada»; vínculo guía ↔ movimiento; estado de contabilización según la opción elegida en C1; prevención de doble descuento y reversión controlada. | Tablas: movimientos de inventario y guías. | **C1** |
| 7. Informes, configuración y pruebas | Informes de inventario/abastecimiento, pedidos/despacho y tareas; catálogo de indicadores; vistas guardadas; «No disponible» con dato faltante; motivo en cambios de parámetros; las 30 pruebas de aceptación + regresión. | Tablas: vistas guardadas, catálogo de indicadores. | — |

Orden sugerido: 2 → 5 (motor de tareas, que usan 3, 4 y 6) → 4 → 3 → 6 → 7. Cada etapa se entrega con sus pruebas
de aceptación (§20) y sin romper las 146 pruebas existentes.

## 5. Riesgos

- **Doble descuento o stock que reaparece** mientras no se resuelva C1.
- **Reservas simultáneas** sin bloqueo de filas en PostgreSQL (C12).
- **Indicadores engañosos** si se calculan con capacidades o estándares inexistentes: se mostrarán como «No disponible».
- **Carga operativa** de tomar dos fotos por movimiento de montacargas: validar con Almacén antes de exigirlo en todas las tareas.

## 6. Autorización solicitada

Según la sección 3 de la especificación, espero su autorización para iniciar las etapas 2 a 7 con este plan, y sus
respuestas a C1, C3–C8, C10 y a los puntos de plazos, hora 10:00 y capacidad. Las etapas que no dependen de una
respuesta (2 sin C3, 5 sin C7/C8, 7) pueden empezar apenas lo autorice.
