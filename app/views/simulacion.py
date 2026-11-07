"""Simulación integral de operaciones — ENTORNO DE PRUEBAS (07-nov-2026): generar, consultar, validar y limpiar."""
from collections import Counter

from flask import Blueprint, abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import SimRun
from ..services import simulacion as sim
from ..services.core import BusinessError
from .common import act, perm_required

bp = Blueprint("sim", __name__, url_prefix="/admin/simulacion")


@bp.route("/", methods=["GET", "POST"])
@perm_required("simulacion.ver", "simulacion.gestionar")
def home():
    back = url_for("sim.home")
    if request.method == "POST":
        if "simulacion.gestionar" not in g.perms:
            abort(403)
        acc = request.form.get("accion")
        up = current_app.config["UPLOAD_DIR"]
        if acc in ("generar", "regenerar"):
            def _gen():
                from .. import simulacion_escenario as se
                if acc == "regenerar":
                    sim.limpiar(g.user, up)
                    db().commit()
                run = se.generar(g.user, up, dias=int(request.form.get("dias") or 14))
                from ..services import simulacion_validacion as sv
                sv.guardar(run, current_app._get_current_object())
                return run
            return act(_gen, lambda r: f"Simulación #{r.id} {r.estado.lower()}: {r.resumen.get('conteos', {}).get('ov', 0)} OV "
                       f"en {r.dias} días. Revise la validación abajo.", back)
        if acc == "validar":
            def _val():
                run = sim.ultima()
                if run is None or run.estado == "LIMPIADA":
                    raise BusinessError("No hay simulación cargada.")
                from ..services import simulacion_validacion as sv
                return sv.guardar(run, current_app._get_current_object())
            return act(_val, "Validación integral actualizada.", back)
        if acc == "limpiar":
            return act(lambda: sim.limpiar(g.user, up),
                       lambda r: f"Datos de prueba eliminados: {r['eliminados']} registros creados por la simulación; "
                       f"{r['restaurados']} registros existentes devueltos a su valor previo.", back)
        abort(400)
    run = sim.ultima()
    corridas = list(db().execute(select(SimRun).order_by(SimRun.id.desc()).limit(10)).scalars())
    rechazos = Counter((x["paso"], x["detalle"]) for x in (run.resumen or {}).get("rechazos", [])) if run else Counter()
    return render_template("simulacion.html", run=run, corridas=corridas, motivo=sim.habilitada(),
                           tablas=sim.conteo_por_tabla(run.id) if run and run.estado != "LIMPIADA" else {},
                           rechazos=rechazos.most_common(40), puede="simulacion.gestionar" in g.perms)
