# Ronda V31 (13-nov-2026): buscador, historial de SAP desde julio, actualizar con SAP, rotación, compras, reposición y OTIF diario

Pruebas con datos ficticios.
- **Lectura de SAP:** órdenes abiertas y cerradas, guías y consumos de producción desde julio.
- **Escritura en SAP:** nada nuevo.
- **Migración nueva:** **0043**.

## 1. Lo pedido y dónde quedó

| Pedido | Implementación |
|---|---|
| Buscar al pulsar Enter, con una lupa al costado | Ver el punto 1.1. |
| Un buscador en las listas, no solo filtros; el paginador fuera del scroll | Ver el punto 1.1. |
| Tareas y alertas filtradas por fecha | Ver el punto 1.1. |
| El granel sale a venta o se usa para producir; la rotación también debe considerar la producción | Ver el punto 2. |
| Datos de SAP: OV abiertas **y cerradas**, desde julio, con filtro por mes | Ver el punto 1.2. |
| Que todo lo que se hace en SAP se refleje, con un botón de actualizar que traiga solo lo que falta | Ver el punto 1.3. |
| Compras: se adquiere todo menos PT, MQ y MP (los produce la empresa) | Ver el punto 1.4. |
| Pre-solicitudes cuando el stock se está acabando, sin esperar el quiebre, con OV pendientes y stock de seguridad | Ver el punto 1.4. |
| Explicar el cálculo de la tarjeta de stock sin rotación | Ver el punto 2. |
| OTIF calculado día a día | Ver el punto 1.5. |

### 1.1 Buscador, paginador y filtro por fecha

**Buscador:**
- Ya **no busca mientras se escribe**: busca al pulsar **Enter** o la **lupa** que aparece al costado de cada buscador.
- Las listas desplegables y las fechas del filtro siguen aplicándose al elegirlas.
- Las listas que solo tenían filtros tienen ahora un **buscador de texto** («Buscar en la lista»). Algunas: órdenes de venta, compras, liquidaciones, certificados, cargas, traslados, importaciones, reempaques, oportunidades, cotizaciones, conteos, guías SUNAT, tickets, devoluciones y ausencias.
- Busca en todos los datos del registro y en los de su cliente, OV, producto, lote y usuario. En las OV, también por los productos de sus líneas.
- Todas las palabras deben aparecer, sin importar mayúsculas ni tildes.
- Conserva los demás filtros.

**Paginador:** quedó **debajo de la lista, fuera del área con scroll**.

**Alertas y tareas:**
- Filtro **Desde / Hasta** por fecha de creación, más un buscador.
- Con «Desde» también aparecen las cerradas de ese rango.

### 1.2 Historial de SAP desde julio (abiertas y cerradas)

**Qué se lee de SAP**, desde `sap_historial_desde` = **01/07/2026**:
- **Órdenes** de venta y de servicio, **abiertas, cerradas y anuladas**, con lo entregado por línea.
- **Guías** (entregas), con su OV.
- **Consumos de producción:** emisiones a órdenes de fabricación.

**Cómo se lee:**
- La primera lectura trae todo desde julio.
- Las siguientes traen **solo lo creado o modificado en SAP** desde la última, con un día de margen.
- Se actualiza sola con cada sincronización (`sap_historial_automatico`), con el botón **«Traer historial desde julio» / «Actualizar historial»** de la pantalla, o con «Actualizar con SAP».

**Órdenes de venta y servicio vs guías:**
- Con el historial cargado, filtro **Mes de la orden** (fecha de emisión) y **Situación en SAP**: Abiertas, Cerradas, o Abiertas y cerradas.
- Cada orden muestra si está abierta o cerrada en SAP.
- Avisos:
  - abierta pero ya entregada completa: cerrarla en SAP;
  - **cerrada en SAP con saldo sin entregar**;
  - nota de crédito;
  - guiado que no cuadra.
- Sin historial, la pantalla sigue como antes (OV abiertas de la última carga).

La **demanda proyectada** también usa este historial (órdenes abiertas y cerradas desde julio, más las OV que solo están en el módulo).

### 1.3 «Actualizar con SAP»

**Dónde:** botón en la barra superior, al lado de «Stock SAP fecha y hora».
- Lo ve quien trabaja con OV, stock, distribución o producción.
- Mientras corre muestra «Actualizando con SAP…».

**Qué trae, solo lo que cambió:**
- facturas de reserva sin entrega;
- los datos de `sap_sync_tipos` (OV, clientes, artículos, guías…). Solo crea una carga si SAP cambió desde la anterior;
- el historial de órdenes y guías;
- las facturas y notas de crédito.

**Para qué:** conviene usarlo antes de registrar una OV, subir guías, crear usuarios, etc.

**Importante:** durante la marcha blanca las cargas de OV, clientes y artículos quedan **para revisar y confirmar**. Para que se apliquen solas, agregue esos tipos a `sap_autoconfirmar`. Es una decisión de ustedes: con la revisión no se aplica nada sin verlo.

La sincronización automática (`SAP_SYNC_MIN`) ya detecta OV nuevas, editadas y cerradas, y guías. Con esta ronda también trae el historial y las facturas de reserva.

### 1.4 Compras y reposición anticipada

**Compras:**
- **No se compra PT, MQ ni MP**: los fabrica la empresa (`prefijos_producidos`).
- Una solicitud de compra de esos artículos se rechaza con el mensaje de generar una solicitud de producción.
- En las opciones ante un faltante de OV, la compra solo se ofrece para lo que no se fabrica.
- La compra de los materiales que faltan para producir no incluye la MP.

**Reposición anticipada (antes del quiebre):** cada día se revisan PT, MQ, MP y GR con stock o con OV pendientes, más los artículos con categoría de reposición o stock mínimo.

**Fórmula:**

```
necesidad = OV pendientes sin reservar + consumo durante el plazo + stock mínimo + stock de seguridad
            + lo que se necesita para producir − stock libre − lo que ya está en camino
```

Si la necesidad es mayor que 0:
- **PT y MQ**, luego **MP** (los fabrica la empresa): **pre-solicitud de producción** (borrador para el Jefe de Producción, alerta `PRODUCCION_REPOSICION`). Su lista de materiales se suma a la necesidad de sus componentes: el PT pide MP, granel e insumos; la MP pide granel.
- **Granel, insumos y demás:** **pre-solicitud de compra** (borrador para Almacén), con lo anterior más lo que se necesita para producir.

**Datos que usa:**
- El **consumo** sale del historial de ventas cargado. Si no lo hay, de las **guías y consumos de producción de SAP** del periodo.
- El **stock de seguridad** se activó (`usar_stock_seguridad` = sí) con el **30 % del consumo mensual** de su Excel actual (`factor_stock_seguridad`).

### 1.5 OTIF día a día

**Nuevo indicador «OTIF a la fecha»:** se calcula cada día solo sobre las OV que ya debían salir (fecha comprometida pasada) o que ya salieron. Las que aún están en plazo **no bajan** el indicador. También muestra on time e in full a la fecha.

**Tabla «OTIF día a día»:** por cada día, las OV comprometidas, su OTIF, on time e in full, y el **OTIF acumulado**.

**Dónde:** en Nivel de servicio y en el Inicio («OTIF a la fecha» y «OTIF del mes»). Se puede filtrar por canal.

**OTIF del mes:** se mantiene con su definición de siempre: base = todas las OV del mes.

## 2. Tarjeta de stock sin rotación: cómo se calculaba y qué se corrigió

### 2.1 Cómo se calculaba antes (lo que muestra su captura)

1. **Universo:** productos con stock en algún lote.
2. **«Sin salida N días»:**
   - Se buscaba la **última salida** solo en el **historial de ventas cargado** (hoja «Qy» de rotación de inventario), que en el servidor **no está cargado**. Por eso todas decían **«Sin salidas registradas»**.
   - Sin ninguna salida, los días se contaban **desde la fecha de admisión del lote más antiguo** en SAP. «1505 días» = hoy − admisión del lote más antiguo del GR-096. Las semanas y los meses son esos días ÷ 7 y ÷ 30,4.
3. **Stock:** la suma de los lotes, **55 374.97** en la unidad de SAP.
4. **«0 kg»:** stock × peso por unidad del artículo. El GR-096 no tiene peso por unidad en el maestro y su unidad no figura como kilogramo, así que el peso salía 0. **Error.**
5. **«Vence 30/09/2023 (−1140 d)»:**
   - Era el vencimiento más próximo de sus lotes, **aunque ya estuviera vencido**: −1140 = 30/09/2023 − hoy.
   - La recomendación «Vence en −1140 días: liquidar…» es la regla «vence en 60 días o menos» aplicada a un lote ya vencido. **Error.**
6. **«A precio mínimo — / Al máximo —»:** stock en kg × precio mínimo y máximo por kg de las listas de precios vigentes. Sin listas cargadas, o con 0 kg, no hay valor.
7. **Orden (#4, #5…):** ranking por más días sin salida (frente «tiempo») o por más valor o kg inmovilizado (frente «cantidad»).

### 2.2 Qué se corrigió

**Salidas:**
- Ahora cuenta como salida tanto la **venta** como el **uso en producción**:
  - venta: guías de SAP desde julio, despachos del módulo e historial cargado;
  - producción: emisiones de SAP a órdenes de fabricación y consumos cargados.
- El granel y la MP que se usan para producir **ya no aparecen como sin rotación**.
- La tarjeta muestra **«Última venta»** y **«Último uso en producción»** por separado.
- Si nunca tuvo salida, dice **«Sin salida (desde su ingreso)»**, para que se entienda de dónde salen los días.

**Peso:** el granel y la MP se miden en kg aunque el maestro no tenga el peso por unidad. Si un artículo no tiene peso, dice **«peso por unidad no definido»** en lugar de «0 kg».

**Vencidos:**
- Los lotes vencidos ya no se muestran como «vence en −N días».
- La tarjeta muestra **«Vencido: cantidad (desde fecha)»** y la recomendación cambia:
  - **todo vencido:** «no se puede vender como vigente: que Calidad lo evalúe (reproceso, uso en producción, venta como subproducto o baja) y confirmar en SAP si el stock y la fecha son correctos»;
  - **parte vencida:** separarla para que Calidad la evalúe; lo vigente sigue con su fecha.

**A revisar con ustedes:** los productos de la captura tienen lotes con vencimiento en 2023-2024 y stock en SAP. Puede ser stock real vencido o lotes antiguos que quedaron en SAP; conviene revisarlo con Almacén y Calidad.

## 3. Parámetros y alertas

| Parámetro | Valor | Estado |
|---|---|---|
| `sap_historial_desde` | 2026-07-01 | DEFINIDO (pedido de la empresa) |
| `sap_historial_automatico` | `true` | DEFINIDO |
| `prefijos_producidos` | PT, MQ, MP | DEFINIDO (pedido de la empresa) |
| `usar_stock_seguridad` | `true` (antes `false`) | Cambio V31, pedido de la empresa |

**Alerta:** `PRODUCCION_REPOSICION` (Jefatura de Producción, Asistentes de Producción y Jefatura de Operaciones).

## 4. Verificación

- `tests/test_v31.py` (7 pruebas):
  - buscador y paginador;
  - alertas por fecha;
  - historial de SAP: completo e incremental, abiertas y cerradas, por mes y pantalla;
  - «Actualizar con SAP»;
  - rotación con producción, vencidos y kg;
  - compras sin PT, MQ ni MP y reposición anticipada;
  - OTIF día a día.
- Migración 0043 aplicada sobre una base nueva: la base coincide con el código.
