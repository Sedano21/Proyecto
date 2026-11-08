"""08-nov-2026: certificado del Service Layer vencido → se fija por huella SHA-256 (SAP_SL_HUELLA)."""
import datetime
import hashlib
import http.server
import ssl
import threading

import pytest

cryptography = pytest.importorskip("cryptography")


def _cert_vencido(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hanab1-demo")])
    hoy = datetime.datetime(2020, 1, 1)
    c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key()).serial_number(1)
         .not_valid_before(hoy).not_valid_after(hoy + datetime.timedelta(days=30)).sign(k, hashes.SHA256()))
    cp, kp = tmp_path / "c.pem", tmp_path / "k.pem"
    cp.write_bytes(c.public_bytes(serialization.Encoding.PEM))
    kp.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cp, kp, hashlib.sha256(c.public_bytes(serialization.Encoding.DER)).hexdigest()


def test_certificado_vencido_aceptado_solo_con_la_huella_exacta(tmp_path, monkeypatch):
    from app.services import sap_sl
    cp, kp, huella = _cert_vencido(tmp_path)

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": 1}')

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cp, kp)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"https://127.0.0.1:{srv.server_address[1]}/"
    try:
        con_dos_puntos = ":".join(huella[i:i + 2] for i in range(0, 64, 2)).upper()
        assert sap_sl._huella("sha256 Fingerprint=" + con_dos_puntos) == huella
        assert sap_sl._opener_con_huella(huella).open(url, timeout=5).read() == b'{"ok": 1}'
        with pytest.raises(Exception):  # otra huella: se rechaza aunque el servidor responda
            sap_sl._opener_con_huella("0" * 64).open(url, timeout=5)
        with pytest.raises(Exception):  # sin huella, la verificación normal rechaza el certificado vencido
            import urllib.request
            urllib.request.urlopen(url, timeout=5, context=ssl.create_default_context(cafile=str(cp)))
        monkeypatch.setenv("SAP_SL_HUELLA", con_dos_puntos)
        assert sap_sl.config()["huella"] == huella
    finally:
        srv.shutdown()
