/* V19: indicador de carga (gato negro durmiendo) que bloquea la pantalla mientras el sistema responde, carga parcial
   de las listas al filtrar o cambiar de página, descargas (Excel/PDF) y ventana con el código de los fallos. */
(function () {
  'use strict';
  var velo = document.getElementById('velo-carga');
  var timer = null, dlTimer = null;

  function mostrar(texto) {
    if (!velo) return;
    clearTimeout(timer);
    // un pequeño retraso evita el parpadeo cuando la respuesta es inmediata
    timer = setTimeout(function () {
      var t = velo.querySelector('[data-texto]');
      if (t) t.textContent = texto || 'Cargando…';
      velo.hidden = false;
      document.documentElement.classList.add('cargando');
    }, 120);
  }
  function ocultar() {
    clearTimeout(timer); clearInterval(dlTimer);
    if (velo) velo.hidden = true;
    document.documentElement.classList.remove('cargando');
  }
  window.cargaMostrar = mostrar; window.cargaOcultar = ocultar;
  window.addEventListener('pageshow', ocultar);   // al volver con «atrás» la página viene de la caché
  window.addEventListener('pagehide', function () { clearTimeout(timer); });

  function esDescarga(url, el) {
    if (el && (el.hasAttribute('download') || el.hasAttribute('data-descarga'))) return true;
    return /([?&](salida|formato|export|exportar)=(xlsx|excel|pdf|csv|pptx|zip))|\/(excel|pdf|xlsx|csv|exportar|export|descargar)(\/|\?|$)/i.test(url);
  }

  // descargas: el servidor responde con una cookie al terminar de generar el archivo; mientras, se ve el gato
  function seguirDescarga(token) {
    var inicio = Date.now();
    clearInterval(dlTimer);
    dlTimer = setInterval(function () {
      if (document.cookie.indexOf('descarga=' + token) >= 0 || Date.now() - inicio > 90000) {
        document.cookie = 'descarga=; Max-Age=0; path=/';
        ocultar();
      }
    }, 300);
  }
  function conToken(url) {
    var token = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    var u = new URL(url, location.href); u.searchParams.set('_dl', token);
    return { url: u.toString(), token: token };
  }

  // ---------------------------------------------------------------- fallos con código
  function abrirFallos(raiz) {
    (raiz || document).querySelectorAll('dialog[data-abrir]').forEach(function (d) {
      if (!d.open && d.showModal) { try { d.showModal(); } catch (e) { d.setAttribute('open', ''); } }
    });
  }
  window.mostrarFallo = function (codigo, mensaje) {
    var d = document.createElement('dialog');
    d.className = 'fallo-dlg';
    d.innerHTML = '<div class="fallo-cab"><span class="fallo-ic" aria-hidden="true">!</span><h2>Ocurrió un fallo en el sistema</h2></div>' +
      '<p></p><div class="fallo-cod"><span>Código del fallo</span><b></b><button type="button" class="sec small">Copiar</button></div>' +
      '<p class="small muted">Envíe este código a Sistemas (también puede usar «Reportar observación»).</p><form method="dialog"><button>Entendido</button></form>';
    d.querySelector('p').textContent = mensaje || 'No se pudo completar la acción.';
    d.querySelector('b').textContent = codigo || 'sin código';
    d.querySelector('.fallo-cod button').setAttribute('data-copiar', codigo || '');
    document.body.appendChild(d); d.showModal();
    d.addEventListener('close', function () { d.remove(); });
  };
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-copiar]');
    if (!b) return;
    var v = b.getAttribute('data-copiar');
    if (navigator.clipboard) navigator.clipboard.writeText(v).then(function () { b.textContent = 'Copiado'; });
  });

  // ---------------------------------------------------------------- carga parcial de listas
  function listasDe(doc) { return doc.querySelectorAll('[data-lista][id]'); }
  function cargarParcial(url, empujar) {
    var destinos = listasDe(document);
    if (!destinos.length) return false;
    destinos.forEach(function (el) { el.classList.add('lista-cargando'); el.setAttribute('aria-busy', 'true'); });
    fetch(url, { headers: { 'X-Parcial': '1' }, credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) {
        var cod = r.headers.get('X-Error-Code');
        return r.text().then(function (t) { throw { codigo: cod, texto: t, estado: r.status }; });
      }
      if (r.redirected && new URL(r.url).pathname !== new URL(url, location.href).pathname) { location.href = r.url; return null; }
      return r.text();
    }).then(function (html) {
      if (html === null) return;
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var n = 0;
      destinos.forEach(function (el) {
        var nuevo = doc.getElementById(el.id);
        if (nuevo) { el.replaceWith(document.importNode(nuevo, true)); n++; }
      });
      if (!n) { location.href = url; return; }
      if (empujar) history.pushState({ parcial: true }, '', url);
      document.dispatchEvent(new CustomEvent('lista:actualizada'));
    }).catch(function (err) {
      listasDe(document).forEach(function (el) { el.classList.remove('lista-cargando'); el.removeAttribute('aria-busy'); });
      if (err && err.codigo) window.mostrarFallo(err.codigo, 'No se pudo cargar la lista.');
      else if (err && err.estado) location.href = url;
      else window.mostrarFallo('', 'No hay conexión con el servidor. Revise su red e intente de nuevo.');
    });
    return true;
  }
  window.addEventListener('popstate', function (e) { if (e.state && e.state.parcial) cargarParcial(location.href, false); });

  // ---------------------------------------------------------------- formularios
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (e.defaultPrevented || !(f instanceof HTMLFormElement) || f.method === 'dialog' || f.target === '_blank') return;
    if (f.hasAttribute('data-sin-carga')) return;
    var metodo = (f.getAttribute('method') || 'get').toLowerCase();
    if (e.submitter && e.submitter.getAttribute('formtarget') === '_blank') return;
    var accion = (e.submitter && e.submitter.getAttribute('formaction')) || f.getAttribute('action') || location.pathname;
    if (e.submitter && e.submitter.getAttribute('formmethod')) metodo = e.submitter.getAttribute('formmethod').toLowerCase();
    if (metodo === 'get') {
      var params = new URLSearchParams(new FormData(f));
      if (e.submitter && e.submitter.name) params.set(e.submitter.name, e.submitter.value);
      params.delete('page');            // un filtro nuevo empieza en la página 1
      var url = new URL(accion, location.href); url.search = params.toString();
      if (esDescarga(url.toString(), e.submitter || f)) {
        e.preventDefault(); var d = conToken(url.toString()); mostrar('Generando el archivo…'); seguirDescarga(d.token); location.href = d.url; return;
      }
      if (new URL(accion, location.href).pathname === location.pathname && !f.hasAttribute('data-completo') && listasDe(document).length) {
        e.preventDefault(); cargarParcial(url.toString(), true); return;
      }
      mostrar(); return;
    }
    // POST: importaciones, registros, aprobaciones… el velo impide un segundo clic mientras responde
    var subeArchivo = f.querySelector('input[type=file]') && [].some.call(f.querySelectorAll('input[type=file]'), function (i) { return i.files && i.files.length; });
    if (esDescarga(accion, e.submitter || f)) {
      var d2 = conToken(accion); if (e.submitter && e.submitter.getAttribute('formaction')) e.submitter.setAttribute('formaction', d2.url); else f.setAttribute('action', d2.url); mostrar('Generando el archivo…'); seguirDescarga(d2.token); return;
    }
    mostrar(subeArchivo ? 'Subiendo y procesando el archivo…' : 'Guardando…');
  }, false);

  // ---------------------------------------------------------------- V31: el buscador busca con Enter o con la lupa
  // (V26 buscaba mientras se escribía; la empresa pidió escribir tranquilo y buscar al pulsar Enter o la lupa)
  function esFiltro(el) {
    var f = el && el.form;
    return f && (f.getAttribute('method') || 'get').toLowerCase() === 'get' && !f.hasAttribute('data-sin-vivo') && !el.closest('dialog');
  }
  function ponerLupas(raiz) {
    (raiz || document).querySelectorAll('form input[type=search], form input[name=q], form input[name=buscar]').forEach(function (el) {
      if (el.dataset.lupa || !esFiltro(el) || el.closest('[data-sin-lupa]')) return;
      el.dataset.lupa = '1';
      var b = document.createElement('button');
      b.type = 'submit'; b.className = 'lupa'; b.title = 'Buscar'; b.setAttribute('aria-label', 'Buscar');
      b.innerHTML = '<svg class="ic" aria-hidden="true" focusable="false"><use href="#i-search"/></svg>';
      var caja = document.createElement('span'); caja.className = 'buscador';
      el.parentNode.insertBefore(caja, el); caja.appendChild(el); caja.appendChild(b);
    });
  }
  window.ponerLupas = ponerLupas;
  // V32: la «X» de un buscador vacía la búsqueda y vuelve a buscar (limpia lo filtrado)
  document.addEventListener('search', function (e) {
    var el = e.target;
    if (!el.matches || !el.matches('input[type=search]') || el.classList.contains('select-search') || el.value || !esFiltro(el)) return;
    if (el.form.requestSubmit) el.form.requestSubmit(); else el.form.submit();
  }, true);
  // V32: en las listas con buscador, el encabezado «Fecha…» ordena de últimas a primeras o al revés
  function encabezadosFecha() {
    if (!document.querySelector('form.buscador-lista')) return;
    document.querySelectorAll('[data-lista] th, .tbl th, .tw th').forEach(function (th) {
      if (th.dataset.orden || !/fecha|comprometida|emisi[oó]n|creada|llegada|vence/i.test(th.textContent)) return;
      th.dataset.orden = '1';
      var url = new URL(location.href), act = url.searchParams.get('orden');
      url.searchParams.set('orden', act === 'desc' ? 'asc' : 'desc'); url.searchParams.delete('page');
      var a = document.createElement('a'); a.href = url.toString(); a.className = 'orden-fecha';
      a.title = act === 'desc' ? 'Ordenar de las primeras a las últimas' : 'Ordenar de las últimas a las primeras';
      a.textContent = th.textContent.trim() + (act === 'desc' ? ' ↓' : act === 'asc' ? ' ↑' : ' ↕');
      th.textContent = ''; th.appendChild(a);
    });
  }
  if (document.readyState !== 'loading') encabezadosFecha(); else document.addEventListener('DOMContentLoaded', encabezadosFecha);
  if (document.readyState !== 'loading') ponerLupas(); else document.addEventListener('DOMContentLoaded', function () { ponerLupas(); });
  document.addEventListener('change', function (e) {  // listas desplegables y fechas del filtro: también al instante
    var el = e.target;
    if (!el.matches || !el.matches('select, input[type=date], input[type=checkbox]') || !esFiltro(el) || !listasDe(document).length) return;
    if (el.form.requestSubmit) el.form.requestSubmit();
  });
  (function volverAlBuscador() {
    var d = null;
    try { d = JSON.parse(sessionStorage.getItem('filtroVivo') || 'null'); sessionStorage.removeItem('filtroVivo'); } catch (_) { d = null; }
    if (!d || d.p !== location.pathname || !d.n) return;
    var el = document.querySelector('form input[name="' + d.n.replace(/"/g, '') + '"]');
    if (el) { el.focus(); var n = el.value.length; try { el.setSelectionRange(n, n); } catch (_) { /* tipo sin cursor */ } }
  })();

  // ---------------------------------------------------------------- enlaces
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('data-sin-carga')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || /^(javascript|mailto|tel):/i.test(href)) return;
    var url = new URL(href, location.href);
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    if (esDescarga(url.toString(), a)) {
      e.preventDefault(); var d = conToken(url.toString()); mostrar('Generando el archivo…'); seguirDescarga(d.token); location.href = d.url; return;
    }
    // cambio de página o de pestaña dentro de una lista: solo se recarga la lista
    if (a.closest('[data-lista]') && a.closest('.pag, [data-parcial]') && url.pathname === location.pathname) {
      e.preventDefault(); cargarParcial(url.toString(), true); return;
    }
    mostrar();
  }, false);

  // ---------------------------------------------------------------- selects que navegan solos (onchange=submit)
  document.addEventListener('DOMContentLoaded', function () { abrirFallos(); });
  if (document.readyState !== 'loading') abrirFallos();
})();
