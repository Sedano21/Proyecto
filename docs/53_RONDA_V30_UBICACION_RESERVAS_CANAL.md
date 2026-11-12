# Ronda V30 (12-nov-2026): ubicación de lotes, documentos por cliente, clientes sin movimiento, facturas de reserva, indicadores por canal y más

Pruebas con datos ficticios.
- **Lectura de SAP:** facturas de reserva.
- **Escritura en SAP:** nada nuevo.
- **Migración nueva:** **0042**.

## 1. Lo pedido y dónde quedó

| Pedido | Implementación | Dónde |
|---|---|---|
| Almacén: ver por lote la cantidad y su ubicación; la editan Supervisor de Almacén, Jefe de Logística, Líder Operativo y Coordinador de Logística | Ver el punto 1.1. | Almacén → Stock y reservas |
| Expediente por cliente y despachos: ver guías, facturas y notas de crédito por cliente | Ver el punto 1.2. | Expedientes por cliente y despacho |
| Jefe y Coordinador Comercial: clientes sin movimiento ni pedido en 18 meses, para excluir, incluir o editar | Ver el punto 1.3. | Comercial → **Clientes sin movimiento** |
| Cargas de SAP: además de corregir y excluir, **incluir** sin editar, con motivo | Ver el punto 1.4. | Cargas → detalle de la carga |
| Facturas de reserva sin entrega: que las vean las jefaturas y sirvan a la preprogramación con aprobación de Producción | Ver el punto 1.5. | Comercial → **Facturas de reserva sin entrega** |
| Respuesta de la empresa: si hay una factura pendiente de entrega, la OV debe quedar abierta | Ver el punto 1.5. | Carga de OV de SAP |
| OTIF y demás indicadores (venta, margen…) filtrables por canal o en general | Ver el punto 1.6. | Inicio, Nivel de servicio, Cómo va la empresa, Informe comercial |
| Órdenes abiertas vs guías sin tanto desplazamiento: ver primero orden, cliente, compromiso y estado, y desplegar el detalle con + / −; igual en la lista de OV | Ver el punto 1.7. | Órdenes de venta y servicio vs guías; Órdenes de venta |
| Recordar la salida de productos del contenedor de fumigación un día antes y el mismo día | Ver el punto 1.8. | Alerta `FUMIGACION_SALIDA` |
| Respuesta de la empresa: la merma en SAP es el desmedro | Ver el punto 1.9. | Producción → Balance de peso de OF (SAP) |

### 1.1 Ubicación de los lotes

- Nueva columna **Ubicación** en la lista de lotes, junto a la cantidad.
- Pueden **editarla** el Supervisor de Almacén, el Líder Operativo, el Jefe de Logística y el Coordinador de Logística (permiso `stock.ubicacion`). Los demás con acceso al stock la ven, sin editar.
- El buscador acepta la ubicación.
- Cada cambio queda en el historial del lote (de, a, quién y cuándo) y en la auditoría.
- La carga de stock de SAP no la borra.

### 1.2 Guías, facturas y notas de crédito por cliente

- Al filtrar por cliente, y en cada fila, aparece **«Guías y facturas»** o **«Guías, facturas y notas de crédito del cliente»**.
- La pantalla tiene pestañas **Guías / Facturas / Notas de crédito**, con filtro de fechas.
- **Guías:**
  - las de las últimas cargas de entregas de SAP;
  - las guías SUNAT regularizadas;
  - las pre-guías del módulo registradas en SAP.
- **Facturas y notas de crédito:** las de Finanzas → Cobranza, cargadas o traídas de SAP. La nota muestra la factura que afecta.

### 1.3 Clientes sin movimiento

**Quién lo usa:** la Jefatura y la Coordinación Comercial (`clientes.inactivos`).

**Qué cuenta como movimiento:** OV, facturas o notas de crédito y cotizaciones. El historial de ventas no trae el cliente.

**Qué clientes aparecen:** los que no tienen movimiento desde hace más de **18 meses** (`clientes_inactividad_meses`) y los que nunca tuvieron movimiento.

Acciones sobre los clientes marcados:
- **Excluir** (con motivo): el cliente deja de ofrecerse al registrar una OV en el módulo.
- **Incluir (mantener):** sale de la lista y vuelve a revisarse si pasan otros 18 meses sin movimiento.
- **Editar:** abre la ficha del cliente.

Si un cliente excluido vuelve a tener un pedido (por ejemplo, de SAP), queda incluido solo, con nota en su historial.

Pestañas: **Por revisar / Excluidos / Incluidos**.

### 1.4 Incluir filas de una carga, con motivo

- En cada fila, junto a **Excluir**, está **Incluir**. Ambos piden motivo.
- **Fila excluida:** vuelve a la carga.
- **Fila con observaciones:** se acepta **tal como viene, sin editarla**. Sus errores pasan a advertencias con el motivo y quién la incluyó.
- No se puede incluir una fila a la que le falta un dato obligatorio; esa hay que corregirla.
- Si al autorizar la carga un dato no se puede usar, no se guarda nada y se muestra el motivo.

### 1.5 Facturas de reserva sin entrega

**Lectura de SAP:** se leen las facturas de reserva abiertas y no anuladas de los últimos `sap_reservas_dias` (180) días, solo las líneas con saldo por entregar y su OV. Hay dos formas:
- el botón **Traer de SAP**;
- **sola**, con cada sincronización (`sap_reservas_automatico`), antes de las OV.

**Quién las ve:** Jefatura de Logística, Coordinación de Logística, Almacén (supervisión y coordinación), Jefatura de Ventas, Jefatura de Operaciones, Jefatura de Producción y Gerencia de Operaciones.

**Preprogramación de producción:**
- La **Jefatura de Producción aprueba** (o no, con motivo) qué líneas entran.
- Las aprobadas se suman al consolidado de requerimientos y a la preprogramación, con la fuente «Factura de reserva».
- Si su OV ya está abierta en el módulo, el faltante entra por la OV y no se cuenta dos veces.
- La aprobación se conserva cuando se vuelve a leer SAP.

**OV abierta:** si SAP cierra una OV porque se facturó con factura de reserva y aún hay mercadería por entregar, el módulo **no la cierra** ni la marca como diferencia.

### 1.6 Indicadores por canal

Selector **Canal** («General (todos)» o un canal) en:
- **Inicio:** pedidos, OTIF, fill rate, monto, volumen y el nivel de servicio del mes.
- **Seguimiento → Nivel de servicio:** OTIF, on time, in full y fill rate.
- **Cómo va la empresa:** venta del mes, frente a la meta del canal si existe, y OTIF del mes.
- **Informe comercial:** ya tenía canal; ahora también los tiempos de preparación y despacho.

El **margen bruto** y la **gestión comercial** ya filtraban por canal.

**Canal de una OV:** el elegido en la OV o, si no tiene, el del cliente; sin canal es «(sin canal)».

### 1.7 Listas plegables (+ / −)

**Órdenes de venta y servicio vs guías:**
- Una línea por orden: **orden, cliente, compromiso y estado**, con un aviso ⚠ si tiene observaciones.
- El botón **+** despliega debajo el detalle y pasa a **−**:
  - observaciones;
  - productos: solicitado, entregado según SAP, pendiente, nota de crédito y guiado;
  - guías, facturas y órdenes de fabricación.
- Botón **Desplegar todo / Plegar todo**.

**Lista de OV:** igual.
- Se ve OV, cliente, fecha comprometida, estado y cobertura.
- El detalle muestra:
  - cobertura de unidades y líneas;
  - decisión parcial;
  - motivo de detención;
  - productos: solicitado, reservado, preparado, despachado y pendiente.

### 1.8 Recordatorio de salida de fumigación

**Cuándo:** cada día se revisan los lotes en fumigación y las solicitudes de fumigación aprobadas.
- Si la fecha de liberación es **mañana**, se envía un recordatorio.
- Si es **hoy**, se envía otro, de prioridad alta.

**Qué dice:** los lotes, la cantidad, el almacén y el lugar (contenedor o patio), para organizar el retiro, el espacio y la revisión de Calidad.

**A quién:** Jefatura de Logística, Líder Operativo, Gerencia de Operaciones, Supervisión de Almacén, Coordinación de Logística, Supervisión de Calidad y Jefatura de Calidad.

No se repite el mismo día.

### 1.9 El desmedro en el balance de peso

La regla quedó como la indicó la empresa:

```
materia ingresada (granel o materia prima)  +  desmedro  =  producto (terminado o materia prima)
```

- El desmedro es el componente «X - DESMEDRO» de la orden: los prefijos de `prefijos_desmedro_bom` (ME-), como en la lista de materiales.
- Cada cantidad se toma con el signo que tiene en SAP.
- La pantalla muestra «Granel / MP kg», «Desmedro kg» y «Producto kg».
- Se retiró el supuesto de la V29 de tomar la merma con cantidad negativa del lado de la salida.

## 2. Parámetros, permisos y alertas nuevos

| Parámetro | Valor | Estado |
|---|---|---|
| `clientes_inactividad_meses` | 18 | DEFINIDO (pedido de la empresa) |
| `sap_reservas_dias` | 180 | PROPUESTO |
| `sap_reservas_automatico` | `true` | DEFINIDO |
| `sap_reservas_ultimo` | — | Interno |

**Permisos:**
- `stock.ubicacion`: Supervisión de Almacén, Jefatura de Logística, Líder Operativo y Coordinación de Logística.
- `clientes.inactivos`: Jefatura y Coordinación Comercial.
- `facturas_reserva.ver`: las jefaturas indicadas en el punto 1.5.
- `facturas_reserva.aprobar`: Jefatura de Producción.

**Alerta:** `FUMIGACION_SALIDA`.

## 3. Verificación

- `tests/test_v30.py` (10 pruebas):
  - ubicación: quién edita, historial, búsqueda y vista sin edición;
  - documentos del cliente;
  - clientes sin movimiento: excluir, incluir, retorno a los 18 meses, inclusión automática con un pedido y permisos;
  - incluir filas con motivo, también con error;
  - facturas de reserva: lectura simulada, aprobación conservada, preprogramación, OV que no se cierra y permisos;
  - indicadores por canal;
  - listas plegables;
  - recordatorio de fumigación;
  - desmedro en el balance.
- `tests/test_v29.py` ajustado al desmedro de la lista de materiales (ME-).
- Migración 0042 aplicada sobre una base nueva: la base coincide con el código.
- Revisión en navegador:
  - stock con ubicación;
  - lista de OV desplegada;
  - clientes sin movimiento;
  - facturas de reserva.
- Suite completa: **612 pruebas, todas pasan**.
