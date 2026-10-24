"""Mantenimiento integral (ronda UX 24-oct-2026): flota (preventivo y correctivo) y saneamiento (zonas y unidades)."""
from flask import Blueprint, abort, current_app, g, render_template, request, url_for

from ..db import db
from ..models import Breakdown, MaintenancePlan, SanitationZone, Vehicle
from ..services import maintenance as msvc
from ..services.distribution import save_upload
from .common import act, perm_required

bp = Blueprint("mant", __name__, url_prefix="/mantenimiento")
TABS = [("flota", "Preventivo"), ("correctivo", "Correctivo"), ("saneamiento", "Zonas"), ("unidades", "Fumigación de unidades")]


@bp.route("/", methods=["GET", "POST"])
@perm_required("mantenimiento.ver", "mantenimiento.flota", "saneamiento.registrar")
def home():
    tab = request.args.get("tab") or request.form.get("tab") or "flota"
    back = url_for("mant.home", tab=tab)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        up = current_app.config["UPLOAD_DIR"]
        if acc == "plan":
            v = db().get(Vehicle, int(f.get("vehicle_id") or 0)) or abort(404)
            p = db().get(MaintenancePlan, int(f["plan_id"])) if f.get("plan_id") else None
            return act(lambda: msvc.save_plan(g.user, v, f, p), "Plan preventivo guardado.", back)
        if acc == "realizado":
            p = db().get(MaintenancePlan, int(f.get("plan_id") or 0)) or abort(404)
            return act(lambda: msvc.complete_plan(g.user, p, f.get("fecha"), f.get("km"), f.get("costo"), f.get("nota", "")),
                       "Mantenimiento preventivo registrado.", back)
        if acc == "averia":
            v = db().get(Vehicle, int(f.get("vehicle_id") or 0)) or abort(404)
            return act(lambda: msvc.report_breakdown(g.user, v, f.get("descripcion", ""), f.get("severidad"), f.get("km"),
                                                     save_upload(request.files.get("foto"), up, f"averia_{v.id}")),
                       "Avería reportada.", url_for("mant.home", tab="correctivo"))
        if acc == "averia_estado":
            b = db().get(Breakdown, int(f.get("breakdown_id") or 0)) or abort(404)
            return act(lambda: msvc.update_breakdown(g.user, b, f.get("estado"), f.get("nota", ""), f.get("fecha_programada"),
                                                     f.get("taller", ""), f.get("costo")), "Avería actualizada.", back)
        if acc == "zona":
            z = db().get(SanitationZone, int(f["zone_id"])) if f.get("zone_id") else None
            return act(lambda: msvc.save_zone(g.user, f, z), "Zona guardada.", back)
        if acc == "saneamiento":
            z = db().get(SanitationZone, int(f["zone_id"])) if f.get("zone_id") else None
            v = db().get(Vehicle, int(f["vehicle_id"])) if f.get("vehicle_id") else None
            return act(lambda: msvc.log_sanitation(g.user, f.get("tipo"), f.get("fecha"), z, v, f.get("responsable", ""),
                                                   f.get("producto", ""), f.get("certificado", ""), f.get("vence"),
                                                   f.get("observacion", ""),
                                                   save_upload(request.files.get("evidencia"), up, "saneamiento")),
                       "Registro guardado en la bitácora.", back)
        abort(400)
    from ..models import Warehouse
    from sqlalchemy import select
    return render_template("maintenance.html", tab=tab, tabs=TABS, d=msvc.board(), estados=msvc.ESTADOS_AVERIA,
                           tipos=msvc.TIPOS_SANEAMIENTO, almacenes=list(db().execute(select(Warehouse)).scalars()))
