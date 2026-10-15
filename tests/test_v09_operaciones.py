"""Observaciones al demo v0.7 – Almacén, Logística, Producción, Calidad, Distribución y Seguridad."""
from datetime import date, timedelta

import pytest

from app.models import Alert, PurchaseRequest, StockLot
from app.services import picking as pk
from app.services.core import BusinessError

from .conftest import alerts_of


def test_alerta_aprobada_queda_derivada_al_area_destino(s, U):
    from app.services import alert_actions, alerts
    from app.services import purchasing as buy
    r = buy.create_request(U("coord.almacen"), "EN-901", 5)
    s.flush()
    a = alerts_of(s, "COMPRA_APROBACION_LOGISTICA", r.id)[0]
    assert alerts.can_act(U("coord.logistica"), a) and not alerts.can_act(U("gerente.operaciones"), a)
    alert_actions.decide(a, U("coord.logistica"), True, "ok")
    s.flush()
    assert a.derivadas and alerts.display_state(a)[0] == "DERIVADA" and "Compras" in alerts.display_state(a)[1]
    hija = s.get(Alert, a.derivadas[0])
    hija.estado = "COMPLETADA"
    assert alerts.display_state(a)[0] == "COMPLETADA"


def test_picking_cambio_de_lote_por_motivo(s, U, new_order):
    from app.services import orders as osvc
    from app.services.stock import line_reserved
    o = new_order([("PT-901", 50)])
    t = pk.tasks_of(o)[0]
    assert any(u.role_code in pk.ROLES_PROPUESTA for u in pk.staff(t.warehouse_code))
    pk.start(t, U("lider.almacen"), "ini.jpg")
    osvc.validate_picking_plan(o, U("lider.almacen"))
    line = o.lines[0]
    res = next(r for r in line.reservations if r.estado == "ACTIVA")
    viejo = res.lot
    otro = s.query(StockLot).filter_by(product_code="PT-901", lote="L901A").one()
    assert otro in pk.lot_options(t, line)
    with pytest.raises(BusinessError, match="observación"):
        pk.change_lot(t, U("lider.almacen"), res.id, otro.id, 10, "ROTURA", "")
    disp_antes = viejo.cantidad
    pk.change_lot(t, U("lider.almacen"), res.id, otro.id, 10, "ROTURA", "Sacos rotos en el rack")
    s.flush()
    assert line_reserved(line) == 50 and viejo.cantidad == disp_antes - 10
    obs = s.query(StockLot).filter_by(product_code="PT-901", lote=viejo.lote, estado="OBSERVADO").one()
    assert obs.cantidad == 10 and alerts_of(s, "PICKING_LOTE_OBSERVADO")
    res2 = next(r for r in line.reservations if r.estado == "ACTIVA" and r.lot_id == viejo.id)
    pk.change_lot(t, U("lider.almacen"), res2.id, otro.id, 5, "DIFICIL_ACCESO", "Pallet al fondo")
    s.flush()
    assert viejo.estado == "DISPONIBLE" and len(t.cambios_lote) == 2
    # el formato toma lote y fechas del stock reservado: el auxiliar solo llena lo despachado
    r_otro = next(r for r in line.reservations if r.estado == "ACTIVA" and r.lot_id == otro.id)
    pk.record(t, U("lider.almacen"), line.id, r_otro.cantidad, otro.lote)
    s.flush()
    assert pk.format_rows([t])[0]["lote"] == otro.lote


def test_asignacion_persona_o_grupo_y_destinatarios(s, U, new_order):
    o = new_order([("PT-905", 10)])
    t = pk.tasks_of(o)[0]
    a = alerts_of(s, "PICKING_PROGRAMADO", o.id)[0]
    assert {"JEFE_LOGISTICA", "COORD_LOGISTICA", "GERENCIA_OPERACIONES"} <= set(a.roles)
    from app.services import alerts
    assert alerts.nature_for(U("gerente.operaciones"), a) == "INFORMATIVA" and alerts.can_act(U("lider.almacen"), a)
    ids = [u.id for u in pk.staff(t.warehouse_code)][:4]
    pk.assign(t, U("lider.almacen"), ids)  # grupo sin límite
    assert t.asignados == sorted(ids)
    pk.assign(t, U("lider.almacen"), [ids[0]])  # una persona
    assert t.asignados == [ids[0]]


def test_presolicitudes_agrupadas_con_ov_y_motivo(s, U, cust):
    from app.services import purchasing as buy
    from app.models import SalesOrder
    o1, o2 = s.query(SalesOrder).limit(2).all() or (None, None)
    f = date.today() + timedelta(days=10)
    r1 = buy.create_request(None, "EN-901", 4, f, origen="OV", order=o1, sistema=True)
    r2 = buy.create_request(None, "EN-901", 6, f, origen="OV", order=o2, sistema=True)
    s.flush()
    if o1 is not None and o2 is not None:
        assert r1.id == r2.id and r1.cantidad == 10 and len(r1.ordenes) == 2
    assert "Quiebre de stock" in r1.motivo and alerts_of(s, "QUIEBRE_STOCK", r1.id)


def test_ejecucion_de_compra_requiere_cotizaciones_y_go(s, U):
    from app.services import purchasing as buy
    r = buy.create_request(U("coord.almacen"), "EN-901", 5)
    buy.approve_logistics(r, U("coord.almacen"), True)  # el Coordinador de Almacén autoriza la presolicitud
    assert r.estado == "SOLICITADA"
    buy.quote(r, U("compras"), "Proveedor A", "COT-A", precio=3.0)
    buy.quote(r, U("compras"), "Proveedor B", "COT-B", precio=2.8, plazo="5 días")
    buy.choose_quote(r, U("compras"), 0)
    assert len(r.cotizaciones) == 2 and r.proveedor == "Proveedor A"
    with pytest.raises(BusinessError, match="Gerencia de Operaciones"):
        buy.generate_order(r, U("compras"), "OC-9", date.today() + timedelta(days=3), "EXT-002")
    buy.request_go_approval(r, U("compras"))
    assert alerts_of(s, "COMPRA_APROBACION_GERENCIA", r.id)
    buy.approve_go(r, U("gerente.operaciones"), True)
    buy.generate_order(r, U("compras"), "OC-9", date.today() + timedelta(days=3), "EXT-002")
    assert r.estado == "ORDEN_GENERADA"


def test_capacidad_por_grupo_y_jornada(s, U):
    from app.services import production as prod
    assert prod.capacity_group("R2")["grupo"] == "RAUMAK 1 Y 2" and prod.capacity_group("CIMBRIA")["kg_dia"] == 25500
    domingo = date.today() + timedelta(days=(6 - date.today().weekday()) % 7 or 7)
    assert prod.day_factor(domingo) == 0 and prod.day_factor(domingo - timedelta(days=1)) == 0.5


def test_requerimientos_consolidados_y_preprogramacion(s, U):
    from app.services import production as prod
    r = prod.create_request("PT-903", 300, U("coord.almacen"), fecha_requerida=date.today() + timedelta(days=3))
    s.flush()
    d = prod.requirements("SEMANA")
    assert any(f["producto"] == "PT-903" and f["cantidad"] >= 300 for f in d["filas"])
    nuevas = prod.preschedule_plan(U("jefe.produccion"), "SEMANA")
    s.flush()
    assert nuevas and all(p.origen == "SISTEMA" for p in nuevas)
    with pytest.raises(BusinessError, match="Jefe de Producción"):
        prod.update_plan(U("asist.produccion"), nuevas[0], 1, "ajuste")
    prod.update_plan(U("jefe.produccion"), nuevas[0], 1, "ajuste")
    assert not [f for f in prod.requirements("SEMANA")["filas"] if f["producto"] == "PT-903" and f["por_planificar"] > 300]
    assert r.id


def test_calidad_antes_durante_y_lote_vs_liquidacion(s, U):
    from app.services import production as prod
    from app.services import quality as q
    rec = q.register(U("asist.calidad"), "PREVIO_PRODUCCION", {"personal_higiene": True, "equipos_calidad_higiene": False,
                                                               "linea": "TRUER", "detalle": "Faja sucia"})
    assert rec.resultado == "NO_CONFORME" and alerts_of(s, "CALIDAD_NO_CONFORME")
    q.register(U("asist.calidad"), "LOTE_PRODUCIDO", {"cantidad": 90, "linea": "TRUER"}, "PT-903", "LQ-LOTE-1")
    liq = prod.register_liquidation(U("asist.produccion"), "LQ-77", "PT-903", 100, "LQ-LOTE-1")
    s.flush()
    c = q.lot_entries_vs_liquidation(liq)
    assert c["calidad"] == 90 and not c["coincide"] and alerts_of(s, "CALIDAD_VS_LIQUIDACION", liq.id)


def test_seguridad_guia_por_item_horas_vehiculo_y_llegadas(s, U):
    from app.services import distribution as dsvc
    from app.services import purchasing as buy
    from app.services import quality as q
    from app.services import security as sec
    from app.models import Route
    v = q.register(U("seguridad"), "VEHICULO_SEGURIDAD", {"placa": "ABC-123", "chofer": "X", "vehiculo_en_orden": False,
                                                          "detalle": "Llanta baja"})
    assert v.resultado == "NO_CONFORME" and alerts_of(s, "VEHICULO_SUBSANAR", v.id)
    r = buy.create_request(U("coord.almacen"), "EN-901", 5)
    r.estado, r.numero_oc, r.fecha_prevista, r.warehouse_code = "ORDEN_GENERADA", "OC-77", date.today(), "EXT-002"
    s.flush()
    assert any(a["tipo"] == "COMPRA" and a["id"] == r.id for a in sec.arrivals())
    with pytest.raises(BusinessError, match="incidente"):
        sec.register_arrival_check(U("seguridad"), "COMPRA", r.id, 4, False)
    sec.register_arrival_check(U("seguridad"), "COMPRA", r.id, 4, False, "Faltan 1 caja", "foto.jpg", "ABC-123")
    assert alerts_of(s, "LLEGADA_INCIDENTE", r.id)
    ruta = Route(fecha=date.today(), estado="CONFIRMADA", zona="Z")
    s.add(ruta)
    s.flush()
    with pytest.raises(BusinessError, match="inicio del despacho"):
        dsvc.register_security_time(ruta, U("seguridad"), "partida", "10:00")
    dsvc.register_security_time(ruta, U("seguridad"), "inicio_despacho", "09:00")
    dsvc.register_security_time(ruta, U("seguridad"), "partida", "")
    assert ruta.horas_seguridad["inicio_despacho"]["hora"] == "09:00" and "partida" in ruta.horas_seguridad
    with pytest.raises(BusinessError, match="motivo"):
        dsvc.register_security_check(ruta, U("seguridad"), "G-1", [{"producto": "PT-905", "esperado": 1, "guia": 1,
                                                                     "cargado": 1, "conforme": False, "motivo": ""}])
    disc = dsvc.register_security_check(ruta, U("seguridad"), "G-1", [{"producto": "PT-905", "esperado": 1, "guia": 1,
                                                                       "cargado": 1, "conforme": False, "motivo": "Saco roto"}])
    assert disc and "Saco roto" in disc[0]


def test_chofer_no_da_conformidad_del_producto(s, U):
    from app.services import despacho as dsp
    from app.models import Route
    ruta = Route(fecha=date.today(), estado="CONFIRMADA", zona="Z")
    s.add(ruta)
    s.flush()
    with pytest.raises(BusinessError, match="no el chofer"):
        dsp.validate_load(ruta, U("conductor1"), {})


def test_pantallas_nuevas(app, s):
    from .test_web import login
    c = app.test_client()
    login(c, "seguridad")
    for url in ("/distribucion/seguridad/llegadas", "/calidad/registro/nuevo/VEHICULO_SEGURIDAD"):
        assert c.get(url).status_code == 200, url
    c2 = app.test_client()
    login(c2, "jefe.produccion")
    assert "Requerimientos consolidados" in c2.get("/produccion/plan?periodo=SEMANA").get_data(as_text=True)
    c3 = app.test_client()
    login(c3, "coord.ventas")
    assert c3.get("/configuracion/canales").status_code == 200
    c4 = app.test_client()
    login(c4, "asist.ventas")
    assert c4.get("/configuracion/canales").status_code == 403 and c4.get("/ov/regularizacion").status_code == 200
