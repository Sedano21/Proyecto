# Ronda V13 (30-oct-2026): Calidad

Indicaciones de Calidad del 30-oct-2026, con:
- la imagen del registro de fumigación RBPM-005;
- un ZIP con 7 imágenes: 4 ejemplos de certificado y 3 formatos de limpieza (PHS-001 áreas externas, almacén de PT y línea automática).

De las imágenes solo se usó la estructura (campos y puntos de verificación). No se guardaron en el repositorio.

**Faltan dos fuentes:**
- La foto del formato **«Control de recepción de envases y embalajes»** no venía en el ZIP. El formato **no está implementado**.
- Los formatos de **higiene personal** y **BPM** no venían. Están creados sin puntos. El Jefe de Calidad puede escribir los puntos en el sistema hasta recibir el formato oficial.

## 1. Lotes y stock

| Indicación | Implementación |
|---|---|
| Categoría **OBSERVADO** con motivo | Calidad observa el lote con una categoría: plaga (para fumigar), piedra, fecha de vencimiento, hongueados o granos infestados. También lo puede hacer durante la producción. |
| Alerta inmediata y semanal | Alerta inmediata a Almacén, Calidad y Producción (`LOTE_OBSERVADO`). Recordatorio cada `dias_recordatorio_lote_observado` (7) días mientras el lote siga en stock. |
| Solo Calidad libera | Un lote bloqueado (observado, pendiente de revisión, en fumigación, no utilizable o dañado) solo pasa a disponible por Calidad (`calidad.liberar`). Si Almacén lo intenta, el sistema le indica que use «Solicitar liberación a Calidad». |
| Almacén solicita, Calidad aprueba | Desde Stock: «Solicitar a Calidad» → liberación, ¿apto para proceso? o ¿va a fumigación?. Calidad resuelve en la **Bandeja**. |
| Reservas y análisis solo con disponibles | Las reservas, la disponibilidad para producción y las proyecciones ya tomaban solo lotes DISPONIBLES. Una prueba lo verifica con un lote observado. |
| Fumigación con inicio y liberación | Calidad pone el lote en fumigación con fecha de inicio, fecha prevista de liberación y zona. Al llegar la fecha se le recuerda liberar (`FUMIGACION_LIBERAR`). |
| Varias fechas de producción por lote | Cada fecha tiene su cantidad y su estado (disponible, observado, en fumigación, no utilizable, liberado). Se registran varias a la vez y el estado se edita. La lista de stock las muestra. |

## 2. Bandeja de Calidad (`/calidad/bandeja`)
- **Solicitudes de revisión**: liberación, apto para proceso o fumigación. Se resuelven con comentario; si van a fumigación, con fechas y zona.
- **Lotes bloqueados**, con:
  - observación, fumigación y liberación solicitada;
  - acciones para observar, fumigar y liberar.
- **Devoluciones e incidencias**: las de motivo de calidad salen primero, con un aviso de que Calidad debe actuar (`DEVOLUCION_CALIDAD`).
- **Solicitudes de reempaque**, con:
  - fecha de vencimiento del lote;
  - marca y presentación del producto destino;
  - nueva fecha de vencimiento.
- **Compras nacionales e importaciones**: Calidad recibe las alertas de llegada, incidente y diferencia. También ve el cuadro «Llegadas de compras e importaciones».

## 3. Producción ↔ Calidad

### 3.1 Observaciones en la línea (`/calidad/linea`)
- Fases: notificación → en atención → fin con motivo.
- Se registran por uno o varios pallets, con fotos opcionales.
- Producción pasa la observación a atención; solo Calidad la cierra.

### 3.2 Validación de merma
1. Al terminar cada proceso (parte finalizado), Calidad recibe la alerta `MERMA_VALIDAR`. Es de prioridad alta si la merma supera el límite de Gerencia.
2. Calidad registra los kg de grano bueno y de grano dañado, con una o varias fotos.
3. Calidad da **conformidad** o pide **reproceso**.
4. El reproceso avisa a Producción. Si Producción no lo atiende en `horas_reproceso` (48 h), la alerta vuelve a Calidad (`REPROCESO_VENCIDO`).

El límite es `merma_limite_gerencia_pct`. Por ahora es 5 % para todas las líneas («*»), marcado como **PROPUESTO**: falta el porcentaje que fija Gerencia para cada línea.

### 3.3 Material y saldo por línea (`/calidad/material`)
- **Material que usará Producción**: para las solicitudes validadas o programadas de los próximos días, según la lista de materiales. Muestra lote, producto, calidad, FV, almacén y faltante. Los lotes se eligen por el primero en vencer, solo entre los disponibles.
- **Saldo por proceso en cada línea**: entrada − producido − merma − remanente de los partes cerrados del periodo.

## 4. Formatos

| Indicación | Implementación |
|---|---|
| Revisar por día o rango y por varios tipos | Filtro por día o desde/hasta, con selección múltiple de tipos de formato. |
| Hora con reloj | Todos los campos de hora usan el selector de hora del navegador. |
| PCC1 | Trigo mote 12.5 %. Trigo en grano, trigo entero pelado y cebada cruda 14.5 %. |
| Fumigación RBPM-005 con zona | Lista de zonas de saneamiento, almacenes externos y «otro», con campo «¿dónde?». |
| «Ingreso de nuevo lote» solo Producción | Lo registra Producción (`produccion.lote_nuevo`). Sale del selector de Calidad y entra al menú de Producción. |
| «Registro de datos de proceso» retirado | Ya no se registra. Los registros anteriores se pueden consultar y aparecen como «(retirado)» en el filtro. |
| Fotos en recepción de importados | Todos los formatos aceptan fotos o adjuntos opcionales, uno o varios. |
| Nuevos formatos de verificación | Formatos C / N-C por punto, con observación o acción correctiva obligatoria si el punto no es conforme: PHS-001 áreas externas, almacén de PT y línea de procesamiento (puntos tomados de las imágenes), higiene personal y BPM (sin puntos, ver arriba). |
| Consolidado en Excel | Se exportan todos los formatos o solo los de materia prima: una hoja por formato y un resumen. Se puede cargar una base anterior con el mismo formato; las filas ya cargadas no se duplican. |
| Certificado | El campo de quién procesa se elige entre «Procesado y envasado por» (por defecto), «Procesado por» e «Importado, procesado y envasado por». Además, Calidad agrega o quita filas de datos adicionales (etiqueta y descripción). |

## 5. Gestión de Calidad (`/calidad/gestion`)

### 5.1 Inspecciones externas
- Fase 1 · Programación: cliente que la solicitó, empresa que la ejecuta, fecha y hora de inicio.
- Fase 2 · Registro y proceso.
- Fase 3 · Resultado:
  - aprobado o desaprobado;
  - puntaje y número de hallazgos;
  - fotos del resultado y de los hallazgos.

La programación y el resultado avisan a:
- Producción;
- Almacén;
- Logística;
- Operaciones;
- Comercial;
- Administración y Finanzas.

### 5.2 Inspecciones internas
Cada hallazgo se asigna como **tarea** al área responsable, con plazo y foto. La tarea se cierra con la evidencia del levantamiento.

### 5.3 Visitas a almacenes externos
1. Calidad propone la fecha y la hora.
2. Almacén confirma o reprograma con motivo.
3. Los hallazgos de la visita se siguen como tareas a las áreas.

El tipo «Fumigación» sirve para la fumigación del almacén externo.

### 5.4 Quejas y no conformidades
El reporte del periodo muestra:
- las quejas, también por cliente;
- las no conformidades y acciones correctivas, con las abiertas resaltadas;
- los productos no conformes.

## 6. Otros arreglos
- **Menú de Calidad**: no muestra productividad por persona, asistencia ni análisis de reposición.
- **Bitácora de zonas y vehículos**: la lista de zonas salía vacía porque la base demo no tenía zonas.
  - La demo trae 4 zonas ficticias.
  - Si no hay zonas, el formulario lo indica.
- **Oportunidades**: cuando hay varios productos, cada uno tiene su proyección en kg/mes y S/ por mes. El total de la oportunidad es la suma.

## 7. Datos técnicos
- Migración `0025`:
  - tablas `review_requests`, `line_observations`, `merma_validations`, `inspections` y `external_visits`;
  - columnas nuevas en `stock_lots`, `quality_records` y `opportunities`.
- Permisos nuevos:
  - `calidad.gestion`;
  - `calidad.revision_solicitar`;
  - `calidad.formatos_configurar`;
  - `produccion.lote_nuevo`.

  Los roles de Calidad reciben además `seguridad.llegadas`.
- Tareas programadas: `check_observed`, `check_fumigation_release` y `check_reprocess`.
- Pruebas: `tests/test_v13.py`.

## 8. Pendiente de la empresa
1. Foto o archivo del formato **«Control de recepción de envases y embalajes»**.
2. Formatos de **higiene personal** y **BPM**, con sus puntos de verificación.
3. **Porcentaje de merma** que acepta Gerencia, por línea.

## 9. Liquidación de proceso CP-OPE-004 (Producción)

Fuente: archivo «LIQUIDACIONES 2026». Se tomó solo la estructura del formato; los datos, productos, proveedores y fotos del archivo no se guardaron en el repositorio. Las celdas de costo (S/ por hora, por unidad y por kg) quedan vacías: las llena Producción.

| Indicación | Implementación |
|---|---|
| Agregar el formato tal cual | Pantalla y Excel con el mismo diseño: cabecera (logo, «LIQUIDACION DE PROCESO», CP- OPE - 004, OPERACIONES, N°), datos del servicio y del producto, tablas por proceso, desviación, horas, operarios y desmedro, referencias gráficas, observaciones y pie con logos. Dos variantes, como las hojas del archivo: **varios procesos** (graneal a MP, MP-T S, MP-T L…) y **un proceso con costo MO + CIF y costo del desmedro**. |
| Jalar lo que llenan los asistentes | Se crea eligiendo uno o varios partes de producción del mismo SKU: cada parte es un proceso con ingreso, salida, desmedro, remanente, horas y operarios; el producto, el lote, la calidad y las fechas salen del artículo y del lote. |
| Ver por línea, SKU o lote | Lista con filtros por línea, SKU y lote; acceso también desde el detalle del parte. |
| Eliminar o añadir campos | Los campos del servicio y del producto, las filas de cada tabla y los procesos se agregan o quitan. |
| Fotografía | Una o varias fotos del lote (cámara del celular), que también se insertan en el Excel. |
| Solo Producción | Permiso `produccion.liquidacion_proceso` (Jefe y Asistente de Producción); Gerencia lo ve en solo lectura. Al cerrar ya no se edita; reabre el Jefe de Producción. |

Cálculos, como en el archivo:
- TOTAL = sacos × peso por saco + saldo.
- MOVIMIENTO = −total en el ingreso y +total en cada salida.
- % = movimiento ÷ total del ingreso.
- DESVIACIÓN = suma de los movimientos.
- DESMEDRO = filas de desmedro ÷ ingreso. En el archivo, la suma del tercer proceso incluía también la fila «SALIDA - GRANEL»; aquí solo cuentan las filas de desmedro.
- Costos: MO = horas × costo por hora; CIF = unidades × costo por unidad; costo unitario = total ÷ unidades; costo del desmedro = kg × costo por kg.

Datos técnicos: migración `0026` (tabla `process_liquidations`), parámetro `liquidacion_proceso_pie`, pruebas `tests/test_liq_proceso.py`.
