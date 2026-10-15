"""Respuestas del usuario del 15-oct-2026: cumplimiento = entregado completo, orden de opciones ante faltante, bultos en
el picking, productos sustitutos (individual o Excel) y alerta de variación de compra por canal o cliente."""
from types import SimpleNamespace

import pytest

from app.models import Param, Product
from app.services.core import BusinessError

from .conftest import alerts_of


def test_cumplimiento_cuenta_solo_entregados_completos(s, U, new_order):
    from app.services.customer_behavior import behavior
    o = new_order([("PT-905", 10)])
    o.estado = "ENTREGADA"
    o.lines[0].entregado = 6  # entrega parcial: no cuenta como cumplida
    s.flush()
    fila = behavior(customer_id=o.customer_id)["clientes"][0]
    ov = next(f for f in fila["detalle"] if f["o"].id == o.id)
    assert ov["atendido"] and not ov["completo"]
    o.lines[0].entregado = 10
    s.flush()
    fila = behavior(customer_id=o.customer_id)["clientes"][0]
    assert next(f for f in fila["detalle"] if f["o"].id == o.id)["completo"]
    assert fila["cumplimiento"] == round(100.0 * fila["completos"] / fila["pedidos"], 1)


def test_opciones_ante_faltante_en_orden_produccion_reempaque_traslado_compra(s, U, new_order):
    from app.services.customer_conditions import action_options
    o = new_order([("PT-905", 10)])
    ops = action_options(o, o.lines[0], 10, [(SimpleNamespace(cantidad=4), "vencimiento")])
    assert ops[-1] == "Compra"
    assert any(x.startswith("Reempaque") and "cubre 4" in x for x in ops)
    clave = {"Producir": 0, "Reempaque": 1, "Traslado": 2, "Compra": 3}
    pos = [next(v for k, v in clave.items() if x.startswith(k)) for x in ops]
    assert pos == sorted(pos)
    assert not any(x.startswith("Reempaque") for x in action_options(o, o.lines[0], 10, []))


def test_bultos_segun_unidades_por_bulto(s):
    from app.services.picking import bultos_de
    p = s.get(Product, "PT-905")
    assert bultos_de(p, 228) is None  # sin unidades por bulto configuradas
    p.unidades_por_bulto = 12
    assert bultos_de(p, 228) == 19


def test_sustitutos_individual_y_excel(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import market
    p = s.get(Product, "PT-905")
    base = ((p.producto_base or p.descripcion).upper().split("*")[0]).strip()
    with pytest.raises(BusinessError, match="Comercial"):
        market.add_substitute(U("aux.almacen"), base, "GARBANZO")
    with pytest.raises(BusinessError, match="no es un producto base"):
        market.add_substitute(U("jefe.ventas"), "TELEVISOR", "RADIO")
    x, nuevo = market.add_substitute(U("jefe.ventas"), base.lower(), "  arveja   partida ")
    assert nuevo and x.sustituto == "ARVEJA PARTIDA" and x.producto_base == base
    s.flush()
    assert market.classify("ARVEJA PARTIDA 1 KG MARCA X")[0] == "SUSTITUTO"
    market.remove_substitute(U("jefe.ventas"), x)
    s.flush()
    assert market.classify("ARVEJA PARTIDA 1 KG MARCA X")[0] is None
    wb = Workbook()
    ws = wb.active
    ws.append(["Producto base", "Sustituto", "Observación"])
    ws.append([base, "ARVEJA PARTIDA", "reactivado"])
    ws.append([base, "PALLAR", ""])
    ws.append(["NO EXISTE", "OTRO", ""])
    f = tmp_path / "sustitutos.xlsx"
    wb.save(f)
    n, errores = market.import_substitutes(U("jefe.ventas"), str(f), "sustitutos.xlsx")
    assert n == 1 and len(errores) == 1 and "Fila 4" in errores[0]
    s.flush()
    assert x.activo and market.classify("PALLAR GRANDE 500 G")[0] == "SUSTITUTO"
    bad = tmp_path / "malo.xlsx"
    bad.write_bytes(b"no es excel")
    with pytest.raises(BusinessError, match="No se pudo leer"):
        market.import_substitutes(U("jefe.ventas"), str(bad), "malo.xlsx")


def test_regla_de_variacion_cliente_sobre_canal_sobre_general(s, U, cust):
    from app.services import customer_behavior as cb
    c = cust()
    c.canal_precio = "MAYORISTA"
    s.flush()
    general = cb.rule_for(c)
    assert general["origen"] == "General" and general["umbral"] == s.get(Param, "variacion_compra_alerta_pct").valor["v"]
    with pytest.raises(BusinessError, match="Configuración"):
        cb.save_variation_rule(U("jefe.ventas"), "CANAL", "MAYORISTA", umbral_pct=10)
    cb.save_variation_rule(U("sistemas"), "CANAL", "mayorista", umbral_pct=10, dias=60)
    s.flush()
    r = cb.rule_for(c)
    assert (r["umbral"], r["dias"], r["origen"]) == (10, 60, "Canal MAYORISTA")
    cb.save_variation_rule(U("sistemas"), "CLIENTE", customer_id=c.id, umbral_pct=50)  # periodo vacío: hereda del canal
    s.flush()
    r = cb.rule_for(c)
    assert (r["umbral"], r["dias"], r["origen"]) == (50, 60, "Cliente")
    otro = cust("20000000002")
    assert cb.rule_for(otro)["origen"] in ("General", f"Canal {(otro.canal_precio or '').upper()}")
    with pytest.raises(BusinessError, match="7 días"):
        cb.save_variation_rule(U("sistemas"), "CANAL", "MAYORISTA", dias=3)


def test_regla_de_cliente_puede_desactivar_la_alerta(s, U, cust, new_order):
    from app.services import customer_behavior as cb
    from app.models import SalesOrder
    from datetime import date, timedelta
    o1 = new_order([("PT-905", 10)])
    o2 = new_order([("PT-905", 100)])
    o1.fecha_emision = date.today() - timedelta(days=80)
    o2.fecha_emision = date.today()
    s.flush()
    cb.save_variation_rule(U("sistemas"), "CLIENTE", customer_id=o1.customer_id, alerta=False)
    s.flush()
    assert cb.check_purchase_variations() == 0 or not alerts_of(s, "CLIENTE_VARIACION_COMPRA", o1.customer_id)
    r = s.query(cb.PurchaseVariationRule).filter_by(customer_id=o1.customer_id).one()
    cb.remove_variation_rule(U("sistemas"), r)
    s.flush()
    cb.check_purchase_variations()
    s.flush()
    assert alerts_of(s, "CLIENTE_VARIACION_COMPRA", o1.customer_id)
    assert s.query(SalesOrder).count() >= 2
