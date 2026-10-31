"""Vistas de Calidad: liberación, formatos REG-*, certificados."""
import os

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, send_file, url_for
from sqlalchemy import select

from ..catalogs import CHECKLIST_CALIDAD, CRITERIO_PESO_PENDIENTE, CRITERIOS_PESO, PCC1_HUMEDAD, SPEC_CALIDAD_SUPERIOR
from ..db import db
from ..models import Certificate, Product, PurchaseRequest, QualityRecord, StockLot
from ..services import purchasing as buysvc
from ..services import quality as qsvc
from ..services.core import audit
from .common import act, f_date, login_required, perm_required

bp = Blueprint("cal", __name__, url_prefix="/calidad")


@bp.route("/")
@perm_required("calidad.ver")
def home():
    pend = list(db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.estado.in_(
        ["PENDIENTE_REVISION", "NO_UTILIZABLE", "EN_FUMIGACION", "OBSERVADO"])).order_by(StockLot.estado, StockLot.id)).scalars())
    # V13: revisión de formatos por día o rango de fechas y por uno o varios tipos de formato
    sel = [x for x in request.args.getlist("formato") if x]
    formato = sel[0] if len(sel) == 1 else ""
    desde, hasta = f_date("desde"), f_date("hasta")
    if f_date("dia"):
        desde = hasta = f_date("dia")
    q = select(QualityRecord).order_by(QualityRecord.fecha.desc(), QualityRecord.id.desc())
    if sel:
        q = q.where(QualityRecord.formato.in_(sel))
    if desde:
        q = q.where(QualityRecord.fecha >= desde)
    if hasta:
        q = q.where(QualityRecord.fecha <= hasta)
    recs = list(db().execute(q.limit(300)).scalars())
    muestras = list(db().execute(select(PurchaseRequest).where(PurchaseRequest.estado == "MUESTRA_EN_CALIDAD")).scalars())
    lotes = list(db().execute(select(StockLot).where(StockLot.cantidad > 0).order_by(StockLot.product_code, StockLot.lote)).scalars())
    fum = qsvc.fumigation_plan()
    # V14: líneas en proceso de producción con su avance, merma y desviaciones (observaciones abiertas, alertas del parte)
    from ..models import LineObservation
    from ..services import parte as ptsvc
    from ..services import prod_home
    en_proceso = []
    for f in prod_home.line_status()[0]:
        r = f.get("parte")
        if r is None or f["estado"] in ("SIN PROGRAMA",):
            continue
        lv = ptsvc.live(r)
        obs = db().execute(select(LineObservation).where(LineObservation.linea == f["linea"],
                                                         LineObservation.fase != "CERRADA")).scalars().all()
        en_proceso.append({"f": f, "r": r, "live": lv, "obs": len(obs)})
    from ..catalogs import HIGIENE_PERSONAL
    nombres = {k: v[1] + (" (retirado)" if k in qsvc.FORMATOS_RETIRADOS else "") for k, v in qsvc.FORMATOS.items()} \
        | {k: v[1] for k, v in CHECKLIST_CALIDAD.items()} | {"HIGIENE_PERSONAL": HIGIENE_PERSONAL[1]}
    return render_template("cal_home.html", en_proceso=en_proceso, pend=pend, recs=recs, formatos={k: v for k, v in qsvc.FORMATOS.items()
                                                                          if k not in qsvc.FORMATOS_RETIRADOS | qsvc.FORMATOS_PRODUCCION},
                           formato=formato, sel=sel, desde=desde, hasta=hasta, dia=f_date("dia"), nombres=nombres,
                           checklists=CHECKLIST_CALIDAD, muestras=muestras,
                           lotes=lotes, tipos=qsvc.CERT_TIPOS, fum=fum, etapas=qsvc.ETAPAS_PRODUCCION,
                           fum_veces=qsvc.fumigation_counts(),
                           etapas_todos={k for v in qsvc.ETAPAS_PRODUCCION.values() for k in v})


@bp.route("/lote/<int:lid>/fumigacion", methods=["POST"])
@perm_required("calidad.ver")
def fumigation(lid):
    lot = db().get(StockLot, lid) or abort(404)
    return act(lambda: qsvc.schedule_fumigation(lot, g.user, f_date("fecha", True)), "Fumigación programada.", url_for("cal.home"))


@bp.route("/abrir")
@perm_required("calidad.registrar")
def open_record():
    """Selector de formatos (lista desplegable): abre el formato elegido, opcionalmente con el lote."""
    formato = request.args.get("formato_sel", "")
    if formato in CHECKLIST_CALIDAD:
        return redirect(url_for("cal.checklist_format", formato=formato))
    if formato not in qsvc.FORMATOS or formato in qsvc.FORMATOS_RETIRADOS:
        abort(404)
    return redirect(url_for("cal.new_record", formato=formato, lot_id=request.args.get("lot_id") or None))


@bp.route("/lote/<int:lid>/liberar", methods=["POST"])
@perm_required("calidad.liberar")
def release(lid):
    lot = db().get(StockLot, lid) or abort(404)
    aprobar = request.form.get("decision") == "liberar"
    return act(lambda: qsvc.release_lot(lot, g.user, aprobar, request.form.get("motivo", "") or ("Liberado" if aprobar else "Rechazado"),
                                        request.form.get("estado_rechazo") or "NO_UTILIZABLE"),
               "Decisión registrada.", url_for("cal.home"))


@bp.route("/muestra/<int:pid>", methods=["POST"])
@perm_required("calidad.evaluar_muestra")
def sample(pid):
    r = db().get(PurchaseRequest, pid) or abort(404)
    return act(lambda: buysvc.evaluate_sample(r, g.user, request.form.get("decision") == "aprobar", request.form.get("observacion", "")),
               "Evaluación de muestra registrada.", url_for("cal.home"))


@bp.route("/registro/nuevo/<formato>", methods=["GET", "POST"])
@perm_required("calidad.registrar", "distribucion.seguridad", "produccion.lote_nuevo")
def new_record(formato):
    if formato not in qsvc.FORMATOS or formato in qsvc.FORMATOS_RETIRADOS:
        abort(404)
    if formato in qsvc.FORMATOS_PRODUCCION and "produccion.lote_nuevo" not in g.perms:
        abort(403)
    if request.method == "POST":
        holder = {}

        def _do():
            from ..services.distribution import save_upload
            datos = qsvc.parse_form(formato, request.form)
            adj = [n for n in (save_upload(f, current_app.config["UPLOAD_DIR"], f"cal_{formato.lower()}")
                               for f in request.files.getlist("adjuntos")) if n]
            holder["r"] = qsvc.register(g.user, formato, datos, (request.form.get("product_code") or "").strip().upper() or None,
                                        request.form.get("lote", "").strip(), request.form.get("lot_id") or None,
                                        request.form.get("resultado") or None, request.form.get("observaciones", ""),
                                        request.form.get("referencia_tipo", ""), int(request.form["referencia_id"]) if request.form.get("referencia_id") else None,
                                        f_date("fecha"))
            holder["r"].adjuntos = adj
            return holder["r"]
        resp = act(_do, lambda r: f"Registro #{r.id} guardado. Resultado: {r.resultado or '-'}.", url_for("cal.new_record", formato=formato))
        if "r" in holder and holder["r"].id:
            return redirect(url_for("cal.record_detail", rid=holder["r"].id))
        return resp
    lots = list(db().execute(select(StockLot).where(StockLot.cantidad > 0).order_by(StockLot.product_code)).scalars())
    from ..models import SanitationZone
    from ..services.quality_mgmt import external_warehouses
    pre = {}  # V14: datos que el sistema ya conoce (p. ej. fechas de la fumigación puestas al bloquear el lote)
    lid = request.args.get("lot_id")
    lot_sel = db().get(StockLot, int(lid)) if lid and lid.isdigit() else None
    if formato == "FUMIGACION" and lot_sel is not None and lot_sel.fumigacion:
        fu = lot_sel.fumigacion
        pre = {"inicio_fecha": fu.get("inicio", ""), "fin_fecha": fu.get("liberacion", ""), "zona": fu.get("zona", "")}
    zonas = [z.nombre for z in db().execute(select(SanitationZone).where(SanitationZone.activo.is_(True))
                                            .order_by(SanitationZone.nombre)).scalars()]
    return render_template("cal_form.html", formato=formato, fdef=qsvc.FORMATOS[formato], lots=lots, pcc1=PCC1_HUMEDAD,
                           zonas=zonas, externos=external_warehouses(), pre=pre, ref_tipo=request.args.get("referencia_tipo", ""),
                           ref_id=request.args.get("referencia_id", ""), prod_ini=request.args.get("product_code", ""),
                           spec=SPEC_CALIDAD_SUPERIOR, pesos=CRITERIOS_PESO, peso_pend=CRITERIO_PESO_PENDIENTE,
                           lot_id=request.args.get("lot_id", ""))


@bp.route("/registro/<int:rid>")
@perm_required("calidad.ver", "distribucion.seguridad")
def record_detail(rid):
    r = db().get(QualityRecord, rid) or abort(404)
    if r.formato == "HIGIENE_PERSONAL":  # V14: PHS-003, grilla por persona
        return redirect(url_for("cal.records_report", id=r.id))
    if r.formato in qsvc.FORMATOS:
        fdef = qsvc.FORMATOS[r.formato]
    elif r.formato in CHECKLIST_CALIDAD:
        fdef = (CHECKLIST_CALIDAD[r.formato][0], CHECKLIST_CALIDAD[r.formato][1], [])
    else:
        abort(404)
    return render_template("cal_record.html", r=r, fdef=fdef, enc=qsvc.ENCABEZADOS.get(r.formato))


@bp.route("/certificados", methods=["GET", "POST"])
@perm_required("calidad.ver")
def certificates():
    if request.method == "POST":
        if "calidad.certificado_revisar" not in g.perms and "calidad.registrar" not in g.perms:
            abort(403)
        lot = db().get(StockLot, int(request.form["lot_id"])) or abort(404)
        tipo = request.form.get("tipo") or None
        return act(lambda: qsvc.generate_certificate(lot, g.user, tipo=tipo),
                   lambda c: f"Certificado {c.numero} generado (borrador).", url_for("cal.certificates"))
    rows = list(db().execute(select(Certificate).order_by(Certificate.id.desc())).scalars())
    lots = list(db().execute(select(StockLot).where(StockLot.cantidad > 0).order_by(StockLot.product_code)).scalars())
    return render_template("certificates.html", rows=rows, lots=lots, tipos=qsvc.CERT_TIPOS)


@bp.route("/certificados/<int:cid>", methods=["GET", "POST"])
@perm_required("calidad.ver")
def certificate_detail(cid):
    c = db().get(Certificate, cid) or abort(404)
    if request.method == "POST":
        if request.form.get("accion") == "regenerar":
            return act(lambda: qsvc.regenerate_certificate(c, g.user, request.form.get("tipo", "")),
                       lambda n: f"Certificado regenerado como {n.numero}.", url_for("cal.certificate_detail", cid=cid),
                       redirect_fn=lambda n: url_for("cal.certificate_detail", cid=n.id))
        cambios = {k: v for k, v in request.form.items() if k not in ("_csrf", "accion", "extra_etiqueta", "extra_descripcion")}
        if "extra_etiqueta" in request.form:  # V13: filas de datos adicionales del certificado
            cambios["datos_adicionales"] = list(zip(request.form.getlist("extra_etiqueta"), request.form.getlist("extra_descripcion")))
        # obs. demo v0.7: el avance se guarda siempre; si la aprobación falla (datos pendientes) no se pierde lo escrito
        resp = act(lambda: qsvc.review_certificate(c, g.user, cambios, False),
                   "Avance del certificado guardado (borrador)." if request.form.get("accion") != "aprobar" else None,
                   url_for("cal.certificate_detail", cid=cid))
        if request.form.get("accion") == "aprobar" and c.estado != "APROBADO":
            from ..services.core import BusinessError
            try:
                qsvc.review_certificate(c, g.user, {}, True)
                db().commit()
                flash("Certificado aprobado.", "ok")
            except BusinessError as e:
                db().rollback()
                flash(f"Se guardó el avance, pero aún no se puede aprobar: {e}", "error")
        return resp
    return render_template("certificate.html", c=c, d=c.datos, editable=qsvc.EDITABLE_CERT_FIELDS,
                           print_mode=request.args.get("imprimir") == "1", tipos=qsvc.CERT_TIPOS, etiquetas=qsvc.CERT_ETIQUETAS,
                           procesado=qsvc.CERT_PROCESADO,
                           firma_url=url_for("cal.firma") if os.path.exists(_firma_path()) else None)


def _firma_path():
    return os.path.join(current_app.instance_path, "firmas", "firma_certificado.png")


@bp.route("/firma", methods=["GET", "POST"])
@login_required
def firma():
    """Imagen de la firma del certificado: se guarda en el servidor (fuera del repositorio) y la carga Sistemas."""
    if request.method == "POST":
        if "config.editar" not in g.perms and g.user.role_code != "JEFE_CALIDAD":  # V14: la carga la Jefa de Calidad
            abort(403)
        f = request.files.get("archivo")
        if not f or not f.filename.lower().endswith(".png"):
            flash("Seleccione una imagen PNG de la firma.", "error")
            return redirect(url_for("cal.certificates"))
        os.makedirs(os.path.dirname(_firma_path()), exist_ok=True)
        f.save(_firma_path())
        audit(g.user, "FIRMA_CERTIFICADO_CARGADA", "Param", "certificado_firmante", {})
        db().commit()
        flash("Firma cargada.", "ok")
        return redirect(url_for("cal.certificates"))
    if "calidad.ver" not in g.perms or not os.path.exists(_firma_path()):
        abort(404)
    return send_file(_firma_path(), mimetype="image/png")
