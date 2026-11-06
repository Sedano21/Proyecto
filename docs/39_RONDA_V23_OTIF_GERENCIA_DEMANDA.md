# Ronda V23 (06-nov-2026): OTIF del mes, bandeja de gerencia, devoluciones sin corte, flujo de demostración completo y demanda proyectada

Todo lo de esta ronda usa **datos ficticios**. No se conectó nada a SAP ni a producción.

## 1. Lo pedido y dónde quedó

| Pedido | Implementación | Dónde |
|---|---|---|
| OTIF = OV a tiempo y completas ÷ OV que se subieron y corresponden despacharse en el mes | La base de los tres indicadores es la misma: OV (sin anuladas ni borradores) cuya **fecha comprometida** cae en el periodo. Una OV que aún no sale cuenta en la base y no en el numerador; se informa aparte cuántas siguen dentro de su fecha. | `services/comercial_v23.py` (`nivel`), `seguimiento.service_month`, indicador `OTIF_SALIDA` del inicio, informe de gestión comercial |
| On time = salieron hasta su fecha ÷ OV del mes; In full = salieron completas ÷ OV del mes | Igual que arriba; *In full* se muestra también en «Nivel de servicio del mes». | `/seguimiento/servicio`, `/informes/gestion` |
| Tasa de recompra | Clientes activos (OV en los últimos `recompra_ventana_dias`) que compran dentro de su frecuencia habitual (promedio de días entre sus OV; con una sola OV, `recompra_frecuencia_defecto_dias`; holgura `recompra_tolerancia_pct`). Lista de clientes que no recompraron y tasa por ejecutivo. | Informe de gestión comercial |
| Venta por cliente nuevo y SKU nuevo en clientes existentes | S/ y % de la venta del periodo. | Ídem |
| DSO comercial por ejecutivo | Deuda de sus clientes ÷ venta diaria promedio de los últimos `dso_ventana_dias`. | Ídem |
| Precio realizado vs base por canal y margen de contribución por kg | Descuento efectivo = 1 − venta ÷ venta a precio de lista. El margen por kg (cascada de margen ÷ kg) solo lo ven perfiles con costos. | Ídem |
| Lead time de pedido y tasa de renegociación | Días emisión → entrega (o salida); OV con fecha cambiada o cambio de fecha solicitado ÷ OV del periodo. | Ídem |
| GG recibe Calidad de forma prioritaria; GGA, Compras e Importaciones | Parámetro `alertas_prioritarias_gerencia`; esas alertas les llegan directo (aviso y celular) y van primero. | `services/alerts.py` |
| Gerencias: alertas agrupadas, solo accionables + informativas consolidadas por área | «Bandeja de gerencia»: 1) prioritarias, 2) las que requieren su decisión, 3) informativas **consolidadas por área y tipo** (p. ej. «Sin conexión con SAP: 12»), que no suenan. Perfiles en `perfiles_alertas_consolidadas`. | `/alertas/gerencia`, inicio de GG y GGA |
| Ver usuarios y contraseñas para recorrer los perfiles | Página **solo en modo demostración** con todos los usuarios por área, la contraseña de la demo y botón «Entrar». En producción (`DEMO_MODE=0`) no existe (404). Enlace desde el ingreso. | `/demo/usuarios` |
| No todas las OV bloqueadas ni «falta precio mínimo»; flujo con datos, no en cero | `demo-dia` ahora agrega el **flujo completo** (`app/demo_flujo.py`): precios mínimos para todos los productos y canales, stock suficiente, ~75 días de historial de OV con todos los desenlaces, facturas, OV del mes en cada estado, producción (solicitudes, partes y liquidaciones), proyección de demanda, metas, importaciones y compras, alertas. Solo quedan a propósito una OV con faltante y una con precio bajo el mínimo. | `python -m app.cli demo-dia` |
| Devoluciones sin hora de corte; reportar que no hay personal y dejar en el vehículo | Sin hora de corte ni vencimiento. El chofer, Distribución o Almacén registra «no hay personal para recibir» con motivo (y foto opcional): la devolución pasa a **EN_VEHICULO** y Almacén, Logística y Distribución reciben una alerta que se cierra al recibirla. | `/operacion/devoluciones`, permiso `devoluciones.dejar_en_vehiculo` |
| Analizar la demanda proyectada, su cumplimiento por semana o periodo, materiales, organización de Producción y Distribución, informes para Directorio | Pantalla **Demanda proyectada** con estilo de informe para Gerencia (ver §2), descargable en PDF y Excel. La ven Jefatura de Operaciones, Jefatura Comercial (Jefe de Ventas, Gerente Comercial), Jefe de Administración y Finanzas y Gerencias (`demanda.analisis`). | `/analisis/demanda` |
| Cuadro de rutas como el Excel de Distribución (imagen recibida) | «Formato cuadro de rutas»: encabezado verde con el día y la fecha, bloque por TRANSPORTE (unidad propia, otro trabajador o EXTERNO), CLIENTE, PESO, DIRECCIÓN con «1ER/2DO VIAJE», HR CITA en amarillo; además guía, OV y valor. Excel con el mismo formato. | `/operacion/despacho?vista=cuadro` |
| Embudo adaptado del tablero de prospectos (imagen recibida) | Indicadores arriba (oportunidades, por día, proyectado, cotizaciones, ganadas), oportunidad por producto (con aviso de las que no tienen producto), etapas en embudo, oportunidades por ejecutivo y etapa, tipo de cliente (canal), cliente nuevo o venta adicional, motivo de cierre y oportunidades por día y ejecutivo; cada bloque con su lectura («Mayor …»). | `/operacion/comercial/embudo` |

## 2. Demanda proyectada: fórmulas

- **Proyectado del periodo** = proyección del mes × días del periodo ÷ días del mes (por producto).
- **Cumplimiento** = despachado ÷ proyectado hasta hoy. Los periodos por venir solo muestran el **avance del pedido** (pedido en OV ÷ proyectado).
- **Comparativo**: proyección por tipo (granel, materia prima, producto terminado, marca blanca) vs promedio de 3 meses, mismo mes del año anterior y mes más alto (historial de ventas).
- **Qué necesitamos tener**: explosión de la lista de materiales con stock, llegadas del mes y reserva (`stock_reserva_dias`); faltante por tipo de ítem (granel, materia prima, envase/lámina, suministro/etiqueta) y fecha máxima de pedido según el tiempo de reposición.
- **Producción**: kg asignados por línea vs capacidad real (`capacidad_lineas`). Si una línea no alcanza: primero se propone pasar la producción a otra línea del mismo proceso con holgura; si no, horas extra = kg sin capacidad ÷ (kg/día ÷ `demanda_jornada_horas`). Por encima de `demanda_horas_extra_max_dia` por día se recomienda tercero (maquila) o turno adicional.
- **Distribución**: kg por despachar en lo que queda del mes (lo mayor entre la proyección restante y las OV abiertas) vs flota propia (un viaje diario por unidad con su capacidad real o el peso permitido, o `distribucion_kg_viaje_ref`). Si falta: viajes de tercero de `distribucion_kg_viaje_tercero` kg o días con segundo viaje.
- Mensaje clave, puntos a validar (variaciones fuertes, productos sin lista de materiales, ítems sin plazo de reposición) y próximos pasos.

Los Excel y el PDF que compartieron (requerimiento de noviembre y comparativo de proyección) se usaron **solo como modelo de presentación**. Sus datos son reales y no se copiaron al sistema ni al repositorio.

## 3. Parámetros nuevos (configurables)

| Parámetro | Valor inicial | Estado |
|---|---|---|
| `alertas_prioritarias_gerencia` | GG: Calidad; GGA: Compras, Importaciones | Definido (pedido) |
| `perfiles_alertas_consolidadas` | GG, GGA | Definido |
| `recompra_ventana_dias` / `recompra_frecuencia_defecto_dias` / `recompra_tolerancia_pct` | 365 / 30 / 20 | **Propuesto**: confirmar |
| `dso_ventana_dias` | 90 | **Propuesto** |
| `demanda_jornada_horas` / `demanda_horas_extra_max_dia` | 8 / 2 | **Propuesto** |
| `distribucion_kg_viaje_tercero` / `distribucion_kg_viaje_ref` | 2 000 / {} | **Propuesto** |

`devolucion_hora_corte` (V22) ya no se usa.

## 4. Cómo revisar

1. Recrear la demostración en el servidor de pruebas (SQLite local): `python -m app.cli reset-demo` y luego `python -m app.cli demo-dia`.
2. Abrir el ingreso → «Ver todos los usuarios y contraseñas de la demostración» → «Entrar» en cada perfil.
3. Recorrido sugerido:
   - **gerente.general**: inicio (indicadores por área y bandeja: Calidad prioritaria, SAP consolidado), Bandeja de gerencia, Demanda proyectada (mes actual y siguiente: el siguiente está proyectado alto a propósito para ver horas extra, tercero y compras), Informe de gestión comercial.
   - **gerente.adjunto**: bandeja con Compras e Importaciones prioritarias.
   - **jefe.ventas / gerente.comercial**: informe de gestión (OTIF del mes e indicadores nuevos), Embudo comercial, Demanda proyectada.
   - **jefe.finanzas**: Demanda proyectada (informe para Directorio), gastos por área.
   - **jefe.operaciones**: Demanda proyectada, Nivel de servicio del mes.
   - **coord.distribucion**: Cuadro de despacho → «Formato cuadro de rutas» y su Excel.
   - **conductor1** y **coord.almacen**: Devoluciones → «No hay personal para recibir» → luego recibirla.

## 5. Límites y pendientes

- El historial ficticio se registra con su resultado final (no pasa por cada pantalla de picking, guía y salida). Lo de hoy sí se opera desde las pantallas.
- El OTIF del mes en curso incluye las OV que aún no salen (así lo indica la fórmula); por eso es bajo al inicio del mes. La pantalla muestra cuántas siguen en plazo.
- La comparación con el mismo mes del año anterior depende de que el historial de ventas esté cargado (en la demo hay ~75 días, por eso sale «—»).
- Los parámetros marcados «Propuesto» necesitan su confirmación.
