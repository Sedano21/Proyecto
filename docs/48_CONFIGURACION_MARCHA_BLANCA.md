# 48 · Configuración para la marcha blanca (servidor coprod-one)

**10-nov-2026.** Lista de lo que hay que dejar configurado para operar todo el flujo: OV, edición, lotes, picking,
guías, producción y calidad, contra la base real de SAP (SBO_CORPRODUC).

**Dónde se configura:**
- **Parámetros:** menú **Administración → Configuración → Parámetros** (con el usuario de Sistemas). Cada cambio queda
  versionado; el enlace «historial» muestra quién lo cambió. Los parámetros de tipo **lista** o **diccionario** se
  escriben en formato JSON:
  - lista: `["A", "B"]`;
  - diccionario: `{"clave": valor}`;
  - comillas dobles siempre.
- **Variables del servidor:** `/etc/operaciones/operaciones.env` (con `sudo nano`, luego
  `sudo systemctl restart operaciones`).

Los parámetros en estado **DEFINIDO** ya tienen el valor que pidió la empresa y no hay que tocarlos. Los marcados
**PENDIENTE** son decisiones de ustedes.

---

## Paso 1 · Datos maestros (antes de traer el stock)

| ☐ | Qué | Dónde | Por qué |
|---|---|---|---|
| ☐ | **Almacenes con el mismo código que SAP** (`ALM-001`, …) | Configuración → Almacenes | El stock se carga en el almacén cuyo código coincide. Revise con `app ".venv/bin/python -m app.cli sap-diagnostico"` la línea «Almacenes … NO existen en SAP». |
| ☐ | Uso y prioridad de cada almacén (venta, MP, externo) | Configuración → Almacenes | Define de dónde se reserva y el orden. |
| ☐ | Líneas de producción y su capacidad | Configuración → Líneas de producción | Programación y monitoreo. |
| ☐ | Vehículos (con SOAT vigente) y choferes vinculados a su usuario | Distribución → Flota y conductores | Sin SOAT vigente no se asigna la unidad. El chofer ve «Mis entregas» solo si su ficha está vinculada a su usuario. |
| ☐ | Usuarios de cada persona con su perfil (y almacén, en Almacén) | Usuarios y permisos / `crear-usuario` | Cada persona con su cuenta. |
| ☐ | Feriados del año | Configuración → Feriados | Plazos y capacidad. |
| ☐ | Listas de precios mínimos vigentes | Comercial → Listas de precios (carga) | Sin lista, las OV no validan el precio mínimo. |
| ☐ | Metas de venta del mes | Comercial → Objetivos de venta | «Cómo va la empresa» y la necesidad semanal. |

## Paso 2 · Traer los datos de SAP (Integración SAP)

Orden recomendado. Cada carga se **revisa y se confirma**: nada se aplica solo.

| ☐ | Dato | Estado | Nota |
|---|---|---|---|
| ✅ | Clientes | Confirmado (carga #1) | |
| ✅ | Artículos | Confirmado (carga #2) | |
| ☐ | **Stock por lote** | Ya se puede (consulta CPOPS_STOCK_LOTE) | Inventario sincerado: **traerlo ahora**. Es la **base inicial**: sus lotes quedan disponibles. Los lotes **nuevos** de cargas posteriores quedan «pendientes de revisión» de Calidad (`estado_lote_nuevo_carga`). |
| ☐ | **Órdenes de venta abiertas** | | Las OV abiertas de SAP entran al módulo para prepararlas y despacharlas. No se duplican. |
| ☐ | **Entregas (guías)** | | **Sí, traerlas.** Trae las guías de los últimos `sap_despachos_dias` (30). Sirven para el historial de despachos, el OTIF, las devoluciones contra guía y la conciliación con SAP. Solo lee de SAP. |
| ☐ | **Liquidaciones de producción** | | **Sí, traerlas.** Trae las de los últimos `sap_liquidacion_dias` (30) con las órdenes de fabricación y entradas estándar de SAP (no necesita consulta guardada). Sirven para el historial y los indicadores de Producción. Solo lee de SAP. |

**Lotes con comas en lugar de puntos** (p. ej. `000863FA,,` en vez de `000863FA..`):
- El sistema **ya lo maneja**. Guarda el lote **exacto como está en SAP**, porque la guía de SAP lo exige así.
- Lo trata como el mismo lote y la misma variante: «,,» = «..» = 3.ª producción. Al buscar `000863FA` aparecen todas
  sus variantes.
- En la carga de stock aparece como **advertencia** («coma en lugar de punto»), no como error: se puede confirmar.
- Lo que conviene es que, **desde ahora**, en SAP se digite con puntos. Los lotes ya creados en SAP no se pueden
  renombrar; no hace falta.

## Paso 3 · Parámetros de Integración SAP

| ☐ | Parámetro | Para la marcha blanca | Comentario |
|---|---|---|---|
| ✅ | `sap_consultas` | `{"STOCK": "CPOPS_STOCK_LOTE", "LIQUIDACION": ""}` | Ya quedó así con el comando. LIQUIDACION vacío está bien (usa las entidades estándar). |
| ☐ | `sap_escritura_empresas` | **Decisión.** Hoy `["ZZZ_CORPRODUC_TEST260826"]`: el módulo **no escribe** en la base real | Para que las OV y guías creadas en el módulo pasen a SAP: `["SBO_CORPRODUC"]`. Hágalo después de una prueba controlada (ver doc 46 y la respuesta del 09-nov). |
| ✅ | `sap_escritura_ov` | `true` (ya) | Solo actúa en las bases de la lista anterior. |
| ☐ | `sap_escritura_cotizaciones` | **Decisión.** Recomendado `false` al inicio | Si está en `true` y la base está autorizada, las cotizaciones del módulo se crean en SAP. |
| ☐ | `sap_sync_tipos` | `["OV", "CLIENTES", "PRODUCTOS", "DESPACHOS"]` | Lo que se trae solo cada `SAP_SYNC_MIN` minutos. El **stock** recomiendo traerlo a pedido una vez al día durante la marcha blanca (y agregarlo aquí después). |
| ☐ | `sap_autoconfirmar` | `[]` (vacío) durante la marcha blanca | Así cada carga se revisa antes de aplicarse. Después: `["CLIENTES", "PRODUCTOS"]`. |
| ✅ | `sap_sync_horario` | `"06:00-21:00"` (ya) | Fuera de ese horario no se sincroniza. |
| ✅ | `cerrar_ov_cerrada_en_sap` | `true` | La OV cerrada en SAP se cierra en el módulo. |

**Sincronización automática (variables del servidor):** agregar al final de `/etc/operaciones/operaciones.env`:
```
SAP_SYNC_USER=sistemas
SAP_SYNC_MIN=60
```
Luego `sudo systemctl restart operaciones`. `SAP_SYNC_USER` es el usuario del módulo a cuyo nombre quedan las cargas
automáticas.

## Paso 4 · Parámetros de la operación

### Comercial

| ☐ | Parámetro | Valor actual | Qué decidir |
|---|---|---|---|
| ✅ | `hora_corte_ov_dia_siguiente` | `"12:00"` | Hora límite para despachar al día siguiente. |
| ✅ | `tipos_ov_despues_corte` | `["MP", "GR"]` | Tipos que se aceptan después del corte. |
| ✅ | `exigir_oc_ov_modulo` | `true` | La OV pide la orden de compra del cliente (o queda en borrador). |
| ☐ | `direccion_recojo` | vacío | **PENDIENTE:** dirección del almacén para los pedidos con «recojo en almacén». |
| ☐ | `margen_alerta_precio_pct` | `0` | **PENDIENTE:** con 0 alerta solo si el precio es igual o menor al mínimo; con 3, también si está a menos de 3 % sobre el mínimo. |
| ☐ | `marcas_propias` | `[]` | Escribir las marcas propias, p. ej. `["COSECHA ANDINA", "CANTACLARO"]`. Lo demás se trata como marca blanca. |

### Almacén y lotes

| ☐ | Parámetro | Valor actual | Qué decidir |
|---|---|---|---|
| ✅ | `politica_lotes` | `"FEFO"` | Reserva primero lo que vence antes. |
| ✅ | `dias_sin_rotacion` | `90` | Días sin salida para «stock sin rotación». |
| ☐ | `dias_vencimiento_proximo` | vacío | **PENDIENTE:** días antes del vencimiento para alertar (p. ej. `60`). Sin valor no alerta. |
| ☐ | `umbrales_tamano_pedido_kg` | vacío | **PENDIENTE (alta), decisión de negocio:** los kg que separan un pedido pequeño, mediano y grande. **Hoy el sistema todavía no usa este valor:** la regla de picking anticipado de pedidos grandes (informe de la simulación) se implementa cuando definan los umbrales. Envíenlos y la dejo funcionando. |
| ☐ | `cortes_preparacion` | `[]` | **PENDIENTE:** horarios de corte del picking, p. ej. `["10:00", "15:00"]`. |

### Distribución

| ☐ | Parámetro | Valor actual | Qué decidir |
|---|---|---|---|
| ✅ | `hora_corte_rutas` | `"15:00"` | |
| ✅ | `exigir_checklist_vehicular` | `true` | Ninguna unidad propia sale sin checklist validado por Seguridad. |
| ✅ | `exigir_soat_vigente` | `true` | |
| ☐ | `zonas_distrito` | `{}` | **PENDIENTE (importante):** agrupar distritos en zonas de reparto, p. ej. `{"LIMA ESTE": ["ATE", "SANTA ANITA", "LA MOLINA"], "LIMA NORTE": ["COMAS", "LOS OLIVOS"]}`. Vacío = una zona por distrito (más rutas de las necesarias). |
| ☐ | `tolerancia_discrepancia_guia` | `0` | Unidades de diferencia guía vs carga que se toleran. 0 = cualquier diferencia es discrepancia. |
| ☐ | `geosatelital_url_panel` | (panel actual) | Confirmar la dirección del panel de GEOSATELITAL. |

### Producción y Calidad

| ☐ | Parámetro | Valor actual | Qué decidir |
|---|---|---|---|
| ☐ | `almacenes_produccion` | `[]` | **PENDIENTE:** códigos SAP de los almacenes de Producción. Con ellos, la validación de materiales mira solo esos almacenes y propone el traslado de lo que falte. |
| ☐ | `merma_pct_global` | vacío | **PENDIENTE:** merma por defecto (%) si el producto no tiene una propia. |
| ☐ | `umbral_merma_pct` | vacío | **PENDIENTE:** merma real (%) que dispara la alerta. |
| ☐ | `autorizacion_sanitaria` | `Nº000502- MIDAGRI-SENASA-LIMA CALLAO` | **Confirmar el texto exacto** (sale en los certificados). |

### Abastecimiento y Mantenimiento (pueden esperar)

`umbral_mayor_volumen`, `margen_reposicion_dias`, `usar_stock_seguridad`, `vigencia_fumigacion_unidad_dias`: se dejan
vacíos hasta que el área los defina; sin ellos el sistema funciona con su comportamiento por defecto.

### Seguridad y datos personales (antes de que entre el personal)

| ☐ | Parámetro | Qué hacer |
|---|---|---|
| ☐ | `aviso_datos_texto` y `aviso_datos_version` | Hoy es un **borrador**. Que lo revise el área legal; luego pegue el texto final y cambie la versión (p. ej. `1.0`). Cada persona lo acepta en su primer ingreso. |
| ☐ | `retencion_datos_personales_dias` | **PENDIENTE (legal):** días que se guardan las fotos de entrega y los datos de conductores. Vacío = no se borran. |

## Paso 5 · Comprobación final

```bash
sudo bash /opt/operaciones/deploy/verificar_servidor.sh coprod-one.duckdns.org --sap
app() { sudo bash /opt/operaciones/deploy/app.sh "$*"; }
app ".venv/bin/python -m app.cli sap-diagnostico"
```
Y una prueba de punta a punta con una OV real:
1. Registrarla.
2. Comprobar que se reserva el stock.
3. Hacer el picking.
4. Generar el precertificado.
5. Armar la ruta.
6. Pasar el checklist y la salida.
7. Registrar la conformidad.

Con `sap_escritura_empresas` autorizado, comprobar además que la OV y la guía aparecen en SAP.
