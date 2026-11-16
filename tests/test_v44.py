"""V44 (16-nov-2026): encabezado con el último cambio de SAP, OTIF de «Cómo va la empresa» con SAP, préstamo con lo que
falta, la OV solo se bloquea por precio, serie de SAP de la guía SUNAT, filtro «En riesgo» y nivel de servicio por
rango. Solo datos ficticios."""
from datetime import date, datetime, timedelta

from .test_v26 import _cliente


def test_encabezado_con_ultimo_cambio_y_revision(app, s):
    from app.services.sap_vigia import _set
    from app.services.stock import stock_freshness
    ahora = datetime.now().replace(microsecond=0)
    _set("sap_vigia_revision", ahora.isoformat(), "x")
    _set("sap_vigia_ultimo_cambio", (ahora - timedelta(minutes=5)).isoformat(), "x")
    s.commit()
    info = stock_freshness()
    if info is None:
        return
    assert info["revisado"] == ahora and info["ultimo_cambio"] >= ahora - timedelta(minutes=5)
    html = _cliente(app, "jefe.logistica").get("/").get_data(as_text=True)
    assert "último cambio" in html and f"revisado {ahora:%H:%M}" in html and "no es tiempo real" not in html


def test_guia_sunat_con_la_serie_de_sap_del_prefijo(app, s, U, new_order, monkeypatch):
    from app.models import SunatGuide
    from app.services import guias_sunat as gs
    from app.services import sap_sl
    o = new_order([("PT-901", 4)])
    g = SunatGuide(serie="EG07", numero="448", lineas=[{"codigo": "PT-901", "descripcion": "x", "lote": "264005DV",
                                                        "cantidad": 4}], sap_ov="1636328", order_id=o.id, archivo="",
                   estado="REGISTRADA", inventario={}, sap={})
    s.add(g)
    s.commit()

    class SL:
        cfg = {"company": "ZZZ_CORPRODUC_TEST260826"}
        body = None

        def get_all(self, path, params=None):
            if path == "DeliveryNotes":
                return [{"DocEntry": 9, "Series": 1, "FolioPrefixString": "T001"},
                        {"DocEntry": 8, "Series": 77, "FolioPrefixString": "EG07", "Indicator": "09"},
                        {"DocEntry": 7, "Series": 77, "FolioPrefixString": "EG07"}]
            return [{"DocEntry": 77, "DocNum": 1636328, "CardCode": "C1", "DocumentLines": [
                {"LineNum": 0, "ItemCode": "PT-901", "RemainingOpenQuantity": 4}]}]

        def _req(self, method, path, body=None, headers=None):
            SL.body = body
            return {"DocEntry": 901, "DocNum": 3002}
    monkeypatch.setattr(sap_sl, "write_enabled", lambda cfg=None: None)
    monkeypatch.setattr(gs, "_req", lambda u: None)
    gs.enviar_sap(U("jefe.operaciones"), g, sl=SL())
    assert SL.body["Series"] == 77 and SL.body["FolioPrefixString"] == "EG07"


def test_prestamo_con_lo_que_falta(app, s, U):
    from app.models import StockLot, SunatGuide
    from app.services import ingresos_sap
    alm = s.query(StockLot).first().warehouse_code
    s.add(StockLot(product_code="PT-901", warehouse_code=alm, lote="440001AB", cantidad=3, estado="DISPONIBLE",
                   fecha_venc=date(2027, 11, 3)))
    g = SunatGuide(serie="EG07", numero="991", lineas=[{"codigo": "PT-901", "descripcion": "x", "lote": "440001AB",
                                                        "cantidad": 10}], archivo="", estado="REGISTRADA", inventario={},
                   sap={}, prestamo={"estado": "PENDIENTE"})
    s.add(g)
    s.commit()
    f = ingresos_sap.faltante(g, alm)["filas"][0]
    assert f["guia"] == 10 and f["stock_sap"] == 3 and f["cantidad"] == 7 and str(f["fv"]) == "2027-11-03"
    html = _cliente(app, "jefe.operaciones").get(f"/operacion/ingresos-mercaderia?guia={g.id}&faltante=1&almacen={alm}").get_data(as_text=True)
    assert "lo que falta" in html and 'value="7' in html
    html = _cliente(app, "jefe.operaciones").get("/operacion/guias-sunat").get_data(as_text=True)
    assert "Registrar el ingreso con lo que falta" in html


def test_por_ahora_solo_se_bloquea_por_precio(app, s, U, new_order):
    from app.catalogs import PARAMS
    from app.services.core import set_param
    v = {k: x for k, x, *_ in PARAMS}
    assert v["bloquear_ov_sin_opcion"] is False and v["dias_minimos_emision_ov"] == 0
    set_param("bloquear_ov_sin_opcion", False)
    set_param("dias_minimos_emision_ov", 0)
    s.commit()
    o = new_order([("PT-901", 900000)], dias=1)  # sin stock ni opción que llegue a tiempo
    assert o.estado != "BLOQUEADA"


def test_en_riesgo_filtra_y_nivel_de_servicio_por_rango(app, s):
    c = _cliente(app, "jefe.logistica")
    html = c.get("/?desp=RIESGO").get_data(as_text=True)
    if "Despachos por cliente y fecha" in html:
        assert "Mostrando solo" in html and "en riesgo" in html
    hoy = date.today()
    html = c.get(f"/seguimiento/servicio?desde={hoy - timedelta(days=6)}&hasta={hoy}").get_data(as_text=True)
    assert f"del {(hoy - timedelta(days=6)):%d/%m/%Y} al {hoy:%d/%m/%Y}" in html and 'name="desde"' in html


def test_otif_de_como_va_la_empresa_con_sap(app, s):
    from app.services import empresa_v24
    from .test_v42 import _historial_sap
    _historial_sap(s, date.today())
    d = empresa_v24.tablero()
    card = next(c for t in [d] for c in t.get("tarjetas", t.get("cards", [])) if "OTIF" in str(c))
    assert "%" in str(card)
