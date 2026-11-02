# Ronda V18: observaciones del 02-nov-2026 (segunda parte)

Todo lo de esta ronda se probó con datos ficticios. Cada punto indica dónde está en el sistema.

## 1. Diseño de los indicadores

- Las tarjetas de indicadores (inicio, informes, control de producción) ya no son todas verdes:
  - fondo blanco con una franja de color a la izquierda, distinta en cada tarjeta;
  - el nombre arriba, en mayúsculas pequeñas, y el número grande en gris oscuro.
- **Lo importante resalta por su estado:**
  - **verde**: dentro de la meta;
  - **ámbar**: vigilar;
  - **rojo**: alerta (atrasos, despachos en riesgo, paradas, merma fuera de rango, tasa de cambio de guías alta).
- El resumen del informe de Producción usa el mismo criterio: cumplimiento en verde, ámbar o rojo; merma en ámbar; paradas en rojo.

## 2. Logística, asistencia y flota

- **Jefe de Logística: todos los almacenes.** Ya no aparece «el almacén no está asignado a su rol». Lo mismo vale para la Jefatura de Operaciones. Se cambió el parámetro `alcance_almacen_excepto`.
- **Asistencia:**
  - **Alta de colaboradores uno a uno o por Excel.** El Excel lleva las columnas Nombre, Documento, Puesto, Línea y Externo.
    - Si el colaborador ya existe (por documento o por nombre en el área), se actualiza; si no, se crea.
  - **Puesto en lista.** La lista tiene:
    - los perfiles del área;
    - los puestos que se agreguen en el parámetro `puestos_por_area`;
    - la opción **«Otro»**, que abre un campo para escribirlo.
  - **Cambio de línea del día (Producción).** Al marcar la asistencia se puede indicar en qué línea trabajó cada persona ese día (por faltas o prioridades). Su línea habitual no cambia.
- **El chofer reporta averías** desde «Mis entregas → Reportar una avería del vehículo». La avería llega a Mantenimiento como las demás.
- **Checklist vehicular:**
  - lo ven Distribución, el Jefe de Logística, la Jefatura de Operaciones, Seguridad y las Gerencias (Distribución → Checklists vehiculares);
  - la **imagen del vehículo es interactiva**: se toca el lugar del daño (lateral izquierdo, lateral derecho, frente, parte posterior o techo), aparece un punto numerado y se escribe qué tiene;
  - las marcas quedan en el checklist y en sus observaciones.

## 3. Inicio: despachos por cliente y fecha

- En el inicio, la sección «Despachos por cliente y fecha» agrupa los pedidos desde ayer hasta 7 días adelante. Para cada cliente y fecha de despacho muestra:
  - el **pronóstico**:
    - **En riesgo**: atraso, detención o faltante;
    - **Por vigilar**: sale hoy sin todo preparado;
    - **A tiempo**;
    - **Cumplido**;
  - las **modificaciones** (cambios de OV, de fecha, renegociaciones, cambios de producto);
  - las **incidencias** y los **problemas**.
- **Quién lo ve:**
  - todo: Jefe de Logística, Jefatura de Operaciones, Gerente General, Gerente General Adjunto, Gerente Comercial, Coordinador Comercial y Jefe de Ventas;
  - el **ejecutivo comercial** solo ve sus clientes y sus OV.

## 4. Picking en una sola pantalla

- Desde la OV, «Preparación» lleva directo a la tarea de picking si hay una sola. En esa pantalla se hace todo:
  - iniciar;
  - validar el plan;
  - registrar cantidad, lote y **bultos**;
  - terminar con foto.
- **«Cambiar lote»** lista **todos** los lotes del producto en el almacén:
  - los que se pueden usar, primero;
  - los que no, con el motivo (vencimiento, observado, sin saldo libre…).
- **Formato de picking:**
  - el lote, la fecha de producción y la de vencimiento salen solos del lote reservado;
  - el auxiliar completa lo despachado y los bultos.

## 5. Producción

- **Validación con plazo no confirmado.**
  - El plazo se marca ✓ o ✗. Con ✗, Producción indica la **fecha en que entregaría**.
  - Debe ser al menos **un día antes del despacho**. Si es posterior, la solicitud se valida igual y se emite la alerta **«Producción no confirma el plazo»**. La reciben:
    - el Jefe de Logística, la Jefatura de Operaciones, el Coordinador y el Jefe de Ventas;
    - el ejecutivo de la OV.
- **Planeamiento:**
  - se registran **varios productos a la vez** (filas con fecha, producto, cantidad, línea y comentario);
  - **«Preprogramar»** ahora sí deja la programación a la vista. Antes se creaba con fechas futuras que la pantalla no mostraba. Además propone la **línea** del producto: la de su última solicitud o su último parte.
- **Monitoreo en tiempo real.** Una producción iniciada desde el planeamiento abre un parte «EN PROCESO» en su línea (OF `PS-<n.°>`), así que aparece en el monitoreo.
- **EAN escaneado:** se elige de la lista de EAN del producto o se escribe.
- **Control de Producción:**
  - se exporta a **Excel** y **PDF** (asistentes, Jefe de Producción y Jefatura de Operaciones);
  - tiene un aspecto más formal: indicadores con estado, tabla por línea, hallazgos, situación y acciones.

## 6. Liquidación de proceso

- **Lista con el encabezado del documento:** N°, Proceso, Descripción, Lote, Proveedor, Procedencia, Calidad, FP, FV y Fecha de recepción.
  - **Filtros** por cualquiera de esas casillas, más N°, línea, SKU, lote y rango de fechas.
- **SKU y lote** se eligen **de la lista** o se **escriben**.
- **Nueva liquidación manual** (sin partes), con todas las casillas de «Datos del servicio» y «Datos del producto».
  - Descripción, marca y calidad se toman del SKU si se dejan vacías.
  - Sigue la creación desde los partes de los asistentes.
- **Fórmulas** del formato (ya estaban): total = sacos × peso + saldo; movimiento; %; desviación; desmedro; MO = horas × costo; CIF = kg × costo; costo unitario; costo del desmedro.
- **Control de merma** (se agregó; son los cálculos al costado de la hoja PF del Excel):
  - % de merma esperada: por defecto el del producto, editable;
  - merma esperada en kg = ingreso × %;
  - total procesado = ingreso − desmedro;
  - sacos de 50 kg = total procesado ÷ 50;
  - diferencia = total procesado − salida procesada.

  Si el desmedro real supera la merma esperada, se resalta. Esta sección va también en el Excel.
- **Siguen igual:** agregar o quitar campos, filas y procesos; varias fotos; impresión y Excel con el diseño del formato.

## 7. Pre-guía y guía (Distribución)

- **Revisión como el precertificado de Calidad** (Distribución → Pre-guías → «Revisar y aprobar», o desde la alerta). Se ve el documento completo y se corrige todo antes de aprobar:
  - la fecha;
  - el punto de llegada;
  - el motivo de traslado;
  - las observaciones que se imprimen;
  - por producto: la cantidad, la presentación y la cantidad por lote (la suma de los lotes debe coincidir).
- **Lo revisado se guarda aunque la aprobación falle**, por ejemplo si hay diferencias con la OV y falta la observación.
- **Aprobar = emitir la guía:**
  - se registra en SAP (entrega basada en la OV, con lotes) si la escritura en SAP está habilitada; si no, queda pendiente y se reintenta sola;
  - la guía queda imprimible con el formato de la empresa.
- **No lleva foto.** Registra tres momentos:
  - **inicio** de la revisión: la primera vez que la abre Distribución;
  - **revisión**: la última vez que se guardó;
  - **fin**: la emisión.

  Muestra también los minutos de espera y de revisión.
- **Emitida, ya no se edita la guía completa.** Solo se cambian la **fecha**, las **cantidades** o la **presentación**, con el **lápiz ✎** y un motivo obligatorio. Cada cambio deja un rastro: quién, qué campo, de qué valor a qué valor, cuándo y por qué.
- **Indicador de cambios** (en Pre-guías), para el Jefe de Logística, la Jefatura de Operaciones, las Gerencias y el Coordinador de Distribución:
  - guías emitidas en el periodo;
  - tasa de guías cambiadas después de emitidas;
  - cambios por campo;
  - quién cambia.
- **Mismo dato en todos lados.** Desde la alerta y desde Pre-guías se abre la misma pantalla. Al aprobar, la alerta se cierra en el mismo momento.
  - Las otras pantallas muestran el estado nuevo al abrirlas o recargarlas.
  - El contador de alertas se actualiza en la consulta periódica, cada 60 s por defecto.
  - No hay actualización «en vivo» sin recargar.

## 8. Límites y puntos por confirmar

1. **Cantidades cambiadas después de emitir la guía en SAP.** SAP no permite cambiar las cantidades de una entrega ya registrada. El módulo guarda el cambio con su rastro y marca la guía como **«ajustar la entrega en SAP»**. El ajuste en SAP (devolución o nueva entrega) es manual. Los cambios de fecha sí se envían a SAP.
2. **Quién recibe «Producción no confirma el plazo».** Se propuso: Jefe de Logística, Jefatura de Operaciones, Coordinador y Jefe de Ventas, más el ejecutivo de la OV. ¿Es correcto?
3. **Lista de puestos.** El parámetro `puestos_por_area` está vacío: por ahora la lista muestra los perfiles del área. Envíen los puestos de cada área si quieren otros.
4. **Sacos de 50 kg** en la liquidación: se tomó el divisor de la fórmula del Excel (O17 = N17 / 50). Si cambia por producto, se puede tomar del «Peso del saco».
5. **Inicio de la revisión de la pre-guía.** Se toma como inicio la primera vez que la abre el Coordinador o el Asistente de Distribución. ¿Lo quieren con un botón «Iniciar revisión»?

## 9. Datos técnicos

- **Migración `0031`:** `attendance.linea` y `vehicle_checklists.marcas`.
- **Servicios:**
  - `guides.py`: `review`, `start_review`, `edit_emitted`, `change_rate`, `durations`;
  - `process_liq.py`: `create_manual`, `header`, `matches` y el control de merma en `calc`;
  - `attendance.py`: `positions`, `import_workers` y la línea del día;
  - `seguimiento.py`: `dispatch_board`;
  - `picking.py`: `lot_options(todos=True)` y `format_rows` con la reserva;
  - `production.py`: `add_plans`, `suggested_line`, el plazo con fecha y el parte en curso al iniciar;
  - `parte.py`: `control_excel`;
  - `vehicle_checklist.py`: `parse_marks`.
- **Vistas nuevas:** `/distribucion/preguia/<id>` y `/distribucion/checklists`.
- **Plantillas:** `preguia_detail.html`, `checklists.html`, `_vehiculo.html` y `control_produccion_pdf.html`.
- **Script:** `static/v18.js`.
- **Catálogo:**
  - permiso `checklist.ver`;
  - alerta `PRODUCCION_PLAZO_RIESGO`;
  - parámetro `puestos_por_area`;
  - cambio en `alcance_almacen_excepto`.
- **Corrección:** al dar de alta un colaborador con «Otro» sin escribir el puesto ya no queda un registro vacío.
- **Pruebas:** `tests/test_v18.py` (15 pruebas).
