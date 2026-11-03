# Ronda V19: experiencia de usuario (03-nov-2026)

## 1. Listas por páginas

Las listas ya no muestran todo de una vez. Por defecto salen **25 registros por página**; abajo se elige la página o se cambia a 50 o 100 por página.

- Al cambiar de página o filtrar, **solo se recarga la lista**; el resto de la pantalla queda igual.
- Los filtros se conservan al cambiar de página. Un filtro nuevo vuelve a la página 1.
- En las listas grandes la base de datos entrega **solo la página pedida**. Así es en:
  - clientes, stock por lote, traslados, registros de Calidad, checklists vehiculares y compras.
- En las demás listas, el sistema primero ordena o filtra por reglas y luego muestra solo la página:
  - OV (orden por prioridad), alertas (urgencia), cargas, conciliación, partes, liquidaciones, cotizaciones, oportunidades, incidencias, movimientos, auditoría, certificados, precios, catálogo, artículos, correos y observaciones.
- **Filas de una carga de archivos:** van de 50 en 50, con un resumen por tipo de aviso. Por ejemplo, «Lote con puntos o comas al final: 298». Al pulsar un tipo se ven solo esas filas.
- **No se paginan** los tableros que ya se limitan a un día o a una semana: rutas del día, programación de picking y programación de producción. Agrupan por fecha y paginarlos partiría la vista del día.

## 2. Clientes: botón «Nuevo cliente»

- Arriba a la derecha está el botón **«Nuevo cliente»**. Abre una **ventana emergente** con todos los datos del alta, sin bajar por la lista.
- La dirección `/ov/clientes?nuevo=1` abre la lista con la ventana ya abierta.
- La búsqueda por nombre o RUC, grupo, canal y ejecutivo se hace en la base de datos. Antes se traían todos los clientes para filtrarlos.

## 3. Indicador de carga

- **Velo gris con un gato negro durmiendo.** Aparece mientras el sistema responde y bloquea la pantalla para que no se pulse otra cosa ni dos veces. Se muestra al:
  - guardar, aprobar o registrar;
  - importar o subir un archivo (dice «Subiendo y procesando el archivo…»);
  - **exportar** a Excel, PDF o PowerPoint (dice «Generando el archivo…»; se quita solo cuando termina la descarga);
  - cambiar de pantalla o de pestaña dentro de un módulo.
- **Carga solo en la lista.** Al filtrar o cambiar de página, solo la lista se atenúa y muestra el gato; el resto de la pantalla sigue a la vista.
- Si la respuesta es inmediata, el velo no llega a verse, para que no parpadee.
- No se activa en los enlaces que abren otra pestaña.
- Respeta la opción «reducir movimiento» del teléfono o la computadora.

## 4. Fallos del sistema con código

- Si ocurre un error inesperado (por ejemplo, la base de datos rechaza un dato), sale una **ventana emergente** con:
  - el **código del fallo**, por ejemplo `E261103-101530-A3F2`;
  - un botón **Copiar** y la indicación de enviarlo a Sistemas.
- La ventana aparece también si el fallo ocurre al cargar una lista o en una página completa (error 500). Nada se guarda a medias: la acción se deshace.
- **Sistemas → Errores del sistema** (Administración): se busca el código y se ve cuándo pasó, quién estaba, en qué pantalla y el detalle técnico. Se guarda en `instance/errores.log` y en el registro del servidor (`journalctl -u operaciones`).
- Los errores de validación de siempre (un dato que falta, un permiso) siguen saliendo como mensaje en la pantalla. No son fallos del sistema.

## 5. Hora del sistema: Perú

- **Antes:** el sistema usaba la hora del servidor, que está en UTC (5 horas más). Por eso la carga «6 – Stock por lote» decía 14:44 cuando se subió a las 9:44.
- **Ahora:** todo el sistema trabaja con la **hora de Perú (America/Lima)**, aunque el servidor esté en UTC. Esto vale para:
  - registros, cargas, alertas, cortes (12:00, 15:00), plazos, turnos y la fecha de «hoy».
- Se cambia con la variable `APP_TZ` en `/etc/operaciones/operaciones.env`.
- **Datos anteriores:** lo registrado antes de esta actualización quedó con la hora de UTC, 5 horas adelantada. No se corrigió automáticamente, porque cambiaría datos guardados. Si lo autorizan, se puede preparar una corrección única que reste 5 horas a esos registros.

## 6. Lotes con puntos o comas (carga «6 – Stock por lote»)

Revisé la consulta exportada de SAP (1 337 filas). Los puntos y comas **ya vienen así de SAP**; el sistema no los agrega.

- **298 filas** tienen lotes con caracteres poco comunes. En casi todas son **puntos o comas al final**, como `017593TG......` o `201025IN,`. Solo hay tres casos distintos: uno con espacio, uno con `|` y uno con `#`.
- En **110 casos**, el mismo artículo tiene el lote **con y sin puntos**. Por ejemplo, `310000CA` y `310000CA.`, o `017593TG..`, `017593TG...` y `017593TG......`. Para SAP son **lotes distintos**; parece que se usan los puntos para diferenciar ingresos del mismo número de lote.
- **Qué hace el sistema:**
  - conserva el lote **exactamente igual**, porque SAP lo exige así en las guías y entregas;
  - ahora explica el aviso: «Lote con puntos o comas al final… Así está registrado en SAP; se carga igual (consulte con Producción si es un error de digitación)».
- **Las 546 filas con aviso** incluyen esos 298 lotes y otros avisos de la misma carga. Por ejemplo:
  - almacenes de tránsito de Producción (ALM-003: 133 filas, no reservables hasta validarse);
  - almacenes no configurados o no habilitados;
  - artículos que no estaban en el catálogo.

  Con el nuevo resumen por tipo de aviso se ven separados.
- **Recomendación:** conviene confirmar con Producción si los puntos son una práctica para diferenciar lotes o un error de digitación. Si es un error, se corrige en SAP; el módulo no debe cambiar el lote por su cuenta.

## 7. Movimientos punto a punto en el celular

En el celular, las fotos de inicio y de fin se superponían sobre la hora y la duración. Ahora cada foto sale como miniatura **debajo de su hora**, con «Ver foto», en dos columnas que se acomodan al ancho de la pantalla.

## 8. Datos técnicos

- `app/__init__.py`: `_set_timezone()` (`APP_TZ`).
- `app/services/errores.py`: código del fallo, registro y búsqueda.
- `views/common.py`:
  - `act()` muestra la ventana con el código ante errores de base de datos o inesperados;
  - `paginate()` y `Pagina`.
- Plantillas:
  - macros `paginacion` y `fallo_modal` en `_m.html`;
  - `_carga.html` (gato y velo);
  - `errores.html`.
- `static/v19.js`: velo, carga parcial de `[data-lista]`, descargas con la cookie `descarga`, ventana de fallos.
- La vista que sirve el archivo responde con la cookie `descarga` cuando la petición trae `_dl`; así el velo se quita al terminar la descarga.
- Pruebas: `tests/test_v19.py`.
