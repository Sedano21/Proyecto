# Ronda V25 (08-nov-2026): Calidad e importaciones, inicio y empresa, chat, notificaciones y Distribución

Todo con **datos ficticios**. No se conectó nada a SAP ni a producción. Migración nueva: **0038**.

## 1. Lo pedido y dónde quedó

| Pedido | Implementación | Dónde |
|---|---|---|
| Calidad: informe de recepción de la importación con dos botones | En cada fila: **Subir PDF** (solo PDF; lo registra Calidad) o **Generar informe**. «Generar» abre el formato **REG-CAL-005 «Informe de recepción de materia prima – productos importados»**, ya prellenado con la referencia (contrato y código SAP), el proveedor, la procedencia, la fecha de ingreso y los documentos subidos. Al guardar queda enlazado a la importación. En los dos casos se avisa a Importaciones y al Gerente General Adjunto (`IMPORT_INFORME_CALIDAD`). Columna nueva «Informe de Calidad». | Seguimiento de importaciones |
| Importaciones sube documentos | Tipos: certificado de origen, fitosanitario, packing list, calidad, fumigación y «otros» (con nombre). Se pueden subir varios por tipo. La columna «Documentos» muestra los enlaces y «Faltan N» o «Completo». «Faltan» es solo un indicador: no bloquea nada. | Ídem (editar → Documentos) |
| Reempaque con la descripción del producto | Código + descripción del producto de origen y del de destino. | Reempaques, detalle, bandeja de Calidad, inicio |
| Fumigación con varios productos, lotes y cantidades | El formato de fumigación tiene la tabla «Productos y lotes fumigados» con **+ Agregar producto**. Cada línea toma un lote del stock o se escribe (producto + lote), con su cantidad opcional. Cada lote del stock pasa a **en fumigación**. | Calidad → Fumigación |
| Inicio: alerta de stock sin rotación | Tarjeta con los productos sin rotación, kg, valor al costo (si el perfil ve costos), valor de venta mínimo–máximo y los 3 principales. Al tocarla se va a la pestaña de rotación. | Inicio (perfiles con `rotacion.ver`) |
| Cómo va la empresa: venta vs meta | Barra «Venta del mes vs la meta», con la marca de lo esperado a la fecha, lo que falta y el aviso si va atrasada. | Cómo va la empresa |
| Necesidad semanal de ingresos (Adm. y Finanzas) | El Jefe de Administración y Finanzas registra cuánto necesita ingresar la empresa cada semana. Comercial lo ve junto a la meta de la semana (la meta general del mes prorrateada por días hábiles, lunes a sábado). Si difiere de la meta en más de `ingreso_semanal_tolerancia_pct` (5 %), se exige el **motivo de la variación**. Todos los cambios quedan en el historial. Al cerrar la semana, si no se llegó, se avisa a Jefatura de Ventas, Gerencia Comercial y Finanzas (`INGRESO_SEMANAL_VARIACION`). | Ídem (tabla y gráfico de 6 semanas) |
| Valor del stock sin rotación | Al costo y a precio de venta mínimo y máximo. | Ídem e Inicio |
| Sonido con la pantalla apagada | Con la pantalla apagada el celular detiene la página: lo único que puede sonar es la **notificación del sistema**. «Notificaciones en el celular» tiene ahora un **diagnóstico de 6 puntos**: https, pestaña propia, navegador compatible (en iPhone, instalar en la pantalla de inicio), permiso, clave del servidor y suscripción. Al activar el sonido (parlante) sin notificaciones activas, se ofrece activarlas. | Menú de usuario → Notificaciones en el celular |
| Chat entre usuarios | **Mensajes**: se elige a quién escribir (lista de usuarios activos), conversación uno a uno, «Leído/Enviado» y contador de no leídos en la barra superior. Quien recibe tiene una notificación en el celular si las activó. «Enviar esta pantalla por mensaje» adjunta el enlace de la pantalla actual (solo enlaces internos). | Icono de mensajes (barra superior) |
| Checklist del chofer desde su perfil | En «Mis entregas», el bloque **Mi checklist vehicular** muestra las rutas del chofer de hoy en adelante, con el estado de la salida y del retorno. Los botones llevan al checklist con la **imagen interactiva** del vehículo: se toca la parte dañada o se escribe la observación. | Mis entregas |
| Ruta manual: «¿Quién lleva la carga?» como lista | Lista desplegable: **Chofer de la empresa** (vehículo y chofer; sin trabajador ni área), **Otro trabajador** (trabajador, área, vehículo y motivo; sin chofer) o **Transporte externo** (unidad, empresa y **costo**; el costo solo aparece aquí). Los campos cambian solos. Lo oculto no se envía. | Cuadro de despacho → Nueva ruta manual |
| Ruta manual sin OV | Las OV son opcionales. Se pueden elegir traslados de la lista o escribir **Otra carga sin OV** (qué lleva, destino y kg, con sugerencias). Esa carga suma al peso de la ruta, a la sobrecarga y al cuadro del día. | Ídem |
| Preprogramación con recomendaciones | **Recomendaciones de la preprogramación**, ordenadas por prioridad. Ninguna se aplica sola. **Capacidad:** sobrecarga; rutas de la misma zona con baja ocupación que caben juntas («consolidar las rutas #A y #B en la unidad X»). **Lugar de entrega:** el mismo cliente y punto en rutas distintas, y OV pendientes que van a un punto que ya tiene ruta. **Horario:** cita antes de la salida, citas muy seguidas y citas por confirmar (modificar la cita o pasar la OV a otra ruta). | Programación de distribución |

## 2. Parámetros nuevos (estado PROPUESTO: los valida el área)

| Parámetro | Valor | Uso |
|---|---|---|
| `ingreso_semanal_tolerancia_pct` | 5 | Diferencia con la meta semanal que exige motivo |
| `ruta_ocupacion_minima_pct` | 60 | Bajo esta ocupación se recomienda consolidar |
| `minutos_minimos_entre_citas` | 45 | Mínimo entre dos citas de una ruta |
| `consolidar_entre_zonas` | No | Si también se recomienda juntar rutas de zonas distintas |

**Permisos nuevos:**
- `importaciones.calidad`: Calidad ve el seguimiento de importaciones y registra el informe.
- `finanzas.necesidad_semanal`: lo tiene el Jefe de Administración y Finanzas.
- `chat.usar`: lo tienen todos los perfiles.

## 3. Pendiente

- **Formato del informe de recepción de importación:** el modelo adjunto no llegó. Se usa REG-CAL-005, que ya estaba
  en el sistema. Si el modelo de la empresa tiene otros campos, se ajusta al recibirlo.
- **Formato de los informes PDF:** el formato adjunto no llegó. El rediseño de los PDF queda pendiente hasta recibirlo.
- **Sonido con la pantalla apagada:** depende de que cada celular tenga activadas las notificaciones, el sistema esté
  en https y, en iPhone, instalado en la pantalla de inicio. Se valida en el servidor definitivo.

## 4. Verificación

- `tests/test_v25.py` (11 pruebas):
  - documentos e informe de Calidad;
  - fumigación con varios lotes;
  - necesidad semanal con motivo;
  - tablero e inicio;
  - chat;
  - ruta sin OV;
  - lista desplegable;
  - checklist del chofer;
  - recomendaciones.
- La prueba de migraciones aplica 0001 → 0038 y compara con el modelo.
- Suite completa: **571 pruebas, todas pasan**.
