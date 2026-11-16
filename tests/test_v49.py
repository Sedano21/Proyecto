"""V49 (16-nov-2026): el plan del Excel se ve día por día en la vista diaria, con un cuadro por línea para agregar,
quitar o modificar; reemplaza lo que antes se subió como plan semanal. Solo datos ficticios."""
from datetime import date, timedelta

import pytest

from .test_v26 import _cliente
from .test_v45 import _xlsx


def _lunes():
    d = date.today() + timedelta(days=7)
    return d - timedelta(days=d.weekday())


def test_vista_diaria_y_cuadro_por_linea(app, s, U, tmp_path):
    from app.models import ProductionPlan
    from app.services import plan_excel
    from app.services.production import add_plan
    lun = _lunes()
    jp = U("jefe.produccion")
    viejo = add_plan(jp, "SEMANA", lun, "PT-901", 300, "R3", "Cargado desde Excel viejo.xlsx")  # subido antes en Semanal
    s.commit()
    p = tmp_path / "plan.xlsx"
    p.write_bytes(_xlsx([["Fecha", "Código", "Cantidad", "Línea"], [lun, "PT-901", 100, "R3"],
                         [lun + timedelta(days=1), "PT-901", 200, "R3"], [lun + timedelta(days=1), "PT-902", 50, "R1"]]))
    r = plan_excel.importar(jp, "DIA", str(p), "plan.xlsx")
    s.commit()
    assert r["creadas"] == 3 and r["reemplazadas"] == 1 and s.get(ProductionPlan, viejo.id) is None
    c = _cliente(app, "jefe.produccion")
    html = c.get(f"/produccion/plan?periodo=DIA&dia={(lun + timedelta(days=1)).isoformat()}").get_data(as_text=True)
    assert "Lo que toca producir el" in html and "Guardar cambios de la línea" in html and "PT-902" in html
    martes = s.query(ProductionPlan).filter_by(fecha=lun + timedelta(days=1), product_code="PT-901").one()
    otro = s.query(ProductionPlan).filter_by(fecha=lun + timedelta(days=1), product_code="PT-902").one()
    # modificar cantidad y línea, quitar uno y agregar otro, en un solo guardado
    datos = {"accion": "linea_dia", "dia": (lun + timedelta(days=1)).isoformat(), "grupo": "RAUMAK 3", "linea_def": "R3",
             "plan_id": [str(martes.id), str(otro.id)], "cantidad": ["250", "50"], "fecha_e": [martes.fecha.isoformat(),
                                                                                             otro.fecha.isoformat()],
             "linea_e": ["R2", "R1"], "quitar": [str(otro.id)], "n_producto": ["PT-905"], "n_cantidad": ["40"],
             "n_linea": ["R3"], "n_comentario": ["urgente (ficticio)"], "motivo": "pedido urgente (ficticio)"}
    with c.session_transaction() as sess:
        tok = sess.get("_csrf") or sess.get("csrf_token")
    if tok:
        datos["_csrf"] = tok
    rr = c.post("/produccion/plan", data=datos, follow_redirects=True)
    s.expire_all()
    assert s.get(ProductionPlan, otro.id) is None
    m = s.get(ProductionPlan, martes.id)
    assert m.cantidad == 250 and m.line_code == "R2"
    assert s.query(ProductionPlan).filter_by(product_code="PT-905", fecha=lun + timedelta(days=1)).count() == 1
    assert rr.status_code == 200


def test_cambio_de_linea_de_un_asistente_queda_por_validar(app, s, U, monkeypatch):
    from app.services import core
    from app.services.production import add_plan, update_plan, validate_plan_change
    pl = add_plan(U("jefe.produccion"), "DIA", _lunes(), "PT-901", 100, "R3", "")
    s.commit()
    real = core.has_perm
    monkeypatch.setattr(core, "has_perm", lambda u, p: False if p == "produccion.plan_validar" else real(u, p))
    update_plan(U("asist.produccion"), pl, 100, "parada de R3 (ficticio)", None, "R1")
    monkeypatch.setattr(core, "has_perm", real)
    assert pl.line_code == "R3" and pl.cambio_pendiente["linea"] == "R1"
    validate_plan_change(U("jefe.produccion"), pl, True)
    assert pl.line_code == "R1"
