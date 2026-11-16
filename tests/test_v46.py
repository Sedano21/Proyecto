"""V46 (16-nov-2026): recetas de SAP que sí se aplican (componentes repetidos, almacén de la receta y filas con datos
no aceptados excluidas) y guía SUNAT editable al subirla. Solo datos ficticios."""
from datetime import date

import pytest

from .test_v26 import _cliente


class _SLBom:
    cfg = {"user": "integracion"}

    def get_all(self, path, params=None):
        return [{"TreeCode": "PT-901", "TreeType": "iProductionTree", "Quantity": 1, "Warehouse": "ALM-001",
                 "ProductTreeLines": [{"ItemCode": "MP-901", "Quantity": 3, "IssueMethod": "im_Manual"},  # sin almacén
                                      {"ItemCode": "MP-901", "Quantity": 2.2, "Warehouse": "ALM-002"},  # repetido
                                      {"ItemCode": "EN-901", "Quantity": 0, "Warehouse": "ALM-002"}]},  # cantidad 0
                {"TreeCode": "PT-902", "Quantity": 1, "Warehouse": "ALM-001",
                 "ProductTreeLines": [{"ItemCode": "MP-902", "Quantity": 4, "Warehouse": "ALM-002"}]}]


def test_recetas_de_sap_se_aplican_aunque_alguna_fila_no_pase(app, s, U, tmp_path):
    from app.models import BOMLine
    from app.services import sap_sl
    filas = sap_sl.rows_bom(_SLBom())
    mp = [f for f in filas if f["Articulo Padre"] == "PT-901" and f["Articulo Componente"] == "MP-901"]
    assert len(mp) == 1 and mp[0]["Cantidad Componente"] == pytest.approx(5.2) and mp[0]["Almacen Componente"]
    b = sap_sl.sync("BOM", U("jefe.produccion"), str(tmp_path), sl=_SLBom(), autoconfirmar=True)
    s.commit()
    assert b.estado == "CONFIRMADO"
    excl = [r for r in b.rows if r.excluida]
    assert len(excl) == 1 and "Excluida al traer de SAP" in excl[0].motivo_exclusion
    assert {(l.padre, l.componente) for l in s.query(BOMLine)} >= {("PT-901", "MP-901"), ("PT-902", "MP-902")}
    html = _cliente(app, "jefe.produccion").get("/produccion/bom").get_data(as_text=True)
    assert "Última lectura de recetas de SAP" in html and "excluida" in html


def _guia(s, **kw):
    from app.models import SunatGuide
    g = SunatGuide(serie="EG07", numero=kw.get("numero", "460"), lineas=[{"codigo": "PT-901", "descripcion": "x",
                                                                         "lote": "251026VG", "fp": "2026-10-25",
                                                                         "fv": "2027-10-25", "cantidad": 560, "um": "UND"}],
                   archivo="", estado="REGISTRADA", inventario=kw.get("inventario", {}), sap=kw.get("sap", {}))
    s.add(g)
    s.commit()
    return g


def test_editar_la_guia_sunat_al_subirla(app, s, U):
    from werkzeug.datastructures import MultiDict
    from app.services import guias_sunat as gs
    from app.services.core import BusinessError
    g = _guia(s)
    u = U("asist.distribucion")
    datos = MultiDict([("codigo", "PT-901"), ("descripcion", "x"), ("lote", "251026VG"), ("fp", "2026-10-25"),
                       ("fv", "2027-10-25"), ("cantidad", "540"), ("um", "UND"), ("placa", "abc123"),
                       ("observacion", "Salió menos: 20 unidades se quedaron (ficticio)")])
    with pytest.raises(BusinessError, match="motivo"):
        gs.editar(u, g, datos)
    datos.add("motivo", "salió menos")
    gs.editar(u, g, datos)
    s.commit()
    assert g.lineas[0]["cantidad"] == 540 and g.placa == "ABC123" and "Salió menos" in g.observacion
    assert g.ediciones[0]["antes"]["lineas"][0]["cantidad"] == 560 and g.ediciones[0]["lineas_cambiadas"]
    # solo la observación: no pide motivo
    gs.editar(u, g, MultiDict([("codigo", "PT-901"), ("lote", "251026VG"), ("fp", "2026-10-25"), ("fv", "2027-10-25"),
                               ("cantidad", "540"), ("observacion", "Cliente recibió conforme")]))
    assert len(g.ediciones) == 2 and not g.ediciones[1]["lineas_cambiadas"]
    html = _cliente(app, "asist.distribucion").get("/operacion/guias-sunat").get_data(as_text=True)
    assert "Editar la guía" in html and "Historial de cambios (2)" in html and "Cliente recibió conforme" in html
    en_sap = _guia(s, numero="461", sap={"estado": "OK"})
    with pytest.raises(BusinessError, match="registrada en SAP"):
        gs.editar(u, en_sap, datos)
    desc = _guia(s, numero="462", inventario={"decision": "DESCONTADO"})
    with pytest.raises(BusinessError, match="decisión de inventario"):
        gs.editar(u, desc, datos)


def test_cambiar_la_ov_de_la_guia_antes_de_enviarla(app, s, U, new_order):
    from app.services import guias_sunat as gs
    from app.services.core import BusinessError
    vieja = new_order([("PT-901", 10)])
    nueva = new_order([("PT-901", 10)])
    g = _guia(s, numero="470")
    u = U("asist.distribucion")
    gs.unir(u, g, vieja.id)
    s.commit()
    assert g.order_id == vieja.id and not g.ediciones
    with pytest.raises(BusinessError, match="por qué"):
        gs.unir(u, g, nueva.id)
    gs.unir(u, g, nueva.id, motivo="se cerró la OV y se creó otra (ficticio)")
    s.commit()
    assert g.order_id == nueva.id and g.ediciones[-1]["cambio_ov"] and g.ediciones[-1]["antes"]["ov"] == vieja.numero
    gs.unir(u, g, None, "1636999", motivo="OV nueva solo en SAP")
    assert g.order_id is None and g.sap_ov == "1636999"
    html = _cliente(app, "asist.distribucion").get("/operacion/guias-sunat").get_data(as_text=True)
    assert "Cambiar la OV" in html and "cambió la OV" in html
    g.sap = {"estado": "OK"}
    with pytest.raises(BusinessError, match="registrada en SAP"):
        gs.unir(u, g, nueva.id, motivo="x")
    g.sap = {}
    g.inventario = {"decision": "DESCONTADO"}
    with pytest.raises(BusinessError, match="decisión de inventario"):
        gs.unir(u, g, nueva.id, motivo="x")
