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

  // V24: el resultado se muestra en la misma barra (los alert() pueden estar bloqueados) y se explica cada motivo
  function avisar(msg, ok) {
    var a = document.getElementById('aviso-push'), m = a && a.querySelector('[data-push-msg]');
    if (m) { m.textContent = msg; m.hidden = false; m.className = 'push-msg ' + (ok ? 'ok' : 'err'); if (a.hidden) a.hidden = false; }
    else { try { alert(msg); } catch (e) {} }
  }
  function motivoNoSoporta() {
    if (!window.isSecureContext) return 'El sistema está abierto sin https (conexión segura): el navegador solo permite notificaciones con https. Pida a Sistemas activar el certificado del dominio.';
    try { if (window.top !== window.self) return 'Abra el sistema en una pestaña del navegador (no dentro de otra aplicación) para activar las notificaciones.'; } catch (e) { return 'Abra el sistema en una pestaña del navegador para activar las notificaciones.'; }
    return 'Este navegador no permite notificaciones. En iPhone: agregue el sistema a la pantalla de inicio (Compartir → Agregar a inicio) y ábralo desde ese ícono.';
  }
  function pedirPermiso() {
    return new Promise(function (ok) {
      var r = Notification.requestPermission(function (p) { ok(p); });  // navegadores antiguos usan callback
      if (r && r.then) r.then(ok);
    });
  }
  window.activarNotificaciones = function () {
    if (!soporta || !window.isSecureContext) { avisar(motivoNoSoporta(), false); return Promise.resolve(false); }
    avisar('Activando… acepte el permiso que muestra el navegador.', true);
    return pedirPermiso().then(function (p) {
      if (p === 'denied') { avisar('Las notificaciones están bloqueadas para este sitio. Actívelas en el candado de la barra de direcciones → Notificaciones → Permitir, y vuelva a pulsar Activar.', false); return false; }
      if (p !== 'granted') { avisar('No se otorgó el permiso. Pulse Activar otra vez y elija «Permitir».', false); return false; }
      return Promise.all([registro(), fetch('/push/clave', { credentials: 'same-origin' }).then(function (r) { return r.json(); })])
        .then(function (res) {
          var clave = res[1].clave;
          if (!clave) throw new Error(res[1].error || 'el servidor no entregó la clave');
          return navigator.serviceWorker.ready.then(function (r) {
            return r.pushManager.getSubscription().then(function (s) {
              return s || r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(clave) });
            });
          });
        })
        .then(function (sub) { return post('/push/suscribir', { suscripcion: sub.toJSON() }); })
        .then(function (r) { if (r.ok) { estado(); avisar('Listo: las alertas llegarán a este dispositivo.', true); return true; } throw new Error(r.error || 'no se guardó'); })
        .catch(function (e) { avisar('No se pudieron activar las notificaciones: ' + e.message, false); return false; });
    });
  };

  function estado() {
    var cajas = document.querySelectorAll('[data-push-estado]');
    if (!cajas.length) return;
    var poner = function (t, activo) { cajas.forEach(function (c) { c.textContent = t; c.dataset.activo = activo ? '1' : '0'; }); };
    if (!soporta || !window.isSecureContext) { poner(motivoNoSoporta(), false); return; }
    if (Notification.permission === 'denied') { poner('Bloqueadas en este navegador (actívelas en la configuración del sitio)', false); return; }
    navigator.serviceWorker.getRegistration('/').then(function (r) {
      if (!r) { poner('No activadas en este dispositivo', false); return; }
      r.pushManager.getSubscription().then(function (s) { poner(s ? 'Activadas en este dispositivo' : 'No activadas en este dispositivo', !!s); });
    });
  }

  // aviso discreto para activar (una vez por dispositivo; se puede cerrar)
  function aviso() {
    var a = document.getElementById('aviso-push');
    if (!a || !soporta || !window.isSecureContext || Notification.permission !== 'default') return;
    try { if (localStorage.getItem('aviso-push-cerrado')) return; } catch (e) { return; }
    a.hidden = false;
    a.querySelector('[data-push-activar]').addEventListener('click', function () { window.activarNotificaciones().then(function (ok) { if (ok) setTimeout(function () { a.hidden = true; }, 2500); }); });
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
