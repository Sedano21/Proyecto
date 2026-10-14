"""Observaciones al demo v0.6 – Almacén: picking programado por persona, tareas con foto, detalle de pre-solicitudes,
materia prima en almacén externo, granel con GO y lista de materiales aprobada por Producción."""
from datetime import date

import pytest

from app.models import PickingRecord
from app.services import picking as pk
from app.services.core import BusinessError

from .conftest import alerts_of


def test_picking_preprogramado_asignado_y_ejecutado_con_fotos(s, U, new_order):
    from app.services import orders as osvc
    o = new_order([("PT-905", 10)])
    tareas = pk.tasks_of(o)
    assert tareas, "el sistema preprograma el picking al quedar la OV lista"
    t = tareas[0]
    assert t.asignados and alerts_of(s, "PICKING_PROGRAMADO", o.id)
    with pytest.raises(BusinessError, match="Líder Operativo"):
        pk.assign(t, U("aux.almacen"), [U("aux.almacen2").id])
    with pytest.raises(BusinessError, match="personal del almacén"):
        pk.assign(t, U("lider.almacen"), [U("aux.almacen.mp").id])
    pk.assign(t, U("lider.almacen"), [U("aux.almacen2").id, U("aux.almacen3").id])  # grupo
    assert t in pk.schedule(U("aux.almacen2"), t.fecha, t.fecha, solo_mios=True)
    with pytest.raises(BusinessError, match="foto"):
        pk.start(t, U("aux.almacen2"), "")
    pk.start(t, U("aux.almacen2"), "foto_ini.jpg")
    osvc.validate_picking_plan(o, U("lider.almacen"))
    line = o.lines[0]
    res = next(r for r in line.reservations if r.estado == "ACTIVA")
    pk.record(t, U("aux.almacen2"), line.id, res.cantidad, res.lot.lote, comentario="ok")
    s.flush()
    rec = s.query(PickingRecord).filter_by(task_id=t.id).one()
    assert rec.fecha_venc == res.lot.fecha_venc
    pk.finish(t, U("aux.almacen2"), "foto_fin.jpg", "Listo en zona de despacho")
    assert t.estado == "LISTO" and alerts_of(s, "MONTACARGUISTA_DESPACHO", o.id)
    filas = pk.format_rows([t])
    assert filas[0]["lote"] == res.lot.lote and filas[0]["despachado"] == res.cantidad


def test_montacarguista_inicia_y_termina_con_foto_sin_asignar(s, U, new_order):
    from app.services import alerts as al
    o = new_order([("PT-905", 10)])
    a = al.emit("MONTACARGUISTA_DESPACHO", "Trasladar OV a despacho", "", "SalesOrder", o.id)
    s.flush()
    m = U("montacarguista")
    with pytest.raises(BusinessError):
        al.assign(a, m, m.id)
    al.start_with_photo(a, m, "ini.jpg")
    assert a.estado == "EN_EJECUCION" and a.asignado_a == m.id
    al.finish_with_photo(a, m, "fin.jpg", "sin observaciones")
    assert a.estado == "COMPLETADA" and a.evidencia == "fin.jpg" and a.foto_inicio == "ini.jpg"


def test_materia_prima_en_almacen_externo(s, U):
    from app.services.production import available_by_warehouse
    r = available_by_warehouse("MP-901")
    assert isinstance(r, dict)


def test_compra_de_granel_requiere_gerencia_de_operaciones(s, U):
    from app.services import purchasing as buy
    from app.models import Product
    gr = s.query(Product).filter_by(tipo="GR").first()
    if gr is None:
        pytest.skip("sin artículo granel en la demo")
    r = buy.create_request(U("coord.almacen.mp"), gr.code, 1)
    assert buy.go_reason(r) == "granel" and buy.needs_go_approval(r)


def test_lista_de_materiales_la_aprueba_produccion(s, U):
    from app.models import ProductionRequest
    from app.services import production as prod
    req = ProductionRequest(product_code="PT-901", cantidad=10, estado="BORRADOR")
    s.add(req)
    s.flush()
    with pytest.raises(BusinessError, match="Producción"):
        prod.review_bom(req, U("coord.almacen"), True)
    prod.review_bom(req, U("asist.produccion"), True)
    assert req.bom_revision["conforme"]


def test_informe_de_almacen(s, U):
    from app.services.reports import almacen
    d = almacen(warehouse="ALM-001")
    assert "serie" in d and "reserva" in d and "dif_conteo" in d
