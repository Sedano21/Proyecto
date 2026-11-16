# Ronda V46 (16-nov-2026): recetas de SAP que sí aparecen y guía SUNAT editable

Solo datos ficticios en pruebas. No verificado contra la base real de SAP.

## 1. «Traer recetas de SAP» no mostraba nada
Causa probable (no se pudo ver el servidor): la carga que se crea con lo traído de SAP pasa por la validación de la
«Lista de materiales»; si alguna fila no la pasaba (componente repetido en la misma receta, línea sin almacén, cantidad
0), la carga quedaba «con errores» y **no se aplicaba**, y la pantalla de recetas solo muestra versiones aplicadas.
Además, si `BOM` no estaba en `sap_autoconfirmar` en el servidor, la carga quedaba esperando revisión.
Cambios:
- Un componente repetido en la receta se suma en una sola fila; si la línea no trae almacén, se usa el de la receta.
- Lo que aún no pasa la validación se **excluye con su motivo** («Excluida al traer de SAP: …») y se aplica el resto
  (recetas y liquidaciones de SAP).
- El botón «Traer recetas de SAP» siempre aplica lo traído.
- La pantalla muestra el estado de la lectura (en curso, error con su mensaje) y la última carga de SAP (estado, filas,
  filas excluidas y enlace a la carga). Mientras se trae, la página se actualiza sola.

## 2. Guía SUNAT editable
- En cada guía, «Editar la guía» permite corregir las líneas (código, descripción, lote, FP, FV, cantidad, UM; agregar
  o quitar líneas), la fecha de traslado, la placa y dejar una **observación** (p. ej. «salió menos»).
- Si cambian las líneas se pide el motivo. Cada edición queda en el **historial de cambios** de la guía (con lo que
  había antes) y en la auditoría.
- No se edita una guía ya registrada en SAP (se corrige en SAP) ni una cuyo stock ya se descontó en el módulo (primero
  se corrige la decisión de inventario, V42).
- Migración `0045` (columnas `observacion` y `ediciones` en `sunat_guides`).

**Pruebas:** `tests/test_v46.py`.
