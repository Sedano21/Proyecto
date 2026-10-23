# Ronda del 23-oct-2026: Producción, Comercial y Finanzas

Fuentes: reunión con Producción y su control de producción 2026; reunión con Comercial; modelo OEE de Producción; archivo de
ventas y margen 2026; formato del reporte diario de Producción; respuestas del usuario del 23-oct. Todo entra antes de la
marcha blanca (sin fases). Los factores y valores son parámetros editables; ninguno usa datos reales de clientes.

## 1. Decisiones aplicadas

| # | Decisión del usuario | Dónde |
|---|---|---|
| 1 | Todo se implementa ahora, sin fases | Este documento |
| 2 | La OV cargada desde SAP no pide OC; la registrada en el módulo sin OC queda como **borrador** y no se ejecuta | `orders.create_order`, `orders.attach_oc` |
| 3 | El balance de masa fuera de rango **bloquea** la liquidación hasta corregirla y alerta al Jefe de Producción | `production.liquidation_checks`, `correct_liquidation` |
| 4 | Pueden aprobar sus propias solicitudes: Jefe Comercial, Jefe de Producción y Jefe de Logística | parámetro `roles_autoaprobacion` |
| 5 | Coordinación de Finanzas: aprueba condiciones de pago, carga facturas (Excel/PDF/SAP), actualiza estados de pago; Comercial sube comprobantes y se notifica a Finanzas; todo en el archivo del cliente; cuadro de vencidas y guía del proceso | rol `COORD_FINANZAS`, `services/finance.py`, Finanzas → Cobranza |
| 6 | Gastos y rebates por canal y por cliente, configurables por el Jefe Comercial | Comercial → Configuración comercial (`margen_config`) |
| 7 | Una hora antes del fin del turno se revisan las tareas abiertas; al día siguiente se muestran primero con su tiempo de atención | `minutos_antes_fin_turno_por_area`, Inicio |
| — | Asistente de Producción 1: además ve y aprueba todo lo del Jefe y registra asistencia | `produccion_alcance_usuarios` («permisos_de») |
| — | Desviación en selección (Cimbria, Truer) = % rendimiento + % desmedro − 100 | `parte.compute` |
| — | Lista de causas de parada de selección enviada por Producción | `causas_parada.SELECCION` |
| — | Plazos, horarios y escalamiento configurables en el panel | Configuración de alertas |
| — | Datos (velocidades, objetivos, incentivos, GS1, fotos, facturas, despachos) se cargan o configuran en el sistema | Configuración de Producción, Configuración comercial, Finanzas, Catálogo |

## 2. Comercial

- **Unidad fija por prefijo** (`um_por_prefijo`): MP, GR, SER en kilos; PT, AB, MQ en unidades. El granel en kilos puede venderse por saco.
- **Orden de compra**: archivo adjunto (PDF, imagen, Excel o correo). Sin OC la OV queda en `BORRADOR` (no reserva ni se evalúa); al adjuntarla se registra, se valida el precio y se evalúa. Las muestras no la piden.
- **Corte de las 12:00** (`hora_corte_ov_dia_siguiente`): después de esa hora no se registra ni se reprograma una OV para el día siguiente.
- **Importes en S/** en las validaciones de precio y costo.
- **Compromiso de Operaciones**: con stock completo el sistema responde «Cumple»; si no, Almacén, Logística o Producción responden CUMPLE / NO CUMPLE (con motivo y fecha estimada) dentro de `plazo_respuesta_cumplimiento_horas` (24 h). NO CUMPLE alerta a Comercial y al vendedor; sin respuesta en el plazo se alerta a Operaciones y Comercial.
- **Cambio de fecha pedido por Logística o Distribución**: solicitud que aprueba Comercial.
- **Expediente**: orden de compra, constancia de devolución, nota de crédito y otros documentos; facturas y notas de crédito de Finanzas; solicitud de nota de crédito.
- **Ficha del cliente**: ubigeo (cliente y lugares de entrega; obligatorio en los nuevos), condición de pago, estado de cuenta y deuda, pedido vs atendido vs facturado (S/ y kg), OV canceladas, oportunidades, acciones y cotizaciones.
- **Prospectos**: el cliente creado en el módulo empieza como prospecto y sin condición de pago; solo admite OV de muestra hasta pasar a cliente (al menos una acción y su orden de compra) y tener la condición aprobada por Finanzas. Los clientes existentes y los cargados desde SAP quedan con la condición aprobada.
- **Venta real**: los informes cuentan las OV abiertas y cerradas; las canceladas van aparte con su motivo; los borradores no se cuentan. Filtros por canal, cliente, vendedor y tipo (granel / envasado); productos más vendidos en S/ y en kg; ticket promedio por cliente; tiempos de preparación y despacho.
- **Margen** (Comercial → Margen): cascada del archivo de ventas y margen por canal, cliente, vendedor o mes, base facturado o venta real; exportable a Excel.
- **Objetivos de venta** general, por canal y por vendedor, mensuales; avance contra lo facturado y la venta real, por semana.
- **Incentivos**: reglas por canal y vendedor (base venta, margen bruto o margen de contribución; %; cumplimiento mínimo del objetivo; tope; vigencia). Sin reglas no hay incentivo.
- **Precios de mercado**: los registra cada vendedor y quedan pendientes; solo el Jefe Comercial los aprueba y recién entran al análisis.
- **Oportunidades**: acciones con el cliente (tipos configurables), oportunidades, cotizaciones imprimibles, funnel y desempeño por vendedor.
- **Catálogo con fotos**: carga múltiple nombrando cada foto con el código del producto.

## 3. Finanzas

Rol nuevo **Coordinación de Finanzas** (usuario demo `coord.finanzas`).
- Condición de pago: contado (sin documentos) o crédito con los documentos del tramo (`credito_tramos`: hasta S/ 30 000 a 30 días; hasta S/ 100 000 a 60 días; más de S/ 100 000 a 60 días; 90 o 120 días piden todos). Finanzas aprueba, observa o rechaza.
- Facturas y notas de crédito: Excel (encabezados reconocidos: número, tipo, RUC o cliente, OV, fecha, vencimiento, moneda, monto, saldo, referencia), PDF individual o consolidado (se indican los números), o registro manual. La nota de crédito descuenta el saldo de su factura.
- Pagos: Comercial sube el comprobante (alerta a Finanzas); Finanzas confirma (descuenta el saldo) u observa.
- Cuadro de cobranza: vencidas por antigüedad, por vencer, deuda por cliente, pagos por confirmar, condiciones por aprobar y la guía del proceso. La factura vencida alerta a Finanzas y al vendedor una vez.

## 4. Producción

- **Parte en línea**: iniciar (línea, máquina, turno, producto, EAN escaneado, lote y vencimiento de MP, peso por saco × sacos + saldo, presentación, unidades por paquete); pausar con causa de la lista y foto opcional; reanudar; finalizar con operarios, pallets por destino, unidades sueltas, defectos por causa y colaboradores (inicio, fin, refrigerio, kg).
- **Cálculos**: total de unidades, % rendimiento, desmedro, peso promedio, desviación de peso y kg entregados de más, horas, horas efectivas, horas-hombre, velocidad (und/min o kg/h), desviación de selección y **OEE** con el modelo de Producción (TD, TP, CP, PR, PB; disponibilidad × rendimiento × calidad; calificación y plan de acción).
- **EAN**: se compara con la tabla GS1 ↔ SAP (Configuración de Producción → cargar Excel). `ean_validacion`: ALERTAR o BLOQUEAR.
- **Estados** (lista cerrada): programado, en proceso, pausado, pendiente, liquidado, liquidación externa pendiente / liquidada, reproceso, reenvasado, bloqueado, anulado. Calidad bloquea y libera (fumigación o reproceso).
- **Liquidación**: horas y operarios obligatorios en la manual; se bloquea si las horas pasan de `tope_horas_of` (150) o el rendimiento está fuera de `tolerancia_rendimiento` (por línea y presentación; mínimos tomados del rendimiento que solo el 10 % de los partes ene–oct no alcanza; máximo 100.5 %). La corrección con motivo la libera.
- **Alcance**: cada asistente ve sus líneas (`produccion_alcance_usuarios`); el asistente 1 tiene el perfil adicional del Jefe y registra asistencia. Los cambios al programa de un asistente sin ese perfil quedan pendientes de validación. Los asistentes modifican la receta (aviso informativo al Jefe); solo el Jefe cambia el código de un componente, con motivo.
- **Almacenes de Producción** (`almacenes_produccion`, por configurar): si se definen, la validación de materiales usa solo esos almacenes y propone traslados.
- **Asistencia** del personal (asistencia, falta, vacaciones, descanso médico, tardanza) y **productividad por persona**.
- **Control de producción** (formato enviado por Producción): diario, semanal o mensual; producción total real, plan, cumplimiento, horas efectivas, productividad; desempeño por proceso y línea (capacidad teórica, plan, real, % cumplimiento, horas, kg/h); gráficos plan vs real, kg y kg/h por línea; asistencia; hallazgos, situación operativa y acciones. Sin plan registrado para una línea se compara con su capacidad del periodo (se marca con *).
- **Tablero OEE**: OEE y sus factores por año/mes (rango), turno, línea y máquina; Pareto de tiempo muerto y defectos; % merma por línea; semana por línea y producto.

## 5. Plazos, horarios y escalamiento (Configuración de alertas)

- Plazo de atención por área y urgencia (Producción 10 min) con aviso al jefe.
- Minutos antes del fin del turno para revisar tareas abiertas, general o por área (60 min).
- Al día siguiente, «Pendientes de días anteriores» en Inicio con horas abiertas, plazo y el indicador de 30 días (% a tiempo y atención promedio).
- Verificaciones automáticas: compromiso CUMPLE / NO CUMPLE vencido, facturas vencidas, cierre de turno.

## 6. «Arma tu informe»

Fuentes por área (Comercial, Finanzas, Almacén, Producción, Calidad, Compras, Distribución, General), cada una con todas sus
columnas; se elige qué mostrar: indicadores, gráfico (barras, columnas o líneas, con su medida), tabla y recomendaciones
automáticas. Al agrupar, los porcentajes se promedian y el resto se suma. PDF y Excel incluyen indicadores y recomendaciones.

## 7. Pendiente de datos o confirmación

1. Velocidad nominal de las líneas de selección (kg/h) y por presentación en envasado (sin ella no se calcula el OEE de esa línea).
2. Códigos SAP de los almacenes propios de Producción.
3. Tabla GS1 ↔ SAP, fotos del catálogo, objetivos de venta, reglas de incentivo, tasas por cliente: se cargan en el sistema.
4. Encabezados de la exportación de despachos de SAP (la carga acepta Excel; la conexión directa con SAP no está implementada).
5. Usuarios reales en `produccion_alcance_usuarios` (hoy con los usuarios demo).
