# Ronda V33 (14-nov-2026): órdenes de servicio de SAP, filtros de órdenes vs guías, alertas por proceso, días no laborables y guía firmada

Pruebas con datos ficticios.
- **Migración:** sin migración nueva.
- **Escritura en SAP:** nada nuevo.

## 1. Por qué no aparecía la orden 1636505

Las capturas lo muestran:
- La **1636315** es una **orden de venta de artículos**: «Artículo/Servicio = Artículo», línea MP-010 con cantidad.
- La **1636505** es una **orden de servicio**: «Artículo/Servicio = **Servicio**». Su línea es un servicio («SERVICIO DE ZARANDEO…») con su cuenta contable, **sin código de artículo ni cantidad**.

El historial guardaba solo las líneas con código de artículo. Por eso las órdenes de servicio, que no tienen ninguno, **se descartaban** y nunca aparecían.

**Corrección:**
- Las órdenes de **servicio** de SAP (tipo de documento «Servicio») se guardan con la clase **SERVICIO**. Cada línea queda como «SERVICIO» con su descripción.
- Se dan por atendidas cuando la línea o la orden se cierra en SAP (las de servicio no tienen guía).
- Salen en la pestaña **Órdenes de servicio** y en «Todas».
- **Recarga automática:** la siguiente lectura del vigilante **vuelve a traer todo el historial desde julio una vez**, para que entren las órdenes de servicio que faltaban. Luego sigue trayendo solo lo que cambia.
- Las órdenes de servicio **no entran a la carga de OV abiertas** del módulo: no se preparan ni se despachan desde el almacén.
- Para clasificarlas no hace falta configurar la serie: SAP ya marca el documento como de servicio. Las dos capturas tienen la misma serie.

## 2. Filtros de «Órdenes vs guías»

**Qué fallaba:**
- Había **dos filtros de mes**: el de la pantalla y el del buscador.
- El del buscador filtraba por la fecha comprometida y no por la de emisión, por eso parecía que no funcionaba.

**Cómo quedó:**
- **Un solo filtro:** «Buscar en la lista» con Desde / Hasta / Mes por **fecha de emisión** de la orden y el orden (más recientes o más antiguas). Se filtra en la consulta, así que los indicadores también se recalculan.
- **Abiertas / Cerradas / Abiertas y cerradas** son pestañas, con su cantidad.
- La columna «Emisión / compromiso» **ya no tiene flecha**, porque son dos fechas; se ordena con «Orden por fecha».
- Las pestañas, los indicadores y el Excel conservan los filtros.

## 3. Alertas por proceso

Las tarjetas de Alertas y tareas ahora agrupan **por proceso**:
- Compras e importaciones;
- Stock y movimientos;
- Pedidos (OV);
- Preparación y despacho;
- Producción;
- Calidad y fumigación;
- Finanzas y cobranza;
- Comercial;
- Mantenimiento y limpieza;
- SAP y sistemas;
- Gerencia y planificación.

Cada tarjeta va en **rojo** si tiene urgentes y en **amarillo** si tiene tareas. Al tocarla se despliega la lista de ese proceso, con «← Todos los procesos» para volver.

## 4. Días no laborables de varias áreas

**Áreas:**
- Nuevas: **Comercial, Calidad, Logística, Compras y Administración y Finanzas**, además de Producción, Almacén, Distribución, Mantenimiento y Limpieza.
- Las registran sus jefaturas; Jefatura de Operaciones, Gerencias y Sistemas registran cualquiera.

**Registro:** se marcan **una, varias o «Todas las áreas»** a la vez, con fecha y motivo.

**Aviso:** llega a **todas las áreas** (`dias_no_laborables_avisar_roles`), no solo a las afectadas. Si son todas, dice «La empresa no labora el…».

**Bloqueo de OV:**
- Si no labora **Almacén o Distribución** (`dias_no_laborables_bloquean_ov`), **no se puede registrar una OV** con despacho ese día, ni mover la fecha comprometida de una OV a ese día.
- El mensaje dice qué área no labora y por qué.
- Las OV que llegan de SAP no se bloquean, porque ya existen en SAP.

## 5. Guía firmada del conductor

En la conformidad de entrega el conductor adjunta **solo la guía de remisión firmada** de esa parada:
- Debe ser **foto o PDF**; se rechaza cualquier otro archivo.
- Debe escribir el **número de la guía que adjunta**. Si la parada ya tiene su número de guía, **debe coincidir**: por ejemplo, T001-12345 es igual a T001-00012345.
- Si es un **PDF con texto**, el número debe aparecer en el documento. Si no aparece, se rechaza («el PDF adjunto no es la guía…»).
- La pantalla muestra el número de guía esperado y la indicación: «guía de esta entrega, firmada y sellada por el cliente».

## 6. Compras

Quedó como lo indican:
- Compras **no compra PT**, porque se fabrica para vender.
- Compra **granel** y, a veces, **MP**; también MQ, como lo habían indicado antes.
- La reposición automática de PT, MQ y MP sigue siendo una pre-solicitud de **producción**.

## 7. Parámetros

| Parámetro | Valor | Estado |
|---|---|---|
| `dias_no_laborables_areas_por_rol` | se agregan Comercial, Calidad, Logística, Compras y Administración y Finanzas | Cambio V33 |
| `dias_no_laborables_bloquean_ov` | Almacén, Distribución | PROPUESTO |
| `dias_no_laborables_avisar_roles` | jefaturas y coordinaciones de todas las áreas y los ejecutivos comerciales | PROPUESTO |

## 8. Verificación

- `tests/test_v33.py` (5 pruebas):
  - órdenes de servicio en el historial, recarga completa y fuera de la carga de OV;
  - filtros de órdenes vs guías;
  - alertas por proceso;
  - días no laborables de varias áreas con aviso y bloqueo de OV;
  - guía firmada: número que no corresponde, tipo de archivo y PDF de otra guía.
- Ajustes a pruebas anteriores: `test_v31` (filtro por mes del buscador) y `test_v32` (alertas por proceso).
- Suite completa: **629 pruebas, todas pasan**.
