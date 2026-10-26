# Observaciones del módulo V7 (26-oct-2026)

Este documento resume cómo se atendió cada observación del módulo V7, las decisiones técnicas tomadas y lo que quedó
pendiente.

**Datos de demostración.** Todos son ficticios.

**Credenciales.** No se guardó ninguna credencial en el repositorio ni en la base. GEOSATELITAL y SAP se configuran
solo con variables de entorno del servidor.

**Esquema de datos.** Migraciones `0018_observaciones_v7` y `0019_v7_movimientos_carga_geosat`. Se probaron subiendo,
bajando y volviendo a subir.

**Pruebas.**
- La suite completa tiene 309 pruebas y todas pasan.
- Las de esta ronda están en `tests/test_v7.py`.
- Se verificaron las pantallas nuevas en navegador a 1280 px y 390 px: todas responden 200 y ninguna tiene desplazamiento horizontal.

## Asistente de Ventas

| Observación | Qué se hizo |
|---|---|
| (a) OC del expediente a pantalla completa sin regreso | Los documentos se abren en un visor dentro de la página, con «Abrir en otra pestaña» y cierre. |
| (d) Volver a la vista anterior desde cualquier pestaña | Hay un botón **Volver** global que recuerda la página anterior de la sesión. Los formularios largos (OV) guardan un borrador automático del navegador y lo recuperan si se sale. |
| (b) Regularización | Ver «Lógica de la regularización» abajo. |
| (c) Precio bajo el precio base | Aviso **en vivo**, por línea, solo para quien registra. Al enviar, una confirmación pregunta «registrar igual o modificar». La retención y aprobación por el Coordinador o el Jefe (decisión Q11) se mantiene para el precio **bajo** el mínimo. |
| (e) Penalidades | Ver la sección «Penalidades». |
| (f) Otra dirección de entrega | Se guarda sola en la ficha como «Dirección N», sin borrar las anteriores, y no se duplica. La dirección fiscal es la «Dirección 1». En la OV se elige de una lista desplegable. |
| (g) Carga masiva de OV de SAP | Ver la sección «Carga de OV de SAP». |
| (h) Corte de las 12:00 | Una OV fuera de corte ya no se pierde: queda en **borrador**, con aviso. Se registra sola al corregir la fecha. |
| (i) Informes corporativos | Nuevo **Informe de gestión comercial**: Informes → Gestión comercial. Ver la sección «Informe de gestión comercial». |
| (j) Códigos de cliente | Se respetan los códigos de SAP y no se aceptan duplicados. Un cliente nuevo recibe el siguiente correlativo con el mismo prefijo y ancho que usa SAP (si aún no hay códigos, parámetro `prefijo_codigo_cliente`). |
| (k) Catálogo | Ver la sección «Catálogo». |
| (l) «Finanzas: cobranza y condiciones de pago,» | **El texto llegó incompleto.** Ya existe el cuadro de cobranza (ronda 23-oct) y el informe muestra el estado de pago por cliente. La pregunta está en el cuestionario operativo. |
| (m) Stock sin rotación | Ranking **top 20 en dos frentes**: por tiempo sin salida y por cantidad inmovilizada (kg, y S/ al costo para quien ve costos). Muestra días, semanas y meses, el vencimiento y una recomendación de venta por producto (por ejemplo, a quiénes ofrecerlo, liquidar si vence o proponerlo como producto del mes). |

### Penalidades del cliente (e)

- Tabla de condiciones **sin límite de filas**: tipos de la lista o uno nuevo, cada uno con monto fijo o % de la OV. Al guardar se actualiza la tabla de condiciones del cliente.
- **Detección automática**: al registrar la entrega se compara con las condiciones del cliente (fecha comprometida, entrega parcial y fill rate mínimo) y se registra la **penalidad calculada**. No se duplica.
- **Registro manual**: Comercial puede registrar una penalidad comunicada por el cliente.
- **Alertas**: se avisa al vendedor o ejecutivo, al Coordinador y al Jefe Comercial para que registren si se **pagó** (con monto) o se **desestimó** (con motivo).
- **Indicador**: calculada, pagada y desestimada (con su %), total y por vendedor. Aparece en la ficha del cliente y en el informe.

### Carga de OV de SAP (g)

- Las OV **cerradas** no se importan.
- Las abiertas **no se duplican**: se identifican por el número de OV. Si se carga varias veces al día, la que ya existe pasa como modificación o queda «sin cambio».
- **Formato no recibido**: el archivo mencionado («el formato que te adjunto») no llegó. Se usa la estructura de exportación de SAP ya configurada; cuando lo envíen se ajusta el mapeo de columnas.
- La lógica de stock para las OV que SAP cerró se explica en la sección «OV cerrada en SAP».

### Informe de gestión comercial (i)

- **Nivel de servicio** con su fórmula visible: On time, In full, OTIF y fill rate (unidades y líneas).
- **Pedidos**: OV ingresadas, atendidas, pendientes del mes y facturación (S/ y kg).
- **Metas**: avance de metas (S/ y kg) contra lo esperado a la fecha.
- **Desempeño por persona**: meta, OTIF, OV modificadas, oportunidades y penalidades.
- **Embudo comercial**.
- **Por canal y cliente**: venta por canal y estado de pago por cliente (deuda y días de atraso).
- **Margen por canal**: solo quien ve costos.
- **Productos**: los menos vendidos, los sin movimiento (primero los que tienen stock) y las presentaciones sin movimiento.
- **Mercado**: precio y costo frente al mercado.
- **Filtros múltiples**: canales para incluir o excluir, granel, sin granel o todo, vendedores y clientes.
- **Recomendaciones** grandes y de color, por prioridad.
- **Descargas** en PDF, Excel y **PowerPoint** con logo (biblioteca `python-pptx`).
- **Indicadores sugeridos**: se proponen otros indicadores para sumar.

### Catálogo (k)

- **Carpeta por producto**: ficha técnica, fotos, certificados, recetas y estrategias comerciales.
- **Fotos**: se cambia la foto principal.
- **Destacados**: «producto del mes» o «de temporada», con mensaje y vigencia.
- **Alta de productos**: con el código de SAP.
- **Permisos**: no se cambiaron. Actualizan el catálogo el Jefe y el Gerente Comercial (permiso `catalogo.fotos`); los demás lo consultan.

### Lógica de la regularización (b)

Una regularización registra un pedido de una **fecha pasada** que no se registró a tiempo en el módulo.

**Fecha.** Debe ser **anterior a hoy**. Si se registra con fecha de hoy o futura, la regularización no avanza:
- se guarda como **borrador observado**, sin perder lo digitado;
- se alerta a quien la registró para que corrija la fecha (o registre una OV normal).

**Por qué hay dos botones.** Después de registrarla hay que decir qué pasó con la mercadería. Son dos situaciones reales distintas:

1. **«La mercadería ya salió: descontar y cerrar»** (antes «Cerrar registro»).
   - El pedido se atendió físicamente; por ejemplo, por teléfono o en contingencia.
   - El sistema **descuenta del inventario** lo que salió. Propone lotes por FEFO usando solo stock libre, para no tocar lo reservado de otras OV, y el usuario puede elegir otros lotes.
   - Registra la venta en el historial y **cierra** la OV.
   - Si esa salida ya está descontada en SAP, se marca «ya descontado en SAP» para no descontar dos veces. La próxima carga de stock de SAP la refleja.
2. **«Aún no se atiende: pasar al flujo normal»** (antes «Liberar con fecha vigente»).
   - El pedido llegó tarde pero la mercadería todavía no sale.
   - Se le pone una **fecha vigente** y entra al flujo normal: evaluación, reserva, picking y despacho como cualquier OV.

**Mientras no elija.** La OV no reserva ni descuenta stock.

### OV cerrada en SAP (g)

Si la carga de SAP trae como **cerrada** una OV que en el módulo sigue abierta (parámetro `cerrar_ov_cerrada_en_sap`):
- **Si aún no entró a preparación**: se cierra como **«Atendida en SAP»** y se liberan sus reservas.
  - **No se descuenta stock en el módulo.** La salida ya está en SAP y la próxima carga de stock la refleja; descontar aquí la duplicaría.
- **Si ya está en preparación o en ruta**: manda el módulo y queda como diferencia en la conciliación para revisarla.

Con el Service Layer se traen además las OV cerradas en los últimos 7 días, solo para este cierre.

## Coordinador, Jefe y Gerente Comercial

| Observación | Qué se hizo |
|---|---|
| (n) Panel de alertas | Ordenado: primero las abiertas que requieren acción, después por urgencia (alta, media, baja) y las más recientes. |
| (o) OV en el límite del precio | Solo **informativa** (alerta de prioridad baja). La OV no se detiene. Por debajo del mínimo sí se detiene. |
| (p, r) Portada | Para Coordinador, Jefe, Gerente Comercial y Gerencia General: metas del mes (S/ y kg, por vendedor, canal y total) con la marca del avance esperado; OV ingresadas, atendidas, pendientes y facturación; OTIF y fill rate; recomendaciones. Una alerta semanal avisa cada **meta atrasada**. |
| (q) Recomendaciones | Más grandes y de color según la prioridad. |
| (s) Informe por persona | En el informe de gestión (desempeño en lugar de datos de uso), más el informe de comportamiento por cliente que ya existía. |
| (t) Sustitutos y competencia | Los registran el Coordinador, el Jefe y el Gerente Comercial (nuevo permiso `mercado.sustitutos`; el Gerente puede registrar precios de competencia). El informe muestra **precio vs mercado** y, para quien ve costos, **costo vs mercado**. |
| (u) Oportunidades | Productos de interés elegidos del catálogo, varios, con «+ Agregar producto». |
| (u) Cotizaciones | Nueva pantalla con las cotizaciones del módulo y de SAP. «Traer de SAP» lee las ofertas de venta (solo lectura, sin duplicar). Cada cotización se ve, imprime y descarga en PDF. |
| (v) Objetivos de venta | Los registran el Coordinador, el Jefe y el Gerente Comercial, en varias filas a la vez: general, por canal y por vendedor. Incluyen S/, kg, **clientes nuevos** y **SKU nuevos en clientes existentes**, con su avance. |
| (w) Proyección de demanda | Registro por grupo («+» filas) y envío completo de una sola vez: si una fila tiene error no se guarda ninguna. Canal y cliente son listas opcionales y la observación es la justificación. **Modificar** una proyección ya registrada requiere justificación y queda pendiente hasta que **Gerencia General** la autorice. |
| (x) Turnos y personal | Cada responsable gestiona **solo su área**; Logística incluye Almacén y Distribución, configurable. Ver «Turnos: quién los gestiona» abajo. |

### Turnos: quién los gestiona (x)

- **Quiénes**: coordinadores en adelante; en Producción también los asistentes; en Almacén también el Líder Operativo.
- **Supervisores**: se incluyeron con nivel de coordinador.
- **Refuerzo de emergencia**: con personal de la empresa o de un **tercero**. El tercero lleva nombre, DNI, empresa y **costo por hora** obligatorio.
- **Costo de horas extra**: se muestra al final de la pantalla (horas × costo por hora).

### Cotizaciones del módulo en SAP (u)

Registrarlas en SAP es **escritura en SAP**. Está implementado pero **deshabilitado** (parámetro `sap_escritura_cotizaciones`) hasta que la empresa lo autorice.

## Otros

**(y) Solicitar movimiento**
- **Cuándo**: inmediato o programado (fecha y hora).
- **Quién solicita**: jefes, supervisores, coordinadores, líderes operativos y el montacarguista. Se retiró el permiso a asistentes y auxiliares; queda registrado en la auditoría.
  - Excepción: el Asistente de Producción sigue pudiendo, porque tiene el perfil adicional del Jefe de Producción (decisión anterior).
- **Asignación**: se puede asignar a un montacarguista, un auxiliar de almacén o un auxiliar de distribución.
- **Horas**: la de inicio y la de fin salen de las fotos (no se editan) y se muestra la duración. Las fotos se abren con el ícono de ojo.
- **Eliminar**: solo quien creó la solicitud puede eliminarla.

**(z) GEOSATELITAL sin API**
- **Panel embebido**: se muestra en un `<iframe>`; dirección en el parámetro `geosatelital_url_panel`.
- **Ventana acoplada**: si el proveedor no permite mostrarlo dentro de otra página, el botón **«Abrir acoplado al costado»** lo abre en una ventana angosta pegada al lado derecho, junto al módulo.
- **Enlace por unidad**: cada unidad puede tener su **enlace de seguimiento** («compartir ubicación» del panel). Se ve embebido en su tarjeta o acoplado. Solo se aceptan enlaces https sin usuario ni contraseña.
- **Credenciales**: la cuenta de la empresa se usa solo al iniciar sesión en el panel del proveedor. El módulo no la guarda.
- **API**: si el proveedor entrega un servicio de posiciones, se usa `GEOSAT_API_URL` (ya implementado).

**(aa) Validación de la carga**
- **Chofer primero**: el chofer valida cantidad, lote, presentación y producto contra la pre-guía.
- **Auxiliar después**: valida el auxiliar de distribución asignado a la ruta, si lo hay. Lo asigna Distribución en la ruta y se le alerta.
- **Llegada**: la registra el chofer.
- **Chofer externo sin cuenta**: Distribución registra su validación por encargo.

**Resto**

| Observación | Qué se hizo |
|---|---|
| (cc) Fumigaciones | Calidad ve cuántas veces se envió a fumigación cada producto y cada lote, con la última fecha. |
| (dd) Sonidos | Distintos por prioridad: alta (alarma insistente), media (campanilla de tres notas) y baja (un toque). Solo suenan las alertas que requieren acción. |
| (ee) Diseño | Se agregaron tarjetas, KPI, pestañas con contraste corregido, filtros con selección múltiple y diseño adaptable a móvil. |
| (bb) Preguntas operativas | Cuestionario publicado (privado): https://claude.ai/artifact/MR9quZpKcLM6r8Jd39DtAu |

## Pendiente de respuesta o de datos

- Texto completo de la observación de Finanzas (l).
- Archivo de formato de la carga masiva de OV de SAP (g).
- Autorización para escribir cotizaciones en SAP (u).
- Dirección del panel de GEOSATELITAL y enlaces de seguimiento por unidad.
- Respuestas al cuestionario operativo.
