"""Observaciones al demo v0.7 – vista general: informes en PDF/Excel, informe personalizado, cargas en PDF,
alertas (estado, naturaleza por perfil, derivación), OV (obligatorios, fechas pasadas, regularización) y manual."""
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _get(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r


@pytest.mark.parametrize("nombre", ["comercial", "almacen", "produccion", "distribucion", "reempaque"])
def test_informes_en_pdf_y_excel(app, nombre):
    c = app.test_client()
    login(c, "gerente.general")
    r = _get(c, f"/informes/{nombre}?formato=pdf")
    assert r.mimetype == "application/pdf" and r.data[:4] == b"%PDF" and len(r.data) > 1500
    r = _get(c, f"/informes/{nombre}?formato=xlsx")
    assert r.data[:2] == b"PK"


def test_informe_personalizado(app):
    c = app.test_client()
    login(c, "coord.ventas")
    assert "Arme su informe" in _get(c, "/informes/personalizado").get_data(as_text=True)
    hoy = date.today()
    q = f"fuente=ov_lineas&desde={(hoy - timedelta(days=60)).isoformat()}&hasta={(hoy + timedelta(days=60)).isoformat()}"
    html = _get(c, f"/informes/personalizado?{q}&ver=1&col=ov&col=producto&col=cantidad").get_data(as_text=True)
    assert "Producto" in html and "fila(s)" in html
    assert _get(c, f"/informes/personalizado?{q}&formato=pdf&agrupar=producto&col=producto&col=cantidad").data[:4] == b"%PDF"
    assert _get(c, f"/informes/personalizado?{q}&formato=xlsx").data[:2] == b"PK"
    assert c.get("/informes/personalizado?fuente=compras").status_code == 403  # Comercial no ve compras


def test_carga_de_stock_en_pdf(s, U, tmp_path):
    from app.services import uploads
    from .test_v07_comercial import _pdf_simple
    f = tmp_path / "stock.pdf"
    f.write_bytes(_pdf_simple([
        "Stock por lote",
        "Número de artículo   Descripción del artículo     Lote        Almacén   Cantidad   Fecha de vencimiento",
        "PT-905               LENTEJA DEMO                 L-PDF-1     ALM-001       120.5   02/09/2027",
        "PT-906               FRIJOL DEMO                  L-PDF-2     ALM-001          40   15/01/2027"]))
    b = uploads.create_batch(U("coord.almacen"), "STOCK", str(f), "stock.pdf")
    assert b.hoja == "PDF" and len(b.rows) == 2
    assert b.rows[0].datos["lote"] == "L-PDF-1" and float(b.rows[0].datos["cantidad"]) == 120.5


def test_ov_exige_producto_cantidad_y_precio(s, U, cust):
    from app.services import orders as osvc
    hoy = date.today()
    with pytest.raises(BusinessError, match="precio"):
        osvc.create_order(U("coord.ventas"), "X-1", cust().id, hoy + timedelta(days=2), [{"product_code": "PT-905", "cantidad": 5}])
    with pytest.raises(BusinessError, match="Regularización"):
        osvc.create_order(U("coord.ventas"), "X-2", cust().id, hoy - timedelta(days=1),
                          [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10}])


def test_regularizacion_sin_reserva_y_liberacion(s, U, cust):
    from app.services import orders as osvc
    from app.services.stock import line_reserved
    hoy = date.today()
    with pytest.raises(BusinessError, match="regularizaciones"):
        osvc.create_order(U("coord.almacen"), "R-0", cust().id, hoy - timedelta(days=2),
                          [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10}], regularizacion="x")
    o = osvc.create_order(U("asist.ventas"), "R-1", cust().id, hoy - timedelta(days=2),
                          [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10}], regularizacion="Pedido telefónico")
    s.flush()
    assert o.estado == "REGULARIZADA" and line_reserved(o.lines[0]) == 0 and alerts_of(s, "OV_REGULARIZACION", o.id)
    with pytest.raises(BusinessError, match="ya pasó"):
        osvc.regularize_release(o, U("coord.ventas"), hoy - timedelta(days=1))
    osvc.regularize_release(o, U("coord.ventas"), hoy + timedelta(days=2), "Se despacha")
    s.flush()
    assert o.estado not in ("REGULARIZADA",) and o.regularizacion["liberada_por"]


def test_naturaleza_por_perfil_y_derivacion(s, U, new_order):
    from app.services import alerts
    from app.services import alert_actions
    o = new_order([("PT-905", 10)], precio=0.01)  # precio bajo: alerta de precio para Comercial
    a = (alerts_of(s, "OV_PRECIO_BAJO_MINIMO", o.id) or alerts_of(s, "OV_PRECIO_BAJO_COSTO", o.id))[0]
    assert alerts.can_act(U("coord.ventas"), a)
    assert alerts.nature_for(U("gerente.operaciones"), a) == "INFORMATIVA"
    assert not alerts.can_act(U("asist.ventas"), a)


def test_estado_de_alertas_para_sonido_y_actualizacion(app):
    c = app.test_client()
    login(c, "coord.almacen")
    d = _get(c, "/alertas/estado.json").get_json()
    assert {"abiertas", "criticas", "version", "repetir_seg", "actualizar_seg"} <= set(d)


def test_gerencias_ven_todas_las_pantallas(app):
    c = app.test_client()
    login(c, "gerente.operaciones")
    for url in ("/configuracion", "/almacen/picking", "/informes/comercial", "/auditoria", "/produccion/plan", "/calidad/", "/abastecimiento/compras", "/distribucion/flota"):
        assert c.get(url).status_code == 200, url


def test_manual_por_rol(app):
    c = app.test_client()
    login(c, "aux.almacen")
    html = _get(c, "/ayuda").get_data(as_text=True)
    assert "Manual de usuario" in html and "Alertas y sonido" in html
    c2 = app.test_client()
    login(c2, "sistemas")
    assert "Coordinador de Ventas" in _get(c2, "/ayuda?rol=COORD_VENTAS").get_data(as_text=True)
