"""V58 (18-nov-2026): lo entregado del mes (guías de SAP) valorizado con SAP, con su detalle. Datos ficticios."""
from datetime import date

from .test_v26 import _cliente


def _ov(s, docnum, code, q, total, igv, estado="ABIERTA"):
    from app.models import SapOrderLine
    s.add(SapOrderLine(docnum=docnum, clase="VENTA", serie="OV", fecha=date.today(), fecha_entrega=date.today(),
                       cliente="CLIENTE PRUEBA", estado=estado, product_code=code, descripcion="x", cantidad=q, entregado=0,
                       linea_cerrada=False, total=total, igv=igv))


def _guia(s, de, ov, code, q, total=0.0, igv=0.0, linea=0):
    from app.models import SapMovement
    s.add(SapMovement(clave=f"GUIA:{de}:{linea}", tipo="GUIA", docentry=de, documento=f"EG07-{de}", fecha=date.today(),
                      ov_numero=ov, cliente="CLIENTE PRUEBA", product_code=code, cantidad=q, total=total, igv=igv))


def test_entregado_del_mes_completas_parciales_y_sin_ov(app, s, U):
    from app.services import empresa_v24, facturacion_sap
    _ov(s, "810001", "MP-902", 10, 100.0, 18.0)          # se entrega completa
    _ov(s, "810002", "MP-902", 10, 200.0, 36.0)          # se entrega la mitad
    _guia(s, 501, "810001", "MP-902", 10, 100.0, 18.0)
    _guia(s, 502, "810002", "MP-902", 5)                 # sin valor propio aún: se valoriza con el precio de su OV
    _guia(s, 503, "", "MP-903", 2, 50.0, 9.0)            # guía sin OV
    s.commit()
    hoy = date.today()
    r = facturacion_sap.entregado(hoy.replace(day=1), hoy)
    assert r["total"] == 118 + 118 + 59 and r["guias"] == 3 and r["ovs"] == 2 and r["estimadas"] == 1
    assert r["por_tipo"] == {"COMPLETA": 118.0, "PARCIAL": 118.0, "CERRADA_PARCIAL": 0.0, "SIN_OV": 59.0}
    assert r["sin_igv"] == 100 + 100 + 50
    c = next(x for x in empresa_v24.tablero()["cards"] if x["titulo"].startswith("Entregado en"))
    assert c["valor"] == "S/ 295" and "parciales S/ 118 (1 OV)" in c["frase"] and c["url"]
    cl = _cliente(app, "jefe.operaciones")
    html = cl.get("/gestion/entregado-sap").get_data(as_text=True)
    assert "EG07-501" in html and "EG07-503" in html and "SIN OV" in html
    html = cl.get("/gestion/entregado-sap?tipo=PARCIAL").get_data(as_text=True)
    assert "EG07-502" in html and "EG07-501" not in html
    html = cl.get("/gestion/entregado-sap?ver=clientes").get_data(as_text=True)
    assert "CLIENTE PRUEBA" in html and "295.00" in html
