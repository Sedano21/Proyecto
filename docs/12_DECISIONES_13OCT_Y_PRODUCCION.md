# Decisiones del 13-oct-2026 y preguntas para pasar a producción

## 1. Respuestas aplicadas

| # | Respuesta | Implementación | Prueba |
|---|---|---|---|
| Q16 | La salida necesita la autorización y el visto bueno de Seguridad, del Líder Operativo y del Auxiliar de Despacho | Seguridad da su visto bueno al revisar los documentos completos. El Auxiliar de Despacho da el suyo con la carga validada (permiso `distribucion.visto_bueno_salida`). El Líder Operativo da el último al autorizar la salida, que exige los otros dos. Los roles exigidos están en el parámetro `vistos_buenos_salida` | `test_q16_salida_requiere_tres_vistos_buenos` |
| Q17 | Ningún coordinador aprueba sus propias solicitudes; en ese caso aprueba el Jefe de Logística. Por ahora cualquiera de los coordinadores opera los almacenes alternativos | `transfers.authorize` rechaza que una persona apruebe su propia solicitud de traslado. Los almacenes alternativos no quedan asignados a ningún coordinador, así que los opera cualquiera | `test_almacen_alternativo_traslado_autorizado` |
| Q5 | Los almacenes virtuales los manejan el Coordinador de Almacén 1560, el Coordinador de Logística y el Jefe de Logística | Almacenes ALM-002/004/005/006/007/012, EXT-007/013 y los que empiezan con PRO- (creados como VIRTUAL al aparecer en una carga): no reservables. El parámetro `alcance_almacen_por_rol` los asigna a esos tres roles. Logística recibe permisos de salida, recepción, cambio de estado y conteo **solo** para ellos | `test_q5_almacenes_virtuales_los_manejan_coord_1560_y_logistica` |
| Q6 | Un lote nuevo entra pendiente de revisión por Calidad | `estado_lote_nuevo_carga` = PENDIENTE_REVISION en las cargas posteriores a la base inicial | `test_q6_lote_nuevo_en_carga_posterior_queda_pendiente_de_revision` |
| Q7 | Márgenes, umbrales y horarios se configuran y modifican en el panel de configuración | Ya son parámetros editables y versionados en **Configuración** (y por artículo en el catálogo). Falta que la organización cargue los valores (§4.2) | `test_parametros_versionados_y_auditados` |
| Q9 | La cantidad se reparte entre los lotes | Si un documento trae varios lotes con la misma cantidad repetida, la carga la reparte en partes iguales (el residuo va al último lote) y avisa. Quien carga puede corregir cada fila; la suma debe coincidir con la cantidad del documento | `test_q9_liquidacion_con_varios_lotes_reparte_la_cantidad` |
| Q10 | Responsable: Coordinador de Importación; las fases y los días se configuran en el panel | Rol renombrado a "Coordinador de Importación", responsable de todas las fases. Fases, días y recordatorios se editan en **Configuración → Fases de importación** | `test_q10_fases_de_importacion_a_cargo_del_coordinador_de_importacion` |
| Q11 | El precio sale de las listas adjuntas; se modifica a voluntad, pero solo lo autoriza el Jefe Comercial. **Es el precio mínimo**: se vende por encima y la lista sirve para alertar si una OV está en el límite o por debajo. La fecha de vencimiento es la fecha comprometida | Cargas PRECIOS (lista por canal) y PRECIOS_GRANEL (mayorista granel) con el mismo formato de los Excel. Pantalla **Comercial → Listas de precios** con historial por SKU. Permiso exclusivo `precios.editar` para el Jefe Comercial (ni Gerencia General ni Sistemas lo tienen). Al registrar, importar o modificar una OV se compara cada línea con el mínimo de su canal; si está en el límite o por debajo, se alerta al vendedor, al Jefe Comercial y al Gerente Comercial (OV_PRECIO_BAJO_MINIMO). El sistema no cambia el precio de la OV. Tablero: OV bajo el mínimo y OV sin precio | `test_q11_*` (4 pruebas) |

**Decisiones de diseño tomadas (reversibles):**
- **El costo de la empresa no se guarda** en el sistema. Se usa solo durante la carga, para recalcular una fórmula sin valor y para advertir si un precio queda por debajo del costo.
- **Cada cambio de precio crea una versión nueva** y guarda quién lo hizo, cuándo y el motivo. Una OV ya registrada no se recalcula si después cambia la lista.
- **"En el límite"** significa igual al mínimo. El parámetro `margen_alerta_precio_pct` (hoy 0 %) permite alertar también cuando el precio está a menos de un X % por encima del mínimo.

## 2. Validación con sus listas reales

Lectura de solo prueba, en una base temporal que se descartó. Los archivos no se guardaron en el repositorio porque contienen costos.

| Archivo | Resultado |
|---|---|
| PRICE_LIST_OCT-NOV_26.xlsx | 350 filas, 10 canales reconocidos (MAYORISTA … DISTRIBUIDORES), 0 errores. 2 SKU repetidos con los mismos precios (MP-035, PT-122): se toman una vez. Ningún precio bajo el costo. 3 480 precios cargados |
| PRICE_LIST_GRANEL_OCT-DIC26.xlsx | 20 filas, 0 errores. **GR-041 tiene un precio por kg (2,98) menor que su costo (4,57)**. GR-201 y GR-041 figuran también en la lista general con otro precio |
| Cruce con el maestro de artículos (DATA) | De los 348 SKU de la lista, 335 existen en el maestro; de los 20 de granel, 17 |
| Cruce con las OV reales (hoja OVS) | De 187 productos con OV, 152 tienen precio mínimo y **35 no figuran en ninguna lista** (17 ME-, 5 GR-, 5 MQ-, 3 AB-, 3 PT-, 1 SU-, 1 SE-). 80 líneas son de clientes OFICINA, CANASTERIA o MINORISTA, que no tienen columna en la lista. 97 líneas son "Muestra comercial". **La exportación de OV no trae precio de venta**, así que con ese archivo el sistema no puede comparar contra el mínimo |

## 3. Preguntas abiertas de esta ronda (respondidas el 13-oct-2026; ver `13_DECISIONES_13OCT_PARTE2.md`)

| # | Pregunta | Qué hace hoy el sistema |
|---|---|---|
| P1 | **¿De dónde se obtiene el precio de venta de cada OV?** La exportación OVS no lo trae. ¿Se agrega la columna "P. Unitario" a la exportación o se toma de otro reporte de SAP? Sin ese dato no se puede alertar el precio bajo el mínimo en las OV cargadas desde SAP | Valida las OV registradas en el módulo con precio. Las importadas sin precio quedan marcadas "sin precio de venta: no se puede validar" |
| P2 | Grupos de cliente sin columna en la lista: **OFICINA, CANASTERIA y MINORISTA**. ¿Qué columna les corresponde? | Sin mínimo: no se validan |
| P3 | Las líneas de **"Muestra comercial"** (precio 0), ¿se excluyen de la alerta? | Si traen precio 0 quedan "sin precio" y no generan alerta |
| P4 | Un SKU que está en las dos listas (GR-201, GR-041): para un cliente MAYORISTA, ¿manda la lista granel o la general? ¿La lista granel aplica solo a MAYORISTA? | Para MAYORISTA manda la lista granel (parámetro `lista_granel_canales`, propuesto) |
| P5 | En la lista granel, ¿el mínimo se compara por kg o por saco? | Por kg si el artículo se vende en kilogramos; si no, por saco |
| P6 | Los 35 productos con OV que no figuran en ninguna lista, ¿deben tener precio mínimo? | No se validan |
| P7 | ¿Una OV bajo el mínimo solo se alerta, o también debe quedar detenida hasta que la apruebe alguien (¿quién?)? | Solo alerta |
| P8 | ¿Gerencia General puede modificar precios? Usted indicó "único: Jefe Comercial" | No puede; solo los consulta |
| P9 | La vigencia de las listas (OCT-NOV 26 y OCT-DIC 26): ¿al vencer se debe alertar o bloquear el uso de la lista? | La lista sigue vigente hasta que se cargue otra |
| P10 | ¿"Jefe Comercial" corresponde al rol Jefe de Ventas? | Sí, se tomó como el mismo rol |

## 4. Qué falta para pasar a producción

No se puede afirmar que el sistema esté listo para producción mientras no se cumpla todo lo siguiente.

### 4.1 Decisiones de negocio pendientes
1. P1 a P10 de la tabla anterior (precios).
2. **Matriz de alertas definitiva (ALR-07).** Revisar quién recibe cada uno de los 63 tipos de alerta, con qué prioridad y si va por correo. Hoy 21 están marcadas como PROPUESTO (18) o PENDIENTE (3) (ver `07_PERFILES_PERMISOS_ALERTAS.md`).
3. **Matriz de permisos definitiva.** De las 463 asignaciones rol-permiso, 272 son propuestas (columna "P" en la matriz) y 191 están definidas por la documentación o por sus decisiones: confirmar rol por rol.
4. **Reparto de configuración (CFG-11).** Hoy Sistemas y Gerencia General editan todos los parámetros. ¿Quién debe editar cada grupo (márgenes, cortes, fases, flota)?
5. **Compras de mayor volumen (REP-06).** ¿Además del Jefe de Logística, la aprueba Gerencia de Operaciones? ¿El umbral se mide en kg o en soles?
6. **Reglas no documentadas:**
   - margen por proveedor (COM-08);
   - excepciones a la proporcionalidad lineal en producción (PRD-15);
   - criterios de conversión de calidad en reempaque (RMP-03);
   - clasificación A/B/C de rotación (REP-04);
   - reglas de asignación de flota (DIS-06).

   Si no aplican en la primera etapa, basta con confirmarlo.
7. **Merma de insumos y granel desde SAP (PRD-12).** Se necesita el formato del reporte; hoy se registra manualmente.
8. **Rol "Coordinación de Producción (por validar)".** ¿Existe?

### 4.2 Datos y valores que debe cargar la organización (no son preguntas)
- Valores de configuración (Q7): margen de reposición, umbral de mayor volumen, merma por defecto y umbral de alerta, horarios de corte, tamaños de pedido, días de vencimiento próximo, tiempos máximos de almacenamiento, tolerancia de diferencia con la guía y margen de alerta de precio.
- Fases reales de importación con días y recordatorios (Q10).
- Maestros reales:
  - artículos (DATA) con peso, tipo y unidad;
  - clientes con RUC, grupo (canal), dirección, horario, cita y vida útil mínima;
  - flota y conductores con capacidad;
  - capacidad diaria de cada línea de producción;
  - lista de materiales vigente, confirmando si ya incluye la merma.
- Base inicial de stock SAP del día de arranque y listas de precios vigentes.
- Usuarios reales: nombre, correo y rol de cada persona, con los dos coordinadores de almacén diferenciados.

### 4.3 TI e infraestructura (requisitos de `09_SEGURIDAD_INFRAESTRUCTURA.md`)
1. **Servidor.** ¿Dónde se instalará (servidor propio, nube corporativa) y quién lo administra?
2. **Base de datos.** Se necesita PostgreSQL o SQL Server (no SQLite), con respaldos diarios y una prueba de restauración.
3. **Migraciones.** Incorporar una herramienta de migraciones (Alembic) antes de cargar datos reales, porque la estructura sigue cambiando.
4. **Correo.** Servidor SMTP corporativo y cuenta remitente para las alertas.
5. **Acceso y seguridad:**
   - HTTPS con certificado;
   - acceso solo desde la red interna o por VPN;
   - ¿inicio de sesión con las cuentas corporativas (Microsoft 365 / Active Directory)?;
   - política de contraseñas y bloqueo de cuentas.
6. **Exportaciones de SAP:**
   - ¿con qué frecuencia y quién genera cada exportación (stock, OV, liquidaciones, salidas)?
   - ¿se quiere automatizar la carga? Hoy es manual;
   - en todos los casos debe quedar visible la fecha de la última actualización.
7. **Datos personales** (Ley 29733): conductores, clientes y fotos de entregas. Definir cuánto tiempo se conservan y quién puede verlos.
8. **Almacenamiento de archivos:** espacio y respaldo para fotos, guías, facturas y certificados.

### 4.4 Validación y puesta en marcha
1. Pruebas de aceptación con usuarios clave de cada área, con datos reales en un entorno de prueba aprobado por TI.
2. Prueba de carga con varios usuarios simultáneos.
3. Capacitación por rol y manual breve de cada pantalla.
4. Plan de arranque:
   - fecha de corte;
   - carga de la base inicial;
   - período en paralelo con el Excel actual;
   - responsable de soporte.
5. Medición de tiempos reales de preparación y despacho durante el piloto, para ajustar cortes y alertas.
