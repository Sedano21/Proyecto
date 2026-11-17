"""V56 (17-nov-2026): Facturación: pre-facturas preparadas desde las guías de SAP (el facturador las revisa, corrige y
valida antes de crearlas en SAP) y regularización de facturas emitidas en SUNAT."""
import os
import uuid

from flask import Blueprint, abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import Prefactura
from ..services import prefacturas as pf
from ..services.core import BusinessError
from .common import act, paginate, perm_required

bp = Blueprint("fac", __name__, url_prefix="/facturacion")

VISTAS = {"pendientes": ("POR_VALIDAR", "OBSERVADA"), "validadas": ("VALIDADA",), "sap": ("ENVIADA_SAP", "FACTURADA_EN_SAP"),
          "descartadas": ("DESCARTADA",)}


@bp.route("/", methods=["GET", "POST"])
@perm_required("facturacion.cargar", "finanzas.ver")
def prefacturas():
    back = url_for("fac.prefacturas", ver=request.args.get("ver", "pendientes"))
    if request.method == "POST":
        if "facturacion.cargar" not in g.perms:
            abort(403)

        def _subir():
            archivos = [x for x in request.files.getlist("archivos") if x and x.filename]
            if not archivos:
                raise BusinessError("Elija el XML o el PDF de la factura de SUNAT (puede subir varias).")
            ok, errores = [], []
            for a in archivos:
                ext = os.path.splitext(a.filename)[1].lower()
                if ext not in (".pdf", ".xml"):
                    errores.append(f"{a.filename}: suba el XML o el PDF de SUNAT.")
                    continue
                nombre = f"factura_sunat_{uuid.uuid4().hex[:10]}{ext}"
                ruta = os.path.join(current_app.config["UPLOAD_DIR"], nombre)
                a.save(ruta)
                try:
                    with db().begin_nested():
                        ok.append(pf.registrar_sunat(g.user, ruta, a.filename, nombre))
                except BusinessError as e:
                    errores.append(f"{a.filename}: {e}")
            if not ok:
                raise BusinessError(" ".join(errores))
            return ok, errores
        return act(_subir, lambda r: f"{len(r[0])} factura(s) de SUNAT subida(s)." + (f" No se cargaron: {' '.join(r[1])}"
                                                                                      if r[1] else ""), back)
    ver = request.args.get("ver", "pendientes")
    q = select(Prefactura).order_by(Prefactura.id.desc())
    if ver in VISTAS:
        q = q.where(Prefactura.estado.in_(VISTAS[ver]))
    lista = list(db().execute(q.limit(500)).scalars())
    cuenta = {k: len(list(db().execute(select(Prefactura.id).where(Prefactura.estado.in_(v))).scalars())) for k, v in VISTAS.items()}
    from ..services.core import param
    return render_template("v56_prefacturas.html", lista=paginate(lista, 30), ver=ver, cuenta=cuenta, total=pf.total,
                           estados=pf.ESTADOS, ultima=param("prefacturas_ultima", {}) or {})


@bp.route("/<int:pid>", methods=["GET", "POST"])
@perm_required("facturacion.cargar", "finanzas.ver")
def prefactura(pid):
    p = db().get(Prefactura, pid) or abort(404)
    back = url_for("fac.prefactura", pid=pid)
    if request.method == "POST":
        if "facturacion.cargar" not in g.perms:
            abort(403)
        f = request.form
        acc = f.get("accion")
        if acc == "editar":
            return act(lambda: pf.editar(g.user, p, f), "Cambios guardados (quedan en el historial).", back)
        if acc == "validar":
            return act(lambda: pf.validar(g.user, p, True, f.get("observacion_val", "")),
                       lambda x: ("Factura creada en SAP (" + (x.sap.get("folio") or x.sap.get("docnum") or "") + ")."
                                  if (x.sap or {}).get("estado") == "OK" else
                                  "Validada. " + ("SAP no la aceptó: " + x.sap.get("error", "") if (x.sap or {}).get("estado") == "ERROR"
                                                  else "Se creará en SAP cuando la escritura esté habilitada.")), back)
        if acc == "observar":
            return act(lambda: pf.validar(g.user, p, False, f.get("observacion_val", "")), "Pre-factura observada.", back)
        if acc == "descartar":
            return act(lambda: pf.descartar(g.user, p, f.get("motivo_desc", "")), "Pre-factura descartada.", back)
        if acc == "reabrir":
            return act(lambda: pf.reabrir(g.user, p, f.get("motivo_reab", "")), "Pre-factura reabierta para corregirla.", back)
        if acc == "reintentar":
            return act(lambda: pf.enviar(p, g.user), lambda s: "Factura creada en SAP." if s.get("estado") == "OK" else
                       f"Aún no se pudo: {s.get('error', '')}", back)
        if acc == "unir":
            guia = db().get(Prefactura, int(f.get("guia_id") or 0)) or abort(404)
            return act(lambda: pf.unir(g.user, p, guia, f.get("motivo", "")), "Factura de SUNAT unida a su guía.", back)
        abort(400)
    return render_template("v56_prefactura.html", p=p, total=pf.total(p), estados=pf.ESTADOS,
                           cand=pf.candidatas(p) if p.origen == "SUNAT" and not p.entrega_docentry else [])
