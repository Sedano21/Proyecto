# Ronda V44 (16-nov-2026): encabezado de SAP, préstamo con lo que falta, bloqueo solo por precio y filtros

Solo datos ficticios en pruebas. Nada se verificó contra la base real de SAP.

## 1. ¿Detecta clientes y artículos nuevos y las liquidaciones?
Sí, mediante el vigilante de SAP (servicio `operaciones-sap`):
- **Clientes, artículos y stock**: una vez por hora (y al pulsar «Actualizar con SAP»), solo si SAP cambió y si están en
  `sap_sync_tipos`.
- **Liquidaciones de producción**: cada minuto se revisan las entradas y salidas de inventario de SAP; si cambian, se
  trae el historial (entradas de producción, V42), el balance de peso de las órdenes de fabricación y, si `LIQUIDACION`
  está en `sap_sync_tipos`, la carga de liquidaciones.

## 2. Encabezado: último cambio de SAP
Antes decía «Stock SAP 12/11 12:38 · no es tiempo real» (la última carga de stock, que solo se crea cuando el stock
cambia). Ahora dice **«SAP · último cambio dd/mm hh:mm · revisado hh:mm»**: el último cambio traído de SAP (stock u
otros documentos) y la última vez que el vigilante revisó SAP. El detalle está en el texto al pasar el cursor.

## 3. OTIF de «Cómo va la empresa»
La tarjeta «OTIF del mes» y el gráfico «OTIF por semana» usan el mismo cálculo con SAP (OV de SAP frente a sus guías)
que el nivel de servicio; se actualizan con cada lectura de SAP.

## 4. Préstamo: «Traer lo que falta»
En la guía SUNAT, «Registrar el ingreso con lo que falta» abre el ingreso con, por cada producto y lote: cantidad de
la guía − stock del lote en SAP (según la última carga de stock de SAP; en el almacén elegido o en todos). Se muestra la
tabla guía / stock SAP / falta y las cantidades quedan **editables** antes de registrar.

## 5. Por ahora la OV solo se bloquea por precio
`bloquear_ov_sin_opcion` pasa a **No** y `dias_minimos_emision_ov` a **0**: la OV ya no se bloquea porque ninguna opción
cumpla la fecha ni por falta de anticipación. El control de precio sigue igual. Se reactivan desde Parámetros.
El día no laborable (V33) sigue impidiendo registrar OV con despacho ese día (`dias_no_laborables_bloquean_ov`).

## 6. Guía SUNAT en SAP con la serie EG07
Al crear la entrega se envía la **serie de numeración de SAP** (`Series`) de las entregas con el mismo prefijo (EG07);
antes SAP usaba su serie por defecto (0001). La entrega 1901794 ya creada con la serie 0001 no se puede cambiar desde el
módulo (SAP no permite cambiar la serie de un documento creado).

## 7. «En riesgo» filtra la tabla
En el inicio, las tarjetas En riesgo, Por vigilar, A tiempo y Modificaciones filtran la tabla de despachos («Mostrando
solo… · ver todos»).

## 8. Nivel de servicio por rango
Además del mes, se elige **desde / hasta** (una semana o un grupo de días). La comparación con el año anterior usa el
mismo rango.

**Pruebas:** `tests/test_v44.py`.
- Suite completa: **655 pruebas, todas pasan** (654 + la prueba de V35 ajustada al nuevo texto del botón).
