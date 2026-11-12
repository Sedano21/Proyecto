/* V30 (12-nov-2026)
   1. Filas plegables: un botón «+» (data-tg="id de la fila de detalle") muestra u oculta el detalle debajo y pasa a «−».
   2. «Marcar todos»: una casilla con data-checkall="nombre" marca o desmarca las casillas con ese nombre. */
(function () {
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tg]');
    if (!b) return;
    var fila = document.getElementById(b.getAttribute('data-tg'));
    if (!fila) return;
    var abrir = fila.hidden;
    fila.hidden = !abrir;
    b.textContent = abrir ? '−' : '+';
    b.setAttribute('aria-expanded', abrir ? 'true' : 'false');
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tg-all]');
    if (!b) return;
    var abrir = b.getAttribute('data-estado') !== 'abierto';
    document.querySelectorAll('[data-tg]').forEach(function (t) {
      var fila = document.getElementById(t.getAttribute('data-tg'));
      if (!fila) return;
      fila.hidden = !abrir;
      t.textContent = abrir ? '−' : '+';
      t.setAttribute('aria-expanded', abrir ? 'true' : 'false');
    });
    b.setAttribute('data-estado', abrir ? 'abierto' : '');
    b.textContent = abrir ? 'Plegar todo' : 'Desplegar todo';
  });
  document.addEventListener('change', function (e) {
    var c = e.target;
    if (!c.matches || !c.matches('[data-checkall]')) return;
    var form = c.form || document;
    form.querySelectorAll('input[type=checkbox][name="' + c.getAttribute('data-checkall') + '"]').forEach(function (x) {
      x.checked = c.checked;
    });
  });
})();
