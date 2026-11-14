# Ronda V42 (14-nov-2026): guía SUNAT con tipo de documento, OTIF con SAP, producción por línea y mejoras de pantalla

Observaciones del usuario y lo que se hizo. Solo datos ficticios en demostración y pruebas. Nada de esto se verificó
contra la base real de SAP; las fórmulas son las de la empresa (V23) aplicadas a los datos de SAP.

## 1. Guía SUNAT a SAP: «(15) Debe indicar el tipo de documento (Pestaña Finanzas)»

- El tipo de operación ya se enviaba (V41). Ahora SAP pide el **tipo de documento** de la pestaña Finanzas: es el
  campo estándar `Indicator` de la entrega.
- Al enviar la guía, se copia el `Indicator` (y los campos de tipo de operación) que tienen las últimas 30 entregas de
  SAP de la misma serie (p. ej. EG07). No se inventa el valor: si las entregas no lo tienen, se envía sin él.

## 2. Corregir la decisión de inventario de una guía

- Permiso nuevo `guias.corregir_inventario` (Jefatura y Gerencia de Operaciones).
- En la guía, «Corregir la decisión de inventario» pide el motivo y anula la decisión: si se había **descontado** del
  lote, lo descontado vuelve al mismo lote. La guía vuelve a «inventario por decidir» y se decide otra vez.
- Queda el historial en la tarjeta de la guía. No se permite si la guía ya está registrada en SAP.

## 3. OTIF, on time, in full y fill rate con las OV de SAP frente a sus guías

Parámetro `otif_fuente` = `SAP` (por defecto). Si ya se leyó el historial de SAP, el nivel de servicio se calcula con:

- **Universo**: OV de venta de SAP (abiertas y cerradas, sin anuladas ni órdenes de servicio) con fecha de entrega en el
  periodo.
- **Salida** de la OV = su primera guía de SAP.
- **On time**: la primera guía es hasta la fecha de entrega ÷ universo.
- **In full**: lo guiado cubre lo pedido en todos los productos ÷ universo.
- **OTIF**: lo guiado **hasta la fecha de entrega** cubre todo lo pedido ÷ universo.
- **Fill rate**: unidades guiadas (hasta lo pedido) ÷ unidades pedidas de las OV con guía; también por líneas.
- OTIF a la fecha y día a día: como en V31, sobre las OV que ya debían salir.

Se usa en la pantalla «Nivel de servicio», en el inicio, en el tablero de la empresa, en el informe de gestión comercial
(sin filtros de cliente, canal o vendedor; con filtros se sigue usando el módulo) y en los indicadores a la salida. El
cumplimiento por cliente dentro de la OV y la simulación siguen con el módulo. Con `otif_fuente` = `MODULO` se vuelve al
cálculo anterior.

## 4. Tarjetas de indicadores que se abren con un clic

- Las tarjetas que ya eran enlaces muestran «›» y se resaltan al pasar el mouse.
- Las demás (`div.kpi`) se abren: con `data-href` van a la pantalla del detalle (p. ej. producción de hoy → monitoreo;
  fill rate en el informe de distribución → nivel de servicio); con `data-ver` bajan a su sección; si no tienen
  ninguno, el sistema busca en la misma página la sección cuyo título comparte palabras con el indicador y la despliega.
  Si no encuentra nada, la tarjeta no se marca como clicable.

## 5. Producción del mes: SAP y módulo

- El historial de SAP (desde julio) ahora también trae las **liquidaciones de SAP**: entradas de mercancía basadas en
  una orden de fabricación (`PRODUCCION`). La versión del historial pasó a 3: la siguiente lectura trae todo una vez.
- El informe de producción y el inicio muestran: liquidado en SAP (kg, unidades, entradas, órdenes), lo procesado según
  los partes del módulo y lo de hoy en tiempo real.

## 6. Planeamiento por línea y alerta de capacidad

- «Planeamiento de producción» empieza con las **líneas**: cada una muestra % programado y % ejecutado de su capacidad;
  al abrirla se ven los productos programados en esa línea. Los requerimientos y el plan vs real por producto quedan
  plegados.
- Alerta nueva `CAPACIDAD_BAJA` (Jefatura de Operaciones y de Producción): una línea usó menos del 80 %
  (`capacidad_alerta_umbral`) de su capacidad en los últimos 7 días (`capacidad_alerta_dias`) o tiene programado menos
  del 80 % para los próximos 7. Una alerta por línea y semana; se revisa en las verificaciones diarias.

## 7. Stock sin rotación: vencimientos y varios almacenes

- Dos tarjetas y listas: lo que **vence en los próximos 3 meses** y **entre 3 y 6 meses** (por producto, con lotes y
  almacén), marcando si además no rota.
- Filtro de **varios almacenes** con casillas; lo elegido aparece abajo como círculos (chips) que se quitan con ×.

## 8. Vistas agrupadas por cliente y diseño

- **Picking**: un bloque por cliente (OV, por preparar, sin asignar, primera fecha); al abrirlo, sus OV agrupadas por
  fecha de entrega.
- **Órdenes de venta**: pestaña «Por cliente» con una tarjeta por cliente (OV, vencidas, próxima fecha); al entrar se
  ve la lista de sus OV.
- **Días no laborables**: las áreas se eligen en una cuadrícula de casillas legible (antes los textos se montaban con
  las casillas); «Todas las áreas» marca todas.

**Pruebas:** `tests/test_v42.py`.
- Suite completa: **645 pruebas, todas pasan**.
