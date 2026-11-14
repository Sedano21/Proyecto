"""V42 (14-nov-2026): guía SUNAT con tipo de documento, corrección de la decisión de inventario, OTIF con OV vs guías de
SAP, producción del mes (SAP y módulo), planeamiento por línea con alerta de capacidad, vencimientos a 3 y 6 meses con
varios almacenes y vistas agrupadas por cliente. Solo datos ficticios."""
from datetime import date, timedelta

import pytest

from .conftest import alerts_of
from .test_v26 import _cliente


def test_guia_lleva_el_tipo_de_documento_de_finanzas(app, s, U, new_order, monkeypatch):
    from app.models import SunatGuide
    from app.services import guias_sunat as gs
    from app.services import sap_sl
    o = new_order([("PT-901", 4)])
    g = SunatGuide(serie="EG07", numero="448", lineas=[{"codigo": "PT-901", "descripcion": "x", "lote": "264005DV",
                                                        "cantidad": 4}], sap_ov="1636328", order_id=o.id, archivo="",
                   estado="REGISTRADA", inventario={}, sap={})
    s.add(g)
    s.commit()

    class SL:
        cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}
        body = None

        def get_all(self, path, params=None):
            if path == "DeliveryNotes":
                return [{"DocEntry": 5, "FolioPrefixString": "EG07", "Indicator": "09", "U_EXX_TIPOOPER": "01"}]
            return [{"DocEntry": 77, "DocNum": 1636328, "CardCode": "C1", "DocumentLines": [
                {"LineNum": 0, "ItemCode": "PT-901", "RemainingOpenQuantity": 4}]}]

        def _req(self, method, path, body=None, headers=None):
            SL.body = body
            return {"DocEntry": 901, "DocNum": 3002}
    monkeypatch.setattr(sap_sl, "write_enabled", lambda cfg=None: None)
    monkeypatch.setattr(gs, "_req", lambda u: None)
    gs.enviar_sap(U("jefe.operaciones"), g, sl=SL())
    assert SL.body["Indicator"] == "09" and SL.body["U_EXX_TIPOOPER"] == "01"


def test_corregir_la_decision_de_inventario(app, s, U, new_order):
    from app.models import StockLot, SunatGuide
    from app.services import guias_sunat as gs
    from app.services.core import BusinessError
    alm = s.query(StockLot).first().warehouse_code
    lot = StockLot(product_code="PT-901", warehouse_code=alm, lote="420001ZZ", cantidad=10, estado="DISPONIBLE")
    s.add(lot)
    g = SunatGuide(serie="EG07", numero="990", lineas=[{"codigo": "PT-901", "descripcion": "x", "lote": "420001ZZ",
                                                        "cantidad": 4}], archivo="", estado="REGISTRADA", inventario={}, sap={})
    s.add(g)
    s.commit()
    gs.decidir_inventario(U("jefe.operaciones"), g, "DESCONTAR")
    s.commit()
    assert lot.cantidad == 6
    with pytest.raises(BusinessError, match="motivo"):
        gs.corregir_inventario(U("jefe.operaciones"), g, "")
    with pytest.raises(BusinessError):
        gs.corregir_inventario(U("vendedor1"), g, "x")
    gs.corregir_inventario(U("jefe.operaciones"), g, "Se marcó por error (ficticio)")
    s.commit()
    assert lot.cantidad == 10 and not g.inventario.get("decision") and g.inventario["historial"][0]["decision"] == "DESCONTADO"
    gs.decidir_inventario(U("jefe.operaciones"), g, "YA_DESCONTADO")
    s.commit()
    assert g.inventario["decision"] == "YA_DESCONTADO" and g.inventario["historial"]
    html = _cliente(app, "jefe.operaciones").get("/operacion/guias-sunat").get_data(as_text=True)
    assert "Corregir la decisión de inventario" in html and "Se marcó por error" in html


def _historial_sap(s, hoy):
    from app.models import SapMovement, SapOrderLine
    from app.services.core import set_param
    ayer = hoy - timedelta(days=1)
    lin = [("8001", "PT-901", 10, ayer), ("8002", "PT-902", 10, ayer), ("8003", "PT-901", 5, ayer), ("8004", "PT-901", 5, hoy + timedelta(days=3))]
    for doc, p, q, f in lin:
        s.add(SapOrderLine(docnum=doc, clase="VENTA", serie="OV", fecha=f - timedelta(days=5), fecha_entrega=f,
                           cliente="Cliente Demo SAP", estado="ABIERTA", product_code=p, descripcion="x", cantidad=q,
                           entregado=0, linea_cerrada=False))
    s.add(SapOrderLine(docnum="8009", clase="SERVICIO", serie="OS", fecha=ayer, fecha_entrega=ayer, cliente="Cliente Demo SAP",
                       estado="ABIERTA", product_code="SERVICIO", descripcion="x", cantidad=1, entregado=0, linea_cerrada=False))
    movs = [("8001", "PT-901", 10, ayer - timedelta(days=1)),  # a tiempo y completa
            ("8002", "PT-902", 6, ayer),  # a tiempo, incompleta
            ("8003", "PT-901", 5, hoy)]  # completa pero tarde
    for i, (ov, p, q, f) in enumerate(movs):
        s.add(SapMovement(clave=f"GUIA:{900 + i}:0", tipo="GUIA", docentry=900 + i, documento=f"T001-{i}", fecha=f,
                          ov_numero=ov, product_code=p, cantidad=q))
    s.commit()
    set_param("sap_ordenes_ultimo", {"historial": True, "ts": "2026-11-14T10:00", "version": 3, "desde": "2026-07-01"})
    s.commit()


def test_otif_con_ov_vs_guias_de_sap(app, s, U):
    from app.services import seguimiento
    hoy = date.today()
    _historial_sap(s, hoy)
    d = seguimiento.service_month(desde=hoy - timedelta(days=5), hasta=hoy + timedelta(days=5))
    assert d["fuente"] == "SAP" and d["universo"] == 4  # la orden de servicio no entra
    assert d["otif_n"] == (1, 4) and d["on_time_n"] == (2, 4) and d["in_full_n"] == (2, 4)
    assert d["fill_rate"] == pytest.approx(round(100 * 21 / 25, 1))
    assert d["otif_fecha_n"] == (1, 3)  # la 8004 aún está en plazo
    html = _cliente(app, "jefe.logistica").get(f"/seguimiento/servicio?mes={hoy}").get_data(as_text=True)
    assert "Calculado con SAP" in html and "8002" in html and "T001-1" in html
    m = seguimiento.service_month(desde=hoy - timedelta(days=5), hasta=hoy + timedelta(days=5), fuente="MODULO")
    assert m["fuente"] == "MODULO"
    from app.services.kpis import compute
    k = compute(hoy - timedelta(days=5), hoy + timedelta(days=5))
    assert k["otif_fuente"] == "SAP" and k["otif_salida"][1:] == (1, 4)


def test_produccion_del_mes_sap_y_modulo(app, s, U):
    from app.models import ProductionReport, SapMovement
    from app.services import reports, sap_v31
    hoy = date.today()

    class SL:
        def get_all(self, path, params=None):
            assert path == "InventoryGenEntries"
            return [{"DocEntry": 70, "DocNum": 7, "DocDate": hoy.isoformat(), "DocumentLines": [
                {"LineNum": 0, "BaseType": 202, "BaseEntry": 55, "ItemCode": "PT-901", "Quantity": 100},
                {"LineNum": 1, "ItemCode": "PT-902", "Quantity": 3}]}]  # sin orden de fabricación: no es producción
    filas = sap_v31.rows_producciones(SL(), hoy - timedelta(days=30))
    assert len(filas) == 1 and filas[0]["tipo"] == "PRODUCCION" and filas[0]["of"] == "55"
    sap_v31.guardar_movimientos(filas, False, ("PRODUCCION",))
    s.add(ProductionReport(linea="CIMBRIA", tipo="SELECCION", fecha=hoy, product_code="GR-901", peso_entrada_kg=500,
                           granel_kg=470, estado="CERRADO"))
    s.commit()
    assert s.query(SapMovement).filter_by(tipo="PRODUCCION").count() == 1
    m = reports.produccion_fuentes(hoy.replace(day=1), hoy)
    assert m["sap_unidades"] == 100 and m["sap_docs"] == 1 and m["modulo_kg"] >= 500 and m["hoy_kg"] >= 500
    html = _cliente(app, "jefe.produccion").get("/informes/produccion").get_data(as_text=True)
    assert "Liquidado en SAP" in html and "Hoy en tiempo real" in html


def test_planeamiento_por_linea_y_alerta_de_capacidad(app, s, U):
    from app.services import v42
    hoy = date.today()
    r = v42.check_capacidad_lineas(hoy)
    s.commit()
    al = alerts_of(s, "CAPACIDAD_BAJA")
    assert al and "por debajo del 80" in al[0].titulo and "JEFE_PRODUCCION" in al[0].roles and r.startswith(str(len(al)))
    v42.check_capacidad_lineas(hoy)  # una por línea y semana
    s.commit()
    assert len(alerts_of(s, "CAPACIDAD_BAJA")) == len(al)
    html = _cliente(app, "jefe.produccion").get("/produccion/plan").get_data(as_text=True)
    assert "Programación por línea" in html and 'class="card linea-plan' in html
    assert html.index("Programación por línea") < html.index("Requerimientos consolidados")


def test_por_vencer_y_varios_almacenes(app, s):
    from app.models import StockLot, Warehouse
    from app.services import supply
    hoy = date.today()
    whs = [w.code for w in s.query(Warehouse).limit(2)]
    s.add(StockLot(product_code="PT-905", warehouse_code=whs[0], lote="V42A", cantidad=7, fecha_venc=hoy + timedelta(days=40)))
    s.add(StockLot(product_code="PT-905", warehouse_code=whs[-1], lote="V42B", cantidad=3, fecha_venc=hoy + timedelta(days=150)))
    s.commit()
    d = supply.rotation_ranking(hoy=hoy, top=1000, almacen=whs)
    assert d["almacenes"] == whs
    tres = {x["code"]: x for x in d["por_vencer"]["3"]}
    seis = {x["code"]: x for x in d["por_vencer"]["6"]}
    assert tres["PT-905"]["cantidad"] >= 7 and seis["PT-905"]["cantidad"] >= 3
    solo = supply.rotation_ranking(hoy=hoy, top=1000, almacen=[whs[0]])
    assert all("V42B" not in " ".join(x["lotes"]) for x in solo["por_vencer"]["6"])
    c = _cliente(app, "jefe.logistica")
    html = c.get("/suministro/rotacion?" + "&".join(f"almacen={w}" for w in whs)).get_data(as_text=True)
    assert "Vencen en los próximos 3 meses" in html and 'class="chip"' in html and "multi-sel" in html


def test_vistas_agrupadas_por_cliente_y_dias_no_laborables(app, s, new_order):
    a = new_order([("PT-901", 2)])
    new_order([("PT-902", 2)], ruc="20000000004")
    c = _cliente(app, "coord.ventas")
    html = c.get("/ov/?vista=cliente").get_data(as_text=True)
    assert "Por cliente" in html and a.customer.nombre in html and "próxima" in html
    r = _cliente(app, "coord.almacen").get("/almacen/picking?vista=semana")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "grupos-cliente" in html or "No hay picking programado" in html
    html = _cliente(app, "jefe.operaciones").get("/dias-no-laborables").get_data(as_text=True)
    assert "check-grid" in html and 'data-checkall="area"' in html
