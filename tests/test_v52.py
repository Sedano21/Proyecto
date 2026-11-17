"""V52 (17-nov-2026): facturación del mes desde SAP (facturas − notas de crédito), aunque el cliente no esté en el
maestro del módulo. Solo datos ficticios."""
from datetime import date



class _SL:
    def __init__(self, hoy):
        self.hoy = hoy

    def get_all(self, path, params=None):
        d = self.hoy.isoformat()
        if path == "Invoices":
            return [{"DocEntry": 1, "DocNum": 10, "FolioPrefixString": "F001", "FolioNumber": 1, "CardCode": "C1",
                     "CardName": "CLIENTE QUE NO ESTA EN EL MODULO", "DocDate": d, "DocCurrency": "S/", "DocTotal": 1180.0,
                     "VatSum": 180.0, "Cancelled": "tNO"},
                    {"DocEntry": 2, "DocNum": 11, "FolioPrefixString": "F001", "FolioNumber": 2, "CardCode": "C2",
                     "CardName": "CLIENTE DOLARES", "DocDate": d, "DocCurrency": "USD", "DocTotal": 3540.0, "VatSum": 540.0,
                     "Cancelled": "tNO"},
                    {"DocEntry": 3, "DocNum": 12, "CardCode": "C3", "CardName": "ANULADA", "DocDate": d, "DocTotal": 999.0,
                     "VatSum": 0, "Cancelled": "tYES"}]
        if path == "CreditNotes":
            return [{"DocEntry": 7, "DocNum": 70, "FolioPrefixString": "FC01", "FolioNumber": 1, "CardCode": "C1",
                     "CardName": "CLIENTE QUE NO ESTA EN EL MODULO", "DocDate": d, "DocTotal": 118.0, "VatSum": 18.0,
                     "Cancelled": "tNO"}]
        return []


def test_facturacion_del_mes_desde_sap(app, s, U):
    from app.services import empresa_v24, facturacion_sap
    hoy = date.today()
    r = facturacion_sap.sync(U("sistemas"), sl=_SL(hoy))
    s.commit()
    assert r["nuevas"] == 3 and r["anuladas"] == 0
    fx = facturacion_sap.resumen(hoy.replace(day=1), hoy)
    assert fx["facturas"] == 4720 and fx["notas_credito"] == 118 and fx["neto"] == 4602 and fx["neto_sin_igv"] == 3900
    facturacion_sap.sync(U("sistemas"), sl=_SL(hoy))  # no duplica
    s.commit()
    assert facturacion_sap.resumen(hoy.replace(day=1), hoy)["neto"] == 4602
    d = empresa_v24.tablero()
    tarjetas = d.get("tarjetas") or d.get("cards") or []
    c = next(x for x in tarjetas if x["titulo"] == "Facturación del mes (SAP)")
    assert c["valor"] == "S/ 4,602" and "notas de crédito" in c["frase"]
