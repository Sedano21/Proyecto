# Decisiones del 12-oct-2026: aplicación y preguntas pendientes detalladas

Este documento registra las respuestas recibidas el 12-oct-2026, cómo se interpretó cada una, dónde quedó implementada
y con qué prueba se verifica. Las reglas nuevas aparecen en la configuración con estado **DEFINIDO** y la fuente
"Decisión del usuario (12-oct-2026)". Las pocas asignaciones que tuve que proponer para que la regla funcione figuran
como **PROPUESTO** y se pueden cambiar sin programar.

## 1. Respuestas aplicadas

| # | Respuesta | Interpretación | Implementación | Prueba |
|---|---|---|---|---|
| Q1 | Por ahora no hay más diagramas | Se trabaja con el IF y el TO-BE L5 | — | — |
| Q2 | OTIF se calcula cuando el vehículo sale con la carga a tiempo. Agregar un fill rate que indique si salió al 100 %, si hubo rechazo y su motivo, para ubicar en qué parte del proceso están los mayores errores | OTIF único = pedido que **sale** completo y en o antes de la fecha comprometida. El OTIF por entrega en destino queda solo como referencia | Parámetro `otif_definicion` = SALIDA. Tablero: fill rate de unidades y de líneas, % de pedidos que salieron al 100 %, cuántos de ellos tuvieron rechazo después, detalle por pedido con el motivo y tabla "¿Dónde están los mayores errores?" por etapa. La asignación de cada causa a una etapa es el parámetro `etapa_por_incidencia` (PROPUESTO, editable) | `test_q2_otif_por_salida_y_fill_rate` |
| Q3 | Aprueba Gerencia de Operaciones **o** Jefe de Logística; el saldo se reprograma para una próxima entrega | Basta una aprobación. Esto corrige la versión anterior, que exigía las dos | `parcial_modo` = CUALQUIERA. Con TODOS se vuelve a exigir a ambos. El saldo se crea como OV `<OV>-S1` al salir el despacho | `test_despacho_parcial_aprobacion_y_saldo`, `test_gerencia_general_aprueba_en_nombre_y_rechazo` |
| Q4 | Gerencia General puede aprobar en nombre de otros roles; Sistemas no | Igual que en la versión anterior | Sistemas tiene todos los permisos salvo los de aprobación | `test_sistemas_no_aprueba_gerencia_general_si`, `test_matriz_permisos_reglas_documentadas` |
| Q5 | Son almacenes virtuales. ALM-003 es el tránsito de Producción: el producto terminado queda ahí hasta que Almacén lo valida y pasa a ALM-001. ALM-010 no se usa | — | ALM-003 (uso TRANSITO_PRODUCCION) y ALM-010 (uso NO_UTILIZADO), ambos no reservables. Al registrar la liquidación, el PT entra a ALM-003. La recepción de Almacén lo saca de ALM-003 y lo ingresa a ALM-001. La carga SAP advierte las filas de ALM-003 y ALM-010 | `test_q5_transito_produccion_y_almacen_no_utilizado`, `test_produccion_bom_merma_y_liquidacion` |
| Q8 | Una diferencia con la guía puede bloquear la salida, pero el Coordinador o el Jefe de Logística puede aprobarla mientras se resuelve la guía | La discrepancia bloquea. Logística aprueba con motivo, y la guía queda pendiente de resolución con alerta abierta | `bloquear_salida_con_discrepancia` = sí. Permiso `distribucion.aprobar_salida_discrepancia` (Jefe y Coordinador de Logística). Alertas GUIA_DISCREPANCIA y SALIDA_CON_DISCREPANCIA. Acción "Registrar guía resuelta". Si Seguridad vuelve a validar sin diferencias, se desbloquea | `test_q8_discrepancia_bloquea_y_logistica_aprueba`, `test_q8_corregir_y_validar_de_nuevo_desbloquea` |
| Q12 | El sistema hace una pre-solicitud de reempaque y se envía con la aprobación del Coordinador de Almacén | — | Estado PRE_SOLICITUD. El Coordinador de Almacén aprueba (pasa a Calidad, que la evalúa, y el lote queda retenido) o la desestima | `test_q12_reempaque_presolicitud_aprobada_por_coordinador` |
| Q13 | El traslado lo aprueba el Jefe o el Coordinador de Logística | — | `traslado.autorizar` asignado a ambos. El sistema también pre-solicita traslados | `test_almacen_alternativo_traslado_autorizado`, `test_q15_…` |
| Q14 | El Jefe de Logística aprueba la solicitud de compra | Aplica a toda solicitud, incluidas las de reposición y las automáticas | Nuevo estado PENDIENTE_LOGISTICA antes de Compras. Permiso `compras.aprobar_solicitud`. Alerta COMPRA_APROBACION_LOGISTICA | `test_compra_nacional_flujo`, `test_reposicion_calculo` |
| Q15 | Orden: producir, reempaque, traslado desde almacén externo, compra | Ante un faltante, el sistema genera la pre-solicitud de la primera opción **viable**. Si esa opción solo cubre una parte, el saldo pasa a la siguiente. Al reevaluar, lo ya solicitado se descuenta para no duplicar | Módulo `app/services/presolicitudes.py`. Viable: producir = la lista de materiales existe y todos los materiales están disponibles; reempaque = hay lote apto para reempacar (si cambia la presentación, se convierte por peso); traslado = hay stock apto libre en almacén alternativo; compra = el artículo no tiene lista de materiales. Parámetros `presolicitudes_automaticas` y `orden_presolicitudes`. La OV muestra sus solicitudes y pre-solicitudes | `test_q15_presolicitudes_en_orden_producir_reempaque_traslado_compra` |
| Q16 | Autoriza la salida el Líder Operativo | Una sola autorización: Seguridad revisa los documentos y el Líder Operativo autoriza la salida con la verificación del IF §12.2. El Coordinador de Distribución ya no confirma la salida | `distribucion.confirmar_salida` asignado al Líder Operativo. Seguridad: "Revisar documentos" | `test_q16_lider_operativo_autoriza_salida` |
| Q17 | Son dos roles; cada uno maneja un almacén (1560 o 1524) | Coordinador 1560 = ALM-001 (y el tránsito ALM-003, porque su producto pasa a ALM-001). Coordinador 1524 = EXT-002 | Nuevo rol COORD_ALMACEN_MP (usuario demo `coord.almacen.mp`). Parámetro `alcance_almacen_por_rol`. Cada coordinador solo actúa sobre su almacén (estados, conteos, recepciones, traslados, reempaques) y recibe solo las alertas de su almacén. Los almacenes no asignados (alternativos) no se restringen | `test_q17_alertas_y_acciones_por_almacen`, `test_conteo_fisico_diferencias`, `test_compra_nacional_flujo` |

## 2. Observaciones que conviene revisar

- **Separación de funciones en traslados (Q13).** El Coordinador de Logística puede solicitar un traslado y también
  aprobarlo. Si no se quiere que una misma persona apruebe su propia solicitud, se puede agregar esa restricción.
- **Almacenes alternativos (767, Trujillo 1 y 2, Isabelita).** No pertenecen a ninguno de los dos coordinadores, así
  que hoy cualquiera de ellos puede registrar la salida o la recepción. Indique si corresponde a uno en particular.
- **Base de datos existente.** Esta versión agrega columnas nuevas (aprobación de la discrepancia en la ruta y
  aprobación de Logística en compras). La demo se recrea con `python -m app.cli demo`. Una instalación con datos
  necesitaría una migración (ver `08_INSTALACION_DESPLIEGUE.md`).

## 3. Preguntas pendientes, detalladas

Para cada pregunta se indica qué hace hoy el sistema y la decisión que se necesita. Puede responder solo con valores.

### Q5 (resto). Otros almacenes que aparecen en la exportación de stock
La carga real trae, además, ALM-002, ALM-004, ALM-005, ALM-006, ALM-007, ALM-012, EXT-007, EXT-013 y PRO-*.
Hoy se cargan como "uso no definido" y **no se reservan**.
- ¿Todos son virtuales como ALM-003 y ALM-010? Para cada uno: ¿se reserva para pedidos (sí/no)? ¿Qué coordinador lo
  maneja (1560, 1524 o ninguno)?

### Q6. Estado de un lote nuevo en cargas SAP posteriores
Cuando una carga SAP trae un lote que el sistema no conocía, hoy entra **Disponible** (se puede reservar). El IF dice
que "Pendiente de revisión" corresponde a una carga recibida.
- ¿Un lote nuevo debe entrar **Disponible** o **Pendiente de revisión** (no se reserva hasta que Calidad lo libere)?
- ¿Aplica a todo artículo o solo a producto terminado o a materia prima?

### Q7. Valores de configuración (hoy vacíos o de demostración)
| Valor | Para qué sirve | Ejemplo de respuesta |
|---|---|---|
| Margen de reposición (días) | Se suma al plazo del proveedor para pedir antes | "3 días para todo; 5 para bobinas" |
| Umbral de compra de mayor volumen | A partir de esta cantidad la compra pide aprobación de GO | "10 000 kg" o "S/ 50 000" |
| ¿GO aprueba las compras de mayor volumen? | Además del Jefe de Logística (Q14) | sí/no |
| Merma por defecto (%) y umbral de alerta (%) | Cálculo de materiales y alerta de merma | "2 % por defecto; alerta sobre 4 %" |
| Horarios de corte de preparación | Ordenan la cola de picking | "10:00 y 15:00" |
| Tamaño de pedido pequeño/mediano/grande (kg) | Tiempo de preparación esperado | "pequeño < 500 kg; grande > 5 000 kg" |
| Días de "vencimiento próximo" | Alerta de lotes por vencer | "60 días" |
| Tiempo máximo de almacenamiento por producto | Alerta de "no utilizable / fumigación" | "granos: 90 días" |
| Tolerancia de discrepancia con la guía (Q8) | Diferencia que no bloquea la salida | "0 unidades" o "0,5 %" |

### Q9. Identificación de las liquidaciones de SAP
En el archivo real (Recep. pt.xlsx), un mismo número de documento aparece con dos lotes. Hoy se toma
**documento + lote** como una liquidación distinta y la cantidad de cada fila como propia.
- ¿Es correcto que un documento tenga varios lotes con su propia cantidad? ¿O la cantidad es el total del documento y
  hay que repartirla entre los lotes?

### Q10. Fases de importación
Hoy se usan 4 fases de demostración: embarque, arribo a puerto, nacionalización y llegada a almacén.
- ¿Cuáles son las fases reales, en qué orden, cuántos días suele tomar cada una y quién es el responsable de cada
  fase? ¿Con cuántos días de anticipación se debe recordar?

### Q11. Precios y fecha comprometida
- La exportación de OV no trae precio, por lo que el monto de las OV en el tablero sale 0. ¿De qué archivo o lista
  se toma el precio (lista de precios SAP, precio por cliente o canal)?
- En la exportación, la columna "Fecha de Vencimiento" de la OV se usa como **fecha comprometida de despacho**.
  ¿Es correcto?
