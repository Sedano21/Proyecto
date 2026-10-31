"""Respuestas del 13-oct (tercera parte, R1–R6): formatos con logos (OV, guía, certificados por tipo), vida útil restante,
RUC en la lista de clientes, costos (venta bajo costo) y comparación automática con precios de mercado."""
import io
from datetime import date, timedelta

import openpyxl
import pytest

from app.models import Alert, Certificate, Customer, CustomerCondition, MarketPrice, ProductCost, StockLot
from app.services.core import BusinessError, param, set_param

from .conftest import alerts_of
from .test_web import csrf, login


# ------------------------------ R6: formatos -------------------------------
def test_monto_en_letras_como_en_la_ov():
    from app.services.documents import monto_en_letras
    assert monto_en_letras(49204.76) == "cuarenta y nueve mil doscientos cuatro y 76 / 100 SOLES"
    assert monto_en_letras(21001) == "veintiún mil uno y 00 / 100 SOLES"
    assert monto_en_letras(1_000_100.5).startswith("un millón cien")


def test_ov_imprimible_con_los_tres_logos(app, s, new_order):
    o = new_order([("PT-905", 10)])
    o.forma_pago = "Crédito 30 días"
    o.lines[0].tax_code = "EXO"
    s.commit()
    c = app.test_client()
    login(c, "coord.ventas")
    html = c.get(f"/ov/{o.id}/imprimir").get_data(as_text=True)
    for logo in ("logo_corporacion_productiva.png", "logo_cantaclaro.png", "logo_cosecha_andina.png"):
        assert logo in html
    assert f"Orden de venta &nbsp; N° &nbsp; {o.numero}" in html and "Crédito 30 días" in html
    assert "C20000000001" in html and "CUENTAS" in html and "SERVICIOS DE ASISTENCIA" in html
    assert "/ 100 SOLES" in html and "EXO" in html


def test_igv_solo_en_lineas_gravadas(s, new_order):
    from app.services.documents import ov_document
    o = new_order([("PT-905", 10), ("PT-906", 2)], precio=100)
    o.lines[0].tax_code = "EXO"
    o.lines[1].tax_code = "IGV"
    d = ov_document(o)
    assert d["importe"] == 1200 and d["igv"] == 36 and d["total"] == 1236


def test_guia_y_preguia_con_membrete(app, s, U, new_order):
    from app.models import Route
    o = new_order([("PT-905", 100)])
    s.commit()
    r = s.query(Route).first()
    assert r is not None
    c = app.test_client()
    login(c, "coord.distribucion")
    for tipo in ("preguia", "folio"):
        html = c.get(f"/distribucion/ruta/{r.id}/folio?tipo={tipo}").get_data(as_text=True)
        assert "logo_cosecha_andina.png" in html and "logo_cantaclaro.png" in html and "logo_corporacion_productiva.png" in html
    assert "PRE-GUÍA DE REMISIÓN" in c.get(f"/distribucion/ruta/{r.id}/folio?tipo=preguia").get_data(as_text=True)


def _lot(s, code):
    return s.query(StockLot).filter(StockLot.product_code == code, StockLot.cantidad > 0).first()


def test_tipos_de_certificado_pt_mp_ca(s, U):
    from app.services import quality as q
    pt = q.generate_certificate(_lot(s, "PT-905"), U("superv.calidad"))
    assert pt.serie == "PT" and pt.numero.startswith(f"CP{date.today().year}-PT") and pt.datos["tipo"] == "PT"
    assert [o["analisis"] for o in pt.datos["organoleptico"]] == ["COLOR", "OLOR Y SABOR", "ASPECTO"]
    assert "Decreto Supremo Nº004-2011-AG" in pt.datos["inocuidad"] and "Normas Técnicas" in pt.datos["conclusiones"]
    mp = q.generate_certificate(_lot(s, "MP-901"), U("superv.calidad"))
    assert mp.serie == "MP" and mp.datos["inocuidad"] == "" and mp.datos["humedad"]["especificacion"] == ""
    # CA: formato Cosecha Andina (características organolépticas, humedad máx. 21 %, Codex), elegido por Calidad
    ca = q.generate_certificate(_lot(s, "PT-906"), U("superv.calidad"), tipo="CA")
    assert ca.serie == "CA" and [o["analisis"] for o in ca.datos["organoleptico"]] == ["Apariencia", "Color", "Olor", "Sabor"]
    assert ca.datos["humedad"]["especificacion"] == "MÁX. 21 %" and "Codex Alimentarius" in ca.datos["conclusiones"]
    assert "pendiente" in ca.datos["registro_sanitario"]
    with pytest.raises(BusinessError):  # registro sanitario pendiente: no se aprueba
        q.review_certificate(ca, U("jefe.calidad"), {}, aprobar=True)


def test_tipo_por_marca_y_regenerar_borrador(s, U):
    from app.services import quality as q
    lot = _lot(s, "PT-905")
    lot.product.marca = "COSECHA ANDINA"
    assert q.certificate_type_for(lot) == "CA"
    c = q.generate_certificate(lot, U("superv.calidad"))
    assert c.serie == "CA"
    n = q.regenerate_certificate(c, U("superv.calidad"), "PT")
    assert c.estado == "ANULADO" and n.serie == "PT" and n.datos["tipo"] == "PT"
    with pytest.raises(BusinessError):
        q.regenerate_certificate(n, U("coord.ventas"), "MP")


def test_certificado_con_membrete_y_firma_solo_aprobado(app, s, U):
    from app.services import quality as q
    c0 = q.generate_certificate(_lot(s, "PT-905"), U("superv.calidad"))
    s.commit()
    c = app.test_client()
    login(c, "jefe.calidad")
    html = c.get(f"/calidad/certificados/{c0.id}").get_data(as_text=True)
    assert "logo_cosecha_andina.png" in html and "marca_agua_cosecha_andina.png" in html
    assert "Av. Aviación Nº1560" in html and "Jefe de Aseguramiento de Calidad" in html
    assert "La firma se imprime solo cuando el certificado está aprobado" in html
    # V14: la firma la carga la Jefatura de Calidad (o Sistemas); otro perfil de Calidad no, y no se publica sin sesión
    c3 = app.test_client()
    login(c3, "asist.calidad")
    tok = csrf(c3, "/calidad/certificados")
    r = c3.post("/calidad/firma", data={"_csrf": tok, "archivo": (io.BytesIO(b"\x89PNG"), "f.png")},
                content_type="multipart/form-data")
    assert r.status_code == 403


# ------------------------------ R1: vida útil ------------------------------
def test_vida_util_restante_en_meses_con_excepcion_harinas(s, U, new_order):
    from app.services.customer_conditions import add_months, min_shelf_months, shelf_rule
    assert shelf_rule("12 MESES / 6 MESES HARINAS") == (12, {"HARINA": 6})
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert param("aplicar_vida_util_cliente") is True
    cli = s.query(Customer).filter_by(ruc="20000000004").one()  # CATERING demo: 6 meses
    assert min_shelf_months(cli) == 6
    # PT-901: L901B vence en 12 días → no cumple 6 meses restantes; se reserva L901A
    o = new_order([("PT-901", 80)], ruc="20000000004")
    assert [r.lot.lote for r in o.lines[0].reservations if r.estado == "ACTIVA"] == ["L901A"]
    # cliente institucional demo: "6 MESES / 3 MESES HARINAS"
    inst = s.query(Customer).filter_by(ruc="20000000005").one()
    harina = _lot(s, "PT-905").product
    harina.descripcion = "HARINA DE HABAS * 500 G (demo)"
    assert min_shelf_months(inst, harina) == 3 and min_shelf_months(inst) == 6


# ------------------------------ R2: RUC ------------------------------------
def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    for r in rows:
        ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def _upload(s, U, tipo, rows, user, tmp_path, name="archivo.xlsx"):
    from app.services import uploads
    p = tmp_path / name
    p.write_bytes(_xlsx(rows).getvalue())
    b = uploads.create_batch(U(user), tipo, str(p), name)
    return b


def test_condiciones_con_ruc_se_vinculan_por_ruc(s, U, tmp_path):
    from app.services import uploads
    from app.services.customer_conditions import for_customer
    b = _upload(s, U, "CLIENTES_CONDICIONES", [
        ["EJECUTIVO", "CANAL", "CLIENTE", "RUC", "SOLICITUD", "LOTE", "VIDA UTIL", "PENALIDAD"],
        ["V", "MAYORISTA", "NOMBRE DISTINTO EN LA LISTA", "20000000001", "PT", "2 LOTES POR SKU", "4 MESES", "PESO"],
        ["V", "MAYORISTA", "CLIENTE X", "123", "PT", "1 LOTE POR SKU", "4 MESES", ""]], "jefe.ventas", tmp_path)
    assert any("RUC inválido" in e for r in b.rows for e in r.errores)
    b.rows[1].excluida = True
    uploads.validate_batch(b)
    uploads.confirm(b, U("jefe.ventas"), {})
    c = for_customer(s.query(Customer).filter_by(ruc="20000000001").one())
    assert c is not None and c.ruc == "20000000001" and c.max_lotes_por_sku == 2


# ------------------------------ R4: costos ---------------------------------
def test_venta_bajo_costo_detiene_y_alerta_sin_mostrar_costo(s, U, new_order):
    from app.services.costs import replace_costs
    from app.services.prices import approve_price
    replace_costs([{"product_code": "PT-905", "costo": 50.0, "unidad": "UND"}], U("jefe.ventas"), "prueba")
    o = new_order([("PT-905", 10)], precio=40)
    assert o.retenida_precio and any("DEBAJO DEL COSTO" in x for x in o.precio_observado)
    assert not any("50.0" in x for x in o.precio_observado)  # el texto visible en la OV no expone el costo
    a = alerts_of(s, "OV_PRECIO_BAJO_COSTO", o.id)
    assert a and "costo S/ 50.00" in a[0].mensaje
    approve_price(o, U("coord.ventas"), "Cliente estratégico")
    assert not o.retenida_precio and a[0].estado == "COMPLETADA"


def test_costo_empresa_de_la_lista_de_precios_se_conserva(s):
    assert s.query(ProductCost).filter_by(vigente=True).count() > 0


def test_carga_excel_de_costos_y_permiso(s, U, tmp_path):
    from app.services import uploads
    rows = [["SKU", "DESCRIPCIÓN", "COSTO", "UNIDAD"], ["PT-905", "x", 3.5, "UND"], ["MP-901", "y", 4.1, "KG"]]
    with pytest.raises(BusinessError):
        _upload(s, U, "COSTOS", rows, "coord.ventas", tmp_path)
    b = _upload(s, U, "COSTOS", rows, "jefe.ventas", tmp_path, "costos.xlsx")
    uploads.confirm(b, U("jefe.ventas"), {})
    c = s.query(ProductCost).filter_by(product_code="MP-901", vigente=True, unidad="KG").one()
    assert c.costo == 4.1


# ------------------------------ R5: mercado --------------------------------
def test_analisis_automatico_costo_vs_mercado_y_tendencia(s, U):
    from app.services.costs import add_market_prices, check_market_alerts, market_analysis, replace_costs
    p = _lot(s, "MP-901").product
    p.producto_base = "FRIJOL CANARIO"
    replace_costs([{"product_code": "MP-901", "costo": 6.5, "unidad": "KG"}], U("jefe.ventas"), "prueba")
    hoy = date.today()
    add_market_prices([{"producto": "FRIJOL CANARIO", "precio_kg": v, "fecha": hoy - timedelta(days=d), "mercado": "Demo",
                        "fuente": "dato ficticio"} for d, v in ((60, 5.6), (30, 5.8), (0, 6.2))], U("jefe.ventas"), "prueba")
    r = [x for x in market_analysis() if x["code"] == "MP-901"][0]
    assert r["mercado"] == "FRIJOL CANARIO" and r["precio_mercado"] == 6.2 and r["brecha_pct"] < 0
    assert r["tendencia_pct"] == pytest.approx(8.8, abs=0.1)
    assert any("Mercado al alza" in t for t in r["recomendaciones"]) and any("sobre" in t for t in r["recomendaciones"])
    assert check_market_alerts() >= 1 and alerts_of(s, "COSTO_SOBRE_MERCADO", "MP-901")


def test_pantalla_costos_restringida(app):
    c = app.test_client()
    login(c, "jefe.ventas")
    assert c.get("/ov/costos").status_code == 200
    c2 = app.test_client()
    login(c2, "vendedor1")
    assert c2.get("/ov/costos").status_code == 403


def test_modificar_ov_solo_comercial(s, U):
    from app.services.core import user_perms
    for u in ("vendedor1", "coord.ventas", "jefe.ventas"):
        assert "ov.modificar" in user_perms(U(u))
    for u in ("gerente.general", "sistemas", "asist.ventas"):
        assert "ov.modificar" not in user_perms(U(u))
