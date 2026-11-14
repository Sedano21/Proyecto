"""V33 (14-nov-2026): órdenes de servicio de SAP en el historial, filtros de órdenes vs guías, alertas por proceso,
días no laborables de varias áreas con bloqueo de OV y guía firmada del conductor. Solo datos ficticios."""
import io
from datetime import date, timedelta

import pytest

from .conftest import alerts_of
from .test_v26 import _cliente


class _SLServicio:
    cfg = {"user": "integracion"}

    def get_all(self, path, params=None):
        if path == "Orders":
            return [{"DocNum": 9505, "DocDate": "2026-11-12", "DocDueDate": "2026-11-14", "CardName": "Cliente Demo S",
                     "DocumentStatus": "bost_Open", "Cancelled": "tNO", "DocType": "dDocument_Service", "Series": 13,
                     "Comments": "SERVICIO DE PROCESAMIENTO",
                     "DocumentLines": [{"ItemDescription": "SERVICIO DE ZARANDEO", "AccountCode": "7032111"}]},
                    {"DocNum": 9315, "DocDate": "2026-11-04", "DocDueDate": "2026-11-13", "CardName": "Cliente Demo S",
                     "DocumentStatus": "bost_Open", "Cancelled": "tNO", "DocType": "dDocument_Items", "Series": 13,
                     "DocumentLines": [{"ItemCode": "MP-901", "ItemDescription": "MP DEMO", "Quantity": 100,
                                        "RemainingOpenQuantity": 100}]}]
        if path in ("DeliveryNotes", "InventoryGenExits"):
            return []
        raise AssertionError(path)


def test_ordenes_de_servicio_en_el_historial(app, s, U):
    from app.models import SapOrderLine
    from app.services import despachos_sap as ds
    from app.services import sap_v31
    r = sap_v31.sync_historial(U("sistemas"), sl=_SLServicio())
    s.commit()
    assert r["servicio"] == 1 and r["version"] == sap_v31.HISTORIAL_VERSION
    os_ = s.query(SapOrderLine).filter_by(docnum="9505").one()
    assert os_.clase == "SERVICIO" and os_.product_code == "SERVICIO" and "ZARANDEO" in os_.descripcion
    serv = ds.conciliar_historial(clase="SERVICIO", situacion="TODAS")
    assert [f["ov"] for f in serv["filas"]] == ["9505"]
    venta = ds.conciliar_historial(clase="VENTA", situacion="TODAS")
    assert [f["ov"] for f in venta["filas"]] == ["9315"]
    # con la versión anterior del historial, la siguiente lectura vuelve a traer todo (para incluir las de servicio)
    from app.services.core import param, set_param
    ult = dict(param("sap_ordenes_ultimo"), version=1)
    set_param("sap_ordenes_ultimo", ult)
    assert sap_v31.sync_historial(U("sistemas"), sl=_SLServicio())["modo"] == "completa"
    # las órdenes de servicio no entran a la carga de OV abiertas (no se preparan en el almacén)
    from app.services import sap_sl

    class _SLov(_SLServicio):
        def get_all(self, path, params=None):
            if path == "SalesPersons":
                return []
            if path == "BusinessPartners":
                return []
            if path == "Orders" and "bost_Close" in params.get("$filter", ""):
                return []
            return super().get_all(path, params)
    filas = sap_sl.rows_ov(_SLov())
    assert {f["Número de documento"] for f in filas} == {9315}


def test_filtros_de_ordenes_vs_guias(app, s, U):
    from app.services import sap_v31
    sap_v31.sync_historial(U("sistemas"), sl=_SLServicio())
    s.commit()
    c = _cliente(app, "jefe.logistica")
    html = c.get("/almacen/cargas/sap/despachos?clase=TODAS&sit=TODAS&f_desde=2026-11-10&f_hasta=2026-11-30").get_data(as_text=True)
    assert "9505" in html and "9315" not in html  # 9315 se emitió el 04/11
    assert html.count('type="month"') == 1  # un solo filtro de mes
    assert "data-sin-orden" in html  # sin flecha en «Emisión / compromiso»
    html = c.get("/almacen/cargas/sap/despachos?clase=TODAS&sit=TODAS&buscar=9315").get_data(as_text=True)
    assert "9315" in html and "9505" not in html


def test_alertas_por_proceso(app, s):
    from app.models import AlertType
    from app.services import alerts
    assert alerts.proceso_de(s.get(AlertType, "REPOSICION_SUGERIDA")) in alerts.PROCESOS
    t = s.query(AlertType).filter_by(grupo="Compras").first()
    if t is not None:
        assert alerts.proceso_de(t) == "Compras e importaciones"
    alerts.emit("REPOSICION_SUGERIDA", "Alerta ficticia V33", "x", "", "", dedup_key="V33:1")
    s.commit()
    html = _cliente(app, "coord.almacen").get("/alertas").get_data(as_text=True)
    assert "Por proceso" in html and alerts.proceso_de(s.get(AlertType, "REPOSICION_SUGERIDA")) in html


def test_dias_no_laborables_varias_areas_y_ov(app, s, U, new_order, cust):
    from app.services import dias_no_laborables as dnl
    from app.services.core import BusinessError
    from app.services.orders import create_order
    assert "Comercial" in dnl.areas_de(U("jefe.ventas"))
    f = date.today() + timedelta(days=4)
    while f.weekday() == 6:
        f += timedelta(days=1)
    ds = dnl.registrar_varios(U("jefe.operaciones"), ["*"], f, "Inventario general (ficticio)")
    s.commit()
    assert {d.area for d in ds} == set(dnl.AREAS)
    al = alerts_of(s, "DIA_NO_LABORABLE")
    assert al and "La empresa no labora" in al[-1].titulo and "EJECUTIVO_VENTAS" in al[-1].roles
    with pytest.raises(BusinessError, match="no labora"):
        create_order(U("coord.ventas"), "", cust().id, f, [{"product_code": "PT-901", "cantidad": 1, "precio_unitario": 999}],
                     vendedor_id=U("vendedor1").id, oc_archivo="oc.pdf")
    o = new_order([("PT-901", 1)], dias=6)
    from app.services.orders import _apply_changes
    with pytest.raises(BusinessError, match="no labora"):
        _apply_changes(o, U("coord.ventas"), {"fecha_compromiso": f})
    with pytest.raises(BusinessError):
        dnl.registrar_varios(U("jefe.ventas"), ["Producción"], f + timedelta(days=1), "x")


class _Archivo:
    def __init__(self, nombre, datos, tipo):
        self.filename, self.mimetype = nombre, tipo
        self.stream = io.BytesIO(datos)

    def read(self):
        return self.stream.read()


def _pdf_con(texto):
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b)
    c.drawString(72, 720, texto)
    c.save()
    return b.getvalue()


def test_guia_firmada_del_conductor(app, s):
    from app.services.core import BusinessError
    from app.services.v33 import verificar_guia_firmada

    class _Stop:
        guia_numero = "T001-00012345"
    st = _Stop()
    foto = _Archivo("guia.jpg", b"\xff\xd8\xff", "image/jpeg")
    with pytest.raises(BusinessError, match="no es la de esta entrega"):
        verificar_guia_firmada(st, foto, "T001-99")
    with pytest.raises(BusinessError, match="foto o un PDF"):
        verificar_guia_firmada(st, _Archivo("nota.docx", b"x", "application/msword"), "T001-12345")
    assert verificar_guia_firmada(st, foto, "t001-12345")
    try:
        otra = _pdf_con("GUIA DE REMISION T001-00055555")
        buena = _pdf_con("GUIA DE REMISION ELECTRONICA T001-00012345")
    except ImportError:
        return
    with pytest.raises(BusinessError, match="no es la guía"):
        verificar_guia_firmada(st, _Archivo("g.pdf", otra, "application/pdf"), "T001-12345")
    assert verificar_guia_firmada(st, _Archivo("g.pdf", buena, "application/pdf"), "T001-12345")
