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
