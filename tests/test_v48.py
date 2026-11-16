"""V48 (16-nov-2026): lo que falta para el préstamo con el stock de SAP en el momento, datos de transporte de la guía
para el panel «Guía de remisión» de SAP y plan del Excel visible en las vistas diaria, semanal y mensual."""
from datetime import date, timedelta

import pytest

from .test_v26 import _cliente


def _guia(s, lineas, **kw):
    from app.models import SunatGuide
    g = SunatGuide(serie="EG07", numero=kw.get("numero", "480"), lineas=lineas, archivo="", estado="REGISTRADA",
                   inventario={}, sap={}, prestamo={"estado": "PENDIENTE"}, transporte=kw.get("transporte", {}),
                   fecha_traslado=date(2026, 11, 16), placa=kw.get("placa", ""), motivo=kw.get("motivo", ""))
    s.add(g)
    s.commit()
    return g


def test_lo_que_falta_con_el_stock_de_sap_en_el_momento(app, s, monkeypatch):
    from app.services import ingresos_sap
    from app.services.core import set_param
    g = _guia(s, [{"codigo": "PT-901", "lote": "A1", "cantidad": 560}, {"codigo": "PT-901", "lote": "A2", "cantidad": 92},
                  {"codigo": "PT-902", "lote": "B1", "cantidad": 100}])

    class SL:
        def _req(self, method, path, body=None):
            stock = {"PT-901": [{"WarehouseCode": "ALM-001", "InStock": 600}, {"WarehouseCode": "ALM-009", "InStock": 50}],
                     "PT-902": [{"WarehouseCode": "ALM-001", "InStock": 0}]}
            return {"ItemWarehouseInfoCollection": stock[path.split("'")[1]]}
    r = ingresos_sap.faltante(g, "ALM-001", sl=SL())
    assert [f["cantidad"] for f in r["filas"]] == [0, 52, 100] and "SAP en este momento" in r["fuente"]

    class SLLote:
        def sql_query(self, code):
            return [{"ItemCode": "PT-901", "DistNumber": "a1", "WhsCode": "ALM-001", "Quantity": 560},
                    {"ItemCode": "PT-901", "DistNumber": "A2", "WhsCode": "ALM-001", "Quantity": 10},
                    {"ItemCode": "PT-902", "DistNumber": "B1", "WhsCode": "ALM-002", "Quantity": 100}]
    set_param("sap_consultas", {"STOCK": "STOCK_LOTE"})
    r = ingresos_sap.faltante(g, "ALM-001", sl=SLLote())
    assert [f["cantidad"] for f in r["filas"]] == [0, 82, 100] and "por lote" in r["fuente"]


XML = """<?xml version="1.0" encoding="UTF-8"?>
<DespatchAdvice xmlns="urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
<cbc:ID>EG07-00000999</cbc:ID><cbc:IssueDate>2026-11-16</cbc:IssueDate>
<cac:DeliveryCustomerParty><cac:Party><cac:PartyIdentification><cbc:ID>20000000001</cbc:ID></cac:PartyIdentification>
<cac:PartyLegalEntity><cbc:RegistrationName>CLIENTE DEMO SAC</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:DeliveryCustomerParty>
<cac:Shipment><cbc:HandlingCode>01</cbc:HandlingCode><cbc:GrossWeightMeasure unitCode="KGM">245.5</cbc:GrossWeightMeasure>
<cac:ShipmentStage><cbc:TransportModeCode>02</cbc:TransportModeCode><cac:TransitPeriod><cbc:StartDate>2026-11-16</cbc:StartDate></cac:TransitPeriod>
<cac:DriverPerson><cbc:ID>40000000</cbc:ID><cbc:FirstName>CONDUCTOR</cbc:FirstName><cbc:FamilyName>DEMO</cbc:FamilyName>
<cac:IdentityDocumentReference><cbc:ID>Q40000000</cbc:ID></cac:IdentityDocumentReference></cac:DriverPerson></cac:ShipmentStage>
<cac:TransportHandlingUnit><cac:TransportEquipment><cbc:ID>ABC123</cbc:ID></cac:TransportEquipment></cac:TransportHandlingUnit>
<cac:Delivery><cac:DeliveryAddress><cac:AddressLine><cbc:Line>AV DEMO 123</cbc:Line></cac:AddressLine></cac:DeliveryAddress></cac:Delivery>
</cac:Shipment>
<cac:DespatchLine><cbc:DeliveredQuantity unitCode="NIU">4</cbc:DeliveredQuantity><cac:Item><cbc:Description>PRODUCTO DEMO LOTE 1</cbc:Description>
<cac:SellersItemIdentification><cbc:ID>PT-901</cbc:ID></cac:SellersItemIdentification></cac:Item></cac:DespatchLine>
</DespatchAdvice>"""


def test_datos_de_transporte_del_xml_y_a_sap(app, s, U, new_order, monkeypatch):
    from app.services import guias_sunat as gs
    from app.services import sap_sl
    d = gs.parse_xml(XML.encode())
    t = d["transporte"]
    assert t["modalidad"] == "PRIVADO" and t["motivo_codigo"] == "01" and t["peso_bruto"] == 245.5
    assert t["conductor_nombre"] == "CONDUCTOR DEMO" and t["licencia"] == "Q40000000"
    o = new_order([("PT-901", 4)])
    g = _guia(s, [{"codigo": "PT-901", "lote": "", "cantidad": 4}], numero="999", transporte=t, placa="ABC123",
              motivo="Venta")
    g.order_id, g.sap_ov, g.prestamo = o.id, "5001", {}
    s.commit()

    class SL:
        cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}
        body = None

        def get_all(self, path, params=None):
            if path == "UserFieldsMD":
                return [{"Name": "EXX_PLACA", "Description": "Placa del vehículo"},
                        {"Name": "EXX_LICCON", "Description": "Licencia del conductor"},
                        {"Name": "EXX_NOMCON", "Description": "Nombre del conductor"},
                        {"Name": "EXX_MODTRA", "Description": "Modalidad de Traslado",
                         "ValidValuesMD": [{"Value": "01", "Description": "Transporte Publico"},
                                           {"Value": "02", "Description": "Transporte Privado"}]},
                        {"Name": "EXX_MOTTRA", "Description": "Motivo de Traslado"},
                        {"Name": "EXX_FECINI", "Description": "Fecha Inicio Traslado"},
                        {"Name": "EXX_PESO", "Description": "Peso Neto / Carga Total KG"},
                        {"Name": "EXX_OTROS", "Description": "Motivo Traslado / Otros"}]
            if path == "DeliveryNotes":
                return []
            return [{"DocEntry": 77, "DocNum": 5001, "CardCode": "C1",
                     "DocumentLines": [{"LineNum": 0, "ItemCode": "PT-901", "RemainingOpenQuantity": 4}]}]

        def _req(self, method, path, body=None, headers=None):
            SL.body = body
            return {"DocEntry": 900, "DocNum": 3001}
    monkeypatch.setattr(sap_sl, "write_enabled", lambda cfg=None: None)
    monkeypatch.setattr(gs, "_req", lambda u: None)
    gs.enviar_sap(U("asist.distribucion"), g, sl=SL())
    b = SL.body
    assert b["U_EXX_PLACA"] == "ABC123" and b["U_EXX_LICCON"] == "Q40000000" and b["U_EXX_NOMCON"] == "CONDUCTOR DEMO"
    assert b["U_EXX_MODTRA"] == "02" and b["U_EXX_MOTTRA"] == "01" and b["U_EXX_FECINI"] == "2026-11-16"
    assert b["U_EXX_PESO"] == 245.5 and b["U_EXX_OTROS"] == "Venta"
    from werkzeug.datastructures import MultiDict
    gs.editar(U("asist.distribucion"), _guia(s, [{"codigo": "PT-901", "lote": "", "cantidad": 4}], numero="998"),
              MultiDict([("codigo", "PT-901"), ("cantidad", "4"), ("t_transportista_ruc", "20000000009"),
                         ("t_modalidad", "publico")]))
    html = _cliente(app, "asist.distribucion").get("/operacion/guias-sunat").get_data(as_text=True)
    assert "Guía de remisión" in html and "RUC del transportista" in html


def test_plan_del_excel_se_ve_en_semana_y_mes(app, s, U, tmp_path):
    from app.services import production
    from app.services import plan_excel
    from .test_v45 import _xlsx
    hoy = date.today()
    p = tmp_path / "plan.xlsx"
    p.write_bytes(_xlsx([["Fecha", "Código", "Cantidad", "Línea"], [hoy, "PT-901", 100, "R3"],
                         [hoy, "PT-902", 40, "R3"]]))
    plan_excel.importar(U("jefe.produccion"), "DIA", str(p))
    s.commit()
    sem = production.plan_vs_real("SEMANA", hoy, hoy)
    mes = production.plan_vs_real("MES", hoy, hoy)
    assert {f["producto"]: f["plan"] for f in sem["filas"]}.get("PT-901") == 100
    assert {f["producto"]: f["plan"] for f in mes["filas"]}.get("PT-902") == 40
    html = _cliente(app, "jefe.produccion").get("/produccion/plan?periodo=SEMANA").get_data(as_text=True)
    assert "PT-901" in html


def test_porcentaje_por_linea_es_lo_programado_del_dia_frente_a_su_capacidad_diaria(app, s, U):
    from app.models import Product, ProductionPlan
    from app.services import production
    from app.services.v42 import plan_por_linea
    dia = date.today()
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    gr = s.get(Product, "GR-901")
    gr.peso_kg = None  # el granel se mide en kg aunque no tenga peso por unidad
    s.add(ProductionPlan(periodo="DIA", fecha=dia, product_code="GR-901", cantidad=20400, line_code="CIMBRIA", comentario=""))
    s.commit()
    capa = production.capacity_vs_plan(dia, dia)
    l = next(x for x in plan_por_linea(list(s.query(ProductionPlan)), capa, dia) if x["grupo"] == "IQ+CIMB")
    assert l["kg_dia_prog"] == 20400 and l["cap_dia"] == 25500 and l["pct_dia"] == 80.0
    assert next(x for x in capa["filas"] if x["grupo"] == "IQ+CIMB")["programada"] >= 20400
    html = _cliente(app, "jefe.produccion").get(f"/produccion/plan?dia={dia.isoformat()}").get_data(as_text=True)
    assert "Día para el % de cada línea" in html and "80 %" in html
