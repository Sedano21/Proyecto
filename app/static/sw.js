/* V20: service worker del Módulo de Operaciones. Solo muestra las notificaciones de alertas (no guarda páginas en caché,
   así nunca se ve información vieja). Funciona aunque la pestaña o el navegador estén cerrados. */
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });

self.addEventListener('push', function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { title: 'Módulo de Operaciones', body: e.data ? e.data.text() : '' }; }
  var titulo = d.title || 'Nueva alerta';
  var op = {
    body: d.body || '',
    icon: '/static/img/icono_192.png',
    badge: '/static/img/insignia_96.png',
    tag: d.tag || undefined,
    renotify: !!d.tag,
    requireInteraction: !!d.urgente,           // las urgentes quedan hasta que se toquen
    vibrate: d.urgente ? [300, 120, 300, 120, 300] : [200],
    data: { url: d.url || '/alertas' },
    lang: 'es-PE'
  };
  e.waitUntil(self.registration.showNotification(titulo, op));
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || '/alertas';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (lista) {
    for (var i = 0; i < lista.length; i++) {
      var c = lista[i];
      if (new URL(c.url).origin === self.location.origin && 'focus' in c) { c.navigate(url); return c.focus(); }
    }
    return self.clients.openWindow(url);
  }));
});
