"""Reglas incorporadas desde el TO-BE COPROD-ONE (L5) y las decisiones Q3/Q4 del 11-oct-2026."""
import os
from datetime import date, timedelta

import openpyxl
import pytest

from app.models import Certificate, Incident, SalesOrder
from app.services import despacho as dsp
from app.services import distribution as dist
from app.services import orders as osvc
from app.services import quality as qual
from app.services import transfers as trs
from app.services import uploads as up
from app.services.core import BusinessError
from app.services.stock import line_reserved

from .conftest import alerts_of
from .test_flujos import approve_certs


def _prepare_and_confirm(s, U, o):
    osvc.validate_picking_plan(o, U("lider.almacen"))
    for l in o.lines:
        for r in [r for r in l.reservations if r.estado == "ACTIVA"]:
            osvc.register_picking(o, U("lider.almacen"), l.id, r.cantidad, r.lot.lote)
    r = dist.active_stop(o).route
    dist.confirm_route(r, U("coord.distribucion"))
    s.commit()
    return r


def test_ov_completa_avisa_certifica_y_programa_ruta(s, U, new_order):
    o = new_order([("PT-905", 100)])
    a = alerts_of(s, "OV_COMPLETA", o.id)[0]
    assert set(a.roles) == {"JEFE_LOGISTICA", "JEFE_VENTAS", "COORD_ALMACEN", "AUX_ALMACEN"}  # ronda UX: Auxiliar de Almacén
    # obs. demo v0.7: el precertificado solo se emite después del picking
    assert s.query(Certificate).filter_by(order_id=o.id).count() == 0
    osvc.finish_preparation(o, U("lider.almacen"))
    s.commit()
    c = s.query(Certificate).filter_by(order_id=o.id).one()
    assert c.estado == "BORRADOR" and alerts_of(s, "CERTIFICADO_REVISION")
    assert dist.active_stop(o).route.estado == "PROPUESTA"
    approve_certs(s, U, o)
    s.commit()
    listo = alerts_of(s, "CERTIFICADO_LISTO")[0]
    assert {"COORD_DISTRIBUCION", "GERENCIA_OPERACIONES", "JEFE_LOGISTICA"} <= set(listo.roles)


def test_modificar_plan_de_picking_cambia_lote(s, U, new_order):
    o = new_order([("PT-901", 50)])
    res = o.lines[0].reservations[0]
    assert res.lot.lote == "L901B"  # FEFO
    from app.models import StockLot
    l901a = s.query(StockLot).filter_by(product_code="PT-901", lote="L901A").one()
    osvc.reassign_pick_lot(o, U("lider.almacen"), res.id, l901a.id)
    s.commit()
    assert [r.lot.lote for r in o.lines[0].reservations if r.estado == "ACTIVA"] == ["L901A"]
    assert line_reserved(o.lines[0]) == 50
    assert s.query(Certificate).filter_by(order_id=o.id).count() == 0  # el precertificado se emite tras el picking
    osvc.finish_preparation(o, U("lider.almacen"))
    s.commit()
    assert [s.get(StockLot, c.lot_id).lote for c in s.query(Certificate).filter_by(order_id=o.id)] == ["L901A"]  # con el lote picado


def test_carga_incongruente_y_documentos_faltantes(s, U, new_order):
    o = new_order([("PT-905", 60)])
    r = _prepare_and_confirm(s, U, o)
    if r.driver and r.driver.user_id:  # V7: el chofer valida primero
        dsp.driver_check_load(r, s.get(type(U("conductor1")), r.driver.user_id), {})
    with pytest.raises(BusinessError):  # falta foto del vehículo antes de la estiba
        dsp.validate_load(r, U("aux.despacho"), {})
    dsp.add_photo(r, U("aux.despacho"), "vehiculo", "v.jpg")
    with pytest.raises(BusinessError):  # la foto de inicio de carga la sube Seguridad
        dsp.add_photo(r, U("aux.despacho"), "inicio_carga", "x.jpg")
    dsp.register_loading_incident(r, U("seguridad"), "inc.jpg", "Saco roto al estibar", "10:15")
    assert alerts_of(s, "INC_CARGA") and s.query(Incident).filter_by(tipo="INCIDENCIA_CARGA").count() == 1
    line_id = str(o.lines[0].id)
    inc = dsp.validate_load(r, U("aux.despacho"), {line_id: {"cargado": "55"}})
    s.commit()
    assert inc and not r.carga_validada
    assert set(alerts_of(s, "CARGA_INCONGRUENCIA")[0].roles) == {"LIDER_ALMACEN", "COORD_ALMACEN"}
    with pytest.raises(BusinessError):  # sin foto de mercadería cargada
        dsp.validate_load(r, U("aux.despacho"), {line_id: {"cargado": "60"}})
    dsp.add_photo(r, U("aux.despacho"), "mercaderia_cargada", "m.jpg")
    dsp.add_photo(r, U("conductor1"), "vehiculo_salida", "salida.jpg")  # obs. demo v0.6
    assert dsp.validate_load(r, U("aux.despacho"), {line_id: {"cargado": "60"}}) == []
    assert "FACTURACION" in alerts_of(s, "CAMION_CARGADO")[0].roles
    faltan = dsp.review_documents(r, U("seguridad"), impresos=True)
    assert any("guía" in f for f in faltan) and any("factura" in f for f in faltan) and any("certificado" in f for f in faltan)
    a = alerts_of(s, "DOCUMENTOS_FALTANTES")[0]
    assert {"COORD_DISTRIBUCION", "FACTURACION", "JEFE_CALIDAD", "JEFE_LOGISTICA", "GERENCIA_OPERACIONES"} <= set(a.roles)
    with pytest.raises(BusinessError):  # sin autorización de Seguridad no hay salida
        dist.confirm_departure(r, U("lider.almacen"), {k: True for k, _ in dist.CHECKLIST})
    st = r.stops[0]
    with pytest.raises(BusinessError):  # guía de SAP exige archivo
        dsp.set_guide(st, U("coord.distribucion"), "T001-1", "SAP")
    dsp.set_guide(st, U("coord.distribucion"), "T001-1", "SAP", "guia.pdf")
    with pytest.raises(BusinessError):
        dsp.set_invoice(st, U("coord.distribucion"), "F1", "f.pdf")
    dsp.set_invoice(st, U("facturacion"), "F001-9", "f.pdf")
    approve_certs(s, U, o)
    assert dsp.review_documents(r, U("seguridad"), impresos=True) == []
    dsp.give_exit_ok(r, (s.get(type(U("conductor1")), r.driver.user_id) if r.driver and r.driver.user_id else U("coord.distribucion")))  # V8 (D02): visto bueno del chofer
    lines = [{**e, "guia": e["esperado"], "cargado": e["esperado"]} for e in dist.expected_lines(r)]
    dist.register_security_check(r, U("seguridad"), "T001-1", lines)
    dist.confirm_departure(r, U("lider.almacen"), {k: True for k, _ in dist.CHECKLIST})
    s.commit()
    assert o.estado == "DESPACHADA"
    assert alerts_of(s, "RUTA_ASIGNADA") and alerts_of(s, "MONTACARGUISTA_DESPACHO")
    dist.register_arrival(st, U("conductor1"))  # ronda UX: lo registra el chofer
    assert set(alerts_of(s, "DIST_LLEGADA")[0].roles) == {"COORD_DISTRIBUCION", "JEFE_LOGISTICA", "GERENCIA_OPERACIONES"}
    dist.register_incident(U("asist.distribucion"), "RECHAZO_CITA", "Llegó fuera de la ventana horaria", stop=st)
    s.commit()
    assert st.estado == "NO_ENTREGADO" and o.estado == "DEVUELTA"


def test_factura_con_modificaciones_si_incompleto(s, U, new_order, today):
    o = new_order([("PT-901", 450)])
    osvc.decide_partial(o, U("gerente.general"), True, "ok", today + timedelta(days=3))
    r = _prepare_and_confirm(s, U, o)
    dsp.add_photo(r, U("aux.despacho"), "vehiculo", "v.jpg")
    dsp.add_photo(r, U("aux.despacho"), "mercaderia_cargada", "m.jpg")
    dsp.add_photo(r, U("conductor1"), "vehiculo_salida", "salida.jpg")  # obs. demo v0.6
    if r.driver and r.driver.user_id:  # V7: el chofer valida primero
        dsp.driver_check_load(r, s.get(type(U("conductor1")), r.driver.user_id), {})
    dsp.validate_load(r, U("aux.despacho"), {})
    dif = dsp.set_invoice(r.stops[0], U("facturacion"), "F001-2", "f.pdf")
    assert dif and r.stops[0].factura_con_modificaciones


def test_sistemas_no_aprueba_gerencia_general_si(s, U, new_order):
    o = new_order([("PT-903", 50)])
    from app.models import StockLot
    lot = s.query(StockLot).filter_by(product_code="PT-903").one()
    t = trs.request_transfer(U("coord.logistica"), lot.id, "ALM-001", 50, o)
    with pytest.raises(BusinessError):
        trs.authorize(t, U("sistemas"), True)
    trs.authorize(t, U("gerente.general"), True)
    assert t.estado == "AUTORIZADO"
    with pytest.raises(BusinessError):
        osvc.cancel_order(o, U("sistemas"), "x")
    with pytest.raises(BusinessError):
        qual.release_lot(lot, U("sistemas"), True, "x")


def test_asistente_carga_consolidado_cambios_requieren_autorizacion(s, U, tmp_path):
    from app.demo_data import write_ovs
    from app.services.core import set_param
    set_param("conciliacion_ov_modo", "APLICAR")  # modo previo a la marcha blanca (en ALERTAR solo se concilia)
    p = os.path.join(tmp_path, "ovs.xlsx")
    write_ovs(p, date.today())
    up.confirm(up.create_batch(U("asist.ventas"), "OV", p, "ovs.xlsx"), U("asist.ventas"))
    o = s.query(SalesOrder).filter_by(numero="SAP-9001").one()
    assert o.lines[0].cantidad == 400
    wb = openpyxl.load_workbook(p)
    ws = wb["OVS"]
    for row in ws.iter_rows(min_row=2):
        if row[1].value == "SAP-9001" and row[12].value == "PT-905":
            row[14].value = 500
    wb.save(p)
    res = up.confirm(up.create_batch(U("asist.ventas"), "OV", p, "ovs.xlsx"), U("asist.ventas"))
    s.commit()
    assert res["solicitudes_de_modificacion"] == 1 and res["ov_modificadas"] == 0
    assert o.lines[0].cantidad == 400 and alerts_of(s, "OV_MODIF_SOLICITUD")
