"""Decisiones del 14-oct: plazo máximo de reserva (7 días), compra de materia prima con Gerencia de Operaciones siempre,
e impacto de cotizaciones de compras nacionales e importación en los precios."""
from datetime import date, datetime, timedelta

import pytest

from app.models import Product, Reservation
from app.services.core import BusinessError, param

from .conftest import alerts_of


def test_ov_fuera_del_plazo_no_reserva_y_se_activa_al_entrar(s, U, new_order):
    from app.services.stock import activate_deferred, line_reserved
    assert param("plazo_max_reserva_dias") == 7
    o = new_order([("PT-905", 10)], dias=12)
    assert o.estado_stock == "DIFERIDA" and line_reserved(o.lines[0]) == 0
    assert o.cobertura_unidades == 100.0 and "Reserva diferida" in o.motivo_detencion
    assert activate_deferred(U("sistemas"), date.today()) == 0
    assert activate_deferred(U("sistemas"), date.today() + timedelta(days=5)) == 1
    assert o.estado_stock == "COMPLETA" and line_reserved(o.lines[0]) == 10


def test_faltante_proyectado_de_ov_diferida_alerta(s, U, new_order):
    o = new_order([("PT-905", 99999)], dias=20)
    assert o.estado_stock == "DIFERIDA" and o.cobertura_unidades < 100
    assert alerts_of(s, "OV_FALTANTE", o.id)


def test_postergar_la_fecha_libera_la_reserva(s, U, new_order):
    from app.services import orders as osvc
    from app.services.stock import line_reserved
    o = new_order([("PT-905", 10)], dias=3)
    assert line_reserved(o.lines[0]) == 10
    osvc.modify_order(o, U("coord.ventas"), {"fecha_compromiso": date.today() + timedelta(days=15)})
    assert o.estado_stock == "DIFERIDA" and line_reserved(o.lines[0]) == 0


def test_reserva_vencida_alerta(s, U, new_order):
    from app.services.stock import check_expired_reservations
    o = new_order([("PT-905", 10)], dias=3)
    for r in s.query(Reservation).filter_by(estado="ACTIVA"):
        r.ts = datetime.now() - timedelta(days=8)
    s.flush()
    assert check_expired_reservations() >= 1 and alerts_of(s, "RESERVA_VENCIDA", o.id)


def test_compra_de_materia_prima_requiere_gerencia_de_operaciones(s, U):
    from app.services import purchasing as buy
    r = buy.create_request(U("coord.almacen.mp"), "MP-901", 1)  # cantidad mínima: no es mayor volumen
    r.estado = "SOLICITADA"
    buy.quote(r, U("compras"), "Proveedor demo", "COT-1", precio=5.0)
    assert buy.needs_go_approval(r) and buy.go_reason(r) == "materia prima"
    with pytest.raises(BusinessError, match="materia prima"):
        buy.generate_order(r, U("compras"), "OC-1", date.today() + timedelta(days=5), "EXT-002")
    buy.request_go_approval(r, U("compras"))
    buy.approve_go(r, U("gerente.operaciones"), True)
    buy.generate_order(r, U("compras"), "OC-1", date.today() + timedelta(days=5), "EXT-002")
    assert r.estado == "ORDEN_GENERADA"
    r2 = buy.create_request(U("coord.almacen.mp"), "EN-901", 1)  # insumo de bajo volumen: no requiere GO
    assert not buy.needs_go_approval(r2)


def test_impacto_de_cotizaciones_nacional_e_importacion(s, U):
    from app.services import imports as imp
    from app.services import purchasing as buy
    from app.services.costs import add_market_prices, quote_impact, replace_costs
    p = s.get(Product, "MP-901")
    p.producto_base = "FRIJOL CANARIO"
    replace_costs([{"product_code": "MP-901", "costo": 5.0, "unidad": "KG"}], U("jefe.ventas"), "prueba")
    add_market_prices([{"producto": "FRIJOL CANARIO", "precio_kg": 5.5, "fecha": date.today(), "tipo_precio": "IMPORTACION",
                        "fuente": "reporte de importación (prueba)"}], U("jefe.ventas"), "prueba")
    r = buy.create_request(U("coord.almacen.mp"), "MP-901", 100)
    r.estado = "SOLICITADA"
    buy.quote(r, U("compras"), "Proveedor nacional", "COT-2", precio=6.0)
    sh = imp.create_shipment(U("importaciones"), "IMP-T-1", "Exterior", "MP-901", 1000, date.today())
    imp.add_cost(sh, U("importaciones"), "Flete internacional", 500, "PEN")
    imp.set_goods_value(sh, U("importaciones"), 1000, "USD", 4.0)  # 4000 + 500 = 4.5 por kg
    filas = {f["origen"]: f for f in quote_impact(["MP-901"])}
    assert filas["nacional"]["nuevo_kg"] == 6.0 and filas["nacional"]["var_pct"] == 20.0
    assert any("supera el precio importacion" in x for x in filas["nacional"]["recomendaciones"])
    assert filas["importacion"]["nuevo_kg"] == 4.5
    assert any("conviene importación" in x for x in filas["importacion"]["recomendaciones"])
    assert alerts_of(s, "COTIZACION_IMPACTO", "MP-901")
