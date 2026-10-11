# Módulo de Operaciones – Corporación Productiva (prototipo funcional v0.2)

Primera versión funcional del sistema especificado en el **Informe Funcional del Módulo de Operaciones v1.0**
(9-oct-2026), construida para probar los procesos digitalizados y presentarlos a la gerencia. Ejecuta la lógica real
(reservas, cobertura, alternativas, BOM y merma, aprobaciones, alertas, rutas, certificados, indicadores) sobre una base
de datos, con perfiles y permisos. Usa **datos ficticios**; no está conectado a SAP ni a sistemas productivos.

> **Este prototipo no está listo para producción.** Ver decisiones pendientes y requisitos de seguridad.

## Inicio rápido

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.cli demo
python run.py                                          # http://127.0.0.1:5000  · contraseña demo: Demo2026!
```

Pruebas: `pip install -r requirements-dev.txt && python -m pytest tests -v` (63 pruebas).

## Documentación entregada (`docs/`)

| Documento | Contenido |
|---|---|
| [01_INVENTARIO_FUENTES](docs/01_INVENTARIO_FUENTES.md) | Los 30 archivos analizados, qué contiene cada uno y cómo se usó |
| [02_ESPECIFICACION_CONSOLIDADA](docs/02_ESPECIFICACION_CONSOLIDADA.md) | Alcance consolidado, contradicciones, vacíos, dependencias, decisiones técnicas y **preguntas Q1–Q17** (Q1, Q3, Q4 resueltas) |
| [03_MATRIZ_TRAZABILIDAD](docs/03_MATRIZ_TRAZABILIDAD.md) | 156 requerimientos (IF + TO-BE + decisiones): fuente → implementación → prueba → estado |
| [04_RESULTADOS_PRUEBAS](docs/04_RESULTADOS_PRUEBAS.md) | 63 pruebas automatizadas, recorridos en navegador (IF y TO-BE) y compatibilidad con los archivos reales |
| [05_ESTADO_FUNCIONALIDADES](docs/05_ESTADO_FUNCIONALIDADES.md) | Implementado, parcial, pendiente y bloqueado |
| [06_MODELO_DATOS](docs/06_MODELO_DATOS.md) | Estructura de almacenamiento (generado desde el código) |
| [07_PERFILES_PERMISOS_ALERTAS](docs/07_PERFILES_PERMISOS_ALERTAS.md) | Roles, permisos, alertas, parámetros y su origen (generado desde el código) |
| [08_INSTALACION_DESPLIEGUE](docs/08_INSTALACION_DESPLIEGUE.md) | Instalación, configuración, puesta en marcha y despliegue |
| [09_SEGURIDAD_INFRAESTRUCTURA](docs/09_SEGURIDAD_INFRAESTRUCTURA.md) | Requisitos a aprobar antes del uso en la organización |
| [10_ANALISIS_TO_BE](docs/10_ANALISIS_TO_BE.md) | TO-BE L5 actividad por actividad, aplicación de Q3/Q4 y nuevas preguntas Q12–Q17 |

## Guion de demostración (≈20 minutos)

1. **Faltante y alternativas** – `coord.ventas` → *Registrar OV*: cliente "CLIENTE DEMO AUTOSERVICIOS", PT-901 × 450,
   PT-903 × 60, PT-905 × 200. El sistema reserva por FEFO solo stock apto (excluye el lote que vence antes de los 180 días
   que exige ese cliente), calcula 70 % de unidades / 33 % de líneas y muestra otros almacenes, reempaque, producción y compra.
2. **Alertas** – `gerente.general` → *Alertas* agrupadas por área y urgencia; asignar, atender, comentar y cerrar.
3. **Traslado** – `coord.logistica` solicita usar el lote del almacén 767; `jefe.logistica` autoriza en *Traslados*;
   `coord.almacen` registra salida y recepción → la OV se reevalúa sola.
4. **Despacho parcial (Q3)** – `jefe.logistica` aprueba el parcial indicando la fecha del saldo; queda pendiente de
   `gerente.operaciones`, que lo aprueba → alerta a Distribución y ruta. (`coord.ventas` y `sistemas` no pueden aprobar;
   `gerente.general` sí, registrado "en nombre de".)
5. **Preparación** – `lider.almacen` → *Preparación*: valida (o cambia el lote de) el plan de picking y registra el
   picking por lote; alerta al 80 %. Los certificados se pre-elaboran al quedar reservada la OV y `superv.calidad` los
   aprueba en *Certificados*.
6. **Despacho TO-BE** – en la ruta: `coord.distribucion` confirma; `aux.despacho` sube la foto del vehículo; `seguridad`
   la de inicio de carga y valida carga vs guía; `aux.despacho` la de mercadería cargada y valida la carga (aviso a
   Facturación); `coord.distribucion` registra la guía (o imprime la pre-guía/folio); `facturacion` carga la factura;
   `seguridad` revisa documentos y autoriza la salida; `coord.distribucion` confirma la salida; `aux.despacho` registra
   llegada, entrega con foto y guía firmada (o incidencia) y retorno. La OV muestra el saldo `-S1` reprogramado.
7. **Producción** – `coord.almacen` crea y envía una solicitud preliminar de PT-903; `jefe.produccion` la valida,
   programa, inicia, termina y liquida; `coord.almacen` recibe el PT; `jefe.calidad` libera el lote.
8. **Cargas** – `coord.almacen` sube `sample_data/demo_stock_lote_con_errores.xlsx`: el sistema muestra errores,
   permite corregir/excluir y solo entonces autoriza.
9. **Gerencia** – `gerente.general` → *Inicio*: indicadores (pendientes, cobertura, OTIF en dos variantes, detenidos,
   tiempos, incidencias, merma, monto y volumen).
10. **Configuración** – `sistemas`: parámetros con estado DEFINIDO/PROPUESTO/PENDIENTE/AS-IS/DEMO y su fuente,
    matriz de permisos y destinatarios de alertas.

## Decisiones que requieren su intervención

Resueltas el 11-oct-2026: Q1 (TO-BE recibido), Q3 (parcial GO + Jefatura de Logística, saldo reprogramado),
Q4 (GG aprueba; Sistemas accede a todo pero no aprueba). Pendientes (detalle en `docs/02` §6 y `docs/10` §4):
Q2 definición de OTIF · Q5 uso de almacenes SAP no documentados · Q6 estado de lotes nuevos en cargas SAP ·
Q7 valores de márgenes/umbrales/cortes · Q8 bloqueo por discrepancia de guía · Q9 clave de liquidación SAP ·
Q10 fases de importación · Q11 fuente de precios y fecha comprometida · Q12 origen del reempaque · Q13 aprobador del
traslado · Q14 aprobación de compra por Logística · Q15 pre-solicitudes automáticas · Q16 quién autoriza la salida ·
Q17 uno o dos roles de coordinación de almacén.

## Documentos originales

Los archivos fuente (incluido el TO-BE recibido el 11-oct-2026) no se modificaron ni se incluyen en el repositorio porque contienen datos reales de clientes,
precios, conductores y placas. Colóquelos en `documentacion_fuente/` (ignorada por git) si desea conservarlos junto al proyecto.
