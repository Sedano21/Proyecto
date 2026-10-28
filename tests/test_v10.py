"""Indicaciones del 28-oct-2026: corte de las 12:00 por tipo de producto y OV del módulo reflejadas en SAP."""
from datetime import date, datetime, timedelta

import pytest

from app.services.core import BusinessError, set_param

from .conftest import alerts_of

LN = [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10, "descuento": 5}]


def _producto(s, code, tipo):
    from app.models import Product
    p = s.get(Product, code) or Product(code=code, descripcion=f"Producto {code}", um="KILOGRAMO")
    p.tipo = tipo
    s.add(p)
    s.flush()
    return p


def test_despues_del_corte_solo_materia_prima_y_granel(s, U):
    from app.services import orders as osvc
    set_param("hora_corte_ov_dia_siguiente", "12:00")
    _producto(s, "MP-TEST", "MP")
    _producto(s, "GR-TEST", "GR")
    hoy = datetime.combine(date.today(), datetime.min.time())
    fecha = date.today() + timedelta(days=3)
    osvc.check_cutoff(fecha, hoy.replace(hour=11, minute=59), productos=["PT-905"])
    osvc.check_cutoff(fecha, hoy.replace(hour=15), productos=["MP-TEST", "GR-TEST"])
    with pytest.raises(BusinessError, match="materia prima y granel"):
        osvc.check_cutoff(fecha, hoy.replace(hour=12, minute=1), productos=["MP-TEST", "PT-905"])
    # MP y granel también para mañana después del corte
    osvc.check_cutoff(date.today() + timedelta(days=1), hoy.replace(hour=17), productos=["GR-TEST"])


class FakeSL:
    def __init__(self, company="ZZZ_CORPRODUC_TEST260826", falla=None):
        self.cfg = {"company": company}
        self.llamadas = []
        self.falla = falla

    def _req(self, method, path, body=None, headers=None):
        self.llamadas.append((method, path, body, headers))
        if self.falla:
            raise BusinessError(self.falla)
        if method == "POST" and path == "Orders":
            return {"DocEntry": 77, "DocNum": 900077}
        return {}


def _ov(s, U, cust, numero="SAP-1"):
    from app.services import orders as osvc
    c = cust()
    c.codigo_sap = "C20000000001"
    o = osvc.create_order(U("coord.ventas"), numero, c.id, date.today() + timedelta(days=4), LN, oc_archivo="oc.pdf",
                          oc_numero="OC-55", evaluar=False)
    s.flush()
    return o


def test_ov_del_modulo_se_crea_actualiza_y_cancela_en_sap(s, U, cust):
    from app.services import orders as osvc
    from app.services import sap_sl
    o = _ov(s, U, cust)
    if o.retenida_precio or o.estado == "BORRADOR":
        pytest.skip("la demo retuvo la OV por precio")
    sl = FakeSL()
    assert sap_sl.pending_action(o) == "CREAR"
    assert sap_sl.push_order(o, U("coord.ventas"), sl) == "CREAR"
    m, path, body, _ = sl.llamadas[-1]
    assert (m, path) == ("POST", "Orders") and body["CardCode"] == "C20000000001" and body["NumAtCard"] == "OC-55"
    assert body["DocumentLines"][0]["ItemCode"] == "PT-905" and body["DocumentLines"][0]["DiscountPercent"] == 10
    assert o.sap_docnum == "900077" and o.sap_docentry == 77 and sap_sl.pending_action(o) is None
    s.flush()
    assert osvc.order_by_number("900077") is o  # la carga desde SAP la reconoce: no se duplica
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 8, "precio_unitario": 10}]})
    assert sap_sl.push_order(o, None, sl) == "ACTUALIZAR"
    m, path, body, headers = sl.llamadas[-1]
    assert (m, path) == ("PATCH", "Orders(77)") and body["DocumentLines"][0]["Quantity"] == 8
    assert headers["B1S-ReplaceCollectionsOnPatch"] == "true"
    osvc.cancel_order(o, U("coord.ventas"), "Cliente desistió")
    assert sap_sl.push_order(o, None, sl) == "CANCELAR" and sl.llamadas[-1][:2] == ("POST", "Orders(77)/Cancel")
    assert sap_sl.pending_action(o) is None


def test_ov_a_sap_solo_en_base_autorizada_y_error_reintenta(s, U, cust):
    from app.services import sap_sl
    o = _ov(s, U, cust, "SAP-2")
    if o.retenida_precio or o.estado == "BORRADOR":
        pytest.skip("la demo retuvo la OV por precio")
    with pytest.raises(BusinessError, match="no está autorizada"):
        sap_sl.push_order(o, None, FakeSL(company="CORPRODUC_PRODUCCION"))
    with pytest.raises(BusinessError, match="SAP respondió"):
        sap_sl.push_order(o, None, FakeSL(falla="SAP respondió 400: Item not found"))
    s.flush()
    assert o.sap_envio["estado"] == "ERROR" and alerts_of(s, "SAP_OV_ERROR", o.id)
    # reintento: no antes de 10 minutos; luego se envía y se cierra la alerta
    ahora = datetime.fromisoformat(o.sap_envio["ts"])
    sl = FakeSL()
    assert sap_sl.push_pending_orders(ahora + timedelta(minutes=2), sl) == 0
    assert sap_sl.push_pending_orders(ahora + timedelta(minutes=11), sl) >= 1
    assert o.sap_envio["estado"] == "ENVIADA" and o.sap_docnum


def test_borrador_y_ov_de_sap_no_se_envian(s, U, cust):
    from app.services import orders as osvc
    from app.services import sap_sl
    c = cust()
    b = osvc.create_order(U("coord.ventas"), "SAP-3", c.id, date.today() + timedelta(days=4), LN, evaluar=False)
    s.flush()
    assert b.estado == "BORRADOR" and sap_sl.pending_action(b) is None
    b.origen = "CARGA_SAP"
    b.estado = "REGISTRADA"
    assert sap_sl.pending_action(b) is None
