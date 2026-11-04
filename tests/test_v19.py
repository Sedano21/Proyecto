"""V19 (03-nov-2026): experiencia de usuario: listas por páginas, alta de cliente en ventana, carga (velo), fallos con
código, hora de Perú, lotes con puntos de SAP y fotos de movimientos en celular. Datos ficticios."""
import os
import time
from datetime import datetime

import pytest

from .test_web import login


def _get(app, user, path, **kw):
    c = app.test_client()
    login(c, user)
    return c.get(path, **kw)


def test_hora_de_peru():
    import app as paquete  # noqa: F401  (al importar el paquete se fija la zona horaria)
    assert os.environ.get("TZ") == os.environ.get("APP_TZ", "America/Lima")
    assert time.strftime("%z") == "-0500"  # Perú no usa horario de verano
    assert abs((datetime.now() - datetime.utcnow()).total_seconds() + 5 * 3600) < 120


def test_clientes_por_paginas_y_alta_en_ventana(app, s, U):
    from app.models import Customer
    for i in range(40):
        s.add(Customer(ruc=f"2099{i:07d}", nombre=f"CLIENTE FICTICIO {i:02d}", grupo="MAYORISTA"))
    s.commit()
    html = _get(app, "coord.ventas", "/ov/clientes").get_data(as_text=True)
    assert 'id="dlg-cliente"' in html and 'data-open="dlg-cliente"' in html  # botón «Nuevo cliente» + ventana
    assert "1–25 de" in html and "page=2" in html and html.count('href="/ov/clientes/') <= 25
    p2 = _get(app, "coord.ventas", "/ov/clientes?page=2").get_data(as_text=True)
    assert "26–" in p2
    filtrado = _get(app, "coord.ventas", "/ov/clientes?q=FICTICIO%2007").get_data(as_text=True)
    assert "CLIENTE FICTICIO 07" in filtrado and "CLIENTE FICTICIO 08" not in filtrado
    assert 'data-autoopen' in _get(app, "coord.ventas", "/ov/clientes?nuevo=1").get_data(as_text=True)


def test_paginacion_conserva_filtros_y_limita(app, s):
    from flask import request  # noqa: F401
    from app.views.common import paginate
    with app.test_request_context("/x?q=abc&page=3&por=10"):
        p = paginate(list(range(95)))
        assert p.page == 3 and p.pages == 10 and list(p) == list(range(20, 30)) and p.total == 95
        assert "q=abc" in p.url(4) and "page=4" in p.url(4)
        assert p.numeros() == [1, 2, 3, 4, 5, None, 10]
    with app.test_request_context("/x?page=999"):
        assert paginate(list(range(30))).page == 2  # una página inexistente muestra la última


@pytest.mark.parametrize("user,path", [
    ("coord.ventas", "/ov/"), ("coord.almacen", "/almacen/stock"), ("coord.almacen", "/almacen/cargas"),
    ("sistemas", "/auditoria"), ("coord.distribucion", "/distribucion/incidencias"), ("jefe.produccion", "/produccion/partes"),
    ("coord.almacen", "/alertas"), ("compras", "/abastecimiento/compras"), ("jefe.calidad", "/calidad/"),
])
def test_listas_con_contenedor_parcial(app, user, path):
    r = _get(app, user, path)
    assert r.status_code == 200, (user, path)
    assert "data-lista" in r.get_data(as_text=True), (user, path)


def test_velo_de_carga_y_aviso_de_descarga(app):
    html = _get(app, "coord.ventas", "/").get_data(as_text=True)
    assert 'id="velo-carga"' in html and "v19.js" in html and 'class="gato' in html
    r = _get(app, "jefe.produccion", "/produccion/control?salida=xlsx&_dl=abc123")
    assert r.status_code == 200 and "descarga=abc123" in r.headers.get("Set-Cookie", "")
    r = _get(app, "jefe.produccion", "/produccion/control?_dl=abc123")  # página normal: sin cookie
    assert "descarga=" not in (r.headers.get("Set-Cookie") or "")


def test_fallo_inesperado_muestra_codigo_en_ventana(app, monkeypatch):
    from app.services import customers as csv_
    from app.services import errores
    app.config["CAPTURAR_FALLOS"] = True

    def roto(*a, **k):
        raise RuntimeError("fallo de prueba")
    monkeypatch.setattr(csv_, "save_customer", roto)
    c = app.test_client()
    login(c, "coord.ventas")
    page = c.get("/ov/clientes").get_data(as_text=True)
    csrf = page.split('name="_csrf" value="')[1].split('"')[0]
    html = c.post("/ov/clientes", data={"_csrf": csrf, "nombre": "X", "ruc": "20999999991"},
                  follow_redirects=True).get_data(as_text=True)
    assert 'class="fallo-dlg"' in html and "Código del fallo" in html
    codigo = html.split("data-codigo>")[1].split("<")[0]
    assert codigo.startswith("E")
    reg = errores.ultimos(5, codigo)
    assert reg and "RuntimeError: fallo de prueba" in reg[0]["resumen"] and reg[0]["ruta"] == "/ov/clientes"
    assert codigo in _get(app, "sistemas", f"/sistemas/errores?q={codigo}").get_data(as_text=True)


def test_error_500_con_codigo(app):
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/_prueba_500")
    def _p500():
        raise ValueError("explota")
    c = app.test_client()
    login(c, "coord.ventas")
    r = c.get("/_prueba_500")
    assert r.status_code == 500 and r.headers.get("X-Error-Code", "").startswith("E")
    assert "fallo-dlg" in r.get_data(as_text=True)
    rp = c.get("/_prueba_500", headers={"X-Parcial": "1"})  # carga parcial de una lista: texto con el código
    assert rp.status_code == 500 and rp.headers["X-Error-Code"] in rp.get_data(as_text=True)


def test_lote_con_puntos_de_sap_se_conserva_y_se_explica(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import uploads
    wb = Workbook()
    ws = wb.active
    ws.title = "STOCK_LOTE"
    ws.append(["Número de artículo", "Descripción del artículo", "Lote", "Almacén", "Cantidad"])
    ws.append(["PT-901", "PRODUCTO DEMO", "310000CA.", "ALM-001", 5])
    ws.append(["PT-901", "PRODUCTO DEMO", "310000CA", "ALM-001", 3])
    ws.append(["PT-901", "PRODUCTO DEMO", "31#00 X", "ALM-001", 1])
    f = tmp_path / "stock.xlsx"
    wb.save(f)
    b = uploads.create_batch(U("coord.almacen"), "STOCK", str(f), "stock.xlsx")
    avisos = {r.datos["lote"]: r.advertencias for r in b.rows}
    # V20: los puntos son variantes del lote (misma numeración, otra producción): se conservan y ya no se advierten
    assert not any("puntos" in w or "inusuales" in w for w in avisos["310000CA."])
    assert not any("puntos" in w for w in avisos["310000CA"])
    assert any("caracteres inusuales" in w for w in avisos["31#00 X"])
    assert not any(e for r in b.rows for e in r.errores if "duplic" in e.lower())  # son dos lotes distintos en SAP


def test_fotos_de_movimiento_sin_superponerse(app):
    css = open(os.path.join(app.static_folder, "style.css"), encoding="utf-8").read()
    assert ".mov-times a.mov-foto{position:static" in css
    tpl = open(os.path.join(app.root_path, "templates", "moves.html"), encoding="utf-8").read()
    assert 'class="mov-foto"' in tpl and 'class="ibtn" href="{{ url_for(\'main.evidence\', name=m.foto_' not in tpl
