"""Casos de prueba del IF §21 (punto 8): pedido completo, faltante, cambio de OV, almacén alternativo,
vencimiento, reempaque, producción, compra, rechazo, devolución y cambio de fecha. Datos ficticios."""
from datetime import date, timedelta

import pytest

from app.models import Alert, Certificate, Liquidation, Reservation, RouteStop, StockLot
from app.services import distribution as dist
from app.services import imports as imp
from app.services import orders as osvc
from app.services import production as prod
from app.services import purchasing as buy
from app.services import quality as qual
from app.services import repack as rep
from app.services import transfers as trs
from app.services.core import BusinessError, set_param
from app.services.stock import alternatives_for_order, free_qty, line_reserved

from .conftest import alerts_of


def lot(s, prod_code, lote, wh=None, estado=None):
    q = s.query(StockLot).filter_by(product_code=prod_code, lote=lote)
    if wh:
        q = q.filter_by(warehouse_code=wh)
    if estado:
        q = q.filter_by(estado=estado)
    return q.one()


def approve_certs(s, U, o):
    for c in s.query(Certificate).filter_by(order_id=o.id, estado="BORRADOR"):
        cambios = {f"org_{i}_resultado": "CONFORME" for i in range(3)}
        cambios.update({"hum_resultado": "12%", "hum_conclusion": "CONFORME", "tamano_lote": "1000 kg",
                        "fecha_analisis": date.today().isoformat()})
        qual.review_certificate(c, U("superv.calidad"), cambios, aprobar=True)


def dispatch(s, U, o, today):
    """Secuencia TO-BE: plan de picking → picking → ruta aprobada → fotos y validación de carga → guía y factura →
    certificados aprobados → Seguridad (carga vs guía, documentos) → salida."""
    from app.services import despacho as dsp
    osvc.validate_picking_plan(o, U("lider.almacen"))
    for l in o.lines:
        for r in [r for r in l.reservations if r.estado == "ACTIVA"]:
            osvc.register_picking(o, U("lider.almacen"), l.id, r.cantidad, r.lot.lote)
    s.commit()
    assert o.estado == "PREPARADA"
    r = dist.active_stop(o).route  # programada automáticamente al quedar la OV completa (TO-BE)
    dist.confirm_route(r, U("coord.distribucion"))
    dsp.add_photo(r, U("aux.despacho"), "vehiculo", "veh.jpg")
    dsp.add_photo(r, U("seguridad"), "inicio_carga", "ini.jpg")
    lines = [{**e, "guia": e["esperado"], "cargado": e["esperado"], "presentacion_ok": True} for e in dist.expected_lines(r)]
    assert dist.register_security_check(r, U("seguridad"), "T001-DEMO", lines) == []
    dsp.add_photo(r, U("aux.despacho"), "mercaderia_cargada", "carga.jpg")
    assert dsp.validate_load(r, U("aux.despacho"), {}) == []
    for st in r.stops:
        dsp.set_guide(st, U("coord.distribucion"), "", "SISTEMA")
        dsp.set_invoice(st, U("facturacion"), f"F001-{st.order.numero}", "fact.pdf")
        approve_certs(s, U, st.order)
    assert dsp.review_documents(r, U("seguridad"), impresos=True) == []
    dist.confirm_departure(r, U("lider.almacen"), {k: True for k, _ in dist.CHECKLIST})
    s.commit()
    return r.stops[0]


# 1. Pedido completo ---------------------------------------------------------
def test_pedido_completo_flujo_hasta_entrega(s, U, new_order, today):
    l905 = lot(s, "PT-905", "L905A")
    libre0 = free_qty(l905)
    o = new_order([("PT-905", 100)])
    assert o.estado_stock == "COMPLETA" and o.cobertura_unidades == 100 and o.cobertura_lineas == 100
    assert free_qty(l905) == libre0 - 100
    assert not alerts_of(s, "OV_FALTANTE", o.id)
    stop = dispatch(s, U, o, today)
    assert alerts_of(s, "OV_PREPARADA", o.id)
    assert s.query(Certificate).filter_by(order_id=o.id).count() == 1  # certificado autogenerado
    assert o.estado == "DESPACHADA" and l905.cantidad == 900
    # entrega exige foto y guía firmada
    with pytest.raises(BusinessError):
        dist.register_delivery(stop, U("aux.despacho"), "", "guia.jpg")
    dist.register_delivery(stop, U("aux.despacho"), "foto.jpg", "guia.jpg")
    s.commit()
    assert o.estado == "ENTREGADA" and stop.route.estado == "CERRADA"
    from app.services.kpis import compute
    k = compute()
    assert k["otif_salida"][0] == 100.0 and k["otif_entrega"][0] == 100.0


# 2. Faltante ---------------------------------------------------------------
def test_faltante_cobertura_alertas_y_alternativas(s, U, new_order):
    o = new_order([("PT-901", 450), ("PT-905", 10)])
    # FEFO: primero L901B (vence antes) y luego L901A
    l1 = o.lines[0]
    assert line_reserved(l1) == 400
    assert [r.lot.lote for r in l1.reservations] == ["L901B", "L901A"]
    assert o.estado_stock == "INCOMPLETA"
    assert o.cobertura_unidades == pytest.approx(round(100 * 410 / 460, 2))
    assert o.cobertura_lineas == 50.0
    a = alerts_of(s, "OV_FALTANTE", o.id)[0]
    assert {"COORD_ALMACEN", "JEFE_LOGISTICA", "GERENCIA_OPERACIONES"} <= set(a.roles)
    d = alerts_of(s, "OV_DECISION_PARCIAL", o.id)[0]
    assert {"JEFE_LOGISTICA", "GERENCIA_OPERACIONES", "JEFE_VENTAS", "COORD_VENTAS"} <= set(d.roles)
    alts = alternatives_for_order(o)
    assert len(alts) == 1
    otros = alts[0]["otros_almacenes"]
    assert any(x["lot"].warehouse_code == "EXT-005" and x["apto"] and x["libre"] == 80 for x in otros)
    assert alts[0]["produccion"] is not None  # PT-901 tiene BOM
    # no se ejecutó ningún traslado automáticamente
    from app.models import Transfer
    assert s.query(Transfer).count() == 0


def test_despacho_parcial_aprobacion_y_saldo(s, U, new_order, today):
    """Q3 (12-oct-2026): aprueba Gerencia de Operaciones o Jefatura de Logística; el saldo se reprograma."""
    o = new_order([("PT-901", 450)])
    assert dist.active_stop(o) is None  # incompleta: aún no se programa ruta
    for quien in ("vendedor1", "coord.ventas", "jefe.ventas", "sistemas", "coord.logistica"):
        with pytest.raises(BusinessError):
            osvc.decide_partial(o, U(quien), True, fecha_saldo=today + timedelta(days=7))
    with pytest.raises(BusinessError):  # fecha del saldo obligatoria
        osvc.decide_partial(o, U("jefe.logistica"), True)
    rutas = osvc.decide_partial(o, U("jefe.logistica"), True, "ok logística", today + timedelta(days=7))
    s.commit()
    assert o.decision_parcial == "APROBADA" and list(o.parcial_aprobaciones) == ["JEFE_LOGISTICA"]
    assert alerts_of(s, "OV_PARCIAL_APROBADO", o.id)
    with pytest.raises(BusinessError):  # ya aprobado
        osvc.decide_partial(o, U("gerente.operaciones"), True)
    assert rutas and rutas[0].stops[0].order_id == o.id and rutas[0].stops[0].peso_kg == pytest.approx(400 * 0.5)
    # despacho del parcial -> OV de saldo con la fecha reprogramada
    dispatch(s, U, o, today)
    from app.models import SalesOrder
    saldo = s.query(SalesOrder).filter_by(parent_id=o.id).one()
    assert saldo.numero == f"{o.numero}-S1" and saldo.fecha_compromiso == today + timedelta(days=7)
    assert saldo.lines[0].product_code == "PT-901" and saldo.lines[0].cantidad == 50
    assert saldo.estado_stock in ("COMPLETA", "INCOMPLETA", "SIN_STOCK") and alerts_of(s, "OV_SALDO_REPROGRAMADO", saldo.id)


def test_gerencia_general_aprueba_en_nombre_y_rechazo(s, U, new_order, today):
    """Q4: Gerencia General puede aprobar en nombre de los roles pendientes; cualquiera de ellos puede rechazar."""
    o = new_order([("PT-901", 450)])
    osvc.decide_partial(o, U("gerente.general"), True, "aprueba GG", today + timedelta(days=5))
    s.commit()
    assert o.decision_parcial == "APROBADA" and all(v["rol_usuario"] == "GERENCIA_GENERAL" for v in o.parcial_aprobaciones.values())
    o2 = new_order([("PT-901", 450)])
    with pytest.raises(BusinessError):
        osvc.decide_partial(o2, U("gerente.operaciones"), False, "")
    # configurable: con parcial_modo = TODOS se exige la aprobación de ambos roles
    set_param("parcial_modo", "TODOS", U("sistemas"))
    for x in (o, o2):
        osvc.cancel_order(x, U("coord.ventas"), "libera stock para la prueba")
    o3 = new_order([("PT-901", 450)])
    osvc.decide_partial(o3, U("gerente.operaciones"), True, "ok", today + timedelta(days=5))
    assert o3.decision_parcial == "PENDIENTE" and osvc.partial_pending_roles(o3) == ["JEFE_LOGISTICA"]
    osvc.decide_partial(o3, U("jefe.logistica"), True, "ok")
    assert o3.decision_parcial == "APROBADA"
    osvc.decide_partial(o2, U("gerente.operaciones"), False, "Cliente no acepta parcial")
    assert o2.decision_parcial == "RECHAZADA"


# 3. Vencimiento y condición del cliente --------------------------------------
def test_vencimiento_y_vida_util_cliente(s, U, new_order):
    o = new_order([("PT-904", 70)])
    assert line_reserved(o.lines[0]) == 50  # L904V vencido no se reserva
    assert all(r.lot.lote != "L904V" for r in o.lines[0].reservations)
    o2 = new_order([("PT-901", 50)], ruc="20000000002")  # cliente con vida útil mínima 120 días
    assert [r.lot.lote for r in o2.lines[0].reservations] == ["L901A"]
    o3 = new_order([("PT-901", 400)], ruc="20000000002")
    alts = alternatives_for_order(o3)
    assert any(x["tipo"] == "ACTUALIZACION_FECHA" and x["lot"].lote == "L901B" for x in alts[0]["reempaque"])


# 4. Cambio de OV --------------------------------------------------------------
def test_cambio_ov_conserva_reservas_y_alerta(s, U, new_order):
    o = new_order([("PT-905", 100)])
    res0 = o.lines[0].reservations[0]
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 150},
                                                       {"product_code": "PT-902", "cantidad": 5}]})
    s.commit()
    assert res0.estado == "ACTIVA" and line_reserved(o.lines[0]) == 150
    assert o.version == 2 and o.estado_stock == "COMPLETA"
    a = alerts_of(s, "OV_CAMBIO", o.id)
    assert a and {"JEFE_LOGISTICA", "COORD_ALMACEN", "GERENCIA_OPERACIONES"} <= set(a[0].roles)
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 40}]})
    s.commit()
    assert line_reserved(o.lines[0]) == 40
    assert line_reserved(o.lines[1]) == 0 and not o.lines[1].activa


def test_asistente_modifica_solo_con_autorizacion(s, U, new_order):
    o = new_order([("PT-905", 10)], vendedor="vendedor1")
    with pytest.raises(BusinessError):
        osvc.modify_order(o, U("asist.ventas"), {"urgente": True})
    req = osvc.request_change(o, U("asist.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 20}]}, "Cliente amplía")
    s.commit()
    assert alerts_of(s, "OV_MODIF_SOLICITUD")
    with pytest.raises(BusinessError):  # vendedor no responsable
        osvc.resolve_change(req, U("vendedor2"), True)
    osvc.resolve_change(req, U("vendedor1"), True)  # vendedor responsable autoriza
    s.commit()
    assert req.estado == "APROBADA" and o.lines[0].cantidad == 20 and line_reserved(o.lines[0]) == 20


def test_cancelacion_libera_reserva_y_ruta(s, U, new_order):
    o = new_order([("PT-905", 100)])
    l905 = o.lines[0].reservations[0].lot
    libre = free_qty(l905)
    s.commit()  # la ruta se programó automáticamente (TO-BE)
    assert s.query(RouteStop).filter_by(order_id=o.id).count() == 1
    with pytest.raises(BusinessError):
        osvc.cancel_order(o, U("asist.ventas"), "x")
    osvc.cancel_order(o, U("jefe.ventas"), "Cliente desistió")
    s.commit()
    assert o.estado == "CANCELADA" and free_qty(l905) == libre + 100
    assert s.query(RouteStop).filter_by(order_id=o.id).count() == 0
    assert alerts_of(s, "OV_CANCELADA", o.id)


# 5. Almacén alternativo -------------------------------------------------------
def test_almacen_alternativo_traslado_autorizado(s, U, new_order):
    o = new_order([("PT-903", 100)])
    assert o.estado_stock == "SIN_STOCK"
    alt = alternatives_for_order(o)[0]["otros_almacenes"][0]
    assert alt["lot"].warehouse_code == "EXT-001"
    t = trs.request_transfer(U("coord.logistica"), alt["lot"].id, "ALM-001", 100, o, "Para OV")
    s.commit()
    assert t.estado == "SOLICITADO" and alerts_of(s, "TRASLADO_SOLICITADO")
    for quien in ("coord.almacen", "sistemas"):
        with pytest.raises(BusinessError):
            trs.authorize(t, U(quien), True)
    trs.authorize(t, U("coord.logistica"), True)  # Q13: Jefe o Coordinador de Logística
    trs.ship(t, U("coord.almacen"))
    trs.receive(t, U("aux.almacen"), 100)
    s.commit()
    assert t.estado == "RECIBIDO"
    assert o.estado_stock == "COMPLETA" and line_reserved(o.lines[0]) == 100
    assert lot(s, "PT-903", "L903A", "ALM-001").cantidad == 100


def test_traslado_con_diferencia(s, U):
    l = lot(s, "PT-903", "L903A", "EXT-001")
    t = trs.request_transfer(U("jefe.logistica"), l.id, "ALM-001", 50)
    trs.authorize(t, U("jefe.logistica"), True)
    trs.ship(t, U("coord.almacen"))
    trs.receive(t, U("coord.almacen"), 45, "faltan 5")
    s.commit()
    assert t.estado == "RECIBIDO_CON_DIFERENCIA" and t.diferencia == 5
    assert alerts_of(s, "TRASLADO_DIFERENCIA")


# 6. Reempaque --------------------------------------------------------------
def test_reempaque_flujo_completo(s, U, new_order):
    o = new_order([("PT-902", 50)])  # solo hay 40
    assert o.estado_stock == "INCOMPLETA"
    alts = alternatives_for_order(o)[0]["reempaque"]
    assert {x["lot"].product_code for x in alts} >= {"PT-901", "PT-906"}
    l906 = lot(s, "PT-906", "L906A")
    with pytest.raises(BusinessError):
        rep.request(U("jefe.calidad"), "CONVERSION_CALIDAD", l906.id, 20, "PT-902", order=o)
    r = rep.request(U("coord.almacen"), "CONVERSION_CALIDAD", l906.id, 20, "PT-902", order=o, motivo="faltante")
    s.commit()
    assert free_qty(l906) == 100  # 20 retenidos
    assert alerts_of(s, "REEMPAQUE_SOLICITUD")
    with pytest.raises(BusinessError):
        rep.evaluate(r, U("coord.almacen"), True, "ok")
    rep.evaluate(r, U("jefe.calidad"), True, "Muestreo conforme")
    s.commit()
    a = alerts_of(s, "REEMPAQUE_APROBADO")[0]
    assert {"COORD_ALMACEN", "JEFE_PRODUCCION"} <= set(a.roles)
    rep.start(r, U("jefe.produccion"))
    nuevo = rep.finish(r, U("jefe.produccion"), "RP902", 2, date.today(), date.today() + timedelta(days=365))
    s.commit()
    assert nuevo.estado == "PENDIENTE_REVISION" and l906.cantidad == 100
    qual.release_lot(nuevo, U("superv.calidad"), True, "Liberado")
    s.commit()
    assert line_reserved(o.lines[0]) == 42  # reevaluación automática al liberar


# 7. Producción ---------------------------------------------------------------
def test_produccion_bom_merma_y_liquidacion(s, U):
    set_param("merma_pct_global", 2.0, U("sistemas"))
    req = prod.material_requirements("PT-903", 100)
    mp = next(m for m in req["materiales"] if m["componente"] == "MP-902")
    assert mp["requerido_base"] == pytest.approx(50) and mp["requerido"] == pytest.approx(51)
    assert mp["faltante"] == pytest.approx(21)
    assert any(x["componente"] == "RE-901" for x in req["recursos"])
    assert not req["factible"]
    r = prod.create_request("PT-903", 300, U("coord.almacen"))
    prod.send_request(r, U("coord.almacen"))
    s.commit()
    assert alerts_of(s, "PRODUCCION_SOLICITUD")
    with pytest.raises(BusinessError):
        prod.validate_request(r, U("jefe.produccion"), True, True, False, True, True)
    prod.validate_request(r, U("jefe.produccion"), True, True, True, True, True, "ok")
    from app.models import ProductionLine
    ln = s.get(ProductionLine, "R1")
    ln.capacidad_kg_dia = 100
    with pytest.raises(BusinessError):  # 300 × 0.5 kg = 150 kg > 100
        prod.schedule(r, U("jefe.produccion"), "R1", date.today())
    ln.capacidad_kg_dia = 1000
    prod.schedule(r, U("jefe.produccion"), "R1", date.today())
    prod.start(r, U("asist.produccion"))
    prod.finish(r, U("asist.produccion"))
    liq = prod.register_liquidation(U("asist.produccion"), "LQ-T1", "PT-903", 300, "L903P", request=r, merma_mp_kg=3)
    s.commit()
    transito = lot(s, "PT-903", "L903P", "ALM-003")  # Q5: el PT queda en el tránsito de Producción
    assert transito.cantidad == 300 and transito.warehouse.reservable is False
    assert r.estado == "LIQUIDADA" and alerts_of(s, "LIQUIDACION_MONTACARGUISTA")[0].roles[0] == "MONTACARGUISTA"
    with pytest.raises(BusinessError):
        prod.register_liquidation(U("asist.produccion"), "LQ-T1", "PT-903", 1, "L903P")
    prod.receive_pt(liq, U("coord.almacen"), 298)
    s.commit()
    assert liq.estado == "RECIBIDA_FALTANTE" and liq.diferencia == 2
    assert alerts_of(s, "LIQUIDACION_DIFERENCIA")
    assert lot(s, "PT-903", "L903P", "ALM-001").estado == "PENDIENTE_REVISION"
    assert lot(s, "PT-903", "L903P", "ALM-003").cantidad == 0  # Q5: sale del tránsito de Producción
    assert prod.merma_real_pct(liq) == pytest.approx(100 * 3 / 153, rel=1e-3)


def test_merma_no_se_duplica_si_no_verificado(s, U):
    set_param("merma_pct_global", 5.0, U("sistemas"))
    v = prod.active_bom()
    v.incluye_merma = "NO_VERIFICADO"
    req = prod.material_requirements("PT-901", 100)
    mp = next(m for m in req["materiales"] if m["componente"] == "MP-901")
    assert mp["requerido"] == pytest.approx(50)
    assert any("NO aplicada" in a for a in req["avisos"])
    v.incluye_merma = "SI"
    assert next(m for m in prod.material_requirements("PT-901", 100)["materiales"] if m["componente"] == "MP-901")["requerido"] == pytest.approx(50)
    v.incluye_merma = "NO"
    assert next(m for m in prod.material_requirements("PT-901", 100)["materiales"] if m["componente"] == "MP-901")["requerido"] == pytest.approx(52.5)


# 8. Compra -------------------------------------------------------------------
def test_compra_nacional_flujo(s, U):
    with pytest.raises(BusinessError):  # nace en Almacén
        buy.create_request(U("compras"), "EN-901", 500)
    set_param("umbral_mayor_volumen", 100.0, U("sistemas"))
    r = buy.create_request(U("coord.almacen.mp"), "EN-901", 500, date.today() + timedelta(days=20))
    s.commit()
    assert r.estado == "PENDIENTE_LOGISTICA" and r.mayor_volumen and not alerts_of(s, "COMPRA_SOLICITUD")
    with pytest.raises(BusinessError):  # Q14: aprueba el Jefe de Logística
        buy.quote(r, U("compras"), "Proveedor Demo", "cotización", 10.5)
    buy.approve_logistics(r, U("jefe.logistica"), True, "ok")
    assert r.estado == "SOLICITADA" and alerts_of(s, "COMPRA_SOLICITUD")
    buy.quote(r, U("compras"), "Proveedor Demo", "cotización", 10.5, requiere_muestra=True)
    assert alerts_of(s, "COMPRA_MUESTRA")
    with pytest.raises(BusinessError):
        buy.generate_order(r, U("compras"), "OC-1", date.today() + timedelta(days=10), "EXT-002")
    buy.evaluate_sample(r, U("jefe.calidad"), True, "conforme")
    with pytest.raises(BusinessError):  # requiere aprobación de GO
        buy.generate_order(r, U("compras"), "OC-1", date.today() + timedelta(days=10), "EXT-002")
    buy.request_go_approval(r, U("compras"))
    with pytest.raises(BusinessError):
        buy.approve_go(r, U("compras"), True)
    buy.approve_go(r, U("gerente.operaciones"), True)
    buy.generate_order(r, U("compras"), "OC-1", date.today() + timedelta(days=10), "EXT-002")
    s.commit()
    assert alerts_of(s, "COMPRA_RECEPCION_PROGRAMAR")[0].roles == ["COORD_ALMACEN_MP"]  # Q17: almacén 1524
    buy.change_date(r, U("compras"), date.today() + timedelta(days=15), "Proveedor reprograma")
    s.commit()
    a = alerts_of(s, "COMPRA_FECHA_CAMBIO")[0]
    assert set(a.roles) == {"COORD_ALMACEN_MP", "GERENCIA_OPERACIONES"}
    with pytest.raises(BusinessError):  # Q17: el coordinador 1560 no recibe en 1524
        buy.receive(r, U("coord.almacen"), 480, "E901N")
    buy.receive(r, U("coord.almacen.mp"), 480, "E901N")
    s.commit()
    assert r.estado == "RECIBIDA_CON_DIFERENCIAS" and alerts_of(s, "COMPRA_DIFERENCIA")
    assert lot(s, "EN-901", "E901N").estado == "PENDIENTE_REVISION"
    with pytest.raises(BusinessError):
        buy.authorize_under_observation(r, U("coord.almacen.mp"), "urgencia")
    buy.authorize_under_observation(r, U("gerente.operaciones"), "Urgencia de producción")
    assert r.estado == "RECIBIDA_BAJO_OBSERVACION"


# 9-10. Rechazo y devolución ----------------------------------------------------
def test_rechazo_por_calidad_alerta_gerencia_general(s, U, new_order, today):
    o = new_order([("PT-905", 40)])
    stop = dispatch(s, U, o, today)
    with pytest.raises(BusinessError):
        dist.register_incident(U("vendedor1"), "RECHAZO_CALIDAD", "x", stop=stop)
    dist.register_incident(U("aux.despacho"), "RECHAZO_CALIDAD", "Cliente rechaza por grano partido", stop=stop)
    s.commit()
    a = alerts_of(s, "INC_RECHAZO_CALIDAD")[0]
    assert {"GERENCIA_GENERAL", "GERENCIA_OPERACIONES", "JEFE_LOGISTICA", "COORD_ALMACEN", "JEFE_VENTAS"} <= set(a.roles)
    assert o.estado == "RECHAZADA" and stop.estado == "RECHAZADO"
    ret = s.query(StockLot).filter_by(product_code="PT-905", estado="PENDIENTE_REVISION").one()
    assert ret.cantidad == 40
    # Gerencia General recibe este tipo por correo directo (preferencia por defecto)
    from app.models import EmailOutbox
    assert s.query(EmailOutbox).filter(EmailOutbox.alert_id == a.id,
                                       EmailOutbox.destinatario == "gerente.general@demo.local").count() == 1


def test_devolucion_y_entrega_parcial(s, U, new_order, today):
    o = new_order([("PT-905", 30)])
    stop = dispatch(s, U, o, today)
    dist.register_incident(U("aux.despacho"), "DEVOLUCION", "Devuelve todo", stop=stop)
    s.commit()
    a = alerts_of(s, "INC_GENERAL")[0]
    assert "GERENCIA_GENERAL" not in a.roles and "GERENCIA_OPERACIONES" in a.roles
    assert o.estado == "DEVUELTA"
    o2 = new_order([("PT-905", 20)])
    stop2 = dispatch(s, U, o2, today)
    dist.register_delivery(stop2, U("aux.despacho"), "f.jpg", "g.jpg", {str(o2.lines[0].id): 15})
    s.commit()
    assert o2.estado == "ENTREGA_PARCIAL"
    from app.models import Incident
    assert s.query(Incident).filter_by(tipo="ENTREGA_PARCIAL", order_id=o2.id).count() == 1


# 11. Cambio de fecha (importación) ----------------------------------------------
def test_importacion_fases_y_cambio_fecha(s, U, today):
    with pytest.raises(BusinessError):
        imp.create_shipment(U("compras"), "IMP-1", "Prov", "MP-902", 1000, today)
    sh = imp.create_shipment(U("importaciones"), "IMP-1", "Proveedor Exterior Demo", "MP-902", 1000, today - timedelta(days=30),
                             warehouse_code="EXT-002")
    s.commit()
    assert len(sh.phases) == 4 and alerts_of(s, "IMPORT_LLEGADA")
    imp.change_arrival(sh, U("importaciones"), today + timedelta(days=5), "Retraso naviera")
    s.commit()
    a = alerts_of(s, "IMPORT_MODIFICACION")[0]
    assert {"GERENCIA_OPERACIONES", "COORD_ALMACEN_MP", "JEFE_LOGISTICA"} <= set(a.roles) and "COORD_ALMACEN" not in a.roles
    n = imp.check_phases(today)
    s.commit()
    vencidas = alerts_of(s, "IMPORT_FASE_VENCIDA")
    assert n >= 1 and vencidas and vencidas[0].estado == "NUEVA"
    assert imp.check_phases(today) >= 1 and len(alerts_of(s, "IMPORT_FASE_VENCIDA")) == len(vencidas)  # sin duplicar
    imp.complete_phase(sh.phases[0], U("importaciones"))
    s.commit()
    assert s.query(Alert).filter_by(dedup_key=f"IMPORT_FASE:{sh.phases[0].id}").one().estado == "CERRADA"
    imp.receive(sh, U("coord.almacen.mp"), 990, "M902I", "EXT-002", diferencias="10 kg faltantes")
    s.commit()
    assert sh.estado == "RECIBIDA_CON_DIFERENCIAS" and alerts_of(s, "IMPORT_DIFERENCIA")


def test_renegociar_fecha_ov(s, U, new_order, today):
    o = new_order([("PT-901", 50)], ruc="20000000003")  # vida útil 180: L901B no sirve
    assert [r.lot.lote for r in o.lines[0].reservations] == ["L901A"]
    osvc.renegotiate_date(o, U("jefe.ventas"), today + timedelta(days=10), "Cliente acepta")
    s.commit()
    assert o.fecha_compromiso == today + timedelta(days=10)
    from app.models import OVDecision
    assert s.query(OVDecision).filter_by(order_id=o.id, tipo="RENEGOCIAR_FECHA").count() == 1
