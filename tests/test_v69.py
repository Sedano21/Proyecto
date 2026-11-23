"""V69 (23-nov-2026): demanda proyectada (ítems por comprar con código y descripción, sin mano de obra ni CIF en los
faltantes, avance por ejecutivo), por despachar vencido / en plazo, fecha de despacho en Estado de OV, análisis
adjuntos al informe de reposición y plantilla del seguimiento de importaciones. Solo datos ficticios."""
import io
from datetime import date, timedelta

from app.models import SapOrderLine

from .test_v64 import _cliente


def test_items_por_comprar_con_codigo_y_sin_mano_de_obra(app, s, U, new_order):
    from app.services import demanda_v23 as dm
    o = new_order([("PT-901", 500)])
    mes = f"{o.fecha_compromiso:%Y-%m}"
    rq = dm.requerimiento(mes)
    assert all(not x["code"].startswith("RE-") for x in rq["faltantes"])
    for g in rq["por_tipo"]:
        assert g["n_items"] == len(g["lista"]) and all(it["code"] and "descripcion" in it for it in g["lista"])
    html = _cliente(app, "jefe.ventas").get(f"/analisis/demanda?mes={mes}").get_data(as_text=True)
    assert "built-in method" not in html


def _sap(docnum, entrega, cant, entregado, total=1000.0):
    return SapOrderLine(docnum=docnum, clase="VENTA", fecha=entrega - timedelta(days=5), fecha_entrega=entrega,
                        cliente="CLIENTE FICTICIO SAC", estado="ABIERTA", product_code="PT-901", descripcion="PT DEMO",
                        cantidad=cant, entregado=entregado, total=total, igv=total * 0.18)


def test_por_despachar_vencido_y_en_plazo(app, s):
    from app.services import por_despachar as pd
    hoy = date.today()
    s.add_all([_sap("FICT-1", hoy - timedelta(days=3), 10, 4), _sap("FICT-2", hoy + timedelta(days=2), 10, 0),
               _sap("FICT-3", hoy - timedelta(days=1), 10, 10)])
    s.commit()
    d = pd.calcular(hoy)
    assert d["VENCIDO"]["n"] == 1 and d["EN_PLAZO"]["n"] == 1
    assert abs(d["VENCIDO"]["soles"] - 1180 * 0.6) < 0.01 and abs(d["EN_PLAZO"]["soles"] - 1180) < 0.01
    c = _cliente(app, "gerente.general")
    assert "Por despachar (OV abiertas SAP)" in c.get("/gestion/empresa").get_data(as_text=True)
    html = c.get("/gestion/por-despachar?tipo=VENCIDO").get_data(as_text=True)
    assert "FICT-1" in html and "FICT-2" not in html
    assert "FICT-2" in c.get("/gestion/por-despachar?tipo=EN_PLAZO").get_data(as_text=True)


def test_avance_por_ejecutivo_y_cartera_tomada(s, U, new_order):
    from app.services import demanda_ejecutivo as dej
    from app.services.supply import save_forecast
    o = new_order([("PT-901", 40)], vendedor="vendedor2")
    mes = f"{o.fecha_compromiso:%Y-%m}"
    save_forecast(U("jefe.ventas"), mes, "PT-901", 100, ejecutivo_id=U("vendedor2").id)
    s.commit()
    v2 = U("vendedor2")
    e = next(x for x in dej.avance(mes)["ejecutivos"] if x["id"] == v2.id)
    f = next(x for x in e["filas"] if x["code"] == "PT-901")
    assert f["proyectado_kg"] > 0 and f["vendido_kg"] > 0 and f["por_vender_kg"] == round(f["proyectado_kg"] - f["vendido_kg"], 1)
    assert f["pct_vendido"] == round(100 * f["vendido_kg"] / f["proyectado_kg"], 1)
    # el ejecutivo 1 toma la cartera del 2: se le asigna su nombre como vendedor de SAP
    U("vendedor1").vendedores_sap = [v2.nombre]
    s.commit()
    e1 = dej.avance(mes, U("vendedor1").id)["ejecutivos"]
    assert len(e1) == 1 and any(x["code"] == "PT-901" and x["vendido_kg"] >= f["vendido_kg"] for x in e1[0]["filas"])


def test_ejecutivo_en_el_excel_de_proyeccion(s, U, tmp_path):
    from openpyxl import Workbook
    from app.models import DemandForecast
    from app.services.supply import import_forecast
    wb = Workbook()
    ws = wb.active
    ws.append(["mes", "producto", "cantidad", "ejecutivo"])
    ws.append(["2099-01", "PT-901", 10, "vendedor1"])
    ws.append(["2099-01", "PT-901", 20, U("vendedor2").nombre])
    ws.append(["2099-01", "PT-901", 5, "NO EXISTE"])
    p = tmp_path / "proy.xlsx"
    wb.save(p)
    n, err = import_forecast(U("jefe.ventas"), str(p))
    assert n == 2 and len(err) == 1
    fs = s.query(DemandForecast).filter_by(mes="2099-01").all()
    assert {f.ejecutivo_id for f in fs} == {U("vendedor1").id, U("vendedor2").id}


def test_fecha_de_despacho_en_estado_de_ov(app, s, new_order):
    o = new_order([("PT-901", 5)])
    html = _cliente(app, "jefe.ventas").get("/ov/estado").get_data(as_text=True)
    assert "Fecha de despacho" in html and o.numero in html


def test_analisis_adjunto_al_informe_de_reposicion(app, s):
    from app.models import ReplenishmentAnalysis
    c = _cliente(app, "gerente.general")
    r = c.post("/gestion/reposicion", data={"accion": "subir", "titulo": "Ficha ficticia de una familia", "familia": "GRANOS",
                                            "archivos": (io.BytesIO(b"%PDF-1.4 ficticio"), "ficha.pdf")},
               content_type="multipart/form-data")
    assert r.status_code in (302, 303)
    a = s.query(ReplenishmentAnalysis).order_by(ReplenishmentAnalysis.id.desc()).first()
    assert a is not None and a.archivos[0]["nombre"] == "ficha.pdf"
    assert "Ficha ficticia de una familia" in c.get("/gestion/reposicion").get_data(as_text=True)
    c.post("/gestion/reposicion", data={"accion": "subir", "titulo": "x", "archivos": (io.BytesIO(b"x"), "malo.exe")},
           content_type="multipart/form-data")
    assert s.query(ReplenishmentAnalysis).count() == 1


def test_plantilla_de_importaciones_se_puede_cargar(app, s, U, tmp_path):
    from openpyxl import load_workbook
    from app.services import importaciones_v24 as imp
    wb = load_workbook(io.BytesIO(imp.plantilla()))
    ws = wb.active
    ws.append(["GR-901", "CT-FICT-1", "PROVEEDOR FICTICIO", "GRANO DEMO", "PAÍS X", 2, date.today(), 10, None, "PENDIENTE",
               "PENDIENTE", None, "PENDIENTE"])
    p = tmp_path / "imp.xlsx"
    wb.save(p)
    assert imp.import_excel(U("importaciones"), str(p)) == (1, 0)
