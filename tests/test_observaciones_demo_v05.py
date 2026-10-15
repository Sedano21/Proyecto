"""Observaciones al demo v0.5 (13-oct): Comercial, Almacén, Producción, Calidad, Abastecimiento, Distribución,
informes y administración."""
from datetime import date, datetime, timedelta

import pytest

from app.models import (Customer, CustomerSite, Incident, ImportShipment, Liquidation, Product, ProductionReport, Route,
                        StockLot, Transfer)
from app.services.core import BusinessError, param

from .conftest import alerts_of
from .test_web import login


# ------------------------------ Comercial ----------------------------------
def test_hora_de_cita_24h_y_lugar_de_entrega(s, U, cust, today):
    from app.services import orders as osvc
    c = cust("20000000001")
    assert "14:30" in osvc.horas_cita() and "2:30 pm" not in osvc.horas_cita()
    with pytest.raises(BusinessError):
        osvc.create_order(U("coord.ventas"), "H-1", c.id, today + timedelta(days=2),
                          [{"product_code": "PT-905", "cantidad": 1, "precio_unitario": 999}], hora_cita="2:30 pm")
    with pytest.raises(BusinessError):  # "otro" lugar sin distrito/provincia: no se puede calcular la ruta
        osvc.resolve_delivery(c, None, "Almacén Norte", "Av. Demo 123", "", "", guardar=True, user=U("coord.ventas"))
    e = osvc.resolve_delivery(c, None, "Almacén Norte", "Av. Demo 123", "Comas", "Lima", guardar=True, user=U("coord.ventas"))
    site = s.get(CustomerSite, e["site_id"])
    assert site.nombre == "Almacén Norte" and site.customer_id == c.id
    o = osvc.create_order(U("coord.ventas"), "H-2", c.id, today + timedelta(days=2),
                          [{"product_code": "PT-905", "cantidad": 1, "precio_unitario": 999}], hora_cita="14:30",
                          entrega=osvc.resolve_delivery(c, site.id))
    assert o.lugar_entrega == "Almacén Norte" and o.distrito == "Comas" and o.provincia == "Lima" and o.hora_cita == "14:30"


def test_venta_por_saco_se_convierte_a_kg(s, U, cust, today):
    from app.models import PriceItem
    from app.services import orders as osvc
    it = s.query(PriceItem).filter_by(lista="GRANEL", vigente=True).first()
    assert it is not None and it.kg_saco
    o = osvc.create_order(U("coord.ventas"), "S-1", cust("20000000001").id, today + timedelta(days=2),
                          [{"product_code": it.product_code, "cantidad": 2, "precio_unitario": 999 * it.kg_saco, "um_venta": "SACO"}])
    l = o.lines[0]
    assert l.um_venta == "SACO" and l.cantidad_venta == 2 and l.cantidad == pytest.approx(2 * it.kg_saco)
    assert l.precio_unitario == pytest.approx(999)  # por kg
    from app.services.documents import ov_document
    d = ov_document(o)
    assert d["lineas"][0]["cantidad"] == 2 and d["lineas"][0]["v_uni"] == pytest.approx(999 * it.kg_saco)


def test_ficha_de_cliente_y_maestro_sap(app, s, U, tmp_path, new_order):
    from app.services import customers as csvc
    from app.services import uploads
    c = s.query(Customer).filter_by(ruc="20000000001").one()
    csvc.save_customer(U("coord.ventas"), c, {"contacto": "Ana Demo", "telefono": "999 000 111", "correo": "ana@demo.pe"})
    with pytest.raises(BusinessError):
        csvc.save_customer(U("coord.ventas"), c, {"correo": "sin-arroba"})
    new_order([("PT-905", 3)])
    p = csvc.profile(c)
    assert p["n"] >= 1 and p["soles"] > 0
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["RUC", "Nombre de cliente", "Teléfono", "Correo electrónico", "Lugar de entrega", "Dirección de entrega",
               "Distrito de entrega", "Provincia de entrega"])
    ws.append(["20000000001", c.nombre, "01 555 0000", "compras@demo.pe", "CD Lurín", "Panamericana Sur km 30", "Lurín", "Lima"])
    ws.append(["20999999999", "CLIENTE NUEVO SAP DEMO SAC", "", "", "", "", "", ""])
    f = tmp_path / "clientes.xlsx"
    wb.save(f)
    b = uploads.create_batch(U("coord.ventas"), "CLIENTES", str(f), "clientes.xlsx")
    res = uploads.confirm(b, U("coord.ventas"), {})
    assert res["clientes_nuevos"] == 1 and res["lugares_de_entrega_nuevos"] == 1
    assert any(x.nombre == "CD Lurín" for x in c.sites) and c.correo == "compras@demo.pe"
    cl = app.test_client()
    login(cl, "vendedor1")
    html = cl.get(f"/ov/clientes/{c.id}").get_data(as_text=True)
    assert "CD Lurín" in html and "Lugares de entrega" in html and "Condiciones y penalidades" in html


def test_informe_comercial_y_desviacion_de_modificaciones(app, s, U, new_order):
    from app.services import orders as osvc
    from app.services.reports import comercial
    o = new_order([("PT-905", 10)], precio=1000)
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 12, "precio_unitario": 1000}]})
    s.commit()
    d = comercial()
    assert d["ovs"] >= 1 and d["soles"] > 0 and d["serie_semanal"]
    assert d["modificadas"]["ovs"] == 1 and d["modificadas"]["desv_cantidad_pct"] == 20.0
    assert d["modificadas"]["desv_soles_pct"] == 20.0
    assert d["margen_producto"] == []  # sin permiso de costos no se muestra margen
    c = app.test_client()
    login(c, "jefe.ventas")
    html = c.get("/informes/comercial").get_data(as_text=True)
    assert "Ventas semanales" in html and "<svg" in html and "OV modificadas" in html


# ------------------------------ Almacén ------------------------------------
def test_cargas_por_area(app):
    c = app.test_client()
    login(c, "coord.almacen")
    html = c.get("/almacen/cargas?area=Almacén").get_data(as_text=True)
    assert "Stock por lote" in html and "Lista de precios" not in html
    assert c.get("/almacen/cargas/nueva?tipo=PRECIOS").status_code == 403


def test_traslado_con_llegada_alerta_a_calidad_y_almacen(s, U):
    from app.services import transfers as tsvc
    lot = s.query(StockLot).filter_by(product_code="PT-901", lote="L901A").one()
    t = tsvc.request_transfer(U("coord.logistica"), lot.id, "EXT-001", 10)
    llegada = datetime.now().replace(second=0, microsecond=0) + timedelta(days=1)
    tsvc.authorize(t, U("jefe.logistica"), True, "ok", llegada)
    assert t.llegada_estimada == llegada
    a = alerts_of(s, "TRASLADO_LLEGADA", t.id)
    assert a and "Calidad" in a[0].mensaje
    from app.models import AlertType
    roles = s.get(AlertType, "TRASLADO_LLEGADA").roles
    assert "JEFE_CALIDAD" in roles and "COORD_ALMACEN" in roles
    with pytest.raises(BusinessError):
        tsvc.set_arrival(t, U("jefe.logistica"), datetime.now() - timedelta(days=2))
    assert tsvc.remind_arrivals(llegada.date()) == 1


def test_informe_de_reempaque(app, s, U):
    from app.services import repack as rsvc
    from app.services.reports import reempaque
    lot = s.query(StockLot).filter_by(product_code="PT-901", lote="L901A").one()
    r = rsvc.request(U("coord.almacen"), "ACTUALIZACION_FECHA", lot.id, 5, motivo="prueba")
    rsvc.evaluate(r, U("jefe.calidad"), False, "Grano partido fuera de especificación")
    s.commit()
    d = reempaque()
    assert d["total"] == 1 and d["tasa_aprobacion"] == 0 and d["motivos"][0][0].startswith("Calidad: Grano partido")
    assert any("aprueban" in x for x in d["recomendaciones"])


# ------------------------------ Producción ---------------------------------
def test_plan_vs_liquidacion_y_cumplimiento(s, U):
    from app.services import production as psvc
    hoy = date.today()
    psvc.add_plan(U("jefe.produccion"), "DIA", hoy, "PT-905", 100)
    psvc.add_plan(U("jefe.produccion"), "SEMANA", hoy, "PT-905", 500)
    psvc.register_liquidation(U("jefe.produccion"), "OF-PLAN-1", "PT-905", 80, "LPLAN1", fecha=hoy)
    d = psvc.plan_vs_real("DIA", hoy, hoy)
    f = [x for x in d["filas"] if x["producto"] == "PT-905"][0]
    assert f["plan"] == 100 and f["real"] == 80 and f["cumplimiento"] == 80.0 and d["tasa"] == 80.0
    w = psvc.plan_vs_real("SEMANA", hoy, hoy)
    assert [x for x in w["filas"] if x["producto"] == "PT-905"][0]["cumplimiento"] == 16.0
    with pytest.raises(BusinessError):
        psvc.add_plan(U("coord.ventas"), "DIA", hoy, "PT-905", 1)


def test_parte_programado_y_completado(s, U):
    from app.services import production as psvc
    r = psvc.register_report(U("asist.produccion"), "TRUER", date.today(), "PT-905", 1000, estado="PROGRAMADO")
    assert r.estado == "PROGRAMADO" and r.rendimiento_pct is None
    n = psvc.complete_report(r, U("asist.produccion"), granel_kg=950, desmedro_kg=50)
    assert n.estado == "EN PROCESO" and n.rendimiento_pct == 95.0 and n.desmedro_pct == 5.0
    assert s.get(ProductionReport, r.id) is None


def test_desmedro_de_la_lista_es_merma_no_material(s, U):
    from app.models import BOMLine
    from app.services import production as psvc
    v = psvc.active_bom()
    s.add(BOMLine(version_id=v.id, padre="PT-905", padre_desc="x", cantidad_bom=1, componente="ME-905",
                  componente_desc="PRODUCTO DEMO - DESMEDRO", cantidad=0.02, orden=99))
    s.flush()
    res = psvc.material_requirements("PT-905", 100)
    assert not any(m["componente"] == "ME-905" for m in res["materiales"])
    assert res["desmedro"][0]["componente"] == "ME-905"
    proj = psvc.bom_merma_projection("PT-905")
    p = s.get(Product, "PT-905")
    assert proj["pct"] == pytest.approx(round(100 * 0.02 / p.peso_kg, 3))


def test_revision_de_lista_de_materiales(s, U):
    from app.services import production as psvc
    req = psvc.create_request("PT-905", 10, U("coord.almacen"))
    with pytest.raises(BusinessError):
        psvc.review_bom(req, U("jefe.produccion"), False, "")
    psvc.review_bom(req, U("jefe.produccion"), False, "Falta la bobina correcta")
    assert req.bom_revision["conforme"] is False and alerts_of(s, "BOM_OBSERVADA", req.id)


# ------------------------------ Calidad ------------------------------------
def test_avisos_de_fumigacion_7_3_y_0_dias(s, U):
    from app.services import quality as qsvc
    lot = s.query(StockLot).filter_by(product_code="MP-901").first()
    hoy = date.today()
    qsvc.schedule_fumigation(lot, U("jefe.calidad"), hoy + timedelta(days=7))
    assert qsvc.fumigation_alerts(hoy) >= 1
    assert qsvc.fumigation_alerts(hoy + timedelta(days=4)) >= 1   # 3 días antes
    assert qsvc.fumigation_alerts(hoy + timedelta(days=7)) >= 1   # el mismo día
    n5 = len(alerts_of(s, "FUMIGACION_PROXIMA", lot.id))
    qsvc.fumigation_alerts(hoy + timedelta(days=2))               # 5 días antes: sin aviso nuevo
    assert len(alerts_of(s, "FUMIGACION_PROXIMA", lot.id)) == n5 == 3


def test_registro_impreso_con_encabezado_del_formato(app, s, U):
    from app.services import quality as qsvc
    r = qsvc.register(U("jefe.calidad"), "MUESTREO", {"humedad": 12}, "PT-905", "L905A", None, "CONFORME", "")
    s.commit()
    c = app.test_client()
    login(c, "jefe.calidad")
    html = c.get(f"/calidad/registro/{r.id}").get_data(as_text=True)
    assert "REG-CAL-002" in html and "Versión: 02" in html and "logo_corporacion_productiva.png" in html
    assert c.get("/calidad/abrir?formato_sel=FUMIGACION").status_code == 302


# ------------------------------ Abastecimiento -----------------------------
def test_costo_maximo_de_compra_alerta(s, U):
    from app.services import purchasing as psvc
    p = s.get(Product, "MP-901")
    p.costo_max_compra = 5.0
    r = psvc.create_request(U("coord.almacen"), "MP-901", 100)
    r.estado = "SOLICITADA"
    psvc.quote(r, U("compras"), "Proveedor demo", "COT-1", precio=5.5)
    assert alerts_of(s, "COMPRA_SOBRE_COSTO_MAXIMO", r.id)


def test_importacion_con_contenedor_y_costos(s, U):
    from app.services import imports as isvc
    sh = isvc.create_shipment(U("importaciones"), "IMP-DEMO-1", "Proveedor ext.", "MP-901", 1000, date.today(),
                              warehouse_code="EXT-002", contenedor="msku1234567", tipo_contenedor="40'")
    assert sh.contenedor == "MSKU1234567"
    isvc.add_cost(sh, U("importaciones"), "Flete internacional", 1000, "USD", 3.5)
    isvc.add_cost(sh, U("importaciones"), "Agente de aduanas", 500, "PEN")
    with pytest.raises(BusinessError):
        isvc.add_cost(sh, U("importaciones"), "Seguro", 100, "USD")  # sin tipo de cambio
    s.flush()
    c = isvc.cost_summary(sh)
    assert c["total_pen"] == 4000 and c["por_unidad"] == 4.0


# ------------------------------ Distribución -------------------------------
def test_transporte_externo_requiere_validacion_del_coordinador(s, U, new_order):
    from app.models import Vehicle
    from app.services import distribution as dist
    o = new_order([("PT-905", 100)])
    r = dist.active_stop(o).route
    ext = s.query(Vehicle).filter_by(propio=False).first()
    dist.update_route(r, U("coord.distribucion"), vehicle_id=ext.id, driver_id=None)
    if r.driver_id is None:
        from app.models import Driver
        r.driver_id = s.query(Driver).filter_by(disponible=True).first().id
    assert r.requiere_externo
    with pytest.raises(BusinessError):
        dist.confirm_route(r, U("coord.distribucion"))
    with pytest.raises(BusinessError):
        dist.validate_external(r, U("asist.distribucion"), True)
    dist.validate_external(r, U("coord.distribucion"), True, "Flota propia ocupada")
    dist.confirm_route(r, U("coord.distribucion"))
    assert r.estado == "CONFIRMADA"
    from app.services.reports import distribucion
    d = distribucion(r.fecha - timedelta(days=1), r.fecha + timedelta(days=1))
    assert d["tot"]["EXTERNO"]["rutas"] >= 1


def test_mapa_y_trafico(s, U, new_order, monkeypatch):
    import io
    import json
    from app.services import maps
    o = new_order([("PT-905", 100)])
    r = maps  # noqa
    route = __import__("app.services.distribution", fromlist=["x"]).active_stop(o).route
    assert maps.gmaps_link(route).startswith("https://www.google.com/maps/dir/?api=1")
    assert maps.embed_url(route) == "" and maps.estimate(route)["min_con_trafico"] is None
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "clave-de-prueba")

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, timeout=15):
        assert "departure_time=now" in url and "clave-de-prueba" in url
        return R(json.dumps({"rows": [{"elements": [{"status": "OK", "distance": {"value": 12000},
                                                     "duration": {"value": 1800}, "duration_in_traffic": {"value": 3000}}]}]}).encode())
    t = maps.check_traffic(route, U("coord.distribucion"), opener=opener)
    assert t["extra_min"] == 20 and route.tiempo_estimado_min == t["min_con_trafico"]
    assert alerts_of(s, "RUTA_TRAFICO", route.id)


def test_incidencias_por_tipo_y_subtipo(s, U, new_order):
    from app.catalogs import INCIDENT_GROUP, INCIDENT_TYPES
    from app.services import distribution as dist
    assert INCIDENT_GROUP["INFESTACION_INTERNA"] == "CALIDAD" and INCIDENT_GROUP["LLEGADA_TARDE"] == "LOGISTICA"
    assert not any("TO-BE" in n for _, n in INCIDENT_TYPES)
    assert "RECHAZO_CITA" not in dict(INCIDENT_TYPES)  # llegada tarde y rechazo por cita son lo mismo
    o = new_order([("PT-905", 5)])
    i = dist.register_incident(U("aux.despacho"), "INFESTACION_EXTERNA", "Gorgojo en sacos", order=o)
    assert i.grupo == "CALIDAD" and alerts_of(s, "INC_RECHAZO_CALIDAD", i.id)
    j = dist.register_incident(U("aux.despacho"), "RECHAZO_CITA", "Llegó tarde", order=o)  # alias anterior
    assert j.tipo == "LLEGADA_TARDE" and j.grupo == "LOGISTICA"


# ------------------------------ Administración y diseño --------------------
def test_permisos_por_rol_amigable(app):
    c = app.test_client()
    login(c, "sistemas")
    html = c.get("/usuarios/permisos?rol=JEFE_VENTAS").get_data(as_text=True)
    assert 'class="switch"' in html and "Cargar y modificar listas de precios" in html
    m = c.get("/usuarios/permisos?vista=matriz&area=Comercial").get_data(as_text=True)
    assert "Matriz compacta" in m and "button class=\"cell" in m


def test_diseno_adaptable(app):
    c = app.test_client()
    login(c, "coord.ventas")
    html = c.get("/").get_data(as_text=True)
    assert 'name="viewport"' in html and "menu-btn" in html
    css = c.get("/static/style.css").get_data(as_text=True)
    assert "@media (max-width:760px)" in css and "@media (max-width:1100px)" in css  # rediseño v0.8
