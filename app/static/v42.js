/* V42 (14-nov-2026): toda tarjeta de indicador se puede abrir para ver su detalle.
   - data-href="url": lleva a la pantalla del detalle.
   - data-ver="#id": baja hasta esa sección de la página (y la despliega si es plegable).
   - Sin ninguno: busca en la página la sección cuyo título comparte palabras con el nombre del indicador
     (p. ej. «Fill rate (unidades)» → «Por qué no salió completo» no; «Incidencias» → «Incidencias por tipo» sí). */
(function () {
  var VACIAS = /^(de|del|la|las|el|los|en|y|o|a|por|con|sin|que|al|su|sus|un|una|para|lo|se|vs|total|promedio)$/;
  function palabras(t) {
    return (t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]/g, " ")
      .split(/\s+/).filter(function (w) { return w.length > 2 && !VACIAS.test(w); });
  }
  function destino(k) {
    if (k.dataset.ver) return document.querySelector(k.dataset.ver);
    var nombre = k.querySelector("span");
    var buscadas = palabras(nombre ? nombre.textContent : "");
    if (!buscadas.length) return null;
    var mejor = null, puntos = 0;
    document.querySelectorAll("main h2, main h3, main summary, .card h3, .card h2, details > summary, .section-title")
      .forEach(function (h) {
        if (k.contains(h) || h.closest(".kpis")) return;
        var p = palabras(h.textContent), n = 0;
        buscadas.forEach(function (w) { if (p.some(function (x) { return x.indexOf(w.slice(0, 6)) === 0; })) n++; });
        if (n > puntos) { puntos = n; mejor = h; }
      });
    return puntos ? mejor : null;
  }
  function abrir(k) {
    if (k.dataset.href) { location.href = k.dataset.href; return; }
    var d = destino(k);
    if (!d) return;
    var det = d.tagName === "SUMMARY" ? d.parentElement : d.closest("details");
    if (det) det.open = true;
    var bloque = d.closest(".card") || d;
    bloque.scrollIntoView({behavior: "smooth", block: "start"});
    bloque.classList.add("resaltado");
    setTimeout(function () { bloque.classList.remove("resaltado"); }, 1800);
  }
  function preparar() {
    document.querySelectorAll("div.kpi").forEach(function (k) {
      if (k.dataset.listo || k.closest("a")) return;
      k.dataset.listo = "1";
      if (!(k.dataset.href || destino(k))) return;
      k.classList.add("kpi-clic");
      k.setAttribute("role", "link");
      k.setAttribute("tabindex", "0");
      k.title = k.dataset.href ? "Ver el detalle" : "Ver el detalle en esta página";
      k.addEventListener("click", function () { abrir(k); });
      k.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrir(k); } });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", preparar); else preparar();
})();
