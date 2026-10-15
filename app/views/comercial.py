"""Vistas de Comercial (OV, decisiones ante faltantes) y preparación."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import AuditLog, Certificate, Customer, OVChangeRequest, OVDecision, Product, SalesOrder, User, Warehouse
from ..services import orders as osvc
from ..services import production as psvc
from ..services import purchasing as buysvc
from ..services import repack as rsvc
from ..services import transfers as tsvc
from ..services.core import BusinessError
from ..services.stock import alternatives_for_order, line_reserved, priority_key
from ..services import options as options_svc
from ..services.customer_conditions import by_product as cond_por_producto, for_customer as cond_for, penalty_estimate
from .common import act, f_bool, f_date, f_float, perm_required

bp = Blueprint("com", __name__, url_prefix="/ov")


def _lines_from_form():
    lines = []
    codes = request.form.getlist("product_code")
    qtys = request.form.getlist("cantidad")
    prices = request.form.getlist("precio_unitario")
    ums = request.form.getlist("um_venta")
    for i, code in enumerate(codes):
        code = (code or "").strip().upper().split(" ")[0]  # el combo muestra "CÓDIGO · descripción"
        if not code:
            if (qtys[i] if i < len(qtys) else "").strip() or (prices[i] if i < len(prices) else "").strip():
                raise BusinessError(f"Línea {i + 1}: indicó cantidad o precio pero falta el producto.")
            continue
        lines.append({"product_code": code, "cantidad": qtys[i] if i < len(qtys) else "",
                      "precio_unitario": prices[i] if i < len(prices) and prices[i] else 0,
                      "um_venta": ums[i] if i < len(ums) else ""})
    return lines


@bp.route("/")
@perm_required("ov.ver")
def orders():
    q = select(SalesOrder)
    estado = request.args.get("estado")
    stock = request.args.get("estado_stock")
    if estado:
        q = q.where(SalesOrder.estado == estado)
    if stock:
        q = q.where(SalesOrder.estado_stock == stock)
    rows = list(db().execute(q).scalars())
    if g.user.role_code == "EJECUTIVO_VENTAS" and request.args.get("mias") != "0":
        rows = [o for o in rows if o.vendedor_id == g.user.id]
    rows.sort(key=priority_key)
    pend = list(db().execute(select(OVChangeRequest).where(OVChangeRequest.estado == "PENDIENTE")).scalars())
    pend = [r for r in pend if osvc.can_authorize_change(g.user, r.order) or r.solicitado_por == g.user.id]
    return render_template("ov_list.html", rows=rows, estado=estado or "", estado_stock=stock or "", pend=pend)


@bp.route("/nueva", methods=["GET", "POST"])
@perm_required("ov.crear")
def order_new():
    customers = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    vendedores = list(db().execute(select(User).where(User.role_code == "EJECUTIVO_VENTAS")).scalars())
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP"])).order_by(Product.code)).scalars())
    if request.method == "POST":
        holder = {}

        def _do():
            fm = request.form
            c = db().get(Customer, int(fm.get("customer_id") or 0))
            if c is None:
                raise BusinessError("Cliente no válido.")
            sid = fm.get("site_id", "")
            entrega = osvc.resolve_delivery(c, sid if sid not in ("", "OTRO", "FISCAL") else None, fm.get("lugar_otro", ""),
                                            fm.get("direccion", ""), fm.get("distrito", ""), fm.get("provincia", ""),
                                            guardar=f_bool("guardar_lugar"), user=g.user)
            if sid == "FISCAL":
                entrega["lugar_entrega"] = "Dirección fiscal"
            o = osvc.create_order(g.user, fm.get("numero"), fm.get("customer_id"),
                                  f_date("fecha_compromiso", True), _lines_from_form(), urgente=f_bool("urgente"),
                                  comentarios=fm.get("comentarios", ""), hora_cita=fm.get("hora_cita", ""),
                                  cita_confirmada=f_bool("cita_confirmada"), vendedor_id=fm.get("vendedor_id") or None,
                                  entrega=entrega, canal_precio=fm.get("canal_precio", ""),
                                  tipo_venta="Muestra comercial" if f_bool("muestra") else "")
            holder["o"] = o
            return o
        resp = act(_do, lambda o: f"OV {o.numero} registrada y evaluada: cobertura {o.cobertura_unidades}% unidades / "
                                  f"{o.cobertura_lineas}% líneas.", url_for("com.orders"))
        if "o" in holder and holder["o"].id:
            return redirect(url_for("com.order_detail", oid=holder["o"].id))
        return resp
    sitios = {c.id: {"fiscal": {"direccion": c.direccion, "distrito": c.distrito, "provincia": c.provincia},
                     "horario": c.horario_recepcion, "cita": c.requiere_cita,
                     "sitios": [{"id": x.id, "nombre": x.nombre, "direccion": x.direccion, "distrito": x.distrito,
                                 "provincia": x.provincia, "horario": x.horario_recepcion} for x in c.sites if x.activo]}
              for c in customers}
    granel = {p.code for p in products if osvc.kg_por_saco(p.code)}
    from ..services import prices as psvc
    from ..services.core import param
    canales = sorted(set(psvc.canales()) | set(param("lista_granel_canales", []) or []))
    canal_cliente = {c.id: psvc.channel_of(c) for c in customers}
    return render_template("ov_new.html", customers=customers, vendedores=vendedores, products=products, sitios=sitios,
                           horas=osvc.horas_cita(), granel=granel, canales=canales, canal_cliente=canal_cliente)


@bp.route("/<int:oid>")
@perm_required("ov.ver")
def order_detail(oid):
    o = db().get(SalesOrder, oid) or abort(404)
    ve_opciones = "ov.opciones" in g.perms  # Comercial ve solo el avance de su pedido (observaciones al demo v0.6)
    alts = alternatives_for_order(o) if ve_opciones and o.estado_stock in ("INCOMPLETA", "SIN_STOCK") and o.estado not in (
        "CANCELADA", "DESPACHADA", "ENTREGADA") else []
    whs = list(db().execute(select(Warehouse).order_by(Warehouse.prioridad)).scalars())
    reqs = list(db().execute(select(OVChangeRequest).where(OVChangeRequest.order_id == o.id).order_by(OVChangeRequest.id.desc())).scalars())
    decs = [d for d in db().execute(select(OVDecision).where(OVDecision.order_id == o.id).order_by(OVDecision.id.desc())).scalars()
            if ve_opciones or d.tipo not in ("ELECCION_OPCION", "USO_ALMACEN_ALTERNATIVO")]
    hist = list(db().execute(select(AuditLog).where(AuditLog.entidad == "SalesOrder", AuditLog.entidad_id == o.numero)
                             .order_by(AuditLog.id.desc()).limit(60)).scalars()) if "auditoria.ver" in g.perms else []
    certs = list(db().execute(select(Certificate).where(Certificate.order_id == o.id)).scalars())
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP"])).order_by(Product.code)).scalars())
    peso, sin_peso = osvc.order_weight_kg(o, "solicitado")
    saldos = list(db().execute(select(SalesOrder).where(SalesOrder.parent_id == o.id)).scalars())
    from ..models import ProductionRequest, PurchaseRequest, RepackRequest, Transfer
    from ..services.core import param
    presol = ([("Producción", x.id, x.product_code, x.cantidad, x.estado, url_for("prod.request_detail", rid=x.id))
               for x in db().execute(select(ProductionRequest).where(ProductionRequest.order_id == o.id)).scalars()] +
              [("Reempaque", x.id, x.producto_destino, x.cantidad_destino or x.cantidad, x.estado, url_for("alm.repack_detail", rid=x.id))
               for x in db().execute(select(RepackRequest).where(RepackRequest.order_id == o.id)).scalars()] +
              [("Traslado", x.id, x.lot.product_code, x.cantidad, x.estado, url_for("alm.transfers"))
               for x in db().execute(select(Transfer).where(Transfer.order_id == o.id)).scalars()] +
              [("Compra", x.id, x.product_code, x.cantidad, x.estado, url_for("buy.purchase_detail", pid=x.id))
               for x in db().execute(select(PurchaseRequest).where(PurchaseRequest.order_id == o.id)).scalars()])
    from ..models import RouteStop
    paradas = list(db().execute(select(RouteStop).where(RouteStop.order_id == o.id).order_by(RouteStop.id)).scalars())
    return render_template("ov_detail.html", o=o, alts=alts, paradas=paradas, whs=whs, reqs=reqs, decs=decs, hist=hist, certs=certs,
                           products=products, line_reserved=line_reserved, monto=osvc.order_amount(o), peso=peso,
                           sin_peso=sin_peso, can_auth=osvc.can_authorize_change(g.user, o), prep=osvc.prep_progress(o),
                           saldos=saldos, aprobadores=osvc.partial_approvers(), pendientes_parcial=osvc.partial_pending_roles(o),
                           parcial_modo=str(param("parcial_modo", "CUALQUIERA")).upper(), presol=presol,
                           horas=osvc.horas_cita(), penal=penalty_estimate(o),
                           vida=lambda lot: options_svc._vida(lot, o), seguimiento=options_svc.progress(o),
                           ve_opciones=ve_opciones, cond_prod=cond_por_producto(o),
                           hay_pendiente=o.estado not in ("CANCELADA", "DESPACHADA", "ENTREGADA") and any(
                               l.activa and l.cantidad - l.despachado - line_reserved(l) > 1e-9 for l in o.lines))


@bp.route("/<int:oid>/opciones", methods=["GET", "POST"])
@perm_required("ov.opciones")
def order_options(oid):
    """Opciones para atender la OV: información completa de la OV, todas las rutas evaluadas, la recomendación del
    sistema y la aprobación de cada pre-solicitud con el motivo de la elección (decisión del 14-oct)."""
    o = db().get(SalesOrder, oid) or abort(404)
    ev = options_svc.evaluate(o)
    if request.method == "POST" and request.form.get("accion") == "designar":
        return act(lambda: options_svc.delegate(o, g.user, request.form.get("user_id"), request.form.get("comentario", "")),
                   "Revisión designada.", url_for("com.order_options", oid=oid))
    if request.method == "POST":
        f = request.form
        resumen = {}
        for it in ev:
            if it["line"].product_code == f.get("producto"):
                resumen = {"recomendada": (it["recomendada"] or {}).get("nombre"), "porque": it["porque"],
                           "opciones": [{"ruta": x["nombre"], "cantidad": x["cantidad"], "plazo": x["plazo"],
                                         "cumple": x["cumple"], "viable": x["viable"]} for x in it["opciones"]]}
        return act(lambda: options_svc.decide(o, g.user, f.get("tipo"), f.get("id"), f.get("accion") == "aprobar",
                                              f.get("motivo", ""), resumen),
                   "Decisión registrada con su motivo.", url_for("com.order_options", oid=oid))
    from ..models import OVDecision
    decs = list(db().execute(select(OVDecision).where(OVDecision.order_id == o.id, OVDecision.tipo == "ELECCION_OPCION")
                             .order_by(OVDecision.id.desc())).scalars())
    from ..services import alerts as alert_svc
    return render_template("ov_options.html", o=o, ev=ev, penal=penalty_estimate(o), monto=osvc.order_amount(o),
                           decs=decs, cond=cond_for(o.customer), rutas=options_svc.RUTAS,
                           designables=alert_svc.assignable(g.user)[0], tarea=options_svc.review_task(o))


@bp.route("/<int:oid>/expediente")
@perm_required("ov.ver")
def order_file(oid):
    """Expediente de la OV (obs. demo v0.7, Coordinador de Distribución): OV, certificados, guía y factura juntos."""
    from ..models import RouteStop
    o = db().get(SalesOrder, oid) or abort(404)
    paradas = list(db().execute(select(RouteStop).where(RouteStop.order_id == o.id).order_by(RouteStop.id)).scalars())
    certs = list(db().execute(select(Certificate).where(Certificate.order_id == o.id, Certificate.estado != "ANULADO")).scalars())
    return render_template("ov_file.html", o=o, paradas=paradas, certs=certs)


@bp.route("/regularizacion", methods=["GET", "POST"])
@perm_required("ov.regularizar")
def regularization():
    """Regularización de OV (obs. demo v0.7): OV con fecha pasada u hora transcurrida. No reserva stock; se libera al
    flujo normal con una fecha vigente o se cierra como registro."""
    if request.method == "POST":
        fm = request.form
        if fm.get("accion") in ("liberar", "cerrar"):
            o = db().get(SalesOrder, int(fm.get("oid") or 0)) or abort(404)
            if fm["accion"] == "liberar":
                return act(lambda: osvc.regularize_release(o, g.user, f_date("nueva_fecha", True), fm.get("comentario", "")),
                           f"OV {o.numero} liberada al flujo normal y evaluada.", url_for("com.order_detail", oid=o.id))
            return act(lambda: osvc.regularize_close(o, g.user, fm.get("comentario", "")),
                       f"OV {o.numero} cerrada como regularización.", url_for("com.regularization"))

        def _crear():
            c = db().get(Customer, int(fm.get("customer_id") or 0))
            if c is None:
                raise BusinessError("Cliente no válido.")
            if not fm.get("motivo", "").strip():
                raise BusinessError("Indique el motivo de la regularización.")
            return osvc.create_order(g.user, fm.get("numero"), c.id, f_date("fecha_compromiso", True), _lines_from_form(),
                                     comentarios=fm.get("comentarios", ""), hora_cita=fm.get("hora_cita", ""),
                                     vendedor_id=fm.get("vendedor_id") or None, canal_precio=fm.get("canal_precio", ""),
                                     regularizacion=fm.get("motivo", ""))
        return act(_crear, lambda o: f"OV {o.numero} registrada como regularización (sin reserva de stock).",
                   url_for("com.regularization"))
    rows = list(db().execute(select(SalesOrder).where(SalesOrder.estado.in_(("REGULARIZADA", "REGULARIZADA_CERRADA")))
                             .order_by(SalesOrder.id.desc())).scalars())
    customers = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    vendedores = list(db().execute(select(User).where(User.role_code == "EJECUTIVO_VENTAS")).scalars())
    products = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP"])).order_by(Product.code)).scalars())
    return render_template("ov_regularization.html", rows=rows, customers=customers, vendedores=vendedores,
                           products=products, horas=osvc.horas_cita())


@bp.route("/<int:oid>/imprimir")
@perm_required("ov.ver")
def order_print(oid):
    """Formato de OV con los logos de Corporación Productiva, Cantaclaro y Cosecha Andina (foto del 13-oct)."""
    from ..services.documents import ov_document
    o = db().get(SalesOrder, oid) or abort(404)
    return render_template("ov_print.html", o=o, d=ov_document(o))


@bp.route("/<int:oid>/accion/<accion>", methods=["POST"])
@perm_required("ov.ver")
def order_action(oid, accion):
    o = db().get(SalesOrder, oid) or abort(404)
    back = url_for("com.order_detail", oid=oid)
    u = g.user
    f = request.form

    def changes():
        ch = {"fecha_compromiso": f_date("fecha_compromiso"), "urgente": f_bool("urgente"),
              "comentarios": f.get("comentarios"), "hora_cita": f.get("hora_cita"), "cita_confirmada": f_bool("cita_confirmada")}
        lines = _lines_from_form()
        if lines:
            ch["lines"] = lines
        return ch

    actions = {
        "modificar": (lambda: osvc.modify_order(o, u, changes()), "OV modificada y reevaluada."),
        "solicitar": (lambda: osvc.request_change(o, u, changes(), f.get("motivo", "")), "Solicitud enviada para autorización."),
        "cancelar": (lambda: osvc.cancel_order(o, u, f.get("motivo", "")), "OV cancelada: reservas y ruta liberadas."),
        "reevaluar": (lambda: __import__("app.services.stock", fromlist=["x"]).evaluate_order(o, u, "REEVALUACION"), "OV reevaluada."),
        "parcial_si": (lambda: osvc.decide_partial(o, u, True, f.get("comentario", ""), f_date("fecha_saldo")),
                       lambda r: "Despacho parcial aprobado; ruta programada. El saldo se reprogramará al salir el despacho." if o.decision_parcial == "APROBADA"
                       else "Aprobación registrada; falta: " + ", ".join(osvc.partial_pending_roles(o))),
        "parcial_no": (lambda: osvc.decide_partial(o, u, False, f.get("comentario", "")), "Despacho parcial rechazado."),
        "confirmar_precio": (lambda: __import__("app.services.prices", fromlist=["x"]).approve_price(o, u, f.get("comentario", "")),
                             "Precio confirmado: la OV queda liberada para preparación y despacho."),
        "renegociar": (lambda: osvc.renegotiate_date(o, u, f_date("nueva_fecha", True), f.get("comentario", "")), "Fecha renegociada; OV reevaluada."),
        "cambiar_producto": (lambda: osvc.change_product(o, u, f.get("line_id"), f.get("nuevo_codigo", "").strip().upper(),
                                                          f_float("cantidad", True), f.get("comentario", "")), "Producto cambiado; OV reevaluada."),
        "traslado": (lambda: tsvc.request_transfer(u, f.get("lot_id"), f.get("destino"), f_float("cantidad", True), o,
                                                   f.get("observacion", "")), "Traslado solicitado (lo aprueba el Jefe o el Coordinador de Logística)."),
        "reempaque": (lambda: rsvc.request(u, f.get("tipo"), f.get("lot_id"), f_float("cantidad", True), f.get("producto_destino") or None,
                                           None, o, f.get("motivo", "")), "Solicitud de reempaque enviada a Calidad."),
        "produccion": (lambda: psvc.create_request(f.get("product_code"), f_float("cantidad", True), u, o, o.fecha_compromiso),
                       "Solicitud preliminar de producción creada (borrador para revisión de Almacén)."),
        "compra": (lambda: buysvc.create_request(u, f.get("product_code"), f_float("cantidad", True), o.fecha_compromiso, "OV", o),
                   "Solicitud de compra enviada a Compras."),
    }
    if accion not in actions:
        abort(404)
    fn, msg = actions[accion]
    if f.get("volver") == "opciones":
        back = url_for("com.order_options", oid=oid)
    return act(fn, msg, back)


@bp.route("/solicitud/<int:rid>/<decision>", methods=["POST"])
@perm_required("ov.autorizar_modificacion")
def change_request(rid, decision):
    r = db().get(OVChangeRequest, rid) or abort(404)
    return act(lambda: osvc.resolve_change(r, g.user, decision == "aprobar", request.form.get("comentario", "")),
               "Solicitud resuelta.", url_for("com.order_detail", oid=r.order_id))


# ------------------------------- preparación -------------------------------
@bp.route("/preparacion")
@perm_required("preparacion.registrar", "ov.ver")
def preparation():
    queue = osvc.preparation_queue()
    cortes = {}
    for o in queue:
        cortes.setdefault(o.corte or "Sin corte configurado", []).append(o)
    from ..services.core import param
    return render_template("prep_list.html", cortes=cortes, progress=osvc.prep_progress, tiempos=param("tiempos_preparacion", {}),
                           peso=lambda o: osvc.order_weight_kg(o)[0])


@bp.route("/preparacion/<int:oid>", methods=["GET", "POST"])
@perm_required("preparacion.registrar", "ov.ver")
def picking(oid):
    o = db().get(SalesOrder, oid) or abort(404)
    if request.method == "POST":
        acc = request.form.get("accion", "picking")
        back = url_for("com.picking", oid=oid)
        if acc == "validar_plan":
            return act(lambda: osvc.validate_picking_plan(o, g.user), "Planificación de picking validada.", back)
        if acc == "cambiar_lote":
            return act(lambda: osvc.reassign_pick_lot(o, g.user, request.form.get("reservation_id"), request.form.get("lot_id"),
                                                      request.form.get("cantidad") or None),
                       "Planificación modificada: lote cambiado.", back)
        return act(lambda: osvc.register_picking(o, g.user, request.form.get("line_id"), f_float("cantidad", True),
                                                 request.form.get("lote", "").strip()),
                   lambda p: f"Picking registrado. Avance {p}%.", back)
    from ..services.stock import free_qty, lot_usable, lots_of, principal_warehouses
    candidatos = {}
    for l in o.lines:
        if l.activa:
            whs = [w.code for w in principal_warehouses(l.product)]
            candidatos[l.id] = [x for x in lots_of(l.product_code, whs)
                                if lot_usable(x, o.fecha_compromiso, o.customer)[0] and free_qty(x) > 0]
    return render_template("prep_detail.html", o=o, progress=osvc.prep_progress(o), line_reserved=line_reserved,
                           candidatos=candidatos, free=free_qty)


# ------------------------------ listas de precios (Q11) --------------------
@bp.route("/precios", methods=["GET", "POST"])
@perm_required("precios.ver", "precios.editar")
def prices():
    from ..models import PriceItem
    from ..services import prices as psvc
    if request.method == "POST" and request.form.get("accion") == "agregar":
        fm = request.form
        return act(lambda: psvc.add_item(g.user, fm.get("lista", "GENERAL"), fm.get("sku", ""), canal=fm.get("canal", ""),
                                         precio=f_float("precio"), precio_saco=f_float("precio_saco"), kg_saco=f_float("kg_saco"),
                                         motivo=fm.get("motivo", "")),
                   "Precio mínimo agregado.", url_for("com.prices", lista=fm.get("lista", "GENERAL"), q=fm.get("sku", "")))
    if request.method == "POST" and request.form.get("accion") == "vigencia":
        fm = request.form
        return act(lambda: psvc.set_validity(g.user, fm.get("lista", "GENERAL"), f_date("vigencia_desde"), f_date("vigencia_hasta")),
                   "Vigencia actualizada.", url_for("com.prices", lista=fm.get("lista", "GENERAL")))
    if request.method == "POST":
        it = db().get(PriceItem, int(request.form["item_id"]))
        if it is None:
            abort(404)
        return act(lambda: psvc.edit_item(it, g.user, request.form.get("motivo", ""), precio=f_float("precio"),
                                          precio_kg=f_float("precio_kg"), precio_saco=f_float("precio_saco")),
                   "Precio actualizado (versión anterior en el historial).",
                   url_for("com.prices", lista=it.lista, q=request.args.get("q", ""), canal=request.args.get("canal", "")))
    lista = request.args.get("lista", "GENERAL")
    q = request.args.get("q", "").strip()
    canal = request.args.get("canal", "")
    rows = psvc.vigentes(lista, q, canal if lista == "GENERAL" else "")
    hist = psvc.history(request.args["sku"]) if request.args.get("sku") else None
    from ..models import PriceListMeta
    from ..services.core import param
    metas = {m.lista: m for m in db().execute(select(PriceListMeta)).scalars()}
    from ..models import Alert
    faltantes = list(db().execute(select(Alert).where(Alert.type_code == "PRECIO_FALTANTE", Alert.estado != "CERRADA")
                                  .order_by(Alert.id.desc()).limit(30)).scalars())
    return render_template("prices.html", rows=rows[:600], total=len(rows), lista=lista, q=q, canal=canal,
                           canales=psvc.canales(), hist=hist, sku=request.args.get("sku", ""), metas=metas,
                           canal_granel=(param("lista_granel_canales", []) or ["-"])[0], faltantes=faltantes)


# ------------------------------ costos y mercado (R4, R5 – 13-oct) --------
@bp.route("/costos", methods=["GET", "POST"])
@perm_required("costos.ver")
def costs():
    from ..services import costs as csvc
    from ..models import MarketPrice, ProductCost
    if request.method == "POST":
        fm = request.form
        return act(lambda: csvc.add_market_prices([{"producto": fm.get("producto", ""), "variedad": fm.get("variedad", ""),
                                                    "precio_kg": f_float("precio_kg", True), "tipo_precio": fm.get("tipo_precio"),
                                                    "mercado": fm.get("mercado", ""), "fecha": f_date("fecha", True),
                                                    "fuente": fm.get("fuente", ""), "url": fm.get("url", "")}], g.user, "Alta manual")
                   and csvc.check_market_alerts(g.user), "Precio de mercado registrado y análisis recalculado.",
                   url_for("com.costs"))
    tipo = request.args.get("tipo", "MAYORISTA")
    analisis = csvc.market_analysis(tipo)
    costos = list(db().execute(select(ProductCost).where(ProductCost.vigente.is_(True)).order_by(ProductCost.product_code)).scalars())
    mercado = list(db().execute(select(MarketPrice).order_by(MarketPrice.fecha.desc(), MarketPrice.producto).limit(300)).scalars())
    from ..services import charts
    productos = sorted({m.producto for m in mercado if m.tipo_precio == tipo})
    sel = request.args.get("producto") or (productos[0] if productos else "")
    serie = [(m.fecha.strftime("%d/%m/%y"), m.precio_kg) for m in reversed(mercado) if m.producto == sel and m.tipo_precio == tipo]
    graf = charts.line([(f"{sel} ({tipo.lower()})", serie)], "S/ por kg", title=f"Precio de mercado {sel}")
    brechas = charts.bars([(r["code"] + " " + (r["base"] or "")[:18], r["brecha_pct"]) for r in
                           sorted(analisis, key=lambda r: r["brecha_pct"] if r["brecha_pct"] is not None else 999)
                           if r["brecha_pct"] is not None], "%", title="Margen del mercado sobre el costo")
    from ..services import market as msvc
    comparacion = [f for f in msvc.analysis(int(request.args.get("dias") or 180))["venta"]
                   if f["prom_competencia"] or f["prom_sustitutos"]]
    return render_template("costs.html", analisis=analisis, comparacion=comparacion, costos=costos, mercado=mercado, tipo=tipo, productos=productos,
                           sel=sel, graf=graf, brechas=brechas, serie=serie, impacto=csvc.quote_impact())


# ------------------------------ ficha de cliente (13-oct) ------------------
@bp.route("/clientes", methods=["GET", "POST"])
@perm_required("clientes.ver")
def customer_list():
    from ..services import customers as csv_
    if request.method == "POST":
        return act(lambda: csv_.save_customer(g.user, None, request.form), lambda c: f"Cliente {c.nombre} creado.",
                   url_for("com.customer_list"), redirect_fn=lambda c: url_for("com.customer_card", cid=c.id))
    from ..services import prices as psvc
    a = request.args
    f = {"q": a.get("q", ""), "grupo": a.get("grupo", ""), "canal": a.get("canal", ""), "vendedor_id": a.get("vendedor_id", "")}
    rows = csv_.search(f["q"], f["grupo"], f["canal"], f["vendedor_id"] or None)
    todos = list(db().execute(select(Customer)).scalars())
    vendedores = list(db().execute(select(User).where(User.role_code.in_(("EJECUTIVO_VENTAS", "COORD_VENTAS", "JEFE_VENTAS")))
                                   .order_by(User.nombre)).scalars())
    return render_template("customer_list.html", rows=rows, f=f, canal_de=psvc.channel_of, vendedores=vendedores,
                           grupos=sorted({c.grupo for c in todos if c.grupo}), grupos_alta=csv_.customer_groups(),
                           canales=sorted({psvc.channel_of(c) for c in todos if psvc.channel_of(c)}))


@bp.route("/clientes/<int:cid>", methods=["GET", "POST"])
@perm_required("clientes.ver")
def customer_card(cid):
    from ..models import CustomerSite
    from ..services import customers as csv_
    from ..services import prices as psvc
    from ..services.core import param
    from ..services.customer_conditions import TIPO_TXT, for_customer
    c = db().get(Customer, cid) or abort(404)
    if request.method == "POST":
        acc = request.form.get("accion")
        if acc == "lugar":
            sid = request.form.get("site_id")
            site = db().get(CustomerSite, int(sid)) if sid else None
            if site is not None and site.customer_id != c.id:
                abort(404)
            return act(lambda: csv_.save_site(g.user, c, request.form, site), "Lugar de entrega guardado.",
                       url_for("com.customer_card", cid=cid))
        if acc == "penalidad":
            from ..services.customer_conditions import set_penalty_amounts
            cond = for_customer(c) or abort(404)
            vals = {t: (request.form.get(f"modo_{t}", "FIJO"), request.form.get(f"valor_{t}", "").strip())
                    for t in (cond.penalidad_tipos or []) if t != "FILL_RATE"}
            return act(lambda: set_penalty_amounts(cond, g.user, vals), "Montos de penalidad guardados.",
                       url_for("com.customer_card", cid=cid))
        def _guardar():
            from flask import current_app
            from ..services.distribution import save_upload
            datos = request.form.to_dict(flat=False)
            datos = {k: (v if k in ("celulares", "correos") else v[0]) for k, v in datos.items()}
            arch = save_upload(request.files.get("contrato"), current_app.config["UPLOAD_DIR"], f"contrato_{c.ruc}")
            if arch:
                datos["contrato_archivo"] = arch
            return csv_.save_customer(g.user, c, datos)
        return act(_guardar, "Ficha guardada.", url_for("com.customer_card", cid=cid))
    canales = sorted(set(psvc.canales()) | set(param("lista_granel_canales", []) or []))
    return render_template("customer_card.html", c=c, p=csv_.profile(c), grupos=csv_.customer_groups(), cond=for_customer(c), canal=psvc.channel_of(c),
                           canales=canales, editable="clientes.editar" in g.perms,
                           tipo_txt=TIPO_TXT, vendedores=list(db().execute(select(User).where(User.role_code.in_(
                               ("EJECUTIVO_VENTAS", "COORD_VENTAS", "JEFE_VENTAS"))).order_by(User.nombre)).scalars()))


# ------------------- precios de mercado por origen (obs. demo v0.6) -------------------
@bp.route("/mercado/registrar", methods=["POST"])
@perm_required("costos.cargar", "compras.gestionar", "importaciones.gestionar")
def market_add():
    from ..services import market
    fm = request.form
    fila = {"producto": fm.get("producto", ""), "variedad": fm.get("variedad", ""), "precio_kg": f_float("precio_kg", True),
            "tipo_precio": fm.get("tipo_precio") or "MAYORISTA", "mercado": fm.get("mercado", ""), "fecha": f_date("fecha", True),
            "fuente": fm.get("fuente", ""), "competidor": fm.get("competidor", ""), "presentacion": fm.get("presentacion", ""),
            "product_code": fm.get("product_code", "")}
    volver = fm.get("volver") or url_for("com.market_analysis")
    if not volver.startswith("/") or volver.startswith("//"):
        volver = url_for("com.market_analysis")
    return act(lambda: market.add(g.user, fm.get("categoria", ""), [fila], "Alta manual"), "Precio registrado.", volver)


@bp.route("/mercado/informe", methods=["GET", "POST"])
@perm_required("costos.cargar")
def market_report():
    """Importa un informe (Excel o PDF) y extrae los precios de productos compatibles para revisión."""
    from flask import current_app
    from ..services import market
    up = current_app.config["UPLOAD_DIR"]
    token = request.values.get("token")
    if request.method == "POST" and request.form.get("accion") == "confirmar":
        def _confirmar():
            prev = market.load_preview(up, token)
            elegidas = set(request.form.getlist("fila"))
            fecha = f_date("fecha", True)
            n = 0
            for i, x in enumerate(prev["filas"]):
                if str(i) not in elegidas:
                    continue
                cat = request.form.get(f"cat_{i}", x["categoria"])
                n += market.add(g.user, cat, [{"producto": x["producto"], "precio_kg": request.form.get(f"pkg_{i}") or x["precio_kg"],
                                               "fecha": fecha, "fuente": x["fuente"], "competidor": request.form.get(f"comp_{i}", ""),
                                               "presentacion": f"{x['presentacion_kg']:g} kg" if x.get("presentacion_kg") else "",
                                               "product_code": x["product_code"], "variedad": x["texto"][:100],
                                               "tipo_precio": "MINORISTA"}], prev["meta"]["archivo"])
            return n
        return act(_confirmar, lambda n: f"{n} precio(s) registrados desde el informe.", url_for("com.market_analysis"))
    if request.method == "POST":
        def _subir():
            f = request.files.get("archivo")
            if f is None or not f.filename:
                raise BusinessError("Seleccione el informe (Excel o PDF).")
            import os
            import tempfile
            ext = os.path.splitext(f.filename)[1].lower()
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                f.save(tmp.name)
            try:
                filas = market.parse_report(tmp.name, f.filename)
            finally:
                os.unlink(tmp.name)
            return market.save_preview(up, filas, {"archivo": f.filename})
        resp = act(_subir, "Informe leído: revise las filas compatibles.", url_for("com.market_report"),
                   redirect_fn=lambda tk: url_for("com.market_report", token=tk))
        return resp
    prev = None
    if token:
        try:
            prev = market.load_preview(up, token)
        except BusinessError as e:
            flash(str(e), "error")
    return render_template("market_report.html", prev=prev, token=token, categorias=market.categorias_para(g.user),
                           hoy=date.today())


@bp.route("/mercado/sustitutos", methods=["GET", "POST"])
@perm_required("costos.ver")
def market_substitutes():
    """Productos sustitutos: alta individual o por Excel (decisión del usuario, 15-oct-2026)."""
    from ..models import ProductSubstitute
    from ..services import market
    if request.method == "POST":
        if "costos.cargar" not in g.perms:
            abort(403)
        acc = request.form.get("accion")
        volver = url_for("com.market_substitutes")
        if acc == "desactivar":
            def _des():
                x = db().get(ProductSubstitute, int(request.form.get("sid") or 0))
                if x is None:
                    raise BusinessError("Sustituto no encontrado.")
                market.remove_substitute(g.user, x)
            return act(_des, "Sustituto desactivado.", volver)
        if acc == "excel":
            def _imp():
                f = request.files.get("archivo")
                if f is None or not f.filename:
                    raise BusinessError("Seleccione el archivo Excel.")
                import os
                import tempfile
                suf = ".pdf" if f.filename.lower().endswith(".pdf") else ".xlsx"
                with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
                    f.save(tmp.name)
                try:
                    n, errores = market.import_substitutes(g.user, tmp.name, f.filename)
                finally:
                    os.unlink(tmp.name)
                for e in errores[:20]:
                    flash(e, "error")
                return n
            return act(_imp, lambda n: f"{n} sustituto(s) nuevos registrados desde el archivo.", volver)
        return act(lambda: market.add_substitute(g.user, request.form.get("producto_base", ""),
                                                 request.form.get("sustituto", ""), request.form.get("observacion", "")),
                   "Sustituto registrado.", volver)
    filas = list(db().execute(select(ProductSubstitute).order_by(ProductSubstitute.activo.desc(),
                                                                 ProductSubstitute.producto_base,
                                                                 ProductSubstitute.sustituto)).scalars())
    return render_template("market_substitutes.html", filas=filas, bases=sorted(market.bases()),
                           editable="costos.cargar" in g.perms)


@bp.route("/mercado/analisis")
@perm_required("costos.ver")
def market_analysis():
    from ..services import charts, market
    dias = int(request.args.get("dias") or 180)
    d = market.analysis(dias)
    graf = {f["producto"]: charts.line([(n, s) for n, s in (("Compra nacional", f["serie_nacional"]),
                                                             ("Importación", f["serie_importacion"])) if s],
                                       "S/ por kg", title=f"{f['producto']}: a cuánto compramos")
            for f in d["compra"] if f["serie_nacional"] or f["serie_importacion"]}
    return render_template("market_analysis.html", d=d, graf=graf, dias=dias, categorias=market.categorias_para(g.user))
