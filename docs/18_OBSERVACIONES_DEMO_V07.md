# Versión 0.9 – Observaciones al demo v0.7 (15-oct-2026)

Aplicación de las observaciones al demo v0.7 y de los mensajes posteriores del mismo día (formato de guía de remisión,
capacidad por línea, manual de usuario por rol, actualización inmediata de alertas, visibilidad de las Gerencias y
Seguridad). Datos de demostración ficticios; las fotos recibidas (guía con datos reales de un cliente) **no** se
incorporan al repositorio: se tomó solo el diseño del formato.

## 1. Vista general

| Observación | Implementación |
|---|---|
| Al rellenar campos, lo escrito no debe borrarse; resaltar lo que falta | `static/app.js`: los obligatorios vacíos se resaltan con su mensaje y un aviso arriba del formulario, sin enviar ni borrar. Si el servidor rechaza el guardado, la pantalla vuelve con **todo lo escrito restaurado** y resalta los campos que faltan o que nombra el mensaje. Funciona en todos los formularios. |
| Organizar las vistas (OV) y hacerlas interactivas | Lista de OV con iconos por fila: **ojo** (ver), **lápiz** (editar o solicitar modificación) y **tres puntos** (renegociar fecha, proponer producto disponible, opciones ante faltante, expediente, imprimir, cancelar). Detalle de la OV en **pestañas**: Resumen, Productos y reservas, Condición y opciones, Editar, Gestionar, Expediente, Solicitudes e historial, con barra de avance del pedido. |
| Alertas con sonido; las importantes con sonido distinto y repetido hasta resolverse | La pantalla consulta el estado de alertas (parámetro `alerta_sonido_consulta_seg`, 60 s): alerta nueva = campanilla y aviso; alerta importante (urgencia ALTA que el usuario debe atender) = sonido insistente, que se **repite** cada `alerta_sonido_repetir_seg` (120 s) mientras siga abierta. Botón de parlante para silenciar en el equipo. El navegador solo permite sonar después del primer toque o clic en la página. |
| Las alertas deben actualizarse inmediatamente para el resto de destinatarios | Las pantallas de alertas, detalle de alerta e inicio se actualizan solas (cada `alerta_actualizacion_seg`, 10 s) cuando otro destinatario actúa; se muestra quién hizo qué. Si el usuario está escribiendo, no se reemplaza su formulario: aparece «Ver lo último». Una acción sobre una tarea ya cerrada por otro es rechazada. |
| Cargar archivos en Excel y PDF | Todas las cargas aceptan Excel y PDF: del PDF (con texto) se lee la tabla con los mismos encabezados que el Excel, por posición de columnas. Un PDF escaneado no se puede leer y el sistema lo indica. |
| Informes descargables en PDF; armar su informe | Cada informe: **Descargar PDF** (títulos, indicadores, tablas y gráficos) y **Excel** (una hoja por tabla). **Arme su informe**: fuente de datos según permisos (OV, líneas de OV, stock, picking, producción, partes, compras, rutas, incidencias, alertas), columnas, periodo, texto a buscar y agrupación con cuenta y sumas; pantalla, PDF o Excel. Se agregó la dependencia `fpdf2` (Python puro). |
| Manual de usuario para cada rol | Menú de usuario → **Manual de usuario** (`/ayuda`): papel del rol, lo que no le corresponde, tareas paso a paso, pantallas autorizadas (según sus permisos) y uso general. Sistemas y Gerencia General pueden ver el de cualquier rol. Se imprime o guarda en PDF. |
| Gerencia de Operaciones y General ven todas las funciones, reportes y movimientos | Permiso `vista.total`: ven (solo consulta) todas las pantallas e informes y la auditoría de movimientos; los botones de acción siguen dependiendo de sus permisos reales. |

## 2. Comercial

| Observación | Implementación |
|---|---|
| Grupo del cliente nuevo como lista desplegable | Lista con los grupos existentes, los del mapeo grupo→canal y los agregados en «Canales y grupos». |
| OV: producto, cantidad y precio obligatorios | Cada línea con producto exige cantidad y precio (resaltado en pantalla y validado en el servidor). Excepción conservada: la **muestra comercial** (decisión del 13-oct) se registra sin precio y queda detenida hasta su confirmación. |
| Añadir canales (solo Coordinador de Ventas, Jefe de Ventas y Sistemas) | Pantalla **Canales y grupos** (permiso exclusivo `canales.gestionar`). |
| Lápiz para editar la OV desde la lista | Ver sección 1. |
| Naturaleza «información» para lo que el perfil no puede aprobar, desestimar o asignar | La naturaleza se calcula por usuario: es **tarea** solo si puede aprobarla o desaprobarla (mismo permiso de su pantalla), designarla dentro de su área o ejecutarla; si no, la ve como **información** (sin botones de acción). |
| Producto base como lista desplegable (competencia, sustituto, mercado) | En todos los formularios de precios de mercado. |
| Recomendación automática con los datos cargados | Costos vs mercado y Análisis de mercado muestran por producto base: nuestro precio (promedio de OV o, sin ventas, mínimo de lista) frente al promedio de competencia y de sustitutos, con la lectura automática (p. ej. «Estamos 15 % más arriba del precio del producto sustituto; estamos 10 % más abajo respecto a la competencia») y la acción sugerida. Se recalcula al cargar datos. |
| No crear OV con fecha pasada u hora transcurrida; apartado de regularización | El registro y la modificación rechazan fechas pasadas y horas de cita ya transcurridas. **Regularización de OV** (Asistente de Ventas, Ejecutivo/responsable de canal, Coordinador y Jefe de Ventas): se registra con motivo **sin reservar stock**; luego se libera al flujo normal con fecha vigente o se cierra como registro. |
| Quién aprobó el precio por debajo del costo o del mínimo | Se muestra en la OV (nombre, cargo, fecha y motivo) y en la lista de OV. |

## 3. Almacén y Logística

| Observación | Implementación |
|---|---|
| Estado de una alerta aprobada que pasa a otra área | La tarea queda «**Derivada · pendiente <área>**» mientras la tarea generada en el área destino siga abierta; en el detalle se enlazan las tareas derivadas. |
| Capacidad por línea (tabla reenviada) | Líneas renombradas según la tabla: IQ+CIMB 25 500, TRUER 12 750, SEL. MANUAL 4 250, RAUMAK 1 Y 2 18 700 (compartida por R1 y R2), RAUMAK 3 29 750, ENV. MANUAL 2 550 kg/día. La programación verifica la carga del grupo con la jornada del día; domingos y feriados no se programa. |
| Asignación del personal en el picking; prepicking con el auxiliar del almacén del pedido | La propuesta considera al auxiliar de almacén **o de despacho** asignado al almacén donde está el stock reservado. La asignación se modifica desde la programación, el detalle y el formato. |
| Producción aprobada sin materiales suficientes | Se puede aprobar: el sistema genera las **presolicitudes de compra** de lo que falta (con la OV de origen), alerta el **quiebre de stock** y el **plazo de reposición**. Almacén (o Logística) autoriza la presolicitud y pasa a Compras; Compras registra las **cotizaciones** y la ejecución requiere la aprobación de **Gerencia de Operaciones**. |
| OV de origen, motivo detallado y agrupación de solicitudes | Cada presolicitud muestra sus OV de origen y el motivo (stock libre vs requerido, plazo de reposición y pedidos similares con faltante). Las del mismo producto y fecha de entrega se **agrupan** en una sola (parámetro `agrupar_presolicitudes_compra`). Compras las ve agrupadas por tipo de artículo. |
| Presolicitudes aprobadas por Jefe o Coordinador de Logística; ejecución solo con GO | `compras.aprobar_solicitud`: Jefe y Coordinador de Logística y Coordinadores de Almacén. Parámetros `compra_ejecucion_requiere_go` (sí) y `cotizaciones_minimas_compra` (1, propuesto). |

## 4. Picking (Auxiliar y Líder Operativo)

- Al iniciar con la foto se abre el **formato de seguimiento de control de despacho** completado con el stock reservado;
  el auxiliar solo llena **Despachado und** (bultos calculados).
- **Cambiar lote** con motivo en lista desplegable: *Rotura o dañado*, *Infestación*, *Contaminación* → lo afectado del
  lote original queda como **Producto observado** (nuevo estado de stock) y se avisa a Calidad; *Difícil acceso* → se
  libera la reserva del lote original (sigue disponible) y se reserva lo picado. El formato y el stock se actualizan al
  instante; los cambios quedan registrados en la tarea.
- Asignación: **Una persona** (lista desplegable con el personal del almacén y su carga del día) o **Un grupo** (sin
  límite), con el **preplaneamiento** del día a la vista.
- La alerta de picking llega al responsable del almacén y su personal, al Coordinador y Jefe de Logística y a Gerencia
  de Operaciones; para quienes no pueden accionarla es informativa.
- El **precertificado se emite después del picking** (parámetro `certificado_previo_al_picking` = no), con los lotes picados.

## 5. Calidad, Producción y Distribución

- **Certificado**: «Guardar avance» lo deja en borrador; «Confirmar y aprobar» pide confirmación; si falta un dato, se
  guarda lo escrito y se indica qué falta. Ventanas de confirmación en las acciones importantes de todo el sistema.
- **Asistente de Calidad**: registros por etapa — *Antes* (higiene del personal y de equipos), *Durante* (ingreso de
  nuevo lote con los datos de la ficha) y *Después* (cierre del proceso). El lote registrado se **contrasta con la
  liquidación** (alerta si difiere) y el stock se actualiza cuando Almacén confirma la recepción.
- **Producción**: consolidado de requerimientos por producto, fecha y cantidad (día, semana o mes); el sistema
  **preprograma** el planeamiento y el Jefe de Producción lo edita. Seguimiento de materiales faltantes con su compra o
  importación y la **fecha estimada de llegada**.
- **Coordinador de Distribución**: ve rutas, pre-guía y guía; **aprueba la guía** como el Asistente; no ve líneas,
  reservas ni lotes de la OV; ve el **expediente** de la OV (OV, certificado, guía y factura).
- **Guía de remisión** con el diseño del formato enviado: emisor y R.U.C., «GUÍA ELECTRÓNICA» y número, destinatario,
  fechas, puntos de partida y llegada, ítems con lote/FP/FV, cantidad y peso, marcas de agua, transportista, placa,
  licencia, motivo de traslado y observaciones. Correo, web y dirección de partida por almacén quedan como parámetros
  por completar en Configuración.

## 6. Seguridad

- Valida **ítem por ítem** lo que debe salir (guía) contra lo que sale: conforme o no conforme con motivo, con foto.
- Registra la **hora de inicio del despacho, de partida y de retorno** del vehículo.
- **Control de vehículos** simplificado: placa, chofer y vehículo en orden; si no, describe qué subsanar y se alerta a Distribución.
- **Cuadro de llegadas** de compras nacionales e importaciones: valida lo que ingresa (cantidad, placa, chofer), con
  foto, y notifica cualquier incidente.
- El **chofer no da conformidad del estado del producto**: la dan Calidad, Distribución y Almacén (permiso
  `distribucion.conformidad_producto`).

## 7. Decisiones técnicas tomadas

1. La naturaleza «información» por perfil no cambia la configuración del tipo de alerta: se calcula por usuario.
2. La alerta importante suena hasta que la tarea se cierra; el usuario puede silenciarla en su equipo.
3. La regularización no reserva stock; liberarla exige una fecha vigente.
4. El estado «Producto observado» se agregó a los estados físicos de stock (antes no se usaba, IF §6.1) por pedido expreso.
5. La recomendación automática usa el precio promedio de nuestras OV del periodo y, sin ventas, el mínimo de lista.
6. Migración `0011` (tablas y columnas nuevas; en bases existentes actualiza el parámetro del precertificado, los
   destinatarios de dos tipos de alerta y la capacidad de las líneas).

## 8. Pendientes o por confirmar

1. Cantidad mínima de cotizaciones para pedir la aprobación de GO (hoy 1).
2. Frecuencias de sonido y de actualización de alertas (60, 120 y 10 s, propuestas).
3. Correo y web de la guía y dirección de partida por almacén (parámetros vacíos).
4. Registros de Calidad «después de producir»: se propuso el formato de cierre del proceso; confirmar sus campos.
5. Lista de feriados (parámetro `feriados`).
