"""Pantallas de Producción de la ronda del 23-oct-2026: parte en línea (iniciar, pausar, reanudar, finalizar), bloqueo de
Calidad, tablero OEE, Control de producción (formato de Producción), asistencia, productividad, receta y configuración.
Comparten el blueprint de Producción."""
import json
import os
from datetime import date, timedelta

from flask import abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import BOMLine, ProductGTIN, ProductionReport, Worker
from ..services import attendance as asvc
from ..services import parte as ptsvc
from ..services import production as psvc
from ..services.core import BusinessError, coerce_param, param, set_param
from .common import act, f_date, f_float, perm_required
from .produccion import bp


@bp.route("/parte/nuevo", methods=["POST"])
@perm_required("produccion.liquidar")
def part_new():
    f = request.form.to_dict()
    f["fecha"] = f_date("fecha") or date.today()
    pid = f.get("parte_id")
    r = db().get(ProductionReport, int(pid)) if pid else None
    return act(lambda: ptsvc.start(g.user, f, r), "Parte iniciado.", url_for("prod.reports"),
               redirect_fn=lambda x: url_for("prod.part_detail", pid=x.id))


@bp.route("/parte/<int:pid>", methods=["GET", "POST"])
@perm_required("produccion.ver", "calidad.bloquear_parte")
def part_detail(pid):
    r = db().get(ProductionReport, pid) or abort(404)
    if not ptsvc.can_see_line(g.user, r.linea) and "calidad.bloquear_parte" not in g.perms:
        abort(403)
    back = url_for("prod.part_detail", pid=pid)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "pausar":
            def _p():
                from ..services.distribution import save_upload
                foto = save_upload(request.files.get("foto"), current_app.config["UPLOAD_DIR"], f"parada_{r.id}")
                return ptsvc.pause(g.user, r, f.get("causa"), foto)
            return act(_p, "Producción pausada.", back)
        if acc == "reanudar":
            return act(lambda: ptsvc.resume(g.user, r, f.get("observacion", "")), "Producción reanudada.", back)
        if acc == "finalizar":
            pallets = [{"destino": d, "cantidad": float(q)} for d, q in zip(f.getlist("pallet_destino"), f.getlist("pallet_cantidad"))
                       if (q or "").strip()]
            defectos = {c: v for c, v in zip(f.getlist("defecto_causa"), f.getlist("defecto_und")) if (v or "").strip()}
            colab = [{"nombre": n, "inicio": i, "fin": fi, "refrigerio_min": rf, "kg": kg} for n, i, fi, rf, kg in
                     zip(f.getlist("col_nombre"), f.getlist("col_inicio"), f.getlist("col_fin"), f.getlist("col_refrigerio"),
                         f.getlist("col_kg")) if n.strip()]
            datos = {k: f.get(k) for k in ("hora_fin", "refrigerio_min", "operarios", "unidades", "unidades_sueltas", "granel_kg",
                                           "mp_kg", "cal3_kg", "desmedro_kg", "sobrante_kg", "observacion")}
            datos.update(pallets=pallets, defectos=defectos, colaboradores=colab)
            return act(lambda: ptsvc.finish(g.user, r, datos),
                       lambda x: f"Parte finalizado: rendimiento {x.rendimiento_pct}%"
                       + (f", OEE {x.indicadores['oee']}% ({x.indicadores['calificacion']})" if (x.indicadores or {}).get("oee") is not None else "")
                       + ".", back)
        if acc == "estado":
            return act(lambda: ptsvc.set_state(g.user, r, f.get("estado"), f.get("motivo", "")), "Estado actualizado.", back)
        if acc == "bloquear":
            return act(lambda: ptsvc.block(g.user, r, f.get("motivo", "")), "Parte bloqueado por Calidad.", back)
        if acc == "liberar":
            return act(lambda: ptsvc.release(g.user, r, f.get("motivo", ""), f.get("estado") or "REPROCESO"), "Parte liberado.", back)
        abort(400)
    ideal = ptsvc.ideal_output(r.linea, r.peso_entrada_kg, r.presentacion_kg)
    return render_template("part_detail.html", r=r, causas=ptsvc.causes(r.tipo), defectos=param("causas_defecto", []) or [],
                           estados=ptsvc.ESTADOS_PARTE, ideal=ideal,
                           destinos=["DESPACHO", "ENVASADO", "PRODUCCION", "ALMACÉN PT", "ALMACÉN MP", "SERV. EXTERNO",
                                     "OBSERVADO", "SEL. MANUAL", "CALIDAD 3", "DESMEDRO"],
                           workers=list(db().execute(select(Worker).where(Worker.activo.is_(True)).order_by(Worker.nombre)).scalars()),
                           gtin=db().get(ProductGTIN, r.ean) if r.ean else None)


@bp.route("/tablero")
@perm_required("produccion.ver")
def oee_dashboard():
    a = request.args
    d = ptsvc.dashboard(g.user, f_date("desde"), f_date("hasta"), a.get("linea", ""), a.get("turno", ""), a.get("maquina", ""))
    from ..services import charts
    graf = {"oee": charts.bars([(x["linea"], x["oee"]) for x in d["lineas"]], "%", title="OEE por línea"),
            "merma": charts.bars([(x["linea"], x["merma_pct"]) for x in d["lineas"]], "%", title="% merma por línea", color=7),
            "causas": charts.bars([(k, v) for k, v in d["causas"]], "min", title="Tiempo muerto por causa (min)", color=3),
            "defectos": charts.bars([(k, v) for k, v in d["defectos"]], "und", title="Defectos por causa", color=1),
            "serie": charts.line([("OEE %", [(f"{k:%d/%m}", v) for k, v in d["serie_oee"]])], "%", title="OEE diario")}
    return render_template("oee_dashboard.html", d=d, graf=graf, lineas=ptsvc.lines_for(g.user),
                           turnos=param("turnos_produccion", []) or [], maquinas=sorted((param("velocidad_nominal", {}) or {}).keys()),
                           f=a)


@bp.route("/control")
@perm_required("produccion.ver", "informes.produccion")
def control():
    periodo = request.args.get("periodo", "DIA")
    d = ptsvc.control_report(periodo, f_date("fecha") or date.today())
    from ..services import charts
    verde = ["#0e7a3d", "#7ab829"]
    nombres = [f["grupo"] for f in d["filas"]]
    graf = {"plan_real": charts.columns(nombres, [("Plan (kg)", [f["plan"] or f["capacidad"] for f in d["filas"]]),
                                                  ("Real (kg)", [f["real"] for f in d["filas"]])], "kg",
                                        title="Producción por línea (kg)", colors=verde),
            "kg": charts.columns(nombres, [("kg", [f["real"] for f in d["filas"]])], "kg", width=420, height=230,
                                 title="kg por línea", colors=verde),
            "kgh": charts.columns(nombres, [("kg/h", [f["kg_h"] for f in d["filas"]])], "kg/h", width=420, height=230,
                                  title="kg/h por línea", colors=verde),
            "asis": charts.donut(d["asistencia_pct"], "Asistencia general", colors=verde)}
    return render_template("control_produccion.html", d=d, graf=graf)


@bp.route("/asistencia", methods=["GET", "POST"])
@perm_required("produccion.ver", "produccion.asistencia")
def attendance():
    fecha = f_date("fecha") or date.today()
    back = url_for("prod.attendance", fecha=fecha.isoformat())
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "colaborador":
            w = db().get(Worker, int(f["id"])) if f.get("id") else None
            return act(lambda: asvc.save_worker(g.user, f, w), "Colaborador guardado.", back)
        marcas = {k[7:]: v for k, v in f.items() if k.startswith("estado_")}
        obs = {k[4:]: v for k, v in f.items() if k.startswith("obs_")}
        return act(lambda: asvc.register_day(g.user, fecha, marcas, obs), lambda n: f"Asistencia registrada ({n}).", back)
    from ..catalogs import PRODUCTION_LINES
    return render_template("attendance.html", fecha=fecha, workers=list(db().execute(select(Worker).order_by(Worker.linea, Worker.nombre)).scalars()),
                           dia=asvc.day(fecha), estados=asvc.states(), puede=asvc.can_register(g.user),
                           resumen=asvc.summary(fecha - timedelta(days=29), fecha), lineas=PRODUCTION_LINES)


@bp.route("/productividad")
@perm_required("produccion.ver")
def productivity():
    d = ptsvc.productivity(g.user, f_date("desde"), f_date("hasta"))
    from ..services import charts
    graf = charts.bars([(x["nombre"], x["kg_hora"]) for x in d["filas"] if x["kg_hora"]], "kg/h", title="kg por hora por colaborador")
    return render_template("productivity.html", d=d, graf=graf)


@bp.route("/bom/editar", methods=["POST"])
@perm_required("produccion.bom_aprobar")
def bom_edit():
    ln = db().get(BOMLine, int(request.form.get("line_id") or 0)) or abort(404)
    return act(lambda: psvc.edit_bom_line(g.user, ln, f_float("cantidad"), request.form.get("componente"), request.form.get("motivo", "")),
               "Receta modificada.", url_for("prod.bom", producto=request.form.get("producto", "")))


PARAMS_PRODUCCION = ["velocidad_nominal", "oee_calificacion", "causas_parada", "causas_paro_planificado", "causas_defecto",
                     "turnos_produccion", "tolerancia_rendimiento", "tope_horas_of", "dias_produccion_por_tipo",
                     "produccion_alcance_usuarios", "almacenes_produccion", "ean_validacion", "asistencia_estados",
                     "umbral_merma_pct"]


@bp.route("/configuracion", methods=["GET", "POST"])
@perm_required("produccion.configurar")
def prod_config():
    from ..models import Param
    back = url_for("prod.prod_config")
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "gs1":
            def _gs1():
                arch = request.files.get("archivo")
                if not arch or not arch.filename.lower().endswith((".xlsx", ".xlsm")):
                    raise BusinessError("Suba la tabla GS1 en Excel (.xlsx).")
                up = current_app.config["UPLOAD_DIR"]
                os.makedirs(up, exist_ok=True)
                path = os.path.join(up, f"gs1_{os.urandom(4).hex()}.xlsx")
                arch.save(path)
                return ptsvc.import_gtins(g.user, path)
            return act(_gs1, lambda r: f"{r[0]} código(s) GS1 cargados." + (f" Errores: {' | '.join(r[1][:5])}" if r[1] else ""), back + "#gs1")
        key = f.get("key")
        if key not in PARAMS_PRODUCCION:
            abort(400)
        p = db().get(Param, key) or abort(404)
        return act(lambda: set_param(key, coerce_param(p.tipo, f.get("valor", "")), g.user), "Parámetro guardado.", back + f"#{key}")
    params = [db().get(Param, k) for k in PARAMS_PRODUCCION]
    return render_template("prod_config.html", params=[p for p in params if p], json=json,
                           gtins=list(db().execute(select(ProductGTIN).order_by(ProductGTIN.product_code).limit(500)).scalars()))
