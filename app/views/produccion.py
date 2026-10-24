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
                                                           merma_insumos=_insumos(), parcial=f_bool("parcial"), **_horas()),
                         _liq_msg, "produccion.liquidar"),
        }
        if acc not in fns:
            abort(404)
        fn, msg, perm = fns[acc]
        if perm not in g.perms:
            abort(403)
        return act(fn, msg, url_for("prod.request_detail", rid=rid))
    lines = list(db().execute(select(ProductionLine).where(ProductionLine.activa.is_(True))).scalars())
    liqs = list(db().execute(select(Liquidation).where(Liquidation.request_id == r.id)).scalars())
    seguimiento = psvc.missing_materials_tracking(r) if r.estado in psvc.OPEN_REQ + ("EN_PROCESO",) else []
    return render_template("prod_detail.html", r=r, a=r.analisis or {}, lines=lines, liqs=liqs, seguimiento=seguimiento,
                           liquidado=psvc.liquidated_qty(r))


def _horas():
    ops = (request.form.get("operarios") or "").strip()
    return {"horas": f_float("horas"), "operarios": int(float(ops)) if ops else None, "mp_kg": f_float("mp_kg")}


def _liq_msg(liq):
    if liq.estado == "BLOQUEADA":
        return "Liquidación BLOQUEADA: " + " ".join((liq.bloqueo or {}).get("motivos", [])) + " Se alertó al Jefe de Producción."
    return "Liquidación registrada; se alertó al montacarguista."


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
    subs = {l.id: psvc.substitutes(l) for l in lines} if "produccion.plan_validar" in g.perms else {}
    return render_template("bom.html", versions=versions, code=code, qty=qty or "", calc=calc, lines=lines, prods=prods, subs=subs)


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
        if acc == "corregir":
            liq = db().get(Liquidation, int(request.form["id"])) or abort(404)
            ops = (request.form.get("operarios") or "").strip()
            return act(lambda: psvc.correct_liquidation(liq, g.user, f_float("cantidad_completada"), f_float("horas"),
                                                        int(float(ops)) if ops else None, f_float("mp_kg"),
                                                        request.form.get("motivo", "")), _liq_msg, url_for("prod.liquidations"))
        return act(lambda: psvc.register_liquidation(g.user, request.form.get("numero_documento", "").strip(),
                                                     request.form.get("product_code", "").strip().upper(), f_float("cantidad_completada", True),
                                                     request.form.get("lote", "").strip(), f_date("fecha_fab"), f_date("fecha_venc"),
                                                     f_float("cantidad_planificada"), None, "MANUAL", merma_mp_kg=f_float("merma_mp_kg"),
                                                     merma_granel_kg=f_float("merma_granel_kg"), merma_insumos=_insumos(), **_horas()),
                   _liq_msg, url_for("prod.liquidations"))
    a = request.args
    desde = f_date("desde") or date.today() - timedelta(days=30)
    hasta = f_date("hasta")
    rows = psvc.liquidations_list(desde, hasta, a.get("tipo", ""), a.get("producto", ""))
    whs = list(db().execute(select(Warehouse).where(Warehouse.uso == "PT")).scalars())
    from ..services.quality import lot_entries_vs_liquidation
    return render_template("liquidations.html", rows=rows, whs=whs, merma=psvc.merma_real_pct, vs_calidad=lot_entries_vs_liquidation,
                           f=a, desde=desde, total=sum(l.cantidad_completada or 0 for l in rows))


@bp.route("/plan", methods=["GET", "POST"])
@perm_required("produccion.ver")
def plan():
    """Planeamiento diario, semanal y mensual de Producción vs liquidación (tasa de cumplimiento)."""
    from ..catalogs import PRODUCTION_LINES
    from ..models import ProductionPlan
    if request.method == "POST" and request.form.get("accion") == "preprogramar":
        per = request.form.get("periodo") or "SEMANA"
        return act(lambda: psvc.preschedule_plan(g.user, per), lambda n: f"Planeamiento preprogramado: {len(n)} entrada(s) nuevas.",
                   url_for("prod.plan", periodo=per))
    if request.method == "POST" and request.form.get("accion") == "validar_cambio":
        pl = db().get(ProductionPlan, int(request.form.get("plan_id") or 0)) or abort(404)
        per = pl.periodo
        return act(lambda: psvc.validate_plan_change(g.user, pl, request.form.get("aprobar") == "1", request.form.get("comentario", "")),
                   "Cambio de programa resuelto.", url_for("prod.plan", periodo=per))
    if request.method == "POST" and request.form.get("accion") == "modificar":
        f = request.form
        pl = db().get(ProductionPlan, int(f.get("plan_id") or 0)) or abort(404)
        return act(lambda: psvc.update_plan(g.user, pl, f_float("cantidad", True), f.get("comentario", ""), f_date("fecha")),
                   lambda r: ("Cambio propuesto: lo valida el Jefe de Producción." if r is not None
                               else "Programación modificada."), url_for("prod.plan", periodo=pl.periodo))
    if request.method == "POST":
        f = request.form
        # la periodicidad es la del selector superior de la pantalla (no se repite en el formulario)
        return act(lambda: psvc.add_plan(g.user, f.get("periodo"), f_date("fecha", True), f.get("product_code", "").strip().upper().split(" ")[0],
                                         f_float("cantidad", True), f.get("line_code") or None, f.get("comentario", "")),
                   "Plan registrado.", url_for("prod.plan", periodo=f.get("periodo", "DIA")))
    periodo = request.args.get("periodo", "DIA")
    d = psvc.plan_vs_real(periodo, f_date("desde"), f_date("hasta"))
    from ..services import charts
    graf = charts.line([("Plan", [(f"{k:%d/%m}", v["plan"]) for k, v in d["serie"]]),
                        ("Real (liquidado)", [(f"{k:%d/%m}", v["real"]) for k, v in d["serie"]])], "und", title="Plan vs real")
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP", "C3"])).order_by(Product.code)).scalars())
    entradas = list(db().execute(select(ProductionPlan).where(ProductionPlan.periodo == d["periodo"],
                                                              ProductionPlan.fecha >= psvc._inicio(d["periodo"], d["desde"]),
                                                              ProductionPlan.fecha <= d["hasta"])
                                 .order_by(ProductionPlan.fecha.desc(), ProductionPlan.id.desc())).scalars())
    req = psvc.requirements(d["periodo"] if d["periodo"] != "DIA" else "DIA")
    faltan = [(r, psvc.missing_materials_tracking(r)) for r in db().execute(
        select(ProductionRequest).where(ProductionRequest.estado.in_(psvc.OPEN_REQ)).order_by(ProductionRequest.id)).scalars()]
    faltan = [(r, m) for r, m in faltan if m]
    estados = {e.id: psvc.plan_status(e) for e in entradas}
    return render_template("prod_plan.html", d=d, graf=graf, products=products, lineas=PRODUCTION_LINES, hoy=date.today(),
                           entradas=entradas, req=req, faltan=faltan, estados=estados,
                           nombre_periodo={"DIA": "diario", "SEMANA": "semanal", "MES": "mensual"}[d["periodo"]])


@bp.route("/partes", methods=["GET", "POST"])
@perm_required("produccion.partes_ver")
def reports():
    """Partes de producción: un solo formato (Registrar ahora / Programar), programación en tarjetas editables y
    partes recientes con rendimiento y desmedro."""
    from ..catalogs import PRODUCTION_LINES
    from ..models import ProductionReport
    from ..services import parte as ptsvc
    from ..services.core import param
    if request.method == "POST":
        if "produccion.liquidar" not in g.perms:
            abort(403)
        f = request.form
        r = db().get(ProductionReport, int(f.get("parte_id") or 0)) or abort(404)
        if f.get("accion") == "editar":
            return act(lambda: ptsvc.edit_program(g.user, r, f_date("fecha"), f_float("cantidad"), f.get("motivo", ""),
                                                  f.get("hora_inicio"), f.get("hora_fin")),
                       "Programación actualizada.", url_for("prod.reports"))
        abort(400)
    a = request.args
    visibles = ptsvc.lines_for(g.user)  # ronda 23-oct-2026: cada asistente ve sus líneas
    q = select(ProductionReport).where(ProductionReport.linea.in_(visibles), ProductionReport.estado != "PROGRAMADO")
    desde, hasta = f_date("desde") or date.today() - timedelta(days=7), f_date("hasta")
    q = q.where(ProductionReport.fecha >= desde)
    if hasta:
        q = q.where(ProductionReport.fecha <= hasta)
    if a.get("linea") in visibles:
        q = q.where(ProductionReport.linea == a["linea"])
    if a.get("estado"):
        q = q.where(ProductionReport.estado == a["estado"])
    rows = list(db().execute(q.order_by(ProductionReport.fecha.desc(), ProductionReport.id.desc()).limit(120)).scalars())
    programados = list(db().execute(select(ProductionReport).where(ProductionReport.linea.in_(visibles),
                                                                   ProductionReport.estado == "PROGRAMADO")
                                    .order_by(ProductionReport.fecha, ProductionReport.id)).scalars())
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP", "C3"])).order_by(Product.code)).scalars())
    return render_template("prod_reports.html", rows=rows, lineas=[x for x in PRODUCTION_LINES if x[0] in visibles], hoy=date.today(),
                           products=products, programados=programados, turnos=param("turnos_produccion", []) or [],
                           estados=ptsvc.ESTADOS_PARTE, no_editables=ptsvc.NO_EDITABLES, f=a, desde=desde,
                           formato_hora=(param("formato_hora", "24H") or "24H").upper(), fmt_hora=ptsvc.fmt_hora,
                           envasado=",".join(ptsvc.LINEAS_ENVASADO))
