# Ronda V45 (16-nov-2026): producción con SAP y con los Excel de Producción

Solo datos ficticios en pruebas. No verificado contra la base real de SAP.

## 1. Listas de materiales (recetas) desde SAP
- Nuevo dato de SAP «Listas de materiales (recetas)» (`BOM`): árboles de producto de SAP (`ProductTrees`) con sus
  componentes, cantidad, almacén y método de emisión, en el mismo formato de la carga «Lista de materiales» (con sus
  validaciones y versiones).
- El vigilante de SAP lo revisa cada hora y solo crea una versión nueva si SAP cambió. En «Lista de materiales» hay un
  botón «Traer recetas de SAP».
- El primer componente de cada receta se toma como principal (columna «Orden» vacía), como en el Excel de SAP.

## 2. Liquidaciones y recepción de PT automáticas
- `LIQUIDACION` y `BOM` se **agregan** a `sap_sync_tipos` y `sap_autoconfirmar` (una sola vez, sin quitar lo que ya
  esté configurado; regla nueva `PARAMS_AGREGAR`). Así, cuando SAP registra entradas por orden de fabricación, el
  vigilante trae la liquidación y la confirma sola; la recepción de PT trabaja sobre esas liquidaciones.
- Si se quitan luego de esas listas, no se vuelven a agregar.

## 3. Plan de producción desde Excel
En «Planeamiento de producción», «Actualizar con Excel» acepta:
- una fila por producto y fecha: Fecha · Código (artículo/producto/SKU) · Cantidad (plan/programado) · Línea ·
  Comentario; o
- una fila por producto con una columna por día (Código · Línea · fechas).
El encabezado puede estar en cualquiera de las primeras 15 filas. Por producto, fecha y línea: si ya hay una entrada
del plan, se actualiza (con la validación del Jefe de Producción para los cambios de un asistente); si no, se crea. En el
plan semanal o mensual se suman las fechas del mismo periodo. **Pendiente:** el usuario no envió aún su Excel; si sus
encabezados son otros, se agregan como sinónimos.

## 4. Liquidaciones por línea desde el Excel de Producción
En «Liquidación de proceso (CP-OPE-004)», «Subir el Excel de liquidaciones» lee el formato LIQUIDACIONES (el mismo que
exporta el módulo): una liquidación por hoja con datos del servicio y del producto, cada proceso (PROCESO · CALIDAD ·
SACOS · PESO POR SACO · SALDO), horas, operarios y observaciones. El SKU se reconoce por la descripción del producto (o
se indica al subir) y la línea por el título del proceso («1ER PROCESO : CIMBRIA») o se elige. Quedan en borrador.

**Pruebas:** `tests/test_v45.py`.
- Suite completa: **659 pruebas, todas pasan**.

## 5. V47 — El Excel PLANEAMIENTO de Producción
El usuario envió su Excel (no se guarda en el repositorio: tiene datos reales; se usó solo para conocer el formato).
Error: «El Excel no tiene filas con producto, fecha y cantidad», porque la columna CODIGO está vacía y las líneas
tienen otros nombres. Ahora se lee ese formato:
- Encabezado en la fila 3: FECHA · SEMANA · # OP · LINEA · PROGRAMADO · CLIENTE · **PLANIFICADO MP- KG** (cantidad) ·
  PRESENTACION · **U.M** · CODIGO · **PRODUCTO** · PRESENTACION / GRANEL · CANTIDAD / SACOS · **DATOS DE GRANEL**.
- Producto: por el código si lo hay; si no, por el **nombre** (sin importar tildes, mayúsculas, espacios ni signos). En
  selección (U.M = KG) se busca primero el granel («DATOS DE GRANEL»); en envasado (UNIDADES), el producto. Si el nombre
  es corto, se acepta solo si un único granel empieza así. No se adivina: las filas cuyo producto no coincide con un
  artículo del sistema **no se cargan y se listan** en el mensaje (fila y nombre).
- Líneas: «CIMBRIA + IQ» → CIMBRIA, «BHULLER + TRUER» → TRUER, «SELECCIÓN MANUAL» → SEL_MANUAL, «ENVASADO MANUAL» →
  ENV_MANUAL, «R1&R2» → R1 (grupo RAUMAK 1 Y 2), «R3» → R3.
- «# OP» y CLIENTE quedan en el comentario de la entrada. Las filas vacías o sin cantidad (p. ej. «#DIV/0!») se omiten.
- Con el Excel recibido se reconocieron las 47 filas con cantidad y todas sus líneas; los productos se reconocen contra
  el maestro de artículos de SAP del servidor (en la demostración los artículos son ficticios).

**Prueba:** `test_plan_con_el_formato_de_produccion_sin_codigo` (datos ficticios con la misma forma).
- Suite completa tras V47 (plan): **663 passed**.

## 6. V50 — El Excel general CONTROL DE PRODUCCION
En «Planeamiento → Actualizar con Excel» se puede subir el libro completo (29 pestañas): el plan se toma de la pestaña
**PROGRAMACION** (o de la primera con el encabezado del plan), no de la primera pestaña. Las demás pestañas aún no se
cargan (ver la revisión entregada al usuario: partes por línea, paradas, colaboradores, asistencia, etc.).

**Prueba:** `test_plan_desde_el_excel_general_con_varias_pestanas`.
- Suite completa V50: **670 passed**.
