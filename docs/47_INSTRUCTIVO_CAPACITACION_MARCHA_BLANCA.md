# 47 · Instructivo de capacitación y marcha blanca — Módulo de Operaciones

**Corporación Productiva · Versión 1 · 09-nov-2026**

- **Parte A:** instructivo general, para todo el personal.
- **Parte B:** instructivos por área, para entregar a cada equipo.
- **Detalle de cada pantalla:** está en el sistema, en **Manual de usuario** (menú de usuario o enlace al pie del menú).
  Se arma solo con lo que cada perfil puede usar.

---

# PARTE A · Instructivo general (todo el personal)

## A1. ¿Qué es la marcha blanca?

Es el periodo en que el sistema se usa con la operación real **en paralelo** a la forma actual de trabajo. Sirve para:
1. que cada persona aprenda su parte con casos reales;
2. encontrar y corregir errores, datos faltantes o pasos que no calzan con la operación;
3. confirmar que la información cuadra con SAP (stock, OV, despachos, facturas).

**Durante la marcha blanca SAP sigue siendo el sistema oficial.** Lo que el módulo escribe en SAP está limitado a lo
que la empresa autorizó (ver A8).

## A2. Cómo entrar

| Paso | Qué hacer |
|---|---|
| 1 | Abra en el navegador (Chrome o Edge; en celular, Chrome o Safari) la dirección que entrega Sistemas. Hoy es **https://coprod-one.duckdns.org**. |
| 2 | Escriba el **usuario** y la **contraseña temporal** que le entregó Sistemas. |
| 3 | Lea y acepte el aviso de tratamiento de datos personales (Ley 29733). |
| 4 | El sistema le pide **cambiar la contraseña**. Es personal: no la comparta ni la anote a la vista. |
| 5 | En el celular: menú del navegador → «Agregar a la pantalla de inicio». En iPhone es **obligatorio** para recibir notificaciones. |

- Si olvidó la contraseña, pida a Sistemas una nueva. La cambiará en su siguiente ingreso.
- Cada persona entra con **su propio usuario**: todo queda registrado a su nombre (auditoría).

## A3. La pantalla

- **Menú lateral:** muestra solo lo que su perfil puede usar.
- **Inicio:** sus tareas pendientes, alertas e indicadores de su área.
- **Barra superior:**
  - fecha de la última carga de **Stock SAP** (no es tiempo real);
  - **Reportar avería** y **Reportar observación**;
  - parlante (sonido de alertas), **Mensajes** y campana de **Alertas**.
- **En las listas:** ojo = ver, lápiz = editar, tres puntos = más opciones.
- **Formularios:**
  - los campos con asterisco rojo son obligatorios;
  - si algo falta, se marca en rojo y **no se borra lo que escribió**;
  - las acciones importantes piden confirmación.

## A4. Alertas, tareas y notificaciones

- **Alertas y tareas** separa «Acción requerida» (lo que usted debe hacer) e «Información».
- Las urgentes suenan distinto y se repiten hasta que se atienden. Si el sonido no sale, toque una vez la página y
  revise el parlante.
- **Notificaciones en el celular** (menú de usuario): pulse «Activar en este dispositivo». Son las únicas que suenan con
  la pantalla apagada.
  - El diagnóstico de esa pantalla muestra qué falta, si algo falla.
  - Cada celular o computadora se activa por separado.
- Una tarea derivada a otra área se ve como «Derivada · pendiente <área>» para su seguimiento.

## A5. Mensajes (chat interno)

Icono de mensajes en la barra superior: elija a la persona y escriba. Para hablar de una pantalla en particular use
«Enviar esta pantalla por mensaje» (menú de usuario): llega con el enlace. Sirve para coordinar o apurar un pendiente.
**No reemplaza** a las alertas ni a los registros formales: una aprobación se hace en su pantalla, no por mensaje.

## A6. Cómo reportar durante la marcha blanca

| Situación | Qué usar | Quién lo recibe |
|---|---|---|
| Algo del sistema no funciona, un dato está mal o un paso no calza con la operación | **Reportar observación** (barra superior; se adjunta la pantalla donde está) | Sistemas y el responsable del proyecto |
| Falla de un equipo, la luz, una máquina o la red; tintas; accesos | **Reportar avería** → elija Mantenimiento o Sistemas | Mantenimiento o Sistemas |
| Aparece un cuadro rojo con un código (p. ej. E-1234) | Tome captura y envíela con Reportar observación | Sistemas |

**Una buena observación dice:** qué hacía, qué esperaba, qué pasó, el número de OV, lote o ruta, y la hora.

## A7. Reglas de la marcha blanca

1. **Registre en el sistema todo lo que haga en su proceso, el mismo día.** Si no se registra, no se puede comparar.
2. **Siga haciendo lo de SAP como siempre** hasta que se indique lo contrario.
3. **Datos reales y exactos:** no cree registros inventados en la base real. Los ejercicios de práctica se hacen con
   la operación real del día. Si se equivoca, use la acción de anular o corregir de esa pantalla y avise con
   «Reportar observación».
4. **No comparta su usuario.** Si alguien no tiene usuario, que lo pida a Sistemas.
5. **Cada día:** atienda primero las tareas en rojo de Inicio.
6. **Al cierre del día:** revise que no le queden tareas abiertas de su proceso.

## A8. Si SAP o el sistema no responden

- **SAP sin conexión:** lo que el módulo debe enviar a SAP **queda en cola** y se envía cuando vuelve la conexión.
  Sistemas recibe la alerta «SAP sin conexión». Siga trabajando normalmente.
- **El sistema no abre:**
  1. Revise su internet.
  2. Si sigue sin abrir, avise a Sistemas y anote en papel lo que hizo.
  3. Regístrelo apenas vuelva, indicando la hora real.
- **Escritura en SAP:** el módulo solo crea documentos (OV, cotizaciones) en las bases de SAP que la empresa autorizó
  («sap_escritura_empresas»). Al inicio, solo lee de la base real.

## A9. Plan de capacitación sugerido

| Sesión | Duración | Contenido | Participantes |
|---|---|---|---|
| 1. General | 45 min | Partes A1 a A8, ingreso de cada uno, cambio de clave, activar notificaciones | Todos, por grupos |
| 2. Por área | 90 min | Instructivo del área (Parte B) con casos reales del día | Cada área |
| 3. Flujo completo | 60 min | Una OV de punta a punta: Comercial → Almacén → Calidad → Distribución → Finanzas | Jefes y coordinadores |
| 4. Seguimiento | 30 min diarios (1.ª semana) | Revisión de observaciones y dudas | Responsable de cada área + Sistemas |

**Criterios para terminar la marcha blanca** (los valida Gerencia):
- dos semanas con todas las áreas registrando el 100 % de su operación;
- sin observaciones críticas abiertas;
- stock, OV y despachos cuadrando con SAP en la conciliación diaria.

---

# PARTE B · Instructivos por área

Cada instructivo tiene: **perfiles**, **qué hace cada día**, **paso a paso de sus tareas principales**,
**ejercicios de práctica** y **qué no hace** su perfil. Lo no descrito aquí está en el Manual de usuario del sistema.

---

## B1. Gerencia (Gerencia General, Gerente General Adjunto, Jefatura de Operaciones)

**Perfiles:**
- Gerencia General ve todo y puede aprobar en nombre de otros roles.
- El Gerente General Adjunto tiene el mismo alcance y además aprueba compras e importaciones.
- La Jefatura de Operaciones tiene las facultades de Logística y consulta Almacén, Producción, Calidad y Distribución.

**Cada día:**
1. **Inicio:** tareas y alertas prioritarias (Calidad para Gerencia General; compras e importaciones para el GGA).
2. **Cómo va la empresa:**
   - venta del mes vs meta y lo que necesita ingresar la empresa en la semana;
   - OTIF, cobranza vencida y producción;
   - importaciones, stock sin rotación y «A qué prestarle atención».
3. Aprobaciones pendientes: compras (GGA), despacho parcial (GGA o Jefatura de Operaciones), decisiones de OV sin
   fecha posible.

**Paso a paso:**
- **Aprobar la ejecución de una compra (GGA):**
  1. Abra la alerta y revise el motivo, las OV de origen y las cotizaciones.
  2. Apruebe u observe.
- **Aprobar un despacho parcial:**
  1. Abra la OV detenida.
  2. Indique la fecha del saldo y apruebe.
  3. Comercial recibe el aviso.
- **Nivel de servicio (Jefatura de Operaciones):** en Nivel de servicio, pulse un indicador para ver las OV que lo
  componen.

**Práctica:**
- revisar Cómo va la empresa;
- abrir una OV y su expediente;
- descargar en PDF el informe de su área.

**No hace:** modificar listas de precios ni la configuración (Jefe Comercial y Sistemas).

---

## B2. Comercial (Gerente Comercial, Jefe Comercial, Coordinador, Asistente y Ejecutivos de Ventas)

**Cada día:**
1. **Inicio:** sus OV por cliente y fecha de despacho, alertas de precio, stock y fechas.
2. **Cómo va la empresa / Objetivos:** la meta y lo que necesita ingresar la empresa en la semana (lo registra
   Finanzas).
3. Registrar las OV del día **antes de la hora de corte** (12:00 para despachar al día siguiente).

**Paso a paso:**
- **Registrar una OV:**
  1. Comercial → Registrar OV.
  2. Elija el cliente y el lugar de entrega.
  3. Indique la fecha comprometida (no se aceptan fechas pasadas) y la cita, si el cliente la pide.
  4. Agregue las líneas: producto, cantidad y precio. La unidad la fija el código.
  5. Adjunte la orden de compra del cliente, o déjela como borrador.
  6. Guarde. El sistema evalúa stock y precio y responde si se cumple la fecha.
- **OV con precio bajo el mínimo:**
  - queda detenida;
  - la confirma el Jefe o el Coordinador, con motivo.
- **Modificar una OV:**
  - Coordinador o Ejecutivo: con el lápiz;
  - Asistente: el lápiz envía una **solicitud**, que autoriza Comercial.
- **OV con fecha pasada:** use Regularización de OV. No reserva stock.
- **Clientes:**
  - Registre el RUC y complete la ficha (canal, grupo, condición de pago, lugares de entrega y correos).
  - La condición de pago la aprueba Finanzas.
- **Pagos:** en la ficha del cliente → Finanzas, suba el comprobante. Finanzas lo confirma.
- **Oportunidades:** registre cada visita, llamada o reunión con su resultado; de ahí salen las cotizaciones.
- **Seguir un pedido:** OV → Resumen (avance) y Expediente (OV, certificado, guía y factura).

**Práctica:**
- registrar una OV real del día;
- solicitar una modificación;
- revisar el expediente de una OV despachada.

**No hace:** el Asistente no modifica OV directamente ni confirma precios fuera de rango.

---

## B3. Finanzas, Facturación y Costos (Jefe de Adm. y Finanzas, Coordinación de Finanzas, Facturación, Costos y Presupuestos)

**Cada día:**
1. **Finanzas:**
   - aprobar condiciones de pago;
   - confirmar u observar los pagos que suben los ejecutivos;
   - revisar la cobranza vencida.
2. **Facturación:** evaluar los pedidos validados y cargar la factura de SAP en la ruta.
3. **Lunes (Jefe de Adm. y Finanzas):** registrar **lo que necesita ingresar la empresa en la semana** (Cómo va la
   empresa → formulario de la semana).

**Paso a paso:**
- **Facturas y notas de crédito:**
  1. Finanzas → Cobranza y condiciones.
  2. Suba el Excel exportado de SAP.
  3. Adjunte los PDF.
- **Confirmar un pago:**
  1. Abra el comprobante.
  2. Pulse Confirmar (descuenta el saldo) u Observar (con motivo).
- **Necesidad semanal:**
  1. Elija cualquier día de la semana y escriba el monto.
  2. Si difiere de la meta en más del 5 %, escriba el **motivo de la variación** (obligatorio).
  3. Comercial lo ve junto a la meta. Si la semana cierra sin llegar, se avisa a Ventas, Gerencia Comercial y
     Finanzas.
- **Costos (perfil Costos y Presupuestos):**
  - cargar el costo por SKU (uno a uno o por Excel);
  - revisar en Costos y reposición el costo registrado frente al costo de reponer y al precio de venta;
  - el tipo de cambio se lee de SUNAT cada día; si no hay conexión, se registra a mano.
- **Gastos y centros de costo:** Rendiciones, movilidad y centros de costo; Gastos y desempeño por área.

**Práctica:**
- cargar las facturas del día;
- confirmar un pago;
- registrar la necesidad de la semana;
- descargar la cobranza en Excel.

**No hace:** registrar OV ni modificar la ficha comercial del cliente.

---

## B4. Logística y Almacén

**Perfiles:**
- Jefe y Coordinador de Logística.
- Supervisores de Almacén 1560 y 1524.
- Supervisión por almacén.
- Líder Operativo.
- Auxiliares de Almacén.
- Montacarguistas.

**Cada día:**
1. **Supervisores:**
   - cargar el **stock de SAP** al inicio del día (Almacén → Cargas de archivos → revisar → autorizar);
   - responder **CUMPLE / NO CUMPLE** en las OV que lo piden.
2. **Líder Operativo:** revisar la **Programación de picking** del día y asignar cada tarea a una persona o a un grupo.
3. **Auxiliares:** hacer el picking asignado.
4. **Montacarguistas:** atender traslados y movimientos con foto de inicio y de fin.
5. **Jefe o Coordinador de Logística:**
   - autorizar presolicitudes de compra y traslados;
   - decidir alternativas ante faltantes;
   - validar el conteo físico (solo el Jefe).

**Paso a paso:**
- **Picking (Auxiliar):**
  1. Almacén → Programación de picking → su tarea.
  2. Inicie con la foto: se abre el formato con el stock reservado.
  3. Registre lo despachado de cada línea (cantidad y lote).
  4. Termine con la foto. El pedido no se cierra si está incompleto; las diferencias se registran con motivo
     (rotura, infestación, difícil acceso…).
- **Faltante en una OV:**
  1. OV → Condición y opciones: el sistema ordena las alternativas (producción, reempaque, traslado, compra).
  2. Elija una, con motivo.
- **Traslados:** solicitud → autorización → salida → llegada.
- **Conteo cíclico:** registre el conteo por producto; las diferencias las valida el Jefe de Logística.
- **Stock sin rotación:**
  - la tarjeta de Inicio lleva a la pestaña de rotación;
  - muestra kg y valor al costo y a precio mínimo y máximo.
- **Reempaque:** presolicitud con el producto de origen y de destino (código y descripción); Calidad lo evalúa.

**Práctica:**
- cargar el stock del día;
- asignar y ejecutar un picking real;
- registrar un traslado;
- registrar un conteo de un producto.

**No hace:**
- el Auxiliar no asigna picking ni cambia lote, fechas o cantidades solicitadas;
- solo el Jefe de Logística valida el conteo físico.

---

## B5. Producción (Jefe de Producción, Asistentes de Producción)

**Cada día:**
1. **Jefe:**
   - validar las solicitudes de producción (por faltante de OV);
   - programarlas en una línea según la capacidad;
   - revisar el planeamiento preprogramado.
2. **Asistentes:**
   - iniciar el **parte en línea** al arrancar cada producción;
   - registrar pausas y avance;
   - **liquidar** al terminar.
3. Revisar el **monitoreo** (líneas trabajando ahora) y el **control de producción / OEE**.

**Paso a paso:**
- **Parte en línea:**
  1. Producción → Partes.
  2. Inicie con línea, producto, EAN escaneado, lote y kg de MP. Si el EAN no coincide, el sistema alerta.
  3. Registre las pausas con su causa (de la lista).
  4. Registre el avance por pallet, si aplica.
- **Liquidar:**
  - Registre horas, operarios y kg de MP (SAP los exige).
  - Si el rendimiento o las horas salen del rango, se pide el motivo.
  - Lo liquidado pasa a almacén y espera la **liberación de Calidad**.
- **Planeamiento:**
  1. Pulse «Preprogramar».
  2. Ajuste las cantidades.
  3. Los cambios de los asistentes los valida el Jefe.

**Práctica:**
- un parte completo de una producción real (inicio, pausa, fin);
- su liquidación;
- revisar el OEE del día.

---

## B6. Calidad (Jefe, Supervisor y Asistente de Calidad)

**Cada día:**
1. **Bandeja de Calidad:** devoluciones, reempaques, solicitudes de revisión e ingresos de compras e importaciones.
2. **Registros:**
   - antes de producir: higiene del personal y de los equipos;
   - durante la producción: ingreso de lotes;
   - después de producir.
3. **Certificados:** el precertificado se genera después del picking. Revise, corrija, «Guardar avance» y
   «Confirmar y aprobar».
4. **Liberación de lotes** de producción y desbloqueo de lotes observados (solo Calidad libera).

**Paso a paso:**
- **Fumigación con varios productos:**
  1. Calidad → Liberación y registros → nuevo registro, formato **Fumigación**.
  2. En «Productos y lotes fumigados» pulse **+ Agregar producto** por cada producto y lote, con su cantidad.
  3. Cada lote del stock pasa a «en fumigación». Al terminar, se libera.
- **Informe de recepción de importaciones:**
  1. Abra el seguimiento de importaciones.
  2. Elija **Subir PDF** (si ya lo tiene) o **Generar informe**: abre el formato REG-CAL-005 prellenado con la
     importación.
  3. Importaciones y el GGA reciben el aviso.
- **Bloquear un parte de producción:** con motivo; se alerta a Producción.
- **Lote observado:** registre el motivo. Queda bloqueado hasta que Calidad lo libere.

**Práctica:**
- registro «antes de producir» del día;
- aprobar un certificado;
- registrar una fumigación con dos lotes;
- generar el informe de una importación.

---

## B7. Abastecimiento (Compras nacionales, Importaciones)

**Cada día:**
1. **Compras:**
   - atender las presolicitudes autorizadas;
   - registrar cotizaciones;
   - pedir la aprobación de ejecución al GGA;
   - registrar la OC.
2. **Importaciones:**
   - actualizar el **seguimiento de importaciones** (llegada, días libres, SENASA, BL, retiro, almacén);
   - subir los **documentos**;
   - atender las alertas de retiro, sobreestadía y penalidad.

**Paso a paso:**
- **Compra nacional:**
  1. Solicitud con la OV o el cliente (o el motivo: stock de seguridad o reposición).
  2. Registre una o varias cotizaciones (proveedor, precio, moneda, plazo, archivo).
  3. El sistema compara con el histórico y alerta si el precio se aparta.
  4. Elija la cotización y pida la aprobación.
- **Documentos de importación:**
  1. Editar → Documentos.
  2. Elija el tipo (certificado de origen, fitosanitario, packing list, calidad, fumigación u otros) y suba el
     archivo.
  3. La columna «Documentos» muestra cuántos faltan.
- **Gastos extra:** sobreestadía, almacenaje, flete, SENASA o agente de aduanas, con sustento. Se suman al costo del
  producto importado.

**Práctica:**
- una compra con tres cotizaciones;
- actualizar una importación y subir su fitosanitario.

---

## B8. Distribución (Coordinador y Asistente de Distribución, Choferes, Auxiliares de Despacho)

**Cada día:**
1. **Coordinador / Asistente:**
   - revisar la **Programación de distribución** y sus **Recomendaciones** (consolidar rutas, mismo punto de entrega,
     citas que no calzan);
   - ajustar y confirmar las rutas;
   - aprobar las guías;
   - registrar rutas manuales si hace falta.
2. **Chofer:**
   - en **Mis entregas**, hacer el **checklist vehicular** de salida;
   - durante la ruta, marcar «Llegué» y registrar la **conformidad** de cada entrega;
   - al volver, hacer el checklist de retorno.
3. **Auxiliar de despacho:** validar la carga, dar el visto bueno de salida y reportar el estado de las guías.

**Paso a paso:**
- **Ruta manual:**
  1. Cuadro de despacho → Nueva ruta manual.
  2. En **Lo lleva** elija:
     - **Chofer de la empresa** → vehículo y chofer;
     - **Otro trabajador** → trabajador, área, vehículo y motivo;
     - **Transporte externo** → unidad, empresa y **costo**.
  3. Marque las OV y los traslados. Si la carga no tiene OV, escríbala en **Otra carga sin OV** (qué lleva, destino,
     kg).
- **Checklist del chofer:**
  1. Mis entregas → **Mi checklist vehicular** → Registrar checklist de salida.
  2. Marque B / M / NA en cada ítem.
  3. Toque en el **dibujo del vehículo** la parte dañada o escriba la observación.
  4. Sin el checklist validado por Seguridad, la unidad propia no sale.
- **Conformidad de entrega:**
  1. Anote nombre y DNI de quien recibe.
  2. Pida su firma en pantalla.
  3. Tome la foto de la entrega y de la guía firmada.
- **Incidencias:** entrega parcial, fallida o devolución, con su paso 2 (lo que realmente vuelve).

**Práctica:**
- confirmar una ruta del día;
- registrar una ruta manual con un trabajador;
- checklist de salida de un chofer;
- una conformidad real.

**No hace:** el chofer no da conformidad del estado del producto (Calidad, Distribución y Almacén).

---

## B9. Seguridad

**Cada día:**
1. **Control de vehículos:** placa y chofer programados, estado del vehículo y validación del checklist (con el
   kilometraje).
2. **Validar la salida contra la guía**, ítem por ítem, y registrar las horas: inicio del despacho, partida y
   retorno.
3. **Llegadas de compras e importaciones:** cantidad que ingresa, placa, chofer, fotos y conformidad o incidente.

**Práctica:**
- validar un checklist con kilometraje;
- validar una salida contra la guía;
- registrar una llegada.

**No hace:** validar la limpieza o la estiba del vehículo (Calidad).

---

## B10. Mantenimiento, Limpieza y Gestión Humana

- **Mantenimiento:**
  - atender los **tickets** de «Reportar avería»;
  - abrir **órdenes de trabajo** con fotos de antes y después;
  - seguir el **cronograma** preventivo (alertas a 7, 3 y 0 días);
  - registrar el mantenimiento de la flota y de las máquinas (calibración).
- **Limpieza:**
  - programar la limpieza por persona y zona;
  - marcar cada limpieza hecha;
  - revisar el desempeño.
- **Gestión Humana / jefes de área:**
  - en **Asistencia y personal**: altas de personal (uno a uno o por Excel) y asistencia;
  - registrar la **disponibilidad**: vacaciones, descanso médico, faltas.

  Quien no está disponible no se puede asignar a rutas ni tareas ese día.

**Práctica:** cerrar un ticket con fotos; registrar una ausencia y comprobar que esa persona no aparece para asignar.

---

## B11. Sistemas

**Cada día:**
1. Revisar las **observaciones** de la marcha blanca y los tickets de Sistemas.
2. Revisar las alertas de integración («SAP sin conexión») y la conexión con SAP.
3. Ver el resultado del respaldo diario.

**Tareas:**
- **Usuarios:**
  - se crean con `crear-usuario` (o en Usuarios y permisos), con su perfil y, en almacén, su almacén;
  - uno mal creado se quita con `eliminar-usuario <usuario>`. Primero sin `--confirmar` para ver qué hará: lo borra si
    no tiene registros; si tiene, lo da de baja.
- **Parámetros:** se cambian en Configuración (quedan versionados y auditados).
- **Verificación del servidor:** `sudo bash /opt/operaciones/deploy/verificar_servidor.sh <dominio> --sap`.

---

# Anexo · Lista de entrega por persona

| ☐ | Ítem |
|---|---|
| ☐ | Usuario creado con el perfil correcto (y almacén, si aplica) |
| ☐ | Primer ingreso hecho, contraseña cambiada y aviso de datos aceptado |
| ☐ | Notificaciones activadas en su celular (y en su PC, si la usa) |
| ☐ | Asistió a la sesión general y a la de su área |
| ☐ | Hizo los ejercicios de práctica de su área |
| ☐ | Sabe usar «Reportar observación» y «Reportar avería» |
| ☐ | Conoce a quién acudir: responsable del área y Sistemas |
