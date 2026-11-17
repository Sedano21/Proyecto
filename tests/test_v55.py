"""V55 (17-nov-2026): «OV del mes» son las OV de SAP con despacho en el mes (con su valor), la facturación muestra solo
el neto y las notas de crédito van en otra tarjeta; las compras salen de las órdenes de compra de SAP. Datos ficticios."""
from datetime import date

from .test_v26 import _cliente
from .test_v52 import _SL as _SLFact


class _SLCompras:
    def __init__(self, hoy):
        self.hoy = hoy
        self.llamadas = []

    def get_all(self, path, params=None):
        self.llamadas.append((path, (params or {}).get("$filter")))
        d = self.hoy.isoformat()
        if path == "PurchaseOrders":
            return [{"DocEntry": 50, "DocNum": 900, "DocDate": d, "DocDueDate": d, "CardCode": "P1",
                     "CardName": "PROVEEDOR PRUEBA SAC", "DocCurrency": "S/", "DocumentStatus": "bost_Open",
                     "Cancelled": "tNO",
                     "DocumentLines": [{"LineNum": 0, "ItemCode": "MP-902", "ItemDescription": "Insumo prueba",
                                        "Quantity": 100, "RemainingOpenQuantity": 40, "LineTotal": 1000.0,
                                        "TaxTotal": 180.0, "LineStatus": "bost_Open"}]},
                    {"DocEntry": 51, "DocNum": 901, "DocDate": d, "CardCode": "P2", "CardName": "ANULADA",
                     "DocumentStatus": "bost_Close", "Cancelled": "tYES",
                     "DocumentLines": [{"LineNum": 0, "ItemCode": "MP-902", "Quantity": 5, "LineTotal": 50.0}]}]
        return []


def _ov_sap(s, docnum, code, q, entregado, total, igv, fecha_entrega, fecha=None, estado="ABIERTA"):
    from app.models import SapOrderLine
    s.add(SapOrderLine(docnum=docnum, clase="VENTA", serie="OV", fecha=fecha or fecha_entrega, fecha_entrega=fecha_entrega,
                       cliente="CLIENTE PRUEBA", estado=estado, product_code=code, descripcion="x", cantidad=q,
                       entregado=entregado, linea_cerrada=False, total=total, igv=igv))


def test_ov_del_mes_y_notas_de_credito_aparte(app, s, U):
    from app.services import empresa_v24, facturacion_sap
    hoy = date.today()
    ini = hoy.replace(day=1)
    facturacion_sap.sync(U("sistemas"), sl=_SLFact(hoy))
    _ov_sap(s, "800001", "MP-902", 10, 5, 1000.0, 180.0, ini)
    _ov_sap(s, "800002", "MP-902", 10, 0, 500.0, 90.0, ini, estado="CANCELADA")  # anulada: no cuenta
    s.commit()
    o = facturacion_sap.ov_del_periodo(ini, hoy.replace(day=28) if hoy.day <= 28 else hoy)
    assert o["total"] == 1180 and o["despachado"] == 590 and o["por_despachar"] == 590 and o["n"] == 1
    cards = empresa_v24.tablero()["cards"]
    tit = [c["titulo"] for c in cards]
    assert "OV ingresadas del mes" not in tit and any(t.startswith("OV con despacho en") for t in tit)
    f = next(c for c in cards if c["titulo"] == "Facturación del mes (SAP)")
    assert f["valor"] == "S/ 4,602" and "neto de notas de crédito" in f["frase"] and "118" not in f["frase"]
    nc = next(c for c in cards if c["titulo"] == "Notas de crédito del mes (SAP)")
    assert nc["valor"] == "S/ 118"


def test_compras_desde_ordenes_de_compra_de_sap(app, s, U):
    from app.services import compras_sap, empresa_v24
    hoy = date.today()
    sl = _SLCompras(hoy)
    r = compras_sap.sync(U("sistemas"), sl=sl)
    s.commit()
    assert r["modo"] == "completa" and r["ordenes"] == 2
    d = compras_sap.resumen(hoy.replace(day=1), hoy)
    assert d["total"] == 1180 and d["sin_igv"] == 1000 and d["recibido"] == 708 and d["por_recibir"] == 472
    assert d["n_ordenes"] == 1 and d["proveedores"][0]["proveedor"] == "PROVEEDOR PRUEBA SAC"
    compras_sap.sync(U("sistemas"), sl=sl)  # la segunda lectura trae solo lo cambiado y no duplica
    s.commit()
    assert "UpdateDate ge" in sl.llamadas[-1][1] and compras_sap.resumen(hoy.replace(day=1), hoy)["total"] == 1180
    c = next(x for x in empresa_v24.tablero()["cards"] if x["titulo"] == "Compras del mes (SAP)")
    assert c["valor"] == "S/ 1,180" and c["url"]
    html = _cliente(app, "jefe.operaciones").get("/gestion/compras-sap?ver=productos").get_data(as_text=True)
    assert "Insumo prueba" in html and "1,180" in html
