/* V22: checklist vehicular sobre las imágenes del vehículo (tocar la parte con falla). */
(function () {
  document.querySelectorAll('.veh-fotos[data-editable="1"]').forEach(function (w) {
    var inp = w.querySelector('input[name=marcas]'), ol = w.querySelector('.veh-notas'), lista = w.id + '-partes', marcas = [];
    try { marcas = JSON.parse(inp.value || '[]') || []; } catch (e) { marcas = []; }
    function guardar() { inp.value = JSON.stringify(marcas); }
    function pintar() {
      w.querySelectorAll('.pin').forEach(function (p) { p.remove(); });
      ol.innerHTML = '';
      marcas.forEach(function (m, i) {
        var cont = w.querySelector('.veh-img[data-vista="' + m.vista + '"]');
        if (cont) { var s = document.createElement('span'); s.className = 'pin'; s.style.left = m.x + '%'; s.style.top = m.y + '%'; s.textContent = i + 1; cont.appendChild(s); }
        var li = document.createElement('li');
        li.innerHTML = '<input list="' + lista + '" placeholder="Parte del vehículo" size="22"> <input placeholder="¿Qué falla?" size="26"> <button type="button" class="ibtn" aria-label="Quitar punto">×</button>';
        var ins = li.querySelectorAll('input');
        ins[0].value = m.parte || ''; ins[1].value = m.nota || '';
        ins[0].addEventListener('input', function () { m.parte = this.value; guardar(); });
        ins[1].addEventListener('input', function () { m.nota = this.value; guardar(); });
        li.querySelector('button').addEventListener('click', function () { marcas.splice(i, 1); pintar(); guardar(); });
        ol.appendChild(li);
      });
    }
    w.querySelectorAll('.veh-img').forEach(function (c) {
      c.addEventListener('click', function (e) {
        if (e.target.tagName !== 'IMG') return;
        var r = e.target.getBoundingClientRect();
        var x = Math.round(1000 * (e.clientX - r.left) / r.width) / 10, y = Math.round(1000 * (e.clientY - r.top) / r.height) / 10;
        marcas.push({ vista: parseInt(c.getAttribute('data-vista'), 10), x: x, y: y, parte: '', nota: '' });
        pintar(); guardar();
        var ult = ol.lastElementChild; if (ult) ult.querySelector('input').focus();
      });
    });
    pintar();
  });
})();
