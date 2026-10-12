"""Vistas de Compras nacionales, reposición e Importaciones."""
from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import DateChange, ImportPhase, ImportShipment, Product, PurchaseRequest, Warehouse
from ..services import imports as isvc
from ..services import purchasing as psvc
from ..services.core import param
from .common import act, f_bool, f_date, f_float, perm_required

bp = Blueprint("buy", __name__, url_prefix="/abastecimiento")


@bp.route("/compras", methods=["GET", "POST"])
@perm_required("compras.ver", "compras.solicitar")
def purchases():
    if request.method == "POST":
        return act(lambda: psvc.create_request(g.user, request.form.get("product_code", "").strip().upper(), f_float("cantidad", True),
                                               f_date("fecha_necesidad")), "Solicitud enviada a Compras.", url_for("buy.purchases"))
    estado = request.args.get("estado") or ""
    q = select(PurchaseRequest).order_by(PurchaseRequest.id.desc())
    if estado:
        q = q.where(PurchaseRequest.estado == estado)
    rows = list(db().execute(q).scalars())
    prods = list(db().execute(select(Product).order_by(Product.code)).scalars())
    return render_template("purchases.html", rows=rows, prods=prods, estado=estado, umbral=param("umbral_mayor_volumen"))


@bp.route("/compras/<int:pid>", methods=["GET", "POST"])
@perm_required("compras.ver", "compras.solicitar")
def purchase_detail(pid):
    r = db().get(PurchaseRequest, pid) or abort(404)
    if request.method == "POST":
        acc = request.form.get("accion")
        u = g.user
        f = request.form
        fns = {
            "enviar": lambda: psvc.send(r, u),
            "cotizar": lambda: psvc.quote(r, u, f.get("proveedor", ""), f.get("cotizacion", ""), f_float("precio"), f_bool("requiere_muestra")),
            "aprobar_log": lambda: psvc.approve_logistics(r, u, True, f.get("comentario", "")),
            "rechazar_log": lambda: psvc.approve_logistics(r, u, False, f.get("comentario", "")),
            "pedir_go": lambda: psvc.request_go_approval(r, u),
            "aprobar_go": lambda: psvc.approve_go(r, u, True, f.get("comentario", "")),
            "rechazar_go": lambda: psvc.approve_go(r, u, False, f.get("comentario", "")),
            "orden": lambda: psvc.generate_order(r, u, f.get("numero_oc", ""), f_date("fecha_prevista", True), f.get("warehouse_code")),
            "fecha": lambda: psvc.change_date(r, u, f_date("nueva_fecha", True), f.get("motivo", "")),
            "recibir": lambda: psvc.receive(r, u, f_float("cantidad", True), f.get("lote", "").strip(), f_date("fecha_venc"), f.get("diferencias", "")),
            "bajo_observacion": lambda: psvc.authorize_under_observation(r, u, f.get("observaciones", "")),
            "subsanar": lambda: psvc.register_rectification(r, u, f.get("detalle", "")),
            "cerrar": lambda: psvc.close(r, u),
        }
        if acc not in fns:
            abort(404)
        return act(fns[acc], "Compra actualizada.", url_for("buy.purchase_detail", pid=pid))
    cambios = list(db().execute(select(DateChange).where(DateChange.entidad == "COMPRA", DateChange.entidad_id == r.id)
                                .order_by(DateChange.id)).scalars())
    whs = list(db().execute(select(Warehouse).order_by(Warehouse.prioridad)).scalars())
    return render_template("purchase_detail.html", r=r, cambios=cambios, whs=whs, needs_go=psvc.needs_go_approval(r))


@bp.route("/reposicion", methods=["GET", "POST"])
@perm_required("compras.ver", "compras.solicitar")
def replenishment():
    if request.method == "POST":
        return act(lambda: psvc.run_replenishment(g.user), lambda r: f"Análisis ejecutado: {len(r)} solicitud(es) preliminar(es) nueva(s).",
                   url_for("buy.replenishment"))
    prods = list(db().execute(select(Product).where((Product.categoria_reposicion != "") | (Product.stock_minimo.is_not(None)))
                              .order_by(Product.code)).scalars())
    analisis = [psvc.analyze_product(p) for p in prods]
    from ..models import LeadTime
    plazos = list(db().execute(select(LeadTime).order_by(LeadTime.categoria, LeadTime.mes_desde)).scalars())
    return render_template("replenishment.html", analisis=analisis, margen=param("margen_reposicion_dias"),
                           abc=psvc.abc_classes(), plazos=plazos)


@bp.route("/importaciones", methods=["GET", "POST"])
@perm_required("importaciones.ver")
def imports():
    if request.method == "POST":
        holder = {}

        def _do():
            holder["s"] = isvc.create_shipment(g.user, request.form.get("referencia", ""), request.form.get("proveedor", ""),
                                               request.form.get("product_code", "").strip().upper(), f_float("cantidad", True),
                                               f_date("fecha_inicio", True), f_date("fecha_llegada"), request.form.get("warehouse_code") or None,
                                               request.form.get("contenedor", ""), request.form.get("tipo_contenedor", ""))
        resp = act(_do, "Importación registrada.", url_for("buy.imports"))
        if "s" in holder and holder["s"].id:
            return redirect(url_for("buy.import_detail", sid=holder["s"].id))
        return resp
    rows = list(db().execute(select(ImportShipment).order_by(ImportShipment.id.desc())).scalars())
    prods = list(db().execute(select(Product).where(Product.tipo.in_(["MP", "GR", "INSUMO"])).order_by(Product.code)).scalars())
    whs = list(db().execute(select(Warehouse).order_by(Warehouse.prioridad)).scalars())
    return render_template("imports.html", rows=rows, prods=prods, whs=whs)


@bp.route("/importaciones/<int:sid>", methods=["GET", "POST"])
@perm_required("importaciones.ver")
def import_detail(sid):
    sh = db().get(ImportShipment, sid) or abort(404)
    if request.method == "POST":
        acc = request.form.get("accion")
        u = g.user
        f = request.form
        ph = db().get(ImportPhase, int(f["phase_id"])) if f.get("phase_id") else None
        fns = {
            "llegada": lambda: isvc.change_arrival(sh, u, f_date("nueva_fecha", True), f.get("motivo", "")),
            "fase_fecha": lambda: isvc.change_phase_date(ph, u, f_date("nueva_fecha", True), f.get("motivo", "")),
            "fase_ok": lambda: isvc.complete_phase(ph, u, f_date("fecha_real")),
            "logistica": lambda: isvc.update_logistics(sh, u, f.get("contenedor", ""), f.get("tipo_contenedor", ""),
                                                       f.get("warehouse_code") or None),
            "costo": lambda: isvc.add_cost(sh, u, f.get("concepto", ""), f_float("monto", True), f.get("moneda", "USD"),
                                           f_float("tipo_cambio"), f.get("documento", "")),
            "recibir": lambda: isvc.receive(sh, u, f_float("cantidad", True), f.get("lote", "").strip(), f.get("warehouse_code"),
                                            f_date("fecha_venc"), f.get("diferencias", "")),
        }
        if acc not in fns:
            abort(404)
        return act(fns[acc], "Importación actualizada.", url_for("buy.import_detail", sid=sid))
    cambios = list(db().execute(select(DateChange).where(DateChange.entidad.in_(["IMPORTACION", "FASE"])).order_by(DateChange.id)).scalars())
    phase_ids = {p.id for p in sh.phases}
    cambios = [c for c in cambios if (c.entidad == "IMPORTACION" and c.entidad_id == sh.id) or (c.entidad == "FASE" and c.entidad_id in phase_ids)]
    whs = list(db().execute(select(Warehouse).order_by(Warehouse.prioridad)).scalars())
    from datetime import date
    from ..services.core import param as _param
    return render_template("import_detail.html", sh=sh, cambios=cambios, whs=whs, hoy=date.today(), costos=isvc.cost_summary(sh),
                           conceptos=_param("conceptos_costo_importacion", []) or [])
