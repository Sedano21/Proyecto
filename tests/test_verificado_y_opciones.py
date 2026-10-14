"""Observación del 14-oct: nada procede sin el verificado de la persona responsable; el sistema muestra la información
completa de la OV, calcula todas las opciones y recomienda la mejor; quien valida registra por qué elige; penalidad
estimada según las condiciones del cliente; vida útil restante y descripción completa del producto."""
import pytest

from app.models import CustomerCondition, OVDecision, Transfer
from app.services.core import BusinessError

from .test_web import login


def test_opciones_recomendacion_y_eleccion_con_motivo(s, U, new_order):
    from app.services import options
    from app.services.stock import line_reserved
    o = new_order([("PT-901", 99999)])
    ev = options.evaluate(o)
    assert ev and ev[0]["pendiente"] > 0
    rutas = {x["ruta"] for x in ev[0]["opciones"]}
    assert rutas & {"B", "C", "D", "E"}
    assert ev[0]["porque"]  # la recomendación explica por qué
    tr = [p for p in ev[0]["presolicitudes"] if p["tipo"] == "TRASLADO" and p["pendiente"]]
    assert tr
    if tr:  # pre-solicitud de traslado del sistema: no procede ni compromete stock sin verificado
        t = s.get(Transfer, tr[0]["id"])
        assert t.estado == "SOLICITADO"
        with pytest.raises(BusinessError, match="por qué"):
            options.decide(o, U("jefe.logistica"), "TRASLADO", t.id, True, "")
        antes = line_reserved(o.lines[0])
        options.decide(o, U("jefe.logistica"), "TRASLADO", t.id, True, "Llega antes que producción",
                       {"recomendada": ev[0]["recomendada"]["ruta"] if ev[0]["recomendada"] else None})
        assert t.estado == "AUTORIZADO" and line_reserved(o.lines[0]) == antes
        s.flush()
        d = s.query(OVDecision).filter_by(order_id=o.id, tipo="ELECCION_OPCION").one()
        assert d.comentario == "Llega antes que producción" and d.detalle["pre_solicitud"] == "TRASLADO"


def test_penalidad_estimada_por_tipo(s, U, new_order):
    from app.services.customer_conditions import penalty_estimate, set_penalty_amounts
    o = new_order([("PT-905", 99999)], precio=10)
    c = CustomerCondition(nombre="CLIENTE PRUEBA", nombre_norm="CLIENTE PRUEBA", customer_id=o.customer_id,
                          penalidad_tipos=["FILL_RATE", "FECHA_ENTREGA", "VENTANA_HORARIA"], fill_rate_min_pct=98)
    s.add(c)
    s.flush()
    pe = {x["tipo"]: x for x in penalty_estimate(o)}
    assert pe["FILL_RATE"]["riesgo"] and pe["FILL_RATE"]["monto"] > 0
    assert pe["FECHA_ENTREGA"]["riesgo"] and pe["FECHA_ENTREGA"]["monto"] is None
    assert "no definido" in pe["VENTANA_HORARIA"]["base"]
    with pytest.raises(BusinessError):
        set_penalty_amounts(c, U("coord.ventas"), {"FECHA_ENTREGA": ("PCT_OV", "150")})
    set_penalty_amounts(c, U("coord.ventas"), {"FECHA_ENTREGA": ("PCT_OV", "5"), "VENTANA_HORARIA": ("FIJO", "200")})
    pe = {x["tipo"]: x for x in penalty_estimate(o)}
    assert pe["VENTANA_HORARIA"]["monto"] == 200
    assert pe["FECHA_ENTREGA"]["monto"] == pytest.approx(sum(l.cantidad * l.precio_unitario for l in o.lines) * 0.05, rel=1e-6)


def test_pantalla_de_opciones_y_descripcion_de_producto(app, s, U, new_order):
    o = new_order([("PT-901", 99999)])
    s.commit()
    c = app.test_client()
    login(c, "jefe.logistica")
    html = c.get(f"/ov/{o.id}/opciones").get_data(as_text=True)
    assert "Recomendación del sistema" in html and o.lines[0].product.descripcion in html
    html = c.get(f"/ov/{o.id}").get_data(as_text=True)
    assert "Opciones para atender" in html and o.lines[0].product.descripcion in html
    html = c.post(f"/ov/{o.id}/opciones", data={"_csrf": "x"}).status_code
    assert html == 400  # CSRF obligatorio


def test_aprobar_presolicitud_desde_la_pantalla(app, s, U, new_order):
    import re
    o = new_order([("PT-901", 99999)])
    s.commit()
    t = s.query(Transfer).filter_by(order_id=o.id, estado="SOLICITADO").first()
    assert t is not None
    c = app.test_client()
    tok, _ = login(c, "jefe.logistica")
    base = {"_csrf": tok, "tipo": "TRASLADO", "id": t.id, "producto": "PT-901", "accion": "aprobar"}
    r = c.post(f"/ov/{o.id}/opciones", data=dict(base, motivo=""), follow_redirects=True)
    assert "por qué" in r.get_data(as_text=True)
    r = c.post(f"/ov/{o.id}/opciones", data=dict(base, motivo="Más rápido que producir"), follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Decisión registrada" in html and "Más rápido que producir" in html
    s.expire_all()
    assert s.get(Transfer, t.id).estado == "AUTORIZADO"
    assert re.search(r"no válida", c.post(f"/ov/{o.id}/opciones", data={"_csrf": tok, "tipo": "TRASLADO", "motivo": "xxxxxx"},
                                           follow_redirects=True).get_data(as_text=True))


def test_generar_presolicitud_de_traslado_desde_opciones_y_ov_cerrada(app, s, U, new_order):
    from app.services import options
    o = new_order([("PT-901", 99999)])
    s.commit()
    ev = options.evaluate(o)
    c_ops = [x for x in ev[0]["opciones"] if x["ruta"] == "C"]
    assert c_ops and c_ops[0]["destino"]
    antes = s.query(Transfer).filter_by(order_id=o.id).count()
    cl = app.test_client()
    tok, _ = login(cl, "coord.logistica")
    r = cl.post(f"/ov/{o.id}/accion/traslado", data={"_csrf": tok, "volver": "opciones", "lot_id": c_ops[0]["lot_id"],
                                                     "destino": c_ops[0]["destino"], "cantidad": 1, "observacion": "x"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/ov/{o.id}/opciones")
    s.expire_all()
    nuevo = s.query(Transfer).filter_by(order_id=o.id).order_by(Transfer.id.desc()).first()
    assert s.query(Transfer).filter_by(order_id=o.id).count() == antes + 1 and nuevo.estado == "SOLICITADO"
    o.estado = "ENTREGADA"
    assert options.evaluate(o) == []
