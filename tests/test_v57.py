"""V57 (18-nov-2026): forma de pago, vencimiento y OC en la factura; varias guías en una factura; lectura del PDF de la
factura de SUNAT; stock de artículos sin lote; el vigilante detecta compras, traslados, artículos y clientes."""
from datetime import date, timedelta

from .test_v26 import _cliente
from .test_v56 import _SL, _escritura


class _SLDos(_SL):
    def get_all(self, path, params=None):
        out = super().get_all(path, params)
        if path == "DeliveryNotes" and out:
            otra = dict(out[0], DocEntry=302, FolioNumber=901,
                        DocumentLines=[{"LineNum": 0, "ItemCode": "MP-903", "ItemDescription": "Otro insumo", "Quantity": 2,
                                        "RemainingOpenQuantity": 2, "UnitPrice": 3.0, "TaxCode": "IGV"}])
            out = out + [otra]
        return out


def test_forma_de_pago_oc_y_varias_guias_en_una_factura(app, s, U):
    from app.models import Prefactura
    from app.services import prefacturas as pf
    sl = _SLDos()
    pf.sincronizar(None, sl=sl)
    s.commit()
    p = s.query(Prefactura).filter_by(entrega_docentry=301).one()
    q = s.query(Prefactura).filter_by(entrega_docentry=302).one()
    assert p.forma_pago == "CREDITO 45 DIAS" and p.vencimiento == date.today() + timedelta(days=45)
    assert p.oc_cliente == "OC-PRUEBA-1" and pf.juntables(p) == [q]
    fact = U("facturacion")
    pf.editar(fact, p, {"forma_pago_codigo": "-1", "oc_cliente": "4900000001"})
    assert p.forma_pago == "CONTADO" and p.vencimiento == p.fecha
    pf.juntar(fact, p, [q], "el cliente pide una sola factura")
    s.commit()
    assert q.estado == "DESCARTADA" and p.guia == "EG07-900, EG07-901" and len(p.lineas) == 3
    _escritura(U)
    pf.validar(fact, p, True, sl=sl)
    s.commit()
    body = sl.posts[-1][1]
    assert body["PaymentGroupCode"] == -1 and body["NumAtCard"] == "4900000001" and body["DocDueDate"] == p.fecha.isoformat()
    assert [(x["BaseEntry"], x["BaseLine"]) for x in body["DocumentLines"]] == [(301, 0), (301, 1), (302, 0)]
    pf.sincronizar(None, sl=sl)  # no se vuelven a preparar las guías ya juntadas
    assert s.query(Prefactura).count() == 2


PDF_TXT = """R.U.C.: 20999999999
FACTURA ELECTRONICA
F001-1001
Señor(es) : CLIENTE PRUEBA SAC
RUC : 20000000001
Fecha de emisión : 13/11/2026
Fecha de vencimiento : 28/12/2026
Forma de pago : CREDITO
N° Orden de
compra : 4900000001
N° Guía(s) de remisión : EG07-900
CANTIDAD CODIGO DESCRIPCIÓN P.U. VALOR
10.00 MP-902 INSUMO PRUEBA 5.00 50.00
Sub Total: S/ 50.00
IGV (18%) S/ 9.00
Importe Total de
la Venta S/ 59.00
"""


def test_pdf_de_factura_sunat_se_une_por_la_guia(app, s, U, monkeypatch):
    from app.models import Customer, Prefactura
    from app.services import prefacturas as pf
    from app.services.core import set_param
    set_param("empresa_ruc", "20999999999")
    c = s.query(Customer).filter_by(ruc="20000000001").first()
    c.codigo_sap = "C20000000001"
    s.commit()
    f = pf.parse_text(PDF_TXT)
    assert (f["serie"], f["numero"], f["ruc"], f["total"], f["oc"], f["forma_pago"], f["guias"]) == \
        ("F001", "1001", "20000000001", 59.0, "4900000001", "CREDITO", ["EG07-900"])
    assert f["fecha"] == date(2026, 11, 13) and f["vencimiento"] == date(2026, 12, 28)
    assert f["lineas"] == [{"codigo": "MP-902", "descripcion": "INSUMO PRUEBA", "um": "", "cantidad": 10.0, "precio": 5.0,
                            "descuento": 0.0}]
    pf.sincronizar(None, sl=_SLDos())
    s.commit()
    monkeypatch.setattr(pf, "leer_archivo", lambda path: pf.parse_text(PDF_TXT))
    p = pf.registrar_sunat(U("facturacion"), "x.pdf", "x.pdf", "x.pdf")
    s.commit()
    # dos guías abiertas del cliente: se une a la que cita la factura
    assert p.entrega_docentry == 301 and p.oc_cliente == "4900000001" and p.forma_pago.startswith("CREDITO")
    assert s.query(Prefactura).filter_by(entrega_docentry=302).one().estado == "POR_VALIDAR"


def test_stock_de_articulos_sin_lote(app, s, U):
    from app.services import sap_sl
    from app.services.core import set_param

    class SL:
        def sql_query(self, code):
            return [{"ItemCode": "MP-902", "ItemName": "x", "DistNumber": "L1", "WhsCode": "W1", "Quantity": 5}]

        def get_all(self, path, params=None):
            assert path == "Items" and "ManageBatchNumbers eq 'tNO'" in params["$filter"]
            return [{"ItemCode": "AB-130", "ItemName": "PANETON PRUEBA", "ItemWarehouseInfoCollection": [
                {"WarehouseCode": "W1", "InStock": 120}, {"WarehouseCode": "W2", "InStock": 0}]}]
    set_param("sap_consultas", {"STOCK": "CPOPS_STOCK_LOTE"})
    filas = sap_sl.fetch("STOCK", SL())
    assert [(f["ItemCode"], f["DistNumber"], f["WhsCode"], f["Quantity"]) for f in filas] == \
        [("MP-902", "L1", "W1", 5), ("AB-130", "SIN LOTE", "W1", 120.0)]


def test_vigilante_detecta_compras_traslados_y_maestros(app, s, U, monkeypatch):
    from app.services import sap_vigia

    class SL:
        cfg = {"user": "x"}

        def __init__(self, n):
            self.n = n
            self.pedidos = []

        def get_all(self, path, params=None):
            self.pedidos.append((path, params["$select"]))
            if path == "StockTransfers":
                return [{"DocEntry": i, "UpdateDate": date.today().isoformat()} for i in range(self.n)]
            if path == "Items":
                return [{"ItemCode": "AB-130", "UpdateDate": date.today().isoformat()}] * self.n
            return []
    sl = SL(1)
    c1, f1 = sap_vigia.cambios(sl, {})
    assert {"COMPRAS", "TRASLADOS", "ARTICULOS", "SOCIOS"} <= set(c1)
    assert ("Items", "ItemCode,UpdateDate,UpdateTime") in sl.pedidos
    c2, _ = sap_vigia.cambios(SL(2), f1)
    assert c2["TRASLADOS"] and c2["ARTICULOS"] and not c2["OV"] and not c2["COMPRAS"]


def test_facturacion_muestra_notas_de_credito(app, s, U):
    from app.services import facturacion_sap
    from .test_v52 import _SL as _SLFact
    facturacion_sap.sync(U("sistemas"), sl=_SLFact(date.today()))
    s.commit()
    html = _cliente(app, "facturacion").get("/facturacion/").get_data(as_text=True)
    assert "Notas de crédito del mes" in html and "S/ 118" in html and "S/ 4,602" in html
    assert _cliente(app, "facturacion").get("/gestion/facturacion-sap?ver=notas").status_code == 200
