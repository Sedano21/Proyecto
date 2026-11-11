"""V29 (11-nov-2026): notas de crédito sobre OV, órdenes de venta y de servicio, desviación de la demanda con órdenes
abiertas y cerradas, y balance de peso de las órdenes de fabricación de SAP. Solo datos ficticios."""
from datetime import date, timedelta

from .conftest import alerts_of
from .test_v26 import _batch, _cliente


def _nc(ov, clave, cantidad, origen="FACTURA_RESERVA", producto="PT-901"):
    return {"clave": clave, "nc_numero": f"FC01-{clave}", "factura": "F001-1", "fecha": date.today().isoformat(),
            "ov": ov, "producto": producto, "cantidad": cantidad, "origen": origen, "comentario": "Prueba ficticia"}


def test_nota_de_credito_descuenta_lo_que_no_se_despacha(app, s, U, new_order):
    from app.models import OrderCreditNote
    from app.services import notas_credito_ov as ncs
    from app.services.stock import line_reserved
    o = new_order([("PT-901", 100), ("PT-902", 10)])
    l1 = next(l for l in o.lines if l.product_code == "PT-901")
    assert line_reserved(l1) > 0
    res = ncs.aplicar(U("coord.finanzas"), [_nc(o.numero, "1:0", 30),
                                            _nc(o.numero, "1:1", 5, origen="FACTURA_GUIA", producto="PT-902"),
                                            _nc("OV-QUE-NO-EXISTE", "1:2", 1)])
    s.commit()
    assert res["aplicadas"] == 1 and res["ya_despachado"] == 1 and res["sin_ov"] == 1, res
    assert l1.cantidad == 70 and line_reserved(l1) <= 70 + 1e-9
    assert next(l for l in o.lines if l.product_code == "PT-902").cantidad == 10  # la nota de la guía no cambia el picking
    al = alerts_of(s, "OV_NOTA_CREDITO", o.id)
    assert len(al) == 1 and "no despachar 30" in al[0].mensaje
    # no se aplica dos veces
    assert ncs.aplicar(U("coord.finanzas"), [_nc(o.numero, "1:0", 30)])["repetidas"] == 1
    assert l1.cantidad == 70
    # la próxima carga de OV de SAP (que sigue mostrando 100 pendiente) no devuelve la cantidad
    from app.services import uploads
    from app.services.core import set_param
    set_param("conciliacion_ov_modo", "APLICAR")
    b = _batch(s, "OV", [{"numero": o.numero, "estado": "Abierto", "ruc": o.customer.ruc, "cliente": o.customer.nombre,
                          "fecha_compromiso": o.fecha_compromiso.isoformat(), "producto": "PT-901", "solicitado": 100,
                          "entregado": 0, "precio": 999.0, "clase": "SERVICIO"},
                         {"numero": o.numero, "estado": "Abierto", "ruc": o.customer.ruc, "cliente": o.customer.nombre,
                          "fecha_compromiso": o.fecha_compromiso.isoformat(), "producto": "PT-902", "solicitado": 10,
                          "entregado": 0, "precio": 999.0, "clase": "SERVICIO"}])
    r = uploads._c_ov(b, U("coord.ventas"), {})
    s.commit()
    assert r["ov_modificadas"] == 0, r
    assert l1.cantidad == 70 and o.clase == "SERVICIO"
    # la OV y el picking muestran qué no se despacha
    c = _cliente(app, "coord.ventas")
    html = c.get(f"/ov/{o.id}").get_data(as_text=True)
    assert "Notas de crédito de SAP sobre esta OV" in html and "NO DESPACHAR" in html
    html = c.get("/comercial/notas-credito-ov").get_data(as_text=True)
    assert "FC01-1:0" in html and "DESCONTADA" in html
    # nota por el resto: la OV ya no tiene nada por despachar y se cierra
    ncs.aplicar(U("coord.finanzas"), [_nc(o.numero, "2:0", 70), _nc(o.numero, "2:1", 10, origen="FACTURA_OV", producto="PT-902")])
    s.commit()
    assert o.estado == "CERRADA" and all(line_reserved(l) == 0 for l in o.lines)
    assert s.query(OrderCreditNote).count() == 5


class _SLNotas:
    cfg = {"user": "integracion"}

    def __init__(self, ov):
        self.ov = ov

    def get_all(self, path, params=None):
        if path == "CreditNotes":
            return [{"DocEntry": 9, "DocNum": 61, "FolioPrefixString": "FC01", "FolioNumber": 3, "DocDate": date.today().isoformat(),
                     "Comments": "Cliente reduce pedido", "DocumentLines": [
                         {"LineNum": 0, "BaseType": 13, "BaseEntry": 5, "BaseLine": 0, "ItemCode": "PT-901", "Quantity": 20}]}]
        if path == "Invoices":
            return [{"DocEntry": 5, "DocNum": 51, "FolioPrefixString": "F001", "FolioNumber": 8, "ReserveInvoice": "tYES",
                     "DocumentLines": [{"LineNum": 0, "BaseType": 17, "BaseEntry": 70, "ItemCode": "PT-901"}]}]
        if path == "DeliveryNotes":
            return []
        if path == "Orders":
            return [{"DocEntry": 70, "DocNum": self.ov}]
        raise AssertionError(path)


def test_lectura_de_notas_de_credito_desde_sap(app, s, U, new_order):
    from app.services import sap_v29
    o = new_order([("PT-901", 50)])
    filas = sap_v29.rows_nc_ov(_SLNotas(o.numero))
    assert filas == [{"clave": "9:0", "nc_numero": "FC01-3", "factura": "F001-8", "fecha": date.today().isoformat(),
                      "ov": o.numero, "producto": "PT-901", "cantidad": 20.0, "origen": "FACTURA_RESERVA",
                      "comentario": "Cliente reduce pedido"}]


def test_clase_de_orden_por_serie(app, s):
    from app.services import sap_v29
    from app.services.core import set_param
    series = {11: "OV2026", 12: "SERV"}
    assert sap_v29.clase_de({"Series": 12}, series) == "VENTA"  # sin configurar, todo es venta
    assert sap_v29.clase_de({"DocType": "dDocument_Service", "Series": 11}, series) == "SERVICIO"
    set_param("sap_series_orden_servicio", ["12"])
    assert sap_v29.clase_de({"Series": 12}) == "SERVICIO" and sap_v29.clase_de({"Series": 11}) == "VENTA"
    set_param("sap_series_orden_servicio", ["serv"])  # por nombre, solo si se conoce (comando sap-series)
    assert sap_v29.clase_de({"Series": 12}, series) == "SERVICIO" and sap_v29.clase_de({"Series": 12}) == "VENTA"


def test_conciliacion_separa_venta_y_servicio(app, s):
    from app.services import despachos_sap as ds
    _batch(s, "OV", [
        {"numero": 901, "estado": "Abierto", "cliente": "Cliente Demo A", "fecha_compromiso": "2026-11-12", "producto": "PT-901",
         "solicitado": 10, "entregado": 4, "clase": "VENTA"},
        {"numero": 902, "estado": "Abierto", "cliente": "Cliente Demo B", "fecha_compromiso": "2026-11-12", "producto": "PT-902",
         "solicitado": 5, "entregado": 0, "clase": "SERVICIO", "serie": "SERV"},
    ])
    venta = ds.conciliar(clase="VENTA")
    serv = ds.conciliar(clase="SERVICIO")
    assert [f["ov"] for f in venta["filas"]] == ["901"] and [f["ov"] for f in serv["filas"]] == ["902"]
    assert venta["por_clase"] == {"VENTA": 1, "SERVICIO": 1}
    assert len(ds.conciliar()["filas"]) == 2
    c = _cliente(app, "jefe.logistica")
    html = c.get("/almacen/cargas/sap/despachos?clase=SERVICIO").get_data(as_text=True)
    assert "Órdenes de servicio abiertas vs guías de SAP" in html and "902" in html and "sap_series_orden_servicio" in html
    assert "Órdenes de venta y servicio vs guías" in c.get("/").get_data(as_text=True)  # en el menú


def test_demanda_con_ordenes_abiertas_y_cerradas_de_sap(app, s, U, new_order):
    from app.services import demanda_v23 as dm
    from app.services import sap_v29
    from app.services.core import set_param
    hoy = date.today()
    desde, hasta = sap_v29.rango_ordenes(hoy)
    f = hoy.isoformat()
    filas = [
        {"docnum": "5001", "clase": "VENTA", "serie": "OV", "fecha": f, "fecha_entrega": f, "cliente": "Cliente Demo A",
         "estado": "CERRADA", "producto": "MP-901", "descripcion": "", "cantidad": 100, "entregado": 100, "linea_cerrada": True},
        {"docnum": "5002", "clase": "SERVICIO", "serie": "SERV", "fecha": f, "fecha_entrega": f, "cliente": "Cliente Demo B",
         "estado": "CERRADA", "producto": "MP-901", "descripcion": "", "cantidad": 50, "entregado": 20, "linea_cerrada": True},
        {"docnum": "5003", "clase": "SERVICIO", "serie": "SERV", "fecha": f, "fecha_entrega": f, "cliente": "Cliente Demo B",
         "estado": "ABIERTA", "producto": "MP-901", "descripcion": "", "cantidad": 30, "entregado": 0, "linea_cerrada": False},
        {"docnum": "5004", "clase": "VENTA", "serie": "OV", "fecha": f, "fecha_entrega": f, "cliente": "Cliente Demo C",
         "estado": "CANCELADA", "producto": "MP-901", "descripcion": "", "cantidad": 999, "entregado": 0, "linea_cerrada": True},
    ]
    sap_v29.guardar_ordenes(filas, desde, hasta)
    set_param("sap_ordenes_ultimo", {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "ts": f"{f}T08:00"})
    o = new_order([("MP-901", 7)], dias=0)  # OV que solo está en el módulo
    s.commit()
    ej = dm.ejecucion(hoy, hoy)
    nums = {x["o"]["numero"]: x["categoria"] for x in ej["filas"]}
    assert nums == {"5001": "CERRADA", "5002": "INCOMPLETA", "5003": "ABIERTA", o.numero: "ABIERTA"}  # sin la anulada
    assert ej["por_clase"]["SERVICIO"]["n"] == 2 and ej["por_clase"]["SERVICIO"]["pedido_kg"] == 80
    assert ej["por_clase"]["SERVICIO"]["desviacion_kg"] == 60 and ej["por_clase"]["VENTA"]["n"] == 2
    assert {x["o"]["numero"] for x in dm.ejecucion(hoy, hoy, "SERVICIO")["filas"]} == {"5002", "5003"}
    cum = dm.cumplimiento(hoy, hoy, "DIA", hoy)
    assert cum["total"]["pedido_kg"] == 187 and cum["total"]["despachado_kg"] == 120
    c = _cliente(app, "jefe.operaciones")
    html = c.get(f"/analisis/demanda?desde={f}&hasta={f}&clase=SERVICIO").get_data(as_text=True)
    assert "órdenes de servicio del" in html and "5003" in html and "Órdenes de SAP (abiertas y cerradas)" in html
    # sin lectura de SAP que cubra el rango, solo las del módulo
    set_param("sap_ordenes_ultimo", {})
    assert {x["o"]["numero"] for x in dm.ejecucion(hoy, hoy)["filas"]} == {o.numero}


def _of(orden, comps, planificado=100, completado=0.0, rechazado=0.0, estado="LIBERADA", producto="MP-902"):
    return {"orden": orden, "producto": producto, "descripcion": "", "estado": estado, "fecha": date.today().isoformat(),
            "planificado": planificado, "completado": completado, "rechazado": rechazado, "componentes": comps}


def test_balance_de_peso_de_ordenes_de_fabricacion(app, s, U):
    from app.models import Product
    from app.services import balance_of
    s.add(Product(code="MR-901", descripcion="MERMA DE SELECCION DEMO", um="KILOGRAMO", peso_kg=1))
    s.flush()
    ok = _of("OF-1", [{"producto": "MP-901", "planificado": 105, "emitido": 105},
                      {"producto": "MR-901", "planificado": -5, "emitido": -5},
                      {"producto": "EN-901", "planificado": 3, "emitido": 3}], completado=100, estado="CERRADA")
    # plan: 105 = 100 + 5 · real: 105 = 100 + 5 → cuadra (el envase no pesa en el balance)
    assert balance_of.evaluar(ok, "PLAN")["ok"] and balance_of.evaluar(ok, "LIQUIDACION")["ok"]
    mala = _of("OF-2", [{"producto": "MP-901", "planificado": 105, "emitido": 120},
                        {"producto": "MR-901", "planificado": -5, "emitido": -5}], completado=100, estado="CERRADA")
    r = balance_of.evaluar(mala, "LIQUIDACION")
    assert not r["ok"] and r["dif_kg"] == 15 and r["insumos_kg"] == 120 and r["merma_kg"] == 5
    en_curso = _of("OF-3", [{"producto": "MP-901", "planificado": 100, "emitido": 100}], completado=40)
    assert balance_of.evaluar(en_curso, "LIQUIDACION") is None  # liquidación en curso: aún no se valida lo real
    plan_malo = _of("OF-4", [{"producto": "GR-901", "planificado": 90, "emitido": 0}])
    assert not balance_of.evaluar(plan_malo, "PLAN")["ok"]  # 90 kg de granel no dan 100 kg
    res = balance_of.revisar(U("jefe.produccion"), [ok, mala, en_curso, plan_malo])
    s.commit()
    assert res["no_cuadran"] == 2, res
    al = alerts_of(s, "BALANCE_OF")
    assert {a.entidad_id for a in al} == {"OF-2", "OF-4"} and all(set(a.roles) == {"JEFE_OPERACIONES", "JEFE_PRODUCCION"} for a in al)
    c = _cliente(app, "jefe.produccion")
    html = c.get("/produccion/balance-of").get_data(as_text=True)
    assert "OF-2" in html and "NO CUADRA" in html and "OF-1" not in html
    assert "OF-1" in c.get("/produccion/balance-of?ver=TODAS").get_data(as_text=True)
    balance_of.revisar(U("jefe.produccion"), [mala])
    s.commit()
    assert len(alerts_of(s, "BALANCE_OF")) == 2  # no se repite


class _SLOF:
    cfg = {"user": "integracion"}

    def get_all(self, path, params=None):
        assert path == "ProductionOrders" and "boposCancelled" in params["$filter"]
        return [{"AbsoluteEntry": 1, "DocumentNumber": 301, "ItemNo": "MP-902", "PlannedQuantity": 100, "CompletedQuantity": 100,
                 "RejectedQuantity": 0, "ProductionOrderStatus": "boposClosed", "PostingDate": date.today().isoformat(),
                 "ProductionOrderLines": [{"ItemNo": "MP-901", "PlannedQuantity": 100, "IssuedQuantity": 110, "ItemType": "pit_Item"},
                                          {"ItemNo": "HORAS", "PlannedQuantity": 8, "IssuedQuantity": 8, "ItemType": "pit_Resource"}]}]


def test_balance_desde_sap_y_por_la_sincronizacion(app, s, U):
    from app.services import balance_of, sap_sl
    res = balance_of.sync(U("jefe.produccion"), sl=_SLOF())
    s.commit()
    assert res == {"ordenes": 1, "evaluadas": 2, "no_cuadran": 1}  # plan cuadra; lo real: 110 kg ≠ 100 kg
    assert alerts_of(s, "BALANCE_OF")[0].entidad_id == "301"
    assert "BALANCE_OF" in sap_sl.EXTRAS
