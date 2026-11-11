# Ronda V29 (11-nov-2026): notas de crédito sobre OV, órdenes de servicio, desviación de la demanda y balance de peso

Pruebas con datos ficticios.
- **Lectura de SAP:** notas de crédito, facturas, órdenes del periodo, órdenes de fabricación y series.
- **Escritura en SAP:** nada nuevo.
- **Migración nueva:** **0041**.

## 1. Lo pedido y dónde quedó

| Pedido | Implementación | Dónde |
|---|---|---|
| Nota de crédito sobre una OV: picar lo correcto y liberar lo reservado | Ver el punto 1.1. | OV, picking, alerta y **Comercial → Notas de crédito sobre OV** |
| Órdenes de venta y órdenes de servicio son distintas y deben salir aparte | Cada orden de SAP queda como **venta** o **servicio** según su **serie**. Ver el punto 1.2. | OV, conciliación y demanda |
| Ver el resultado de órdenes abiertas vs guías, con un filtro arriba para las órdenes de servicio | Pestañas **Órdenes de venta / Órdenes de servicio / Todas** en la pantalla de conciliación. Ver el punto 1.3. | Comercial → **Órdenes de venta y servicio vs guías** (también desde Integración SAP) |
| La desviación de la proyección de demanda con las OV y órdenes de servicio, abiertas y cerradas | Ver el punto 1.4. | Análisis → Demanda proyectada |
| Alertar cuando en SAP el cálculo de una orden de fabricación o liquidación no cuadra | Ver el punto 1.5. | Producción → **Balance de peso de OF (SAP)** y alerta `BALANCE_OF` |
| Cómo funciona la simulación y cómo usarla con la base de pruebas de SAP | Ver el punto 2. | — |

### 1.1 Notas de crédito sobre una OV

Se leen junto con **«Facturas y notas de crédito → Traer de SAP»**. Para cada línea de la nota se sigue la cadena: nota de crédito → factura → OV.

**Nota sobre una factura hecha desde la OV** (factura de reserva o factura anticipada), con la OV todavía por despachar:
- La cantidad de la nota **se descuenta de lo que falta despachar** de esa línea. Lo ya despachado no se toca.
- Se **liberan las reservas que sobran**, las más recientes primero.
- Si ya se preparó de más, la alerta dice cuánto devolver al stock.
- Si la OV se queda sin nada por despachar, **se cierra** en el módulo y se liberan todas sus reservas.
- Se avisa a Comercial (con el ejecutivo de la OV), Almacén, Distribución y la Jefatura de Operaciones.
- La OV y la tarea de picking muestran el recuadro **«NO DESPACHAR»** con la nota, el producto y la cantidad.

**Nota sobre la factura de una guía** (la mercadería ya salió: devolución o descuento): solo se registra; no cambia el picking.

Otras reglas:
- Cada línea de nota se aplica **una sola vez**.
- La siguiente carga de OV de SAP, que sigue mostrando lo acreditado como pendiente, **no devuelve** la cantidad. Si alguien también rebaja la OV en SAP, no se descuenta dos veces.
- Las notas manuales (sin factura base) o basadas en una devolución no se pueden unir a una OV y no se aplican.

### 1.2 Órdenes de venta y órdenes de servicio

Cada orden de SAP se clasifica así:
- **Servicio:** el **código de su serie** está en el parámetro `sap_series_orden_servicio` (p. ej. `["23"]`), o el documento es de tipo servicio en SAP.
- **Venta:** todas las demás.

La clase se guarda en la OV del módulo; en el detalle, la orden de servicio se titula «Orden de servicio».

Para saber qué serie usan, el comando **`app ".venv/bin/python -m app.cli sap-series"`** lista las series de órdenes de SAP con su código y su nombre, cuántas órdenes tuvo cada una en los últimos 90 días y cómo las clasifica hoy el módulo. Solo lee. La sincronización usa solo consultas de lectura (GET) y por eso clasifica por el código, no por el nombre.

Las **órdenes de fabricación** de SAP ligadas a una orden (V27) siguen en su columna, ahora llamada «Orden de fabricación», para no confundirlas con las órdenes de servicio.

### 1.3 Pantalla de órdenes abiertas vs guías de SAP

- Pestañas arriba: **Órdenes de venta / Órdenes de servicio / Todas**, cada una con su cantidad.
- En cada pestaña: indicadores de incompletas, completas, sin despacho y con observación; el detalle y el Excel. El Excel trae la clase y la serie.
- Muestra la situación de todas las órdenes abiertas hasta hoy, según la última lectura de SAP, que la sincronización actualiza sola.
- Nueva columna **«Nota de crédito»**: lo que una nota sacó del despacho. Si con ella la orden quedó completa, avisa que hay que cerrarla en SAP.
- Está en el menú de Comercial para quienes ven OV o Distribución (**Órdenes de venta y servicio vs guías**), no solo en Integración SAP.

### 1.4 Desviación de la demanda

La sección «Ejecución del periodo» y el cumplimiento por semana o día ahora usan las **órdenes de venta y de servicio, abiertas y cerradas**:
- **Fuente:** la lectura de SAP del periodo, con el botón **«Traer de SAP las órdenes del periodo»** o la sincronización automática si se agrega `ORDENES` a `sap_sync_tipos`. Lee desde el primer día de hace `sap_ordenes_meses` − 1 meses (3) hasta el fin del mes siguiente. Las anuladas no cuentan.
- Se suman las OV que **solo están en el módulo**, sin duplicar las que también están en SAP.
- Sin una lectura de SAP que cubra el rango, se usan solo las OV del módulo, como antes. La pantalla dice qué fuente usó.

En pantalla:
- Pestañas **Venta y servicio / Órdenes de venta / Órdenes de servicio**.
- Indicadores por clase con lo pedido, lo despachado y la **desviación** en kg.
- El filtro también se aplica al cumplimiento, al PDF y al Excel.

### 1.5 Balance de peso de las órdenes de fabricación de SAP

**Regla de la empresa:** la materia que ingresa (granel o materia prima) debe ser igual en peso al producto (terminado o materia prima, según el proceso) más la merma o desmedro. En kg:

```
insumos (granel + materia prima)  =  producto (completado + rechazado)  +  merma / desmedro
```

**Cuándo se valida:**
- **Al registrar la orden de fabricación:** con lo planificado.
- **Al liquidar:** con lo emitido de cada componente frente a lo completado y rechazado. Se valida cuando la orden está cerrada o ya completó lo planificado; antes, la liquidación puede estar en curso.

**Qué cuenta en el cálculo:**
- **Merma o desmedro:** el componente con cantidad negativa en SAP (subproducto que se recibe), el que esté en `liquidacion_items_merma` o el que diga MERMA o DESMEDRO en su descripción.
- No pesan en el balance: envases, etiquetas, suministros, recursos (horas) y textos.
- Las unidades se pasan a kg con el maestro de artículos del módulo. Si falta el peso de un artículo, se avisa «sin peso».

**Alerta y revisión:**
- Si la diferencia supera `balance_of_tolerancia_pct` (0,5 % de los insumos), se alerta **`BALANCE_OF`** (alta) a la **Jefatura de Operaciones** y a la **Jefatura de Producción**, con los kg de cada lado y la diferencia.
- La misma diferencia no se alerta dos veces.
- Se revisa **solo** con cada sincronización con SAP (`balance_of_automatico`), al traer las liquidaciones y con el botón **«Revisar ahora en SAP»** de la pantalla. La pantalla muestra «No cuadran» y «Todas».

## 2. La simulación (entorno de pruebas) y la base de pruebas de SAP

**Cómo funciona.** La simulación **no usa SAP**, ni la base real ni la de pruebas:
- Genera 14 días de operación ficticia (clientes «CLIENTE SIMULADO», productos «SIM-PT», OV «SIM-OV») dentro de la **base de datos del propio módulo**.
- Pasa esos datos por los mismos servicios del sistema y valida el resultado.
- Mientras está cargada, el módulo **corta toda salida a SAP**, correos y notificaciones.
- «Limpiar datos de prueba» borra solo lo simulado.

**Candados:**
- Solo corre con `SIMULACION_HABILITADA=1` o en modo demostración.
- Se niega si el servidor tiene la escritura en SAP habilitada.
- En el servidor de producción (coprod-one) **no debe habilitarse**: mezclaría datos ficticios con los reales del módulo. El verificador del servidor lo marca como falla.

**Qué es lo «conectado a la base original».** No es la simulación: es la conexión del módulo con SAP (`SAP_SL_COMPANY=SBO_CORPRODUC` en `/etc/operaciones/operaciones.env`). Esa conexión debe seguir así en producción. **No conviene cambiarla** a la base de pruebas en el mismo servidor: la base del módulo ya tiene clientes, artículos y stock de la base real, y se mezclarían con los de pruebas.

**Cómo probar contra la base de pruebas de SAP (ZZZ_CORPRODUC_TEST260826).** Con una **segunda instalación** del módulo, como el servidor de AWS Académico (doc 44, paso 13) u otra instancia pequeña:
1. Instalar con `deploy/instalar_ubuntu.sh` y su propio dominio.
2. En su `operaciones.env`:
   - `SAP_SL_COMPANY=ZZZ_CORPRODUC_TEST260826`;
   - el mismo usuario de integración;
   - `SAP_SYNC_MIN=0` o un intervalo largo.
3. Opcional: `SIMULACION_HABILITADA=1` para usar ahí la simulación.

Ahí sí se pueden probar de punta a punta la creación de OV y guías en SAP. Esa base ya está autorizada en `sap_escritura_empresas`.

Ojo: la simulación se niega si la escritura en SAP está habilitada. En esa instancia se usa la simulación **o** la prueba de escritura en SAP, no las dos a la vez.

Si quieren, preparo el procedimiento paso a paso para esa segunda instancia. Para hacerlo necesito saber qué servidor o dominio usarán: es una decisión de ustedes, por el costo.

## 3. Parámetros nuevos

| Parámetro | Valor | Estado |
|---|---|---|
| `sap_series_orden_servicio` | `[]` | **PENDIENTE:** el código de la serie o series de SAP de las órdenes de servicio (ver `sap-series`) |
| `sap_ordenes_meses` | 3 | PROPUESTO |
| `liquidacion_items_merma` | `[]` | **PENDIENTE:** códigos de los artículos de merma o desmedro, si no tienen cantidad negativa ni la palabra en la descripción |
| `balance_of_tolerancia_pct` | 0,5 | PROPUESTO (0 = cualquier diferencia alerta) |
| `balance_of_automatico` | `true` | DEFINIDO (pedido de la empresa) |
| `sap_ordenes_ultimo`, `sap_balance_of_ultimo` | — | Internos (los escribe el sistema) |

**Alertas nuevas:**
- `OV_NOTA_CREDITO`: Comercial, Almacén, Distribución y Jefatura de Operaciones.
- `BALANCE_OF`: Jefatura de Operaciones y Jefatura de Producción.

## 4. Puntos a confirmar con la empresa

1. **Serie de las órdenes de servicio:** con `sap-series`, indiquen cuál es (su código) y la configuro, o la escriben en `sap_series_orden_servicio`. Hasta entonces todas las órdenes salen como de venta, salvo las de tipo servicio de SAP.
2. **Merma en SAP:** se asumió que la merma o desmedro se registra en la orden de fabricación como subproducto (cantidad negativa) o como un artículo de merma. Si la registran de otra forma, por ejemplo solo en un comentario, envíen una orden de ejemplo y ajusto la lectura.
3. **Factura de reserva:** si la OV se factura completa con factura de reserva, SAP cierra la OV y el pendiente queda en la factura. Confirmen si trabajan así: en ese caso conviene que el módulo no cierre esas OV hasta que salga la guía (hoy las cierra si aún no entraron a preparación).

## 5. Verificación

- `tests/test_v29.py` (8 pruebas):
  - nota de crédito: descuento, reservas, cierre, sin duplicar, carga de OV posterior y pantallas;
  - lectura de notas desde SAP (simulado);
  - clase por serie;
  - conciliación separada;
  - demanda con órdenes abiertas, cerradas y anuladas de SAP más las del módulo;
  - balance de peso (plan, real, en curso, sin duplicar alertas y pantalla);
  - balance leído de SAP (simulado).
- Ajustes a pruebas anteriores: el título de la conciliación (`test_v26`) y la fila de la ejecución, que ahora es un diccionario (`test_v28`).
- Migración 0041 aplicada sobre una base nueva: la base coincide con el código.
- Suite completa: **602 pruebas, todas pasan**.
- Revisión en navegador: notas de crédito, OV con el aviso «NO DESPACHAR», conciliación por clase, demanda y balance de peso.
