"""V22 (06-nov-2026): Mantenimiento de planta y Limpieza (Jefe de Mantenimiento, técnicos y personal de limpieza)."""
import os
from datetime import date, timedelta

from flask import Blueprint, Response, abort, current_app, g, render_template, request, url_for

from ..db import db
from ..models import CleaningAssignment, SanitationZone, WorkOrder, Worker
from ..services import limpieza as lp
from ..services import mant_trabajos as mt
from ..services import tickets as tk
from ..services.core import BusinessError
from ..services.distribution import save_evidences
from .common import act, f_date, paginate, perm_required

bp = Blueprint("mant2", __name__, url_prefix="/planta")


def _up():
    return current_app.config["UPLOAD_DIR"]


@bp.route("/")
@perm_required("mantenimiento.gestionar", "tickets.ver_todos")
def panel():
    """Panel del Jefe de Mantenimiento: tickets, trabajos del día y próximos, limpieza de hoy, máquinas y fumigaciones."""
    hoy = date.today()
    from ..services import maintenance as msvc
    abiertos = tk.visible(g.user, "MANTENIMIENTO", "ABIERTOS")
    hoy_ots = [w for w in mt.board(None, hoy, "ABIERTOS")]
    proximos = mt.board(hoy + timedelta(days=1), hoy + timedelta(days=14), "ABIERTOS")
    limp = lp.day(hoy)
    zonas = [(z, msvc.zone_status(z, hoy)) for z in lp.zones()]
    return render_template("v22_mant_panel.html", tickets=abiertos[:12], hoy_ots=hoy_ots, proximos=proximos, limp=limp,
                           prog=sum(c.veces for c in limp), hechas=sum(min(len(c.checks or []), c.veces) for c in limp),
                           maquinas=mt.machine_summary(30), dias=mt.alert_days(), zonas=zonas, hoy=hoy,
                           rep=mt.report(hoy.replace(day=1), hoy), lugar=mt.lugar)


@bp.route("/configuracion", methods=["POST"])
@perm_required("mantenimiento.gestionar")
def config():
    return act(lambda: mt.set_alert_days(g.user, request.form.get("dias", "")),
               lambda d: "Avisos de preventivos: " + ", ".join(f"{x} días antes" if x else "el mismo día" for x in d) + ".",
               url_for("mant2.panel"))


# ------------------------------------------------------------------ trabajos
@bp.route("/trabajos", methods=["GET", "POST"])
@perm_required("mantenimiento.gestionar", "mantenimiento.ejecutar")
def works():
    back = url_for("mant2.works", estado=request.args.get("estado", ""), tipo=request.args.get("tipo", ""))
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "nuevo":
            return act(lambda: mt.save(g.user, f), lambda w: f"Trabajo #{w.id} programado.", back)
        if acc == "cronograma":
            def _imp():
                from ..services.finance import save_document
                ruta = save_document(request.files.get("archivo"), _up(), "cronograma_mant")
                if not ruta:
                    raise BusinessError("Adjunte el Excel del cronograma.")
                return mt.import_schedule(g.user, os.path.join(_up(), ruta))
            return act(_imp, lambda r: f"Cronograma cargado: {r[0]} trabajos programados."
                       + (" Filas con error: " + "; ".join(r[1][:5]) if r[1] else ""), back)
        wo = db().get(WorkOrder, int(f.get("id") or 0)) or abort(404)
        if acc == "asignar":
            return act(lambda: mt.assign(g.user, wo, f.get("worker_id")), "Trabajo asignado.", back)
        if acc == "inicio":
            return act(lambda: mt.start(g.user, wo, save_evidences(request.files.getlist("fotos"), _up(), f"ot{wo.id}_antes")),
                       "Trabajo iniciado (foto de antes registrada).", back)
        if acc == "fin":
            rep = [{"pieza": p, "cantidad": q, "costo": c} for p, q, c in
                   zip(f.getlist("pieza"), f.getlist("pieza_cant"), f.getlist("pieza_costo"))]
            return act(lambda: mt.finish(g.user, wo, save_evidences(request.files.getlist("fotos"), _up(), f"ot{wo.id}_despues"),
                                         f.get("observacion", ""), rep, f.get("costo")),
                       "Trabajo terminado (foto de después registrada).", back)
        if acc == "cancelar":
            return act(lambda: mt.cancel(g.user, wo, f.get("motivo", "")), "Trabajo cancelado.", back)
        abort(404)
    if "mantenimiento.gestionar" not in g.perms:
        rows = mt.mine(g.user)
    else:
        hoy = date.today()
        rows = mt.board(f_date("desde") or hoy - timedelta(days=30), f_date("hasta") or hoy + timedelta(days=60),
                        request.args.get("estado") or None, request.args.get("tipo") or None)
    return render_template("v22_trabajos.html", rows=paginate(rows), tecnicos=mt.technicians(), zonas=lp.zones(),
                           maquinas=mt.machines(), tipos=mt.TIPOS, estados=mt.ESTADOS, lugar=mt.lugar,
                           gestiona="mantenimiento.gestionar" in g.perms, hoy=date.today(),
                           estado=request.args.get("estado", ""), tipo=request.args.get("tipo", ""))


@bp.route("/informe")
@perm_required("mantenimiento.gestionar", "mantenimiento.ver")
def report():
    hoy = date.today()
    desde = f_date("desde") or hoy.replace(day=1)
    hasta = f_date("hasta") or hoy
    if request.args.get("salida") == "xlsx":
        return Response(mt.report_excel(desde, hasta),
                        headers={"Content-Disposition": f"attachment; filename=trabajos_mantenimiento_{desde:%Y%m%d}_{hasta:%Y%m%d}.xlsx"},
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return render_template("v22_mant_informe.html", d=mt.report(desde, hasta), desde=desde, hasta=hasta, lugar=mt.lugar,
                           tiempos=tk.response_times(desde, hasta, "MANTENIMIENTO"), tipos=mt.TIPOS, estados=mt.ESTADOS)


# ------------------------------------------------------------------ máquinas de producción
@bp.route("/maquinas", methods=["GET", "POST"])
@perm_required("maquinas.ver")
def machines():
    back = url_for("mant2.machines")
    if request.method == "POST":
        f = request.form
        params = {k: v for k, v in zip(f.getlist("param_nombre"), f.getlist("param_valor")) if (k or "").strip()}
        return act(lambda: mt.log_machine(g.user, f.get("maquina"), f.get("tipo"), f.get("detalle", ""), f.get("pieza", ""),
                                          f.get("costo"), params, save_evidences(request.files.getlist("fotos"), _up(),
                                                                                 f"maq_{f.get('maquina')}"), f.get("proxima")),
                   "Registro de máquina guardado.", back)
    return render_template("v22_maquinas.html", filas=mt.machine_summary(int(request.args.get("dias") or 30)),
                           tipos=mt.TIPOS_MAQUINA, maquinas=mt.machines())


# ------------------------------------------------------------------ limpieza
@bp.route("/limpieza", methods=["GET", "POST"])
@perm_required("limpieza.gestionar", "limpieza.marcar")
def cleaning():
    fecha = f_date("fecha") or date.today()
    back = url_for("mant2.cleaning", fecha=fecha.isoformat())
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "marcar":
            c = db().get(CleaningAssignment, int(f.get("id") or 0)) or abort(404)
            fotos = save_evidences(request.files.getlist("foto"), _up(), f"limpieza_{c.id}", videos=False)
            return act(lambda: lp.mark(g.user, c, fotos[0] if fotos else ""), "Limpieza marcada.", back)
        if acc == "asignar":
            return act(lambda: lp.assign(g.user, f_date("fecha_asig") or fecha, f.get("worker_id"), f.getlist("zona"),
                                         f.get("veces") or 1, f.get("turno", ""), f.get("nota", "")),
                       lambda r: f"Asignadas {len(r)} zona(s).", back)
        if acc == "copiar":
            return act(lambda: lp.copy_day(g.user, f_date("desde_fecha") or fecha - timedelta(days=1), fecha),
                       lambda n: f"Se copiaron {n} asignaciones.", back)
        if acc == "quitar":
            c = db().get(CleaningAssignment, int(f.get("id") or 0)) or abort(404)
            return act(lambda: lp.remove(g.user, c), "Asignación quitada.", back)
        if acc == "zona":
            z = db().get(SanitationZone, int(f["zid"])) if f.get("zid") else None
            return act(lambda: lp.save_zone(g.user, f, z), "Zona guardada.", back)
        if acc == "persona":
            w = db().get(Worker, int(f["wid"])) if f.get("wid") else None
            return act(lambda: lp.save_person(g.user, f, w), "Datos del personal guardados.", back)
        abort(404)
    if "limpieza.gestionar" not in g.perms:
        w, mias = lp.mine(g.user, fecha)
        return render_template("v22_mi_limpieza.html", w=w, mias=mias, fecha=fecha)
    hoy = date.today()
    desde = f_date("desde") or hoy - timedelta(days=14)
    from ..models import User
    from sqlalchemy import select
    cuentas = list(db().execute(select(User).where(User.role_code.in_(("PERSONAL_LIMPIEZA", "TECNICO_MANTENIMIENTO")),
                                                   User.activo.is_(True)).order_by(User.nombre)).scalars())
    return render_template("v22_limpieza.html", fecha=fecha, dia=lp.day(fecha), staff=lp.staff(), todos=lp.staff(False),
                           zonas=lp.zones(), todas_zonas=lp.zones(False), perf=lp.performance(desde, hoy), desde=desde,
                           cuentas=cuentas)
