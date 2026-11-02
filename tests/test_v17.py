"""V17 (02-nov-2026): observaciones al módulo."""
from datetime import date, timedelta

import pytest

from app.models import Alert, PhysicalCount, StockLot
from app.services import alerts
from app.services.core import BusinessError, has_perm, param

from .conftest import alerts_of
from .test_web import login


def _get(app, user, path):
    c = app.test_client()
    login(c, user)
    return c.get(path)


# ------------------------------------------------------------------ numeración automática
def test_numeracion_automatica_de_ov_oc_y_guia(s, U, cust, today):
    from app.services import despacho as dsp
    from app.services import numeracion as num
    from app.services.orders import create_order
    o1 = create_order(U("coord.ventas"), None, cust("20000000001").id, today + timedelta(days=3),
                      [{"product_code": "PT-901", "cantidad": 1, "precio_unitario": 999}], oc_archivo="oc.pdf")
    o2 = create_order(U("coord.ventas"), "", cust("20000000001").id, today + timedelta(days=3),
                      [{"product_code": "PT-901", "cantidad": 1, "precio_unitario": 999}], oc_archivo="oc.pdf")
    assert o1.numero == "OV-000001" and o2.numero == "OV-000002" and num.next_order_number() == "OV-000003"
    assert num.next_purchase_order_number() == "OC-000001" and num.next_contingency_guide_number() == "GS-000001"


def test_orden_de_compra_y_guia_sin_numero_manual(s, U, today, monkeypatch):
    from app.services import purchasing as buy
    monkeypatch.setattr(buy, "needs_go_approval", lambda r: False)
    r = buy.create_request(U("coord.almacen.mp"), "EN-901", 5)
    r.estado = "EN_COTIZACION"
    buy.generate_order(r, U("compras"), "", today + timedelta(days=5), "EXT-002")
    assert r.numero_oc == "OC-000001"


def test_guia_de_sap_toma_el_numero_de_la_pre_guia(s, U, new_order):
    from app.models import Route, RouteStop
    from app.services import despacho as dsp
    o = new_order([("PT-901", 5)])
    o.preguia = {"sap": {"docnum": "99001", "estado": "ENVIADA"}}
    r = Route(fecha=date.today(), estado="CONFIRMADA")
    s.add(r)
    s.flush()
    st = RouteStop(route_id=r.id, order_id=o.id, orden=1)
    s.add(st)
    s.flush()
    dsp.set_guide(st, U("coord.distribucion"), "", "SAP", "guia.pdf")
    assert st.guia_numero == "99001"
    o.preguia = {}
    st.guia_numero = ""
    with pytest.raises(BusinessError, match="aún no tiene número"):
        dsp.set_guide(st, U("coord.distribucion"), "", "SAP", "guia.pdf")
    dsp.set_guide(st, U("coord.distribucion"), "", "SISTEMA", motivo="SAP no disponible")
    assert st.guia_numero.startswith("GS-")


def test_formularios_sin_numero_manual(app):
    for path in ("/ov/nueva", "/ov/regularizacion"):
        html = _get(app, "coord.ventas", path).get_data(as_text=True)
        assert 'name="numero"' not in html and "Lo asigna el sistema" in html


# ------------------------------------------------------------------ perfiles y permisos
def test_jefatura_de_operaciones_y_despacho_parcial(s, U, new_order):
    from app.services import orders as osvc
    jop = U("jefe.operaciones")
    assert jop.role_code == "JEFE_OPERACIONES"
    assert has_perm(jop, "ov.aprobar_parcial") and has_perm(jop, "asistencia.todas") and has_perm(jop, "indicadores.servicio")
    from app.services.inventory import can_validate
    assert not can_validate(jop) and can_validate(U("jefe.logistica"))
    assert param("parcial_aprobadores") == ["JEFE_LOGISTICA", "JEFE_OPERACIONES"]
    o = new_order([("PT-901", 450)])
    assert o.estado_stock != "COMPLETA" and o.cobertura_unidades > 0
    osvc.decide_partial(o, jop, True, "ok", date.today() + timedelta(days=5))
    assert o.decision_parcial == "APROBADA"
    a = alerts_of(s, "OV_PARCIAL_APROBADO", o.id)[0]
    assert {"COORD_VENTAS", "JEFE_VENTAS"} <= set(a.roles) and o.vendedor_id in a.usuarios


def test_revision_de_formatos_solo_calidad(app, s, U):
    assert has_perm(U("jefe.calidad"), "calidad.formatos_revisar")
    assert not has_perm(U("jefe.logistica"), "calidad.formatos_revisar")
    assert _get(app, "jefe.logistica", "/calidad/reporte").status_code == 403
    assert "Revisión de formatos" not in _get(app, "jefe.logistica", "/calidad/").get_data(as_text=True)
    assert "Revisión de formatos" in _get(app, "jefe.calidad", "/calidad/").get_data(as_text=True)


def test_asistencia_por_area(s, U):
    from app.models import Worker
    from app.services import attendance as asvc
    s.add_all([Worker(nombre="Colaborador Prod Demo", area="Producción", linea="R1"),
               Worker(nombre="Colaborador Almacén Demo", area="Almacén"),
               Worker(nombre="Colaborador Logística Demo", area="Logística")])
    s.flush()
    ver = lambda u: {w.area for w in asvc.workers_of(U(u), ver=True)}
    assert "Producción" not in ver("coord.almacen") and "Almacén" in ver("coord.almacen")
    assert {"Logística", "Almacén"} <= ver("jefe.logistica") and "Producción" not in ver("jefe.logistica")
    assert {"Producción", "Almacén", "Logística"} <= ver("jefe.operaciones")


def test_coordinador_de_logistica_hace_lo_de_los_supervisores(s, U):
    from app.services.core import check_warehouse_scope
    cl = U("coord.logistica")
    for p in ("stock.conteo", "picking.asignar", "reempaque.solicitar"):
        assert has_perm(cl, p), p
    check_warehouse_scope(cl, "ALM-001")
    check_warehouse_scope(cl, "EXT-002")
    check_warehouse_scope(cl, "EXT-014")
    with pytest.raises(BusinessError, match="Producción"):
        check_warehouse_scope(cl, "ALM-003")
    assert has_perm(U("superv.almacen"), "picking.asignar")


def test_picking_con_varias_personas_y_quien_reporta(s, U, new_order):
    from app.services import picking as pk
    o = new_order([("PT-905", 10)])
    t = pk.tasks_of(o)[0]
    gente = [u.id for u in pk.staff(t.warehouse_code)][:3]
    assert len(gente) >= 2
    pk.assign(t, U("superv.almacen"), gente, reportantes=[gente[0]])
    assert t.asignados == sorted(gente) and t.reportantes == [gente[0]]
    from app.models import User
    otro = s.get(User, gente[1])
    assert not pk._es_asignado(t, otro) and pk._es_asignado(t, s.get(User, gente[0]))


def test_programacion_semanal_con_rango(app):
    html = _get(app, "lider.almacen", f"/almacen/picking?vista=semana&desde={date.today().isoformat()}"
                                      f"&hasta={(date.today() + timedelta(days=10)).isoformat()}").get_data(as_text=True)
    assert "Desde (semanal)" in html and (date.today() + timedelta(days=10)).strftime("%d/%m/%Y") in html


def test_solicitud_a_produccion_valida_la_ov(s, U, new_order):
    from app.services import production as psvc
    o = new_order([("PT-901", 5)])
    with pytest.raises(BusinessError, match="no está en la OV"):
        psvc.create_request("PT-902", 10, U("coord.almacen"), o, validar_ov=True)
    r = psvc.create_request("PT-901", 10, U("coord.almacen"), o, validar_ov=True)
    assert r.customer_id == o.customer_id


# ------------------------------------------------------------------ almacén y logística
def test_conteo_producto_por_producto_validado_por_el_jefe_de_logistica(s, U):
    from app.services import inventory as inv
    c = inv.open_count(U("coord.almacen"), "ALM-001", por_producto=True)
    assert c.lines == []
    lot = s.query(StockLot).filter(StockLot.warehouse_code == "ALM-001", StockLot.cantidad > 0).first()
    assert inv.add_products(c, U("coord.almacen"), [lot.product_code]) >= 1
    line = next(l for l in c.lines if l.lot_id == lot.id)
    lot.fecha_verificacion = antes = None
    inv.save_lines(c, U("coord.almacen"), {str(l.id): {"conteo": str(l.sap)} for l in c.lines})
    inv.save_lines(c, U("coord.almacen"), {str(line.id): {"conteo": str(lot.cantidad)}})
    inv.close_count(c, U("coord.almacen"))
    assert c.estado == "POR_VALIDAR" and lot.fecha_verificacion == antes and alerts_of(s, "CONTEO_POR_VALIDAR", c.id)
    with pytest.raises(BusinessError):
        inv.validate_count(c, U("coord.almacen"), True)
    inv.validate_count(c, U("jefe.logistica"), False, "recontar el rack 3")
    assert c.estado == "ABIERTO"
    inv.close_count(c, U("coord.almacen"))
    inv.validate_count(c, U("jefe.logistica"), True)
    assert c.estado == "CERRADO" and lot.verificado and lot.fecha_verificacion is not None and c.validacion["estado"] == "VALIDADO"


def test_traslado_autorizado_llega_a_distribucion_y_zonas_de_movimiento(s, U):
    from app.services import supply
    assert "COORD_DISTRIBUCION" in s.get(__import__("app.models", fromlist=["x"]).AlertType, "TRASLADO_AUTORIZADO").roles
    pts = supply.move_points("")
    assert {"Zona manual", "Almacén 1524", "Almacén 1560"} <= set(pts)
    assert supply.zone_from_form({"origen_zona": "__OTRA__", "origen_otra": "Patio norte", "origen_subzona": "A-2"}, "origen") \
        == "Patio norte · subzona A-2"
    with pytest.raises(BusinessError):
        supply.zone_from_form({"origen_zona": "__OTRA__"}, "origen")


def test_cumplimiento_del_cliente_en_la_ov(app, s, U, new_order):
    o = new_order([("PT-905", 5)])
    html = _get(app, "jefe.logistica", f"/ov/{o.id}").get_data(as_text=True)
    assert "Cumplimiento con" in html


# ------------------------------------------------------------------ comercial
def test_inicio_del_ejecutivo_y_aviso_de_retraso(app, s, U, new_order, today):
    from app.services import seguimiento as seg
    o = new_order([("PT-905", 5)], vendedor="vendedor1")
    o.fecha_compromiso = today - timedelta(days=2)
    s.commit()
    filas = seg.seller_orders(U("vendedor1"))
    x = next(f for f in filas if f["o"].id == o.id)
    assert "Atrasada" in x["retraso"] and x["area"]
    assert seg.check_seller_delays() >= 1
    a = s.query(Alert).filter_by(type_code="OV_RETRASO_EJECUTIVO", entidad_id=str(o.id)).one()
    assert U("vendedor1").id in a.usuarios
    html = _get(app, "vendedor1", "/").get_data(as_text=True)
    assert "Mis pedidos" in html and o.numero in html


def test_expediente_agrupado_por_cliente_y_despacho(app, s, U, new_order, today):
    from app.services import seguimiento as seg
    a, b = new_order([("PT-905", 2)]), new_order([("PT-901", 2)])
    gr = [g for g in seg.groups() if g["fecha"] == a.fecha_compromiso and g["cliente"].id == a.customer_id]
    assert gr and {a.id, b.id} <= {o.id for o in gr[0]["ovs"]}
    for user in ("coord.ventas", "coord.almacen", "jefe.calidad"):
        assert _get(app, user, "/seguimiento/expedientes").status_code == 200, user
    html = _get(app, "jefe.calidad", f"/seguimiento/expedientes/{a.customer_id}/{a.fecha_compromiso.isoformat()}?certificados=consolidado").get_data(as_text=True)
    assert a.numero in html and b.numero in html and "Certificado consolidado" in html


def test_pago_en_el_expediente(app, s, U, new_order):
    import io
    from app.models import CustomerPayment, OrderAttachment
    o = new_order([("PT-905", 2)])
    c = app.test_client()
    tok, _ = login(c, "coord.ventas")
    r = c.post(f"/ov/{o.id}/accion/pago", data={"_csrf": tok, "fecha_pago": date.today().isoformat(), "monto": "150",
                                          "medio": "Transferencia", "archivo": (io.BytesIO(b"%PDF-1.4"), "pago.pdf")},
               content_type="multipart/form-data")
    assert r.status_code == 302
    assert s.query(CustomerPayment).filter_by(customer_id=o.customer_id, monto=150).count() == 1
    assert s.query(OrderAttachment).filter_by(order_id=o.id, tipo="PAGO").count() == 1


def test_recojo_en_almacen(s, U, cust, today):
    from app.services import orders as osvc
    from app.services import seguimiento as seg
    from app.services.distribution import dispatchable_orders
    o = osvc.create_order(U("coord.ventas"), None, cust("20000000001").id, today + timedelta(days=2),
                          [{"product_code": "PT-905", "cantidad": 2, "precio_unitario": 999}], oc_archivo="oc.pdf",
                          entrega=osvc.pickup_delivery())
    assert o.modalidad_entrega == "RECOJO" and o not in dispatchable_orders(require_prepared=False)
    with pytest.raises(BusinessError, match="preparada"):
        seg.register_pickup(o, U("lider.almacen"), "Cliente demo")
    o.estado = "PREPARADA"
    seg.register_pickup(o, U("lider.almacen"), "Cliente demo", "DNI demo")
    assert o.estado == "ENTREGADA" and o.salida_ts


def test_saldo_comercial_cierra_lineas_o_las_envia(s, U, new_order, today):
    from app.services import seguimiento as seg
    from app.services.orders import create_order
    padre = new_order([("PT-905", 2)])
    saldo = create_order(U("coord.ventas"), f"{padre.numero}-S1", padre.customer_id, today + timedelta(days=4),
                         [{"product_code": "PT-905", "cantidad": 3, "precio_unitario": 999},
                          {"product_code": "PT-901", "cantidad": 2, "precio_unitario": 999}], origen="SALDO", evaluar=False)
    saldo.parent_id = padre.id
    s.flush()
    assert len(seg.pending_lines(padre)) == 2
    cerrar = [l.id for l in saldo.lines if l.product_code == "PT-901"]
    with pytest.raises(BusinessError, match="motivo"):
        seg.resolve_balance(saldo, U("coord.ventas"), cerrar)
    seg.resolve_balance(saldo, U("coord.ventas"), cerrar, today + timedelta(days=6), "cliente ya no lo requiere")
    assert [l.product_code for l in saldo.lines if l.activa] == ["PT-905"] and saldo.fecha_compromiso == today + timedelta(days=6)


def test_regularizacion_cliente_en_el_mismo_casillero(app):
    html = _get(app, "coord.ventas", "/ov/regularizacion").get_data(as_text=True)
    assert 'list="reg_clientes"' in html and 'name="customer_id"' in html


# ------------------------------------------------------------------ indicadores
def test_nivel_de_servicio_del_mes_y_detalle(app, s, U, new_order, today):
    from app.services import seguimiento as seg
    o = new_order([("PT-905", 2)])
    o.salida_ts = __import__("datetime").datetime.combine(o.fecha_compromiso, __import__("datetime").time(10))
    for l in o.lines:
        l.despachado = l.cantidad
    s.commit()
    d = seg.service_month(desde=today - timedelta(days=1), hasta=today + timedelta(days=30))
    assert d["universo"] >= 1 and d["on_time"] == 100.0 and d["otif"] == 100.0
    html = _get(app, "jefe.operaciones", "/").get_data(as_text=True)
    assert "Nivel de servicio del mes" in html and "/seguimiento/servicio" in html
    assert _get(app, "coord.logistica", "/seguimiento/servicio?ver=tarde").status_code == 200
    assert _get(app, "coord.ventas", "/seguimiento/desempeno").status_code == 403


def test_tiempos_de_respuesta_y_desempeno(app, s, U):
    from datetime import datetime
    from app.models import MoveRequest
    from app.services import seguimiento as seg
    m = MoveRequest(area="Producción", origen="Almacén 1524", destino="Línea R1", carga={"tipo": "MATERIA_PRIMA"},
                    estado="COMPLETADA", asignado_a=U("montacarguista").id, ts=datetime.now() - timedelta(minutes=50),
                    inicio_ts=datetime.now() - timedelta(minutes=40), fin_ts=datetime.now() - timedelta(minutes=20))
    s.add(m)
    s.commit()
    t = seg.response_times()
    fila = next(r for r in t["resumen"] if r["tipo"] == "Movimiento · Producción")
    assert fila["subtipo"] == "Materia prima" and 29 <= fila["prom_min"] <= 31
    eq = seg.team_performance()
    assert any(f["user"].username == "montacarguista" and f["movimientos"] == 1 for f in eq["filas"])
    assert _get(app, "jefe.operaciones", "/seguimiento/desempeno").status_code == 200


def test_indicadores_del_inicio_llevan_al_detalle(app):
    html = _get(app, "jefe.logistica", "/").get_data(as_text=True)
    assert 'class="kpi' in html and '<a href="/' in html
