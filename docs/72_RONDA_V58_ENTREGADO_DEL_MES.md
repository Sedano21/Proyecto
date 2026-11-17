# Ronda V58 (18-nov-2026): lo entregado del mes, valorizado con SAP

## Observación
En «Cómo va la empresa» indicar el valor de lo entregado, sumando despachos totales y parciales, valorizado según SAP,
con su detalle.

## Qué cambió
**Tarjeta «Entregado en <mes> (SAP)».** Suma todas las guías (entregas) de SAP con fecha en el mes, hasta hoy.
- **Valor:** el de cada línea de la guía en SAP, en soles con IGV (LineTotal + TaxTotal).
- **Reparto según cómo quedó la OV**, con todas sus guías (de este u otro mes):
  - **completas**: lo guiado cubre todo lo pedido;
  - **parciales**: queda saldo por despachar;
  - **parciales ya cerradas**: la OV se cerró en SAP con saldo;
  - **sin OV**: guías no basadas en una OV.
- También muestra el número de guías y de OV, el valor sin IGV y la comparación con el mismo corte del mes anterior.

**Detalle** (`/gestion/entregado-sap`), con clic en la tarjeta:
- totales por tipo de despacho; cada total filtra la lista;
- lista por guía (fecha, guía, cliente, OV, despacho de la OV, líneas, valor) o por cliente;
- buscador, filtro de fechas y de tipo, y paginador.

**Valor de las guías.** Se agregan a las guías leídas de SAP el valor de cada línea y su IGV (migración 0052). El
historial se relee completo una vez (HISTORIAL_VERSION 5), en la próxima revisión del vigilante. Hasta entonces, las
líneas sin valor se valorizan con el precio de su OV en SAP y la tarjeta lo indica.

## No verificado
No se probó contra la base real de SAP.

**Pruebas:** `tests/test_v58.py`.
