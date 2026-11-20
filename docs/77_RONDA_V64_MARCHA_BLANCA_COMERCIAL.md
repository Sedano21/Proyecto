# Ronda V64 (20-nov-2026): marcha blanca del área comercial

Fuente: transcripción de la capacitación y marcha blanca con el área comercial (51 páginas) y las notas de la reunión.
La transcripción se leyó completa para no perder pedidos que no estaban en las notas. No se guardó en el repositorio
ni se copiaron nombres, clientes ni precios: las pruebas usan solo datos ficticios.

## Qué se hizo

### 1. Registro de la OV
- **IGV por línea:** cada línea es **Afecto** o **Exonerado / inafecto**.
  - Se propone el último código usado para ese artículo; si no hay, «ov_tax_code_por_defecto».
  - Los códigos son los de SAP: «ov_tax_code_afecto» = IGV y «ov_tax_code_exonerado» = EXO.
- **Totales:** subtotal (sin IGV), IGV y total.
  - En el formulario se ven en vivo. En la OV, en el resumen.
  - La OV impresa usa la misma tasa («igv_tasa»).
- **Total de la OC:** se registra el total de la orden de compra del cliente.
  - El sistema dice si cuadra con el total de la OV o la diferencia.
  - Tolerancia: «ov_tolerancia_total_oc», S/ 1.
  - La OC sigue siendo obligatoria (sin ella, borrador).
- **Precio por tramo de cantidad:** la lista de precios mínimos admite tramos («desde cantidad»).
  - Ejemplo: un mínimo desde 5 kg y otro desde 500 kg.
  - La OV y el aviso en vivo usan el tramo de la cantidad de cada línea.
  - Al proponer otro producto en una OV se puede indicar el nuevo precio.
- **Costo de la empresa al lado del precio:**
  - En la OV detenida por precio, quien aprueba y ve costos ve el costo de cada línea observada.
  - En la lista de precios hay columnas de costo y margen.
  - Filtros de la lista de precios: «precio mínimo bajo el costo», «margen bajo el mínimo» y «sin costo».
  - El costo lo calcula el sistema con lo que carga Costos y Presupuestos (Excel de costos). Falta que se carguen los
    costos (ver Pendientes).
- **Auxiliar y estiba:** la OV marca si la entrega va con auxiliar o requiere estiba.
  - Se completa con la ficha del cliente.
  - Se puede cambiar en cada OV, porque depende de la negociación.
- **Fecha de emisión y de ingreso:**
  - La lista de OV muestra la emisión y se puede ordenar por fecha de emisión.
  - El detalle muestra cuándo se ingresó al sistema y los días de la emisión a la fecha comprometida.
  - Sirve para medir el tiempo de atención de Operaciones.

### 2. Cerrar no es cancelar
- **Cancelar:** el cliente ya no quiere el pedido.
  - No cuenta como pedido ni como venta.
  - La causal es obligatoria («ov_causales_cancelacion»).
- **Cerrar:** la OV no se despachará, o no se despachará su saldo.
  - Cuenta como pedido. Lo no despachado es **venta perdida**, salvo que la causal sea de reprogramación
    («ov_causales_cierre_reprogramacion»).
  - La causal es obligatoria («ov_causales_cierre»).
  - Se puede cerrar también una OV con despacho parcial.
  - Si la OV ya está en SAP, se cierra también en SAP (Close).
- **OV cerrada en SAP:** sigue siendo «cerrada», aunque no tenga guía. Registra su venta perdida en kg.
- **Botones:** en «Gestionar» hay dos botones separados, cada uno con su causal.
- **Estado de OV y Informe comercial:** muestran cerradas y canceladas por separado, con sus causales. La venta
  perdida se da en kg y soles.
- **Causales:** las de los parámetros son una propuesta tomada de la reunión. Comercial las puede cambiar.

### 3. Kilos, vendedores, canales y OTIF
- **Kilos reales:** los envasados usan el peso del maestro y, si falta, el de la presentación de la descripción
  («* 500 G» → 0,5 kg).
  - Granel y MP ya van en kilos.
  - Ya no sale 0 kg cuando la OV es en unidades, ni se suman unidades con kilos.
  - Estado de OV muestra kg pedidos y kg despachados por OV (con el avance) y en total.
  - Los kilos se muestran con dos decimales.
- **Vendedores de SAP por usuario** (Administración → Vendedores de SAP):
  - A cada usuario comercial se le asignan los nombres de vendedor de SAP cuyas OV también son suyas. Ejemplo: una
    ejecutiva cuyas OV salen en SAP a nombre de otro vendedor.
  - Las ve en la lista de OV, Estado de OV, expedientes, seguimiento e indicadores.
  - Las OV de SAP con un vendedor que no es usuario se asignan al usuario que lo tiene, si es uno solo.
- **OV ingresadas por canal:**
  - En Gestión comercial, si el ejecutivo vende en más de un canal, su fila se abre por canal.
  - Las OV ingresadas también se muestran por canal, en el informe y en el inicio.
- **Indicadores legibles:** los textos chicos de los indicadores ya no se encogen en una sola línea.
  - En Facturación, el detalle largo pasa al texto emergente.
- **OTIF único:** con historial de SAP, Gestión comercial usa el mismo cálculo de SAP (OV frente a sus guías) para:
  - el general;
  - cada ejecutivo, canal y cliente;
  - los filtros.

  El seguimiento por ejecutivo hace lo mismo. Antes, por persona y por canal se medía con las OV del módulo.

### 4. Clientes, alertas y carga masiva
- **Correos por uso** en la ficha del cliente:
  - envío (recibe la guía y la factura);
  - facturación y pagos;
  - logística (citas y recepción).
- **Estiba** en la ficha del cliente.
- **Notas sobre la deuda** (lo propuesto para la v1.2):
  - El ejecutivo deja una nota (p. ej. «ya pagó y sigue figurando») y Finanzas recibe una alerta.
  - Queda el historial con usuario y fecha.
- **Stock disponible:** si una OV con faltante queda completa antes de su fecha, el ejecutivo recibe la alerta
  «Stock disponible». Así puede ofrecer adelantar la entrega o el recojo.
- **Devoluciones y rechazos:** las alertas de rechazo parcial, retorno y devolución (por recibir y observada) ahora le
  llegan al ejecutivo de la OV. Antes se avisaba por correo.
- **Cancelación y cierre:** también le llegan al ejecutivo.
- **Carga de OV con plantilla** (Órdenes de venta → Cargar con plantilla):
  - Plantilla homologada en Excel; también se acepta CSV con las mismas columnas (el que arma la IA).
  - Las filas con el mismo RUC, N° de OC y fecha forman una OV.
  - Cada OV pasa por las mismas validaciones del formulario.
  - Mientras el módulo está en prueba, **ninguna OV cargada se envía a SAP** hasta que Comercial la revise y pulse
    «Validar y enviar a SAP».
  - Si el cliente usa sus propios códigos, «homologacion_sku_cliente» los convierte.

## Ya existía (se verificó; no se cambió)
- Días no laborables del área comercial: los registra la Jefatura o la Coordinación de Ventas («Comercial»), y las demás
  áreas lo ven (V33).
- Fotos del catálogo: carga de fotos por código («catalogo.fotos»).
- Proyección comercial frente al promedio de 3 meses y al mismo mes del año anterior (Proyección de demanda, V23).
- % de OV modificadas por persona (Gestión comercial).
- La OC es obligatoria para registrar la OV. La validación manual antes de SAP se agregó para la carga masiva.

## Pendiente (requiere datos, una decisión o autorización)

| Pedido | Por qué no se hizo | Qué se necesita |
|---|---|---|
| Registrar clientes desde la API de SUNAT | Es un servicio externo: requiere una cuenta, sus credenciales y su autorización. | El proveedor de la API y la credencial. Se pedirá con el formulario seguro, no por el chat. |
| Envío automático de guía y factura por correo al cliente | Enviar correos a clientes es una acción externa: requiere autorización y la cuenta de correo de envío. Los correos ya se registran por uso. | Su autorización y la cuenta SMTP. |
| Costo de la empresa calculado por el sistema | La carga de costos existe, pero no hay costos cargados. | El Excel de costos de Costos y Presupuestos. |
| Tabla de homologación de códigos de clientes | La plantilla ya acepta el código del cliente. Falta la tabla. | La relación código del cliente → código nuestro. |
| Leer la OC en PDF con IA y llenar la OV | No se implementó en esta ronda. La plantilla CSV cubre el flujo que hoy hace la IA. | Definir si se quiere y con qué servicio. |
| Asignar los vendedores de SAP de cada ejecutiva | Son datos de configuración, no se ponen en el código. | Que Sistemas o la Jefatura los asigne en Administración → Vendedores de SAP. |
| Cargar la demanda comercial y el plan de producción | La carga ya existe. | Subir los archivos del mes. |
| Causales de cancelación y cierre | Las actuales son una propuesta. | Que Comercial las confirme o las cambie en Parámetros. |

## No verificado
- No se probó contra SAP real: la conexión con la base productiva sigue con el error -5027.
- Falta confirmar que SAP acepte «Orders(n)/Close» con el usuario del módulo.
- Falta confirmar que los códigos IGV y EXO sean los mismos en la base productiva.

## Pruebas
`tests/test_v64.py` (11 pruebas). Suite completa: 723 pruebas pasan.
