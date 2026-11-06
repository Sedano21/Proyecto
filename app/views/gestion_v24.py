"""V24 (06-nov-2026): compras nacionales (consolidado y cotizaciones), seguimiento de importaciones, costos y
presupuestos, tablero «Cómo va la empresa» e informe consolidado de reposición."""
import io
import os
from datetime import date

from flask import Blueprint, Response, abort, current_app, g, render_template, request, send_file, url_for
from sqlalchemy import select

from ..db import db
from ..models import Customer, ImportFollowup, Product, SupplierQuote
from ..services import compras_v24 as cv
from ..services import costos_v24 as cos
from ..services import empresa_v24 as emp
from ..services import importaciones_v24 as imp
from ..services import tipo_cambio as tcs
from ..services.core import BusinessError
from .common import act, f_date, f_float, perm_required

bp = Blueprint("v24", __name__, url_prefix="/gestion")


def _up():
    return current_app.config["UPLOAD_DIR"]


def _archivo(campo, prefijo):
    from ..services.finance import save_document
    fa = request.files.get(campo)
    if not fa or not fa.filename:
        return ""
    return save_document(fa, _up(), prefijo)


def _descarga(html, titulo, nombre):
    from ..services import pdfreport
    f = request.args.get("formato")
    if f == "pdf":
        return send_file(io.BytesIO(pdfreport.html_to_pdf(html, titulo)), mimetype="application/pdf", as_attachment=True,
                         download_name=f"{nombre}_{date.today():%Y%m%d}.pdf")
    if f == "xlsx":
        return send_file(io.BytesIO(pdfreport.html_to_xlsx(html, titulo)), as_attachment=True,
                         download_name=f"{nombre}_{date.today():%Y%m%d}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return html


# ------------------------------------------------------------------ compras nacionales
@bp.route("/compras-nacionales", methods=["GET", "POST"])
@perm_required("compras.consolidado", "compras.cotizar", "compras.solicitar")
def purchases():
    back = url_for("v24.purchases", producto=request.args.get("producto", ""))
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "solicitud":
            return act(lambda: cv.create(g.user, (f.get("product_code") or "").strip().upper(), f_float("cantidad", True),
                                         f_date("fecha_necesidad"), f.get("ov", "").strip(), f.get("customer_id") or None,
                                         f.get("motivo_tipo", ""), f.get("motivo", "")),
                       lambda r: f"Solicitud #{r.id} registrada.", back)
        if acc == "cotizaciones":
            code = (f.get("product_code") or "").strip().upper()
            reqs = f.getlist("request_ids")

            def _guardar():
                filas = []
                provs = f.getlist("proveedor")
                for i, prov in enumerate(provs):
                    if not (prov or "").strip():
                        continue
                    datos = {k: (f.getlist(k)[i] if i < len(f.getlist(k)) else "") for k in
                             ("origen", "proveedor", "fecha_entrega", "calidad", "precio", "moneda", "um", "cantidad", "observacion")}
                    datos["request_ids"] = reqs
                    arch = ""
                    fa = request.files.getlist("archivo")
                    if i < len(fa) and fa[i] and fa[i].filename:
                        from ..services.finance import save_document
                        arch = save_document(fa[i], _up(), f"cotizacion_{code}")
                    filas.append(cv.add_quote(g.user, code, datos, arch))
                if not filas:
                    raise BusinessError("Registre al menos un proveedor.")
                return filas
            return act(_guardar, lambda fs: f"{len(fs)} cotización(es) registrada(s)." +
                       ("".join(f" ⚠ {q.proveedor}: {c['alerta']}" for q, c in fs if c["alerta"])), back)
        if acc == "elegir":
            q = db().get(SupplierQuote, int(f.get("quote_id") or 0)) or abort(404)
            return act(lambda: cv.choose(g.user, q), "Cotización elegida: se pasó a la(s) solicitud(es).", back)
        abort(400)
    prod = request.args.get("producto") or None
    d = cv.consolidado(prod)
    comps = {q.id: cv.comparar(q) for p in d for q in p["cotizaciones"]}
    prods = list(db().execute(select(Product).order_by(Product.code)).scalars())
    clientes = list(db().execute(select(Customer).where(Customer.es_prospecto.is_(False)).order_by(Customer.nombre)).scalars())
    return render_template("v24_compras.html", d=d, comps=comps, prods=prods, clientes=clientes, motivos=cv.MOTIVOS,
                           puede_cotizar=cv.puede_cotizar(g.user), prod=prod or "", hoy=date.today(),
                           historial={p["code"]: cv.historial(p["code"]) for p in d})


# ------------------------------------------------------------------ importaciones
@bp.route("/importaciones", methods=["GET", "POST"])
@perm_required("importaciones.ver", "importaciones.seguimiento")
def imports():
    back = url_for("v24.imports")
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        fila = db().get(ImportFollowup, int(f.get("id") or 0)) if f.get("id") else None
        if acc == "guardar":
            datos = dict(f)
            datos["retiro_real"] = f.get("retiro_real", "")
            arch = _archivo("contrato_archivo", "contrato_importacion")
            if arch:
                datos["contrato_archivo"] = arch
            return act(lambda: imp.save(g.user, datos, fila), lambda x: f"Importación {x.contrato} guardada.", back)
        if fila is None and acc in ("gasto", "incidencia"):
            abort(404)
        if acc == "gasto":
            return act(lambda: imp.add_expense(g.user, fila, f.get("tipo"), f.get("monto"), f.get("moneda", "USD"),
                                               f.get("detalle", ""), _archivo("archivo", f"gasto_imp_{fila.id}")),
                       "Gasto registrado.", back)
        if acc == "incidencia":
            return act(lambda: imp.add_incident(g.user, fila, f.get("tipo", ""), f.get("detalle", "")),
                       "Inconveniente reportado: se avisó a Gerencia Adjunta e Importaciones.", back)
        if acc == "excel":
            def _cargar():
                ruta = _archivo("archivo", "seguimiento_importaciones")
                if not ruta:
                    raise BusinessError("Adjunte el Excel.")
                return imp.import_excel(g.user, os.path.join(_up(), ruta))
            return act(_cargar, lambda r: f"Cuadro cargado: {r[0]} nuevas, {r[1]} actualizadas.", back)
        abort(400)
    if request.args.get("salida") == "xlsx":
        return Response(imp.excel(), headers={"Content-Disposition": f"attachment; filename=importaciones_{date.today():%Y%m%d}.xlsx"},
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return render_template("v24_importaciones.html", d=imp.board(incluir_cerradas=request.args.get("todas") == "1"),
                           precios=imp.precios_importado_vs_nacional(), tipos_gasto=imp.TIPOS_GASTO, estados=imp.ESTADOS,
                           puede=("importaciones.seguimiento" in g.perms), hoy=date.today())


# ------------------------------------------------------------------ costos y presupuestos
@bp.route("/costos", methods=["GET", "POST"])
@perm_required("costos.gestionar", "costos.analisis")
def costs():
    back = url_for("v24.costs")
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "costo":
            if "costos.gestionar" not in g.perms:
                abort(403)
            return act(lambda: cos.guardar_costo(g.user, f.get("product_code"), f_float("costo", True), f.get("unidad", "KG")),
                       "Costo actualizado.", back)
        if acc == "tc":
            return act(lambda: tcs.manual(g.user, f_date("fecha") or date.today(), f_float("compra", True), f_float("venta", True)),
                       "Tipo de cambio registrado.", back)
        if acc == "tc_sunat":
            def _sunat():
                r = tcs.actualizar()
                if r is None:
                    raise BusinessError("No se pudo leer el tipo de cambio de SUNAT (sin conexión). Regístrelo a mano.")
                return r
            return act(_sunat, lambda r: f"Tipo de cambio SUNAT {r.fecha:%d/%m/%Y}: compra {r.compra} · venta {r.venta}.", back)
        abort(400)
    d = cos.analisis(dias=int(request.args.get("dias") or 30))
    prods = list(db().execute(select(Product).order_by(Product.code)).scalars())
    html = render_template("v24_costos.html", d=d, prods=prods, puede="costos.gestionar" in g.perms, hoy=date.today(),
                           tc=tcs.ultimo())
    return _descarga(html, "Costos, reposición y precios", "costos_reposicion")


# ------------------------------------------------------------------ tablero de la empresa
@bp.route("/empresa")
@perm_required("tablero.empresa")
def company():
    from ..services import charts
    d = emp.tablero(ver_costos="costos.analisis" in g.perms or "costos.ver" in g.perms)
    sem = d["graficos"]["semanas"]
    graf = {"venta": charts.columns([x[0] for x in sem], [("Venta S/", [x[1] for x in sem])], "S/", title="Venta por semana"),
            "otif": charts.line([("OTIF %", [(x[0], x[2]) for x in sem])], "%", title="OTIF por semana"),
            "cobranza": charts.bars(d["graficos"]["cobranza"], "S/", title="Deuda vencida por antigüedad (días)", color=7)}
    html = render_template("v24_empresa.html", d=d, graf=graf)
    return _descarga(html, "Cómo va la empresa", "como_va_la_empresa")


@bp.route("/reposicion")
@perm_required("tablero.empresa", "compras.ver", "compras.consolidado")
def replenishment():
    html = render_template("v24_reposicion.html", d=emp.reposicion())
    return _descarga(html, "Informe de reposición", "informe_reposicion")
