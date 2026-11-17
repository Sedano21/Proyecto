"""V54 (17-nov-2026): la OV del módulo toma el estado de SAP (guías, cierre, anulación); el cumplimiento con el cliente
usa las guías de SAP; las OV bloqueadas por reglas apagadas se reactivan; el motivo del bloqueo se ve en expedientes."""
from datetime import date, timedelta

from .test_v26 import _cliente


def _guia(s, docentry, ov, code, q, fecha=None, linea=0):
    from app.models import SapMovement
    s.add(SapMovement(clave=f"GUIA:{docentry}:{linea}", tipo="GUIA", docentry=docentry, documento=f"EG07-{docentry}",
                      fecha=fecha or date.today(), ov_numero=ov, product_code=code, cantidad=q))


def _sap_ov(s, docnum, code, q, estado="ABIERTA", cliente="x"):
    from app.models import SapOrderLine
    s.add(SapOrderLine(docnum=docnum, clase="VENTA", serie="OV", fecha=date.today(), fecha_entrega=date.today(),
                       cliente=cliente, estado=estado, product_code=code, descripcion="x", cantidad=q, entregado=0,
                       linea_cerrada=False))


def test_guia_parcial_y_luego_completa(app, s, U, new_order):
    from app.services import ov_sap
    o = new_order([("MP-902", 10)])
    o.sap_docnum = "9000001"
    _guia(s, 7001, "9000001", "MP-902", 4)
    s.commit()
    r = ov_sap.sincronizar(None)
    s.commit()
    assert o.numero in r["parciales"] and o.estado == "DESPACHO_PARCIAL"
    ln = o.lines[0]
    assert ln.despachado == 4 and o.salida_ts is not None
    assert sum(x.cantidad for x in ln.reservations if x.estado == "ACTIVA") <= 6 + 1e-9  # solo reserva el saldo
    _guia(s, 7002, "9000001", "MP-902", 6)
    s.commit()
    r = ov_sap.sincronizar(None)
    s.commit()
    assert o.numero in r["despachadas"] and o.estado == "DESPACHADA" and ln.despachado == 10
    assert not [x for x in ln.reservations if x.estado == "ACTIVA"]


def test_ov_anulada_y_cerrada_en_sap(app, s, U, new_order):
    from app.services import ov_sap
    a = new_order([("MP-902", 5)])
    b = new_order([("MP-902", 5)], ruc="20000000004")
    a.sap_docnum, b.sap_docnum = "9000002", "9000003"
    _sap_ov(s, "9000002", "MP-902", 5, "CANCELADA")
    _sap_ov(s, "9000003", "MP-902", 5, "CERRADA")
    _guia(s, 7003, "9000003", "MP-902", 2)
    s.commit()
    ov_sap.sincronizar(None)
    s.commit()
    assert a.estado == "CANCELADA" and "SAP" in a.cancelacion_motivo
    assert b.estado == "CERRADA" and "parcial" in b.motivo_detencion


def test_bloqueada_por_regla_apagada_se_reactiva(app, s, U, new_order):
    from app.services import ov_sap
    from app.services.core import set_param
    o = new_order([("MP-902", 5)])
    assert ov_sap.reactivar_bloqueadas(None) == []
    o.estado = "BLOQUEADA"
    o.bloqueo_ov = {"tipo": "EMISION", "estado": "RENEGOCIAR", "motivo": "Se emitió tarde", "historial": []}
    s.commit()
    assert ov_sap.reactivar_bloqueadas(None) == []  # con la regla encendida sigue bloqueada
    set_param("dias_minimos_emision_ov", 0)  # V44: por ahora solo se bloquea por precio
    s.commit()
    assert ov_sap.reactivar_bloqueadas(None) == [o.numero]
    s.commit()
    assert o.estado != "BLOQUEADA" and o.bloqueo_ov["estado"] == "LEVANTADO"
    assert o.bloqueo_ov["motivo_original"] == "Se emitió tarde" and "llega" in o.bloqueo_ov["evaluacion"]


def test_pantallas_estado_ov_y_expedientes(app, s, U, new_order):
    o = new_order([("MP-902", 10)])
    o.sap_docnum = "9000004"
    _guia(s, 7004, "9000004", "MP-902", 10)
    p = new_order([("MP-902", 3)], ruc="20000000004")
    p.retenida_precio = True
    p.motivo_detencion = "Detenida por precio bajo el mínimo: requiere confirmación comercial."
    s.commit()
    c = _cliente(app, "jefe.operaciones")
    html = c.get("/ov/estado?desde=%s&hasta=%s" % ((date.today() - timedelta(days=5)).isoformat(),
                                                   (date.today() + timedelta(days=10)).isoformat())).get_data(as_text=True)
    s.expire_all()
    assert "EG07-7004" in html and "cumplido (guía)" in html and "¿por qué?" in html
    from app.models import SalesOrder
    assert s.get(SalesOrder, o.id).estado == "DESPACHADA"
    html = c.get(f"/ov/{o.id}").get_data(as_text=True)
    assert "EG07-7004" in html
    html = c.get("/seguimiento/expedientes?desde=%s&hasta=%s" % (date.today().isoformat(),
                                                                (date.today() + timedelta(days=10)).isoformat())).get_data(as_text=True)
    assert "Detenida por precio bajo el mínimo" in html


def test_cumplimiento_del_cliente_con_guias_de_sap(app, s, U, new_order):
    from app.services import seguimiento
    o = new_order([("MP-902", 10)])
    _sap_ov(s, "9000005", "MP-902", 10, cliente=o.customer.nombre)
    _guia(s, 7005, "9000005", "MP-902", 10)
    s.commit()
    from app.services import sap_v31
    if not sap_v31.tiene_historial():
        from app.services.core import set_param
        set_param("sap_ordenes_ultimo", {"historial": True, "ts": "2026-11-17T00:00"})
        s.commit()
    d = seguimiento.customer_compliance(o.customer_id)
    assert d["fuente"] == "SAP" and [f["o"].numero for f in d["ultimas"]] == ["9000005"]
