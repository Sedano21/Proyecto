"""Decisiones del usuario del 13-oct-2026: Q11 (lista de precios mínimos, solo el Jefe Comercial la modifica, alerta de
OV en el límite o por debajo), Q16 (vistos buenos de Seguridad, Líder Operativo y Auxiliar de Despacho), Q17 (nadie
aprueba su propia solicitud de traslado), Q5 (almacenes virtuales), Q6 (lote nuevo pendiente de revisión), Q9 (reparto
de la cantidad de una liquidación con varios lotes) y Q10 (fases de importación a cargo del Coordinador de Importación)."""
import os
from datetime import date, timedelta

import openpyxl
import pytest

from app.models import Customer, ImportPhaseTemplate, PriceItem, Role, StockLot, Warehouse
from app.services import despacho as dsp
from app.services import distribution as dist
from app.services import orders as osvc
from app.services import prices as prc
from app.services import uploads as up
from app.services.core import BusinessError
from app.services.stock import add_or_increase_lot, change_lot_state

from .conftest import alerts_of
from .test_flujos import approve_certs


def _min(s, sku, canal):
    return s.query(PriceItem).filter_by(lista="GENERAL", product_code=sku, canal=canal, vigente=True).one()


def test_q11_lista_cargada_formula_recalculada_y_solo_jefe_comercial_modifica(s, U):
    it = _min(s, "PT-901", "MAYORISTA")
    assert it.precio == pytest.approx(1.80 / (1 - 0.12), rel=1e-6)  # fórmula sin valor calculado: costo/(1−margen)
    assert _min(s, "PT-906", "AUTOSERVICIOS").precio == pytest.approx(1.60 / 0.65, rel=1e-5)
    g = s.query(PriceItem).filter_by(lista="GRANEL", product_code="MP-901", vigente=True).one()
    assert g.precio_saco == 90 and g.precio_kg == pytest.approx(3.6)
    assert not hasattr(it, "costo")  # el costo de la empresa no se guarda
    for quien in ("gerente.general", "sistemas", "coord.ventas", "gerente.comercial"):
        with pytest.raises(BusinessError):
            prc.edit_item(it, U(quien), "x", precio=3)
    with pytest.raises(BusinessError):  # motivo obligatorio
        prc.edit_item(it, U("jefe.ventas"), "", precio=3)
    nuevo = prc.edit_item(it, U("jefe.ventas"), "Ajuste de campaña", precio=2.5)
    s.commit()
    assert not it.vigente and it.hasta and nuevo.vigente and nuevo.precio == 2.5
    assert len([h for h in prc.history("PT-901") if h.canal == "MAYORISTA"]) == 2


def test_q11_alerta_si_la_ov_esta_en_el_limite_o_por_debajo(s, U, new_order):
    minimo = _min(s, "PT-905", "MAYORISTA").precio
    o = osvc.create_order(U("coord.ventas"), "P-1", s.query(Customer).filter_by(ruc="20000000001").one().id,
                          date.today() + timedelta(days=3), [{"product_code": "PT-905", "cantidad": 10,
                                                              "precio_unitario": round(minimo - 0.01, 4)}],
                          vendedor_id=U("vendedor1").id, oc_archivo="oc_prueba.pdf")
    s.commit()
    l = o.lines[0]
    assert l.precio_minimo == pytest.approx(minimo) and l.precio_origen.startswith("POR DEBAJO")
    a = alerts_of(s, "OV_PRECIO_BAJO_MINIMO", o.id)[0]
    assert {"JEFE_VENTAS", "GERENTE_COMERCIAL"} <= set(a.roles) and U("vendedor1").id in a.usuarios
    assert l.precio_unitario == pytest.approx(minimo - 0.01, abs=1e-4)  # el sistema no cambia el precio de la OV
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 10, "precio_unitario": minimo}]})
    s.commit()
    # V7 (26-oct): en el límite solo informa: no detiene la OV y se avisa con una alerta informativa
    assert o.lines[0].precio_origen.startswith("EN EL LÍMITE") and not o.retenida_precio
    assert alerts_of(s, "OV_PRECIO_LIMITE", o.id)
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 10,
                                                        "precio_unitario": minimo * 1.2}]})
    s.commit()
    assert o.lines[0].precio_origen.startswith("Sobre") and a.estado == "COMPLETADA"


def test_q11_ov_sin_precio_o_muestra_comercial_queda_detenida(s, U, new_order):
    """Decisión 13-oct (2.ª parte): las muestras comerciales (precio 0) se incluyen en la alerta y la OV queda detenida
    hasta la confirmación del Coordinador o Jefe Comercial."""
    o = osvc.create_order(U("coord.ventas"), "MC-1", s.query(Customer).filter_by(ruc="20000000001").one().id,
                          date.today() + timedelta(days=3), [{"product_code": "PT-905", "cantidad": 10}],
                          tipo_venta="Muestra comercial", oc_archivo="oc_prueba.pdf")
    s.commit()
    assert o.retenida_precio and "sin precio de venta" in o.lines[0].precio_origen
    a = alerts_of(s, "OV_PRECIO_BAJO_MINIMO", o.id)[0]
    assert "Muestra comercial" in a.titulo and {"COORD_VENTAS", "JEFE_VENTAS"} <= set(a.roles)
    assert not osvc.ready_for_preparation(o) and dist.active_stop(o) is None  # no se prepara ni se programa
    for quien in ("gerente.general", "sistemas", "vendedor1", "asist.ventas"):
        with pytest.raises(BusinessError):
            prc.approve_price(o, U(quien), "ok")
    with pytest.raises(BusinessError):  # motivo obligatorio
        prc.approve_price(o, U("coord.ventas"), "")
    prc.approve_price(o, U("coord.ventas"), "Muestra para cliente nuevo")
    s.commit()
    assert not o.retenida_precio and a.estado == "COMPLETADA" and osvc.ready_for_preparation(o)
    assert dist.active_stop(o) is not None  # al liberarse se programa la ruta (TO-BE)
    # si luego cambian los precios observados, vuelve a detenerse
    osvc.modify_order(o, U("coord.ventas"), {"lines": [{"product_code": "PT-905", "cantidad": 12, "precio_unitario": 0.1}]})
    s.commit()
    assert o.retenida_precio


def test_q11_productos_o_clientes_sin_precio_alertan_para_completar(s, U):
    c = Customer(ruc="20000000099", nombre="CLIENTE DEMO OFICINA", grupo="OFICINA")
    s.add(c)
    s.flush()
    o = osvc.create_order(U("coord.ventas"), "P-2", c.id, date.today() + timedelta(days=3),
                          [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 999}], oc_archivo="oc_prueba.pdf")
    assert o.lines[0].precio_minimo is None and not o.retenida_precio
    assert "canal" in alerts_of(s, "PRECIO_FALTANTE", o.id)[0].mensaje
    from app.services.core import has_perm
    assert not has_perm(U("coord.ventas"), "clientes.canal")  # solo el Jefe Comercial (o Sistemas) traslada clientes
    assert has_perm(U("jefe.ventas"), "clientes.canal") and has_perm(U("sistemas"), "clientes.canal")
    assert not has_perm(U("gerente.general"), "clientes.canal") and not has_perm(U("gerente.general"), "config.editar")
    o2 = osvc.create_order(U("coord.ventas"), "P-3", s.query(Customer).filter_by(ruc="20000000001").one().id,
                           date.today() + timedelta(days=3), [{"product_code": "EN-903", "cantidad": 5, "precio_unitario": 1}], oc_archivo="oc_prueba.pdf")
    assert "EN-903" in alerts_of(s, "PRECIO_FALTANTE", o2.id)[0].mensaje and not o2.retenida_precio
    prc.add_item(U("jefe.ventas"), "GENERAL", "EN-903", canal="MAYORISTA", precio=0.8, motivo="Completar lista")
    osvc.modify_order(o2, U("coord.ventas"), {"lines": [{"product_code": "EN-903", "cantidad": 5, "precio_unitario": 1}]})
    s.commit()
    assert alerts_of(s, "PRECIO_FALTANTE", o2.id)[0].estado == "COMPLETADA" and o2.lines[0].precio_minimo == 0.8


def test_q11_lista_granel_por_canal_y_compara_kg_y_saco(s, U):
    from app.models import Product
    p = s.get(Product, "MP-901")  # granel: 90 por saco de 25 kg = 3.6 por kg
    mayor = s.query(Customer).filter_by(ruc="20000000001").one()
    assert prc.price_for(p, mayor)[1].startswith("Lista de precios, canal MAYORISTA")  # presentaciones
    mayor.canal_precio = "MAYORISTA GRANEL"  # el Jefe Comercial lo traslada al canal granel
    s.flush()
    minimo, origen = prc.price_for(p, mayor)
    assert "granel" in origen
    p.um = "KILOGRAMO"
    o = osvc.create_order(U("coord.ventas"), "G-1", mayor.id, date.today() + timedelta(days=3),
                          [{"product_code": "MP-901", "cantidad": 100, "precio_unitario": 3.5}], oc_archivo="oc_prueba.pdf")
    assert o.retenida_precio and "por kg: S/ 3.50 vs mínimo S/ 3.60" in o.lines[0].precio_origen
    assert "por saco: S/ 87.50 vs mínimo S/ 90.00" in o.lines[0].precio_origen  # compara ambos


def test_q11_vigencia_de_lista_avisa_sin_bloquear(s, U, new_order, today):
    with pytest.raises(BusinessError):
        prc.set_validity(U("gerente.general"), "GENERAL", today - timedelta(days=30), today - timedelta(days=1))
    prc.set_validity(U("jefe.ventas"), "GENERAL", today - timedelta(days=30), today - timedelta(days=1))
    assert prc.check_validity(today) == 1 and alerts_of(s, "LISTA_PRECIOS_VENCIDA")
    o = new_order([("PT-905", 10)], precio=0.01)
    assert o.lines[0].precio_minimo is not None and o.retenida_precio  # la lista vencida se sigue usando


def test_q16_salida_requiere_tres_vistos_buenos(s, U, new_order):
    o = new_order([("PT-905", 40)])
    osvc.validate_picking_plan(o, U("lider.almacen"))
    for l in o.lines:
        for r in [r for r in l.reservations if r.estado == "ACTIVA"]:
            osvc.register_picking(o, U("lider.almacen"), l.id, r.cantidad, r.lot.lote)
    r = dist.active_stop(o).route
    dist.confirm_route(r, U("coord.distribucion"))
    dsp.add_photo(r, U("aux.despacho"), "vehiculo", "v.jpg")
    with pytest.raises(BusinessError):  # sin carga validada no hay visto bueno del chofer
        dsp.give_exit_ok(r, (s.get(type(U("conductor1")), r.driver.user_id) if r.driver and r.driver.user_id else U("coord.distribucion")))
    dsp.add_photo(r, U("aux.despacho"), "mercaderia_cargada", "m.jpg")
    dsp.add_photo(r, U("conductor1"), "vehiculo_salida", "salida.jpg")  # obs. demo v0.6
    if r.driver and r.driver.user_id:  # V7: el chofer valida primero
        dsp.driver_check_load(r, s.get(type(U("conductor1")), r.driver.user_id), {})
    dsp.validate_load(r, U("aux.despacho"), {})
    lines = [{**e, "guia": e["esperado"], "cargado": e["esperado"]} for e in dist.expected_lines(r)]
    dist.register_security_check(r, U("seguridad"), "T1", lines)
    for st in r.stops:
        dsp.set_guide(st, U("coord.distribucion"), "T1", "SISTEMA")
        dsp.set_invoice(st, U("facturacion"), "F1", "f.pdf")
    approve_certs(s, U, o)
    check = {k: True for k, _ in dist.CHECKLIST}
    with pytest.raises(BusinessError, match="Seguridad"):
        dsp.review_documents(r, U("aux.despacho"), True)
    assert dsp.review_documents(r, U("seguridad"), impresos=True) == []
    with pytest.raises(BusinessError, match="Chofer"):  # V8 (D02)
        dist.confirm_departure(r, U("lider.almacen"), check)
    for quien in ("seguridad", "lider.almacen", "aux.despacho"):
        with pytest.raises(BusinessError):
            dsp.give_exit_ok(r, U(quien))
    dsp.give_exit_ok(r, (s.get(type(U("conductor1")), r.driver.user_id) if r.driver and r.driver.user_id else U("coord.distribucion")), "Carga conforme")
    dist.confirm_departure(r, U("lider.almacen"), check)
    assert set(r.vistos_buenos) == {"SEGURIDAD", "CHOFER", "LIDER_ALMACEN"} and r.estado == "EN_RUTA"


def test_q5_almacenes_virtuales_los_manejan_coord_1560_y_logistica(s, U):
    up._ensure_wh("PRO-01")
    assert s.get(Warehouse, "PRO-01").uso == "VIRTUAL"
    lot = add_or_increase_lot("PT-905", "ALM-005", "LV1", 10, "DISPONIBLE")
    pro = add_or_increase_lot("PT-905", "PRO-01", "LV2", 10, "DISPONIBLE")
    s.flush()
    assert lot.warehouse.reservable is False
    with pytest.raises(BusinessError):
        change_lot_state(lot, "DANADO", U("coord.almacen.mp"), "x")
    for quien in ("coord.logistica", "jefe.logistica", "coord.almacen"):
        change_lot_state(lot, "DANADO" if lot.estado != "DANADO" else "NO_UTILIZABLE", U(quien), "Revisión")
    with pytest.raises(BusinessError):  # V13: un lote bloqueado solo lo libera Calidad
        change_lot_state(lot, "DISPONIBLE", U("coord.almacen"), "Revisión")
    change_lot_state(pro, "DANADO", U("coord.logistica"), "PRO-* también es virtual")
    l001 = s.query(StockLot).filter_by(product_code="PT-905", warehouse_code="ALM-001").first()
    with pytest.raises(BusinessError):  # Logística solo maneja los virtuales
        change_lot_state(l001, "DANADO", U("coord.logistica"), "x")


def test_q6_lote_nuevo_en_carga_posterior_queda_pendiente_de_revision(s, U, tmp_path, today):
    from app.demo_data import write_stock
    p = os.path.join(tmp_path, "s2.xlsx")
    write_stock(p, today, extra_rows=[("PT-905", "L905N", "ALM-001", 50, today + timedelta(days=300), None, None)])
    b = up.create_batch(U("coord.almacen"), "STOCK", p, "s2.xlsx")
    up.confirm(b, U("coord.almacen"))
    s.commit()
    nuevo = s.query(StockLot).filter_by(lote="L905N").one()
    assert nuevo.estado == "PENDIENTE_REVISION"
    assert s.query(StockLot).filter_by(lote="L905A", warehouse_code="ALM-001").first().estado == "DISPONIBLE"


def test_q9_liquidacion_con_varios_lotes_reparte_la_cantidad(s, U, tmp_path, today):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dat.Prod"
    ws.append(["Número de documento", "Tipo de Operación", "Almacén", "Fecha de creación", "Código de producto",
               "Descripción de producto", "Cantidad Planificada", "Cantidad Completada", "Unidad de medida", "Lote"])
    for lote in ("LQA", "LQB", "LQC"):
        ws.append(["DOC-77", "Estándar", "ALM", today, "PT-903", "LENTEJA", 301, 301, "UNIDAD", lote])
    p = os.path.join(tmp_path, "liq.xlsx")
    wb.save(p)
    b = up.create_batch(U("jefe.produccion"), "LIQUIDACION", p, "liq.xlsx")
    qs = [up._num(r.datos["completada"]) for r in sorted(b.rows, key=lambda r: r.fila)]
    assert qs == [100, 100, 101] and sum(qs) == 301
    assert any("repartió" in w for r in b.rows for w in r.advertencias)
    fila = b.rows[0]
    up.edit_row(b, fila, U("jefe.produccion"), {"completada": "150"})  # reparto real distinto: debe cuadrar
    assert b.estado == "VALIDADO_CON_ERRORES"
    up.edit_row(b, b.rows[1], U("jefe.produccion"), {"completada": "50"})
    assert b.estado != "VALIDADO_CON_ERRORES"
    up.confirm(b, U("jefe.produccion"))
    from app.models import Liquidation
    assert sorted(l.cantidad_completada for l in s.query(Liquidation).filter_by(numero_documento="DOC-77")) == [50, 101, 150]


def test_q10_fases_de_importacion_a_cargo_del_coordinador_de_importacion(s):
    assert {f.responsable_rol for f in s.query(ImportPhaseTemplate)} == {"IMPORTACIONES"}
    assert s.get(Role, "IMPORTACIONES").nombre == "Coordinador de Importación"
