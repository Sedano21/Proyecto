# Ronda V26 (11-nov-2026): OV vs guías de SAP, facturas, canales, filtros, fumigados y picking

Pruebas con datos ficticios.
- Lectura de SAP: OV, guías y facturas.
- Escritura de SAP: solo se registran en el módulo. En SAP no se escribe nada nuevo.
- Sin migración nueva: se usan columnas y tablas que ya existían.

## 1. Lo pedido y dónde quedó

| Observación | Implementación | Dónde |
|---|---|---|
| OV abiertas comparadas con la guía en SAP: despachos completos o incompletos | Pantalla **«OV abiertas vs guías de SAP»**. Por cada OV abierta: solicitado, entregado según SAP, pendiente y lo **guiado** según las guías de SAP, con sus guías y facturas. Estados: **Incompleto (parcial)**, **Completo** (entregada pero todavía abierta en SAP: hay que cerrarla) y **Sin despacho**. Marca **⚠** cuando lo guiado no cuadra con lo entregado. Indicadores arriba (cada uno filtra) y descarga en Excel. | Integración SAP → botón «OV abiertas vs guías de SAP» |
| Que también traiga las facturas | Tarjeta **«Facturas y notas de crédito → Traer de SAP»**. Lee de SAP las facturas y notas de crédito de los últimos `sap_facturas_dias` (60) días, sin las anuladas. Las registra en **Finanzas → Cobranza**: las nuevas se crean y en las existentes se actualizan monto y **saldo según SAP**. Cada una queda unida a su OV, directa o a través de la guía; la nota de crédito queda unida a la factura que afecta. Además, la carga de **guías** ahora trae la factura de cada guía para la conciliación. | Integración SAP; Finanzas → Cobranza y condiciones |
| «Traer de SAP» se cortaba | Corre en segundo plano y la tarjeta muestra el avance. Las guías piden los números de OV en grupos de 20 (V25b). | Integración SAP |
| Los filtros deben buscar mientras se escribe | En todas las listas con buscador, el filtro se aplica solo **desde la 2.ª letra**, al dejar de escribir (0,45 s), sin pulsar «Buscar». Las listas desplegables y fechas del filtro también filtran al instante. El cursor se queda en el buscador. Los selectores con buscador incorporado ya filtraban letra a letra. | Todas las listas |
| En la OV y en el catálogo no salía el desplegable de canal | Había dos fuentes distintas: Clientes tomaba los canales de las fichas y de la tabla grupo → canal; la OV y el catálogo, solo de las listas de precios (aún no cargadas en el servidor). Ahora **una sola lista** en todas partes: canales de las listas de precios, los agregados, los de la tabla grupo → canal y los asignados en fichas. | OV, catálogo, ficha y lista de clientes |
| Botón para agregar canales | En **Clientes**, botón **«+ Agregar canal»** que abre una ventana: nombre del canal, se agrega y vuelve a la lista. Muestra los canales actuales y enlaza a «Canales y grupos». Lo usan Coordinador y Jefe de Ventas y Sistemas (`canales.gestionar`). | Comercial → Clientes |
| Producto ya fumigado: máximo 20 días almacenado | Al registrar el **fin de la fumigación** se guarda la fecha en el lote; también cuenta la liberación de Calidad. Cada día se revisan los lotes fumigados que siguen con stock. **Aviso a los 15 días** (`fumigado_dias_aviso`) y **alerta a los 20** (`fumigado_dias_max`) a Calidad y a Almacén (al coordinador del almacén del lote y a la Jefatura de Logística). Pantalla de seguimiento **«Producto fumigado almacenado»** con días almacenado y semáforo. Una nueva fumigación reinicia el conteo. | Calidad (y Almacén) → Producto fumigado almacenado |
| Picking agrupado por cliente | La programación de picking ya agrupaba por cliente; se mantiene. | Almacén → Programación de picking |
| El operario solo registra la cantidad; lote y fechas bloqueados, salvo si picó otro lote (y entonces jala FP y FV) | En el formato, el lote y las fechas salen del lote reservado y están **bloqueados (🔒)**: el operario llena solo la cantidad despachada y los bultos. Si picó otro lote, «Cambiar lote»: al elegir el lote, la **fecha de producción y la de vencimiento se completan solas** con las de ese lote. Al registrar se actualizan el formato y el stock. | Picking → su tarea |
| Catálogo general y específico por tipo (MP, MQ, PT, GR) | Filtro **«Catálogo»**: General (todos) o uno por tipo según el prefijo del código (MP, MQ, PT, GR y los demás que existan). Se combina con canal, destacados y fotos. | Comercial → Catálogo |

## 2. Parámetros nuevos

| Parámetro | Valor | Estado |
|---|---|---|
| `sap_facturas_dias` | 60 | PROPUESTO |
| `fumigado_dias_max` | 20 | DEFINIDO (pedido de la empresa) |
| `fumigado_dias_aviso` | 15 | PROPUESTO |

**Alerta nueva:** `FUMIGADO_ESTANCADO` para Calidad, Almacén y la Jefatura de Logística.

## 3. Notas

- **Facturas y permisos:** traerlas solo lee de SAP. El usuario de integración necesita permiso de lectura sobre
  facturas y notas de crédito de clientes. Si no lo tiene, el mensaje de error lo dice. Las guías se traen igual,
  sin la columna de factura.
- **Sin guía en la conciliación:** si SAP marca entregas de una OV pero no hay guías en la carga, la pantalla lo
  advierte. Suele ser una guía anterior al periodo traído; se amplía `sap_despachos_dias`.
- **«Completo, sin cerrar en SAP»:** el cierre se hace en SAP. Al volver a traer las OV, el módulo la cierra.

## 4. Verificación

- `tests/test_v26.py` (6 pruebas):
  - conciliación OV vs guías y pantalla;
  - facturas desde SAP (OV por la guía, nota de crédito con su factura, saldo de SAP, sin duplicar);
  - fumigados (aviso, alerta, sin duplicar, pantalla);
  - fin de fumigación registrado en el lote;
  - canales únicos y alta desde Clientes;
  - catálogo por tipo.
- `tests/test_sap_segundo_plano.py`: carga en segundo plano y guías con su factura.
- Suite completa: **581 pruebas, todas pasan** (una prueba anterior se ajustó porque ahora la carga de guías también lee las facturas del periodo).
- Revisión en navegador:
  - OV vs guías;
  - ventana «Agregar canal»;
  - catálogo por tipo;
  - fumigados;
  - búsqueda al escribir (filtró al escribir «dem» y el cursor siguió en el buscador).
