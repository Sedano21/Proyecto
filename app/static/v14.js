/* Indicaciones del 31-oct-2026 (V14), para laptop, tablet y celular:
   1. Hora: lista de horas y de minutos con flechas para sumar o restar minutos y botón «Ahora» (reemplaza el reloj
      del navegador en <input type="time"> y <input data-hora>).
   2. Fotos y archivos: «Galería» o «Cámara» (toma la foto en el momento) y, donde se aceptan varios, «+ Añadir otro»
      para sumar uno a uno; vista previa de cada foto.
   3. Las fotos ya guardadas se ven en miniatura junto al registro (no solo como enlace).
   Todo funciona por delegación de eventos, así que también sirve en filas que se agregan con «+». */
(function () {
  'use strict';
  function $all(sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function parse(v) {
    var m = String(v || '').trim().match(/^(\d{1,2}):(\d{2})\s*([ap]\.?\s*m\.?)?$/i);
    if (!m) return null;
    var h = +m[1], mi = +m[2];
    if (m[3]) { var pm = /^p/i.test(m[3]); if (h === 12) h = 0; if (pm) h += 12; }
    return h < 24 && mi < 60 ? [h, mi] : null;
  }

  /* ---------------------------------------------------------------- 1. hora */
  function hourWidget(inp) {
    if (inp.dataset.v14 || inp.closest('[data-hora-nativa]')) return;
    inp.dataset.v14 = '1';
    var w = document.createElement('span');
    w.className = 'hm';
    var hs = '<option value="">hh</option>', ms = '<option value="">mm</option>';
    for (var h = 0; h < 24; h++) hs += '<option value="' + h + '">' + pad(h) + '</option>';
    for (var m = 0; m < 60; m++) ms += '<option value="' + m + '">' + pad(m) + '</option>';
    w.innerHTML = '<button type="button" class="hm-b" data-hm="-5" aria-label="Restar 5 minutos">«</button>' +
      '<button type="button" class="hm-b" data-hm="-1" aria-label="Restar 1 minuto">‹</button>' +
      '<select class="hm-h" aria-label="Hora">' + hs + '</select><b>:</b><select class="hm-m" aria-label="Minutos">' + ms + '</select>' +
      '<button type="button" class="hm-b" data-hm="1" aria-label="Sumar 1 minuto">›</button>' +
      '<button type="button" class="hm-b" data-hm="5" aria-label="Sumar 5 minutos">»</button>' +
      '<button type="button" class="hm-now" data-hm="now">Ahora</button>';
    inp.classList.add('hm-src');
    inp.parentNode.insertBefore(w, inp.nextSibling);
    if (inp.required) { w.querySelector('.hm-h').required = true; w.querySelector('.hm-m').required = true; inp.required = false; }
    if (inp.disabled || inp.readOnly) $all('select,button', w).forEach(function (x) { x.disabled = true; });
    paint(inp, w);
  }
  function paint(inp, w) {
    var t = parse(inp.value);
    w.querySelector('.hm-h').value = t ? String(t[0]) : '';
    w.querySelector('.hm-m').value = t ? String(t[1]) : '';
  }
  function setT(w, h, m) {
    var inp = w.previousElementSibling;
    var tot = ((h * 60 + m) % 1440 + 1440) % 1440;
    inp.value = pad(Math.floor(tot / 60)) + ':' + pad(tot % 60);
    paint(inp, w);
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.hm [data-hm]');
    if (!b) return;
    var w = b.closest('.hm'), inp = w.previousElementSibling, k = b.getAttribute('data-hm');
    if (k === 'now') { var d = new Date(); setT(w, d.getHours(), d.getMinutes()); return; }
    var t = parse(inp.value);
    if (!t) { var n = new Date(); t = [n.getHours(), n.getMinutes()]; }
    setT(w, t[0], t[1] + (+k));
  });
  document.addEventListener('change', function (e) {
    var s = e.target.closest('.hm select');
    if (!s) return;
    var w = s.closest('.hm'), h = w.querySelector('.hm-h').value, m = w.querySelector('.hm-m').value;
    var inp = w.previousElementSibling;
    if (h === '' && m === '') { inp.value = ''; return; }
    setT(w, +(h || 0), +(m || 0));
  });

  /* ---------------------------------------------------------------- 2. fotos y archivos */
  var esImagen = function (inp) { return /image/.test(inp.getAttribute('accept') || '') || !inp.getAttribute('accept'); };
  function fileWidget(inp) {
    if (inp.dataset.v14 || inp.hasAttribute('data-plain')) return;
    inp.dataset.v14 = '1';
    var multi = inp.multiple;
    inp.multiple = false;  // una por fila; «+ Añadir otro» suma filas con el mismo nombre
    inp.removeAttribute('capture');
    var box = document.createElement('div');
    box.className = 'fu';
    if (multi) box.dataset.multi = '1';
    inp.parentNode.insertBefore(box, inp);
    var row = document.createElement('div');
    row.className = 'fu-row';
    box.appendChild(row);
    row.appendChild(inp);
    inp.classList.add('fu-in');
    var img = esImagen(inp);
    row.insertAdjacentHTML('beforeend',
      '<button type="button" class="sec small" data-fu="gal">' + (img ? 'Galería / archivo' : 'Elegir archivo') + '</button>' +
      (img ? '<button type="button" class="sec small" data-fu="cam">Cámara</button>' : '') +
      '<span class="fu-name small muted">Ningún archivo</span><img class="fu-prev" alt="" hidden>' +
      '<button type="button" class="ibtn fu-del" data-fu="del" aria-label="Quitar archivo" hidden>×</button>');
    if (multi) box.insertAdjacentHTML('beforeend', '<button type="button" class="sec small fu-add" data-fu="add" hidden>+ Añadir otro</button>');
  }
  function refresh(row) {
    var inp = row.querySelector('.fu-in'), f = inp.files && inp.files[0];
    var nm = row.querySelector('.fu-name'), pv = row.querySelector('.fu-prev'), del = row.querySelector('.fu-del');
    nm.textContent = f ? f.name : 'Ningún archivo';
    del.hidden = !f;
    if (f && /^image\//.test(f.type) && window.URL) { pv.src = URL.createObjectURL(f); pv.hidden = false; } else { pv.hidden = true; pv.removeAttribute('src'); }
    var box = row.closest('.fu'), add = box.querySelector('.fu-add');
    if (add) add.hidden = !$all('.fu-in', box).every(function (i) { return i.files && i.files.length; });
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fu]');
    if (!b) return;
    var k = b.getAttribute('data-fu'), box = b.closest('.fu'), row = b.closest('.fu-row');
    if (k === 'gal' || k === 'cam') {
      var inp = row.querySelector('.fu-in');
      if (k === 'cam') inp.setAttribute('capture', 'environment'); else inp.removeAttribute('capture');
      inp.click();
    } else if (k === 'del') {
      var rows = $all('.fu-row', box);
      if (rows.length > 1) row.remove(); else { row.querySelector('.fu-in').value = ''; refresh(row); }
      var r0 = box.querySelector('.fu-row'); if (r0) refresh(r0);
    } else if (k === 'add') {
      var base = box.querySelector('.fu-row'), n = base.cloneNode(true), ni = n.querySelector('.fu-in');
      ni.value = ''; ni.required = false;
      box.insertBefore(n, b);
      refresh(n);
      n.querySelector('[data-fu="gal"]').focus();
    }
  });
  document.addEventListener('change', function (e) {
    if (e.target.classList && e.target.classList.contains('fu-in')) refresh(e.target.closest('.fu-row'));
  });

  /* ---------------------------------------------------------------- 2b. V15: aviso del sistema operativo
     Si llega una alerta importante y la ventana está minimizada o en otra pestaña: notificación del sistema (Windows,
     Mac, Android) y el título de la pestaña parpadea. El permiso se pide una sola vez, con el primer clic. */
  var parpadeo = null, tituloBase = document.title;
  function pedirPermiso() {
    try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch (e) {}
  }
  document.addEventListener('click', pedirPermiso, { once: true });
  window.cpNotificar = function (titulo, cuerpo, url, importante) {
    if (!document.hidden) return;
    try {
      if ('Notification' in window && Notification.permission === 'granted') {
        var n = new Notification(titulo, { body: cuerpo || '', tag: 'cp-alerta', renotify: true, requireInteraction: !!importante,
                                           icon: '/static/img/logo_corporacion_productiva.png' });
        n.onclick = function () { window.focus(); if (url) location.href = url; n.close(); };
      }
    } catch (e) {}
    if (!parpadeo) {
      var on = false;
      parpadeo = setInterval(function () { on = !on; document.title = on ? '⚠ ' + titulo : tituloBase; }, 1000);
    }
  };
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && parpadeo) { clearInterval(parpadeo); parpadeo = null; document.title = tituloBase; }
  });

  /* ---------------------------------------------------------------- 3. miniaturas de fotos guardadas */
  function thumbs(root) {
    $all('a[href*="/evidencias/"]', root).forEach(function (a) {
      if (a.dataset.v14 || a.querySelector('img') || !/\.(jpe?g|png|webp|gif)(\?|$)/i.test(a.getAttribute('href'))) return;
      a.dataset.v14 = '1';
      a.classList.add('ev-thumb');
      a.setAttribute('target', '_blank');
      var im = document.createElement('img');
      im.src = a.getAttribute('href'); im.alt = a.textContent.trim() || 'foto'; im.loading = 'lazy';
      a.insertBefore(im, a.firstChild);
    });
  }

  function init(root) {
    $all('input[type="time"], input[data-hora]', root).forEach(hourWidget);
    $all('input[type="file"]', root).forEach(fileWidget);
    thumbs(root);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { init(document); });
  else init(document);
  // contenido que llega después (paneles que se recargan solos)
  if (window.MutationObserver) new MutationObserver(function (ms) {
    ms.forEach(function (m) { [].forEach.call(m.addedNodes, function (n) { if (n.nodeType === 1) { thumbs(n); $all('input[type="time"]:not([data-v14]), input[data-hora]:not([data-v14])', n).forEach(hourWidget); $all('input[type="file"]:not([data-v14])', n).forEach(fileWidget); } }); });
  }).observe(document.body, { childList: true, subtree: true });
})();
