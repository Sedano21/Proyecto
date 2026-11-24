# Ronda V71 (24-nov-2026): guías y facturas de SAP en el expediente, novedades de la carga y recepción en el cliente

Fuente: los mensajes del usuario del 24-nov. Pidió:
- ver e imprimir desde el módulo la guía y la factura que ya están en SAP, en todas las OV;
- ver por cliente y fecha de despacho todos los SKU y su guía, sin entrar OV por OV;
- reportar el faltante o sobrante al validar la carga;
- registrar la recepción en el cliente, conforme o con inconformidad por SKU.

Las pruebas usan solo datos ficticios.

## Por qué en unas OV se veían la guía y la factura y en otras no
- **La factura nunca quedaba enlazada.** El vigilante guardaba cada guía de SAP con el campo «factura» vacío, y las
  facturas se leían sin saber de qué guía ni de qué OV salían. En la OV y en el expediente solo se veía el número de
  facturas cargadas a mano.
- **Algunas guías no quedaban en su OV.** Solo se asociaban a la OV las guías hechas directamente desde la orden de
  venta. Una guía hecha desde una factura (por ejemplo, una factura de reserva) quedaba sin OV.
- **El expediente por cliente y despacho no mostraba guías ni facturas de SAP**, solo los adjuntos de la OV.
- **El expediente del cliente solo tomaba las guías de las cargas de Excel**, no las que lee el vigilante.

## Qué se hizo
### Guías y facturas de SAP enlazadas
- **Facturas.** Al leerlas de SAP se guarda de qué guías (entregas) y de qué OV salen cada factura y cada nota de
  crédito. La primera vez se relee todo el historial para completar las ya cargadas.
- **Guías hechas desde una factura.** Quedan en la OV de esa factura y con su factura.
- **Cada guía muestra su factura**, aunque SAP no la cite en la guía.

### Todo se ve e imprime desde el módulo
- **Expediente por cliente y despacho**, por cada OV:
  - las guías de SAP (o la guía SUNAT subida);
  - las facturas y notas de crédito de SAP;
  - la guía firmada por el cliente y la foto de la entrega;
  - los adjuntos.
  - Cada documento se abre para ver e imprimir.
  - Con las casillas se eligen varios y se imprimen juntos («Ver e imprimir seleccionados» o «PDF de los
    seleccionados»).
- **Detalle de la OV:** facturas de SAP con enlace, además de las guías.
- **Expediente del cliente** (guías, facturas y notas de crédito): ahora incluye las guías que lee el vigilante, con
  enlace a la guía, a su factura y a la guía firmada.
- **Datos de cada documento:**
  - lo que ya leyó el vigilante;
  - al abrirlo, una lectura de solo consulta en SAP completa la dirección, los lotes y el detalle de la factura;
  - si SAP no responde, se muestra lo ya leído con un aviso.
- **No es el comprobante electrónico.** La guía y la factura impresas desde el módulo son una representación interna
  de los datos de SAP; el comprobante electrónico se imprime desde SAP o el OSE.

### Todos los SKU por cliente y fecha de despacho
- En «Expedientes por cliente y despacho», cada grupo (cliente y fecha de despacho; si se reprogramó, la nueva fecha)
  tiene «N SKU · ver productos y guías».
- Despliega todos los SKU de todas las OV del grupo: OV, pedido, despachado, pendiente y la guía (y factura) que los
  llevó, con enlace.

### Faltante o sobrante al validar la carga
- En **Carga de unidades** y en el **detalle de la ruta**, quienes validan la carga reportan ahí mismo «Reportar
  faltante o sobrante»:
  - lo pueden reportar Almacén, el Auxiliar de Despacho, el chofer, Seguridad y Calidad;
  - se elige el SKU de la pre-guía (o se escribe el código si sobra algo que no está en ella), la cantidad y un
    detalle.
- Al reportar:
  - se registra una incidencia (faltante o sobrante al validar la carga);
  - avisa al almacén que corresponde;
  - la carga deja de estar validada.
- **La salida espera** hasta que Almacén (Líder, Asistente, Supervisor o Coordinador) marque la novedad como
  resuelta, indicando cómo.

### Recepción en el cliente
- En la conformidad de entrega se elige **«Conforme»** o **«Con inconformidad»**.
- Con inconformidad, por cada producto de la guía:
  - lo despachado según la guía y cuánto recibió el cliente;
  - el tipo: **faltante** (no llegó), **producto observado** (mal estado, con la cantidad observada) o
    **devolución**;
  - un detalle.
- Se registra una incidencia por tipo:
  - faltante en la entrega;
  - producto observado (va a Calidad);
  - devolución.
- Lo que el cliente no recibe por mal estado o devolución queda **por recibir en Almacén** (Devoluciones por recibir),
  con la guía de la entrega.
- Si marca «Conforme» pero indica menos de lo despachado, el sistema pide marcar la inconformidad.
- **La guía firmada** (foto o PDF) y **la foto de la entrega** quedan como documentos de la OV. Por eso se ven en el
  expediente de la OV, en el del despacho y en el del cliente.

## Pendiente o por validar
| Punto | Situación |
|---|---|
| Datos reales de SAP | Las guías y facturas de producción se completan cuando el vigilante vuelva a leer SAP: la primera lectura de facturas relee todo el historial para enlazarlas. Sigue pendiente el cambio a admin1 y el -5027 intermitente. |
| Guías hechas desde una factura y ya leídas antes | Para enlazar a su OV las guías hechas desde una factura y ya leídas, hay que releer las guías desde el historial («Actualizar con SAP» completo). Las nuevas se enlazan solas. |
| Comprobante electrónico | El PDF oficial (con QR) de SUNAT sale de SAP o del OSE; el módulo no lo genera. |

## Pruebas
`tests/test_v71.py` (5 pruebas). Migración 0059: origen de las facturas de SAP y recepción de cada entrega.
