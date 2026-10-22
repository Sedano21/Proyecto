# 19. Marcha blanca: funcionalidades nuevas (respuestas del 22-oct-2026)

Marcha blanca: **todas las áreas, todo el flujo, con datos reales y en paralelo a SAP** durante una semana, con revisión
diaria que prioriza Gerencia General con el equipo de desarrollo. Las preguntas de Sistemas (infraestructura, base de
datos, correo, SAP Service Layer, Git) se responderán aparte; este documento cubre lo funcional.

## 1. Decisiones del usuario aplicadas

| Tema | Decisión (22-oct) | Cómo quedó en el sistema |
|---|---|---|
| Diferencias con SAP | Cualquier diferencia alerta para regularizar o levantar la observación | Conciliación SAP (§2). Parámetro `conciliacion_ov_modo = ALERTAR` |
| Cortes de carga SAP | Tres al día: inicio, mediodía y fin de jornada. Objetivo: sincronización automática | `cortes_carga_sap`; `horas_max_sin_carga` = 8 h (alerta si no se carga). La sincronización automática (Service Layer) queda para producción |
| Turnos | Varios turnos por persona y rotativos por semana; se descuenta el refrigerio | Turnos del personal (§3) |
| Entrada/salida | La mide otro sistema; el módulo registra interacciones y cumplimiento y alerta al jefe si no se cumple | Informe de cumplimiento y aviso al jefe (§3) |
| Asignación de tareas | Solo personal en turno; en Configuración se agrega personal para emergencias | `asignar_solo_personal_en_turno`; refuerzos de emergencia |
| Segundo factor | Por ahora sin MFA; al aceptar el uso aceptan la responsabilidad por su usuario y contraseña | Aviso al primer ingreso con dos casillas (§4) |
| Contraseñas | Mínimo 8, cambio en el primer ingreso, bloqueo tras 5 intentos, vencimiento a 90 días | §4 |
| Aviso de datos | Borrador para revisión; responsable «Corporación Productiva» | Parámetro `aviso_datos_texto` (editable) y `aviso_datos_version` |
| Contingencia | El objetivo es la carga automática, pero se puede registrar en contingencia | Registro en contingencia (§5) |
| Guía | Vale la de SAP; el sistema la genera solo si SAP se cae | Origen SAP por defecto; la del sistema exige motivo de contingencia |
| Certificado | El del sistema reemplaza al actual | Sin cambio (ya implementado) |
| OV abiertas al arranque | Se cargan y reservan stock al ingresar (SAP no tiene ese análisis) | Carga de OV de SAP: crea la OV y reserva (pendiente = solicitado − entregado) |
| Numeración | Se respeta la de SAP | La conciliación empareja por el número de OV |
| Observaciones | Botón «Reportar observación» en cada pantalla | §6 |

## 2. Conciliación SAP

**Caso de uso.** Almacén, Comercial, Producción o Distribución sube la exportación de SAP en su corte. Al autorizar la
carga, el sistema compara con lo registrado en el módulo:

| Carga | Qué compara | Área que recibe la alerta |
|---|---|---|
| Stock por lote (`STOCK`) | Cantidad por artículo, lote y almacén (desde la segunda carga; la inicial es la base) | Almacén |
| Órdenes de venta (`OV`) | Fecha comprometida, cantidad pendiente y precio por producto; OV cerradas en SAP y abiertas en el módulo; OV del módulo que no figuran en SAP | Comercial |
| Liquidaciones (`LIQUIDACION`) | Si ya está registrada en el módulo: producto, cantidad completada y vencimiento (no se duplica) | Producción |
| Despachos de SAP (`DESPACHOS`, **nuevo**) | Guía, factura y cantidad despachada por OV | Distribución (guía y cantidad) y Facturación (factura) |

Cada diferencia queda en **Marcha blanca → Conciliación SAP** con el valor de SAP y el del módulo. El responsable del área
la marca como **Regularizada** (se corrigió en SAP o en el módulo) o **Levanta la observación** con su motivo (se aplica a
varias a la vez). Cuando no queda ninguna pendiente de una carga, su alerta se cierra sola.

En modo `ALERTAR` la carga de OV **no** modifica una OV que ya existe en el módulo: registra la diferencia. Las OV nuevas de
SAP sí se crean (sincronización).

**Formato propuesto para la carga de despachos de SAP** (hoja `DESPACHOS`; Sistemas ajusta la consulta de SAP a estos
encabezados o se agregan sinónimos): `Número de OV`, `Número de guía`, `Número de factura`, `Fecha`,
`Código de producto`, `Cantidad`. La cantidad debe ser lo despachado acumulado de la OV (si la exportación trae solo un
periodo, aparecerán diferencias de cantidad).

## 3. Turnos, asignación y cumplimiento

- **Administración → Turnos del personal**: turnos (días, inicio, fin, refrigerio; si el fin es menor que el inicio, el
  turno termina al día siguiente), asignación por persona con vigencia y rotación (cada N semanas, le toca la semana k),
  **refuerzos de emergencia** (persona, fechas, horario y motivo) y «quién trabaja el día».
- **Picking**: se propone y se asigna solo a personal en turno ese día (incluidos los refuerzos). Mientras nadie del almacén
  tenga turno configurado se usa todo el personal (transición).
- **Aviso al jefe**: en cada verificación automática, una tarea que vence su plazo (`horas_plazo_tarea`: ALTA 4 h, MEDIA 24 h,
  BAJA 72 h, propuesta) o un picking atrasado genera la alerta «Tarea no cumplida» al jefe del responsable, una sola vez.
  El jefe se define por rol en `jefe_por_rol` (organigrama **propuesto**, a confirmar).
- **Informe de interacciones y cumplimiento por persona** (Informes): acciones registradas (dentro y fuera de turno, solo
  para análisis), tareas recibidas, a tiempo, fuera de plazo y vencidas, y pickings listos, con retraso y atrasados.

## 4. Acceso

- **Primer ingreso**: aviso de datos personales (Ley N.° 29733) con dos casillas obligatorias: autorización del
  tratamiento y responsabilidad por el usuario y la contraseña. Se registra versión, fecha e IP. Si se cambia la versión
  del aviso, todos lo vuelven a aceptar. Si no acepta, se cierra la sesión.
- **Contraseñas**: mínimo 8 caracteres (`clave_longitud_minima`), distinta del usuario y de la anterior; la que asigna
  Sistemas se cambia en el primer ingreso; vence a los 90 días (`clave_dias_vigencia`).
- **Bloqueo**: 5 intentos fallidos seguidos (`clave_intentos_bloqueo`) bloquean el usuario 15 minutos
  (`clave_minutos_bloqueo`, propuesta para operación 24/7; con 0 queda bloqueado hasta que Sistemas lo desbloquee desde
  Usuarios).
- **Texto del aviso**: borrador en `aviso_datos_texto` (Configuración), para revisión del área legal.

## 5. Contingencia

**Administración → Contingencia** (Sistemas y Gerencias): se activa con un motivo mientras se registra lo trabajado en
manual. Todo lo registrado en ese lapso queda marcado `registrado_en_contingencia` en la auditoría y todas las pantallas
muestran el aviso. La guía de remisión del sistema solo se genera como contingencia (SAP no disponible) e indicando el
motivo; la guía válida es la de SAP (número y archivo).

## 6. Observaciones de los usuarios

Botón **«Reportar observación»** en la barra superior de todas las pantallas: tipo (algo no funciona, mejora, duda),
descripción, «me impide seguir trabajando» y captura opcional; se guardan la pantalla, el usuario y la versión.
**Marcha blanca → Observaciones** (Gerencia General y Sistemas): clasificación (bloqueante, mayor, menor, mejora),
estado (abierta, en curso, corregida, descartada), respuesta y exportación a Excel. Cada usuario ve las suyas en
«Mis observaciones» y recibe aviso cuando se corrigen o descartan.

## 7. Permisos nuevos (propuestos, revisables en la matriz)

| Permiso | Roles |
|---|---|
| `observaciones.gestionar` | Gerencia General, Sistemas |
| `turnos.gestionar` | Sistemas y jefaturas/coordinaciones de Almacén, Logística, Producción, Distribución, Calidad y Ventas |
| `informes.cumplimiento` | Los mismos y Gerencias |
| `conciliacion.ver` / `conciliacion.resolver` | Responsables de cada área (Almacén, Comercial, Producción, Distribución, Facturación) |
| `contingencia.gestionar` | Sistemas, Gerencia General, Gerencia de Operaciones |

## 8. Pendiente de confirmar

1. Plazos de atención por urgencia (`horas_plazo_tarea`) y organigrama de jefes (`jefe_por_rol`).
2. Texto definitivo del aviso de datos (borrador en Configuración).
3. Encabezados de la exportación de despachos de SAP.
4. Duración del bloqueo por intentos (15 min propuesto).
