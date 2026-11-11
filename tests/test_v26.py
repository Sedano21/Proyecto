"""V26 (11-nov-2026): OV abiertas vs guías de SAP, facturas desde SAP, producto fumigado almacenado, canales únicos,
catálogo por tipo y filtros. Solo datos ficticios."""
from datetime import date, timedelta

from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


def _batch(s, tipo, filas):
    from app.models import UploadBatch, UploadRow
    b = UploadBatch(tipo=tipo, archivo=f"SAP_SL_{tipo}_prueba.xlsx", estado="CONFIRMADO")
    s.add(b)
    s.flush()
    for i, d in enumerate(filas, 2):
        s.add(UploadRow(batch_id=b.id, fila=i, datos=d))
    s.commit()
    return b


def test_ov_abiertas_vs_guias(app, s):
    from app.services import despachos_sap as ds
    _batch(s, "OV", [
        {"numero": 801, "estado": "Abierto", "cliente": "Cliente Demo A", "fecha_compromiso": "2026-11-12", "producto": "PT-901",
         "solicitado": 10, "entregado": 4},
        {"numero": 802, "estado": "Abierto", "cliente": "Cliente Demo B", "fecha_compromiso": "2026-11-12", "producto": "PT-901",
         "solicitado": 5, "entregado": 5},
        {"numero": 803, "estado": "Abierto", "cliente": "Cliente Demo C", "fecha_compromiso": "2026-11-13", "producto": "PT-902",
         "solicitado": 3, "entregado": 0},
        {"numero": 804, "estado": "Cerrado", "cliente": "Cliente Demo D", "producto": "PT-902", "solicitado": 1},
    ])
    _batch(s, "DESPACHOS", [
        {"ov": 801, "guia": "T001-1", "fecha": "2026-11-10", "producto": "PT-901", "cantidad": 4, "factura": "F001-9"},
        {"ov": 802, "guia": "T001-2", "fecha": "2026-11-10", "producto": "PT-901", "cantidad": 3},
    ])
    res = ds.conciliar()
    por = {f["ov"]: f for f in res["filas"]}
    assert set(por) == {"801", "802", "803"}  # la cerrada no entra
    assert por["801"]["estado"] == "PARCIAL" and por["801"]["lineas"][0]["pendiente"] == 6 and por["801"]["facturas"] == ["F001-9"]
    assert por["802"]["estado"] == "COMPLETO" and any("cerrarla en SAP" in a for a in por["802"]["alertas"])
    assert not por["802"]["lineas"][0]["cuadra"]  # 3 guiado frente a 5 entregado
    assert por["803"]["estado"] == "SIN_DESPACHO" and not por["803"]["alertas"]
    assert res["tot"]["PARCIAL"] == 1 and res["tot"]["COMPLETO"] == 1
    assert ds.excel(res)[:2] == b"PK"
    c = _cliente(app, "jefe.logistica")
    html = c.get("/almacen/cargas/sap/despachos").get_data(as_text=True)
    assert "Órdenes de venta abiertas vs guías de SAP" in html and "INCOMPLETO" in html and "T001-1" in html
    assert c.get("/almacen/cargas/sap/despachos?salida=xlsx").status_code == 200


class _SLFacturas:
    cfg = {"user": "integracion"}

    def get_all(self, path, params=None):
        hoy = date.today().isoformat()
        if path == "Invoices":
            return [{"DocEntry": 1, "DocNum": 5001, "FolioPrefixString": "F001", "FolioNumber": 77, "CardCode": "C20000000001",
                     "CardName": "Cliente", "DocDate": hoy, "DocDueDate": hoy, "DocCurrency": "S/", "DocTotal": 1180.0,
                     "PaidToDate": 180.0, "DocumentLines": [{"BaseType": 15, "BaseEntry": 30}]}]
        if path == "CreditNotes":
            return [{"DocEntry": 2, "DocNum": 6001, "FolioPrefixString": "FC01", "FolioNumber": 5, "CardCode": "C20000000001",
                     "CardName": "Cliente", "DocDate": hoy, "DocCurrency": "S/", "DocTotal": 100.0,
                     "DocumentLines": [{"BaseType": 13, "BaseEntry": 1}]}]
        if path == "DeliveryNotes":
            return [{"DocEntry": 30, "DocNum": 900, "DocumentLines": [{"BaseType": 17, "BaseEntry": 40}]}]
        if path == "Orders":
            return [{"DocEntry": 40, "DocNum": 701}]
        if path == "BusinessPartners":
            return [{"CardCode": "C20000000001", "FederalTaxID": "20000000001"}]
        raise AssertionError(path)


def test_facturas_desde_sap(app, s, U):
    from app.models import CustomerInvoice
    from app.services import sap_sl
    filas = sap_sl.rows_facturas(_SLFacturas())
    f = next(x for x in filas if x["tipo"] == "FACTURA")
    nc = next(x for x in filas if x["tipo"] == "NOTA_CREDITO")
    assert f["numero"] == "F001-77" and f["ov"] == "701" and f["saldo"] == 1000.0 and f["moneda"] == "SOLES"
    assert nc["referencia"] == "F001-77" and nc["ruc"] == "20000000001"
    r = sap_sl.sync_facturas(U("coord.finanzas"), sl=_SLFacturas())
    s.commit()
    assert r["registradas"] == 2, r
    inv = s.query(CustomerInvoice).filter_by(numero="F001-77").one()
    assert inv.origen == "SAP" and inv.saldo == 1000.0  # el saldo final es el de SAP
    assert sap_sl.sync_facturas(U("coord.finanzas"), sl=_SLFacturas())["registradas"] == 2  # no duplica
    s.commit()
    assert s.query(CustomerInvoice).filter_by(numero="F001-77").count() == 1


def test_producto_fumigado_almacenado(app, s):
    from app.models import StockLot
    from app.services import fumigados
    from .conftest import alerts_of
    hoy = date.today()
    lots = s.query(StockLot).filter(StockLot.estado == "DISPONIBLE", StockLot.cantidad > 0).limit(3).all()
    lots[0].fumigacion = {"inicio": (hoy - timedelta(days=30)).isoformat(), "fin": (hoy - timedelta(days=22)).isoformat()}
    lots[1].fumigacion = {"fin": (hoy - timedelta(days=16)).isoformat()}
    lots[2].fumigacion = {"liberacion": (hoy + timedelta(days=2)).isoformat()}  # aún no termina
    s.commit()
    d = fumigados.listar(hoy)
    niveles = {x["lot"].id: x["nivel"] for x in d["filas"]}
    assert niveles[lots[0].id] == "VENCIDO" and niveles[lots[1].id] == "AVISO" and lots[2].id not in niveles
    assert fumigados.revisar(hoy) == 2
    s.commit()
    a = alerts_of(s, "FUMIGADO_ESTANCADO", lots[0].id)
    assert a and "JEFE_CALIDAD" in a[0].roles and ({"COORD_ALMACEN", "COORD_ALMACEN_MP"} & set(a[0].roles))
    assert fumigados.revisar(hoy) == 2 and len(alerts_of(s, "FUMIGADO_ESTANCADO", lots[0].id)) == 1  # sin duplicar
    html = _cliente(app, "asist.calidad").get("/calidad/fumigados").get_data(as_text=True)
    assert "Producto fumigado almacenado" in html and "SOBRE EL PLAZO" in html


def test_fin_de_fumigacion_se_registra_en_el_lote(app, s, U):
    from app.models import StockLot
    from app.services import quality as q
    lot = s.query(StockLot).filter(StockLot.estado == "DISPONIBLE", StockLot.cantidad > 0).first()
    hoy = date.today().isoformat()
    q.register(U("asist.calidad"), "FUMIGACION", {"inicio_fecha": hoy}, lot_id=lot.id)
    q.register(U("asist.calidad"), "FUMIGACION", {"inicio_fecha": hoy, "fin_fecha": hoy}, lot_id=lot.id)
    s.commit()
    s.expire_all()
    assert (s.get(StockLot, lot.id).fumigacion or {}).get("fin") == hoy


def test_canales_unicos_y_alta_desde_clientes(app, s, U):
    from app.models import Customer
    from app.services import prices as psvc
    c0 = s.query(Customer).first()
    c0.canal_precio = "CANAL DEMO FICHA"
    s.commit()
    assert "CANAL DEMO FICHA" in psvc.canales()
    c = _cliente(app, "jefe.ventas")
    assert "CANAL DEMO FICHA" in c.get("/ov/nueva").get_data(as_text=True)
    html = c.get("/ov/clientes").get_data(as_text=True)
    assert "Agregar canal" in html
    import re
    tok = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
    r = c.post("/configuracion/canales", data={"_csrf": tok, "nombre": "Canal Nuevo Demo", "volver": "/ov/clientes"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/ov/clientes")
    assert "CANAL NUEVO DEMO" in psvc.canales()


def test_catalogo_general_y_por_tipo(app):
    c = _cliente(app, "jefe.ventas")
    html = c.get("/ov/catalogo").get_data(as_text=True)
    assert "General (todos)" in html
    pt = c.get("/ov/catalogo?tipo=PT").get_data(as_text=True)
    assert "PT-" in pt and "MP-9" not in pt.split("lista-catalogo")[-1]
