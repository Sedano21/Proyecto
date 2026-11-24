"""V72 (24-nov-2026): reempaque para líderes, supervisores, jefes y coordinadores; vista total de las gerencias;
materiales del plan para Almacén, revisión del plan (capacidad baja, entregas no incluidas, horario extendido) y tiempos
por producto. Solo datos ficticios."""
from datetime import date, timedelta

from app.models import RolePermission

from .test_v64 import _cliente


def test_reempaque_y_gerencias(s):
    def roles(p):
        return {rp.role_code for rp in s.query(RolePermission).filter_by(perm_code=p)}
    assert {"LIDER_ALMACEN", "SUPERV_ALMACEN", "JEFE_LOGISTICA", "JEFE_PRODUCCION", "COORD_ALMACEN", "COORD_VENTAS"} \
        <= roles("reempaque.solicitar")
    assert not roles("reempaque.solicitar") & {"JEFE_CALIDAD", "SUPERV_CALIDAD"}  # Calidad evalúa, no solicita
    assert {"GERENCIA_GENERAL", "GERENTE_GENERAL_ADJUNTO", "GERENTE_COMERCIAL", "GERENTE_ADMIN_FINANZAS"} <= roles("vista.total")
    # ver todo no es aprobar: la Gerencia Comercial no aprueba lo de Producción ni de Calidad
    assert "GERENTE_COMERCIAL" not in roles("produccion.plan_validar") | roles("reempaque.evaluar")


def test_gerencia_comercial_ve_pantallas_de_otras_areas(app, s):
    from app.models import User
    if s.query(User).filter_by(role_code="GERENTE_COMERCIAL").first() is None:
        return
    u = s.query(User).filter_by(role_code="GERENTE_COMERCIAL").first().username
    c = _cliente(app, u)
    for url in ("/almacen/stock", "/produccion/plan", "/almacen/reempaques"):
        assert c.get(url).status_code == 200, url


def test_plan_avisa_materiales_a_almacen_y_revisa(app, s, U):
    from app.models import Alert
    from app.services import plan_produccion_v72 as pv
    from app.services import production as prod
    manana = date.today() + timedelta(days=1)
    prod.add_plans(U("jefe.produccion"), "DIA", [{"fecha": manana, "product_code": "PT-901", "cantidad": 100, "line_code": "R1"}])
    s.commit()
    m = pv.materiales(date.today(), manana)
    assert m["filas"] and all(a["entregar_el"] <= manana for a in m["filas"])
    assert all(not a["componente"].startswith("RE-") for a in m["filas"])
    assert s.query(Alert).filter_by(type_code="PLAN_MATERIALES_ALMACEN").count() >= 1
    r = pv.revision(date.today(), manana)
    assert "baja" in r and "no_incluido" in r and "extendido" in r
    html = _cliente(app, "lider.almacen").get(f"/produccion/plan/materiales?desde={date.today()}&hasta={manana}").get_data(as_text=True)
    assert "Qué entregar a Producción" in html and "PT-901" in html


def test_horario_extendido_cuando_supera_la_capacidad(s, U):
    from app.services import plan_produccion_v72 as pv
    from app.services import production as prod
    from app.services.core import param
    dia = date.today() + timedelta(days=2)
    grupo = next(g for g in param("capacidad_lineas", []) if "SEL_MANUAL" in g.get("lineas", []))
    prod.add_plan(U("jefe.produccion"), "DIA", dia, "MP-901", float(grupo["kg_dia"]) * 3, "SEL_MANUAL")
    s.commit()
    r = pv.revision(dia, dia)
    e = next((f for f in r["extendido"] if "SEL_MANUAL" in f["lineas"]), None)
    assert e is not None and e["horas_extra"] > 0 and e["recomendacion"]


def test_tiempos_por_producto(app, s, U):
    from app.models import ProductionReport
    from app.services import plan_produccion_v72 as pv
    hoy = date.today()
    s.add_all([ProductionReport(linea="SEL_MANUAL", tipo="SELECCION", fecha=hoy, product_code="MP-901", peso_entrada_kg=400,
                                horas=8, operarios=4, estado="CERRADO"),
               ProductionReport(linea="SEL_MANUAL", tipo="SELECCION", fecha=hoy, product_code="MP-903", peso_entrada_kg=800,
                                horas=8, operarios=4, estado="CERRADO"),
               ProductionReport(linea="SEL_MANUAL", tipo="SELECCION", fecha=hoy, product_code="MP-903", peso_entrada_kg=100,
                                hora_inicio="08:00", hora_fin="10:00", operarios=2, estado="CERRADO")])
    s.commit()
    d = pv.tiempos(hoy - timedelta(days=1), hoy, "SEL_MANUAL")
    lentos = [f["producto"] for f in d["filas"]]
    assert lentos.index("MP-901") < lentos.index("MP-903")  # el más lento primero
    f = next(x for x in d["filas"] if x["producto"] == "MP-901")
    assert f["kg_hora"] == 50 and f["kg_hora_operario"] == 12.5
    assert "Tiempos por producto" in _cliente(app, "jefe.produccion").get("/produccion/tiempos").get_data(as_text=True)
