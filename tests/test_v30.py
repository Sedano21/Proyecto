"""V30 (12-nov-2026): ubicación de lotes, documentos por cliente, clientes sin movimiento, incluir filas de carga con
motivo, facturas de reserva sin entrega, indicadores por canal, listas plegables, recordatorio de salida de fumigación y
desmedro en el balance de peso. Solo datos ficticios."""
import re
from datetime import date, timedelta

import pytest

from .conftest import alerts_of
from .test_v26 import _batch, _cliente


def _post(c, url, data, origen="/"):
    html = c.get(origen).get_data(as_text=True)
    tok = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
    return c.post(url, data=dict(data, _csrf=tok), follow_redirects=True)


def test_ubicacion_del_lote(app, s, U):
    from app.models import StockLot
    from app.services import v30
    from app.services.core import BusinessError
    lot = s.query(StockLot).filter(StockLot.cantidad > 0).first()
    with pytest.raises(BusinessError):
        v30.set_location(U("aux.almacen"), lot, "A-01")
    for u in ("superv.almacen", "jefe.logistica", "lider.almacen", "coord.logistica"):
        v30.set_location(U(u), lot, f"  rack {u[:3]} 01 ")
    s.commit()
    assert lot.ubicacion == "RACK COO 01" and len(lot.ubicacion_hist) == 4 and lot.ubicacion_hist[0]["de"] == ""
    c = _cliente(app, "lider.almacen")
    r = _post(c, f"/almacen/lote/{lot.id}/ubicacion", {"ubicacion": "B-02-1", "volver": "/almacen/stock"}, "/almacen/stock")
    assert r.status_code == 200 and "B-02-1" in r.get_data(as_text=True)
    s.refresh(lot)
    assert lot.ubicacion == "B-02-1"
    html = _cliente(app, "aux.almacen").get("/almacen/stock?q=B-02").get_data(as_text=True)
    assert "B-02-1" in html and f'action="/almacen/lote/{lot.id}/ubicacion"' not in html  # la ve pero no la edita


def test_documentos_del_cliente(app, s, U, cust, new_order):
    from app.models import CustomerInvoice
    o = new_order([("PT-901", 5)])
    c = cust()
    _batch(s, "DESPACHOS", [{"ov": o.numero, "guia": "T001-77", "fecha": date.today().isoformat(), "producto": "PT-901",
                             "cantidad": 5, "factura": "F001-9"}])
    s.add(CustomerInvoice(customer_id=c.id, order_id=o.id, tipo="FACTURA", numero="F001-9", fecha=date.today(), monto=100,
                          saldo=100, origen="SAP"))
    s.add(CustomerInvoice(customer_id=c.id, tipo="NOTA_CREDITO", numero="FC01-3", referencia="F001-9", fecha=date.today(),
                          monto=10, saldo=0, origen="SAP"))
    s.commit()
    w = _cliente(app, "coord.ventas")
    assert "Guías, facturas y notas de crédito del cliente" in w.get(f"/seguimiento/expedientes?cliente={c.id}").get_data(as_text=True)
    assert "T001-77" in w.get(f"/seguimiento/expedientes/cliente/{c.id}").get_data(as_text=True)
    assert "F001-9" in w.get(f"/seguimiento/expedientes/cliente/{c.id}?ver=facturas").get_data(as_text=True)
    html = w.get(f"/seguimiento/expedientes/cliente/{c.id}?ver=notas").get_data(as_text=True)
    assert "FC01-3" in html and "F001-9" in html


def test_clientes_sin_movimiento(app, s, U, cust, new_order):
    from app.models import Customer
    from app.services import v30
    from app.services.core import BusinessError
    viejo = Customer(ruc="20999999901", nombre="CLIENTE DEMO SIN MOVIMIENTO")
    s.add(viejo)
    s.commit()
    hoy = date.today()
    ids = {x["c"].id for x in v30.inactivos(hoy)["filas"]}
    assert viejo.id in ids
    o = new_order([("PT-901", 1)])  # cliente con pedido: no aparece
    assert o.customer_id not in {x["c"].id for x in v30.inactivos(hoy)["filas"]}
    with pytest.raises(BusinessError):
        v30.decidir(U("vendedor1"), viejo, "EXCLUIR", "x")
    with pytest.raises(BusinessError):
        v30.decidir(U("jefe.ventas"), viejo, "EXCLUIR", "")
    w = _cliente(app, "coord.ventas")
    r = _post(w, "/comercial/clientes-sin-movimiento", {"cid": str(viejo.id), "accion": "EXCLUIR",
                                                         "motivo": "Empresa cerrada (ficticio)"}, "/comercial/clientes-sin-movimiento")
    assert r.status_code == 200
    s.refresh(viejo)
    assert viejo.excluido and viejo.inactividad["estado"] == "EXCLUIDO"
    assert "CLIENTE DEMO SIN MOVIMIENTO" not in w.get("/ov/nueva").get_data(as_text=True)  # no se ofrece al registrar
    assert viejo.id in {x["c"].id for x in v30.inactivos(hoy, "EXCLUIDOS")["filas"]}
    v30.decidir(U("jefe.ventas"), viejo, "INCLUIR")
    s.commit()
    assert not viejo.excluido and viejo.id not in {x["c"].id for x in v30.inactivos(hoy)["filas"]}  # mantenido
    assert viejo.id in {x["c"].id for x in v30.inactivos(hoy + timedelta(days=600))["filas"]}  # vuelve tras 18 meses más
    # un excluido que vuelve a pedir queda incluido solo
    v30.decidir(U("jefe.ventas"), viejo, "EXCLUIR", "prueba")
    from app.services.orders import create_order
    create_order(U("coord.ventas"), "SAP-9001", viejo.id, hoy + timedelta(days=3),
                 [{"product_code": "PT-901", "cantidad": 1, "precio_unitario": 999}], origen="CARGA_SAP")
    s.commit()
    assert not viejo.excluido and "Volvió a tener movimiento" in viejo.inactividad["motivo"]
    assert _cliente(app, "vendedor1").get("/comercial/clientes-sin-movimiento").status_code == 403


def test_incluir_fila_de_carga_con_motivo(app, s, U):
    from app.services import uploads
    from app.services.core import BusinessError
    b = _batch(s, "DESPACHOS", [{"ov": "1", "guia": "T001-1", "fecha": date.today().isoformat(), "producto": "PT-901",
                                 "cantidad": 1}])
    b.estado = "LISTO"
    r = b.rows[0]
    with pytest.raises(BusinessError):
        uploads.include_row(b, r, U("coord.distribucion"), "")
    uploads.exclude_row(b, r, U("coord.distribucion"), "no corresponde")
    assert r.excluida
    uploads.include_row(b, r, U("coord.distribucion"), "La guía es correcta (ficticio)")
    s.commit()
    assert not r.excluida and r.inclusion["motivo"].startswith("La guía es correcta")
    assert b.estado == "LISTO"


def test_incluir_fila_con_error_pasa_a_advertencia(app, s, U, monkeypatch):
    from app.services import uploads
    from app.services.core import BusinessError
    b = _batch(s, "DESPACHOS", [{"ov": "1", "guia": "T001-2", "fecha": date.today().isoformat(), "producto": "PT-901",
                                 "cantidad": 1}])
    b.estado = "LISTO"

    def _v(bt):
        for x in bt.rows:
            x.errores = ["Producto no reconocido (ficticio)"]
    monkeypatch.setitem(uploads.__dict__, "_v_despachos", _v)
    uploads.validate_batch(b)
    assert b.estado == "VALIDADO_CON_ERRORES"
    uploads.include_row(b, b.rows[0], U("coord.distribucion"), "Se acepta tal como viene")
    assert b.estado == "LISTO" and not b.rows[0].errores
    assert any("Incluida con motivo" in a for a in b.rows[0].advertencias)
    b.rows[0].datos = dict(b.rows[0].datos, guia="")  # sin un dato obligatorio no se puede incluir
    s.flush()
    spec_req = uploads.SPECS["DESPACHOS"]["req"]
    if "guia" in spec_req:
        with pytest.raises(BusinessError):
            uploads.include_row(b, b.rows[0], U("coord.distribucion"), "otra vez")


class _SLReservas:
    cfg = {"user": "integracion"}

    def __init__(self, ov):
        self.ov = ov

    def get_all(self, path, params=None):
        if path == "Invoices":
            assert "ReserveInvoice eq 'tYES'" in params["$filter"]
            return [{"DocEntry": 11, "DocNum": 81, "FolioPrefixString": "F001", "FolioNumber": 500, "DocDate": date.today().isoformat(),
                     "DocDueDate": (date.today() + timedelta(days=4)).isoformat(), "CardCode": "C1", "CardName": "Cliente Demo A",
                     "DocumentLines": [
                         {"LineNum": 0, "BaseType": 17, "BaseEntry": 70, "ItemCode": "PT-901", "Quantity": 40, "RemainingOpenQuantity": 25},
                         {"LineNum": 1, "BaseType": 17, "BaseEntry": 70, "ItemCode": "PT-902", "Quantity": 5, "RemainingOpenQuantity": 0}]}]
        if path == "Orders":
            return [{"DocEntry": 70, "DocNum": self.ov}]
        raise AssertionError(path)


def test_facturas_de_reserva_sin_entrega(app, s, U, new_order):
    from app.models import SapReserveInvoiceLine, SalesOrder
    from app.services import facturas_reserva as fr
    from app.services import production, uploads
    from app.services.core import BusinessError
    r = fr.sync(U("jefe.logistica"), sl=_SLReservas("7701"))
    s.commit()
    assert r == {"lineas": 1, "facturas": 1}  # la línea ya entregada no entra
    x = s.query(SapReserveInvoiceLine).one()
    assert x.numero == "F001-500" and x.ov_numero == "7701" and x.pendiente == 25 and x.vigente
    with pytest.raises(BusinessError):
        fr.decidir(U("jefe.logistica"), [x], True)
    fr.decidir(U("jefe.produccion"), [x], True)
    s.commit()
    fr.sync(U("jefe.logistica"), sl=_SLReservas("7701"))  # la aprobación se conserva al volver a leer
    s.commit()
    assert x.aprobacion["estado"] == "APROBADA"
    assert [y.clave for y in fr.para_preprogramacion()] == [x.clave]
    req = production.requirements("SEMANA", date.today() - timedelta(days=7), date.today() + timedelta(days=30))
    assert any("Factura de reserva F001-500" in f for a in req["filas"] for f in a["fuentes"])
    # la OV del módulo con factura de reserva por entregar no se cierra aunque SAP la cierre
    o = new_order([("PT-901", 25)])
    o.sap_docnum = "7701"
    s.commit()
    b = _batch(s, "OV", [{"numero": "7701", "estado": "Cerrado", "ruc": o.customer.ruc, "cliente": o.customer.nombre,
                          "producto": "PT-901", "solicitado": 40}])
    uploads._c_ov(b, U("coord.ventas"), {})
    s.commit()
    assert s.get(SalesOrder, o.id).estado != "CERRADA"
    assert fr.para_preprogramacion() == []  # su OV está abierta en el módulo: entra por la OV, no dos veces
    for u in ("jefe.logistica", "jefe.ventas", "jefe.produccion", "superv.almacen"):
        html = _cliente(app, u).get("/logistica/facturas-reserva").get_data(as_text=True)
        assert "F001-500" in html, u
    assert _cliente(app, "vendedor1").get("/logistica/facturas-reserva").status_code == 403


def test_indicadores_por_canal(app, s, U, cust, new_order):
    from app.services import kpis, seguimiento
    from app.services.margin import channel
    o1 = new_order([("PT-901", 10)], dias=0)
    o2 = new_order([("PT-901", 10)], dias=0, ruc="20000000004")
    o1.canal_precio, o2.canal_precio = "CANAL DEMO A", "CANAL DEMO B"
    s.commit()
    hoy = date.today()
    assert channel(o1.customer, o1) == "CANAL DEMO A"
    todo = seguimiento.service_month(desde=hoy, hasta=hoy)
    a = seguimiento.service_month(desde=hoy, hasta=hoy, canal="CANAL DEMO A")
    assert a["universo"] == 1 and todo["universo"] >= 2
    assert kpis.compute(hoy, hoy, "CANAL DEMO B")["pendientes"] == 1
    c = _cliente(app, "jefe.operaciones")
    assert 'name="canal"' in c.get("/?canal=CANAL+DEMO+A").get_data(as_text=True)
    assert "CANAL DEMO A" in c.get("/seguimiento/servicio?canal=CANAL+DEMO+A").get_data(as_text=True)
    g = _cliente(app, "gerente.general")
    assert "canal <b>CANAL DEMO B</b>" in g.get("/gestion/empresa?canal=CANAL+DEMO+B").get_data(as_text=True)


def test_listas_plegables(app, s, new_order):
    o = new_order([("PT-901", 3)])
    _batch(s, "OV", [{"numero": 991, "estado": "Abierto", "cliente": "Cliente Demo A", "fecha_compromiso": "2026-11-14",
                      "producto": "PT-901", "solicitado": 10, "entregado": 4}])
    c = _cliente(app, "jefe.logistica")
    html = c.get("/almacen/cargas/sap/despachos").get_data(as_text=True)
    assert 'data-tg="d1"' in html and 'id="d1" hidden' in html and "Nota de crédito" in html
    html = c.get("/ov/").get_data(as_text=True)
    assert f'data-tg="ovd{o.id}"' in html and f'id="ovd{o.id}" hidden' in html


def test_recordatorio_salida_de_fumigacion(app, s, U):
    from app.models import StockLot
    from app.services import quality_v13
    hoy = date.today()
    lots = s.query(StockLot).filter(StockLot.cantidad > 0).limit(2).all()
    for lot, f in zip(lots, (hoy + timedelta(days=1), hoy)):
        lot.estado = "EN_FUMIGACION"
        lot.fumigacion = {"inicio": (hoy - timedelta(days=3)).isoformat(), "liberacion": f.isoformat(), "zona": "Contenedor 1"}
    s.commit()
    assert quality_v13.check_fumigation_exit_reminder(hoy) == 2
    s.commit()
    al = alerts_of(s, "FUMIGACION_SALIDA")
    assert len(al) == 2 and {a.titulo.split(" ")[0] for a in al} == {"HOY", "MAÑANA"}
    assert set(al[0].roles) >= {"JEFE_LOGISTICA", "LIDER_ALMACEN", "GERENCIA_OPERACIONES", "SUPERV_ALMACEN",
                                "COORD_LOGISTICA", "SUPERV_CALIDAD", "JEFE_CALIDAD"}
    quality_v13.check_fumigation_exit_reminder(hoy)
    s.commit()
    assert len(alerts_of(s, "FUMIGACION_SALIDA")) == 2  # no se repite


def test_desmedro_en_el_balance_de_peso(app, s):
    from app.models import Product
    from app.services import balance_of
    s.add(Product(code="ME-902", descripcion="LENTEJA - DESMEDRO DEMO", um="KILOGRAMO", peso_kg=1))
    s.flush()
    of = {"orden": "OF-9", "producto": "MP-902", "descripcion": "", "estado": "CERRADA", "fecha": "", "planificado": 100,
          "completado": 100, "rechazado": 0,
          "componentes": [{"producto": "MP-902", "planificado": 97, "emitido": 97},
                          {"producto": "ME-902", "planificado": 3, "emitido": 3}]}
    r = balance_of.evaluar(of, "LIQUIDACION")  # materia ingresada 97 + desmedro 3 = producto 100
    assert r["ok"] and r["merma_kg"] == 3 and r["insumos_kg"] == 97
    of["componentes"][1]["emitido"] = 8
    r = balance_of.evaluar(of, "LIQUIDACION")
    assert not r["ok"] and r["dif_kg"] == 5
