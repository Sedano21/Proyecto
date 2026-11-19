"""V59 (19-nov-2026): abastecimiento: quiebre del stock con las OV por fecha y lo pendiente de ingresar en SAP, origen
sugerido (nacional o importado) y lo registrado en SAP como ingreso; Importación ve la proyección de demanda.
Solo datos ficticios."""
from datetime import date, timedelta

from .test_v26 import _cliente


def _oc(s, de, code, q, recibido, total, fecha, entrega, pais, tipo="OC", estado="ABIERTA", prov="PROVEEDOR PRUEBA"):
    from app.models import SapPurchaseLine
    s.add(SapPurchaseLine(clave=f"{'R:' if tipo == 'RECEPCION' else ''}{de}:0", docentry=de, docnum=str(9000 + de), tipo=tipo,
                          fecha=fecha, fecha_entrega=entrega, cardcode=f"P{de}", proveedor=prov, estado=estado, moneda="S/",
                          product_code=code, descripcion="Granel prueba", cantidad=q, recibido=recibido, total=total, igv=0,
                          pais=pais))


def test_quiebre_con_ov_por_fecha_y_oc_por_ingresar(app, s, U, new_order):
    from app.models import Product
    from app.services import abastecimiento as ab
    hoy = date.today()
    p = s.get(Product, "GR-901")
    p.stock_minimo = 0
    s.commit()
    libre = ab._libre("GR-901")
    # una OV que en 5 días se lleva todo lo libre más 10
    o = new_order([("GR-901", libre + 10)], dias=5)
    s.commit()
    r = ab.proyeccion(p, hoy, horizonte=30, ov=ab._ov_por_fecha(hoy).get("GR-901", []), pend=[])
    falta = r["ov_total"]
    assert r["quiebre"] is not None and r["quiebre"] <= hoy + timedelta(days=5)
    assert any(num == o.numero for num, _ in r["ov_quiebre"]) and r["sugerido"] > 0
    # con una OC de SAP que ingresa antes, ya no se quiebra en esa fecha
    pend = [{"docnum": "1", "proveedor": "x", "origen": "NACIONAL", "pais": "PE", "pendiente": falta + 50, "cantidad": falta + 50,
             "recibido": 0, "fecha": hoy, "entrega": hoy + timedelta(days=2), "descripcion": "", "vencida": False}]
    r2 = ab.proyeccion(p, hoy, horizonte=5, ov=ab._ov_por_fecha(hoy).get("GR-901", []), pend=pend)
    assert r2["por_ingresar"] == falta + 50 and (r2["quiebre"] is None or r2["quiebre"] > hoy + timedelta(days=5))


def test_origen_sugerido_por_plazo_y_costo(app, s, U):
    from app.models import Product
    from app.services import abastecimiento as ab
    hoy = date.today()
    _oc(s, 1, "GR-901", 100, 100, 500.0, hoy - timedelta(days=60), hoy - timedelta(days=55), "PE", estado="CERRADA")   # nacional: 5 días, S/ 5
    _oc(s, 2, "GR-901", 100, 100, 300.0, hoy - timedelta(days=90), hoy - timedelta(days=45), "CN", estado="CERRADA")   # importado: 45 días, S/ 3
    s.commit()
    p = s.get(Product, "GR-901")
    h = ab.historial(["GR-901"], hoy)["GR-901"]
    assert h["NACIONAL"]["plazo_dias"] == 5 and h["IMPORTADO"]["costo_unit"] == 3.0
    assert ab.recomendar(p, h, 10)[0] == "NACIONAL"     # solo lo nacional llega antes del quiebre
    assert ab.recomendar(p, h, 60)[0] == "IMPORTADO"    # llegan los dos: el más barato
    mp = s.get(Product, "MP-902")
    assert ab.recomendar(mp, h, 60) == ("NACIONAL", "Materia prima: la compra solo Compras nacionales.")


def test_pestanas_por_ingresar_e_ingresado(app, s, U):
    hoy = date.today()
    _oc(s, 3, "GR-901", 100, 40, 500.0, hoy, hoy + timedelta(days=3), "PE")
    _oc(s, 4, "GR-901", 80, 80, 400.0, hoy, hoy, "CN", tipo="RECEPCION", estado="CERRADA", prov="PROVEEDOR EXTERIOR")
    s.commit()
    c = _cliente(app, "compras")
    html = c.get("/gestion/abastecimiento?ver=pendientes").get_data(as_text=True)
    assert "9003" in html and "60" in html  # 100 pedidos − 40 recibidos
    html = c.get("/gestion/abastecimiento?ver=ingresados&origen=").get_data(as_text=True)
    assert "9004" in html and "PROVEEDOR EXTERIOR" in html
    html = c.get("/gestion/abastecimiento?ver=ingresados").get_data(as_text=True)  # Compras ve lo nacional por defecto
    assert "PROVEEDOR EXTERIOR" not in html
    assert c.get("/gestion/abastecimiento").status_code == 200


def test_importacion_ve_la_proyeccion_de_demanda(app, s, U):
    from app.services.core import has_perm
    for u in ("importaciones", "compras"):
        assert has_perm(U(u), "demanda.ver"), u
