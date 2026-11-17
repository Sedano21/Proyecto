"""V56 (17-nov-2026): pre-facturas desde las guías abiertas de SAP con validación del facturador, regularización de
facturas emitidas en SUNAT y quitar ítems de la pre-guía. Solo datos ficticios."""
from datetime import date

from .test_v26 import _cliente

BASE = "ZZZ_BASE_PRUEBA"


class _SL:
    cfg = {"company": BASE}

    def __init__(self, abiertas=True):
        self.abiertas = abiertas
        self.posts = []

    def get_all(self, path, params=None):
        if path == "DeliveryNotes":
            if not self.abiertas:
                return []
            return [{"DocEntry": 301, "DocNum": 4001, "FolioPrefixString": "EG07", "FolioNumber": 900, "DocDate": date.today().isoformat(),
                     "CardCode": "C20000000001", "CardName": "CLIENTE PRUEBA SAC", "DocCurrency": "S/",
                     "PaymentGroupCode": 3, "NumAtCard": "OC-PRUEBA-1",
                     "DocumentLines": [
                         {"LineNum": 0, "ItemCode": "MP-902", "ItemDescription": "Insumo prueba", "Quantity": 10,
                          "RemainingOpenQuantity": 10, "UnitPrice": 5.0, "DiscountPercent": 0, "TaxCode": "IGV",
                          "BaseType": 17, "BaseEntry": 77},
                         {"LineNum": 1, "ItemCode": "MP-903", "ItemDescription": "Otro insumo", "Quantity": 4,
                          "RemainingOpenQuantity": 4, "UnitPrice": 2.5, "TaxCode": "IGV", "BaseType": 17, "BaseEntry": 77}]}]
        if path == "Orders":
            return [{"DocEntry": 77, "DocNum": 9000010}]
        if path == "PaymentTermsTypes":
            return [{"GroupNumber": -1, "PaymentTermsGroupName": "CONTADO", "NumberOfAdditionalDays": 0},
                    {"GroupNumber": 3, "PaymentTermsGroupName": "CREDITO 45 DIAS", "NumberOfAdditionalDays": 45}]
        return []

    def _req(self, method, path, body=None, headers=None):
        self.posts.append((path, body))
        return {"DocEntry": 500, "DocNum": 7000, "FolioPrefixString": "F001", "FolioNumber": 55}


def _escritura(U):
    from app.services.core import set_param
    set_param("sap_escritura_ov", True, U("sistemas"))
    set_param("sap_escritura_empresas", [BASE], U("sistemas"))


def test_prefactura_desde_guia_editar_y_crear_en_sap(app, s, U):
    from app.models import Prefactura
    from app.services import prefacturas as pf
    from app.services.core import BusinessError
    sl = _SL()
    r = pf.sincronizar(None, sl=sl)
    s.commit()
    assert r["nuevas"] == ["EG07-900"]
    p = s.query(Prefactura).one()
    assert p.estado == "POR_VALIDAR" and p.ov_numero == "9000010" and pf.total(p) == 60.0
    pf.sincronizar(None, sl=sl)  # no duplica
    assert s.query(Prefactura).count() == 1
    fact = U("facturacion")
    try:
        pf.editar(U("coord.ventas"), p, {})
        raise AssertionError("solo Facturación")
    except BusinessError:
        pass
    try:  # cambiar líneas exige motivo
        pf.editar(fact, p, {"precio_0": "5.5"})
        raise AssertionError("falta motivo")
    except BusinessError:
        pass
    try:  # no más de lo guiado
        pf.editar(fact, p, {"cantidad_0": "11", "motivo": "x"})
        raise AssertionError("más de lo guiado")
    except BusinessError:
        pass
    pf.editar(fact, p, {"precio_0": "5.5", "quitar_1": "1", "motivo": "precio mal digitado; MP-903 no se factura",
                        "observacion": "OC 123"})
    s.commit()
    assert [x["codigo"] for x in p.lineas] == ["MP-902"] and pf.total(p) == 55.0 and p.ediciones[-1]["lineas_cambiadas"]
    pf.validar(fact, p, True, sl=sl)  # sin escritura habilitada: queda validada y pendiente
    s.commit()
    assert p.estado == "VALIDADA" and p.sap["estado"] == "PENDIENTE" and not sl.posts
    _escritura(U)
    assert pf.enviar_pendientes(sl=sl) == 1
    s.commit()
    path, body = sl.posts[-1]
    assert path == "Invoices" and body["CardCode"] == "C20000000001" and "OC 123" in body["Comments"]
    assert body["DocumentLines"] == [{"BaseType": 15, "BaseEntry": 301, "BaseLine": 0, "Quantity": 10, "UnitPrice": 5.5,
                                      "DiscountPercent": 0, "TaxCode": "IGV"}]
    assert p.estado == "ENVIADA_SAP" and p.sap["folio"] == "F001-55"


def test_guia_facturada_en_sap_cierra_la_prefactura(app, s, U):
    from app.models import Prefactura
    from app.services import prefacturas as pf
    pf.sincronizar(None, sl=_SL())
    s.commit()
    r = pf.sincronizar(None, sl=_SL(abiertas=False))  # la guía ya no está abierta: se facturó en SAP
    s.commit()
    assert r["facturadas_en_sap"] == ["EG07-900"] and s.query(Prefactura).one().estado == "FACTURADA_EN_SAP"


XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>F002-00000123</cbc:ID><cbc:IssueDate>2026-11-17</cbc:IssueDate><cbc:DocumentCurrencyCode>PEN</cbc:DocumentCurrencyCode>
 <cac:AccountingCustomerParty><cac:Party><cac:PartyIdentification><cbc:ID>20000000001</cbc:ID></cac:PartyIdentification>
 <cac:PartyLegalEntity><cbc:RegistrationName>CLIENTE PRUEBA SAC</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>
 <cac:LegalMonetaryTotal><cbc:PayableAmount>59.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
 <cac:InvoiceLine><cbc:InvoicedQuantity unitCode="NIU">10</cbc:InvoicedQuantity>
 <cac:Item><cbc:Description>Insumo prueba</cbc:Description><cac:SellersItemIdentification><cbc:ID>MP-902</cbc:ID></cac:SellersItemIdentification></cac:Item>
 <cac:Price><cbc:PriceAmount>5.00</cbc:PriceAmount></cac:Price></cac:InvoiceLine>
</Invoice>"""


def test_regularizar_factura_emitida_en_sunat(app, s, U, tmp_path):
    from app.models import Customer, Prefactura
    from app.services import prefacturas as pf
    c = s.query(Customer).filter_by(ruc="20000000001").first()
    c.codigo_sap = "C20000000001"
    s.commit()
    sl = _SL()
    pf.sincronizar(None, sl=sl)
    s.commit()
    ruta = tmp_path / "f.xml"
    ruta.write_text(XML, encoding="utf-8")
    p = pf.registrar_sunat(U("facturacion"), str(ruta), "f.xml", "f.xml")
    s.commit()
    assert p.serie == "F002" and p.numero == "123" and p.entrega_docentry == 301  # se unió sola a la única guía del cliente
    guia = s.query(Prefactura).filter_by(origen="SAP").one()
    assert guia.estado == "DESCARTADA"
    assert [x["codigo"] for x in p.lineas] == ["MP-902", "MP-903"]
    pf.editar(U("facturacion"), p, {"quitar_1": "1", "motivo": "la factura de SUNAT solo trae MP-902"})
    _escritura(U)
    pf.validar(U("facturacion"), p, True, sl=sl)
    s.commit()
    body = sl.posts[-1][1]
    assert body["FolioPrefixString"] == "F002" and body["FolioNumber"] == 123 and p.estado == "ENVIADA_SAP"
    try:
        pf.registrar_sunat(U("facturacion"), str(ruta), "f.xml", "f.xml")
        raise AssertionError("duplicada")
    except Exception as e:  # noqa: BLE001
        assert "ya se subió" in str(e)


def test_pantallas_y_expediente(app, s, U, new_order):
    from app.models import Prefactura
    from app.services import prefacturas as pf
    o = new_order([("MP-902", 10)])
    o.sap_docnum = "9000010"
    s.commit()
    pf.sincronizar(None, sl=_SL())
    s.commit()
    p = s.query(Prefactura).one()
    assert p.order_id == o.id
    c = _cliente(app, "facturacion")
    html = c.get("/facturacion/").get_data(as_text=True)
    assert "EG07-900" in html and "Por validar" in html
    html = c.get(f"/facturacion/{p.id}").get_data(as_text=True)
    assert "Validar y crear en SAP" in html and "quitar_1" in html
    html = _cliente(app, "jefe.operaciones").get(f"/ov/{o.id}").get_data(as_text=True)
    assert f"pre-factura #{p.id}" in html


def test_preguia_quitar_item_con_motivo(app, s, U, new_order):
    from app.services import guides
    from app.services.core import BusinessError
    o = new_order([("MP-902", 10), ("MP-903", 5)])
    guides.generate(o)
    s.commit()
    u = U("coord.distribucion")
    try:
        guides.review(u, o, {"quitar_1": "1"})
        raise AssertionError("falta motivo")
    except BusinessError:
        pass
    pg = guides.review(u, o, {"quitar_1": "1", "motivo_quitar": "el cliente no lo recibe hoy"})
    s.commit()
    assert [x["codigo"] for x in pg["items"]] == ["MP-902"]
    assert pg["cambios"][-1]["campo"] == "ítem quitado" and pg["cambios"][-1]["motivo"] == "el cliente no lo recibe hoy"
