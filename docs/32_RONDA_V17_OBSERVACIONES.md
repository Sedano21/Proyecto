# Ronda V17: observaciones al módulo (02-nov-2026)

## 1. Numeración automática

No se escriben a mano los números de OV, orden de compra ni guía. Los asigna el sistema, en orden.

| Documento | Número |
|---|---|
| OV del módulo | Correlativo propio: `OV-000001`, `OV-000002`… Al enviarse a SAP, la OV guarda **también el número que asigna SAP**, que se ve junto al del módulo. Las OV que vienen de SAP conservan el número de SAP. |
| Orden de compra (Compras) | `OC-000001`… |
| Guía de SAP | La numera **SAP** cuando se envía la pre-guía validada. Distribución solo adjunta el archivo; si la pre-guía aún no se envió, el sistema lo indica. |
| Guía de contingencia (SAP no disponible) | `GS-000001`… |
| Guía de una regularización | Se toma de SAP en la conciliación de despachos. Mientras tanto queda «POR CONCILIAR CON SAP». |

Los prefijos se configuran en el parámetro `numeracion_prefijos`.

## 2. Comercial

- **Inicio del ejecutivo comercial: «Mis pedidos».** Muestra:
  - cada OV, con su estado y **dónde está** (Comercial, Logística, Almacén en picking, Distribución…);
  - el **% de productos y de líneas** completados y el avance;
  - los **retrasos** (atrasada, detenida o sale hoy sin estar preparada), en rojo arriba.

  Además, el ejecutivo recibe **de inmediato** la alerta «OV atrasada o detenida» (una por OV y día; las verificaciones automáticas corren cada minuto).
- **Pago en el expediente.** «Agregar pago al expediente» registra la fecha, el monto, el medio, el n.° de operación y el comprobante. Queda en el expediente y llega a Finanzas, que lo confirma.
- **Expedientes por cliente y despacho** (Comercial → Expedientes por cliente y despacho). Agrupa las OV de un cliente que salen el mismo día; por ejemplo, «cliente X, despacho 02/11: 20 OV».
  - Muestra el avance, los retrasos, los documentos y los certificados.
  - Lo ven Comercial, Almacén, Logística, Calidad y Distribución. Cada área elige si ve el seguimiento por OV (como siempre) o por cliente y despacho.
  - **Calidad** elige entre **un certificado por producto** o un **certificado consolidado** con todos los productos del despacho, que se puede imprimir.
- **Despacho incompleto.** En la OV aparece «Saldo pendiente»: Comercial marca qué líneas **se cierran** (con motivo; no se envían) y en qué **fecha** salen las demás.
- **Entrega o recojo.** Al registrar la OV se elige:
  - **envío a la dirección del cliente**;
  - **recojo en almacén de Corporación Productiva**. La OV no va a ruta. Cuando está preparada, el Líder Operativo o el Supervisor registra en la OV quién la recogió.

  La dirección del almacén de recojo se configura en `direccion_recojo`.
- **Regularización:** el cliente se escribe y se elige en el **mismo casillero** (lista desplegable), como en «Registrar OV».

## 3. Logística y almacén

- **Coordinación de Logística:**
  - tiene **todo lo que hacen los Supervisores de Almacén 1560 y 1524** (conteos, picking, reempaque, etc.);
  - maneja **todos los almacenes salvo los de Producción** (el tránsito ALM-003 y los PRO-*). Parámetro `alcance_almacen_excepto`.
- **«No cumple».** En la OV, junto a la respuesta, se ve el **cumplimiento con ese cliente** en los últimos 90 días: OTIF, a tiempo, fill rate, veces que se respondió «no cumple» y sus últimos despachos.
- **Traslado aprobado:** llega también al **Coordinador de Distribución**, para que gestione el traslado y coordine con los almacenes externos.
- **Conteo físico producto por producto.** Al abrir el conteo se marca «Producto por producto»:
  - se elige cada producto a medida que se cuenta;
  - lo contado se registra en la misma pantalla;
  - al terminar, el conteo pasa a **«Por validar»**: **no actualiza el sistema ni SAP** hasta que el **Jefe de Logística** lo valida;
  - el Jefe de Logística también puede devolverlo con un comentario para recontar.
- **Movimientos.** Zonas nuevas:
  - **Zona manual**, **Almacén 1524** y **Almacén 1560**;
  - **Otra zona**, que se escribe a mano;
  - una **subzona** opcional.
- **Picking:**
  - los **supervisores** también asignan el picking a su personal y al montacarguista;
  - con **«+ Agregar persona»** se suman las personas necesarias;
  - en un grupo se marca **quién reporta** en el sistema (uno o varios). Si no se marca a nadie, reporta cualquiera del grupo.
- **Programación de picking semanal:** se elige el **rango de fechas** («Desde» y «Hasta»).
- **Solicitud a Producción:**
  - el producto se elige con **código, nombre y presentación**;
  - si se relaciona una OV, **solo se pueden elegir productos de esa OV**, y el sistema lo valida;
  - además de la OV, se puede indicar el **cliente relacionado**.
- **Asistencia:** Almacén y Logística ven **solo su propio personal**, no el de Producción. La **Jefatura de Operaciones** ve la de todos. Parámetro `asistencia_areas_por_rol`.
- **Revisión de formatos de Calidad** (revisión, reportes y consolidado): **exclusiva del perfil de Calidad**.

## 4. Despacho parcial

- Lo aprueba la **Jefatura de Logística o la Jefatura de Operaciones** (basta una).
- Al aprobarse, se alerta al **ejecutivo comercial a cargo**, al **Coordinador de Ventas** y al **Jefe de Ventas**.

## 5. Indicadores

- **Cada indicador del Inicio abre su detalle.** Por ejemplo, OTIF lleva a las OV que no cumplen y pedidos pendientes a las OV.
- **Nivel de servicio del mes:**
  - lo ven el Coordinador y el Jefe de Logística, la Jefatura de Operaciones, Gerencia General y el Gerente General Adjunto;
  - aparece en su Inicio y en Almacén → Nivel de servicio.

  | Indicador | Cálculo |
  |---|---|
  | **OTIF** | OV que salieron completas y a tiempo, entre las OV cuya fecha ya pasó o que ya salieron |
  | **A tiempo** | OV que salieron hasta su fecha, entre las OV que salieron |
  | **Fill rate** | Unidades despachadas entre pedidas; también por líneas |

  - **Universo:** las OV cargadas cuya fecha comprometida cae en el **mes en curso**.
  - Cada indicador lleva a la lista de sus OV: las que no cumplen, las tardías, las incompletas y las que faltan despachar.
- **Tiempos de respuesta por tipo de solicitud** (Almacén → Tiempos de respuesta y desempeño):
  - **movimientos**, por área que solicita y tipo de carga; por ejemplo, Producción pide materia prima para la línea X: cuánto tardaron en abastecerla;
  - **traslados entre almacenes**, de la solicitud a la recepción;
  - se muestran el promedio, el máximo y el detalle.
- **Desempeño del equipo:** por persona y periodo (hoy o un rango), muestra:
  - clientes y OV atendidas en el picking;
  - unidades y kg picados;
  - movimientos ejecutados y su tiempo promedio;
  - tareas atendidas.

  Lo ven la Jefatura de Operaciones, Logística y los Supervisores de Almacén.

## 6. Jefatura de Operaciones (perfil nuevo)

- **Tiene:**
  - las facultades de la **Jefatura de Logística**;
  - la **consulta** de Almacén, Producción, Calidad y Distribución;
  - la **aprobación del despacho parcial**;
  - la **asistencia de todo el personal**, el **nivel de servicio**, los **tiempos de respuesta** y el **desempeño de los equipos**.
- **No valida** el conteo físico: eso es del Jefe de Logística.
- **Alertas:** ve y atiende las de la Jefatura de Logística, sin sonido (`roles_equivalentes`).
- Usuario de ejemplo: `jefe.operaciones`.

## 7. Por confirmar

1. **Alcance de la Jefatura de Operaciones.** Se armó con lo que pide el mensaje: aprobar el parcial, ver la asistencia de todos y los indicadores, más las facultades de la Jefatura de Logística. ¿Debe tener algo más, por ejemplo aprobar en Producción? ¿Quién es su jefe en el aviso por tareas vencidas?
2. **«Almacenes de producción»** que no maneja la Coordinación de Logística: se tomaron el tránsito de Producción (ALM-003) y los PRO-*. ¿Hay otros?
3. **Número de la OV del módulo frente al de SAP.** El módulo no puede adivinar el número que SAP asignará: usa su propio correlativo y guarda el de SAP al enviarla. Si prefieren que el número principal sea el de SAP, se puede mostrar primero el de SAP.
4. **Dirección del almacén de recojo:** falta el dato (`direccion_recojo`).

## 8. Datos técnicos

- **Migraciones:**
  - `0029`: cliente del extranjero;
  - `0030`: modalidad de entrega de la OV, quién reporta en el picking, cliente en la solicitud a Producción y validación del conteo.
- **Servicios:**
  - `app/services/numeracion.py`;
  - `app/services/seguimiento.py`.
- **Vistas:** `app/views/seguimiento.py`.
- **Plantillas:** `seg_*`.
- **Pruebas:** `tests/test_v17.py`.
