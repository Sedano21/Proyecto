"""V76 (26-nov-2026): Producción, Calidad y experiencia de uso. Tablero OEE con datos irregulares, asistencia sin filas
de resumen, parte (producto a generar e insumo sugerido, EAN solo PT, correcciones con historial), comportamiento por
grano, tiempos con filtros, plan con granel y rotación, tabla GS1 desde la exportación de GS1, liquidación a SAP (apagada
por defecto), certificado de harinas, referencias por grano, quién generó la alerta y los formatos en la base.
Solo datos ficticios."""
import io
import re
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .test_v64 import _cliente


def _parte(s, linea="R1", code="PT-901", kg=500, estado="EN PROCESO", dias=1, **kw):
    from app.models import ProductionReport
    r = ProductionReport(linea=linea, tipo="ENVASADO", fecha=date.today() - timedelta(days=dias), product_code=code,
                         peso_entrada_kg=kg, estado=estado, hora_inicio="08:00", hora_fin="10:00", operarios=2, **kw)
    s.add(r)
    s.commit()
    return r


def test_tablero_oee_con_datos_irregulares(app, s):
    _parte(s, estado="CERRADO", defectos={"ROTURA": "5", "OTRO": None}, indicadores={"oee": "71.5", "pausas_por_causa": {"X": "12"}})
    _parte(s, linea="R2", estado="CERRADO", indicadores="texto", granel_kg=None)
    html = _cliente(app, "jefe.produccion").get("/produccion/tablero")
    assert html.status_code == 200 and "OEE por línea" in html.get_data(as_text=True)


def test_asistencia_sin_filas_de_resumen(app, s, U):
    from app.models import Worker
    from app.services import attendance as asvc
    for n in ("DM", "VACACIONES", "ASISTENCIA", "TOTAL"):
        s.add(Worker(nombre=n, area="Producción", linea="21", activo=True))
    s.add(Worker(nombre="COLABORADOR DEMO UNO", area="Producción", activo=True))
    s.commit()
    assert not asvc.es_colaborador("VACACIONES") and asvc.es_colaborador("COLABORADOR DEMO UNO")
    with pytest.raises(BusinessError, match="no es un colaborador"):
        asvc.save_worker(U("jefe.produccion"), {"nombre": "TOTAL"})
    html = _cliente(app, "jefe.produccion").get("/produccion/asistencia").get_data(as_text=True)
    assert "COLABORADOR DEMO UNO" in html and ">VACACIONES<" not in html and ">DM<" not in html
    assert s.query(Worker).filter_by(nombre="TOTAL").one().activo is False and "+ Nuevo colaborador" in html


def test_parte_producto_insumo_y_ean_solo_pt(app, s, U):
    from app.services import parte as pt
    info = pt.product_info("PT-901")
    assert info["usa_ean"] and info["insumos"] and info["insumos"][0]["code"] == "MP-901"
    mp = pt.product_info("MP-901")
    assert not mp["usa_ean"] and mp["gtins"] == []
    salida, entrada = pt.productos_parte()
    assert any(p.code == "PT-901" for p in salida) and any(p.code == "GR-901" for p in entrada)
    assert not any(p.code.startswith("EN") for p in entrada)
    html = _cliente(app, "jefe.produccion").get("/produccion/partes").get_data(as_text=True)
    assert "Producto que se va a generar" in html and "Materia prima o granel que ingresa" in html and "data-solo-pt" in html


def test_correccion_del_parte_con_historial(app, s, U):
    from app.models import Worker
    from app.services import parte as pt
    w1, w2 = Worker(nombre="OPERARIO DEMO A", area="Producción", activo=True), Worker(nombre="OPERARIO DEMO B", area="Producción", activo=True)
    s.add_all([w1, w2])
    s.commit()
    r = _parte(s, linea="R1")
    with pytest.raises(BusinessError, match="motivo"):
        pt.corregir(U("jefe.produccion"), r, {"operarios": "3"})
    reg = pt.corregir(U("jefe.produccion"), r, {"operarios": "3", "hora_inicio": "0730", "mp_codigo": "MP-901 · ARVEJA"},
                      "se digitó mal", [str(w1.id), str(w2.id)])
    assert r.operarios == 3 and r.hora_inicio == "07:30" and r.mp_codigo == "MP-901"
    assert {c["nombre"] for c in r.colaboradores} == {"OPERARIO DEMO A", "OPERARIO DEMO B"} and "colaboradores" in reg["cambios"]
    with pytest.raises(BusinessError, match="No hay cambios"):
        pt.corregir(U("jefe.produccion"), r, {"operarios": "3"}, "otra vez")
    s.commit()
    html = _cliente(app, "jefe.produccion").get(f"/produccion/parte/{r.id}").get_data(as_text=True)
    assert "Historial de correcciones" in html and "se digitó mal" in html


def test_comportamiento_por_grano_y_tiempos(app, s):
    for i, (code, kg, rend, desm) in enumerate([("PT-901", 1000, 90, 2), ("PT-901", 900, 88, 3), ("PT-903", 400, 80, 9),
                                                ("PT-903", 300, 78, 10), ("PT-905", 500, 85, 4), ("PT-905", 450, 84, 4)]):
        _parte(s, linea="R1" if i % 2 else "R2", code=code, kg=kg, estado="CERRADO", dias=i + 1, rendimiento_pct=rend,
               desmedro_pct=desm)
    from app.services import analisis_grano as ag
    d = ag.analisis(date.today() - timedelta(days=30), date.today())
    assert d["partes"] == 6 and {x["grano"] for x in d["granos"]} and all(x["kg_hora"] for x in d["granos"])
    cl = _cliente(app, "asist.produccion")
    html = cl.get("/produccion/analisis-granos").get_data(as_text=True)
    assert "Comportamiento por grano" in html and "Grano por línea" in html
    t = cl.get("/produccion/tiempos?linea=&producto=PT-901").get_data(as_text=True)
    assert "Evolución semanal" in t and "PT-901" in t


def test_plan_con_granel_rotacion_y_aviso_a_almacen(app, s, U):
    from app.models import Alert, ProductionPlan
    from app.services import production as psvc
    hoy = date.today()
    psvc.add_plans(U("jefe.produccion"), "SEMANA", [{"fecha": hoy + timedelta(days=7), "product_code": "PT-901", "cantidad": 100,
                                                     "insumo": "MP-901 · ARVEJA VERDE PARTIDA"}])
    s.commit()
    pl = s.query(ProductionPlan).filter_by(product_code="PT-901", periodo="SEMANA").one()
    assert pl.insumo == "MP-901"
    html = _cliente(app, "jefe.produccion").get("/produccion/plan?periodo=DIA").get_data(as_text=True)
    assert "Rotación del producto" in html and "Granel o MP a utilizar" in html
    from app.models import AlertType
    assert {"JEFE_LOGISTICA", "JEFE_OPERACIONES"} <= set(s.get(AlertType, "PLAN_MATERIALES_ALMACEN").roles)


def test_gs1_desde_exportacion_de_gs1(app, s, U):
    from openpyxl import Workbook
    from app.models import Product, ProductGTIN
    from app.services import parte as pt
    s.add(Product(code="PT-976", descripcion="FRIJOL CANARIO MARCA DEMO BOLSA * 450 G", tipo="PT", peso_kg=0.45, marca="MARCA DEMO"))
    s.commit()
    wb = Workbook()
    ws = wb.active
    ws.append(["Estándar", "Código", "Marca", "Descripción", "Envase", "Contenido", "Unidad", "Código interno", "Nombre genérico", "Variedad"])
    ws.append(["GTIN13", "7700000000017", "MARCA DEMO", "FRIJOL MARCA DEMO CANARIO X 450 GR", "BOLSA", "450.00", "GRAMOS", None, "FRIJOL", "CANARIO"])
    ws.append(["GTIN13", "7700000000024", "OTRA MARCA", "PRODUCTO SIN PAR", "BOLSA", "1.00", "KILO", None, "X", None])
    ws.append(["GTIN14", "17700000000014", "MARCA DEMO", "CAJA", "CAJA", "450.00", "GRAMOS", "MP-901", "FRIJOL", None])
    path = "/dev/shm/gs1_demo.xlsx"
    wb.save(path)
    with pytest.raises(BusinessError):
        pt.import_gtins(U("vendedor1"), path)
    n, errores, sin = pt.import_gtins(U("jefe.produccion"), path)
    assert n == 2 and len(errores) == 1 and "no es un producto terminado" in errores[0] and len(sin) == 1
    assert s.get(ProductGTIN, "7700000000017").product_code == "PT-976"
    pt.asignar_gtin(U("jefe.produccion"), "7700000000024", "PT-901")
    assert s.get(ProductGTIN, "7700000000024").product_code == "PT-901"


def test_liquidacion_a_sap_apagada_y_cuerpo(app, s, U):
    from app.models import Liquidation
    from app.services import sap_liquidacion as sliq
    liq = Liquidation(numero_documento="5001", product_code="PT-901", cantidad_completada=10, lote="L-DEMO", fecha=date.today(),
                      fecha_fab=date.today(), fecha_venc=date.today() + timedelta(days=300))
    s.add(liq)
    s.commit()

    class SL:
        cfg = {"company": "SBO_DEMO"}

        def get_all(self, *a, **k):
            return [{"AbsoluteEntry": 77, "DocumentNumber": 5001, "ItemNo": "PT-901", "ProductionOrderStatus": "boposReleased"}]

        def _req(self, *a, **k):
            return {"DocNum": 9001, "DocEntry": 1}
    with pytest.raises(BusinessError, match="desactivado"):
        sliq.enviar(U("jefe.produccion"), liq, SL())
    assert "desactivado" in liq.sap["error"]
    body = sliq.payload(liq, 77, "ALM-001")
    ln = body["DocumentLines"][0]
    assert ln["BaseType"] == 202 and ln["BaseEntry"] == 77 and ln["BatchNumbers"][0]["BatchNumber"] == "L-DEMO"
    from app.services.core import set_param
    set_param("sap_escritura_liquidacion", True)
    set_param("sap_escritura_empresas", ["SBO_DEMO"])
    liq.sap = {}
    assert sliq.enviar(U("jefe.produccion"), liq, SL()) == 9001 and liq.sap["docnum"] == 9001


def test_certificado_de_harina_y_referencias_por_grano(app, s, U):
    from app.models import Product, StockLot
    from app.services import quality as q
    assert "Maíz mote" in q._referencia_ntp("MAIZ MOTE PELADO") and "Pallar" in q._referencia_ntp("PALLAR BEBE")
    s.add(Product(code="PT-977", descripcion="HARINA DE SOYA * 5 KG - COSECHA ANDINA", tipo="PT", peso_kg=5, marca="COSECHA ANDINA"))
    s.flush()
    lot = StockLot(product_code="PT-977", warehouse_code=s.query(StockLot).first().warehouse_code, lote="H-DEMO-1", cantidad=10,
                   estado="DISPONIBLE")
    s.add(lot)
    s.commit()
    _parte(s, code="PT-977", lote_pt="H-DEMO-1", controles_calidad=[{"parametro": "Humedad (%) – PCC1", "valor": "8.7",
                                                                      "conforme": True, "user": "asistente", "ts": "2026-11-20T10:00"}])
    assert q.certificate_type_for(lot) == "HA"
    c = q.generate_certificate(lot, U("jefe.calidad"))
    assert "-CA" in c.numero and c.datos["humedad"]["resultado"] == "8.7%" and c.datos["humedad"]["especificacion"] == "MÁX. 15 %"
    assert c.datos["referencia_organoleptico"].startswith("FICHA TECNICA CORPORACIÓN PRODUCTIVA.")
    assert c.datos["organoleptico"][0]["especificacion"] == "Homogéneo, sin grumos."
    s.commit()
    html = _cliente(app, "jefe.calidad").get(f"/calidad/certificados/{c.id}").get_data(as_text=True)
    assert "CARACTERISTICAS ORGANOLEPTICAS" in html and "FICHA TECNICA" in html


def test_quien_genero_la_alerta_y_formatos_en_la_base(app, s, U):
    from app.services import alerts
    a = alerts.emit("CARGA_INCONGRUENCIA", "Alerta demo V76", "detalle", "Route", 1, creado_por=U("aux.despacho"))
    s.commit()
    cl = _cliente(app, "gerente.general")
    det = cl.get(f"/alertas/{a.id}").get_data(as_text=True)
    assert "Auxiliar de Despacho" in det
    html = _cliente(app, "jefe.calidad").get("/calidad/formatos").get_data(as_text=True)
    assert "Registros en la base de datos" in html


def test_asistente_produccion_mueve_y_ve_eficiencia(app):
    from app.catalogs import ROLE_PERMISSIONS
    assert any(p[0] == "movimiento.solicitar" for p in ROLE_PERMISSIONS["ASIST_PRODUCCION"])
    cl = _cliente(app, "asist.produccion")
    assert cl.get("/produccion/productividad").status_code == 200
    menu = cl.get("/produccion/partes").get_data(as_text=True)
    assert "Eficiencia por persona" in menu and "Movimientos punto a punto" in menu
