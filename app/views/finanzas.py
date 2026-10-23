"""Finanzas (ronda 23-oct-2026): cuadro de cobranza con la guía del proceso, carga de facturas y notas de crédito
(Excel, PDF consolidado o individual, registro manual), confirmación de pagos y condiciones de pago por aprobar."""
import os

from flask import Blueprint, abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import Customer, CustomerInvoice, CustomerPayment
from ..services import finance as fin
from .common import act, perm_required

bp = Blueprint("fin", __name__, url_prefix="/finanzas")


@bp.route("/", methods=["GET", "POST"])
@perm_required("finanzas.gestionar", "facturas.cargar", "finanzas.ver")
def board():
    back = url_for("fin.board")
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        up = current_app.config["UPLOAD_DIR"]
        if acc == "excel":
            def _do():
                arch = request.files.get("archivo")
                if not arch or not arch.filename.lower().endswith((".xlsx", ".xlsm")):
                    raise fin.BusinessError("Suba el Excel de facturas (.xlsx).")
                os.makedirs(up, exist_ok=True)
                path = os.path.join(up, fin.save_document(arch, up, "facturas", (".xlsx", ".xlsm")))
                return fin.import_invoices_excel(g.user, path, arch.filename)
            return act(_do, lambda r: f"{len(r[0])} documento(s) cargados." + (f" {len(r[1])} con error: " + " | ".join(r[1][:5]) if r[1] else ""),
                       back)
        if acc == "pdf":
            return act(lambda: fin.attach_pdf(g.user, fin.save_document(request.files.get("archivo"), up, "factura_pdf", (".pdf",)),
                                              f.get("numeros", "")),
                       lambda r: f"PDF adjunto a {len(r[0])} documento(s)." + (f" No encontrados: {', '.join(r[1])}." if r[1] else ""),
                       back)
        if acc == "manual":
            return act(lambda: fin.register_invoice(g.user, f.to_dict(), fin.save_document(request.files.get("archivo"), up,
                                                                                           "factura"), "MANUAL"),
                       lambda i: f"{i.tipo.replace('_', ' ').capitalize()} {i.numero} registrada.", back)
        if acc == "estado":
            inv = db().get(CustomerInvoice, int(f.get("id") or 0)) or abort(404)
            return act(lambda: fin.set_invoice_state(inv, g.user, f.get("estado"), f.get("observacion", "")), "Estado actualizado.", back)
        if acc == "pago":
            p = db().get(CustomerPayment, int(f.get("id") or 0)) or abort(404)
            return act(lambda: fin.confirm_payment(p, g.user, f.get("ok") == "1", f.get("observacion", "")), "Pago revisado.", back)
        abort(400)
    d = fin.collection_board()
    clientes = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    return render_template("finance.html", d=d, clientes=clientes)
