# Ronda V12 (29-oct-2026): Producción y Distribución

Indicaciones del 29-oct-2026 y dos archivos de la empresa:
- el checklist vehicular CP-OPE-004;
- el modelo de presupuesto de Logística.

De esos archivos solo se usó la estructura. El presupuesto trae datos personales (DNI y sueldos) y **no se guardó en el repositorio**.

## 1. Producción

### 1.1 Inicio del Jefe de Producción
El inicio tiene un bloque **«Producción de hoy»**:

| Qué muestra | Cómo se calcula |
|---|---|
| Ejecutado frente a lo planificado | Plan diario del día (o partes programados) contra lo producido en los partes de hoy. |
| Desviación frente a lo esperado a la hora | Producido ÷ (plan × avance de la jornada) − 1. Alerta si cae más de `desviacion_plan_alerta_pct` (10 %). |
| Cuánto producirá al cierre y si alcanza el plan | Avance actual + ritmo × horas que quedan hasta `hora_fin_produccion`. |
| Líneas en proceso y líneas paradas, con el motivo | Partes en proceso o pausados; motivo y minutos de la pausa abierta. |
| Paradas prolongadas | Más de `parada_prolongada_min` (30 min). Alerta a Producción y Gerencia de Operaciones. |
| Por línea: ritmo, tiempo restante, fin estimado, kg al cierre y si termina | Ritmo **real** del parte (kg ÷ minutos efectivos). Si aún no hay avance, capacidad nominal (marcada «nom.»). |
| Merma de hoy y de 7 días | Desmedro de los partes cerrados frente al umbral. |
| Solicitudes de producción pendientes y productos pendientes | Solicitudes enviadas, validadas, programadas o en proceso, con fecha requerida y vencidas. |
| Reempaques por ejecutar | **Solo los aprobados por Calidad.** |

Además, a Producción ya no se le muestran «Preparación (picking)» ni «Programación de picking» en el menú.

### 1.2 Informes de Producción
Son seis informes:
1. **Producción.**
2. **Merma y remanente de MP** (nuevo).
3. **Reempaque.** Solo muestra lo que Calidad aprobó: recibidos, por iniciar, en ejecución, ejecutados y tiempos.
4. **Control de producción.**
5. **Tablero OEE.**
6. **Cumplimiento por persona.**

A Producción no se le muestran informes de otras áreas.

**Nombre del «pucho».** Pasa a llamarse **«remanente de MP»**: materia prima utilizable que no se usó porque el pedido ya estaba completo. Es el campo antes rotulado «sobrante MP» del parte.

**Merma y remanente:**
- se ven por línea y, en las líneas manuales, por persona;
- el parte de las líneas manuales pide ahora la merma y el remanente de cada colaborador;
- si un parte no los tiene por persona, la merma se reparte según los kg de cada uno y se marca «estimada»;
- al cerrar un parte con merma o remanente se crea una **tarea para Calidad, Gerencia de Operaciones y Jefatura de Logística**, que deciden el destino: reproceso, reingreso o próximo lote.

**Recomendaciones.** Se generan con reglas y umbrales configurables (`reglas_recomendacion_produccion`), con el dato que las sustenta y un mínimo de 3 partes:
- persona por debajo del promedio de su línea → capacitación;
- tasa de faltas más alta → conversar y analizar la permanencia;
- merma por encima del promedio → más atención;
- persona más rápida en una línea que en otra → permanencia en la línea donde rinde más;
- línea con capacidad poco aprovechada → contrastar con la planificación;
- línea con merma sobre el umbral.

**Estilo de los informes.** Siguen el estilo de un resumen anual:
- una frase que resume el periodo;
- cifras grandes con los colores de la empresa;
- preguntas como títulos de sección;
- gráficos por línea, por día y por persona.

**PDF.** La exportación es **vertical** (A4) y lleva el logo.

**Cumplimiento por persona.** Muestra solo el personal del área de quien consulta y solo lo relacionado con sus funciones:
- tareas a tiempo, fuera de plazo y vencidas;
- en **Producción**: tasa de ausencia, rendimiento (kg/h por persona y por línea), merma y remanente;
- en **Almacén**: picking;
- en **Distribución**: entregas por chofer.

La interacción general con el sistema ya no se muestra.

### 1.3 Movimientos
**Qué se mueve** se elige de una lista, y cada tipo pide sus datos:

| Tipo | Datos que pide |
|---|---|
| Pallet de PT | N.° de pallets y código de PT (lista) |
| Merma | Peso en kg |
| Remanente de MP | Peso en kg y la MP (lista) |
| Muestra | PT, cantidad y cliente al que se envía |
| Pallet | Cantidad |

Un movimiento programado se pide por **día** con una **hora editable** (por defecto `hora_movimiento_programado`). Quien lo solicitó puede reprogramar el día y la hora; queda en el historial.

### 1.4 Proyección de demanda
La proyección de Comercial se contrasta con:
- el stock de todos los almacenes: PT, MP, externos y producción, **sin la merma** ni los lotes no disponibles;
- las **importaciones** que llegan en el mes;
- las **compras nacionales** con OC;
- la producción en curso.

Cada producto se muestra con su segmento (producto terminado, marca blanca, granel o MP), marca, presentación y canales. Para clasificar la marca blanca hay que configurar `marcas_propias`.

Cada perfil ve su parte:

| Perfil | Qué ve |
|---|---|
| Compras, Gerencia de Operaciones y Gerencia General (`demanda_presolicitud_roles`) | **Presolicitudes de compra** de la MP faltante, con la **fecha máxima para pedir** (fecha de necesidad − días máximos de reposición de su categoría), el botón «Generar presolicitud» y un aviso antes de la fecha. No se muestran a Producción. |
| Almacén, Logística y Gerencia de Operaciones | **Llegadas del mes**: importaciones y compras con fecha estimada. |
| Producción y Gerencia de Operaciones | **Preprogramación por capacidad real**: qué producir, en qué línea (la habitual del producto o la menos cargada) y en qué días, manteniendo un **stock de reserva** de `stock_reserva_dias` (7) días de demanda. Se pasa al planeamiento con un botón. |

**Demanda mayor que la capacidad.** Si la demanda supera la capacidad del mes, se muestra cuántos kg no caben y se pide definir con Gerencia de Operaciones cómo cubrirlos. Tu mensaje quedó cortado en «si la demanda proyectada es mayor a la capacidad de producción,…»: indíquenme qué debe hacer el sistema en ese caso.

## 2. Distribución

### 2.1 Checklist vehicular (CP-OPE-004)
- **Quién lo hace:** al salir y al volver, el chofer marca cada ítem B, M o NA (los 37 del formato) y registra el kilometraje y las observaciones de choques o raspaduras. Si el chofer no tiene cuenta, lo registra Distribución por encargo.
- **Validación:** Seguridad valida lo que subió el chofer y **registra el kilometraje de salida y de retorno**, que actualiza el odómetro de la unidad.
- **Puntos NN:** un punto NN (freno de mano, freno de servicio, luces altas y bajas) en mal estado **impide la salida**.
- **Observaciones:** cualquier ítem en mal estado u observación alerta al Coordinador y al Asistente de Distribución, con enlace a la ficha.
- **Retorno:** sin el **paso 2 de las incidencias** de la ruta (devoluciones, entregas parciales y cancelaciones) no se puede registrar el checklist de retorno, y sin él validado no se cierra el retorno.
- **Configuración:** `exigir_checklist_vehicular`.

### 2.2 Pre-guía y guía
- Al terminar el picking se genera la **pre-guía** (lo preparado frente a la OV, con lotes y diferencias).
- La validan el Coordinador o el Asistente de Distribución; si hay diferencias, deben justificarlas.
- Validada, se registra en SAP como **entrega basada en la OV**, con lotes, y queda en el expediente del cliente (documentos de la OV).
- Si SAP no está disponible, queda pendiente y se reintenta.
- **Solo el Coordinador y el Asistente de Distribución** registran o modifican guías.

**Cambio de fecha.** La fecha de la pre-guía o de la guía emitida se cambia indicando el motivo. El cambio se envía a SAP, y lo que se cambie en SAP llega al módulo con la sincronización de despachos. Los dos sentidos quedan registrados.

**Corte de rutas: 15:00 del día anterior** (`hora_corte_rutas`).
- Lo que se prepare o se pida para mañana después del corte se registra igual y se alerta a Distribución para que confirme si entra en la ruta.
- Si pasado el corte hay OV de mañana sin ruta, se avisa.

### 2.3 Transporte tercero
1. **Solicitud.** Se registran proveedor, cliente para quien se contrata, punto de partida y llegada, tipo de vehículo, toneladas y monto con IGV.
2. **Aprobación previa** de Gerencia de Operaciones. Finanzas queda informada.
3. **Tarifario.** El monto se compara con el tarifario. Si es mayor, el Coordinador indica el motivo: se permite y se alerta a Gerencia de Operaciones y Finanzas.
   - El tarifario lo modifica (parcial o totalmente) el Coordinador de Distribución, con historial por tarifa; cada cambio alerta a Gerencia de Operaciones y Finanzas.
4. **Factura.** Se registran número y archivo, centro de costo, tipo de servicio (fletes o estibas y su subcategoría) y la **guía remitente**, que se trae de SAP o de la ruta y Distribución valida. La **fecha del servicio es la de la guía**.
5. **OC.** Compras recibe la tarea y registra la OC; el **expediente** (factura + guía + OC) queda completo.
6. **Finanzas.** Administración y Finanzas valida, programa pagos (también **parciales**), registra observaciones y sube el **comprobante**. Se alerta si un pago programado vence sin registrarse.
7. **Proveedores.** Se registran sus incidencias y sus **indicadores**: servicios, toneladas, monto, S/ por tonelada, servicios sobre tarifa, incidencias y su tasa, y pagado.

**Tipos de servicio y centros de costo.** Hoy son configurables (`terceros_tipos_servicio`, `terceros_centros_costo`). Se tomarán de SAP cuando se conecte el Service Layer, para lo que hay que confirmar con el partner de dónde se leen.

### 2.4 Presupuesto del área
- **Registro.** Lo registra el Coordinador de Distribución cargando el **mismo modelo de Excel**: partidas por categoría, concepto, tipo de vehículo y placa, con presupuesto y real por mes. También puede hacerlo partida por partida.
- **Aprobación.** Lo envía a Administración y Finanzas, que lo aprueba u observa.
- **Gasto real.** Se registra a mano por partida. Además se toma automáticamente lo que el módulo ya conoce:
  - el transporte tercero;
  - los mantenimientos (preventivo, correctivo y revisión técnica) por placa.
- **Alertas.** Alerta al **75 %** del presupuesto acumulado a la fecha (`presupuesto_alerta_pct`), en total y por categoría, recomendando moderar el gasto; y otra al superar el 100 %.

### 2.5 Incidencias
- **Paso 1:** al momento.
- **Paso 2:** al retorno, lo que realmente vuelve. Se crea una **tarea para Almacén**, que confirma lo recibido. Después:

| Situación de la OV | Qué sigue |
|---|---|
| Ya **facturada** (factura registrada desde SAP o en la entrega) | Finanzas valida si procede la nota de crédito y el Coordinador de Distribución la solicita con la factura a la vista. |
| **Sin factura** | El Coordinador de Distribución registra la solicitud de devolución. |

**Modificaciones.** Pueden modificar la incidencia el Coordinador y el Asistente de Distribución, el Jefe de Logística y Gerencia de Operaciones. Cada cambio queda registrado con su motivo y el antes y después.

### 2.6 Flota y mantenimiento
- Nuevo documento: **tarjeta de circulación**.
- Avisos por tipo de documento (`aviso_documentos_vehiculo_dias`), con **recordatorio un día antes y el mismo día**:

| Documento | Anticipación del aviso |
|---|---|
| SOAT | 2 semanas |
| Tarjeta de circulación | 1 mes |
| Revisión técnica | 1 mes; es anual: el vencimiento se calcula a 365 días si no se indica |

- **Mantenimiento cada 5 000 km**, avisado 500 km antes. Se cuenta desde el último preventivo o, si no hay, desde el kilometraje actual.
- Cada mantenimiento admite el **informe** del taller, la **factura** (también la registra Compras) y la **incidencia con el taller**: motivo, días fuera de servicio y detalle.
- El informe de **Distribución** muestra el **fill rate**: unidades, líneas, pedidos al 100 % y causas.

## 3. Pendiente de confirmar
1. Qué hacer cuando la demanda proyectada supera la capacidad de producción (el mensaje quedó cortado).
2. Horario de producción para las estimaciones del día: hoy de 08:00 a 17:00 (`hora_inicio_produccion` y `hora_fin_produccion`).
3. «Gerente general adjunto»: se usó el perfil de Gerencia General. Si es otra persona, se crea su perfil.
4. Marcas propias, para distinguir la marca blanca.
5. Tipos de servicio (fletes y estibas) y centros de costo desde SAP: confirmar con el partner de dónde se leen.
6. Registro de la entrega (guía) en SAP: probarlo en la base de pruebas con una OV real. Se asume que la línea de la entrega corresponde a la posición de la línea en la OV que envía el módulo.
7. «Administración y Finanzas» se asignó al perfil de Coordinación de Finanzas.

## 4. Verificación
- Pruebas automáticas: `tests/test_v12.py` (18 pruebas). Se ejecutó también la batería completa.
- Migraciones `0023` y `0024`, sin diferencias con el modelo.
- Recorrido en el navegador de las pantallas nuevas.
