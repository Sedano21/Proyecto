/* V77 (27-nov-2026): menú lateral plegable por área.
   Los perfiles con muchas opciones (gerencias, jefaturas) veían una lista muy larga. Ahora:
   - cada área (Comercial, Almacén, Producción…) conserva su título y tiene una flecha a la derecha; al tocarlo se
     despliega o se pliega;
   - el área de la pantalla abierta se despliega sola; las demás quedan como el usuario las dejó (se recuerda en este
     dispositivo);
   - «Áreas» pliega o despliega todas a la vez;
   - «Buscar en el menú» filtra las opciones al escribir y abre las áreas donde hay coincidencias.
   No cambia qué opciones ve cada perfil: eso lo sigue decidiendo el servidor con los permisos. Se ejecuta antes de
   v76.js, para que el menú anclado lleve a la opción activa ya visible. */
(function () {
  'use strict';
  var nav = document.querySelector('.side .nav-scroll');
  if (!nav) return;
  /* Panel general (sin encabezado): Inicio, Bandeja de gerencia, Mi ruta y Alertas quedan siempre a la vista, arriba;
     si además tiene muchas opciones (gerencias), el resto pasa a un área plegable «Panel general». */
  var panel = nav.querySelector(':scope > .grp[data-grupo="Panel"]');
  var FIJAS = ['inicio', 'bandeja de gerencia', 'mi ruta (paso a paso)', 'alertas y tareas'];
  if (panel && !panel.querySelector(':scope > h4')) {
    var pl = [].slice.call(panel.querySelectorAll(':scope > a'));
    var fijas = pl.filter(function (a, i) {
      var l = a.querySelector('.lbl');
      return i === 0 || FIJAS.indexOf(((l ? l.textContent : a.textContent) || '').trim().toLowerCase()) >= 0;
    });
    if (pl.length - fijas.length > 4) {
      var resto = pl.filter(function (a) { return fijas.indexOf(a) < 0; });
      fijas.forEach(function (a) { a.classList.add('fija'); });
      var h = document.createElement('h4');
      h.innerHTML = '<span class="lbl">Panel general</span>';
      panel.insertBefore(h, resto[0]); // fijas arriba (en su orden), luego el encabezado y el resto
      fijas.slice().reverse().forEach(function (a) { panel.insertBefore(a, panel.firstChild); });
    }
  }
  var grupos = [].slice.call(nav.querySelectorAll(':scope > .grp')).filter(function (g) { return g.querySelector(':scope > h4'); });
  if (grupos.length < 2) return; // con una sola área no hay nada que plegar

  var K = 'cp-nav-grupos';
  var estado = {};
  try { estado = JSON.parse(localStorage.getItem(K) || '{}') || {}; } catch (e) { estado = {}; }
  function guardar() { try { localStorage.setItem(K, JSON.stringify(estado)); } catch (e) {} }
  function norm(t) { return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim(); }

  var vistos = {};
  var items = grupos.map(function (g, i) {
    var nombre = g.dataset.grupo || ('grupo' + i);
    vistos[nombre] = (vistos[nombre] || 0) + 1;
    var clave = vistos[nombre] > 1 ? nombre + '#' + vistos[nombre] : nombre; // p. ej. dos bloques «Distribución»
    var h4 = g.querySelector(':scope > h4');
    var links = [].slice.call(g.querySelectorAll(':scope > a:not(.fija)'));
    var id = 'nav-g' + i;
    g.id = g.id || id;
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'grp-tog';
    b.setAttribute('aria-controls', g.id);
    var titulo = (h4.textContent || nombre).trim();
    b.innerHTML = '<span class="grp-t"></span><svg class="ic grp-chev" aria-hidden="true"><use href="#i-chevron"/></svg>';
    b.querySelector('.grp-t').textContent = titulo;
    h4.textContent = '';
    h4.appendChild(b);
    h4.classList.add('grp-h');
    return { g: g, b: b, clave: clave, links: links, activa: !!g.querySelector(':scope > a.on:not(.fija)') };
  });

  function aplicar(it, abierta) {
    it.g.classList.toggle('plegado', !abierta);
    it.b.setAttribute('aria-expanded', abierta ? 'true' : 'false');
    it.b.title = (abierta ? 'Plegar ' : 'Desplegar ') + it.b.querySelector('.grp-t').textContent;
  }
  // por defecto: plegadas, salvo el área de la pantalla abierta (siempre visible) y las que el usuario dejó abiertas
  items.forEach(function (it) { aplicar(it, it.activa || estado[it.clave] === true); });
  items.forEach(function (it) {
    it.b.addEventListener('click', function () {
      var abrir = it.g.classList.contains('plegado');
      aplicar(it, abrir);
      estado[it.clave] = abrir;
      guardar();
      sincTodas();
    });
  });

  /* encabezado «Áreas»: plegar o desplegar todo; y buscador del menú */
  var barra = document.createElement('div');
  barra.className = 'nav-tools lbl';
  barra.innerHTML = '<button type="button" class="grp-all"><span class="grp-t">Áreas</span>' +
    '<svg class="ic grp-chev" aria-hidden="true"><use href="#i-chevron"/></svg></button>' +
    '<input type="search" class="nav-q" placeholder="Buscar en el menú…" aria-label="Buscar en el menú" autocomplete="off">';
  nav.insertBefore(barra, nav.firstChild);
  var todas = barra.querySelector('.grp-all'), q = barra.querySelector('.nav-q');
  function sincTodas() {
    var alguna = items.some(function (it) { return !it.g.classList.contains('plegado'); });
    todas.setAttribute('aria-expanded', alguna ? 'true' : 'false');
    todas.title = alguna ? 'Plegar todas las áreas' : 'Desplegar todas las áreas';
  }
  todas.addEventListener('click', function () {
    var abrir = todas.getAttribute('aria-expanded') !== 'true';
    items.forEach(function (it) { aplicar(it, abrir || it.activa); estado[it.clave] = abrir; });
    guardar();
    sincTodas();
  });
  sincTodas();

  // búsqueda: muestra solo las opciones que coinciden (en todas las áreas, también en el panel general)
  var todosLinks = [].slice.call(nav.querySelectorAll('.grp > a'));
  q.addEventListener('input', function () {
    var t = norm(q.value);
    nav.classList.toggle('buscando', !!t);
    todosLinks.forEach(function (a) {
      var ok = !t || norm(a.textContent).indexOf(t) >= 0 || norm((a.closest('.grp') || {}).dataset && a.closest('.grp').dataset.grupo).indexOf(t) >= 0;
      a.classList.toggle('nav-oculto', !ok);
    });
    [].forEach.call(nav.querySelectorAll('.grp'), function (g) {
      g.classList.toggle('sin-coincidencias', !!t && !g.querySelector(':scope > a:not(.nav-oculto)'));
    });
  });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && q.value) { e.stopPropagation(); q.value = ''; q.dispatchEvent(new Event('input')); }
    if (e.key === 'Enter') { // Enter abre la primera coincidencia
      var a = nav.querySelector('.grp > a:not(.nav-oculto)');
      if (q.value && a) { e.preventDefault(); location.href = a.href; }
    }
  });
})();
