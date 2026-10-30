"""Vistas de Calidad de la ronda V13 (30-oct-2026): bandeja (devoluciones, reempaques, revisiones, bloqueados), acciones
sobre lotes (observar, fumigar, fechas de producción, solicitar revisión o liberación), Producción ↔ Calidad
(observaciones en línea, validación de merma, reproceso, material previo, saldo por proceso), gestión (inspecciones,
visitas a almacenes externos, quejas y no conformidades), formatos de verificación por puntos y consolidado Excel."""
import io
import os
import uuid
from datetime import date, datetime

from flask import abort, current_app, flash, g, redirect, render_template, request, send_file, url_for
from sqlalchemy import select

from ..catalogs import CHECKLIST_CALIDAD, OBS_CATEGORIAS
from ..db import db
from ..models import (ExternalVisit, Inspection, LineObservation, MermaValidation, ProductionLine, ProductionReport,
                      ReviewRequest, SanitationZone, StockLot)
from ..services import quality_mgmt as qm
from ..services import quality_v13 as q13
from ..services.core import BusinessError
from ..services.distribution import save_upload
from .calidad import bp
from .common import act, f_date, perm_required


def _fotos(campo, prefijo):
    """Una o varias fotos opcionales."""
    up = current_app.config["UPLOAD_DIR"]
    return [n for n in (save_upload(f, up, prefijo) for f in request.files.getlist(campo)) if n]


def _back(default):
    nxt = request.form.get("next") or ""
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else default


def _zonas():
    z = [x.nombre for x in db().execute(select(SanitationZone).order_by(SanitationZone.nombre)).scalars()]
    return z, qm.external_warehouses()


def _zona_form(f):
    z = f.get("zona") or ""
    if z == "OTRO":
        donde = (f.get("zona_otro") or "").strip()
        if not donde:
            raise BusinessError("Indique dónde se fumiga.")
        return f"Otro: {donde}"
    return z


# ------------------------------------------------------------------ bandeja
@bp.route("/bandeja")
@perm_required("calidad.ver")
def inbox():
    data = q13.inbox()
    zonas, externos = _zonas()
    return render_template("cal_bandeja.html", **data, rep={r.id: q13.repack_detail(r) for r in data["reempaques"]},
                           cats=OBS_CATEGORIAS, zonas=zonas, externos=externos, hoy=date.today())


@bp.route("/lote/<int:lid>/observar", methods=["POST"])
@perm_required("calidad.registrar", "calidad.liberar")
def observe(lid):
    lot = db().get(StockLot, lid) or abort(404)
    return act(lambda: q13.observe_lot(g.user, lot, request.form.get("categoria", ""), request.form.get("detalle", "")),
               "Lote observado: se avisó a Almacén, Calidad y Producción.", _back(url_for("cal.inbox")))


@bp.route("/lote/<int:lid>/fumigar", methods=["POST"])
@perm_required("calidad.registrar", "calidad.liberar")
def fumigate(lid):
    lot = db().get(StockLot, lid) or abort(404)
    return act(lambda: q13.set_fumigation(g.user, lot, f_date("inicio") or date.today(), f_date("liberacion", True),
                                          _zona_form(request.form)),
               "Lote en fumigación con fecha prevista de liberación.", _back(url_for("cal.inbox")))


@bp.route("/lote/<int:lid>/revision", methods=["POST"])
@perm_required("calidad.revision_solicitar", "stock.cambiar_estado")
def review_request(lid):
    lot = db().get(StockLot, lid) or abort(404)
    return act(lambda: q13.request_review(g.user, lot, request.form.get("tipo", ""), request.form.get("motivo", "")),
               "Solicitud enviada a Calidad.", _back(url_for("alm.stock")))


@bp.route("/revision/<int:rid>", methods=["POST"])
@perm_required("calidad.liberar")
def review_resolve(rid):
    r = db().get(ReviewRequest, rid) or abort(404)
    f = request.form
    return act(lambda: q13.resolve_review(g.user, r, f.get("resultado", ""), f.get("comentario", ""), f_date("inicio"),
                                          f_date("liberacion"), _zona_form(f) if f.get("resultado") == "A_FUMIGACION" else ""),
               "Solicitud resuelta.", _back(url_for("cal.inbox")))


@bp.route("/lote/<int:lid>/fechas", methods=["GET", "POST"])
@perm_required("calidad.ver", "stock.cambiar_estado", "produccion.liquidar")
def production_dates(lid):
    lot = db().get(StockLot, lid) or abort(404)
    back = url_for("cal.production_dates", lid=lid)
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "estado":
            return act(lambda: q13.update_production_date(g.user, lot, f.get("fecha"), f.get("estado", ""), f.get("nota", "")),
                       "Estado de la fecha actualizado.", back)
        filas = [{"fecha": fe, "cantidad": c, "estado": e, "nota": n} for fe, c, e, n in
                 zip(f.getlist("f_fecha"), f.getlist("f_cantidad"), f.getlist("f_estado"), f.getlist("f_nota"))]
        return act(lambda: q13.add_production_dates(g.user, lot, filas), "Fechas de producción registradas.", back)
    return render_template("cal_lote_fechas.html", lot=lot, estados=q13.ESTADOS_FECHA)


# ------------------------------------------------------------------ Producción ↔ Calidad
@bp.route("/linea", methods=["GET", "POST"])
@perm_required("calidad.ver", "produccion.liquidar")
def line():
    back = url_for("cal.line")
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "observar":
            rep = db().get(ProductionReport, int(f["report_id"])) if f.get("report_id") else None
            pallets = [{"pallet": p, "detalle": d} for p, d in zip(f.getlist("pallet"), f.getlist("pallet_detalle"))]
            return act(lambda: q13.observe_line(g.user, f.get("linea", ""), f.get("descripcion", ""), pallets, rep,
                                                _fotos("fotos", "obslinea")),
                       "Observación notificada a Producción.", back)
        if acc == "fase":
            o = db().get(LineObservation, int(f["oid"])) or abort(404)
            return act(lambda: q13.advance_observation(g.user, o, f.get("fase", ""), f.get("motivo", "")), "Observación actualizada.", back)
        if acc == "merma":
            mv = db().get(MermaValidation, int(f["mid"])) or abort(404)
            return act(lambda: q13.validate_merma(g.user, mv, f.get("decision") == "conforme", f.get("grano_bueno"),
                                                  f.get("grano_danado"), _fotos("fotos", "merma"), f.get("observacion", "")),
                       "Validación de merma registrada.", back)
        if acc == "reproceso":
            mv = db().get(MermaValidation, int(f["mid"])) or abort(404)
            return act(lambda: q13.attend_reprocess(g.user, mv, f.get("nota", "")), "Reproceso registrado como atendido.", back)
        abort(400)
    obs = list(db().execute(select(LineObservation).order_by(LineObservation.fase == "CERRADA", LineObservation.id.desc())
                            .limit(100)).scalars())
    mvs = list(db().execute(select(MermaValidation).order_by(MermaValidation.estado.notin_(("PENDIENTE", "REPROCESO")),
                                                             MermaValidation.id.desc()).limit(100)).scalars())
    lineas = list(db().execute(select(ProductionLine).where(ProductionLine.activa.is_(True)).order_by(ProductionLine.code)).scalars())
    partes = list(db().execute(select(ProductionReport).where(ProductionReport.estado.in_(("EN PROCESO", "PAUSADO")))
                               .order_by(ProductionReport.linea)).scalars())
    return render_template("cal_linea.html", obs=obs, mvs=mvs, lineas=lineas, partes=partes)


@bp.route("/material")
@perm_required("calidad.ver", "produccion.ver")
def materials():
    dias = int(request.args.get("dias") or 7)
    return render_template("cal_material.html", filas=q13.materials_for_production(dias), dias=dias,
                           saldo=q13.balance_by_line(f_date("desde"), f_date("hasta")))


# ------------------------------------------------------------------ gestión: inspecciones, visitas, quejas y NC
@bp.route("/gestion", methods=["GET", "POST"])
@perm_required("calidad.ver")
def management():
    back = url_for("cal.management")
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "inspeccion":
            return act(lambda: qm.schedule_inspection(g.user, f), "Inspección programada.", back,
                       redirect_fn=lambda i: url_for("cal.inspection", iid=i.id))
        if f.get("accion") == "visita":
            cuando = f"{f.get('fecha')}T{f.get('hora') or '09:00'}"
            return act(lambda: qm.propose_visit(g.user, f.get("warehouse_code", ""), cuando, f.get("tipo", "VISITA"),
                                                f.get("observacion", "")),
                       "Propuesta enviada a Almacén para confirmar o reprogramar.", back,
                       redirect_fn=lambda v: url_for("cal.visit", vid=v.id))
        abort(400)
    insp = list(db().execute(select(Inspection).order_by(Inspection.fecha.desc()).limit(100)).scalars())
    vis = list(db().execute(select(ExternalVisit).order_by(ExternalVisit.propuesta.desc()).limit(100)).scalars())
    rep = qm.complaints_report(f_date("desde"), f_date("hasta"))
    return render_template("cal_gestion.html", insp=insp, vis=vis, rep=rep, externos=qm.external_warehouses(),
                           tab=request.args.get("tab") or "inspecciones")


def _findings(obj, back):
    f = request.form
    if f.get("accion") == "hallazgo":
        return act(lambda: qm.add_finding(g.user, obj, f.get("descripcion", ""), f.get("area", ""), f_date("plazo"),
                                          (_fotos("foto", "hallazgo") or [""])[0]),
                   "Hallazgo registrado y asignado como tarea al área.", back)
    if f.get("accion") == "levantar":
        return act(lambda: qm.close_finding(g.user, obj, f.get("n"), f.get("evidencia", ""), (_fotos("foto", "levanta") or [""])[0]),
                   "Hallazgo levantado.", back)
    return None


@bp.route("/inspeccion/<int:iid>", methods=["GET", "POST"])
@perm_required("calidad.ver", "alertas.gestionar")
def inspection(iid):
    i = db().get(Inspection, iid) or abort(404)
    back = url_for("cal.inspection", iid=iid)
    if request.method == "POST":
        f = request.form
        r = _findings(i, back)
        if r is not None:
            return r
        if f.get("accion") == "iniciar":
            return act(lambda: qm.start_inspection(g.user, i, f.get("hora_inicio", "")), "Inspección en proceso.", back)
        if f.get("accion") == "cerrar":
            return act(lambda: qm.close_inspection(g.user, i, f.get("resultado", ""), f.get("puntaje"), f.get("n_hallazgos"),
                                                   _fotos("fotos_resultado", "insp_res"), _fotos("fotos_hallazgos", "insp_hal")),
                       "Resultado de la inspección registrado.", back)
        abort(400)
    return render_template("cal_inspeccion.html", i=i, areas=list(qm.AREAS_TAREA))


@bp.route("/visita/<int:vid>", methods=["GET", "POST"])
@perm_required("calidad.ver", "stock.cambiar_estado", "stock.autorizar_carga", "alertas.gestionar")
def visit(vid):
    v = db().get(ExternalVisit, vid) or abort(404)
    back = url_for("cal.visit", vid=vid)
    if request.method == "POST":
        f = request.form
        r = _findings(v, back)
        if r is not None:
            return r
        if f.get("accion") == "responder":
            nueva = f"{f.get('fecha')}T{f.get('hora') or '09:00'}" if f.get("fecha") else None
            return act(lambda: qm.answer_visit(g.user, v, f.get("confirmar") == "1", nueva, f.get("motivo", "")),
                       "Respuesta registrada.", back)
        if f.get("accion") == "realizada":
            return act(lambda: qm.complete_visit(g.user, v, f.get("observacion", "")), "Visita registrada como realizada.", back)
        abort(400)
    return render_template("cal_visita.html", v=v, areas=list(qm.AREAS_TAREA))


# ------------------------------------------------------------------ formatos de verificación por puntos
@bp.route("/verificacion/<formato>", methods=["GET", "POST"])
@perm_required("calidad.registrar", "calidad.formatos_configurar")
def checklist_format(formato):
    if formato not in CHECKLIST_CALIDAD:
        abort(404)
    back = url_for("cal.checklist_format", formato=formato)
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "puntos":
            return act(lambda: qm.save_points(g.user, formato, f.get("puntos", "")), "Puntos del formato guardados.", back)
        valores = {k[2:]: v for k, v in f.items() if k.startswith("v_")}
        obs = {k[2:]: v for k, v in f.items() if k.startswith("o_")}
        return act(lambda: qm.register_checklist(g.user, formato, f_date("fecha"), valores, obs),
                   lambda r: f"Registro #{r.id} guardado: {r.resultado.replace('_', ' ').lower()}.", back,
                   redirect_fn=lambda r: url_for("cal.record_detail", rid=r.id))
    codigo, nombre, grupos = qm.checklist_points(formato)
    return render_template("cal_verificacion.html", formato=formato, codigo=codigo, nombre=nombre, grupos=grupos,
                           hoy=date.today(), total=sum(len(ps) for _, ps in grupos),
                           configurable=not CHECKLIST_CALIDAD[formato][2])


# ------------------------------------------------------------------ consolidado Excel
@bp.route("/consolidado", methods=["GET", "POST"])
@perm_required("calidad.ver")
def consolidated():
    if request.method == "POST":
        f = request.files.get("archivo")
        if not f or not f.filename.lower().endswith(".xlsx"):
            flash("Seleccione el consolidado en Excel (.xlsx).", "error")
            return redirect(url_for("cal.home"))
        path = os.path.join(current_app.config["UPLOAD_DIR"], f"consolidado_{uuid.uuid4().hex[:10]}.xlsx")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        f.save(path)
        return act(lambda: qm.import_consolidated(g.user, path),
                   lambda r: f"Base cargada: {r['cargados']} registro(s); {r['omitidos']} ya existían."
                             + (f" Con observaciones: {'; '.join(r['errores'][:5])}" if r["errores"] else ""),
                   url_for("cal.home"))
    data = qm.export_consolidated(f_date("desde"), f_date("hasta"), request.args.getlist("formatos") or None,
                                  request.args.get("solo_mp") == "1")
    nombre = f"consolidado_calidad{'_MP' if request.args.get('solo_mp') == '1' else ''}_{date.today():%Y%m%d}.xlsx"
    return send_file(io.BytesIO(data), as_attachment=True, download_name=nombre,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
