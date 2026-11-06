"""Genera la propuesta de servidor para el directorio (PDF). Uso: python3 servidor_pdf.py <salida.pdf> <logo.png>"""
import sys

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT, LOGO = sys.argv[1], sys.argv[2]
pdfmetrics.registerFont(TTFont("DV", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily  # noqa: E402
registerFontFamily("DV", normal="DV", bold="DVB", italic="DV", boldItalic="DVB")

VERDE = colors.HexColor("#0b6b3a")
VERDE_CL = colors.HexColor("#e7f3ec")
GRIS = colors.HexColor("#5f6b66")
GRIS_CL = colors.HexColor("#f3f5f4")
AMBAR = colors.HexColor("#fff4d6")
ROJO_CL = colors.HexColor("#fde8e8")

ss = getSampleStyleSheet()
N = ParagraphStyle("n", parent=ss["Normal"], fontName="DV", fontSize=9, leading=12.5)
NS = ParagraphStyle("ns", parent=N, fontSize=7.6, leading=9.6)
NSB = ParagraphStyle("nsb", parent=NS, fontName="DVB")
H1 = ParagraphStyle("h1", parent=N, fontName="DVB", fontSize=15, leading=19, textColor=VERDE, spaceBefore=4, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=N, fontName="DVB", fontSize=11.5, leading=15, textColor=VERDE, spaceBefore=10, spaceAfter=4)
TIT = ParagraphStyle("tit", parent=N, fontName="DVB", fontSize=22, leading=27, textColor=VERDE, alignment=TA_CENTER)
SUB = ParagraphStyle("sub", parent=N, fontSize=11, leading=15, textColor=GRIS, alignment=TA_CENTER)
CAJA = ParagraphStyle("caja", parent=N, fontSize=9.5, leading=13.5)

TC = 3.50  # tipo de cambio referencial S/ por USD


def P(t, s=N):
    return Paragraph(t, s)


def tabla(filas, anchos, cab=1, estilo_extra=(), s=NS):
    data = [[c if not isinstance(c, str) else P(c, NSB if i < cab else s) for c in f] for i, f in enumerate(filas)]
    t = Table(data, colWidths=anchos, repeatRows=cab)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d3ce")),
          ("BACKGROUND", (0, 0), (-1, cab - 1), VERDE_CL),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    t.setStyle(TableStyle(st + list(estilo_extra)))
    return t


def caja(texto, fondo=VERDE_CL, borde=VERDE):
    t = Table([[P(texto, CAJA)]], colWidths=[25.7 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fondo), ("BOX", (0, 0), (-1, -1), 1, borde),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("DV", 7.5)
    canvas.setFillColor(GRIS)
    canvas.drawString(1.5 * cm, 0.9 * cm, "Propuesta de servidor para el Módulo de Operaciones · 06-nov-2026 · Precios referenciales en USD, sin IGV")
    canvas.drawRightString(A4[1] - 1.5 * cm, 0.9 * cm, f"Página {doc.page}")
    canvas.restoreState()


story = []

# ------------------------------------------------------------------ portada
story += [Spacer(1, 1.2 * cm), Image(LOGO, width=6.5 * cm, height=6.5 * cm * 0.32, kind="proportional"), Spacer(1, 0.6 * cm),
          P("Propuesta de servidor para el Módulo de Operaciones", TIT), Spacer(1, 0.25 * cm),
          P("Cuadro comparativo de costos, especificaciones técnicas, ventajas y desventajas, y recomendación", SUB),
          Spacer(1, 0.2 * cm), P("Para presentación al Directorio · 06 de noviembre de 2026", SUB), Spacer(1, 0.8 * cm)]
story.append(caja(
    "<b>Decisión que se solicita al Directorio</b><br/>"
    "Aprobar la contratación de un servidor en la nube a nombre de la empresa para pasar el módulo a producción. Hoy "
    "funciona en un laboratorio académico, que no es propiedad de la empresa y no es apto para datos de producción.<br/><br/>"
    "<b>Recomendación:</b> <b>AWS Lightsail, plan de 16 GB</b> (4 núcleos, 16 GB de memoria, 320 GB de disco SSD y "
    "6 TB de tráfico al mes), con copias de seguridad automáticas y una copia externa.<br/>"
    f"<b>Costo estimado:</b> unos <b>USD 95 al mes</b> (unos S/ {95 * TC:,.0f}), es decir, <b>USD 1 140 al año</b> "
    f"(unos S/ {1140 * TC:,.0f}), más IGV si corresponde.<br/><br/>"
    "<b>Alternativa de menor costo:</b> el plan de 8 GB (2 núcleos), por unos USD 53 al mes. Sirve para empezar, pero "
    "tiene la mitad de los procesadores con los que se midió la velocidad del sistema. Se puede subir de plan después "
    "en unos 30 minutos."))
story.append(Spacer(1, 0.5 * cm))
story.append(tabla([
    ["Punto", "Resumen"],
    ["Por qué AWS", "El sistema ya está en AWS (EC2) y conectado con SAP. Seguir en AWS no exige rehacer nada: se mudan la base y los archivos, y la VPN hacia SAP queda igual."],
    ["Por qué Lightsail y no EC2", "Mismo centro de datos y misma calidad que EC2, pero con precio fijo mensual que ya incluye el disco, la IP fija y el tráfico. En EC2 esas partes se cobran por separado y la factura varía."],
    ["Por qué 16 GB y 4 núcleos", "La prueba de carga de la ronda V20 se hizo con 4 núcleos: hasta unas 100 personas conectadas, con respuestas de menos de medio segundo en la mayoría de pantallas. El disco de 320 GB alcanza para unos 5 años si las fotos se comprimen (sección 3)."],
    ["Por qué no la laptop", "Sirve para pruebas o como copia de respaldo local, pero no para producción. No está hecha para estar encendida 24/7, no tiene redundancia y, si se corta la luz o internet en planta, nadie puede usar el sistema: choferes y vendedores en la calle tampoco."],
], [5 * cm, 20.7 * cm]))
story.append(PageBreak())

# ------------------------------------------------------------------ 1. situación actual y qué guarda el sistema
story.append(P("1. Situación actual y qué guarda el sistema", H1))
story.append(P(
    "Hoy el módulo corre en una instancia EC2 de AWS de un laboratorio académico. Llega a SAP Business One (Service "
    "Layer) por un túnel abierto desde una máquina virtual de la empresa; la ronda V21 dejó lista una VPN WireGuard para "
    "reemplazarlo. Para producción, el servidor debe ser <b>de la empresa</b>, por tres motivos:"))
story.append(P(
    "• La cuenta académica no es de la empresa y puede vencer o cerrarse.<br/>"
    "• Los datos de clientes y trabajadores (nombres, DNI de receptores, firmas, fotos) son datos personales protegidos "
    "por la Ley 29733; la empresa debe ser la titular del servidor que los guarda.<br/>"
    "• Se necesita facturación a nombre de la empresa, control de accesos y copias de seguridad propias."))
story.append(Spacer(1, 4))
story.append(P("<b>Qué se guarda en el servidor</b> (base de datos y archivos):", N))
story.append(tabla([
    ["Información", "Ejemplos", "Dónde se guarda", "Crecimiento"],
    ["Maestros traídos de SAP", "Clientes y sus direcciones, artículos, almacenes, listas de precios, condiciones de pago", "Base de datos", "Bajo"],
    ["Ventas", "OV y sus líneas, cotizaciones, oportunidades, penalidades, pagos, incidencias", "Base de datos", "Medio"],
    ["Compras e importaciones", "Presolicitudes, OC, cotizaciones, llegadas, archivos de OC y facturas (PDF)", "Base de datos + archivos", "Medio"],
    ["Inventario", "Stock por lote y almacén, reservas, movimientos, conteos de inventario, fumigaciones", "Base de datos", "Medio"],
    ["Copias de lo traído de SAP", "Cada carga de stock, OV, liquidaciones y despachos queda con sus filas (sirve de respaldo y para conciliar)", "Base de datos", "Alto"],
    ["Producción y Calidad", "Partes, liquidaciones, formatos de calidad, certificados, inspecciones, no conformidades", "Base de datos + fotos", "Medio"],
    ["Evidencias fotográficas", "Fotos de inicio y fin de los montacarguistas, fin de picking, checklist vehicular, entregas", "Archivos", "<b>Muy alto</b>"],
    ["Documentos de distribución", "Guías firmadas, firma del receptor, conformidades, facturas de transporte", "Archivos", "Alto"],
    ["Control y seguridad", "Usuarios, permisos, alertas, auditoría de cada cambio, registro de errores", "Base de datos", "Medio"],
], [5 * cm, 11.2 * cm, 4.5 * cm, 5 * cm]))
story.append(Spacer(1, 5))
story.append(caja(
    "<b>Importante:</b> el módulo guarda <b>una copia de los datos de SAP que usa</b> (clientes, OV, stock, despachos, "
    "liquidaciones), además de todo lo que se registra solo en el módulo (fotos, firmas, partes, alertas). Esa copia "
    "<b>no reemplaza la copia de seguridad propia de SAP</b>: la base de SAP debe seguir respaldándose en el servidor "
    "de SAP.", AMBAR, colors.HexColor("#c79a1b")))
story.append(PageBreak())

# ------------------------------------------------------------------ 2. especificaciones
story.append(P("2. Especificaciones técnicas del servidor", H1))
story.append(P(
    "Están basadas en la prueba de carga de la ronda V20, hecha con PostgreSQL y gunicorn igual que en el servidor, "
    "sobre una base de volumen realista (1 505 clientes, 1 517 lotes, 435 OV, 20 473 registros de auditoría):"))
story.append(tabla([
    ["Escenario medido (4 núcleos)", "Peticiones/s", "Mediana", "95 % de respuestas"],
    ["30 usuarios con uso intenso (un clic cada 2 s)", "10", "0,2 s", "1,3 s"],
    ["60 usuarios con uso intenso", "17", "0,5 s", "3,2 s"],
    ["100 usuarios con uso normal (un clic cada ~10 s)", "6", "0,2 s", "3,4 s"],
    ["200 usuarios con uso normal", "9", "0,9 s", "10,9 s"],
], [11 * cm, 4 * cm, 4 * cm, 6.7 * cm]))
story.append(Spacer(1, 6))
story.append(tabla([
    ["Recurso", "Mínimo (piloto, hasta ~30 usuarios a la vez)", "Recomendado (producción, hasta ~100 a la vez)", "Para crecer (200 o más a la vez)", "Por qué"],
    ["Núcleos (vCPU)", "2", "<b>4</b>", "8", "La prueba de carga se hizo con 4. El sistema usa procesos = núcleos + 1, con 4 hilos cada uno, y se ajusta solo."],
    ["Memoria RAM", "4 GB", "<b>8 a 16 GB</b>", "32 GB", "PostgreSQL usa la memoria como caché: con 16 GB la base cabe entera en memoria durante años, y las pantallas e informes responden más rápido."],
    ["Disco del sistema y la base", "80 GB SSD", "<b>160 a 320 GB SSD</b>", "320 GB + disco adicional", "Base de datos, sistema operativo, copias diarias de la base y las fotos (ver sección 3)."],
    ["Almacenamiento de archivos", "En el mismo disco", "<b>En el mismo disco, con fotos comprimidas</b>", "Almacenamiento de objetos (S3)", "Las fotos son lo que más crece. S3 cuesta USD 0,023 por GB al mes y no tiene límite."],
    ["Tráfico de red", "1 TB/mes", "<b>3 a 6 TB/mes</b> (incluido)", "6 TB/mes o más", "Las fotos que se suben no cuentan como tráfico de salida; las que se ven y descargan sí."],
    ["IP pública fija", "Sí", "<b>Sí</b>", "Sí", "Para el dominio, el certificado HTTPS y la VPN con SAP."],
    ["Sistema y programas", "Ubuntu 24.04 LTS", "Ubuntu 24.04 LTS, PostgreSQL 16, Python 3, Caddy (HTTPS)", "Igual", "Programas gratuitos (código abierto): no hay licencias que pagar."],
    ["Copias de seguridad", "Diaria", "<b>Diaria automática (7 días) + copia externa (30 días)</b>", "Igual + réplica", "Instantánea del servidor y copia de la base y los archivos fuera del servidor."],
    ["Conexión con SAP", "VPN WireGuard", "<b>VPN WireGuard (punto a punto)</b>", "Igual", "Ya está preparada (ronda V21). Solo expone el puerto 50000 del Service Layer."],
], [3.4 * cm, 3.6 * cm, 4.6 * cm, 3.6 * cm, 10.5 * cm], estilo_extra=[("BACKGROUND", (2, 1), (2, -1), VERDE_CL)]))
story.append(PageBreak())

# ------------------------------------------------------------------ 3. almacenamiento
story.append(P("3. Cuánto espacio se necesita y cómo crecerá", H1))
story.append(P(
    "No se tienen todavía los volúmenes reales de producción, así que el cálculo usa <b>supuestos de trabajo</b> que "
    "conviene confirmar con cada área. El resultado escala en proporción: si hay el doble de fotos, se necesita el doble "
    "de espacio de fotos. Se toman 310 días laborables al año."))
story.append(tabla([
    ["Origen de los archivos (supuesto diario)", "Cantidad/día", "Sin comprimir (~3 MB c/u)", "Comprimido (~250 KB c/u)"],
    ["Montacarguistas: foto de inicio y de fin por movimiento (120 movimientos)", "240 fotos", "720 MB", "60 MB"],
    ["Fin de picking (40 OV)", "40 fotos", "120 MB", "10 MB"],
    ["Entregas: foto, guía firmada y firma del receptor (40 paradas)", "120 archivos", "360 MB", "30 MB"],
    ["Checklist vehicular de salida y retorno (10 unidades × 4 fotos × 2)", "80 fotos", "240 MB", "20 MB"],
    ["Calidad: formatos, fumigaciones, inspecciones", "40 fotos", "120 MB", "10 MB"],
    ["Documentos PDF: OC, facturas, certificados, cargas Excel (~300 KB c/u)", "40 archivos", "12 MB", "12 MB"],
    ["<b>Total por día</b>", "<b>~560</b>", "<b>~1,6 GB</b>", "<b>~140 MB</b>"],
    ["<b>Total por año (310 días)</b>", "", "<b>~490 GB</b>", "<b>~44 GB</b>"],
], [13.2 * cm, 3 * cm, 4.75 * cm, 4.75 * cm], estilo_extra=[("BACKGROUND", (0, -2), (-1, -1), GRIS_CL)]))
story.append(Spacer(1, 6))
story.append(tabla([
    ["Componente", "Año 1", "Año 3", "Año 5", "Supuesto"],
    ["Sistema operativo, programas y registros", "10 GB", "12 GB", "15 GB", "Fijo"],
    ["Base de datos PostgreSQL", "5 GB", "15 GB", "25 GB", "~5 GB/año: OV, movimientos, auditoría y dos cargas diarias de stock de SAP"],
    ["Copias diarias de la base en el servidor (7 días, comprimidas)", "2 GB", "5 GB", "8 GB", "La copia de 30 días va fuera del servidor"],
    ["Fotos y documentos <b>comprimidos</b>", "44 GB", "132 GB", "220 GB", "~44 GB/año"],
    ["<b>Total con fotos comprimidas</b>", "<b>~61 GB</b>", "<b>~164 GB</b>", "<b>~268 GB</b>", "<b>Cabe en 320 GB (plan de 16 GB)</b>"],
    ["Total sin comprimir las fotos", "~507 GB", "~1,5 TB", "~2,5 TB", "No cabe en ningún plan fijo; habría que pagar almacenamiento aparte"],
], [8 * cm, 2.6 * cm, 2.6 * cm, 2.6 * cm, 9.9 * cm],
    estilo_extra=[("BACKGROUND", (0, 5), (-1, 5), VERDE_CL), ("BACKGROUND", (0, 6), (-1, 6), ROJO_CL)]))
story.append(Spacer(1, 6))
story.append(caja(
    "<b>Requisito técnico previo:</b> hoy el módulo guarda las fotos tal como las toma el celular (2 a 5 MB cada una). "
    "Antes de pasar a producción conviene <b>comprimirlas al subirlas</b>, por ejemplo a 1600 px de lado y unos 250 KB. "
    "Se siguen viendo bien como evidencia, pesan unas 10 veces menos y se suben más rápido por datos móviles. "
    "<b>Esta mejora aún no está hecha en el sistema</b>; es un cambio de programación pequeño y se puede incluir en la "
    "próxima entrega.<br/><b>Si en el futuro se supera el disco:</b> se agrega un disco adicional (USD 0,10 por GB al mes) "
    "o se pasan las fotos con más de un año a S3 (USD 0,023 por GB al mes), sin cambiar de servidor.",
    AMBAR, colors.HexColor("#c79a1b")))
story.append(PageBreak())

# ------------------------------------------------------------------ 4. cuadro comparativo de costos
story.append(P("4. Cuadro comparativo de opciones y costos", H1))
story.append(P(
    f"Montos en USD al mes, sin IGV. Las soles son referenciales, a S/ {TC:.2f} por dólar; actualizar al tipo de cambio del "
    "día. Las tarifas son de lista y se tomaron de fuentes públicas en noviembre de 2026 (ver sección 8): <b>deben "
    "confirmarse en la calculadora oficial de cada proveedor antes de contratar</b>."))
op = [
    ["Opción", "Especificación", "Servidor", "Disco y extras", "Copias de seguridad", "Total/mes USD", "Total/año USD (S/)", "3 años USD"],
    ["<b>A. AWS Lightsail 16 GB (recomendada)</b>", "4 vCPU, 16 GB RAM, 320 GB SSD, 6 TB tráfico, IP fija", "84", "Incluido", "~8 instantáneas + ~3 copia externa S3", "<b>~95</b>", f"<b>~1 140 (S/ {1140 * TC:,.0f})</b>", "<b>~3 420</b>"],
    ["B. AWS Lightsail 8 GB (económica)", "2 vCPU, 8 GB RAM, 160 GB SSD, 5 TB tráfico, IP fija", "44", "Incluido (+10 desde el año 3 por un disco adicional de 100 GB)", "~6 + ~3", "~53–63", f"~700 (S/ {700 * TC:,.0f})", "~2 100"],
    ["C. AWS Lightsail 4 GB (solo piloto)", "2 vCPU, 4 GB RAM, 80 GB SSD, 4 TB tráfico", "24", "Disco lleno en ~1 año", "~4 + ~3", "~31", f"~372 (S/ {372 * TC:,.0f})", "No alcanza"],
    ["D. AWS EC2 t4g.xlarge (la opción actual, ampliada)", "4 vCPU, 16 GB RAM, disco gp3 de 200 GB aparte", "~98", "Disco ~16 + IP ~3,6 + tráfico de salida ~0–9", "~5 instantáneas + ~3 S3", "~125–135", f"~1 560 (S/ {1560 * TC:,.0f})", "~4 700"],
    ["E. Microsoft Azure B4ms", "4 vCPU, 16 GB RAM (precio de 2 × B2ms)", "~121", "Disco administrado ~20–40 (estimado)", "~10 (estimado)", "~150–170", f"~1 920 (S/ {1920 * TC:,.0f})", "~5 760"],
    ["F. Hetzner CPX31 (EE. UU.)", "4 vCPU, 8 GB RAM, 160 GB", "~70 (EUR 62,49)", "IP aparte", "~14 (20 %)", "~85", f"~1 020 (S/ {1020 * TC:,.0f})", "~3 060"],
    ["G. Oracle Cloud «Always Free»", "Hasta 4 núcleos Ampere, 24 GB RAM, 200 GB", "0", "Incluido", "~3 copia externa", "~3", "~36", "~110"],
    ["H. Laptop de la empresa como servidor local", "Según la laptop; mínimo 4 núcleos, 16 GB RAM y SSD de 512 GB", "0 (equipo existente)", "UPS S/ 450 + disco externo S/ 300 una sola vez; luz ~S/ 25 al mes", "Disco externo + S3 ~3", f"~10 (S/ {10 * TC:.0f})", f"~330 el año 1 (S/ {330 * TC:,.0f})", "~570 + reposición del equipo"],
]
story.append(tabla(op, [4.5 * cm, 4.6 * cm, 2 * cm, 4 * cm, 3.2 * cm, 2.2 * cm, 3.2 * cm, 2 * cm],
                   estilo_extra=[("BACKGROUND", (0, 1), (-1, 1), VERDE_CL), ("BACKGROUND", (0, 8), (-1, 8), GRIS_CL)]))
story.append(Spacer(1, 6))
story.append(P(
    "<b>Notas:</b><br/>"
    "• <b>Lightsail:</b> la instantánea automática diaria guarda 7 días y se cobra a USD 0,05 por GB al mes (solo lo usado "
    "y los cambios). El tráfico extra cuesta USD 0,09 por GB.<br/>"
    "• <b>EC2:</b> con un compromiso de 1 año (Savings Plan) el servidor baja aproximadamente un 30 %, unos USD 100 al mes "
    "en total. Aun así es más caro y más complejo de administrar que Lightsail.<br/>"
    "• <b>Hetzner:</b> subió sus precios dos veces en 2026 (abril y junio), hasta 2 a 3 veces en algunos planes. Es "
    "inestable para presupuestar y no tiene centro de datos en Sudamérica.<br/>"
    "• <b>Oracle gratis:</b> no tiene garantía de servicio, puede no haber capacidad para crear la máquina y Oracle puede "
    "reclamar máquinas poco usadas. Sirve como ambiente de pruebas, no de producción.<br/>"
    "• <b>IGV:</b> los servicios digitales de proveedores del exterior pagan IGV en el Perú. Confirmar con Contabilidad cómo "
    "se factura.", NS))
story.append(PageBreak())

# ------------------------------------------------------------------ gráfico de costo a 3 años
story.append(P("Costo acumulado a 3 años (USD, sin IGV)", H2))
d = Drawing(25 * cm, 7.4 * cm)
ch = HorizontalBarChart()
ch.x, ch.y, ch.width, ch.height = 6.2 * cm, 0.4 * cm, 17.5 * cm, 6.6 * cm
nombres = ["H. Laptop local*", "G. Oracle gratis**", "B. Lightsail 8 GB", "F. Hetzner CPX31", "A. Lightsail 16 GB",
           "D. AWS EC2 t4g.xlarge", "E. Azure B4ms"]
vals = [570, 110, 2100, 3060, 3420, 4700, 5760]
ch.data = [vals]
ch.categoryAxis.categoryNames = nombres
ch.categoryAxis.labels.fontName = "DV"
ch.categoryAxis.labels.fontSize = 8
ch.categoryAxis.labels.dx = -4
ch.categoryAxis.labels.boxAnchor = "e"
ch.valueAxis.valueMin, ch.valueAxis.valueMax, ch.valueAxis.valueStep = 0, 6000, 1000
ch.valueAxis.labels.fontName = "DV"
ch.valueAxis.labels.fontSize = 7.5
ch.bars[0].fillColor = colors.HexColor("#9fc5b0")
ch.bars[(0, 4)].fillColor = VERDE
ch.barLabelFormat = "%d"
ch.barLabels.fontName = "DV"
ch.barLabels.fontSize = 7.5
ch.barLabels.dx = 14
d.add(ch)
story.append(d)
story.append(P("* No incluye la reposición de la laptop (unos S/ 3 500 a S/ 5 000) ni el costo de las horas sin "
               "sistema por cortes de luz o de internet.<br/>"
               "** Sin garantía de servicio y con riesgo de que Oracle recupere la máquina.", NS))

# ------------------------------------------------------------------ 5. pros y contras
story.append(P("5. Ventajas y desventajas", H1))
pc = [
    ["Opción", "Ventajas", "Desventajas"],
    ["<b>A. AWS Lightsail 16 GB</b>",
     "• Precio fijo y predecible: incluye disco, IP y 6 TB de tráfico.<br/>• Misma infraestructura de AWS, con un "
     "99,99 % de disponibilidad del centro de datos.<br/>• Mismo proveedor que hoy: la mudanza y la VPN hacia SAP no "
     "cambian.<br/>• 4 núcleos, igual que en la prueba de carga.<br/>• Instantáneas automáticas con un clic y subida de "
     "plan en minutos.<br/>• Facturación a nombre de la empresa.",
     "• Cuesta más que el plan de 8 GB.<br/>• Es un solo servidor: si falla, se restaura la instantánea en unos 30 a "
     "60 minutos.<br/>• Si se superan los 6 TB de tráfico, se paga el exceso (improbable con fotos comprimidas)."],
    ["B. AWS Lightsail 8 GB",
     "• Cuesta casi la mitad que el de 16 GB.<br/>• Mismas ventajas de AWS y Lightsail.<br/>• Se sube al de 16 GB en "
     "minutos cuando haga falta.",
     "• Tiene 2 núcleos: la mitad que en la prueba de carga.<br/>• Los informes pesados pueden hacer más lento al resto.<br/>"
     "• El disco de 160 GB se llena hacia el año 3."],
    ["D. AWS EC2",
     "• Es lo que hoy está conectado con SAP.<br/>• Lo más flexible: cualquier tamaño, discos separados, bases "
     "administradas (RDS).<br/>• Con compromiso anual baja el precio.",
     "• Cobra por separado el disco, la IP, el tráfico y las copias: la factura varía cada mes.<br/>• Es más complejo "
     "de administrar.<br/>• Cuesta 30 a 40 % más que Lightsail con la misma capacidad."],
    ["E. Microsoft Azure",
     "• Buen soporte corporativo.<br/>• Se integra con Microsoft 365, si la empresa lo usa.",
     "• Es el más caro de la comparación.<br/>• Habría que mudar todo a otro proveedor y rehacer la VPN.<br/>• Disco y "
     "copias se cobran aparte."],
    ["F. Hetzner",
     "• Hardware potente por el precio.",
     "• Precios inestables: dos alzas en 2026.<br/>• Lejos del Perú: mayor latencia.<br/>• Soporte y facturación "
     "menos adecuados para una empresa peruana."],
    ["G. Oracle «Always Free»",
     "• Gratis.<br/>• Máquina potente: 4 núcleos y 24 GB de RAM.",
     "• Sin garantía de servicio ni soporte.<br/>• Oracle puede recuperar la máquina.<br/>• No es recomendable para "
     "datos de producción. Sirve como ambiente de pruebas."],
    ["H. Laptop de la empresa (servidor local)",
     "• Sin pago mensual al proveedor.<br/>• Los datos quedan físicamente en la empresa.<br/>• Llega a SAP por la red "
     "interna, sin VPN.<br/>• Útil como ambiente de pruebas o como copia local de respaldo.",
     "• Una laptop no está diseñada para estar encendida 24/7: calor, batería y desgaste.<br/>• Es un único punto "
     "de falla: si se daña, se pierde el sistema hasta repararla.<br/>• Un corte de luz o de internet en planta detiene "
     "el sistema para todos, incluidos choferes, vendedores y gerencia fuera de la oficina.<br/>• Para publicarlo hacia "
     "afuera se necesita IP fija o un túnel, y aumenta el riesgo de ataques a la red interna.<br/>• Riesgo de robo o "
     "daño físico; las copias quedan a cargo de una persona.<br/>• El área de Sistemas tiene que administrar todo."],
]
story.append(tabla(pc, [4.4 * cm, 10.65 * cm, 10.65 * cm], estilo_extra=[("BACKGROUND", (0, 1), (-1, 1), VERDE_CL)]))
story.append(PageBreak())

# ------------------------------------------------------------------ 6. evaluación ponderada
story.append(P("6. Evaluación ponderada", H1))
story.append(P("Puntaje de 1 (malo) a 5 (excelente). El peso refleja lo que pidió la empresa: costo, velocidad, que el "
               "sistema esté siempre disponible, respaldo de la información, crecimiento y conexión con SAP."))
crit = [("Costo", 20), ("Velocidad y rendimiento", 20), ("Disponibilidad (24/7, sin cortes)", 20),
        ("Respaldo y seguridad de datos", 15), ("Escalabilidad (crecer sin rehacer)", 10), ("Conexión con SAP", 10),
        ("Facilidad de administración", 5)]
ops = [("A. Lightsail 16 GB", [4, 5, 5, 4, 4, 5, 5]), ("B. Lightsail 8 GB", [5, 3, 5, 4, 4, 5, 5]),
       ("D. AWS EC2", [2, 5, 5, 5, 5, 5, 3]), ("E. Azure", [2, 5, 5, 5, 5, 3, 3]),
       ("F. Hetzner", [3, 3, 4, 3, 4, 3, 3]), ("G. Oracle gratis", [5, 4, 2, 3, 3, 4, 3]),
       ("H. Laptop local", [5, 3, 1, 1, 1, 5, 2])]
filas = [["Criterio", "Peso"] + [o for o, _ in ops]]
for i, (c, w) in enumerate(crit):
    filas.append([c, f"{w} %"] + [str(v[i]) for _, v in ops])
tot = [sum(v[i] * crit[i][1] for i in range(len(crit))) / 100 for _, v in ops]
filas.append(["<b>Puntaje final (sobre 5)</b>", "100 %"] + [f"<b>{t:.2f}</b>" for t in tot])
story.append(tabla(filas, [5.6 * cm, 1.5 * cm] + [2.65 * cm] * 7,
                   estilo_extra=[("BACKGROUND", (2, 1), (2, -1), VERDE_CL), ("BACKGROUND", (0, -1), (-1, -1), GRIS_CL),
                                 ("ALIGN", (1, 1), (-1, -1), "CENTER")]))
story.append(Spacer(1, 6))
story.append(P(
    "La opción A obtiene el mayor puntaje. EC2 (D) empata en rendimiento y respaldo, pero cuesta más y su factura "
    "varía cada mes. La laptop (H) es la más barata, pero la peor en disponibilidad y respaldo, que es lo más crítico "
    "para un sistema del que dependen almacén, despacho y ventas todos los días."))

# ------------------------------------------------------------------ 7. conclusión y plan
story.append(P("7. Conclusión y plan de implementación", H1))
story.append(caja(
    "<b>Conclusión:</b> se recomienda contratar <b>AWS Lightsail, plan de 16 GB (4 vCPU, 16 GB de RAM, 320 GB SSD, "
    "6 TB de tráfico, IP fija)</b> en una <b>cuenta de AWS a nombre de la empresa</b>, con:<br/>"
    "• instantánea automática diaria;<br/>"
    "• copia externa de la base y los archivos en S3;<br/>"
    "• compresión de fotos (mejora pendiente);<br/>"
    "• la VPN WireGuard hacia SAP ya preparada.<br/>"
    f"<b>Presupuesto:</b> unos <b>USD 95 al mes / USD 1 140 al año</b> (unos S/ {1140 * TC:,.0f} al año), más IGV si "
    "corresponde. Con eso se cubren hasta unas 100 personas conectadas a la vez y unos 5 años de fotos y documentos.<br/>"
    "Si el presupuesto obliga a empezar con menos, el plan de 8 GB (unos USD 53 al mes) funciona para un piloto y se "
    "sube al de 16 GB en minutos, sin reinstalar.<br/>"
    "La laptop de la empresa se puede usar como <b>servidor de pruebas</b> o como <b>copia local diaria</b> del "
    "servidor en la nube, no como servidor principal."))
story.append(Spacer(1, 6))
story.append(tabla([
    ["Paso", "Qué se hace", "Responsable", "Tiempo"],
    ["1", "Crear la cuenta de AWS de la empresa: tarjeta corporativa, doble factor de autenticación y alerta de presupuesto (p. ej. USD 120 al mes)", "Gerencia / Sistemas", "1 día"],
    ["2", "Crear la instancia Lightsail de 16 GB con IP fija y abrir solo los puertos 443 (web), 22 (administración) y UDP 51820 (VPN)", "Sistemas + desarrollo", "1 hora"],
    ["3", "Instalar el sistema según la guía docs/25 (PostgreSQL, Caddy con HTTPS y servicio del sistema)", "Desarrollo", "2–3 horas"],
    ["4", "Activar la VPN WireGuard hacia SAP (docs/36, sección 5) y probar con la base de pruebas de SAP", "Sistemas + desarrollo", "Medio día"],
    ["5", "Mudar la base y los archivos del servidor académico al nuevo (copia y restauración) y verificar los totales", "Desarrollo", "2 horas"],
    ["6", "Configurar el dominio de la empresa, las instantáneas automáticas y la copia externa a S3", "Sistemas", "2 horas"],
    ["7", "Implementar la compresión de fotos y hacer el recorrido de pruebas por área", "Desarrollo + usuarios clave", "1–2 días"],
    ["8", "Puesta en producción y retiro del servidor académico", "Todos", "1 día"],
], [1.2 * cm, 15.5 * cm, 5 * cm, 4 * cm]))
story.append(PageBreak())

# ------------------------------------------------------------------ 8. supuestos y fuentes
story.append(P("8. Supuestos, límites de este análisis y fuentes", H1))
story.append(P(
    "• Los precios son de lista en USD, se consultaron en noviembre de 2026 y no incluyen IGV. Los proveedores los "
    "cambian: en 2026 hubo alzas por el costo de la memoria (DRAM). Antes de contratar, confirmarlos en la página "
    "oficial de precios o en la calculadora de cada proveedor. Desde este entorno no se pudo abrir la página oficial de "
    "AWS, así que las cifras de AWS vienen de fuentes que la citan.<br/>"
    "• Los volúmenes diarios de fotos y documentos son supuestos de trabajo, no mediciones; deben confirmarse con cada "
    "área. El espacio necesario crece en proporción.<br/>"
    "• La capacidad de usuarios sale de la prueba de carga de la ronda V20, con 4 núcleos y la base, el sistema y el "
    "generador de carga en la misma máquina. Es un resultado conservador.<br/>"
    "• No se verificó en qué región de AWS está hoy la instancia académica. Se recomienda la región más cercana a la "
    "empresa que ofrezca Lightsail y que convenga para la VPN; confirmarla al crear la cuenta.<br/>"
    "• Para comparar, el costo de la laptop no incluye las horas del personal que la administra ni el costo de las "
    "horas sin sistema.", N))
story.append(Spacer(1, 6))
story.append(P("<b>Fuentes consultadas</b> (noviembre de 2026):", N))
fuentes = [
    ("AWS Lightsail: planes, instantáneas y almacenamiento", "https://cloudburn.io/blog/amazon-lightsail-pricing"),
    ("AWS Lightsail: tabla de planes 2026", "https://kuberns.com/blogs/aws-lightsail-pricing-your-comprehensive-guide/"),
    ("AWS Lightsail: calculadora de planes y excesos", "https://www.factualminds.com/tools/aws-lightsail-pricing-calculator/"),
    ("AWS Lightsail: página oficial de precios (para confirmar)", "https://aws.amazon.com/lightsail/pricing/"),
    ("AWS EC2 t4g.large en us-east-1", "https://calculator.holori.com/aws/ec2/t4g.large/us-east-1"),
    ("AWS EC2 t4g (precios por región)", "https://www.devzero.io/instances/aws/t4g.large"),
    ("AWS EBS gp3", "https://cloudburn.io/blog/amazon-ebs-pricing"),
    ("Amazon S3 y Glacier", "https://upstash.com/blog/aws-s3-pricing-explained-2026"),
    ("Microsoft Azure B2ms", "https://www.economize.cloud/resources/azure/pricing/virtual-machine/b2ms/"),
    ("Hetzner: alzas de 2026", "https://wz-it.com/en/blog/hetzner-price-increase-june-2026-cpx-ccx-alternatives/"),
    ("Hetzner: alza de abril de 2026", "https://www.tomshardware.com/tech-industry/hetzner-to-raise-prices-by-up-to-37-percent-from-april-1"),
    ("Prueba de carga del sistema (ronda V20)", "docs/35_RONDA_V20_RENDIMIENTO_NOTIFICACIONES_LOTES.md del proyecto"),
    ("VPN WireGuard hacia SAP (ronda V21)", "docs/36_RONDA_V21_LOTES_SAP_VPN_INVENTARIO.md del proyecto"),
]
story.append(tabla([["Tema", "Fuente"]] + [[a, b] for a, b in fuentes], [8 * cm, 17.7 * cm]))

doc = SimpleDocTemplate(OUT, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.3 * cm,
                        bottomMargin=1.4 * cm, title="Propuesta de servidor - Módulo de Operaciones",
                        author="Proyecto Módulo de Operaciones")
doc.build(story, onFirstPage=pie, onLaterPages=pie)
print("ok", OUT)
