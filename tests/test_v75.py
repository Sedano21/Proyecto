"""V75 (25-nov-2026): inicio de Gerencia General. Solo devoluciones generales, resumen de Calidad y de Compras e
Importaciones, OV con entrega en el mes, sugerencias de productividad por área y venta del año anterior junto al
OTIF. Solo datos ficticios."""
from datetime import date, timedelta

from .test_v42 import _historial_sap
from .test_v64 import _cliente


def test_inicio_gg_devoluciones_generales_calidad_y_compras(app, s, U, new_order):
    from app.models import ImportFollowup, PurchaseRequest, ReturnReceipt
    from app.services import tablero_gg
    o = new_order([("PT-901", 2)], dias=5)
    s.add_all([ReturnReceipt(order_id=o.id, tipo="TOTAL", plazo=date.today(), estado="PENDIENTE"),
               ReturnReceipt(order_id=o.id, tipo="PARCIAL", plazo=date.today(), estado="PENDIENTE"),
               PurchaseRequest(product_code="GR-901", cantidad=10, estado="ORDEN_GENERADA",
                               fecha_prevista=date.today() - timedelta(days=2))])
    s.commit()
    with app.test_request_context():
        areas = {a["area"]: {c["etiqueta"]: c for c in a["tarjetas"]} for a in tablero_gg.area_cards(perms=frozenset())}
    assert areas["Logística y Almacén"]["Devoluciones generales por recibir"]["valor"] == 1
    assert "Inspecciones del mes" in areas["Calidad"] and "Reempaques en curso" in areas["Calidad"]
    assert areas["Compras nacionales e importaciones"]["Compras atrasadas"]["valor"] >= 1
    assert "OV con entrega en el mes" in areas["Comercial"]
    html = _cliente(app, "gerente.general").get("/").get_data(as_text=True)
    for t in ("Devoluciones generales por recibir", "Inspecciones del mes", "Compras nacionales abiertas",
              "OV con entrega en el mes"):
        assert t in html
    dv = _cliente(app, "gerente.general").get("/operacion/devoluciones?tipo=TOTAL").get_data(as_text=True)
    assert "Generales (totales)" in dv


def test_ov_con_entrega_en_el_mes_filtra_la_lista(app, new_order):
    hoy = date.today()
    ini = hoy.replace(day=1)
    fin = (ini.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    html = _cliente(app, "gerente.general").get(f"/ov/?entrega_desde={ini}&entrega_hasta={fin}")
    assert html.status_code == 200


def test_sugerencias_de_productividad_por_area(app, s, U):
    from app.models import ProductionReport
    from app.services import sugerencias as sg
    hoy = date.today()
    for i, kg in enumerate([1000, 1000, 1000, 1000, 200, 200]):
        prod = "PT-901" if i < 2 else ("PT-902" if i < 4 else "PT-905")
        s.add(ProductionReport(linea="R1", tipo="ENVASADO", fecha=hoy - timedelta(days=i + 1), product_code=prod,
                               peso_entrada_kg=kg, estado="CERRADO", hora_inicio="08:00", hora_fin="10:00", operarios=2))
    s.commit()
    filas = sg.prod_productivity(hoy=hoy)
    assert any("PT-905" in x["titulo"] and x["area"] == "Producción" for x in filas)
    resumen = {r["area"]: r for r in sg.productivity_summary(hoy)}
    assert set(resumen) == {"Producción", "Almacén", "Distribución"} and resumen["Producción"]["valor"] != "—"
    html = _cliente(app, "gerente.general").get("/operacion/sugerencias").get_data(as_text=True)
    assert "Productividad por área" in html and "se procesa lento" in html
    assert "Producción" in _cliente(app, "gerente.general").get("/operacion/sugerencias?area=Producción").get_data(as_text=True)


def test_venta_del_anio_anterior_junto_al_otif(app, s, U):
    from app.models import SapBilling, SapOrderLine
    from app.services import seguimiento
    hoy = date.today()
    _historial_sap(s, hoy)
    for ln in s.query(SapOrderLine).all():
        ln.total = 100.0
    try:
        f_ant = (hoy - timedelta(days=1)).replace(year=hoy.year - 1)
    except ValueError:
        f_ant = (hoy - timedelta(days=2)).replace(year=hoy.year - 1)
    s.add(SapOrderLine(docnum="7001", clase="VENTA", serie="OV", fecha=f_ant, fecha_entrega=f_ant, cliente="Cliente Demo SAP",
                       estado="CERRADA", product_code="PT-901", descripcion="x", cantidad=5, entregado=5,
                       linea_cerrada=True, total=250.0))
    s.add(SapBilling(clave="FACTURA:777001", tipo="FACTURA", numero="F001-777", fecha=f_ant, cliente="Cliente Demo SAP",
                     total=118.0, igv=18.0))
    s.commit()
    v = seguimiento.venta_periodo_sap(f_ant, f_ant)
    assert v["ov"] == 250.0 and v["facturado"] == 100.0
    html = _cliente(app, "jefe.logistica").get(
        f"/seguimiento/servicio?desde={hoy - timedelta(days=5)}&hasta={hoy + timedelta(days=5)}").get_data(as_text=True)
    assert "Mismo periodo del año anterior" in html and "Venta" in html and "facturado neto" in html
