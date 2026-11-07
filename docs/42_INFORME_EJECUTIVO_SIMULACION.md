# 42 · Informe ejecutivo: simulación de 14 días de operación (ENTORNO DE PRUEBAS)

**Fecha:** 07-nov-2026 · **Escenario:** 25-oct al 07-nov-2026, 12 días hábiles · **Base:** demostración, sin datos reales.

## 1. Conclusión
El módulo procesó 14 días de operación completos, de la OV a la entrega, **sin una sola falla de programa**. La
información queda conectada entre áreas. Los 18 controles de integridad pasaron y las 30 pantallas revisadas
respondieron con los datos simulados.

Se encontraron y **corrigieron 2 defectos**, con su prueba automática:
- en una entrega parcial, las líneas recibidas completas quedaban sin entregar;
- al cambiar la unidad de una ruta, el retorno podía actualizar el kilometraje del vehículo anterior.

Quedan **6 observaciones** y **2 decisiones de negocio** pendientes (sección 5). No se recomienda pasar a producción
hasta resolver al menos las de prioridad alta.

Esta prueba se hizo en el entorno de pruebas. **No reemplaza** la marcha blanca con usuarios reales ni la prueba sobre
PostgreSQL con la conexión SAP del servidor.

## 2. Qué se generó (transacciones reales dentro de la base, procesadas por los servicios)

| Área | Resultado de la corrida |
|---|---|
| Comercial | 102 OV registradas (57 pequeñas, 34 medianas, 11 grandes), más saldos reprogramados: 104 OV en total. Decisiones de Gerencia General para OV sin opción de fecha. |
| Almacén | 53 pedidos preparados. Picking: 53 listos, 6 en preparación y 15 pendientes; 6 con diferencia de cantidad. 8 traslados (3 en tránsito hoy). Conteo cíclico con diferencias validado. 1 lote infestado observado. 33 movimientos de montacargas completados y 2 pendientes. |
| Producción | 16 solicitudes por faltante: validadas, programadas por capacidad de línea, iniciadas, con parte, liquidación, recepción en almacén y liberación por Calidad. Planificado 1 367 und / producido 1 274 und (93 %). Paradas de línea. **Hoy hay 6 partes en curso**, 3 de ellos con avance registrado por pallet. |
| Distribución | 26 salidas de vehículos con checklist de salida validado por Seguridad, 24 checklists de retorno. 39 entregas completas, 5 parciales y 4 fallidas (cliente ausente), con su mercadería de vuelta. |
| Indicadores (fórmula del sistema) | OTIF del periodo 67,1 % · On time 74,1 % · In full 76,5 % · OTIF de salida (tablero) 80,3 % · tiempo de preparación 1,3 h. |

Evolución diaria del OTIF: entre 63 % y 100 % en los días cerrados. Baja a 30–39 % en los dos últimos días porque esos
pedidos siguen en ruta o en picking. Se ve igual que en la operación real a media jornada.

## 3. Funcionalidades verificadas
- OV con trazabilidad completa: cliente, líneas, reserva, picking, ruta, guía, factura ficticia, certificado y entrega.
- Plazo de reserva de 7 días (OV diferidas que se reservan solas al entrar al plazo).
- Faltantes atendidos por producción, por traslado o por despacho parcial aprobado, con saldo reprogramado.
- Producción conectada con almacén:
  - liquidación → tránsito → recepción → liberación por Calidad → stock disponible → reevaluación de OV;
  - capacidad por línea y día.
- Picking con fotos, lote y cantidad; no se cierra si el pedido está incompleto.
- Despacho:
  - ninguna unidad propia sale sin checklist validado;
  - el SOAT es obligatorio para asignar la unidad;
  - carga contra guía, vistos buenos y documentos.
- Registro de checklists por conductor y por vehículo (filtros agregados en esta ronda).
- Devoluciones que reingresan como «pendiente de revisión».
- Inventario sin negativos; lo comprometido nunca supera la existencia; el balance cuadra
  (inicial + producido + devuelto − despachado − en tránsito).
- Filtros por fecha; pantallas de OV, stock, picking, traslados, conteos, montacargas, producción (monitoreo, partes,
  plan, liquidaciones, OEE), distribución, checklists, flota, incidencias, seguimiento, alertas e informes.

## 4. Protección de la información real (verificado)
- La simulación solo corre con `SIMULACION_HABILITADA=1` o en modo demostración, y se niega si SAP tiene la escritura
  habilitada.
- Usa datos maestros propios y rotulados (clientes, productos, lotes, vehículos y conductores «SIM»). La numeración es
  aparte (SIM-OV, SIM-CP, SIM-GS) y no consume correlativos reales.
- Mientras está cargada no salen notificaciones push ni correos, y no hay conexión a SAP.
- **Prueba de limpieza:** se tomó la huella de cada tabla antes de generar y después de limpiar. El resultado es
  **idéntico**, con 0 registros existentes modificados. Solo quedan 2 filas en la auditoría («simulación generada» y
  «simulación limpiada») y el historial de la corrida.

## 5. Pendientes y riesgos antes de producción

| Prioridad | Tema | Recomendación |
|---|---|---|
| **Alta** | Regla de picking de pedidos grandes (2 días antes): no se aplica porque no están definidos los kg de pequeño, mediano y grande. | **Decisión de negocio:** definir los umbrales; luego aplicar la regla por tamaño en la programación del picking. |
| **Alta** | `DEMO_MODE` vale 1 si no se configura. | En producción fijar `DEMO_MODE=0` y no definir `SIMULACION_HABILITADA`. |
| **Alta** | Entrega parcial sin conformidad del receptor (nombre, DNI, firma). | **Decisión de negocio:** ¿se exige la conformidad también en la entrega parcial? Si sí, ajustar el flujo. |
| Media | El indicador «entregas parciales» cuenta solo el subtipo ENTREGA_PARCIAL. | Contar por el resultado de la entrega (`entrega = PARCIAL`). |
| Media | La numeración de certificados cuenta los existentes del año: si se borra uno, el número se repite. | Usar el máximo correlativo (como en OV y guías). |
| Media | No hay tabla de movimientos (kardex) y el consumo de materia prima no descuenta lotes (depende de la carga SAP). | Confirmar que la carga diaria de stock SAP será la fuente oficial; si no, implementar el kardex. |
| Baja | «Mover parada» deja rutas vacías en estado propuesta. | Anular automáticamente la ruta que queda vacía. |
| Baja | Los indicadores del tablero no separan demostración y simulación. | Hacer la prueba final en un entorno de pruebas limpio, sin datos de demostración. |

**Otros riesgos:**
- La prueba se hizo con SQLite. Falta repetirla en PostgreSQL con varios usuarios a la vez y con la carga SAP real.
- Las tareas no tienen un estado «Incidencia» común: cada proceso registra sus incidencias a su manera (alerta-tarea,
  parada, incidencia de distribución).

## 6. Cómo revisarlo
Menú «Simulación (entorno de pruebas)» → Generar. Luego recorrer los módulos:
- Órdenes de venta: OV «SIM-OV-…».
- Producción → Monitoreo: líneas trabajando ahora.
- Preparación (picking): pendientes y en curso.
- Distribución → Rutas.
- Distribución → Checklists, con el filtro por «Conductor simulado».
- Seguimiento → Nivel de servicio.

Al terminar: **Limpiar datos de prueba**. El detalle técnico está en `docs/41_SIMULACION_AUDITORIA.md`.
