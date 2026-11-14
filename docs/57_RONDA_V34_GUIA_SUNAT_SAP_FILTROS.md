# Ronda V34 (14-nov-2026): envío de la guía SUNAT a SAP y filtros de «Órdenes vs guías»

Sin migración nueva. Pruebas con datos ficticios.

## 1. «SAP respondió 400: Invalid value [DocumentLines.BaseLine][line: 1]» al enviar la guía EG07-457

**Causa:**
- La guía trae el **mismo producto en dos lotes**: PT-121 con los lotes 251026vg y 091117vg; PT-148 con 071011as y 307111as.
- El módulo mandaba **una línea de entrega por cada lote**, y las dos apuntaban a la **misma línea de la OV** (BaseLine).
- SAP rechaza dos líneas de la misma entrega basadas en la misma línea de la OV. «line: 1» es la segunda línea, la del segundo lote del PT-121.

**Corrección:**
- Ahora se manda **una línea de entrega por cada línea de la OV**, con la cantidad total y **los lotes dentro** (BatchNumbers), como lo hace SAP al copiar la OV a una entrega.
- Si la OV tiene el mismo producto en varias líneas, la cantidad se reparte según el saldo de cada una.
- El número de una OV puede repetirse entre series. Si SAP devuelve más de una OV con ese número, se toma la que tiene saldo abierto de los productos de la guía.

**Para reintentar:** en Guías SUNAT, pulse **«Enviar a SAP»** de nuevo en la guía EG07-457. Antes de que se instale esta versión puede mostrarse otra vez el mismo error.

**Otro arreglo en la misma pantalla:** el buscador de la lista había quedado dentro de cada guía. Ahora está una sola vez, arriba de la lista, con búsqueda por serie, número, destinatario, OV o producto y filtro por fecha de emisión.

## 2. «Órdenes vs guías»: una sola fila de pestañas y filtros que funcionan

**Pestañas:**
- Queda solo la fila **Órdenes de venta / Órdenes de servicio / Todas**.
- **Abiertas / Cerradas / Abiertas y cerradas** pasó a ser un **filtro**: «Situación en SAP», dentro del buscador, con la cantidad de cada una.

**Filtros que no hacían nada:**
- Elegir **«Orden por fecha»**, la situación, una fecha o un mes **no aplicaba nada**. En esta pantalla esos cambios solo se aplicaban con Enter o con la lupa.
- Ahora **se aplican al elegirlos**, en esta y en todas las pantallas con filtros.
- Los selectores de cliente con buscador también filtran al elegir un cliente de la lista.

## 3. Verificación

- `tests/test_v33.py` (6 pruebas): se agrega la guía con el mismo producto en dos lotes (una línea por línea de OV con sus lotes y elección de la OV correcta entre series) y la situación como filtro.
- `tests/test_v27.py`: se verifica que no se repita la línea de la OV.
- Suite completa: **630 pruebas, todas pasan**.
