"""V32 (13-nov-2026): vigilante de SAP, listas con fecha, mes, orden y paginador, alertas por área y compras (GR y,
eventualmente, MP o MQ). Solo datos ficticios."""
import re
from datetime import date, timedelta

import pytest

from .test_v26 import _cliente


class _SLFirmas:
    cfg = {"user": "integracion"}

    def __init__(self, ordenes=1):
        self.ordenes = ordenes

    def get_all(self, path, params=None):
        assert "UpdateDate ge" in params["$filter"]
        if path == "Orders":
            return [{"DocEntry": i, "UpdateDate": date.today().isoformat(), "UpdateTime": "10:00:00"} for i in range(self.ordenes)]
        return []


def test_vigilante_trae_solo_lo_que_cambio(app, s, U, monkeypatch):
    from app.services import balance_of, facturas_reserva, sap_sl, sap_v31, sap_vigia
    from app.services.core import set_param
    llamadas = []
    monkeypatch.setattr(sap_v31, "sync_historial", lambda u, sl=None, completo=False: llamadas.append("historial"))
    monkeypatch.setattr(sap_v31, "tiene_historial", lambda: True)
    monkeypatch.setattr(facturas_reserva, "sync", lambda u, sl=None: llamadas.append("reservas"))
    monkeypatch.setattr(balance_of, "sync", lambda u, sl=None: llamadas.append("balance"))
    monkeypatch.setattr(sap_sl, "sync", lambda t, u, d, sl=None, solo_si_cambia=False, autoconfirmar=None: llamadas.append(t))
    monkeypatch.setattr(sap_sl, "sync_facturas", lambda u, sl=None, desde=None: llamadas.append("facturas"))
    monkeypatch.setattr(sap_sl, "push_pending_orders", lambda ahora=None, sl=None: None)
    monkeypatch.setattr(sap_sl, "push_pending_guides", lambda sl=None: None)
    set_param("sap_sync_tipos", ["OV", "DESPACHOS", "CLIENTES"])
    u = U("sistemas")
    sap_vigia.ciclo(u, "/tmp", sl=_SLFirmas(1))  # primera vez: todo se considera cambiado
    s.commit()
    assert {"historial", "OV", "DESPACHOS", "reservas", "facturas", "balance", "CLIENTES"} <= set(llamadas)
    llamadas.clear()
    sap_vigia.ciclo(u, "/tmp", sl=_SLFirmas(1))  # nada cambió en SAP: no se trae nada
    s.commit()
    assert llamadas == []
    sap_vigia.ciclo(u, "/tmp", sl=_SLFirmas(2))  # una OV nueva o modificada
    s.commit()
    assert llamadas == ["historial", "OV"]
    llamadas.clear()
    sap_vigia.ciclo(u, "/tmp", forzar=True, sl=_SLFirmas(2))  # el botón: revisa todo
    assert {"historial", "OV", "reservas", "facturas"} <= set(llamadas)


def test_boton_con_vigilante_deja_el_pedido(app, s, U):
    from app.services import sap_sl, sap_vigia
    from datetime import datetime
    import os
    os.environ.update({"SAP_SL_URL": "https://sap.invalid:50000/b1s/v1", "SAP_SL_COMPANY": "X", "SAP_SL_USER": "u",
                       "SAP_SL_PASSWORD": "p"})
    try:
        sap_vigia._set("sap_vigia_latido", datetime.now().isoformat(timespec="seconds"), "x")
        s.commit()
        assert sap_vigia.vivo()
        c = _cliente(app, "coord.ventas")
        html = c.get("/ov/").get_data(as_text=True)
        tok = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
        r = c.post("/almacen/cargas/sap", data={"tipo": "ACTUALIZAR", "volver": "/ov/", "_csrf": tok}, follow_redirects=True)
        assert "Actualizando con SAP" in r.get_data(as_text=True)
        s.expire_all()
        assert sap_vigia._p("sap_vigia_pedido")["usuario"] and sap_sl.job_state("ACTUALIZAR")["estado"] == "EN_CURSO"
    finally:
        for k in ("SAP_SL_URL", "SAP_SL_COMPANY", "SAP_SL_USER", "SAP_SL_PASSWORD"):
            os.environ.pop(k, None)


def test_listas_por_fecha_mes_y_orden(app, s, new_order):
    hoy = date.today()
    a = new_order([("PT-901", 1)], dias=1)
    b = new_order([("PT-901", 1)], dias=20)
    c = _cliente(app, "coord.ventas")
    html = c.get(f"/ov/?f_desde={hoy}&f_hasta={hoy + timedelta(days=5)}").get_data(as_text=True)
    assert a.numero in html and b.numero not in html and 'type="month"' in html and 'name="f_desde"' in html
    mes = (hoy + timedelta(days=20)).strftime("%Y-%m")
    html = c.get(f"/ov/?f_mes={mes}").get_data(as_text=True)
    assert b.numero in html
    html = c.get("/ov/?orden=desc&buscar=PT-901").get_data(as_text=True)
    assert html.index(b.numero) < html.index(a.numero)  # de las últimas a las primeras
    html = c.get("/ov/?orden=asc&buscar=PT-901").get_data(as_text=True)
    assert html.index(a.numero) < html.index(b.numero)


def test_alertas_por_area(app, s):
    from app.services import alerts
    alerts.emit("REPOSICION_SUGERIDA", "Alerta ficticia V32 de almacén", "x", "", "", prioridad="ALTA", dedup_key="V32:1")
    s.commit()
    c = _cliente(app, "coord.almacen")
    html = c.get("/alertas").get_data(as_text=True)
    assert 'class="area-card err"' in html and "Ver todas en una sola lista" in html
    assert "Alerta ficticia V32" not in html  # primero las tarjetas
    html = c.get("/alertas?area=Almac%C3%A9n").get_data(as_text=True)
    assert "Alerta ficticia V32 de almacén" in html and "Todas las áreas" in html
    assert "Alerta ficticia V32" in c.get("/alertas?vista=lista").get_data(as_text=True)


def test_compras_gr_y_eventualmente_mp_mq(app, s, U):
    from app.services import purchasing
    from app.services.core import BusinessError, set_param
    set_param("compras_no_comprables", ["PT"])
    with pytest.raises(BusinessError, match="producto terminado"):
        purchasing.create_request(U("coord.almacen"), "PT-902", 5)
    assert purchasing.create_request(U("coord.almacen"), "GR-901", 5).id
    assert purchasing.create_request(U("coord.almacen"), "MP-903", 5).id
