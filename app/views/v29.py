"""V29 (11-nov-2026): notas de crédito de SAP sobre OV y balance de peso de las órdenes de fabricación de SAP."""
from flask import Blueprint, g, render_template, request

from ..services import balance_of, notas_credito_ov, sap_sl
from .common import perm_required

bp = Blueprint("v29", __name__)


@bp.route("/comercial/notas-credito-ov")
@perm_required("ov.ver", "distribucion.ver", "preparacion.registrar", "facturas.cargar")
def credit_notes():
    estado = request.args.get("estado", "")
    filas = notas_credito_ov.listado(estado if estado in ("APLICADA", "YA_DESPACHADO", "SIN_OV") else "")
    return render_template("v29_notas_credito.html", filas=filas, estado=estado, job=sap_sl.job_state("FACTURAS"),
                           puede_traer=sap_sl.configured() and "facturas.cargar" in g.perms)


@bp.route("/produccion/balance-of")
@perm_required("produccion.ver", "produccion.liquidar")
def mass_balance():
    ult = balance_of.ultimo()
    ver = request.args.get("ver", "MAL")
    filas = [f for f in ult.get("filas", []) if ver != "MAL" or not f["ok"]]
    from ..services.core import param
    return render_template("v29_balance_of.html", ult=ult, filas=filas, ver=ver, job=sap_sl.job_state("BALANCE_OF"),
                           configurado=sap_sl.configured(), tol=param("balance_of_tolerancia_pct", 0.5))
