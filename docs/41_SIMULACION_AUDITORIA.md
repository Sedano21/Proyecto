# 41 · Simulación integral de operaciones: auditoría del módulo y uso del ENTORNO DE PRUEBAS (07-nov-2026)

Prueba integral antes de la puesta en marcha. Se trabajó sobre el módulo existente: misma arquitectura, base de datos,
servicios, reglas y pantallas. No se creó otro módulo. La simulación genera transacciones ficticias **a través de los
mismos servicios** que usan las personas de cada área. Los indicadores se calculan después a partir de esas
transacciones; ningún número se coloca a mano en un tablero.

## 1. Auditoría previa (lo que hay en el sistema)

### 1.1 Arquitectura
- Flask + SQLAlchemy 2 + Jinja. Alembic (cabeza **0037**). SQLite en demostración y PostgreSQL en servidor.
- **117 tablas** (115 propias del negocio y 2 nuevas de la simulación), 95 servicios y 27 grupos de pantallas.
- Permisos por rol (`perm_required`, `has_perm`). Alertas como tareas. Auditoría (`audit_log`) en cada acción.
- Integraciones externas:
  - SAP Service Layer (lectura y escritura de OV y guías, según parámetros);
  - correo (`email_outbox`, solo con SMTP configurado);
  - notificaciones push (web push);
  - lectura pública del tipo de cambio de SUNAT;
  - GEOSATELITAL y mapas (solo lectura).

### 1.2 Estados por proceso (tal como están implementados)

| Proceso | Entidad | Estados |
|---|---|---|
| OV | `sales_orders` | REGISTRADA, EVALUADA, BLOQUEADA, POR_APROBAR, EN_PREPARACION, PREPARADA, PROGRAMADA, DESPACHADA, ENTREGADA, ENTREGA_PARCIAL, DEVUELTA, RECHAZADA, CANCELADA, BORRADOR. Cobertura: COMPLETA, INCOMPLETA, SIN_STOCK, DIFERIDA |
| Reserva | `reservations` | ACTIVA, LIBERADA, CONSUMIDA |
| Lote | `stock_lots` | DISPONIBLE, PENDIENTE_REVISION, OBSERVADO, BLOQUEADO, NO_UTILIZABLE… |
| Picking | `picking_tasks` | PROGRAMADO, EN_PROCESO, LISTO |
| Montacargas | `move_requests` | SOLICITADA, EN_CURSO, COMPLETADA, ANULADA |
| Traslado | `transfers` | SOLICITADO, AUTORIZADO, EN_TRANSITO, RECIBIDO, RECIBIDO_CON_DIFERENCIA, RECHAZADO |
| Solicitud de producción | `production_requests` | BORRADOR, ENVIADA, VALIDADA, RECHAZADA, PROGRAMADA, EN_PROCESO, FINALIZADA, LIQUIDADA |
| Parte de producción | `production_reports` | PROGRAMADO, EN PROCESO, PAUSADO, PENDIENTE (de liquidar), bloqueos y reproceso |
| Liquidación | `liquidations` | REGISTRADA, RECIBIDA_COMPLETA, RECIBIDA_FALTANTE, RECIBIDA_SOBRANTE, BLOQUEADA |
| Ruta | `routes` | PROPUESTA, CONFIRMADA, EN_RUTA, CERRADA, ANULADA |
| Parada | `route_stops` | PENDIENTE, EN_CAMINO, LLEGADA, ENTREGADO, ENTREGA_PARCIAL, NO_ENTREGADO, RECHAZADO, DEVUELTO |
| Checklist vehicular | `vehicle_checklists` | REGISTRADO, VALIDADO, OBSERVADO (momento SALIDA o RETORNO) |
| Conteo físico | `physical_counts` | ABIERTO, POR_VALIDAR, CERRADO |

**Tareas «Pendiente / En ejecución / Completada / Incidencia».** El sistema no tiene una entidad única de tareas con esos
cuatro estados. Cada proceso tiene los suyos:
- picking: PROGRAMADO / EN_PROCESO / LISTO;
- montacargas: SOLICITADA / EN_CURSO / COMPLETADA;
- producción: PROGRAMADA / EN_PROCESO / FINALIZADA.

La «incidencia» se registra como alerta-tarea, parada de línea, incidencia de distribución u observación del picking; no
es un estado de la tarea. La simulación respeta esos estados y no inventa uno nuevo.

### 1.3 Reglas de negocio verificadas

| Regla | Situación |
|---|---|
| PT comprometido solo en los 7 días previos al despacho | **Implementada.** Parámetro `plazo_max_reserva_dias` = 7. La OV queda DIFERIDA y se reserva sola al entrar al plazo (`activate_deferred`); hay alerta si una reserva lo supera. |
| Picking de pedidos grandes como máximo 2 días antes; medianos y pequeños, 1 día | **Parcial.** Se aplica un solo plazo para todos (`dias_picking_antes_despacho` = 1). La clasificación por tamaño depende de `umbrales_tamano_pedido_kg`, que está **PENDIENTE (no definido)**; por eso la regla de 2 días para pedidos grandes no se aplica. `tiempos_preparacion` es solo informativo. **Decisión de negocio pendiente:** definir los límites en kg de pequeño, mediano y grande. |
| Despacho parcial con aprobación (Jefatura de Logística u Operaciones) y saldo reprogramado | Implementada. |
| OV sin opción que cumpla la fecha → decisión de Gerencia General | Implementada (BLOQUEADA → decisión). |
| Capacidad por grupo de líneas y día (media jornada el sábado, no se opera el domingo) | Implementada. |
| Checklist vehicular validado por Seguridad antes de salir; SOAT vigente para asignar la unidad | Implementada. |
| Conformidad de entrega solo por el chofer (nombre, DNI, firma, foto y guía firmada) | Implementada para la entrega completa. En la parcial: ver 1.5. |
| Consumo de materia prima al producir | **Parcial.** La liquidación registra el consumo según la lista de materiales (`sales_history`, origen CONSUMO_PRODUCCION), pero no descuenta los lotes de MP: según el diseño, el stock de materiales se actualiza con la carga de SAP. |
| Diferencias de inventario | El conteo validado no cambia la cantidad del lote (dato SAP): fija la «cantidad verificada», que limita lo reservable. No hay tabla de movimientos (kardex): la trazabilidad se arma con reservas, picking, traslados, liquidaciones, devoluciones y auditoría. |

### 1.4 Tableros, indicadores e informes existentes usados en la validación
- Tablero e indicadores (`kpis.compute`): pendientes, completos/incompletos, OTIF de salida y de entrega, cobertura,
  faltantes, tiempos de preparación y despacho, producción pendiente, diferencias de inventario, incidencias por tipo y merma.
- Nivel de servicio del mes (`seguimiento.service_month`): OTIF, On time e In full con la fórmula V23. La validación lo
  calcula **día por día** para ver la evolución.
- Monitoreo de producción en tiempo real, partes, planeamiento, liquidaciones y tablero OEE.
- Distribución: rutas, checklists, flota e incidencias; cuadro de despacho; seguimiento y desempeño; alertas; centro de informes.

### 1.5 Inconsistencias encontradas

| # | Hallazgo | Tratamiento |
|---|---|---|
| 1 | **Entrega parcial:** las líneas que el cliente sí recibió completas quedaban con «entregado» en 0, ni entregadas ni de vuelta en el almacén. | **Corregido** (`distribution._return_lines`), con prueba automática. |
| 2 | **Cambio de unidad o conductor de una ruta:** se cambiaba solo la columna. En una misma sesión, la ruta seguía apuntando al vehículo anterior y el retorno actualizaba el kilometraje del vehículo equivocado. | **Corregido** (`distribution.update_route` asigna la relación). |
| 3 | La lista de checklists no filtraba por conductor ni por vehículo y mostraba por defecto solo 7 días. | **Agregados** los filtros por conductor y por vehículo. |
| 4 | «Mover parada» deja la ruta de origen vacía como PROPUESTA (no la anula). | Informado; no se modificó. |
| 5 | El indicador «entregas parciales» del tablero cuenta solo las incidencias del subtipo ENTREGA_PARCIAL. Una entrega parcial registrada con otro motivo (p. ej. producto roto) no se cuenta, aunque la OV quede en ENTREGA_PARCIAL. | Informado. |
| 6 | En la entrega parcial no se registra la conformidad del receptor (nombre, DNI, firma): la parada se cierra con la incidencia y la conformidad ya no se acepta («La parada no está en ruta»). | Informado: falta definir el flujo. |
| 7 | La numeración de certificados se calcula contando los existentes del año. Si alguna vez se borra uno, el siguiente número se repite. | Informado. La simulación usa su propia serie «SIM-». |
| 8 | `DEMO_MODE` vale 1 si no se configura. | Riesgo de despliegue: en producción debe fijarse `DEMO_MODE=0`. |
| 9 | Los indicadores del tablero no distinguen el origen de los datos: en un entorno con datos de demostración, suman demostración y simulación. | Informado. Para leer solo la simulación, usar el entorno de pruebas limpio. |

## 2. Cómo funciona la simulación

**Candado de entorno.** Solo se ejecuta con `SIMULACION_HABILITADA=1` o en modo demostración. Se niega si la escritura
en SAP está habilitada. En producción la opción no aparece.

**Datos maestros propios y rotulados:**
- 12 «CLIENTE SIMULADO» (RUC 2099900…, distritos «SIMULACIÓN ZONA …»);
- 6 productos SIM-PT, 2 materias primas SIM-MP y 1 insumo SIM-EN, con precio, costo y lista de materiales;
- 6 camiones SIM-001 a SIM-006 con SOAT y revisión técnica;
- 6 conductores simulados (usuarios `sim.conductorN` que no pueden ingresar);
- existencias iniciales en el almacén principal y en el alternativo.

Las transacciones simuladas nunca reservan, consumen ni modifican existencias reales.

**Numeración aparte.** OV, OC, guías de contingencia y certificados llevan el prefijo «SIM-». Las facturas y guías son
números ficticios (SIM-F001-…, SIM-T001-…): no son comprobantes.

**Sin salidas externas.** Mientras hay una simulación cargada no se envían notificaciones push ni correos, y no hay
conexión a SAP, ni de lectura ni de escritura.

**Reloj simulado.** Cada día se registra con su fecha y hora (por ejemplo, OV entre 08:00 y 10:00, salidas entre 14:00 y
15:00, entregas desde las 16:00). El reloj cambia solo en el hilo de la simulación: el resto del sistema sigue con la
hora real.

**Registro de cada fila.** Cada fila creada queda en `sim_records`. Cada fila existente que cambie guarda sus valores
previos. **Limpieza:** devuelve lo previo y borra solo lo creado, por orden de dependencias, junto con las evidencias
(imágenes rotuladas «SIMULACIÓN»).

**Flujo diario** (días hábiles; el domingo no se opera):
1. Activación de reservas diferidas.
2. Traslados (autorización, salida y recepción, a veces con diferencia).
3. Producción: inicio de lo programado; fin de parte, liquidación, recepción en almacén (a veces con faltante) y
   liberación por Calidad; paradas de línea.
4. 7 a 10 OV del día: pequeñas, medianas y grandes, con 1 a 3 productos y despacho entre 1 y 9 días hábiles.
5. Respuesta a los faltantes: producción, traslado del almacén alternativo, despacho parcial aprobado o decisión de
   Gerencia General; el resto queda pendiente.
6. Picking según la regla vigente: validación del plan, asignación, inicio con foto, lote y cantidad, cierre con foto;
   algunas con diferencia.
7. Movimientos de montacargas.
8. Despacho: consolidación por zona; unidad y conductor simulados; checklist de salida validado por Seguridad; fotos;
   carga contra guía; validación del chofer y del auxiliar; guía, factura ficticia y certificados; documentos; visto
   bueno y salida.
9. Entregas: completas, parciales o fallidas; mercadería que vuelve; checklist de retorno y retorno.
10. Conteo cíclico con diferencias (día 5) y lote infestado observado (día 8).
11. El último día (hoy): líneas trabajando con avance, picking pendiente y en curso, rutas en camino, traslados en
    tránsito y partes programados para mañana.

## 3. Uso

- **Pantalla:** menú «Simulación (entorno de pruebas)» (`/admin/simulacion/`). Sistemas genera, vuelve a validar, vuelve
  a ejecutar y limpia. Gerencias, Jefatura de Operaciones y Jefatura de Logística consultan. Mientras haya datos
  cargados, todas las pantallas muestran el aviso rojo **ENTORNO DE PRUEBAS**.
- **Consola:** `python -m app.cli simulacion generar|validar|estado|limpiar|regenerar [usuario]`.
- **Ver el registro de un conductor:** Distribución → Checklists → filtro «Conductor» (y «Vehículo»), con fecha «Desde»
  al inicio de la simulación.
- **Archivos:** `app/services/simulacion.py` (candados, reloj, registro y limpieza), `app/simulacion_escenario.py`
  (escenario), `app/services/simulacion_validacion.py` (validación integral), `app/views/simulacion.py`,
  `app/templates/simulacion.html`, migración `0037_simulacion.py` y pruebas en `tests/test_simulacion.py`.
