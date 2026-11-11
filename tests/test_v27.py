"""V27 (11-nov-2026): Gerente de Administración y Finanzas, nombre propio, días no laborables, guías SUNAT,
facturas y órdenes de servicio en la conciliación, solicitudes de fumigación, firmas por persona, estado de OV,
desempeño por persona, checklist vehicular diario y vistos buenos de la carga. Solo datos ficticios."""
import os
import re
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


def _alm(s):
    from app.models import StockLot
    return s.query(StockLot).filter(StockLot.product_code == "PT-901").first().warehouse_code


def _tok(html):
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


# ------------------------------------------------------------------ perfiles y cuenta
def test_gerente_admin_finanzas_y_nombre_propio(app, s, U):
    from app.services.core import has_perm, roles_of
    g = U("gerente.finanzas")
    assert has_perm(g, "finanzas.gestionar") and has_perm(g, "margen.ver") and has_perm(g, "tablero.empresa")
    assert {"JEFE_ADMIN_FINANZAS", "COORD_FINANZAS"} <= roles_of(g)
    c = _cliente(app, "vendedor1")
    html = c.get("/cambiar-clave").get_data(as_text=True)
    assert "Mi nombre" in html
    r = c.post("/cambiar-clave", data={"_csrf": _tok(html), "accion": "nombre", "nombre": "  Ejecutivo   Demo Uno  "})
    assert r.status_code == 302
    s.expire_all()
    assert U("vendedor1").nombre == "Ejecutivo Demo Uno"


# ------------------------------------------------------------------ días no laborables
def test_dia_no_laborable_replanifica(app, s, U, new_order):
    from app.models import PickingTask
    from app.services import dias_no_laborables as dnl
    from app.services import production, rutas_manual as rm
    manana = date.today() + timedelta(days=1)
    while manana.weekday() >= 5:
        manana += timedelta(days=1)
    o = new_order([("PT-901", 2)], dias=5)
    t = PickingTask(order_id=o.id, warehouse_code=_alm(s), fecha=manana, asignados=[])
    s.add(t)
    s.commit()
    with pytest.raises(BusinessError):
        dnl.registrar(U("vendedor1"), "Almacén", manana, "inventario")
    with pytest.raises(BusinessError):
        dnl.registrar(U("jefe.logistica"), "Almacén", manana, "")
    d = dnl.registrar(U("jefe.logistica"), "Almacén", manana, "Inventario general")
    dp = dnl.registrar(U("jefe.produccion"), "Producción", manana, "Mantenimiento de líneas")
    dd = dnl.registrar(U("jefe.logistica"), "Distribución", manana, "Inventario general")
    s.commit()
    assert any(x["tipo"] == "PICKING" and x["id"] == t.id for x in dnl.afectados("Almacén", manana))
    assert production.day_factor(manana) == 0
    with pytest.raises(BusinessError, match="no labora"):
        rm.create_manual(U("coord.distribucion"), manana, {"tipo_transportista": "TRABAJADOR"}, [o.id])
    r = dnl.replanificar(U("jefe.logistica"), d)
    s.commit()
    assert r["movidos"] == 1 and s.get(PickingTask, t.id).fecha == r["destino"] > manana
    assert d.replanificado and dp.id and dd.id
    html = _cliente(app, "jefe.logistica").get("/dias-no-laborables").get_data(as_text=True)
    assert "Días no laborables por área" in html and "Inventario general" in html


# ------------------------------------------------------------------ guías SUNAT
TEXTO_GUIA = """RUC N°20000000009
GUÍA DE REMISIÓN ELECTRÓNICA
REMITENTE
N° EG07 - 00000123
EMPRESA DEMO SAC
09/11/2026 08:28 AM
Fecha de inicio de Traslado :
Motivo de Traslado :
09/11/2026
Venta AV. DEMO 123 - LIMA - LIMA
Punto de llegada
Punto de Partida
Datos del Destinatario :CLIENTE DEMO MAYORISTA S.A.C. - REGISTRO ÚNICO DE CONTRIBUYENTES N° 20000000001
Bienes por transportar:
producto demo 901 * 500 g
lote 900001aa  fp: 27-09-26    fv: 27-09-27
pt-901 UNIDAD (NIU)1 NO 4.00
producto demo 902 * 500 g
lote 900002bb  fp: 26-08-26  fv: 26-08-27
pt-902 UNIDAD (NIU)2 NO 2.00
Placa de vehículo:ABC123
"""

XML_GUIA = b"""<?xml version="1.0" encoding="UTF-8"?>
<DespatchAdvice xmlns="urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>EG07-124</cbc:ID><cbc:IssueDate>2026-11-09</cbc:IssueDate>
 <cac:DeliveryCustomerParty><cac:Party><cac:PartyIdentification><cbc:ID>20000000001</cbc:ID></cac:PartyIdentification>
 <cac:PartyLegalEntity><cbc:RegistrationName>CLIENTE DEMO</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:DeliveryCustomerParty>
 <cac:Shipment><cbc:HandlingInstructions>Venta</cbc:HandlingInstructions><cac:ShipmentStage><cac:TransitPeriod><cbc:StartDate>2026-11-10</cbc:StartDate></cac:TransitPeriod></cac:ShipmentStage>
 <cac:TransportHandlingUnit><cac:TransportEquipment><cbc:ID>ABC123</cbc:ID></cac:TransportEquipment></cac:TransportHandlingUnit></cac:Shipment>
 <cac:DespatchLine><cbc:ID>1</cbc:ID><cbc:DeliveredQuantity unitCode="NIU">3</cbc:DeliveredQuantity>
 <cac:Item><cbc:Description>producto demo 901 lote 900001aa fp: 27-09-26 fv: 27-09-27</cbc:Description>
 <cac:SellersItemIdentification><cbc:ID>pt-901</cbc:ID></cac:SellersItemIdentification></cac:Item></cac:DespatchLine>
</DespatchAdvice>"""


def test_lectura_de_guia_sunat_texto_y_xml():
    from app.services import guias_sunat as gs
    g = gs.parse_text(TEXTO_GUIA)
    assert (g["serie"], g["numero"], g["destinatario_ruc"], g["placa"], g["motivo"]) == ("EG07", "123", "20000000001", "ABC123", "Venta")
    assert g["fecha_emision"] == date(2026, 11, 9)
    l1 = g["lineas"][0]
    assert (l1["codigo"], l1["cantidad"], l1["lote"], l1["fp"], l1["fv"]) == ("PT-901", 4.0, "900001aa", "2026-09-27", "2027-09-27")
    assert len(g["lineas"]) == 2
    x = gs.parse_xml(XML_GUIA)
    assert (x["serie"], x["numero"], x["fecha_traslado"]) == ("EG07", "124", date(2026, 11, 10))
    assert x["lineas"][0]["codigo"] == "PT-901" and x["lineas"][0]["lote"] == "900001aa" and x["lineas"][0]["cantidad"] == 3
    with pytest.raises(BusinessError):
        gs.parse_text("sin datos de guía")


def test_guia_sunat_ov_inventario_y_sap(app, s, U, new_order, tmp_path, monkeypatch):
    from app.models import StockLot
    from app.services import guias_sunat as gs
    from app.services import sap_sl
    o = new_order([("PT-901", 4)], dias=3)
    lot = StockLot(product_code="PT-901", warehouse_code=_alm(s), lote="900001AA", cantidad=10, estado="DISPONIBLE")
    s.add(lot)
    s.commit()
    p = tmp_path / "g.xml"
    p.write_bytes(XML_GUIA)
    with pytest.raises(BusinessError):
        gs.registrar(U("vendedor1"), str(p))
    g = gs.registrar(U("asist.distribucion"), str(p), "g.xml")
    s.commit()
    assert g.order_id == o.id  # una sola OV del cliente con ese producto: se une sola
    with pytest.raises(BusinessError, match="ya está cargada"):
        gs.registrar(U("asist.distribucion"), str(p))
    with pytest.raises(BusinessError):
        gs.decidir_inventario(U("asist.distribucion"), g, "DESCONTAR")
    gs.decidir_inventario(U("jefe.operaciones"), g, "DESCONTAR")
    s.commit()
    assert s.get(StockLot, lot.id).cantidad == 7 and g.inventario["decision"] == "DESCONTADO"
    with pytest.raises(BusinessError, match="ya fue decidido"):
        gs.decidir_inventario(U("jefe.operaciones"), g, "YA_DESCONTADO")

    class SL:
        cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}
        enviado = None

        def get_all(self, path, params=None):
            return [{"DocEntry": 77, "DocNum": 5001, "CardCode": "C20000000001",
                     "DocumentLines": [{"LineNum": 0, "ItemCode": "PT-901", "RemainingOpenQuantity": 4}]}]

        def _req(self, method, path, body=None, headers=None):
            SL.enviado = (method, path, body)
            return {"DocEntry": 900, "DocNum": 3001}
    gs.unir(U("asist.distribucion"), g, o.id, "5001")
    monkeypatch.setattr(sap_sl, "write_enabled", lambda cfg=None: None)
    gs.enviar_sap(U("asist.distribucion"), g, sl=SL())
    s.commit()
    m, path, body = SL.enviado
    assert (m, path) == ("POST", "DeliveryNotes") and body["FolioPrefixString"] == "EG07" and body["FolioNumber"] == 124
    assert body["DocumentLines"][0]["BaseEntry"] == 77 and body["DocumentLines"][0]["BatchNumbers"][0]["BatchNumber"] == "900001AA"
    assert g.estado == "ENVIADA_SAP" and g.sap["docnum"] == 3001
    html = _cliente(app, "asist.distribucion").get("/operacion/guias-sunat").get_data(as_text=True)
    assert "EG07-124" in html and "EN SAP" in html


def test_guia_sunat_desde_pdf(app, s, U, tmp_path):
    from fpdf import FPDF
    from app.services import guias_sunat as gs
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    for ln in TEXTO_GUIA.splitlines():
        pdf.cell(0, 5, ln.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT")
    p = tmp_path / "guia.pdf"
    pdf.output(str(p))
    d = gs.leer_archivo(str(p))
    assert d["serie"] == "EG07" and d["numero"] == "123" and [x["codigo"] for x in d["lineas"]] == ["PT-901", "PT-902"]


# ------------------------------------------------------------------ conciliación: facturas y órdenes de servicio
def test_conciliacion_con_facturas_y_ordenes_de_servicio(app, s, U, new_order):
    from app.models import CustomerInvoice, UploadBatch, UploadRow
    from app.services import despachos_sap as ds
    from app.services.core import set_param
    o = new_order([("PT-901", 5)], dias=3)
    b = UploadBatch(tipo="OV", archivo="SAP_SL_OV_x.xlsx", estado="CONFIRMADO")
    s.add(b)
    s.flush()
    s.add(UploadRow(batch_id=b.id, fila=2, datos={"numero": o.numero, "estado": "Abierto", "cliente": "Demo",
                                                   "fecha_compromiso": "2026-11-20", "producto": "PT-901", "solicitado": 5, "entregado": 0}))
    s.add(CustomerInvoice(customer_id=o.customer_id, order_id=o.id, tipo="FACTURA", numero="F001-55", fecha=date.today(),
                          monto=10, saldo=10))
    set_param("sap_servicios_ultimo", {"ts": "2026-11-11T10:00", "filas": [
        {"ov": o.numero, "orden": 801, "producto": "PT-901", "planificado": 5, "completado": 5, "estado": "CERRADA"}]})
    s.commit()
    f = next(x for x in ds.conciliar()["filas"] if x["ov"] == o.numero)
    assert "F001-55" in f["facturas"] and f["servicios"][0]["orden"] == 801
    assert any("Orden de servicio" in a and "falta despacharla" in a for a in f["alertas"])


# ------------------------------------------------------------------ fumigación solicitada
def test_solicitud_de_fumigacion_parcial(app, s, U):
    from app.models import StockLot
    from app.services import fumigacion_solicitudes as fs
    l1 = StockLot(product_code="PT-901", warehouse_code=_alm(s), lote="FUM-DEMO-1", cantidad=100, estado="DISPONIBLE")
    l2 = StockLot(product_code="PT-902", warehouse_code=_alm(s), lote="FUM-DEMO-2", cantidad=30, estado="DISPONIBLE")
    s.add_all([l1, l2])
    s.commit()
    with pytest.raises(BusinessError):
        fs.solicitar(U("vendedor1"), "Almacén", "gorgojo", [{"lot_id": l1.id, "cantidad": 40}])
    with pytest.raises(BusinessError):
        fs.solicitar(U("coord.almacen"), "Almacén", "gorgojo", [{"lot_id": l1.id, "cantidad": 400}])
    r = fs.solicitar(U("coord.almacen"), "Almacén", "Presencia de gorgojo",
                     [{"lot_id": l1.id, "cantidad": 40}, {"lot_id": l2.id, "cantidad": ""}])
    s.commit()
    with pytest.raises(BusinessError):
        fs.aprobar(U("coord.almacen"), r, "Patio", date.today(), date.today() + timedelta(days=3))
    with pytest.raises(BusinessError):
        fs.aprobar(U("jefe.calidad"), r, "Techo", date.today(), date.today() + timedelta(days=3))
    fs.aprobar(U("jefe.calidad"), r, "Contenedor 1", date.today(), date.today() + timedelta(days=3))
    s.commit()
    fs.confirmar_ingreso(U("coord.almacen"), r, {str(l1.id): "40", str(l2.id): "30"})
    s.commit()
    s.expire_all()
    assert r.estado == "EN_FUMIGACION"
    assert s.get(StockLot, l1.id).cantidad == 60 and s.get(StockLot, l1.id).estado == "DISPONIBLE"
    fum = s.query(StockLot).filter_by(lote="FUM-DEMO-1", estado="EN_FUMIGACION").one()
    assert fum.cantidad == 40 and fum.fumigacion["zona"] == "Contenedor 1"
    assert s.query(StockLot).filter_by(lote="FUM-DEMO-2", estado="EN_FUMIGACION").one().cantidad == 30
    html = _cliente(app, "jefe.calidad").get("/calidad/fumigacion/solicitudes").get_data(as_text=True)
    assert "Fumigación #" in html and "Contenedor 1" in html


# ------------------------------------------------------------------ firmas, estado de OV y desempeño
def test_firma_solo_jefe_y_supervisora(app, s, U):
    from app.services import quality as q
    assert q.param("firma_certificado_roles") == ["JEFE_CALIDAD", "SUPERV_CALIDAD"]
    c = _cliente(app, "asist.calidad")
    html = c.get("/calidad/certificados").get_data(as_text=True)
    assert "Mi firma para los certificados" not in html
    assert c.post("/calidad/firma", data={"_csrf": _tok(html)}).status_code == 403
    assert "Mi firma para los certificados" in _cliente(app, "superv.calidad").get("/calidad/certificados").get_data(as_text=True)


def test_estado_de_ov_y_desempeno(app, new_order):
    new_order([("PT-901", 2)], dias=2)
    html = _cliente(app, "jefe.ventas").get("/ov/estado").get_data(as_text=True)
    assert "Estado de OV" in html and "Picking" in html and "Factura" in html
    html = _cliente(app, "gestion.humana").get("/seguimiento/desempeno-personas").get_data(as_text=True)
    assert "Desempeño por persona" in html


# ------------------------------------------------------------------ checklist diario y vistos buenos
def _vals():
    from app.services import vehicle_checklist as vc
    return {code: "B" for code, *_ in vc.items()}


def test_checklist_diario_varios_vehiculos(app, s, U):
    from app.models import Driver, Vehicle
    from app.services import vehicle_checklist as vc
    u = U("conductor1")
    d = s.query(Driver).filter_by(user_id=u.id).first()
    v1, v2 = s.query(Vehicle).filter(Vehicle.propio.is_(True)).limit(2).all()
    with pytest.raises(BusinessError, match="foto"):
        vc.register_daily(u, v1, "INICIO_DIA", _vals(), 1000, foto_adelante="a.jpg")
    with pytest.raises(BusinessError, match="inicio del día"):
        vc.register_daily(u, v1, "FIN_DIA", _vals(), 1000, foto_adelante="a.jpg", foto_atras="b.jpg")
    vc.register_daily(u, v1, "INICIO_DIA", _vals(), 1000, foto_adelante="a.jpg", foto_atras="b.jpg")
    vc.register_daily(u, v2, "INICIO_DIA", _vals(), 500, foto_adelante="c.jpg", foto_atras="d.jpg")
    with pytest.raises(BusinessError, match="Ya registró"):
        vc.register_daily(u, v1, "INICIO_DIA", _vals(), 1000, foto_adelante="a.jpg", foto_atras="b.jpg")
    with pytest.raises(BusinessError, match="no puede ser menor"):
        vc.register_daily(u, v1, "FIN_DIA", _vals(), 900, foto_adelante="a.jpg", foto_atras="b.jpg")
    c = vc.register_daily(u, v1, "FIN_DIA", _vals(), 1080, foto_adelante="e.jpg", foto_atras="f.jpg")
    s.commit()
    assert c.fotos == {"adelante": "e.jpg", "atras": "f.jpg"} and c.driver_id == d.id
    st = vc.daily_status(u)
    assert len(st["filas"]) == 2
    vc.validate(U("seguridad"), c, True, 1080)
    s.commit()
    html = _cliente(app, "conductor1").get("/distribucion/checklist-diario").get_data(as_text=True)
    assert "Checklist de inspección vehicular diario" in html and v1.placa in html


def test_visto_bueno_de_calidad_dia_anterior_o_mismo_dia(app, s, U, cust):
    from app.models import Route
    from app.services import despacho as dsp
    from app.services.core import set_param
    from .test_v12 import _route
    set_param("vistos_buenos_salida", ["SEGURIDAD", "CHOFER", "CALIDAD", "AUX_DESPACHO", "LIDER_ALMACEN"])
    assert dsp.required_exit_approvals() == ["SEGURIDAD", "CHOFER", "CALIDAD", "AUX_DESPACHO", "LIDER_ALMACEN"]
    r, _o = _route(s, U, cust)
    r.fecha = date.today() + timedelta(days=3)
    s.commit()
    with pytest.raises(BusinessError, match="día anterior"):
        dsp.give_exit_ok(r, U("asist.calidad"))
    r.fecha = date.today() + timedelta(days=1)
    s.commit()
    assert dsp.roles_vb_de(r, U("asist.calidad")) == ["CALIDAD"]
    dsp.give_exit_ok(r, U("asist.calidad"), "Producto conforme")
    s.commit()
    assert "CALIDAD" in s.get(Route, r.id).vistos_buenos
    assert "CALIDAD" in dsp.missing_exit_approvals(Route(vistos_buenos={}))
    from app import catalogs as C
    assert dict((k, v) for k, v, *_ in C.PARAMS)["vistos_buenos_salida"][2] == "CALIDAD"  # valor de la empresa
