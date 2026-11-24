# Ronda V70 (24-nov-2026): semáforo de inventarios, lotes, carga de unidades, recorridos y OV fuera de horario

Fuentes: las observaciones del usuario con capturas (reempaque, solicitar movimiento, lotes, asignación de picking), la
presentación del análisis de abastecimiento de una familia (presentación a Gerencia, 16 láminas) y el Excel de control
de producción que no se podía subir. Los archivos solo se usaron para entender el pedido; no se guardan en el
repositorio. Las pruebas usan solo datos ficticios.

## Qué se hizo

### Excel de programación de producción (no se dejaba subir)
- **Causa.** La pestaña PROGRAMACION tiene filas a medio llenar: con cantidad y producto, pero sin fecha (filas 52 y
  53 del archivo). La carga se detenía en la primera con «Fila 52: fecha no válida (None)» y no cargaba nada.
- **Ahora:**
  - esas filas se informan («sin fecha») y las demás se cargan;
  - una línea con un nombre no reconocido tampoco detiene la carga: la fila se informa;
  - si una fila falla al guardarse (por ejemplo, una regla del plan), se informa y las demás siguen.
- El archivo pesa 4,3 MB y está dentro del límite (40 MB). Con la base de demostración se lee en unos 3 segundos.
- Las filas cuyo producto no coincide con el maestro de artículos se siguen informando con su número de fila. En
  producción, el maestro es el de SAP.

### Semáforo de inventarios (para todos)
- Menú **Panel → Semáforo de inventarios**: lo ven todos los perfiles.
- Sigue la presentación de Operaciones a Gerencia. Por producto y agrupado por familia muestra:
  - **stock utilizable**;
  - **llegadas**: órdenes de compra abiertas de SAP, en su fecha de entrega;
  - **OV abiertas**: lo que falta despachar, incluido lo vencido;
  - **saldo** = stock + llegadas − OV;
  - **sin stock el**: se recorre día a día con las OV en su fecha y las llegadas en la suya;
  - **cobertura** en días;
  - **stock de seguridad** y **mínimo a comprar o producir**.
- **Estados:**
  - Rojo: no cubre las OV.
  - Temporal: se queda sin stock hasta que llegue lo pedido.
  - Ámbar: cubre las OV, pero queda bajo el stock de seguridad.
  - Verde: cubre las OV y el stock de seguridad.
- **Stock de seguridad** = z × desviación de la venta mensual de 12 meses × √(plazo ÷ 30).
  - z sale del parámetro «semaforo_z» (1,65 = 95 %).
  - El plazo es el de la categoría de reposición de cada producto o, si no tiene, «semaforo_plazo_dias».
  - Es el mismo método que usa la presentación.
- Filtros por familia, tipo, estado y producto. Se descarga en Excel.

### Rotación y stock de seguridad (Almacén)
- Menú **Almacén → Rotación y stock de seguridad**, por familia o por producto. Muestra:
  - venta mensual en kg de 12 meses frente al año anterior (gráfico);
  - mes pico y mes más bajo, y las semanas con más salida;
  - reparto por día de la semana;
  - **presentaciones preferidas** y productos más vendidos;
  - **clientes habituales** (compran en 3 o más de los últimos 6 meses) y **ocasionales**;
  - stock de seguridad de la familia en kg y en días de venta.
- La venta sale de las guías de SAP o, si no hay, del historial cargado. Los clientes solo se ven con las guías.

### Stock y lotes
- **Filtro por almacén** junto a la tabla de lotes (botones por almacén), además del filtro de arriba.
- **Cambio de estado total o parcial.** En «Cambiar estado» se elige «Todo el lote» o «Solo una parte».
  - Si es parcial, se indica la cantidad y la ubicación de esa parte.
  - La parte queda como un segmento del mismo lote con el nuevo estado. Si ya había un segmento en ese estado, se
    suma a él.
  - Lo reservado para OV no se toca: el cambio parcial de un lote disponible solo puede tomar la parte libre.
  - Un lote bloqueado solo lo libera Calidad, igual que antes.
- **Reglas de Calidad por cliente.** En «Clientes (Calidad)» se elige una de dos reglas y se agregan los clientes que
  hagan falta con «+ cliente»:
  - «Solo se despacha a…»;
  - «Bloqueado para…».
  - La regla se aplica a todo el lote (todos sus segmentos).
  - El sistema no reserva ni deja picar ese lote para un cliente que la regla no permite.
  - Las reservas activas que la regla ya no permite se liberan y la OV se reevalúa.
  - La define Calidad (permiso «lote.reglas_clientes», dado a los perfiles que liberan lotes).
- Se corrigió que la fecha de producción salía pegada a «fechas» («01/03/2025fechas»).

### Líder Operativo y Supervisor
- **Indicadores de pedidos y operación** (Almacén → Indicadores):
  - pedidos de hoy y de mañana por etapa (OV y kg);
  - OV atrasadas con sus días de atraso;
  - pedidos de última hora por validar;
  - picking del día y tiempo promedio de picking (7 días);
  - movimientos pendientes, en curso y hechos hoy, con su tiempo promedio;
  - reempaques abiertos;
  - OTIF del mes.
  - Lo ven el Líder Operativo, el Asistente, el Supervisor y el Coordinador de Almacén.
- **Reempaque**:
  - el Líder Operativo y el Asistente pueden ver, solicitar y ejecutar reempaques, y ven el informe;
  - el Supervisor también ejecuta.
- **Producción en tiempo real**: el Supervisor y el Coordinador de Almacén ven el monitoreo (el Líder ya lo veía).
  Hay un acceso directo en el menú de Almacén.
- **Más indicadores** para el Líder: nivel de servicio (OTIF), desempeño del equipo y tablero de operaciones.

### Reempaque por cliente, fecha de despacho y OV
- La lista muestra la OV (con enlace a su detalle), el cliente y la fecha de despacho. Se filtra por cliente, OV y
  rango de fechas de despacho.
- La vista «Agrupado por OV» junta los reempaques de cada OV, con su cliente y fecha de despacho. Cada uno abre su
  detalle.

### Solicitar movimiento
- **Producto filtrado por lo que se mueve.**
  - Pallet de PT o muestra: solo producto terminado.
  - Granel: solo granel.
  - Materia prima: solo MP.
  - Remanente: MP o granel.
  - «Otros productos en el mismo movimiento» sigue el mismo filtro.
- **Se escribe y van saliendo las opciones** (código o nombre), en lugar de una lista larga.

### Asignar personas (nombres y celular)
- **Las listas para elegir varias personas** («con Ctrl») ahora son casillas grandes con buscador, cómodas en el
  celular. Aplica en todo el módulo (movimientos, perfiles adicionales, alertas, vendedores de SAP, carga).
- **Nombres en lugar de usuarios.** Las listas ya muestran el «nombre» de cada usuario. En producción varios usuarios
  tienen como nombre su usuario (por ejemplo, aux.almacen2). En Administración → Usuarios ahora sale un aviso con
  esos usuarios y su casilla de nombre marcada, para completar los apellidos y nombres.

### Carga de unidades (chofer ↔ Almacén)
- Menú **Carga de unidades** (Almacén y Distribución). El circuito:
  1. **El chofer avisa que la unidad está lista para cargar**: marca que está limpia y dónde está (dentro del 1560,
     del 1524 u otro lugar).
  2. **Le llega la alerta al almacén que corresponde**: si la ruta lleva granel o MP, al personal del 1524; si lleva
     producto terminado, al del 1560; si lleva ambos, a los dos. El personal es el que tiene ese almacén en su
     usuario. Se ajusta en los parámetros «carga_almacen_granel» y «carga_almacen_pt».
  3. **Almacén responde** que inició el traslado y la carga, y marca a quién se lo asignó. El chofer y Distribución
     reciben el aviso y pueden hacer el seguimiento.
  4. **Evidencias**: Almacén sube fotos del antes y del después de la carga y, si puede, un video. Sirven para
     revisar las quejas de mercadería mal paletizada. Para exigirlas antes de la salida, se activa
     «carga_exigir_fotos».
- **Firmas antes de salir:**
  - Seguridad;
  - el chofer;
  - el Auxiliar de Despacho, solo si la ruta lleva uno (si va sin auxiliar, no se le pide);
  - Calidad, de forma **opcional**: puede firmar, pero no bloquea la salida.
  - Luego el Líder Operativo autoriza la salida, como antes.

### Recorrido de los vehículos (Distribución)
- Menú **Distribución → Recorrido de los vehículos**. Por cada vehículo del día se ve el movimiento punto a punto:
  - central o planta (carga) → cliente X → cliente Y → … → retorno a la central → nueva carga → cliente R…;
  - el estado de cada entrega (por salir, en camino, llegó, entregado, rechazado) y su hora;
  - el auxiliar de despacho de cada vuelta, o «sin auxiliar».
- El auxiliar (uno o varios, o ninguno) se registra en la ruta, como ya se hacía en la programación.

### Pedidos fuera de horario
- **Cómo funciona.** Antes, una OV de producto terminado para mañana registrada después de la hora de corte quedaba
  en borrador. Ahora:
  1. Comercial solicita la aprobación con un motivo, en «OV fuera de horario».
  2. El **Jefe de Operaciones** aprueba o desestima (con motivo). Si aprueba, la OV se registra y sigue normal.
  3. Si la desestima, Comercial puede **elevarla a Gerencia General**, que decide en última instancia.
- **Almacén** ve en «Pedidos fuera de horario» las OV aprobadas y las que están por decidir, con su historial (quién,
  cuándo y por qué).
- Se mantiene la validación de pedidos grandes de última hora (V66).

### Guías de SAP: ver e imprimir en el módulo
- **El problema** (ejemplo: un despacho con fecha 16/11). El módulo trae de SAP el número de la guía y sus líneas, pero
  solo mostraba el número: no había dónde verla ni imprimirla.
- **Ahora** el número de la guía es un enlace a «Guía de remisión» en:
  - el detalle de la OV;
  - Estado de OV (paso «Guía»);
  - «OV vs guías».
- La guía muestra:
  - fecha, cliente, punto de llegada, OV y factura;
  - productos con cantidades, kg y lotes.
- Botones **Imprimir** y **PDF**.
- **De dónde salen los datos:**
  - las líneas, de lo que ya leyó el vigilante;
  - la dirección, los comentarios y los lotes, de una lectura de **solo consulta** de la guía en SAP, en el momento.
  - Si SAP no responde, se muestra lo ya leído con un aviso.
- Las guías SUNAT subidas al módulo abren su archivo.
- **Facturas de SAP:** junto a cada guía sale el enlace a su factura («Factura», con Imprimir y PDF). La cabecera
  viene de lo leído de SAP y el detalle, de una lectura de solo consulta de la factura en SAP; si SAP no responde, se
  usan las líneas de la guía. Funciona igual para las notas de crédito.
- **Regularización:** una OV con guía de SAP ya cuenta como despachada (total o parcial), y su factura se ve en la OV
  (desde V54). Ahora además se pueden abrir e imprimir las dos.
- **Para validar la carga** ven la pre-guía de la ruta y, por OV, la guía y la factura de SAP:
  - Almacén;
  - el Auxiliar de Despacho (antes no podía abrir la pre-guía);
  - el chofer;
  - Seguridad;
  - Calidad.
  - Están en «Carga de unidades» y en el detalle de la ruta («Documentos para validar la carga»).
- **Es una representación interna** de los datos de SAP. El comprobante electrónico de SUNAT, con su código QR, se
  sigue imprimiendo desde SAP o el OSE.

## Pendiente o por validar

| Punto | Situación |
|---|---|
| «Con acceso a SAP ya debe verse toda la información» | El módulo lee SAP desde su servidor con el vigilante, no desde aquí. Sigue pendiente lo de antes: cambiar el módulo al usuario admin1, reactivar el vigilante y resolver el -5027 intermitente del Service Layer con Exxis. Hasta entonces, el semáforo, la rotación y los indicadores usan lo último que se leyó de SAP. |
| Nombres de las personas | En Administración → Usuarios hay que escribir los apellidos y nombres de los usuarios que hoy tienen su usuario como nombre. Es un dato que no pongo yo. |
| Almacén asignado al personal | La alerta de unidad lista va al personal que tiene asignado el almacén 1560 o 1524 en su usuario. Si nadie lo tiene, va a los perfiles de Almacén. |
| Reempaque: evaluar | No se le dio al Líder Operativo la evaluación (aprobar o desaprobar) del reempaque. Es el control de Calidad (IF §9.1) y quien solicita no debería aprobar su propio reempaque. Si se decide darle también esa opción, es un cambio de permiso. |
| Stock de seguridad | La fórmula y z = 1,65 son las de la presentación; quedan como propuesta en los parámetros. Las familias sin venta en 12 meses quedan en 0. |
| Productos del Excel de producción | Las filas cuyo producto no está en el maestro de artículos se informan; no se adivinan. |

## No verificado
- El semáforo y la rotación se probaron con datos ficticios. Con la base real dependen de la última lectura de SAP
  (guías y órdenes de compra).
- El aviso de carga y las firmas se probaron con rutas ficticias.

## Pruebas
`tests/test_v70.py` (13 pruebas). Se ajustaron también test_controles (reempaque del Líder), test_v45 (mensaje de la carga del plan) y test_v8 (vistos buenos de salida). Migración 0058: regla por cliente en el lote, aviso de carga en la ruta y OV fuera de
horario. `tests/test_v27.py` se ajustó: Calidad ya no es obligatoria en la salida.
