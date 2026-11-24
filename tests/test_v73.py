"""V73 (24-nov-2026): capacitación de choferes. Checklist de carga por guía, paso a paso en el cliente, impedimento de
ingreso, peaje/combustible/parqueo, correo de la cita, peso vs capacidad, demoras en clientes, cancelación tardía y
checklist vehicular (conos, luces diurnas). Solo datos ficticios."""
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .test_flujos import RECEPTOR, _user_chofer, dispatch
from .test_v12 import _route
from .test_v64 import _cliente


def test_checklist_de_carga_por_guia(app, s, U, cust):
    from app.models import Incident
    from app.services import ruta_chofer_v73 as rc
    from app.services.carga_v70 import novedades_abiertas
    r, o = _route(s, U, cust)
    g = rc.checklist_guia(r, o.id)
    lid = g["items"][0]["order_line_id"]
    q = g["items"][0]["cantidad"]
    res, nov = rc.registrar_checklist(U("aux.despacho"), r, o.id, {str(lid): {"ok": True}})
    assert res["conforme"] and not nov
    res, nov = rc.registrar_checklist(U("aux.despacho"), r, o.id, {str(lid): {"ok": False, "cantidad": q - 1}},
                                      "una caja golpeada", mal_paletizado=True)
    assert not res["conforme"] and nov[0]["tipo"] == "FALTANTE" and nov[0]["cantidad"] == 1
    assert novedades_abiertas(r) and s.query(Incident).filter_by(tipo="CARGA_MAL_PALETIZADA").count() == 1
    r.auxiliares = [U("aux.despacho").id]
    s.commit()
    rv = _cliente(app, "aux.despacho").get("/distribucion/mi-ruta")
    html = rv.get_data(as_text=True)
    assert rv.status_code == 200 and "Validar la carga guía por guía" in html and "Reportar faltante o sobrante" in html


def test_paso_a_paso_en_el_cliente_y_demoras(app, s, U, new_order, today):
    from app.services import distribution as dist
    from app.services import ruta_chofer_v73 as rc
    o = new_order([("PT-905", 10)])
    stop = dispatch(s, U, o, today)
    ch = _user_chofer(s, U, stop)
    with pytest.raises(BusinessError):
        rc.marcar(ch, stop, "ATENCION")  # primero «Llegué»
    dist.register_arrival(stop, ch)
    rc.marcar(ch, stop, "ATENCION")
    rc.impedimento(ch, stop, "seguridad no tiene el correo")
    dist.register_delivery(stop, ch, "f.jpg", "g.jpg", **RECEPTOR)
    rc.marcar(ch, stop, "SALIDA")
    s.commit()
    assert stop.hitos["atencion"] and stop.hitos["salida"] and stop.hitos["impedimentos"]
    d = rc.demoras(today - timedelta(days=1), today + timedelta(days=1))
    assert any(f["cliente"] == o.customer.nombre and f["visitas"] == 1 for f in d["filas"])
    assert "Demoras en clientes" in _cliente(app, "coord.distribucion").get("/distribucion/demoras-clientes").get_data(as_text=True)


def test_peaje_combustible_parqueo_y_correo_de_cita(s, U, cust):
    from app.models import Alert
    from app.services import ruta_chofer_v73 as rc
    r, o = _route(s, U, cust)
    ch = U("coord.distribucion")  # programa: puede registrar por encargo
    with pytest.raises(BusinessError):
        rc.registrar_gasto(ch, r, "PARQUEO")  # sin monto
    rc.registrar_gasto(ch, r, "PARQUEO", 5, "mercado", comprobante=False)
    rc.registrar_gasto(ch, r, "COMBUSTIBLE", nota="tarjeta sin saldo")
    s.flush()
    assert [g_["tipo"] for g_ in r.gastos] == ["PARQUEO", "COMBUSTIBLE"]
    assert s.query(Alert).filter_by(type_code="FLOTA_PEAJE_COMBUSTIBLE").count() == 1
    rc.adjuntar_correo_cita(ch, r.stops[0], "cita.pdf")
    assert r.stops[0].hitos["correos_cita"][0]["archivo"] == "cita.pdf"
    with pytest.raises(BusinessError):
        rc.adjuntar_correo_cita(U("aux.despacho"), r.stops[0], "x.pdf")


def test_exceso_de_peso(s, U, cust):
    from app.services import ruta_chofer_v73 as rc
    r, _ = _route(s, U, cust)
    r.peso_total = (r.vehicle.capacidad_kg or 0) + 100
    assert rc.exceso_peso(r)[2] is True


def test_cancelacion_tardia_avisa(s, U, new_order):
    from app.models import Alert
    from app.services import orders as osvc
    o = new_order([("PT-905", 5)], dias=0)
    osvc.cancel_order(o, U("coord.ventas"), "el cliente ya no lo quiere")
    s.flush()
    assert s.query(Alert).filter_by(type_code="OV_CANCELACION_TARDIA", entidad_id=str(o.id)).count() == 1


def test_checklist_vehicular_conos_y_luces_diurnas(s, U, cust):
    from app.services import vehicle_checklist as vc
    from .test_v12 import _vals
    assert any(c == "LUZ_DIURNAS" for c, *_ in vc.items())
    r, _ = _route(s, U, cust)
    ch = U("coord.distribucion")
    vals = dict(_vals(), CONOS_CANTIDAD="2")
    c = vc.register(ch, r, "SALIDA", vals, 1000)
    assert c.items["CONOS_CANTIDAD"] == 2
    assert vc.previo(r.vehicle_id, c.id + 1)["CONOS_CANTIDAD"] == 2
