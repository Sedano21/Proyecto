"""V23 (06-nov-2026): OTIF del mes, indicadores comerciales, bandeja de gerencia, devoluciones sin hora de corte,
usuarios de la demostración, flujo ficticio completo, demanda proyectada, cuadro de rutas y tablero del embudo.
Datos ficticios."""
from datetime import date, datetime, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


# ------------------------------------------------------------------ OTIF
def test_otif_base_son_las_ov_que_corresponden_despacharse_en_el_mes(s, U, new_order, today):
    from app.services import comercial_v23 as cv
    a = new_order([("PT-901", 10)], dias=2)   # salió a tiempo y completa
    b = new_order([("PT-901", 10)], dias=2)   # salió tarde
    c = new_order([("PT-901", 10)], dias=2)   # salió incompleta
    d = new_order([("PT-901", 10)], dias=2)   # no salió
    for o, salida, q in ((a, 0, 10), (b, 2, 10), (c, 0, 6)):
        o.salida_ts = datetime.combine(o.fecha_compromiso + timedelta(days=salida), datetime.min.time())
        o.lines[0].despachado = q
    s.commit()
    n = cv.nivel([a, b, c, d], hoy=today)
    assert n["n"] == 4 and n["salieron"] == 3
    assert n["otif"] == 25.0 and n["on_time"] == 50.0 and n["in_full"] == 50.0  # sobre 4, no sobre las que salieron
    assert n["en_plazo"] == 1 and {x["numero"] for x in n["fallas"]} == {b.numero, c.numero}


def test_service_month_usa_la_misma_formula(s, U, new_order):
    from app.services import seguimiento
    o = new_order([("PT-901", 10)], dias=1)
    s.commit()
    d = seguimiento.service_month(desde=o.fecha_compromiso, hasta=o.fecha_compromiso)
    assert d["universo"] == 1 and d["otif"] == 0.0 and d["in_full"] == 0.0 and d["en_plazo"] == 1


def test_indicadores_comerciales_adicionales(s, U, new_order, today):
    from app.services import comercial_v23 as cv
    o = new_order([("PT-901", 10)], dias=1)
    o.salida_ts = datetime.now()
    o.entrega_ts = datetime.now()
    s.commit()
    r = cv.indicadores(today - timedelta(days=5), today, ver_costos=False)
    assert r["recompra"]["activos"] >= 1 and r["recompra"]["tasa"] is not None
    assert r["nuevos"]["n_clientes"] >= 1  # el cliente no tenía OV previas
    assert r["lead"]["n"] >= 1 and r["precio"] and "descuento_pct" in r["precio"][0]
    assert "filas" in r["dso"]


def test_informe_de_gestion_muestra_los_indicadores(app):
    c = _cliente(app, "gerente.comercial")
    h = c.get("/informes/gestion").get_data(as_text=True)
    assert "Tasa de recompra" in h and "DSO comercial" in h and "corresponden despacharse" in h


# ------------------------------------------------------------------ bandeja de gerencia
def test_bandeja_de_gerencia_prioriza_y_consolida(s, U):
    from app.services import alerts
    alerts.emit("LOTE_OBSERVADO", "Lote observado (prueba)", "", "Prueba", "1")
    alerts.emit("COMPRA_SOLICITUD", "Compra por aprobar (prueba)", "", "Prueba", "2")
    for i in range(3):
        alerts.emit("SAP_SIN_CONEXION", f"SAP sin conexión {i}", "", "Prueba", f"s{i}")
    s.commit()
    gg = alerts.gerencia_bandeja(U("gerente.general"))
    assert any(a.type_code == "LOTE_OBSERVADO" for a in gg["prioritarias"])
    assert not any(a.type_code == "COMPRA_SOLICITUD" for a in gg["prioritarias"])
    sap = [t for ar in gg["informativas"] for t in ar["tipos"] if t["code"] == "SAP_SIN_CONEXION"]
    assert sap and sap[0]["n"] == 3  # consolidadas en una fila
    gga = alerts.gerencia_bandeja(U("gerente.adjunto"))
    assert any(a.type_code == "COMPRA_SOLICITUD" for a in gga["prioritarias"])
    a_sap = next(a for a in alerts.inbox(U("gerente.general")) if a.type_code == "SAP_SIN_CONEXION")
    assert not alerts.is_direct(U("gerente.general"), a_sap)  # las informativas no suenan


def test_pantalla_bandeja_de_gerencia(app):
    c = _cliente(app, "gerente.general")
    assert "Prioritarias" in c.get("/alertas/gerencia").get_data(as_text=True)
    assert "Bandeja de gerencia" in c.get("/").get_data(as_text=True)
    c2 = _cliente(app, "coord.almacen")
    assert c2.get("/alertas/gerencia").status_code == 302


# ------------------------------------------------------------------ devoluciones
def test_devolucion_queda_en_el_vehiculo_sin_personal(s, U, new_order):
    from app.services import devoluciones
    o = new_order([("PT-901", 10)])
    r = devoluciones.create_for(o, U("coord.distribucion"), "TOTAL", lineas=[{"line_id": o.lines[0].id, "devuelto": 5}])
    s.commit()
    with pytest.raises(BusinessError, match="motivo"):
        devoluciones.leave_in_vehicle(U("conductor1"), r, "")
    with pytest.raises(BusinessError):
        devoluciones.leave_in_vehicle(U("vendedor1"), r, "x")
    devoluciones.leave_in_vehicle(U("conductor1"), r, "No hay personal de almacén disponible")
    s.commit()
    assert r.estado == "EN_VEHICULO" and r.en_vehiculo["motivo"] and alerts_of(s, "DEVOLUCION_EN_VEHICULO", r.id)
    devoluciones.receive(U("coord.almacen"), r, {str(o.lines[0].id): {"cantidad": 5}})
    s.commit()
    assert r.estado == "CONFORME" and all(a.estado != "PENDIENTE" for a in alerts_of(s, "DEVOLUCION_EN_VEHICULO", r.id))


# ------------------------------------------------------------------ demostración
def test_pagina_de_usuarios_demo(app):
    c = app.test_client()
    h = c.get("/demo/usuarios").get_data(as_text=True)
    assert "Demo2026!" in h and "gerente.general" in h and "jefe.mantenimiento" in h
    app.config["DEMO_MODE"] = False
    assert c.get("/demo/usuarios").status_code == 404
    app.config["DEMO_MODE"] = True


def test_flujo_ficticio_completo_y_analisis(s, app, tmp_path):
    from app.demo_flujo import seed_flow
    from app.models import SalesOrder
    from app.services import comercial_v23 as cv
    from app.services import demanda_v23 as dm
    r = seed_flow(str(tmp_path))
    s.commit()
    assert r and r["historial"]["ok"] > 50 and r["partes_produccion"] > 20 and r["proyeccion"]
    estados = {o.estado for o in s.query(SalesOrder).filter(SalesOrder.numero.like("DF-%"))}
    assert {"ENTREGADA", "EN_RUTA", "PREPARADA", "EN_PREPARACION", "EVALUADA", "REGISTRADA", "CANCELADA"} <= estados
    assert seed_flow(str(tmp_path)) is None
    n = cv.nivel_periodo()
    assert n["n"] > 0
    d = dm.informe()
    assert d["comparativo"]["total_kg"] > 0 and d["cumplimiento"]["filas"] and d["mensajes"]
    sig = (date.today().replace(day=28) + timedelta(days=5)).strftime("%Y-%m")
    d2 = dm.informe(sig)
    assert d2["produccion"]["lineas"] and d2["distribucion"]["kg_por_despachar"] > 0
    c = _cliente(app, "jefe.operaciones")
    assert "Mensaje clave" in c.get("/analisis/demanda").get_data(as_text=True)
    assert c.get("/analisis/demanda?formato=pdf").mimetype == "application/pdf"
    assert c.get("/analisis/demanda?formato=xlsx").status_code == 200
    assert _cliente(app, "aux.almacen").get("/analisis/demanda").status_code == 403


def test_cuadro_de_rutas_y_tablero_del_embudo(app):
    c = _cliente(app, "coord.distribucion")
    h = c.get("/operacion/despacho?vista=cuadro").get_data(as_text=True)
    assert "Cuadro de rutas" in h
    assert c.get("/operacion/despacho?salida=cuadro_xlsx").status_code == 200
    c2 = _cliente(app, "gerente.comercial")
    h2 = c2.get("/operacion/comercial/embudo").get_data(as_text=True)
    assert "Oportunidad por producto" in h2 and "Tipo de cliente" in h2
