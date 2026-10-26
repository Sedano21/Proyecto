"""Pantallas de Comercial de la ronda del 23-oct-2026: oportunidades y cotizaciones, configuración comercial (gastos y
rebates por canal y cliente, mercaderismo, objetivos, incentivos), margen, objetivos, incentivos, catálogo con fotos y
aprobación de precios de mercado. Comparten el blueprint de Comercial."""
from datetime import date

from flask import abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import (Customer, IncentiveRule, MarginInvestment, Opportunity, Product, ProductGTIN, Quote, SalesOrder, SalesTarget,
                      User)
from ..services import margin as msvc
from ..services import opportunities as opsvc
from ..services import parte as ptsvc
from ..services.core import BusinessError, param
from .comercial import bp
from .common import act, f_date, perm_required


def _vendedores():
    return list(db().execute(select(User).where(User.role_code.in_(("EJECUTIVO_VENTAS", "COORD_VENTAS", "JEFE_VENTAS")),
                                                User.activo.is_(True)).order_by(User.nombre)).scalars())


def _canales():
    from ..services import prices as psvc
    clientes = list(db().execute(select(Customer)).scalars())
    return sorted(set(psvc.canales()) | {psvc.channel_of(c) for c in clientes if psvc.channel_of(c)})


# ------------------------------------------------------------------ oportunidades
@bp.route("/oportunidades", methods=["GET", "POST"])
@perm_required("oportunidades.registrar", "oportunidades.ver_todas")
def opportunities():
    if request.method == "POST":
        f = request.form
        c = db().get(Customer, int(f.get("customer_id") or 0))
        if c is None:
            return act(lambda: (_ for _ in ()).throw(BusinessError("Elija el cliente o prospecto.")), "", url_for("com.opportunities"))
        if f.get("accion") == "accion":
            return act(lambda: opsvc.add_action(g.user, c, f.get("tipo"), f.get("fecha") or "", f.get("resultado", ""),
                                                f.get("gasto"), None, f.get("proxima") or None),
                       "Acción registrada.", url_for("com.opportunities"))
        return act(lambda: opsvc.save_opportunity(g.user, c, f), "Oportunidad creada.", url_for("com.opportunities"),
                   redirect_fn=lambda o: url_for("com.opportunity_detail", oid=o.id))
    a = request.args
    rows = opsvc.listing(g.user, a.get("estado", ""), a.get("vendedor_id") or None)
    clientes = list(db().execute(select(Customer).order_by(Customer.es_prospecto.desc(), Customer.nombre)).scalars())
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP"])).order_by(Product.code)).scalars())
    return render_template("opportunities.html", rows=rows, fun=opsvc.funnel(g.user, f_date("desde"), f_date("hasta")), products=products,
                           estados=opsvc.ESTADOS, clientes=clientes, sel=a.get("customer_id", ""),
                           tipos=param("tipos_accion_cliente", []) or [], vendedores=_vendedores(), f=a, today=date.today())


@bp.route("/oportunidades/<int:oid>", methods=["GET", "POST"])
@perm_required("oportunidades.registrar", "oportunidades.ver_todas")
def opportunity_detail(oid):
    o = db().get(Opportunity, oid) or abort(404)
    if "oportunidades.ver_todas" not in g.perms and o.vendedor_id != g.user.id:
        abort(403)
    back = url_for("com.opportunity_detail", oid=oid)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "accion":
            return act(lambda: opsvc.add_action(g.user, o.customer, f.get("tipo"), f.get("fecha") or "", f.get("resultado", ""),
                                                f.get("gasto"), o, f.get("proxima") or None), "Acción registrada.", back)
        if acc == "estado":
            return act(lambda: opsvc.set_state(g.user, o, f.get("estado"), f.get("motivo", "")), "Estado actualizado.", back)
        if acc == "cotizacion":
            lineas = [{"product_code": p, "cantidad": q, "precio": pr} for p, q, pr in
                      zip(f.getlist("product_code"), f.getlist("cantidad"), f.getlist("precio")) if p.strip()]
            return act(lambda: opsvc.save_quote(g.user, o.customer, lineas, f.get("vigencia") or None, o, f.get("observacion", "")),
                       lambda q: f"Cotización {q.numero} emitida.", back)
        if acc == "cotizacion_estado":
            q = db().get(Quote, int(f.get("id") or 0)) or abort(404)
            return act(lambda: opsvc.set_quote_state(g.user, q, f.get("estado")), "Cotización actualizada.", back)
        return act(lambda: opsvc.save_opportunity(g.user, o.customer, f, o), "Oportunidad guardada.", back)
    quotes = list(db().execute(select(Quote).where(Quote.opportunity_id == o.id).order_by(Quote.id.desc())).scalars())
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP"])).order_by(Product.code)).scalars())
    return render_template("opportunity_detail.html", o=o, quotes=quotes, estados=opsvc.ESTADOS, products=products,
                           tipos=param("tipos_accion_cliente", []) or [], today=date.today())


@bp.route("/cotizacion/<int:qid>")
@perm_required("oportunidades.registrar", "oportunidades.ver_todas")
def quote_print(qid):
    q = db().get(Quote, qid) or abort(404)
    html = render_template("quote_print.html", q=q)
    if request.args.get("formato") == "pdf":  # V7: descargar la cotización en PDF
        import io
        from flask import send_file
        from ..services import pdfreport
        return send_file(io.BytesIO(pdfreport.html_to_pdf(html, f"Cotización {q.numero}")), mimetype="application/pdf",
                         as_attachment=True, download_name=f"cotizacion_{q.numero}.pdf")
    return html


@bp.route("/cotizaciones", methods=["GET", "POST"])
@perm_required("oportunidades.registrar", "oportunidades.ver_todas")
def quotes():
    """V7: cotizaciones del módulo y de SAP en una sola lista; traer de SAP, imprimir/descargar y (si está autorizado)
    registrar en SAP las del módulo."""
    from ..services import sap_sl
    if request.method == "POST":
        acc = request.form.get("accion")
        if acc == "traer_sap":
            return act(lambda: sap_sl.pull_quotes(g.user), lambda r: f"SAP: {r['nuevas']} cotizaciones nuevas, "
                       f"{r['actualizadas']} actualizadas" + (f", {r['sin_cliente']} sin cliente en el módulo" if r["sin_cliente"] else "") + ".",
                       url_for("com.quotes"))
        if acc == "enviar_sap":
            q = db().get(Quote, int(request.form.get("id") or 0)) or abort(404)
            return act(lambda: sap_sl.push_quote(q, g.user), lambda n: f"Cotización registrada en SAP con el N° {n}.",
                       url_for("com.quotes"))
        abort(400)
    rows = list(db().execute(select(Quote).order_by(Quote.fecha.desc(), Quote.id.desc()).limit(300)).scalars())
    if "oportunidades.ver_todas" not in g.perms:
        rows = [q for q in rows if q.user_id == g.user.id or (q.customer.vendedor_id == g.user.id)]
    origen = request.args.get("origen", "")
    if origen:
        rows = [q for q in rows if q.origen == origen]
    return render_template("quotes.html", rows=rows, origen=origen, sap_ok=sap_sl.configured(),
                           escritura=bool(param("sap_escritura_cotizaciones", False)))


# ------------------------------------------------------------------ configuración comercial (Jefe Comercial)
@bp.route("/configuracion", methods=["GET", "POST"])
@perm_required("comercial.configurar", "margen.ver")
def commercial_config():
    back = url_for("com.commercial_config")
    if request.method == "POST":
        if "comercial.configurar" not in g.perms:
            abort(403)
        f = request.form
        acc = f.get("accion")
        if acc == "tasas":
            return act(lambda: msvc.save_rates(g.user, f.get("alcance"), f.get("clave"), {k: f.get(k) for k in msvc.CLAVES},
                                               f.get("ir_pct")), "Tasas guardadas.", back + "#tasas")
        if acc == "inversion":
            return act(lambda: msvc.save_investment(g.user, f.get("customer_id"), f.get("mes"), f.get("monto"), f.get("concepto")),
                       "Inversión registrada.", back + "#inversion")
        if acc == "objetivo":
            return act(lambda: msvc.save_target(g.user, f.get("mes"), f.get("alcance"), f.get("clave"), f.get("soles"),
                                                f.get("kg")), "Objetivo guardado.", back + "#objetivos")
        if acc == "incentivo":
            r = db().get(IncentiveRule, int(f["id"])) if f.get("id") else None
            return act(lambda: msvc.save_rule(g.user, f, r), "Regla de incentivo guardada.", back + "#incentivos")
        if acc == "gs1":
            def _gs1():
                import os
                arch = request.files.get("archivo")
                if not arch or not arch.filename.lower().endswith((".xlsx", ".xlsm")):
                    raise BusinessError("Suba la tabla GS1 en Excel (.xlsx).")
                up = current_app.config["UPLOAD_DIR"]
                os.makedirs(up, exist_ok=True)
                path = os.path.join(up, f"gs1_{os.urandom(4).hex()}.xlsx")
                arch.save(path)
                return ptsvc.import_gtins(g.user, path)
            return act(_gs1, lambda r: f"{r[0]} código(s) GS1 cargados." + (f" Errores: {' | '.join(r[1][:5])}" if r[1] else ""),
                       back + "#gs1")
        if acc == "gtin":
            return act(lambda: ptsvc.save_gtin(g.user, f), "GTIN guardado.", back + "#gs1")
        if acc == "gtin_baja":
            return act(lambda: ptsvc.delete_gtin(g.user, f.get("gtin")), "GTIN retirado.", back + "#gs1")
        abort(400)
    cfg = msvc.config()
    clientes = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    por_ruc = {c.ruc: c for c in clientes}
    mes = request.args.get("mes") or f"{date.today():%Y-%m}"
    return render_template("commercial_config.html", cfg=cfg, tasas=msvc.TASAS, gastos=msvc.GASTOS, canales=_canales(),
                           clientes=clientes, por_ruc=por_ruc, vendedores=_vendedores(), mes=mes,
                           inversiones=list(db().execute(select(MarginInvestment).order_by(MarginInvestment.mes.desc(),
                                                                                           MarginInvestment.id.desc()).limit(60)).scalars()),
                           objetivos=list(db().execute(select(SalesTarget).order_by(SalesTarget.mes.desc(),
                                                                                    SalesTarget.alcance)).scalars()),
                           reglas=list(db().execute(select(IncentiveRule).order_by(IncentiveRule.id)).scalars()),
                           usuarios={str(u.id): u.nombre for u in _vendedores()},
                           gtins=list(db().execute(select(ProductGTIN).order_by(ProductGTIN.product_code).limit(1000)).scalars()),
                           editable="comercial.configurar" in g.perms)


@bp.route("/margen")
@perm_required("margen.ver")
def margin_report():
    a = request.args
    d = msvc.margin(f_date("desde"), f_date("hasta"), a.get("agrupar", "CANAL"), a.get("base", "FACTURADO"), a.get("canal", ""),
                    a.get("customer_id") or None, a.get("vendedor", ""))
    if a.get("formato") == "xlsx":
        return _margin_xlsx(d)
    from ..services import charts
    graf = charts.bars([(f["clave"][:22], f["pct_mcv"] or 0) for f in d["filas"][:15]], "%",
                       title="Margen de contribución variable (%)", color=2)
    return render_template("margin.html", d=d, graf=graf, bases=msvc.BASES, canales=_canales(), vendedores=_vendedores(),
                           clientes=list(db().execute(select(Customer).order_by(Customer.nombre)).scalars()), f=a)


def _margin_xlsx(d):
    import io
    from flask import send_file
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Margen"
    cab = ["Grupo", "Venta", "Costo de venta", "Margen bruto", "% MB"] + [n for _, n in msvc.TASAS] + [
        "Inversión adicional", "Margen contrib. variable", "% MCV"] + [n for _, n in msvc.GASTOS] + [
        "Utilidad antes de impuestos", "IR", "Utilidad neta", "% UN"]
    ws.append(cab)
    for f in d["filas"] + ([dict(d["total"], clave="TOTAL")] if d["total"] else []):
        ws.append([f["clave"], f["venta"], f["costo"], f["margen_bruto"], f["pct_mb"]] + [round(f[k], 2) for k, _ in msvc.TASAS]
                  + [f["inversion"], f["mcv"], f["pct_mcv"]] + [round(f[k], 2) for k, _ in msvc.GASTOS]
                  + [f["uai"], f["ir"], f["utilidad_neta"], f["pct_un"]])
    out = io.BytesIO()
    wb.save(out)
    return send_file(io.BytesIO(out.getvalue()), as_attachment=True, download_name=f"margen_{d['desde']:%Y%m%d}_{d['hasta']:%Y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/objetivos", methods=["GET", "POST"])
@perm_required("objetivos.ver", "objetivos.registrar")
def targets():
    if request.method == "POST":
        f = request.form

        def _guardar():
            n = 0
            for alc, cl, so, kg, nc, ns in zip(f.getlist("alcance"), f.getlist("clave"), f.getlist("soles"), f.getlist("kg"),
                                               f.getlist("nuevos_clientes"), f.getlist("nuevos_sku")):
                if not (so or kg or nc or ns):
                    continue
                msvc.save_target(g.user, f.get("mes"), alc, cl, so, kg, nc, ns)
                n += 1
            if not n:
                raise BusinessError("Complete al menos un objetivo.")
            return n
        return act(_guardar, lambda n: f"{n} objetivo(s) guardados.", url_for("com.targets", mes=f.get("mes")))
    d = msvc.targets_progress(request.args.get("mes"))
    from ..services.commercial_mgmt import _metas
    from datetime import timedelta as _td
    mes = d["mes"]
    ini = date(int(mes[:4]), int(mes[5:7]), 1)
    fin = (ini.replace(day=28) + _td(days=4)).replace(day=1) - _td(days=1)
    ovs = [o for o in db().execute(select(SalesOrder).where(SalesOrder.fecha_emision >= ini, SalesOrder.fecha_emision <= fin)).scalars()
           if o.estado not in ("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")]
    usuarios = {str(u.id): u.nombre for u in db().execute(select(User)).scalars()}
    d["v7"] = _metas(mes, ovs, "", usuarios)
    vendedores = list(db().execute(select(User).where(User.role_code.in_(("EJECUTIVO_VENTAS", "COORD_VENTAS", "JEFE_VENTAS")),
                                                      User.activo.is_(True)).order_by(User.nombre)).scalars())
    d["vendedores"], d["canales"] = vendedores, _canales()
    if "comercial.configurar" not in g.perms and "margen.ver" not in g.perms and g.user.role_code == "EJECUTIVO_VENTAS":
        d["filas"] = [x for x in d["filas"] if x["t"].alcance != "VENDEDOR" or x["t"].clave == str(g.user.id)]
        d["v7"]["filas"] = [x for x in d["v7"]["filas"] if x["alcance"] != "VENDEDOR" or x["nombre"] == g.user.nombre]
    return render_template("targets.html", d=d)


@bp.route("/incentivos")
@perm_required("incentivos.ver")
def incentives():
    return render_template("incentives.html", d=msvc.incentives(request.args.get("mes")))


# ------------------------------------------------------------------ catálogo con fotos
@bp.route("/catalogo", methods=["GET", "POST"])
@perm_required("catalogo.ver", "catalogo.fotos")
def catalog():
    from ..services import catalog as ctsvc
    if request.method == "POST":
        if "catalogo.fotos" not in g.perms:
            abort(403)
        if request.form.get("accion") == "nuevo":
            return act(lambda: ctsvc.add_product(g.user, request.form), lambda p: f"Producto {p.code} agregado al catálogo.",
                       url_for("com.catalog"), redirect_fn=lambda p: url_for("com.catalog_item", code=p.code))

        def _do():
            import os
            from ..services.core import audit
            from ..services.distribution import save_upload
            n, sin = 0, []
            for fs in request.files.getlist("fotos"):
                if not fs or not fs.filename:
                    continue
                code = request.form.get("product_code", "").strip().upper() or os.path.splitext(os.path.basename(fs.filename))[0].upper()
                p = db().get(Product, code)
                if p is None:
                    sin.append(code)
                    continue
                p.foto = save_upload(fs, current_app.config["UPLOAD_DIR"], f"foto_{code}")
                n += 1
            audit(g.user, "CATALOGO_FOTOS", "Product", "", {"fotos": n, "sin_producto": sin})
            if sin and not n:
                raise BusinessError(f"Sin producto con ese código: {', '.join(sin[:10])}. Nombre cada foto con el código del "
                                    "producto (p. ej. PT-901.jpg) o elija el producto.")
            return n, sin
        return act(_do, lambda r: f"{r[0]} foto(s) cargadas." + (f" Sin producto: {', '.join(r[1][:10])}." if r[1] else ""),
                   url_for("com.catalog"))
    q = (request.args.get("q") or "").strip().upper()
    rows = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP"])).order_by(Product.code)).scalars())
    if request.args.get("destacado"):
        rows = [p for p in rows if p.destacado == request.args["destacado"]]
    if q:
        rows = [p for p in rows if q in p.code.upper() or q in (p.descripcion or "").upper() or q in (p.marca or "").upper()]
    if request.args.get("con_foto") == "1":
        rows = [p for p in rows if p.foto]
    from ..services.orders import unit_for
    return render_template("catalog.html", rows=rows, q=q, unit_for=unit_for, con_foto=request.args.get("con_foto", ""),
                           destacados=ctsvc.featured(), dest_txt=ctsvc.DESTACADOS, dest=request.args.get("destacado", ""))


@bp.route("/catalogo/<code>", methods=["GET", "POST"])
@perm_required("catalogo.ver", "catalogo.fotos")
def catalog_item(code):
    """V7: carpeta del producto (ficha técnica, fotos, certificados, recetas, estrategias) y producto del mes."""
    from ..models import ProductDocument
    from ..services import catalog as ctsvc
    from ..services.distribution import save_upload
    p = db().get(Product, code) or abort(404)
    back = url_for("com.catalog_item", code=code)
    if request.method == "POST":
        fm = request.form
        acc = fm.get("accion")
        if acc == "documento":
            def _doc():
                n = 0
                for fs in request.files.getlist("archivos"):
                    if fs and fs.filename:
                        arch = save_upload(fs, current_app.config["UPLOAD_DIR"], f"prod_{code}_{fm.get('carpeta', '').lower()}")
                        ctsvc.add_document(g.user, p, fm.get("carpeta", ""), arch, fm.get("nombre") or fs.filename)
                        n += 1
                if not n:
                    raise BusinessError("Adjunte al menos un archivo.")
                return n
            return act(_doc, lambda n: f"{n} archivo(s) agregados a la carpeta.", back)
        if acc == "foto":
            return act(lambda: ctsvc.set_photo(g.user, p, save_upload(request.files.get("foto"), current_app.config["UPLOAD_DIR"],
                                                                      f"foto_{code}")), "Foto actualizada.", back)
        if acc == "retirar":
            d = db().get(ProductDocument, int(fm.get("doc_id") or 0))
            if d is None or d.product_code != code:
                abort(404)
            return act(lambda: ctsvc.retire_document(g.user, d), "Archivo retirado de la carpeta.", back)
        if acc == "destacado":
            return act(lambda: ctsvc.set_featured(g.user, p, fm.get("destacado", ""), fm.get("nota", ""), f_date("hasta")),
                       "Catálogo actualizado.", back)
        abort(400)
    from ..services.orders import unit_for
    return render_template("catalog_item.html", p=p, docs=ctsvc.documents(p), carpetas=ctsvc.CARPETAS,
                           dest_txt=ctsvc.DESTACADOS, unit_for=unit_for)


# ------------------------------------------------------------------ precios de mercado por aprobar
@bp.route("/mercado/aprobar", methods=["GET", "POST"])
@perm_required("mercado.aprobar")
def market_approve():
    from ..services import market
    if request.method == "POST":
        ids = request.form.getlist("ids")
        aprobar = request.form.get("decision") == "aprobar"
        return act(lambda: market.approve(g.user, ids, aprobar), lambda n: f"{n} precio(s) {'aprobados' if aprobar else 'rechazados'}.",
                   url_for("com.market_approve"))
    return render_template("market_approve.html", rows=market.pending(), categorias=market.CATEGORIAS)
