/* V18 (02-nov-2026): dibujo interactivo del vehículo en el checklist. Cada toque agrega un punto numerado con su nota. */
(function () {
  'use strict';
  function iniciar(w) {
    if (w.dataset.ok || !w.dataset.editable) return;
    w.dataset.ok = '1';
    var svg = w.querySelector('svg'), g = w.querySelector('.veh-marcas'), inp = w.querySelector('input[name=marcas]'),
        ol = w.querySelector('.veh-notas'), NS = 'http://www.w3.org/2000/svg', marcas = [];
    try { marcas = JSON.parse(inp.value || '[]') || []; } catch (e) { marcas = []; }
    function pintar() {
      while (g.firstChild) g.removeChild(g.firstChild);
      ol.innerHTML = '';
      marcas.forEach(function (m, i) {
        var c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', m.x); c.setAttribute('cy', m.y); c.setAttribute('r', 9); c.setAttribute('fill', '#c62828');
        var t = document.createElementNS(NS, 'text'); t.setAttribute('x', m.x); t.setAttribute('y', m.y + 4); t.setAttribute('text-anchor', 'middle');
        t.setAttribute('fill', '#fff'); t.setAttribute('font-size', '11'); t.setAttribute('font-weight', '700'); t.textContent = i + 1;
        g.appendChild(c); g.appendChild(t);
        var li = document.createElement('li');
        li.innerHTML = '<input class="veh-nota" placeholder="¿Qué defecto u observación hay?" aria-label="Nota del punto ' + (i + 1) + '"> <button type="button" class="ibtn" aria-label="Quitar punto ' + (i + 1) + '">×</button>';
        var n = li.querySelector('input'); n.value = m.nota || ''; n.required = true;
        n.addEventListener('input', function () { m.nota = n.value; guardar(); });
        li.querySelector('button').addEventListener('click', function () { marcas.splice(i, 1); pintar(); guardar(); });
        ol.appendChild(li);
      });
    }
    function guardar() { inp.value = JSON.stringify(marcas); }
    svg.addEventListener('click', function (e) {
      var pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
      var p = pt.matrixTransform(svg.getScreenCTM().inverse());
      marcas.push({ x: Math.round(p.x * 10) / 10, y: Math.round(p.y * 10) / 10, nota: '' });
      pintar(); guardar();
      var ult = ol.querySelector('li:last-child input'); if (ult) ult.focus();
    });
    pintar();
  }
  function todo() { [].forEach.call(document.querySelectorAll('.veh-wrap'), iniciar); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', todo); else todo();
})();
