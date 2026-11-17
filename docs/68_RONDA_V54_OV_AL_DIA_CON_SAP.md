# Ronda V54 (17-nov-2026): la OV del módulo al día con SAP

Observaciones:
- Una OV con guía seguía «abierta». Debe pasar a despacho (parcial o completo) descontando lo guiado. Completa, se
  cierra.
- En el expediente se debe ver si ya se facturó.
- «Sin despachos recientes al cliente» aparecía aunque sí había despachos.
- En Estado de OV todo figuraba «Detenida». Con guía, factura o entrega, el stock, el picking y la preparación de lo
  entregado ya se cumplieron.
- En Expedientes por cliente y despacho, al tocar un estado bloqueado se debe ver el motivo. Por ahora solo se bloquea
  por precio, y se sigue mostrando si con el stock de hoy se llega a atender.

## Qué cambió

**Servicio `ov_sap`**. El módulo lee SAP y lo aplica a la OV sin esperar a que alguien lo registre:
- **Guías.** Lo guiado se descuenta de cada línea (despachado). Cuenta lo guiado en SAP (entregas basadas en la OV,
  por su número o por el número que SAP le dio) y en las guías SUNAT subidas al módulo que aún no están en SAP. Una
  guía que está en los dos lados se cuenta una vez.
  - Si cubre todo lo pedido, la OV queda **DESPACHADA** y libera sus reservas.
  - Si cubre una parte, queda **DESPACHO_PARCIAL**: lo guiado libera su reserva y el saldo conserva la suya. Cuando
    llega la guía del saldo, pasa a DESPACHADA.
- **Anulada en SAP sin guías.** La OV queda CANCELADA («Anulada en SAP»).
- **Cerrada en SAP con parte guiada.** La OV queda CERRADA: el saldo no se atenderá.
- Nada se envía a SAP: SAP es la fuente.

**Cuándo se aplica:**
- Cada vez que el vigilante lee el historial de SAP, es decir cuando cambian OV o guías.
- Al abrir el detalle de la OV, Estado de OV y Expedientes por cliente y despacho.

**Bloqueos.** Por ahora la OV solo se bloquea por precio (V44). Las OV que quedaron BLOQUEADAS antes por anticipación
o por falta de opción se reactivan y se vuelven a evaluar (reservan stock).
- Queda guardado si con lo disponible se llega o no a la fecha. Se muestra en la OV y en expedientes, sin bloquear.
- Si la regla se vuelve a encender en Parámetros, ya no se reactivan.

**Estado de OV:**
- «Detenida» es solo la OV bloqueada o retenida por precio, con el motivo en «¿por qué?».
- La OV evaluada sin problemas figura «Por preparar».
- Se agregan las etapas «Despacho parcial» y «Despachada (con guía)». La OV despachada ya no cuenta como atrasada.
- Con guía, los pasos Stock, Picking, Ruta y Guía se dan por cumplidos en lo guiado, con el número de guía.
- La Entrega sigue siendo la que confirma Distribución: SAP no informa la entrega al cliente.

**Detalle de la OV:**
- El expediente lista las guías (de SAP o subidas al módulo) con sus productos y cantidades, además de las facturas y
  notas de crédito de Finanzas que SAP liga a la OV.
- Avisa si la OV tiene despacho parcial o si se reactivó, con su evaluación.

**Cumplimiento con el cliente** (recuadro de la OV). Usa las OV de SAP del cliente y sus guías, como el nivel de
servicio. Muestra las guías de cada OV y enlaza las que están en el módulo.

**Expedientes por cliente y despacho.** Al tocar un estado con OV detenidas o bloqueadas se ve, por OV:
- el motivo;
- la evaluación de hoy (stock y % cubierto, y si llega a la fecha cuando se evaluó).

## No verificado
No se probó contra la base real de SAP. Cuando el vigilante lea el historial, las OV con guía en SAP cambian de estado
solas; conviene revisar algunas en Estado de OV.

**Pruebas:** `tests/test_v54.py`.
