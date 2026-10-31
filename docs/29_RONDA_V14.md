# Ronda V14 (31-oct-2026)

Indicaciones del 31-oct-2026. Se recibieron:
- el cuadro de capacidades por línea;
- cuatro PDF de formatos de Calidad;
- una foto de la ficha del cliente.

De los PDF solo se usó la estructura. El de higiene de personal trae nombres reales del personal y **no se guardó**: la lista del formato sale del personal registrado en el sistema.

## 1. Interfaz general (laptop, tablet y celular)

| Indicación | Implementación |
|---|---|
| Hora más práctica | Todos los campos de hora (formatos y registros) usan una lista de horas y otra de minutos. Tienen flechas para restar o sumar 1 o 5 minutos y un botón «Ahora». Reemplaza el reloj del navegador. |
| Foto de la galería o tomada en el momento | Cada carga de foto ofrece «Galería / archivo» y «Cámara». La cámara abre la del celular o la tablet. |
| Varios archivos con «+» | Donde se guardan varios documentos o fotos, se adjunta uno y aparece «+ Añadir otro», sin límite. Cada archivo muestra su vista previa y se quita con ×. |
| Fotos junto al registro | Las fotos guardadas se ven en miniatura junto al registro, también al imprimir. Al hacer clic se abren en grande. |
| Notificaciones | Las notificaciones y los mensajes de error se ven en un recuadro rojo con letras blancas. |

Las evidencias de un paso conservan **una foto por paso**:
- inicio y fin de un movimiento o del picking;
- conformidad de entrega;
- inicio y fin de una tarea.

En esos casos la hora del paso se toma de la foto. Igual tienen «Galería» y «Cámara».

## 2. Calidad

- **Antes de producir** se separa en dos formatos:
  - **Higiene del personal (PHS-003, diario):**
    - una fila por persona, con ✓ o X en HP (higiene personal), ES (estado de salud), U/T (uniforme y tapaboca), UÑ (uñas) y H (heridas);
    - el área de cada persona: SM, P, L, M o S;
    - si hay una X, la observación o acción correctiva es obligatoria y se alerta a Calidad;
    - la lista sale del personal activo y se agregan o quitan personas con «+» o ×.
  - **Higiene de equipos y áreas:**
    - PHS-001, áreas externas;
    - PHS-002, almacén de PT;
    - PHS-002, óptica y envasado automático.

    Se registran con C o N/C por punto. Los códigos y nombres se corrigieron según los PDF.
- El archivo «BPM.pdf» era el PHS-003. Por eso ya no hay un formato «BPM» separado sin puntos. El antiguo «Antes de producir: higiene del personal y de los equipos» queda retirado; sus registros anteriores se pueden consultar.
- **Reportes de cualquier registro** por día o rango de fechas, de un formato o de varios:
  - se ven en pantalla;
  - se descargan en **PDF** o en **Excel**;
  - se exportan **individualmente** desde cada registro o **en grupo** desde «Revisión de formatos».
- **Revisión de formatos:** los tipos de formato se eligen en una lista desplegable con «+ Agregar otro tipo».
- **Lote elegido:** en las fichas de Calidad, al elegir un lote de la lista se bloquea la casilla para digitar el lote.
- **Ficha de muestreo (CP-FOR-CAL-10)** en compras nacionales:
  - desde «Muestras de compras por evaluar» se abre la ficha de la compra;
  - su resultado (aprobado o desaprobado) aprueba o rechaza la muestra.
- **Fumigación:** al registrar el control de un lote que se bloqueó por fumigación, las fechas de inicio y fin y la zona salen llenas.
- **Precertificado:**
  - toma los registros de Calidad del lote, por número o por id de lote;
  - también toma los del proceso de producción que lo generó: el lote de MP de los partes con ese lote de PT;
  - Calidad puede modificarlo y aprobarlo.
- **Firma del certificado:** la carga la Jefatura de Calidad (o Sistemas) y se imprime en los certificados aprobados.
- **Inspecciones** internas y externas, calificadas por puntaje:
  - ≤ 69 % desaprobado;
  - 70–85 % regular;
  - 86–95 % bueno;
  - 96–100 % muy bueno.

  Un puntaje con decimales entre dos rangos toma el inferior: 85,5 % es regular.
- **Inicio de Calidad:** muestra cuántas líneas están en proceso y cuáles. De cada una muestra:
  - producto, OF y lote;
  - avance y ritmo;
  - merma en vivo;
  - paradas y observaciones abiertas.

  Tiene acceso al detalle del parte y a «Observar / merma».

## 3. Producción y movimientos

- **Solicitudes y programa:**
  - la capacidad de **RAUMAK 1 y 2** (18 700 kg/día, compartida por el grupo) aparece en ambas líneas;
  - cada día muestra la carga frente a la capacidad, ajustada a la jornada: sábado media jornada, domingo y feriados sin operación.
- **Planeamiento:** cuadro **capacidad real vs programada vs ejecutada** por línea, con los porcentajes de uso y de cumplimiento, en el mismo periodo de la pantalla.
  - Capacidad real: kg por día × jornadas operativas.
  - Programada: solicitudes programadas o plan con línea, en kg.
  - Ejecutada: kg de los partes de producción.
- **Solicitar movimiento:** se agregaron **granel** y **materia prima** (kg, artículo y sacos opcionales).

## 4. Gerencia

- Ya no hay Gerencia de Operaciones. Se creó el perfil **Gerente General Adjunto**, con el **mismo poder que Gerencia General** (las mismas autorizaciones).
- Las aprobaciones de **compras nacionales e importaciones** las hace el Gerente General Adjunto (o Gerencia General): ejecución de la compra y recepción bajo observación. Gerencia de Operaciones deja de recibir esas alertas y ya no tiene esos permisos.
- Usuario de demostración: `gerente.adjunto`.

## 5. Comercial: ficha del cliente

- Los indicadores de penalidades (calculada, pagada, desestimada y por resolver) se ven en una fila horizontal.
- Cada **lugar de entrega** admite **uno o varios contactos**, cada uno con su teléfono y correo (varios correos separados por coma). El sistema valida el formato de los correos.

## 6. Datos técnicos

- Migración `0028`: `customer_sites.contactos`.
- Archivos nuevos:
  - `app/static/v14.js`;
  - las plantillas `cal_higiene_personal`, `cal_higiene_equipos` y `cal_reporte`.
- Pruebas: `tests/test_v14.py`. La suite completa se ejecutó en SQLite y en PostgreSQL 16.
