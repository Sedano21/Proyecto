"""V66 (23-nov-2026): marcha blanca del área de almacén. Movimientos con varios productos y varias personas, lote
adicional en el picking, notas de crédito en el picking, traslados a SAP, pedidos grandes de última hora, consolidado,
etiquetas de Calidad y accesos del Asistente de Almacén. Solo datos ficticios."""
from datetime import date, datetime, timedelta

import pytest

from app.models import StockLot
from app.services import picking as pk
from app.services.core import BusinessError

from .conftest import alerts_of
from .test_v64 import _cliente


def test_movimiento_con_varios_productos_y_dos_montacarguistas(s, U):
    from app.services import supply
    m1, m2 = U("montacarguista"), U("montacarguista2")
    m = supply.request_move(U("lider.almacen"), "RACK A", "DESPACHO", carga={"tipo": "PALLET_PT", "cantidad": 2,
                                                                          "producto": "PT-901"},
                            adicionales=[{"producto": "GR-901", "cantidad": "3", "unidad": "sacos"},
                                         {"producto": "", "cantidad": ""}],
                            equipo=[str(m1.id), str(m2.id)])
    s.commit()
    assert m.equipo == [m1.id, m2.id] and m.asignado_a is None
    assert m.carga["adicionales"][0]["producto"] == "GR-901" and "GR-901" in m.detalle
    with pytest.raises(BusinessError):
        supply.start_move(U("aux.almacen"), m, "ini.jpg")  # no es del equipo
    supply.start_move(m2, m, "ini.jpg")
    supply.finish_move(m1, m, "fin.jpg")  # cualquiera del equipo lo termina
    assert m.estado == "COMPLETADA"
    with pytest.raises(BusinessError):
        supply.request_move(U("lider.almacen"), "A", "B", adicionales=[{"producto": "NO-EXISTE", "cantidad": 1}])


def test_lote_adicional_cuando_uno_no_alcanza(s, U, new_order):
    from app.services.stock import line_reserved
    o = new_order([("PT-901", 50)])
    line = o.lines[0]
    t = pk.tasks_of(o)[0]
    pk.start(t, U("lider.almacen"), "ini.jpg")
    # se simula que el lote reservado no alcanzaba: se quitan 10 de la reserva
    res = next(r for r in line.reservations if r.estado == "ACTIVA")
    res.cantidad -= 10
    s.flush()
    assert pk.falta_reservar(t, line) == pytest.approx(10)
    otro = next(x["lot"] for x in pk.lot_options(t, line, todos=True) if x["ok"])
    pk.add_lot(t, U("lider.almacen"), line.id, otro.id, 10, "un lote no alcanzaba")
    s.flush()
    assert line_reserved(line) == pytest.approx(50) and t.cambios_lote[-1]["lote_nuevo"] == otro.lote
    with pytest.raises(BusinessError):
        pk.add_lot(t, U("lider.almacen"), line.id, otro.id, 1)  # ya está todo reservado


def test_pedido_grande_de_ultima_hora_espera_a_almacen(s, U, new_order):
    from app.services import almacen_v66 as av
    from app.services.core import set_param
    from app.services.orders import ready_for_preparation
    set_param("almacen_ov_tardia_hora", "00:00")
    set_param("almacen_ov_tardia_unidades", 100)
    s.commit()
    o = new_order([("PT-901", 150)], dias=1)
    assert av.pendiente(o) and alerts_of(s, "OV_VALIDAR_ALMACEN", o.id)
    assert not ready_for_preparation(o)
    t = pk.tasks_of(o)
    if t:
        with pytest.raises(BusinessError, match="validación"):
            pk.start(t[0], U("lider.almacen"), "ini.jpg")
    with pytest.raises(BusinessError):
        av.validar(U("aux.almacen"), o, True)  # el auxiliar no valida
    with pytest.raises(BusinessError):
        av.validar(U("lider.almacen"), o, False, "")  # observar exige motivo
    av.validar(U("lider.almacen"), o, True, "ok")
    assert o.validacion_almacen["estado"] == "VALIDADA"
    chica = new_order([("PT-901", 5)], dias=1)
    assert not av.pendiente(chica)
    lejana = new_order([("PT-901", 150)], dias=5)
    assert not av.pendiente(lejana)


def test_consolidado_por_cliente_y_pdf(app, s, U, new_order):
    from app.services import almacen_v66 as av
    new_order([("PT-901", 10)], dias=1)
    new_order([("PT-901", 20)], dias=1)
    d = av.consolidado(date.today(), date.today() + timedelta(days=2))
    g = next(x for x in d["grupos"] if "PT-901" in x["productos"])
    assert g["productos"]["PT-901"]["cantidad"] >= 30 and len(g["productos"]["PT-901"]["ovs"]) >= 2
    c = _cliente(app, "lider.almacen")
    assert "Consolidado del picking" in c.get("/almacen/consolidado").get_data(as_text=True)
    r = c.get("/almacen/consolidado?formato=pdf")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    assert c.get("/almacen/consolidado?formato=xlsx").status_code == 200


def test_etiquetas_de_calidad_en_el_picking(app, s, U, new_order):
    from app.services import etiquetas
    o = new_order([("PT-901", 5)])
    with pytest.raises(BusinessError):
        etiquetas.guardar(U("aux.almacen"), "PT-901", instrucciones="x")
    e = etiquetas.guardar(U("jefe.calidad"), "PT-901", marca="MARCA FICTICIA", instrucciones="Una por saco, en la cara frontal")
    s.commit()
    assert e in etiquetas.para_orden(o)
    t = pk.tasks_of(o)[0]
    html = _cliente(app, "lider.almacen").get(f"/almacen/picking/{t.id}").get_data(as_text=True)
    assert "MARCA FICTICIA" in html and "Etiquetas que indica Calidad" in html


def test_traslado_recibido_queda_para_sap(s, U):
    from app.models import Transfer, Warehouse
    from app.services import transfers, traslados_sap
    lot = s.query(StockLot).filter(StockLot.cantidad > 5, StockLot.estado == "DISPONIBLE").first()
    destino = next(w.code for w in s.query(Warehouse).all() if w.code != lot.warehouse_code)
    t = Transfer(origen_lot_id=lot.id, destino_code=destino, cantidad=2, estado="EN_TRANSITO")
    s.add(t)
    s.flush()
    user = U("sistemas")
    transfers.receive(t, user, 2, "")
    assert t.sap["estado"] == "PENDIENTE"
    body = traslados_sap.payload(t)
    linea = body["StockTransferLines"][0]
    assert linea["ItemCode"] == lot.product_code and linea["Quantity"] == 2 and linea["WarehouseCode"] == destino

    class SL:
        cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}

        def _req(self, method, path, body=None, headers=None):
            assert path == "StockTransfers"
            return {"DocEntry": 9, "DocNum": 99}
    from app.services.core import set_param
    set_param("sap_escritura_ov", True)
    s.flush()
    assert traslados_sap.push(t, SL()) == "ENVIADO" and t.sap["docnum"] == "99"


def test_nota_de_credito_en_picking_solo_si_afecta(app, s, U, new_order):
    from app.models import OrderCreditNote
    o = new_order([("PT-901", 5)])
    s.add(OrderCreditNote(clave="NC-FICT:1", nc_numero="NC-FICT-1", ov_numero=o.numero, order_id=o.id,
                          product_code="PT-901", cantidad=1, aplicada=0, estado="YA_DESPACHADO"))
    s.commit()
    t = pk.tasks_of(o)[0]
    c = _cliente(app, "lider.almacen")
    assert "NC-FICT-1" not in c.get(f"/almacen/picking/{t.id}").get_data(as_text=True)
    assert "NC-FICT-1" in _cliente(app, "jefe.ventas").get(f"/ov/{o.id}").get_data(as_text=True)


def test_asistente_de_almacen_tiene_lo_del_lider_y_mas(app, s):
    from app.models import RolePermission
    perms = {rp.perm_code for rp in s.query(RolePermission).filter_by(role_code="ASIST_ALMACEN")}
    lider = {rp.perm_code for rp in s.query(RolePermission).filter_by(role_code="LIDER_ALMACEN")}
    assert lider <= perms
    assert {"ingresos.ver", "compras.recibir", "produccion.ver", "produccion.solicitud", "almacen.consolidado"} <= perms
