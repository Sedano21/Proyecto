# Ronda V65 (20-nov-2026): reintento del ingreso a SAP y consulta de facturas duplicadas

## Ingreso a SAP: el primero falla y el segundo entra
Prueba manual en PowerShell contra la base productiva: con varios usuarios, el primer `Login` responde 500
(«Switch company error: -5027») y el segundo, idéntico, entra.

- El módulo ahora reintenta **solo ese error**: hasta «sap_login_reintentos» veces (3), con una pausa de
  «sap_login_espera_seg» segundos (2) entre intentos.
- Cualquier otro error (contraseña, usuario, licencia) se informa al primer intento.
- Es una mitigación. La causa está en el Service Layer del servidor (un proceso que no carga la base productiva a
  la primera); conviene que el proveedor que administra el servidor lo revise.

## Consulta de Finanzas: facturas de proveedor duplicadas en el reporte de cuentas por pagar
Se revisó el código del módulo. El módulo nunca crea facturas de proveedor ni notas de débito en SAP: no escribe
PurchaseInvoices, PurchaseCreditNotes ni PurchaseDownPayments. Solo escribe:
- órdenes de venta (Orders);
- entregas o guías (DeliveryNotes);
- facturas de cliente desde las pre-facturas (Invoices);
- entradas de inventario (InventoryGenEntries);
- ofertas (Quotations);
- la consulta de stock (SQLQueries).

Además, solo escribe en las bases de «sap_escritura_empresas», que por defecto es solo la base de pruebas.
Los folios del reporte (DI-, FT-, RH-) son documentos de proveedores con fecha de emisión 30/10.

## Pruebas
`tests/test_v65.py`.
