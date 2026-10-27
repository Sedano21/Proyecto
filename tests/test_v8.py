"""Ronda V8 (27-oct-2026): flota desde GEOSATELITAL, carga de OV desde las exportaciones de SAP y respuestas del
cuestionario operativo. Datos ficticios."""
from datetime import date, datetime, timedelta

import openpyxl
import pytest

from app.services.core import BusinessError

from .conftest import alerts_of
from .test_web import login


def _xlsx(path, filas):
    wb = openpyxl.Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    wb.save(path)
    return str(path)


def test_carga_de_unidades_formato_geosatelital(s, U, tmp_path):
    from app.models import Vehicle
    from app.services.fleet import import_vehicles
    p = _xlsx(tmp_path / "u.xlsx", [["Nombre", "Conductor", "Flota", "Placa", "Marca", "Modelo", "Año", "Tipo", "Odometro"],
                                    ["ZZZ901", None, None, "ZZZ901", "Sin marca", "Sin modelo", "N/A", "Auto", 0],
                                    ["ZZZ902", None, None, "ZZZ902", "MARCA DEMO", "MD35", 2025, "Camion", 47620.0],
                                    [None, None, None, "X", None, None, None, None, None]])
    r = import_vehicles(U("coord.distribucion"), p)
    assert r["nuevas"] == 2 and len(r["errores"]) == 1
    v1 = s.query(Vehicle).filter_by(placa="ZZZ901").one()
    v2 = s.query(Vehicle).filter_by(placa="ZZZ902").one()
    assert v1.marca == "" and v1.anio is None and v1.tipo_unidad == "Auto" and not v1.disponible
    assert (v2.marca, v2.modelo, v2.anio, v2.km_actual) == ("MARCA DEMO", "MD35", 2025, 47620.0)
    r = import_vehicles(U("coord.distribucion"), p)
    assert r["nuevas"] == 0 and r["actualizadas"] == 2
    with pytest.raises(BusinessError):
        import_vehicles(U("vendedor1"), p)


def test_enlace_geosatelital_con_vigencia(s, U):
    from app.models import Vehicle
    from app.services import geosat
    v = s.query(Vehicle).first()
    with pytest.raises(BusinessError, match="15 minutos"):
        geosat.set_vehicle_link(v, U("coord.distribucion"), "https://geo.example/x", 30)
    geosat.set_vehicle_link(v, U("coord.distribucion"), "https://geo.example/x", 0.25)
    assert geosat.link_status(v)[0]
    assert not geosat.link_status(v, datetime.now() + timedelta(minutes=20))[0]


CAB = ["#", "# SAP", "Fecha", "Cliente", "Empleado del departamento de ventas", "Comentarios", "Fecha de vencimiento",
       "Comentarios", "Firma del usuario", "Peso Total", "Persona de contacto", "Status de documento", "Destino", "Serie",
       "Serie de folios", "Cancelado", "vendedor", "Entrada de anexo", "Código de cliente/proveedor"]
DET = ["#", "Artículo", "Descripción Artículo", "Cantidad", "En stock", "Precio por unidad (moneda)", "Precio por unidad",
       "Precio tras el descuento", "Impuesto", "Almacén", "Cantidad pendiente", "Código de unidad de medida", "Peso"]


def _cab(numero, estado="Abiertos", ruc="20999999901", venc=None):
    venc = venc or date.today() + timedelta(days=4)
    return [1, numero, date.today().strftime("%d/%m/%Y"), "CLIENTE FICTICIO SAC", "VENDEDOR DEMO", "Entrega en almacén",
            venc.strftime("%d/%m/%Y"), f"Pedidos de cliente - C{ruc}", "Usuario", 120.0, 0, estado,
            "AV. FICTICIA 123 LIMA PERU", 13, None, "No", "Sí", None, "CLIENTE FICTICIO SAC"]


def test_ov_desde_exportaciones_sap(s, U, tmp_path):
    from app.models import Customer, SalesOrder, SapOrderHeader
    from app.services import sap_excel as sx
    u = U("coord.ventas")
    pc = _xlsx(tmp_path / "lista.xlsx", [CAB, _cab(7000001), _cab(7000002), _cab(7000003, "Cerrado")])
    assert sx.detect(pc) == "CABECERAS"
    r = sx.import_headers(u, pc)
    assert (r["nuevas"], r["pendientes_detalle"], r["cerradas_omitidas"]) == (2, 2, 1)
    r = sx.import_headers(u, pc)  # segunda carga del día: no duplica
    assert r["nuevas"] == 0 and r["sin_cambio"] == 2
    h = s.query(SapOrderHeader).filter_by(numero="7000001").one()
    assert (h.ruc, h.card_code) == ("20999999901", "C20999999901")
    pd = _xlsx(tmp_path / "7000001.xlsx", [DET, [1, "PT-905", "QUINUA DEMO", 24, 97, "SOL", 10.0, 9.5, "EXO", "ALM-001", 20, "NIU", 120],
                                           [2, "PT-902", "PRODUCTO DEMO", 10, 5, "SOL", 5.0, 5.0, "EXO", "ALM-001", 0, "NIU", 50],
                                           [3, None, None, None, None, None, None, None, None, None, None, None, None]])
    assert sx.detect(pd) == "DETALLE"
    o = sx.import_detail(u, pd, nombre_archivo="7000001.xlsx")
    assert o.origen == "CARGA_SAP" and len(o.lines) == 1 and o.lines[0].cantidad == 20 and o.lines[0].precio_unitario == 9.5
    c = s.query(Customer).filter_by(ruc="20999999901").one()
    assert c.codigo_sap == "C20999999901" and o.customer_id == c.id
    with pytest.raises(BusinessError, match="ya está"):
        sx.import_detail(u, pd, "7000001")
    assert [x.numero for x in sx.pending_headers()] == ["7000002"]
    # SAP la cierra: la OV abierta del módulo (sin preparar) se cierra sin descontar stock
    sx.import_headers(u, _xlsx(tmp_path / "lista2.xlsx", [CAB, _cab(7000001, "Cerrado")]))
    assert s.query(SalesOrder).filter_by(numero="7000001").one().estado == "CERRADA"
    with pytest.raises(BusinessError):
        sx.import_headers(U("jefe.calidad"), pc)


def test_pantalla_ov_desde_sap(app):
    c = app.test_client()
    login(c, "coord.ventas")
    assert c.get("/ov/carga-sap").status_code == 200


def test_movimiento_reasignado_con_rastro_y_aviso_programado(s, U):
    from app.services import supply
    ej = supply.move_executors()
    m = supply.request_move(U("jefe.produccion"), "Zona de recepción", "Rack", programado_para=datetime.now() + timedelta(hours=2),
                            asignado_id=ej[0].id, aviso_min=60)
    assert m.aviso_min == 60 and "Zona de despacho" in supply.move_points("")
    with pytest.raises(BusinessError, match="quien solicitó"):
        supply.reassign_move(U("coord.almacen"), m, ej[-1].id)
    supply.reassign_move(U("jefe.produccion"), m, None, "Se liberó para el primero disponible")
    assert m.asignado_a is None and m.historial[-1]["a"] == "primero disponible"
    assert supply.check_scheduled_moves(datetime.now()) == 0
    assert supply.check_scheduled_moves(datetime.now() + timedelta(hours=1, minutes=1)) == 1
    assert supply.check_scheduled_moves(datetime.now() + timedelta(hours=1, minutes=2)) == 0  # un solo aviso


def test_fumigacion_repetida_alerta_a_calidad(s, U):
    from app.models import StockLot
    from app.services.stock import change_lot_state
    lot = s.query(StockLot).filter(StockLot.cantidad > 0, StockLot.estado == "DISPONIBLE").first()
    change_lot_state(lot, "EN_FUMIGACION", U("jefe.calidad"), "1.ª")
    assert not alerts_of(s, "FUMIGACION_REPETIDA")
    change_lot_state(lot, "PENDIENTE_REVISION", U("jefe.calidad"), "fin")
    change_lot_state(lot, "EN_FUMIGACION", U("jefe.calidad"), "2.ª")
    s.flush()
    a = alerts_of(s, "FUMIGACION_REPETIDA")
    assert a and "JEFE_CALIDAD" in a[0].roles


def test_auxiliar_por_paradas_peso_o_cliente(s, U, cust):
    from app.models import Route, RouteStop
    from app.services.distribution import needs_auxiliar
    r = Route(fecha=date.today(), estado="PROPUESTA", zona="Z", peso_total=2500)
    s.add(r)
    s.flush()
    assert any("kg" in m for m in needs_auxiliar(r))
    r.peso_total = 100
    from app.services import orders as osvc
    o = osvc.create_order(U("coord.ventas"), "AUX-1", cust().id, date.today() + timedelta(days=3),
                          [{"product_code": "PT-905", "cantidad": 1, "precio_unitario": 10}], oc_archivo="o", evaluar=False)
    o.customer.requiere_auxiliar = True
    r.stops.append(RouteStop(order=o, orden=1, peso_kg=1))
    s.flush()
    assert any("cliente" in m for m in needs_auxiliar(r))


def test_receptor_sin_dni(s, U):
    from app.services import distribution as dist
    from app.models import Route, RouteStop
    st = RouteStop(estado="LLEGADA", route=Route(fecha=date.today(), estado="EN_RUTA", zona="Z"))
    with pytest.raises(BusinessError):
        dist.register_delivery(st, U("conductor1"), "f.jpg", "g.jpg", receptor_nombre="Ana Demo", receptor_dni="12",
                               firma_path="x.png", receptor_tipo="DNI")


def test_sap_url_horario_y_escritura_solo_pruebas(s, U, monkeypatch):
    from app.services import sap_sl
    assert sap_sl._base_url("https://10.0.0.1:50000/") == "https://10.0.0.1:50000/b1s/v1"
    assert sap_sl._base_url("https://10.0.0.1:50000/b1s/v2") == "https://10.0.0.1:50000/b1s/v2"
    for k, v in {"SAP_SL_URL": "https://sap.invalid:50000", "SAP_SL_COMPANY": "BASE_PRODUCCION", "SAP_SL_USER": "u",
                 "SAP_SL_PASSWORD": "p", "SAP_SYNC_MIN": "1", "SAP_SYNC_USER": "coord.ventas"}.items():
        monkeypatch.setenv(k, v)
    assert sap_sl.scheduled_sync(datetime(2026, 10, 27, 22, 30)) == 0  # fuera del horario 06:00-21:00
    from app.models import Quote
    q = Quote(numero="COT-X", customer_id=1, fecha=date.today(), lineas=[], total=0)
    s.add(q)
    s.flush()
    with pytest.raises(BusinessError, match="base de pruebas"):
        sap_sl.push_quote(q, U("coord.ventas"))


def test_cambios_de_parametros_en_bases_existentes(s):
    from app.models import Param
    from app.seed import sync_catalogs
    from app.services.core import param
    p = s.get(Param, "vistos_buenos_salida")
    p.valor = {"v": ["SEGURIDAD", "AUX_DESPACHO", "LIDER_ALMACEN"]}
    from app.models import AuditLog
    s.query(AuditLog).filter_by(accion="PARAMETRO_CAMBIO_CATALOGO").delete()
    s.flush()
    sync_catalogs()
    assert param("vistos_buenos_salida") == ["SEGURIDAD", "CHOFER", "LIDER_ALMACEN"]
