# Ronda V52 (17-nov-2026): facturación del mes desde SAP

Observación: Comercial reporta al 14/11 una facturación de S/ 2 431 718.99 − notas de crédito S/ 383 414.40 = S/ 2 048 304.59,
y el módulo mostraba alrededor de un millón.

## Causa
1. La tarjeta «Venta del mes» de «Cómo va la empresa» sumaba las **OV registradas en el módulo** (no la facturación).
2. Las facturas de SAP solo quedaban en el módulo si el **cliente ya existía** en su maestro (las demás se descartaban
   con «cliente no encontrado»).
3. El vigilante de SAP traía solo las facturas de los **últimos 3 días** cuando cambiaban.

## Cambios
- Tabla nueva `sap_facturacion` (migración 0048): todas las facturas y notas de crédito de SAP no anuladas, con su total
  en soles (DocTotal, moneda local) y su IGV (VatSum), **sin depender del maestro de clientes**. Lo anulado en SAP se
  quita.
- El vigilante la llena la primera vez desde el inicio del historial de SAP (1-ene-2025, para comparar con el año
  anterior) y luego, cada vez que cambian facturas o notas de crédito, relee el mes en curso y el anterior.
- «Cómo va la empresa»: nueva tarjeta **«Facturación del mes (SAP)»** = facturas − notas de crédito (con IGV, y el neto
  sin IGV), comparada con el mismo corte del mes anterior; la tarjeta de OV se llama ahora «OV ingresadas del mes».
- Inicio de Comercial e informe comercial: la «Facturación» usa la misma fuente (sin filtro de cliente o vendedor; con
  un canal, por el canal del cliente).
- No verificado contra la base real de SAP: la cifra se debe comparar con el reporte de Comercial una vez que el
  vigilante haya leído la facturación (si Comercial reporta sin IGV, comparar con el «sin IGV» de la tarjeta).

**Pruebas:** `tests/test_v52.py`.
