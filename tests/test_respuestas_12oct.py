"""Decisiones del usuario del 12-oct-2026: Q2 (OTIF por salida y fill rate), Q3 (aprueba GO o Jefatura de Logística),
Q5 (almacenes virtuales ALM-003 / ALM-010), Q8 (discrepancia de guía bloquea; Logística puede aprobar la salida),
Q12-Q15 (pre-solicitudes automáticas y sus aprobadores), Q16 (Líder Operativo autoriza la salida) y Q17 (dos
coordinadores de almacén)."""
import os
from datetime import timedelta

import pytest

from app.models import ProductionRequest, PurchaseRequest, RepackRequest, StockLot, Transfer, Warehouse
from app.services import despacho as dsp
from app.services import distribution as dist
from app.services import kpis
from app.services import orders as osvc
from app.services import purchasing as buy
from app.services import repack as rep
from app.services import transfers as trs
from app.services import uploads as up
from app.services.core import BusinessError

from .conftest import alerts_of
from .test_flujos import approve_certs


def _ready_route(s, U, o, discrepancia=False):
    """Prepara el pedido y deja la ruta lista para la salida (TO-BE), opcionalmente con discrepancia de guía."""
    osvc.validate_picking_plan(o, U("lider.almacen"))
    for l in o.lines:
        for r in [r for r in l.reservations if r.estado == "ACTIVA"]:
            osvc.register_picking(o, U("lider.almacen"), l.id, r.cantidad, r.lot.lote)
    r = dist.active_stop(o).route
    dist.confirm_route(r, U("coord.distribucion"))
    dsp.add_photo(r, U("aux.despacho"), "vehiculo", "v.jpg")
    dsp.add_photo(r, U("aux.despacho"), "mercaderia_cargada", "m.jpg")
    dsp.validate_load(r, U("aux.despacho"), {})
    lines = [{**e, "guia": e["esperado"], "cargado": e["esperado"] - (1 if discrepancia else 0)} for e in dist.expected_lines(r)]
    dist.register_security_check(r, U("seguridad"), "T001-9", lines)
    for st in r.stops:
        dsp.set_guide(st, U("coord.distribucion"), "T001-9", "SISTEMA")
        dsp.set_invoice(st, U("facturacion"), f"F-{st.order.numero}", "f.pdf")
        approve_certs(s, U, st.order)
    assert dsp.review_documents(r, U("seguridad"), impresos=True) == []
    dsp.give_exit_ok(r, U("aux.despacho"))  # Q16: visto bueno del auxiliar
    s.commit()
    return r


CHECK = {k: True for k, _ in dist.CHECKLIST}


def test_q16_lider_operativo_autoriza_salida(s, U, new_order):
    o = new_order([("PT-905", 40)])
    r = _ready_route(s, U, o)
    for quien in ("coord.distribucion", "seguridad", "sistemas"):
        with pytest.raises(BusinessError):
            dist.confirm_departure(r, U(quien), CHECK)
    dist.confirm_departure(r, U("lider.almacen"), CHECK)
    assert r.estado == "EN_RUTA" and o.estado == "DESPACHADA"


def test_q8_discrepancia_bloquea_y_logistica_aprueba(s, U, new_order):
    o = new_order([("PT-905", 40)])
    r = _ready_route(s, U, o, discrepancia=True)
    a = alerts_of(s, "GUIA_DISCREPANCIA")[0]
    assert {"JEFE_LOGISTICA", "COORD_LOGISTICA"} <= set(a.roles) and a.estado != "CERRADA"
    with pytest.raises(BusinessError):  # bloquea la salida
        dist.confirm_departure(r, U("lider.almacen"), CHECK)
    for quien in ("lider.almacen", "coord.distribucion", "seguridad"):
        with pytest.raises(BusinessError):
            dsp.approve_exit_with_discrepancy(r, U(quien), "x")
    with pytest.raises(BusinessError):  # motivo obligatorio
        dsp.approve_exit_with_discrepancy(r, U("coord.logistica"), "")
    dsp.approve_exit_with_discrepancy(r, U("coord.logistica"), "Guía se corrige con nota en destino")
    assert alerts_of(s, "SALIDA_CON_DISCREPANCIA")
    dist.confirm_departure(r, U("lider.almacen"), CHECK)
    assert r.estado == "EN_RUTA" and r.checklist["salida_aprobada_por_logistica"]
    assert a.estado != "CERRADA"  # la guía sigue por resolver
    dsp.resolve_guide_discrepancy(r, U("coord.distribucion"), "Guía rectificada T001-10")
    s.commit()
    assert a.estado == "CERRADA" and r.aprobacion_discrepancia["resuelta"]


def test_q8_corregir_y_validar_de_nuevo_desbloquea(s, U, new_order):
    o = new_order([("PT-905", 30)])
    r = _ready_route(s, U, o, discrepancia=True)
    lines = [{**e, "guia": e["esperado"], "cargado": e["esperado"]} for e in dist.expected_lines(r)]
    assert dist.register_security_check(r, U("seguridad"), "T001-9", lines) == []
    s.commit()
    assert alerts_of(s, "GUIA_DISCREPANCIA")[0].estado == "CERRADA"
    dist.confirm_departure(r, U("lider.almacen"), CHECK)


def test_q2_otif_por_salida_y_fill_rate(s, U, new_order, today):
    o1 = new_order([("PT-905", 40)])
    dist.confirm_departure(_ready_route(s, U, o1), U("lider.almacen"), CHECK)
    o2 = new_order([("PT-901", 450)])  # salida parcial (400 de 450)
    osvc.decide_partial(o2, U("gerente.operaciones"), True, "ok", today + timedelta(days=4))
    dist.confirm_departure(_ready_route(s, U, o2), U("lider.almacen"), CHECK)
    from app.models import RouteStop
    st = s.query(RouteStop).filter_by(order_id=o1.id).one()
    dist.register_arrival(st, U("aux.despacho"))
    dist.register_incident(U("aux.despacho"), "RECHAZO_CALIDAD", "Humedad observada por el cliente", stop=st)
    s.commit()
    k = kpis.compute()
    assert k["otif_definicion"] == "SALIDA" and k["otif_salida"][1:] == (1, 2)
    assert k["fill_rate_unidades"] == pytest.approx(round(100 * 440 / 490, 1))
    assert k["fill_rate_pedidos"] == (50.0, 1, 2) and k["completos_con_rechazo"] == (1, 1)
    det = {d["numero"]: d for d in k["fill_detalle"]}
    assert det[o1.numero]["rechazo"] and "Humedad" in det[o1.numero]["motivos"][0]
    causas = {(e, m): n for e, m, n in k["fill_causas"]}
    assert causas[("Calidad", "Rechazo por calidad")] == 1
    assert causas[("Abastecimiento (stock, producción, compras)", "Salió incompleto (faltante)")] == 1


def test_q15_presolicitudes_en_orden_producir_reempaque_traslado_compra(s, U, new_order):
    # 1) producir: PT-901 tiene lista de materiales con materiales disponibles
    o = new_order([("PT-901", 450)])
    pr = s.query(ProductionRequest).filter_by(order_id=o.id).one()
    assert pr.cantidad == 50 and pr.estado == "BORRADOR" and pr.creado_por is None
    assert alerts_of(s, "PRESOLICITUD_AUTOMATICA", o.id)
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-901", "cantidad": 450}]})
    assert s.query(ProductionRequest).filter_by(order_id=o.id).count() == 1  # no duplica al reevaluar
    osvc.cancel_order(o, U("coord.ventas"), "prueba")
    # 2) reempaque cuando producir no es viable (sin materia prima); si no cubre todo, el saldo pasa a la siguiente opción
    s.query(StockLot).filter_by(product_code="MP-901").one().cantidad = 0
    o2 = new_order([("PT-901", 450)], ruc="20000000003")  # vida útil 180 d: L901B no apto → actualización de fecha
    assert s.query(ProductionRequest).filter_by(order_id=o2.id).count() == 0
    reps = s.query(RepackRequest).filter_by(order_id=o2.id).all()
    assert {r.estado for r in reps} == {"PRE_SOLICITUD"} and sum(r.cantidad_destino for r in reps) == pytest.approx(150)
    assert reps[0].tipo == "ACTUALIZACION_FECHA" and reps[0].lot.lote == "L901B"
    assert s.query(Transfer).filter_by(order_id=o2.id).count() == 0
    # 3) traslado: PT-903 sin materia prima suficiente ni reempaque, con stock en almacén externo
    o3 = new_order([("PT-903", 100)])
    t = s.query(Transfer).filter_by(order_id=o3.id).one()
    assert t.estado == "SOLICITADO" and t.cantidad == 100 and t.destino_code == "ALM-001" and t.solicitado_por is None
    assert {"JEFE_LOGISTICA", "COORD_LOGISTICA"} <= set(alerts_of(s, "TRASLADO_SOLICITADO")[-1].roles)
    trs.authorize(t, U("coord.logistica"), True)  # Q13
    # 4) compra: artículo sin lista de materiales
    o4 = new_order([("EN-903", 50)])
    c = s.query(PurchaseRequest).filter_by(order_id=o4.id).one()
    assert c.estado == "PENDIENTE_LOGISTICA" and c.cantidad == 40
    a = alerts_of(s, "PRESOLICITUD_AUTOMATICA", o4.id)[0]
    assert "COORD_ALMACEN_MP" in a.roles and "COORD_ALMACEN" not in a.roles  # Q17: insumos → almacén 1524
    buy.approve_logistics(c, U("jefe.logistica"), True)
    assert c.estado == "SOLICITADA"


def test_q12_reempaque_presolicitud_aprobada_por_coordinador(s, U, new_order):
    s.query(StockLot).filter_by(product_code="MP-901").one().cantidad = 0
    o = new_order([("PT-901", 400)], ruc="20000000003")
    r = s.query(RepackRequest).filter_by(order_id=o.id).first()
    lot = r.lot
    assert r.estado == "PRE_SOLICITUD" and not alerts_of(s, "REEMPAQUE_SOLICITUD")
    with pytest.raises(BusinessError):  # Calidad no evalúa una pre-solicitud
        rep.evaluate(r, U("jefe.calidad"), True, "ok")
    with pytest.raises(BusinessError):  # Q17: el lote está en 1560
        rep.approve_presolicitud(r, U("coord.almacen.mp"), True)
    with pytest.raises(BusinessError):
        rep.approve_presolicitud(r, U("jefe.logistica"), True)
    rep.approve_presolicitud(r, U("coord.almacen"), True, "Se envía a Calidad")
    s.commit()
    assert r.estado == "SOLICITADA" and alerts_of(s, "REEMPAQUE_SOLICITUD")
    assert lot.estado == "PENDIENTE_REVISION" or r.lot.estado == "PENDIENTE_REVISION"
    rep.evaluate(r, U("jefe.calidad"), True, "Muestreo conforme")
    assert r.estado == "APROBADA"


def test_q17_alertas_y_acciones_por_almacen(s, U, new_order):
    o = new_order([("PT-903", 100)])
    a = alerts_of(s, "OV_FALTANTE", o.id)[0]
    assert "COORD_ALMACEN" in a.roles and "COORD_ALMACEN_MP" not in a.roles
    l = s.query(StockLot).filter_by(product_code="EN-901").one()
    from app.services.stock import change_lot_state
    with pytest.raises(BusinessError):
        change_lot_state(l, "DANADO", U("coord.almacen"), "Bobina golpeada")
    change_lot_state(l, "DANADO", U("coord.almacen.mp"), "Bobina golpeada")
    a2 = alerts_of(s, "STOCK_NO_UTILIZABLE")
    assert not a2 or "COORD_ALMACEN" not in a2[-1].roles


def test_q5_transito_produccion_y_almacen_no_utilizado(s, U, tmp_path, today, new_order):
    w3, w10 = s.get(Warehouse, "ALM-003"), s.get(Warehouse, "ALM-010")
    assert w3.uso == "TRANSITO_PRODUCCION" and not w3.reservable
    assert w10.uso == "NO_UTILIZADO" and not w10.reservable
    from app.demo_data import write_stock
    p = os.path.join(tmp_path, "st.xlsx")
    write_stock(p, today, extra_rows=[("PT-905", "L905X", "ALM-010", 5, None, None, None),
                                      ("PT-903", "L903T", "ALM-003", 7, None, None, None)])
    b = up.create_batch(U("coord.almacen"), "STOCK", p, "st.xlsx")
    adv = [w for r in b.rows for w in r.advertencias]
    assert any("ALM-010" in w and "no utilizado" in w for w in adv)
    assert any("ALM-003" in w and "tránsito" in w for w in adv)
    up.confirm(b, U("coord.almacen"))
    s.commit()
    o = new_order([("PT-905", 1005)])
    assert all(r.lot.warehouse_code != "ALM-010" for r in o.lines[0].reservations)
