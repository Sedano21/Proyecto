"""V43 (14-nov-2026): gráficos sin rótulos encimados, un solo picking por cliente y fecha de despacho, historial de SAP
del año anterior para comparar. Solo datos ficticios."""
import re
from datetime import date, timedelta

import pytest

from .test_v26 import _cliente


def test_columnas_sin_rotulos_encimados():
    from app.services import charts
    labels = [f"Sem {d:02d}/09 – {d + 5:02d}/09" for d in range(1, 31, 2)]
    svg = str(charts.columns(labels, [("Proyectado", [0] * 15), ("Pedido (OV)", [54480 + i * 9000 for i in range(15)]),
                                      ("Despachado", [858348 if i == 6 else 1000 * i for i in range(15)])], "kg"))
    assert "rotate(-40" in svg  # etiquetas largas inclinadas, no encimadas
    vals = re.findall(r'class="val"[^>]*>([^<]*)<', svg)
    assert "0.0" not in vals and "0" not in vals  # sin ceros sobre el eje
    assert all(len(v) <= 6 for v in vals)  # números compactos (858 k, no «858 348»)
    assert charts._corto(858348) == "858 k" and charts._corto(1234567) == "1,2 M" and charts._corto(5448) == "5,4 k"
    assert "legend" in svg and "Pase el cursor" in svg
    assert "Sin datos" in str(charts.columns(["a", "b"], [("x", [0, 0])]))


def _dos_ov_mismo_cliente(new_order):
    a = new_order([("PT-901", 6)], dias=2)
    b = new_order([("PT-901", 4), ("PT-905", 3)], dias=2)
    return a, b


def test_un_solo_picking_por_cliente_y_fecha(app, s, U, new_order):
    from app.services import picking as pk
    from app.services import picking_cliente as pc
    from app.services.core import BusinessError
    a, b = _dos_ov_mismo_cliente(new_order)
    s.commit()
    ta, tb = pk.tasks_of(a)[0], pk.tasks_of(b)[0]
    assert ta.warehouse_code == tb.warehouse_code
    ts = pc.tareas(a.customer_id, a.fecha_compromiso, ta.warehouse_code)
    assert {t.id for t in ts} >= {ta.id, tb.id}
    filas = pc.consolidado(ts)
    pt901 = [f for f in filas if f["producto"] == "PT-901"]
    assert sum(f["total"] for f in pt901) == pytest.approx(10)  # 6 + 4 de las dos OV, en una sola lista
    gente = [u.id for u in pk.staff(ta.warehouse_code)][:2]
    sup = U("superv.almacen")
    pc.asignar(sup, ts, gente)
    assert all(t.asignados == sorted(gente) for t in ts)
    with pytest.raises(BusinessError, match="foto"):
        pc.iniciar(sup, ts, "")
    pc.iniciar(sup, ts, "foto.jpg")
    assert all(t.estado == "EN_PROCESO" for t in ts)
    f = pt901[0]
    pc.validar_plan(U("lider.almacen"), ts)
    with pytest.raises(BusinessError, match="solo faltan"):
        pc.registrar(sup, ts, "PT-901", f["lote"], f["pendiente"] + 1)
    for f in pc.consolidado(ts):
        pc.registrar(sup, ts, f["producto"], f["lote"], f["pendiente"])
    s.commit()
    assert all(x["pendiente"] == 0 for x in pc.consolidado(ts))
    pc.finalizar(sup, ts, "lista.jpg")
    s.commit()
    assert all(t.estado == "LISTO" for t in ts)
    c = _cliente(app, "superv.almacen")
    html = c.get(f"/almacen/picking/cliente/{a.customer_id}/{a.fecha_compromiso.isoformat()}/{ta.warehouse_code}").get_data(as_text=True)
    assert "Lista para pickear (consolidada)" in html and a.numero in html and b.numero in html
    html = c.get(f"/almacen/picking?vista=semana&desde={date.today() - timedelta(days=3)}&hasta={date.today() + timedelta(days=10)}").get_data(as_text=True)
    assert "Un solo picking" in html and "/almacen/picking/cliente/" in html


def test_historial_desde_enero_2025_y_mismo_mes_del_anio_anterior(app, s, U):
    from app.models import SapMovement, SapOrderLine
    from app.services import demanda_v23 as dm
    from app.services import sap_v31
    from app.services.core import set_param
    from app.catalogs import PARAMS
    assert {k: v for k, v, *_ in PARAMS}["sap_historial_desde"] == "2025-01-01"
    hoy = date.today()
    hace_un_anio = hoy.replace(year=hoy.year - 1, day=min(hoy.day, 28))
    s.add(SapMovement(clave="GUIA:7001:0", tipo="GUIA", docentry=7001, documento="T001-1", fecha=hace_un_anio,
                      ov_numero="7700", product_code="PT-901", cantidad=100))
    s.add(SapOrderLine(docnum="7700", clase="VENTA", serie="OV", fecha=hace_un_anio, fecha_entrega=hace_un_anio,
                       cliente="Cliente Demo SAP", estado="CERRADA", product_code="PT-901", descripcion="x", cantidad=100,
                       entregado=100, linea_cerrada=True))
    s.commit()
    comp = dm.comparativo(f"{hoy:%Y-%m}")
    assert comp["anio_ant_kg"] > 0  # lo despachado el mismo mes del año anterior, según las guías de SAP
    set_param("sap_ordenes_ultimo", {"historial": True, "ts": "2026-11-14T10:00", "version": sap_v31.HISTORIAL_VERSION,
                                     "desde": "2025-01-01"})
    s.commit()
    html = _cliente(app, "jefe.logistica").get(f"/seguimiento/servicio?mes={hoy}").get_data(as_text=True)
    assert "Mismo periodo del año anterior" in html


def test_vistas_por_cliente_en_preparacion_y_ov_vs_guias(app, s, U, new_order):
    from app.services import sap_v31
    from .test_v33 import _SLServicio
    new_order([("PT-901", 2)])
    s.commit()
    html = _cliente(app, "lider.almacen").get("/ov/preparacion").get_data(as_text=True)
    assert "grupos-cliente" in html or "No hay pedidos listos" in html
    sap_v31.sync_historial(U("sistemas"), sl=_SLServicio())
    s.commit()
    c = _cliente(app, "jefe.logistica")
    html = c.get("/almacen/cargas/sap/despachos?clase=TODAS&sit=TODAS&vista=cliente").get_data(as_text=True)
    assert "Por cliente" in html and "Cliente Demo S" in html and "buscar=Cliente%20Demo%20S" in html
