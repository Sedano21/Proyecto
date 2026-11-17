# Ronda V55 (17-nov-2026): OV del mes, notas de crédito aparte y compras desde SAP

## Observación
En «Cómo va la empresa» la facturación del mes (S/ 3.19 M) salía mayor que las «OV ingresadas del mes» (S/ 1.70 M).
Además:
- la facturación debe mostrar solo el neto, con las notas de crédito en otro indicador;
- las compras deben salir de las órdenes de compra de SAP, con su valor y lo que se compró.

## Por qué no cuadraba
La tarjeta de OV sumaba las OV **del módulo** por fecha de **emisión**:
- no incluía las OV que se trabajan solo en SAP, ni su valor;
- no eran las OV que se despachan en el mes.

La facturación sí venía de SAP. Por eso no eran comparables.

## Qué cambió
- **OV con despacho en el mes (SAP).** Son las OV de venta y de servicio de SAP con fecha de entrega en el mes en
  curso, abiertas y cerradas, sin las anuladas. Su valor es la suma de sus líneas en soles: LineTotal + TaxTotal,
  moneda local. La tarjeta muestra:
  - el valor total con IGV;
  - lo ya despachado, en proporción a lo entregado de cada línea;
  - lo que falta despachar;
  - el valor sin IGV;
  - las OV ingresadas (emitidas) en el mes, como dato aparte.

  Para traer el valor de las líneas, el historial de SAP se relee completo una vez (HISTORIAL_VERSION 4). Hasta
  entonces se sigue viendo la tarjeta anterior del módulo.
- **Facturación del mes (SAP).** Muestra solo el neto (facturas − notas de crédito), con su valor sin IGV y la
  comparación con el mismo corte del mes anterior. Cuando el neto supera lo despachado de las OV del mes, se indica
  que incluye lo facturado de OV de meses anteriores y documentos sin OV.
- **Notas de crédito del mes (SAP).** Tarjeta nueva con:
  - el monto, la cantidad y el valor sin IGV;
  - el porcentaje de lo facturado (en amarillo si pasa del 10 %);
  - la comparación con el mes anterior.
- **Compras del mes (SAP).** Salen de las órdenes de compra de SAP (PurchaseOrders) emitidas en el mes, sin las
  anuladas. La tarjeta muestra el valor con IGV, lo recibido y lo que falta recibir (por la cantidad ya ingresada de
  cada línea), el valor sin IGV y el monto por moneda del documento. La tarjeta lleva al detalle
  `/gestion/compras-sap`, con filtro de fechas y tres vistas: por orden (qué se compró en cada una), por proveedor y
  por producto.
  - El vigilante las lee cada hora. La primera vez lee desde el inicio del historial; luego, lo modificado en SAP
    desde el día anterior a la última lectura, que incluye recepciones y cierres.
  - Si nunca se leyeron, se sigue viendo «Compras nacionales abiertas» del módulo.

## Ajustes del mismo día
Observación: «la facturación del mes es el total facturado menos las notas de crédito; al hacer clic debe verse el
detalle».

- **La tarjeta muestra la cuenta completa:** «facturado S/ X − notas de crédito S/ Y = S/ Z», más el valor sin IGV y la
  comparación con el mes anterior.
- **Facturación (SAP)** (`/gestion/facturacion-sap`):
  - total facturado, notas de crédito y facturación del periodo;
  - vistas por cliente (facturado, notas y neto), facturas, notas de crédito y todos los documentos;
  - filtro de fechas.

  La tarjeta de notas de crédito abre esta misma pantalla en la vista de notas.
- **OV con despacho en el periodo (SAP)** (`/gestion/ov-mes-sap`): una fila por OV con valor, despachado y saldo, con
  buscador y fechas.
- **Toda tarjeta abre su detalle con un clic:**

  | Tarjeta | Abre |
  |---|---|
  | OV | Órdenes de venta, o la pantalla nueva cuando hay valor de SAP |
  | OTIF | Nivel de servicio |
  | Cobranza | Finanzas |
  | Demanda | Análisis de la demanda |
  | Producción | Partes |
  | Compras | Detalle de SAP, o el consolidado |
  | Importaciones | Seguimiento de importaciones |
  | Costos | Costos y reposición |
  | Stock sin rotación | Rotación |

- **El vigilante relee el historial completo sin esperar a que cambie algo en SAP** cuando la última lectura es de una
  versión anterior. Así trae ya el valor de las líneas de OV.
- **Las órdenes de compra de SAP se leen en cuanto falten**, reintentando cada 10 minutos si falla. Un error al
  leerlas no frena el resto de la revisión.
- Mientras tanto, las tarjetas anteriores indican que el dato de SAP aparecerá apenas se lea.

## Pendiente de definir
SAP no separa por sí solo las compras **nacionales** de las **importaciones**. La tarjeta muestra todas las órdenes
de compra, con el monto por moneda del documento. Para separarlas hace falta el criterio de la empresa: serie de
numeración, grupo de proveedor u otro.

## No verificado
No se probó contra la base real de SAP. Los valores asumen que LineTotal y TaxTotal de la línea vienen en moneda
local (soles), como DocTotal en la facturación.

**Pruebas:** `tests/test_v55.py`. Suite completa: 682 pruebas pasan.
