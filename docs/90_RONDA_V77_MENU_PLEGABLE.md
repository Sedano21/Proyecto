# Ronda V77 (27-nov-2026): menú lateral plegable por área

Fuente: el mensaje del usuario del 27-nov. Pidió un menú que se despliegue por categorías, como el de la imagen de
referencia, porque hay perfiles con muchas opciones.

## Qué se hizo
- **Áreas plegables:** cada área del menú (Comercial, Finanzas, Almacén, Producción, Calidad, Abastecimiento,
  Distribución, Mantenimiento, Administración, Marcha blanca…) tiene un encabezado con:
  - una flecha que indica si está abierta o cerrada;
  - un cuadro de color propio del área;
  - la cantidad de opciones que tiene.

  Al tocar el encabezado se despliega o se pliega.
- **Qué queda abierto:**
  - El área de la pantalla abierta se despliega sola.
  - Las demás quedan como el usuario las dejó, y se recuerda en ese dispositivo.
  - La primera vez, todas empiezan plegadas.
- **Panel general:** Inicio, Bandeja de gerencia, Mi ruta y Alertas y tareas quedan siempre a la vista, arriba.
  - Si el panel tiene muchas opciones más (gerencias), estas pasan al área plegable «Panel general».
  - Con pocas opciones (p. ej. el Auxiliar de Despacho), el panel no cambia.
- **«Áreas»:** pliega o despliega todas las áreas a la vez.
- **Buscar en el menú:**
  - Muestra solo las opciones que coinciden mientras se escribe, sin importar tildes, y abre las áreas donde las hay.
  - Enter abre la primera coincidencia y Esc limpia la búsqueda.
- **Menú contraído a íconos (escritorio):** se ven todos los íconos, sin encabezados ni buscador, como antes.
- **Celular y tablet:** el mismo menú plegable dentro del panel que se abre con el botón de menú.

## Qué no cambia
- **Opciones visibles:** cada perfil sigue viendo las mismas. Las sigue decidiendo el servidor con los permisos. El
  plegado se hace en el navegador (`app/static/v77.js`) sobre los grupos que ya arma `base.html`.
- **Servidor:** no hay cambios en la base de datos, ni migraciones, ni variables del servidor.
- **Menú anclado (V76):** se mantiene. `v77.js` se carga antes que `v76.js`, para que el menú se desplace hasta la opción
  activa cuando ya está visible.

## Pruebas
- `tests/test_v77.py`: 3 pruebas.
  - La página carga el script antes del menú anclado.
  - Los grupos tienen su encabezado.
  - Un perfil con pocas opciones no ve más de lo que le corresponde.
- **En navegador, con los datos de demostración:**
  - perfiles: Gerencia General y Auxiliar de Despacho;
  - pantallas: escritorio, menú contraído a íconos y celular;
  - casos: plegar y desplegar, «Áreas», búsqueda y área activa al navegar.

  No hubo errores de JavaScript.
