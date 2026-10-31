"""Ronda del 23-oct-2026: reuniones con Comercial y Producción, modelo OEE, ventas y margen 2026 y decisiones del usuario."""
import io
from datetime import date, datetime, timedelta

import openpyxl
import pytest

from app.services.core import BusinessError, param, set_param

from .conftest import alerts_of
from .test_web import csrf, login


def _cliente_nuevo(s, U, ruc="20999999901", prospecto=False):
    from app.services import customers as csv_
    c = csv_.save_customer(U("coord.ventas"), None, {"ruc": ruc, "nombre": "CLIENTE NUEVO DEMO", "ubigeo": "150101",
                                                      "prospecto": "1" if prospecto else "0"})
    s.commit()
    return c


# ------------------------------------------------------------------ OV
def test_unidad_fija_por_prefijo_y_oc_obligatoria(s, U, cust, today):
    from app.services import orders as osvc
    assert osvc.unit_for(s.get(__import__("app.models", fromlist=["Product"]).Product, "PT-901")) == "UND"
    assert osvc.unit_for(s.get(__import__("app.models", fromlist=["Product"]).Product, "MP-901")) == "KG"
    with pytest.raises(BusinessError, match="por unidades"):
        osvc.create_order(U("coord.ventas"), "U-1", cust().id, today + timedelta(days=3),
                          [{"product_code": "PT-901", "cantidad": 5, "precio_unitario": 999, "um_venta": "KG"}])
    s.rollback()
    o = osvc.create_order(U("coord.ventas"), "U-2", cust().id, today + timedelta(days=3),
                          [{"product_code": "PT-901", "cantidad": 5, "precio_unitario": 999}])
    s.commit()
    assert o.estado == "BORRADOR" and o.lines[0].um_venta == "UND" and not o.lines[0].reservations
    osvc.attach_oc(o, U("coord.ventas"), "oc_cliente.pdf", "OC-77")
    s.commit()
    assert o.estado != "BORRADOR" and o.oc_numero == "OC-77" and o.estado_stock != "SIN_EVALUAR"
    # la muestra comercial no necesita OC
    m = osvc.create_order(U("coord.ventas"), "U-3", cust().id, today + timedelta(days=3),
                          [{"product_code": "PT-901", "cantidad": 1, "precio_unitario": 0}], tipo_venta="Muestra comercial")
    assert m.estado != "BORRADOR"


def test_corte_de_las_12_para_despachar_manana(s, U, cust):
    from app.services import orders as osvc
    set_param("hora_corte_ov_dia_siguiente", "12:00")
    manana = date.today() + timedelta(days=1)
    with pytest.raises(BusinessError, match="12:00"):
        osvc.check_cutoff(manana, datetime.combine(date.today(), datetime.min.time()).replace(hour=12, minute=30))
    osvc.check_cutoff(manana, datetime.combine(date.today(), datetime.min.time()).replace(hour=11, minute=59))
    osvc.check_cutoff(manana + timedelta(days=1), datetime.combine(date.today(), datetime.min.time()).replace(hour=17))


def test_prospecto_y_condicion_de_pago_con_finanzas(s, U, today):
    from app.services import finance as fin
    from app.services import orders as osvc
    c = _cliente_nuevo(s, U)
    assert c.condicion_estado == "SIN_SOLICITAR" and c.ubigeo == "150101"
    with pytest.raises(BusinessError, match="condición de pago"):
        osvc.create_order(U("coord.ventas"), "C-1", c.id, today + timedelta(days=3),
                          [{"product_code": "PT-901", "cantidad": 2, "precio_unitario": 999}], oc_archivo="oc.pdf")
    s.rollback()
    c = s.merge(c)
    # crédito de S/ 50,000 a 60 días: pide ficha RUC, reporte tributario, resumen ejecutivo, DJ anual y referencias
    assert fin.required_docs("CREDITO", 50000, 60) == ["FICHA_RUC", "REPORTE_TRIBUTARIO", "RESUMEN_EJECUTIVO", "DJ_ANUAL", "REFERENCIAS"]
    assert set(fin.required_docs("CREDITO", 5000, 90)) == set(fin.credit_rules()["documentos"])
    assert fin.required_docs("CONTADO") == []
    with pytest.raises(BusinessError, match="Faltan documentos"):
        fin.request_condition(c, U("vendedor1"), "CREDITO", 20000, 30, {"FICHA_RUC": "f.pdf"})
    with pytest.raises(BusinessError, match="plazo máximo es 30"):
        fin.request_condition(c, U("vendedor1"), "CREDITO", 20000, 45, {})
    fin.request_condition(c, U("vendedor1"), "CREDITO", 20000, 30,
                          {"FICHA_RUC": "a.pdf", "REPORTE_TRIBUTARIO": "b.pdf", "RESUMEN_EJECUTIVO": "c.pdf"})
    s.commit()
    assert c.condicion_estado == "PENDIENTE" and alerts_of(s, "CONDICION_PAGO_SOLICITADA", c.id)
    with pytest.raises(BusinessError):
        fin.resolve_condition(c, U("jefe.ventas"), "APROBADA")
    fin.resolve_condition(c, U("coord.finanzas"), "APROBADA")
    s.commit()
    o = osvc.create_order(U("coord.ventas"), "C-2", c.id, today + timedelta(days=3),
                          [{"product_code": "PT-901", "cantidad": 2, "precio_unitario": 999}], oc_archivo="oc.pdf")
    assert o.estado != "BORRADOR"


def test_prospecto_pasa_a_cliente_con_accion_y_oc(s, U):
    from app.services import opportunities as op
    from app.services import orders as osvc
    c = _cliente_nuevo(s, U, prospecto=True)
    with pytest.raises(BusinessError, match="prospecto"):
        osvc.customer_can_order(c)
    osvc.customer_can_order(c, muestra=True)
    opp = op.save_opportunity(U("vendedor1"), c, {"titulo": "Ingreso de quinua 5 kg", "proyeccion_mensual": "12000"})
    with pytest.raises(BusinessError, match="acción"):
        op.convert_prospect(U("vendedor1"), c, "oc.pdf")
    op.add_action(U("vendedor1"), c, "VISITA", date.today().isoformat(), "Presentación de catálogo", "45", opp)
    q = op.save_quote(U("vendedor1"), c, [{"product_code": "PT-901", "cantidad": "100", "precio": "4.5"}], None, opp)
    assert q.total == 450 and opp.estado == "COTIZADA" and q.numero.startswith("COT-")
    op.convert_prospect(U("vendedor1"), c, "oc.pdf")
    s.commit()
    assert not c.es_prospecto and opp.estado == "GANADA"
    f = op.funnel(U("jefe.ventas"))
    assert f["acciones"] == 1 and f["cotizaciones"] == 1 and f["conversion"] == 100.0


def test_autoaprobacion_de_jefes_y_cambio_de_fecha_por_logistica(s, U, new_order, today):
    from app.services import orders as osvc
    o = new_order([("PT-901", 2)], dias=5)
    req = osvc.request_date_change(o, U("jefe.logistica"), today + timedelta(days=7), "Unidad en mantenimiento")
    s.commit()
    assert alerts_of(s, "OV_CAMBIO_FECHA_SOLICITUD")
    osvc.resolve_change(req, U("coord.ventas"), True)
    s.commit()
    assert o.fecha_compromiso == today + timedelta(days=7)
    # el Jefe Comercial, el Jefe de Producción y el Jefe de Logística pueden aprobar sus propias solicitudes
    from app.services.core import can_self_approve
    assert all(can_self_approve(U(x)) for x in ("jefe.ventas", "jefe.produccion", "jefe.logistica"))
    assert not can_self_approve(U("coord.ventas")) and not can_self_approve(U("asist.ventas"))
    req3 = osvc.request_change(o, U("asist.ventas"), {"comentarios": "x"}, "prueba")
    with pytest.raises(BusinessError):
        osvc.resolve_change(req3, U("asist.ventas"), True)


def test_compromiso_cumple_no_cumple_y_plazo(s, U, new_order):
    from app.services import commitment as cm
    set_param("bloquear_ov_sin_opcion", False)  # aquí se prueba el compromiso; el bloqueo se prueba en test_ronda_26oct
    o = new_order([("PT-901", 1)])
    assert o.compromiso["estado"] in ("CUMPLE", "PENDIENTE")
    o2 = new_order([("PT-902", 999999)])
    assert o2.compromiso["estado"] == "PENDIENTE"
    with pytest.raises(BusinessError, match="por qué"):
        cm.respond(o2, U("coord.almacen"), False)
    cm.respond(o2, U("coord.almacen"), False, "Falta materia prima: se compra", date.today() + timedelta(days=9))
    s.commit()
    a = alerts_of(s, "OV_NO_CUMPLE", o2.id)
    assert a and U("vendedor1").id in a[0].usuarios
    o3 = new_order([("PT-904", 999999)])
    s.commit()
    assert cm.check_pending(datetime.now() + timedelta(hours=25)) >= 1
    assert alerts_of(s, "OV_SIN_COMPROMISO", o3.id)


# ------------------------------------------------------------------ Finanzas
def _excel(path, filas):
    wb = openpyxl.Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    wb.save(path)


def test_facturas_excel_nota_de_credito_pagos_y_vencidas(s, U, cust, tmp_path):
    from app.services import finance as fin
    p = tmp_path / "fact.xlsx"
    _excel(p, [["Número", "Tipo", "RUC", "Fecha", "Vencimiento", "Monto"],
               ["F001-1", "Factura", "20000000001", date.today() - timedelta(days=24), date.today() - timedelta(days=10), 1000],
               ["F001-2", "Factura", "20000000001", date.today(), date.today() + timedelta(days=30), 500],
               ["NC01-1", "Nota de crédito", "20000000001", date.today(), None, 100],
               ["F001-3", "Factura", "99999999999", date.today(), None, 10]])
    with pytest.raises(BusinessError):
        fin.import_invoices_excel(U("vendedor1"), str(p))
    ok, err = fin.import_invoices_excel(U("coord.finanzas"), str(p))
    s.commit()
    assert len(ok) == 3 and len(err) == 1
    from app.models import CustomerInvoice
    f1 = s.query(CustomerInvoice).filter_by(numero="F001-1").one()
    f1.referencia = ""
    nc = s.query(CustomerInvoice).filter_by(numero="NC01-1").one()
    nc.referencia = "F001-1"
    fin._apply_credit_note(nc)
    assert f1.saldo == 900 and f1.estado == "PARCIAL"
    pg = fin.report_payment(U("vendedor1"), cust(), date.today(), 900, "voucher.jpg", f1.id, "transferencia", "OP-1")
    s.commit()
    assert pg.estado == "REPORTADO" and alerts_of(s, "PAGO_REPORTADO")
    fin.confirm_payment(pg, U("coord.finanzas"), True)
    s.commit()
    assert f1.saldo == 0 and f1.estado == "PAGADA"
    f1.estado, f1.saldo = "PENDIENTE", 200  # vuelve a quedar saldo para probar la vencida
    s.commit()
    assert fin.check_overdue() == 1 and fin.check_overdue() == 0
    est = fin.statement(cust())
    assert est["deuda_vencida"] == 200 and est["estado_pago"] == "VENCIDA" and est["deuda"] == 700
    b = fin.collection_board()
    assert b["total_vencido"] == 200 and b["tramos"]["1-15"]


# ------------------------------------------------------------------ margen, objetivos, incentivos, mercado
def test_cascada_de_margen_como_el_archivo(s, U, cust, new_order):
    from app.models import CustomerInvoice
    from app.services import margin as m
    o = new_order([("PT-901", 10)], precio=100.0)  # venta S/ 1,000
    s.add(CustomerInvoice(customer_id=cust().id, order_id=o.id, numero="F-M1", fecha=date.today(), monto=1000, saldo=1000))
    m.save_rates(U("jefe.ventas"), "CLIENTE", cust().id, {"rebate_comercial_pct": 10, "logistica_pct": 3, "b2b_pct": 0.5,
                                                          "no_devolucion_pct": 1})
    m.save_investment(U("jefe.ventas"), cust().id, f"{date.today():%Y-%m}", 50)
    with pytest.raises(BusinessError):
        m.save_rates(U("coord.ventas"), "DEFECTO", "", {})
    s.commit()
    d = m.margin(date.today().replace(day=1), date.today(), "CLIENTE")
    f = d["filas"][0]
    # margen bruto = venta - costo; inversión fija 14.5 % = 145; MCV = MB - 145 - 50 (mercaderismo)
    mb = 1000 - f["costo"]
    assert f["venta"] == 1000 and f["inversion_fija"] == 145 and f["mcv"] == pytest.approx(mb - 195)
    # gastos 1.5 + 3 + 1.42 = 5.92 % = 59.2; IR 29.5 % sobre la utilidad antes de impuestos
    uai = mb - 195 - 59.2
    assert f["gastos"] == pytest.approx(59.2) and f["uai"] == pytest.approx(uai)
    assert f["utilidad_neta"] == pytest.approx(uai * (1 - 0.295), abs=0.02)


def test_objetivos_e_incentivos_configurables(s, U, cust, new_order):
    from app.models import CustomerInvoice
    from app.services import margin as m
    o = new_order([("PT-901", 10)], precio=100.0)
    s.add(CustomerInvoice(customer_id=cust().id, order_id=o.id, numero="F-I1", fecha=date.today(), monto=1000, saldo=1000))
    mes = f"{date.today():%Y-%m}"
    m.save_target(U("jefe.ventas"), mes, "GENERAL", "", 2000)
    m.save_target(U("jefe.ventas"), mes, "VENDEDOR", U("vendedor1").id, 800)
    s.commit()
    t = m.targets_progress(mes)
    gen = next(x for x in t["filas"] if x["t"].alcance == "GENERAL")
    assert gen["facturado"] == 1000 and gen["avance"] == 50.0
    assert m.incentives(mes)["total"] == 0  # sin reglas no hay incentivo
    m.save_rule(U("jefe.ventas"), {"vendedor_id": U("vendedor1").id, "base": "VENTA", "pct": "2", "cumplimiento_min_pct": "100"})
    s.commit()
    inc = m.incentives(mes)
    assert inc["filas"][0]["incentivo"] == 20.0 and inc["filas"][0]["cumplimiento"] == 125.0


def test_precio_de_mercado_del_vendedor_queda_pendiente(s, U):
    from app.services import market
    n = market.add(U("vendedor1"), "COMPETENCIA", [{"producto": "QUINUA", "precio_kg": 9.5, "fecha": date.today(),
                                                    "competidor": "Marca X"}], "Alta manual")
    s.commit()
    pend = market.pending()
    assert n == 1 and len(pend) == 1 and alerts_of(s, "PRECIO_MERCADO_PENDIENTE")
    with pytest.raises(BusinessError):
        market.approve(U("coord.ventas"), [pend[0].id])
    assert market.approve(U("jefe.ventas"), [pend[0].id]) == 1


# ------------------------------------------------------------------ Producción
def test_oee_con_el_ejemplo_del_modelo(s, U):
    """Ejemplo del documento: 90 min planificados, 15 de paro planificado, 10 de tiempo muerto, R2 a 45 und/min,
    2,800 producidas con 300 defectuosas → D 87 %, R 96 %, C 89 %, OEE 74 % (Aceptable)."""
    from app.models import ProductionReport
    from app.services import parte
    r = ProductionReport(linea="R2", tipo="ENVASADO", fecha=date.today(), product_code="PT-905", peso_entrada_kg=700,
                         presentacion_kg=0.25, unidades=2500, defectos={"MAL SELLADO": 300}, refrigerio_min=15,
                         inicio_ts=datetime(2026, 10, 20, 7, 0), fin_ts=datetime(2026, 10, 20, 8, 30), hora_fin="08:30",
                         pausas=[{"inicio": "2026-10-20T07:40:00", "fin": "2026-10-20T07:50:00", "causa": "CAMBIO DE BOBINA"}],
                         operarios=4, maquina="R2")
    parte.compute(r)
    i = r.indicadores
    assert i["td_min"] == 75 and i["tp_min"] == 65 and i["cp"] == 2925 and i["pr"] == 2800
    assert i["disponibilidad"] == pytest.approx(86.7, abs=0.1) and i["rendimiento_oee"] == pytest.approx(95.7, abs=0.1)
    assert i["calidad"] == pytest.approx(89.3, abs=0.1) and i["oee"] == pytest.approx(74.1, abs=0.2)
    assert i["calificacion"] == "Aceptable"


def test_parte_en_linea_ean_pausas_y_desviacion(s, U):
    from app.models import ProductGTIN
    from app.services import parte
    s.add(ProductGTIN(gtin="7750000000017", product_code="PT-901", tipo="EAN13", descripcion="DEMO 500 G"))
    s.commit()
    r = parte.start(U("asist.produccion"), {"linea": "R1", "product_code": "PT-905", "ean": "7750000000017",
                                            "sacos": 4, "peso_saco_kg": 25, "presentacion_kg": 0.25, "und_paquete": 20})
    s.commit()
    assert r.peso_entrada_kg == 100 and r.ean_ok is False and alerts_of(s, "EAN_NO_COINCIDE")
    with pytest.raises(BusinessError, match="lista"):
        parte.pause(U("asist.produccion"), r, "CAUSA INVENTADA")
    parte.pause(U("asist.produccion"), r, "CAMBIO DE BOBINA")
    parte.resume(U("asist.produccion"), r)
    with pytest.raises(BusinessError, match="alcance"):
        parte.pause(U("asist.produccion2"), r, "CAMBIO DE BOBINA")
    parte.finish(U("asist.produccion"), r, {"operarios": 3, "pallets": [{"destino": "DESPACHO", "cantidad": 19}],
                                            "unidades_sueltas": 0, "defectos": {"BAJO PESO": 5}})
    s.commit()
    # 19 paquetes x 20 und = 380 und de 250 g = 95 kg de 100 kg → rendimiento 95 %; peso promedio 0.263 kg
    assert r.unidades == 380 and r.rendimiento_pct == 95.0 and r.estado == "PENDIENTE"
    assert r.indicadores["desviacion_peso_pct"] == pytest.approx(5.26, abs=0.01) and r.indicadores["kg_sobrepeso"] == 5.0
    # selección: desviación = % rendimiento + % desmedro - 100
    sel = parte.start(U("asist.produccion2"), {"linea": "TRUER", "product_code": "GR-901", "peso_entrada_kg": 1000})
    parte.finish(U("asist.produccion2"), sel, {"operarios": 2, "granel_kg": 950, "desmedro_kg": 30})
    assert sel.indicadores["desviacion_pct"] == -2.0
    # Calidad bloquea y libera
    parte.block(U("asist.calidad"), r, "Infestación detectada")
    with pytest.raises(BusinessError):
        parte.set_state(U("asist.produccion"), r, "LIQUIDADO")
    parte.release(U("asist.calidad"), r, "Fumigado", "REPROCESO")
    assert r.estado == "REPROCESO"


def test_liquidacion_bloqueada_por_balance_y_por_horas(s, U):
    from app.services import production as prod
    with pytest.raises(BusinessError, match="horas"):
        prod.register_liquidation(U("asist.produccion"), "OF-B0", "PT-902", 100, "LB0")
    s.rollback()
    # 500 kg de MP en bolsas de 5 kg = 100 bolsas como máximo; declarar 150 bloquea y alerta al Jefe
    liq = prod.register_liquidation(U("asist.produccion"), "OF-B1", "PT-902", 150, "LB1", horas=8, operarios=4, mp_kg=500)
    s.commit()
    assert liq.estado == "BLOQUEADA" and "Balance de masa" in liq.bloqueo["motivos"][0]
    a = alerts_of(s, "LIQUIDACION_BLOQUEADA", liq.id)
    assert a and "JEFE_PRODUCCION" in a[0].roles and not alerts_of(s, "LIQUIDACION_MONTACARGUISTA", liq.id)
    with pytest.raises(BusinessError):
        prod.correct_liquidation(liq, U("asist.produccion"), 99)  # sin motivo
    prod.correct_liquidation(liq, U("asist.produccion"), 99, motivo="Se digitó 150 por 99")
    s.commit()
    assert liq.estado == "REGISTRADA" and alerts_of(s, "LIQUIDACION_MONTACARGUISTA", liq.id)
    liq2 = prod.register_liquidation(U("asist.produccion"), "OF-B2", "PT-902", 90, "LB2", horas=207, operarios=1, mp_kg=500)
    assert liq2.estado == "BLOQUEADA" and "150" in liq2.bloqueo["motivos"][0]


def test_alcance_de_asistentes_cambios_de_programa_y_receta(s, U, today):
    from app.services import attendance as asv
    from app.services import parte
    from app.services import production as prod
    from app.services.core import has_perm
    assert parte.lines_for(U("asist.produccion2")) == ["TRUER", "CIMBRIA", "SEL_MANUAL"]
    assert has_perm(U("asist.produccion"), "produccion.plan_validar")  # aprueba como el Jefe
    assert not has_perm(U("asist.produccion2"), "produccion.plan_validar")
    pl = prod.add_plan(U("asist.produccion2"), "DIA", today, "PT-901", 100, "TRUER")
    s.commit()
    prod.update_plan(U("asist.produccion2"), pl, 80, "Falta de MP")
    s.commit()
    assert pl.cantidad == 100 and pl.cambio_pendiente["cantidad"] == 80 and alerts_of(s, "PROGRAMA_CAMBIO_POR_VALIDAR")
    prod.validate_plan_change(U("asist.produccion"), pl, True)
    assert pl.cantidad == 80 and not pl.cambio_pendiente
    # asistencia: el asistente 1 registra; el 2 no
    w = asv.save_worker(U("asist.produccion"), {"nombre": "Colaborador Demo", "linea": "SEL_MANUAL"})
    assert asv.register_day(U("asist.produccion"), today, {str(w.id): "ASISTENCIA"}) == 1
    with pytest.raises(BusinessError):
        asv.register_day(U("asist.produccion2"), today, {str(w.id): "FALTA"})


def test_control_de_produccion_diario(s, U, today):
    from app.models import ProductionReport
    from app.services import parte
    s.add(ProductionReport(linea="TRUER", tipo="SELECCION", fecha=today, product_code="GR-901", peso_entrada_kg=16000,
                           granel_kg=14970.9, horas=6, indicadores={"horas_efectivas": 6.0}, estado="PENDIENTE"))
    s.commit()
    d = parte.control_report("DIA", today)
    truer = next(f for f in d["filas"] if f["grupo"] == "TRUER")
    # sin plan registrado se compara con la capacidad del día (12,750 kg)
    assert truer["real"] == 14970.9 and truer["kg_h"] == 2495
    assert any("TRUER" in x for x in d["hallazgos"])


def test_fin_de_turno_avisa_al_jefe_y_arrastre(s, U):
    from app.models import Alert
    from app.services import alerts, shifts
    adm = U("sistemas")
    t = shifts.save_shift(adm, "Día", [0, 1, 2, 3, 4, 5, 6], "08:00", "17:00", 60)
    shifts.assign_shift(adm, U("aux.almacen").id, t.id, date.today() - timedelta(days=1))
    a = alerts.emit("LIQUIDACION_MONTACARGUISTA", "Mover PT", "", "Liquidation", 1)
    a.asignado_a = U("aux.almacen").id
    a.creado_ts = datetime.now() - timedelta(days=1)
    s.commit()
    ahora = datetime.combine(date.today(), datetime.min.time()).replace(hour=16, minute=30)
    assert shifts.check_end_of_shift(ahora) == 1 and shifts.check_end_of_shift(ahora) == 0
    av = s.query(Alert).filter_by(type_code="TAREAS_PENDIENTES_FIN_TURNO").one()
    assert "LIDER_ALMACEN" in av.roles
    arr = shifts.pending_carryover(U("aux.almacen"))
    assert arr["filas"] and arr["filas"][0]["alerta"].id == a.id


# ------------------------------------------------------------------ informes y pantallas
def test_arma_tu_informe_por_area_con_grafico_y_recomendaciones(s, U, new_order):
    from app.services import custom_report as cr
    new_order([("PT-901", 3)])
    new_order([("PT-902", 2)], ruc="20000000002")
    por_area = cr.sources_by_area(U("jefe.produccion"))
    assert "Producción" in por_area and any(k == "asistencia" for k, _ in por_area["Producción"])
    assert "facturas" in cr.sources_for(U("coord.finanzas"))
    r = cr.run(U("gerente.general"), "ov", ["cliente", "monto"], hasta=date.today() + timedelta(days=10), agrupar="cliente")
    assert r["kpis"] and isinstance(r["recomendaciones"], list)
    assert cr.chart(r) is not None


def test_pantallas_nuevas_responden(app, s, U, new_order):
    o = new_order([("PT-901", 1)])
    paginas = {"jefe.ventas": ["/ov/oportunidades", "/ov/configuracion", "/ov/margen", "/ov/objetivos", "/ov/incentivos",
                               "/ov/catalogo", "/ov/mercado/aprobar", f"/ov/{o.id}", f"/ov/clientes/{o.customer_id}",
                               "/informes/comercial", "/informes/personalizado?fuente=ov&ver=1&elem=grafico&elem=kpis"],
               "coord.finanzas": ["/finanzas/", f"/ov/clientes/{o.customer_id}"],
               "jefe.produccion": ["/produccion/control", "/produccion/control?periodo=SEMANA", "/produccion/control?periodo=MES",
                                   "/produccion/tablero", "/produccion/asistencia", "/produccion/productividad",
                                   "/produccion/configuracion", "/produccion/partes", "/produccion/liquidaciones",
                                   "/produccion/plan", "/informes/personalizado?fuente=partes&ver=1&agrupar=linea"],
               "sistemas": ["/alertas/configuracion", "/"]}
    for usuario, urls in paginas.items():
        c = app.test_client()
        login(c, usuario)
        for u in urls:
            r = c.get(u)
            assert r.status_code == 200, (usuario, u, r.status_code)
    c = app.test_client()
    login(c, "vendedor1")
    assert c.get("/finanzas/").status_code == 200  # ve la cobranza de consulta
    assert c.get("/ov/configuracion").status_code == 403
