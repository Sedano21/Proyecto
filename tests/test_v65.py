"""V65 (20-nov-2026): el primer ingreso a la base productiva falla con «Switch company error: -5027» y el segundo entra:
el módulo reintenta solo ese error."""
import io
import json
import urllib.error

from .test_v62 import CFG, _Resp


def _opener(fallas, codigo=b"Switch company error: -5027"):
    llamadas = []

    def opener(req, timeout):
        llamadas.append(1)
        if len(llamadas) <= fallas:
            raise urllib.error.HTTPError(req.full_url, 500, "x", {},
                                         io.BytesIO(b'{"error":{"message":{"value":"' + codigo + b'"}}}'))
        return _Resp(json.dumps({"SessionId": "S1"}).encode())
    return opener, llamadas


def test_reintenta_el_switch_company():
    from app.services.sap_sl import ServiceLayer
    op, llamadas = _opener(1)
    sl = ServiceLayer(CFG, opener=op)
    sl.login(intentos=3, espera=0)
    assert sl.session == "S1" and len(llamadas) == 2


def test_no_reintenta_otros_errores():
    from app.services.core import BusinessError
    from app.services.sap_sl import ServiceLayer
    op, llamadas = _opener(5, b"Fail to get DB Credentials from SLD")
    try:
        ServiceLayer(CFG, opener=op).login(intentos=3, espera=0)
        raise AssertionError("debía fallar")
    except BusinessError:
        assert len(llamadas) == 1


def test_se_rinde_tras_los_intentos():
    from app.services.core import BusinessError
    from app.services.sap_sl import ServiceLayer
    op, llamadas = _opener(10)
    try:
        ServiceLayer(CFG, opener=op).login(intentos=3, espera=0)
        raise AssertionError("debía fallar")
    except BusinessError as e:
        assert "-5027" in str(e) and len(llamadas) == 3
