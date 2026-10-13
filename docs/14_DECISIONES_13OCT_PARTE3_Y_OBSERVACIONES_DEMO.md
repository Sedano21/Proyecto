# Versión 0.6 – Respuestas R1–R6 del 13-oct y observaciones al demo v0.5

Este documento registra lo aplicado a partir de (1) las respuestas R1–R6 con la foto del formato de OV y el certificado
N°CP2026-CA0764, y (2) las observaciones al demo v0.5. Todo se probó con datos ficticios (140 pruebas automatizadas,
recorrido en navegador en escritorio y en celular). **El sistema sigue sin estar listo para producción**: ver §4.

## 1. Respuestas R1–R6

| # | Respuesta | Implementación | Estado |
|---|---|---|---|
| R1 | La vida útil de la lista de clientes es la **vida útil restante mínima al despacho** | `aplicar_vida_util_cliente` = sí (DEFINIDO). Se mide en **meses calendario** y admite excepciones por familia: «12 MESES / 6 MESES HARINAS» → harinas 6 meses. La reserva excluye lotes que no la cumplen y explica el motivo. | ✅ (ver riesgo §4-1) |
| R2 | El RUC se agregará a la lista de penalidades | Columna **RUC** opcional en la carga: si la fila trae RUC se vincula por RUC (valida 11 dígitos); si no, por nombre. Un nombre igual con otro RUC no se vincula. | ✅ |
| R3 | Pesos de penalidad validados | `peso_penalidad` y `orden_prioridad` pasan a DEFINIDO. | ✅ |
| R4 | El costo sirve para (1) que ninguna venta quede por debajo del costo y (2) comparar automáticamente con el mercado y su tendencia | (1) La columna **COSTO EMPRESA** de las listas de precios ahora se conserva (versionada, visibilidad restringida) y hay una carga «Costos de la empresa» con encabezados flexibles. Cada línea de OV se compara con el costo en su unidad de venta: si está por debajo, la OV **queda detenida** (la confirma el Coordinador o Jefe Comercial) y se alerta `OV_PRECIO_BAJO_COSTO`; el texto visible en la OV no muestra el costo. (2) Pantalla **Costos vs mercado**: cruce automático del costo por kg con el último precio de mercado del producto base, tendencia (último vs promedio de 90 días), margen y recomendaciones; se recalcula al cargar datos y en la tarea diaria (alerta `COSTO_SOBRE_MERCADO`). | ✅ (falta el Excel de costos real) |
| R5 | Precios de mercado de la investigación en internet | Modelo y carga «Precios de mercado» (producto, variedad, S/ por kg, tipo mayorista/minorista/importación, mercado, fecha, fuente, URL) y registro manual. Ver §1.1: **no se precargan cifras** porque no pude abrir los reportes oficiales desde este entorno para verificarlas. | ⚠️ parcial |
| R6 | La OV trae precio unitario y «Tipo de Venta»; logos de Corporación Productiva, Cantaclaro y Cosecha Andina en OV, guía y certificado; diversos tipos de certificado | **OV imprimible** como la foto (logos, razón social, cuentas bancarias, instrucciones de pago, asistencia, monto en letras, IGV solo en líneas con TaxCode IGV); nuevas columnas opcionales de la exportación: forma de pago, moneda, descuento, TaxCode. **Guía y pre-guía** con membrete. **Certificados por tipo** con el formato del PDF (membrete, marca de agua, pie, bloque de firma): **PT** (modelo PT3756), **MP** (MP276) y **CA** (CA0764: características organolépticas, humedad máx. 21 %, conclusión Codex). Tipo automático por tipo de artículo o marca (Cosecha Andina → CA, propuesto) y Calidad puede regenerar el borrador con otro tipo. | ✅ |

### 1.1 Precios de mercado encontrados (pendientes de verificación)

La fuente pública más útil es el **«Reporte de ingreso y precios en el Mercado Mayorista de Productores» (Santa Anita)**
que MIDAGRI publica en gob.pe (precios promedio diarios en S/ por kg, con IGV, incluye frijol canario, lenteja y
garbanzo). Desde este entorno el acceso a gob.pe está bloqueado, así que solo obtuve cifras a través de resúmenes del
buscador, que **no coinciden exactamente entre sí**; por eso no se cargaron al sistema:

| Producto | Referencia encontrada | Fecha del dato | Fuente |
|---|---|---|---|
| Frijol canario | ≈ S/ 5.85 por kg | 20-feb-2026 | [Reporte MIDAGRI 20-02-2026](https://cdn.www.gob.pe/uploads/document/file/9484208/7685508-reporte-de-ingreso-y-precios-en-el-mercado-mayorista-de-productores-20-02-2026.pdf) |
| Lenteja | ≈ S/ 5.20 por kg (semana anterior ≈ 5.74) | 20-feb-2026 | mismo reporte |
| Frijol canario / garbanzo / lenteja | ≈ S/ 7.35–7.40 / 6.03–6.05 / 6.08–6.10 por kg | 1-abr-2026 | [Reporte MIDAGRI 01-04-2026](https://cdn.www.gob.pe/uploads/document/file/9731992/7958943-reporte-de-ingreso-y-precios-en-el-mercado-mayorista-de-productores-01-04-2026.pdf) |

No encontré reportes posteriores a abril de 2026 ni una descarga en formato de datos (Excel/API) que permita automatizar
la lectura sin intervención; los reportes son PDF con URL variable. MIDAGRI menciona además el aplicativo SISAP y
Agrochatea para precios en tiempo real. Propuesta: que Comercial cargue cada semana la tabla del reporte (plantilla de
la carga «Precios de mercado») hasta definir una fuente automatizable (§4-3). El demo usa precios **ficticios**
marcados como tales.

## 2. Observaciones al demo v0.5

| Área | Observación | Implementación |
|---|---|---|
| General | Informes con gráficos, tendencias y recomendaciones | Menú **Informes**: Comercial, Reempaque, Producción y Distribución, con periodo, indicadores, gráficos (SVG propios, con tabla de datos), tendencia y recomendaciones automáticas por reglas con umbrales configurables. |
| Comercial | Hora de cita desplegable | Lista de horas en formato 24 h (cada 30 min); el sistema rechaza horas en otro formato. |
| Comercial | Lugar de entrega del cliente u «otro» | Selector con los lugares de la ficha del cliente, la dirección fiscal u **Otro** (nombre, dirección, distrito y provincia obligatorios; opción de guardarlo en la ficha). Dirección, distrito y provincia se usan para la ruta. |
| Comercial | Ficha de cliente | Datos, canal de precios, contacto, teléfono, correo, horario, lugares de entrega, condiciones y penalidades, OV, productos más comprados, entregas incompletas e incidencias. Carga del maestro de clientes exportado de SAP (crea/actualiza clientes y lugares de entrega). |
| Comercial | Venta por kilo o por saco | Cada línea elige la unidad: por saco se convierte a kg con los kg por saco de la lista granel (precio y cantidad se guardan por kg; la OV impresa muestra sacos y precio por saco). Precio mínimo y costo se validan por kg y por saco. |
| Comercial | Panel de reportes | Ventas por vendedor (S/ y kg), semanales, productos más vendidos, presentaciones preferidas, comportamiento de compra por cliente (frecuencia, días sin comprar, alerta de riesgo), margen promedio y por producto (solo con permiso de costos), entregas incompletas (unidades y S/), pedidos pendientes y OV modificadas con % de desviación en cantidad y en soles. |
| Comercial | Modificar OV solo Ejecutivo, Coordinador y Jefe Comercial | `ov.modificar` es exclusivo de esos tres roles (ya no lo heredan Gerencia General ni Sistemas) y el panel solo se muestra a ellos. |
| Almacén | Artículo en lista desplegable que también permita escribir | Combo con búsqueda en Stock, OV, plan y partes (código, nombre y presentación). |
| Almacén | Cargas solo del área | Cada área ve y sube sus cargas (Comercial, Almacén, Producción, Configuración). |
| Almacén | Traslados: fecha y hora de llegada | Se registra al autorizar (o después); alerta `TRASLADO_LLEGADA` a Calidad (revisión) y Almacén (almacenamiento) y se repite el día de llegada. |
| Almacén | Reporte de reempaque | Solicitudes por semana, tasa de aprobación, desaprobadas, desestimadas, motivos, tiempos de respuesta de Almacén, Calidad y Comercial, gráfico y cuadro. |
| Producción | Código + nomenclatura + presentación; verificar la lista de materiales | Se muestran juntos; en la solicitud Producción marca **Lista correcta** u **Observar lista** (alerta `BOM_OBSERVADA`). |
| Producción | Planeamiento diario, semanal y mensual vs liquidación | Pantalla **Planeamiento**: plan por día/semana/mes, contraste con lo liquidado y tasa de cumplimiento. |
| Producción | Merma = desmedro de la lista de materiales vs liquidación | Los componentes «X - DESMEDRO» (ME-…) son la merma proyectada y ya no se tratan como material a consumir. La merma ejecutada sale de los partes o del desmedro liquidado en el mismo documento. Si el valor de la lista es simbólico (0.001, como en el archivo real), se usa la merma configurada y se indica. |
| Producción | Parte en estado Programado y reporte de producción | Estado **PROGRAMADO** (lo que se producirá) que luego se completa; informe de producción por día/periodo con gráficos, rendimiento y desmedro por línea, cumplimiento del plan y merma proyectada vs ejecutada. |
| Calidad | Formatos en lista desplegable y precertificado | Selector de formato (+ lote) y generación del precertificado con el tipo que requiere el producto. Cada registro se imprime con el cuadro de encabezado del formato original (código, versión y fecha tomados de los documentos) y el pie. |
| Calidad | Alertas de fumigación 7, 3 y 0 días | Plan de fumigación (fecha programada o fin del tiempo máximo de almacenamiento) y alertas `FUMIGACION_PROXIMA`. |
| Calidad | Diversos tipos de certificado | Ver R6. |
| Abastecimiento | Pre-solicitud al contrastar stock | Botón «Contrastar stock ahora» y lista de pre-solicitudes automáticas en Compras. |
| Abastecimiento | Plazos por familia y costo máximo | Los plazos (bobinas 25–30, con campaña de canastería nov–dic; GR/MP 5–7; harinas 7–10; film 2–5; sacos 1–2 / 5–7; ribbons y etiquetas 2–5) se muestran en reposición. **Costo máximo de compra** por artículo en Configuración → Productos; una cotización mayor alerta `COMPRA_SOBRE_COSTO_MAXIMO`. |
| Abastecimiento | Importaciones: contenedor, almacén, costos | N° y tipo de contenedor, almacén donde se almacenará y costos asociados (USD con tipo de cambio o PEN) con total en soles y costo por unidad. |
| Distribución | Chofer, vehículo, mapa, tiempo, tráfico, clientes | En la ruta: unidad, chofer y licencia, clientes en orden con su cita, enlace a Google Maps con todas las paradas, tiempo estimado; con `GOOGLE_MAPS_API_KEY`: mapa embebido, tiempo con tráfico y alerta `RUTA_TRAFICO` (exceso de tráfico o cita que ya no se alcanza). |
| Distribución | Propio vs externo; el externo lo valida el coordinador | La ruta con transporte externo no se confirma sin la validación del Coordinador de Distribución (alerta `RUTA_EXTERNO_VALIDAR`). Informe de distribución: rutas propio vs externo por semana, carga y pedidos, externos sin validar, incidencias por tipo/subtipo. |
| Distribución | Incidencias con tipo y subtipo, sin «(TO-BE)» | Tipos **Calidad** (infestación interna, infestación externa, producto fuera de características, rechazo por calidad, particularidad en la descarga), **Logística** (llegada tarde = rechazo por cita fuera de hora, entrega parcial, producto roto, retraso, vehículo esperando, cambio de ruta, falta de conductor, incidencia en la carga) y **Cliente / Comercial**. Las de Calidad alertan también a Calidad. |
| Administración | Matriz de permisos más amigable | **Permisos por rol**: lista de roles por área y permisos agrupados por módulo con interruptores, búsqueda y origen (D/P); y matriz compacta filtrable por área. |
| General | Adaptable a celular, tablet y laptop | Menú lateral desplegable (☰) en pantallas menores a 1024 px, formularios y grillas en una columna en celular, tablas con desplazamiento horizontal, controles de 40 px. |

## 3. Decisiones técnicas tomadas (justificadas)

- La **firma** del certificado no se guarda en el repositorio: la carga Sistemas en el servidor y solo se imprime en
  certificados aprobados (evita que un borrador salga firmado y que la firma circule en copias del código).
- Las **cuentas bancarias, teléfonos y textos** de la OV son parámetros editables (Configuración), tomados de la foto.
- El **IGV** se calcula solo para líneas con TaxCode «IGV»; el formato real muestra «EXO» en menestras.
- Los **gráficos** se generan en el servidor (SVG) sin librerías externas: la instalación es local y no depende de internet.
- La **migración** 0002/0003 agrega las tablas y columnas nuevas (Alembic).

## 4. Preguntas para continuar (necesito su respuesta)

1. **Vida útil 12 meses (riesgo alto).** Los certificados reales muestran productos con 12 meses de vida total
   (p. ej. FP 29-09-26 / FV 29-09-27). Si «12 MESES» es vida **restante** al despacho, casi ningún lote calificaría para
   esos clientes (97 de las 103 filas de la lista indican 12 meses). ¿Es restante o es la vida útil total del producto? ¿O hay un mínimo
   restante distinto (p. ej. 2/3 de la vida)?
2. **Excel de costos:** ¿el costo viene por unidad de presentación o por kg? ¿Quién debe ver costos? (propuesto:
   Gerencia General, Gerente Comercial, Jefe Comercial y Coordinador Comercial).
3. **Fuente de precios de mercado:** ¿aprueban que Comercial cargue semanalmente el reporte de MIDAGRI (Santa Anita) y,
   si lo desean automático, que se evalúe un servicio con datos estructurados (con su costo)? ¿Qué mercado/tipo de
   precio quieren como referencia principal (mayorista Lima, importación CIF)?
4. **Datos impresos de la OV:** confirme que las cuentas bancarias, teléfonos de asistencia y correos del pie del
   certificado (incluido un correo personal) están vigentes y se pueden imprimir.
5. **Serie CA:** ¿el certificado CA corresponde a toda la marca Cosecha Andina o a productos específicos (fécula, harinas)?
6. **Costo máximo de compra:** ¿solo alerta o debe bloquear la orden de compra hasta una aprobación? ¿Quién aprueba?
7. **Google Maps:** ¿autorizan contratar la clave (tiene costo por consulta) para tráfico y mapa embebido?
8. **TaxCode/IGV:** ¿la nueva exportación de OV trae el código de impuesto por línea?
9. **Merma proyectada:** en la lista de materiales real el desmedro figura con 0.001 (simbólico). ¿Nos pasan el %
   de merma esperado por producto o familia?
10. **Asistente de Ventas:** con «modificar OV solo Ejecutivo, Coordinador y Jefe Comercial», el asistente ya no ve el
    formulario de solicitud de modificación (sigue pudiendo cargar el consolidado de cambios). ¿Correcto?
11. **Fumigación:** ¿la fecha se programa manualmente o existe una frecuencia por producto (días desde el ingreso)?
12. **Tiempo de respuesta de Comercial (reempaque):** se mide desde que la OV queda con faltante hasta la primera
    decisión comercial registrada. ¿Es la definición correcta?

## 5. Decisiones del 14-oct

| Decisión | Implementación | Estado |
|---|---|---|
| **Plazo máximo de reserva: 7 días** (espacio físico del almacén) | Parámetro `plazo_max_reserva_dias` = 7. Una OV cuya fecha comprometida está a más de 7 días **no aparta stock**: queda «DIFERIDA», con la cobertura proyectada calculada con el stock libre (y alerta de faltante proyectado para anticipar compras o producción). La tarea diaria la reserva automáticamente al entrar en el plazo, por orden de prioridad. Si se posterga la fecha más allá del plazo, la reserva se libera. Las reservas con más de 7 días alertan `RESERVA_VENCIDA` (no se liberan solas porque el pedido puede estar en preparación). | ✅ |
| **Compra de materia prima: siempre con Gerencia de Operaciones** | Parámetro `tipos_compra_requieren_go` = [MP]: toda compra de artículos MP requiere la aprobación de GO antes de generar la orden de compra, sin importar el volumen (las demás siguen la regla de mayor volumen). | ✅ (ver pregunta 13) |
| **Comparar reportes de importación (internet y Estado) y cotizaciones de Importaciones y Compras nacionales con los precios** | En *Costos vs mercado*, sección **Impacto de cotizaciones**: cada cotización nacional (precio cotizado) y de importación (valor de la mercadería + costos asociados = costo puesto en almacén) se compara con el costo vigente, el precio mayorista, la referencia de importación (reportes cargados como precio de mercado tipo IMPORTACION) y el precio mínimo de lista; muestra la variación, el margen que quedaría sobre el precio mínimo, el impacto estimado en soles sobre la demanda de 90 días y si conviene importar o comprar en el país. Alerta `COTIZACION_IMPACTO` a Comercial, Compras, Importaciones y GO cuando el margen cae bajo el umbral o la cotización supera la referencia. | ✅ |

13. **Granel (GR):** ¿la regla «materia prima siempre con Gerencia de Operaciones» incluye también los artículos granel (GR) o solo MP? Hoy aplica solo a MP; se cambia en Configuración.
14. **Reservas vencidas:** ¿se deben liberar automáticamente al pasar los 7 días (si el pedido aún no está en preparación) o basta con la alerta?
