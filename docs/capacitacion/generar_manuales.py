"""Genera los PDF de capacitación desde docs/47_INSTRUCTIVO_CAPACITACION_MARCHA_BLANCA.md:
un manual general (Parte A + anexo) y uno por área (B1…B11), con portada, registro de asistencia y lista de entrega.
Uso:  .venv/bin/python docs/capacitacion/generar_manuales.py      (requiere el paquete «markdown» y Chromium/Playwright)"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile

import markdown

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FUENTE = os.path.join(RAIZ, "docs", "47_INSTRUCTIVO_CAPACITACION_MARCHA_BLANCA.md")
SALIDA = os.path.join(RAIZ, "docs", "capacitacion")
LOGO = os.path.join(RAIZ, "app", "static", "img", "logo_corporacion_productiva.png")
CHROME = next((p for p in ("/opt/pw-browsers/chromium", "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome")
               if os.path.exists(p)), None)

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #1f2933; font-size: 10.5pt; line-height: 1.45; }
.portada { height: 255mm; display: flex; flex-direction: column; justify-content: space-between; page-break-after: always; }
.portada img { width: 70mm; }
.portada .bloque { border-left: 6px solid #0b7a3b; padding: 6mm 0 6mm 8mm; }
.portada .kicker { color: #0b7a3b; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: 10pt; }
.portada h1 { font-size: 26pt; margin: 3mm 0 2mm; color: #12324f; border: 0; }
.portada .sub { font-size: 13pt; color: #52606d; }
.portada .pie { font-size: 9pt; color: #7b8794; border-top: 1px solid #d9e2ec; padding-top: 3mm; }
h1 { font-size: 17pt; color: #12324f; border-bottom: 3px solid #0b7a3b; padding-bottom: 2mm; margin-top: 0; }
h2 { font-size: 14pt; color: #12324f; margin-top: 7mm; border-bottom: 1px solid #d9e2ec; padding-bottom: 1mm; page-break-after: avoid; }
h3 { font-size: 11.5pt; color: #0b7a3b; margin-top: 5mm; page-break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 6mm; margin: 1.5mm 0; }
li { margin: .8mm 0; }
strong { color: #12324f; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt; background: #f0f4f8; padding: 0 1mm; border-radius: 2px; }
pre { background: #f0f4f8; padding: 3mm; border-radius: 3px; font-size: 8.5pt; white-space: pre-wrap; }
table { width: 100%; border-collapse: collapse; margin: 3mm 0; font-size: 9.5pt; page-break-inside: avoid; }
th { background: #12324f; color: #fff; text-align: left; padding: 1.8mm 2mm; }
td { border-bottom: 1px solid #d9e2ec; padding: 1.8mm 2mm; vertical-align: top; }
tr:nth-child(even) td { background: #f7f9fb; }
hr { display: none; }
.nota { background: #e8f5ee; border-left: 4px solid #0b7a3b; padding: 3mm 4mm; margin: 4mm 0; font-size: 9.5pt; }
.salto { page-break-before: always; }
.firmas td { height: 10mm; }
"""


def _logo():
    with open(LOGO, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s")


def _normalizar(txt):
    """El Markdown del instructivo usa sangría de 2-3 espacios en las sublistas y listas pegadas al párrafo anterior;
    Python-Markdown necesita 4 espacios por nivel y una línea en blanco antes de la lista."""
    out, pila = [], []  # pila: sangrías originales de los niveles abiertos
    for linea in txt.split("\n"):
        m = _ITEM.match(linea)
        if m:
            ind = len(m.group(1))
            while pila and ind < pila[-1]:
                pila.pop()
            if not pila or ind > pila[-1]:
                if not pila and out and out[-1].strip() and not _ITEM.match(out[-1]):
                    out.append("")
                pila.append(ind)
            nivel = len(pila) - 1
            out.append(" " * (4 * nivel) + linea.lstrip())
        elif pila and linea.strip() and linea.startswith(" "):
            out.append(" " * (4 * len(pila)) + linea.lstrip())  # continuación de un ítem
        else:
            if linea.strip():
                pila = []
            out.append(linea)
    return "\n".join(out)


def _md(txt):
    return markdown.markdown(_normalizar(txt), extensions=["tables", "sane_lists"])


def _portada(titulo, sub, version):
    return (f'<section class="portada"><img src="{_logo()}" alt="Corporación Productiva">'
            f'<div class="bloque"><div class="kicker">Módulo de Operaciones · Capacitación y marcha blanca</div>'
            f'<h1>{titulo}</h1><div class="sub">{sub}</div></div>'
            f'<div class="pie">{version} · Documento de uso interno. Detalle de cada pantalla: «Manual de usuario» dentro del sistema.</div></section>')


def _asistencia(area):
    filas = "".join("<tr><td></td><td></td><td></td><td></td></tr>" for _ in range(14))
    return (f'<div class="salto"></div><h1>Registro de capacitación · {area}</h1>'
            '<p>Fecha: ______________ &nbsp;&nbsp; Hora: ________ &nbsp;&nbsp; Facilitador: ______________________________</p>'
            '<table class="firmas"><tr><th style="width:36%">Nombre y apellido</th><th style="width:24%">Cargo / perfil</th>'
            f'<th style="width:18%">Usuario del sistema</th><th>Firma</th></tr>{filas}</table>')


def secciones():
    txt = open(FUENTE, encoding="utf-8").read()
    version = re.search(r"\*\*(Corporación Productiva · Versión[^*]+)\*\*", txt).group(1)
    a = txt[txt.index("# PARTE A"):txt.index("# PARTE B")]
    anexo = txt[txt.index("# Anexo"):]
    b = txt[txt.index("# PARTE B"):txt.index("# Anexo")]
    areas = re.split(r"\n(?=## B\d+\. )", b)[1:]
    return version, a, anexo, [x.strip().rstrip("-").strip() for x in areas]


def _html(cuerpo):
    return f'<!doctype html><html lang="es"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{cuerpo}</body></html>'


def documentos():
    version, a, anexo, areas = secciones()
    docs = [("00_Manual_general_capacitacion.pdf",
             _html(_portada("Instructivo general", "Para todo el personal · cómo entrar, usar el sistema y reportar durante la marcha blanca", version)
                   + _md(a.replace("# PARTE A · ", "# ")) + '<div class="salto"></div>' + _md(anexo) + _asistencia("Sesión general")))]
    for sec in areas:
        m = re.match(r"## (B\d+)\. ([^\n(]+)(\(([^)]*)\))?", sec)
        codigo, nombre, perfiles = m.group(1), m.group(2).strip(), (m.group(4) or "").strip()
        cuerpo = sec.replace(m.group(0), f"# {nombre}" + (f"\n\n**Perfiles:** {perfiles}" if perfiles else ""), 1)
        recuerde = ('<div class="nota"><b>Antes de empezar:</b> este instructivo complementa el <b>Instructivo general</b> '
                    '(ingreso, alertas, notificaciones, mensajes, «Reportar observación» y «Reportar avería», reglas de la marcha '
                    'blanca). Lo no descrito aquí está en el <b>Manual de usuario</b> del sistema, que muestra solo las pantallas '
                    'de su perfil.</div>')
        archivo = f"{int(codigo[1:]):02d}_Manual_{re.sub(r'[^A-Za-z0-9]+', '_', _sin_tildes(nombre)).strip('_')}.pdf"
        docs.append((archivo, _html(_portada(nombre, f"Instructivo del área{(' · ' + perfiles) if perfiles else ''}", version)
                                    + recuerde + _md(cuerpo) + '<div class="salto"></div>' + _md(anexo) + _asistencia(nombre))))
    return docs


def _sin_tildes(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def main():
    if CHROME is None:
        sys.exit("No se encontró Chromium (/opt/pw-browsers).")
    os.makedirs(SALIDA, exist_ok=True)
    tmp = tempfile.mkdtemp()
    trabajos = []
    for archivo, html in documentos():
        h = os.path.join(tmp, archivo.replace(".pdf", ".html"))
        open(h, "w", encoding="utf-8").write(html)
        trabajos.append({"html": h, "pdf": os.path.join(SALIDA, archivo)})
    js = """
const { chromium } = require('playwright');
(async () => {
  const jobs = JSON.parse(process.argv[2]);
  const b = await chromium.launch({ executablePath: process.argv[3], args: ['--no-sandbox'] });
  const p = await b.newPage();
  for (const j of jobs) {
    await p.goto('file://' + j.html, { waitUntil: 'load' });
    await p.pdf({ path: j.pdf, format: 'A4', printBackground: true, displayHeaderFooter: true,
      headerTemplate: '<span></span>',
      footerTemplate: '<div style="font-size:7.5pt;color:#7b8794;width:100%;padding:0 15mm;display:flex;justify-content:space-between">' +
        '<span>Corporación Productiva · Módulo de Operaciones · Capacitación</span><span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>',
      margin: { top: '16mm', bottom: '18mm', left: '15mm', right: '15mm' } });
    console.log(j.pdf);
  }
  await b.close();
})();
"""
    jsf = os.path.join(tmp, "imprimir.js")
    open(jsf, "w").write(js)
    subprocess.run(["node", jsf, json.dumps(trabajos), CHROME], check=True, cwd=tmp)


if __name__ == "__main__":
    main()
