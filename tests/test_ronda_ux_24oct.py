"""Ronda UX del 24-oct-2026: Producción (formato único Registrar / Programar, personal dinámico, validaciones, receta,
liquidación parcial, monitoreo), Distribución (SOAT, conformidad del chofer, GEOSATELITAL, incidencias por ítem),
Mantenimiento, cadena de suministro y matriz de accesos por área."""
import base64
import struct
import zlib
from datetime import date, timedelta

import openpyxl
import pytest
from sqlalchemy import select

from app.services.core import BusinessError, has_perm, set_param

from .conftest import alerts_of
from .test_web import csrf, login


def _png(w=40, h=20):
    """PNG mínimo válido (para la firma en pantalla)."""
    raw = b"".join(b"\x00" + bytes([(x * 7 + y * 3) % 255 for x in range(w)]) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 0)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------ Producción
def test_horas_12_y_24(app):
    from app.services.parte import fmt_hora, parse_hora
    assert parse_hora("3:30 pm") == "15:30" and parse_hora("12 am") == "00:00" and parse_hora("7:05") == "07:05"
    assert parse_hora("03:30 p. m.") == "15:30"
    with pytest.raises(BusinessError):
        parse_hora("25:00")
    with pytest.raises(BusinessError):
        parse_hora("13 pm")
    set_param("formato_hora", "12H")
    assert fmt_hora("15:30") == "3:30 p. m."
    set_param("formato_hora", "24H")
    assert fmt_hora("15:30") == "15:30"


def test_programar_validaciones_y_edicion(s, U):
    from app.services import parte
    u = U("asist.produccion")
    with pytest.raises(BusinessError, match="futura"):
        parte.program(u, {"linea": "R1", "product_code": "PT-905", "fecha": date.today() - timedelta(days=1),
                          "peso_entrada_kg": 100})
    manana = date.today() + timedelta(days=1)
    with pytest.raises(BusinessError, match="menor"):
        parte.program(u, {"linea": "R1", "product_code": "PT-905", "fecha": manana, "peso_entrada_kg": 100,
                          "hora_inicio": "3 pm", "hora_fin": "9:00"})
    with pytest.raises(BusinessError, match="no corresponde"):  # PT-905 es de 0.25 kg
        parte.program(u, {"linea": "R1", "product_code": "PT-905", "fecha": manana, "peso_entrada_kg": 100,
                          "presentacion_kg": 0.5})
    with pytest.raises(BusinessError, match="producto terminado"):
        parte.program(u, {"linea": "R1", "product_code": "MP-901", "fecha": manana, "peso_entrada_kg": 100})
    r = parte.program(u, {"linea": "R1", "product_code": "PT-905", "fecha": manana, "sacos": 4, "peso_saco_kg": 25,
                          "hora_inicio": "7:00 am", "hora_fin": "3:00 pm", "und_paquete": 20})
    assert r.estado == "PROGRAMADO" and r.peso_entrada_kg == 100 and r.presentacion_kg == 0.25
    assert r.programa == {"hora_inicio": "07:00", "hora_fin": "15:00", "kg": 100, "fecha": manana.isoformat()}
    with pytest.raises(BusinessError, match="motivo"):
        parte.edit_program(u, r, manana, 120, "")
    parte.edit_program(u, r, manana + timedelta(days=1), 120, "Llegó más MP")
    assert r.peso_entrada_kg == 120 and r.fecha == manana + timedelta(days=1)
    r.estado = "LIQUIDADO"
    with pytest.raises(BusinessError, match="liquidado"):
        parte.edit_program(u, r, manana, 130, "otra")


def test_formato_unico_registrar_y_programar_web(app, s):
    from app.models import ProductionReport
    c = app.test_client()
    login(c, "asist.produccion")
    tok = csrf(c, "/produccion/partes")
    html = c.get("/produccion/partes").get_data(as_text=True)
    assert 'value="programar"' in html and 'value="registrar"' in html and "Registrar o programar parte" not in html
    manana = (date.today() + timedelta(days=1)).isoformat()
    r = c.post("/produccion/parte/nuevo", data={"_csrf": tok, "accion": "programar", "linea": "R1", "product_code": "PT-905",
                                               "fecha": manana, "peso_entrada_kg": "80"}, follow_redirects=True)
    assert "Parte programado" in r.get_data(as_text=True)
    r = c.post("/produccion/parte/nuevo", data={"_csrf": tok, "accion": "registrar", "linea": "R1", "product_code": "PT-905",
                                               "fecha": manana, "peso_entrada_kg": "80"}, follow_redirects=True)
    assert "para otra fecha use «Programar»" in r.get_data(as_text=True)
    r = c.post("/produccion/parte/nuevo", data={"_csrf": tok, "accion": "registrar", "linea": "R1", "product_code": "PT-905",
                                               "fecha": date.today().isoformat(), "peso_entrada_kg": "80"}, follow_redirects=True)
    assert "Parte iniciado" in r.get_data(as_text=True)
    estados = {x.estado for x in s.execute(select(ProductionReport)).scalars()}
    assert {"PROGRAMADO", "EN PROCESO"} <= estados
    j = c.get("/produccion/api/producto?code=PT-905").get_json()
    assert j["presentacion_kg"] == 0.25 and j["tipo"] == "PT"


def test_finalizar_con_colaboradores_registrados_y_paquetes(s, U):
    from app.services import attendance, parte
    u = U("asist.produccion")
    w1 = attendance.save_worker(u, {"nombre": "Colaborador Uno"})
    w2 = attendance.save_worker(u, {"nombre": "Colaborador Dos"})
    r = parte.start(u, {"linea": "R1", "product_code": "PT-905", "peso_entrada_kg": 100, "und_paquete": 20})
    base = {"operarios": 2, "pallets": [{"destino": "DESPACHO", "cantidad": 19}]}
    with pytest.raises(BusinessError, match="registrado"):
        parte.finish(u, r, dict(base, colaboradores=[{"nombre": "Persona Inventada"}]))
    with pytest.raises(BusinessError, match="repetido"):
        parte.finish(u, r, dict(base, colaboradores=[{"worker_id": w1.id}, {"worker_id": w1.id}]))
    with pytest.raises(BusinessError, match="operarios"):
        parte.finish(u, r, dict(base, operarios=1, colaboradores=[{"worker_id": w1.id}, {"worker_id": w2.id}]))
    with pytest.raises(BusinessError, match="fin no puede ser menor"):
        parte.finish(u, r, dict(base, colaboradores=[{"worker_id": w1.id, "inicio": "15:00", "fin": "8:00"}]))
    with pytest.raises(BusinessError, match="completan un paquete"):
        parte.finish(u, r, dict(base, unidades_sueltas=20))
    with pytest.raises(BusinessError, match="enteros"):
        parte.finish(u, r, dict(base, pallets=[{"destino": "DESPACHO", "cantidad": 2.5}]))
    parte.finish(u, r, dict(base, unidades_sueltas=5, colaboradores=[{"worker_id": w1.id, "inicio": "7:00 am", "fin": "3 pm"},
                                                                     {"worker_id": str(w2.id)}]))
    assert r.unidades == 385 and r.estado == "PENDIENTE" and r.motivo_estado.startswith("liquidación")
    assert [c["nombre"] for c in r.colaboradores] == ["COLABORADOR UNO", "COLABORADOR DOS"]
    assert r.colaboradores[0]["inicio"] == "07:00" and r.colaboradores[0]["fin"] == "15:00"
    with pytest.raises(BusinessError, match="pendiente"):
        parte.set_state(u, r, "PENDIENTE", "")
    parte.set_state(u, r, "PENDIENTE", "material de empaque")
    assert r.motivo_estado == "material de empaque"


def test_monitoreo_en_tiempo_real(s, U):
    from app.services import parte
    u = U("asist.produccion")
    r = parte.start(u, {"linea": "R1", "product_code": "PT-905", "peso_entrada_kg": 100, "und_paquete": 20})
    parte.add_progress(u, r, "DESPACHO", 10)  # 10 paquetes × 20 und × 0.25 kg = 50 kg
    l = parte.live(r)
    assert l["rend"] == 50.0 and l["salida_kg"] == 50.0 and not l["final"]
    with pytest.raises(BusinessError, match="enteros"):
        parte.add_progress(u, r, "DESPACHO", 1.5)
    assert any(x is r for x, _ in parte.monitor(u))


def test_receta_reemplazo_por_categoria(s, U):
    from app.models import BOMLine
    from app.services import production as prod
    ln = s.execute(select(BOMLine).where(BOMLine.padre == "PT-901", BOMLine.componente == "MP-901")).scalars().first()
    with pytest.raises(BusinessError, match="arveja por frijol"):
        prod.edit_bom_line(U("jefe.produccion"), ln, None, "MP-903", "prueba")
    en = s.execute(select(BOMLine).where(BOMLine.padre == "PT-901", BOMLine.componente == "EN-901")).scalars().first()
    with pytest.raises(BusinessError):
        prod.edit_bom_line(U("jefe.produccion"), en, None, "SU-901", "prueba")
    prod.edit_bom_line(U("jefe.produccion"), en, None, "EN-902", "lámina alternativa")
    assert en.componente == "EN-902"
    assert "MP-903" not in [p.code for p in prod.substitutes(ln)]


def test_liquidacion_parcial_y_filtro_por_fecha(s, U):
    from app.services import production as prod
    u = U("jefe.produccion")
    req = prod.create_request("PT-902", 100, u, origen="MANUAL")
    prod.register_liquidation(u, "OF-P1", "PT-902", 40, "LP1", request=req, horas=4, operarios=2, parcial=True)
    assert req.estado == "EN_PROCESO" and prod.liquidated_qty(req) == 40
    prod.register_liquidation(u, "OF-P2", "PT-902", 60, "LP2", request=req, horas=4, operarios=2, parcial=True)
    assert req.estado == "LIQUIDADA"
    assert {l.numero_documento for l in prod.liquidations_list(date.today(), date.today(), "PARCIAL")} == {"OF-P1", "OF-P2"}
    assert not prod.liquidations_list(date.today() + timedelta(days=1))


def test_plan_editable_con_motivo_pendiente(s, U):
    from app.services import production as prod
    pl = prod.add_plan(U("asist.produccion2"), "DIA", date.today() + timedelta(days=2), "PT-902", 50)
    prod.update_plan(U("asist.produccion2"), pl, 70, "Pedido adicional", date.today() + timedelta(days=3))
    st, motivo, _ = prod.plan_status(pl)
    assert st == "PENDIENTE" and "validación del Jefe" in motivo and "fecha" in motivo
    prod.validate_plan_change(U("jefe.produccion"), pl, True)
    assert pl.cantidad == 70 and pl.fecha == date.today() + timedelta(days=3)
    assert prod.plan_status(pl, real=70)[0] == "LIQUIDADO"


# ------------------------------------------------------------------ Distribución
def test_soat_vigente_para_asignar(s, U):
    from app.models import Route, Vehicle, VehicleDocument
    from app.services import distribution as dist
    v = s.query(Vehicle).filter_by(placa="DEM-10T").one()
    s.query(VehicleDocument).filter_by(vehicle_id=v.id).delete()
    r = Route(fecha=date.today(), estado="PROPUESTA", peso_total=10)
    s.add(r)
    s.flush()
    with pytest.raises(BusinessError, match="SOAT"):
        dist.update_route(r, U("coord.distribucion"), v.id)
    from app.services.fleet import soat_status
    assert soat_status(v) == (False, "sin SOAT registrado")
    assert alerts_of(s, "FLOTA_DOCUMENTO", v.id)


def test_firma_y_conformidad_por_chofer(s, U, new_order, today, tmp_path):
    from app.services import distribution as dist
    from .test_flujos import _user_chofer, dispatch
    with pytest.raises(BusinessError):
        dist.save_signature("data:image/png;base64," + base64.b64encode(b"no es png" * 40).decode(), str(tmp_path), "x")
    nombre = dist.save_signature("data:image/png;base64," + base64.b64encode(_png()).decode(), str(tmp_path), "ov1")
    assert nombre.endswith(".png")
    o = new_order([("PT-905", 10)])
    stop = dispatch(s, U, o, today)
    ch = _user_chofer(s, U, stop)
    assert [st for _, sts in dist.driver_stops(ch) for st in sts if st.id == stop.id]
    dist.register_delivery(stop, ch, "f.jpg", "g.jpg", receptor_nombre="persona  ficticia", receptor_dni="87654321",
                           firma_path=nombre)
    assert stop.receptor_nombre == "PERSONA FICTICIA" and o.estado == "ENTREGADA"


def test_geosatelital_sin_configurar_y_con_proveedor(s, monkeypatch):
    from app.models import Vehicle
    from app.services import geosat
    vehs = list(s.execute(select(Vehicle)).scalars())
    from app.services.core import set_param
    set_param("geosatelital_url_panel", "")  # V8: el panel viene configurado por defecto
    t = geosat.tracking_board(vehs)
    assert not t["configurado"] and t["error"] is None and all(x["pos"] is None for x in t["filas"])
    monkeypatch.setenv("GEOSAT_API_URL", "https://proveedor.invalid/api")

    class R:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    datos = {"data": [{"plate": "DEM-4T5", "latitude": -12.05, "longitude": -77.03, "speed": 42, "timestamp": "10:00"},
                      {"placa": "XYZ-999", "lat": -12.1, "lng": -77.0, "velocidad": 0}]}
    t = geosat.tracking_board(vehs, opener=lambda req, timeout: R(__import__("json").dumps(datos).encode()))
    pos = {x["v"].placa: x["pos"] for x in t["filas"]}
    assert pos["DEM-4T5"]["en_movimiento"] and pos["DEM-4T5"]["velocidad"] == 42
    assert [p["placa"] for p in t["sin_flota"]] == ["XYZ-999"]

    def falla(req, timeout):
        raise OSError("sin conexión")
    assert "No se pudo consultar" in geosat.tracking_board(vehs, opener=falla)["error"]


def test_incidencia_con_novedad_por_item(s, U, new_order):
    from app.services import distribution as dist
    o = new_order([("PT-905", 10)])
    l = o.lines[0]
    inc = dist.register_incident(U("asist.distribucion"), "PRODUCTO_ROTO", "Bolsas rotas", order=o,
                                 lineas=[{"line_id": l.id, "producto": l.product_code, "devuelto": 0, "novedad": "2 bolsas rotas"}])
    assert inc.lineas[0]["novedad"] == "2 bolsas rotas" and o.estado != "ENTREGA_PARCIAL"


# ------------------------------------------------------------------ Mantenimiento
def test_preventivo_correctivo_y_saneamiento(s, U):
    from app.models import Vehicle
    from app.services import maintenance as m
    v = s.query(Vehicle).filter_by(placa="DEM-4T5").one()
    v.km_actual = 9800
    u = U("coord.distribucion")
    with pytest.raises(BusinessError, match="frecuencia"):
        m.save_plan(u, v, {"tarea": "Cambio de aceite"})
    p = m.save_plan(u, v, {"tarea": "Cambio de aceite", "cada_km": 5000, "ultimo_km": 5000})
    assert m.due(p)["estado"] == "PROXIMO" and m.due(p)["prox_km"] == 10000
    assert m.check_alerts() >= 1 and alerts_of(s, "MANT_PREVENTIVO", p.id)
    m.complete_plan(u, p, date.today(), 10000, 150)
    assert m.due(p)["estado"] == "AL_DIA" and p.ultimo_km == 10000
    b = m.report_breakdown(u, v, "Falla de frenos", "ALTA", 10010)
    assert not v.disponible and alerts_of(s, "MANT_CORRECTIVO", b.id)
    with pytest.raises(BusinessError, match="fecha programada"):
        m.update_breakdown(u, b, "PROGRAMADA")
    m.update_breakdown(u, b, "PROGRAMADA", fecha_programada=date.today().isoformat(), taller="Taller ficticio")
    with pytest.raises(BusinessError, match="anterior"):
        m.update_breakdown(u, b, "REPORTADA")
    m.update_breakdown(u, b, "CERRADA", "Cambio de pastillas", costo="300")
    assert v.disponible and b.estado == "CERRADA"
    cal = U("jefe.calidad")
    with pytest.raises(BusinessError):
        m.save_zone(u, {"nombre": "Zona"})  # Distribución no registra saneamiento
    z = m.save_zone(cal, {"nombre": "Almacén PT - pasillo A", "area": "Almacén", "frecuencia_limpieza_dias": 7,
                          "frecuencia_fumigacion_dias": 30})
    assert m.zone_status(z)["limpieza"]["estado"] == "VENCIDO"
    m.check_alerts()
    assert alerts_of(s, "SANEAMIENTO_VENCIDO", z.id)
    m.log_sanitation(cal, "LIMPIEZA", date.today(), zone=z, responsable="Equipo de limpieza")
    assert m.zone_status(z)["limpieza"]["estado"] == "AL_DIA"
    with pytest.raises(BusinessError, match="vigencia"):
        m.log_sanitation(cal, "FUMIGACION", date.today(), vehicle=v, responsable="Empresa ficticia", producto="Producto X")
    m.log_sanitation(cal, "FUMIGACION", date.today() - timedelta(days=40), vehicle=v, responsable="Empresa ficticia",
                     producto="Producto X", vence=date.today() - timedelta(days=10))
    assert m.vehicle_fumigation(v)["estado"] == "VENCIDO"
    m.check_alerts()
    assert alerts_of(s, "FUMIGACION_UNIDAD", v.id)


# ------------------------------------------------------------------ Cadena de suministro
def test_aviso_riesgo_48_24_y_atraso_logistica(s, U, new_order):
    from app.services import supply
    o = new_order([("PT-902", 500)], dias=1)
    assert o.estado_stock != "COMPLETA"
    assert supply.check_order_risk() == 1 and supply.check_order_risk() == 0  # una sola vez
    a = alerts_of(s, "OV_RIESGO_DESPACHO", o.id)
    assert a and "24 h" in a[0].titulo
    with pytest.raises(BusinessError):
        supply.report_delay(U("coord.almacen"), o, "Falta MP")
    with pytest.raises(BusinessError, match="motivo"):
        supply.report_delay(U("jefe.logistica"), o, "")
    with pytest.raises(BusinessError, match="día de creación"):
        supply.report_delay(U("jefe.logistica"), o, "Falta MP", hoy=date.today() + timedelta(days=2))
    supply.report_delay(U("jefe.logistica"), o, "Falta materia prima", date.today() + timedelta(days=5))
    assert o.aviso_atraso["motivo"] == "Falta materia prima" and alerts_of(s, "OV_ATRASO_LOGISTICA", o.id)


def test_proyeccion_de_demanda(s, U, tmp_path):
    from app.services import supply
    mes = f"{date.today():%Y-%m}"
    with pytest.raises(BusinessError):
        supply.save_forecast(U("jefe.logistica"), mes, "PT-905", 100)
    supply.save_forecast(U("jefe.ventas"), mes, "PT-905", 100)
    # V7: modificar una proyección registrada requiere justificación y la autorización de Gerencia General
    with pytest.raises(BusinessError, match="justificación"):
        supply.save_forecast(U("jefe.ventas"), mes, "PT-905", 120)
    f0 = supply.save_forecast(U("jefe.ventas"), mes, "PT-905", 120, observacion="Nuevo cliente mayorista")
    assert f0.cantidad == 100 and f0.cambio["estado"] == "PENDIENTE"
    supply.decide_change(f0, U("gerente.general"), True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mes", "Producto", "Cantidad", "Canal"])
    ws.append([mes, "PT-902", 500, "MAYORISTA"])
    ws.append([mes, "NO-EXISTE", 5, ""])
    p = tmp_path / "dem.xlsx"
    wb.save(p)
    n, err = supply.import_forecast(U("jefe.ventas"), str(p))
    assert n == 1 and len(err) == 1
    d = supply.forecast_view(mes, 1)
    f = {x["code"]: x for x in d["filas"]}
    assert f["PT-905"]["total"] == 120 and f["PT-902"]["faltante"] > 0


def test_stock_sin_rotacion_mensual(s, U):
    from app.services import supply
    d = supply.no_rotation(30)
    assert d["filas"]
    assert supply.check_no_rotation(date.today().replace(day=1)) > 0
    assert supply.check_no_rotation(date.today().replace(day=1)) == 0  # una vez por mes
    a = alerts_of(s, "STOCK_SIN_ROTACION")
    assert a and "AUX_ALMACEN" in a[0].roles and "GERENCIA_GENERAL" in a[0].roles


def test_movimientos_punto_a_punto(s, U):
    from app.services import supply
    # V7: solicitan jefes, supervisores, coordinadores, líderes y el montacarguista (ya no los asistentes)
    with pytest.raises(BusinessError):
        supply.request_move(U("aux.almacen"), "Línea R2", "Zona de despacho")
    m = supply.request_move(U("jefe.produccion"), "Línea R2", "Zona de despacho", "PT-905 2 pallets", "2",
                            asignado_id=U("montacarguista").id)
    assert m.area == "Producción" and alerts_of(s, "MOVIMIENTO_SOLICITADO", m.id)
    with pytest.raises(BusinessError):  # asignado al montacarguista
        supply.start_move(U("aux.almacen"), m, "f.jpg")
    with pytest.raises(BusinessError, match="foto"):
        supply.start_move(U("montacarguista"), m, "")
    supply.start_move(U("montacarguista"), m, "ini.jpg")
    with pytest.raises(BusinessError, match="validación"):
        supply.finish_move(U("montacarguista"), m, "")
    supply.finish_move(U("montacarguista"), m, "fin.jpg")
    assert m.estado == "COMPLETADA" and m in supply.moves(U("montacarguista"))
    assert has_perm(U("montacarguista"), "traslados.ver")


def test_reempaque_por_excel_y_conteo_sobre_lista(s, U, tmp_path):
    from app.models import PhysicalCount
    from app.services import inventory, repack
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Tipo", "Producto", "Lote", "Almacén", "Cantidad", "Producto destino", "Motivo"])
    ws.append(["Actualización de fecha", "PT-901", "L901B", "ALM-001", 10, "", "Fecha próxima"])
    ws.append(["Cambio de presentación", "PT-901", "NO-EXISTE", "ALM-001", 5, "PT-902", ""])
    p = tmp_path / "rep.xlsx"
    wb.save(p)
    creadas, err = repack.import_requests(U("coord.almacen"), str(p))
    assert len(creadas) == 1 and len(err) == 1 and creadas[0].estado == "SOLICITADA"
    c1 = inventory.open_count(U("coord.almacen"), "ALM-001", codigos=["PT-901", "PT-902"])
    assert {l.product_code for l in c1.lines} == {"PT-901", "PT-902"}
    c2 = inventory.open_count(U("coord.almacen"), "", base=c1)
    assert {l.product_code for l in c2.lines} == {"PT-901", "PT-902"} and "conteo #" in c2.observacion
    assert s.query(PhysicalCount).count() >= 2


# ------------------------------------------------------------------ Accesos por área
def test_matriz_de_accesos_por_area(app, s, U):
    from app.models import AlertType, Role
    jl = U("jefe.logistica")
    assert not has_perm(jl, "produccion.ver") and not has_perm(jl, "produccion.partes_ver")
    assert has_perm(jl, "ov.ver") and has_perm(jl, "ingresos.ver") and has_perm(jl, "asistencia.area")
    assert "JEFE_PRODUCCION" not in s.get(AlertType, "QUIEBRE_STOCK").roles
    aux = U("aux.despacho")
    assert has_perm(aux, "guias.estado") and not has_perm(aux, "distribucion.ver") and not has_perm(aux, "distribucion.entrega")
    alm = U("aux.almacen")
    assert has_perm(alm, "stock.cambiar_estado") and has_perm(alm, "rotacion.ver") and has_perm(alm, "alertas.gestionar")
    assert s.get(Role, "COORD_ALMACEN").nombre == "Supervisor de 1524 y 1560"
    assert U("coord.almacen").nombre == "Supervisor de 1524 y 1560"
    c = app.test_client()
    login(c, "jefe.logistica")
    for url in ("/produccion/partes", "/produccion/control", "/produccion/tablero", "/produccion/monitoreo"):
        assert c.get(url).status_code == 403, url
    for url in ("/almacen/ingresos", "/suministro/demanda", "/produccion/asistencia"):
        assert c.get(url).status_code == 200, url
    c2 = app.test_client()
    login(c2, "aux.despacho")
    assert c2.get("/distribucion/").status_code == 403
    assert c2.get("/distribucion/guias").status_code == 200


def test_bases_existentes_retiran_permisos_y_renombran(s, U):
    from app.models import AlertType, Role, RolePermission
    from app.seed import sync_catalogs
    s.add(RolePermission(role_code="JEFE_LOGISTICA", perm_code="produccion.ver", origen="DEFINIDO", fuente="base anterior"))
    s.get(Role, "COORD_ALMACEN").nombre = "Coordinación de Almacén 1560 (producto terminado)"
    t = s.get(AlertType, "QUIEBRE_STOCK")
    t.roles = list(t.roles) + ["JEFE_PRODUCCION"]
    s.flush()
    sync_catalogs()
    assert not has_perm(U("jefe.logistica"), "produccion.ver")
    assert s.get(Role, "COORD_ALMACEN").nombre == "Supervisor de 1524 y 1560"


def test_asistencia_por_area_del_jefe_de_logistica(app, s, U):
    from app.services import attendance
    jl = U("jefe.logistica")
    w = attendance.save_worker(jl, {"nombre": "Auxiliar Logística Ficticio"})
    assert w.area == "Logística"
    attendance.register_day(jl, date.today(), {str(w.id): "ASISTENCIA"})
    pw = attendance.save_worker(U("jefe.produccion"), {"nombre": "Operario Ficticio"})
    assert [x.id for x in attendance.workers_of(jl)] == [w.id]
    assert pw.id not in [x.id for x in attendance.workers_of(jl)]
    assert w.id not in [x.id for x in attendance.workers_of(U("jefe.produccion"))]


def test_pantallas_nuevas_cargan(app):
    rutas = {"jefe.produccion": ["/produccion/partes", "/produccion/monitoreo", "/produccion/plan", "/produccion/liquidaciones",
                                 "/produccion/bom?producto=PT-901"],
             "coord.distribucion": ["/distribucion/flota", "/distribucion/rastreo", "/distribucion/incidencias",
                                    "/distribucion/guias", "/mantenimiento/?tab=flota", "/mantenimiento/?tab=correctivo"],
             "jefe.calidad": ["/mantenimiento/?tab=saneamiento", "/mantenimiento/?tab=unidades"],
             "conductor1": ["/distribucion/mis-entregas"],
             "montacarguista": ["/suministro/movimientos"],
             "coord.almacen": ["/suministro/rotacion", "/almacen/picking", "/almacen/conteos", "/almacen/reempaques"],
             "jefe.ventas": ["/suministro/demanda"]}
    for user, urls in rutas.items():
        c = app.test_client()
        login(c, user)
        for url in urls:
            assert c.get(url).status_code == 200, (user, url)
