# Ronda V53 (17-nov-2026): compras por OV que ya se atendieron

Observación: «Compras nacionales (consolidado)» seguía mostrando panetones por comprar para OV que ese día ya subieron
sus guías. Las presolicitudes de compra nacidas de una OV no se revisaban cuando la OV se atendía.

## Cambio
Servicio `compras_ov.revisar`: una OV deja de necesitar lo comprado de un producto cuando
- está cerrada o anulada en SAP (historial de SAP), o
- sus guías de SAP ya cubren lo pedido de ese producto, o
- en el módulo está despachada, entregada o cancelada, o su línea de ese producto ya se despachó.
Lo atendido se quita de la presolicitud y del consolidado. Si la presolicitud aún no pasó a Compras (borrador o
pendiente de Logística) se reduce o se **cancela sola** (queda en su motivo y en la auditoría); si ya está en Compras
(cotización, orden, etc.) no se toca y se **avisa** a Compras y al Jefe de Logística (alerta COMPRA_REVISAR_OV_ATENDIDA).

Se ejecuta cada vez que el vigilante lee el historial de SAP (cuando cambian OV o guías, cada minuto) y al abrir el
consolidado de compras, para que no quede nada pendiente que ya se resolvió.

**Pruebas:** `tests/test_v53.py`.
