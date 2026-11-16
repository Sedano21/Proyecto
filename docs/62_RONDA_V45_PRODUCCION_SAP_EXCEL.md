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
