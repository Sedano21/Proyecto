"""V21 (05-nov-2026): lotes con puntos asignados por el sistema, revisión de lotes para el inventario, autorización de
cargas con aviso, liquidaciones y entregas desde SAP, verificación previa de OV. Datos ficticios."""
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


def _lote(s, lote, fp=None, fv=None, cant=5, pc="PT-901"):
    from app.models import StockLot
    s.add(StockLot(product_code=pc, warehouse_code="ALM-001", lote=lote, cantidad=cant, estado="DISPONIBLE",
                   fecha_fab=fp, fecha_venc=fv))


# ------------------------------------------------------------------ lotes: el sistema pone los puntos
def test_asignar_lote_reutiliza_o_crea_la_siguiente_variante(s):
    from app.services import lotes
    d1, d2, d3 = date(2026, 2, 10), date(2026, 3, 3), date(2026, 4, 1)
    assert lotes.asignar("PT-901", "888001QA", d1) == ("888001QA", True, "Primera producción de este lote.")
    _lote(s, "888001QA", d1, d1 + timedelta(days=365))
    _lote(s, "888001QA.", d2, d2 + timedelta(days=365))
    s.commit()
    cod, nueva, nota = lotes.asignar("PT-901", "888001QA", d2)  # misma fecha que la 2.ª producción: la misma variante
    assert cod == "888001QA." and not nueva and "ya registrados" in nota
    cod, nueva, nota = lotes.asignar("PT-901", "888001QA...", d3)  # aunque escriban puntos, se toma el número base
    assert cod == "888001QA.." and nueva and "3.ª producción" in nota
    assert lotes.asignar("PT-902", "888001QA", d3)[0] == "888001QA"  # otro producto: independiente


def test_parte_asigna_el_lote_para_sap(s, U):
    from app.services import parte
    hoy = date.today()
    _lote(s, "777100PZ", hoy - timedelta(days=40), hoy + timedelta(days=300), pc="PT-905")
    s.commit()
    r = parte.start(U("asist.produccion"), {"linea": "R1", "product_code": "PT-905", "peso_entrada_kg": 100,
                                            "lote_pt": "777100PZ"})
    s.commit()
    assert r.lote_pt == "777100PZ." and "2.ª producción" in r.lote_pt_nota
    # un segundo parte del mismo día y lote usa la misma variante (no inventa otro punto)
    r2 = parte.start(U("asist.produccion"), {"linea": "R1", "product_code": "PT-905", "peso_entrada_kg": 50,
                                             "lote_pt": "777100PZ"})
    assert r2.lote_pt == "777100PZ."


def test_revision_de_lotes_y_excel(app, s):
    from app.services import lotes
    d = date(2026, 1, 5)
    _lote(s, "201025IN,")
    _lote(s, "333001AB", d, d + timedelta(days=365))
    _lote(s, "333001AB.", d, d + timedelta(days=365))
    _lote(s, "333001AB..")
    _lote(s, "31#00 X")
    s.commit()
    tipos = {a["tipo"]: a for a in lotes.anomalias(["PT-901"])}
    assert "«201025IN.»" in tipos["Coma en lugar de punto"]["detalle"]
    assert "333001AB, 333001AB." == tipos["Variantes con las mismas fechas"]["lote"]
    assert tipos["Variante sin fechas"]["lote"] == "333001AB.."
    assert tipos["Caracteres no válidos"]["lote"] == "31#00 X"
    c = _cliente(app, "coord.almacen")
    html = c.get("/almacen/lotes?q=333001AB").get_data(as_text=True)
    assert "Coma en lugar de punto" in html and "333001AB.." in html
    x = c.get("/almacen/lotes?salida=xlsx")
    assert x.status_code == 200 and x.data[:2] == b"PK" and "lotes_a_corregir_" in x.headers["Content-Disposition"]
    assert "Lotes y variantes" in c.get("/").get_data(as_text=True)


# ------------------------------------------------------------------ autorización de cargas
def test_carga_que_el_perfil_no_puede_autorizar_avisa_a_quien_si(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import uploads
    roles = uploads.autorizadores("STOCK")
    assert "SISTEMAS" not in roles and "COORD_ALMACEN" in roles
    wb = Workbook()
    ws = wb.active
    ws.title = "STOCK_LOTE"
    ws.append(["Número de artículo", "Descripción del artículo", "Lote", "Almacén", "Cantidad"])
    ws.append(["PT-901", "PRODUCTO DEMO", "444001AA", "ALM-001", 5])
    f = tmp_path / "stock.xlsx"
    wb.save(f)
    b = uploads.create_batch(U("sistemas"), "STOCK", str(f), "stock.xlsx")
    s.commit()
    a = alerts_of(s, "CARGA_POR_AUTORIZAR", b.id)
    assert len(a) == 1 and f"Carga #{b.id}" in a[0].titulo
    with pytest.raises(BusinessError, match="no autorizarla.*Coordinación|no autorizarla.*Ya se les avisó"):
        uploads.confirm(b, U("sistemas"))
    b2 = uploads.create_batch(U("coord.almacen"), "STOCK", str(f), "stock.xlsx")  # quien autoriza: sin alerta
    s.commit()
    assert not alerts_of(s, "CARGA_POR_AUTORIZAR", b2.id)


# ------------------------------------------------------------------ SAP: liquidaciones, entregas y verificación de OV
class _SLLectura:
    cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}

    def __init__(self):
        self.filtros = []

    def get_all(self, path, params=None):
        self.filtros.append((path, (params or {}).get("$filter")))
        if path == "InventoryGenEntries":
            return [{"DocEntry": 1, "DocNum": 7001, "DocDate": "2026-11-02T00:00:00Z", "Comments": "",
                     "DocumentLines": [
                         {"BaseType": 202, "BaseEntry": 55, "ItemCode": "PT-901", "Quantity": 30, "WarehouseCode": "ALM-001",
                          "BatchNumbers": [{"BatchNumber": "555001AA", "Quantity": 20}, {"BatchNumber": "555001AA.", "Quantity": 10}]},
                         {"BaseType": -1, "ItemCode": "PT-902", "Quantity": 5}]}]
        return []

    def _req(self, method, path, body=None, headers=None):
        if path.startswith("ProductionOrders(55)"):
            return {"DocumentNumber": 9055, "PlannedQuantity": 32, "ProductionOrderStatus": "boposReleased", "InventoryUOM": "UND"}
        return {}


def test_liquidaciones_desde_sap_sin_consulta(s):
    from app.services import sap_sl
    sl = _SLLectura()
    filas = sap_sl.fetch("LIQUIDACION", sl)
    assert [f["Lote"] for f in filas] == ["555001AA", "555001AA."]  # solo entradas por producción, una fila por lote
    assert filas[0]["Número de documento"] == 9055 and filas[0]["Estado"] == "Liberado" and filas[0]["Entrada SAP"] == 7001
    desde = (date.today() - timedelta(days=30)).isoformat()
    assert ("InventoryGenEntries", f"DocDate ge '{desde}'") in sl.filtros


def test_entregas_de_los_ultimos_30_dias(s):
    from app.services import sap_sl
    sl = _SLLectura()
    sap_sl.rows_despachos(sl)
    desde = (date.today() - timedelta(days=30)).isoformat()
    assert ("DeliveryNotes", f"DocDate ge '{desde}'") in sl.filtros
    # V26: además se leen las facturas del mismo periodo (para la factura de cada guía)
    assert any(f[0] == "Invoices" and f[1].startswith(f"DocDate ge '{desde}'") for f in sl.filtros)


class _SLVerif:
    cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}

    def __init__(self, bp=None, items=None):
        self.bp, self.items = bp, items or {}

    def _req(self, method, path, body=None, headers=None):
        assert method == "GET"  # la verificación no escribe nada en SAP
        if path.startswith("BusinessPartners"):
            if self.bp is None:
                raise BusinessError("No existe")
            return self.bp
        code = path.split("'")[1]
        if code not in self.items:
            raise BusinessError("No existe")
        return self.items[code]


def test_verificacion_previa_de_ov(s, U, new_order):
    from app.services import sap_sl
    from app.services.core import set_param
    o = new_order([("PT-901", 5)])
    o.customer.codigo_sap = "C20999999991"
    set_param("sap_escritura_ov", False, U("sistemas"))
    s.commit()
    probs, _ = sap_sl.preflight_order(o, _SLVerif())
    assert any("desactivada" in p for p in probs)
    set_param("sap_escritura_ov", True, U("sistemas"))
    set_param("sap_escritura_empresas", ["ZZZ_CORPRODUC_TEST260826"], U("sistemas"))
    s.commit()
    probs, _ = sap_sl.preflight_order(o, _SLVerif(bp=None))
    assert any("no existe en esta base" in p for p in probs)
    ok = _SLVerif(bp={"CardType": "cCustomer", "Valid": "tYES", "Frozen": "tNO"},
                  items={"PT-901": {"SalesItem": "tYES", "Valid": "tYES", "Frozen": "tNO"}})
    probs, avisos = sap_sl.preflight_order(o, ok)
    assert probs == []
    inact = _SLVerif(bp={"CardType": "cCustomer", "Valid": "tNO", "Frozen": "tNO"},
                     items={"PT-901": {"SalesItem": "tNO", "Valid": "tYES", "Frozen": "tNO"}})
    probs, _ = sap_sl.preflight_order(o, inact)
    assert any("inactivo o bloqueado" in p for p in probs) and any("no es de venta" in p for p in probs)


def test_boton_verificar_con_sap_en_la_ov(app, s, new_order):
    o = new_order([("PT-901", 5)])
    s.commit()
    assert o.estado not in ("BORRADOR", "BLOQUEADA"), o.estado
    html = _cliente(app, "coord.ventas").get(f"/ov/{o.id}").get_data(as_text=True)
    assert f"/ov/{o.id}/accion/sap_verificar" in html and "Verificar con SAP" in html


def test_aviso_de_texto_conservado_solo_en_formularios_con_campos(app):
    import os
    js = open(os.path.join(app.static_folder, "app.js"), encoding="utf-8").read()
    assert "restaurar" in js


def test_archivos_de_vpn():
    import os
    base = os.path.join(os.path.dirname(__file__), "..", "deploy", "vpn")
    sh = open(os.path.join(base, "instalar_wireguard_servidor.sh"), encoding="utf-8").read()
    assert "51820" in sh and "wg-quick@wg0" in sh and "PrivateKey" in sh
    for f in ("wg-pasarela-linux.conf.ejemplo", "wg-sap-windows.conf.ejemplo"):
        txt = open(os.path.join(base, f), encoding="utf-8").read()
        assert "[Peer]" in txt and "PrivateKey = " in txt and "50000" in txt


# ------------------------------------------------------------------ V21b: comas = puntos, artículos de SAP en la OV y catálogo por canal
def test_la_coma_es_el_punto_mal_digitado(s):
    from app.services import lotes
    assert lotes.normal("201025IN,") == "201025IN." and lotes.normal("201025IN.,") == "201025IN.."
    assert lotes.misma("201025IN,", "201025IN.") and not lotes.misma("201025IN,", "201025IN")
    assert set(lotes.escrituras("201025IN..")) == {"201025IN..", "201025IN.,", "201025IN,.", "201025IN,,"}
    d = date(2026, 3, 1)
    _lote(s, "666001CC", d, d + timedelta(days=365))
    _lote(s, "666001CC,", d + timedelta(days=30), d + timedelta(days=395))  # 2.ª producción escrita con coma
    _lote(s, "666001CC.", d + timedelta(days=30), d + timedelta(days=395))  # y la misma con punto
    s.commit()
    # la coma ocupa la variante 1: la siguiente producción es la 3.ª
    assert lotes.asignar("PT-901", "666001CC", d + timedelta(days=60))[0] == "666001CC.."
    tipos = {a["tipo"]: a for a in lotes.anomalias(["PT-901"])}
    assert "666001CC," in tipos["Mismo lote con coma y con punto"]["lote"]
    assert "666001CC." in tipos["Coma en lugar de punto"]["detalle"]


def test_picking_acepta_el_lote_con_punto_si_en_sap_esta_con_coma(s, U, new_order):
    from app.models import StockLot
    from app.services import orders as osvc
    for l in s.query(StockLot).filter_by(product_code="PT-905", lote="L905A").all():
        l.lote = "L905A,"  # así quedó digitado en SAP
    s.commit()
    o = new_order([("PT-905", 10)])
    osvc.validate_picking_plan(o, U("lider.almacen"))
    osvc.register_picking(o, U("lider.almacen"), o.lines[0].id, 1, "L905A.")
    assert o.lines[0].preparado == 1
    with pytest.raises(BusinessError):
        osvc.register_picking(o, U("lider.almacen"), o.lines[0].id, 1, "L905A")  # sin punto es otra producción


def test_articulos_de_sap_sin_tipo_aparecen_en_ov_y_catalogo(app, s):
    from app.models import PriceItem, Product
    s.add(Product(code="AB-926", descripcion="ARROZ DEMO LARGO - 50 Kg", tipo=""))  # así llegan del maestro de SAP
    s.add(Product(code="GR-902", descripcion="GRANEL DEMO", tipo="", um="KILOGRAMO"))
    s.add(Product(code="EN-991", descripcion="ENVASE DEMO", tipo="EN"))  # no se vende
    s.add(PriceItem(lista="GENERAL", product_code="AB-926", canal="CANAL DEMO", precio=88.5))
    s.commit()
    c = _cliente(app, "coord.ventas")
    html = c.get("/ov/nueva").get_data(as_text=True)
    assert "AB-926 · ARROZ DEMO" in html and "GR-902 · GRANEL" in html and "EN-991" not in html
    assert '"AB-926": "UND"' in html and '"GR-902": "KG"' in html  # la unidad se completa al elegir el producto
    cat = c.get("/ov/catalogo?canal=CANAL%20DEMO").get_data(as_text=True)
    assert "AB-926" in cat and "S/ 88.50" in cat and "GR-902" not in cat
    assert "GR-902" in c.get("/ov/catalogo?q=GR-902").get_data(as_text=True)
