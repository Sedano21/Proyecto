"""V25 (08-nov-2026): chat interno uno a uno entre usuarios."""
from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for

from ..db import db
from ..services import chat as svc
from .common import act, perm_required

bp = Blueprint("chat", __name__, url_prefix="/chat")


@bp.route("/", methods=["GET", "POST"])
@perm_required("chat.usar")
def home():
    con = request.values.get("con", type=int)
    if request.method == "POST":
        def _env():
            svc.enviar(g.user, request.form.get("para_id"), request.form.get("texto"),
                       request.form.get("ref_url", ""), request.form.get("ref_titulo", ""))
        return act(_env, None, url_for("chat.home", con=request.form.get("para_id", type=int)))
    otro, msgs = (None, [])
    if con:
        otro, msgs = svc.conversacion(g.user, con)
        db().commit()
    return render_template("chat.html", convs=svc.conversaciones(g.user), contactos=svc.contactos(g.user), otro=otro,
                           msgs=msgs, ref_url=request.args.get("ref_url", ""), ref_titulo=request.args.get("ref_titulo", ""))


@bp.route("/no-leidos")
@perm_required("chat.usar")
def unread():
    return jsonify(n=svc.no_leidos(g.user))
