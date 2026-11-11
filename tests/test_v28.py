"""V28 (11-nov-2026): ejecución del periodo en la demanda proyectada, historial y retrasos de importaciones, y
conductores con usuario en Flota. Solo datos ficticios."""
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


def test_ejecucion_del_periodo_abiertas_incompletas_cerradas(app, s, new_order):
    from app.services import demanda_v23 as dm
    a = new_order([("PT-901", 10)], dias=2)
    b = new_order([("PT-901", 10)], dias=2)
    c = new_order([("PT-902", 5)], dias=2)
    b.lines[0].despachado = 4
    c.lines[0].despachado = 5
    c.estado = "ENTREGADA"
    s.commit()
    hoy = date.today()
    e = dm.ejecucion(hoy, hoy + timedelta(days=5))
    cat = {x["o"]["oid"]: x["categoria"] for x in e["filas"]}
    assert (cat[a.id], cat[b.id], cat[c.id]) == ("ABIERTA", "INCOMPLETA", "CERRADA")
    assert e["tot"]["INCOMPLETA"]["n"] >= 1
    mes = f"{hoy:%Y-%m}"
    html = _cliente(app, "jefe.operaciones").get(
        f"/analisis/demanda?mes={mes}&desde={hoy.isoformat()}&hasta={(hoy + timedelta(days=5)).isoformat()}&ov=INCOMPLETA"
    ).get_data(as_text=True)
    assert "Ejecución del periodo" in html and b.numero in html and a.numero not in html


def test_importacion_historial_de_status_y_retraso(app, s, U):
    from app.services import importaciones_v24 as imp
    u = U("importaciones")
    hoy = date.today()
    f = imp.save(u, {"codigo_sap": "GR-900", "contrato": "DEMO-1", "proveedor": "Proveedor Demo", "item": "Frijol demo",
                     "contenedores": 2, "fecha_llegada": hoy.isoformat(), "dias_libres": 10})
    s.commit()
    imp.save(u, {"codigo_sap": "GR-900", "contrato": "DEMO-1", "proveedor": "Proveedor Demo", "item": "Frijol demo",
                 "contenedores": 2, "fecha_llegada": hoy.isoformat(), "dias_libres": 10, "status_senasa": "LIBERADO",
                 "status_bl": "PENDIENTE DE LIBERACIÓN DE BL"}, f)
    s.commit()
    h = f.historial_status
    assert h and h[-1]["campo"] == "SENASA" and h[-1]["de"] == "PENDIENTE" and h[-1]["a"] == "LIBERADO" and "T" in h[-1]["ts"]
    with pytest.raises(BusinessError):
        imp.register_delay(u, f, "BL", "", hoy + timedelta(days=3))
    with pytest.raises(BusinessError):
        imp.register_delay(U("vendedor1"), f, "BL", "La naviera no libera", hoy + timedelta(days=3))
    imp.register_delay(u, f, "BL", "La naviera no libera el BL", hoy + timedelta(days=15))
    s.commit()
    assert f.retrasos[-1]["campo"] == "BL" and f.historial_status[-1]["motivo"] == "La naviera no libera el BL"
    a = alerts_of(s, "IMPORT_RETRASO", f.id)
    assert any("sobreestadía" in x.mensaje for x in a)  # la nueva fecha pasa el máximo de retiro (llegada + 10 días)
    imp.register_delay(u, f, "LLEGADA", "Buque reprogramado", hoy + timedelta(days=2))
    s.commit()
    assert f.fecha_llegada == hoy + timedelta(days=2)
    html = _cliente(app, "importaciones").get("/gestion/importaciones").get_data(as_text=True)
    assert "Historial" in html and "Registrar retraso" in html and "Retraso:" in html


def test_flota_muestra_usuarios_conductores(app, s, U):
    from app.models import Driver
    from app.seed import create_user
    nuevo = create_user("conductor.nuevo", "Conductor Nuevo Demo", "CONDUCTOR", "x" * 10, "conductor.nuevo@example.com")
    s.commit()
    assert s.query(Driver).filter_by(user_id=nuevo.id).count() == 0
    html = _cliente(app, "coord.distribucion").get("/distribucion/flota").get_data(as_text=True)
    assert "Conductor Nuevo Demo" in html and "USUARIO" in html and "Agregar conductor externo" in html
    s.expire_all()
    d = s.query(Driver).filter_by(user_id=nuevo.id).one()
    assert not d.externo and d.disponible
