"""Indicaciones del 29-oct-2026 (V12): Producción y Distribución."""
from datetime import date, datetime, timedelta

import pytest

from app.services.core import BusinessError, set_param

from .conftest import alerts_of
from .test_web import login


def _get(app, user, path):
    c = app.test_client()
    login(c, user)
    r = c.get(path)
    assert r.status_code == 200, (user, path, r.status_code)
    return r.get_data(as_text=True)


def _parte(s, linea="TRUER", estado="EN PROCESO", kg=1000, inicio_min=120, pallets=None, pausas=None):
    from app.models import ProductionReport, now
    r = ProductionReport(linea=linea, tipo="SELECCION", fecha=date.today(), product_code="PT-905", peso_entrada_kg=kg,
                         estado=estado, inicio_ts=now() - timedelta(minutes=inicio_min), pallets=pallets or [],
                         pausas=pausas or [])
    s.add(r)
    s.flush()
    return r


def test_inicio_produccion_lineas_ritmo_paradas(app, s, U):
    from app.models import now
    from app.services import prod_home
    set_param("parada_prolongada_min", 30)
    _parte(s, "TRUER", pallets=[{"destino": "DESPACHO", "cantidad": 400}])  # 400 kg en 120 min → 200 kg/h
    p = _parte(s, "CIMBRIA", estado="PAUSADO", pausas=[{"inicio": (now() - timedelta(minutes=45)).isoformat(timespec="seconds"),
                                                        "fin": None, "causa": "Falta de materia prima"}])
    s.commit()
    h = prod_home.summary()
    truer = next(f for f in h["lineas"] if f["linea"] == "TRUER")
    assert truer["estado"] == "EN PROCESO" and truer["ritmo_fuente"] == "real" and abs(truer["ritmo_kg_h"] - 200) < 1
    assert truer["restante_min"] == 180 and truer["fin_estimado"] is not None
    cim = next(f for f in h["lineas"] if f["linea"] == "CIMBRIA")
    assert cim["estado"] == "PARADA" and cim["parada"]["causa"] == "Falta de materia prima" and cim["parada"]["prolongada"]
    assert h["en_proceso"] == 1 and len(h["paradas"]) == 1
    assert any("parada hace" in t for _, t in h["alertas"])
    assert prod_home.check_long_stops() == 1
    s.flush()
    assert alerts_of(s, "PARADA_PROLONGADA", p.id)
    html = _get(app, "jefe.produccion", "/")
    for txt in ("Producción de hoy", "Estado de las líneas", "Líneas paradas", "Falta de materia prima",
                "Productos pendientes de producción", "Reempaques aprobados por Calidad", "Producirá al cierre"):
        assert txt in html, txt
    assert "Producción de hoy" not in _get(app, "jefe.ventas", "/")


def test_reempaques_solo_aprobados_por_calidad(s, U):
    from app.models import RepackRequest, StockLot
    from app.services import prod_home
    lot = s.query(StockLot).first()
    a = RepackRequest(tipo="ACTUALIZACION_FECHA", lot_id=lot.id, cantidad=5, estado="APROBADA")
    b = RepackRequest(tipo="ACTUALIZACION_FECHA", lot_id=lot.id, cantidad=5, estado="SOLICITADA")
    s.add_all([a, b])
    s.flush()
    ids = {r.id for r in prod_home.summary()["reempaques"]}
    assert a.id in ids and b.id not in ids


def _parte_cerrado(s, linea, colabs, merma_pct=4.0, sobrante=0, kg=500, fecha=None):
    from app.models import ProductionReport
    r = ProductionReport(linea=linea, tipo="SELECCION", fecha=fecha or date.today(), product_code="PT-905",
                         peso_entrada_kg=kg, granel_kg=kg * (1 - merma_pct / 100), desmedro_pct=merma_pct,
                         sobrante_kg=sobrante, estado="PENDIENTE", colaboradores=colabs, horas=8)
    s.add(r)
    s.flush()
    return r


def test_merma_remanente_por_linea_y_persona_con_recomendaciones(app, s, U):
    from app.services import prod_analytics as pa
    for i in range(3):
        _parte_cerrado(s, "SEL_MANUAL", [
            {"nombre": "ANA DEMO", "inicio": "08:00", "fin": "12:00", "kg": 400, "merma_kg": 4, "remanente_kg": 10},
            {"nombre": "LUIS DEMO", "inicio": "08:00", "fin": "12:00", "kg": 200, "merma_kg": 12, "remanente_kg": 0}],
            sobrante=10, fecha=date.today() - timedelta(days=i))
    s.commit()
    d = pa.analyze()
    lin = next(x for x in d["lineas"] if x["linea"] == "SEL_MANUAL")
    assert lin["partes"] == 3 and lin["remanente"] == 30
    ana = next(p for p in d["personas"] if p["nombre"] == "ANA DEMO")
    luis = next(p for p in d["personas"] if p["nombre"] == "LUIS DEMO")
    assert ana["kg_h"] == 100 and luis["kg_h"] == 50 and ana["remanente"] == 30
    textos = " ".join(t for _, t in d["recomendaciones"])
    assert "LUIS DEMO rinde 50" in textos and "capacitación" in textos
    assert "LUIS DEMO genera" in textos and "prestar más atención" in textos
    assert "remanente de MP" in textos
    html = _get(app, "jefe.produccion", "/informes/merma")
    assert "Merma y remanente por línea" in html and "LUIS DEMO" in html and "story-hero" in html
    c = app.test_client()
    login(c, "jefe.produccion")
    pdf = c.get("/informes/merma?formato=pdf").data
    assert pdf[:4] == b"%PDF" and b"/MediaBox [0 0 595" in pdf  # A4 vertical


def test_informes_de_produccion_y_cumplimiento_solo_su_area(app, s, U):
    html = _get(app, "jefe.produccion", "/informes/")
    for t in ("Reempaque", "Control de producción", "Cumplimiento por persona", "Tablero OEE", "Merma y remanente"):
        assert t in html, t
    assert "Movimiento de stock" not in html
    html = _get(app, "jefe.produccion", "/informes/cumplimiento")
    assert "asistencia y rendimiento" in html and "Coordinador de Ventas" not in html and "Acciones" not in html
    assert "Distribución: entregas por chofer" not in html


def test_parte_con_remanente_alerta_a_calidad_operaciones_y_logistica(s, U):
    from app.services import parte as pt
    r = _parte_cerrado(s, "TRUER", [], sobrante=25)
    pt._alert_merma(r, U("jefe.produccion"))
    s.flush()
    a = alerts_of(s, "MERMA_REMANENTE_DESTINO", r.id)
    assert a and "25.0 kg de remanente" in a[0].titulo


def test_movimiento_con_tipo_de_carga_y_reprogramacion(s, U, cust):
    from app.services import supply
    jp = U("jefe.produccion")
    with pytest.raises(BusinessError, match="pallets"):
        supply.request_move(jp, "Línea R2", "Despacho", carga={"tipo": "PALLET_PT", "producto": "PT-905"})
    m = supply.request_move(jp, "Línea R2", "Despacho", carga={"tipo": "PALLET_PT", "cantidad": "3", "producto": "PT-905"})
    assert m.carga == {"tipo": "PALLET_PT", "cantidad": 3, "producto": "PT-905"} and "3 pallet(s) de PT PT-905" in m.detalle
    with pytest.raises(BusinessError, match="cliente"):
        supply.request_move(jp, "Línea R2", "Calidad", carga={"tipo": "MUESTRA", "producto": "PT-905", "cantidad": "2"})
    mu = supply.request_move(jp, "Línea R2", "Calidad", carga={"tipo": "MUESTRA", "producto": "PT-905", "cantidad": "2",
                                                                "customer_id": str(cust().id)})
    assert "para " in mu.detalle
    with pytest.raises(BusinessError, match="materia prima"):
        supply.request_move(jp, "Línea R2", "Almacén MP", carga={"tipo": "REMANENTE", "kg": "12", "mp": "PT-905"})
    mana = (date.today() + timedelta(days=1)).isoformat()
    p = supply.request_move(jp, "Línea R2", "Despacho", carga={"tipo": "MERMA", "kg": "8"},
                            programado_para=supply._when(mana, "10:30"))
    assert p.programado_para.strftime("%H:%M") == "10:30"
    supply.reschedule_move(jp, p, mana, "15:45", "cambió el turno")
    assert p.programado_para.strftime("%H:%M") == "15:45" and p.historial[-1]["evento"] == "REPROGRAMADO"
    with pytest.raises(BusinessError, match="Solo quien solicitó"):
        supply.reschedule_move(U("aux.almacen"), p, mana, "16:00")


def test_proyeccion_contrasta_stock_y_preprograma_por_capacidad(app, s, U):
    from app.models import DemandForecast, LeadTime, Product
    from app.services import demand_plan as dp
    mes = f"{date.today():%Y-%m}"
    s.add(DemandForecast(mes=mes, product_code="PT-905", cantidad=1_000_000))  # más de lo que hay y se puede producir
    mp = s.query(Product).filter(Product.tipo == "MP").first() or s.get(Product, "GR-901")
    mp.categoria_reposicion = "CAT-PRUEBA"
    s.add(LeadTime(categoria="CAT-PRUEBA", dias_min=5, dias_max=10))
    s.add(DemandForecast(mes=mes, product_code=mp.code, cantidad=999_999))
    s.commit()
    d = dp.analyze(mes)
    pt = next(x for x in d["filas"] if x["code"] == "PT-905")
    assert pt["a_producir"] > 0 and pt["reserva"] > 0 and pt["cobertura"] < 100
    assert d["programa"] and d["programa"][0]["linea"]
    assert d["deficit"] and d["kg_deficit"] > 0  # la demanda supera la capacidad del mes
    x = next(p for p in d["presolicitudes"] if p["code"] == mp.code)
    assert x["lead_dias"] == 10 and x["fecha_maxima"] == x["fecha_necesidad"] - timedelta(days=10)
    # cada perfil ve su parte: Producción no ve las presolicitudes de compra
    html = _get(app, "jefe.produccion", "/suministro/demanda")
    assert "Preprogramación de producción" in html and "Presolicitudes de compra" not in html
    html = _get(app, "compras", "/suministro/demanda")
    assert "Presolicitudes de compra" in html and "Preprogramación de producción" not in html
    assert dp.check_purchase_deadlines() >= 1


# ------------------------------------------------------------------ Distribución
def _route(s, U, cust, propio=True):
    from app.models import Driver, Route, RouteStop, Vehicle
    from app.services import orders as osvc
    v = s.query(Vehicle).filter(Vehicle.propio.is_(propio)).first()
    d = s.query(Driver).first()
    o = osvc.create_order(U("coord.ventas"), f"V12-{s.query(Route).count() + 1}", cust().id, date.today() + timedelta(days=3),
                          [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10}], oc_archivo="oc.pdf", evaluar=False)
    r = Route(fecha=date.today(), vehicle_id=v.id, driver_id=d.id, estado="CONFIRMADA")
    s.add(r)
    s.flush()
    s.add(RouteStop(route_id=r.id, order_id=o.id))
    s.flush()
    return r, o


def _vals(m="B", malos=()):
    from app.services.vehicle_checklist import items
    return {c: ("M" if c in malos else m) for c, *_ in items()}


def test_checklist_salida_nn_bloquea_y_seguridad_valida_km(s, U, cust):
    from app.services import vehicle_checklist as vc
    set_param("exigir_checklist_vehicular", True)
    r, _ = _route(s, U, cust)
    assert "Falta el checklist" in vc.can_depart(r)
    with pytest.raises(BusinessError, match="Marque B, M o NA"):
        vc.register(U("coord.distribucion"), r, "SALIDA", {}, km=1000)
    c = vc.register(U("coord.distribucion"), r, "SALIDA", _vals(malos=("INT_FRENO_MANO", "LUZ_CABINA")), km=1000,
                    observaciones="Raspadura puerta izquierda")
    s.flush()
    assert c.nn_fallidos == ["Freno de mano"] and alerts_of(s, "CHECKLIST_OBSERVADO", r.id)
    assert "NO NEGOCIABLES" in vc.can_depart(r)
    c2 = vc.register(U("coord.distribucion"), r, "SALIDA", _vals(), km=1000)
    assert "Seguridad aún no valida" in vc.can_depart(r)
    with pytest.raises(BusinessError, match="Seguridad"):
        vc.validate(U("coord.distribucion"), c2, True, 1001)
    vc.validate(U("seguridad"), c2, True, 1002)
    assert vc.can_depart(r) is None and r.km_salida == 1002 and r.vehicle.km_actual >= 1002


def test_retorno_exige_paso2_y_flujo_almacen_finanzas_nc(s, U, cust):
    from app.models import CustomerInvoice, Incident
    from app.services import incidents_flow as fl
    from app.services import vehicle_checklist as vc
    r, o = _route(s, U, cust)
    r.estado = "EN_RUTA"
    i = Incident(tipo="DEVOLUCION", route_id=r.id, order_id=o.id, descripcion="Cliente devolvió 2 und", entrega="PARCIAL")
    s.add(i)
    s.flush()
    with pytest.raises(BusinessError, match="paso 2"):
        vc.register(U("coord.distribucion"), r, "RETORNO", _vals(), km=1100)
    fl.register_part2(U("coord.distribucion"), i, [{"producto": "PT-905", "cantidad": 2}])
    s.flush()
    assert alerts_of(s, "INCIDENCIA_ALMACEN", i.id)
    vc.register(U("coord.distribucion"), r, "RETORNO", _vals(), km=1100)
    # la OV está facturada en SAP → Finanzas valida la NC; luego Distribución la solicita
    s.add(CustomerInvoice(customer_id=o.customer_id, order_id=o.id, numero="F001-123", fecha=date.today(), monto=59,
                          saldo=59, origen="SAP"))
    s.flush()
    with pytest.raises(BusinessError, match="Almacén"):
        fl.warehouse_confirm(U("coord.distribucion"), i, True)
    fl.warehouse_confirm(U("coord.almacen"), i, True)
    s.flush()
    assert i.flujo["finanzas"]["estado"] == "PENDIENTE" and alerts_of(s, "INCIDENCIA_NC", i.id)
    fl.finance_validate(U("coord.finanzas"), i, True, "Procede por producto devuelto en buen estado")
    assert i.flujo["devolucion"]["tipo"] == "SOLICITUD_NC" and i.flujo["devolucion"]["factura"] == "F001-123"
    fl.request_return(U("coord.distribucion"), i, "SNC-0001")
    assert i.estado == "CERRADA"
    # modificación con motivo y rastro
    with pytest.raises(BusinessError, match="motivo"):
        fl.edit(U("jefe.logistica"), i, {"descripcion": "x"}, "")
    fl.edit(U("jefe.logistica"), i, {"descripcion": "Devolvió 2 und por empaque roto"}, "Detalle del cliente")
    assert i.historial[-1]["motivo"] == "Detalle del cliente"
    with pytest.raises(BusinessError):
        fl.edit(U("aux.almacen"), i, {"descripcion": "y"}, "z")


def test_devolucion_sin_factura_va_a_coordinador(s, U, cust):
    from app.models import Incident
    from app.services import incidents_flow as fl
    r, o = _route(s, U, cust)
    i = Incident(tipo="CANCELACION", route_id=r.id, order_id=o.id, descripcion="Cancelado en ruta")
    s.add(i)
    s.flush()
    fl.register_part2(U("coord.distribucion"), i, [{"producto": "PT-905", "cantidad": 5}])
    fl.warehouse_confirm(U("coord.almacen"), i, True)
    assert "finanzas" not in i.flujo and i.flujo["devolucion"]["tipo"] == "SOLICITUD_DEVOLUCION"


def test_flota_tarjeta_circulacion_avisos_y_mantenimiento_cada_5000(s, U):
    from app.models import Alert, Vehicle
    from app.services import fleet
    v = s.query(Vehicle).filter(Vehicle.propio.is_(True)).first()
    hoy = date.today()
    fleet.add_document(U("coord.distribucion"), v, "TARJETA_CIRCULACION", "TC-1", vencimiento=hoy + timedelta(days=25))
    fleet.add_document(U("coord.distribucion"), v, "SOAT", "S-1", vencimiento=hoy + timedelta(days=20))  # fuera de 14 días
    rt = fleet.add_document(U("coord.distribucion"), v, "REVISION_TECNICA", "RT-1", fecha=hoy - timedelta(days=340))
    assert rt.vencimiento == hoy - timedelta(days=340) + timedelta(days=365)
    v.km_actual = 14_600  # próximo mantenimiento a los 15 000 km (cada 5 000), aviso 500 km antes
    s.flush()
    fleet.check_alerts(hoy)
    s.flush()
    titulos = [a.titulo for a in s.query(Alert).all()]
    assert any("Tarjeta de circulación" in t and "por vencer" in t for t in titulos)
    assert not any(t.startswith("SOAT") and v.placa in t for t in titulos)
    assert any("Mantenimiento próximo" in t and v.placa in t for t in titulos)
    v2 = s.query(Vehicle).filter(Vehicle.id != v.id).first()
    fleet.add_document(U("coord.distribucion"), v2, "SOAT", "S-2", vencimiento=hoy + timedelta(days=1))
    fleet.check_alerts(hoy)
    s.flush()
    assert any("SOAT" in a.titulo and "vence mañana" in a.titulo for a in s.query(Alert).all())


def test_mantenimiento_con_informe_factura_e_incidencia_de_taller(s, U):
    from app.models import Vehicle
    from app.services import fleet, maintenance as mt
    v = s.query(Vehicle).first()
    m = fleet.add_maintenance(U("coord.distribucion"), v, date.today(), "PREVENTIVO", km=5000, costo=450)
    mt.attach_document(U("coord.distribucion"), m, "INFORME", archivo="informe.pdf")
    mt.attach_document(U("compras"), m, "FACTURA", "F001-77", "factura.pdf")  # Compras también registra la factura
    with pytest.raises(BusinessError):
        mt.attach_document(U("compras"), m, "INFORME", archivo="x.pdf")
    mt.workshop_incident(U("coord.distribucion"), m, "Entregó tarde", dias_fuera=3, detalle="Faltaba repuesto")
    assert [d["tipo"] for d in m.documentos] == ["INFORME", "FACTURA"] and m.incidencias_taller[0]["dias_fuera"] == 3


def test_preguia_tras_picking_validacion_y_cambio_de_fecha(s, U, cust):
    from app.services import guides
    from app.services import orders as osvc
    r, o = _route(s, U, cust)
    osvc.finish_preparation(o, U("coord.almacen"))
    s.flush()
    assert o.preguia["estado"] == "POR_VALIDAR" and alerts_of(s, "GUIA_POR_VALIDAR", o.id)
    with pytest.raises(BusinessError, match="Coordinador y el Asistente"):
        guides.validate(U("coord.almacen"), o, True)
    guides.validate(U("asist.distribucion"), o, True, "ok")
    assert o.preguia["estado"] == "VALIDADA" and o.preguia["sap"]["estado"] == "PENDIENTE"  # sin SAP conectado
    manana = date.today() + timedelta(days=1)
    guides.change_date(U("coord.distribucion"), o, manana, "El pedido sale mañana")
    assert o.preguia["fecha_guia"] == manana.isoformat() and o.preguia["cambios"][-1]["motivo"] == "El pedido sale mañana"
    assert r.stops[0].fecha_guia == manana
    # el cambio hecho en SAP también llega al módulo
    assert guides.apply_sap_date(o, "", manana + timedelta(days=1))
    assert o.preguia["cambios"][-1]["origen"] == "SAP"


def test_corte_de_rutas_15_horas(s, U, cust):
    from app.services import guides
    set_param("hora_corte_rutas", "15:00")
    manana = date.today() + timedelta(days=1)
    hoy = datetime.combine(date.today(), datetime.min.time())
    assert guides.after_cutoff(manana, hoy.replace(hour=15, minute=30))
    assert not guides.after_cutoff(manana, hoy.replace(hour=14, minute=59))
    assert not guides.after_cutoff(manana + timedelta(days=1), hoy.replace(hour=16))


def test_guia_en_sap_con_ov_registrada(s, U, cust):
    from app.services import guides
    from app.services import orders as osvc
    from .test_v10 import FakeSL
    r, o = _route(s, U, cust)
    o.sap_docentry, o.sap_docnum = 77, "900077"
    o.lines[0].preparado = 5
    osvc.finish_preparation(o, U("coord.almacen"))
    guides.validate(U("coord.distribucion"), o, True, "ok")
    sl = FakeSL()
    sl._req = (lambda orig: lambda m, p, b=None, headers=None: (sl.llamadas.append((m, p, b, headers)),
                                                                 {"DocEntry": 9, "DocNum": 3009} if p == "DeliveryNotes" else {})[1])(sl._req)
    sap = guides.try_push(o, U("coord.distribucion"), sl)
    m, p, body, _ = sl.llamadas[-1]
    assert (m, p) == ("POST", "DeliveryNotes") and body["DocumentLines"][0]["BaseEntry"] == 77
    assert sap["docnum"] == "3009" and r.stops[0].guia_numero == "3009"
    guides.change_date(U("coord.distribucion"), o, date.today() + timedelta(days=2), "Reprogramado")
    pg = guides.try_push(o, None, sl)
    assert sl.llamadas[-1][:2] == ("PATCH", "DeliveryNotes(9)") and "fecha_pendiente" not in pg


def test_transporte_tercero_flujo_completo(s, U, cust):
    from app.services import third_party as tp
    tp.save_rates(U("coord.distribucion"), [{"destino": "Huachipa", "precio": "750"}], "Tarifario inicial")
    s.flush()
    assert alerts_of(s, "TARIFARIO_MODIFICADO", "")
    with pytest.raises(BusinessError, match="tarifario"):
        tp.save_rates(U("asist.distribucion"), [{"destino": "Lurín", "precio": "700"}])
    with pytest.raises(BusinessError, match="motivo"):
        tp.request_service(U("asist.distribucion"), {"proveedor": "TRANSPORTES DEMO", "destino": "Huachipa", "monto": "900"})
    t = tp.request_service(U("asist.distribucion"), {"proveedor": "TRANSPORTES DEMO", "destino": "Huachipa", "monto": "900",
                                                     "toneladas": "16.8", "customer_id": str(cust().id),
                                                     "motivo_sobre_tarifa": "Unidad de 20 t por volumen"})
    s.flush()
    assert t.tarifa == 750 and alerts_of(s, "TERCERO_SOBRE_TARIFA", t.id) and alerts_of(s, "TERCERO_POR_APROBAR", t.id)
    with pytest.raises(BusinessError, match="aprobada"):
        tp.register_invoice(U("asist.distribucion"), t, {"factura_numero": "E001-1"}, "f.pdf")
    tp.approve(U("gerente.operaciones"), t, True, "ok")
    tp.register_invoice(U("asist.distribucion"), t, {"factura_numero": "e001-907", "centro_costo": "DIST-01",
                                                     "tipo_servicio": "Fletes", "subtipo_servicio": "Despacho de venta"}, "f.pdf")
    s.flush()
    assert t.estado == "FACTURADO" and alerts_of(s, "TERCERO_OC", t.id)
    with pytest.raises(BusinessError, match="Compras"):
        tp.register_po(U("asist.distribucion"), t, "OC-1")
    tp.register_po(U("compras"), t, "OC-1", "oc.pdf")
    t.guia_numero, t.guia = "T001-55", {"numero": "T001-55", "archivo": ""}
    with pytest.raises(BusinessError, match="incompleto"):
        tp.finance_validate(U("coord.finanzas"), t)
    tp.validate_guide(U("coord.distribucion"), t, True, date.today())
    tp.finance_validate(U("coord.finanzas"), t, "Conforme")
    tp.schedule_payment(U("coord.finanzas"), t, date.today() - timedelta(days=1), 400)
    with pytest.raises(BusinessError, match="supera"):
        tp.schedule_payment(U("coord.finanzas"), t, date.today(), 600)
    s.flush()
    assert tp.check_payments() == 1
    tp.register_payment(U("coord.finanzas"), t, 1, "comprobante.pdf")
    assert t.estado == "PAGO_PARCIAL"
    tp.schedule_payment(U("coord.finanzas"), t, date.today(), 500)
    tp.register_payment(U("coord.finanzas"), t, 2, "comprobante2.pdf")
    assert t.estado == "PAGADO"
    tp.register_incident(U("coord.distribucion"), "TRANSPORTES DEMO", "LLEGADA_TARDE", "Llegó 2 h tarde", t)
    ind = next(x for x in tp.provider_indicators() if x["proveedor"] == "TRANSPORTES DEMO")
    assert ind["servicios"] == 1 and ind["sobre_tarifa"] == 1 and ind["incidencias"] == 1 and ind["costo_tn"] == round(900 / 16.8, 2)


def test_presupuesto_modelo_excel_aprobacion_y_alerta_75(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import budget
    from app.services import fleet
    from app.models import Vehicle
    wb = Workbook()
    ws = wb.active
    ws.title = "PRESUPUESTO"
    ws.append([None, None, None, None, "PRESUPUESTO PROYECTADO 2026 - LOGISTICA"])
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
    cab = ["Nombre", "GLOSA 01", "GLOSA 02"]
    for m in meses:
        cab += [f"{m}-{date.today():%y}", f"Real {m}"]
    ws.append(cab)
    ws.append(["DISTRIBUCIÓN CON UNIDADES PROPIAS"])
    fila = ["GASTO DE TRANSPORTE DEMO - COMBUSTIBLE", "CAMIONETA", "ABC123"]
    for _ in meses:
        fila += [1000, 800]
    ws.append(fila)
    ws.append(["MANTENIMIENTOS"])
    v = s.query(Vehicle).first()
    fila = [f"MANTENIMIENTO PREVENTIVO - {v.placa}", "CAMIÓN", v.placa]
    for _ in meses:
        fila += [100, None]
    ws.append(fila)
    p = tmp_path / "pres.xlsx"
    wb.save(p)
    b = budget.import_excel(U("coord.distribucion"), str(p))
    assert len(b.lines) == 2 and b.lines[1].fuente_real == "MANT_PREVENTIVO" and b.lines[0].categoria == "DISTRIBUCIÓN CON UNIDADES PROPIAS"
    with pytest.raises(BusinessError):
        budget.decide(U("coord.finanzas"), b, True)  # aún no enviado
    budget.submit(U("coord.distribucion"), b)
    with pytest.raises(BusinessError, match="Finanzas"):
        budget.decide(U("coord.distribucion"), b, True)
    budget.decide(U("coord.finanzas"), b, True, "Aprobado")
    # el mantenimiento registrado en el módulo cuenta como gasto real de su partida
    fleet.add_maintenance(U("coord.distribucion"), v, date.today(), "PREVENTIVO", km=1, costo=100 * date.today().month)
    c = budget.consumption(b)
    mant = next(f for f in c["filas"] if f["line"].fuente_real == "MANT_PREVENTIVO")
    assert mant["pct"] == 100.0
    assert budget.check_consumption() >= 1  # 80 % combustible + 100 % mantenimiento ≥ 75 %
    with pytest.raises(BusinessError, match="aprobado"):
        budget.save_line(U("coord.distribucion"), b, {"concepto": "x"})


def test_pantallas_de_distribucion_por_perfil(app, s, U, cust):
    from app.models import Incident, ThirdPartyTransport
    from app.services import third_party as tp
    r, o = _route(s, U, cust)
    i = Incident(tipo="DEVOLUCION", route_id=r.id, order_id=o.id, descripcion="Devolución", entrega="PARCIAL")
    s.add(i)
    t = tp.request_service(U("coord.distribucion"), {"proveedor": "PROV DEMO", "destino": "Lurín", "monto": "500"})
    s.commit()
    for user, path, txt in [
            ("coord.distribucion", f"/distribucion/ruta/{r.id}/checklist", "CP-OPE-004"),
            ("seguridad", f"/distribucion/ruta/{r.id}/checklist", "Checklists registrados"),
            ("coord.distribucion", f"/distribucion/incidencias/{i.id}", "Paso 2"),
            ("coord.distribucion", "/distribucion/incidencias", "Falta el paso 2"),
            ("coord.distribucion", "/distribucion/preguias", "Pre-guías"),
            ("coord.distribucion", "/distribucion/terceros", "Tarifario"),
            ("gerente.operaciones", f"/distribucion/terceros/{t.id}", "Aprobación (Gerencia de Operaciones)"),
            ("coord.finanzas", "/distribucion/terceros", "Indicadores por proveedor"),
            ("coord.distribucion", "/distribucion/presupuesto", "Presupuesto de Distribución"),
            ("coord.finanzas", "/distribucion/presupuesto", "Presupuesto de Distribución"),
            ("jefe.logistica", "/informes/distribucion", "Fill rate (unidades)")]:
        assert txt in _get(app, user, path), (user, path)
    c = app.test_client()
    login(c, "jefe.produccion")
    assert c.get("/distribucion/terceros").status_code == 403
    assert c.get("/distribucion/presupuesto").status_code == 403
