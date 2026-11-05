/* Comportamiento común de la interfaz (observaciones al demo v0.7):
   1. Los formularios no se borran: si el servidor rechaza el envío, se restauran los datos escritos y se resalta lo que
      falta completar.
   2. Validación visible: los campos obligatorios vacíos se resaltan con su mensaje, sin perder lo escrito.
   3. Ventana de confirmación para acciones que la piden (atributo data-confirm en el formulario o el botón).
   4. Alertas con sonido por urgencia (V16): urgente = sirena estridente que se repite hasta que se resuelva; media = pitidos
      agudos; baja = dos pitidos cortos. */
(function () {
  'use strict';
  var body = document.body;
  function $all(sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); }
  function store(kind) { try { return window[kind]; } catch (e) { return null; } }
  var ss = store('sessionStorage'), ls = store('localStorage');
  function sget(k) { try { return ss ? ss.getItem(k) : null; } catch (e) { return null; } }
  function sset(k, v) { try { if (ss) ss.setItem(k, v); } catch (e) {} }
  function sdel(k) { try { if (ss) ss.removeItem(k); } catch (e) {} }
  function lget(k) { try { return ls ? ls.getItem(k) : null; } catch (e) { return null; } }
  function lset(k, v) { try { if (ls) ls.setItem(k, v); } catch (e) {} }

  /* ------------------------------------------------------------------ 2. validación visible */
  function campoDe(el) { return el.closest('.fcell, td, label') || el.parentNode; }
  function marcar(el, msg) {
    if (!el || el.type === 'hidden') return;
    el.classList.add('invalid');
    el.setAttribute('aria-invalid', 'true');
    var next = el.nextElementSibling;
    if (!(next && next.classList.contains('field-msg'))) {
      var m = document.createElement('span'); m.className = 'field-msg'; m.setAttribute('role', 'alert');
      el.insertAdjacentElement('afterend', m); next = m;
    }
    next.textContent = msg || el.validationMessage || 'Complete este campo.';
  }
  function limpiar(el) {
    el.classList.remove('invalid'); el.removeAttribute('aria-invalid');
    var next = el.nextElementSibling; if (next && next.classList.contains('field-msg')) next.remove();
  }
  function resumen(form, n) {
    var box = form.querySelector('.form-alert');
    if (!n) { if (box) box.remove(); return; }
    if (!box) { box = document.createElement('div'); box.className = 'form-alert'; box.setAttribute('role', 'alert'); form.insertBefore(box, form.firstChild); }
    box.textContent = n === 1 ? 'Falta completar 1 campo (resaltado). Lo demás que escribió se conserva.'
      : 'Faltan completar ' + n + ' campos (resaltados). Lo demás que escribió se conserva.';
  }
  var pendientes = new Map();
  document.addEventListener('invalid', function (e) {
    var el = e.target, f = el.form; marcar(el);
    if (!f) return;
    if (!pendientes.has(f)) {
      pendientes.set(f, true);
      setTimeout(function () {
        pendientes.delete(f);
        var malos = $all('.invalid', f).filter(function (x) { return x.form === f || f.contains(x); });
        resumen(f, malos.length);
        if (malos[0]) { malos[0].scrollIntoView({ block: 'center', behavior: 'smooth' }); try { malos[0].focus({ preventScroll: true }); } catch (err) {} }
      }, 0);
    }
  }, true);
  function revalidar(e) {
    var el = e.target; if (!el.classList || !el.classList.contains('invalid')) return;
    var ok = el.checkValidity ? el.checkValidity() : true;
    if (ok && (!el.required || String(el.value || '').trim() !== '')) {
      limpiar(el);
      var f = el.form; if (f) resumen(f, $all('.invalid', f).length);
    }
  }
  document.addEventListener('input', revalidar, true);
  document.addEventListener('change', revalidar, true);
  // los obligatorios que solo tienen espacios también se marcan
  document.addEventListener('submit', function (e) {
    var f = e.target, vacios = [];
    $all('[required]', f).forEach(function (el) {
      if (el.disabled || el.type === 'file' || el.type === 'checkbox' || el.type === 'radio' || el.type === 'hidden') return;
      if (String(el.value || '').trim() === '') vacios.push(el);
    });
    if (vacios.length) {
      e.preventDefault(); e.stopImmediatePropagation();
      vacios.forEach(function (el) { marcar(el, 'Complete este campo.'); });
      resumen(f, vacios.length);
      vacios[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, true);

  /* ------------------------------------------------------------------ 3. confirmación */
  var dlg = null;
  function confirmar(msg, ok) {
    if (!window.HTMLDialogElement) { if (window.confirm(msg)) ok(); return; }
    if (!dlg) {
      dlg = document.createElement('dialog'); dlg.className = 'confirm';
      dlg.innerHTML = '<form method="dialog"><h3>Confirme la acción</h3><p class="cmsg"></p>' +
        '<div class="actions"><button value="no" class="sec">Volver y revisar</button> <button value="si" class="primary">Sí, continuar</button></div></form>';
      body.appendChild(dlg);
    }
    dlg.querySelector('.cmsg').textContent = msg;
    dlg.returnValue = '';
    dlg.onclose = function () { if (dlg.returnValue === 'si') ok(); };
    dlg.showModal();
    dlg.querySelector('button[value=si]').focus();
  }
  document.addEventListener('submit', function (e) {
    var f = e.target, b = e.submitter;
    var msg = (b && b.getAttribute('data-confirm')) || f.getAttribute('data-confirm');
    if (!msg || f._confirmado) { f._confirmado = false; return; }
    e.preventDefault(); e.stopImmediatePropagation();
    confirmar(msg, function () {
      f._confirmado = true;
      if (f.requestSubmit) { f.requestSubmit(b || undefined); }
      else { if (b && b.name) { var h = document.createElement('input'); h.type = 'hidden'; h.name = b.name; h.value = b.value; f.appendChild(h); } f.submit(); }
    });
  }, true);

  /* ------------------------------------------------------------------ 1. conservar lo escrito */
  var CLAVE = 'cp-form';
  function serializar(f) {
    var datos = [];
    [].forEach.call(f.elements, function (el) {
      if (!el.name || el.disabled || el.name === '_csrf') return;
      var t = (el.type || '').toLowerCase();
      if (t === 'file' || t === 'password' || t === 'hidden' || t === 'submit' || t === 'button') return;
      if (t === 'checkbox' || t === 'radio') { datos.push([el.name, el.value, el.checked ? 1 : 0]); return; }
      if (el.tagName === 'SELECT' && el.multiple) { datos.push([el.name, [].filter.call(el.options, function (o) { return o.selected; }).map(function (o) { return o.value; }), 2]); return; }
      datos.push([el.name, el.value, -1]);
    });
    return datos;
  }
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (e.defaultPrevented || (f.getAttribute('method') || '').toLowerCase() !== 'post' || f.hasAttribute('data-noguardar')) return;
    if (f.querySelector('input[type="password"]')) return;  // V15: el ingreso no se guarda ni se marca
    var forms = $all('form').filter(function (x) { return x.action === f.action; });
    sset(CLAVE, JSON.stringify({ action: f.action, idx: forms.indexOf(f), datos: serializar(f), t: Date.now() }));
  });
  function restaurar() {
    var raw = sget(CLAVE); sdel(CLAVE);
    if (!raw) return;
    var st; try { st = JSON.parse(raw); } catch (e) { return; }
    var error = document.querySelector('.flash.error');
    if (!error || Date.now() - st.t > 10 * 60 * 1000) return;
    var forms = $all('form').filter(function (x) { return x.action === st.action; });
    var f = forms[st.idx] || forms[0];
    if (!f) return;
    // V21: formularios de un solo botón (p. ej. «Traer de SAP») no tienen nada escrito que conservar
    var escritos = [].filter.call(f.elements, function (el) {
      return el.name && el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button' && el.tagName !== 'BUTTON'; });
    if (!escritos.length) return;
    var porNombre = {};
    st.datos.forEach(function (d) { (porNombre[d[0]] = porNombre[d[0]] || []).push(d); });
    Object.keys(porNombre).forEach(function (n) {
      var lista = porNombre[n];
      var els = function () { return [].filter.call(f.elements, function (x) { return x.name === n && x.type !== 'hidden'; }); };
      var add = f.querySelector('[data-addrow]'), guard = 0;
      while (add && els().length < lista.length && guard++ < 200) add.click();
      var actuales = els();
      lista.forEach(function (d, i) {
        if (d[2] === 0 || d[2] === 1) {
          var c = actuales.filter(function (x) { return x.value === d[1]; })[0] || actuales[i];
          if (c) c.checked = !!d[2];
          return;
        }
        var el = actuales[i]; if (!el) return;
        if (d[2] === 2) { [].forEach.call(el.options, function (o) { o.selected = d[1].indexOf(o.value) >= 0; }); }
        else el.value = d[1];
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
    // resaltar lo que falta: obligatorios vacíos y campos nombrados en el mensaje del servidor
    var txt = error.textContent || '', n = 0;
    $all('[required]', f).forEach(function (el) {
      if (el.type === 'hidden' || el.type === 'file') return;
      if (String(el.value || '').trim() === '') { marcar(el, 'Complete este campo.'); n++; }
    });
    var re = /'([a-z_]+)'/g, m;
    while ((m = re.exec(txt))) { [].forEach.call(f.elements, function (el) { if (el.name === m[1] && !el.classList.contains('invalid')) { marcar(el, txt); n++; } }); }
    var box = document.createElement('div'); box.className = 'form-alert'; box.setAttribute('role', 'alert');
    box.textContent = 'Se conservó lo que escribió. ' + (n ? 'Corrija lo resaltado y vuelva a guardar.' : 'Revise el mensaje y vuelva a guardar.');
    f.insertBefore(box, f.firstChild);
    var first = f.querySelector('.invalid') || f;
    first.scrollIntoView({ block: 'center' });
  }
  restaurar();

  /* ------------------------------------------------------------------ menús de acciones por fila */
  document.addEventListener('click', function (e) {
    $all('details.row-menu[open]').forEach(function (d) { if (!d.contains(e.target)) d.open = false; });
  });

  /* ------------------------------------------------------------------ 4. alertas con sonido */
  var url = body.getAttribute('data-alertas');
  if (!url) return;
  var btn = document.querySelector('.snd-btn');
  var ctx = null;
  function silenciado() { return lget('cp-sound') === 'off'; }
  function pintarBoton() {
    if (!btn) return;
    var off = silenciado();
    btn.classList.toggle('off', off);
    btn.innerHTML = '<svg class="ic" aria-hidden="true" focusable="false"><use href="#i-' + (off ? 'mute' : 'volume') + '"/></svg>';
    btn.setAttribute('aria-label', off ? 'Sonido de alertas silenciado (pulse para activar)' : 'Sonido de alertas activado (pulse para silenciar)');
  }
  function audio() {
    if (!ctx) { var A = window.AudioContext || window.webkitAudioContext; if (!A) return null; ctx = new A(); }
    if (ctx.state === 'suspended') { try { ctx.resume(); } catch (e) {} }
    return ctx;
  }
  ['click', 'keydown', 'touchstart'].forEach(function (ev) { document.addEventListener(ev, function () { audio(); }, { once: true, passive: true }); });
  if (btn) btn.addEventListener('click', function () { lset('cp-sound', silenciado() ? 'on' : 'off'); pintarBoton(); if (!silenciado()) sonar('MEDIA'); });
  pintarBoton();
  /* V16 (02-nov-2026): sonidos por urgencia, estridentes y cambiantes para que el oído no se acostumbre.
     - ALTA (urgente): sirena aguda de ≈4 s en la zona de 2–4 kHz (la más sensible del oído), onda cuadrada o en diente de
       sierra, con uno de varios patrones al azar (barrido, pulsos rápidos o dos tonos) y un leve cambio de tono cada vez;
       se repite hasta que se atienda.
     - MEDIA: tres pitidos agudos dobles (≈1,5 s), también con patrón y tono variables.
     - BAJA: dos pitidos cortos.
     Un compresor permite subir el volumen sin distorsión. */
  var salida = null;
  function destino(c) {
    if (!salida) {
      try { salida = c.createDynamicsCompressor(); salida.threshold.value = -12; salida.knee.value = 6; salida.ratio.value = 12;
            salida.attack.value = 0.002; salida.release.value = 0.1; salida.connect(c.destination); }
      catch (e) { salida = c.destination; }
    }
    return salida;
  }
  function nota(c, f, t0, dur, tipo, vol, f2) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = tipo; o.frequency.setValueAtTime(f, t0);
    if (f2) o.frequency.linearRampToValueAtTime(f2, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.01);
    g.gain.setValueAtTime(vol, t0 + Math.max(0.012, dur - 0.02)); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(destino(c)); o.start(t0); o.stop(t0 + dur + 0.05);
  }
  function azar(n) { return Math.floor(Math.random() * n); }
  var PATRONES = {
    ALTA: [
      function (c, t, k) { for (var i = 0; i < 8; i++) nota(c, 1800 * k, t + i * 0.5, 0.45, 'sawtooth', 0.9, 3600 * k); },          // barrido ascendente
      function (c, t, k) { for (var i = 0; i < 26; i++) nota(c, (i % 4 === 3 ? 2200 : 3100) * k, t + i * 0.15, 0.09, 'square', 0.8); }, // pulsos rápidos
      function (c, t, k) { for (var i = 0; i < 16; i++) nota(c, (i % 2 ? 2400 : 3300) * k, t + i * 0.25, 0.22, 'square', 0.85); },    // dos tonos
      function (c, t, k) { for (var i = 0; i < 5; i++) { nota(c, 3400 * k, t + i * 0.8, 0.35, 'sawtooth', 0.9, 1900 * k);
                                                         nota(c, 2900 * k, t + i * 0.8 + 0.4, 0.3, 'square', 0.85); } }           // caída y golpe
    ],
    MEDIA: [
      function (c, t, k) { for (var i = 0; i < 3; i++) { nota(c, 2600 * k, t + i * 0.45, 0.12, 'square', 0.7); nota(c, 2600 * k, t + i * 0.45 + 0.17, 0.12, 'square', 0.7); } },
      function (c, t, k) { for (var i = 0; i < 3; i++) nota(c, 1600 * k, t + i * 0.4, 0.28, 'sawtooth', 0.7, 3000 * k); },
      function (c, t, k) { [2000, 2600, 3200, 2000, 2600, 3200].forEach(function (f, i) { nota(c, f * k, t + i * 0.2, 0.15, 'square', 0.7); }); }
    ],
    BAJA: [
      function (c, t, k) { nota(c, 1900 * k, t, 0.08, 'square', 0.45); nota(c, 1900 * k, t + 0.14, 0.08, 'square', 0.45); }
    ]
  };
  function sonar(nivel) {
    if (silenciado()) return false;
    var c = audio(); if (!c || c.state !== 'running') return false;
    nivel = nivel === true ? 'ALTA' : (nivel === false || !nivel ? 'MEDIA' : nivel);
    var lista = PATRONES[nivel] || PATRONES.MEDIA;
    var k = 0.92 + Math.random() * 0.16;  // ±8 % de tono en cada aviso
    lista[azar(lista.length)](c, c.currentTime + 0.05, k);
    return true;
  }
  window.cpSonarAlerta = sonar;
  var cont = null;
  function toast(html, importante) {
    if (!cont) { cont = document.createElement('div'); cont.className = 'toasts'; cont.setAttribute('aria-live', 'polite'); body.appendChild(cont); }
    var t = document.createElement('div'); t.className = 'toast' + (importante ? ' crit' : '');
    t.innerHTML = html + '<button type="button" class="tclose" aria-label="Cerrar aviso">×</button>';
    t.querySelector('.tclose').onclick = function () { t.remove(); };
    cont.appendChild(t);
    setTimeout(function () { t.remove(); }, importante ? 30000 : 12000);
  }
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  var intervalo = 60000, repetir = 120000, version = 0;
  var vivo = !!document.querySelector('[data-live]');
  /* Pantallas de alertas y tareas: se actualizan con lo que hacen los demás destinatarios (información siempre
     certera). Si usted está escribiendo en un formulario de esa zona, no se reemplaza: se avisa con un botón. */
  document.addEventListener('input', function (e) { var f = e.target.form; if (f && f.closest('[data-live]')) f.dataset.dirty = '1'; }, true);
  function realzar(root) {
    $all('table.stack', root).forEach(function (t) {
      var hs = [].map.call(t.querySelectorAll('thead th, tr:first-child > th'), function (h) { return h.textContent.trim(); });
      t.querySelectorAll('tr').forEach(function (tr) { [].forEach.call(tr.children, function (td, i) { if (td.tagName === 'TD' && hs[i]) td.setAttribute('data-label', hs[i]); }); });
    });
    $all('table', root).forEach(function (t) {
      if (t.closest('.tw, .tbl, .doc') || t.classList.contains('kv')) return;
      var w = document.createElement('div'); w.className = 'tw'; t.parentNode.insertBefore(w, t); w.appendChild(t);
    });
  }
  function refrescar(forzar) {
    return fetch(location.href, { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.text() : null; }).then(function (html) {
      if (!html) return;
      var doc = new DOMParser().parseFromString(html, 'text/html');
      $all('[data-live][id]').forEach(function (zona) {
        var nueva = doc.getElementById(zona.id); if (!nueva) return;
        var ocupado = zona.contains(document.activeElement) && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)
          || $all('form[data-dirty]', zona).length;
        if (ocupado && !forzar) {
          if (!zona.querySelector('.live-banner')) {
            var b = document.createElement('div'); b.className = 'live-banner'; b.setAttribute('role', 'status');
            b.innerHTML = 'Otro usuario actualizó esta información. <button type="button" class="small">Ver lo último</button>';
            b.querySelector('button').onclick = function () { refrescar(true); };
            zona.insertBefore(b, zona.firstChild);
          }
          return;
        }
        zona.replaceWith(nueva); realzar(nueva);
        nueva.classList.add('live-flash'); setTimeout(function () { nueva.classList.remove('live-flash'); }, 1600);
      });
    }).catch(function () {});
  }
  function consultar() {
    fetch(url + (version ? '?desde=' + version : ''), { credentials: 'same-origin', headers: { 'Accept': 'application/json' } }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d) return;
      intervalo = Math.max(vivo ? 5 : 15, (vivo ? d.actualizar_seg : d.consulta_seg) || 60) * 1000; repetir = Math.max(30, d.repetir_seg || 120) * 1000;
      if (version && d.version > version) {
        if (vivo) refrescar(false);
        (d.cambios || []).forEach(function (c) { if (vivo) toast('<b>' + esc(c.usuario) + ' · ' + esc(c.accion) + '</b><a href="' + c.url + '">' + esc(c.titulo) + '</a>', false); });
      }
      version = d.version || version;
      var dot = document.querySelector('.bell .dot');
      if (d.abiertas && !dot) { var b = document.querySelector('.bell'); if (b) { dot = document.createElement('span'); dot.className = 'dot'; b.appendChild(dot); } }
      if (dot) { if (d.abiertas) dot.textContent = d.abiertas < 100 ? d.abiertas : '99+'; else dot.remove(); }
      var ultimo = parseInt(lget('cp-alert-last') || '0', 10), ahora = Date.now();
      var nuevas = (d.recientes || []).filter(function (a) { return a.id > ultimo; });
      lset('cp-alert-last', String(Math.max(ultimo, d.ultimo_id || 0)));
      var sonó = false;
      if (ultimo && nuevas.length) {
        // suena solo para quien debe actuar, derivar o decidir (decisión del 16-oct); los demás reciben el aviso sin sonido
        var accionables = nuevas.filter(function (a) { return a.tarea; });
        var imp = accionables.some(function (a) { return a.prioridad === 'ALTA'; });
        var nivel = imp ? 'ALTA' : (accionables.some(function (a) { return a.prioridad === 'MEDIA'; }) ? 'MEDIA' : 'BAJA');
        if (accionables.length) sonó = sonar(nivel);
        toast('<b>' + (nuevas.length === 1 ? 'Nueva alerta' : nuevas.length + ' alertas nuevas') + (accionables.length ? '' : ' (información)') + '</b>' + nuevas.slice(0, 3).map(function (a) {
          return '<a href="' + a.url + '">' + esc(a.titulo) + '</a>'; }).join('') + (!accionables.length || sonó || silenciado() ? '' : '<small>Toque la pantalla para activar el sonido.</small>'), imp);
        // V15: si la ventana está minimizada o en otra pestaña, aviso del sistema operativo
        if (window.cpNotificar && (imp || accionables.length)) window.cpNotificar(
          nuevas.length === 1 ? nuevas[0].titulo : nuevas.length + ' alertas nuevas', nuevas.slice(0, 3).map(function (a) { return a.titulo; }).join(' · '),
          nuevas[0].url, imp);
      }
      var ult = parseInt(lget('cp-alert-ring') || '0', 10);
      if (d.criticas > 0 && ahora - ult >= repetir) {
        if (!sonó) sonó = sonar(true);
        if (window.cpNotificar && (!nuevas.length || !ultimo)) window.cpNotificar(d.criticas + ' alerta(s) importante(s) sin resolver', 'Abra el sistema para atenderlas.', url.replace('/estado.json', '?prioridad=ALTA'), true);
        if (!nuevas.length || !ultimo) toast('<b>' + d.criticas + ' alerta(s) importante(s) sin resolver</b><a href="' + url.replace('/estado.json', '?prioridad=ALTA') + '">Ver alertas</a>' +
          (sonó || silenciado() ? '' : '<small>Toque la pantalla para activar el sonido.</small>'), true);
        lset('cp-alert-ring', String(ahora));
      }
    }).catch(function () {}).then(function () { setTimeout(consultar, intervalo); });
  }
  setTimeout(consultar, 1500);
})();

/* Pestañas de detalle: <nav class="tabs"> con enlaces #id y secciones .tabpane (sin JS se ven todas). */
(function () {
  var nav = document.querySelector('.content nav.tabs');
  if (!nav) return;
  var links = [].slice.call(nav.querySelectorAll('a[href^="#"]'));
  var panes = links.map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); }).filter(Boolean);
  if (!panes.length) return;
  function mostrar(id, enfocar) {
    var pane = document.getElementById(id);
    if (!pane || panes.indexOf(pane) < 0) {  // un ancla dentro de una pestaña abre esa pestaña
      var dentro = id && document.getElementById(id);
      pane = dentro ? panes.filter(function (p) { return p.contains(dentro); })[0] : null;
      if (!pane) pane = panes[0];
    }
    panes.forEach(function (p) { p.hidden = p !== pane; });
    links.forEach(function (a) { var on = a.getAttribute('href') === '#' + pane.id; a.classList.toggle('on', on); a.setAttribute('aria-selected', on ? 'true' : 'false'); });
    if (enfocar) nav.scrollIntoView({ block: 'start' });
  }
  links.forEach(function (a) { a.setAttribute('role', 'tab'); a.addEventListener('click', function (e) {
    e.preventDefault(); var id = a.getAttribute('href').slice(1); history.replaceState(null, '', '#' + id); mostrar(id, false); }); });
  nav.setAttribute('role', 'tablist');
  var err = document.querySelector('.flash.error'), inv = document.querySelector('.content form .invalid');
  mostrar(location.hash.slice(1), !!location.hash);
  // si se restauró un formulario con error, se abre su pestaña
  setTimeout(function () { var x = document.querySelector('.content .invalid, .content .form-alert'); if (x) { var p = panes.filter(function (q) { return q.contains(x); })[0]; if (p) mostrar(p.id, false); } }, 50);
  window.addEventListener('hashchange', function () { mostrar(location.hash.slice(1), true); });
  window.addEventListener('beforeprint', function () { panes.forEach(function (p) { p.hidden = false; }); });
})();

/* Menú «más opciones» por fila: se posiciona sobre la página para no quedar recortado por la tabla. */
(function () {
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (!d.classList || !d.classList.contains('row-menu') || !d.open) return;
    document.querySelectorAll('details.row-menu[open]').forEach(function (x) { if (x !== d) x.open = false; });
    var pop = d.querySelector('.menu-pop'), r = d.querySelector('summary').getBoundingClientRect();
    pop.style.position = 'fixed';
    var w = Math.min(260, window.innerWidth - 16);
    pop.style.width = w + 'px';
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + 'px';
    pop.style.right = 'auto';
    var h = pop.offsetHeight, top = r.bottom + 4;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 4);
    pop.style.top = top + 'px';
  }, true);
  window.addEventListener('scroll', function () { document.querySelectorAll('details.row-menu[open]').forEach(function (x) { x.open = false; }); }, true);

  /* ------------------------------------------------------------------ 5. reportar observación (marcha blanca) */
  var obs = document.getElementById('obsdlg');
  if (obs) {
    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-obs]')) {
        var h1 = document.querySelector('main h1');
        var nombre = (h1 ? h1.textContent.trim() : document.title).slice(0, 190);
        obs.querySelector('[name=url]').value = location.pathname + location.search;
        obs.querySelector('[name=pantalla]').value = nombre;
        obs.querySelector('.obs-pant').textContent = nombre;
        if (obs.showModal) obs.showModal(); else obs.setAttribute('open', '');
        obs.querySelector('textarea').focus();
      } else if (e.target.closest('[data-obs-close]')) {
        obs.close ? obs.close() : obs.removeAttribute('open');
      }
    });
  }
})();
