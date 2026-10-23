"""Informes por área con gráficos, tendencias y recomendaciones (observaciones al demo v0.5, 13-oct)."""
from flask import Blueprint, abort, g, render_template, request, send_file

from ..services import charts
from ..services import reports as rsvc
from .common import f_date, login_required

bp = Blueprint("rep", __name__, url_prefix="/informes")

# informe -> (título, permisos que lo habilitan)
INFORMES = {
    "comercial": ("Comercial", ("informes.comercial",)),
    "reempaque": ("Reempaque", ("informes.reempaque",)),
    "produccion": ("Producción", ("informes.produccion",)),
    "distribucion": ("Distribución", ("informes.distribucion",)),
    "almacen": ("Movimiento de stock del almacén", ("informes.almacen",)),
    "cumplimiento": ("Interacciones y cumplimiento por persona", ("informes.cumplimiento",)),
}


def disponibles():
    return [(k, t) for k, (t, perms) in INFORMES.items() if any(p in g.perms for p in perms) or "vista.total" in g.perms]


def _periodo():
    try:
        return f_date("desde"), f_date("hasta")
    except Exception:  # noqa: BLE001
        return None, None


@bp.route("/personalizado")
@login_required
def custom():
    """Arme su informe (obs. demo v0.7): fuente, columnas, periodo, filtro y agrupación; pantalla, PDF o Excel."""
    import io
    from ..services import custom_report as cr
    from ..services import pdfreport
    fuentes = cr.sources_for(g.user)
    if not fuentes:
        abort(403)
    fuente = request.args.get("fuente") or next(iter(fuentes))
    if fuente not in fuentes:
        abort(403)
    desde, hasta = _periodo()
    r = None
    if request.args.get("ver") or request.args.get("formato"):
        r = cr.run(g.user, fuente, request.args.getlist("col"), desde, hasta, request.args.get("q", ""),
                   request.args.get("agrupar", ""))
        nombre = f"informe_{fuente}_{r['hasta']:%Y%m%d}"
        elementos = request.args.getlist("elem") or ["tabla", "grafico", "kpis", "recomendaciones"]
        notas_pdf = r["notas"] + ([f"{k}: {v}" for k, v in r["kpis"]] if "kpis" in elementos else []) + (
            ["Recomendación: " + x for x in r["recomendaciones"]] if "recomendaciones" in elementos else [])
        if request.args.get("formato") == "pdf":
            return send_file(io.BytesIO(pdfreport.table_pdf(r["titulo"], r["columnas"], r["filas"] if "tabla" in elementos else [],
                                                            notas_pdf)),
                             mimetype="application/pdf", as_attachment=True, download_name=nombre + ".pdf")
        if request.args.get("formato") == "xlsx":
            from openpyxl import Workbook
            from openpyxl.styles import Font
            wb = Workbook()
            ws = wb.active
            ws.title = r["titulo"][:30]
            ws.append([r["titulo"]])
            ws["A1"].font = Font(bold=True, size=12)
            for n in notas_pdf:
                ws.append([n])
            ws.append(r["columnas"])
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
            for f in r["filas"]:
                ws.append(list(f))
            out = io.BytesIO()
            wb.save(out)
            return send_file(io.BytesIO(out.getvalue()), as_attachment=True, download_name=nombre + ".xlsx",
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elementos = request.args.getlist("elem") or ["tabla", "grafico", "kpis", "recomendaciones"]
    grafico = None
    if r is not None and "grafico" in elementos:
        med = request.args.get("medida")
        grafico = cr.chart(r, request.args.get("tipo_grafico", "barras"), int(med) if (med or "").isdigit() else None)
    return render_template("informe_personalizado.html", fuentes=fuentes, fuente=fuente, columnas=cr.columns(fuente),
                           r=r, sel=request.args.getlist("col"), items=disponibles(), por_area=cr.sources_by_area(g.user),
                           elementos=elementos, grafico=grafico)


@bp.route("/")
@login_required
def home():
    from ..services.custom_report import sources_for
    items = disponibles()
    if not items and not sources_for(g.user):
        abort(403)
    return render_template("informes_home.html", items=items)


def _descarga(html, titulo):
    """Obs. demo v0.7: cada informe se descarga en PDF (y sus tablas en Excel) tal como se ve en pantalla."""
    import io
    from datetime import date
    from ..services import pdfreport
    formato = request.args.get("formato")
    nombre = "informe_" + "".join(ch if ch.isalnum() else "_" for ch in titulo.lower()).strip("_") + f"_{date.today():%Y%m%d}"
    if formato == "pdf":
        return send_file(io.BytesIO(pdfreport.html_to_pdf(html, f"Informe {titulo}")), mimetype="application/pdf",
                         as_attachment=True, download_name=nombre + ".pdf")
    if formato == "xlsx":
        return send_file(io.BytesIO(pdfreport.html_to_xlsx(html, f"Informe {titulo}")), as_attachment=True,
                         download_name=nombre + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return html


@bp.route("/<nombre>")
@login_required
def show(nombre):
    if nombre not in INFORMES or nombre not in dict(disponibles()):
        abort(403)
    return _descarga(_show(nombre), INFORMES[nombre][0])


def _show(nombre):
    desde, hasta = _periodo()
    if nombre == "comercial":
        fa = request.args
        vend = fa.get("vendedor", "")
        if g.user.role_code == "EJECUTIVO_VENTAS":  # el ejecutivo ve lo suyo
            vend = g.user.nombre
        d = rsvc.comercial(desde, hasta, ver_costos="costos.ver" in g.perms, canal=fa.get("canal", ""),
                           customer_id=fa.get("customer_id") or None, vendedor=vend, tipo=fa.get("tipo", ""))
        from sqlalchemy import select
        from ..db import db
        from ..models import Customer
        from ..services import kpis as kpisvc
        from ..services import prices as prsvc
        clientes = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
        filtros = {"canales": sorted({prsvc.channel_of(c) for c in clientes} - {"", None}), "clientes": clientes,
                   "vendedores": sorted({v for v, _ in d["vendedores"]})}
        k = kpisvc.compute(desde, hasta)
        d["tiempos"] = {"preparacion_h": k.get("tiempo_preparacion_h"), "despacho_h": k.get("tiempo_despacho_h")}
        graf = {"semanal": charts.line([("Ventas S/", d["serie_semanal"])], "S/", title="Ventas semanales"),
                "vend_soles": charts.bars([(k, v["soles"]) for k, v in d["vendedores"]], "S/", title="Ventas por vendedor (S/)"),
                "vend_kg": charts.bars([(k, v["kg"]) for k, v in d["vendedores"]], "kg", title="Ventas por vendedor (kg)", color=2),
                "top": charts.bars([(f"{k} {n[:18]}", v) for k, n, v, _ in d["top_productos"]], "S/", title="Productos más vendidos"),
                "pres": charts.bars([(str(k), v) for k, v in d["presentaciones"]], "", title="Presentaciones preferidas", color=6),
                "margen": charts.bars([(f"{k} {n[:16]}", m) for k, n, m in d["margen_producto"][:15]], "%",
                                      title="Margen por producto (menores primero)", color=2)}
        from ..services.customer_behavior import behavior
        cb = behavior(d["desde"], d["hasta"])
        graf["cumplimiento"] = charts.bars([(x["customer"].nombre[:22], x["cumplimiento"] or 0) for x in cb["clientes"][:15]], "%",
                                           title="Cumplimiento por cliente (entregados completos / pedidos)", color=2)
        graf["top_kg"] = charts.bars([(f"{k} {n[:18]}", v) for k, n, v, _ in d["top_kg"]], "kg", title="Productos más vendidos (kg)", color=2)
        return render_template("informe_comercial.html", d=d, cb=cb, graf=graf, items=disponibles(), actual=nombre, filtros=filtros)
    if nombre == "almacen":
        from ..services.core import warehouse_scopes
        propios = warehouse_scopes().get(g.user.role_code)
        if propios is None and g.user.almacen:
            propios = [g.user.almacen]
        propios = [w for w in (propios or []) if not w.endswith("*")]
        wh = request.args.get("almacen") or ""
        if propios and wh and wh not in propios:
            abort(403)
        d = rsvc.almacen(desde, hasta, wh or None, propios)
        graf = charts.line([("Stock total (unidades)", d["serie"])], "und", title="Stock en cada carga de SAP")
        return render_template("informe_almacen.html", d=d, graf=graf, propios=propios, items=disponibles(), actual=nombre)
    if nombre == "produccion":
        d = rsvc.produccion(desde, hasta)
        cap = rsvc.produccion_capacidad(desde, hasta, request.args.get("agrupar", "DIA"), request.args.get("n") or 7)
        etiqueta = (lambda b: f"{b:%m/%Y}") if cap["agrupar"] == "MES" else (lambda b: f"{b:%d/%m}")
        graf_cap = charts.line([(f["grupo"], [(etiqueta(x["bucket"]), x["uso"] or 0) for x in f["serie"]]) for f in cap["filas"]
                                if f["capacidad"]], "%", title="Uso de capacidad por línea")
        graf_prog = charts.bars([(f["grupo"], f["cumplimiento"] or 0) for f in cap["filas"] if f["programado"]], "%",
                                title="Programado vs ejecutado (cumplimiento)", color=2)
        return render_template("informe_produccion.html", d=d, cap=cap, graf_cap=graf_cap, graf_prog=graf_prog,
                               charts=charts, items=disponibles(), actual=nombre)
    if nombre == "cumplimiento":
        from datetime import date, timedelta
        from ..services.shifts import compliance
        d = compliance(desde or date.today() - timedelta(days=6), hasta or date.today())
        return render_template("informe_cumplimiento.html", d=d, items=disponibles(), actual=nombre)
    fn = getattr(rsvc, nombre)
    d = fn(desde, hasta)
    return render_template(f"informe_{nombre}.html", d=d, charts=charts, items=disponibles(), actual=nombre)


@bp.route("/comercial/cliente/<int:cid>")
@login_required
def customer_behavior(cid):
    """Detalle del comportamiento de un cliente: cada OV con su atención, retraso, rechazos, modificaciones y penalidad."""
    if "informes.comercial" not in g.perms and "vista.total" not in g.perms:
        abort(403)
    return _descarga(_customer_behavior(cid), "Comportamiento del cliente")


def _customer_behavior(cid):
    from ..services.customer_behavior import behavior
    desde, hasta = _periodo()
    d = behavior(desde, hasta, cid)
    if not d["clientes"]:
        from ..db import db
        from ..models import Customer
        c = db().get(Customer, cid) or abort(404)
        return render_template("informe_cliente.html", d=d, c=None, cliente=c, items=disponibles(), actual="comercial")
    return render_template("informe_cliente.html", d=d, c=d["clientes"][0], cliente=d["clientes"][0]["customer"],
                           items=disponibles(), actual="comercial")
