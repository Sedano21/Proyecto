"""V70 (24-nov-2026): Excel de producción con filas sin fecha, cambio de estado parcial del lote, reglas de Calidad por
cliente, semáforo de inventarios y rotación, indicadores de Almacén, reempaque por OV, aviso de carga, firmas de salida,
recorrido de los vehículos y OV fuera de horario. Solo datos ficticios."""
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook

from app.models import StockLot
from app.services.core import BusinessError, set_param

from .test_v12 import _route
from .test_v64 import _cliente


def test_excel_de_programacion_con_filas_sin_fecha_no_se_detiene(s, tmp_path):
    from app.services import plan_excel
    wb = Workbook()
    ws = wb.active
    ws.title = "PROGRAMACION"
    ws.append(["PLAN DE PRODUCCION SEMANAL"])
    ws.append([])
    ws.append(["FECHA", "SEMANA", "# OP", "LINEA", "PROGRAMADO", "EJECUTADO", "CLIENTE", "PLANIFICADO MP- KG", "PRESENTACION",
               "U.M", "CODIGO", "PRODUCTO"])
    ws.append([datetime(2099, 1, 5), 1, 3, "R3", True, "", "", 400, 5, "UNIDADES", "PT-901", "PRODUCTO DEMO"])
    ws.append([None, 52, None, None, False, None, None, 4000, 0.4, None, "PT-902", "OTRO DEMO"])  # a medio llenar
    ws.append([datetime(2099, 1, 6), 1, 3, "LINEA FICTICIA", True, "", "", 100, 5, "UNIDADES", "PT-901", "PRODUCTO DEMO"])
    p = tmp_path / "plan.xlsx"
    wb.save(p)
    filas, sin = plan_excel.leer(str(p))
    assert [f["product_code"] for f in filas] == ["PT-901"]
    motivos = {x.get("motivo", "") for x in sin}
    assert "sin fecha" in motivos and any("no reconocida" in m for m in motivos)


def _lote_libre(s, minimo=10):
    from app.services.stock import free_qty
    return next(l for l in s.query(StockLot).filter(StockLot.estado == "DISPONIBLE", StockLot.cantidad >= minimo).all()
                if free_qty(l) >= minimo)


def test_cambio_de_estado_parcial_con_cantidad_y_ubicacion(s, U):
    from app.services import lotes_v70
    lot = _lote_libre(s)
    antes = lot.cantidad
    seg = lotes_v70.cambiar_estado(U("jefe.calidad"), lot, "NO_UTILIZABLE", "saco roto", "PARCIAL", 3, "z-01")
    s.flush()
    assert lot.cantidad == pytest.approx(antes - 3) and lot.estado == "DISPONIBLE"
    assert seg.estado == "NO_UTILIZABLE" and seg.cantidad == pytest.approx(3) and seg.ubicacion == "Z-01"
    assert seg.lote == lot.lote and seg.product_code == lot.product_code
    with pytest.raises(BusinessError):
        lotes_v70.cambiar_estado(U("jefe.calidad"), lot, "NO_UTILIZABLE", "x", "PARCIAL", "")
    lotes_v70.cambiar_estado(U("jefe.calidad"), lot, "DANADO", "todo", "TOTAL")
    assert lot.estado == "DANADO"


def test_regla_de_calidad_solo_para_o_bloqueado_para_clientes(s, U, cust):
    from app.services import lotes_v70
    from app.services.stock import lot_usable
    lot = _lote_libre(s, 1)
    a, b = cust("20000000001"), cust("20000000002")
    with pytest.raises(BusinessError):
        lotes_v70.restringir_clientes(U("aux.almacen"), lot, "SOLO", [a.id], "x")
    lotes_v70.restringir_clientes(U("jefe.calidad"), lot, "SOLO", [a.id], "exigencia del cliente")
    assert lot_usable(lot, customer=a)[0] and not lot_usable(lot, customer=b)[0]
    lotes_v70.restringir_clientes(U("jefe.calidad"), lot, "EXCEPTO", [a.id, b.id], "reclamo")
    assert not lot_usable(lot, customer=a)[0] and not lot_usable(lot, customer=b)[0]
    lotes_v70.restringir_clientes(U("jefe.calidad"), lot, "", [], "")
    assert lot_usable(lot, customer=b)[0]


def test_semaforo_lo_ven_todos_y_marca_rojo_si_no_cubre(app, s, new_order):
    from app.services import semaforo
    from app.services.stock import lots_of
    stock = sum(l.cantidad for l in lots_of("PT-901"))
    new_order([("PT-901", stock + 500)], dias=2)
    d = semaforo.semaforo()
    f = next(x for x in d["filas"] if x["code"] == "PT-901")
    assert f["estado"] == "ROJO" and f["saldo"] < 0 and f["sin_stock"] is not None
    assert any(g["familia"] == f["familia"] for g in d["familias"])
    for u in ("montacarguista", "aux.almacen", "jefe.ventas"):
        assert "Semáforo de inventarios" in _cliente(app, u).get("/almacen/semaforo").get_data(as_text=True)
    assert _cliente(app, "lider.almacen").get("/almacen/semaforo?formato=xlsx").status_code == 200
    assert "Stock de seguridad" in _cliente(app, "lider.almacen").get("/almacen/rotacion-analisis").get_data(as_text=True)


def test_stock_de_seguridad_por_variacion_mensual():
    from app.services.semaforo import stock_seguridad
    assert stock_seguridad([100] * 12, 30) == 0
    assert stock_seguridad([50, 150] * 6, 30) > 0


def test_indicadores_de_almacen_y_reempaque_por_ov(app, s):
    c = _cliente(app, "lider.almacen")
    assert "Indicadores de pedidos y operación" in c.get("/almacen/indicadores").get_data(as_text=True)
    assert c.get("/almacen/reempaques?vista=ov").status_code == 200
    from app.models import RolePermission
    perms = {rp.perm_code for rp in s.query(RolePermission).filter_by(role_code="LIDER_ALMACEN")}
    assert {"reempaque.solicitar", "reempaque.ejecutar", "almacen.indicadores", "produccion.partes_ver"} <= perms
    sup = {rp.perm_code for rp in s.query(RolePermission).filter_by(role_code="SUPERV_ALMACEN")}
    assert "produccion.partes_ver" in sup


def test_aviso_de_carga_llega_al_almacen_que_corresponde(app, s, U, cust):
    from app.models import Alert
    from app.services import carga_v70 as cv
    r, o = _route(s, U, cust)
    assert cv.almacenes_de(r) == ["1560"]  # producto terminado
    assert U("lider.almacen") in cv.personal_de("1560")
    chofer = r.driver.user_id and s.get(type(U("lider.almacen")), r.driver.user_id) or U("coord.distribucion")
    with pytest.raises(BusinessError):
        cv.unidad_lista(chofer, r, False, "Almacén 1560")
    cv.unidad_lista(chofer, r, True, "Almacén 1560")
    s.flush()
    a = s.query(Alert).filter_by(type_code="CARGA_UNIDAD_LISTA").order_by(Alert.id.desc()).first()
    assert U("lider.almacen").id in a.usuarios
    with pytest.raises(BusinessError):
        cv.responder(U("lider.almacen"), r, [])
    cv.responder(U("lider.almacen"), r, [U("aux.almacen").id], "va el equipo 1")
    assert r.aviso_carga["respuesta"]["asignados"][0]["id"] == U("aux.almacen").id
    cv.subir_evidencia(U("lider.almacen"), r, "carga_antes", ["antes.jpg"])
    cv.subir_evidencia(U("lider.almacen"), r, "carga_video", ["carga.mp4"])
    assert r.fotos["carga_antes"][0]["archivo"] == "antes.jpg"
    assert "Carga de unidades" in _cliente(app, "lider.almacen").get("/almacen/carga").get_data(as_text=True)


def test_auxiliar_firma_solo_si_va_y_calidad_es_opcional(s, U, cust):
    from app.services import despacho as dsp
    set_param("vistos_buenos_salida", ["SEGURIDAD", "CHOFER", "AUX_DESPACHO", "LIDER_ALMACEN"])
    r, _ = _route(s, U, cust)
    assert "AUX_DESPACHO" not in dsp.missing_exit_approvals(r)
    r.auxiliares = [U("aux.despacho").id] if s.query(type(U("aux.almacen"))).filter_by(username="aux.despacho").first() \
        else [U("aux.almacen").id]
    assert "AUX_DESPACHO" in dsp.missing_exit_approvals(r)
    assert "CALIDAD" not in dsp.missing_exit_approvals(r)


def test_recorrido_del_vehiculo(app, s, U, cust):
    r, o = _route(s, U, cust)
    s.commit()
    html = _cliente(app, "coord.distribucion").get(f"/distribucion/recorridos?fecha={r.fecha.isoformat()}").get_data(as_text=True)
    assert "Recorrido de los vehículos" in html and o.numero in html and "Retorno a la central" in html and "sin auxiliar" in html


def test_ov_fuera_de_horario_jefe_de_operaciones_y_gerencia(app, s, U, cust):
    from app.services import fuera_horario as fh
    from app.services import orders as osvc
    set_param("hora_corte_ov_dia_siguiente", "00:00")
    manana = date.today() + timedelta(days=1)
    o = osvc.create_order(U("coord.ventas"), "FH-1", cust().id, manana,
                          [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10}], oc_archivo="oc.pdf", evaluar=False)
    s.flush()
    assert o.estado == "BORRADOR" and fh.es_fuera_de_corte(o)
    fh.solicitar(U("coord.ventas"), o, "cliente clave, pedido urgente")
    with pytest.raises(BusinessError):
        fh.decidir_jo(U("coord.ventas"), o, True)
    jo = next((u for u in s.query(type(U("coord.ventas"))).filter_by(role_code="JEFE_OPERACIONES").all()), None)
    if jo is None:
        pytest.skip("sin usuario Jefe de Operaciones en la demo")
    with pytest.raises(BusinessError):
        fh.decidir_jo(jo, o, False, "")
    fh.decidir_jo(jo, o, False, "no hay capacidad")
    assert o.estado == "BORRADOR" and o.fuera_horario["estado"] == "DESESTIMADA"
    fh.elevar(U("coord.ventas"), o, "el cliente lo necesita")
    gg = s.query(type(jo)).filter_by(role_code="GERENCIA_GENERAL").first()
    fh.decidir_gg(gg, o, True, "va")
    assert o.estado != "BORRADOR" and o.fuera_horario["estado"] == "APROBADA_GG"
    assert o.numero in _cliente(app, "lider.almacen").get("/almacen/fuera-horario").get_data(as_text=True)


def test_pantallas_v70_cargan(app, s, U, cust):
    r, o = _route(s, U, cust)
    s.commit()
    for user, url, txt in [("jefe.calidad", "/almacen/stock", "Clientes (Calidad)"), ("lider.almacen", "/almacen/stock", "Cambiar estado"),
                           ("lider.almacen", "/suministro/movimientos", "dl-pt"), ("lider.almacen", "/almacen/reempaques", "Despacho"),
                           ("sistemas", "/usuarios", "Usuarios"), ("coord.distribucion", f"/distribucion/ruta/{r.id}", "Ruta"),
                           ("lider.almacen", "/almacen/fuera-horario", "fuera de horario")]:
        resp = _cliente(app, user).get(url, follow_redirects=True)
        assert resp.status_code == 200, (user, url, resp.status_code)
        assert txt in resp.get_data(as_text=True), (user, url)


def test_guia_de_sap_se_ve_e_imprime(app, s, U, new_order):
    from app.models import SapMovement
    o = new_order([("PT-901", 5)])
    s.add(SapMovement(clave="GUIA:777001:0", tipo="GUIA", docentry=777001, documento="T001-999", fecha=date.today(),
                      ov_numero=o.numero, cliente="CLIENTE FICTICIO SAC", product_code="PT-901", cantidad=5))
    s.commit()
    c = _cliente(app, "jefe.ventas")
    html = c.get("/ov/guia-sap/777001?sap=0").get_data(as_text=True)
    assert "T001-999" in html and "PT-901" in html and "Imprimir" in html
    assert c.get("/ov/guia-sap?doc=T001-999&sap=0").status_code == 200
    r = c.get("/ov/guia-sap/777001?sap=0&formato=pdf")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    assert "/ov/guia-sap/777001" in c.get(f"/ov/{o.id}").get_data(as_text=True)
    assert "/ov/guia-sap/777001" in c.get("/ov/estado").get_data(as_text=True)


def test_todos_los_que_validan_ven_guia_factura_y_preguia(app, s, U, cust):
    from app.models import SapBilling, SapMovement
    r, o = _route(s, U, cust)
    s.add(SapMovement(clave="GUIA:777002:0", tipo="GUIA", docentry=777002, documento="T001-998", fecha=date.today(),
                      ov_numero=o.numero, factura="F001-555", cliente="CLIENTE FICTICIO SAC", product_code="PT-905",
                      cantidad=5, total=50, igv=9))
    s.add(SapBilling(clave="FACTURA:888001", tipo="FACTURA", numero="F001-555", fecha=date.today(),
                     cliente="CLIENTE FICTICIO SAC", total=59, igv=9))
    s.commit()
    for u in ("aux.despacho", "seguridad", "superv.calidad", "lider.almacen", "aux.almacen", "conductor1"):
        if s.query(type(U("lider.almacen"))).filter_by(username=u).first() is None:
            continue
        c = _cliente(app, u)
        assert c.get("/ov/guia-sap/777002?sap=0").status_code == 200, u
        html = c.get("/ov/factura-sap?doc=F001-555&sap=0").get_data(as_text=True)
        assert "F001-555" in html and "T001-998" in html, u
    c = _cliente(app, "aux.despacho")
    assert c.get(f"/distribucion/ruta/{r.id}/folio?tipo=preguia").status_code == 200
    carga = _cliente(app, "lider.almacen").get("/almacen/carga").get_data(as_text=True)
    assert "pre-guía de la ruta" in carga and "/ov/guia-sap/777002" in carga and "factura F001-555" in carga
    det = _cliente(app, "coord.distribucion").get(f"/distribucion/ruta/{r.id}").get_data(as_text=True)
    assert "Documentos para validar la carga" in det and "/ov/factura-sap?doc=F001-555" in det
