"""Decisiones del 13-oct-2026 (segunda parte): configuración solo de Sistemas, sin Coordinación de Producción, umbral de
compras configurable, reglas configurables (margen por proveedor, excepciones de materiales, conversiones de calidad,
ABC, flota), partes de producción con desmedro (= merma), frescura de cargas SAP, correo deshabilitado, depuración de
datos personales e inicio de sesión con Microsoft 365."""
import os
from datetime import date, datetime, timedelta

import pytest

from app.models import Role, RouteStop, StockLot, User
from app.services import distribution as dist
from app.services import production as prod
from app.services import purchasing as buy
from app.services.core import BusinessError, has_perm, set_param
from app.services.stock import alternatives_for_order

from .conftest import alerts_of


def test_roles_y_configuracion(s, U):
    assert s.get(Role, "COORD_PRODUCCION") is None
    assert s.query(User).filter_by(role_code="ASIST_PRODUCCION").count() == 2
    assert has_perm(U("sistemas"), "config.editar")
    for quien in ("gerente.general", "jefe.ventas", "gerente.operaciones"):
        assert not has_perm(U(quien), "config.editar")
    assert has_perm(U("coord.ventas"), "ov.aprobar_precio") and not has_perm(U("gerente.general"), "ov.aprobar_precio")


def test_umbral_mayor_volumen_en_kg_o_soles(s, U):
    from app.models import Product
    p = s.get(Product, "PT-902")  # 5 kg por unidad
    set_param("umbral_mayor_volumen", 1000.0, U("sistemas"))
    assert buy.is_mayor_volumen(150, p) is False and buy.is_mayor_volumen(200, p) is True  # 200 × 5 = 1000 kg
    set_param("umbral_mayor_volumen_unidad", "SOLES", U("sistemas"))
    assert buy.is_mayor_volumen(200, p) is False  # sin precio cotizado no se evalúa en soles
    assert buy.is_mayor_volumen(200, p, precio=6) is True  # 1200 soles
    r = buy.create_request(U("coord.almacen"), "PT-902", 100)
    buy.approve_logistics(r, U("jefe.logistica"), True)
    buy.quote(r, U("compras"), "Proveedor Demo", "cot", precio=20)  # 2000 soles ≥ 1000
    assert r.mayor_volumen and buy.needs_go_approval(r)


def test_margen_por_proveedor(s, U):
    from app.models import Product
    p = s.get(Product, "EN-901")
    p.proveedor_habitual = "PROVEEDOR DEMO SAC"
    set_param("margen_por_proveedor", {"PROVEEDOR DEMO SAC": 6}, U("sistemas"))
    a = buy.analyze_product(p)
    assert a["margen_dias"] == 6 and any("PROVEEDOR DEMO SAC" in x for x in a["avisos"])


def test_excepcion_a_la_proporcionalidad(s, U):
    base = prod.material_requirements("PT-901", 100)
    en = next(m for m in base["materiales"] if m["componente"] == "EN-901")
    assert en["requerido_base"] == pytest.approx(0.5)
    set_param("excepciones_bom", {"PT-901": {"EN-901": 2}}, U("sistemas"))
    for q in (100, 1000):
        r = prod.material_requirements("PT-901", q)
        assert next(m for m in r["materiales"] if m["componente"] == "EN-901")["requerido_base"] == 2


def test_conversiones_de_calidad_configurables(s, U, new_order):
    s.query(StockLot).filter_by(product_code="MP-901").one().cantidad = 0
    o = new_order([("PT-901", 450)], ruc="20000000003")
    tipos = [x["tipo"] for x in alternatives_for_order(o)[0]["reempaque"]]
    assert "CONVERSION_CALIDAD" in tipos  # PT-906 (SUPERIOR) → PT-901 (EXTRA)
    set_param("conversiones_calidad_permitidas", ["EXTRA>SUPERIOR"], U("sistemas"))
    tipos = [x["tipo"] for x in alternatives_for_order(o)[0]["reempaque"]]
    assert "CONVERSION_CALIDAD" not in tipos


def test_clasificacion_abc(s):
    abc = buy.abc_classes()
    assert abc and set(abc.values()) <= {"A", "B", "C"} and "A" in abc.values()


def test_reglas_de_flota_configurables(s, U, new_order):
    set_param("orden_asignacion_flota", ["TERCERO", "PROPIO"], U("sistemas"))
    o = new_order([("PT-905", 40)])
    assert dist.active_stop(o).route.vehicle.placa == "TER-2T"
    set_param("orden_asignacion_flota", ["PROPIO", "TERCERO"], U("sistemas"))
    set_param("vehiculos_por_zona", {o.distrito: ["DEM-10T"]}, U("sistemas"))
    o2 = new_order([("PT-905", 40)], dias=4)
    assert dist.active_stop(o2).route.vehicle.placa == "DEM-10T"


def test_partes_de_produccion_con_formulas_de_los_formatos(s, U):
    with pytest.raises(BusinessError):  # registra Producción
        prod.register_report(U("coord.ventas"), "CIMBRIA", date.today(), "MP-901", 10795.68)
    # ejemplo de LINEA CIMBRIA: 10 795,68 kg, granel 10 400, desmedro 300 → 96,33 % / 2,78 %
    r = prod.register_report(U("asist.produccion"), "CIMBRIA", date.today(), "MP-901", 10795.68, granel_kg=10400,
                             desmedro_kg=300, of="LQ-P1", horas=5.5)
    assert r.rendimiento_pct == pytest.approx(96.33) and r.desmedro_pct == pytest.approx(2.78)
    assert r.diferencia_kg == pytest.approx(95.68) and r.ratio_kg_hora == pytest.approx(1890.9)
    # ejemplo de ENVASADOS: 2 950 kg de MP, presentación 5 kg, 587 unidades → 99,49 %
    e = prod.register_report(U("asist.produccion2"), "R3", date.today(), "PT-902", 2950, presentacion_kg=5, unidades=587,
                             of="LQ-P2")
    assert e.rendimiento_pct == pytest.approx(99.49) and e.desmedro_pct == pytest.approx(0.51)
    # la merma real de la liquidación se toma del parte (por OF) y dispara la alerta si supera el umbral
    set_param("umbral_merma_pct", 2.0, U("sistemas"))
    liq = prod.register_liquidation(U("asist.produccion"), "LQ-P1", "PT-903", 100, "L-P1", horas=8, operarios=4)
    assert prod.merma_real_pct(liq) == pytest.approx(2.779, rel=1e-3)
    prod.register_report(U("asist.produccion"), "TRUER", date.today(), "MP-901", 1000, granel_kg=950, desmedro_kg=40)
    assert alerts_of(s, "MERMA_FUERA_PARAMETRO")


def test_alerta_si_las_cargas_de_sap_no_se_actualizan(s, U):
    from app.services.scheduler import check_upload_freshness
    n = check_upload_freshness(datetime.now() + timedelta(hours=13))
    a = {x.titulo.split(" ")[2]: x for x in alerts_of(s, "CARGA_SAP_DESACTUALIZADA")}
    assert n >= 2 and "STOCK" in a and "COORD_ALMACEN" in a["STOCK"].roles and "SISTEMAS" in a["STOCK"].roles
    assert "OV" in a  # sin ninguna carga de OV
    assert check_upload_freshness(datetime.now()) >= 1  # OV sigue sin cargas; STOCK al día se cierra
    s.commit()
    assert a["STOCK"].estado == "COMPLETADA"


def test_correo_deshabilitado_alertas_solo_en_sistema(s, U, new_order):
    from app.models import EmailOutbox
    new_order([("PT-903", 10)])
    assert s.query(EmailOutbox).count() == 0


def test_depuracion_de_fotos_segun_retencion(s, U, tmp_path, new_order):
    from app.services.retention import purge_photos
    assert "no configurada" in purge_photos(str(tmp_path))["estado"]
    st = RouteStop(order_id=new_order([("PT-905", 1)]).id, route_id=None, foto_path="foto_x.jpg",
                   entrega_ts=datetime.now() - timedelta(days=400))
    from app.models import Route
    r = Route(fecha=date.today())
    r.stops.append(st)
    s.add(r)
    s.flush()
    (tmp_path / "foto_x.jpg").write_bytes(b"x")
    set_param("retencion_datos_personales_dias", 365, U("sistemas"))
    simul = purge_photos(str(tmp_path))
    assert simul["registros"] == 1 and simul["archivos_borrados"] == 0 and (tmp_path / "foto_x.jpg").exists()
    res = purge_photos(str(tmp_path), aplicar=True)
    assert res["archivos_borrados"] == 1 and not (tmp_path / "foto_x.jpg").exists() and st.foto_path == ""


def test_login_microsoft_365(app, s, U, monkeypatch):
    from app.views import m365
    for k, v in (("M365_CLIENT_ID", "cid"), ("M365_CLIENT_SECRET", "sec"), ("M365_TENANT_ID", "tid")):
        monkeypatch.setenv(k, v)
    U("jefe.ventas").email = "Jefe.Comercial@empresa.pe"
    s.commit()

    class FakeMsal:
        def __init__(self, *a, **k):
            pass

        def initiate_auth_code_flow(self, scopes, redirect_uri):
            return {"auth_uri": "https://login.microsoftonline.com/tid/oauth2/v2.0/authorize?x=1", "state": "st"}

        def acquire_token_by_auth_code_flow(self, flow, args):
            if args.get("state") != flow["state"]:
                raise ValueError("state")
            return {"id_token_claims": {"preferred_username": args.get("u"), "tid": "tid"}}
    monkeypatch.setattr(m365, "_client", lambda: FakeMsal())
    c = app.test_client()
    assert "Microsoft 365" in c.get("/login").get_data(as_text=True)
    r = c.get("/login/microsoft")
    assert r.status_code == 302 and "login.microsoftonline.com" in r.headers["Location"]
    r = c.get("/auth/microsoft/callback?state=st&u=jefe.comercial@empresa.pe")
    assert r.status_code == 302 and c.get("/ov/precios").status_code == 200  # sesión abierta como Jefe Comercial
    c2 = app.test_client()
    c2.get("/login/microsoft")
    c2.get("/auth/microsoft/callback?state=st&u=desconocido@empresa.pe")
    assert c2.get("/ov/precios").status_code == 302  # no registrado: sin sesión
    c3 = app.test_client()
    c3.get("/login/microsoft")
    c3.get("/auth/microsoft/callback?state=OTRO&u=jefe.comercial@empresa.pe")
    assert c3.get("/ov/precios").status_code == 302  # state alterado: rechazado


def test_login_no_redirige_a_sitios_externos(app):
    from .test_web import login
    c = app.test_client()
    r = c.get("/login")
    import re
    tok = re.search(r'name="_csrf" value="([^"]+)"', r.get_data(as_text=True)).group(1)
    r = c.post("/login?next=//sitio-malicioso.com", data={"username": "coord.ventas", "password": "Demo2026!", "_csrf": tok})
    assert r.status_code == 302 and "sitio-malicioso" not in r.headers["Location"]


# ---- Lista de clientes con penalidades y lotes (13-oct-2026) ----------------------------------------------------
def test_condiciones_de_clientes_cargadas_y_vinculadas_por_nombre(s):
    from app.models import Customer, CustomerCondition
    from app.services.customer_conditions import for_customer, summary
    conds = {c.nombre_norm: c for c in s.query(CustomerCondition)}
    assert len(conds) == 4  # el encabezado repetido se omitió
    inst = for_customer(s.query(Customer).filter_by(ruc="20000000005").one())
    assert inst.max_lotes_por_sku == 1 and inst.penalidad_tipos == ["FECHA_ENTREGA"] and inst.vida_util_meses == 6
    rest = for_customer(s.query(Customer).filter_by(ruc="20000000002").one())
    assert rest.max_lotes_por_sku == 2 and set(rest.penalidad_tipos) == {"VENTANA_HORARIA", "FILL_RATE"}
    assert rest.fill_rate_min_pct == 95
    assert conds["CLIENTE DEMO NUEVO S A C"].customer_id is None  # pendiente: se vincula cuando llegue en una OV
    assert "máx. 1 lote" in summary(s.query(Customer).filter_by(ruc="20000000004").one())


def test_regla_de_lotes_por_sku_en_la_reserva(s, U, new_order):
    from app.services.core import set_param
    set_param("aplicar_vida_util_cliente", False)  # se prueba la regla de lotes aislada (la vida útil tiene su prueba)
    # PT-901: L901B (100, vence antes) y L901A (300). Sin condición se usan los dos (FEFO).
    o = new_order([("PT-901", 350)])
    assert {r.lot.lote for r in o.lines[0].reservations if r.estado == "ACTIVA"} == {"L901A", "L901B"}
    osvc_cancel(s, U, o)
    # CATERING: 1 lote por SKU → solo L901A (el único que cubre más); queda faltante en vez de mezclar lotes
    o2 = new_order([("PT-901", 350)], ruc="20000000004")
    lotes = [r.lot.lote for r in o2.lines[0].reservations if r.estado == "ACTIVA"]
    assert lotes == ["L901A"] and o2.estado_stock == "INCOMPLETA"
    osvc_cancel(s, U, o2)
    o3 = new_order([("PT-901", 80)], ruc="20000000004")  # un solo lote lo cubre: se respeta FEFO (L901B vence antes)
    assert [r.lot.lote for r in o3.lines[0].reservations if r.estado == "ACTIVA"] == ["L901B"]
    from app.models import StockLot
    from app.services import orders as osvc
    l901a = s.query(StockLot).filter_by(product_code="PT-901", lote="L901A").one()
    res = o3.lines[0].reservations[0]
    with pytest.raises(BusinessError):  # cambiar parte a otro lote dejaría 2 lotes
        osvc.reassign_pick_lot(o3, U("lider.almacen"), res.id, l901a.id, 10)
    osvc.reassign_pick_lot(o3, U("lider.almacen"), res.id, l901a.id)  # cambio completo: sigue siendo 1 lote


def osvc_cancel(s, U, o):
    from app.services import orders as osvc
    osvc.cancel_order(o, U("jefe.ventas"), "prueba")
    s.commit()


def test_prioridad_por_penalidad_a_igual_fecha(s, U, new_order):
    from app.services.stock import priority_key
    a = new_order([("PT-905", 10)], ruc="20000000001")  # sin penalidades registradas
    b = new_order([("PT-905", 10)], ruc="20000000005")  # PAE: penalidad por fecha de entrega
    assert priority_key(b) < priority_key(a)
    c = new_order([("PT-905", 10)], ruc="20000000005", dias=5)
    assert priority_key(a) < priority_key(c)  # la fecha comprometida manda primero


def test_aviso_fill_rate_en_decision_de_parcial(s, U, new_order):
    o = new_order([("PT-901", 450)], ruc="20000000002")  # restaurantes: penaliza fill rate < 95 %
    a = alerts_of(s, "OV_DECISION_PARCIAL", o.id)[0]
    assert "fill rate < 95%" in a.mensaje
