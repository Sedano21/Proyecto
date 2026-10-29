"""Pantallas de Producción de la ronda del 23-oct-2026: parte en línea (iniciar, pausar, reanudar, finalizar), bloqueo de
Calidad, tablero OEE, Control de producción (formato de Producción), asistencia, productividad, receta y configuración.
Comparten el blueprint de Producción."""
import json
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


def _err(msg):
    raise BusinessError(msg)


@bp.route("/parte/nuevo", methods=["POST"])
@perm_required("produccion.liquidar")
def part_new():
    """Formato único del parte: «Registrar» lo inicia ahora; «Programar» lo deja para la fecha y horario indicados."""
    f = request.form.to_dict()
    if f.get("accion") == "programar":
        return act(lambda: ptsvc.program(g.user, f), "Parte programado.", url_for("prod.reports") + "#programados")
    f["fecha"] = f_date("fecha") or date.today()
    pid = f.get("parte_id")
    r = db().get(ProductionReport, int(pid)) if pid else None
    if r is None and f["fecha"] != date.today():
        return act(lambda: _err("«Registrar» inicia el parte hoy; para otra fecha use «Programar»."),
                   "", url_for("prod.reports"))
    return act(lambda: ptsvc.start(g.user, f, r), "Parte iniciado.", url_for("prod.reports"),
               redirect_fn=lambda x: url_for("prod.part_detail", pid=x.id))


@bp.route("/api/producto")
@perm_required("produccion.ver")
def product_api():
    """Datos del producto para validar en pantalla (presentación, tipo, GTIN)."""
    from flask import jsonify
    return jsonify(ptsvc.product_info(request.args.get("code", "")) or {})


@bp.route("/monitoreo")
@perm_required("produccion.partes_ver")
def monitor():
    """Monitoreo en tiempo real: partes en curso y del día con rendimiento y desmedro (se actualiza cada minuto)."""
    return render_template("prod_monitor.html", items=ptsvc.monitor(g.user), hoy=date.today())


@bp.route("/parte/<int:pid>", methods=["GET", "POST"])
@perm_required("produccion.partes_ver", "calidad.bloquear_parte")
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
            n = len(f.getlist("col_worker"))
            mermas = (f.getlist("col_merma") + [""] * n)[:n]
            rems = (f.getlist("col_remanente") + [""] * n)[:n]
            colab = [{"worker_id": w, "inicio": i, "fin": fi, "refrigerio_min": rf, "kg": kg, "merma_kg": me, "remanente_kg": re}
                     for w, i, fi, rf, kg, me, re in zip(f.getlist("col_worker"), f.getlist("col_inicio"), f.getlist("col_fin"),
                                                          f.getlist("col_refrigerio"), f.getlist("col_kg"), mermas, rems)]
            if len([c for c in colab if c["worker_id"]]) < len(colab):
                return act(lambda: _err("Elija el colaborador de cada tarjeta."), "", back)
            datos = {k: f.get(k) for k in ("hora_fin", "refrigerio_min", "operarios", "unidades", "unidades_sueltas", "granel_kg",
                                           "mp_kg", "cal3_kg", "desmedro_kg", "sobrante_kg", "observacion")}
            datos.update(pallets=pallets, defectos=defectos, colaboradores=colab)
            return act(lambda: ptsvc.finish(g.user, r, datos),
                       lambda x: f"Parte finalizado: rendimiento {x.rendimiento_pct}%"
                       + (f", OEE {x.indicadores['oee']}% ({x.indicadores['calificacion']})" if (x.indicadores or {}).get("oee") is not None else "")
                       + ".", back)
        if acc == "avance":
            return act(lambda: ptsvc.add_progress(g.user, r, f.get("destino"), f.get("cantidad")), "Avance registrado.", back)
        if acc == "editar":
            return act(lambda: ptsvc.edit_program(g.user, r, f_date("fecha"), f_float("cantidad"), f.get("motivo", "")),
                       "Parte actualizado.", back)
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
                           workers=list(db().execute(select(Worker).where(Worker.activo.is_(True), Worker.area == "Producción")
                                                     .order_by(Worker.nombre)).scalars()),
                           gtin=db().get(ProductGTIN, r.ean) if r.ean else None, live=ptsvc.live(r),
                           tol=ptsvc.tolerance_for(r.linea, r.presentacion_kg) or {}, no_editables=ptsvc.NO_EDITABLES,
                           formato_hora=(param("formato_hora", "24H") or "24H").upper(), fmt_hora=ptsvc.fmt_hora)


@bp.route("/tablero")
@perm_required("produccion.partes_ver")
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
@perm_required("produccion.partes_ver")
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
@perm_required("produccion.ver", "produccion.asistencia", "asistencia.area")
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
    area = asvc.area_of(g.user) or "Producción"
    return render_template("attendance.html", fecha=fecha, workers=asvc.workers_of(g.user) if asvc.area_of(g.user) else
                           list(db().execute(select(Worker).where(Worker.area == "Producción").order_by(Worker.linea, Worker.nombre)).scalars()),
                           dia=asvc.day(fecha), estados=asvc.states(), puede=asvc.can_register(g.user), area=area,
                           resumen=asvc.summary(fecha - timedelta(days=29), fecha, area=area), lineas=PRODUCTION_LINES)


@bp.route("/productividad")
@perm_required("produccion.partes_ver")
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


PARAMS_PRODUCCION = ["formato_hora", "oee_calificacion", "causas_parada", "causas_paro_planificado", "causas_defecto",
                     "turnos_produccion", "tope_horas_of", "dias_produccion_por_tipo",
                     "produccion_alcance_usuarios", "almacenes_produccion", "ean_validacion", "asistencia_estados",
                     "umbral_merma_pct"]


def _num(v, campo):
    v = (v or "").replace(",", ".").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        raise BusinessError(f"{campo}: «{v}» no es un número.")


def _save_speeds(user, f):
    """Velocidad nominal por máquina y, opcionalmente, por presentación (clave «MÁQUINA|kg»)."""
    out = {}
    for maq, pres, val in zip(f.getlist("maquina"), f.getlist("presentacion"), f.getlist("valor")):
        maq = (maq or "").strip().upper()
        v = _num(val, f"Velocidad de {maq or 'la fila'}")
        if not maq and v is None:
            continue
        if not maq:
            raise BusinessError("Indique la máquina o línea de cada velocidad.")
        if v is None:
            continue  # valor vacío = se retira la fila
        if v <= 0:
            raise BusinessError(f"{maq}: la velocidad debe ser mayor que cero.")
        pk = _num(pres, f"Presentación de {maq}")
        out[f"{maq}|{pk:g}" if pk else maq] = v
    return set_param("velocidad_nominal", out, user)


def _save_tolerances(user, f):
    reglas = []
    for lin, pres, mn, mx in zip(f.getlist("linea"), f.getlist("presentacion"), f.getlist("min_pct"), f.getlist("max_pct")):
        lin = (lin or "").strip().upper()
        mn, mx = _num(mn, f"Mínimo de {lin}"), _num(mx, f"Máximo de {lin}")
        if not lin:
            if mn is not None or mx is not None:
                raise BusinessError("Indique la línea de cada tolerancia («*» = todas, «R*» = R1, R2 y R3).")
            continue
        if mn is None and mx is None:
            continue
        if mn is not None and mx is not None and mn > mx:
            raise BusinessError(f"{lin}: el mínimo no puede ser mayor que el máximo.")
        reglas.append({"linea": lin, "presentacion_kg": _num(pres, f"Presentación de {lin}"), "min_pct": mn, "max_pct": mx})
    return set_param("tolerancia_rendimiento", reglas, user)


def _speed_rows():
    from .. import catalogs as C
    seleccion = {c for c, *_ in C.PRODUCTION_LINES if ptsvc.tipo_linea(c) == "SELECCION"}
    rows = []
    for k, v in sorted((param("velocidad_nominal", {}) or {}).items()):
        maq, _, pres = k.partition("|")
        rows.append({"maquina": maq, "presentacion": pres, "valor": v,
                     "um": "kg/h" if maq in seleccion else "und/min"})
    return rows, sorted(seleccion)


@bp.route("/configuracion", methods=["GET", "POST"])
@perm_required("produccion.configurar")
def prod_config():
    from ..models import Param
    back = url_for("prod.prod_config")
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "velocidades":
            return act(lambda: _save_speeds(g.user, f), "Velocidades nominales guardadas.", back + "#velocidad_nominal")
        if f.get("accion") == "tolerancias":
            return act(lambda: _save_tolerances(g.user, f), "Tolerancias guardadas.", back + "#tolerancia_rendimiento")
        key = f.get("key")
        if key not in PARAMS_PRODUCCION:
            abort(400)
        p = db().get(Param, key) or abort(404)
        return act(lambda: set_param(key, coerce_param(p.tipo, f.get("valor", "")), g.user), "Parámetro guardado.", back + f"#{key}")
    params = [db().get(Param, k) for k in PARAMS_PRODUCCION]
    from ..catalogs import PRODUCTION_LINES
    vel, seleccion = _speed_rows()
    return render_template("prod_config.html", params=[p for p in params if p], json=json, velocidades=vel, seleccion=seleccion,
                           tolerancias=param("tolerancia_rendimiento", []) or [], lineas=PRODUCTION_LINES,
                           pv=db().get(Param, "velocidad_nominal"), pt=db().get(Param, "tolerancia_rendimiento"),
                           gtins=list(db().execute(select(ProductGTIN).order_by(ProductGTIN.product_code).limit(500)).scalars()))
