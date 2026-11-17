# Ronda V56 (17-nov-2026): facturación semiautomática con validación del facturador

## Observación
- El rol de Facturación debe poder facturar como en SAP. El sistema prepara la factura, pero siempre bajo la
  validación del facturador antes de subirla a SAP. El facturador puede:
  - editar lo mal digitado;
  - agregar una observación;
  - eliminar ítems.
- Se puede facturar en SUNAT y regularizar después, como la pestaña de Guías SUNAT.
- Distribución sigue igual que con las pre-guías al terminar el picking, validadas por el asistente o el coordinador:
  editar, eliminar ítems, etc. Todo queda en el expediente del cliente.

## Qué hace el módulo

**1. Pre-factura automática.** El vigilante lee de SAP las guías (entregas) abiertas, es decir aún no facturadas. Lo
hace cuando cambian guías o facturas, y la primera vez.
- Por cada guía sin pre-factura, prepara la factura con lo que trae la guía: productos, cantidad por facturar
  (RemainingOpenQuantity), precio, descuento, impuesto, almacén, cliente y OV.
- La guía puede venir de la pre-guía validada en el módulo o haberse hecho en SAP.
- Avisa a Facturación con la alerta PREFACTURA_POR_VALIDAR.

**2. Validación del facturador** (menú Finanzas → «Facturación (pre-facturas)», permiso `facturacion.cargar` del rol
Facturación):
- **Corregir:** cantidad (no más de lo guiado), precio unitario y descuento %, quitar ítems, fecha de la factura y
  observación (va en los comentarios de la factura en SAP).
- Si cambian cantidades, precios o ítems, el motivo es obligatorio. El historial guarda quién, cuándo y cómo estaban
  antes.
- **Validar y crear en SAP:** se crea la factura (Invoices) **basada en la guía** (BaseType 15, con la línea de la
  guía), como la haría el facturador en SAP.
  - Si la escritura en SAP no está habilitada para esa base, queda «Validada» y se crea sola cuando se habilite.
  - Si SAP la rechaza, queda el error, se avisa con la alerta PREFACTURA_ERROR_SAP y se puede reintentar o reabrir
    para corregir.
- **Observar** con motivo: avisa al ejecutivo de la OV.
- **Descartar** con motivo, cuando no se factura con esa guía.
- Si la guía se factura directamente en SAP, la pre-factura se cierra sola como «Facturada en SAP».

**3. Regularización de facturas emitidas en SUNAT.** Se sube el XML (UBL) o el PDF de la factura.
- Se lee la serie y el número, la fecha, el cliente (RUC), el total y, del XML, los ítems con código, cantidad y
  precio. Del PDF no se leen los ítems: se toman de la guía y se revisan.
- Se une sola a la guía del cliente si hay una sola por facturar; si no, se elige. La pre-factura de esa guía queda
  reemplazada.
- Al validarla se registra en SAP basada en la guía, con la serie y el número de SUNAT (FolioPrefixString y
  FolioNumber).
- No se puede subir dos veces la misma factura.

**4. Expediente.** La factura creada en SAP queda en los documentos de la OV. La pestaña Expediente de la OV lista sus
pre-facturas con su estado y su número en SAP.

**5. Pre-guía (Distribución).** Sigue el flujo existente: se genera al terminar el picking y la revisan y validan el
Coordinador o el Asistente de Distribución (`distribucion.guia_modificar`).
- **Se agrega:** quitar ítems de la guía, con motivo obligatorio. Queda en el rastro de cambios como «ítem quitado».
- Se mantiene lo de antes: editar fecha, punto de llegada, cantidades, presentación y lotes, observar o aprobar.
- La guía aprobada se registra en SAP y queda en el expediente.

## No verificado / por confirmar
- **Base real de SAP.** No se probó contra ella.
  - Puede que la localización exija campos propios de la factura electrónica, como la serie o campos de usuario.
    En ese caso SAP devolverá el mensaje: queda en la pre-factura y se agrega el campo, como se hizo con las guías.
  - La escritura sigue limitada a las bases de «sap_escritura_empresas».
- **Primera lectura.** Prepara pre-facturas para todas las guías abiertas de SAP desde el inicio del historial. Las
  que en la práctica ya se facturaron sin basarse en la guía deben descartarse una vez, con motivo.

**Pruebas:** `tests/test_v56.py`.
