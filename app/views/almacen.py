"""Vistas de Almacén: stock y estados, cargas de archivos, conteos, traslados y reempaques."""
import os
import uuid

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from ..catalogs import REPACK_TYPES
from ..db import db
from ..models import (PhysicalCount, Product, RepackRequest, StockLot, Transfer, UploadBatch, UploadRow, Warehouse)
from ..services import inventory as isvc
from ..services import repack as rsvc
from ..services import transfers as tsvc
from ..services import uploads as usvc
from ..services.core import BusinessError
from ..services.stock import (ESTADOS_FISICOS, ESTADOS_LABEL, base_qty, change_lot_state, free_qty, product_stock_summary,
                              reserved_qty)
from .common import act, f_date, f_float, fail, perm_required

bp = Blueprint("alm", __name__, url_prefix="/almacen")


@bp.route("/stock")
@perm_required("stock.ver")
def stock():
    q = (request.args.get("q") or "").strip().upper()
    wh = request.args.get("almacen") or ""
    est = request.args.get("estado") or ""
    stmt = select(StockLot).where(StockLot.cantidad > 0)
    if q:
        stmt = stmt.join(Product).where((StockLot.product_code.like(f"%{q}%")) | (Product.descripcion.like(f"%{q}%")))
    if wh:
        stmt = stmt.where(StockLot.warehouse_code == wh)
    if est:
        stmt = stmt.where(StockLot.estado == est)
    lots = list(db().execute(stmt.order_by(StockLot.product_code, StockLot.fecha_venc).limit(800)).scalars())
    codes = sorted({l.product_code for l in lots})
    resumen = {c: product_stock_summary(c) for c in codes[:300]}
    whs = list(db().execute(select(Warehouse).order_by(Warehouse.prioridad, Warehouse.code)).scalars())
    return render_template("stock.html", lots=lots, resumen=resumen, q=q, wh=wh, est=est, whs=whs, estados=ESTADOS_FISICOS,
                           labels=ESTADOS_LABEL, reserved=reserved_qty, free=free_qty, base=base_qty)


@bp.route("/lote/<int:lid>/estado", methods=["POST"])
@perm_required("stock.cambiar_estado", "calidad.liberar")
def lot_state(lid):
    lot = db().get(StockLot, lid) or abort(404)
    nuevo = request.form.get("estado")
    if nuevo == "DISPONIBLE" and "calidad.liberar" not in g.perms and lot.estado in ("PENDIENTE_REVISION", "NO_UTILIZABLE",
                                                                                   "EN_FUMIGACION"):
        return fail("La liberación a Disponible la realiza Calidad.", request.referrer or url_for("alm.stock"))
    return act(lambda: change_lot_state(lot, nuevo, g.user, request.form.get("motivo", "")),
               f"Lote {lot.lote} actualizado.", request.referrer or url_for("alm.stock"))


# ------------------------------- cargas ------------------------------------
@bp.route("/cargas")
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar")
def uploads():
    rows = list(db().execute(select(UploadBatch).order_by(UploadBatch.id.desc()).limit(200)).scalars())
    return render_template("uploads.html", rows=rows, specs=usvc.SPECS)


@bp.route("/cargas/nueva", methods=["GET", "POST"])
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar")
def upload_new():
    tipo = request.values.get("tipo") or "STOCK"
    if request.method == "POST":
        f = request.files.get("archivo")
        if not f or not f.filename:
            return fail("Seleccione un archivo.", url_for("alm.upload_new", tipo=tipo))
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".xlsx", ".xlsm"):
            return fail("Solo se aceptan archivos .xlsx o .xlsm.", url_for("alm.upload_new", tipo=tipo))
        path = os.path.join(current_app.config["UPLOAD_DIR"], f"carga_{uuid.uuid4().hex[:10]}{ext}")
        f.save(path)
        holder = {}

        def _do():
            holder["b"] = usvc.create_batch(g.user, tipo, path, os.path.basename(f.filename), request.form.get("hoja") or None)
            return holder["b"]
        resp = act(_do, lambda b: f"Archivo leído: {len(b.rows)} filas. Revise errores y advertencias antes de autorizar.",
                   url_for("alm.uploads"))
        if "b" in holder and holder["b"].id:
            return redirect(url_for("alm.upload_detail", bid=holder["b"].id))
        return resp
    return render_template("upload_new.html", tipo=tipo, specs=usvc.SPECS)


@bp.route("/cargas/<int:bid>")
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar")
def upload_detail(bid):
    b = db().get(UploadBatch, bid) or abort(404)
    filtro = request.args.get("filtro", "problemas")
    rows = b.rows
    if filtro == "problemas":
        rows = [r for r in rows if r.errores or r.advertencias or r.excluida or r.editada]
    return render_template("upload_detail.html", bt=b, rows=rows[:1000], filtro=filtro, spec=usvc.SPECS[b.tipo])


@bp.route("/cargas/<int:bid>/fila/<int:rid>", methods=["POST"])
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar")
def upload_row(bid, rid):
    b = db().get(UploadBatch, bid) or abort(404)
    r = db().get(UploadRow, rid) or abort(404)
    if r.batch_id != b.id:
        abort(404)
    accion = request.form.get("accion")
    if accion == "excluir":
        fn = lambda: usvc.exclude_row(b, r, g.user, request.form.get("motivo", ""))  # noqa: E731
    elif accion == "incluir":
        fn = lambda: usvc.exclude_row(b, r, g.user, "", excluir=False)  # noqa: E731
    else:
        nuevos = {k[2:]: v for k, v in request.form.items() if k.startswith("c_")}
        fn = lambda: usvc.edit_row(b, r, g.user, nuevos)  # noqa: E731
    return act(fn, "Fila actualizada y carga revalidada.", url_for("alm.upload_detail", bid=bid) + f"#f{r.id}")


@bp.route("/cargas/<int:bid>/<accion>", methods=["POST"])
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar")
def upload_action(bid, accion):
    b = db().get(UploadBatch, bid) or abort(404)
    if accion == "confirmar":
        opciones = {k: v for k, v in request.form.items() if k not in ("_csrf",)}
        return act(lambda: usvc.confirm(b, g.user, opciones), lambda r: f"Carga autorizada e incorporada: {r}",
                   url_for("alm.upload_detail", bid=bid))
    if accion == "descartar":
        return act(lambda: usvc.discard(b, g.user), "Carga descartada.", url_for("alm.uploads"))
    abort(404)


# ------------------------------- conteos -----------------------------------
@bp.route("/conteos", methods=["GET", "POST"])
@perm_required("stock.conteo")
def counts():
    if request.method == "POST":
        holder = {}

        def _do():
            holder["c"] = isvc.open_count(g.user, request.form["warehouse_code"], request.form.get("prefijo", "").strip().upper(),
                                          request.form.get("observacion", ""))
        resp = act(_do, "Conteo abierto.", url_for("alm.counts"))
        if "c" in holder and holder["c"].id:
            return redirect(url_for("alm.count_detail", cid=holder["c"].id))
        return resp
    rows = list(db().execute(select(PhysicalCount).order_by(PhysicalCount.id.desc())).scalars())
    whs = list(db().execute(select(Warehouse).order_by(Warehouse.prioridad)).scalars())
    return render_template("counts.html", rows=rows, whs=whs)


@bp.route("/conteos/<int:cid>", methods=["GET", "POST"])
@perm_required("stock.conteo")
def count_detail(cid):
    c = db().get(PhysicalCount, cid) or abort(404)
    if request.method == "POST":
        vals = {}
        for line in c.lines:
            vals[str(line.id)] = {"conteo": request.form.get(f"conteo_{line.id}"),
                                  "peso_unitario": request.form.get(f"peso_{line.id}"),
                                  "comentario": request.form.get(f"com_{line.id}", "")}
        def _do():
            isvc.save_lines(c, g.user, vals)
            if request.form.get("cerrar") == "1":
                return isvc.close_count(c, g.user)
        return act(_do, "Conteo guardado.", url_for("alm.count_detail", cid=cid))
    return render_template("count_detail.html", c=c)


# ------------------------------- traslados ---------------------------------
@bp.route("/traslados")
@perm_required("traslados.ver")
def transfers():
    rows = list(db().execute(select(Transfer).order_by(Transfer.id.desc())).scalars())
    return render_template("transfers.html", rows=rows)


@bp.route("/traslados/<int:tid>/<accion>", methods=["POST"])
@perm_required("traslados.ver")
def transfer_action(tid, accion):
    t = db().get(Transfer, tid) or abort(404)
    fns = {
        "autorizar": lambda: tsvc.authorize(t, g.user, True, request.form.get("observacion", "")),
        "rechazar": lambda: tsvc.authorize(t, g.user, False, request.form.get("observacion", "")),
        "salida": lambda: tsvc.ship(t, g.user),
        "recibir": lambda: tsvc.receive(t, g.user, f_float("cantidad_recibida", True), request.form.get("observacion", "")),
    }
    if accion not in fns:
        abort(404)
    return act(fns[accion], "Traslado actualizado.", url_for("alm.transfers"))


# ------------------------------- reempaque ---------------------------------
@bp.route("/reempaques", methods=["GET", "POST"])
@perm_required("reempaque.ver")
def repacks():
    if request.method == "POST":
        return act(lambda: rsvc.request(g.user, request.form.get("tipo"), request.form.get("lot_id"), f_float("cantidad", True),
                                        (request.form.get("producto_destino") or "").strip().upper() or None, None, None,
                                        request.form.get("motivo", "")),
                   "Solicitud de reempaque enviada a Calidad.", url_for("alm.repacks"))
    rows = list(db().execute(select(RepackRequest).order_by(RepackRequest.id.desc())).scalars())
    lots = list(db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.estado.in_(["DISPONIBLE", "PENDIENTE_REVISION"]),
                                                    StockLot.product_code.like("P%")).order_by(StockLot.product_code)).scalars())
    prods = list(db().execute(select(Product).where(Product.tipo == "PT").order_by(Product.code)).scalars())
    return render_template("repacks.html", rows=rows, lots=lots, prods=prods, tipos=REPACK_TYPES, free=free_qty)


@bp.route("/reempaques/<int:rid>", methods=["GET", "POST"])
@perm_required("reempaque.ver")
def repack_detail(rid):
    r = db().get(RepackRequest, rid) or abort(404)
    if request.method == "POST":
        acc = request.form.get("accion")
        fns = {
            "aprobar": lambda: rsvc.evaluate(r, g.user, True, request.form.get("resultado", "")),
            "desaprobar": lambda: rsvc.evaluate(r, g.user, False, request.form.get("resultado", "")),
            "iniciar": lambda: rsvc.start(r, g.user),
            "finalizar": lambda: rsvc.finish(r, g.user, request.form.get("lote_resultante", "").strip(),
                                             f_float("cantidad_resultante", True), f_date("nueva_fecha_fab"), f_date("nueva_fecha_venc")),
        }
        if acc not in fns:
            abort(404)
        return act(fns[acc], "Reempaque actualizado.", url_for("alm.repack_detail", rid=rid))
    return render_template("repack_detail.html", r=r, tipos={c: (n, d) for c, n, d in REPACK_TYPES})
