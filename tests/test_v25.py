"""V25 (08-nov-2026): importaciones con documentos e informe de Calidad, fumigación de varios productos, necesidad semanal
de ingresos, stock sin rotación en el inicio y chat interno. Solo datos ficticios."""
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


def _imp(U, s):
    from app.services import importaciones_v24 as imp
    f = imp.save(U("importaciones"), {"codigo_sap": "MP-903", "contrato": "T-25", "proveedor": "Exportadora Demo",
                                      "item": "Frijol", "contenedores": 1, "dias_libres": 10})
    s.commit()
    return imp, f


def test_documentos_de_la_importacion(s, U):
    imp, f = _imp(U, s)
    assert set(imp.missing_documents(f)) >= {imp.TIPOS_DOC[k] for k in ("CERTIFICADO_ORIGEN", "FITOSANITARIO", "PACKING_LIST")}
    with pytest.raises(BusinessError):
        imp.add_document(U("vendedor1"), f, "FITOSANITARIO", "x.pdf")
    with pytest.raises(BusinessError):
        imp.add_document(U("importaciones"), f, "OTRO", "x.pdf")  # «otros» exige el nombre
    imp.add_document(U("importaciones"), f, "FITOSANITARIO", "fito.pdf")
    imp.add_document(U("importaciones"), f, "OTRO", "bl.pdf", nombre="Copia de BL")
    s.commit()
    assert imp.TIPOS_DOC["FITOSANITARIO"] not in imp.missing_documents(f) and len(f.documentos) == 2


def test_informe_de_calidad_pdf_o_generado(s, U, app):
    imp, f = _imp(U, s)
    with pytest.raises(BusinessError):
        imp.upload_quality_report(U("importaciones"), f, "inf.pdf")  # lo registra Calidad
    with pytest.raises(BusinessError):
        imp.upload_quality_report(U("asist.calidad"), f, "inf.docx")
    imp.upload_quality_report(U("asist.calidad"), f, "inf.pdf")
    s.commit()
    assert f.informe_calidad["modo"] == "PDF" and alerts_of(s, "IMPORT_INFORME_CALIDAD", f.id)
    # «Generar informe»: el formulario REG-CAL-005 viene prellenado con los datos de la importación
    c = _cliente(app, "asist.calidad")
    html = c.get(f"/calidad/registro/nuevo/RECEPCION_IMPORTADO?referencia_tipo=ImportFollowup&referencia_id={f.id}"
                 ).get_data(as_text=True)
    assert "T-25" in html and "Exportadora Demo" in html
    html = c.get("/gestion/importaciones").get_data(as_text=True)
    assert "Subir PDF" in html and "Generar informe" in html


def test_fumigacion_con_varios_productos_y_lotes(s, U):
    from app.models import StockLot
    from app.services import quality as q
    lots = s.query(StockLot).filter(StockLot.estado == "DISPONIBLE", StockLot.cantidad > 0).limit(2).all()
    form = {"fum_lot_id": [str(lots[0].id), str(lots[1].id), ""], "fum_producto": ["", "", ""],
            "fum_lote": ["", "", ""], "fum_cantidad": ["10", "", ""]}
    lineas = q.fumigation_lines(form)
    assert [x["lote"] for x in lineas] == [lots[0].lote, lots[1].lote] and lineas[0]["cantidad"] == 10
    with pytest.raises(BusinessError):
        q.fumigation_lines({"fum_producto": ["MP-1"], "fum_lote": [""], "fum_cantidad": ["5"]})
    q.register(U("asist.calidad"), "FUMIGACION", {"inicio_fecha": date.today().isoformat(), "lineas": lineas})
    s.commit()
    s.expire_all()
    assert all(x.estado == "EN_FUMIGACION" for x in lots)


def test_necesidad_semanal_exige_motivo_si_difiere_de_la_meta(s, U, monkeypatch):
    from app.services import ingresos_semana as ing
    lunes = ing.lunes(date.today())
    monkeypatch.setattr(ing, "meta_semana", lambda semana: 100000.0)
    with pytest.raises(BusinessError):
        ing.registrar(U("vendedor1"), lunes, 100000)
    ing.registrar(U("jefe.finanzas"), lunes, 103000)  # dentro de la tolerancia (5 %)
    with pytest.raises(BusinessError):
        ing.registrar(U("jefe.finanzas"), lunes, 150000)
    r = ing.registrar(U("jefe.finanzas"), lunes + timedelta(days=2), 150000, motivo="Pago de importación demo")
    s.commit()
    assert r.semana == lunes and r.variacion_motivo and len(r.historial) == 2


def test_tablero_de_la_empresa_venta_vs_meta_y_semana(app):
    html = _cliente(app, "jefe.finanzas").get("/gestion/empresa").get_data(as_text=True)
    assert "Venta del mes vs la meta" in html and "necesita ingresar" in html.lower()


def test_inicio_muestra_stock_sin_rotacion(app):
    html = _cliente(app, "jefe.logistica").get("/").get_data(as_text=True)
    assert "sin rotación" in html.lower()


def test_chat_entre_usuarios(s, U, app):
    from app.services import chat
    a, b = U("vendedor1"), U("jefe.logistica")
    with pytest.raises(BusinessError):
        chat.enviar(a, b.id, "   ")
    with pytest.raises(BusinessError):
        chat.enviar(a, a.id, "hola")
    chat.enviar(a, b.id, "¿Me apoyas con la OV demo?", ref_url="//externo.example/x")
    s.commit()
    assert chat.no_leidos(b) == 1
    _, msgs = chat.conversacion(b, a.id)
    s.commit()
    assert msgs[0].ref_url == "" and chat.no_leidos(b) == 0
    assert chat.conversaciones(a)[0]["user"].id == b.id
    c = _cliente(app, "jefe.logistica")
    assert "¿Me apoyas con la OV demo?" in c.get(f"/chat/?con={a.id}").get_data(as_text=True)


# ------------------------------------------------------------------ distribución
def test_ruta_manual_sin_ov_con_carga_escrita(s, U):
    from app.models import Driver, Vehicle
    from app.services import rutas_manual as rm
    v = s.query(Vehicle).filter_by(propio=True, disponible=True).first()
    d = s.query(Driver).filter_by(disponible=True).first()
    base = {"tipo_transportista": "CHOFER", "vehicle_id": v.id, "driver_id": d.id}
    with pytest.raises(BusinessError, match="al menos"):
        rm.create_manual(U("coord.distribucion"), date.today(), base)
    with pytest.raises(BusinessError, match="qué se lleva"):
        rm.create_manual(U("coord.distribucion"), date.today(), {**base, "libre_desc": [""], "libre_destino": ["ALM-2"],
                                                                 "libre_kg": ["10"]})
    r = rm.create_manual(U("coord.distribucion"), date.today(), {**base, "libre_desc": ["Materiales e insumos"],
                                                                 "libre_destino": ["Almacén demo 2"], "libre_kg": ["120"]})
    s.commit()
    assert r.peso_total == 120 and r.carga_libre[0]["destino"] == "Almacén demo 2" and not r.stops
    assert rm.daily_board(date.today())["filas"][0]["libre"]


def test_cuadro_de_despacho_lista_desplegable_quien_lleva(app):
    html = _cliente(app, "coord.distribucion").get("/operacion/despacho").get_data(as_text=True)
    assert '<select id="tt-sel" name="tipo_transportista"' in html and "Otra carga sin OV" in html


def test_checklist_desde_el_perfil_del_chofer(s, U, app):
    from app.models import Driver, Vehicle
    from app.services import rutas_manual as rm
    from app.services.vehicle_checklist import driver_checklists
    chofer = U("conductor1")
    d = s.query(Driver).filter_by(user_id=chofer.id).first()
    v = s.query(Vehicle).filter_by(propio=True, disponible=True).first()
    r = rm.create_manual(U("coord.distribucion"), date.today(), {"tipo_transportista": "CHOFER", "vehicle_id": v.id,
                                                                 "driver_id": d.id, "libre_desc": ["Muestras"], "libre_kg": ["5"]})
    s.commit()
    filas = driver_checklists(chofer)
    assert filas and filas[0]["r"].id == r.id and filas[0]["salida"] is None and filas[0]["pendiente"]
    html = _cliente(app, "conductor1").get("/distribucion/mis-entregas").get_data(as_text=True)
    assert "Mi checklist vehicular" in html and "Registrar checklist de salida" in html
    assert _cliente(app, "conductor1").get(f"/distribucion/ruta/{r.id}/checklist").status_code == 200


def test_preprogramacion_recomienda_consolidar_y_modificar_citas(s, U, new_order):
    from app.models import Route, RouteStop, Vehicle
    from app.services.rutas_recomendaciones import recomendaciones
    o1 = new_order([("PT-901", 2)], dias=1)
    o2 = new_order([("PT-901", 2)], dias=1)
    o3 = new_order([("PT-901", 2)], dias=1)
    f = o1.fecha_compromiso
    for o in (o1, o2, o3):
        o.lugar_entrega = "Almacén central demo"
    o1.hora_cita, o3.hora_cita = "08:00", "08:20"
    o3.lugar_entrega = "Otro punto demo"
    vs = s.query(Vehicle).filter(Vehicle.capacidad_kg > 0).order_by(Vehicle.capacidad_kg.desc()).limit(2).all()
    r1 = Route(fecha=f, vehicle_id=vs[0].id, zona="Z1", estado="PROPUESTA", peso_total=10, advertencias=[],
               hora_salida_prog="09:00")
    r2 = Route(fecha=f, vehicle_id=vs[1].id, zona="Z1", estado="PROPUESTA", peso_total=10, advertencias=[])
    r1.stops.append(RouteStop(order_id=o1.id, orden=1, peso_kg=5))
    r1.stops.append(RouteStop(order_id=o3.id, orden=2, peso_kg=5))
    r2.stops.append(RouteStop(order_id=o2.id, orden=1, peso_kg=10))
    s.add_all([r1, r2])
    s.commit()
    recs = recomendaciones(f, pendientes=[])
    titulos = " | ".join(x["titulo"] for x in recs)
    assert f"Consolidar las rutas #{r1.id} y #{r2.id}" in titulos  # baja ocupación, misma zona, caben juntas
    assert "mismo punto de entrega en 2 rutas" in titulos            # o1 y o2 van al mismo lugar en rutas distintas
    assert "antes de la salida" in titulos and "citas muy seguidas" in titulos
    assert recs[0]["prioridad"] == "ALTA"
