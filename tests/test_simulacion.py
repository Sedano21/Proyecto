"""Simulación integral de operaciones (ENTORNO DE PRUEBAS, 07-nov-2026): generación por los servicios, candados de
salida externa, numeración aparte, validación integral y limpieza que deja la base exactamente como estaba."""
import hashlib

import pytest
from sqlalchemy import text

from app.services.core import BusinessError

from .test_web import login


def _huella(s):
    out = {}
    tablas = [r[0] for r in s.execute(text("select name from sqlite_master where type='table' and name not like 'sqlite_%'"))]
    for t in tablas:
        if t in ("sim_runs", "sim_records", "alembic_version", "audit_log"):
            continue
        filas = sorted(repr(tuple(r)) for r in s.execute(text(f'select * from "{t}"')))
        out[t] = hashlib.md5("\n".join(filas).encode()).hexdigest()
    return out


@pytest.fixture()
def corrida(app, s, U):
    from app import simulacion_escenario as se
    antes = _huella(s)
    run = se.generar(U("sistemas"), app.config["UPLOAD_DIR"], dias=6)
    s.expire_all()
    return run, antes


def test_genera_por_los_servicios_y_valida(app, s, U, corrida):
    from app.models import Route, SalesOrder, VehicleChecklist
    from app.services import simulacion as sim
    from app.services import simulacion_validacion as sv
    run, _ = corrida
    assert run.estado == "GENERADA" and run.resumen["fallas_total"] == 0
    c = run.resumen["conteos"]
    assert c["ov"] >= 30 and c.get("rutas_salieron", 0) > 0 and c.get("entregas_completas", 0) > 0
    ovs = s.query(SalesOrder).filter(SalesOrder.id.in_(sim.ids_creados(run.id, "sales_orders"))).all()
    assert ovs and all(o.numero.startswith("SIM-OV-") for o in ovs)
    assert {o.estado for o in ovs} >= {"ENTREGADA", "EVALUADA"}  # no todo queda completado
    chk = s.query(VehicleChecklist).filter(VehicleChecklist.id.in_(sim.ids_creados(run.id, "vehicle_checklists"))).all()
    assert chk and all(x.driver_id and x.vehicle_id and x.route_id for x in chk)
    assert all(s.get(Route, x.route_id).vehicle.placa.startswith("SIM-") for x in chk), [(x.momento, s.get(Route, x.route_id).vehicle.placa, s.get(Route, x.route_id).estado, x.vehicle.placa) for x in chk if not s.get(Route, x.route_id).vehicle.placa.startswith("SIM-")]
    v = sv.guardar(run, app)
    malos = [x["control"] for x in v["controles"] if not x["ok"]]
    assert not malos, (malos, [p for p in v["pantallas"] if not p["ok"]])
    assert v["indicadores"]["Órdenes recibidas (simulación)"] == len(ovs)
    assert v["evolucion"] and len(v["evolucion"]) == 6
    # la pantalla de la simulación: Sistemas la gestiona; un auxiliar no la ve
    cl = app.test_client()
    login(cl, "sistemas")
    h = cl.get("/admin/simulacion/").get_data(as_text=True)
    assert "ENTORNO DE PRUEBAS" in h and "Validación integral" in h and "Limpiar datos de prueba" in h
    aux = app.test_client()
    login(aux, "aux.almacen")
    assert aux.get("/admin/simulacion/").status_code in (302, 403)
    # el registro de checklists por conductor
    d = chk[0].driver_id
    gg = app.test_client()
    login(gg, "gerente.general")
    h = gg.get(f"/distribucion/checklists?conductor={d}&desde={run.desde.isoformat()}").get_data(as_text=True)
    assert s.get(Route, chk[0].route_id).vehicle.placa in h


def test_con_simulacion_no_salen_notificaciones_ni_se_conecta_a_sap(app, s, U, corrida):
    from app.models import Alert, EmailOutbox
    from app.services import alerts, numeracion, push
    from app.services import simulacion as sim
    from app.services.sap_sl import SapConnectionError, ServiceLayer
    assert sim.hay_simulacion() and sim.bloqueo_externo()
    a = s.query(Alert).first()
    assert push.encolar(a, [U("sistemas").id]) == 0
    n = s.query(EmailOutbox).count()
    U("jefe.logistica").email = "persona.ficticia@ejemplo.test"
    alerts.emit("TRASLADO_SOLICITADO", "Prueba", "Prueba de correo bloqueado")
    s.flush()
    assert s.query(EmailOutbox).count() == n
    sl = ServiceLayer({"url": "https://sap.ejemplo.test", "company": "X", "user": "u", "password": "p", "timeout": 1,
                       "ca": "", "verify": True})
    with pytest.raises(SapConnectionError, match="ENTORNO DE PRUEBAS|simulación"):
        sl._req("GET", "Items")
    assert not numeracion.next_order_number().startswith("SIM-")  # fuera de la simulación, la numeración real


def test_limpieza_deja_la_base_como_estaba(app, s, U, corrida):
    from app.models import SimRun
    from app.services import simulacion as sim
    run, antes = corrida
    r = sim.limpiar(U("sistemas"), app.config["UPLOAD_DIR"])
    s.commit()
    assert r["eliminados"] > 500 and r["no_encontrados"] == 0
    assert _huella(s) == antes
    assert s.get(SimRun, run.id).estado == "LIMPIADA" and not sim.hay_simulacion()
    with pytest.raises(BusinessError, match="Ya hay"):  # no se generan dos simulaciones a la vez
        from app import simulacion_escenario as se
        se.generar(U("sistemas"), app.config["UPLOAD_DIR"], dias=5)
        se.generar(U("sistemas"), app.config["UPLOAD_DIR"], dias=5)


def test_solo_en_entorno_de_pruebas(app, monkeypatch):
    from app.services import simulacion as sim
    monkeypatch.delenv("SIMULACION_HABILITADA", raising=False)
    app.config["DEMO_MODE"] = False
    assert "ENTORNO DE PRUEBAS" in (sim.habilitada(app) or "")
    monkeypatch.setenv("SIMULACION_HABILITADA", "1")
    assert sim.habilitada(app) is None


def test_entrega_parcial_las_lineas_no_devueltas_quedan_entregadas(s, U, new_order, today):
    from app.services import distribution as dist
    from tests.test_flujos import _user_chofer, dispatch
    o = new_order([("PT-905", 50), ("PT-901", 20)])
    stop = dispatch(s, U, o, today)
    l905, l901 = o.lines
    dist.register_incident(_user_chofer(s, U, stop), "PRODUCTO_ROTO", "Empaque dañado", stop=stop, order=o, entrega="PARCIAL",
                           lineas=[{"line_id": l905.id, "devuelto": 5, "motivo": "Empaque dañado"}])
    assert o.estado == "ENTREGA_PARCIAL"
    assert l905.entregado == l905.despachado - 5 and l901.entregado == l901.despachado
