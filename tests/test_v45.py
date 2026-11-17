"""V45 (16-nov-2026): recetas (listas de materiales) y liquidaciones desde SAP solas, plan de producción desde Excel y
liquidaciones por línea desde el Excel de Producción. Solo datos ficticios."""
import io
from datetime import date, timedelta

import pytest

from .test_v26 import _cliente


class _SLBom:
    cfg = {"user": "integracion"}

    def get_all(self, path, params=None):
        assert path == "ProductTrees"
        return [{"TreeCode": "PT-901", "TreeType": "iProductionTree", "Quantity": 1, "Warehouse": "ALM-001",
                 "ProductTreeLines": [{"ItemCode": "MP-901", "Quantity": 5.2, "Warehouse": "ALM-002",
                                       "IssueMethod": "im_Manual"},
                                      {"ItemCode": "EN-901", "Quantity": 1, "Warehouse": "ALM-002",
                                       "IssueMethod": "im_Backflush"}]}]

    def login(self):
        pass

    def logout(self):
        pass


def test_recetas_desde_sap(app, s, U, tmp_path):
    from app.models import BOMLine, UploadBatch
    from app.services import sap_sl
    filas = sap_sl.rows_bom(_SLBom())
    assert [f["Articulo Componente"] for f in filas] == ["MP-901", "EN-901"] and filas[0]["Tipo BOM"] == "P"
    b = sap_sl.sync("BOM", U("jefe.produccion"), str(tmp_path), sl=_SLBom(), autoconfirmar=True)
    s.commit()
    assert b.estado == "CONFIRMADO", (b.estado, b.errores if hasattr(b, "errores") else "")
    comps = {l.componente: l.cantidad for l in s.query(BOMLine).filter_by(padre="PT-901")}
    assert comps.get("MP-901") == pytest.approx(5.2)
    html = _cliente(app, "jefe.produccion").get("/produccion/bom").get_data(as_text=True)
    assert "Lista de materiales" in html
    assert s.query(UploadBatch).filter(UploadBatch.archivo.like("SAP_SL_BOM_%")).count() == 1


def test_liquidaciones_y_recetas_se_agregan_a_la_sincronizacion(app, s):
    from app.catalogs import PARAMS_AGREGAR
    from app.models import AuditLog
    from app.seed import _apply_param_changes
    from app.services.core import param, set_param
    assert ("sap_sync_tipos", ["LIQUIDACION", "BOM"]) == PARAMS_AGREGAR[0][:2]
    set_param("sap_sync_tipos", ["OV", "STOCK"])
    s.query(AuditLog).filter(AuditLog.entidad_id.like("+sap_%")).delete(synchronize_session=False)
    s.commit()
    _apply_param_changes()
    s.commit()
    assert param("sap_sync_tipos") == ["OV", "STOCK", "LIQUIDACION", "BOM"]
    set_param("sap_sync_tipos", ["OV"])
    s.commit()
    _apply_param_changes()  # una sola vez: si luego se quitan, no se vuelven a agregar
    assert param("sap_sync_tipos") == ["OV"]


def _xlsx(filas):
    from openpyxl import Workbook
    wb = Workbook()
    for r in filas:
        wb.active.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_plan_desde_excel_crea_y_actualiza(app, s, U, tmp_path):
    from app.models import ProductionPlan
    from app.services import plan_excel
    hoy = date.today()
    p = tmp_path / "plan.xlsx"
    p.write_bytes(_xlsx([["PLAN DE PRODUCCIÓN (ficticio)"], [], ["Fecha", "Código", "Descripción", "Cantidad", "Línea"],
                         [hoy, "PT-901", "x", 100, "Cimbria"], [hoy + timedelta(days=1), "PT-902", "y", 50, "R1"],
                         [None, None, None, None, None]]))
    r = plan_excel.importar(U("jefe.produccion"), "DIA", str(p), "plan.xlsx")
    s.commit()
    assert r["creadas"] == 2
    pl = s.query(ProductionPlan).filter_by(product_code="PT-901", fecha=hoy).one()
    assert pl.line_code == "CIMBRIA" and pl.cantidad == 100
    # segunda versión del Excel en forma de matriz (una columna por día): actualiza lo que ya estaba
    p2 = tmp_path / "plan2.xlsx"
    p2.write_bytes(_xlsx([["Código", "Línea", hoy.strftime("%d/%m/%Y"), (hoy + timedelta(days=2)).strftime("%d/%m/%Y")],
                          ["PT-901", "CIMBRIA", 120, 30]]))
    r = plan_excel.importar(U("jefe.produccion"), "DIA", str(p2), "plan2.xlsx")
    s.commit()
    assert r["actualizadas"] == 1 and r["creadas"] == 1 and pl.cantidad == 120
    from app.services.core import BusinessError
    p3 = tmp_path / "malo.xlsx"
    p3.write_bytes(_xlsx([["Fecha", "Código", "Cantidad", "Línea"], [hoy, "PT-901", 5, "LINEA INEXISTENTE"]]))
    with pytest.raises(BusinessError, match="no reconocida"):
        plan_excel.importar(U("jefe.produccion"), "DIA", str(p3))
    c = _cliente(app, "jefe.produccion")
    assert "Actualizar con Excel" in c.get("/produccion/plan").get_data(as_text=True)


def test_liquidaciones_por_linea_desde_excel(app, s, U, tmp_path):
    from app.services import process_liq as pl
    u = U("jefe.produccion")
    liq = pl.create_manual(u, {"variante": "PR", "product_code": "PT-901", "lote": "LQ45A", "linea": "CIMBRIA",
                               "fecha": date.today().isoformat()})
    liq.procesos[0]["filas"][0].update({"sacos": 10, "peso_saco": 50})
    liq.procesos[0]["filas"][1].update({"saldo": 480})
    liq.procesos[0]["horas"] = 6
    liq.procesos[0]["operarios"] = 4
    s.commit()
    data = pl.export_excel(liq, app.static_folder, str(tmp_path))  # el mismo formato que usa Producción
    p = tmp_path / "liquidaciones.xlsx"
    p.write_bytes(data)
    nuevas = pl.importar_excel(u, str(p), nombre="liquidaciones.xlsx")
    s.commit()
    n = nuevas[0]
    assert n.product_code == "PT-901" and n.linea == "CIMBRIA" and n.lote == "LQ45A"
    f0 = n.procesos[0]["filas"][0]
    assert (f0["sacos"], f0["peso_saco"]) == (10, 50) and n.procesos[0]["filas"][1]["saldo"] == 480
    assert n.procesos[0]["horas"] == 6 and n.procesos[0]["operarios"] == 4
    html = _cliente(app, "jefe.produccion").get("/produccion/liquidacion-proceso").get_data(as_text=True)
    assert "Subir el Excel de liquidaciones" in html


def test_plan_con_el_formato_de_produccion_sin_codigo(app, s, U, tmp_path):
    """V47: el Excel PLANEAMIENTO de Producción no trae código: producto por nombre (en selección, el granel), líneas
    por sus nombres y cantidad en «PLANIFICADO MP- KG». Datos ficticios con la misma forma."""
    from datetime import datetime as dt
    from app.models import Product, ProductionPlan
    from app.services import plan_excel
    s.get(Product, "PT-901").descripcion = "LENTEJA DEMO * 500 G - MARCA DEMO"
    s.get(Product, "GR-901").descripcion = "LENTEJA DEMO * GRANEL - PROVEEDOR DEMO"
    s.commit()
    hoy = dt.combine(date.today(), dt.min.time())
    cab = ["FECHA", "SEMANA", "# OP", "LINEA", "PROGRAMADO", "CLIENTE", "PLANIFICADO MP- KG", "PRESENTACION", "U.M",
           "CODIGO", "PRODUCTO", "PRESENTACION / GRANEL", "CANTIDAD / SACOS", "DATOS DE GRANEL"]
    p = tmp_path / "PLANEAMIENTO.xlsx"
    p.write_bytes(_xlsx([[], [], cab,
                         [hoy, 47, 3, "CIMBRIA + IQ", True, None, 40000, 1, "KG", " ", "LENTEJA DEMO", 45.36, 908,
                          "LENTEJA DEMO  * GRANEL - PROVEEDOR DEMO"],
                         [hoy, 47, None, "R1&R2", False, None, 7000, 0.5, "UNIDADES", " ", "LENTEJA DEMO * 500 G - MARCA DEMO",
                          50, 70, "LENTEJA DEMO"],
                         [hoy, 47, None, "R3", False, None, 900, 5, "UNIDADES", " ", "PRODUCTO QUE NO EXISTE * 5 KG", 50, 90,
                          "X"],
                         [None, 52, None, None, False, None, None, None, None, " ", None, None, "#DIV/0!", None]]))
    r = plan_excel.importar(U("jefe.produccion"), "DIA", str(p), "PLANEAMIENTO.xlsx")
    s.commit()
    assert r["creadas"] == 2 and [x["fila"] for x in r["sin_producto"]] == [6]
    gr = s.query(ProductionPlan).filter_by(product_code="GR-901").one()
    pt = s.query(ProductionPlan).filter_by(product_code="PT-901").one()
    assert (gr.line_code, gr.cantidad) == ("CIMBRIA", 40000) and "OP 3" in gr.comentario
    assert (pt.line_code, pt.cantidad) == ("R1", 7000)


def test_plan_desde_el_excel_general_con_varias_pestanas(app, s, U, tmp_path):
    """V50: el Excel CONTROL DE PRODUCCION tiene muchas pestañas; el plan se toma de «PROGRAMACION»."""
    from openpyxl import Workbook
    from app.services import plan_excel
    wb = Workbook()
    wb.active.title = "REQ"
    wb.active.append(["NRO", "COLABORADORES", "LINEA"])
    ws = wb.create_sheet("PROGRAMACION")
    ws.append([])
    ws.append(["FECHA", "SEMANA", "# OP", "LINEA", "PLANIFICADO MP- KG", "U.M", "CODIGO", "PRODUCTO"])
    ws.append([date.today(), 47, 3, "R3", 120, "UNIDADES", "PT-901", "x"])
    p = tmp_path / "general.xlsx"
    wb.save(p)
    r = plan_excel.importar(U("jefe.produccion"), "DIA", str(p))
    assert r["creadas"] == 1
