"""Pantallas de la marcha blanca (respuestas del 22-oct-2026): observaciones de los usuarios, turnos del personal,
conciliación con SAP y registro en contingencia."""
import io
import os
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, send_file, url_for
from sqlalchemy import select

from ..db import db
from ..models import Observation, SapDiscrepancy, Shift, User, UserShift
from ..services import conciliation as csvc
from ..services import observations as osvc
from ..services import shifts as ssvc
from ..services.core import BusinessError, audit, contingency, param, set_param
from .common import act, f_date, login_required, perm_required

bp = Blueprint("mb", __name__)


# ------------------------------------------------------------------ observaciones
@bp.route("/observaciones/nueva", methods=["POST"])
@login_required
def observation_new():
    f = request.form
    volver = f.get("url") or ""
    volver = volver if volver.startswith("/") and not volver.startswith("//") else url_for("main.dashboard")

    def _do():
        captura = ""
        arch = request.files.get("captura")
        if arch and arch.filename:
            from ..services.distribution import save_upload
            captura = save_upload(arch, current_app.config["UPLOAD_DIR"], f"observacion_u{g.user.id}")
        return osvc.report(g.user, f.get("comentario", ""), f.get("url", ""), f.get("pantalla", ""), f.get("tipo", "ERROR"),
                           f.get("impide") == "1", captura, current_app.config.get("APP_VERSION", ""))
    return act(_do, lambda o: f"Observación #{o.id} registrada. Gracias: se revisa en la reunión diaria.", volver)


@bp.route("/observaciones", methods=["GET", "POST"])
@login_required
def observations():
    gestiona = "observaciones.gestionar" in g.perms
    if request.method == "POST":
        o = db().get(Observation, int(request.form.get("id") or 0)) or abort(404)
        return act(lambda: osvc.update(g.user, o, request.form.get("clasificacion"), request.form.get("estado"),
                                       request.form.get("respuesta")),
                   f"Observación #{o.id} actualizada.", url_for("mb.observations", **request.args))
    estado = request.args.get("estado", "ABIERTA" if gestiona else "")
    rows = osvc.listing(g.user, estado, request.args.get("clasificacion", ""), propias=request.args.get("propias") == "1")
    if request.args.get("formato") == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Observaciones"
        ws.append(["#", "Fecha", "Usuario", "Rol", "Pantalla", "Tipo", "Observación", "Clasificación", "Estado", "Respuesta",
                   "Versión"])
        for o in rows:
            ws.append([o.id, o.ts.strftime("%d/%m/%Y %H:%M"), o.user.nombre if o.user else "", o.user.role.nombre if o.user else "",
                       o.pantalla or o.url, osvc.TIPOS.get(o.tipo, o.tipo), o.comentario,
                       osvc.CLASIFICACION.get(o.clasificacion, o.clasificacion), osvc.ESTADOS.get(o.estado, o.estado),
                       o.respuesta, o.version])
        out = io.BytesIO()
        wb.save(out)
        return send_file(io.BytesIO(out.getvalue()), as_attachment=True, download_name=f"observaciones_{date.today():%Y%m%d}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    from collections import Counter
    todas = osvc.listing(g.user, "", "")
    return render_template("observations.html", rows=rows, gestiona=gestiona, tipos=osvc.TIPOS, clasif=osvc.CLASIFICACION,
                           estados=osvc.ESTADOS, estado=estado, clasificacion=request.args.get("clasificacion", ""),
                           conteo=Counter(o.clasificacion for o in todas if o.estado == "ABIERTA"))


@bp.route("/observaciones/captura/<int:oid>")
@login_required
def observation_capture(oid):
    o = db().get(Observation, oid) or abort(404)
    if o.user_id != g.user.id and "observaciones.gestionar" not in g.perms:
        abort(403)
    from flask import send_from_directory
    return send_from_directory(current_app.config["UPLOAD_DIR"], os.path.basename(o.captura))


# ------------------------------------------------------------------ turnos
@bp.route("/configuracion/turnos", methods=["GET", "POST"])
@perm_required("turnos.gestionar", "usuarios.administrar")
def shifts():
    s = db()
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "turno":
            sh = s.get(Shift, int(f["id"])) if f.get("id") else None
            fn = lambda: ssvc.save_shift(g.user, f.get("nombre"), f.getlist("dias"), f.get("inicio"), f.get("fin"),  # noqa: E731
                                         f.get("refrigerio_min") or 0, sh, f.get("activo", "1") == "1")
        elif acc == "asignar":
            fn = lambda: ssvc.assign_shift(g.user, f.get("user_id"), f.get("shift_id"), f_date("desde", True),  # noqa: E731
                                           f_date("hasta"), f.get("ciclo") or 1, int(f.get("semana") or 1) - 1)
        elif acc == "refuerzo":
            fn = lambda: ssvc.add_reinforcement(g.user, f.get("user_id"), f_date("desde", True), f_date("hasta"),  # noqa: E731
                                                f.get("inicio"), f.get("fin"), f.get("motivo"))
        elif acc == "retirar":
            us = s.get(UserShift, int(f["id"])) or abort(404)
            fn = lambda: ssvc.remove_assignment(g.user, us)  # noqa: E731
        else:
            abort(400)
        return act(fn, "Turnos actualizados.", url_for("mb.shifts", dia=request.args.get("dia", "")))
    try:
        dia = date.fromisoformat(request.args.get("dia") or "")
    except ValueError:
        dia = date.today()
    users = list(s.execute(select(User).where(User.activo.is_(True)).order_by(User.role_code, User.nombre)).scalars())
    asign = list(s.execute(select(UserShift).order_by(UserShift.tipo, UserShift.desde.desc())).scalars())
    vigentes = [a for a in asign if a.hasta is None or a.hasta >= date.today() - timedelta(days=7)]
    return render_template("shifts.html", turnos=list(s.execute(select(Shift).order_by(Shift.nombre)).scalars()), users=users,
                           asignaciones=vigentes, dia=dia, tabla=ssvc.schedule_table(dia), dias=ssvc.DIAS,
                           solo_turno=param("asignar_solo_personal_en_turno", True), today=date.today())


# ------------------------------------------------------------------ conciliación SAP
@bp.route("/conciliacion", methods=["GET", "POST"])
@perm_required("conciliacion.ver", "conciliacion.resolver")
def conciliation():
    if request.method == "POST":
        ids = request.form.getlist("ids")
        return act(lambda: csvc.resolve(g.user, ids, request.form.get("accion"), request.form.get("motivo")),
                   lambda n: f"{n} diferencia(s) actualizada(s).", url_for("mb.conciliation", **request.args))
    estado = request.args.get("estado", "PENDIENTE")
    area = request.args.get("area", "")
    origen = request.args.get("origen", "")
    rows = csvc.listing(estado, area, origen)
    return render_template("conciliation.html", rows=rows, estado=estado, area=area, origen=origen,
                           areas=sorted(set(csvc.AREA.values())), origenes=csvc.ORIGEN_TXT, resumen=csvc.summary(),
                           puede=lambda d: csvc.can_resolve(g.user, d), cortes=param("cortes_carga_sap", []) or [])


# ------------------------------------------------------------------ contingencia
@bp.route("/contingencia", methods=["GET", "POST"])
@perm_required("contingencia.gestionar")
def contingency_view():
    from ..models import AuditLog, now
    from ..services import alerts
    if request.method == "POST":
        def _do():
            activar = request.form.get("accion") == "activar"
            actual = contingency()
            if activar:
                motivo = (request.form.get("motivo") or "").strip()
                if not motivo:
                    raise BusinessError("Indique el motivo (por ejemplo: caída del sistema de 08:10 a 10:40; se registra "
                                        "lo trabajado en manual).")
                if actual:
                    raise BusinessError("El registro en contingencia ya está activo.")
                valor = {"activa": True, "desde": now().isoformat(timespec="minutes"), "motivo": motivo, "por": g.user.nombre}
                set_param("modo_contingencia", valor, g.user)
                alerts.emit("CONTINGENCIA", "Registro en contingencia ACTIVADO",
                            f"{motivo}. Todo lo que se registre queda marcado como «registrado en contingencia».",
                            creado_por=g.user)
            else:
                if not actual:
                    raise BusinessError("El registro en contingencia no está activo.")
                set_param("modo_contingencia", {"activa": False, "ultimo": {**actual, "hasta": now().isoformat(timespec="minutes"),
                                                                            "cerrado_por": g.user.nombre}}, g.user)
                alerts.emit("CONTINGENCIA", "Registro en contingencia DESACTIVADO",
                            f"Activo desde {actual.get('desde', '')[:16].replace('T', ' ')} ({actual.get('motivo', '')}).",
                            creado_por=g.user)
        return act(_do, "Registro en contingencia actualizado.", url_for("mb.contingency_view"))
    hist = [a for a in db().execute(select(AuditLog).where(AuditLog.accion == "PARAM_EDITADO",
                                                           AuditLog.entidad_id == "modo_contingencia")
                                    .order_by(AuditLog.ts.desc()).limit(30)).scalars()]
    marcados = db().execute(select(AuditLog).order_by(AuditLog.ts.desc()).limit(3000)).scalars()
    marcados = [a for a in marcados if (a.detalle or {}).get("registrado_en_contingencia")][:200]
    return render_template("contingency.html", actual=contingency(), hist=hist, marcados=marcados)
