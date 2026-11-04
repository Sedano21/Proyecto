/* V20: activar las notificaciones del sistema en este dispositivo (celular o computadora). */
(function () {
  'use strict';
  var soporta = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  function b64(clave) {
    var p = '='.repeat((4 - clave.length % 4) % 4), s = (clave + p).replace(/-/g, '+').replace(/_/g, '/');
    var raw = atob(s), out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }
  function csrf() { var m = document.querySelector('meta[name="csrf"]'); return m ? m.content : ''; }
  function post(url, cuerpo) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF': csrf() },
      body: JSON.stringify(cuerpo) }).then(function (r) { return r.json(); });
  }
  function registro() { return navigator.serviceWorker.register('/sw.js', { scope: '/' }); }

  window.activarNotificaciones = function () {
    if (!soporta) { alert('Este navegador no permite notificaciones. En iPhone: agregue el sistema a la pantalla de inicio (Compartir → Agregar a inicio) y ábralo desde ese ícono.'); return Promise.resolve(false); }
    return Notification.requestPermission().then(function (p) {
      if (p !== 'granted') { alert('Las notificaciones quedaron bloqueadas. Actívelas en la configuración del navegador para este sitio.'); return false; }
      return Promise.all([registro(), fetch('/push/clave', { credentials: 'same-origin' }).then(function (r) { return r.json(); })])
        .then(function (res) {
          var reg = res[0], clave = res[1].clave;
          if (!clave) throw new Error(res[1].error || 'sin clave');
          return navigator.serviceWorker.ready.then(function (r) {
            return r.pushManager.getSubscription().then(function (s) {
              return s || r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(clave) });
            });
          });
        })
        .then(function (sub) { return post('/push/suscribir', { suscripcion: sub.toJSON() }); })
        .then(function (r) { if (r.ok) { estado(); return true; } throw new Error(r.error || 'no se guardó'); })
        .catch(function (e) { alert('No se pudieron activar las notificaciones: ' + e.message); return false; });
    });
  };

  function estado() {
    var cajas = document.querySelectorAll('[data-push-estado]');
    if (!cajas.length) return;
    var poner = function (t, activo) { cajas.forEach(function (c) { c.textContent = t; c.dataset.activo = activo ? '1' : '0'; }); };
    if (!soporta) { poner('Este navegador no permite notificaciones', false); return; }
    if (Notification.permission === 'denied') { poner('Bloqueadas en este navegador (actívelas en la configuración del sitio)', false); return; }
    navigator.serviceWorker.getRegistration('/').then(function (r) {
      if (!r) { poner('No activadas en este dispositivo', false); return; }
      r.pushManager.getSubscription().then(function (s) { poner(s ? 'Activadas en este dispositivo' : 'No activadas en este dispositivo', !!s); });
    });
  }

  // aviso discreto para activar (una vez por dispositivo; se puede cerrar)
  function aviso() {
    var a = document.getElementById('aviso-push');
    if (!a || !soporta || Notification.permission !== 'default') return;
    try { if (localStorage.getItem('aviso-push-cerrado')) return; } catch (e) { return; }
    a.hidden = false;
    a.querySelector('[data-push-activar]').addEventListener('click', function () { window.activarNotificaciones().then(function (ok) { if (ok) a.hidden = true; }); });
    a.querySelector('[data-push-cerrar]').addEventListener('click', function () { a.hidden = true; try { localStorage.setItem('aviso-push-cerrado', '1'); } catch (e) {} });
  }
  document.addEventListener('click', function (e) { if (e.target.closest('[data-push-activar-btn]')) { e.preventDefault(); window.activarNotificaciones(); } });
  // si ya estaba activado, se mantiene el service worker al día
  if (soporta && Notification.permission === 'granted') registro().catch(function () {});
  document.addEventListener('DOMContentLoaded', function () { estado(); aviso(); });
  if (document.readyState !== 'loading') { estado(); aviso(); }
})();

/* V20: tablas que no entran en su espacio (celular o computadora) se apilan solas: cada fila pasa a ser una tarjeta con
   el nombre de cada columna junto a su dato. Si luego hay espacio (pantalla más ancha), vuelven a ser tabla. */
(function () {
  'use strict';
  var EXCLUIR = '.kv, .no-apilar, .doc table, .g-items, .lq-tw table, .sec table, [data-no-apilar] table';
  function etiquetas(t) {
    var cab = t.querySelector('thead tr') || t.querySelector('tr');
    if (!cab) return 0;
    var hs = [].map.call(cab.children, function (h) { return h.tagName === 'TH' ? h.textContent.trim() : ''; });
    if (!hs.some(Boolean)) return 0;
    t.querySelectorAll('tr').forEach(function (tr) {
      if (tr === cab) return;
      var i = 0;
      [].forEach.call(tr.children, function (td) {
        if (td.tagName === 'TD' && hs[i] && !td.hasAttribute('data-label')) td.setAttribute('data-label', hs[i]);
        i += parseInt(td.getAttribute('colspan') || '1', 10);
      });
    });
    return hs.length;
  }
  function ajustar(t) {
    if (t.matches(EXCLUIR) || t.closest('.doc, [data-no-apilar], dialog.fallo-dlg')) return;
    if (!t.dataset.v20) { t.dataset.v20 = etiquetas(t) >= 3 ? '1' : '0'; }
    if (t.dataset.v20 !== '1') return;
    var caja = t.parentElement;
    t.classList.remove('apilada');
    var ancho = caja.clientWidth || caja.getBoundingClientRect().width;
    if (ancho && t.scrollWidth > ancho + 4) t.classList.add('apilada');
  }
  var obs = 'ResizeObserver' in window ? new ResizeObserver(function (es) {
    es.forEach(function (e) { e.target.querySelectorAll(':scope > table').forEach(ajustar); });
  }) : null;
  function revisar(raiz) {
    (raiz || document).querySelectorAll('.content table, main table').forEach(function (t) {
      ajustar(t);
      if (obs && t.parentElement && !t.parentElement.dataset.v20obs) { t.parentElement.dataset.v20obs = '1'; obs.observe(t.parentElement); }
    });
  }
  document.addEventListener('DOMContentLoaded', function () { revisar(); });
  if (document.readyState !== 'loading') revisar();
  document.addEventListener('lista:actualizada', function () { revisar(); });
  window.addEventListener('load', function () { revisar(); });
})();
