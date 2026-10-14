"""Vistas de Producción: solicitudes, validación, programación, BOM/calculadora, liquidaciones y recepción de PT."""
from datetime import date, timedelta

from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import BOMLine, BOMVersion, Liquidation, Product, ProductionLine, ProductionRequest, SalesOrder, Warehouse
from ..services import production as psvc
from .common import act, f_bool, f_date, f_float, perm_required

bp = Blueprint("prod", __name__, url_prefix="/produccion")


@bp.route("/", methods=["GET", "POST"])
@perm_required("produccion.ver")
def requests():
    if request.method == "POST":
        holder = {}

        def _do():
            o = None
            if request.form.get("ov"):
                o = db().execute(select(SalesOrder).where(SalesOrder.numero == request.form["ov"].strip())).scalars().first()
            holder["r"] = psvc.create_request(request.form.get("product_code", "").strip().upper(), f_float("cantidad", True),
                                              g.user, o, f_date("fecha_requerida"), origen="OV" if o else "MANUAL",
                                              observacion=request.form.get("observacion", ""))
        resp = act(_do, "Solicitud preliminar creada.", url_for("prod.requests"))
        if "r" in holder and holder["r"].id:
            return redirect(url_for("prod.request_detail", rid=holder["r"].id))
        return resp
    rows = list(db().execute(select(ProductionRequest).order_by(ProductionRequest.id.desc())).scalars())
    lines = list(db().execute(select(ProductionLine).order_by(ProductionLine.code)).scalars())
    ini = f_date("desde") or date.today()
    dias = [ini + timedelta(days=i) for i in range(7)]
    prog = {}
    for r in rows:
        if r.fecha_programada and r.line_code:
            prog.setdefault((r.line_code, r.fecha_programada), []).append(r)
    carga = {(l.code, d): psvc.line_load_kg(l.code, d) for l in lines for d in dias}
    prods = [p for p, _ in psvc.bom_products()]
    from ..services.stock import ORDEN_ESTADOS_CERRADOS
    ovs = list(db().execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS))
                            .order_by(SalesOrder.fecha_compromiso)).scalars())
    return render_template("prod_list.html", rows=rows, lines=lines, dias=dias, prog=prog, carga=carga, prods=prods, ovs=ovs)


@bp.route("/solicitud/<int:rid>", methods=["GET", "POST"])
@perm_required("produccion.ver")
def request_detail(rid):
    r = db().get(ProductionRequest, rid) or abort(404)
    if request.method == "POST":
        acc = request.form.get("accion")
        u = g.user
        fns = {
            "recalcular": (lambda: psvc.refresh_analysis(r), "Análisis recalculado.", "produccion.solicitud"),
            "bom_ok": (lambda: psvc.review_bom(r, u, True, request.form.get("comentario", "")), "Lista de materiales confirmada.",
                       "produccion.ver"),
            "bom_obs": (lambda: psvc.review_bom(r, u, False, request.form.get("comentario", "")),
                        "Lista de materiales observada (se alertó).", "produccion.ver"),
            "enviar": (lambda: psvc.send_request(r, u), "Solicitud enviada a Producción.", "produccion.solicitud"),
            "validar": (lambda: psvc.validate_request(r, u, True, f_bool("lista_ok"), f_bool("disponibilidad_ok"), f_bool("capacidad_ok"),
                                                      f_bool("plazo_ok"), request.form.get("comentario", "")), "Solicitud validada.", "produccion.validar"),
            "rechazar": (lambda: psvc.validate_request(r, u, False, f_bool("lista_ok"), f_bool("disponibilidad_ok"), f_bool("capacidad_ok"),
                                                       f_bool("plazo_ok"), request.form.get("comentario", "")), "Solicitud rechazada.", "produccion.validar"),
            "programar": (lambda: psvc.schedule(r, u, request.form.get("line_code"), f_date("fecha_programada", True)),
                          lambda av: "Programada. " + " ".join(av or []), "produccion.programar"),
            "iniciar": (lambda: psvc.start(r, u), "Inicio registrado.", "produccion.registrar"),
            "finalizar": (lambda: psvc.finish(r, u), "Fin registrado. Registre la liquidación.", "produccion.registrar"),
            "liquidar": (lambda: psvc.register_liquidation(u, request.form.get("numero_documento", "").strip(), r.product_code,
                                                           f_float("cantidad_completada", True), request.form.get("lote", "").strip(),
                                                           f_date("fecha_fab"), f_date("fecha_venc"), r.cantidad, r, "MANUAL",
                                                           merma_mp_kg=f_float("merma_mp_kg"), merma_granel_kg=f_float("merma_granel_kg"),
                                                           merma_insumos=_insumos()),
                         "Liquidación registrada; se alertó al montacarguista.", "produccion.liquidar"),
        }
        if acc not in fns:
            abort(404)
        fn, msg, perm = fns[acc]
        if perm not in g.perms:
            abort(403)
        return act(fn, msg, url_for("prod.request_detail", rid=rid))
    lines = list(db().execute(select(ProductionLine).where(ProductionLine.activa.is_(True))).scalars())
    liqs = list(db().execute(select(Liquidation).where(Liquidation.request_id == r.id)).scalars())
    return render_template("prod_detail.html", r=r, a=r.analisis or {}, lines=lines, liqs=liqs)


def _insumos():
    out = {}
    for code, q in zip(request.form.getlist("insumo_code"), request.form.getlist("insumo_qty")):
        if code.strip() and q.strip():
            out[code.strip().upper()] = float(q.replace(",", "."))
    return out


@bp.route("/bom")
@perm_required("produccion.ver")
def bom():
    versions = list(db().execute(select(BOMVersion).order_by(BOMVersion.version.desc())).scalars())
    code = (request.args.get("producto") or "").strip().upper()
    qty = request.args.get("cantidad")
    calc = None
    lines = []
    if code:
        v = psvc.active_bom()
        if v:
            lines = list(db().execute(select(BOMLine).where(BOMLine.version_id == v.id, BOMLine.padre == code)).scalars())
        if qty:
            try:
                calc = psvc.material_requirements(code, float(qty))
            except ValueError:
                calc = None
    prods = psvc.bom_products()
    return render_template("bom.html", versions=versions, code=code, qty=qty or "", calc=calc, lines=lines, prods=prods)


@bp.route("/liquidaciones", methods=["GET", "POST"])
@perm_required("produccion.ver", "produccion.recibir_pt")
def liquidations():
    if request.method == "POST":
        acc = request.form.get("accion")
        if acc == "recibir":
            if "produccion.recibir_pt" not in g.perms:
                abort(403)
            liq = db().get(Liquidation, int(request.form["id"])) or abort(404)
            return act(lambda: psvc.receive_pt(liq, g.user, f_float("cantidad_recibida", True), request.form.get("presentacion_ok") == "1",
                                               request.form.get("observacion", ""), request.form.get("warehouse_code") or None),
                       "Recepción validada.", url_for("prod.liquidations"))
        if "produccion.liquidar" not in g.perms:
            abort(403)
        return act(lambda: psvc.register_liquidation(g.user, request.form.get("numero_documento", "").strip(),
                                                     request.form.get("product_code", "").strip().upper(), f_float("cantidad_completada", True),
                                                     request.form.get("lote", "").strip(), f_date("fecha_fab"), f_date("fecha_venc"),
                                                     f_float("cantidad_planificada"), None, "MANUAL", merma_mp_kg=f_float("merma_mp_kg"),
                                                     merma_granel_kg=f_float("merma_granel_kg"), merma_insumos=_insumos()),
                   "Liquidación registrada.", url_for("prod.liquidations"))
    rows = list(db().execute(select(Liquidation).order_by(Liquidation.id.desc())).scalars())
    whs = list(db().execute(select(Warehouse).where(Warehouse.uso == "PT")).scalars())
    return render_template("liquidations.html", rows=rows, whs=whs, merma=psvc.merma_real_pct)


@bp.route("/plan", methods=["GET", "POST"])
@perm_required("produccion.ver")
def plan():
    """Planeamiento diario, semanal y mensual de Producción vs liquidación (tasa de cumplimiento)."""
    from ..catalogs import PRODUCTION_LINES
    if request.method == "POST":
        f = request.form
        return act(lambda: psvc.add_plan(g.user, f.get("periodo"), f_date("fecha", True), f.get("product_code", "").strip().upper().split(" ")[0],
                                         f_float("cantidad", True), f.get("line_code") or None, f.get("comentario", "")),
                   "Plan registrado.", url_for("prod.plan", periodo=f.get("periodo", "DIA")))
    periodo = request.args.get("periodo", "DIA")
    d = psvc.plan_vs_real(periodo, f_date("desde"), f_date("hasta"))
    from ..services import charts
    graf = charts.line([("Plan", [(f"{k:%d/%m}", v["plan"]) for k, v in d["serie"]]),
                        ("Real (liquidado)", [(f"{k:%d/%m}", v["real"]) for k, v in d["serie"]])], "und", title="Plan vs real")
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP", "C3"])).order_by(Product.code)).scalars())
    return render_template("prod_plan.html", d=d, graf=graf, products=products, lineas=PRODUCTION_LINES, hoy=date.today())


@bp.route("/partes", methods=["GET", "POST"])
@perm_required("produccion.ver")
def reports():
    """Partes de producción por línea con rendimiento y desmedro (= merma)."""
    from ..catalogs import PRODUCTION_LINES
    from ..models import ProductionReport
    if request.method == "POST":
        if "produccion.liquidar" not in g.perms:
            abort(403)
        f = request.form
        ops = f.get("operarios", "").strip()
        if f.get("parte_id"):
            prog = db().get(ProductionReport, int(f["parte_id"])) or abort(404)
            return act(lambda: psvc.complete_report(
                prog, g.user, granel_kg=f_float("granel_kg"), mp_kg=f_float("mp_kg"), cal3_kg=f_float("cal3_kg"),
                desmedro_kg=f_float("desmedro_kg"), presentacion_kg=f_float("presentacion_kg"), unidades=f_float("unidades"),
                sobrante_kg=f_float("sobrante_kg"), hora_inicio=f.get("hora_inicio", ""), hora_fin=f.get("hora_fin", ""),
                horas=f_float("horas"), operarios=int(ops) if ops else None, estado=f.get("estado"),
                peso_entrada_kg=f_float("peso_entrada_kg"), lote=f.get("lote", "").strip() or None),
                lambda r: f"Parte completado: rendimiento {r.rendimiento_pct}%, desmedro {r.desmedro_pct}%.", url_for("prod.reports"))
        return act(lambda: psvc.register_report(
            g.user, f.get("linea"), f_date("fecha"), f.get("product_code", "").strip().upper().split(" ")[0], f_float("peso_entrada_kg"),
            f_float("granel_kg") or 0, f_float("mp_kg") or 0, f_float("cal3_kg") or 0, f_float("desmedro_kg") or 0,
            f_float("presentacion_kg"), f_float("unidades"), f_float("sobrante_kg") or 0, f.get("of", ""), f.get("op", ""),
            f.get("turno", ""), f.get("hora_inicio", ""), f.get("hora_fin", ""), f_float("horas"), int(ops) if ops else None,
            f.get("cliente", ""), f.get("mp_codigo", "").strip().upper(), f.get("lote", "").strip(), f.get("estado", "EN PROCESO"),
            f.get("observacion", "")), lambda r: f"Parte registrado: rendimiento {r.rendimiento_pct}%, desmedro {r.desmedro_pct}%.",
            url_for("prod.reports"))
    rows = list(db().execute(select(ProductionReport).order_by(ProductionReport.fecha.desc(), ProductionReport.id.desc())
                             .limit(300)).scalars())
    comp = db().get(ProductionReport, int(request.args["completar"])) if request.args.get("completar", "").isdigit() else None
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP", "C3"])).order_by(Product.code)).scalars())
    return render_template("prod_reports.html", rows=rows, lineas=PRODUCTION_LINES, hoy=date.today(), comp=comp, products=products)
