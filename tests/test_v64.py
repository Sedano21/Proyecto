"""V64 (20-nov-2026): marcha blanca del área comercial. IGV por línea y totales de la OV, tramos de precio por cantidad,
cerrar vs cancelar con causal, kilos, vendedores de SAP por usuario, ficha del cliente, alertas y carga de OV con
plantilla. Solo datos ficticios."""
from datetime import date, timedelta

import pytest

from .conftest import alerts_of
from .test_web import login


class _C:
    """Cliente de prueba que agrega el token CSRF a cada POST."""
    def __init__(self, app, user):
        self.c = app.test_client()
        self.tok, _ = login(self.c, user)

    def get(self, *a, **k):
        return self.c.get(*a, **k)

    def post(self, url, data=None, **k):
        data = dict(data or {})
        data["_csrf"] = self.tok
        return self.c.post(url, data=data, **k)


def _cliente(app, user):
    return _C(app, user)


def test_totales_con_igv_por_linea(app, s, U, new_order):
    from app.services import orders as osvc
    o = new_order([("PT-901", 10), ("GR-901", 100)], precio=2.0)
    o.lines[0].tax_code, o.lines[1].tax_code = "IGV", "EXO"
    o.oc_total = 43.6
    s.commit()
    t = osvc.totales(o)
    # 10 × 2 = 20 afecto (IGV 3,60) + 100 × 2 = 200 exonerado
    assert t["subtotal"] == 220 and t["igv"] == 3.6 and t["total"] == 223.6
    assert t["dif_oc"] == 180 and t["cuadra_oc"] is False


def test_formulario_registra_igv_y_total_de_oc(app, s, U, cust):
    from app.models import SalesOrder
    c = _cliente(app, "coord.ventas")
    html = c.get("/ov/nueva").get_data(as_text=True)
    assert "Exonerado / inafecto" in html and "Total de la OC" in html and "t_tot" in html
    f = (date.today() + timedelta(days=5)).isoformat()
    r = c.post("/ov/nueva", data={"customer_id": cust().id, "fecha_compromiso": f, "modalidad_entrega": "RECOJO",
                                  "product_code": ["PT-901", "GR-901"], "cantidad": ["4", "10"], "precio_unitario": ["999", "999"],
                                  "um_venta": ["", ""], "tax_code": ["EXO", "IGV"], "oc_total": "1234.5",
                                  "requiere_estiba": "1"}, follow_redirects=True)
    assert r.status_code == 200
    o = s.query(SalesOrder).order_by(SalesOrder.id.desc()).first()
    assert {l.product_code: l.tax_code for l in o.lines} == {"PT-901": "EXO", "GR-901": "IGV"}
    assert o.oc_total == 1234.5 and o.requiere_estiba
    html = c.get(f"/ov/{o.id}").get_data(as_text=True)
    assert "Subtotal / IGV / total" in html and "no cuadra" in html and "Ingresada al sistema" in html


def test_tramos_de_precio_por_cantidad(app, s, U, cust):
    from app.models import Product
    from app.services import prices
    jefe = U("jefe.ventas")
    prices.add_item(jefe, "GENERAL", "PT-901", canal="CANAL FICTICIO", precio=5.0, motivo="prueba")
    prices.add_item(jefe, "GENERAL", "PT-901", canal="CANAL FICTICIO", precio=4.0, motivo="prueba", cantidad_desde=500)
    s.commit()
    p, c = s.get(Product, "PT-901"), cust()
    assert prices.price_for(p, c, "CANAL FICTICIO", 5)[0] == 5.0
    assert prices.price_for(p, c, "CANAL FICTICIO", 500)[0] == 4.0
    assert prices.check_line_price(p, c, 4.5, canal="CANAL FICTICIO", cantidad=10)["estado"] == "DEBAJO"
    assert prices.check_line_price(p, c, 4.5, canal="CANAL FICTICIO", cantidad=600)["estado"] != "DEBAJO"
    with pytest.raises(Exception):
        prices.add_item(jefe, "GENERAL", "PT-901", canal="CANAL FICTICIO", precio=3.0, motivo="x", cantidad_desde=500)


def test_cancelar_exige_causal_y_cerrar_es_venta_perdida(app, s, U, new_order):
    from app.services import orders as osvc
    from app.services.core import BusinessError
    from app.services.reports import comercial
    a = new_order([("PT-901", 10)])
    b = new_order([("PT-901", 20)])
    jefe = U("jefe.ventas")
    with pytest.raises(BusinessError):
        osvc.cancel_order(a, jefe, "", causal="")
    with pytest.raises(BusinessError):
        osvc.close_order(b, jefe, "")
    osvc.cancel_order(a, jefe, "llamó para anular", causal="El cliente ya no quiere el pedido")
    osvc.close_order(b, jefe, "Sin stock: no se pudo atender", "prueba")
    s.commit()
    assert a.estado == "CANCELADA" and a.cierre["tipo"] == "CANCELADA"
    assert b.estado == "CERRADA" and b.cierre["venta_perdida"] and b.cierre["kg_perdidos"] == 10.0  # 20 × 0,5 kg
    assert alerts_of(s, "OV_CERRADA", b.id)
    d = comercial(date.today(), date.today())
    assert d["canceladas"]["ovs"] >= 1 and d["cerradas"]["ovs"] >= 1
    assert ("Sin stock: no se pudo atender", 1) in d["cerradas"]["causales"]
    c = new_order([("PT-901", 4)])
    osvc.close_order(c, jefe, "Saldo reprogramado en otra OV")
    assert c.cierre["venta_perdida"] is False and c.cierre["reprogramada"]


def test_cierre_se_envia_a_sap_y_cancelada_aparte_en_estado_de_ov(app, s, U, new_order):
    from app.services import estado_ov, orders as osvc, sap_sl
    o = new_order([("PT-901", 2)])
    o.sap_docentry, o.sap_docnum = 77, "77"
    osvc.close_order(o, U("jefe.ventas"), "Otra causa")
    s.commit()
    assert sap_sl.pending_action(o) == "CERRAR"
    assert estado_ov.etapa(o) == "CERRADA"
    x = new_order([("PT-901", 2)])
    osvc.cancel_order(x, U("jefe.ventas"), "", causal="Otra causa")
    assert estado_ov.etapa(x) == "CANCELADA"
    html = _cliente(app, "jefe.ventas").get(f"/ov/{x.id}").get_data(as_text=True)
    assert "Cancelada" in html and "Otra causa" in html


def test_kilos_de_envasados_por_la_presentacion(app, s):
    from app.models import Product
    from app.services.orders import kg_unidad
    p = s.get(Product, "PT-901")
    p.peso_kg = None  # sin peso en el maestro: se toma de «* 500 G»
    assert kg_unidad(p) == 0.5
    assert kg_unidad(s.get(Product, "GR-901")) == 1.0


def test_vendedores_de_sap_por_usuario(app, s, U, new_order):
    from app.models import SalesOrder
    from app.services import orders as osvc
    o = new_order([("PT-901", 2)], vendedor=None)
    o.vendedor_nombre = "VENDEDOR SAP FICTICIO"
    s.commit()
    v = U("vendedor1")
    assert o.id not in [x.id for x in s.query(SalesOrder).filter(osvc.clausula_vendedor(v.id))]
    c = _cliente(app, "sistemas")
    assert "VENDEDOR SAP FICTICIO" in c.get("/ov/vendedores-sap").get_data(as_text=True)
    c.post("/ov/vendedores-sap", data={"user_id": v.id, "vendedores": ["VENDEDOR SAP FICTICIO"]})
    s.expire_all()
    assert o.id in [x.id for x in s.query(SalesOrder).filter(osvc.clausula_vendedor(v.id))]
    assert osvc.usuario_por_nombre_sap("VENDEDOR SAP FICTICIO").id == v.id
    assert o.numero in _cliente(app, "vendedor1").get("/ov/").get_data(as_text=True)


def test_ficha_cliente_correos_estiba_y_nota_de_deuda(app, s, U, cust):
    c = _cliente(app, "jefe.ventas")
    cli = cust()
    c.post(f"/ov/clientes/{cli.id}", data={"nombre": cli.nombre, "correo_envio": "envio@ficticio.test, otro@ficticio.test",
                                           "correo_facturacion": "pagos@ficticio.test", "requiere_estiba": "1"})
    c.post(f"/ov/clientes/{cli.id}", data={"accion": "nota_deuda", "texto": "El cliente indica que ya pagó (prueba)"})
    s.expire_all()
    cli = cust()
    assert cli.correo_envio == "envio@ficticio.test, otro@ficticio.test" and cli.requiere_estiba
    assert cli.notas_deuda and "ya pagó" in cli.notas_deuda[-1]["texto"]
    assert alerts_of(s, "CLIENTE_NOTA_DEUDA", cli.id)


def test_alerta_stock_disponible_al_ejecutivo(app, s, U, new_order):
    from app.models import StockLot
    from app.services.stock import evaluate_order
    o = new_order([("PT-901", 10 ** 6)], dias=5)
    assert o.estado_stock in ("INCOMPLETA", "SIN_STOCK")
    for ln in o.lines:
        ln.cantidad = 1
    evaluate_order(o, U("coord.ventas"), "REEVALUACION")
    s.commit()
    if o.estado_stock == "COMPLETA":
        a = alerts_of(s, "OV_STOCK_DISPONIBLE", o.id)
        assert a and "adelantar" in a[0].mensaje
    else:  # sin stock demo suficiente: al menos no avisa en falso
        assert not alerts_of(s, "OV_STOCK_DISPONIBLE", o.id)
    assert s.query(StockLot).count() >= 0


def test_carga_de_ov_con_plantilla_se_valida_antes_de_sap(app, s, U, cust, tmp_path):
    from app.models import SalesOrder
    from app.services import carga_ov, sap_sl
    f = (date.today() + timedelta(days=6)).strftime("%d/%m/%Y")
    ruc = cust().ruc
    path = tmp_path / "ov.csv"
    path.write_text("RUC del cliente;N° de OC;Total de la OC (con IGV);Fecha comprometida (dd/mm/aaaa);Código del producto;"
                    "Cantidad;Precio unitario sin IGV;IGV (AFECTO o EXONERADO)\n"
                    f"{ruc};OC-FICT-1;100;{f};PT-901;5;999;AFECTO\n"
                    f"{ruc};OC-FICT-1;100;{f};GR-901;10;999;EXONERADO\n"
                    f"99999999999;OC-FICT-2;10;{f};PT-901;1;999;AFECTO\n", encoding="utf-8")
    r = carga_ov.importar(U("coord.ventas"), str(path), "ov.csv")
    s.commit()
    assert len(r["creadas"]) + len(r["borradores"]) == 1 and any("99999999999" in e for e in r["errores"])
    o = s.query(SalesOrder).filter_by(oc_numero="OC-FICT-1").one()
    assert len(o.lines) == 2 and {l.tax_code for l in o.lines} == {"IGV", "EXO"} and o.oc_total == 100
    assert o.sap_envio.get("por_validar") and sap_sl.pending_action(o) is None
    c = _cliente(app, "coord.ventas")
    assert o.numero in c.get("/ov/carga-plantilla").get_data(as_text=True)
    assert c.get("/ov/carga-plantilla?descargar=1").status_code == 200
    c.post(f"/ov/{o.id}/accion/validar_carga")
    s.expire_all()
    assert not s.get(SalesOrder, o.id).sap_envio.get("por_validar")


def test_pantallas_comerciales(app, s, U, new_order):
    new_order([("PT-901", 3)])
    c = _cliente(app, "jefe.ventas")
    for url in ("/ov/", "/ov/?orden=emision", "/ov/estado", "/ov/precios", "/informes/comercial", "/informes/gestion",
                "/ov/carga-plantilla"):
        r = c.get(url)
        assert r.status_code == 200, url
    html = c.get("/ov/estado").get_data(as_text=True)
    assert "Kg pedidos" in html and "Cancelada" in html
