"""V18 (02-nov-2026): observaciones (diseño, almacenes del Jefe de Logística, asistencia, averías, checklist vehicular,
despachos en el inicio, picking, producción, liquidación de proceso y pre-guía). Datos ficticios."""
import io
import json
from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from app.services.core import BusinessError, has_perm, param

from .conftest import alerts_of
from .test_web import login


def _get(app, user, path):
    c = app.test_client()
    login(c, user)
    return c.get(path)


# ------------------------------------------------------------------ logística y almacenes
def test_jefe_de_logistica_maneja_todos_los_almacenes(s, U):
    from app.models import Warehouse
    from app.services.core import check_warehouse_scope
    exc = param("alcance_almacen_excepto")
    assert exc.get("JEFE_LOGISTICA") == [] and exc.get("JEFE_OPERACIONES") == []
    for w in s.query(Warehouse).all():  # ningún almacén da «no asignado a su rol»
        check_warehouse_scope(U("jefe.logistica"), w.code)
        check_warehouse_scope(U("jefe.operaciones"), w.code)


# ------------------------------------------------------------------ asistencia
def test_asistencia_puesto_otro_excel_y_linea_del_dia(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import attendance as at
    jp = U("jefe.produccion")
    with pytest.raises(BusinessError, match="Otro"):
        at.save_worker(jp, {"nombre": "Operario Demo", "puesto": "__OTRO__", "puesto_otro": ""})
    w = at.save_worker(jp, {"nombre": "Operario Demo", "puesto": "__OTRO__", "puesto_otro": "Estibador", "linea": "TRUER"})
    assert w.sublinea == "Estibador" and w.nombre == "OPERARIO DEMO"
    assert at.positions(jp)  # lista de puestos del área
    wb = Workbook()
    ws = wb.active
    ws.append(["Nombre", "Documento", "Puesto", "Línea", "Externo"])
    ws.append(["Persona Ficticia Uno", "00000001", "Operario", "CIMBRIA", "no"])
    ws.append(["Operario Demo", "", "Seleccionador", "TRUER", "sí"])
    f = tmp_path / "personal.xlsx"
    wb.save(f)
    nuevos, act = at.import_workers(jp, str(f))
    assert (nuevos, act) == (1, 1), (nuevos, act)
    assert w.sublinea == "Seleccionador" and w.externo
    hoy = date.today()
    at.register_day(jp, hoy, {str(w.id): at.states()[0]}, lineas={str(w.id): "CIMBRIA"})
    s.flush()
    assert at.day(hoy)[w.id].linea == "CIMBRIA"
    at.register_day(jp, hoy, {str(w.id): at.states()[0]}, lineas={str(w.id): "TRUER"})  # su línea habitual
    s.flush()
    assert at.day(hoy)[w.id].linea == ""


# ------------------------------------------------------------------ choferes y checklist
def test_chofer_reporta_averia(s, U):
    from app.models import Vehicle
    from app.services import maintenance as m
    v = s.query(Vehicle).first()
    b = m.report_breakdown(U("conductor1"), v, "Ruido en la caja de cambios", "ALTA")
    assert b.id and b.descripcion.startswith("Ruido")


def test_checklist_con_marcas_en_la_imagen_y_visible_para_jefaturas(app, s, U, cust):
    from app.services import vehicle_checklist as vc
    from .test_v12 import _route, _vals
    with pytest.raises(BusinessError):
        vc.parse_marks(json.dumps([{"x": 10, "y": 20, "nota": ""}]))
    marcas = vc.parse_marks(json.dumps([{"x": 10, "y": 20, "nota": "Abolladura puerta"}]))
    r, _ = _route(s, U, cust)
    c = vc.register(U("coord.distribucion"), r, "SALIDA", _vals(), 1000, "", marcas=marcas)
    assert c.marcas[0]["nota"] == "Abolladura puerta" and "Abolladura" in c.observaciones
    s.commit()
    for u in ("jefe.logistica", "jefe.operaciones", "coord.distribucion"):
        assert has_perm(U(u), "checklist.ver")
        assert _get(app, u, "/distribucion/checklists").status_code == 200


# ------------------------------------------------------------------ inicio: despachos por cliente y fecha
def test_inicio_despachos_por_cliente_y_fecha(app, s, U, new_order):
    from app.services import seguimiento as seg
    o = new_order([("PT-901", 5)])
    s.commit()
    d = seg.dispatch_board(U("jefe.logistica"))
    g = next(x for x in d if o in x["ovs"])
    assert g["fecha"] == o.fecha_compromiso and g["pronostico"][0] in ("RIESGO", "VIGILAR", "A_TIEMPO", "CUMPLIDO")
    otro = U("vendedor2")
    assert all(x.vendedor_id == otro.id for g in seg.dispatch_board(otro) for x in g["ovs"])
    html = _get(app, "jefe.logistica", "/").get_data(as_text=True)
    assert "Despachos por cliente y fecha" in html


# ------------------------------------------------------------------ picking
def test_picking_lista_todos_los_lotes_con_su_condicion(s, U, new_order):
    from app.services import picking as pk
    o = new_order([("PT-901", 50)])
    t = pk.tasks_of(o)[0]
    line = o.lines[0]
    todos = pk.lot_options(t, line, todos=True)
    assert todos and all({"lot", "ok", "motivo", "libre"} <= set(x) for x in todos)
    usables = pk.lot_options(t, line)
    assert {x["lot"].id for x in todos if x["ok"]} == {l.id for l in usables}


def test_formato_de_picking_con_lote_y_fechas_desde_la_reserva(s, U, new_order):
    from app.services import picking as pk
    o = new_order([("PT-901", 50)])
    t = pk.tasks_of(o)[0]
    filas = pk.format_rows([t])
    assert filas and all(f.get("lote") for f in filas)


# ------------------------------------------------------------------ producción
def test_plazo_no_confirmado_exige_fecha_y_alerta_si_es_tarde(s, U, new_order):
    from app.services import production as prod
    o = new_order([("PT-903", 10)], dias=4)
    r = prod.create_request("PT-903", 100, U("coord.almacen"), order=o)
    prod.send_request(r, U("coord.almacen"))
    jp = U("jefe.produccion")
    with pytest.raises(BusinessError, match="fecha"):
        prod.validate_request(r, jp, True, True, True, True, False)
    prod.validate_request(r, jp, True, True, True, True, False, "sin turno libre", fecha_entrega=o.fecha_compromiso)
    s.flush()
    assert r.validacion["fecha_entrega"] == o.fecha_compromiso.isoformat()
    assert alerts_of(s, "PRODUCCION_PLAZO_RIESGO", r.id)


def test_plan_con_varios_productos_y_preprogramacion_con_linea(s, U):
    from app.models import ProductionPlan
    from app.services import production as prod
    jp = U("jefe.produccion")
    hoy = date.today()
    filas = [{"fecha": hoy, "product_code": "PT-903", "cantidad": 100, "line_code": None, "comentario": ""},
             {"fecha": hoy + timedelta(days=1), "product_code": "PT-905", "cantidad": 50, "line_code": None, "comentario": ""},
             {"fecha": None, "product_code": "", "cantidad": None}]
    creadas = prod.add_plans(jp, "SEMANA", filas)
    assert len(creadas) == 2
    with pytest.raises(BusinessError, match="al menos una fila"):
        prod.add_plans(jp, "SEMANA", [{"product_code": "", "cantidad": None}])
    assert s.query(ProductionPlan).count() >= 2


def test_iniciar_desde_planeamiento_aparece_en_el_monitoreo(s, U):
    from app.models import ProductionLine, ProductionReport
    from app.services import production as prod
    r = prod.create_request("PT-903", 100, U("coord.almacen"))
    prod.send_request(r, U("coord.almacen"))
    jp = U("jefe.produccion")
    prod.validate_request(r, jp, True, True, True, True, True)
    linea = s.query(ProductionLine).first()
    prod.schedule(r, jp, linea.code, date.today())
    prod.start(r, jp)
    s.flush()
    rep = s.query(ProductionReport).filter_by(of=f"PS-{r.id}").one()
    assert rep.estado == "EN PROCESO" and rep.linea == linea.code


def test_control_de_produccion_exportable(app, s):
    for u in ("jefe.produccion", "asist.produccion", "jefe.operaciones"):
        x = _get(app, u, "/produccion/control?salida=xlsx")
        assert x.status_code == 200 and x.data[:2] == b"PK", u
    p = _get(app, "jefe.produccion", "/produccion/control?salida=pdf")
    assert p.status_code == 200 and p.data[:4] == b"%PDF"


# ------------------------------------------------------------------ liquidación de proceso
def test_liquidacion_manual_encabezado_filtros_y_merma(app, s, U):
    from app.services import process_liq as pl
    d = MultiDict({"variante": "PF", "product_code": "pt-905", "lote": "L-FICTICIO-9", "linea": "TRUER",
                   "fecha": date.today().isoformat(), "p_Proveedor": "Proveedor Demo", "p_Procedencia": "Junín",
                   "p_FP": "2026-10-01", "s_Proceso": "Selección"})
    with pytest.raises(BusinessError):
        pl.create_manual(U("asist.calidad"), d)
    liq = pl.create_manual(U("asist.produccion"), d)
    h = pl.header(liq)
    assert liq.product_code == "PT-905" and h["Lote"] == "L-FICTICIO-9" and h["Proveedor"] == "Proveedor Demo"
    assert h["FP"] == "01/10/2026" and h["Proceso"] == "Selección" and liq.report_ids == []
    assert pl.matches(liq, {"Proveedor": "demo"}) and not pl.matches(liq, {"Procedencia": "Lima"})
    # filas: ingreso 1000, procesado 940, desmedro 50 → total procesado 950, sacos 19, diferencia 10
    liq.procesos = [dict(liq.procesos[0], filas=[pl._fila("INGRESO", "GRANEL", None, None, 1000),
                                                 pl._fila("SALIDA", "PROCESADO", None, None, 940),
                                                 pl._fila("SALIDA", "DESMEDRO", None, None, 50)])]
    liq.costos = {"merma_esperada_pct": 4}
    c = pl.calc(liq)["costos"]
    assert c["merma_esperada_kg"] == 40 and c["total_procesado"] == 950 and c["sacos_50"] == 19 and c["diferencia"] == 10
    s.commit()
    html = _get(app, "jefe.produccion", "/produccion/liquidacion-proceso?h_Proveedor=demo").get_data(as_text=True)
    assert "Proveedor Demo" in html and 'list="dl-sku"' in html and 'list="dl-lote"' in html
    assert _get(app, "jefe.produccion", f"/produccion/liquidacion-proceso/{liq.id}/excel").data[:2] == b"PK"


# ------------------------------------------------------------------ pre-guía
def _preguia(s, U, cust):
    from app.services import orders as osvc
    from .test_v12 import _route
    r, o = _route(s, U, cust)
    osvc.finish_preparation(o, U("coord.almacen"))
    s.flush()
    return r, o


def test_preguia_revision_editable_y_emision(s, U, cust):
    from app.services import guides
    r, o = _preguia(s, U, cust)
    ad = U("asist.distribucion")
    guides.start_review(ad, o)
    assert o.preguia["revision_inicio_por"] == ad.nombre
    cant = o.preguia["items"][0]["preparado"]
    f = {"fecha_guia": (date.today() + timedelta(days=1)).isoformat(), "llegada": "Av. Ficticia 123",
         "pres_0": "Saco 25 kg", "cant_0": str(cant)}
    if len(o.preguia["items"][0]["lotes"]) == 1:
        f["lote_0_0"] = str(cant)
    guides.review(ad, o, f)
    assert o.preguia["llegada"] == "Av. Ficticia 123" and o.preguia["items"][0]["presentacion"] == "Saco 25 kg"
    if "lote_0_0" in f:  # la suma de los lotes debe coincidir con la cantidad
        with pytest.raises(BusinessError, match="no coincide"):
            guides.review(ad, o, dict(f, cant_0=str(cant + 1)))
    guides.validate(ad, o, True, "ok")
    from app.services.alerts import CERRADOS
    s.flush()
    assert o.preguia["estado"] == "VALIDADA" and all(a.estado in CERRADOS for a in alerts_of(s, "GUIA_POR_VALIDAR", o.id))
    assert guides.durations(o.preguia)["total"] is not None
    with pytest.raises(BusinessError, match="lápiz"):
        guides.review(ad, o, f)


def test_guia_emitida_solo_cambia_fecha_cantidad_presentacion_con_rastro(s, U, cust):
    from app.services import guides
    r, o = _preguia(s, U, cust)
    cd = U("coord.distribucion")
    guides.validate(cd, o, True, "ok")
    with pytest.raises(BusinessError, match="motivo"):
        guides.edit_emitted(cd, o, "cantidad", "", 0, 3)
    with pytest.raises(BusinessError, match="solo se cambian"):
        guides.edit_emitted(cd, o, "cliente", "x", 0, "y")
    with pytest.raises(BusinessError):
        guides.edit_emitted(U("coord.almacen"), o, "cantidad", "x", 0, 3)
    guides.edit_emitted(cd, o, "cantidad", "Cliente recibe menos", 0, 3)
    guides.edit_emitted(cd, o, "presentacion", "Cambio de empaque", 0, "Caja x 12")
    guides.edit_emitted(cd, o, "fecha", "Sale mañana", valor=date.today() + timedelta(days=1))
    campos = [c["campo"] for c in o.preguia["cambios"]]
    assert campos == ["cantidad", "presentacion", "fecha"] and o.preguia["cambios"][0]["user"] == cd.nombre
    ind = guides.change_rate()
    assert ind["emitidas"] == 1 and ind["con_cambio"] == 1 and ind["tasa"] == 100.0 and ind["por_campo"]["cantidad"] == 1


def test_preguia_desde_la_alerta_y_desde_la_lista(app, s, U, cust):
    r, o = _preguia(s, U, cust)
    s.commit()
    a = alerts_of(s, "GUIA_POR_VALIDAR", o.id)[0]
    html = _get(app, "coord.distribucion", f"/alertas/{a.id}").get_data(as_text=True)
    assert f"/distribucion/preguia/{o.id}" in html
    c = app.test_client()
    login(c, "coord.distribucion")
    page = c.get(f"/distribucion/preguia/{o.id}").get_data(as_text=True)
    assert "Aprobar y emitir la guía" in page and "PRE-GUÍA DE REMISIÓN" in page
    csrf = page.split('name="_csrf" value="')[1].split('"')[0]
    x = c.post(f"/distribucion/preguia/{o.id}", data={"_csrf": csrf, "accion": "aprobar", "observacion": "ok"},
               follow_redirects=True).get_data(as_text=True)
    assert "guía emitida" in x and "GUÍA ELECTRÓNICA" in x
    s.expire_all()
    from app.services.alerts import CERRADOS
    assert a.estado in CERRADOS  # aprobada en la pre-guía, la alerta se cierra en el mismo momento
    assert "OV " + o.numero not in c.get("/distribucion/preguias").get_data(as_text=True).split("Guías validadas")[0]
    assert _get(app, "jefe.logistica", "/distribucion/preguias").get_data(as_text=True).count("Tasa de cambio") == 1
