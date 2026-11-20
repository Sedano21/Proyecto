"""V62 (20-nov-2026): el vigilante reutiliza la sesión de SAP, la renueva sola si vence y espacia los reintentos cuando
SAP rechaza el ingreso (p. ej. «Switch company error: -5027»), con un mensaje que dice qué revisar."""
import io
import json
import urllib.error

from .test_v32 import _SLFirmas

CFG = {"url": "https://sap.invalid:50000/b1s/v1", "company": "ZZZ_PRUEBA", "user": "u", "password": "p", "verify": True,
       "ca": "", "timeout": 5, "huella": ""}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sesion_vencida_se_renueva_sola():
    from app.services.sap_sl import ServiceLayer
    llamadas = []
    vencida = {"v": True}

    def opener(req, timeout):
        llamadas.append(req.full_url.rsplit("/", 1)[-1])
        if req.full_url.endswith("Login"):
            return _Resp(json.dumps({"SessionId": f"S{len(llamadas)}"}).encode())
        if vencida["v"]:
            vencida["v"] = False
            raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b'{"error":{"message":{"value":"Invalid session"}}}'))
        return _Resp(b'{"value": [1]}')
    sl = ServiceLayer(CFG, opener=opener)
    sl.login()
    assert sl.get_all("Items") == [1]
    assert llamadas == ["Login", "Items", "Login", "Items"]


def test_switch_company_explica_que_revisar():
    from app.services.core import BusinessError
    from app.services.sap_sl import ServiceLayer

    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "x", {},
                                     io.BytesIO(b'{"error":{"message":{"value":"Switch company error: -5027"}}}'))
    try:
        ServiceLayer(CFG, opener=opener).login()
        raise AssertionError("debía fallar")
    except BusinessError as e:
        assert "-5027" in str(e) and "servidor SAP" in str(e) and "cola" in str(e)


def test_vigilante_reutiliza_la_sesion(app, s, U, monkeypatch):
    from app.services import balance_of, compras_sap, facturacion_sap, facturas_reserva, prefacturas, sap_sl, sap_v31, sap_vigia
    for mod, nombre, fn in [(sap_v31, "sync_historial", lambda u, sl=None, completo=False: None),
                            (sap_v31, "tiene_historial", lambda: True), (sap_v31, "necesita_relectura", lambda: False),
                            (facturas_reserva, "sync", lambda u, sl=None: None), (balance_of, "sync", lambda u, sl=None: None),
                            (sap_sl, "sync", lambda *a, **k: None), (sap_sl, "sync_facturas", lambda *a, **k: None),
                            (facturacion_sap, "sync", lambda *a, **k: None), (compras_sap, "sync_seguro", lambda *a, **k: None),
                            (prefacturas, "sincronizar_seguro", lambda *a, **k: None),
                            (sap_sl, "push_pending_orders", lambda *a, **k: None),
                            (sap_sl, "push_pending_guides", lambda *a, **k: None)]:
        monkeypatch.setattr(mod, nombre, fn)

    class SL(_SLFirmas):
        ingresos = 0
        salidas = 0

        def __init__(self):
            super().__init__(1)
            self.session = None
            self.cfg = sap_sl.config()

        def login(self):
            SL.ingresos += 1
            self.session = "S"

        def logout(self):
            SL.salidas += 1
            self.session = None
    monkeypatch.setattr(sap_vigia, "_SL", SL())
    u = U("sistemas")
    for _ in range(3):
        sap_vigia.ciclo(u, "/tmp")
        s.commit()
    assert SL.ingresos == 1 and SL.salidas == 0


def test_rechazo_de_sap_queda_registrado_y_espera(app, s, U, monkeypatch):
    from app.services import sap_sl, sap_vigia
    from app.services.core import BusinessError
    llamadas = []

    def ciclo(*a, **k):
        llamadas.append(1)
        raise BusinessError(sap_sl.explicar_error("SAP respondió 500: Switch company error: -5027"))
    monkeypatch.setattr(sap_sl, "configured", lambda: True)
    monkeypatch.setattr(sap_vigia, "ciclo", ciclo)
    monkeypatch.setattr(sap_vigia, "_en_horario", lambda ahora: True)
    sap_vigia.vigilar(app, cada_seg=0, una_vez=True)
    st = sap_sl.connection_state()
    assert llamadas == [1] and st.get("ok") is False and "-5027" in st.get("error", "")
