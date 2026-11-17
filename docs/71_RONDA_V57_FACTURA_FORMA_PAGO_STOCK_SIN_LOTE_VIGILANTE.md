# Ronda V57 (18-nov-2026): datos que ingresa el facturador, stock sin lote y vigilante más amplio

## Observaciones
- En Facturación, las métricas deben mostrar también las notas de crédito.
- En «Stock y reservas» no aparecía el panetón, que sí está en el maestro de artículos.
- En la factura, el facturador ingresa la forma de pago y, si corresponde, junta las guías en la factura («de guías a
  factura»). Lo demás lo arrastra la guía. Se tomó como referencia el formato de la factura electrónica de la empresa;
  sus datos no se guardan en el repositorio.
- Todo debe actualizarse con el vigilante, que detecta los cambios en SAP. Las listas largas, con paginador.

## Qué cambió

**Facturación (pre-facturas).**
- **Métricas del mes desde SAP**, cada una con su detalle: facturado, notas de crédito y facturación (facturado −
  notas).
- **Forma de pago.** Se elige de las condiciones de pago de SAP (PaymentTermsTypes). El vigilante las lee al preparar
  las pre-facturas. Viene propuesta con la de la guía (PaymentGroupCode) y calcula el vencimiento con sus días; el
  vencimiento se puede cambiar. Es obligatoria para validar.
- **N° de orden de compra del cliente.** Viene de la guía (NumAtCard) o de la OV del módulo, y se puede editar.
- **En SAP la factura lleva:** PaymentGroupCode, DocDueDate (vencimiento) y NumAtCard (OC).
- **De guías a factura.** En una pre-factura se pueden juntar otras guías por facturar del mismo cliente.
  - Cada línea conserva su guía de origen (BaseEntry y BaseLine).
  - Las pre-facturas juntadas quedan descartadas como «unidas» y no se vuelven a preparar.
- **PDF de la factura de SUNAT.** Ahora se lee con el formato de la factura de la empresa:
  - serie y número, RUC del cliente (distinto del RUC propio), fecha de emisión y vencimiento;
  - forma de pago, N° de orden de compra y N° de guía(s) de remisión;
  - ítems (cantidad, código, descripción, P.U.) y el importe total.
  - Del XML se leen además la guía (DespatchDocumentReference), la OC (OrderReference) y la forma de pago y el
    vencimiento (PaymentTerms).
  - La factura se une a la guía que **cita**, aunque el cliente tenga varias guías abiertas.

**Stock de SAP.**
- **Artículos sin lote.** La lectura del stock usaba solo la consulta de stock por lote (OBTQ). Por eso los artículos
  que SAP no maneja por lote, como los panetones, no aparecían. Ahora se suman los artículos de inventario sin lote,
  con su stock por almacén (Items → ItemWarehouseInfoCollection.InStock), como lote «SIN LOTE».
- **Almacenes habilitados.** Si aun así un artículo no aparece, revisar que su almacén de SAP esté habilitado en el
  módulo.

**Vigilante (cada minuto).** Además de OV, guías, facturas, notas de crédito, entradas y salidas, ahora detecta:
- órdenes de compra y recepciones de compra;
- traslados entre almacenes;
- artículos y socios de negocio.

Qué hace con cada cambio:
- Cuando algo mueve el stock (guías, entradas o salidas, recepciones de compra, traslados), relee el stock al
  instante, ya no solo cada hora.
- Con un artículo nuevo o modificado relee los productos; con un cliente, los clientes; con una compra, las órdenes de
  compra.
- Cada carga se hace una sola vez por vuelta.

**Paginador.** Las listas de compras de SAP (por orden, proveedor y producto) y de facturación por cliente ahora se
paginan.

## No verificado
No se probó contra la base real de SAP. En particular, conviene confirmar en la primera factura que SAP acepte la
forma de pago y el vencimiento enviados.

**Pruebas:** `tests/test_v57.py` (y `tests/test_v56.py` actualizado: la forma de pago es obligatoria). Suite completa: 693 pruebas pasan.
