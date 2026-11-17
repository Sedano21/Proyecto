"""V53 (17-nov-2026): las compras por OV se actualizan solas cuando la OV ya tiene sus guías en SAP o se cerró."""
from datetime import date

from .conftest import alerts_of


def test_compra_por_ov_se_quita_cuando_la_ov_ya_tiene_guia(app, s, U, new_order):
    from app.models import PurchaseRequest, SapMovement, SapOrderLine
    from app.services import compras_ov, purchasing
    a = new_order([("MP-902", 10)])
    b = new_order([("MP-902", 5)], ruc="20000000004")
    u = U("coord.almacen")
    r = purchasing.create_request(u, "MP-902", 10, order=a, origen="OV", enviar=False)
    purchasing.create_request(u, "MP-902", 5, order=b, origen="OV", enviar=False)
    s.commit()
    assert r.cantidad == 15 and len(r.ordenes) == 2
    a.sap_docnum = "1636113"
    s.add(SapOrderLine(docnum="1636113", clase="VENTA", serie="OV", fecha=date.today(), fecha_entrega=date.today(),
                       cliente="x", estado="ABIERTA", product_code="MP-902", descripcion="x", cantidad=10, entregado=10,
                       linea_cerrada=False))
    s.add(SapMovement(clave="GUIA:5001:0", tipo="GUIA", docentry=5001, documento="EG07-1", fecha=date.today(),
                      ov_numero="1636113", product_code="MP-902", cantidad=10))
    s.commit()
    res = compras_ov.revisar(U("sistemas"))
    s.commit()
    assert res["ajustadas"] == 1 and r.cantidad == 5 and [x["numero"] for x in r.ordenes] == [b.numero]
    b.estado = "CANCELADA"
    s.commit()
    compras_ov.revisar(U("sistemas"))
    s.commit()
    assert r.estado == "CANCELADA" and r.cantidad == 0


def test_compra_ya_en_compras_solo_avisa(app, s, U, new_order):
    from app.services import compras_ov, purchasing
    a = new_order([("MP-902", 10)])
    r = purchasing.create_request(U("coord.almacen"), "MP-902", 10, order=a, origen="OV", enviar=False)
    r.estado = "EN_COTIZACION"
    a.estado = "DESPACHADA"
    s.commit()
    assert compras_ov.revisar(U("sistemas"))["avisadas"] == 1
    s.commit()
    assert r.cantidad == 10 and r.estado == "EN_COTIZACION" and alerts_of(s, "COMPRA_REVISAR_OV_ATENDIDA", r.id)
