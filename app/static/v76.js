/* V76 (26-nov-2026), reglas generales de experiencia de uso:
   1. El menú lateral queda anclado: al abrir una opción, el menú conserva la posición donde estaba y muestra la
      opción activa (no vuelve al inicio).
   2. Escribir y filtrar: toda lista desplegable larga (más de 8 opciones) agrega un buscador; los campos con lista de
      sugerencias (<input list>) muestran sus coincidencias mientras se escribe, también en el celular.
   3. Hora: además de las listas, se puede digitar (7:30, 0730, 7.30 o 730). */
(function () {
  'use strict';
  function $all(sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); }
  function norm(t) { return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim(); }

  /* 1. menú anclado */
  var nav = document.querySelector('.side .nav-scroll');
  if (nav) {
    var K = 'cp-nav-scroll';
    try { var y = sessionStorage.getItem(K); if (y !== null) nav.scrollTop = +y; } catch (e) {}
    var act = nav.querySelector('a.on');
    if (act) {
      var r = act.getBoundingClientRect(), n = nav.getBoundingClientRect();
      if (r.top < n.top || r.bottom > n.bottom) act.scrollIntoView({ block: 'center' });
    }
    var guardar = function () { try { sessionStorage.setItem(K, String(nav.scrollTop)); } catch (e) {} };
    nav.addEventListener('scroll', guardar, { passive: true });
    nav.addEventListener('click', guardar);
    window.addEventListener('pagehide', guardar);
  }

  /* 2a. listas largas con buscador (las marca antes de que ux.js agregue el buscador) */
  $all('.content select:not([multiple]):not([data-search]):not([data-no-search])').forEach(function (s) {
    if (s.options.length > 8 && !s.closest('.hm') && !s.closest('.sel-buscar')) s.setAttribute('data-search', 'Escriba para buscar…');
  });

  /* 2a'. listas que se agregan después (p. ej. cada colaborador del parte con «+»): mismo buscador al escribir */
  function buscador(sel) {
    if (sel.closest('.sel-buscar') || sel.closest('.hm') || sel.multiple || sel.options.length <= 8 || sel.hasAttribute('data-no-search')) return;
    var q = document.createElement('input');
    q.type = 'search'; q.placeholder = 'Escriba para buscar…'; q.className = 'select-search'; q.setAttribute('aria-label', 'Buscar en la lista');
    var c = document.createElement('div'); c.className = 'sel-buscar';
    sel.parentNode.insertBefore(c, sel); c.appendChild(q); c.appendChild(sel);
    q.addEventListener('input', function () {
      var t = norm(q.value), mejor = null;
      [].forEach.call(sel.options, function (o) {
        var ok = !o.value || !t || norm(o.text).indexOf(t) >= 0;
        o.hidden = !ok;
        if (ok && o.value && t && !mejor && !o.disabled) mejor = o;
      });
      if (mejor) { sel.value = mejor.value; sel.dispatchEvent(new Event('change', { bubbles: true })); }
    });
  }
  if (window.MutationObserver) {
    new MutationObserver(function (ms) {
      ms.forEach(function (m) {
        [].forEach.call(m.addedNodes, function (n) {
          if (n.nodeType !== 1 || !n.closest('.content')) return;
          (n.tagName === 'SELECT' ? [n] : $all('select', n)).forEach(buscador);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  /* 2b. sugerencias mientras se escribe en <input list> */
  var caja = null, actual = null;
  function cerrar() { if (caja) { caja.remove(); caja = null; actual = null; } }
  function abrir(inp) {
    var id = inp.getAttribute('data-list') || inp.getAttribute('list');
    var dl = id && document.getElementById(id);
    if (!dl) return;
    if (inp.getAttribute('list')) { inp.setAttribute('data-list', id); inp.removeAttribute('list'); }
    var t = norm(inp.value), ops = [].slice.call(dl.options), out = [];
    for (var i = 0; i < ops.length && out.length < 40; i++) {
      var v = ops[i].value, extra = ops[i].textContent || '';
      if (!t || norm(v + ' ' + extra).indexOf(t) >= 0) out.push([v, extra]);
    }
    cerrar();
    if (!out.length || (out.length === 1 && out[0][0] === inp.value)) return;
    caja = document.createElement('div'); caja.className = 'sug-caja'; caja.setAttribute('role', 'listbox');
    out.forEach(function (o) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'sug-op'; b.setAttribute('role', 'option');
      b.textContent = o[0]; if (o[1] && o[1] !== o[0]) { var sm = document.createElement('small'); sm.textContent = ' ' + o[1]; b.appendChild(sm); }
      b.addEventListener('mousedown', function (e) { e.preventDefault(); });
      b.addEventListener('click', function () {
        inp.value = o[0]; cerrar();
        inp.dispatchEvent(new Event('input', { bubbles: true })); inp.dispatchEvent(new Event('change', { bubbles: true }));
      });
      caja.appendChild(b);
    });
    var rc = inp.getBoundingClientRect();
    caja.style.left = (rc.left + window.scrollX) + 'px';
    caja.style.top = (rc.bottom + window.scrollY + 2) + 'px';
    caja.style.minWidth = Math.max(rc.width, 220) + 'px';
    document.body.appendChild(caja); actual = inp;
  }
  document.addEventListener('input', function (e) {
    var el = e.target;
    if (el.matches && el.matches('input[list], input[data-list]')) abrir(el);
  });
  document.addEventListener('focusin', function (e) {
    var el = e.target;
    if (el.matches && el.matches('input[list], input[data-list]')) abrir(el);
  });
  document.addEventListener('focusout', function (e) { if (e.target === actual) setTimeout(cerrar, 150); });
  document.addEventListener('keydown', function (e) {
    if (!caja) return;
    if (e.key === 'Escape') { cerrar(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); var f = caja.querySelector('.sug-op'); if (f) f.focus(); }
  });
  document.addEventListener('keydown', function (e) {
    var b = e.target.closest && e.target.closest('.sug-op');
    if (!b) return;
    if (e.key === 'ArrowDown' && b.nextElementSibling) { e.preventDefault(); b.nextElementSibling.focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); (b.previousElementSibling || actual).focus(); }
  });
  window.addEventListener('scroll', function () { if (caja && actual) { var rc = actual.getBoundingClientRect(); caja.style.top = (rc.bottom + window.scrollY + 2) + 'px'; } }, { passive: true });

  /* 3. hora digitable: normaliza 730 / 0730 / 7.30 / 7h30 → 07:30 antes de validar */
  function normHora(v) {
    var t = String(v || '').trim().toLowerCase().replace(/\s+/g, ' ');
    var suf = (t.match(/\s?([ap])\.?\s?m\.?$/) || [])[1];
    t = t.replace(/\s?[ap]\.?\s?m\.?$/, '').replace(/[.h]/, ':');
    if (/^\d{3,4}$/.test(t)) t = t.slice(0, t.length - 2) + ':' + t.slice(-2);
    if (/^\d{1,2}$/.test(t)) t = t + ':00';
    var m = t.match(/^(\d{1,2}):(\d{1,2})$/);
    if (!m) return null;
    var h = +m[1], mi = +m[2];
    if (suf) { if (h === 12) h = 0; if (suf === 'p') h += 12; }
    if (h > 23 || mi > 59) return null;
    return (h < 10 ? '0' : '') + h + ':' + (mi < 10 ? '0' : '') + mi;
  }
  document.addEventListener('change', function (e) {
    var el = e.target;
    if (!(el.matches && el.matches('input.hm-src'))) return;
    var v = normHora(el.value);
    if (v && v !== el.value) { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }
    var w = el.nextElementSibling;
    if (w && w.classList.contains('hm') && v) {
      var hh = w.querySelector('.hm-h'), mm = w.querySelector('.hm-m');
      if (hh) hh.value = String(+v.slice(0, 2));
      if (mm) { var m5 = String(+v.slice(3)); mm.value = [].some.call(mm.options, function (o) { return o.value === m5; }) ? m5 : ''; }
    }
  }, true);
  document.addEventListener('blur', function (e) {
    var el = e.target;
    if (el.matches && el.matches('input.hm-src')) { var v = normHora(el.value); if (v && v !== el.value) { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); } }
  }, true);
})();
/* V76: filtrar la lista de colaboradores (casillas) mientras se escribe */
document.addEventListener('input', function (e) {
  var q = e.target;
  if (!q.matches || !q.matches('[data-filtra-personas]')) return;
  var t = q.value.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
  var box = q.parentNode.querySelector('.personas-lista');
  [].forEach.call(box ? box.querySelectorAll('label') : [], function (l) {
    l.hidden = !!t && l.textContent.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').indexOf(t) < 0;
  });
});
/* V76: en el plan, al elegir el producto se sugiere el granel o la MP de su receta */
document.addEventListener('change', function (e) {
  var el = e.target;
  if (!el.matches || !el.matches('[data-sugiere-insumo]')) return;
  var fila = el.closest('tr'), ins = fila && fila.querySelector('[name="insumo"]');
  var code = (el.value || '').split(' ')[0];
  if (!ins || !code) return;
  fetch(el.getAttribute('data-sugiere-insumo') + '?code=' + encodeURIComponent(code), { credentials: 'same-origin' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && j.insumos && j.insumos.length && !ins.value) ins.value = j.insumos[0].code + ' · ' + j.insumos[0].descripcion; })
    .catch(function () {});
});
