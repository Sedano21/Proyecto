"""V71 (24-nov-2026): expediente por cliente y despacho con todos los SKU y sus guías; faltante o sobrante al validar la
carga; recepción en el cliente conforme o con inconformidad por SKU; guías y facturas de SAP enlazadas a la OV (también
las guías que salen de una factura) y visibles e imprimibles en el expediente. Solo datos ficticios."""
from datetime import date

import pytest

from app.services.core import BusinessError

from .test_flujos import RECEPTOR, _user_chofer, dispatch
from .test_v12 import _route
from .test_v64 import _cliente


def test_faltante_o_sobrante_en_la_carga_detiene_la_salida(app, s, U, cust):
    from app.services import carga_v70 as cv
    r, o = _route(s, U, cust)
    lid = cv.items_carga(r)[0][0]
    with pytest.raises(BusinessError):
        cv.reportar_novedad(U("aux.despacho"), r, "FALTANTE", 0, lid)
    cv.reportar_novedad(U("aux.despacho"), r, "FALTANTE", 2, lid, nota="falta un pallet")
    cv.reportar_novedad(U("seguridad"), r, "SOBRANTE", 1, producto="PT-901")
    assert len(cv.novedades_abiertas(r)) == 2 and r.carga_validada is False
    assert any("faltante" in x for x in cv.falta_para_salir(r))
    with pytest.raises(BusinessError):
        cv.resolver_novedad(U("aux.despacho"), r, 1)  # resuelve Almacén
    cv.resolver_novedad(U("lider.almacen"), r, 1, "se completó")
    cv.resolver_novedad(U("lider.almacen"), r, 2, "se retiró")
    assert cv.falta_para_salir(r) == []
    s.commit()
    html = _cliente(app, "aux.despacho").get("/almacen/carga").get_data(as_text=True)
    assert "Reportar faltante o sobrante" in html


def test_recepcion_con_inconformidad_por_sku_y_guia_al_expediente(s, U, new_order, today):
    from app.models import OrderAttachment, ReturnReceipt
    from app.services import distribution as dist
    o = new_order([("PT-905", 100)])
    stop = dispatch(s, U, o, today)
    ch = _user_chofer(s, U, stop)
    ln = o.lines[0]
    with pytest.raises(BusinessError, match="inconformidad"):
        dist.register_delivery(stop, ch, "foto.jpg", "guia.jpg", entregas={str(ln.id): 90}, recepcion="CONFORME", **RECEPTOR)
    with pytest.raises(BusinessError):
        dist.register_delivery(stop, ch, "foto.jpg", "guia.jpg", recepcion="INCONFORME", **RECEPTOR)
    dist.register_delivery(stop, ch, "foto.jpg", "guia.jpg", entregas={str(ln.id): 90}, recepcion="INCONFORME",
                           novedades={str(ln.id): {"tipo": "OBSERVADO", "observado": 10, "motivo": "sacos rotos"}}, **RECEPTOR)
    s.commit()
    assert stop.recepcion["resultado"] == "INCONFORME" and stop.recepcion["novedades"][0]["devuelto"] == 10
    assert ln.entregado == 90 and o.estado == "ENTREGA_PARCIAL"
    assert s.query(ReturnReceipt).filter_by(order_id=o.id).count() == 1
    tipos = {a.tipo for a in s.query(OrderAttachment).filter_by(order_id=o.id)}
    assert {"GUIA_FIRMADA", "ENTREGA"} <= tipos


def test_recepcion_conforme_y_faltante(s, U, new_order, today):
    from app.services import distribution as dist
    o = new_order([("PT-905", 50)])
    stop = dispatch(s, U, o, today)
    ch = _user_chofer(s, U, stop)
    ln = o.lines[0]
    dist.register_delivery(stop, ch, "foto.jpg", "guia.jpg", entregas={str(ln.id): 45}, recepcion="INCONFORME",
                           novedades={str(ln.id): {"tipo": "FALTANTE", "motivo": "no llegó una caja"}}, **RECEPTOR)
    assert stop.recepcion["novedades"][0]["faltante"] == 5


def test_expediente_muestra_guia_y_factura_de_sap_e_imprime(app, s, U, new_order):
    from app.models import SapBilling, SapMovement
    o = new_order([("PT-901", 5)])
    s.add(SapMovement(clave="GUIA:777010:0", tipo="GUIA", docentry=777010, documento="T001-990", fecha=date.today(),
                      ov_numero=o.numero, cliente="CLIENTE FICTICIO SAC", product_code="PT-901", cantidad=5))
    # la factura no viene en la guía: se enlaza porque SAP dice que sale de esa entrega
    s.add(SapBilling(clave="FACTURA:888010", tipo="FACTURA", numero="F001-990", fecha=date.today(), cliente="CLIENTE FICTICIO SAC",
                     total=59, igv=9, origenes={"guias": [777010], "ovs": [], "leido": True}))
    s.commit()
    c = _cliente(app, "jefe.ventas")
    html = c.get(f"/seguimiento/expedientes/{o.customer_id}/{o.fecha_compromiso.isoformat()}").get_data(as_text=True)
    assert "/ov/guia-sap/777010" in html and "/ov/factura-sap?doc=F001-990" in html and "imprimir seleccionados" in html.lower()
    assert "F001-990" in c.get(f"/ov/{o.id}").get_data(as_text=True)
    r = c.get("/ov/imprimir-documentos?g=777010&f=F001-990&sap=0")
    assert r.status_code == 200 and "T001-990" in r.get_data(as_text=True)
    assert c.get("/ov/imprimir-documentos?g=777010&f=F001-990&sap=0&formato=pdf").data[:4] == b"%PDF"
    lista = c.get("/seguimiento/expedientes").get_data(as_text=True)
    assert "SKU" in lista and "T001-990" in lista


def test_guia_desde_factura_queda_en_la_ov_y_factura_con_origen():
    from app.services import sap_v31
    from app.services.facturacion_sap import origenes

    class SL:
        def get_all(self, ent, params):
            if ent == "DeliveryNotes":
                return [{"DocEntry": 5, "DocNum": 50, "FolioPrefixString": "T001", "FolioNumber": 77, "DocDate": "2026-11-16",
                         "CardName": "CLIENTE FICTICIO", "DocumentLines": [{"ItemCode": "PT-901", "Quantity": 3, "LineNum": 0,
                                                                          "BaseType": 13, "BaseEntry": 9}]}]
            if ent == "Invoices":
                return [{"DocEntry": 9, "DocNum": 90, "FolioPrefixString": "F001", "FolioNumber": 12,
                         "DocumentLines": [{"BaseType": 17, "BaseEntry": 1}]}]
            if ent == "Orders":
                return [{"DocEntry": 1, "DocNum": 1600001}]
            return []
    filas = sap_v31.rows_guias(SL(), date(2026, 11, 1))
    assert filas[0]["ov"] == "1600001" and filas[0]["factura"] == "F001-12"
    o = origenes({"DocumentLines": [{"BaseType": 15, "BaseEntry": 5}, {"BaseType": 17, "BaseEntry": 1}]},
                 {1: {"DocNum": 1600001}})
    assert o["guias"] == [5] and o["ovs"] == ["1600001"]
