"""V20 (04-nov-2026): rendimiento, límites contra abusos, notificaciones push, lotes con variantes por puntos y tablas que
se acomodan. Datos ficticios."""
import base64
import json
import os
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from .conftest import alerts_of
from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


def _csrf(c, path="/"):
    html = c.get(path).get_data(as_text=True)
    return html.split('name="csrf" content="')[1].split('"')[0]


# ------------------------------------------------------------------ rendimiento
def test_cache_de_parametros_por_peticion_se_limpia_al_editar(app, s, U):
    from app.services.core import param, set_param
    with app.test_request_context("/"):
        antes = param("push_prioridades")
        assert param("push_prioridades") is antes  # misma petición: no vuelve a consultar
        set_param("push_prioridades", ["ALTA"], U("sistemas"))
        assert param("push_prioridades") == ["ALTA"]


def test_buzon_de_alertas_se_recalcula_tras_una_alerta_nueva(app, s, U):
    from app.services import alerts
    from flask import g
    u = U("coord.almacen")
    with app.test_request_context("/"):
        g.user = u
        n = len(alerts.inbox(u, solo_abiertas=True))
        alerts.emit("OV_FALTANTE", "Faltante de prueba", "x", "SalesOrder", "1", extra_users=[u.id])
        s.flush()
        assert len(alerts.inbox(u, solo_abiertas=True)) == n + 1


def test_inicio_de_jefaturas_y_comercial_con_ov_no_falla(app, s, new_order):
    """Regresión: el inicio daba error 500 (o.vendedor) cuando había OV en el tablero de despachos."""
    new_order([("PT-901", 5)])
    s.commit()
    for u in ("gerente.general", "coord.ventas", "jefe.logistica", "jefe.operaciones", "vendedor1"):
        r = _cliente(app, u).get("/")
        assert r.status_code == 200, u
        assert "app;dur=" in r.headers.get("Server-Timing", "")


def test_sondeo_de_alertas_responde_lo_mismo_si_nada_cambio(app, s, U):
    c = _cliente(app, "coord.almacen")
    a = c.get("/alertas/estado.json").get_json()
    b = c.get("/alertas/estado.json").get_json()
    assert a == b
    from app.db import db
    from app.services import alerts
    alerts.emit("OV_FALTANTE", "Otra alerta", "x", "SalesOrder", "2", extra_users=[U("coord.almacen").id], prioridad="ALTA")
    db().commit()  # tras una petición del cliente de pruebas, la sesión vigente es la de db()
    assert c.get("/alertas/estado.json").get_json()["abiertas"] == a["abiertas"] + 1


def test_configuracion_de_gunicorn():
    ns = {}
    exec(open(os.path.join(os.path.dirname(__file__), "..", "deploy", "gunicorn.conf.py")).read(), ns)
    assert ns["worker_class"] == "gthread" and ns["workers"] >= 2 and ns["threads"] == 4 and ns["keepalive"] > 30
    svc = open(os.path.join(os.path.dirname(__file__), "..", "deploy", "operaciones.service")).read()
    assert "gunicorn.conf.py" in svc


# ------------------------------------------------------------------ límites contra abusos
def test_limite_de_ingresos_por_ip(app, monkeypatch):
    from app.services import limites
    limites.reiniciar()
    monkeypatch.setenv("LIMITE_LOGIN_MIN", "3")
    app.config["LIMITES_EN_PRUEBAS"] = True
    c = app.test_client()
    tok = c.get("/login").get_data(as_text=True).split('name="_csrf" value="')[1].split('"')[0]
    codigos = [c.post("/login", data={"_csrf": tok, "username": "nadie", "password": "x"}).status_code for _ in range(5)]
    assert codigos[:3] != [429, 429, 429] and codigos[-1] == 429
    limites.reiniciar()


def test_ventana_deslizante():
    from app.services import limites
    limites.reiniciar()
    assert all(limites.permitido("k", 3) for _ in range(3)) and not limites.permitido("k", 3)
    assert limites.permitido("otra", 3)
    limites.reiniciar()


# ------------------------------------------------------------------ notificaciones push
def _suscripcion(n=1):
    return {"endpoint": f"https://push.ejemplo.invalid/s/{n}", "keys": {"p256dh": "BPRUEBA" + "A" * 80, "auth": "AUTHPRUEBA12345"}}


def test_service_worker_y_manifiesto(app):
    c = app.test_client()
    r = c.get("/sw.js")
    assert r.status_code == 200 and r.headers.get("Service-Worker-Allowed") == "/" and b"showNotification" in r.data
    m = c.get("/manifest.webmanifest")
    assert m.status_code == 200 and json.loads(m.data)["display"] == "standalone"


def test_suscribir_dispositivo_y_recibir_alerta_tras_guardar(app, s, U):
    from app.services import alerts
    from app.models import PushSubscription
    app.config["PUSH_ENVIADOS"] = []
    c = _cliente(app, "coord.almacen")
    assert c.get("/push/clave").get_json()["clave"]
    r = c.post("/push/suscribir", json={"suscripcion": _suscripcion()}, headers={"X-CSRF": _csrf(c)})
    assert r.get_json()["ok"] and s.query(PushSubscription).count() == 1
    u = U("coord.almacen")
    # se deshace: no se avisa
    alerts.emit("OV_FALTANTE", "No debe avisar", "x", "SalesOrder", "9", extra_users=[u.id], prioridad="ALTA")
    s.rollback()
    assert app.config["PUSH_ENVIADOS"] == []
    # se guarda: se avisa con título, enlace y urgencia
    a = alerts.emit("OV_FALTANTE", "Faltante en OV-000123", "Falta stock", "SalesOrder", "9", extra_users=[u.id], prioridad="ALTA")
    s.commit()
    datos = app.config["PUSH_ENVIADOS"][-1][4]
    assert "Faltante en OV-000123" in datos["title"] and datos["url"] == f"/alertas/{a.id}" and datos["urgente"]
    # BAJA no llega al celular (parámetro push_prioridades)
    n = len(app.config["PUSH_ENVIADOS"])
    alerts.emit("OV_FALTANTE", "Informativa", "x", "SalesOrder", "10", extra_users=[u.id], prioridad="BAJA")
    s.commit()
    assert len(app.config["PUSH_ENVIADOS"]) == n
    html = c.get("/notificaciones").get_data(as_text=True)
    assert "Mis dispositivos" in html and "Quitar" in html


def test_suscripcion_invalida(app):
    c = _cliente(app, "coord.almacen")
    r = c.post("/push/suscribir", json={"suscripcion": {"endpoint": "http://inseguro"}}, headers={"X-CSRF": _csrf(c)})
    assert r.status_code == 400


def test_envio_real_cifrado_con_vapid(app):
    """Envío de punta a punta a un servicio de push local: cabecera VAPID, vigencia y contenido cifrado (aes128gcm)."""
    http_ece = pytest.importorskip("http_ece")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from app.services import push
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    b64 = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")  # noqa: E731
    recibido = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            recibido["cuerpo"] = self.rfile.read(int(self.headers["Content-Length"]))
            recibido["cab"] = {k.lower(): v for k, v in self.headers.items()}
            self.send_response(201)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with app.app_context():
            push._enviar([(0, f"http://127.0.0.1:{srv.server_address[1]}/p", b64(pub), b64(auth),
                           {"title": "Prueba", "body": "Cuerpo", "url": "/alertas", "tag": "t", "urgente": True})])
    finally:
        srv.shutdown()
    cab = recibido["cab"]
    assert cab["authorization"].startswith("vapid t=") and cab["urgency"] == "high" and cab["ttl"] == "86400"
    claro = http_ece.decrypt(recibido["cuerpo"], private_key=priv, auth_secret=auth, version="aes128gcm")
    assert json.loads(claro)["title"] == "Prueba"


# ------------------------------------------------------------------ lotes con variantes por puntos
def test_lote_base_y_variante():
    from app.services import lotes
    assert lotes.base("000863FA..") == "000863FA" and lotes.variante("000863FA..") == 2
    assert lotes.variante("000863FA") == 0 and lotes.etiqueta("000863FA.") == "000863FA · 2.ª prod."
    assert lotes.tiene_coma("201025IN,") and not lotes.tiene_coma("201025IN.")


def test_carga_de_stock_con_variantes(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import uploads
    wb = Workbook()
    ws = wb.active
    ws.append(["articulo", "descripción", "lote", "almacen", "nombre_almacen", "cantidad", "fecha_venc", "fecha_fab", "fecha_admision"])
    ws.append(["PT-901", "PRODUCTO DEMO", "000863FA", "ALM-001", "PT", 5, "10/02/2027", "10/02/2026", ""])
    ws.append(["PT-901", "PRODUCTO DEMO", "000863FA.", "ALM-001", "PT", 3, "03/03/2027", "03/03/2026", ""])  # otra producción
    ws.append(["PT-901", "PRODUCTO DEMO", "111111AB", "ALM-001", "PT", 3, "01/01/2027", "01/01/2026", ""])
    ws.append(["PT-901", "PRODUCTO DEMO", "111111AB.", "ALM-001", "PT", 3, "01/01/2027", "01/01/2026", ""])  # mismas fechas
    ws.append(["PT-901", "PRODUCTO DEMO", "201025IN,", "ALM-001", "PT", 1, "", "", ""])
    ws.append(["PT-901", "PRODUCTO DEMO", "S00791.001", "ALM-001", "PT", 1, "", "", ""])
    f = tmp_path / "consulta_sap.xlsx"
    wb.save(f)
    b = uploads.create_batch(U("coord.almacen"), "STOCK", str(f), "consulta_sap.xlsx")  # encabezados de la consulta de SAP
    av = {r.datos["lote"]: " | ".join(r.advertencias or []) for r in b.rows}
    assert "inusual" not in av["000863FA."] and "duplicado" not in av["000863FA."]
    assert "Posible duplicado" in av["111111AB"] and "Posible duplicado" in av["111111AB."]
    assert "coma" in av["201025IN,"]
    assert "inusual" not in av["S00791.001"]


def test_stock_busca_el_lote_y_todas_sus_variantes(app, s):
    from app.models import StockLot
    for lt in ("777001ZZ", "777001ZZ.", "777001ZZ.."):
        s.add(StockLot(product_code="PT-901", warehouse_code="ALM-001", lote=lt, cantidad=5, estado="DISPONIBLE",
                       fecha_venc=date.today() + timedelta(days=200)))
    s.commit()
    html = _cliente(app, "coord.almacen").get("/almacen/stock?q=777001ZZ").get_data(as_text=True)
    assert html.count('title="En SAP: 777001ZZ.') == 2 and "<sup>3.ª</sup>" in html


# ------------------------------------------------------------------ tablas que se acomodan
def test_tablas_apiladas_automaticas(app):
    js = open(os.path.join(app.static_folder, "v20.js"), encoding="utf-8").read()
    css = open(os.path.join(app.static_folder, "style.css"), encoding="utf-8").read()
    assert "ResizeObserver" in js and "apilada" in js and "table.apilada td[data-label]::before" in css
    html = _cliente(app, "coord.almacen").get("/").get_data(as_text=True)
    assert "v20.js" in html and 'rel="manifest"' in html
