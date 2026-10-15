# Versión 0.7 – Observaciones al demo v0.6 (14-oct-2026)

Cada observación recibida se registra con su implementación y estado. Los datos de demostración son ficticios. Los
formatos recibidos (foto del formato *Seguimiento de control de despacho de producto terminado* y la tabla de capacidad
por línea) se usaron como referencia. Los nombres reales de clientes y personas que figuran en ellos **no** se incorporaron
al repositorio.

Estados: ✅ implementado · ◐ implementado con supuesto por confirmar · ⏳ pendiente (motivo indicado).

## 1. Asistente de Ventas

| Observación | Implementación | Estado |
|---|---|---|
| **A. Inicio/Tablero: ver el detalle de la alerta e indicar su estado** | Cada alerta abre su detalle (qué ocurrió, documento relacionado con enlace, fecha, responsable, estado e historial). Estados de tarea: **Pendiente**, **En ejecución**, **Completada** (con detalle, acción y evidencia: foto o PDF), **Incidencia** y **Desistida/desaprobada**. | ✅ |
| Incidencia sin eliminar ni cerrar la tarea | La incidencia registra situación, acciones, responsable y resolución. La tarea queda en «Incidencia» y no se puede completar mientras siga abierta. El sistema tampoco la cierra automáticamente. Al resolverla, vuelve a su estado anterior. | ✅ |
| Tarea físicamente completada con proceso posterior pendiente | Al completar se puede anotar el proceso posterior pendiente (recepción, contabilización…), que queda visible. | ✅ |
| Informativas con otro mecanismo; solo tareas las que requieren aprobación o atención | Cada tipo de alerta tiene naturaleza **Tarea** o **Informativa**. Las informativas solo se «reconocen». La clasificación inicial es propuesta y se cambia en *Configurar alertas*. | ◐ (clasificación por validar) |
| Asignar responsable; le llega a su inicio y una alerta | «Designar» a una persona o a un cargo de la misma área. El designado recibe la alerta *Tarea designada* y la ve en **Mis tareas** de su inicio. | ✅ |
| **B. Informe Comercial: comportamiento del cliente** | Por cliente: pedidos, atendidos, **% de cumplimiento = atendidos ÷ pedidos × 100**, completos, retrasos, rechazos, modificaciones, penalidad estimada y variaciones (pide más o menos) por producto y por presentación. Incluye el consolidado y el detalle por cliente (cada OV). La alerta *Cliente pide más o menos de lo habitual* usa un umbral configurable (30 %, propuesto). | ◐ (ver pregunta 1) |
| **C. Registrar OV: condición del cliente según el producto pedido** | En la OV, la tabla «Condición del cliente por producto» muestra la vida útil mínima aplicable a ese producto (con la excepción por familia, p. ej. harinas), lotes por SKU y cuántos lotes cumplen. Solo se reservan lotes que cumplen. Si hay stock que no cumple, se alerta el motivo y la acción sugerida: reempaque si solo falla el vencimiento, o producir / ampliar la producción. | ◐ (regla de acción por definir, pregunta 2) |
| Comercial ve solo el avance; Almacén ve las opciones | Comercial ve «Seguimiento del pedido» (% y líneas, y cómo se completa cada una). Las opciones evaluadas, las alternativas y las pre-solicitudes solo las ven Almacén, Jefe y Coordinador de Logística y Gerencia de Operaciones (permiso `ov.opciones`). | ✅ |
| Canal o grupo al registrar la OV | Selector «Canal / grupo de precios» (precargado con el canal de la ficha). El precio mínimo se calcula con el canal elegido y queda en la OV y en la auditoría. | ✅ |
| Historial de auditoría solo Sistemas | El permiso `auditoria.ver` queda exclusivo de Sistemas: la OV ya no muestra el historial a Comercial (ni a otros roles). | ✅ |
| **D. Ficha del cliente** | Hasta 3 celulares y 3 correos; ¿tiene contrato? con carga del contrato (PDF o imagen); certificaciones que pide; penalidades establecidas; vendedor responsable. Búsqueda por cliente/RUC, grupo, canal y vendedor responsable. | ✅ |

## 2. Coordinador de Almacén 1560

| Observación | Implementación | Estado |
|---|---|---|
| Ficha del cliente: modifica solo Comercial; ven Almacén, Distribución, GO y GG | `clientes.editar` solo para roles comerciales; `clientes.ver` para Comercial, Coordinadores de Almacén, Distribución, GO, GG y Sistemas. | ✅ |
| Opciones y pre-solicitudes: las ve y aprueba el Coordinador o las asigna a otra persona | En la pantalla de opciones, «Derivar la revisión» designa la tarea a otra persona de su área, que ve todas las opciones y sus motivos. | ✅ |
| Producción con falta de materia prima: revisar almacenes externos | El análisis de materiales informa el stock en otros almacenes (p. ej. externos). La opción «Producción» queda viable con «trasladar la materia prima antes de producir», sumando el plazo del traslado. | ✅ |
| Retirar todo lo que diga AS-IS o TO-BE | Se retiró de pantallas, mensajes y fuentes visibles (ahora «Diagrama de procesos COPROD-ONE» o «proceso actual»; el estado de parámetro AS-IS pasa a ACTUAL). | ✅ |
| Tablero sin OV con límite de precio ni merma | Secciones del tablero por permiso: `dashboard.precios` (Comercial, GG y, como propuesta, GO), `dashboard.operaciones`, `dashboard.merma` (Producción, Logística, GO y GG). | ✅ |
| Informes: no Comercial, Producción ni Distribución; sí Reempaque y movimiento de stock de su almacén | Permisos por informe. Nuevo **Informe de movimiento de stock del almacén**: evolución por carga de SAP (pico), bajas mayores al 20 %, demoras (traslados y picking), productos que se acercan al stock de reserva según el plazo de compra (fecha límite para pedir) e incidencias con enlace al detalle (conteos, recepción de traslados e incidencias de tareas). Cada coordinador ve solo sus almacenes. | ✅ |
| Alertas: tipos y áreas de su área; GO, GG y Sistemas ven todo | Los filtros de tipo y área muestran solo los de su área o los que se comunican con ella. La bandeja y el contador siguen la misma regla. GO pasa a ver todo. | ✅ |
| Ver el detalle (formato) de la pre-solicitud antes de aprobar | «ver formato» en cada pre-solicitud: traslado (nueva vista), reempaque, producción y compra. | ✅ |
| Ver el detalle antes de validar el picking pre-asignado | El botón de validar está al final, después del detalle, y exige marcar «Revisé el detalle». | ✅ |
| OV relacionada en lista desplegable y opcional (solicitud de producción) | Lista desplegable con las OV abiertas, con la opción «Sin OV». | ✅ |
| La lista de materiales la aprueba el Asistente o Jefe de Producción, no Almacén | Nuevo permiso `produccion.bom_aprobar` (Jefe y Asistente de Producción). El Asistente también puede cargar o modificar la lista. | ✅ |
| Almacén sin acceso a registros de Calidad (formatos) | Se retiró `calidad.ver` a los Coordinadores de Almacén. | ✅ |
| Alerta de fumigación a Almacén, Calidad, Logística y GO | Destinatarios ampliados en *Fumigación iniciada/finalizada* y *Fumigación próxima*. | ✅ |
| Compras de materia prima y de granel con Gerencia de Operaciones | `tipos_compra_requieren_go` = MP y GR. | ✅ |

## 3. Jefe Comercial

| Observación | Implementación | Estado |
|---|---|---|
| Tablero solo con temas de su área | Sin tiempos de preparación, compras/producción pendientes, diferencias de inventario ni merma. | ✅ |
| Alertas: confirmar/aprobar, desistir/desaprobar, designar (solo su área) | «Confirmar / aprobar» y «Desistir / desaprobar» aplican la misma regla de negocio de cada pantalla: precio de la OV, traslado, pre-solicitud y evaluación de reempaque, compras (Logística y GO), modificación de OV y transporte externo. El sistema deriva el siguiente paso al área que corresponde (p. ej., aprobar el precio → evaluación → Almacén recibe las opciones). Solo se designa dentro de la misma área. | ✅ |
| Motivo obligatorio al aprobar por debajo o fuera del parámetro | Obligatorio al aprobar un precio en el límite, bajo el mínimo o bajo el costo, y en toda desaprobación. Desaprobar el precio mantiene la OV detenida. | ✅ |
| «En ejecución» y «Completar» solo cuando hay responsable | Se muestran solo si la tarea está designada; antes se debe «Tomar» o «Designar». | ✅ |
| Cargas de archivos: lista desplegable del tipo | Selector «Nueva carga: tipo de archivo». | ✅ |
| Lista de precios: quitar «demo_price_list xlsx» | Se retiró el nombre del archivo. | ✅ |
| Importar informe Excel o PDF y extraer productos compatibles (competencia y sustitutos) | **Importar informe**: lee Excel o PDF, extrae solo las filas de productos que ofrecemos (competencia directa = mismo producto base) o de sustitutos (parámetro `productos_sustitutos`, pendiente de definir por Comercial) y calcula S/ por kg según la presentación del texto. Nada se registra sin revisar y confirmar. | ◐ (lista de sustitutos pendiente) |
| Registro de precios desde Importaciones, Compras y Comercial; análisis en dos niveles | Formulario de precios en Importaciones (importación), Compras (compra nacional) y Comercial (competencia, sustitutos, referencia). **Análisis en dos niveles**: (1) a cuánto compramos (nacional vs importación, evolución, conviene importar o comprar en el país); (2) a cuánto vendemos (nuestro S/ por kg y volumen frente a competidores y sustitutos, con lectura de quién gana mercado). | ✅ (sin volumen de la competencia: no hay dato) |
| Costo de reposición | No se implementa: el usuario indicará la definición más adelante. | ⏳ |
| Informes: solo Comercial y con penalidades | Permisos por informe; penalidad estimada por cliente y total en el informe Comercial. | ✅ |

## 4. Supervisor de Calidad

| Observación | Implementación | Estado |
|---|---|---|
| No ver las opciones de la OV, salvo lo derivado como reempaque | Sin `ov.opciones`. Ve el reempaque derivado en su detalle. | ✅ |
| Lote distinto del producto | El registro tiene «Producto» y «Lote en stock» (filtrado por el producto) por separado, o lote en texto. | ✅ |
| Certificado con fechas de producción y vencimiento y marca autocompletadas | Se toman del lote o, si faltan, de la liquidación. La marca se toma del maestro o de la descripción del artículo. | ✅ |
| Análisis organoléptico, fisicoquímico y sanidad-aspecto en cada evaluación | Nuevo registro *Análisis del lote para el certificado*. Cualquier persona de Calidad lo llena. Los certificados en borrador del lote se actualizan solos y los nuevos ya lo incluyen. | ✅ |

## 5. Coordinador de Distribución

| Observación | Implementación | Estado |
|---|---|---|
| Informe: salidas a tiempo, desviación plan vs ejecutado, gasto en transporte externo y estibas | % de transportes a tiempo (contra la hora de salida programada o la fecha); por ruta: paradas planificadas vs entregadas, tiempo y km estimados vs reales; gasto en transporte externo (y S/ por kg) y en estibas. Nuevos datos por ruta: hora de salida programada, km de salida y retorno, costo de transporte externo y de estiba. | ✅ |
| Alertas de su área y de lo que modifica su plan; no merma | Filtro por área (sin merma). *Cambio de OV* (p. ej. fecha de entrega) ahora también le llega. | ✅ |
| Incidencias: OV del día en lista desplegable; entrega total o parcial; productos devueltos con motivo | Lista con las OV llevadas en las rutas del día (fecha elegible). Entrega total / parcial / no entregada. Si es parcial, la tabla de productos de la guía permite indicar lo devuelto y el motivo; lo devuelto regresa como «Pendiente de revisión» y lo demás queda entregado. | ✅ |
| SOAT, impuestos, multas; combustible; quién tenía el vehículo; mantenimiento y km; fotos de salida y retorno | **Seguimiento de flota** y detalle por vehículo: documentos con vencimiento y alerta (anticipación 15 días, propuesta), multas con el conductor y la ruta de ese día, «¿quién tenía el vehículo?» por fecha, cargas de combustible con rendimiento km/galón y S/ por km, mantenimientos con alerta por km (margen 500 km, propuesto) o fecha. Foto del vehículo al salir (obligatoria antes de autorizar la salida, vehículos propios) y al retornar, con kilometraje. | ✅ |
| Folio con guía, certificados y factura cargada por Facturación | «Folio completo»: guía, archivo de la guía y de la factura (imagen o PDF) y cada certificado, uno por página. | ◐ (los PDF y certificados embebidos pueden requerir imprimirse por separado según el navegador) |

## 6. Auxiliar / Asistente de Almacén, Líder Operativo y Montacarguista

| Observación | Implementación | Estado |
|---|---|---|
| Auxiliar y Líder sin informe Comercial | Permisos por informe. | ✅ |
| Líder: alertas de su área o relacionadas | Filtro por área. | ✅ |
| Preprogramación del picking al Líder y al Coordinador con detalle y asignación | Al quedar la OV lista, el sistema programa el picking por almacén (1 día antes de la fecha comprometida, propuesto) con el auxiliar de menor carga y avisa al Líder y al Coordinador. **Programación de picking** (diaria y semanal) con detalle (tipo, mercadería, cantidad, lote, fechas, asignados); se asigna a una persona o a un grupo del mismo almacén y se puede modificar. | ✅ |
| Dotación por almacén | Usuarios demo con almacén asignado. 1560: 4 auxiliares, 2 líderes y 2 montacarguistas. 1524: 1 auxiliar y 1 montacarguista. | ✅ |
| Auxiliar: programación diaria y semanal; registra lo que llena a mano, foto y «listo» | Ve solo lo suyo. Inicia con foto, registra por lote lo despachado, el lote y las fechas de producción y vencimiento (precargadas del lote; si difieren del sistema se alerta) y marca «Todo listo para trasladar al despacho» con foto, lo que avisa al montacarguista. **Formato imprimible** *Seguimiento de control de despacho de producto terminado* generado por el sistema. | ◐ (ver pregunta 4) |
| Planeación del traslado al montacarguista | *Traslado autorizado* y *Llegada programada de traslado* también le llegan. | ✅ |
| Montacarguista: no asigna; inicia y termina con foto y observación | Se le retira `alertas.gestionar`. En sus tareas: «Inicié la tarea» con foto y «Terminé la tarea» con foto y observación. | ✅ |

## 7. Jefatura de Producción

| Observación | Implementación | Estado |
|---|---|---|
| Sin informe Comercial; sí Producción y Reempaque | Permisos por informe. | ✅ |
| Capacidad vs producido y programado vs ejecutado, por tipo de línea, periodo configurable, evolución, caídas, demoras, atención y paradas | Usa la tabla de capacidades (IQ+CIMB 25 500; TRUER 12 750; SEL. MANUAL 4 250; RAUMAK 1 y 2 18 700; RAUMAK 3 29 750; ENV. MANUAL 2 550 kg/día) por proceso (Selección / Envasado). Agrupación diaria, cada N días o mensual. Muestra uso de capacidad, programado vs ejecutado, caídas mayores al 20 %, tiempo de atención de solicitudes, solicitudes demoradas y paradas de línea (nuevo dato del parte: minutos y motivo). | ◐ (ver pregunta 3) |
| Revisar y modificar la lista de materiales | Jefe y Asistente la aprueban u observan (indicando la modificación) y pueden cargar la nueva lista. | ✅ |
| Liquidación por Excel o desde SAP | Botón visible «Cargar liquidación (Excel o exportación de SAP)». | ✅ |
| Programación diaria, semanal y mensual, modificable manualmente | La programación registrada se modifica con motivo (0 la elimina); queda en el historial y en la auditoría. | ✅ |

## 8. Decisiones técnicas tomadas

1. Los estados internos de las alertas pasan a los estados de tarea pedidos. La migración 0006 convierte los
   existentes: NUEVA o ASIGNADA → PENDIENTE, EN_ATENCION → EN_EJECUCION y CERRADA → COMPLETADA.
2. Cuando el sistema detecta que la condición desapareció (p. ej., se aprobó desde su pantalla), completa la tarea,
   salvo que tenga una incidencia abierta.
3. GG y GO también designan solo dentro de su área («Gerencia»), por la regla general de respetar la línea de
   comunicación.
4. La sincronización de catálogos (`python -m app.cli init` sobre una base existente) agrega los tipos de alerta,
   permisos y parámetros nuevos sin modificar lo ya configurado.
5. Para leer PDF se agregó `pypdf` (librería liviana, solo Python).

## 9. Preguntas para continuar

1. **Cumplimiento del cliente:** la fórmula indicada fue «pedidos realizados ÷ atendidos × 100», que da más de 100 %.
   Se implementó **atendidos ÷ pedidos × 100**, donde atendido = salió del almacén. ¿Es correcto, o «atendido» debe ser
   «entregado completo»?
2. **Condición del cliente no cumplida:** ¿se confirma la regla «reempaque si solo falla el vencimiento; producir o
   ampliar la producción en los demás casos»? ¿Hay otros casos (p. ej. lotes por SKU)?
3. **Capacidad por línea:** confirme la correspondencia IQ+CIMB = Cimbria, RAUMAK 1 y 2 = R1 y R2, RAUMAK 3 = R3.
   ¿«CA» significa capacidad? ¿Qué días no se opera (para calcular la capacidad del periodo)?
4. **Formato de picking:** junto a la descripción hay números escritos a mano (p. ej. 19, 58, 45). ¿Qué representan
   (ubicación, pallet, saldo)? Se agregarán como columna.
5. **Naturaleza de las alertas:** revise la clasificación propuesta (tarea o informativa) en *Configurar alertas*.
6. **Productos sustitutos:** indique, por producto base, qué productos se consideran sustitutos.
7. **Anticipaciones propuestas:** picking 1 día antes de la fecha comprometida; aviso de documentos del vehículo
   15 días antes; aviso de mantenimiento 500 km antes; variación de compra del cliente ≥ 30 % en 90 días.
8. **Costo de reposición:** queda a la espera de su definición.

## 10. Respuestas del 15-oct-2026 aplicadas

| # | Respuesta del usuario | Aplicación |
|---|---|---|
| 1 | «Debe ser entregado completo» | Cumplimiento = OV **entregadas completas** (estado ENTREGADA y cada línea recibida por completo) ÷ pedidos × 100. Los informes muestran por separado *Despachados* (salieron del almacén) y *Entregados completos*. |
| 2 | Producción 1, reempaque 2, traslado externo 3, compra 4 | En la condición por producto de la OV, la acción ya no es una sola: se listan las **opciones aplicables en ese orden** (el del parámetro `orden_presolicitudes`). Producir si hay lista de materiales («revisar materiales» si no es factible); reempaque si lo único que falla es el vencimiento; traslado si un almacén externo tiene lotes que cumplen y están libres; compra siempre. |
| 3 | Sábados hasta mediodía; domingos y feriados no se opera | Parámetros `dias_operacion` (lunes a viernes 1, sábado 0,5, domingo 0) y `feriados` (lista de fechas, vacía). La capacidad del periodo se calcula con ese factor por día. |
| 4 | Los números a mano son la información para seguimiento del stock y la emisión de certificados | Se dedujo que son **bultos (cajas)**: coinciden con lo solicitado ÷ 12 (228 → 19, 696 → 58). Se agregó *unidades por bulto* al artículo (catálogo) y la columna **BULTOS** al registro y al formato de picking (se calcula si el artículo tiene unidades por bulto; el auxiliar puede corregirla). **Por confirmar** (ver §11). |
| 5 | Los sustitutos se remitirán; debe haber un apartado para subirlos en Excel o de manera individual | Nueva pantalla **Comercial → Análisis de precios de mercado → Productos sustitutos** (`/ov/mercado/sustitutos`): alta individual, carga por Excel (columnas *Producto base*, *Sustituto*, opcional *Observación*), listado y desactivación. Registra Comercial (`costos.cargar`); consultan quienes ven costos. Reemplaza al parámetro `productos_sustitutos`, que se retiró del catálogo. |
| 6 | Alerta de variación de compra configurable por canal o cliente en el panel de configuración | Nueva sección **Configuración → Alerta de variación de compra** (Sistemas, `config.editar`): reglas por canal o por cliente con umbral %, periodo en días y si genera alerta. Precedencia: cliente > canal > parámetros generales; un campo vacío hereda. El informe del cliente muestra el umbral aplicado y su origen. Además quedan **DEFINIDOS** los valores confirmados: picking 1 día antes, aviso de documentos del vehículo 15 días, aviso de mantenimiento 500 km. |
| 7 | «De acuerdo» con la clasificación de las alertas | La naturaleza (tarea o informativa) propuesta se mantiene; puede ajustarse en *Configurar alertas*. |

Cambios técnicos: migración `0010` (columnas `products.unidades_por_bulto` y `picking_records.bultos`; tablas
`product_substitutes` y `purchase_variation_rules`; marca DEFINIDO de `dias_picking_antes_despacho`). Los parámetros
retirados del catálogo (`dias_no_operativos`, `productos_sustitutos`) no se borran de una base existente: dejan de
mostrarse en Configuración y ya no se usan. Pruebas nuevas en `tests/test_respuestas_15oct.py` y en `tests/test_web.py`.

## 11. Preguntas que siguen abiertas

1. **Capacidad por línea:** confirme la correspondencia IQ+CIMB = Cimbria, RAUMAK 1 y 2 = R1 y R2, RAUMAK 3 = R3.
2. **Bultos del picking:** ¿los números escritos a mano son cajas o bultos (lo solicitado ÷ unidades por caja, p. ej.
   12)? Indique las unidades por bulto de cada artículo o envíe la relación para cargarla. ¿Deben figurar en el
   certificado? Si es así, ¿en qué campo?
3. **Feriados:** envíe la lista de feriados del año para cargarla en el parámetro `feriados`.
4. **Productos sustitutos:** pendiente de envío (la pantalla de carga ya está disponible).
5. **Umbral de variación de compra:** el general sigue en 30 % y 90 días (PROPUESTO) hasta su validación.
6. **Costo de reposición:** queda a la espera de su definición.
