# Módulo de Operaciones – Corporación Productiva (prototipo funcional v0.6)

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

Pruebas: `pip install -r requirements-dev.txt && python -m pytest tests -v` (146 pruebas; también en PostgreSQL con TEST_DATABASE_URL).

## Documentación entregada (`docs/`)

| Documento | Contenido |
|---|---|
| [01_INVENTARIO_FUENTES](docs/01_INVENTARIO_FUENTES.md) | Los 30 archivos analizados, qué contiene cada uno y cómo se usó |
| [02_ESPECIFICACION_CONSOLIDADA](docs/02_ESPECIFICACION_CONSOLIDADA.md) | Alcance consolidado, contradicciones, vacíos, dependencias, decisiones técnicas y **preguntas Q1–Q17** (Q1, Q3, Q4 resueltas) |
| [03_MATRIZ_TRAZABILIDAD](docs/03_MATRIZ_TRAZABILIDAD.md) | 184 requerimientos (IF + TO-BE + decisiones): fuente → implementación → prueba → estado |
| [04_RESULTADOS_PRUEBAS](docs/04_RESULTADOS_PRUEBAS.md) | 104 pruebas automatizadas (SQLite y PostgreSQL), recorridos en navegador y compatibilidad con los archivos reales |
| [05_ESTADO_FUNCIONALIDADES](docs/05_ESTADO_FUNCIONALIDADES.md) | Implementado, parcial, pendiente y bloqueado |
| [14_DECISIONES_13OCT_PARTE3_Y_OBSERVACIONES_DEMO](docs/14_DECISIONES_13OCT_PARTE3_Y_OBSERVACIONES_DEMO.md) | v0.6: formatos con logos (OV, guía, certificados PT/MP/CA), vida útil, costos y mercado, observaciones al demo v0.5 y preguntas abiertas |
| [06_MODELO_DATOS](docs/06_MODELO_DATOS.md) | Estructura de almacenamiento (generado desde el código) |
| [07_PERFILES_PERMISOS_ALERTAS](docs/07_PERFILES_PERMISOS_ALERTAS.md) | Roles, permisos, alertas, parámetros y su origen (generado desde el código) |
| [08_INSTALACION_DESPLIEGUE](docs/08_INSTALACION_DESPLIEGUE.md) | Instalación, configuración, puesta en marcha y despliegue |
| [09_SEGURIDAD_INFRAESTRUCTURA](docs/09_SEGURIDAD_INFRAESTRUCTURA.md) | Requisitos a aprobar antes del uso en la organización |
| [10_ANALISIS_TO_BE](docs/10_ANALISIS_TO_BE.md) | TO-BE L5 actividad por actividad, aplicación de Q3/Q4 y nuevas preguntas Q12–Q17 |
| [13_DECISIONES_13OCT_PARTE2](docs/13_DECISIONES_13OCT_PARTE2.md) | Decisiones del 13-oct (2.ª parte), lista de clientes con penalidades, **preguntas abiertas y lo que falta para producción** |
| [12_DECISIONES_13OCT_Y_PRODUCCION](docs/12_DECISIONES_13OCT_Y_PRODUCCION.md) | Decisiones del 13-oct, validación de las listas de precios reales y **preguntas para pasar a producción** |
| [11_DECISIONES_12OCT](docs/11_DECISIONES_12OCT.md) | Respuestas del 12-oct aplicadas (interpretación, implementación, prueba) y **preguntas pendientes detalladas** |

## Guion de demostración (≈20 minutos)

1. **Faltante y alternativas** – `coord.ventas` → *Registrar OV*: cliente "CLIENTE DEMO AUTOSERVICIOS", PT-901 × 450,
   PT-903 × 60, PT-905 × 200. El sistema reserva por FEFO solo stock apto (excluye el lote que vence antes de los 180 días
   que exige ese cliente), calcula 70 % de unidades / 33 % de líneas y muestra otros almacenes, reempaque, producción y compra.
2. **Alertas** – `gerente.general` → *Alertas* agrupadas por área y urgencia; asignar, atender, comentar y cerrar.
3. **Traslado** – `coord.logistica` solicita usar el lote del almacén 767; `jefe.logistica` autoriza en *Traslados*;
   `coord.almacen` registra salida y recepción → la OV se reevalúa sola.
4. **Despacho parcial (Q3)** – `jefe.logistica` **o** `gerente.operaciones` aprueba el parcial indicando la fecha del
   saldo → alerta a Distribución y ruta. (`coord.ventas` y `sistemas` no pueden aprobar; `gerente.general` sí, registrado
   "en nombre de".) En la OV se ven las pre-solicitudes que el sistema generó ante el faltante (Q15).
5. **Preparación** – `lider.almacen` → *Preparación*: valida (o cambia el lote de) el plan de picking y registra el
   picking por lote; alerta al 80 %. Los certificados se pre-elaboran al quedar reservada la OV y `superv.calidad` los
   aprueba en *Certificados*.
6. **Despacho TO-BE** – en la ruta: `coord.distribucion` confirma; `aux.despacho` sube la foto del vehículo; `seguridad`
   la de inicio de carga y valida carga vs guía; `aux.despacho` la de mercadería cargada y valida la carga (aviso a
   Facturación); `coord.distribucion` registra la guía (o imprime la pre-guía/folio); `facturacion` carga la factura;
   `seguridad` revisa documentos y `aux.despacho` da su visto bueno; `lider.almacen` (Líder Operativo) autoriza la salida (Q16). Si Seguridad registró una
   diferencia con la guía, la salida se bloquea hasta que `coord.logistica` o `jefe.logistica` la apruebe (Q8); `aux.despacho` registra
   llegada, entrega con foto y guía firmada (o incidencia) y retorno. La OV muestra el saldo `-S1` reprogramado.
7. **Producción** – `coord.almacen` crea y envía una solicitud preliminar de PT-903; `jefe.produccion` la valida,
   programa, inicia, termina y liquida; `coord.almacen` recibe el PT; `jefe.calidad` libera el lote.
8. **Cargas** – `coord.almacen` sube `sample_data/demo_stock_lote_con_errores.xlsx`: el sistema muestra errores,
   permite corregir/excluir y solo entonces autoriza.
9. **Gerencia** – `gerente.general` → *Inicio*: indicadores (pendientes, cobertura, OTIF en dos variantes, detenidos,
   tiempos, incidencias, merma, monto y volumen).
10. **Precios mínimos (Q11)** – `jefe.ventas` modifica un precio en *Listas de precios*; `coord.ventas` registra una OV
    con precio igual o menor al mínimo de su canal (o sin precio) → alerta y la OV queda **detenida** hasta que
    `coord.ventas` o `jefe.ventas` la confirme. Los clientes con penalidades muestran sus condiciones (lotes por SKU).
    `asist.produccion` registra partes de producción con rendimiento y desmedro.
11. **Configuración** – `sistemas`: parámetros con estado DEFINIDO/PROPUESTO/PENDIENTE/AS-IS/DEMO y su fuente,
    matriz de permisos y destinatarios de alertas.

## Decisiones que requieren su intervención

Q1–Q17 y P1–P10 resueltas. Abiertas: R1 (significado de la vida útil del cliente), R2 (RUC en la lista de clientes),
R3 (pesos de penalidad), R4 (formato del costo), R5 (fuente de precios de mercado), R6 (nueva exportación de OV), más lo
que falta para producción: `docs/13_DECISIONES_13OCT_PARTE2.md` §4-§5.

## Documentos originales

Los archivos fuente (incluido el TO-BE recibido el 11-oct-2026) no se modificaron ni se incluyen en el repositorio porque contienen datos reales de clientes,
precios, conductores y placas. Colóquelos en `documentacion_fuente/` (ignorada por git) si desea conservarlos junto al proyecto.
