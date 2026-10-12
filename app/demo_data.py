"""Generación de archivos Excel FICTICIOS con los mismos encabezados que los formatos reales.

Ningún dato aquí proviene de clientes, conductores, placas o lotes reales: códigos 9xx, marca 'DEMO',
RUC 2000000000x. Las fechas se calculan respecto al día de generación para que los casos de prueba
(vencimientos, retrasos) sean reproducibles.
"""
import os
from datetime import date, timedelta

import openpyxl

PRODUCTS = [
    # code, descripcion, ppb, maq, tipo, calidad, categoria_reposicion
    ("PT-901", "ARVEJA VERDE PARTIDA * 500 G - MARCA DEMO", 0.5, "E2000", "PT", "EXTRA", ""),
    ("PT-902", "ARVEJA VERDE PARTIDA * 5 KG - MARCA DEMO", 5, "E1000", "PT", "EXTRA", ""),
    ("PT-903", "LENTEJA * 500 G - MARCA DEMO", 0.5, "E2000", "PT", "EXTRA", ""),
    ("PT-904", "FRIJOL CANARIO * 5 KG - MARCA DEMO", 5, "E1000", "PT", "SUPERIOR", ""),
    ("PT-905", "QUINUA * 250 G - MARCA DEMO", 0.25, "E2000", "PT", "SUPERIOR", ""),
    ("PT-906", "ARVEJA VERDE PARTIDA * 500 G - MARCA DEMO ECONOMICA", 0.5, "E2000", "PT", "SUPERIOR", ""),
    ("MP-901", "ARVEJA VERDE PARTIDA", 1, "T1000", "MP", "EXTRA", "GR y MP"),
    ("MP-902", "LENTEJA", 1, "T1000", "MP", "EXTRA", "GR y MP"),
    ("MP-903", "FRIJOL CANARIO", 1, "T1000", "MP", "SUPERIOR", "GR y MP"),
    ("GR-901", "QUINUA * GRANEL - DEMO", 1, "T1000", "GR", "SUPERIOR", "GR y MP"),
]
INSUMOS = [
    ("EN-901", "LAMINA DEMO - 500 G", "Bobinas"),
    ("EN-902", "LAMINA DEMO - 5 KG", "Bobinas"),
    ("EN-903", "SOBREEMPAQUE DEMO", "Film"),
    ("EN-904", "SACO LAMINADO DEMO 50 KG", "Sacos sin estampado"),
    ("SU-901", "ETIQUETA ADHESIVA DEMO", "Etiquetas adhesivas"),
    ("RE-901", "MANO DE OBRA / PROCESO DEMO", ""),
    ("RE-902", "COSTO CIF / LINEA DEMO", ""),
]

BOM = [
    # padre, componente, cantidad, almacen componente, orden
    ("PT-901", "MP-901", 0.5, "EXT-002", None), ("PT-901", "EN-901", 0.005, "EXT-002", 1),
    ("PT-901", "EN-903", 0.0018, "EXT-002", 2), ("PT-901", "RE-901", 0.000625, "ALM-001", 3),
    ("PT-901", "RE-902", 1, "ALM-001", 4),
    ("PT-902", "MP-901", 5, "EXT-002", None), ("PT-902", "EN-902", 0.05, "EXT-002", 1),
    ("PT-902", "SU-901", 1, "EXT-002", 2), ("PT-902", "RE-901", 0.0015, "ALM-001", 3),
    ("PT-903", "MP-902", 0.5, "EXT-002", None), ("PT-903", "EN-901", 0.005, "EXT-002", 1),
    ("PT-903", "RE-901", 0.000625, "ALM-001", 2),
    ("PT-904", "MP-903", 5, "EXT-002", None), ("PT-904", "EN-902", 0.05, "EXT-002", 1),
    ("PT-904", "SU-901", 1, "EXT-002", 2),
    ("PT-905", "GR-901", 0.25, "EXT-002", None), ("PT-905", "EN-901", 0.0025, "EXT-002", 1),
    ("PT-906", "MP-901", 0.5, "EXT-002", None), ("PT-906", "EN-901", 0.005, "EXT-002", 1),
]


def stock_rows(today):
    d = lambda n: today + timedelta(days=n)  # noqa: E731
    return [
        # articulo, desc, lote, almacen, cantidad, venc, fab, admision
        ("PT-901", "L901A", "ALM-001", 300, d(240), d(-120), d(-100)),
        ("PT-901", "L901B", "ALM-001", 100, d(12), d(-350), d(-340)),
        ("PT-902", "L902A", "ALM-001", 40, d(300), d(-60), d(-55)),
        ("PT-903", "L903A", "EXT-001", 200, d(200), d(-90), d(-80)),
        ("PT-904", "L904A", "ALM-001", 50, d(180), d(-30), d(-25)),
        ("PT-904", "L904V", "ALM-001", 30, d(-1), d(-366), d(-360)),
        ("PT-905", "L905A", "ALM-001", 1000, d(330), d(-20), d(-18)),
        ("PT-906", "L906A", "ALM-001", 120, d(250), d(-40), d(-35)),
        ("MP-901", "M901A", "EXT-002", 2000, d(500), d(-30), d(-28)),
        ("MP-902", "M902A", "EXT-002", 30, d(500), d(-30), d(-28)),
        ("MP-903", "M903A", "EXT-002", 600, d(500), d(-30), d(-28)),
        ("GR-901", "G901A", "EXT-002", 800, d(400), d(-30), d(-28)),
        ("EN-901", "E901A", "EXT-002", 15, None, None, d(-10)),
        ("EN-902", "E902A", "EXT-002", 3, None, None, d(-10)),
        ("EN-903", "E903A", "EXT-002", 10, None, None, d(-10)),
        ("SU-901", "S901A", "EXT-002", 5000, None, None, d(-10)),
        ("PT-901", "L901C", "EXT-005", 80, d(220), d(-100), d(-90)),
    ]


def _desc(code):
    for p in PRODUCTS:
        if p[0] == code:
            return p[1]
    for p in INSUMOS:
        if p[0] == code:
            return p[1]
    return code


def write_stock(path, today, extra_rows=None, con_errores=False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "STOCK_LOTE"
    ws.append(["Número de artículo", "Descripción del artículo", "Lote", "Almacén", "Cantidad", "Fecha de vencimiento",
               "Fecha de fabricación", "Fecha de admisión"])
    for a, lote, alm, q, v, f, ad in stock_rows(today) + (extra_rows or []):
        ws.append([a, _desc(a), lote, alm, q, v, f, ad])
    if con_errores:
        ws.append(["PT-901", _desc("PT-901"), "L901A", "ALM-001", 5, None, None, None])  # duplicado
        ws.append(["PT-902", _desc("PT-902"), "L902Z", "ALM-001", -4, None, None, None])  # negativo
        ws.append(["PT-905", _desc("PT-905"), "L905Z", "ALM-001", "doce", None, None, None])  # no numérico
    wb.save(path)


def write_bom(path, today, cambios=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append(["Articulo Padre", "Descripcion Padre", "Tipo BOM", "Cantidad BOM", "Almacen PT", "Fecha Creacion",
               "Fecha Actualizacion", "Orden", "Articulo Componente", "Descripcion Componente", "Cantidad Componente",
               "Almacen Componente", "UM", "Metodo Emision", "Columna1"])
    for padre, comp, q, alm, orden in BOM + (cambios or []):
        ws.append([padre, _desc(padre), "P", 1, "ALM-001", today - timedelta(days=90), today - timedelta(days=30), orden,
                   comp, _desc(comp), q, alm, None, "M", None])
    wb.save(path)


def write_products(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DATA"
    ws.append(["Código de Producto", "Descripción de Producto", "PPB", "MAQ", "TIPO", "CALIDAD"])
    for code, desc, ppb, maq, tipo, cal, _ in PRODUCTS:
        ws.append([code, desc, ppb, maq, tipo, cal])
    wb.save(path)


def write_ovs(path, today):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "OVS"
    ws.append(["Número interno", "Número de documento", "Estado", "Fecha de Emisión", "Fecha de Vencimiento", "Vendedor",
               "Ruc", "Nombre de cliente", "Grupo de cliente", "Dirección", "Distrito", "Provincia", "Código de Producto",
               "Descripción de Producto", "Solicitado", "Entregado", "Unidad de medida", "Presentación", "Peso",
               "Comentarios", "P. Unitario SOLES"])
    rows = [
        (9001, "SAP-9001", "Abierto", today, today + timedelta(days=3), "VENDEDOR DEMO UNO", "20000000001",
         "CLIENTE DEMO MAYORISTA S.A.C.", "MAYORISTA", "AV. DEMO 100", "ATE", "LIMA", "PT-905", 400, 0, "UNIDAD", 40, 0.25, "", 3.9),
        (9001, "SAP-9001", "Abierto", today, today + timedelta(days=3), "VENDEDOR DEMO UNO", "20000000001",
         "CLIENTE DEMO MAYORISTA S.A.C.", "MAYORISTA", "AV. DEMO 100", "ATE", "LIMA", "PT-902", 10, 0, "UNIDAD", 1, 5, "", 31.5),
        (9002, "SAP-9002", "Cerrado", today - timedelta(days=20), today - timedelta(days=10), "VENDEDOR DEMO UNO",
         "20000000002", "CLIENTE DEMO RESTAURANTES S.A.C.", "HOTELES - RESTAURANTES", "JR. DEMO 200", "SURCO", "LIMA",
         "PT-901", 24, 24, "UNIDAD", 24, 0.5, "", 4.5),
    ]
    for r in rows:
        ws.append([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], _desc(r[12]), r[13],
                   r[14], r[15], r[16], r[17], r[18], r[19]])
    wb.save(path)


def write_liquidation(path, today, numero="LQ-DEMO-1", producto="PT-903", cantidad=300, lote="L903P"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dat.Prod"
    ws.append(["Número de documento", "Tipo de Operación", "Almacén", "Fecha de creación", "Código de producto",
               "Descripción de producto", "Cantidad Planificada", "Cantidad Completada", "Unidad de medida", "Valorizado",
               "Estado", "Realizado por", "Comentarios", "Lote", "Fecha de admisión", "Fecha de vencimiento"])
    ws.append([numero, "Estándar", "ALMACEN CENTRAL", today, producto, _desc(producto), cantidad, cantidad, "UNIDAD", 0,
               "Cerrado", "Usuario Demo (Producción)", f"Orden fabricación: {producto}", lote, today, today + timedelta(days=365)])
    wb.save(path)


def write_sales(path, today):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Qy"
    ws.append(["Número de documento", "Fecha de Emisión", "Código de Producto", "Descripción de Producto", "Cantidad"])
    n = 1
    consumo = {"PT-901": 12, "PT-902": 2, "PT-903": 10, "PT-905": 30, "EN-901": 1.2, "EN-902": 0.3, "SU-901": 40,
               "MP-902": 15}
    for i in range(1, 31):
        for code, q in consumo.items():
            ws.append([f"DOC-DEMO-{n:05d}", today - timedelta(days=i), code, _desc(code), q])
            n += 1
    wb.save(path)


CANALES = [("MAYORISTA", 0.12), ("INSTITUCIONAL", 0.18), ("CUENTAS CLAVE", 0.15), ("MARCA BLANCA", 0.20), ("CATERING", 0.20),
           ("HOTELES - RESTAURANTES", 0.22), ("AUTOSERVICIOS", 0.35), ("ENTRETENIMIENTO", 0.25), ("E-COMMERCE", 0.35),
           ("DISTRIBUIDORES", 0.15)]
COSTOS_DEMO = {"PT-901": 1.80, "PT-902": 17.50, "PT-903": 2.10, "PT-904": 30.00, "PT-905": 2.40, "PT-906": 1.60,
               "MP-901": 3.10, "MP-902": 3.60, "MP-903": 5.80, "GR-901": 8.90}


def write_prices(path):
    """Lista de precios FICTICIA con el formato de PRICE_LIST (márgenes en la fila 1, precio = costo / (1 − margen))."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append([None, None, None, None] + [m for _, m in CANALES])
    ws.append([None, "SKU", "GRANEL", "COSTO EMPRESA"] + [f"{c}\n{int(m * 100)}%" for c, m in CANALES])
    for i, (code, costo) in enumerate(COSTOS_DEMO.items(), start=3):
        cols = "EFGHIJKLMN"
        ws.append([None, code, _desc(code), costo] + [f"=D{i}/(1-${c}$1)" if code != "PT-906" else round(costo / (1 - m), 6)
                                                    for c, (_, m) in zip(cols, CANALES)])
    wb.save(path)


def write_prices_granel(path):
    """Lista mayorista granel FICTICIA con el formato de PRICE_LIST_GRANEL."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append([None, None, "LISTA DE PRECIOS MAYORISTA GRANEL"])
    ws.append([None, None, None, None, 0.12])
    ws.append([None, "SKU", "DESCRIPCIÓN", "COSTO EMPRESA", "PRECIO X KG", "CANTIDAD KG X SACO", "PRECIO X SACO"])
    ws.append([None, "MP-901", _desc("MP-901"), 3.10, "=G4/F4", 25, 90])
    ws.append([None, "GR-901", _desc("GR-901"), 8.90, "=G5/F5", 25, 255])
    wb.save(path)


def write_customer_conditions(path):
    """Lista FICTICIA de clientes con penalidades y lotes (formato del archivo de Comercial; dos bloques con encabezado)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    enc = ["EJECUTIVO", "CANAL", "CLIENTE", "SOLICITUD", "LOTE", "VIDA UTIL", "Columna1"]
    ws.append(enc)
    ws.append(["VENDEDOR DEMO UNO", "INSTITUCIONAL", "CLIENTE DEMO INSTITUCIONAL S.A.C.", "PRODUCTO TERMINADO", "1 LOTE POR SKU",
               "6 MESES / 3 MESES HARINAS", "PAE INCLUMPLIMENTO DE FECHA DE ENTREGA - PENALIDAD DE LA INSTIUCION TRANFERIDA A NOSOTROS"])
    ws.append(["VENDEDOR DEMO DOS", "Catering", "CLIENTE DEMO CATERING E.I.R.L.", "PRODUCTO TERMINADO", "1 LOTE POR SKU",
               "6 MESES", "INCUMPLIMIENTO VENTANA HORARIA - NO SE RECIBE"])
    ws.append(enc)
    ws.append(["VENDEDOR DEMO DOS", "Restaurantes", "CLIENTE DEMO RESTAURANTES S.A.C.", "PRODUCTO TERMINADO", "2 LOTES POR SKU",
               "4 MESES", "FILL RATE <95% - Se Facturara lo no atendido y el margen perdido y rebate\n"
               "INCUMPLIMIENTO VENTANA HORARIA - 100% Gastos logisticos por demoras o incumplimiento, no recepción"])
    ws.append(["VENDEDOR DEMO UNO", "AUTOSERVICIO", "CLIENTE DEMO NUEVO S.A.C.", "MATERIA PRIMA", "1 LOTE POR SKU", "6 MESES",
               "INCUMPLIMIENTO VENTANA HORARIA - NO SE RECIBE"])
    wb.save(path)


def write_all(folder, today=None):
    today = today or date.today()
    os.makedirs(folder, exist_ok=True)
    files = {
        "productos": os.path.join(folder, "demo_productos_DATA.xlsx"),
        "stock": os.path.join(folder, "demo_stock_lote.xlsx"),
        "stock_errores": os.path.join(folder, "demo_stock_lote_con_errores.xlsx"),
        "bom": os.path.join(folder, "demo_lista_materiales.xlsx"),
        "ovs": os.path.join(folder, "demo_ovs_sap.xlsx"),
        "liquidacion": os.path.join(folder, "demo_liquidacion_datprod.xlsx"),
        "salidas": os.path.join(folder, "demo_historial_salidas_qy.xlsx"),
        "precios": os.path.join(folder, "demo_price_list.xlsx"),
        "precios_granel": os.path.join(folder, "demo_price_list_granel.xlsx"),
        "clientes": os.path.join(folder, "demo_clientes_penalidades_lotes.xlsx"),
    }
    write_products(files["productos"])
    write_stock(files["stock"], today)
    write_stock(files["stock_errores"], today, con_errores=True)
    write_bom(files["bom"], today)
    write_ovs(files["ovs"], today)
    write_liquidation(files["liquidacion"], today)
    write_sales(files["salidas"], today)
    write_prices(files["precios"])
    write_prices_granel(files["precios_granel"])
    write_customer_conditions(files["clientes"])
    return files
