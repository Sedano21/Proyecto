# Rediseño de informes y tableros: matriz de indicadores por área (28-oct-2026)

Este documento es la **matriz de control** del rediseño. No es una pantalla del sistema. La fuente única es `app/services/indicators.py`, y esta tabla se genera desde ese archivo.

## 1. Reglas

- **OBLIGATORIO.** El indicador aparece en el inicio y en el informe predeterminado del área. En el informe personalizado viene marcado como «predeterminado».
- **DISPONIBLE.** No aparece por defecto, pero el usuario puede agregarlo en «Personalizar informe».
- **NO VISIBLE.** Cualquier otra área no ve el indicador en ninguna vista. Tampoco aparece en filtros, gráficos, tablas, exportaciones PDF/Excel ni plantillas, porque se descarta al calcular y no solo al mostrar.
- **Gerencia y Sistemas.** Ven el conjunto: Gerencia supervisa todas las áreas y Sistemas da soporte.
- **Permiso.** Los datos restringidos (montos, finanzas) exigen además su permiso. Ocultar un indicador no reemplaza la seguridad.
- **Exclusiones de la empresa.** El parámetro `indicadores_ocultos` (*Configuración*) retira indicadores de un área o de un perfil. Formato: `{"Producción": ["CODIGO"], "JEFE_VENTAS": ["CODIGO"]}`.
  - Prevalece sobre la matriz en todas las vistas de ese perfil.
  - No borra el dato ni lo quita a las demás áreas.
- **Asignación por área.** Es una **propuesta** basada en las responsabilidades documentadas de cada perfil. La empresa la ajusta con ese parámetro, sin tocar el código.

## 2. Producción
Producción ve solo su operación:
- cumplimiento del programa;
- producido frente al plan;
- rendimiento y desmedro por línea;
- mermas fuera de lo proyectado;
- uso de capacidad;
- paradas y demoras de atención;
- OEE;
- solicitudes pendientes;
- diferencias en la recepción de producto terminado.

Del área comercial recibe un solo dato operativo: **faltantes por producto**, que le indica qué producir.

**Ya no ve:** OTIF, fill rate, montos de OV, precios, volumen de OV, pedidos por estado, tiempos de almacén ni rechazos. En el informe personalizado tampoco aparecen las columnas de precio, importe ni monto, ni siquiera en las exportaciones.

## 3. Matriz

| Código | Indicador | Área propietaria | Ubicación | Obligatorio (predeterminado) | Disponible (personalizar) | Requiere permiso | Motivo funcional |
|---|---|---|---|---|---|---|---|
| `PED_PENDIENTES` | Pedidos pendientes y su cobertura de stock | Comercial | Inicio · Pedidos | Gerencia, Sistemas, Comercial, Almacén, Logística, Distribución | Finanzas, Facturación | — | Saber cuántas OV faltan atender y cuántas tienen stock completo para planificar la atención. |
| `PED_COBERTURA` | Cobertura promedio de stock de los pedidos | Logística | Inicio · Pedidos | Gerencia, Sistemas, Comercial, Almacén, Logística | — | — | Detectar pedidos sin stock suficiente para reponer, trasladar o renegociar la fecha. |
| `OTIF_SALIDA` | OTIF a la salida (completo y a tiempo) | Logística | Inicio · Pedidos | Gerencia, Sistemas, Comercial, Almacén, Logística, Distribución | Calidad | — | Medir el nivel de servicio comprometido con el cliente (decisión Q2). |
| `FILL_RATE` | Fill rate a la salida (unidades, líneas y pedidos al 100 %) | Logística | Inicio · Pedidos | Gerencia, Sistemas, Comercial, Almacén, Logística, Distribución | — | — | Medir cuánto de lo pedido salió; base para corregir faltantes en preparación. |
| `VOLUMEN_OV_KG` | Volumen de OV en kg (total y pendiente) | Comercial | Inicio · Pedidos | Gerencia, Sistemas, Comercial, Logística | Almacén, Distribución | — | Dimensionar la carga de preparación y transporte del periodo. |
| `RECHAZOS` | Rechazos, devoluciones y entregas parciales | Distribución | Inicio · Pedidos | Gerencia, Sistemas, Comercial, Distribución, Logística, Calidad | Almacén | — | Gestionar la causa con el cliente (Comercial), en ruta (Distribución) o del producto (Calidad). |
| `MONTO_OV` | Monto de OV en S/ (total y pendiente) | Comercial | Inicio · Precios y montos | Gerencia, Sistemas, Comercial | Finanzas, Facturación | dashboard.precios, finanzas.ver | Seguimiento de la venta; Finanzas lo usa para créditos y cobranza. |
| `PRECIO_BAJO_MINIMO` | OV con precio en el límite o bajo el mínimo de lista | Comercial | Inicio · Precios y montos | Gerencia, Sistemas, Comercial | — | dashboard.precios | Comercial confirma o corrige precios fuera de política. |
| `T_PREPARACION` | Tiempo promedio de preparación | Almacén | Inicio · Operación | Gerencia, Sistemas, Almacén, Logística | Distribución | — | Controlar la productividad del picking. |
| `T_DESPACHO` | Tiempo de preparado a salida | Distribución | Inicio · Operación | Gerencia, Sistemas, Almacén, Distribución, Logística | — | — | Detectar demoras entre el fin de la preparación y la salida del camión. |
| `COMPRAS_PENDIENTES` | Compras pendientes | Compras | Inicio · Operación | Gerencia, Sistemas, Compras, Importaciones, Logística | Almacén | — | Seguir las solicitudes de compra abiertas. |
| `PRODUCCION_PENDIENTE` | Solicitudes de producción pendientes | Producción | Inicio · Operación | Gerencia, Sistemas, Producción, Logística | Almacén | — | Producción programa y atiende las solicitudes abiertas. |
| `DIF_INVENTARIO` | Diferencias de inventario en conteos | Almacén | Inicio · Operación | Gerencia, Sistemas, Almacén, Logística | — | — | Almacén corrige y concilia con SAP. |
| `DIF_RECEPCION_PT` | Diferencias en la recepción de producto terminado | Almacén | Inicio · Operación | Gerencia, Sistemas, Almacén, Producción, Logística | — | — | Producción y Almacén aclaran lo liquidado frente a lo recibido. |
| `PED_DETENIDOS` | Pedidos detenidos y motivo | Comercial | Inicio · Seguimiento | Gerencia, Sistemas, Comercial, Almacén, Logística | Finanzas, Distribución | — | Liberar los pedidos detenidos (precio, crédito, stock, orden de compra). |
| `PED_ESTADOS` | Pedidos por estado | Comercial | Inicio · Seguimiento | Gerencia, Sistemas, Comercial, Logística | Almacén, Distribución | — | Vista de la cartera de pedidos por etapa. |
| `FALTANTES` | Faltantes por producto (unidades no reservadas) | Logística | Inicio · Seguimiento | Gerencia, Sistemas, Almacén, Logística, Producción, Compras | Comercial | — | Dato operativo para decidir qué producir, comprar o trasladar. |
| `FILL_DETALLE` | Fill rate por pedido despachado | Logística | Inicio · Seguimiento | Gerencia, Sistemas, Logística, Distribución | Comercial, Almacén | — | Revisar pedido por pedido lo que salió incompleto o tarde. |
| `CAUSAS_ERROR` | Dónde están los mayores errores (por etapa) | Logística | Inicio · Seguimiento | Gerencia, Sistemas, Logística, Almacén, Distribución, Calidad | Comercial | — | Atacar la etapa que más falla. |
| `INCIDENCIAS` | Incidencias por tipo | Distribución | Inicio · Seguimiento | Gerencia, Sistemas, Distribución, Calidad, Logística | Almacén, Comercial | — | Gestionar las incidencias abiertas de su ámbito. |
| `PROD_CUMPLIMIENTO` | Cumplimiento del programa de producción | Producción | Inicio · Producción e informe de producción | Gerencia, Sistemas, Producción | Logística | — | Producción mide si ejecutó lo planificado. |
| `PROD_PRODUCIDO` | Producido frente al plan (kg y unidades) | Producción | Inicio · Producción e informe de producción | Gerencia, Sistemas, Producción | Logística, Almacén | — | Volumen ejecutado y su brecha con el plan. |
| `PROD_RENDIMIENTO` | Rendimiento y desmedro por línea | Producción | Inicio · Producción e informe de producción | Gerencia, Sistemas, Producción | Calidad | — | Controlar mermas y calibración por línea. |
| `PROD_MERMA_FUERA` | Mermas fuera de lo proyectado | Producción | Inicio · Producción e informe de producción | Gerencia, Sistemas, Producción | Calidad | — | Investigar las liquidaciones con merma fuera de tolerancia. |
| `PROD_CAPACIDAD` | Uso de capacidad por línea | Producción | Inicio · Producción e informe de producción | Gerencia, Sistemas, Producción | Logística | — | Detectar líneas sub- o sobreutilizadas. |
| `PROD_PARADAS` | Paradas de línea y demoras de atención | Producción | Inicio · Producción e informe de producción | Gerencia, Sistemas, Producción | — | — | Reducir paradas y solicitudes atendidas tarde. |
| `PROD_OEE` | OEE (disponibilidad, rendimiento y calidad) | Producción | Inicio · Producción e informe de producción | Gerencia, Sistemas, Producción | — | — | Eficiencia global de los equipos. |
| `MONTOS_VENTA` | Montos de venta (precio, importe, total, proyección, gasto) | Comercial | Columnas del informe personalizado | Gerencia, Sistemas, Comercial | Finanzas, Facturación | dashboard.precios, finanzas.ver | Información comercial; no corresponde a áreas operativas. |
| `COSTO_COMPRA` | Precio de compra | Compras | Columnas del informe personalizado | Gerencia, Sistemas, Compras, Importaciones | Logística, Finanzas | — | Gestión de compras y costos de abastecimiento. |
| `COSTO_TRANSPORTE` | Costo de transporte | Distribución | Columnas del informe personalizado | Gerencia, Sistemas, Distribución, Logística | Finanzas | — | Control del costo de la flota y de los transportistas. |

Las áreas que no figuran en una fila no ven ese indicador.

## 4. Informes

- **Portada de Informes.** Ofrece dos opciones:
  - **«Informe predeterminado»:** el informe institucional del área, listo para usar.
  - **«Personalizar informe».**
  
  Debajo están las plantillas guardadas y los demás informes autorizados. No se agregaron pestañas nuevas.
- **Informe predeterminado por área:**

  | Área | Informe |
  |---|---|
  | Gerencia, Sistemas y Comercial | Gestión comercial |
  | Producción | Producción |
  | Almacén y Logística | Movimiento de stock |
  | Distribución | Distribución |
  | Calidad | Reempaque |
  | Compras, Importaciones, Finanzas y Facturación | Configuración institucional del informe personalizado (compras, importaciones o facturas del periodo) |

- **Cabecera institucional.** Logo original, nombre del informe, área, periodo, fecha y hora de actualización, fuentes de datos y limitaciones conocidas. El PDF lleva el logo en el encabezado.
- **Informe de Producción.** Orden de lectura:
  1. indicadores principales;
  2. «Qué requiere atención»;
  3. capacidad;
  4. programación;
  5. detalle.
  
  Sin partes en el periodo, muestra un solo aviso (antes había uno por línea). Los gráficos sin datos lo dicen en lugar de dibujar una línea en cero.
- **Personalizar informe:**
  - el usuario elige periodo, **indicadores de su área**, datos (fuente), columnas, agrupación, búsqueda y secciones;
  - la **vista previa** muestra primero el **resumen de la configuración**, que también va en el PDF y el Excel;
  - las **plantillas** pueden ser **personales** o **compartidas con el área**. Las comparten las jefaturas y coordinaciones con el permiso `informes.plantillas_compartidas`;
  - la plantilla guarda el periodo como «últimos N días»;
  - una plantilla no cambia el informe predeterminado de nadie. Al abrirla se vuelven a aplicar las reglas del perfil que la usa.
- **Inicio.** Cada perfil ve solo sus bloques. Comercial ya no ve duplicados el OTIF, el fill rate y los montos, que están en «Gestión comercial del mes».

## 5. Pendiente de confirmar por la empresa

- La asignación de áreas de la matriz (§3), en especial:
  - Calidad: rechazos e incidencias;
  - Finanzas: montos y pedidos detenidos;
  - Compras: faltantes.
- Las metas de referencia: OTIF 95 % y cumplimiento del programa 90 %. Hoy solo marcan en ámbar los valores por debajo y no generan bloqueos.
- El logo: se usa el archivo de la empresa en `static/img`. Si existe una versión oficial vectorial, se carga como `logo_oficial.svg` o `.png` y el sistema la toma sola.
