"""Observaciones del módulo V7 (26-oct-2026)."""
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login

LN = [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10}]


def test_regularizacion_con_fecha_no_pasada_queda_en_borrador_y_alerta(s, U, cust):
    from app.services import orders as osvc
    u = U("asist.ventas")
    o = osvc.create_order(u, "RG-1", cust().id, date.today(), LN, regularizacion="Pedido telefónico")
    s.flush()
    assert o.estado == "REGULARIZACION_OBSERVADA" and o.id
    a = alerts_of(s, "OV_REGULARIZACION_FECHA", o.id)
    assert a and u.id in a[0].usuarios
    with pytest.raises(BusinessError, match="anterior a hoy"):
        osvc.regularize_fix_date(o, u, date.today())
    osvc.regularize_fix_date(o, u, date.today() - timedelta(days=1))
    assert o.estado == "REGULARIZADA"


def test_regularizacion_mercaderia_salio_descuenta_fefo(s, U, cust):
    from app.models import SalesHistory
    from app.services import orders as osvc
    from app.services.stock import free_qty, lots_of
    u = U("asist.ventas")
    o = osvc.create_order(u, "RG-2", cust().id, date.today() - timedelta(days=2), LN, regularizacion="Atendido el sábado")
    s.flush()
    antes = sum(l.cantidad for l in lots_of("PT-905"))
    prop = osvc.regularization_exits(o)
    assert prop and prop[0]["propuesta"]
    osvc.regularize_close(o, U("coord.ventas"), "Guía 001-1")
    s.flush()
    assert o.estado == "REGULARIZADA_CERRADA" and o.lines[0].despachado == 5
    assert abs(sum(l.cantidad for l in lots_of("PT-905")) - (antes - 5)) < 1e-6
    assert s.query(SalesHistory).filter_by(documento="RG-2", origen="REGULARIZACION").count() >= 1
    assert o.regularizacion["salidas"]


def test_regularizacion_ya_descontada_en_sap_no_descuenta(s, U, cust):
    from app.services import orders as osvc
    from app.services.stock import lots_of
    o = osvc.create_order(U("asist.ventas"), "RG-3", cust().id, date.today() - timedelta(days=2), LN, regularizacion="x")
    s.flush()
    antes = sum(l.cantidad for l in lots_of("PT-905"))
    osvc.regularize_close(o, U("coord.ventas"), "Ya en SAP", descontar=False)
    assert sum(l.cantidad for l in lots_of("PT-905")) == antes and o.regularizacion["descontado"] is False


def test_fuera_del_corte_queda_borrador_y_se_registra_al_corregir_fecha(s, U, cust):
    from app.services import orders as osvc
    from app.services.core import set_param
    set_param("hora_corte_ov_dia_siguiente", "00:00")
    manana = date.today() + timedelta(days=1)
    o = osvc.create_order(U("coord.ventas"), "CT-1", cust().id, manana, LN, oc_archivo="oc.pdf", evaluar=False)
    s.flush()
    assert o.estado == "BORRADOR"
    assert "Corrija la fecha" in o.motivo_detencion
    osvc.modify_order(o, U("coord.ventas"), {"fecha_compromiso": manana + timedelta(days=2)})
    assert o.estado != "BORRADOR"


def test_precio_bajo_base_en_vivo(s, U, cust):
    from app.models import PriceItem, Product
    from app.services.prices import check_line_price
    c = cust()
    it = s.query(PriceItem).filter(PriceItem.lista == "GENERAL", PriceItem.vigente.is_(True)).first()
    if it is None:
        pytest.skip("demo sin lista general")
    c.canal_precio = it.canal
    p = s.get(Product, it.product_code)
    assert check_line_price(p, c, it.precio * 0.5)["estado"] == "DEBAJO"
    assert check_line_price(p, c, it.precio * 2)["estado"] == "SOBRE"


def test_otra_direccion_se_agrega_como_direccion_n(s, U, cust):
    from app.services import orders as osvc
    c = cust()
    n0 = len(c.sites)
    e = osvc.resolve_delivery(c, None, "", "Jr. Ficticio 456", "Ate", "Lima", guardar=True, user=U("coord.ventas"))
    s.flush()
    s.refresh(c)
    assert len(c.sites) == n0 + 1 and e["site_id"] and e["lugar_entrega"].startswith("Dirección")
    e2 = osvc.resolve_delivery(c, None, "", "jr.  ficticio 456", "ATE", "Lima", guardar=True, user=U("coord.ventas"))
    s.flush()
    s.refresh(c)
    assert len(c.sites) == n0 + 1 and e2["site_id"] == e["site_id"]


def test_pantallas_v7(app):
    c = app.test_client()
    login(c, "coord.ventas")
    assert c.get("/ov/regularizacion").status_code == 200
    r = c.get("/ov/api/precio?producto=PT-905&cliente=1&precio=1")
    assert r.status_code == 200 and "estado" in r.get_json()
