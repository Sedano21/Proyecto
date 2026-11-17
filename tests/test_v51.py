"""V51 (17-nov-2026): carga del histórico del Excel CONTROL DE PRODUCCION (libro con muchas pestañas) y planeamiento
semanal/mensual por rango de fechas. Libro ficticio con la misma forma que el de Producción."""
from datetime import date, datetime, time, timedelta

from .test_v26 import _cliente


def _libro(tmp_path):
    from openpyxl import Workbook
    hoy = date.today()
    f1 = datetime.combine(hoy - timedelta(days=3), time())
    wb = Workbook()
    ws = wb.active
    ws.title = "REQ"
    ws.append(["NRO", "COLABORADORES", "LINEA", "L", "M"])
    ws = wb.create_sheet("ASISTENCIA-NOV")
    for _ in range(5):
        ws.append([])
    dias = [datetime.combine(hoy - timedelta(days=k), time()) for k in (4, 3, 2)]
    ws.append(["NRO ", "DNI", "COLABORADORES", "LINEA", "SUBLINEA"] + dias)
    ws.append(["E001", 40000001.0, "COLABORADOR DEMO UNO", "SELECCIÓN", "SELECCIÓN MANUAL", True, False, True])
    ws = wb.create_sheet("IQ+CIMB")
    ws.append(["LINEA CIMBRIA"])
    cab = ["FECHA", "# OP", "HORA INICIO", "HORA FIN", "TURNO", "CLIENTE", "CANT. PLANIFICADA", "CODIGO", "MP", "CALIDAD",
           "LOTE", "F.V.", "PESO KG", "# 1", "SALDO", "GRANEL", "MP", "CAL3", "DESM.", "TOTAL", "% REND. GLOBAL", "OF",
           "ESTADO", "MAQ. 01", "COLAB. 01", "TIEMPO INACTIVO", "REFRIG. U OTROS", "CAUSA", "PARADA DE MAQ.",
           "TOTAL HR EFECTIVAS", "RATIO KG / HR"]
    ws.append(cab)
    ws.append(["ENERO"])
    ws.append([f1, 3, time(7), time(16, 30), "TURNO 1", "CLIENTE DEMO", 9000, " ", "LENTEJA DEMO * GRANEL", "SUPERIOR",
               "L-DEMO-1", "30.12.26", 50, 12, 0, 8000, 8600, 0, 400, 9000, 0.9556, 3116684, "LIQUIDADO", "MAQUINISTA DEMO",
               "AYUDANTE DEMO", 2, 1, "LIMPIEZA", None, 7.5, 1100])
    ws.append([f1.replace(year=2027), 3, time(7), time(9), "TURNO 1"])  # fecha mal digitada
    ws = wb.create_sheet("ENVASADO R1 R2 R3")
    ws.append([])
    ws.append(["FECHA", "LINEA", "# OP", "HORA INICIO", "HORA FIN", "TURNO", "CANTIDAD PLANIFICADA", "CLIENTE", "CODIGO",
               "PRODUCTO X", "PRESENTACION", "LOTE", "F.V.", "TOTAL UNID", "TOTAL MP KG", "% REND.", "OF", "ESTADO",
               "TIEMPO INACTIVO", "REFRIG. U OTROS", "CAUSA", "MAQUINISTA Y OPERARIO", "COLAB 01"])
    ws.append([f1, "RAUMAK 3", 3, time(10, 50), time(15, 20), "TURNO 1", None, "CLIENTE DEMO", "PT-901", "x", 5.0,
               "L-DEMO-2", "02.01.27", 278, 1400, 0.9929, 3116557, "LIQUIDADO", 1, 1, None, "MAQUINISTA DEMO", "AYUDANTE DEMO"])
    ws = wb.create_sheet("SEL. MANUAL")
    ws.append([])
    ws.append(["FECHA", "MES", "TURNO", "CODIGO MP", "CODIGO GR / MP", "DESCRIPCION", "CALIDAD", "LOTE", "PESO KG",
               "SELECCION", "HORA INICIO", "HORA FINAL", "REFRIGERIO", "T. HORAS X COLA.", "TOTAL HORAS", "# 1",
               "SALDO - KG", "TOTAL DESMEDRO", "TOTAL DE SACOS", "TOTAL  MP - KG", "TOTAL DESMEDRO", "OF", "ESTADO"])
    ws.append([f1, "nov", "TURNO 1", " ", " ", "PRODUCTO SIN CODIGO", "SUPERIOR", "L-DEMO-3", 40, "SELECCIONADORA DEMO",
               time(8, 30), time(10), None, 1.5, 12, 2, 5, 0.85, 2, 700, 10, 3116578, "LIQ. EXT."])
    ws = wb.create_sheet("REQ. DE MP")
    for _ in range(3):
        ws.append([])
    ws.append(["ORDEN DE ENTREGA", "FECHA", "MARCA", "DESCRIPCION", "CLIENTE", "CANTIDAD - KG", "STATUS"])
    ws.append([15, f1, "DEMO", "LENTEJA DEMO", "CLIENTE DEMO", 2500, "ATENDIDO"])
    wb.create_sheet("OV").append(["Número interno", "Número de documento"])
    ws = wb.create_sheet("PROGRAMACION")
    ws.append([])
    ws.append(["FECHA", "SEMANA", "# OP", "LINEA", "PLANIFICADO MP- KG", "U.M", "CODIGO", "PRODUCTO"])
    ws.append([f1, 47, 3, "R3", 120, "UNIDADES", "PT-901", "x"])
    ws.append([f1, 47, 3, "R3", 50, "UNIDADES", "XX-999", "NO EXISTE"])
    p = tmp_path / "CONTROL DE PRODUCCION.xlsx"
    wb.save(p)
    return p


def test_carga_del_historico_del_excel_de_control(app, s, U, tmp_path):
    from app.models import Attendance, ProductionHistory, ProductionPlan, ProductionReport, Worker
    from app.services import historico_excel as hx
    p = _libro(tmp_path)
    r = hx.importar(U("jefe.produccion"), str(p), "CONTROL DE PRODUCCION.xlsx")
    s.commit()
    por = {h["hoja"]: h for h in r["hojas"]}
    assert por["PROGRAMACION"]["cargadas"] == 1 and por["PROGRAMACION"]["sin_producto"] == 1
    assert por["IQ+CIMB"]["cargadas"] == 1 and por["IQ+CIMB"]["n_errores"] == 1
    assert por["OV"]["destino"] == "No se carga" and por["REQ"]["destino"] == "No se carga"
    cim = s.query(ProductionReport).filter_by(linea="CIMBRIA", of="3116684").one()
    assert (cim.peso_entrada_kg, cim.mp_kg, cim.desmedro_kg) == (9000, 8600, 400)
    assert cim.parada_min == 60 and cim.motivo_parada == "LIMPIEZA" and cim.rendimiento_pct == 95.56
    assert {p["rol"] for p in cim.colaboradores} == {"maquinista", "colaborador"} and cim.operarios == 2
    env = s.query(ProductionReport).filter_by(of="3116557").one()
    assert env.linea == "R3" and env.product_code == "PT-901" and env.granel_kg == 278 * 5 and env.parada_min is None
    sel = s.query(ProductionReport).filter_by(linea="SEL_MANUAL").one()
    assert sel.mp_kg == 700 - 10 - 5 and sel.estado == "LIQ. EXT. LIQUIDADO" and sel.colaboradores[0]["rol"] == "seleccion"
    assert sel.colaboradores[0]["kg"] == 700 and sel.product_code == ""
    w = s.query(Worker).filter_by(documento="40000001").one()
    est = {a.fecha: a.estado for a in s.query(Attendance).filter_by(worker_id=w.id)}
    assert sorted(est.values()) in (["ASISTENCIA", "ASISTENCIA", "FALTA"], ["ASISTENCIA", "ASISTENCIA"])
    assert s.query(ProductionHistory).filter_by(tipo="REQ_MP").one().cantidad == 2500
    assert s.query(ProductionPlan).filter_by(product_code="PT-901").count() == 1
    # volver a subir el mismo libro no duplica
    r2 = hx.importar(U("jefe.produccion"), str(p), "CONTROL DE PRODUCCION.xlsx")
    s.commit()
    assert s.query(ProductionReport).filter_by(of="3116684").count() == 1 and r2["total"] <= 1
    c = _cliente(app, "jefe.produccion")
    html = c.get("/produccion/historico-excel").get_data(as_text=True)
    assert "Última carga" in html and "IQ+CIMB" in html and "REQ_MP" in html
    assert c.get("/informes/produccion").status_code == 200


def test_semanal_y_mensual_por_rango(app, s, U):
    from app.services.production import add_plan
    hoy = date.today()
    lun = hoy - timedelta(days=hoy.weekday())
    add_plan(U("jefe.produccion"), "DIA", lun + timedelta(days=1), "PT-901", 100, "R3", "")
    add_plan(U("jefe.produccion"), "DIA", lun + timedelta(days=9), "PT-902", 50, "R3", "")
    s.commit()
    c = _cliente(app, "jefe.produccion")
    def seccion(url):
        h = c.get(url).get_data(as_text=True)
        return h.split("Programación por línea")[1].split("Requerimientos consolidados")[0]
    sem = seccion(f"/produccion/plan?periodo=SEMANA&r_desde={lun}&r_hasta={lun + timedelta(days=6)}")
    assert "Esta semana" in sem and "Programado del" in sem and "<b>PT-901</b>" in sem and "<b>PT-902</b>" not in sem
    mes = seccion(f"/produccion/plan?periodo=MES&r_desde={lun}&r_hasta={lun + timedelta(days=13)}")
    assert "Este mes" in mes and "<b>PT-902</b>" in mes and 'name="dia"' not in mes
