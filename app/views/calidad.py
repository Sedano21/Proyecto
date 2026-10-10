"""Vistas de Calidad: liberación, formatos REG-*, certificados."""
from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..catalogs import CRITERIO_PESO_PENDIENTE, CRITERIOS_PESO, PCC1_HUMEDAD, SPEC_CALIDAD_SUPERIOR
from ..db import db
from ..models import Certificate, Product, PurchaseRequest, QualityRecord, StockLot
from ..services import purchasing as buysvc
from ..services import quality as qsvc
from .common import act, f_date, perm_required

bp = Blueprint("cal", __name__, url_prefix="/calidad")


@bp.route("/")
@perm_required("calidad.ver")
def home():
    pend = list(db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.estado.in_(
        ["PENDIENTE_REVISION", "NO_UTILIZABLE", "EN_FUMIGACION"])).order_by(StockLot.estado, StockLot.id)).scalars())
    formato = request.args.get("formato") or ""
    q = select(QualityRecord).order_by(QualityRecord.id.desc())
    if formato:
        q = q.where(QualityRecord.formato == formato)
    recs = list(db().execute(q.limit(200)).scalars())
    muestras = list(db().execute(select(PurchaseRequest).where(PurchaseRequest.estado == "MUESTRA_EN_CALIDAD")).scalars())
    return render_template("cal_home.html", pend=pend, recs=recs, formatos=qsvc.FORMATOS, formato=formato, muestras=muestras)


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
@perm_required("calidad.registrar", "distribucion.seguridad")
def new_record(formato):
    if formato not in qsvc.FORMATOS:
        abort(404)
    if request.method == "POST":
        holder = {}

        def _do():
            datos = qsvc.parse_form(formato, request.form)
            holder["r"] = qsvc.register(g.user, formato, datos, (request.form.get("product_code") or "").strip().upper() or None,
                                        request.form.get("lote", "").strip(), request.form.get("lot_id") or None,
                                        request.form.get("resultado") or None, request.form.get("observaciones", ""),
                                        request.form.get("referencia_tipo", ""), int(request.form["referencia_id"]) if request.form.get("referencia_id") else None,
                                        f_date("fecha"))
            return holder["r"]
        resp = act(_do, lambda r: f"Registro #{r.id} guardado. Resultado: {r.resultado or '-'}.", url_for("cal.new_record", formato=formato))
        if "r" in holder and holder["r"].id:
            return redirect(url_for("cal.record_detail", rid=holder["r"].id))
        return resp
    lots = list(db().execute(select(StockLot).where(StockLot.cantidad > 0).order_by(StockLot.product_code)).scalars())
    return render_template("cal_form.html", formato=formato, fdef=qsvc.FORMATOS[formato], lots=lots, pcc1=PCC1_HUMEDAD,
                           spec=SPEC_CALIDAD_SUPERIOR, pesos=CRITERIOS_PESO, peso_pend=CRITERIO_PESO_PENDIENTE,
                           lot_id=request.args.get("lot_id", ""))


@bp.route("/registro/<int:rid>")
@perm_required("calidad.ver", "distribucion.seguridad")
def record_detail(rid):
    r = db().get(QualityRecord, rid) or abort(404)
    return render_template("cal_record.html", r=r, fdef=qsvc.FORMATOS[r.formato])


@bp.route("/certificados", methods=["GET", "POST"])
@perm_required("calidad.ver")
def certificates():
    if request.method == "POST":
        if "calidad.certificado_revisar" not in g.perms and "calidad.registrar" not in g.perms:
            abort(403)
        lot = db().get(StockLot, int(request.form["lot_id"])) or abort(404)
        return act(lambda: qsvc.generate_certificate(lot, g.user), lambda c: f"Certificado {c.numero} generado (borrador).",
                   url_for("cal.certificates"))
    rows = list(db().execute(select(Certificate).order_by(Certificate.id.desc())).scalars())
    lots = list(db().execute(select(StockLot).where(StockLot.cantidad > 0).order_by(StockLot.product_code)).scalars())
    return render_template("certificates.html", rows=rows, lots=lots)


@bp.route("/certificados/<int:cid>", methods=["GET", "POST"])
@perm_required("calidad.ver")
def certificate_detail(cid):
    c = db().get(Certificate, cid) or abort(404)
    if request.method == "POST":
        cambios = {k: v for k, v in request.form.items() if k not in ("_csrf", "accion")}
        return act(lambda: qsvc.review_certificate(c, g.user, cambios, request.form.get("accion") == "aprobar"),
                   "Certificado actualizado.", url_for("cal.certificate_detail", cid=cid))
    return render_template("certificate.html", c=c, d=c.datos, editable=qsvc.EDITABLE_CERT_FIELDS,
                           print_mode=request.args.get("imprimir") == "1")
