"""V60 (19-nov-2026): plan de abastecimiento por grano (método del Excel Maestro), Compras no compra PT/MQ (ni MP salvo
harinas y quinua) y carga de la proyección de Comercial tal cual. Solo datos ficticios."""
import math
from datetime import date, timedelta

import pytest

from .test_v26 import _cliente


def _guia(s, de, code, kg, fecha, cliente, linea=0):
    from app.models import SapMovement
    s.add(SapMovement(clave=f"GUIA:{de}:{linea}", tipo="GUIA", docentry=de, documento=f"EG07-{de}", fecha=fecha,
                      ov_numero="", cliente=cliente, product_code=code, cantidad=kg, total=kg * 5, igv=0))


def test_grano_por_descripcion(app, s):
    from app.services import plan_granos as pg
    cfg = pg.granos_config()
    assert pg.grano_de("FRIJOL CANARIO CAMANEJO * 500 G - MARCA", cfg) == "FRIJOL CANARIO"
    assert pg.grano_de("MAIZ POP CORN * GRANEL - PRUEBA", cfg) == "MAIZ POP CORN"
    assert pg.grano_de("POP CORN ROJO", cfg) == "MAIZ POP CORN"
    assert pg.grano_de("HARINA DE QUINUA", cfg) == "QUINUA"       # el nombre más largo gana
    assert pg.grano_de("HARINA 7 SEMILLAS", cfg) == "HARINAS"
    assert pg.grano_de("ARROZ EXTRA * 50 KG", cfg) == "OTROS"


@pytest.fixture
def canario(s):
    """GR-901 pasa a ser un granel de canario (importado) con 6 meses de guías de dos clientes."""
    from app.models import Product
    p = s.get(Product, "GR-901")
    p.descripcion = "FRIJOL CANARIO * GRANEL - PRUEBA"
    hoy = date.today()
    ini = hoy.replace(day=1)
    de = 100
    for i in range(1, 7):  # 6 meses completos: 10 t/mes de un cliente activo y 2 t/mes de otro
        mes = (ini - timedelta(days=1)).replace(day=1) if i == 1 else None
        f = ini
        for _ in range(i):
            f = (f - timedelta(days=1)).replace(day=1)
        _guia(s, de, "GR-901", 10000, f + timedelta(days=4), "CLIENTE ACTIVO SAC"); de += 1
        _guia(s, de, "GR-901", 2000, f + timedelta(days=9), "CLIENTE CHICO SAC"); de += 1
    s.commit()
    return p


def test_plan_por_grano_formulas(app, s, U, canario):
    from app.services import plan_granos as pg
    r = pg.calcular()["FRIJOL CANARIO"]
    assert r["origen"] == "IMPORTADO" and r["responsable"] == "Coordinador de Importación"
    assert abs(r["p6"] - 12000) < 1 and r["base_elegida"] == "Prom. 6m"
    assert r["factor_mp"] == 1.0  # todo se vendió a granel
    assert r["lead_time"] == 50 and r["revision"] == 30 and r["horizonte"] == 80
    # SS = z × min(σ, base) × √(LT/30) × factor MP
    assert abs(r["ss"] - r["z"] * min(r["sigma"], r["base"]) * math.sqrt(50 / 30)) < 1e-6
    # compra = demanda del horizonte × factor MP + SS − stock − en camino
    assert abs(r["compra"] - max(0, r["demanda_horizonte"] + r["ss"] - r["stock"] - r["camino"])) < 1e-6
    act = next(c for c in r["clientes"] if c["cliente"] == "CLIENTE ACTIVO SAC")
    assert act["estado"] in ("Activo", "Atrasado") and abs(act["recompra"] - 10000 * 80 / 30) < 1
    if r["compra"] > 0:
        assert r["fcl"] == math.ceil(r["compra"] / 22680) and r["a_pedir"] == r["fcl"] * 22680
        assert r["clasificacion"] in ("IMPORTACIÓN INMEDIATA", "PROGRAMAR IMPORTACIÓN", "REQUIERE VALIDACIÓN")
    # con la recompra habitual (plan) se agota antes o igual que solo con OV
    assert r["agota"]["D"] is not None


def test_simulacion_de_agotamiento():
    from app.services.plan_granos import _sim
    hoy = date(2026, 11, 19)
    llegadas = {hoy + timedelta(days=10): 500.0}
    ov = {hoy + timedelta(days=2): 800.0}
    assert _sim(hoy, 1000, llegadas, ov, 0.0, "ov", 30) == (None, None)
    d, _ = _sim(hoy, 1000, llegadas, ov, 100.0, "suma", 30)   # 1000 − 800 − 100/día: se agota al tercer día
    assert d == hoy + timedelta(days=2)
    d, _ = _sim(hoy, 1000, {}, ov, 50.0, "max", 30)           # max(800, 50 d) llega a 1000 el día 20
    assert d == hoy + timedelta(days=20)


def test_pantallas_plan_y_detalle(app, s, U, canario):
    c = _cliente(app, "importaciones")
    html = c.get("/gestion/abastecimiento").get_data(as_text=True)   # Importación ve lo importado por defecto
    assert "FRIJOL CANARIO" in html and "Plan por grano" in html
    html = c.get("/gestion/abastecimiento?g=FRIJOL%20CANARIO").get_data(as_text=True)
    html = c.get("/gestion/abastecimiento/grano?g=FRIJOL CANARIO").get_data(as_text=True)
    assert "Cálculo de la compra" in html and "CLIENTE ACTIVO SAC" in html
    html = _cliente(app, "compras").get("/gestion/abastecimiento").get_data(as_text=True)  # Compras: lo nacional
    assert "FRIJOL CANARIO</b>" not in html


def test_compras_no_compra_pt_mq_ni_mp_salvo_harinas_y_quinua(app, s, U, new_order):
    from app.models import Product, PurchaseRequest
    from app.services import purchasing
    from app.services.core import BusinessError, set_param
    set_param("compras_no_comprables", ["PT", "MQ", "MP"])  # el valor de producción (las pruebas antiguas usan [])
    s.commit()
    assert purchasing.es_no_comprable(s.get(Product, "PT-901"))
    mp = s.get(Product, "MP-902")
    mp.descripcion = "LENTEJA SELECCIONADA"
    assert purchasing.es_no_comprable(mp)
    mp.descripcion = "HARINA DE QUINUA"
    assert not purchasing.es_no_comprable(mp)
    assert not purchasing.es_no_comprable(s.get(Product, "GR-901"))
    with pytest.raises(BusinessError):
        purchasing.create_request(U("coord.almacen"), "PT-901", 5)
    # una solicitud vieja de PT (de antes de la regla) se cancela sola al abrir Compras
    r = PurchaseRequest(product_code="PT-901", cantidad=5, estado="PENDIENTE_LOGISTICA", origen="OV")
    s.add(r)
    s.commit()
    html = _cliente(app, "compras").get("/abastecimiento/compras").get_data(as_text=True)
    s.expire_all()
    assert s.get(PurchaseRequest, r.id).estado == "CANCELADA" and f">{r.id}<" not in html.replace("#", "")


def test_proyeccion_de_comercial_tal_cual(app, s, U, tmp_path):
    from openpyxl import Workbook
    from app.models import DemandForecast, Product
    from app.services import supply
    wb = Workbook()
    ws = wb.active
    ws.title = "IMPORTADO"
    ws.append(["N°", "CODIGO DE PRODUCTO", "DESCRIPCION DE PRODUCTO", "UM", "TIPO DE DEMANDA", "CANTIDAD PROYECTADA"])
    ws.append([1, "GR-901", "GRANEL PRUEBA", "KG", "ED", 1500])
    ws2 = wb.create_sheet("NACIONAL")
    ws2.append(["N°", "CODIGO DE PRODUCTO", "DESCRIPCION DE PRODUCTO", "UM", "TIPO DE DEMANDA", "CANTIDAD PROYECTADA"])
    ws2.append([1, "PT-901", "PT PRUEBA", "KG", "ED", 100])
    ws3 = wb.create_sheet("PROY NOV 26")
    ws3["B2"] = "PROYECTADO NOVIEMBRE 26 - TOTAL"
    path = tmp_path / "proy.xlsx"
    wb.save(path)
    n, errores = supply.import_forecast(U("coord.ventas"), str(path))
    s.commit()
    assert n == 2 and not errores
    gr = s.query(DemandForecast).filter_by(mes="2026-11", product_code="GR-901").one()
    assert gr.cantidad == 1500
    pt = s.query(DemandForecast).filter_by(mes="2026-11", product_code="PT-901").one()
    peso = s.get(Product, "PT-901").peso_kg
    assert pt.cantidad == (round(100 / peso, 4) if peso else 100)
