# Ronda V24 (06-nov-2026): personal por área, compras nacionales, importaciones, costos y tablero de la empresa

Todo con **datos ficticios**. No se conectó nada a SAP ni a producción. El tipo de cambio se lee de la publicación
pública de SUNAT (solo lectura); en las pruebas no se sale a internet.

## 1. Lo pedido y dónde quedó

| Pedido | Implementación | Dónde |
|---|---|---|
| «Reportar avería» más entendible | El cuadro ahora pregunta «¿A quién va dirigido?» con dos tarjetas grandes: **Mantenimiento** (luz, agua, puertas, máquinas, montacargas…) y **Sistemas** (laptop, celular, impresora, tintas, red, accesos), cada una con ejemplos; luego «Cuéntenos qué pasa». | Botón «Reportar avería» (todas las pantallas) |
| Alta de personal distinta por área | Limpieza y Mantenimiento: solo el colaborador y su puesto (sin línea). Comercial: el vendedor con su **canal** (obligatorio). Logística: puesto **auxiliar de almacén** o **auxiliar de despacho** (o montacarguista). Producción: línea, sublínea y función (**maquinista**, operario, ayudante, supervisor de línea). Configurable en `alta_personal_por_area`. La Jefatura Comercial registra a sus vendedores (`personal.comercial`). | Asistencia y personal |
| Compras nacionales para OV, cliente o motivo | La solicitud lleva la OV **o** el cliente; si no, el motivo (stock de seguridad, reposición u otro que se especifica). Si se indican ambos, la OV debe ser de ese cliente. | Compras nacionales (consolidado) |
| Consolidado que valida OV ↔ cliente | Por producto: para cada cliente se juntan lo pedido por sus OV y lo pedido «para el cliente». Si la OV es del mismo cliente se toma lo mayor (1 t por la OV565 + 2 t para el mismo cliente = **2 t**, con la nota «la OV565 es de ese cliente»); si es de otro cliente se suma (**3 t**). Al final se suma el stock de seguridad / reposición. Lo ven Compras nacionales, el Gerente General Adjunto, Logística y Operaciones. | Ídem |
| Cotizaciones a mano o con archivo, varias por solicitud, histórico y alertas de precio | Compras nacionales o el Gerente General Adjunto registran tantos proveedores como quieran (origen o mercado, proveedor, fecha estimada de entrega, calidad, precio, moneda, UM, cantidad y archivo opcional). Todas quedan como histórico. Cada cotización se compara con el promedio de los **últimos 30 días**, el **último trimestre** y el **mismo mes del año anterior**; si se aparta más de `compras_alerta_variacion_pct` se alerta. «Elegir» pasa proveedor y precio a las solicitudes. | Ídem |
| Cuadro de importaciones como el de la empresa, bonito y con alertas | Columnas: código SAP (o POR CONFIRMAR), contrato, proveedor, ítem, país, contenedores, llegada, días libres, **fecha máxima de retiro (llegada + días libres)**, 1 SENASA, 2 BL, 3 retiro (real o tentativo) e información del almacén. Semáforo por fila; carga y descarga en Excel con esas columnas. | Seguimiento de importaciones |
| Gastos extra, contratos y penalidades | Gastos por tipo (sobreestadía, devolución tarde de contenedor, almacenaje, flete, SENASA, agente de aduanas, otro) con sustento; contrato adjunto con fecha pactada, penalidad por día y costo de sobreestadía. Se calcula el **riesgo de sobreestadía** (contenedores × días × costo) y la **penalidad a favor** si el proveedor llegó tarde. | Ídem |
| Alertas a Gerencia Adjunta, Coordinación y Asistencia de Importaciones | Retiro próximo (5, 2 y 0 días), sobreestadía, carga en puerto con SENASA/BL pendiente, cambio de fecha de llegada, penalidad a favor o en contra e inconvenientes reportados. Perfil nuevo **Asistente de Importaciones** (registra lo mismo que la Coordinación). | Ídem; bandeja de gerencia del GGA |
| Precios importado vs nacional | Por producto: precio del contrato + gastos extra prorrateados por kg, al tipo de cambio SUNAT, frente al promedio de cotizaciones nacionales de 90 días; indica qué conviene. | Ídem |
| Perfil de Costos y Presupuestos | Perfil nuevo que carga el costo por SKU (uno a uno o por Excel) y ve el análisis: costo registrado vs **costo de reposición** (cotización elegida o importación con gastos; producto terminado por su lista de materiales) vs **precio de venta realizado**, márgenes, impacto en S/ y la lectura «sube: actualizar costo / revisar precio» o «baja: compensa». Resume si las bajas compensan las subidas. Alerta mensual por SKU cuando reponer cuesta más que el costo. | Costos y reposición |
| Tipo de cambio SUNAT automático | Tarea diaria que lee el TC de SUNAT; si no hay conexión, avisa y se registra a mano. Las compras e importaciones en dólares se valorizan con el TC de venta del día. | Costos y reposición; tarea programada |
| Gráficos e informes de cómo va la empresa | **Cómo va la empresa**: «A qué prestarle atención» (ordenado por gravedad) y una tarjeta por área (venta vs meta, OTIF, cobranza, cumplimiento de la demanda, producción, compras, importaciones, costos) con semáforo y una frase; gráficos de venta y OTIF por semana y deuda por antigüedad; PDF. Lo ven Jefatura Comercial, Jefatura de Operaciones, Jefatura de Administración y Finanzas, Costos y Presupuestos y Gerencias. | Cómo va la empresa |
| Análisis de reposición como informe consolidado y fácil de leer | **Informe de reposición**: resumen en una frase, tabla por tipo y los productos agrupados en «Comprar ya», «Comprar esta semana», «Programar», «Cubierto» y «Faltan datos», cada uno con una frase («Comprar 1 200 kg antes del 10/11: el stock alcanza 4 días; el proveedor tarda 7…»). PDF y Excel. | Informe de reposición |

## 2. Usuarios nuevos de la demostración

- `costos.presupuestos` (Costos y Presupuestos).
- `asist.importaciones` (Asistente de Importaciones).

Contraseña de la demo: la de siempre. También están en «Ver todos los usuarios y contraseñas de la demostración».

## 3. Parámetros nuevos

| Parámetro | Valor inicial | Estado |
|---|---|---|
| `alta_personal_por_area` | Producción: línea, sublínea y función; Mantenimiento: solo puesto; Comercial: canal; Logística: auxiliar de almacén o despacho | Definido |
| `compras_alerta_variacion_pct` | 10 % | **Propuesto** |
| `import_alerta_retiro_dias` | 5, 2, 0 | **Propuesto** |
| `import_sobreestadia_usd_dia` | 0 (se usa el del contrato) | **Propuesto** |
| `costo_reposicion_tolerancia_pct` | 5 % | **Propuesto** |
| `tipo_cambio_url` | publicación de SUNAT | **Propuesto** |

## 4. Cómo revisar

1. `python -m app.cli reset-demo` y `python -m app.cli demo-dia` (ahora carga además los datos V24).
2. Recorrido sugerido:
   - **gerente.adjunto**: Compras nacionales: frijol canario, con una OV del mismo cliente que no se suma y stock de seguridad. Lenteja, con una OV de otro cliente que sí se suma. Cotizaciones con su comparación frente al histórico. Seguimiento de importaciones, Cómo va la empresa.
   - **asist.importaciones**: editar una fila, registrar un gasto, reportar un inconveniente, descargar el Excel.
   - **costos.presupuestos**: Costos y reposición, actualizar un costo y registrar el tipo de cambio.
   - **jefe.ventas**: Asistencia y personal: registrar un vendedor con su canal.
   - **jefe.logistica**: registrar a un auxiliar de despacho.
   - **jefe.produccion**: registrar a un maquinista con su línea.
   - Cualquier perfil: «Reportar avería».

## 5. Límites

- El costo de reposición del producto terminado usa los componentes con reposición conocida; los que no la tienen usan su costo registrado.
- La comparación importado vs nacional necesita el precio del contrato y los kg de la importación para prorratear los gastos.
- Si el servidor no tiene salida a internet, el tipo de cambio se registra a mano (la alerta lo recuerda cada día).
- El cuadro de importaciones que compartieron se usó solo como modelo: sus contratos y proveedores reales no se copiaron al sistema ni al repositorio.

## 6. Ajustes del 07-nov-2026

| Pedido | Implementación |
|---|---|
| Ruta manual: quién lleva la carga en lista desplegable, con «otro» | Si la lleva otro trabajador se elige de la lista (con su área, que se completa sola) o «Otro (escribir)». El chofer y el vehículo ya eran listas. |
| Hora de salida en lista o escrita | Lista de horas cada 30 min (05:00 a 20:30) que también acepta escribir; se normaliza (730, 7.30 o 7:30 → 07:30). |
| Transporte externo con su costo | Al elegir «Transporte tercero» se pide el costo (S/, obligatorio) y la empresa; se ve en el cuadro de despacho. |
| Ver el sistema como si llevara 15 días | `demo-dia` agrega **15 días hábiles de operación** (`app/demo_quincena.py`). Comercial: ~130 OV en esos días, con OTIF ~84 % (a tiempo, tarde, parciales, anuladas). Almacén: picking con lote, bultos y foto. Distribución: rutas cerradas con guías, receptor y hora de entrega, transporte externo con costo e incidencias. Chofer y Seguridad: **checklist vehicular completo de salida y retorno** con puntos marcados en el dibujo, validado. Calidad: registros diarios y certificados. Saneamiento, asistencia de todos, pagos confirmados, oportunidades y cotizaciones. |
| Modelo de Costos y Presupuestos (Excel «costo empresa») | En «Costos y reposición» se carga el Excel con bloques **SKU, DESCRIPCIÓN, COSTO EMPRESA** (uno o varios lado a lado): GR y MP por kg, PT y MQ por unidad; solo se versionan los que cambian e informa los códigos que no existen. |
| Centro de costos (opcional) en compras nacionales | Catálogo cargado desde el Excel de centros de costo (grupo → área → centro → subcentro). Se elige, sin ser obligatorio, en la solicitud de compra nacional, al generar la OC y en las **rendiciones de facturas y planillas de movilidad** (pantalla nueva «Rendiciones, movilidad y centros de costo», con resumen por centro). |
| «Activar» notificaciones no hacía nada | El resultado ahora se muestra en la misma barra (antes salía en ventanas emergentes que algunos navegadores bloquean). Se explica cada caso: sitio sin https, sistema abierto dentro de otra aplicación, permiso bloqueado o rechazado, servidor sin clave. **Para que funcione, el sistema debe abrirse con https** (el navegador no permite notificaciones sin conexión segura). |
| Revisar que cada botón funcione | Recorrido automático con navegador por el menú de 16 perfiles, abriendo cada ventana (botones «Nuevo…», «Reportar avería», etc.) y registrando errores de página o de JavaScript. Resultado en el informe de la ronda. |

Los Excel de costo empresa y de centro de costos que compartieron se usaron solo como modelo de formato: sus datos no se copiaron al repositorio. En la demostración hay centros de costo ficticios.
