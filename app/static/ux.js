/* Componentes de interfaz de la ronda UX (24-oct-2026): divulgación progresiva y formularios dinámicos.
   1. Ventanas (modal) y paneles laterales (drawer): <dialog class="modal|drawer" id="x"> + botón [data-open="x"].
   2. Asistente por pasos: <form class="wizard"> con secciones .wz-step; botones [data-next] / [data-prev].
   3. Tarjetas según cantidad: <input data-repeat="#destino" data-template="#plantilla"> crea solo N tarjetas.
   4. Horas en formato 12 h o 24 h: <input data-hora> valida y normaliza.
   5. Selector con búsqueda: <select data-search> agrega un filtro rápido encima de la lista.
   6. Validación en tiempo real del producto y el paquete (parte de producción): [data-product-info].
   7. Recarga periódica de un panel: [data-refresh="segundos"]. */
(function () {
  'use strict';
  function $all(sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); }

  /* 1. modales y paneles laterales */
  document.addEventListener('click', function (e) {
    var op = e.target.closest('[data-open]');
    if (op) {
      var d = document.getElementById(op.getAttribute('data-open').replace(/^#/, ''));
      if (d && d.showModal) {
        e.preventDefault();
        Object.keys(op.dataset).forEach(function (k) {
          if (k.indexOf('set') === 0 && k.length > 3) {
            var name = k.slice(3).replace(/^[A-Z]/, function (c) { return c.toLowerCase(); }).replace(/[A-Z]/g, function (c) { return '_' + c.toLowerCase(); });
            $all('[name="' + name + '"]', d).forEach(function (el) { el.value = op.dataset[k]; });
            $all('[data-show="' + name + '"]', d).forEach(function (el) { el.textContent = op.dataset[k]; });
          }
        });
        d.showModal();
        var f = d.querySelector('input:not([type=hidden]),select,textarea'); if (f) try { f.focus(); } catch (err) {}
      }
      return;
    }
    var cl = e.target.closest('[data-close]');
    if (cl) { var dd = cl.closest('dialog'); if (dd) { e.preventDefault(); dd.close(); } }
  });
  $all('dialog.modal, dialog.drawer').forEach(function (d) {
    d.addEventListener('click', function (e) { if (e.target === d) d.close(); });
    if (d.hasAttribute('data-autoopen')) { try { d.showModal(); } catch (err) {} }
  });

  /* 2. asistente por pasos */
  $all('form.wizard').forEach(function (f) {
    var steps = $all('.wz-step', f), nav = f.querySelector('.steps'), i = 0;
    function show(n) {
      i = Math.max(0, Math.min(n, steps.length - 1));
      steps.forEach(function (s, k) { s.hidden = k !== i; });
      if (nav) $all('li', nav).forEach(function (li, k) { li.className = k < i ? 'done' : (k === i ? 'now' : ''); });
    }
    function valid(step) {
      var ok = true;
      $all('input,select,textarea', step).forEach(function (el) { if (ok && el.willValidate && !el.checkValidity()) { el.reportValidity(); ok = false; } });
      return ok;
    }
    f.addEventListener('click', function (e) {
      if (e.target.closest('[data-next]')) { e.preventDefault(); if (valid(steps[i])) show(i + 1); }
      if (e.target.closest('[data-prev]')) { e.preventDefault(); show(i - 1); }
    });
    var err = steps.findIndex ? steps.findIndex(function (s) { return s.querySelector('.invalid'); }) : -1;
    show(err > 0 ? err : 0);
  });

  /* 3. tarjetas según cantidad (sin filas vacías fijas) */
  $all('[data-repeat]').forEach(function (inp) {
    var box = document.querySelector(inp.getAttribute('data-repeat')),
        tpl = document.querySelector(inp.getAttribute('data-template')),
        max = parseInt(inp.getAttribute('data-max') || '50', 10);
    if (!box || !tpl) return;
    function render() {
      var n = Math.max(0, Math.min(parseInt(inp.value || '0', 10) || 0, max)), cur = box.children.length;
      for (var k = cur; k < n; k++) {
        var html = tpl.innerHTML.replace(/__N__/g, String(k + 1));
        var wrap = document.createElement('div'); wrap.innerHTML = html.trim();
        box.appendChild(wrap.firstElementChild);
      }
      while (box.children.length > n) box.removeChild(box.lastElementChild);
      var empty = document.querySelector(inp.getAttribute('data-empty') || '#none');
      if (empty) empty.hidden = n > 0;
      box.dispatchEvent(new Event('repeat'));
    }
    inp.addEventListener('input', render); render();
  });
  /* no repetir el mismo colaborador en dos tarjetas */
  document.addEventListener('change', function (e) {
    var sel = e.target.closest('select[data-unique]'); if (!sel) return;
    var grupo = sel.getAttribute('data-unique'), usados = {};
    $all('select[data-unique="' + grupo + '"]').forEach(function (s) { if (s.value) usados[s.value] = (usados[s.value] || 0) + 1; });
    $all('select[data-unique="' + grupo + '"]').forEach(function (s) {
      s.setCustomValidity(s.value && usados[s.value] > 1 ? 'Este colaborador ya está en otra tarjeta.' : '');
    });
  });

  /* 4. horas 12 h / 24 h */
  function parseHora(t) {
    t = String(t || '').trim().toLowerCase().replace(/\./g, '').replace(/\s+/g, ' ');
    if (!t) return '';
    var m = t.match(/^(\d{1,2})(?::(\d{2}))?\s*(a ?m|p ?m)?$/);
    if (!m) return null;
    var h = +m[1], mi = +(m[2] || 0), suf = m[3] ? m[3].replace(' ', '') : '';
    if (suf) { if (h < 1 || h > 12) return null; h = (h === 12 ? 0 : h) + (suf === 'pm' ? 12 : 0); }
    if (h > 23 || mi > 59) return null;
    return (h < 10 ? '0' : '') + h + ':' + (mi < 10 ? '0' : '') + mi;
  }
  function fmtHora(hhmm, f12) {
    if (!hhmm || !f12) return hhmm;
    var h = +hhmm.slice(0, 2), m = hhmm.slice(3);
    return ((h % 12) || 12) + ':' + m + (h >= 12 ? ' pm' : ' am');
  }
  function checkHora(el) {
    var v = parseHora(el.value), f12 = (el.getAttribute('data-hora') || '') === '12H';
    if (v === null) { el.setCustomValidity(f12 ? 'Hora inválida (p. ej. 3:30 pm).' : 'Hora inválida (p. ej. 15:30).'); return; }
    el.setCustomValidity('');
    var min = el.getAttribute('data-min-hora'), ref = min && document.querySelector(min);
    var rv = ref ? parseHora(ref.value) : null;
    if (v && rv && v <= rv) el.setCustomValidity('La hora de fin debe ser mayor que la de inicio.');
    var fecha = el.getAttribute('data-fecha') && document.querySelector(el.getAttribute('data-fecha'));
    if (v && fecha && el.hasAttribute('data-no-pasada')) {
      var hoy = new Date(), iso = hoy.toISOString().slice(0, 10), ahora = (hoy.getHours() < 10 ? '0' : '') + hoy.getHours() + ':' + (hoy.getMinutes() < 10 ? '0' : '') + hoy.getMinutes();
      if (fecha.value === iso && v < ahora) el.setCustomValidity('La hora de fin no puede ser menor que la hora actual.');
    }
    if (v && document.activeElement !== el) el.value = fmtHora(v, f12);
  }
  document.addEventListener('input', function (e) { if (e.target.matches && e.target.matches('[data-hora]')) checkHora(e.target); });
  document.addEventListener('blur', function (e) { if (e.target.matches && e.target.matches('[data-hora]')) checkHora(e.target); }, true);

  /* 5. selector con búsqueda */
  $all('select[data-search]').forEach(function (sel) {
    var q = document.createElement('input');
    q.type = 'search'; q.placeholder = sel.getAttribute('data-search') || 'Buscar…'; q.className = 'select-search';
    q.setAttribute('aria-label', q.placeholder);
    sel.parentNode.insertBefore(q, sel);
    var opts = $all('option', sel);
    q.addEventListener('input', function () {
      var t = q.value.trim().toLowerCase(), first = null;
      opts.forEach(function (o) { var ok = !o.value || o.text.toLowerCase().indexOf(t) >= 0; o.hidden = !ok; if (ok && o.value && !first) first = o; });
      if (t && first && (sel.selectedOptions[0] || {}).hidden !== false) sel.value = first.value;
    });
  });

  /* 6. validación en tiempo real del producto y el paquete */
  $all('form[data-product-info]').forEach(function (f) {
    var url = f.getAttribute('data-product-info'), out = f.querySelector('.live-check'), info = null;
    function v(n) { var el = f.querySelector('[name="' + n + '"]'); return el ? el.value : ''; }
    function set(n, val) { var el = f.querySelector('[name="' + n + '"]'); if (el && !el.value && val != null) el.value = val; }
    function check() {
      if (!out) return;
      var msgs = [], ok = [];
      var pres = parseFloat(v('presentacion_kg')), und = v('und_paquete'), ean = v('ean').trim();
      var linea = v('linea'), env = (f.getAttribute('data-envasado') || '').split(',').indexOf(linea) >= 0;
      if (info) {
        if (env && info.tipo && info.tipo !== 'PT') msgs.push('En envasado se registra producto terminado; ' + info.code + ' es ' + info.tipo + '.');
        if (env && info.presentacion_kg && pres && Math.abs(pres - info.presentacion_kg) > 1e-6) msgs.push('La presentación no corresponde: ' + info.code + ' es de ' + info.presentacion_kg + ' kg.');
        if (ean) { if (info.gtins.indexOf(ean) >= 0) ok.push('EAN coincide con ' + info.code + '.'); else msgs.push(info.gtins.length ? 'El EAN no corresponde a ' + info.code + '.' : 'El EAN no está en la tabla GS1 ↔ SAP.'); }
      }
      if (und && (parseFloat(und) <= 0 || parseFloat(und) % 1 !== 0)) msgs.push('Las unidades por paquete deben ser un entero mayor que cero.');
      var sacos = parseFloat(v('sacos')), ps = parseFloat(v('peso_saco_kg')), saldo = parseFloat(v('saldo_mp_kg')) || 0;
      var kg = sacos && ps ? sacos * ps + saldo : parseFloat(v('peso_entrada_kg'));
      if (kg && pres) ok.push('Producción ideal: ' + Math.floor(kg / pres).toLocaleString('es-PE') + ' unidades' + (und ? ' (' + Math.floor(kg / pres / und).toLocaleString('es-PE') + ' paquetes)' : '') + ' con ' + kg.toLocaleString('es-PE') + ' kg.');
      out.innerHTML = '';
      msgs.forEach(function (m) { var p = document.createElement('div'); p.className = 'chk bad'; p.textContent = '✕ ' + m; out.appendChild(p); });
      ok.forEach(function (m) { var p = document.createElement('div'); p.className = 'chk good'; p.textContent = '✓ ' + m; out.appendChild(p); });
      var prod = f.querySelector('[name="product_code"]');
      if (prod) prod.setCustomValidity(msgs.length ? msgs[0] : '');
    }
    function load() {
      var code = (v('product_code') || '').split(' ')[0];
      if (!code) { info = null; check(); return; }
      fetch(url + '?code=' + encodeURIComponent(code), { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { info = j && j.code ? j : null; if (info && env()) set('presentacion_kg', info.presentacion_kg); check(); }).catch(function () {});
    }
    function env() { return (f.getAttribute('data-envasado') || '').split(',').indexOf(v('linea')) >= 0; }
    f.addEventListener('change', function (e) { if (e.target.name === 'product_code' || e.target.name === 'linea') load(); else check(); });
    f.addEventListener('input', function (e) { if (e.target.name !== 'product_code') check(); });
    load();
  });

  /* cálculo en vivo al finalizar el parte: unidades, rendimiento y desmedro */
  $all('form[data-live-yield]').forEach(function (f) {
    var d = JSON.parse(f.getAttribute('data-live-yield')), out = f.querySelector('.live-check');
    function num(n) { return $all('[name="' + n + '"]', f).reduce(function (a, el) { return a + (parseFloat(el.value) || 0); }, 0); }
    function calc() {
      var entrada = d.entrada || 0, salida, msgs = [];
      if (d.tipo === 'ENVASADO') {
        var paq = num('pallet_cantidad'), sueltas = num('unidades_sueltas'), und = paq ? paq * (d.und || 1) + sueltas : num('unidades');
        if (d.und && sueltas >= d.und) msgs.push('Las unidades sueltas completan un paquete: regístrelo en el pallet.');
        salida = und * (d.pres || 0);
        msgs.unshift(und.toLocaleString('es-PE') + ' unidades');
      } else { salida = num('granel_kg') || num('pallet_cantidad'); }
      var rend = entrada ? 100 * salida / entrada : 0, desm = d.tipo === 'ENVASADO' ? 100 - rend : (entrada ? 100 * num('desmedro_kg') / entrada : 0);
      var txt = 'Rendimiento ' + rend.toFixed(1) + ' % · desmedro ' + Math.max(desm, 0).toFixed(1) + ' %';
      var bad = (d.min != null && rend < d.min) || (d.max != null && rend > d.max);
      out.innerHTML = '<div class="chk ' + (bad ? 'bad' : 'good') + '">' + (bad ? '✕ ' : '✓ ') + txt +
        (bad ? ' — fuera del rango ' + (d.min != null ? d.min : '…') + '–' + (d.max != null ? d.max : '…') + ' % (la liquidación se bloqueará)' : '') + '</div>' +
        msgs.map(function (m) { return '<div class="chk">' + m + '</div>'; }).join('');
    }
    f.addEventListener('input', calc); calc();
  });

  /* 8. firma en pantalla: <canvas data-signature="campo_oculto"> */
  $all('canvas[data-signature]').forEach(function (cv) {
    var form = cv.closest('form'), hid = form && form.querySelector('[name="' + cv.getAttribute('data-signature') + '"]');
    var ctx = cv.getContext('2d'), drawing = false, drawn = false;
    function size() { var r = cv.getBoundingClientRect(); if (r.width) { cv.width = r.width; cv.height = r.height; ctx.lineWidth = 2.2; ctx.lineCap = 'round'; ctx.strokeStyle = '#13201a'; } }
    function pt(e) { var r = cv.getBoundingClientRect(), t = e.touches ? e.touches[0] : e; return [t.clientX - r.left, t.clientY - r.top]; }
    function down(e) { if (!cv.width) size(); drawing = true; var p = pt(e); ctx.beginPath(); ctx.moveTo(p[0], p[1]); e.preventDefault(); }
    function move(e) { if (!drawing) return; var p = pt(e); ctx.lineTo(p[0], p[1]); ctx.stroke(); drawn = true; e.preventDefault(); }
    function up() { if (drawing && drawn && hid) { hid.value = cv.toDataURL('image/png'); hid.setCustomValidity(''); } drawing = false; }
    cv.addEventListener('mousedown', down); cv.addEventListener('mousemove', move); window.addEventListener('mouseup', up);
    cv.addEventListener('touchstart', down, { passive: false }); cv.addEventListener('touchmove', move, { passive: false }); cv.addEventListener('touchend', up);
    var clr = form && form.querySelector('[data-clear-signature]');
    if (clr) clr.addEventListener('click', function (e) { e.preventDefault(); ctx.clearRect(0, 0, cv.width, cv.height); drawn = false; if (hid) hid.value = ''; });
    var dlg = cv.closest('dialog');
    if (form) form.addEventListener('submit', function (e) {
      if (hid && !hid.value) { e.preventDefault(); alert('Falta la firma de quien recibe.'); }
    });
    new MutationObserver(function () { if (cv.offsetWidth && cv.width !== cv.offsetWidth) size(); }).observe(dlg || document.body, { attributes: true, subtree: true, attributeFilter: ['open', 'hidden'] });
  });

  /* 9. «Volver»: pila de pantallas visitadas en la pestaña (sin repetir la misma al guardar un formulario) */
  (function () {
    var KEY = 'cp-nav', here = location.pathname + location.search, pila = [];
    try { pila = JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch (e) { pila = []; }
    var back = document.querySelector('[data-back]');
    if (pila.length && pila[pila.length - 1] === here) { /* recarga o guardado en la misma pantalla */ }
    else if (pila.length > 1 && pila[pila.length - 2] === here && sessionStorage.getItem('cp-nav-back') === '1') { pila.pop(); }
    else { pila.push(here); }
    try { sessionStorage.removeItem('cp-nav-back'); sessionStorage.setItem(KEY, JSON.stringify(pila.slice(-30))); } catch (e) {}
    if (!back || pila.length < 2 || location.pathname === '/' ) return;
    var prev = pila[pila.length - 2];
    back.href = prev; back.hidden = false;
    back.addEventListener('click', function (e) {
      e.preventDefault();
      try { sessionStorage.setItem('cp-nav-back', '1'); } catch (err) {}
      location.href = prev;
    });
  })();

  /* 10. visor de documentos: la OC, guías, facturas y fotos se abren en una ventana con retorno, sin salir de la pantalla */
  (function () {
    var dlg = null;
    function viewer() {
      if (dlg) return dlg;
      dlg = document.createElement('dialog'); dlg.className = 'modal viewer';
      dlg.innerHTML = '<div class="dlg-head"><h3 class="v-title">Documento</h3><a class="btn sec small v-open" target="_blank" rel="noopener">Abrir en otra pestaña</a>' +
        '<button type="button" class="ibtn v-close" aria-label="Cerrar">✕</button></div><div class="v-body"></div>';
      document.body.appendChild(dlg);
      dlg.querySelector('.v-close').addEventListener('click', function () { dlg.close(); });
      dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
      dlg.addEventListener('close', function () { dlg.querySelector('.v-body').innerHTML = ''; });
      return dlg;
    }
    document.addEventListener('click', function (e) {
      var a = e.target.closest('a[href*="/evidencias/"]');
      if (!a || e.ctrlKey || e.metaKey || e.shiftKey || a.hasAttribute('download')) return;
      e.preventDefault();
      var d = viewer(), url = a.getAttribute('href'), ext = (url.split('?')[0].split('.').pop() || '').toLowerCase();
      d.querySelector('.v-title').textContent = (a.textContent || 'Documento').trim() || 'Documento';
      d.querySelector('.v-open').href = url;
      var body = d.querySelector('.v-body');
      if (['jpg', 'jpeg', 'png', 'webp', 'gif'].indexOf(ext) >= 0) {
        var img = document.createElement('img'); img.src = url; img.alt = d.querySelector('.v-title').textContent; body.appendChild(img);
      } else if (ext === 'pdf') {
        var f = document.createElement('iframe'); f.src = url; f.title = 'Documento'; body.appendChild(f);
      } else {
        body.innerHTML = '<p class="small">Este tipo de archivo no se puede mostrar aquí. Use «Abrir en otra pestaña» para descargarlo.</p>';
      }
      d.showModal();
    });
  })();

  /* 11. borrador de la pantalla: si sale a otra pestaña (p. ej. la ficha del cliente) y vuelve, lo escrito sigue ahí */
  $all('form[data-borrador]').forEach(function (f) {
    var key = 'cp-borrador:' + location.pathname + ':' + (f.id || 'f');
    function campos() { return $all('input,select,textarea', f).filter(function (el) {
      var t = (el.type || '').toLowerCase(); return el.name && el.name !== '_csrf' && ['file', 'password', 'hidden', 'submit', 'button'].indexOf(t) < 0; }); }
    try {
      var raw = sessionStorage.getItem(key);
      if (raw && !document.querySelector('.flash.error')) {
        var st = JSON.parse(raw), cnt = {};
        var add = f.querySelector('[data-addrow]'), guard = 0;
        var falta = function () { return Object.keys(st).some(function (n) { return f.querySelectorAll('[name="' + n + '"]').length && f.querySelectorAll('[name="' + n + '"]').length < st[n].length; }); };
        while (add && falta() && guard++ < 100) add.click();
        campos().forEach(function (el) {
          var i = cnt[el.name] = (cnt[el.name] || 0); cnt[el.name]++;
          var v = (st[el.name] || [])[i]; if (v === undefined) return;
          if (el.type === 'checkbox' || el.type === 'radio') el.checked = v === true || v === el.value; else el.value = v;
        });
        var aviso = document.createElement('div'); aviso.className = 'flash info noprint';
        aviso.innerHTML = '<span>Recuperamos lo que estaba escribiendo. </span>';
        var b = document.createElement('button'); b.type = 'button'; b.className = 'small sec'; b.textContent = 'Empezar de nuevo';
        b.addEventListener('click', function () { try { sessionStorage.removeItem(key); } catch (e) {} location.reload(); });
        aviso.appendChild(b); f.parentNode.insertBefore(aviso, f);
      }
    } catch (e) {}
    var tm = null;
    function guardar() {
      var st = {};
      campos().forEach(function (el) { (st[el.name] = st[el.name] || []).push(el.type === 'checkbox' || el.type === 'radio' ? (el.checked ? el.value : false) : el.value); });
      try { sessionStorage.setItem(key, JSON.stringify(st)); } catch (e) {}
    }
    f.addEventListener('input', function () { clearTimeout(tm); tm = setTimeout(guardar, 400); });
    f.addEventListener('change', guardar);
    f.addEventListener('submit', function () { try { sessionStorage.removeItem(key); } catch (e) {} });
  });

  /* 12. filas dinámicas «+»: <button type="button" data-addrow="#tbody"> clona la última fila vacía;
     [data-delrow] dentro de la fila la quita (siempre queda una). */
  document.addEventListener('click', function (e) {
    var add = e.target.closest('[data-addrow]');
    if (add) {
      var box = document.querySelector(add.getAttribute('data-addrow')); if (!box) return;
      var filas = box.querySelectorAll(':scope > .dynrow'), ult = filas[filas.length - 1]; if (!ult) return;
      var max = parseInt(add.getAttribute('data-max'), 10) || 60; if (filas.length >= max) return;
      var n = ult.cloneNode(true);
      $all('input,select,textarea', n).forEach(function (el) {
        if (el.type === 'checkbox' || el.type === 'radio') el.checked = false;
        else if (el.tagName === 'SELECT') el.selectedIndex = 0; else if (el.type !== 'hidden' || el.hasAttribute('data-clear')) el.value = '';
        el.removeAttribute('required'); el.classList.remove('falta');
      });
      ult.parentNode.insertBefore(n, ult.nextSibling);
      var foco = n.querySelector('input:not([type=hidden]),select'); if (foco) foco.focus();
      box.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    var del = e.target.closest('[data-delrow]');
    if (del) {
      var fila = del.closest('.dynrow'), cont = fila && fila.parentNode;
      if (!fila || cont.querySelectorAll(':scope > .dynrow').length <= 1) return;
      fila.remove(); cont.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });

  /* 7. recarga periódica */
  $all('[data-refresh]').forEach(function (el) {
    var s = parseInt(el.getAttribute('data-refresh'), 10) || 60;
    setInterval(function () {
      if (document.hidden || document.querySelector('dialog[open]') || el.querySelector('iframe:not([hidden]), details[open]')) return;
      fetch(location.href, { credentials: 'same-origin' }).then(function (r) { return r.text(); }).then(function (h) {
        var doc = new DOMParser().parseFromString(h, 'text/html'), nuevo = doc.getElementById(el.id);
        if (nuevo) el.innerHTML = nuevo.innerHTML;
      }).catch(function () {});
    }, s * 1000);
  });
})();
