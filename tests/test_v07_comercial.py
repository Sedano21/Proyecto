"""Observaciones al demo v0.6 – Comercial: canal de precios en la OV, ficha de cliente ampliada, comportamiento del
cliente, precios de mercado por origen e importación de informes."""
from datetime import date

import pytest

from app.models import Product
from app.services.core import BusinessError


def test_ficha_cliente_tres_celulares_y_correos_solo_comercial(s, U, cust):
    from app.services import customers
    c = cust()
    customers.save_customer(U("coord.ventas"), c, {"celulares": ["999111222", "988 777 666"],
                                                   "correos": ["a@demo.invalid", "b@demo.invalid", "c@demo.invalid"],
                                                   "tiene_contrato": "1", "certificaciones": "Certificado de calidad por lote",
                                                   "penalidades": "Fill rate < 95 %"})
    assert c.celulares == ["999111222", "988 777 666"] and c.correo == "a@demo.invalid" and c.tiene_contrato
    with pytest.raises(BusinessError, match="3 correos"):
        customers.save_customer(U("coord.ventas"), c, {"correos": ["a@x.pe", "b@x.pe", "c@x.pe", "d@x.pe"]})
    with pytest.raises(BusinessError, match="Comercial"):
        customers.save_customer(U("coord.almacen"), c, {"nombre": "X"})
    assert c in customers.search(grupo=c.grupo) if c.grupo else True


def test_canal_elegido_en_la_ov_define_el_minimo(s, U, new_order):
    from app.services import prices
    o = new_order([("PT-905", 1)], precio=999)
    canal_cliente = prices.channel_of(o.customer)
    otros = [c for c in prices.canales() if c != canal_cliente]
    if not otros:
        pytest.skip("la lista demo tiene un solo canal")
    o.canal_precio = otros[0]
    prices.check_order_prices(o)
    assert f"canal {otros[0]}" in o.lines[0].precio_origen or "Sin precio mínimo" in o.lines[0].precio_origen


def test_comportamiento_del_cliente(s, U, new_order):
    from app.services.customer_behavior import behavior
    o = new_order([("PT-905", 10)])
    d = behavior()
    fila = next(x for x in d["clientes"] if x["customer"].id == o.customer_id)
    assert fila["pedidos"] >= 1 and fila["cumplimiento"] is not None and "retrasos" in fila and "penalidad" in fila


def test_precios_de_mercado_por_origen(s, U):
    from app.services import market
    with pytest.raises(BusinessError, match="área responsable"):
        market.add(U("jefe.ventas"), "IMPORTACION", [{"producto": "LENTEJA", "precio_kg": 4, "fecha": date.today()}], "t")
    assert market.add(U("importaciones"), "IMPORTACION", [{"producto": "LENTEJA", "precio_kg": 4, "fecha": date.today()}], "t") == 1
    assert market.add(U("compras"), "COMPRA_NACIONAL", [{"producto": "LENTEJA", "precio_kg": 5, "fecha": date.today()}], "t") == 1
    d = market.analysis()
    f = next(x for x in d["compra"] if x["producto"] == "LENTEJA")
    assert f["conviene"] == "importar"


def test_informe_excel_extrae_solo_productos_compatibles(s, U, tmp_path):
    from openpyxl import Workbook
    from app.services import market
    p = s.get(Product, "PT-905")
    base = ((p.producto_base or p.descripcion).upper().split("*")[0]).strip()
    wb = Workbook()
    ws = wb.active
    ws.append(["Producto", "Precio"])
    ws.append([f"{base} 500 G MARCA COMPETIDOR", 6.5])
    ws.append(["TELEVISOR 50 PULGADAS", 1500])
    f = tmp_path / "informe.xlsx"
    wb.save(f)
    filas = market.parse_report(str(f), "informe.xlsx")
    assert len(filas) == 1 and filas[0]["categoria"] == "COMPETENCIA" and filas[0]["precio_kg"] == 13.0


def _pdf_simple(lineas):
    """PDF mínimo de una página con texto (sin dependencias)."""
    contenido = "BT /F1 10 Tf 40 800 Td 14 TL " + " ".join(f"({x}) Tj T*" for x in lineas) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(contenido)} >>\nstream\n{contenido}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{x:010d} 00000 n \n" for x in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return out.encode("latin-1")


def test_informe_pdf_extrae_productos_compatibles(s, tmp_path):
    from app.services import market
    p = s.get(Product, "PT-905")
    base = ((p.producto_base or p.descripcion).upper().split("*")[0]).strip()
    f = tmp_path / "informe.pdf"
    f.write_bytes(_pdf_simple([f"{base} 1 KG S/ 7.20", "CEMENTO 42 KG 30.00"]))
    filas = market.parse_report(str(f), "informe.pdf")
    assert len(filas) == 1 and filas[0]["precio_kg"] == 7.2
