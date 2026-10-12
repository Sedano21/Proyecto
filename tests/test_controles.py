"""Controles funcionales: cargas con validación, estados de stock, conteos, alertas, reposición,
verificaciones periódicas y matriz de permisos (IF §6, §7, §14, §15, §19, §22)."""
import os
from datetime import date, timedelta

import openpyxl
import pytest

from app.models import Alert, AlertEvent, EmailOutbox, Permission, RolePermission, StockLot, UploadBatch
from app.services import alerts as al
from app.services import inventory as inv
from app.services import purchasing as buy
from app.services import quality as qual
from app.services import uploads as up
from app.services.core import BusinessError, set_param
from app.services.stock import base_qty, change_lot_state, line_reserved

from .conftest import alerts_of


def _stock_file(tmp_path, rows, name="s.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "STOCK_LOTE"
    ws.append(["Número de artículo", "Descripción del artículo", "Lote", "Almacén", "Cantidad", "Fecha de vencimiento",
               "Fecha de fabricación", "Fecha de admisión"])
    for r in rows:
        ws.append(r)
    p = os.path.join(tmp_path, name)
    wb.save(p)
    return p


# --------------------------- cargas -----------------------------------------
def test_carga_stock_con_errores_se_corrige_antes_de_autorizar(s, U, app, tmp_path):
    from app.demo_data import write_stock
    p = os.path.join(tmp_path, "err.xlsx")
    write_stock(p, date.today(), con_errores=True)
    b = up.create_batch(U("coord.almacen"), "STOCK", p, "err.xlsx")
    s.commit()
    assert b.estado == "VALIDADO_CON_ERRORES"
    errs = [r for r in b.rows if r.errores]
    assert len(errs) == 4  # duplicado (2 filas), negativo, no numérico
    with pytest.raises(BusinessError):
        up.confirm(b, U("coord.almacen"))
    neg = next(r for r in b.rows if any("negativa" in e for e in r.errores))
    up.edit_row(b, neg, U("coord.almacen"), {"cantidad": "4"})
    txt = next(r for r in b.rows if any("numérico" in e for e in r.errores))
    up.exclude_row(b, txt, U("coord.almacen"), "Dato ilegible en origen")
    dup = [r for r in b.rows if any("Duplicado" in e for e in r.errores)]
    up.exclude_row(b, dup[-1], U("coord.almacen"), "Fila duplicada")
    s.commit()
    assert b.estado == "LISTO"
    with pytest.raises(BusinessError):  # el auxiliar no autoriza
        up.confirm(b, U("aux.almacen"))
    up.confirm(b, U("coord.almacen"))
    s.commit()
    assert b.estado == "CONFIRMADO"
    assert s.query(StockLot).filter_by(product_code="PT-902", lote="L902Z").one().cantidad == 4
    a = alerts_of(s, "STOCK_CARGA_DIFERENCIAS", b.id)
    assert a and "SISTEMAS" in a[0].roles


def test_carga_stock_reduce_reserva_y_reevalua(s, U, new_order, tmp_path):
    o = new_order([("PT-905", 900)])
    assert o.estado_stock == "COMPLETA"
    hoy = date.today()
    p = _stock_file(tmp_path, [["PT-905", "QUINUA", "L905A", "ALM-001", 500, hoy + timedelta(days=300), None, None]])
    b = up.create_batch(U("coord.almacen"), "STOCK", p, "s.xlsx")
    assert b.resumen["reservas_afectadas"] == 1
    up.confirm(b, U("coord.almacen"))
    s.commit()
    assert line_reserved(o.lines[0]) == 500 and o.estado_stock == "INCOMPLETA"
    assert alerts_of(s, "RESERVA_AFECTADA", o.id)
    # el resto de almacenes no incluidos en el archivo no se tocó
    assert s.query(StockLot).filter_by(product_code="MP-901").one().cantidad == 2000
    # otros lotes de ALM-001 ausentes quedaron en 0
    assert s.query(StockLot).filter_by(product_code="PT-902", lote="L902A").one().cantidad == 0


def test_carga_bom_validacion_y_version(s, U, tmp_path):
    from app.demo_data import write_bom
    p = os.path.join(tmp_path, "bom.xlsx")
    write_bom(p, date.today(), cambios=[("PT-901", "EN-903", 0.002, "EXT-002", 5)])  # duplicado padre/componente
    b = up.create_batch(U("jefe.produccion"), "BOM", p, "bom.xlsx")
    assert b.estado == "VALIDADO_CON_ERRORES"
    assert sum(1 for r in b.rows if any("Duplicado" in e for e in r.errores)) == 2
    up.exclude_row(b, [r for r in b.rows if r.errores][-1], U("jefe.produccion"), "duplicado")
    with pytest.raises(BusinessError):
        up.confirm(b, U("jefe.produccion"), {"incluye_merma": "TAL VEZ"})
    r = up.confirm(b, U("jefe.produccion"), {"incluye_merma": "NO_VERIFICADO"})
    s.commit()
    assert r["version"] == 2 and r["version_anterior"] == 1
    from app.services.production import active_bom
    assert active_bom().version == 2 and active_bom().incluye_merma == "NO_VERIFICADO"


def test_importar_ov_sap_y_liquidacion(s, U, tmp_path):
    from app.demo_data import write_liquidation, write_ovs
    p = os.path.join(tmp_path, "ovs.xlsx")
    write_ovs(p, date.today())
    b = up.create_batch(U("coord.ventas"), "OV", p, "ovs.xlsx")
    res = up.confirm(b, U("coord.ventas"))
    s.commit()
    assert res["ov_creadas"] == 1  # SAP-9002 está cerrada
    from app.models import SalesOrder
    o = s.query(SalesOrder).filter_by(numero="SAP-9001").one()
    assert len(o.lines) == 2 and o.estado_stock == "COMPLETA" and o.vendedor_id == U("vendedor1").id
    p2 = os.path.join(tmp_path, "liq.xlsx")
    write_liquidation(p2, date.today())
    b2 = up.create_batch(U("asist.produccion"), "LIQUIDACION", p2, "liq.xlsx")
    up.confirm(b2, U("asist.produccion"), {"origen": "SAP"})
    s.commit()
    b3 = up.create_batch(U("asist.produccion"), "LIQUIDACION", p2, "liq.xlsx")
    assert b3.estado == "VALIDADO_CON_ERRORES"  # duplicado contra lo ya registrado


def test_parse_presentation():
    assert up.parse_presentation("ARVEJA VERDE PARTIDA * 500 G - CANTACLARO") == ("500 G", 0.5)
    assert up.parse_presentation("ARROZ EXTRA - OLIMAR DAMBO - 50 Kg")[1] == 50
    assert up.product_base("LENTEJA * 400 G - MERKAT") == "LENTEJA"


# --------------------------- estados de stock --------------------------------
def test_estados_stock_y_reservas(s, U, new_order):
    o = new_order([("PT-904", 40)])
    l = o.lines[0].reservations[0].lot
    with pytest.raises(BusinessError):
        change_lot_state(l, "OBSERVADO", U("coord.almacen"), "x")
    change_lot_state(l, "DANADO", U("coord.almacen"), "Sacos rotos")
    s.commit()
    assert line_reserved(o.lines[0]) == 0 and o.estado_stock == "SIN_STOCK"
    assert alerts_of(s, "RESERVA_AFECTADA", o.id)
    # fumigación por registro de Calidad
    l2 = s.query(StockLot).filter_by(product_code="MP-903").one()
    qual.register(U("asist.calidad"), "FUMIGACION", {"inicio_fecha": date.today().isoformat()}, lot_id=l2.id)
    s.commit()
    assert l2.estado == "EN_FUMIGACION" and alerts_of(s, "FUMIGACION")
    qual.register(U("asist.calidad"), "FUMIGACION", {"inicio_fecha": date.today().isoformat(),
                                                    "fin_fecha": date.today().isoformat()}, lot_id=l2.id)
    s.commit()
    assert l2.estado == "PENDIENTE_REVISION"
    with pytest.raises(BusinessError):
        qual.release_lot(l2, U("coord.almacen"), True, "ok")
    qual.release_lot(l2, U("jefe.calidad"), True, "Fumigación conforme")
    assert l2.estado == "DISPONIBLE"


def test_calidad_pcc1_y_no_conforme(s, U):
    r = qual.register(U("asist.calidad"), "RECEPCION_MP", {"grupo_humedad": "QUINUA_CANIHUA_MOTE", "humedad": 13.1,
                                                           "impurezas_conforme": True, "plaga_conforme": True}, "GR-901", "G1")
    s.commit()
    assert r.resultado == "NO_CONFORME" and alerts_of(s, "CALIDAD_NO_CONFORME")
    r2 = qual.register(U("asist.calidad"), "RECEPCION_MP", {"grupo_humedad": "OTROS", "humedad": 13.1}, "MP-901", "M1")
    assert r2.resultado == "CONFORME"
    r3 = qual.register(U("asist.calidad"), "CONTROL_PESOS", {"peso1": 0.502, "peso2": 0.499}, "PT-901", "L")
    assert r3.resultado == "NO_CONFORME"


def test_certificado_revision_y_aprobacion(s, U, new_order):
    o = new_order([("PT-905", 10)])
    lt = o.lines[0].reservations[0].lot
    qual.register(U("asist.calidad"), "MUESTREO", {"humedad": 11.0, "grano_partido": 0.5}, lot_id=lt.id)
    c = qual.generate_certificate(lt, U("superv.calidad"), o)
    s.commit()
    assert c.numero.startswith(f"CP{date.today().year}-PT")
    assert c.datos["humedad"]["resultado"] == "11.0%"
    with pytest.raises(BusinessError):  # datos organolépticos pendientes
        qual.review_certificate(c, U("superv.calidad"), {}, aprobar=True)
    with pytest.raises(BusinessError):
        qual.review_certificate(c, U("asist.calidad"), {"marca": "X"})
    cambios = {f"org_{i}_resultado": "CONFORME" for i in range(3)}
    cambios["marca"] = "MARCA DEMO"
    cambios["tamano_lote"] = "250 kg"
    qual.review_certificate(c, U("superv.calidad"), cambios, aprobar=True)
    s.commit()
    assert c.estado == "APROBADO" and len(c.cambios) >= 3


# --------------------------- conteos ----------------------------------------
def test_conteo_fisico_diferencias(s, U):
    with pytest.raises(BusinessError):  # Q17: el coordinador 1560 no cuenta el almacén 1524
        inv.open_count(U("coord.almacen"), "EXT-002", "EN-901")
    c = inv.open_count(U("coord.almacen.mp"), "EXT-002", "EN-901")
    line = c.lines[0]
    inv.save_lines(c, U("coord.almacen.mp"), {str(line.id): {"conteo": "4", "peso_unitario": "3"}})
    assert line.fisico == 12 and line.faltante == 3 and line.sobrante == 0
    difs = inv.close_count(c, U("coord.almacen.mp"))
    s.commit()
    assert len(difs) == 1
    a = alerts_of(s, "INVENTARIO_DIFERENCIA")[0]
    assert "SISTEMAS" in a.roles and "COORD_ALMACEN_MP" in a.roles and "COORD_ALMACEN" not in a.roles
    lot = s.get(StockLot, line.lot_id)
    assert base_qty(lot) == 12


# --------------------------- alertas ----------------------------------------
def test_alerta_ciclo_y_visibilidad(s, U, new_order):
    o = new_order([("PT-903", 10)])
    a = alerts_of(s, "OV_FALTANTE", o.id)[0]
    assert al.can_see(U("coord.almacen"), a) and al.can_see(U("gerente.general"), a)
    assert not al.can_see(U("montacarguista"), a)
    with pytest.raises(BusinessError):
        al.attend(a, U("montacarguista"))
    al.assign(a, U("coord.almacen"), U("aux.almacen").id, "revisar")
    assert al.can_see(U("aux.almacen"), a)  # asignado
    al.attend(a, U("coord.almacen"), "en revisión")
    al.comment(a, U("gerente.general"), "Priorizar")
    with pytest.raises(BusinessError):
        al.close(a, U("coord.almacen"), "", "")
    al.close(a, U("coord.almacen"), "Stock trasladado", "Traslado desde 767")
    s.commit()
    acciones = [e.accion for e in a.events]
    assert acciones == ["CREADA", "ASIGNADA", "EN_ATENCION", "COMENTARIO", "CERRADA"]
    assert all(e.ts for e in a.events) and a.cerrado_por == U("coord.almacen").id
    # filtros/agrupación de Gerencia General
    rows = al.visible_alerts(U("gerente.general"), prioridad="ALTA", area="Almacén")
    assert all(x.prioridad == "ALTA" and x.area == "Almacén" for x in rows)


def test_correo_sin_smtp_no_se_simula(s, U, new_order, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    new_order([("PT-903", 10)])
    from app.services.mailer import flush_outbox
    r = flush_outbox()
    s.commit()
    assert r["enviados"] == 0 and r["sin_smtp"] > 0
    assert s.query(EmailOutbox).filter_by(estado="ENVIADO").count() == 0
    # GG no recibe por correo los tipos que no configuró
    assert s.query(EmailOutbox).filter_by(destinatario="gerente.general@demo.local").count() == 0


def test_alerta_80_por_ciento(s, U, new_order):
    from app.services.orders import register_picking
    o = new_order([("PT-905", 100)])
    from app.services.orders import validate_picking_plan
    with pytest.raises(BusinessError):  # TO-BE: primero se valida el plan de picking
        register_picking(o, U("lider.almacen"), o.lines[0].id, 1, "L905A")
    validate_picking_plan(o, U("lider.almacen"))
    register_picking(o, U("lider.almacen"), o.lines[0].id, 85, "L905A")
    s.commit()
    assert alerts_of(s, "OV_80_PREPARACION", o.id)
    with pytest.raises(BusinessError):  # lote no reservado
        register_picking(o, U("lider.almacen"), o.lines[0].id, 5, "OTRO")
    with pytest.raises(BusinessError):  # excede lo reservado
        register_picking(o, U("lider.almacen"), o.lines[0].id, 50, "L905A")


# --------------------------- reposición / verificaciones --------------------
def test_reposicion_calculo(s, U, today):
    from app.models import Product
    p = s.get(Product, "EN-901")
    a = buy.analyze_product(p, today)
    assert a["consumo_diario"] == pytest.approx(1.2) and a["plazo_dias"] == 30
    assert a["cantidad_sugerida"] == 21  # 1.2 × 30 − 15 disponibles
    lt, modo = buy.lead_time_for(p, date(today.year, 11, 15))
    assert lt.dias_max == 40 and modo == "estacional"
    set_param("margen_reposicion_dias", 5, U("sistemas"))
    assert buy.analyze_product(p, today)["cantidad_sugerida"] == 27
    creadas = buy.run_replenishment(U("coord.almacen"), ["EN-901"], today)
    s.commit()
    assert creadas and creadas[0].estado == "BORRADOR" and alerts_of(s, "REPOSICION_SUGERIDA")
    buy.send(creadas[0], U("coord.almacen"))
    assert creadas[0].estado == "PENDIENTE_LOGISTICA" and alerts_of(s, "COMPRA_APROBACION_LOGISTICA")  # Q14
    with pytest.raises(BusinessError):
        buy.approve_logistics(creadas[0], U("coord.logistica"), True)
    buy.approve_logistics(creadas[0], U("jefe.logistica"), True)
    assert creadas[0].estado == "SOLICITADA"


def test_verificaciones_periodicas(s, U, new_order, today):
    o = new_order([("PT-905", 10)], dias=-1)
    from app.services.scheduler import run_checks
    r = run_checks(U("sistemas"), today)
    s.commit()
    assert r["ov_retrasadas"] >= 1 and alerts_of(s, "OV_RETRASO", o.id)
    assert r["lotes_por_vencer"] >= 1  # L901B vence en 12 días (umbral demo 30)
    run_checks(U("sistemas"), today)
    s.commit()
    assert len(alerts_of(s, "OV_RETRASO", o.id)) == 1  # sin duplicados


# --------------------------- permisos ---------------------------------------
def test_matriz_permisos_reglas_documentadas(s):
    def roles_con(perm):
        return {rp.role_code for rp in s.query(RolePermission).filter_by(perm_code=perm)}
    # Q4: Gerencia General aprueba; Sistemas tiene acceso pero no aprueba
    assert roles_con("ov.cancelar") == {"COORD_VENTAS", "JEFE_VENTAS", "GERENCIA_GENERAL"}
    # Q13: Jefe o Coordinador de Logística; Q14: Jefe de Logística aprueba compras; Q16: Líder Operativo autoriza salida
    assert roles_con("traslado.autorizar") == {"JEFE_LOGISTICA", "COORD_LOGISTICA", "GERENCIA_GENERAL"}
    assert roles_con("compras.aprobar_solicitud") == {"JEFE_LOGISTICA", "GERENCIA_GENERAL"}
    assert roles_con("distribucion.aprobar_salida_discrepancia") == {"JEFE_LOGISTICA", "COORD_LOGISTICA", "GERENCIA_GENERAL"}
    assert roles_con("reempaque.solicitar") == {"COORD_ALMACEN", "COORD_ALMACEN_MP", "SUPERV_ALMACEN", "GERENCIA_GENERAL"}
    assert roles_con("calidad.certificado_revisar") == {"JEFE_CALIDAD", "SUPERV_CALIDAD", "GERENCIA_GENERAL"}
    assert roles_con("distribucion.confirmar_salida") == {"LIDER_ALMACEN", "GERENCIA_GENERAL"}
    # Q3: despacho parcial lo aprueba GO o Jefatura de Logística (y GG por acceso completo)
    assert roles_con("ov.aprobar_parcial") == {"GERENCIA_OPERACIONES", "JEFE_LOGISTICA", "GERENCIA_GENERAL"}
    aprob = {p.code for p in s.query(Permission).filter_by(tipo="aprobacion")}
    sist = {rp.perm_code for rp in s.query(RolePermission).filter_by(role_code="SISTEMAS")}
    assert not (aprob & sist) and "config.editar" in sist and "usuarios.administrar" in sist and "ov.ver" in sist
    assert "ASIST_VENTAS" not in roles_con("ov.modificar")
    assert {"ov.solicitar_modificacion", "ov.importar"} <= {rp.perm_code for rp in s.query(RolePermission).filter_by(role_code="ASIST_VENTAS")}
    assert "COMPRAS" not in roles_con("compras.solicitar")
    assert roles_con("facturacion.cargar") == {"FACTURACION", "GERENCIA_GENERAL", "SISTEMAS"}
    rp = s.query(RolePermission).filter_by(role_code="JEFE_VENTAS", perm_code="ov.cancelar").one()
    assert rp.origen == "DEFINIDO"


def test_salidas_no_descarta_lineas_legitimas_y_evita_recarga(s, U, tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Qy"
    ws.append(["Número de documento", "Fecha de Emisión", "Código de Producto", "Cantidad"])
    ws.append(["D1", date.today(), "PT-901", 5])
    ws.append(["D1", date.today(), "PT-901", 3])  # misma OV/producto en dos líneas: legítimo
    ws.append(["D1", date.today(), None, 1])      # servicio sin producto
    p = os.path.join(tmp_path, "qy.xlsx")
    wb.save(p)
    r = up.confirm(up.create_batch(U("coord.almacen"), "SALIDAS", p, "qy.xlsx"), U("coord.almacen"))
    assert r["registros"] == 2 and r["omitidos_sin_producto"] == 1
    r2 = up.confirm(up.create_batch(U("coord.almacen"), "SALIDAS", p, "qy.xlsx"), U("coord.almacen"))
    assert r2["registros"] == 0 and r2["omitidos_ya_cargados"] == 2


def test_fechas_de_carga():
    from datetime import date as d
    assert up._date(46474) == d(2027, 3, 28)  # número de serie de Excel
    assert up._date("21/08/2026") == d(2026, 8, 21)
    with pytest.raises(ValueError):
        up._date("01/01/0026")  # año inválido presente en el stock real
