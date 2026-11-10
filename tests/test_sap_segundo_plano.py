"""10-nov-2026: «Traer de SAP» en segundo plano y guías con los números de OV pedidos en grupos."""
from app.services.core import BusinessError

from .test_web import login


class _SLFalso:
    def __init__(self, n_entregas=45):
        self.cfg = {"user": "x"}
        self.consultas = []
        self.n = n_entregas

    def get_all(self, path, params=None):
        self.consultas.append(path)
        if path == "DeliveryNotes":
            return [{"DocNum": 9000 + i, "DocDate": "2026-11-09", "FolioPrefixString": "T001", "FolioNumber": 100 + i,
                     "DocumentLines": [{"BaseType": 17, "BaseEntry": 500 + i, "ItemCode": "PT-901", "Quantity": 2}]}
                    for i in range(self.n)]
        if path == "Orders":
            ids = [int(x.split(" eq ")[1]) for x in params["$filter"].split(" or ")]
            assert len(ids) <= 20
            return [{"DocEntry": i, "DocNum": 70000 + i} for i in ids]
        raise AssertionError(path)

    def _req(self, *a, **k):
        raise AssertionError("no debe pedir las OV una por una")


def test_guias_piden_las_ov_en_grupos_de_20(app):
    from app.services import sap_sl
    sl = _SLFalso(45)
    filas = sap_sl.rows_despachos(sl)
    assert len(filas) == 45 and filas[0]["Número de OV"] == 70500 and filas[0]["Número de guía"] == "T001-100"
    assert sl.consultas.count("Orders") == 3  # 45 OV → 3 consultas (antes 45)


def test_traer_de_sap_en_segundo_plano_deja_estado_y_carga(app, s, U, monkeypatch):
    from app.services import sap_sl
    llamadas = []

    class _Carga:
        id = 77

    def _sync(tipo, user, up):
        llamadas.append(tipo)
        return _Carga()
    monkeypatch.setattr(sap_sl, "sync", _sync)
    sap_sl.sync_background(app, "DESPACHOS", U("sistemas"), "/tmp")
    j = sap_sl.job_state("DESPACHOS")
    assert llamadas == ["DESPACHOS"] and j["estado"] == "OK" and j["carga"] == 77

    def _falla(tipo, user, up):
        raise BusinessError("SAP respondió 500")
    monkeypatch.setattr(sap_sl, "sync", _falla)
    sap_sl.sync_background(app, "DESPACHOS", U("sistemas"), "/tmp")
    assert sap_sl.job_state("DESPACHOS")["estado"] == "ERROR"
    # no se lanza dos veces a la vez
    sap_sl._job_set("STOCK", {"estado": "EN_CURSO", "inicio": "2999-01-01T00:00:00", "usuario": "x"})
    try:
        sap_sl.sync_background(app, "STOCK", U("sistemas"), "/tmp")
        raise AssertionError("debió rechazar")
    except BusinessError:
        pass


def test_pantalla_muestra_trayendo_y_se_actualiza(app):
    from app.services import sap_sl
    with app.app_context():
        sap_sl._job_set("CLIENTES", {"estado": "EN_CURSO", "inicio": "2999-01-01T10:15:00", "usuario": "Sistemas"})
    c = app.test_client()
    login(c, "sistemas")
    html = c.get("/almacen/cargas/sap").get_data(as_text=True)
    assert "Trayendo de SAP" in html and "location.reload" in html
