"""V31 (13-nov-2026): buscador, paginador, alertas por fecha, historial de SAP desde julio (órdenes abiertas y cerradas,
guías y consumos), botón «Actualizar con SAP», rotación con venta y producción, compras sin PT/MQ/MP, reposición
anticipada y OTIF día a día. Solo datos ficticios."""
from datetime import date, datetime, timedelta

import pytest

from .conftest import alerts_of
from .test_v26 import _cliente


def test_buscador_y_paginador(app, s, new_order):
    import os
    a = new_order([("PT-901", 2)])
    b = new_order([("PT-902", 2)], ruc="20000000004")
    c = _cliente(app, "coord.ventas")
    html = c.get(f"/ov/?buscar={b.customer.nombre.split()[-1]}").get_data(as_text=True)
    assert b.numero in html and a.numero not in html and 'name="buscar"' in html
    assert a.numero in c.get("/ov/?buscar=PT-901").get_data(as_text=True)  # también por producto de la OV
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(raiz, "app/static/v19.js"), encoding="utf-8").read()
    assert "ponerLupas" in js and "setTimeout(function () {\n      if (!listasDe" not in js  # ya no busca al escribir
    plantilla = open(os.path.join(raiz, "app/templates/ov_list.html"), encoding="utf-8").read()
    assert "</table></div>{{ paginacion(rows) }}</div>" in plantilla  # el paginador queda fuera del scroll


def test_alertas_por_fecha(app, s, U):
    from app.services import alerts
    a = alerts.emit("REPOSICION_SUGERIDA", "Alerta ficticia de prueba V31", "x", "", "", dedup_key="V31:A")
    s.commit()
    c = _cliente(app, "coord.almacen")
    hoy = date.today()
    assert "Alerta ficticia de prueba V31" in c.get(f"/alertas?desde={hoy}").get_data(as_text=True)
    assert "Alerta ficticia de prueba V31" not in c.get(f"/alertas?desde={hoy + timedelta(days=1)}").get_data(as_text=True)
    assert "Alerta ficticia de prueba V31" not in c.get("/alertas?buscar=otra+cosa").get_data(as_text=True)
    assert a.id


class _SLHist:
    cfg = {"user": "integracion"}

    def __init__(self):
        self.filtros = []

    def get_all(self, path, params=None):
        self.filtros.append((path, params.get("$filter", "")))
        if path == "Orders" and "DocEntry eq" in params.get("$filter", ""):
            return [{"DocEntry": 70, "DocNum": 7001}, {"DocEntry": 71, "DocNum": 7002}]
        if path == "Orders":
            return [{"DocNum": 7001, "DocDate": "2026-07-10", "DocDueDate": "2026-07-15", "CardName": "Cliente Demo A",
                     "DocumentStatus": "bost_Close", "Cancelled": "tNO",
                     "DocumentLines": [{"ItemCode": "PT-901", "Quantity": 10, "RemainingOpenQuantity": 0}]},
                    {"DocNum": 7002, "DocDate": "2026-08-03", "DocDueDate": "2026-08-05", "CardName": "Cliente Demo B",
                     "DocumentStatus": "bost_Open", "Cancelled": "tNO",
                     "DocumentLines": [{"ItemCode": "PT-902", "Quantity": 8, "RemainingOpenQuantity": 3}]}]
        if path == "DeliveryNotes":
            return [{"DocEntry": 900, "DocNum": 90, "FolioPrefixString": "T001", "FolioNumber": 15, "DocDate": "2026-07-14",
                     "CardName": "Cliente Demo A", "DocumentLines": [{"LineNum": 0, "BaseType": 17, "BaseEntry": 70,
                                                                       "ItemCode": "PT-901", "Quantity": 10}]},
                    {"DocEntry": 901, "DocNum": 91, "FolioPrefixString": "T001", "FolioNumber": 16, "DocDate": "2026-08-04",
                     "CardName": "Cliente Demo B", "DocumentLines": [{"LineNum": 0, "BaseType": 17, "BaseEntry": 71,
                                                                       "ItemCode": "PT-902", "Quantity": 5}]}]
        if path == "InventoryGenExits":
            return [{"DocEntry": 500, "DocNum": 50, "DocDate": date.today().isoformat(),
                     "DocumentLines": [{"LineNum": 0, "BaseType": 202, "BaseEntry": 33, "ItemCode": "GR-901", "Quantity": 400}]}]
        raise AssertionError(path)


def test_historial_sap_desde_julio(app, s, U):
    from app.models import SapMovement
    from app.services import despachos_sap as ds
    from app.services import sap_v31
    sl = _SLHist()
    r = sap_v31.sync_historial(U("sistemas"), sl=sl)
    s.commit()
    assert r["modo"] == "completa" and r["ordenes"] == 2 and r["guias"] == 2 and r["consumos"] == 1
    assert any("2026-07-01" in f for p, f in sl.filtros if p == "Orders")
    assert s.query(SapMovement).filter_by(tipo="CONSUMO").one().product_code == "GR-901"
    todas = ds.conciliar_historial(situacion="TODAS")
    por = {f["ov"]: f for f in todas["filas"]}
    assert por["7001"]["sap"] == "CERRADA" and por["7001"]["estado"] == "COMPLETO" and por["7001"]["guias"][0][0] == "T001-15"
    assert por["7002"]["estado"] == "PARCIAL" and por["7002"]["lineas"][0]["guiado"] == 5
    assert [f["ov"] for f in ds.conciliar_historial(situacion="ABIERTAS")["filas"]] == ["7002"]
    assert [f["ov"] for f in ds.conciliar_historial("2026-07", situacion="TODAS")["filas"]] == ["7001"]
    c = _cliente(app, "jefe.logistica")
    html = c.get("/almacen/cargas/sap/despachos?sit=CERRADAS&mes=2026-07").get_data(as_text=True)
    assert "cerradas vs guías de SAP" in html and "7001" in html and "Mes de la orden" in html
    # la segunda lectura solo pide lo que cambió
    sl2 = _SLHist()
    r2 = sap_v31.sync_historial(U("sistemas"), sl=sl2)
    s.commit()
    assert r2["modo"].startswith("cambios desde") and all("UpdateDate ge" in f for p, f in sl2.filtros
                                                          if p in ("DeliveryNotes", "InventoryGenExits"))
    assert s.query(SapMovement).count() == 3  # no se duplica


def test_actualizar_con_sap(app, s, U, monkeypatch):
    from app.services import sap_sl
    from app.services.core import set_param
    llamadas = []
    monkeypatch.setattr(sap_sl, "sync_extra", lambda tipo, u, sl=None: llamadas.append(tipo) or {})
    monkeypatch.setattr(sap_sl, "sync", lambda tipo, u, d, sl=None, autoconfirmar=None, solo_si_cambia=False: llamadas.append(tipo))
    set_param("sap_sync_tipos", ["OV", "DESPACHOS"])
    res = sap_sl.actualizar_todo(U("coord.ventas"), "/tmp")
    assert llamadas == ["RESERVAS", "OV", "DESPACHOS", "ORDENES", "FACTURAS"]
    assert res["OV"] == "sin cambios"


def test_rotacion_con_produccion_vencidos_y_kg(app, s):
    from app.models import Product, SapMovement, StockLot
    from app.services import supply
    hoy = date.today()
    gr = s.get(Product, "GR-901")
    gr.peso_kg = None
    gr.um = "UNIDAD"
    lot = s.query(StockLot).filter_by(product_code="GR-901").filter(StockLot.cantidad > 0).first()
    assert lot is not None
    d = supply.rotation_ranking(hoy=hoy, top=1000)
    fila = next((f for f in d["por_tiempo"] if f["code"] == "GR-901"), None)
    if fila:
        assert fila["kg"] == pytest.approx(fila["stock"])  # el granel se mide en kg aunque no tenga peso por unidad
    s.add(SapMovement(clave="CONSUMO:1:0", tipo="CONSUMO", docentry=1, fecha=hoy - timedelta(days=3), product_code="GR-901",
                      cantidad=100))
    s.commit()
    assert "GR-901" not in {x["code"] for x in supply.no_rotation(hoy=hoy)["filas"]}  # usar para producir también es salida
    # producto vencido: la recomendación no dice «vence en -N días»
    p = s.get(Product, "PT-906")
    for l in s.query(StockLot).filter_by(product_code="PT-906"):
        l.fecha_venc = hoy - timedelta(days=400)
    s.commit()
    d = supply.rotation_ranking(hoy=hoy, top=1000)
    f = next((x for x in d["por_tiempo"] if x["code"] == "PT-906"), None)
    if f is not None:
        assert f["recomendacion"].startswith("Vencido desde") and "-" not in f["recomendacion"].split(":")[0]
        assert f["vence"] is None and f["cant_vencida"] > 0
    assert p is not None


def test_compras_no_pt_mq_mp_y_reposicion_anticipada(app, s, U, new_order):
    from app.models import ProductionRequest, PurchaseRequest
    from app.services import purchasing
    from app.services.core import BusinessError, param
    for code in ("PT-901", "MP-901"):
        with pytest.raises(BusinessError, match="fabrica la empresa"):
            purchasing.create_request(U("coord.almacen"), code, 10)
    assert param("usar_stock_seguridad") is True
    new_order([("PT-901", 500000)])  # OV grande sin stock suficiente
    creadas = purchasing.run_replenishment(U("coord.almacen"), product_codes=["PT-901", "MP-901", "EN-901", "GR-901"])
    s.commit()
    pr = s.query(ProductionRequest).filter_by(product_code="PT-901", origen="REPOSICION").one()
    assert pr.estado == "BORRADOR" and pr.cantidad > 0 and "antes de quedarse sin stock" in pr.observacion
    assert alerts_of(s, "PRODUCCION_REPOSICION")
    compras = {r.product_code for r in s.query(PurchaseRequest).filter_by(origen="REPOSICION")}
    assert "PT-901" not in compras and "MP-901" not in compras  # lo que se fabrica no se compra
    assert all(not purchasing.es_producido(r.product) for r in creadas)


def test_otif_dia_a_dia(app, s, new_order):
    from app.services import seguimiento
    hoy = date.today()
    ayer = new_order([("PT-901", 2)], dias=-1)
    ok = new_order([("PT-901", 2)], dias=-1)
    futura = new_order([("PT-901", 2)], dias=5)
    ok.salida_ts = datetime.combine(hoy - timedelta(days=2), datetime.min.time())
    for l in ok.lines:
        l.despachado = l.cantidad
    s.commit()
    d = seguimiento.service_month(desde=hoy - timedelta(days=1), hasta=hoy + timedelta(days=6))
    assert d["otif_fecha_n"] == (1, 2) and d["otif_fecha"] == 50.0  # la futura no baja el indicador
    assert d["otif_n"][1] == 3
    dia = next(x for x in d["diario"] if x["fecha"] == hoy - timedelta(days=1))
    assert dia["n"] == 2 and dia["otif"] == 50.0 and dia["otif_acum"] == 50.0
    html = _cliente(app, "jefe.logistica").get("/seguimiento/servicio").get_data(as_text=True)
    assert "OTIF a la fecha" in html and "OTIF día a día" in html
    assert ayer and futura
