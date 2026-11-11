"""V23 (06-nov-2026): análisis de la demanda proyectada e informe para el Directorio."""
import io
from datetime import date

from flask import Blueprint, render_template, request, send_file

from ..services import demanda_v23 as dm
from .common import perm_required

bp = Blueprint("v23", __name__, url_prefix="/analisis")


@bp.route("/demanda")
@perm_required("demanda.analisis")
def demand():
    hoy = date.today()
    mes = request.args.get("mes") or f"{hoy:%Y-%m}"
    try:
        dm._rango_mes(mes)
    except (ValueError, IndexError):
        mes = f"{hoy:%Y-%m}"
    gran = request.args.get("gran") if request.args.get("gran") in ("DIA", "SEMANA", "MES") else "SEMANA"
    # V28: rango de fechas para ver la ejecución del mes (por defecto, el mes elegido)
    from .common import f_date
    ini, fin = dm._rango_mes(mes)
    desde, hasta = f_date("desde") or ini, f_date("hasta") or fin
    if hasta < desde:
        desde, hasta = hasta, desde
    d = dm.informe(mes, desde=desde, hasta=hasta, gran=gran, hoy=hoy)
    d["ejecucion"] = dm.ejecucion(desde, hasta)
    d["rango"] = (desde, hasta)
    cat_f = request.args.get("ov", "")
    meses = [dm._mes_rel(f"{hoy:%Y-%m}", k) for k in (-3, -2, -1, 0, 1, 2)]
    from ..services import charts
    fs = d["cumplimiento"]["filas"]
    graf = charts.columns([f["periodo"] for f in fs], [("Proyectado", [f["proyectado_kg"] for f in fs]),
                                                       ("Pedido (OV)", [f["pedido_kg"] for f in fs]),
                                                       ("Despachado", [f["despachado_kg"] for f in fs])], "kg",
                          title="Proyectado vs pedido vs despachado")
    html = render_template("v23_demanda.html", d=d, meses=meses, gran=gran, graf=graf, cat_f=cat_f)
    formato = request.args.get("formato")
    if formato in ("pdf", "xlsx"):
        from ..services import pdfreport
        titulo = f"Demanda proyectada y requerimiento · {mes}"
        nombre = f"informe_demanda_{mes}"
        if formato == "pdf":
            return send_file(io.BytesIO(pdfreport.html_to_pdf(html, titulo, "Operaciones · Informe para Gerencia y Directorio")),
                             mimetype="application/pdf", as_attachment=True, download_name=nombre + ".pdf")
        return send_file(io.BytesIO(pdfreport.html_to_xlsx(html, titulo)), as_attachment=True, download_name=nombre + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return html
