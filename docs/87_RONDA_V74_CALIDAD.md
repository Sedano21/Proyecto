# Ronda V74 (25-nov-2026): pedidos de Calidad

Fuente: el mensaje del usuario del 25-nov («CALIDAD»). Las pruebas usan solo datos ficticios.

## Qué se hizo

### Especificaciones por producto
- Pantalla nueva: Calidad → **Especificaciones por producto**.
- Al elegir un producto (se escribe el código o el nombre y la lista se va filtrando) se ven los archivos que ya están
  en la base de datos, en la carpeta del producto:
  - especificaciones de calidad (carpeta nueva);
  - ficha técnica;
  - certificados.
- **Subir o actualizar:** la Jefatura y la Supervisión de Calidad suben PDF o Excel.
  - «Actualizar» reemplaza los archivos vigentes de esa carpeta.
  - Los reemplazados no se borran: quedan en el historial, como no vigentes.
- **Excel:** la primera hoja se muestra en pantalla, sin descargarla.
- **Certificado:** el detalle del certificado muestra la especificación y la ficha técnica del producto, con enlaces.
- **Catálogo comercial:** la nueva carpeta «Especificaciones de calidad» también aparece en la carpeta del producto.
- Permiso nuevo: «calidad.especificaciones» (Jefatura y Supervisión de Calidad).

### Certificados
- **Referencia por tipo de producto:** pantalla nueva «Referencias de certificados».
  - La tabla es «palabra del tipo de producto → norma de referencia».
  - El certificado busca esa palabra en el producto declarado y toma la referencia sola.
  - Antes la tabla estaba en Configuración y solo la cambiaba Sistemas. Ahora la mantiene Calidad (Jefatura o
    Supervisión).
  - Valores cargados:
    - FRIJOL → NTP-205.015.2015;
    - LENTEJA → NTP-205.022.2014.
  - Faltan los demás tipos (ver «Por decidir»).
- **Detalle del picking:** el certificado muestra, solo para leer, lo registrado en el picking.
  - Toma la OV del certificado o, si no tiene OV, el mismo producto y lote.
  - Por cada registro: OV, lote, cantidad, bultos, fechas de producción y vencimiento, quién registró y comentario.
  - Por cada tarea de picking: estado, verificador y las fotos de inicio y de listo.

### Carga: observación de calidad del producto
- Al validar la carga se puede escribir una **observación de calidad del producto** (por ejemplo, sacos húmedos o
  rotos). Lo pueden hacer:
  - el chofer y el auxiliar de despacho, en el checklist de cada guía de «Mi ruta»;
  - Almacén y Seguridad, en la carga de la ruta.
- Calidad recibe la alerta.
- **La unidad no sale** hasta que Calidad apruebe la observación.
  - Si Calidad no la aprueba, escribe qué corregir.
  - Almacén recibe el aviso y Calidad vuelve a revisar.
- Aprueban la Jefatura, la Supervisión y el Asistente de Calidad, con los permisos que ya tenían de visto bueno o
  liberación.

### Controles de Calidad en el proceso, en tiempo real
- La Jefatura, la Supervisión y el Asistente de Calidad registran controles en el parte en curso:
  - el parámetro controlado;
  - el valor;
  - si está conforme o no, con su observación.
- Se registran desde tres lugares:
  - el parte de producción;
  - «En la línea» (lista de partes en curso);
  - el botón de cada tarjeta del **Monitoreo en tiempo real**, que muestra el último control.
- Un control **no conforme** avisa a Producción y a Calidad.
- Los parámetros sugeridos salen de formatos ya documentados: humedad (PCC1), peso, rotulado y sellado (REG-CAL-003).
  Se puede escribir otro parámetro.

### Etiquetas para el despacho
- **Productos:** solo materia prima (MP) y producto terminado (PT).
- **Cliente:** se escribe el nombre y la lista se va filtrando. Si queda vacío, la etiqueta vale para todos los
  clientes.
- **Marca:** es opcional. Se sugieren Cantaclaro y Cosecha Andina, y se puede escribir otra.
- **Lote y fecha de vencimiento:** se digitan en la etiqueta y se ven en el picking.

### Solicitudes de fumigación
El flujo nuevo tiene cinco pasos:
1. **Almacén solicita la revisión.** También pueden solicitarla Producción o Calidad.
2. **Calidad decide** si se fumiga o no. Si no se fumiga, indica el motivo.
3. **Almacén confirma el espacio.** Si Calidad decidió fumigar, a Almacén le llega la alerta.
   - Si no hay espacio, la solicitud queda **pendiente («Sin espacio»)** hasta que Almacén lo confirme.
4. **Calidad programa** el lugar, el inicio y la liberación.
   - El inicio sugerido es el próximo **martes, jueves o sábado** (parámetro «fumigacion_dias_preferidos»).
   - Para otro día hay que escribir el motivo.
5. **Almacén confirma el ingreso** con el checklist, como antes.

Alertas nuevas: «Fumigación: confirmar si hay espacio» (Almacén) y «Fumigación: espacio confirmado, programar»
(Calidad).

### Fumigación de unidades
- **Producto:** se quitó del registro de fumigación de la unidad. Solo se pide en las zonas.
- **Registro o certificado:** se adjunta como foto o PDF.
- **Validación:** la Jefatura o la Supervisión de Calidad marca el registro conforme o no conforme. Si es no conforme:
  - escribe qué está mal;
  - la unidad vuelve a avisar.
- Permiso nuevo: «saneamiento.validar».
- Hay acceso directo desde el menú de Calidad.

### Abastecimiento: informe de recepción de Calidad
- Pantalla nueva: **Informes de recepción**, en Calidad y en Abastecimiento.
- **Compras nacionales:** Calidad sube el informe de cada compra con orden generada o recibida.
  - Formato: PDF o Excel.
  - Resultado: conforme, observado o no conforme.
  - Se agrega una nota y se guarda el historial.
  - Compras y Logística reciben el aviso.
- **Importaciones:** el informe se sube aquí o en el seguimiento, ahora también en Excel. Se mantiene la opción de
  generarlo con REG-CAL-005.

### Formatos de Calidad e higiene del personal
- Pantalla nueva: **Formatos (higiene y todos)**. Reúne todos los formatos, cada uno con «Registrar» y «Reporte»:
  - higiene del personal (PHS-003);
  - higiene de equipos y áreas;
  - los registros REG-* por etapa.
- Al final hay una lista con todas las pantallas que ve y usa la Jefatura de Calidad.

## Por decidir

| Punto | Situación |
|---|---|
| Cuadro de referencias por tipo de producto | El mensaje menciona un cuadro adjunto, pero no llegó ningún archivo. La tabla ya se puede llenar en «Referencias de certificados». Si me envían el cuadro, lo cargo tal cual. No inventé normas. |
| Tipo de certificado «Harinas» | Queda pendiente. Para crearlo hace falta un certificado modelo de harinas, con sus análisis, especificaciones y referencias. No lo inventé. |
| «Validar el formato» de la fumigación de unidades | Lo interpreté como que Calidad valida el registro (conforme o no conforme). Si se refería a revisar el diseño del formato impreso, hace falta el formato vigente. |
| Días preferidos para fumigar | Martes, jueves y sábado, ajustable. Otro día se permite con el motivo. |

## Pruebas
- `tests/test_v74.py`: 11 pruebas.
- `tests/test_v27.py`: se ajustó al flujo nuevo de fumigación.
