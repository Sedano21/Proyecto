"""Observaciones al demo v0.6 – Calidad, Producción y Distribución."""
from datetime import date, timedelta

import pytest

from app.models import StockLot, Vehicle
from app.services.core import BusinessError

from .conftest import alerts_of


def test_analisis_de_calidad_alimenta_el_precertificado(s, U):
    from app.services import quality as q
    lot = s.query(StockLot).filter_by(product_code="PT-905").first()
    cert = q.generate_certificate(lot, U("superv.calidad"))
    assert "pendiente" in cert.datos["organoleptico"][0]["resultado"]
    q.register(U("asist.calidad"), "ANALISIS_LOTE", {"org_color": "Característico", "org_olor_sabor": "Característico",
                                                     "org_aspecto": "Grano entero", "humedad": 12.5},
               lot_id=lot.id, resultado="CONFORME")
    s.flush()
    org = {x["analisis"]: x for x in cert.datos["organoleptico"]}
    assert any(x["resultado"] == "Característico" for x in org.values())
    assert cert.datos["humedad"]["resultado"] == "12.5%"
    assert cert.datos["fecha_vencimiento"] and cert.datos["marca"] is not None


def test_programacion_modificable_con_motivo(s, U):
    from app.services import production as prod
    pl = prod.add_plan(U("jefe.produccion"), "DIA", date.today(), "PT-906", 100, "TRUER")
    with pytest.raises(BusinessError, match="motivo"):
        prod.update_plan(U("jefe.produccion"), pl, 80, "")
    prod.update_plan(U("jefe.produccion"), pl, 80, "Falta de material")
    assert pl.cantidad == 80 and "Falta de material" in pl.comentario


def test_capacidad_vs_producido_y_programado(s, U):
    from app.services import production as prod
    from app.services.reports import produccion_capacidad
    hoy = date.today()
    prod.add_plan(U("jefe.produccion"), "DIA", hoy, "PT-906", 100, "TRUER")
    prod.register_report(U("asist.produccion"), "TRUER", hoy, "PT-906", 1000, granel_kg=930, desmedro_kg=50, mp_kg=10,
                         cal3_kg=10, parada_min=30, motivo_parada="Mantenimiento")
    d = produccion_capacidad(hoy - timedelta(days=2), hoy, "DIA")
    truer = next(f for f in d["filas"] if f["grupo"] == "TRUER")
    jornada = {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0.5, 6: 0}  # sábado medio día, domingo no se opera (15-oct)
    esperado = 12750 * sum(jornada[(hoy - timedelta(days=i)).weekday()] for i in range(3))
    assert truer["capacidad"] == esperado and truer["producido"] == 1000 and truer["proceso"] == "SELECCION"
    assert d["paradas_min"] >= 30
    m = produccion_capacidad(hoy - timedelta(days=40), hoy, "MES")
    assert m["agrupar"] == "MES" and len(m["buckets"]) >= 2


def test_flota_soat_multa_combustible_y_mantenimiento(s, U):
    from app.services import fleet
    from app.models import VehicleDocument
    v = s.query(Vehicle).filter_by(propio=True).first()
    s.query(VehicleDocument).filter_by(vehicle_id=v.id).delete()  # sin el SOAT ficticio de la demostración
    u = U("coord.distribucion")
    fleet.add_document(u, v, "SOAT", "SOAT-1", vencimiento=date.today() + timedelta(days=5))
    fleet.add_fuel(u, v, date.today() - timedelta(days=7), 10000, 20, 300)
    fleet.add_fuel(u, v, date.today(), 10400, 10, 160)
    fleet.add_maintenance(u, v, date.today(), "PREVENTIVO", 10400, "Cambio de aceite", 250, proximo_km=10600)
    multa = fleet.add_document(u, v, "MULTA", "PAP-1", fecha=date.today(), monto=500)
    assert multa.estado == "PENDIENTE"
    st = fleet.status(v)
    assert st["rendimiento"] == 40.0 and st["km_restantes"] == 200
    assert fleet.check_alerts() >= 2
    assert alerts_of(s, "FLOTA_DOCUMENTO", str(v.id)) and alerts_of(s, "FLOTA_MANTENIMIENTO", str(v.id))
    with pytest.raises(BusinessError, match="menor"):
        fleet.add_fuel(u, v, date.today(), 9000, 5)


def test_incidencia_con_entrega_parcial_por_producto(s, U, new_order):
    from app.services import distribution as dist
    o = new_order([("PT-905", 10)])
    l = o.lines[0]
    l.despachado = 10
    o.estado = "DESPACHADA"
    s.flush()
    with pytest.raises(BusinessError, match="productos devueltos"):
        dist.register_incident(U("asist.distribucion"), "PRODUCTO_ROTO", "Bolsas rotas", order=o, entrega="PARCIAL")
    inc = dist.register_incident(U("asist.distribucion"), "PRODUCTO_ROTO", "Bolsas rotas", order=o, entrega="PARCIAL",
                                 lineas=[{"line_id": l.id, "devuelto": 3, "motivo": "rotas"}])
    assert inc.entrega == "PARCIAL" and inc.lineas[0]["recibido"] == 7 and l.entregado == 7
    assert o.estado == "ENTREGA_PARCIAL"


def test_informe_distribucion_a_tiempo_y_costos(s, U):
    from app.services.reports import distribucion
    d = distribucion()
    assert {"pct_a_tiempo", "costo_externo", "costo_estiba", "desviacion"} <= set(d)


def test_detalle_de_traslado(app, s, U):
    from app.services import transfers as tsvc
    from .test_web import login
    lot = s.query(StockLot).filter_by(product_code="PT-901", lote="L901C").one()
    t = tsvc.request_transfer(None, lot.id, "ALM-001", 1, sistema=True)
    s.commit()
    c = app.test_client()
    login(c, "coord.almacen")
    html = c.get(f"/almacen/traslados/{t.id}").get_data(as_text=True)
    assert "Pre-solicitud de traslado" in html and lot.lote in html


def test_capacidad_sin_feriados_ni_domingos(s, U):
    from app.services.core import set_param
    from app.services.reports import produccion_capacidad
    lunes = date(2026, 10, 12)
    set_param("feriados", [lunes.isoformat()], U("sistemas"))
    d = produccion_capacidad(lunes, lunes + timedelta(days=6), "N", 7)  # semana lunes a domingo
    truer = next(f for f in d["filas"] if f["grupo"] == "TRUER")
    assert truer["capacidad"] == 12750 * (4 + 0.5)  # martes-viernes + sábado medio día; lunes feriado, domingo no
