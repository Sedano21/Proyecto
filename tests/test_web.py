"""Pruebas HTTP: login, CSRF, permisos por pantalla y recorrido de todas las pantallas sin errores."""
import io
import re
from datetime import date, timedelta

import pytest

from app.db import SessionLocal


def login(client, username, password="Demo2026!"):
    r = client.get("/login")
    tok = re.search(r'name="_csrf" value="([^"]+)"', r.get_data(as_text=True)).group(1)
    r = client.post("/login", data={"username": username, "password": password, "_csrf": tok}, follow_redirects=False)
    return tok, r


def csrf(client, path="/"):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else None


def test_login_y_bloqueo(app):
    c = app.test_client()
    tok, r = login(c, "coord.ventas", "malo")
    assert r.status_code == 200 and "incorrectos" in r.get_data(as_text=True)
    tok, r = login(c, "coord.ventas")
    assert r.status_code == 302
    assert c.get("/").status_code == 200


def test_csrf_obligatorio(app):
    c = app.test_client()
    login(c, "coord.ventas")
    r = c.post("/ov/nueva", data={"numero": "X"})
    assert r.status_code == 400


def test_permiso_por_pantalla(app):
    c = app.test_client()
    login(c, "asist.ventas")
    assert c.get("/configuracion").status_code == 403
    assert c.get("/usuarios").status_code == 403
    assert c.get("/ov/").status_code == 200
    c2 = app.test_client()
    login(c2, "montacarguista")
    assert c2.get("/ov/").status_code == 403


PAGES = ["/", "/alertas", "/alertas?agrupar=area", "/alertas?agrupar=grupo&prioridad=ALTA", "/ov/", "/ov/nueva",
         "/ov/preparacion", "/almacen/stock", "/almacen/cargas", "/almacen/cargas/nueva?tipo=BOM", "/almacen/conteos",
         "/almacen/traslados", "/almacen/reempaques", "/produccion/", "/produccion/bom?producto=PT-901&cantidad=100",
         "/produccion/liquidaciones", "/produccion/partes", "/calidad/", "/calidad/certificados", "/abastecimiento/compras",
         "/abastecimiento/reposicion", "/abastecimiento/importaciones", "/distribucion/", "/distribucion/incidencias",
         "/distribucion/flota", "/configuracion", "/configuracion/productos", "/configuracion/clientes", "/usuarios",
         "/alertas/configuracion", "/correo", "/auditoria", "/alertas/preferencias",
         "/configuracion/param/cortes_preparacion/historial", "/ov/precios", "/ov/precios?lista=GRANEL",
         "/ov/precios?sku=PT-901", "/almacen/cargas/nueva?tipo=PRECIOS",
         # v0.6: informes, fichas de cliente, costos, plan de producción, permisos, cargas por área
         "/informes/", "/informes/comercial", "/informes/reempaque", "/informes/produccion", "/informes/distribucion",
         "/ov/clientes", "/ov/clientes/1", "/ov/costos", "/produccion/plan", "/produccion/plan?periodo=SEMANA",
         "/usuarios/permisos", "/usuarios/permisos?vista=matriz", "/almacen/cargas?area=Comercial",
         "/almacen/cargas?area=Producción", "/almacen/cargas/nueva?tipo=CLIENTES", "/almacen/cargas/nueva?tipo=COSTOS",
         "/almacen/cargas/nueva?tipo=MERCADO",
         # v0.7: mercado por origen, comportamiento de clientes
         "/ov/mercado/analisis", "/ov/mercado/informe", "/informes/comercial/cliente/1", "/ov/clientes?grupo=X&canal=Y"] + \
        [f"/calidad/registro/nuevo/{f}" for f in ["MUESTREO", "RECEPCION_MP", "FUMIGACION", "NO_CONFORME", "QUEJA", "NC_ACCION",
                                                  "CONTROL_PESOS", "CONTROL_GRANOS", "RECEPCION_IMPORTADO", "VEHICULO",
                                                  "DISENO_BOBINA", "PROCESO", "INSPECCION_CARGA"]]


@pytest.mark.parametrize("username", ["gerente.general", "sistemas", "coord.almacen", "jefe.calidad", "coord.distribucion",
                                      "compras", "jefe.produccion", "seguridad", "vendedor1", "jefe.ventas",
                                      "coord.almacen.mp", "lider.almacen", "aux.despacho"])
def test_recorrido_pantallas_sin_errores(app, username):
    c = app.test_client()
    login(c, username)
    for p in PAGES:
        r = c.get(p)
        assert r.status_code in (200, 403), (username, p, r.status_code)


def test_flujo_web_ov_y_detalles(app):
    c = app.test_client()
    tok, _ = login(c, "coord.ventas")
    fecha = (date.today() + timedelta(days=2)).isoformat()
    from app.models import Customer
    cid = SessionLocal().query(Customer).first().id
    r = c.post("/ov/nueva", data={"_csrf": tok, "numero": "WEB-1", "customer_id": cid, "fecha_compromiso": fecha,
                                  "product_code": ["PT-901", "PT-903"], "cantidad": ["50", "10"], "precio_unitario": ["999", "999"]},
               follow_redirects=True)
    html = r.get_data(as_text=True)
    # Comercial ve solo el avance de su pedido, no la evaluación de opciones (observaciones al demo v0.6)
    assert r.status_code == 200 and "OV WEB-1" in html and "Seguimiento del pedido" in html
    assert "Alternativas ante faltante" not in html and "Historial (auditoría)" not in html
    from app.models import SalesOrder
    o = SessionLocal().query(SalesOrder).filter_by(numero="WEB-1").one()
    assert c.get(f"/ov/{o.id}/opciones").status_code == 403
    ca = app.test_client()
    login(ca, "coord.almacen")
    assert "Alternativas ante faltante" in ca.get(f"/ov/{o.id}").get_data(as_text=True)
    assert o.estado_stock == "INCOMPLETA"
    # exportación
    r = c.get("/exportar/ov.xlsx")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    # todas las páginas de detalle existentes responden
    c2 = app.test_client()
    login(c2, "sistemas")
    from app.models import Alert, UploadBatch
    s = SessionLocal()
    for a in s.query(Alert).limit(20):
        assert c2.get(f"/alertas/{a.id}").status_code == 200
    for b in s.query(UploadBatch):
        assert c2.get(f"/almacen/cargas/{b.id}").status_code == 200
        assert c2.get(f"/almacen/cargas/{b.id}?filtro=todas").status_code == 200
    assert c2.get(f"/ov/{o.id}").status_code == 200
    assert c2.get(f"/ov/preparacion/{o.id}").status_code == 200


def test_carga_por_web_y_entrega_con_evidencia(app, tmp_path):
    import os
    from app.demo_data import write_stock
    c = app.test_client()
    tok, _ = login(c, "coord.almacen")
    p = os.path.join(tmp_path, "e.xlsx")
    write_stock(p, date.today(), con_errores=True)
    with open(p, "rb") as fh:
        r = c.post("/almacen/cargas/nueva", data={"_csrf": tok, "tipo": "STOCK", "archivo": (fh, "e.xlsx")},
                   content_type="multipart/form-data", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "VALIDADO CON ERRORES" in html and "Cantidad negativa" in html


def test_pantallas_ruta_y_folio_en_cada_etapa(app):
    """Renderiza la ruta (propuesta, confirmada) y el folio para los roles del despacho TO-BE."""
    from app.models import Route
    from app.services import distribution as dist
    from app.services.orders import create_order
    from app.models import Customer, User
    s = SessionLocal()
    u = s.query(User).filter_by(username="coord.ventas").one()
    c = s.query(Customer).first()
    o = create_order(u, "WEB-R1", c.id, date.today() + timedelta(days=1), [{"product_code": "PT-905", "cantidad": 20,
                                                                                      "precio_unitario": 50}])
    s.commit()
    r = dist.active_stop(o).route
    for estado_paso in ("PROPUESTA", "CONFIRMADA"):
        if estado_paso == "CONFIRMADA":
            dist.confirm_route(r, s.query(User).filter_by(username="coord.distribucion").one())
            s.commit()
        for user in ("coord.distribucion", "aux.despacho", "seguridad", "facturacion", "gerente.general", "lider.almacen"):
            cl = app.test_client()
            login(cl, user)
            for path in (f"/distribucion/ruta/{r.id}", f"/distribucion/ruta/{r.id}/folio", f"/distribucion/ruta/{r.id}/folio?tipo=preguia",
                         f"/ov/preparacion/{o.id}"):
                resp = cl.get(path)
                assert resp.status_code in (200, 403), (user, path, resp.status_code)


def test_detalle_de_todas_las_alertas_incluidas_las_sin_documento(app):
    """Regresión: las alertas sin documento asociado (carga SAP atrasada, merma de un parte) rompían su detalle."""
    from app.models import Alert, User
    from app.services.scheduler import run_checks
    s = SessionLocal()
    run_checks(s.query(User).filter_by(username="sistemas").one())
    s.commit()
    c = app.test_client()
    login(c, "gerente.general")
    for a in s.query(Alert):
        assert c.get(f"/alertas/{a.id}").status_code == 200, (a.type_code, a.entidad, a.entidad_id)
