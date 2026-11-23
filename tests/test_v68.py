"""V68 (23-nov-2026): en el stock sin rotación se ve en qué almacén está cada producto y cuánto hay en cada uno.
Datos ficticios."""
from datetime import date, timedelta

from app.models import StockLot

from .test_v64 import _cliente


def test_sin_rotacion_desglosa_por_almacen(app, s):
    from app.services import supply
    d = supply.rotation_ranking(top=10000)
    filas = d["por_tiempo"] + d["por_cantidad"]
    assert filas
    for x in filas:
        lotes = s.query(StockLot).filter(StockLot.product_code == x["code"], StockLot.cantidad > 0).all()
        esperado = {}
        for l in lotes:
            esperado[l.warehouse_code] = esperado.get(l.warehouse_code, 0) + l.cantidad
        assert {a["almacen"]: a["cantidad"] for a in x["por_almacen"]} == {k: round(v, 2) for k, v in esperado.items()}
        assert sum(a["cantidad"] for a in x["por_almacen"]) == round(sum(esperado.values()), 2) or not esperado
    html = _cliente(app, "jefe.ventas").get("/suministro/rotacion").get_data(as_text=True)
    assert "Por almacén" in html or not any(x["por_almacen"] for x in filas)
