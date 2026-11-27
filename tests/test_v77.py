"""V77 (27-nov-2026): menú lateral plegable por área. El plegado se hace en el navegador (static/v77.js) sobre los mismos
grupos que arma el servidor; aquí se comprueba que la página lo carga antes del menú anclado (v76.js) y que los grupos
siguen teniendo su encabezado y su nombre, que es lo que usa el script. Solo datos ficticios."""
import os
import re

from .test_v64 import _cliente


def test_menu_plegable_se_carga_y_tiene_grupos(app):
    html = _cliente(app, "gerente.general").get("/").get_data(as_text=True)
    i77, i76 = html.find("static/v77.js"), html.find("static/v76.js")
    assert 0 < i77 < i76  # v77 pliega antes de que v76 lleve el menú a la opción activa
    grupos = re.findall(r'<div class="grp" data-grupo="([^"]+)"><h4>', html)
    assert {"Comercial", "Almacén", "Producción", "Calidad", "Distribución", "Administración"} <= set(grupos)
    assert 'data-grupo="Panel"' in html  # el panel general (Inicio, Alertas…) lo reorganiza v77.js


def test_menu_plegable_no_cambia_permisos(app):
    """Un perfil con pocas opciones sigue viendo solo lo suyo: el script no agrega opciones."""
    html = _cliente(app, "aux.despacho").get("/").get_data(as_text=True)
    assert "static/v77.js" in html
    assert 'data-grupo="Administración"' not in html


def test_script_v77_existe():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(raiz, "app", "static", "v77.js"), encoding="utf-8").read()
    assert "cp-nav-grupos" in js and "aria-expanded" in js
