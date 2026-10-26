"""Ronda del 26-oct-2026: OV sin opción que cumpla la fecha → bloqueo y decisión de Gerencia General; límite de emisión
de la OV; conector de solo lectura con SAP Service Layer."""
import io
import json
import urllib.error
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError, set_param

from .conftest import alerts_of


def _ov(U, cust, codigo, cantidad, dias, numero):
    from app.services.orders import create_order
    return create_order(U("coord.ventas"), numero, cust().id, date.today() + timedelta(days=dias),
                        [{"product_code": codigo, "cantidad": cantidad, "precio_unitario": 999}], vendedor_id=U("vendedor1").id,
                        oc_archivo="oc.pdf")


def test_ov_sin_opcion_bloqueada_y_decision_de_gg(s, U, cust):
    from app.services import orders as osvc
    from app.services.stock import line_reserved
    o = _ov(U, cust, "PT-902", 999999, 3, "GG-1")
    assert o.estado == "BLOQUEADA" and o.bloqueo_ov["estado"] == "SIN_OPCION" and o.bloqueo_ov["lineas"]
    assert all(line_reserved(l) == 0 for l in o.lines)  # no compromete stock
    a = alerts_of(s, "OV_SIN_OPCION", o.id)
    assert a and U("vendedor1").id in a[0].usuarios
    with pytest.raises(BusinessError):
        osvc.decide_gg(o, U("gerente.general"), True)  # aún no se pidió
    with pytest.raises(BusinessError, match="por qué"):
        osvc.request_gg_decision(o, U("coord.ventas"), "")
    osvc.request_gg_decision(o, U("coord.ventas"), "Cliente estratégico: campaña con fecha fija")
    assert o.bloqueo_ov["estado"] == "PENDIENTE_GG" and alerts_of(s, "OV_DECISION_GG", o.id)
    with pytest.raises(BusinessError):
        osvc.renegotiate_date(o, U("coord.ventas"), o.fecha_compromiso + timedelta(days=5))
    with pytest.raises(BusinessError):
        osvc.decide_gg(o, U("gerente.comercial"), True)  # solo Gerencia General
    osvc.decide_gg(o, U("gerente.general"), True, "Va", "ALTA")
    assert o.estado not in ("BLOQUEADA",) and o.urgente and o.bloqueo_ov["decision"]["aprobada"]
    assert alerts_of(s, "OV_DECISION_GG_RESUELTA", o.id)
    assert o.compromiso.get("estado")  # sigue el flujo normal (compromiso de Operaciones)


def test_gg_no_aprueba_y_comercial_renegocia(s, U, cust):
    from app.services import orders as osvc
    o = _ov(U, cust, "PT-904", 999999, 3, "GG-2")
    osvc.request_gg_decision(o, U("jefe.ventas"), "Lo pide el cliente")
    with pytest.raises(BusinessError, match="por qué"):
        osvc.decide_gg(o, U("gerente.general"), False, "")
    osvc.decide_gg(o, U("gerente.general"), False, "No hay capacidad esa semana")
    assert o.estado == "BLOQUEADA" and o.bloqueo_ov["estado"] == "RENEGOCIAR"
    # con una cantidad posible y nueva fecha se vuelve a analizar y queda activa
    o.lines[0].cantidad = 10
    osvc.renegotiate_date(o, U("jefe.ventas"), o.fecha_compromiso + timedelta(days=4), "Acordado con el cliente")
    assert o.estado != "BLOQUEADA" and o.bloqueo_ov["estado"] == "RENEGOCIADA"


def test_limite_de_emision_un_dia_antes(s, U, cust):
    from app.services import orders as osvc
    o = _ov(U, cust, "PT-905", 10, 0, "EM-1")  # para hoy
    assert o.estado == "BLOQUEADA" and o.bloqueo_ov["tipo"] == "EMISION"
    assert alerts_of(s, "OV_RENEGOCIAR_FECHA", o.id)
    osvc.renegotiate_date(o, U("coord.ventas"), date.today() + timedelta(days=2), "Nueva fecha")
    assert o.estado != "BLOQUEADA"
    o2 = _ov(U, cust, "PT-905", 10, 2, "EM-2")
    assert o2.estado != "BLOQUEADA"
    set_param("dias_minimos_emision_ov", 0)
    assert _ov(U, cust, "PT-905", 1, 0, "EM-3").estado != "BLOQUEADA"


def test_pantalla_ov_bloqueada(app, s, U, cust):
    from .test_web import csrf, login
    o = _ov(U, cust, "PT-902", 999999, 3, "GG-3")
    s.commit()
    c = app.test_client()
    login(c, "coord.ventas")
    html = c.get(f"/ov/{o.id}").get_data(as_text=True)
    assert "OV bloqueada" in html and "pedir decisión de Gerencia General" in html
    tok = csrf(c, f"/ov/{o.id}")
    r = c.post(f"/ov/{o.id}/accion/solicitar_gg", data={"_csrf": tok, "justificacion": "Campaña"}, follow_redirects=True)
    assert "Gerencia General" in r.get_data(as_text=True)
    c2 = app.test_client()
    login(c2, "gerente.general")
    assert 'id="dlg-gg-dec"' in c2.get(f"/ov/{o.id}").get_data(as_text=True)
    tok = csrf(c2, f"/ov/{o.id}")
    c2.post(f"/ov/{o.id}/accion/decision_gg", data={"_csrf": tok, "aprobar": "1", "prioridad": "ALTA"})
    s.expire_all()
    from app.models import SalesOrder
    assert s.get(SalesOrder, o.id).estado != "BLOQUEADA"


# ------------------------------------------------------------------ SAP Service Layer
class _Resp:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_sl(llamadas):
    def opener(req, timeout):
        url = req.full_url
        llamadas.append((req.get_method(), url))
        assert req.get_method() in ("GET",) or url.endswith(("/Login", "/Logout"))  # solo lectura
        if url.endswith("/Login"):
            body = json.loads(req.data)
            if body["Password"] != "clave":
                raise urllib.error.HTTPError(url, 401, "x", {}, io.BytesIO(json.dumps(
                    {"error": {"message": {"value": "Fail to get DB Credentials"}}}).encode()))
            return _Resp({"SessionId": "abc", "Version": "1000190", "SessionTimeout": 30})
        if url.endswith("/Logout"):
            return _Resp({})
        if "SalesPersons" in url:
            return _Resp({"value": [{"SalesEmployeeCode": 1, "SalesEmployeeName": "Ejecutivo de Ventas 1"}]})
        if "BusinessPartners" in url:
            return _Resp({"value": [{"CardCode": "C001", "CardName": "CLIENTE DEMO MAYORISTA S.A.C.",
                                     "FederalTaxID": "20000000001", "Address": "AV. DEMO 100", "City": "LIMA", "County": "ATE"}]})
        if "Orders" in url and "skip" not in url:
            return _Resp({"value": [{"DocNum": 5001, "DocDate": "2026-10-26", "DocDueDate": (date.today() + timedelta(days=5)).isoformat(),
                                     "CardCode": "C001", "CardName": "CLIENTE DEMO MAYORISTA S.A.C.", "SalesPersonCode": 1,
                                     "DocumentLines": [{"ItemCode": "PT-905", "ItemDescription": "QUINUA", "Quantity": 20,
                                                        "RemainingOpenQuantity": 20, "Price": 9.5}]}],
                          "odata.nextLink": "Orders?$skip=500"})
        if "Orders" in url:
            return _Resp({"value": [{"DocNum": 5002, "DocDate": "2026-10-26", "DocDueDate": (date.today() + timedelta(days=6)).isoformat(),
                                     "CardCode": "C001", "CardName": "CLIENTE DEMO MAYORISTA S.A.C.", "SalesPersonCode": 1,
                                     "DocumentLines": [{"ItemCode": "PT-901", "ItemDescription": "ARVEJA", "Quantity": 5,
                                                        "RemainingOpenQuantity": 5, "Price": 4}]}]})
        raise AssertionError(url)
    return opener


def _cfg(clave="clave"):
    return {"url": "https://sap.invalid:50000/b1s/v1", "company": "EMPRESA_PRUEBA", "user": "integracion", "password": clave,
            "ca": "", "verify": True, "timeout": 5}


def test_sap_service_layer_ov_por_el_flujo_de_cargas(s, U, tmp_path):
    from app.services import sap_sl
    llamadas = []
    with pytest.raises(BusinessError, match="no está configurada"):
        sap_sl.ServiceLayer()
    with pytest.raises(BusinessError, match="401"):
        sap_sl.ServiceLayer(_cfg("mala"), opener=_fake_sl(llamadas)).login()
    sl = sap_sl.ServiceLayer(_cfg(), opener=_fake_sl(llamadas))
    assert sap_sl.test_connection(sl)["version"] == "1000190"
    sl.login()
    b = sap_sl.sync("OV", U("jefe.ventas"), str(tmp_path), sl=sl, autoconfirmar=False)
    sl.logout()
    assert b.archivo.startswith("SAP_SL_OV_") and len(b.rows) == 2  # dos páginas
    assert {r.datos["numero"] for r in b.rows} == {"5001", "5002"} or {r.datos["numero"] for r in b.rows} == {5001, 5002}
    assert all(m == "GET" or u.endswith(("/Login", "/Logout")) for m, u in llamadas)
    with pytest.raises(BusinessError, match="sap_consultas"):
        sl.login()
        sap_sl.fetch("STOCK", sl)


def test_pantalla_sap_sin_configurar(app):
    from .test_web import login
    c = app.test_client()
    login(c, "jefe.ventas")
    html = c.get("/almacen/cargas/sap").get_data(as_text=True)
    assert "aún no está configurada" in html and "Órdenes de venta abiertas" in html
