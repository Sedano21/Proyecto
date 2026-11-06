"""V22 (06-nov-2026): rutas manuales y cambios, traslados en ruta, peso permitido/real, varios auxiliares, ruta llevada
por otro trabajador, disponibilidad del personal, recepción de devoluciones, pernocte, tickets, mantenimiento de planta,
limpieza, máquinas, perfiles nuevos, sugerencias, embudo y día de operación ficticio. Datos ficticios."""
import os
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


def _drv(s, nombre):
    from app.models import Driver
    return s.query(Driver).filter_by(nombre=nombre).one()


def _veh(s, placa):
    from app.models import Vehicle
    return s.query(Vehicle).filter_by(placa=placa).one()


# ------------------------------------------------------------------ distribución
def test_ruta_manual_con_varios_clientes_auxiliares_y_traslado(s, U, new_order, today):
    from app.services import rutas_manual as rm, transfers
    from app.models import StockLot
    o1 = new_order([("PT-901", 5)], ruc="20000000001")
    o2 = new_order([("PT-905", 20)], ruc="20000000002")
    lote = s.query(StockLot).filter_by(product_code="MP-901").first()
    t = transfers.request_transfer(U("coord.logistica"), lote.id, "ALM-001", 100)
    transfers.authorize(t, U("jefe.logistica"), True)
    s.commit()
    aux = [U("aux.despacho").id, U("aux.despacho2").id]
    r = rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "CHOFER", "vehicle_id": _veh(s, "DEM-4T5").id,
                                                          "driver_id": _drv(s, "Chofer 1").id, "hora_salida": "07:30"},
                         [o1.id, o2.id], [t.id], aux)
    s.commit()
    assert r.manual and r.auxiliares == aux and r.auxiliar_id == aux[0] and len(r.stops) == 2
    assert len(rm.route_transfers(r)) == 1 and r.peso_total >= 100  # el traslado (kg de MP) suma al peso
    d = rm.daily_board(today)
    fila = next(f for f in d["filas"] if f["r"].id == r.id)
    assert len(fila["clientes"]) == 2 and fila["valor"] > 0 and fila["traslados"]
    assert rm.board_excel(today)[:2] == b"PK"
    with pytest.raises(BusinessError, match="ya está en la ruta"):  # un traslado no va en dos rutas
        rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "CHOFER", "vehicle_id": _veh(s, "DEM-10T").id,
                                                          "driver_id": _drv(s, "Chofer 2").id}, [], [t.id])


def test_cambios_a_ruta_confirmada_exigen_motivo_y_quedan_en_el_rastro(s, U, new_order, today):
    from app.services import rutas_manual as rm
    from app.services.distribution import confirm_route
    o1, o2 = new_order([("PT-901", 5)]), new_order([("PT-902", 2)], ruc="20000000003")
    r = rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "CHOFER", "vehicle_id": _veh(s, "DEM-4T5").id,
                                                          "driver_id": _drv(s, "Chofer 1").id}, [o1.id])
    confirm_route(r, U("coord.distribucion"))
    s.commit()
    with pytest.raises(BusinessError, match="motivo"):
        rm.modify(r, U("coord.distribucion"), "", agregar_ov=[o2.id])
    rm.modify(r, U("coord.distribucion"), "El cliente adelantó su pedido", agregar_ov=[o2.id],
              auxiliar_ids=[U("aux.despacho").id, U("aux.despacho3").id])
    s.commit()
    assert len(r.stops) == 2 and len(r.auxiliares) == 2
    assert any(c["campo"] == "OV agregada" and c["motivo"] == "El cliente adelantó su pedido" for c in r.cambios)
    with pytest.raises(BusinessError, match="vacía"):
        rm.modify(r, U("coord.distribucion"), "x", quitar_stop=[st.id for st in r.stops])


def test_ruta_llevada_por_un_vendedor(s, U, new_order, today):
    from app.services import rutas_manual as rm
    o = new_order([("PT-901", 5)])
    with pytest.raises(BusinessError, match="motivo"):
        rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "TRABAJADOR", "t_nombre": "Ejecutivo 1",
                                                          "t_area": "Comercial", "t_vehiculo": "Camioneta"}, [o.id])
    r = rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "TRABAJADOR", "t_nombre": "Ejecutivo 1",
                                                          "t_area": "Comercial", "t_vehiculo": "Camioneta", "t_placa": "ABC-123",
                                                          "t_motivo": "Visita al cliente"}, [o.id])
    from app.services.distribution import confirm_route
    confirm_route(r, U("coord.distribucion"))  # sin vehículo ni chofer de la empresa
    s.commit()
    assert r.estado == "CONFIRMADA" and r.vehicle_id is None and r.transportista["motivo"] == "Visita al cliente"


def test_sobrecarga_peso_permitido_y_real(s, U, new_order, today):
    from app.services import rutas_manual as rm
    v = _veh(s, "DEM-450")
    v.capacidad_real_kg, v.carga_habitual_kg = 500, 400
    o = new_order([("PT-901", 5)])
    r = rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "CHOFER", "vehicle_id": v.id,
                                                          "driver_id": _drv(s, "Chofer 2").id}, [o.id])
    assert rm.overload(r) is None
    msg = rm.set_real_weight(r, U("coord.distribucion"), 470)  # sobre lo permitido (450), bajo la capacidad real
    s.commit()
    assert "permitido" in msg and alerts_of(s, "RUTA_SOBRECARGA", r.id)
    r.peso_real_kg = 520
    assert "capacidad real" in rm.overload(r)
    x = next(f for f in rm.vehicle_load_stats(30) if f["v"].id == v.id)
    assert x["sobrecargas"] == 0 or x["habitual"] == 400  # rutas propuestas no cuentan aún; la carga habitual sí


def test_pernocte_con_foto_del_chofer(s, U, new_order, today):
    from app.services import rutas_manual as rm
    o = new_order([("PT-901", 5)])
    r = rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "CHOFER", "vehicle_id": _veh(s, "DEM-4T5").id,
                                                          "driver_id": _drv(s, "Chofer 1").id}, [o.id])
    with pytest.raises(BusinessError, match="foto"):
        rm.register_overnight(r, U("conductor1"), [])
    with pytest.raises(BusinessError, match="chofer de la ruta"):
        rm.register_overnight(r, U("conductor2"), ["x.jpg"])
    rm.register_overnight(r, U("conductor1"), ["pernocte.jpg"], "12 sacos")
    assert r.pernocte[0]["fotos"] == ["pernocte.jpg"]


# ------------------------------------------------------------------ disponibilidad del personal
def test_chofer_de_vacaciones_no_se_asigna_y_avisa_sus_rutas(s, U, new_order, today):
    from app.services import ausencias, rutas_manual as rm
    from app.services.distribution import propose_routes, update_route
    o = new_order([("PT-901", 5)])
    d1 = _drv(s, "Chofer 1")
    r = rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "CHOFER", "vehicle_id": _veh(s, "DEM-4T5").id,
                                                          "driver_id": d1.id}, [o.id])
    s.commit()
    a = ausencias.register(U("coord.distribucion"), f"DRIVER:{d1.id}", "VACACIONES", today, today + timedelta(days=7))
    s.commit()
    assert alerts_of(s, "PERSONAL_NO_DISPONIBLE", r.id) and "Vacaciones" in ausencias.texto(a)
    o2 = new_order([("PT-902", 2)], ruc="20000000002")
    with pytest.raises(BusinessError, match="no está disponible"):
        rm.create_manual(U("coord.distribucion"), today, {"tipo_transportista": "CHOFER", "vehicle_id": _veh(s, "DEM-10T").id,
                                                          "driver_id": d1.id}, [o2.id])
    with pytest.raises(BusinessError, match="no está disponible"):
        update_route(r, U("coord.distribucion"), driver_id=d1.id)
    assert d1.id in ausencias.unavailable_driver_ids(today)
    for ruta in propose_routes(today, U("coord.distribucion"), orders=[o2], require_prepared=False):
        assert ruta.driver_id != d1.id


def test_faltas_justificada_e_injustificada_y_asistencia(s, U, today):
    from app.models import Attendance, Worker
    from app.services import ausencias
    w = Worker(nombre="COLABORADOR PRUEBA", area="Producción")
    s.add(w)
    s.commit()
    with pytest.raises(BusinessError, match="motivo"):
        ausencias.register(U("gestion.humana"), f"WORKER:{w.id}", "FALTA_JUSTIFICADA", today)
    ausencias.register(U("gestion.humana"), f"WORKER:{w.id}", "FALTA_JUSTIFICADA", today, None, "Duelo familiar")
    s.commit()
    att = s.query(Attendance).filter_by(worker_id=w.id, fecha=today).one()
    assert att.estado == "FALTA JUSTIFICADA" and att.observacion == "Duelo familiar"
    with pytest.raises(BusinessError, match="se cruza"):
        ausencias.register(U("gestion.humana"), f"WORKER:{w.id}", "FALTA_INJUSTIFICADA", today)
    with pytest.raises(BusinessError, match="no registra"):
        ausencias.register(U("vendedor1"), f"WORKER:{w.id}", "VACACIONES", today + timedelta(days=3))


# ------------------------------------------------------------------ devoluciones
def test_devolucion_se_recibe_contra_la_guia_con_evidencia(s, U, new_order, monkeypatch):
    from datetime import datetime
    from app.services import devoluciones
    o = new_order([("PT-901", 10)])
    l = o.lines[0]
    monkeypatch.setattr(devoluciones, "now", lambda: datetime.combine(date.today(), datetime.min.time()).replace(hour=19))
    r = devoluciones.create_for(o, U("coord.distribucion"), "PARCIAL", lineas=[{"line_id": l.id, "devuelto": 4}])
    s.commit()
    # V23: sin hora de corte (aunque llegue a las 19:00, se recibe cuando llega)
    assert r.plazo == date.today() and alerts_of(s, "DEVOLUCION_POR_RECIBIR", r.id)
    datos = {str(l.id): {"cantidad": 3, "presentacion_ok": "1", "danado": "1", "detalle": "saco roto"}}
    with pytest.raises(BusinessError, match="foto o video"):
        devoluciones.receive(U("coord.almacen"), r, datos)
    with pytest.raises(BusinessError, match="Almacén"):
        devoluciones.receive(U("vendedor1"), r, datos, ["f.jpg"])
    difs = devoluciones.receive(U("coord.almacen"), r, datos, ["video.mp4"])
    s.commit()
    assert r.estado == "OBSERVADA" and len(difs) == 2 and alerts_of(s, "DEVOLUCION_OBSERVADA", r.id)


def test_devolucion_sin_plazo_no_vence(s, U, new_order):
    """V23: ya no hay hora de corte ni vencimiento; si no hay personal se reporta y queda en el vehículo (test_v23)."""
    from app.services import devoluciones
    o = new_order([("PT-901", 10)])
    r = devoluciones.create_for(o, U("coord.distribucion"), "PARCIAL", lineas=[{"line_id": o.lines[0].id, "devuelto": 2}])
    r.plazo = date.today() - timedelta(days=3)
    assert devoluciones.check_overdue() == 0 and not alerts_of(s, "DEVOLUCION_VENCIDA", r.id)


# ------------------------------------------------------------------ tickets
def test_ticket_de_averia_y_de_sistemas(s, U, today):
    from app.models import Worker
    from app.services import tickets
    with pytest.raises(BusinessError, match="lugar"):
        tickets.create(U("aux.almacen"), "MANTENIMIENTO", "Luz / eléctrico", "Fluorescente quemado")
    t = tickets.create(U("aux.almacen"), "MANTENIMIENTO", "Luz / eléctrico", "Fluorescente quemado",
                       "Almacén Producto Terminado – Zona B", True, ["luz.jpg"])
    ts = tickets.create(U("vendedor1"), "SISTEMAS", "Tintas / tóner", "Sin tóner en ventas")
    s.commit()
    a = alerts_of(s, "TICKET_MANTENIMIENTO", t.id)[0]
    assert a.prioridad == "ALTA" and "JEFE_MANTENIMIENTO" in a.roles and alerts_of(s, "TICKET_SISTEMAS", ts.id)
    with pytest.raises(BusinessError, match="Mantenimiento"):
        tickets.assign(U("sistemas"), t)
    tec = Worker(nombre="TECNICO PRUEBA", area="Mantenimiento", user_id=U("tecnico.mant1").id)
    s.add(tec)
    s.flush()
    wo = tickets.to_work_order(U("jefe.mantenimiento"), t, today, tec.id)
    s.commit()
    assert wo.zone is not None and wo.zone.nombre == "Almacén Producto Terminado – Zona B" and t.estado == "ASIGNADO"
    tickets.set_state(U("sistemas"), ts, "RESUELTO", "Tóner instalado")
    assert ts.resuelto_ts and tickets.response_times(today - timedelta(days=1), today)
    assert [x.id for x in tickets.visible(U("vendedor1"))] == [ts.id]  # cada uno ve sus tickets


# ------------------------------------------------------------------ mantenimiento de planta
def test_trabajo_con_foto_antes_y_despues_y_avisos_7_3_0(s, U, today):
    from app.models import Worker
    from app.services import mant_trabajos as mt
    tec = Worker(nombre="TECNICO PRUEBA", area="Mantenimiento", user_id=U("tecnico.mant1").id)
    s.add(tec)
    s.flush()
    with pytest.raises(BusinessError, match="Jefe de Mantenimiento"):
        mt.save(U("jefe.produccion"), {"tipo": "PREVENTIVO", "titulo": "x"})
    wo = mt.save(U("jefe.mantenimiento"), {"tipo": "CORRECTIVO", "titulo": "Cambio de luminarias", "fecha_programada": today,
                                          "asignado_worker_id": tec.id})
    assert wo.estado == "ASIGNADA" and alerts_of(s, "TRABAJO_ASIGNADO", wo.id)
    with pytest.raises(BusinessError, match="ANTES"):
        mt.start(U("tecnico.mant1"), wo, [])
    mt.start(U("tecnico.mant1"), wo, ["antes.jpg"])
    with pytest.raises(BusinessError, match="DESPUÉS"):
        mt.finish(U("tecnico.mant1"), wo, [])
    mt.finish(U("tecnico.mant1"), wo, ["despues.jpg"], "listo", [{"pieza": "Fluorescente", "cantidad": "2"}], 30)
    assert wo.estado == "TERMINADA" and mt.report(today, today)["terminados"] == 1
    assert mt.report_excel(today, today)[:2] == b"PK"
    for dias in (7, 3, 0, 5):
        mt.save(U("jefe.mantenimiento"), {"tipo": "PREVENTIVO", "titulo": f"Preventivo {dias}",
                                         "fecha_programada": today + timedelta(days=dias)})
    assert mt.check_alerts(today) == 3 and mt.check_alerts(today) == 0  # 7, 3 y el mismo día; una sola vez
    mt.set_alert_days(U("jefe.mantenimiento"), "5")
    assert mt.alert_days() == [5] and mt.check_alerts(today) == 1


def test_cronograma_desde_excel(s, U, tmp_path, today):
    from openpyxl import Workbook
    from app.services import mant_trabajos as mt
    wb = Workbook()
    ws = wb.active
    ws.append(["Fecha", "Trabajo", "Tipo", "Zona o máquina", "Técnico"])
    ws.append([today + timedelta(days=2), "Lubricación de fajas", "Preventivo", "IQ+CIMB (selección Cimbria)", ""])
    ws.append([(today + timedelta(days=4)).strftime("%d/%m/%Y"), "Revisión de racks", "Preventivo",
               "Almacén Producto Terminado – Miniracks", ""])
    ws.append(["no es fecha", "Mal", "", "", ""])
    f = tmp_path / "crono.xlsx"
    wb.save(f)
    n, err = mt.import_schedule(U("jefe.mantenimiento"), str(f))
    assert n == 2 and len(err) == 1
    rows = mt.board(today, today + timedelta(days=10))
    assert {w.maquina for w in rows} >= {"CIMBRIA"} and any(w.zone for w in rows)


def test_bitacora_de_maquinas_y_paradas(s, U):
    from app.services import mant_trabajos as mt
    with pytest.raises(BusinessError, match="pieza"):
        mt.log_machine(U("jefe.mantenimiento"), "R1", "CAMBIO_PIEZA", "cambio")
    mt.log_machine(U("jefe.mantenimiento"), "CIMBRIA", "CALIBRACION", "Calibración de cámaras", parametros={"sens": "70 %"})
    with pytest.raises(BusinessError):
        mt.log_machine(U("vendedor1"), "R1", "AJUSTE", "x")
    fila = next(m for m in mt.machine_summary() if m["code"] == "CIMBRIA")
    assert fila["calibracion"].parametros == {"sens": "70 %"}


def test_zonas_de_la_planta(s):
    from app.models import SanitationZone
    nombres = {z.nombre for z in s.query(SanitationZone)}
    for z in ("Selección Manual", "Contenedor de fumigación 1", "Contenedor de fumigación 2",
              "Línea de Selección Automática – Cimbria", "Línea de Selección Automática – Truer",
              "Almacén Producto Terminado – Zona A", "Almacén Producto Terminado – Zona B",
              "Almacén Producto Terminado – Miniracks", "Almacén Producto Terminado – Zona C"):
        assert z in nombres


# ------------------------------------------------------------------ limpieza
def test_limpieza_programada_marcada_y_desempeno(s, U, today):
    from app.models import SanitationZone
    from app.services import ausencias, limpieza as lp
    w = lp.save_person(U("jefe.mantenimiento"), {"nombre": "Limpieza prueba", "puesto": "Limpieza",
                                                 "user_id": U("limpieza1").id})
    z1 = s.query(SanitationZone).filter_by(nombre="Selección Manual").one()
    z2 = lp.save_zone(U("jefe.mantenimiento"), {"nombre": "Comedor", "grupo": "Servicios"})
    cs = lp.assign(U("jefe.mantenimiento"), today, w.id, [z1.id, z2.id], veces=2)
    s.commit()
    w_, mias = lp.mine(U("limpieza1"))
    assert w_.id == w.id and len(mias) == 2
    lp.mark(U("limpieza1"), cs[0])
    lp.mark(U("limpieza1"), cs[0])
    with pytest.raises(BusinessError, match="todas"):
        lp.mark(U("limpieza1"), cs[0])
    with pytest.raises(BusinessError, match="persona asignada"):
        lp.mark(U("limpieza2"), cs[1])
    p = lp.performance(today, today)
    assert p["personas"][0]["hechas"] == 2 and p["personas"][0]["programadas"] == 4
    ausencias.register(U("jefe.mantenimiento"), f"WORKER:{w.id}", "VACACIONES", today + timedelta(days=1))
    with pytest.raises(BusinessError, match="no está disponible"):
        lp.assign(U("jefe.mantenimiento"), today + timedelta(days=1), w.id, [z1.id])
    z2b = lp.save_zone(U("jefe.mantenimiento"), {"nombre": "Comedor principal", "grupo": "Servicios"}, z2)
    assert z2b.id == z2.id and z2b.nombre == "Comedor principal"


# ------------------------------------------------------------------ producción: paradas con varias fotos o videos
def test_parada_con_varias_evidencias(s, U):
    from app.services import parte
    r = parte.start(U("asist.produccion"), {"linea": "R1", "product_code": "PT-905", "peso_entrada_kg": 100})
    causa = parte.causes(r.tipo)[0]
    parte.pause(U("asist.produccion"), r, causa, evidencias=["a.jpg", "b.mp4"])
    assert r.pausas[-1]["evidencias"] == ["a.jpg", "b.mp4"] and r.pausas[-1]["foto"] == "a.jpg"


def test_checklist_marca_la_parte_sobre_la_imagen():
    from app.services.vehicle_checklist import parse_marks
    m = parse_marks('[{"vista": 1, "x": 30, "y": 40, "parte": "Espejo izquierdo", "nota": ""}]')
    assert m == [{"x": 30.0, "y": 40.0, "nota": "falla", "parte": "Espejo izquierdo", "vista": 1}]
    with pytest.raises(BusinessError):
        parse_marks('[{"x": 1, "y": 2}]')


# ------------------------------------------------------------------ perfiles
def test_jefe_de_finanzas_solo_ve_alertas_de_presupuesto_superado(s, U):
    from app.services import alerts
    a1 = alerts.emit("PRESUPUESTO_SUPERADO", "Distribución sobre presupuesto", "", "AreaBudget", "1")
    otras = [alerts.emit(t, "otra", "", "X", "1") for t in ("TERCERO_EXPEDIENTE", "PRESUPUESTO_POR_APROBAR", "INCIDENCIA_NC")]
    s.commit()
    jaf = U("jefe.finanzas")
    assert alerts.can_see(jaf, a1) and not alerts.can_see(U("coord.finanzas"), a1)
    assert not any(alerts.can_see(jaf, a) for a in otras)
    assert all(alerts.can_see(U("coord.finanzas"), a) for a in otras)
    from app.services.shifts import _bosses
    assert "JEFE_ADMIN_FINANZAS" not in _bosses(["COORD_FINANZAS"])  # tampoco recibe avisos de escalamiento


def test_gestion_humana_solo_asistencia(app):
    c = _cliente(app, "gestion.humana")
    assert c.get("/produccion/asistencia").status_code == 200
    assert c.get("/operacion/personal/disponibilidad").status_code == 200
    assert c.get("/ov/").status_code == 403 and c.get("/almacen/stock").status_code == 403


def test_inicio_de_gerencia_con_indicadores_por_area(app):
    for u in ("gerente.general", "gerente.adjunto"):
        html = _cliente(app, u).get("/").get_data(as_text=True)
        assert "Indicadores por área" in html and "Mantenimiento y Limpieza" in html and "Distribución (hoy)" in html
    assert "Indicadores por área" not in _cliente(app, "coord.ventas").get("/").get_data(as_text=True)


def test_boton_reportar_averia_en_todas_las_pantallas(app, s):
    from app.models import Ticket
    c = _cliente(app, "montacarguista")
    html = c.get("/").get_data(as_text=True)
    assert 'id="dlg-averia' in html and "Reportar avería" in html
    tok = html.split('name="csrf" content="')[1].split('"')[0]
    r = c.post("/operacion/tickets/nuevo", data={"_csrf": tok, "destino": "MANTENIMIENTO", "categoria": "Luz / eléctrico",
                                                  "descripcion": "Foco quemado en rack", "lugar": "Zona A", "urgente": "1"})
    assert r.status_code == 302 and s.query(Ticket).count() == 1


# ------------------------------------------------------------------ sugerencias, embudo y día de operación
def test_dia_de_operacion_ficticio_y_pantallas(app, s):
    from app.demo_dia import seed_operation_day
    from app.services import sugerencias
    r = seed_operation_day(app.config["UPLOAD_DIR"])
    s.commit()
    assert r and r["rutas_hoy"] >= 4 and r["tickets"] == 6 and r["devoluciones"] == 3 and not r.get("avisos")
    assert seed_operation_day(app.config["UPLOAD_DIR"]) is None  # no se duplica
    titulos = " | ".join(x["titulo"] for x in sugerencias.all_suggestions())
    assert "transporte tercero" in titulos and "sobrecarga" in titulos
    paginas = [("coord.distribucion", "/operacion/despacho"), ("coord.distribucion", "/operacion/flota/cargas"),
               ("coord.distribucion", "/operacion/personal/disponibilidad"), ("coord.almacen", "/operacion/devoluciones"),
               ("coord.almacen", "/operacion/devoluciones?estado=OBSERVADA"), ("jefe.mantenimiento", "/operacion/tickets"),
               ("sistemas", "/operacion/tickets?destino=SISTEMAS"), ("gerente.general", "/operacion/sugerencias"),
               ("jefe.finanzas", "/operacion/finanzas/gastos-por-area"), ("jefe.ventas", "/operacion/comercial/embudo"),
               ("jefe.mantenimiento", "/planta/"), ("jefe.mantenimiento", "/planta/trabajos"), ("jefe.mantenimiento", "/planta/informe"),
               ("jefe.mantenimiento", "/planta/maquinas"), ("jefe.mantenimiento", "/planta/limpieza"), ("limpieza1", "/planta/limpieza"),
               ("tecnico.mant1", "/planta/trabajos"), ("gerente.general", "/"), ("gerente.adjunto", "/"), ("jefe.finanzas", "/"),
               ("gestion.humana", "/produccion/asistencia"), ("conductor1", "/distribucion/mis-entregas"),
               ("coord.distribucion", "/distribucion/ruta/1"), ("conductor1", "/distribucion/ruta/1/checklist"),
               ("jefe.produccion", "/planta/maquinas")]
    for u, p in paginas:
        resp = _cliente(app, u).get(p)
        assert resp.status_code == 200, (u, p)
    assert "veh_camion.jpg" in _cliente(app, "conductor1").get("/distribucion/ruta/1/checklist").get_data(as_text=True)
    assert _cliente(app, "coord.distribucion").get("/operacion/despacho?salida=xlsx").data[:2] == b"PK"
    emb = __import__("app.services.tablero_gg", fromlist=["x"]).funnel(date.today() - timedelta(days=60), date.today())
    assert emb["filas"][0]["n"] == 12 and emb["perdidas"] == 2 and emb["filas"][4]["n"] == 3


def test_imagenes_del_checklist_existen(app):
    from app.catalogs import IMAGENES_CHECKLIST
    for _n, imgs in IMAGENES_CHECKLIST.values():
        for f in imgs:
            assert os.path.exists(os.path.join(app.static_folder, "img", "vehiculos", f)), f
