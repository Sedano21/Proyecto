"""V30 (12-nov-2026): ubicación de lotes, clientes sin movimiento y facturas de reserva de SAP sin entrega."""
from flask import Blueprint, abort, g, render_template, request, url_for

from ..db import db
from ..models import Customer, SapReserveInvoiceLine, StockLot
from ..services import facturas_reserva as frsvc
from ..services import sap_sl, v30
from .common import act, perm_required

bp = Blueprint("v30", __name__)


@bp.route("/almacen/lote/<int:lid>/ubicacion", methods=["POST"])
@perm_required("stock.ubicacion")
def lot_location(lid):
    lot = db().get(StockLot, lid) or abort(404)
    volver = request.form.get("volver", "")
    volver = volver if volver.startswith("/") and not volver.startswith("//") else url_for("alm.stock")
    return act(lambda: v30.set_location(g.user, lot, request.form.get("ubicacion", "")),
               f"Ubicación del lote {lot.lote} actualizada.", volver + f"#lote{lot.id}")


@bp.route("/comercial/clientes-sin-movimiento", methods=["GET", "POST"])
@perm_required("clientes.inactivos")
def inactive_customers():
    if request.method == "POST":
        f = request.form
        ids = [int(x) for x in f.getlist("cid") if x.isdigit()]
        accion = f.get("accion", "")

        def _do():
            if not ids:
                from ..services.core import BusinessError
                raise BusinessError("Elija al menos un cliente.")
            for cid in ids:
                c = db().get(Customer, cid) or abort(404)
                v30.decidir(g.user, c, accion, f.get("motivo", ""))
            return len(ids)
        return act(_do, lambda n: f"{n} cliente(s) {'excluido(s)' if accion == 'EXCLUIR' else 'incluido(s)'}.",
                   url_for("v30.inactive_customers", ver=request.args.get("ver", "PENDIENTES")))
    ver = request.args.get("ver", "PENDIENTES")
    ver = ver if ver in ("PENDIENTES", "EXCLUIDOS", "INCLUIDOS") else "PENDIENTES"
    d = v30.inactivos(ver=ver)
    from .common import paginate
    d["filas"] = paginate(d["filas"])  # V32
    return render_template("v30_clientes_inactivos.html", d=d, ver=ver)


@bp.route("/logistica/facturas-reserva", methods=["GET", "POST"])
@perm_required("facturas_reserva.ver", "facturas_reserva.aprobar")
def reserve_invoices():
    if request.method == "POST":
        f = request.form
        lineas = [x for x in (db().get(SapReserveInvoiceLine, int(i)) for i in f.getlist("lid") if i.isdigit()) if x]
        aprobar = f.get("accion") == "aprobar"
        return act(lambda: frsvc.decidir(g.user, lineas, aprobar, f.get("motivo", "")),
                   lambda n: f"{n} línea(s) {'aprobadas para' if aprobar else 'fuera de'} la preprogramación de producción.",
                   url_for("v30.reserve_invoices"))
    filas = frsvc.vigentes()
    q = (request.args.get("q") or "").strip().upper()
    if q:
        filas = [x for x in filas if q in (x.cliente or "").upper() or q in x.product_code.upper() or q in x.numero.upper()
                 or q in (x.ov_numero or "")]
    from ..services.core import param
    from .common import paginate
    total_pend = sum(x.pendiente for x in filas)
    n_fact = len({x.numero for x in filas})
    filas = paginate(filas)  # V32
    return render_template("v30_facturas_reserva.html", filas=filas, total_pend=total_pend, n_fact=n_fact, q=q, job=sap_sl.job_state("RESERVAS"),
                           ult=param("sap_reservas_ultimo", {}) or {}, configurado=sap_sl.configured(),
                           puede_traer=bool(g.perms & {"facturas_reserva.ver", "facturas_reserva.aprobar"}),
                           puede_aprobar="facturas_reserva.aprobar" in g.perms)
