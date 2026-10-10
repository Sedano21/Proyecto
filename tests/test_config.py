"""Configuración versionada, auditoría, preferencias de Gerencia General, rutas y capacidad, KPIs."""
from datetime import date

import pytest

from app.models import AuditLog, GGAlertPreference, ParamHistory, Route
from app.services import distribution as dist
from app.services.core import BusinessError, param, set_param

from .test_web import csrf, login


def test_parametros_versionados_y_auditados(s, U):
    set_param("umbral_merma_pct", 3.5, U("sistemas"), "DEFINIDO")
    set_param("umbral_merma_pct", 4.0, U("gerente.general"))
    s.commit()
    hist = s.query(ParamHistory).filter_by(key="umbral_merma_pct").order_by(ParamHistory.version).all()
    assert [h.valor["v"] for h in hist] == [3.5, 4.0] and param("umbral_merma_pct") == 4.0
    assert s.query(AuditLog).filter_by(accion="PARAM_EDITADO", entidad_id="umbral_merma_pct").count() == 2


def test_merma_fuera_de_parametro(s, U):
    from app.services.production import register_liquidation
    set_param("umbral_merma_pct", 1.0, U("sistemas"))
    register_liquidation(U("asist.produccion"), "LQ-M", "PT-901", 100, "LM1", merma_mp_kg=5)  # 5/(50+5)=9 %
    s.commit()
    from .conftest import alerts_of
    assert alerts_of(s, "MERMA_FUERA_PARAMETRO")


def test_gg_preferencias_por_web(app):
    c = app.test_client()
    login(c, "gerente.general")
    tok = csrf(c, "/alertas/preferencias")
    r = c.post("/alertas/preferencias", data={"_csrf": tok, "directo": ["OV_FALTANTE", "INC_RECHAZO_CALIDAD"]},
               follow_redirects=True)
    assert r.status_code == 200
    from app.db import SessionLocal
    from app.models import User
    s = SessionLocal()
    uid = s.query(User).filter_by(username="gerente.general").one().id
    directas = {p.type_code for p in s.query(GGAlertPreference).filter_by(user_id=uid, recibir_directo=True)}
    assert directas == {"OV_FALTANTE", "INC_RECHAZO_CALIDAD"}
    c2 = app.test_client()
    login(c2, "coord.almacen")
    assert c2.get("/alertas/preferencias").status_code == 403


def test_exportaciones(app):
    c = app.test_client()
    login(c, "sistemas")
    for e in ["ov", "stock", "alertas", "auditoria", "compras", "produccion", "incidencias", "rutas", "calidad", "liquidaciones"]:
        r = c.get(f"/exportar/{e}.xlsx")
        assert r.status_code == 200 and r.data[:2] == b"PK", e
    c2 = app.test_client()
    login(c2, "asist.ventas")
    assert c2.get("/exportar/ov.xlsx").status_code == 403


def test_propuesta_rutas_capacidad_y_externo(s, U, new_order):
    # pedidos grandes que superan unidades propias disponibles en una zona
    o1 = new_order([("PT-905", 900)], ruc="20000000001")   # 225 kg, ATE
    o2 = new_order([("PT-902", 40)], ruc="20000000004")    # 200 kg, ATE
    rutas = dist.propose_routes(o1.fecha_compromiso, U("coord.distribucion"), orders=[o1, o2], require_prepared=False)
    s.commit()
    assert len(rutas) == 1 and rutas[0].vehicle.capacidad_kg >= 425  # agrupa la zona ATE en una unidad suficiente
    assert rutas[0].vehicle.placa == "DEM-450"
    from app.models import Vehicle
    for v in s.query(Vehicle):
        v.disponible = False
    o3 = new_order([("PT-905", 50)], ruc="20000000005")
    r3 = dist.propose_routes(o3.fecha_compromiso, U("coord.distribucion"), orders=[o3], require_prepared=False)
    assert r3[0].vehicle_id is None and r3[0].requiere_externo
    assert any("transporte externo" in a for a in r3[0].advertencias)
    with pytest.raises(BusinessError):
        dist.confirm_route(r3[0], U("coord.distribucion"))


def test_cita_no_confirmada_advierte(s, U, new_order):
    o = new_order([("PT-905", 10)], ruc="20000000002")
    r = dist.propose_routes(o.fecha_compromiso, U("coord.distribucion"), orders=[o], require_prepared=False)
    assert any("cita" in a for a in r[0].advertencias)


def test_salida_exige_pedidos_preparados(s, U, new_order):
    o = new_order([("PT-905", 10)])
    r = dist.propose_routes(o.fecha_compromiso, U("coord.distribucion"), orders=[o], require_prepared=False)[0]
    dist.confirm_route(r, U("coord.distribucion"))
    lines = [{**e, "guia": e["esperado"], "cargado": e["esperado"]} for e in dist.expected_lines(r)]
    dist.register_security_check(r, U("seguridad"), "G1", lines)
    with pytest.raises(BusinessError):
        dist.confirm_departure(r, U("coord.distribucion"), {k: True for k, _ in dist.CHECKLIST})
