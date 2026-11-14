"""V35 (14-nov-2026): guías SUNAT sincronizadas con SAP, guías de SAP en la OV, préstamo por inventario negativo e
ingreso de mercadería a SAP por la Jefatura de Operaciones. Solo datos ficticios."""
import re
from datetime import date

import pytest

from .conftest import alerts_of
from .test_v26 import _cliente


def _guia(s, o, numero="457"):
    from app.models import SunatGuide
    g = SunatGuide(serie="EG07", numero=numero, lineas=[{"codigo": "PT-901", "descripcion": "x", "lote": "251026VG",
                                                         "cantidad": 12, "fp": "2026-11-03", "fv": "2027-11-03"}],
                   sap_ov="1636305", order_id=o.id, archivo="", estado="REGISTRADA", inventario={}, sap={}, prestamo={},
                   destinatario="Cliente Demo")
    s.add(g)
    s.commit()
    return g


class _SL:
    cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}
    posts = []
    stock = False

    def get_all(self, path, params=None):
        return [{"DocEntry": 77, "DocNum": 1636305, "CardCode": "C1",
                 "DocumentLines": [{"LineNum": 0, "ItemCode": "PT-901", "RemainingOpenQuantity": 20}]}]

    def _req(self, method, path, body=None, headers=None):
        from app.services.core import BusinessError
        _SL.posts.append((path, body))
        if path == "DeliveryNotes" and not _SL.stock:
            raise BusinessError("SAP respondió 400: Quantity falls into negative inventory [DocumentLines.ItemCode][line: 1]")
        if path == "InventoryGenEntries":
            _SL.stock = True
            return {"DocEntry": 501, "DocNum": 61}
        return {"DocEntry": 900, "DocNum": 3001}


def test_prestamo_e_ingreso_de_mercaderia(app, s, U, new_order, monkeypatch):
    from app.models import GoodsReceipt
    from app.services import guias_sunat as gs
    from app.services import ingresos_sap, sap_sl
    from app.services.core import BusinessError
    monkeypatch.setattr(sap_sl, "write_enabled", lambda cfg=None: None)
    _SL.posts, _SL.stock = [], False
    o = new_order([("PT-901", 20)])
    g = _guia(s, o)
    with pytest.raises(BusinessError, match="negative inventory"):
        gs.enviar_sap(U("asist.distribucion"), g, sl=_SL())
    s.commit()
    assert g.prestamo["estado"] == "PENDIENTE" and g.sap["estado"] == "ERROR"
    al = alerts_of(s, "PRESTAMO_STOCK", g.id)
    assert al and set(al[0].roles) >= {"JEFE_OPERACIONES", "COORD_DISTRIBUCION", "JEFE_LOGISTICA"}
    with pytest.raises(BusinessError, match="Jefatura de Operaciones"):
        ingresos_sap.registrar(U("coord.distribucion"), date.today(), "ALM-001", "x", g.prestamo["lineas"], g, sl=_SL())
    ing = ingresos_sap.registrar(U("jefe.operaciones"), date.today(), "ALM-001", "Préstamo guía EG07-457",
                                 g.prestamo["lineas"], g, sl=_SL())
    s.commit()
    path, body = next(x for x in _SL.posts if x[0] == "InventoryGenEntries")
    ln = body["DocumentLines"][0]
    assert ln["ItemCode"] == "PT-901" and ln["WarehouseCode"] == "ALM-001" and ln["Quantity"] == 12
    assert ln["BatchNumbers"][0] == {"BatchNumber": "251026VG", "Quantity": 12, "ManufacturingDate": "2026-11-03",
                                     "ExpiryDate": "2027-11-03"}
    assert ing.estado == "EN_SAP" and ing.sap["docnum"] == 61
    assert g.sap["estado"] == "OK" and g.prestamo["estado"] == "INGRESADO"  # la guía se volvió a enviar sola
    assert s.query(GoodsReceipt).count() == 1


def test_pantallas_del_prestamo(app, s, U, new_order):
    o = new_order([("PT-901", 20)])
    g = _guia(s, o, "458")
    from app.services import guias_sunat as gs
    gs.pedir_prestamo(U("asist.distribucion"), g, "negative inventory")
    s.commit()
    html = _cliente(app, "jefe.operaciones").get("/operacion/guias-sunat").get_data(as_text=True)
    assert "PRÉSTAMO PENDIENTE" in html and "Registrar el ingreso (préstamo)" in html
    html = _cliente(app, "jefe.operaciones").get(f"/operacion/ingresos-mercaderia?guia={g.id}").get_data(as_text=True)
    assert "préstamo para la guía EG07-458" in html and 'value="251026VG"' in html
    assert _cliente(app, "vendedor1").get("/operacion/ingresos-mercaderia").status_code == 403


def test_guias_sunat_y_ov_se_actualizan_con_sap(app, s, U, new_order):
    from app.models import SapMovement
    from app.services import guias_sunat as gs
    o = new_order([("PT-901", 20)])
    o.sap_docnum = "1636305"
    g = _guia(s, o, "00000459")
    s.add(SapMovement(clave="GUIA:900:0", tipo="GUIA", docentry=900, documento="EG07-459", fecha=date.today(),
                      ov_numero="1636305", product_code="PT-901", cantidad=12))
    s.commit()
    assert gs.conciliar_con_sap() == 1
    s.commit()
    assert g.sap["estado"] == "OK" and g.estado == "ENVIADA_SAP"
    html = _cliente(app, "coord.ventas").get(f"/ov/{o.id}").get_data(as_text=True)
    assert "Guías de esta OV en SAP" in html and "EG07-459" in html


def test_ingreso_sin_cuenta_contable_y_reintento(app, s, U, monkeypatch):
    """V36: SAP pide la cuenta contable de compensación («Inventory account is not defined»); se reintenta con ella."""
    from app.services import ingresos_sap, sap_sl
    monkeypatch.setattr(sap_sl, "write_enabled", lambda cfg=None: None)

    class SLc:
        cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}
        body = None

        def _req(self, method, path, body=None, headers=None):
            from app.services.core import BusinessError
            SLc.body = body
            if not body["DocumentLines"][0].get("AccountCode"):
                raise BusinessError("SAP respondió 400: Inventory account is not defined [DocumentLines.AccountCode][line: 1]")
            return {"DocEntry": 5, "DocNum": 70}
    r = ingresos_sap.registrar(U("jefe.operaciones"), date.today(), "ALM-001", "Préstamo de prueba",
                               [{"codigo": "PT-901", "lote": "264005DV", "cantidad": 4, "fv": "2027-11-03"}], sl=SLc())
    s.commit()
    assert r.estado == "ERROR" and "CUENTA CONTABLE" in ingresos_sap.mensaje_error(r.sap["error"])
    assert "UnitPrice" not in SLc.body["DocumentLines"][0]  # el préstamo va sin costo
    ingresos_sap.reintentar(U("jefe.operaciones"), r, "6911101", sl=SLc())
    s.commit()
    assert r.estado == "EN_SAP" and SLc.body["DocumentLines"][0]["AccountCode"] == "6911101" and r.sap["cuenta"] == "6911101"
    html = _cliente(app, "jefe.operaciones").get("/operacion/ingresos-mercaderia").get_data(as_text=True)
    assert "Cuenta contable de compensación" in html and "Costo unitario" not in html
