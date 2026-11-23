# Ronda V69 (23-nov-2026): demanda proyectada, por despachar, fecha de despacho y adjuntos

Fuente: las observaciones del usuario con capturas de Demanda proyectada, Cómo va la empresa, Margen bruto y Estado de
OV, y tres archivos de ejemplo del análisis de abastecimiento (ficha de una familia, presentación a Gerencia y ficha
general). Los archivos de ejemplo solo sirvieron para entender el pedido; no se guardan en el repositorio. Las pruebas
usan solo datos ficticios.

## Qué se hizo

### Demanda proyectada → «Qué necesitamos tener»
- **«Ítems por comprar» mostraba `<built-in method items of dict…>`.** Era un error: el nombre de la columna chocaba
  con una función interna de la plantilla. Ahora muestra la cantidad de ítems y, al desplegarla, cada ítem con su
  **código, descripción y lo que falta**.
- **Sin RE- en «Mayores faltantes».** Los RE- (mano de obra y costos CIF) son recursos de la lista de materiales,
  no se compran. Ya se excluían del consumo de Producción con el parámetro «prefijos_no_material_bom» (RE-). Ahora
  también se excluyen de los faltantes, de «Ítems por comprar» y de las presolicitudes de compra. Por eso desaparece
  la fila «Otros insumos» cuando solo tenía RE-.

### Demanda proyectada → avance por ejecutivo
- Nueva sección **«Avance de lo proyectado por ejecutivo»**. Por cada ejecutivo muestra:
  - lo proyectado;
  - lo vendido (OV con compromiso en el mes, sin borradores ni canceladas), en kilos y en %;
  - lo despachado de lo vendido, en kilos y en %;
  - lo **pendiente por despachar** y lo **pendiente por vender**.
- Cada ejecutivo se despliega con la **lista completa** de productos (y los clientes, si la proyección es por
  cliente). Los productos vendidos sin proyección se marcan.
- El ejecutivo comercial ve solo su cartera; las jefaturas ven a todos.
- **¿De qué ejecutivo es cada proyección?** Hoy la proyección la cargan la Jefatura, la Coordinación y la Gerencia
  Comercial, no los ejecutivos. Por eso se agregó el **ejecutivo** a la proyección:
  - en el formulario «Registrar proyección», una columna nueva;
  - en el Excel, una columna opcional «ejecutivo», con el nombre o el usuario;
  - si no se indica, cuenta para el ejecutivo responsable del cliente;
  - si tampoco hay, va a «(sin ejecutivo asignado)».
- **Cuando un ejecutivo toma la cartera de otro** (por ejemplo, una ejecutiva que toma las OV de otro ejecutivo):
  en Administración → Vendedores de SAP por usuario se le asigna el nombre del otro. Esa pantalla ya existía (V64).
  Desde ahí:
  - ve como suyas las OV de esa cartera, que ya era el comportamiento anterior;
  - en Demanda proyectada, también la proyección y el avance de esa cartera.
  - No hace falta cargar nada en el sistema con nombres de personas.

### Cómo va la empresa → por despachar vencido y en plazo
- Nueva tarjeta **«Por despachar (OV abiertas SAP)»**. Toma el saldo de las órdenes de venta abiertas de SAP, sin las
  cerradas, las anuladas ni las líneas cerradas, y lo separa en:
  - **vencido**: la fecha de entrega ya pasó;
  - **en plazo**: la fecha de entrega es hoy o después.
- Muestra el valor en soles con IGV (proporcional al saldo), los kilos y el número de OV. La tarjeta sale en rojo
  si hay saldo vencido.
- Al hacer clic se abre **Por despachar**, con una pestaña para lo vencido y otra para lo que está en plazo. Por OV
  muestra:
  - cliente, emisión y entrega;
  - días de atraso, o días que faltan;
  - saldo en kg y en soles;
  - detalle por línea.
- Se descarga en PDF y Excel.

### Cifras completas (no partidas)
- Las cifras de los indicadores y de las columnas numéricas ya no se parten en dos líneas. Por ejemplo, antes
  «S/ 1 141 980.98» o «454 886.12» se veían cortadas.
- El tamaño de la cifra se ajusta al ancho de la tarjeta. En tablas anchas, la tabla se desplaza dentro de su tarjeta.

### Estado de OV → fecha de despacho
- Nueva columna **«Fecha de despacho»**:
  - si la OV ya salió, la fecha de su guía (SAP o SUNAT) o la de la salida registrada, con «tarde» si fue después
    del compromiso;
  - si no salió, la fecha de la ruta en que está programada («programada»);
  - si no tiene ruta, «sin programar».
- El indicador «Kg pedidos / despachados» aclara cuando suma solo la etapa elegida. En la captura, el filtro «Por
  preparar» mostraba 0 kg despachados porque esas OV aún no salen.

### Informe de reposición → análisis adjuntos
- Nueva sección **«Análisis adjuntos»** para subir el análisis de abastecimiento junto con el informe y entenderlo
  mejor: la ficha de una familia, la presentación a Gerencia, la ficha general o el Excel.
- Lleva título, familia y comentario, opcionales los dos últimos. Acepta varios archivos: PDF, PowerPoint, Excel,
  Word, CSV o imagen.
- Lo ve y lo puede subir quien ve el informe. Lo retira quien lo subió o la Gerencia.

### Seguimiento de importaciones → cargar Excel
- La carga del cuadro desde Excel ya existía, pero estaba al final de la página. Ahora hay un botón **«Cargar
  Excel»** arriba, junto a «Nueva importación».
- Se agregó una **plantilla** descargable con las columnas que lee la carga. Si el contrato ya existe se actualiza;
  si no, se crea.

## Pendiente o por validar

| Punto | Situación |
|---|---|
| Asignar la cartera tomada | Falta que Administración asigne, en «Vendedores de SAP por usuario», el nombre del ejecutivo cuya cartera se toma al usuario que la toma. Es un dato que no pongo yo. |
| Ejecutivo de las proyecciones ya cargadas | Las proyecciones registradas antes de esta ronda no tienen ejecutivo: cuentan para el ejecutivo del cliente o quedan «sin ejecutivo asignado». Para atribuirlas hay que volver a cargarlas con la columna «ejecutivo». |
| Margen bruto con costo 0 | En la captura, el margen sale al 100 % porque 273 líneas no tienen costo empresa cargado y todo sale «(sin canal)». No es un error de cálculo: falta cargar el costo empresa y el canal de los clientes. No se cambió en esta ronda. |
| OV con 0 kg pedidos | Una OV de la captura muestra 0 kg pedidos: su producto no tiene peso por unidad en el maestro. Se corrige cargando el peso del producto. |
| Fichas como las de ejemplo generadas por el sistema | En esta ronda se pueden **adjuntar** al informe. Generarlas automáticamente (ficha por familia con cobertura por marca y compra mínima) sería un desarrollo aparte, con reglas que hay que validar con Operaciones. |

## No verificado
- La tarjeta y la pantalla «Por despachar» se probaron con OV de SAP ficticias. Faltan cifras reales: se verán cuando
  el vigilante de SAP vuelva a leer la base productiva, que sigue con el error -5027 intermitente.

## Pruebas
`tests/test_v69.py` (7 pruebas). Migración 0057: tabla de análisis adjuntos y ejecutivo en la proyección de demanda.
