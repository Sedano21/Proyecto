# Especificación consolidada

Fuente principal: **Informe Funcional del Módulo de Operaciones v1.0 (9-oct-2026)** — citado como *IF §n*.
Fuentes complementarias: diagrama AS-IS L5, formatos REG-*, Excel operativos y PDF (ver `01_INVENTARIO_FUENTES.md`).
El catálogo completo de requerimientos, con su fuente, implementación, prueba y estado, está en
**`03_MATRIZ_TRAZABILIDAD.md`** (fuente única para no duplicar).

Clasificación usada (la misma del IF): **Definido** (regla expresa) · **Propuesto** (organización que requiere validación) ·
**Pendiente** (decisión no tomada; se deja configurable/inactiva) · **AS-IS** (valor observado en archivos actuales, no aprobado).

## 1. Alcance consolidado por proceso

| Proceso | Qué hace el sistema (TO-BE, IF) | Qué decide una persona |
|---|---|---|
| OV (IF §5) | Registra/importa OV; al crear o modificar evalúa stock, reserva y calcula cobertura (unidades y líneas); prioriza por fecha comprometida, completitud y urgencia | Asistente modifica solo con autorización; Coord./Jefe de Ventas cancelan; Comercial + GO renegocian |
| Stock (IF §6) | 6 estados (Disponible, Reservado, No utilizable, Dañado, En fumigación, Pendiente de revisión; sin "Observado"); reserva solo stock físico verificado y utilizable del almacén principal; lote/vencimiento (FEFO); carga SAP con validación previa; conteos y diferencias | Quien carga corrige y autoriza; Calidad libera |
| Faltantes (IF §4.4, §6.2-6.3) | Reserva lo disponible, alerta, presenta alternativas: otros almacenes (767, Trujillo 1/2, Isabelita), reempaque, producción (BOM), compra | Logística decide alternativos; Jefatura de Logística autoriza traslado; Jefatura Log./GO/Comercial deciden despacho parcial |
| Reposición y compras (IF §7, §10) | Plazos por categoría en días naturales (+ campaña canastería), margen configurable, análisis (salidas, consumo, stock, reservado, OV pendientes, en camino) → alerta, cantidad sugerida, fecha de necesidad y solicitud preliminar; flujo cotización → muestra → (GO si mayor volumen) → OC → recepción | Almacén origina; Compras cotiza y genera OC; Calidad aprueba muestra; GO autoriza recepción bajo observaciones |
| Producción (IF §8) | Carga BOM Excel validada y versionada; cálculo proporcional con merma configurable sin doble conteo; solicitud preliminar; programación por línea con capacidad; inicio/fin; liquidación (manual/Excel/SAP) → alerta montacarguista; recepción de PT con cruce | Almacén revisa y envía; Producción valida lista, disponibilidad real, capacidad y plazo |
| Reempaque (IF §9) | 3 tipos; producto seleccionado queda Pendiente de revisión; notificaciones | Almacén inicia, Calidad aprueba, Producción ejecuta |
| Calidad (IF §9.3-9.4) | Formatos REG-* digitalizados con evaluación automática por límites documentados; liberación; fumigación con cambio de estado; certificados autogenerados | Supervisor/Jefatura revisan, corrigen y aprueban certificados |
| Importaciones (IF §11) | Fases configurables, fechas, recordatorios, alerta de fase vencida, cambios de llegada | Importaciones actualiza; Almacén y Calidad reciben |
| Distribución (IF §12) | Propuesta de rutas (zona/distrito, capacidad, cita, prioridad, terceros), verificación de salida (5 controles), validación de Seguridad carga vs guía, avance de ruta, entrega con foto + guía firmada, incidencias con destinatarios definidos | Coord. Distribución ajusta y confirma salida; Seguridad valida |
| Alertas (IF §14) | Panel + correo; asignar, en atención, comentar, cerrar con motivo/acción; GG agrupa por área/tipo/urgencia y elige cuáles recibe; destinatarios configurables por alerta/rol/usuario | Responsables atienden |
| Gerencia (IF §17) | Indicadores: pendientes completos/incompletos, OTIF, cobertura, detenidos y motivo, tiempos, compras/producción pendientes, diferencias, incidencias, merma prevista vs real, monto y volumen | — |

## 2. Contradicciones y diferencias detectadas

| # | Diferencia | Fuentes | Tratamiento en el prototipo | ¿Requiere su decisión? |
|---|---|---|---|---|
| K1 | Ext-005/Ext-010 se llaman "Trujillo 1/2" en el IF y "Atsac 1/2" en el Excel de rotación | IF §6.2 vs `stock almacenes` | Se usa el nombre del IF y se anota el alias | No (confirmar nombre) |
| K2 | IF: 1524 (=EXT-002) es el almacén de MP/granel/insumos; pero la BOM real ubica la MP en **ALM-003** y suministros en ALM-005/007/012, y el stock real tiene MP en ALM-003/ALM-010 | IF §6.2 vs BOM y STOCK_LOTE | Reserva de OV de MP/GR solo en 1524 (regla IF). El cálculo de materiales usa el almacén que indica la BOM. Almacenes no documentados se crean como "OTRO" (no reservables) | **Sí – Q5** |
| K3 | 1560 (ALM-001) es de PT, pero la BOM consume láminas EN- desde ALM-001 y el inventario de bobinas se titula "1524" | BOM vs Inven. bobinas | Igual que K2: la BOM manda para materiales | Incluido en Q5 |
| K4 | OTIF: IF lo comunica como "pedidos que salieron a tiempo"; el Excel SAP `Qy - OTIF` usa fecha de **entrega** y da crédito parcial (OTIF = % entregado si llegó a tiempo pero incompleto) | IF §17 vs Rotación de inventario | Se calculan y muestran dos variantes (salida y entrega, ambas "completo y a tiempo"); parámetro `otif_definicion` | **Sí – Q2** |
| K5 | Autorización sanitaria "MIDAGRI" vs "MINAGRI" | Certificados MP276 vs PT3756 | Parámetro editable (PENDIENTE) | No (confirmar texto) |
| K6 | Criterio de peso de 50 kg ilegible/inconsistente ("50.08 kg < 5.0 Kg > 5.010 kg") | REG-CAL-003 | Se evalúan 250 g, 500 g y 5 kg; 50 kg se informa como sin criterio | No (Calidad confirma) |
| K7 | IF: margen de seguridad "no fijado, configurable"; Excel actual aplica 30 % del consumo mensual y promedio de 15 días | IF §7 vs Reporte/PROM_15D | 15 días como período por defecto (AS-IS); 30 % cargado pero **desactivado** | Valor en Q7 |
| K8 | "Acceso completo" de Sistemas y GG vs aprobaciones críticas | IF §15 | Tienen todos los permisos, pero ningún paso de aprobación se omite y todo se audita | **Sí – Q4** |
| K9 | Despacho parcial: §4.5 dice que Comercial y GO "participan" en aprobarlo; §6.3 alerta a Jefatura de Logística, GO y Comercial "para decidir" | IF §4.5, §6.3 | Cualquiera de esos roles puede registrar la decisión (con usuario, comentario y fecha) | **Sí – Q3** (¿un aprobador o aprobación conjunta?) |
| K10 | Liquidaciones SAP reales con el mismo documento en dos lotes y la misma cantidad | Recep. pt / Dat.Prod | Clave documento + lote; advertencia de verificar si la cantidad se repite por lote | **Sí – Q9** |
| K11 | OV SAP reales con el mismo producto en varias líneas | OVS | Se consolidan las cantidades por producto al importar (advertencia) | No |
| K12 | La exportación OVS no trae precio; el monto de OV solo existe en `Qy - OTIF` | IF §17 vs OVS | Precio unitario opcional en OV/importación; si no viene, el monto es 0 | Indicar fuente de montos (Q11) |
| K13 | "Fecha comprometida de despacho" no aparece con ese nombre en SAP | IF §5 vs OVS | Se interpreta como "Fecha de Vencimiento" de la OV (es la que usan las tablas de seguimiento y OTIF actuales) | Confirmar (Q11) |
| K14 | No se recibió documentación TO-BE separada pese a mencionarse | Solicitud vs archivos | TO-BE = flujo del IF §4-§14 | **Sí – Q1** |

## 3. Vacíos (información pendiente según el propio IF §20) y cómo quedan

Todos se dejan **configurables y explícitos**, sin convertir supuestos en reglas: margen de reposición, umbral de compra de
mayor volumen y rol de GO, merma (y si el Excel la incluye: se pregunta al cargar cada versión), excepciones a la
proporcionalidad, criterios de conversión de calidad/SKU/lote en reempaque, OTIF, matriz final de alertas, permisos y
"acceso completo", tiempos por etapa, regla de bloqueo por discrepancia carga/guía, fases de importación y responsables,
capacidades de líneas, formato de recepción bajo observaciones, horarios de corte, umbral de vencimiento próximo, tiempo
máximo de almacenamiento por producto, estado de lotes nuevos en cargas SAP posteriores a la base inicial.

## 4. Dependencias entre procesos

OV → evaluación de stock (requiere carga SAP autorizada y almacenes configurados) → faltante → {traslado | reempaque →
Calidad → Producción | solicitud de producción (requiere BOM cargada) | compra} → reevaluación automática por prioridad
cuando ingresa stock (carga, traslado, liberación de Calidad) → preparación (cortes) → certificados → programación de rutas
(requiere flota y pesos por artículo) → Seguridad → salida (descarga stock) → entrega con evidencia / incidencias → KPI.

## 5. Decisiones técnicas tomadas (justificadas, reversibles)

1. **Aplicación web** Python/Flask + SQLAlchemy, servidor único, sin dependencias de nube; SQLite para el prototipo y
   PostgreSQL/SQL Server para producción (misma capa ORM).
2. **Reservado** se deriva de las reservas activas (no es un estado físico) para que un lote pueda estar parcialmente reservado.
3. Un mismo lote SAP puede tener **segmentos por estado** (p.ej. parte devuelta "Pendiente de revisión"); la carga SAP
   asigna al segmento Disponible el total SAP menos los otros segmentos.
4. Las cargas SAP de stock reemplazan el saldo **solo en los almacenes incluidos en el archivo**.
5. Una carga autorizada marca los lotes como verificados; un conteo físico con menor cantidad limita lo reservable sin
   alterar el dato SAP.
6. Componentes BOM con prefijo **RE-** (mano de obra / costo CIF) no se verifican contra stock (parámetro).
7. Producto devuelto/rechazado reingresa como **Pendiente de revisión** para decisión de Calidad (propuesto).
8. Fin de fumigación deja el lote **Pendiente de revisión** (requiere liberación).
9. Alertas con **deduplicación** de condiciones repetidas y cierre automático cuando la condición desaparece.
10. Correo: si no hay SMTP, el mensaje queda en bandeja con estado SIN_SMTP; **no se simula** el envío.
11. Rutas: una salida por unidad y día en la propuesta (la AS-IS muestra "primer viaje"; múltiples viajes quedan como mejora).

## 6. Preguntas para su decisión

Solo se listan decisiones de negocio que afectan reglas; el desarrollo continuó con los valores configurables indicados.

- ~~**Q1.**~~ **Respondida (11-oct-2026):** se recibió el TO-BE L5 (pedidos y despachos). Ver `10_ANALISIS_TO_BE.md`.
- **Q2.** OTIF: ¿salida completa a tiempo, entrega completa a tiempo en destino, o la fórmula SAP actual con crédito parcial?
- ~~**Q3.**~~ **Respondida (11-oct-2026):** el parcial lo aprueban Gerencia de Operaciones y Jefatura de Logística; lo que falta despachar se reprograma. Implementado como aprobación de ambos (parámetro `parcial_aprobadores`) y OV de saldo `<OV>-S1` con fecha reprogramada al confirmar la salida.
- ~~**Q4.**~~ **Respondida (11-oct-2026):** Gerencia General tiene acceso completo y puede aprobar (queda registrado "en nombre de"); Sistemas tiene acceso a todo pero **no** aprueba. Implementado: Sistemas recibe todos los permisos salvo los de tipo aprobación.
- **Q5.** Mapeo de almacenes SAP: ¿qué uso tienen ALM-002/003/004/005/006/007/010/012, EXT-007/013 y PRO-*? ¿Cuáles son reservables para MP/insumos?
- **Q6.** En cargas SAP posteriores a la base inicial, ¿un lote nuevo entra Disponible o Pendiente de revisión?
- **Q7.** Valores para: margen de reposición, umbral de mayor volumen, merma por defecto y umbral de alerta, horarios de corte, días de "vencimiento próximo", tiempos máximos de almacenamiento por producto.
- **Q8.** ¿Una discrepancia carga vs guía bloquea la salida o solo alerta? ¿Con qué tolerancia?
- **Q9.** En la liquidación SAP, ¿la clave es documento+lote y la cantidad se repite por lote o debe repartirse?
- **Q10.** Fases de importación definitivas y responsable por hito.
- **Q11.** Fuente oficial de precios/montos y confirmación de que "Fecha de Vencimiento" de la OV es la fecha comprometida de despacho.

Nuevas preguntas surgidas del TO-BE (detalle en `10_ANALISIS_TO_BE.md` §4):

- **Q12.** Reempaque: ¿lo inicia Almacén (IF §9.1) o el sistema lo remite a Calidad tras analizar el stock (TO-BE)?
- **Q13.** Traslado: ¿lo aprueba la Jefatura de Logística (IF) o el Coordinador de almacén (TO-BE)?
- **Q14.** Compra: ¿Logística aprueba la pre-solicitud antes de Compras (TO-BE) o pasa directo (IF)?
- **Q15.** Pre-solicitudes automáticas: si hay varias opciones viables, ¿cuál genera el sistema?
- **Q16.** Salida: ¿autoriza Seguridad (TO-BE), confirma el Coordinador de Distribución (IF) o ambos (implementado)?
- **Q17.** ¿Los dos coordinadores de almacén del TO-BE son roles distintos?
