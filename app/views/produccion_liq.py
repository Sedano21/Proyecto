"""Liquidación de proceso CP-OPE-004 (30-oct-2026): solo Producción. Lista por línea, SKU y lote; creación desde los
partes de los asistentes; edición del formato (campos, filas y procesos que se agregan o quitan), fotos, impresión y
Excel con el diseño del formato."""
import io
from datetime import date

from flask import abort, current_app, g, render_template, request, send_file, url_for
from sqlalchemy import select

from ..db import db
from ..models import ProcessLiquidation, ProductionLine, ProductionReport
from ..services import process_liq as pl
from ..services.distribution import save_upload
from .common import act, perm_required
from .produccion import bp

VER = ("produccion.liquidacion_proceso", "vista.total")


@bp.route("/liquidacion-proceso", methods=["GET", "POST"])
@perm_required(*VER)
def process_liqs():
    a = request.args
    if request.method == "POST":
        return act(lambda: pl.create(g.user, request.form.getlist("report_id"), request.form.get("variante", "PR")),
                   lambda l: f"Liquidación N° {l.numero:05d} creada con los partes elegidos.", url_for("prod.process_liqs"),
                   redirect_fn=lambda l: url_for("prod.process_liq", lid=l.id))
    q = select(ProcessLiquidation).order_by(ProcessLiquidation.fecha.desc(), ProcessLiquidation.id.desc())
    if a.get("linea"):
        q = q.where(ProcessLiquidation.linea.contains(a["linea"]))
    if a.get("sku"):
        q = q.where(ProcessLiquidation.product_code == a["sku"].strip().upper())
    if a.get("lote"):
        q = q.where(ProcessLiquidation.lote == a["lote"].strip())
    rows = list(db().execute(q.limit(300)).scalars())
    partes = pl.reports_for(a.get("linea", ""), (a.get("sku") or "").strip().upper(), (a.get("lote") or "").strip(), 100)
    usados = {i for x in db().execute(select(ProcessLiquidation.report_ids)).scalars() for i in (x or [])}
    lineas = [x.code for x in db().execute(select(ProductionLine).order_by(ProductionLine.code)).scalars()]
    return render_template("liq_proceso_lista.html", rows=rows, partes=partes, usados=usados, lineas=lineas, a=a,
                           calc=pl.calc)


@bp.route("/liquidacion-proceso/<int:lid>", methods=["GET", "POST"])
@perm_required(*VER)
def process_liq(lid):
    liq = db().get(ProcessLiquidation, lid) or abort(404)
    back = url_for("prod.process_liq", lid=lid)
    if request.method == "POST":
        if "produccion.liquidacion_proceso" not in g.perms:
            abort(403)
        acc = request.form.get("accion")
        if acc == "fotos":
            up = current_app.config["UPLOAD_DIR"]
            return act(lambda: pl.add_photos(g.user, liq, [save_upload(f, up, f"liqproc_{liq.id}")
                                                          for f in request.files.getlist("fotos")]), "Fotos agregadas.", back)
        if acc == "cerrar":
            return act(lambda: pl.close(g.user, pl.update(g.user, liq, request.form)), "Liquidación guardada y cerrada.", back)
        if acc == "reabrir":
            return act(lambda: pl.reopen(g.user, liq), "Liquidación reabierta.", back)
        return act(lambda: pl.update(g.user, liq, request.form), "Liquidación guardada.", back)
    editable = liq.estado != "CERRADA" and "produccion.liquidacion_proceso" in g.perms and request.args.get("imprimir") != "1"
    partes = [db().get(ProductionReport, i) for i in liq.report_ids or []]
    return render_template("liq_proceso.html", liq=liq, c=pl.calc(liq), editable=editable, codigo=pl.CODIGO, pie=pl.pie(),
                           partes=[p for p in partes if p], print_mode=request.args.get("imprimir") == "1")


@bp.route("/liquidacion-proceso/<int:lid>/excel")
@perm_required(*VER)
def process_liq_excel(lid):
    liq = db().get(ProcessLiquidation, lid) or abort(404)
    data = pl.export_excel(liq, current_app.static_folder, current_app.config["UPLOAD_DIR"])
    return send_file(io.BytesIO(data), as_attachment=True, download_name=f"liquidacion_proceso_{liq.numero:05d}_{date.today():%Y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
