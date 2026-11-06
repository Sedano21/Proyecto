"""V24 (06-nov-2026): alta de personal por área, compras nacionales (OV/cliente/motivo, consolidado, cotizaciones e
histórico), seguimiento de importaciones, costos y presupuestos, tipo de cambio SUNAT, tablero de la empresa e informe
de reposición. Datos ficticios."""
from datetime import date, timedelta

import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _cliente(app, user):
    c = app.test_client()
    login(c, user)
    return c


# ------------------------------------------------------------------ personal por área
def test_alta_de_personal_segun_el_area(s, U):
    from app.services import attendance as at
    w = at.save_worker(U("jefe.produccion"), {"nombre": "Op Demo", "linea": "R2", "puesto": "Maquinista"})
    assert w.area == "Producción" and w.linea == "R2" and w.puesto == "Maquinista"
    jv = U("jefe.ventas")
    with pytest.raises(BusinessError, match="canal"):
        at.save_worker(jv, {"nombre": "Vendedor Demo", "puesto": "Ejecutivo comercial"})
    v = at.save_worker(jv, {"nombre": "Vendedor Demo", "puesto": "Ejecutivo comercial", "canal": "MAYORISTA", "linea": "R1"})
    assert v.area == "Comercial" and v.canal == "MAYORISTA" and v.linea == ""  # al vendedor no se le asigna línea
    lg = at.save_worker(U("jefe.logistica"), {"nombre": "Aux Demo", "puesto": "Auxiliar de despacho", "linea": "R1"})
    assert lg.linea == "" and lg.puesto == "Auxiliar de despacho"
    assert at.positions(U("jefe.logistica"))[:2] == ["Auxiliar de almacén", "Auxiliar de despacho"]
    m = at.save_worker(U("jefe.mantenimiento"), {"nombre": "Limpieza Demo", "puesto": "Personal de limpieza", "linea": "R1"})
    assert m.area == "Mantenimiento" and m.linea == ""


def test_reportar_averia_muestra_las_dos_opciones(app):
    h = _cliente(app, "aux.almacen").get("/").get_data(as_text=True)
    assert "dest-card" in h and "Mantenimiento" in h and "laptop o PC" in h


# ------------------------------------------------------------------ compras nacionales
def _ov(new_order, ruc):
    return new_order([("PT-901", 5)], ruc=ruc)


def test_consolidado_ov_del_mismo_cliente_no_se_suma(s, U, new_order, cust):
    from app.services import compras_v24 as cv
    o = _ov(new_order, "20000000001")
    c = cust("20000000001")
    alm = U("coord.almacen")
    nec = date.today() + timedelta(days=10)
    cv.create(alm, "MP-903", 1000, nec, o.numero)
    cv.create(alm, "MP-903", 2000, nec, "", c.id)
    cv.create(alm, "MP-903", 500, nec, "", None, "STOCK_SEGURIDAD")
    s.commit()
    p = cv.consolidado("MP-903")[0]
    assert p["total"] == 2500 and p["pedido_bruto"] == 3500  # la OV es de ese cliente: se toman 2 t, no 3 t
    assert p["clientes"][0]["nota"] and p["motivos"][0]["cantidad"] == 500


def test_consolidado_ov_de_otro_cliente_se_suma(s, U, new_order, cust):
    from app.services import compras_v24 as cv
    o = _ov(new_order, "20000000002")
    alm = U("coord.almacen")
    nec = date.today() + timedelta(days=11)
    cv.create(alm, "MP-902", 1000, nec, o.numero)
    cv.create(alm, "MP-902", 2000, nec, "", cust("20000000001").id)
    s.commit()
    p = cv.consolidado("MP-902")[0]
    assert p["total"] == 3000 and len(p["clientes"]) == 2


def test_solicitud_valida_ov_cliente_y_motivo(s, U, new_order, cust):
    from app.services import compras_v24 as cv
    o = _ov(new_order, "20000000002")
    alm = U("coord.almacen")
    with pytest.raises(BusinessError, match="es del cliente"):
        cv.create(alm, "MP-901", 10, None, o.numero, cust("20000000001").id)
    with pytest.raises(BusinessError, match="motivo"):
        cv.create(alm, "MP-901", 10)
    with pytest.raises(BusinessError, match="Especifique"):
        cv.create(alm, "MP-901", 10, None, "", None, "OTRO", "")


def test_cotizaciones_historico_y_alerta(s, U):
    from app.models import SupplierQuote
    from app.services import compras_v24 as cv
    hoy = date.today()
    for k in range(1, 4):
        s.add(SupplierQuote(product_code="MP-901", proveedor="Prov Demo", precio=5.0, moneda="PEN", um="KG",
                            fecha=hoy - timedelta(days=10 * k)))
    s.commit()
    with pytest.raises(BusinessError):
        cv.add_quote(U("vendedor1"), "MP-901", {"proveedor": "X", "precio": 6})
    q, c = cv.add_quote(U("gerente.adjunto"), "MP-901", {"origen": "Mercado X", "proveedor": "María (demo)",
                                                         "fecha_entrega": (hoy + timedelta(days=20)).isoformat(),
                                                         "calidad": "Primera", "precio": 6.5, "um": "KG"})
    s.commit()
    assert c["alerta"] and "por encima" in c["alerta"] and alerts_of(s, "COMPRA_PRECIO_VARIACION", q.id)
    cv.choose(U("compras"), q)
    assert q.elegida


def test_pantalla_compras_nacionales(app):
    c = _cliente(app, "compras")
    assert "Nueva solicitud de compra" in c.get("/gestion/compras-nacionales").get_data(as_text=True)
    assert _cliente(app, "vendedor1").get("/gestion/compras-nacionales").status_code == 403


# ------------------------------------------------------------------ importaciones
def test_importacion_alertas_y_penalidades(s, U):
    from app.services import importaciones_v24 as imp
    hoy = date.today()
    u = U("importaciones")
    with pytest.raises(BusinessError):
        imp.save(U("vendedor1"), {"contrato": "X", "proveedor": "Y", "item": "Z"})
    f = imp.save(u, {"codigo_sap": "MP-903", "contrato": "T-1", "proveedor": "Exportadora Demo", "item": "Frijol",
                     "contenedores": 2, "fecha_llegada": (hoy - timedelta(days=15)).strftime("%d/%m/%Y"), "dias_libres": 13,
                     "retiro_fecha": "", "sobreestadia_dia": 100, "penalidad_dia": 50, "precio": 1800,
                     "fecha_entrega_contrato": (hoy - timedelta(days=20)).isoformat()})
    s.commit()
    e = imp.estado(f)
    assert e["fmax"] == hoy - timedelta(days=2) and e["semaforo"] == "err"
    assert e["riesgo_sobreestadia"] == 2 * 2 * 100 and e["penalidad_a_favor"] == 5 * 50
    assert imp.check_alerts() >= 2
    assert alerts_of(s, "IMPORT_SOBREESTADIA", f.id) and alerts_of(s, "IMPORT_PENALIDAD", f.id)
    imp.add_expense(u, f, "Devolución tarde de contenedor", 300, "USD", "demo")
    imp.add_incident(u, f, "Retraso", "Naviera demo")
    s.commit()
    assert imp.total_gastos(f, 3.7) == 300 and alerts_of(s, "IMPORT_INCIDENCIA", f.id)
    a = alerts_of(s, "IMPORT_INCIDENCIA", f.id)[0]
    assert "GERENTE_GENERAL_ADJUNTO" in a.roles and "ASIST_IMPORTACIONES" in a.roles


def test_importacion_desde_excel_con_columnas_del_cuadro(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import importaciones_v24 as imp
    wb = Workbook()
    ws = wb.active
    ws.append(imp.COLUMNAS_EXCEL)
    ws.append(["POR CONFIRMAR", "DEMO-X1", "Proveedor Demo", "GARBANZO", "MÉXICO", 2, "29/11/2026", 13, "12/12/2026",
               "PENDIENTE", "PENDIENTE DE LIBERACIÓN DE BL", "04-dic", "PENDIENTE"])
    p = tmp_path / "imp.xlsx"
    wb.save(p)
    assert imp.import_excel(U("asist.importaciones"), str(p)) == (1, 0)
    s.commit()
    f = imp.board()["filas"][0]["f"]
    assert f.retiro_fecha == date(2026, 12, 4) and imp.fecha_max_retiro(f) == date(2026, 12, 12)
    assert imp.import_excel(U("asist.importaciones"), str(p)) == (0, 1)


def test_pantalla_importaciones(app):
    c = _cliente(app, "asist.importaciones")
    assert "Seguimiento de importaciones" in c.get("/gestion/importaciones").get_data(as_text=True)
    assert c.get("/gestion/importaciones?salida=xlsx").status_code == 200


# ------------------------------------------------------------------ tipo de cambio y costos
def test_tipo_cambio_sunat_y_manual(s, U):
    from app.services import tipo_cambio as tc
    r = tc.actualizar(fetch=lambda url: "06/11/2026|3.751|3.758|", hoy=date(2026, 11, 6))
    s.commit()
    assert r.venta == 3.758 and tc.rate(date(2026, 11, 7)) == 3.758
    assert tc.actualizar(fetch=lambda url: (_ for _ in ()).throw(OSError("sin red")), hoy=date(2026, 11, 8)) is None
    assert alerts_of(s, "TIPO_CAMBIO_PENDIENTE")
    with pytest.raises(BusinessError):
        tc.manual(U("vendedor1"), date(2026, 11, 8), 3.7, 3.71)
    tc.manual(U("costos.presupuestos"), date(2026, 11, 8), 3.70, 3.71)
    s.commit()
    assert tc.rate(date(2026, 11, 8)) == 3.71


def test_costo_de_reposicion_vs_costo_registrado(s, U):
    from app.models import SupplierQuote
    from app.services import costos_v24 as cos
    from app.services import tipo_cambio as tc
    tc.guardar(date.today(), 3.70, 3.71)
    cos.guardar_costo(U("costos.presupuestos"), "MP-901", 4.0, "KG")
    s.add(SupplierQuote(product_code="MP-901", proveedor="Prov Demo", precio=5.0, moneda="PEN", um="KG", elegida=True,
                        fecha=date.today()))
    s.commit()
    d = cos.analisis()
    f = next(x for x in d["filas"] if x["code"] == "MP-901")
    assert f["costo_kg"] == 4.0 and f["reposicion_kg"] == 5.0 and f["var_pct"] == 25.0 and f["nivel"] == "err"
    assert cos.check_alerts() >= 1 and alerts_of(s, "COSTO_REPOSICION_ALTO")


def test_flujo_v24_demo_y_pantallas(s, app, tmp_path):
    from app.demo_flujo import seed_flow, seed_v24
    seed_flow(str(tmp_path))
    r = seed_v24(str(tmp_path))
    s.commit()
    assert r["importaciones"] == 6 and r["compras_nacionales"] >= 4
    assert seed_v24(str(tmp_path)) is None
    for user, urls in (("gerente.adjunto", ["/gestion/compras-nacionales", "/gestion/importaciones", "/gestion/empresa",
                                            "/gestion/costos", "/gestion/reposicion"]),
                       ("costos.presupuestos", ["/gestion/costos", "/gestion/costos?formato=pdf", "/gestion/empresa"]),
                       ("jefe.operaciones", ["/gestion/empresa", "/gestion/reposicion?formato=xlsx"])):
        c = _cliente(app, user)
        for u in urls:
            assert c.get(u).status_code == 200, (user, u)
    h = _cliente(app, "gerente.general").get("/gestion/empresa").get_data(as_text=True)
    assert "A qué prestarle atención" in h and "Importaciones" in h
    assert _cliente(app, "aux.almacen").get("/gestion/empresa").status_code == 403


# ------------------------------------------------------------------ V24b: ruta manual, costos Excel, centros de costo
def test_ruta_manual_tercero_exige_costo_y_hora_flexible(s, U, new_order):
    from app.services import rutas_manual as rm
    from app.models import Vehicle
    o = new_order([("PT-901", 5)], dias=1)
    s.commit()
    ter = s.query(Vehicle).filter_by(propio=False).first()
    datos = {"tipo_transportista": "TERCERO", "vehicle_id": ter.id, "hora_salida": "730"}
    with pytest.raises(BusinessError, match="costo"):
        rm.create_manual(U("coord.distribucion"), o.fecha_compromiso, datos, [o.id])
    datos["costo_tercero"] = "350"
    r = rm.create_manual(U("coord.distribucion"), o.fecha_compromiso, datos, [o.id])
    assert r.transportista["costo"] == 350 and r.hora_salida_prog == "07:30"
    assert rm._hora("7.5") == "07:05" or rm._hora("07:45") == "07:45"


def test_ruta_manual_trabajador_de_la_lista(s, U, new_order):
    from app.services import rutas_manual as rm
    o = new_order([("PT-901", 5)], dias=1)
    s.commit()
    v = U("vendedor1")
    r = rm.create_manual(U("coord.distribucion"), o.fecha_compromiso,
                         {"tipo_transportista": "TRABAJADOR", "t_user_id": str(v.id), "t_vehiculo": "camioneta",
                          "t_motivo": "queda en su ruta"}, [o.id])
    assert r.transportista["nombre"] == v.nombre and r.transportista["area"]


def test_costos_desde_excel_formato_empresa(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import costos_v24 as cos
    from app.services.costs import current_cost
    wb = Workbook()
    ws = wb.active
    ws.append(["1. COSTO EMPRESA", None, None, None, "2. COSTO EMPRESA"])
    ws.append(["SKU", "DESCRIPCIÓN", "COSTO EMPRESA", None, "SKU", "DESCRIPCIÓN", "COSTO EMPRESA"])
    ws.append(["MP-901", "ARVEJA", 3.2, None, "PT-901", "ARVEJA 500 G", 1.9])
    ws.append(["XX-999", "NO EXISTE", 1.0, None, None, None, None])
    p = tmp_path / "c.xlsx"
    wb.save(p)
    r = cos.import_excel(U("costos.presupuestos"), str(p))
    s.commit()
    assert r["leidos"] == 2 and r["omitidos"] == ["XX-999"]
    assert current_cost("MP-901")["KG"].costo == 3.2 and current_cost("PT-901")["UND"].costo == 1.9


def test_centros_de_costo_y_rendiciones(s, U, tmp_path, app):
    from openpyxl import Workbook
    from app.services import centros_costo as cc
    wb = Workbook()
    ws = wb.active
    ws.append([None, "CENTRO DE COSTOS (demo)"])
    ws.append([None, "GRUPO", "AREA", None, "CENTRO DE COSTO", None, "SUB-CENTRO DE COSTO"])
    ws.append([None, None, "NUMERO", "DESCRIPCION", "NUMERO", "DESCRIPCION", "NUMERO", "DESCRIPCION"])
    ws.append([None, "ADMIN DEMO", 11, "ADMINISTRACION DEMO", 1101, "GERENCIAS DEMO", 110101, "GERENCIA DEMO"])
    ws.append([None, None, None, None, None, None, 110102, "ADJUNTA DEMO"])
    ws.append([None, None, None, None, 1102, "LIMPIEZA DEMO", None, None])
    p = tmp_path / "cc.xlsx"
    wb.save(p)
    assert cc.import_excel(U("compras"), str(p)) == (3, 0)
    s.commit()
    c = {x.codigo: x for x in cc.lista()}
    assert c["110102"].centro == "GERENCIAS DEMO" and c["1102"].descripcion == "LIMPIEZA DEMO"
    e = cc.registrar_gasto(U("compras"), {"tipo": "MOVILIDAD", "concepto": "Taxi demo", "monto": "25.5"})
    assert e.centro_costo == ""  # el centro de costo no es obligatorio
    with pytest.raises(BusinessError):
        cc.registrar_gasto(U("compras"), {"tipo": "RENDICION", "concepto": "x", "monto": 10, "centro_costo": "999"})
    cc.registrar_gasto(U("compras"), {"tipo": "RENDICION", "concepto": "Sacos", "monto": 100, "centro_costo": "110101"})
    s.commit()
    assert any(k == "110101" for k, _e, _v in cc.resumen_por_centro())
    assert "Rendiciones" in _cliente(app, "compras").get("/gestion/rendiciones").get_data(as_text=True)


def test_quince_dias_de_operacion(s, app, tmp_path):
    from app.demo_flujo import seed_flow, seed_v24
    from app.demo_quincena import seed_quincena
    from app.models import VehicleChecklist
    from app.services.vehicle_checklist import items
    seed_flow(str(tmp_path))
    seed_v24(str(tmp_path))
    r = seed_quincena(str(tmp_path))
    s.commit()
    assert r["rutas"] > 10 and r["paradas"] >= 80 and r["checklists"] == 2 * r["rutas"] and r["picking"] == r["paradas"]
    c = s.query(VehicleChecklist).first()
    assert set(c.items) == {code for code, *_ in items()} and c.validado_por  # checklist completo y validado
    assert seed_quincena(str(tmp_path)) is None
    cl = _cliente(app, "coord.distribucion")
    assert cl.get(f"/distribucion/ruta/{c.route_id}/checklist").status_code == 200
