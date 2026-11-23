"""Manuales con capturas por rol del área de Almacén (pedido tras la capacitación del 20-nov-2026):
Auxiliar de Almacén, Asistente de Almacén, Líder Operativo y Coordinador (Supervisor) de Almacén.

Crea una base de demostración (solo datos ficticios), deja preparado un picking, un movimiento y un pedido de última
hora, toma las capturas con Chromium entrando con el usuario demo de cada rol y arma un PDF por rol en
docs/capacitacion/almacen/.

Uso:  .venv/bin/python docs/capacitacion/generar_manuales_almacen.py     (requiere Node + Playwright y Chromium)
"""
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
SALIDA = os.path.join(RAIZ, "docs", "capacitacion", "almacen")
LOGO = os.path.join(RAIZ, "app", "static", "img", "logo_corporacion_productiva.png")
CHROME = next((p for p in ("/opt/pw-browsers/chromium", "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome")
               if os.path.exists(p)), None)
CLAVE_DEMO = "Demo2026!"

# ------------------------------------------------------------------ contenido de cada manual
# Cada sección: título, pantalla (ruta), pasos y, si conviene, la parte de la pantalla a capturar (selector CSS).
COMUNES_INICIO = [
    {"t": "Entrar al sistema e inicio", "url": "/", "pasos": [
        "Abra el navegador del celular (Chrome) y entre a la dirección del módulo. Escriba su usuario y su contraseña.",
        "La primera vez acepte el aviso de datos personales y cambie su contraseña por una que recuerde. No la comparta.",
        "En el inicio verá sus alertas y tareas pendientes. La campana de arriba muestra las alertas: púlsela para verlas.",
        "Arriba están «Reportar avería» (máquinas, luz, infraestructura: le llega a Mantenimiento) y «Reportar "
        "observación» (algo del sistema no funciona o tiene una duda: le llega a Sistemas). Adjunte siempre una foto."]},
]
COMUNES_FIN = [
    {"t": "Mensajes (chat) con foto", "url": "/chat/", "pasos": [
        "Pulse el ícono de mensajes arriba. Elija a quién escribir en «Escribir a…».",
        "Escriba el mensaje y, si hace falta, pulse «📷 Foto» para adjuntar una foto (por ejemplo, un saco roto).",
        "Use el chat para coordinar; lo que es una tarea (mover, picar) debe registrarse como tarea para que quede el rastro."]},
    {"t": "Si el sistema le dice que falta un dato", "url": None, "pasos": [
        "Al guardar, si falta algo obligatorio, aparece abajo un aviso rojo que dice exactamente qué falta (por ejemplo, "
        "«Falta adjuntar: Foto de validación en el destino») y el campo queda marcado en rojo. Complételo y vuelva a guardar.",
        "Si algo no funciona, use «Reportar observación» con una foto de la pantalla."]},
]

PICKING_AUX = [
    {"t": "Mis pickings del día", "url": "/almacen/picking", "pasos": [
        "Menú Almacén → «Programación de picking». Ahí están los pickings que le asignaron (por cliente y fecha).",
        "Pulse el picking para abrirlo."]},
    {"t": "Iniciar el picking (con foto)", "url": "@picking_programado", "pasos": [
        "Pulse «Iniciar» y tome la foto de inicio con la cámara del celular. El sistema toma la hora de la foto.",
        "Si la OV es un «pedido grande de última hora», no podrá iniciar hasta que el Líder, el Asistente o el "
        "Coordinador lo valide."]},
    {"t": "Registrar lo picado: el formato ya viene lleno", "url": "@picking_en_proceso", "sel": "#formato", "pasos": [
        "El formato trae el lote, la fecha de producción y la de vencimiento del lote reservado (🔒). Usted solo llena "
        "«Despachado und» y los bultos, y pulsa «Registrar» en cada fila.",
        "Si picó OTRO lote (roto, infestado, difícil acceso), use «Cambiar lote»: elija el lote, el motivo y escriba la "
        "observación. Las fechas del nuevo lote se completan solas.",
        "Si un lote NO alcanza para lo pedido, aparece «Agregar otro lote»: elija el segundo lote y la cantidad que falta.",
        "Si Calidad indicó una etiqueta (por ejemplo, de una marca de terceros), aparece arriba con su foto: péguela."]},
    {"t": "Marcar el picking como listo", "url": "@picking_en_proceso", "pasos": [
        "Cuando todas las líneas están registradas, al final pulse «Marcar listo» con la foto de la mercadería lista "
        "(donde la dejó). Le llega al montacarguista para llevarla a despacho."]},
]
MOVIMIENTOS = [
    {"t": "Movimientos punto a punto (montacarguista)", "url": "/suministro/movimientos", "pasos": [
        "Menú Almacén → «Movimientos punto a punto». Pulse «Solicitar movimiento».",
        "Elija desde dónde y hasta dónde, qué se mueve y la cantidad. Puede agregar otros productos en la misma "
        "solicitud («Otros productos en el mismo movimiento»).",
        "Asígnelo a una persona o a varias a la vez (Ctrl/selección múltiple) si se necesitan dos montacarguistas; o "
        "déjelo para «quien esté disponible». Puede ser inmediato o programado.",
        "Quien lo ejecuta lo inicia con la foto del origen y lo termina con la foto del destino; puede adjuntar más fotos "
        "y anotar en qué rack quedó el lote."]},
]
STOCK = [
    {"t": "Stock y reservas, ubicación del lote", "url": "/almacen/stock", "pasos": [
        "Menú Almacén → «Stock y reservas». Filtre por almacén, producto o estado.",
        "Disponible es lo que se puede usar; Reservado ya está comprometido para un cliente; Observado, En fumigación o "
        "Pendiente de revisión no se usan hasta que Calidad decida.",
        "Ubicación: escriba el rack (p. ej. A-01-2). Si el lote está en varios lugares, escriba «A-01-2: 30; B-03-1: 20».",
        "Si un lote llegó roto o con plaga, cámbielo a Observado con el motivo; solo Calidad lo libera."]},
]
LIDER = [
    {"t": "Asignar el picking (persona o grupo)", "url": "@picking_programado", "sel": None, "pasos": [
        "Almacén → «Programación de picking». El sistema preprograma el picking por cliente y fecha.",
        "Abra el picking, elija «Una persona» o «Un grupo» y quiénes reportan en el sistema. Guarde: a cada uno le llega "
        "su alerta.",
        "Valide la planificación del picking y, en esta etapa de prueba, valide que lo picado esté correcto."]},
    {"t": "Pedidos grandes de última hora", "url": "/almacen/pedidos-ultima-hora", "pasos": [
        "Almacén → «Pedidos de última hora». Aquí llegan las OV grandes para hoy o mañana registradas tarde por Comercial.",
        "Revise productos y cantidades y pulse «Validar: se prepara» u «Observar» (con el motivo). Comercial recibe la "
        "respuesta. Hasta validarla, no se puede iniciar su picking."]},
    {"t": "Consolidado del picking (PDF / Excel)", "url": "/almacen/consolidado", "pasos": [
        "Almacén → «Consolidado del picking». Elija fechas y, si quiere, cliente, sede, producto o almacén.",
        "Agrupe por cliente, fecha, sede, producto o almacén: suma lo que falta preparar de varias OV (p. ej. varias sedes "
        "del mismo cliente).",
        "Descárguelo en PDF o Excel con los botones de arriba (reemplaza la tabla dinámica hecha a mano)."]},
]
ASISTENTE_EXTRA = [
    {"t": "Requerimientos a Producción", "url": "/produccion/", "pasos": [
        "Almacén → «Requerimientos a Producción». Registre el producto, la cantidad y la fecha requerida (reemplaza la "
        "pizarra). Producción recibe la alerta y lo incluye en su planificación."]},
    {"t": "Ingresos a almacén y liquidaciones de producción (consulta)", "url": "/almacen/ingresos", "pasos": [
        "Almacén → «Ingresos a almacén»: lo que entra por compras y producción.",
        "Producción → «Liquidaciones» y «Monitoreo en tiempo real»: lo que se produce y lo que pasa de producción a almacén."]},
]
COORD = [
    {"t": "Traslados entre almacenes", "url": "/almacen/traslados", "pasos": [
        "Almacén → «Traslados». Se solicita, se autoriza, se registra la salida y el almacén destino confirma la recepción.",
        "Al confirmar la recepción, el traslado se registra también en SAP (columna Estado: «SAP: transferencia N°»)."]},
    {"t": "Conteos físicos", "url": "/almacen/conteos", "pasos": [
        "Almacén → «Conteos físicos». Abra un conteo del almacén, registre lo contado y valide; los ajustes requieren "
        "autorización."]},
    {"t": "Lotes y variantes", "url": "/almacen/lotes", "pasos": [
        "Almacén → «Lotes y variantes»: lotes con diferencias para revisar, filtro por almacén o estado."]},
]

MANUALES = [
    {"archivo": "Manual_Auxiliar_de_Almacen.pdf", "rol": "Auxiliar de Almacén", "usuario": "aux.almacen", "movil": True,
     "intro": "Para quien hace el picking y apoya los movimientos.",
     "secciones": COMUNES_INICIO + PICKING_AUX + MOVIMIENTOS + STOCK + COMUNES_FIN},
    {"archivo": "Manual_Asistente_de_Almacen.pdf", "rol": "Asistente de Almacén", "usuario": "asist.almacen", "movil": False,
     "intro": "Hace lo mismo que el Líder Operativo y, además, requerimientos a Producción y consultas de ingresos y "
              "liquidaciones.",
     "secciones": COMUNES_INICIO + LIDER + PICKING_AUX + MOVIMIENTOS + STOCK + ASISTENTE_EXTRA + COMUNES_FIN},
    {"archivo": "Manual_Lider_Operativo.pdf", "rol": "Líder Operativo", "usuario": "lider.almacen", "movil": False,
     "intro": "Asigna el picking, valida lo picado y los pedidos de última hora, y organiza los movimientos.",
     "secciones": COMUNES_INICIO + LIDER + PICKING_AUX + MOVIMIENTOS + STOCK + ASISTENTE_EXTRA + COMUNES_FIN},
    {"archivo": "Manual_Coordinador_de_Almacen.pdf", "rol": "Coordinador (Supervisor) de Almacén", "usuario": "coord.almacen",
     "movil": False, "intro": "Supervisa el almacén: stock, traslados, conteos, consolidado y validaciones.",
     "secciones": COMUNES_INICIO + STOCK + LIDER + COORD + MOVIMIENTOS + COMUNES_FIN},
]


# ------------------------------------------------------------------ base de demostración preparada
def preparar_demo(db_path, uploads):
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ.setdefault("SECRET_KEY", "manuales")
    from app import create_app
    app = create_app({"DATABASE_URL": f"sqlite:///{db_path}", "UPLOAD_DIR": uploads, "DEMO_MODE": True})
    rutas = {}
    with app.app_context():
        from app.seed import seed_catalogs, seed_demo
        seed_catalogs()
        seed_demo(os.path.join(uploads, "demo"))
        from app.db import SessionLocal
        from app.models import PickingTask, User
        from app.services import picking as pk
        from app.services.core import set_param
        from app.services.orders import create_order
        s = SessionLocal()
        U = lambda n: s.query(User).filter_by(username=n).one()  # noqa: E731
        set_param("hora_corte_ov_dia_siguiente", "")
        from app.models import Customer
        cli = s.query(Customer).first()
        aux, lider = U("aux.almacen"), U("lider.almacen")
        hechas = []
        for i, q in enumerate((20, 30)):
            o = create_order(U("coord.ventas"), f"DEMO-MAN-{i + 1}", cli.id, date.today() + timedelta(days=1),
                             [{"product_code": "PT-901", "cantidad": q, "precio_unitario": 999}], oc_archivo="oc_demo.pdf")
            s.flush()
            t = pk.tasks_of(o)
            if t:
                pk.assign(t[0], lider, [aux.id, U("asist.almacen").id, lider.id])
                hechas.append(t[0])
        if hechas:
            pk.start(hechas[0], aux, "demo_inicio.jpg")
            rutas["picking_en_proceso"] = f"/almacen/picking/{hechas[0].id}"
            rutas["picking_programado"] = f"/almacen/picking/{hechas[-1].id}"
        # pedido grande de última hora por validar
        set_param("almacen_ov_tardia_hora", "00:00")
        set_param("almacen_ov_tardia_unidades", 100)
        create_order(U("coord.ventas"), "DEMO-MAN-GRANDE", cli.id, date.today() + timedelta(days=1),
                     [{"product_code": "PT-901", "cantidad": 150, "precio_unitario": 999}], oc_archivo="oc_demo.pdf")
        from app.services import etiquetas, supply
        etiquetas.guardar(U("jefe.calidad"), "PT-901", marca="MARCA DEMO", instrucciones="Una etiqueta por caja, en la cara frontal.")
        supply.request_move(lider, "RACK A-01", "ZONA DESPACHO", carga={"tipo": "PALLET_PT", "cantidad": 2, "producto": "PT-901"},
                            equipo=[str(U("montacarguista").id), str(U("montacarguista2").id)])
        s.commit()
    return rutas


def _puerto():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


CAPTURAR_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const cfg = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
  const b = await chromium.launch({ executablePath: cfg.chrome, args: ['--no-sandbox'] });
  for (const m of cfg.manuales) {
    const ctx = await b.newContext(m.movil ? { viewport: { width: 412, height: 860 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }
                                           : { viewport: { width: 1280, height: 820 }, deviceScaleFactor: 1 });
    const p = await ctx.newPage();
    await p.goto(cfg.base + '/login');
    await p.fill('input[name=username]', m.usuario);
    await p.fill('input[name=password]', cfg.clave);
    await p.press('input[name=password]', 'Enter');
    await p.waitForLoadState('networkidle');
    for (const c of m.capturas) {
      try {
        await p.goto(cfg.base + c.url, { waitUntil: 'networkidle' });
        await p.addStyleTag({ content: '#aviso-falta,.demo-strip,#aviso-push{display:none!important}' });
        if (c.sel && await p.$(c.sel)) { await (await p.$(c.sel)).screenshot({ path: c.out }); }
        else { await p.screenshot({ path: c.out }); }
        console.log('ok', m.usuario, c.url);
      } catch (e) { console.log('fallo', m.usuario, c.url, String(e).slice(0, 120)); }
    }
    await ctx.close();
  }
  await b.close();
})();
"""

PDF_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const jobs = JSON.parse(process.argv[2]);
  const b = await chromium.launch({ executablePath: process.argv[3], args: ['--no-sandbox'] });
  const p = await b.newPage();
  for (const j of jobs) {
    await p.goto('file://' + j.html, { waitUntil: 'load' });
    await p.pdf({ path: j.pdf, format: 'A4', printBackground: true, displayHeaderFooter: true, headerTemplate: '<span></span>',
      footerTemplate: '<div style="font-size:7.5pt;color:#7b8794;width:100%;padding:0 15mm;display:flex;justify-content:space-between">' +
        '<span>Corporación Productiva · Módulo de Operaciones · ' + j.rol + '</span><span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>',
      margin: { top: '14mm', bottom: '16mm', left: '14mm', right: '14mm' } });
    console.log(j.pdf);
  }
  await b.close();
})();
"""

CSS = """
@page { size: A4; }
body { font-family: "Segoe UI", Arial, sans-serif; color: #1f2933; font-size: 10.5pt; line-height: 1.45; }
.portada { height: 250mm; display: flex; flex-direction: column; justify-content: space-between; page-break-after: always; }
.portada img { width: 65mm; } .portada .b { border-left: 6px solid #0b7a3b; padding: 6mm 0 6mm 8mm; }
.portada h1 { font-size: 26pt; color: #12324f; margin: 2mm 0; } .k { color: #0b7a3b; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
h2 { font-size: 14pt; color: #12324f; border-bottom: 2px solid #0b7a3b; padding-bottom: 1mm; margin-top: 8mm; page-break-after: avoid; }
ol { padding-left: 6mm; } li { margin: 1mm 0; }
.cap { text-align: center; margin: 3mm 0 2mm; page-break-inside: avoid; }
.cap img { max-width: 100%; max-height: 120mm; border: 1px solid #d9e2ec; border-radius: 4px; }
.cap.movil img { max-height: 135mm; }
.sec { page-break-inside: avoid; }
.indice li { margin: .5mm 0; } .nota { background: #e8f5ee; border-left: 4px solid #0b7a3b; padding: 3mm 4mm; font-size: 9.5pt; }
"""


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def html_manual(m, caps):
    logo = f'<img src="data:image/png;base64,{_b64(LOGO)}" alt="">' if os.path.exists(LOGO) else ""
    partes = [f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>",
              f"<div class='portada'>{logo}<div class='b'><div class='k'>Manual con capturas · Almacén</div><h1>{m['rol']}</h1>"
              f"<div>{m['intro']}</div></div><div style='font-size:9pt;color:#7b8794'>Corporación Productiva · Módulo de "
              f"Operaciones · {datetime.now():%d/%m/%Y}. Las capturas son de la base de demostración (datos ficticios).</div></div>",
              "<h2>Contenido</h2><ol class='indice'>" + "".join(f"<li>{s['t']}</li>" for s in m["secciones"]) + "</ol>",
              "<div class='nota'>Si algo no funciona o tiene una duda, use «Reportar observación» (con foto). Si una máquina, la "
              "luz o la infraestructura fallan, use «Reportar avería».</div>"]
    for i, s in enumerate(m["secciones"], 1):
        partes.append(f"<div class='sec'><h2>{i}. {s['t']}</h2><ol>" + "".join(f"<li>{p}</li>" for p in s["pasos"]) + "</ol>")
        img = caps.get(i)
        if img and os.path.exists(img):
            partes.append(f"<div class='cap {'movil' if m['movil'] else ''}'><img src='data:image/png;base64,{_b64(img)}' alt=''></div>")
        partes.append("</div>")
    partes.append("</body></html>")
    return "".join(partes)


def main():
    if CHROME is None:
        sys.exit("No se encontró Chromium (/opt/pw-browsers).")
    os.makedirs(SALIDA, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="manuales_alm_")
    db_path, uploads = os.path.join(tmp, "demo.db"), os.path.join(tmp, "up")
    os.makedirs(uploads, exist_ok=True)
    rutas = preparar_demo(db_path, uploads)
    puerto = _puerto()
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db_path}", SECRET_KEY="manuales", PORT=str(puerto), UPLOAD_DIR=uploads)
    srv = subprocess.Popen([sys.executable, os.path.join(RAIZ, "run.py")], cwd=RAIZ, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", puerto), 1).close()
                break
            except OSError:
                time.sleep(.5)
        cfg = {"chrome": CHROME, "base": f"http://127.0.0.1:{puerto}", "clave": CLAVE_DEMO, "manuales": []}
        caps = {}
        for k, m in enumerate(MANUALES):
            lista = []
            for i, s in enumerate(m["secciones"], 1):
                url = s.get("url")
                if not url:
                    continue
                if url.startswith("@"):
                    url = rutas.get(url[1:])
                    if not url:
                        continue
                out = os.path.join(tmp, f"m{k}_s{i}.png")
                lista.append({"url": url, "out": out, "sel": s.get("sel")})
                caps.setdefault(k, {})[i] = out
            cfg["manuales"].append({"usuario": m["usuario"], "movil": m["movil"], "capturas": lista})
        cfgf = os.path.join(tmp, "cfg.json")
        json.dump(cfg, open(cfgf, "w"))
        js = os.path.join(tmp, "capturar.js")
        open(js, "w").write(CAPTURAR_JS)
        subprocess.run(["node", js, cfgf], check=True, cwd=tmp)
    finally:
        srv.terminate()
    trabajos = []
    for k, m in enumerate(MANUALES):
        h = os.path.join(tmp, m["archivo"].replace(".pdf", ".html"))
        open(h, "w", encoding="utf-8").write(html_manual(m, caps.get(k, {})))
        trabajos.append({"html": h, "pdf": os.path.join(SALIDA, m["archivo"]), "rol": m["rol"]})
    js = os.path.join(tmp, "pdf.js")
    open(js, "w").write(PDF_JS)
    subprocess.run(["node", js, json.dumps(trabajos), CHROME], check=True, cwd=tmp)


if __name__ == "__main__":
    main()
