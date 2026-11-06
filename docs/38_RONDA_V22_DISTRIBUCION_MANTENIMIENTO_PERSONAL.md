# Ronda V22 (06-nov-2026): distribución manual, personal, devoluciones, mantenimiento, limpieza y nuevos perfiles

Todos los datos de ejemplo son ficticios: clientes «DEMO», placas DEM-/TER-, «Colaborador demo N» y fotos de muestra
generadas con texto.

## 1. Qué se pidió y dónde quedó

| Pedido | Dónde está en el sistema | Estado |
|---|---|---|
| Asignar rutas a mano a los choferes | Distribución → **Cuadro de despacho y ruta manual** → «Nueva ruta manual» | Hecho |
| Cambiar rutas programadas | Ruta → «Modificar ruta» | Hecho (ver nota 1) |
| Traslados entre almacenes dentro de la programación | En la ruta manual y en «Modificar ruta» | Hecho (ver nota 2) |
| Peso real que puede cargar el vehículo y peso que suele cargar | Distribución → **Carga de los vehículos** | Hecho (ver nota 3) |
| Varios auxiliares de despacho por ruta (botón +) | Ruta manual y «Modificar ruta» → «Agregar auxiliar» | Hecho (ver nota 4) |
| Rutas manuales del día, más presentables, con guías y valor | **Cuadro de despacho** | Hecho (ver nota 5) |
| Vacaciones y descanso médico (desde/hasta), faltas justificadas con motivo e injustificadas | Distribución → **Disponibilidad del personal** (también Mantenimiento y Gestión Humana) | Hecho (ver nota 6) |
| Devoluciones contrastadas con la guía, con foto o video si hay observación | Almacén → **Devoluciones por recibir** | Hecho (ver nota 7) |
| Foto del chofer de lo que queda en el vehículo (pernocte) | Mis entregas → «Pernocte» y ruta → «Pernocte (foto)» | Hecho |
| Zonas nuevas de mantenimiento | Zonas de la planta | Hecho (ver nota 8) |
| Perfil Jefe de Mantenimiento | Usuario `jefe.mantenimiento` | Hecho (ver nota 9) |
| Tickets de todas las áreas | Tickets de averías y solicitudes | Hecho |
| Máquinas: configuración, calibración y piezas | Mantenimiento de planta → **Máquinas de producción** | Hecho (ver nota 10) |
| Preventivos y correctivos asignados, foto antes y después, tiempos, informe, cronograma | **Trabajos** e **Informe de mantenimiento** | Hecho (ver nota 11) |
| Alertas 7, 3 y 0 días antes, configurables | Panel de mantenimiento → «Configuración de avisos» | Hecho |
| Limpieza programada con check por zona | **Limpieza** (Jefe) y **Mis zonas de limpieza** (personal) | Hecho (ver nota 12) |
| Paradas de producción con una o más fotos o videos | Parte de producción → «Pausar» | Hecho |
| Carga llevada por un vendedor u otro trabajador | Ruta manual → «Otro trabajador» | Hecho (ver nota 13) |
| Sugerencias automáticas de eficiencia | **Sugerencias de eficiencia** e inicio de Gerencia | Hecho (ver nota 14) |
| Embudo comercial adaptado | Comercial → **Embudo comercial** | Hecho (ver nota 15) |
| Botón superior «Reportar avería» | En todas las pantallas | Hecho (ver nota 16) |
| Checklist vehicular del chofer sobre la imagen del vehículo | Checklist vehicular | Hecho (ver nota 17) |
| Jefe de Administración y Finanzas: gastos por área, desempeño, informes; alertas solo si se supera el presupuesto | **Gastos y desempeño por área** | Hecho (ver nota 18) |
| Perfil Gestión Humana: solo asistencia por área | Usuario `gestion.humana` | Hecho (ver nota 19) |
| Inicio de Gerente General y Gerente Adjunto con los indicadores de cada área | Inicio | Hecho (ver nota 20) |
| Datos ficticios de un día de operación con casuísticas | `python -m app.cli demo-dia` | Hecho (ver secciones 3 y 4) |

**Notas a la tabla**

1. **Cambiar rutas programadas.** Se puede cambiar el vehículo y el chofer, agregar o quitar OV y traslados, y agregar o
   quitar auxiliares. Si la ruta ya estaba confirmada, el motivo es obligatorio. Cada cambio queda en el rastro de la ruta.
2. **Traslados en la programación.** Solo se pueden programar traslados autorizados o solicitados, y un traslado no puede
   estar en dos rutas a la vez. Su peso se suma al de la ruta.
3. **Peso del vehículo.** Se manejan tres datos:
   - el peso permitido (el de la tarjeta);
   - la capacidad real;
   - la carga habitual.

   Además se puede registrar el peso real (balanza) de cada ruta. Si se supera lo permitido, llega la alerta
   «RUTA_SOBRECARGA».
4. **Auxiliares.** No se pueden elegir auxiliares que tengan una ausencia registrada para ese día.
5. **Cuadro de despacho.** Se organiza por vehículo: quién lo lleva, auxiliares, clientes (varios por carro), OV, guías,
   distrito, peso, % de uso y valor de lo que sale (tomado de las OV). Incluye los traslados y se puede descargar en Excel
   o imprimir.
6. **Disponibilidad.** Una ausencia:
   - impide asignar a la persona en esas fechas;
   - avisa a Distribución de las rutas que ya tenía, con los clientes que lleva;
   - completa sola la asistencia del colaborador.
7. **Devoluciones.** El plazo de recepción es el mismo día si llegan hasta las 17:00 (configurable); si no, al día
   siguiente. Las que pasan el plazo generan alerta. Si hay diferencias, se alerta a Logística, Distribución y Calidad.
8. **Zonas.** Selección Manual, Contenedor de fumigación 1 y 2, Línea Cimbria, Línea Truer, Almacén Producto Terminado
   (Zona A, Zona B, Miniracks y Zona C).
9. **Jefe de Mantenimiento.** Tiene acceso de consulta a Producción, al mantenimiento de flota, a la fumigación con Calidad
   y a la asistencia de su personal.
10. **Máquinas.** Además de la bitácora, muestra los minutos de parada por mantenimiento o avería de cada línea, según los
    partes de producción.
11. **Trabajos.** Se asignan al técnico con anticipación o el mismo día. Sin foto de antes no se inicia y sin foto de
    después no se termina. El informe sale en Excel y en versión imprimible/PDF. El cronograma se carga en Excel.
12. **Limpieza.** El Jefe puede modificar asignaciones, ver el desempeño por persona y zona, agregar o renombrar zonas y
    registrar o editar al personal.
13. **Otro trabajador.** Se registra el nombre, el área, los datos del vehículo y el motivo.
14. **Sugerencias.** Entre otras: uso frecuente de transporte tercero (compra o alquiler más largo), sobrecargas, averías
    repetidas, paradas de máquinas, devoluciones, faltas, limpieza incompleta y trabajos vencidos.
15. **Embudo.** Ver la nota de la sección 5: la imagen de referencia no llegó.
16. **Reportar avería.** Las averías (luz, gasfitería, máquinas, etc.) van a Mantenimiento; las solicitudes de tintas,
    laptops, celulares, impresoras y red van a Sistemas. Se indica motivo, lugar, foto o video y si es urgente.
17. **Checklist.** Usa las imágenes del Excel del checklist (sección 5).
18. **Jefe de Administración y Finanzas.** Ya no recibe las alertas de la Coordinación de Finanzas ni avisos de
    escalamiento. Mantiene todas las funciones de Finanzas.
19. **Gestión Humana.** Ve el reporte de asistencia de todas las áreas y la disponibilidad del personal.
20. **Inicio de Gerencia.** Muestra Comercial, Logística y Almacén, Distribución, Producción, Mantenimiento y Limpieza,
    Personal y Finanzas, más las principales sugerencias.

## 2. Reglas nuevas (marcadas como PROPUESTO cuando falta confirmarlas)

- **Rutas automáticas y manuales.** Al evaluar una OV, el sistema la sigue poniendo en una ruta *propuesta*. Distribución
  puede tomarla para una ruta manual: sale de la propuesta automática y, si esta queda vacía, se anula. Una OV que ya está
  en una ruta confirmada o en otra ruta manual no se puede tomar.
- **Sobrecarga** (`sobrecarga_tolerancia_pct`, PROPUESTO = 0 %). Se alerta cuando el peso supera el permitido o la
  capacidad real. No se bloquea, porque en la práctica ya ocurre y se necesita el registro para el análisis.
- **Plazo de recepción de devoluciones** (`devolucion_hora_corte`, PROPUESTO = 17:00).
- **Avisos de preventivos** (`mant_alerta_dias` = 7, 3, 0). Los modifica el Jefe de Mantenimiento desde su panel.
- **Categorías de tickets** (`ticket_categorias`, PROPUESTO): se pueden ajustar en Configuración.
- **Costo mensual de referencia por tipo de unidad** (`costo_mensual_unidad_ref`, vacío). Si se registra, la sugerencia
  de transporte tercero calcula el ahorro de comprar o alquilar por periodo. El sistema no inventa ese costo.
- **Perfiles nuevos:** Jefe de Mantenimiento, Técnico de Mantenimiento, Personal de Limpieza y Gestión Humana.
  - Los técnicos y el personal de limpieza son colaboradores del área Mantenimiento.
  - Si se les vincula una cuenta, ven sus trabajos o zonas en el celular.
  - Sin cuenta, el Jefe registra por ellos.
- **Estados de asistencia:** se agregaron «FALTA JUSTIFICADA» y «FALTA INJUSTIFICADA».

## 3. Cómo cargar el día de operación ficticio

En el servidor de pruebas (no en producción):

```bash
python -m app.cli reset-demo     # solo SQLite local: borra y recrea la demostración
python -m app.cli demo-dia       # agrega el día de operación con todas las casuísticas
```

Si la base de demostración ya existe, basta con `python -m app.cli demo-dia`: agrega las cuentas nuevas y el día. Si el
día ya estaba cargado, no hace nada.

La contraseña de todas las cuentas de demostración es la de siempre de la demo (`Demo2026!`).

## 4. Recorrido por perfil (un día normal de operación)

| Usuario | Qué revisar | Casuísticas que verá |
|---|---|---|
| `gerente.general` / `gerente.adjunto` | Inicio | Indicadores por área (venta del mes, OTIF, rutas de hoy con 1 sobrecarga, tickets abiertos y urgentes, trabajos vencidos, limpieza 3/10, 4 personas no disponibles, Distribución sobre su presupuesto) y las sugerencias |
| `coord.distribucion` | Cuadro de despacho; Ruta #1; Carga de los vehículos; Disponibilidad del personal | Ver detalle debajo de la tabla |
| `conductor1` | Mis entregas → Checklist vehicular y Pernocte | Toque una parte del camión en la imagen, elija «Espejo izquierdo» y escriba la falla |
| `coord.almacen` | Devoluciones por recibir | Una a tiempo, una vencida (alerta), una ya recibida con un saco menos y otro roto (foto) |
| `jefe.mantenimiento` | Panel; Tickets; Trabajos; Informe; Máquinas; Limpieza; Asistencia | Ver detalle debajo de la tabla |
| `tecnico.mant1` | Mis trabajos | Trabajos asignados con «foto ANTES» para iniciar y «foto DESPUÉS» para terminar |
| `limpieza1` | Mis zonas de limpieza | Zonas del día con el botón «Limpieza realizada» |
| `sistemas` | Tickets → Sistemas | Tóner (resuelto), laptop que no enciende (urgente), sin wifi en despacho |
| `jefe.finanzas` | Inicio; Gastos y desempeño por área; Alertas | Solo alertas de **presupuesto superado** (Distribución: combustible y mantenimiento sobre lo presupuestado) |
| `gestion.humana` | Asistencia por área; Disponibilidad del personal | Faltas injustificadas repetidas de un colaborador (aparece en las sugerencias) |
| `jefe.ventas` | Embudo comercial | 12 oportunidades → contactadas → cotizadas → negociación → 3 ganadas → OV → entregadas; 2 perdidas con motivo; por ejecutivo |
| `jefe.produccion` | Máquinas de producción; Partes | Parte de hoy en R1 pausado con foto; la Cimbria con 330 min de paradas por mantenimiento |
| Cualquier usuario (p. ej. `montacarguista`) | Botón «Reportar avería» | Crear un ticket con foto y ver cómo le llega al Jefe de Mantenimiento |

**`coord.distribucion`** verá:

- 6 rutas del día:
  - una con 3 clientes y 2 auxiliares;
  - una con sobrecarga (520 kg pesados en una unidad de 450 kg permitidos);
  - una que lleva el ejecutivo comercial en su camioneta, con motivo;
  - un tercero que lleva una OV y un traslado entre almacenes;
  - dos propuestas automáticas del sistema, una sin chofer porque el Chofer 3 está de vacaciones y el Chofer 4 con
    descanso médico.
- La ruta #1 con un cambio registrado con su motivo.
- Una ruta de ayer con la foto del pernocte.

**`jefe.mantenimiento`** verá:

- 3 tickets abiertos, uno urgente, y uno ya convertido en trabajo.
- Trabajos en todos los estados:
  - programados a 7, 3 y 14 días;
  - el de hoy, una fumigación coordinada con Calidad;
  - uno en proceso con foto de antes;
  - uno terminado con fotos de antes y después;
  - 3 vencidos.
- Los avisos 7/3/0.
- La bitácora de máquinas: calibración de la Cimbria, configuración de la Truer y cambio de pieza en R1.
- La limpieza de la semana, con una zona que suele quedar incompleta.
- El personal: un técnico con vacaciones programadas.

## 5. Límites y pendientes

- **Imágenes que no llegaron.** Las dos imágenes adjuntas (el cuadro de rutas que arma Distribución en su Excel y el
  embudo de la empresa de autos) no llegaron a esta conversación.
  - El cuadro de despacho y el embudo se diseñaron con lo descrito: por vehículo, varios clientes, guías y valor; embudo
    de la oportunidad a la OV entregada.
  - Si se reenvían, se ajustan columnas y etapas a ese formato.
- **Imágenes del checklist.** Se usaron las imágenes de cada pestaña del Excel del checklist (camión, furgón, camión de
  cabina corta, tracto y camioneta). Se dejó fuera una que trae la marca de agua de Shutterstock; para el tracto se usan
  los dibujos de línea del mismo Excel. En Flota se elige la imagen de cada vehículo; si no se elige, se deduce del tipo
  de unidad.
- **Videos.** Se aceptan videos en las paradas, devoluciones, tickets y trabajos (hasta 40 MB por envío). No se
  comprimen: conviene grabar videos cortos.
- **Traslados en ruta.** Viajan en la ruta, pero su salida y recepción siguen el flujo existente de traslados
  (salida y recepción por Almacén).
- **Sin conexión productiva.** Nada de esta ronda se probó contra SAP ni contra la base productiva.
