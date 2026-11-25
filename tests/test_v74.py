"""V74 (25-nov-2026): pedidos de Calidad. Fumigación por pasos (decide, espacio, programa), fumigación de unidades
validada por Calidad, etiquetas solo MP/PT con lote y vencimiento, especificaciones por producto, referencias de los
certificados, informe de recepción de compras, controles de Calidad en el proceso y observación de calidad en la carga.
Solo datos ficticios."""
import io
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .test_v12 import _route
from .test_v64 import _cliente


def _lote(s, code="PT-901", cant=50, lote="V74-L1"):
    from app.models import StockLot
    wh = s.query(StockLot).filter(StockLot.product_code == "PT-901").first().warehouse_code
    l = StockLot(product_code=code, warehouse_code=wh, lote=lote, cantidad=cant, estado="DISPONIBLE")
    s.add(l)
    s.commit()
    return l


def test_fumigacion_decide_espacio_y_programa(app, s, U):
    from app.services import fumigacion_solicitudes as fs
    l = _lote(s)
    r = fs.solicitar(U("coord.almacen"), "Almacén", "Revisión: presencia de gorgojo", [{"lot_id": l.id, "cantidad": ""}])
    with pytest.raises(BusinessError, match="Primero decida"):
        fs.aprobar(U("jefe.calidad"), r, "Patio", date.today(), date.today() + timedelta(days=2))
    with pytest.raises(BusinessError):
        fs.decidir(U("coord.almacen"), r, True)
    fs.decidir(U("jefe.calidad"), r, True, "se fumiga")
    assert r.estado == "POR_ESPACIO"
    with pytest.raises(BusinessError, match="Almacén confirme el espacio"):
        fs.aprobar(U("jefe.calidad"), r, "Patio", date.today(), date.today() + timedelta(days=2))
    with pytest.raises(BusinessError, match="por qué no hay espacio"):
        fs.confirmar_espacio(U("coord.almacen"), r, False)
    fs.confirmar_espacio(U("coord.almacen"), r, False, nota="contenedores llenos")
    assert r.estado == "SIN_ESPACIO"
    fs.confirmar_espacio(U("coord.almacen"), r, True, "Contenedor 2")
    assert r.estado == "POR_PROGRAMAR" and fs.lugar_sugerido(r) == "Contenedor 2"
    pref = fs.proximo_dia_preferido(date(2026, 11, 23))  # lunes → martes
    assert pref == date(2026, 11, 24) and pref.weekday() in fs.dias_preferidos()
    lunes = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    with pytest.raises(BusinessError, match="motivo"):
        fs.aprobar(U("jefe.calidad"), r, "Contenedor 2", lunes, lunes + timedelta(days=3))
    fs.aprobar(U("jefe.calidad"), r, "Contenedor 2", lunes, lunes + timedelta(days=3), "urgente por despacho")
    assert r.estado == "APROBADA"
    s.commit()
    html = _cliente(app, "jefe.calidad").get("/calidad/fumigacion/solicitudes").get_data(as_text=True)
    assert "Programada" in html and "contenedores llenos" in html


def test_no_se_fumiga(s, U):
    from app.services import fumigacion_solicitudes as fs
    l = _lote(s, lote="V74-L2")
    r = fs.solicitar(U("coord.almacen"), "Almacén", "revisión", [{"lot_id": l.id}])
    with pytest.raises(BusinessError, match="por qué no se fumiga"):
        fs.decidir(U("superv.calidad"), r, False)
    fs.decidir(U("superv.calidad"), r, False, "sin presencia de plaga")
    assert r.estado == "RECHAZADA"


def test_fumigacion_de_unidad_sin_producto_y_validada(app, s, U):
    from app.models import Vehicle
    from app.services import maintenance as m
    v = s.query(Vehicle).first()
    lg = m.log_sanitation(U("asist.calidad"), "FUMIGACION", date.today(), vehicle=v, responsable="Empresa demo",
                          vence=date.today() + timedelta(days=30))
    assert lg.producto == ""
    with pytest.raises(BusinessError):
        m.validate_vehicle_fumigation(U("asist.calidad"), lg, True)
    with pytest.raises(BusinessError, match="qué está mal"):
        m.validate_vehicle_fumigation(U("jefe.calidad"), lg, False)
    m.validate_vehicle_fumigation(U("jefe.calidad"), lg, True)
    assert lg.validacion["resultado"] == "CONFORME"
    s.commit()
    html = _cliente(app, "jefe.calidad").get("/mantenimiento/?tab=unidades").get_data(as_text=True)
    assert "Registro conforme" in html and 'name="producto" required' not in html


def test_etiquetas_mp_pt_lote_y_vencimiento(app, s, U, cust):
    from app.models import Product
    from app.services import etiquetas as e
    otro = s.query(Product).filter(Product.tipo.notin_(("MP", "PT"))).first()
    if otro is not None:
        with pytest.raises(BusinessError, match="solo para materia prima"):
            e.guardar(U("jefe.calidad"), otro.code, instrucciones="x")
    c = cust()
    et = e.guardar(U("jefe.calidad"), "PT-901 · algo", f"{c.nombre} · {c.ruc}", "", "una por caja", lote="L-74",
                   fecha_vencimiento=(date.today() + timedelta(days=200)).isoformat())
    assert et.customer_id == c.id and et.lote == "L-74" and et.fecha_vencimiento and et.marca == ""
    assert all(p.tipo in ("MP", "PT") for p in e.productos())
    s.commit()
    html = _cliente(app, "jefe.calidad").get("/calidad/etiquetas").get_data(as_text=True)
    assert "Cosecha Andina" in html and "L-74" in html and 'list="et-clientes"' in html


def test_especificaciones_pdf_y_excel(app, s, U):
    from openpyxl import Workbook
    from app.services import calidad_v74 as c74
    wb = Workbook()
    wb.active.append(["Parámetro", "Especificación"])
    wb.active.append(["Humedad", "máx. demo"])
    buf = io.BytesIO()
    wb.save(buf)
    cl = _cliente(app, "jefe.calidad")
    html = cl.get("/calidad/especificaciones?producto=PT-901").get_data(as_text=True)
    import re
    tok = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
    rv = cl.post("/calidad/especificaciones?producto=PT-901", data={
        "_csrf": tok, "producto": "PT-901", "carpeta": "ESPECIFICACIONES",
        "archivos": [(io.BytesIO(buf.getvalue()), "espec_demo.xlsx"), (io.BytesIO(b"%PDF-1.4 demo"), "ficha_demo.pdf")]},
        content_type="multipart/form-data", follow_redirects=True)
    out = rv.get_data(as_text=True)
    assert "2 archivo(s) guardados" in out and "máx. demo" in out
    assert len(c74.documentos("PT-901")["ESPECIFICACIONES"]) == 2
    from app.models import Product
    with pytest.raises(BusinessError):
        c74.subir(U("asist.calidad"), s.get(Product, "PT-901"), "ESPECIFICACIONES", [("x.pdf", "x.pdf")])
    nuevos, ret = c74.subir(U("superv.calidad"), s.get(Product, "PT-901"), "ESPECIFICACIONES", [("y.pdf", "y.pdf")], True)
    assert ret == 2 and len(c74.documentos("PT-901")["ESPECIFICACIONES"]) == 1


def test_referencias_y_picking_en_certificado(app, s, U):
    from app.models import StockLot
    from app.services import calidad_v74 as c74
    from app.services import quality as q
    with pytest.raises(BusinessError):
        c74.guardar_referencias(U("asist.calidad"), [("ARVEJA", "Norma demo")])
    c74.guardar_referencias(U("jefe.calidad"), [("frijol", "NTP demo frijol"), ("ARVEJA", "Norma demo arveja"), ("", "")])
    assert q.param("referencias_ntp") == {"FRIJOL": "NTP demo frijol", "ARVEJA": "Norma demo arveja"}
    lot = s.query(StockLot).filter(StockLot.product_code == "PT-901", StockLot.cantidad > 0).first()
    c = q.generate_certificate(lot, U("jefe.calidad"))
    s.commit()
    html = _cliente(app, "jefe.calidad").get(f"/calidad/certificados/{c.id}").get_data(as_text=True)
    assert "Detalle del picking" in html and "Especificaciones del producto" in html


def test_informe_de_recepcion_de_compra(app, s, U):
    from app.models import PurchaseRequest
    from app.services import calidad_v74 as c74
    pr = PurchaseRequest(product_code="GR-901", cantidad=100, estado="RECIBIDA", proveedor="Proveedor demo")
    s.add(pr)
    s.commit()
    with pytest.raises(BusinessError):
        c74.subir_informe_compra(U("compras"), pr, "inf.pdf")
    c74.subir_informe_compra(U("superv.calidad"), pr, "inf_demo.xlsx", "informe.xlsx", "ok", "CONFORME")
    assert c74.informe_compra(pr)["resultado"] == "CONFORME"
    s.commit()
    html = _cliente(app, "compras").get("/calidad/informes-recepcion").get_data(as_text=True)
    assert f"Compra #{pr.id}" in html and "informe.xlsx" in html


def test_controles_de_calidad_en_el_proceso(app, s, U):
    from app.models import Alert, ProductionReport
    from app.services import calidad_v74 as c74
    r = ProductionReport(linea="R2", tipo="ENVASADO", fecha=date.today(), product_code="PT-905", peso_entrada_kg=500,
                         estado="EN PROCESO")
    s.add(r)
    s.commit()
    for u in ("jefe.calidad", "superv.calidad", "asist.calidad"):
        c74.registrar_control(U(u), r, "Peso", "0.50", True)
    with pytest.raises(BusinessError, match="no conforme"):
        c74.registrar_control(U("jefe.calidad"), r, "Sellado", "", False)
    c74.registrar_control(U("jefe.calidad"), r, "Sellado", "", False, "sello abierto en 3 bolsas")
    with pytest.raises(BusinessError):
        c74.registrar_control(U("jefe.produccion"), r, "Peso", "1", True)
    assert len(r.controles_calidad) == 4
    assert s.query(Alert).filter_by(type_code="CALIDAD_CONTROL_PROCESO").count() >= 1
    s.commit()
    cl = _cliente(app, "superv.calidad")
    assert "sello abierto" in cl.get(f"/produccion/parte/{r.id}").get_data(as_text=True)
    assert "Controles de Calidad en el proceso" in cl.get("/calidad/linea").get_data(as_text=True)
    assert "Registrar control de Calidad" in cl.get("/produccion/monitoreo").get_data(as_text=True)


def test_observacion_de_calidad_en_la_carga_bloquea_salida(app, s, U, cust):
    from app.services import carga_v70 as cv
    from app.services import ruta_chofer_v73 as rc
    r, o = _route(s, U, cust)
    g = rc.checklist_guia(r, o.id)
    lid = g["items"][0]["order_line_id"]
    res, _ = rc.registrar_checklist(U("aux.despacho"), r, o.id, {str(lid): {"ok": True}}, obs_calidad="sacos húmedos")
    assert not res["conforme"] and cv.obs_calidad_abiertas(r)
    assert any("Calidad" in x for x in cv.falta_para_salir(r))
    with pytest.raises(BusinessError):
        cv.resolver_obs_calidad(U("aux.despacho"), r, 1, True)
    with pytest.raises(BusinessError, match="corregirse"):
        cv.resolver_obs_calidad(U("jefe.calidad"), r, 1, False)
    cv.resolver_obs_calidad(U("jefe.calidad"), r, 1, False, "cambiar los 2 sacos")
    assert cv.obs_calidad_abiertas(r)
    cv.resolver_obs_calidad(U("jefe.calidad"), r, 1, True, "cambiados")
    assert not cv.obs_calidad_abiertas(r) and not any("Calidad" in x for x in cv.falta_para_salir(r))
    s.commit()
    html = _cliente(app, "jefe.calidad").get(f"/distribucion/ruta/{r.id}").get_data(as_text=True)
    assert "sacos húmedos" in html and "Calidad aprobó la salida" in html


def test_formatos_y_menu_de_calidad(app):
    cl = _cliente(app, "jefe.calidad")
    html = cl.get("/calidad/formatos").get_data(as_text=True)
    assert "Control de higiene de personal" in html and "Registrar" in html and "Reporte" in html
    menu = cl.get("/calidad/bandeja").get_data(as_text=True)
    for t in ("Especificaciones por producto", "Informes de recepción", "Formatos (higiene y todos)", "Fumigación de unidades",
              "Referencias de certificados"):
        assert t in menu
