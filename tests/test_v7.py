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
    r = c.get("/ov/clientes/1")
    assert r.status_code == 200 and "Penalidades del cliente" in r.get_data(as_text=True)
    r = c.get("/ov/api/precio?producto=PT-905&cliente=1&precio=1")
    assert r.status_code == 200 and "estado" in r.get_json()


def test_penalidades_ilimitadas_deteccion_y_resultado(s, U, cust):
    from app.services import orders as osvc
    from app.services import penalties as pen
    c = cust()
    filas = [{"tipo": "FECHA_ENTREGA", "modo": "FIJO", "valor": "150"}, {"tipo": "ENTREGA_PARCIAL", "modo": "PCT_OV", "valor": "10"},
             {"tipo": "OTRO", "nombre": "Etiquetado incorrecto", "modo": "FIJO", "valor": "80"}]
    cond = pen.save_conditions(c, U("coord.ventas"), filas)
    assert "ETIQUETADO_INCORRECTO" in cond.penalidad_tipos and len(cond.penalidad_tipos) == 3
    o = osvc.create_order(U("coord.ventas"), "PN-1", c.id, date.today() + timedelta(days=3), LN, oc_archivo="oc.pdf", evaluar=False)
    s.flush()
    o.lines[0].entregado = 3
    nuevas = pen.detect_for_order(o, U("coord.ventas"), fecha_entrega=o.fecha_compromiso + timedelta(days=1))
    assert {p.tipo for p in nuevas} == {"FECHA_ENTREGA", "ENTREGA_PARCIAL"}
    assert pen.detect_for_order(o, U("coord.ventas"), fecha_entrega=o.fecha_compromiso + timedelta(days=1)) == []
    assert alerts_of(s, "CLIENTE_PENALIDAD", nuevas[0].id)
    with pytest.raises(BusinessError, match="desestim"):
        pen.resolve(nuevas[0], U("coord.ventas"), "DESESTIMADA")
    pen.resolve(nuevas[0], U("coord.ventas"), "PAGADA", 100)
    pen.resolve(nuevas[1], U("coord.ventas"), "DESESTIMADA", comentario="El cliente aceptó la reposición")
    ind = pen.indicator(customer_id=c.id)["total"]
    assert ind["pagada"] == 100 and ind["calculada"] == 150 + round(50 * 0.10, 2) and ind["pendientes"] == 0


def test_codigo_de_cliente_correlativo(s, U):
    from app.models import Customer
    from app.services import customers as csv_
    from app.services.penalties import next_customer_code
    s.query(Customer).first().codigo_sap = "C000120"
    s.flush()
    assert next_customer_code() == "C000121"
    c = csv_.save_customer(U("coord.ventas"), None, {"ruc": "20999999991", "nombre": "CLIENTE FICTICIO V7",
                                                      "direccion": "Av. Ficticia 1", "ubigeo": "150101"})
    assert c.codigo_sap == "C000121"


def test_carga_sap_cierra_ov_atendida_en_sap_sin_duplicar(s, U, tmp_path):
    import os
    import openpyxl
    from app.demo_data import write_ovs
    from app.models import SalesOrder
    from app.services import uploads as up
    from app.services.stock import line_reserved
    p = os.path.join(tmp_path, "ovs.xlsx")
    write_ovs(p, date.today())
    up.confirm(up.create_batch(U("coord.ventas"), "OV", p, "ovs.xlsx"), U("coord.ventas"))
    n = s.query(SalesOrder).count()
    res = up.confirm(up.create_batch(U("coord.ventas"), "OV", p, "ovs.xlsx"), U("coord.ventas"))  # 2.ª carga del día
    assert s.query(SalesOrder).count() == n and res["ov_creadas"] == 0
    o = s.query(SalesOrder).filter_by(numero="SAP-9001").one()
    assert any(line_reserved(l) > 0 for l in o.lines)
    wb = openpyxl.load_workbook(p)
    ws = wb["OVS"]
    hdr = [c.value for c in ws[1]]
    ie, inum = hdr.index("Estado"), hdr.index("Número de documento")
    for row in ws.iter_rows(min_row=2):
        if row[inum].value == "SAP-9001":
            row[ie].value = "Cerrado"
    wb.save(p)
    res = up.confirm(up.create_batch(U("coord.ventas"), "OV", p, "ovs.xlsx"), U("coord.ventas"))
    s.flush()
    assert res["ov_cerradas_en_sap"] == 1 and o.estado == "CERRADA"
    assert all(line_reserved(l) == 0 for l in o.lines)
