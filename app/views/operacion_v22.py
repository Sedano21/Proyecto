"""V22 (06-nov-2026): cuadro de despacho y rutas manuales, disponibilidad del personal, recepción de devoluciones, tickets
(«Reportar avería»), sugerencias de eficiencia, gastos por área y embudo comercial."""
from datetime import date, timedelta

from flask import Blueprint, Response, abort, current_app, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import Absence, Driver, ReturnReceipt, Route, SalesOrder, Ticket, User, Vehicle
from ..services import ausencias as asv
from ..services import devoluciones as dev
from ..services import rutas_manual as rm
from ..services import tickets as tk
from ..services.core import BusinessError
from ..services.distribution import save_evidences
from .common import act, f_date, f_float, login_required, paginate, perm_required

bp = Blueprint("v22", __name__, url_prefix="/operacion")


def _up():
    return current_app.config["UPLOAD_DIR"]


# ------------------------------------------------------------------ cuadro de despacho y ruta manual
@bp.route("/despacho", methods=["GET", "POST"])
@perm_required("distribucion.ver")
def board():
    fecha = f_date("fecha") or date.today()
    if request.method == "POST":
        f = request.form
        if "distribucion.programar" not in g.perms:
            abort(403)
        return act(lambda: rm.create_manual(g.user, f_date("fecha_ruta") or fecha, f, f.getlist("ov"), f.getlist("traslado"),
                                            f.getlist("auxiliar")),
                   lambda r: f"Ruta #{r.id} registrada." + (" ¡Atención: sobrecarga!" if rm.overload(r) else ""),
                   url_for("v22.board", fecha=fecha.isoformat()), redirect_fn=lambda r: url_for("dist.route_detail", rid=r.id))
    if request.args.get("salida") == "cuadro_xlsx":  # V23: formato del Excel de rutas de la empresa
        return Response(rm.cuadro_empresa_excel(fecha), headers={"Content-Disposition": f"attachment; filename=rutas_{fecha:%Y%m%d}.xlsx"},
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if request.args.get("vista") == "cuadro":
        return render_template("v23_cuadro.html", d=rm.cuadro_empresa(fecha), fecha=fecha)
    if request.args.get("salida") == "xlsx":
        return Response(rm.board_excel(fecha), headers={"Content-Disposition": f"attachment; filename=despacho_{fecha:%Y%m%d}.xlsx"},
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    from ..services.distribution import dispatchable_orders, orders_in_active_route
    usados = orders_in_active_route()
    pend = [o for o in dispatchable_orders(fecha, require_prepared=False)
            if o.id not in usados or rm.automatic_proposal(o) is not None]  # las de propuestas automáticas se pueden tomar
    from ..services.orders import order_amount, order_weight_kg
    ausentes = asv.unavailable_driver_ids(fecha)
    drivers = [d for d in db().execute(select(Driver).where(Driver.disponible.is_(True)).order_by(Driver.nombre)).scalars()]
    vehicles = list(db().execute(select(Vehicle).where(Vehicle.disponible.is_(True)).order_by(Vehicle.capacidad_kg)).scalars())
    auxiliares = list(db().execute(select(User).where(User.role_code == "AUX_DESPACHO", User.activo.is_(True))
                                   .order_by(User.nombre)).scalars())
    trabajadores = list(db().execute(select(User).where(User.activo.is_(True), User.role_code.in_(
        ("EJECUTIVO_VENTAS", "COORD_VENTAS", "JEFE_VENTAS", "ASIST_VENTAS", "AUX_ALMACEN", "SUPERV_ALMACEN", "LIDER_ALMACEN",
         "COORD_DISTRIBUCION", "ASIST_DISTRIBUCION", "COMPRAS")))
        .order_by(User.nombre)).scalars())
    return render_template("v22_board.html", d=rm.daily_board(fecha), fecha=fecha, pend=pend, peso=lambda o: order_weight_kg(o)[0],
                           monto=order_amount, prop=rm.automatic_proposal, drivers=drivers, ausentes=ausentes, vehicles=vehicles, auxiliares=auxiliares,
                           traslados=rm.open_transfers(), tw=rm.transfer_weight, trabajadores=trabajadores,
                           aus_txt={d: asv.texto(asv.ausencia_de("DRIVER", d, fecha) or asv.ausencia_de(
                               "USER", db().get(Driver, d).user_id, fecha)) for d in ausentes})


@bp.route("/ruta/<int:rid>", methods=["POST"])
@perm_required("distribucion.programar", "distribucion.seguridad", "distribucion.carga", "distribucion.conformidad")
def route_action(rid):
    r = db().get(Route, rid) or abort(404)
    back = request.form.get("volver") or url_for("dist.route_detail", rid=rid)
    f = request.form
    acc = f.get("accion")
    if acc == "modificar":
        aux = f.getlist("auxiliar") if f.get("aux_enviado") else None
        return act(lambda: rm.modify(r, g.user, f.get("motivo", ""), f.getlist("agregar_ov"), f.getlist("quitar_stop"),
                                     f.getlist("agregar_traslado"), f.getlist("quitar_traslado"), f.get("vehicle_id") or None,
                                     f.get("driver_id") or None, aux, f),
                   lambda x: "Ruta modificada." + (" ¡Atención: sobrecarga!" if rm.overload(r) else ""), back)
    if acc == "peso_real":
        return act(lambda: rm.set_real_weight(r, g.user, f.get("peso_real_kg")),
                   lambda m: f"Peso real registrado. {m}" if m else "Peso real registrado: dentro de lo permitido.", back)
    if acc == "pernocte":
        return act(lambda: rm.register_overnight(r, g.user, save_evidences(request.files.getlist("fotos"), _up(),
                                                                           f"pernocte_{r.id}", videos=False), f.get("nota", "")),
                   "Pernocte registrado con foto.", back)
    abort(404)


@bp.route("/flota/cargas")
@perm_required("distribucion.ver", "flota.ver")
def vehicle_loads():
    dias = int(request.args.get("dias") or 90)
    from ..catalogs import IMAGENES_CHECKLIST
    return render_template("v22_cargas.html", filas=rm.vehicle_load_stats(dias), dias=dias, imagenes=IMAGENES_CHECKLIST)


@bp.route("/flota/vehiculo/<int:vid>/capacidad", methods=["POST"])
@perm_required("distribucion.flota")
def vehicle_capacity(vid):
    v = db().get(Vehicle, vid) or abort(404)

    def _do():
        from ..services.core import audit
        real, hab = f_float("capacidad_real_kg"), f_float("carga_habitual_kg")
        if real is not None and real <= 0 or hab is not None and hab <= 0:
            raise BusinessError("Los pesos deben ser mayores que cero.")
        v.capacidad_real_kg, v.carga_habitual_kg = real, hab
        img = request.form.get("imagen_checklist", "")
        from ..catalogs import IMAGENES_CHECKLIST
        if img and img not in IMAGENES_CHECKLIST:
            raise BusinessError("Imagen no válida.")
        v.imagen_checklist = img
        audit(g.user, "VEHICULO_CAPACIDAD", "Vehicle", v.id, {"real": real, "habitual": hab, "imagen": img})
    return act(_do, "Capacidades del vehículo guardadas.", request.form.get("volver") or url_for("v22.vehicle_loads"))


# ------------------------------------------------------------------ disponibilidad del personal
@bp.route("/personal/disponibilidad", methods=["GET", "POST"])
@perm_required("personal.ausencias", "asistencia.todas")
def absences():
    back = url_for("v22.absences")
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "anular":
            a = db().get(Absence, int(f.get("id") or 0)) or abort(404)
            return act(lambda: asv.cancel(g.user, a, f.get("motivo", "")), "Ausencia anulada.", back)

        def _do():
            arch = save_evidences(request.files.getlist("archivo"), _up(), "ausencia", videos=False)
            return asv.register(g.user, f.get("persona"), f.get("tipo"), f_date("desde"), f_date("hasta"), f.get("motivo", ""),
                                arch[0] if arch else "")
        return act(_do, lambda a: f"Registrado: {a.nombre} · {asv.texto(a)}.", back)
    hoy = date.today()
    desde = f_date("desde") or hoy - timedelta(days=30)
    hasta = f_date("hasta") or hoy + timedelta(days=30)
    area = request.args.get("area") or None
    rows = asv.activas(desde=desde, hasta=hasta, area=area)
    choferes = []
    for d in db().execute(select(Driver).order_by(Driver.nombre)).scalars():
        clientes, proximas = rm.driver_clients(d)
        a = asv.ausencia_de("DRIVER", d.id, hoy) or (asv.ausencia_de("USER", d.user_id, hoy) if d.user_id else None)
        choferes.append({"d": d, "clientes": clientes[:6], "proximas": proximas, "ausencia": a})
    from ..catalogs import AUSENCIA_TIPOS
    return render_template("v22_ausencias.html", rows=paginate(rows), personas=asv.personas(), tipos=AUSENCIA_TIPOS,
                           desde=desde, hasta=hasta, area=area or "", choferes=choferes, texto=asv.texto,
                           resumen=asv.summary(desde, hasta), areas=sorted({x[2] for x in asv.personas() if x[2]}))


# ------------------------------------------------------------------ devoluciones
@bp.route("/devoluciones", methods=["GET", "POST"])
@perm_required("devoluciones.ver", "devoluciones.recibir", "devoluciones.dejar_en_vehiculo")
def returns():
    back = url_for("v22.returns", estado=request.args.get("estado", ""))
    if request.method == "POST":
        f = request.form
        r = db().get(ReturnReceipt, int(f.get("id") or 0)) or abort(404)
        if f.get("accion") == "en_vehiculo":
            return act(lambda: dev.leave_in_vehicle(g.user, r, f.get("motivo", ""),
                                                    save_evidences(request.files.getlist("evidencias"), _up(), f"devolucion_{r.id}_veh")),
                       "Registrado: la mercadería queda en el vehículo. Se avisó a Almacén, Logística y Distribución.", back)
        datos = {str(e["line_id"]): {"cantidad": f.get(f"q_{e['line_id']}"), "presentacion_ok": f.get(f"pres_{e['line_id']}", "1"),
                                     "danado": f.get(f"dan_{e['line_id']}", "0"), "detalle": f.get(f"det_{e['line_id']}", "")}
                 for e in r.esperado}
        return act(lambda: dev.receive(g.user, r, datos, save_evidences(request.files.getlist("evidencias"), _up(),
                                                                         f"devolucion_{r.id}"), f.get("observacion", "")),
                   lambda difs: ("Recibida con observaciones: " + "; ".join(difs) + ". Se avisó a Logística y Calidad.")
                   if difs else "Devolución recibida conforme a la guía.", back)
    estado = request.args.get("estado") or "PENDIENTE"
    q = select(ReturnReceipt).order_by(ReturnReceipt.plazo.desc() if estado != "PENDIENTE" else ReturnReceipt.plazo,
                                       ReturnReceipt.id.desc())
    if estado == "PENDIENTE":
        q = q.where(ReturnReceipt.estado.in_(dev.POR_RECIBIR))
    elif estado != "TODAS":
        q = q.where(ReturnReceipt.estado == estado)
    rows = list(db().execute(q).scalars())
    return render_template("v22_devoluciones.html", rows=paginate(rows), estado=estado, hoy=date.today())


# ------------------------------------------------------------------ tickets («Reportar avería»)
@bp.route("/tickets/nuevo", methods=["POST"])
@login_required
def ticket_new():
    f = request.form
    back = f.get("volver") or request.referrer or url_for("main.dashboard")
    return act(lambda: tk.create(g.user, f.get("destino"), f.get("categoria"), f.get("descripcion", ""), f.get("lugar", ""),
                                 f.get("urgente") == "1", save_evidences(request.files.getlist("evidencias"), _up(), "ticket")),
               lambda t: f"Ticket #{t.id} enviado a {tk.DESTINOS[t.destino]}." + (" Marcado como urgente." if t.urgente else ""),
               back)


@bp.route("/tickets", methods=["GET", "POST"])
@login_required
def tickets():
    back = url_for("v22.tickets", destino=request.args.get("destino", ""), estado=request.args.get("estado", ""))
    if request.method == "POST":
        f = request.form
        t = db().get(Ticket, int(f.get("id") or 0)) or abort(404)
        if f.get("accion") == "asignar":
            return act(lambda: tk.assign(g.user, t, f.get("worker_id") or None, f.get("nota", "")), "Ticket asignado.", back)
        if f.get("accion") == "trabajo":
            return act(lambda: tk.to_work_order(g.user, t, f_date("fecha") or date.today(), f.get("worker_id") or None),
                       lambda wo: f"Trabajo correctivo #{wo.id} programado.", back)
        return act(lambda: tk.set_state(g.user, t, f.get("estado"), f.get("nota", ""),
                                        save_evidences(request.files.getlist("evidencias"), _up(), f"ticket{t.id}")),
                   "Ticket actualizado.", back)
    destino = request.args.get("destino") or None
    estado = request.args.get("estado") or "ABIERTOS"
    rows = tk.visible(g.user, destino, None if estado == "TODOS" else estado)
    from ..services.mant_trabajos import technicians
    hoy = date.today()
    return render_template("v22_tickets.html", rows=paginate(rows), destino=destino or "", estado=estado, estados=tk.ESTADOS,
                           tecnicos=technicians(), atiende=lambda t: tk.can_attend(g.user, t),
                           tiempos=tk.response_times(hoy - timedelta(days=30), hoy, destino))


# ------------------------------------------------------------------ gerencia, finanzas y comercial
@bp.route("/sugerencias")
@perm_required("sugerencias.ver")
def suggestions():
    from ..services import sugerencias
    return render_template("v22_sugerencias.html", rows=sugerencias.all_suggestions())


@bp.route("/finanzas/gastos-por-area")
@perm_required("finanzas.gastos_areas")
def area_spending():
    from ..services import tablero_gg
    return render_template("v22_gastos.html", filas=tablero_gg.budget_by_area(), hoy=date.today(),
                           tarjetas=tablero_gg.area_cards(perms=frozenset(g.perms)))


@bp.route("/comercial/embudo")
@perm_required("informes.comercial", "ov.ver")
def funnel():
    from ..services import tablero_gg
    hoy = date.today()
    desde = f_date("desde") or hoy.replace(day=1) - timedelta(days=60)
    hasta = f_date("hasta") or hoy
    vend = request.args.get("vendedor") or None
    if g.user.role_code == "EJECUTIVO_VENTAS":
        vend = g.user.id
    vendedores = list(db().execute(select(User).where(User.role_code == "EJECUTIVO_VENTAS").order_by(User.nombre)).scalars())
    d = tablero_gg.funnel(desde, hasta, vend)
    from ..services import charts
    t = d["tablero"]
    graf = {"producto": charts.donut_parts(t["por_producto"], "oportunidades"),
            "etapas": charts.funnel_shape([(f["nombre"], f["n"]) for f in d["filas"] if f["code"] not in ("OV", "ENTREGADAS")]),
            "ejecutivo": charts.columns(t["por_ejecutivo"]["labels"], t["por_ejecutivo"]["series"], "", width=420, height=260,
                                        title="Oportunidades por ejecutivo y etapa"),
            "canal": charts.donut_parts(t["canales"], "clientes"), "tipo": charts.donut_parts(t["tipos"], "oportunidades"),
            "cierre": charts.bars(t["cierres"], "", width=420, title="Motivo de cierre", color=6),
            "dia": charts.line(t["por_dia"], "", title="Oportunidades por día y ejecutivo") if t["por_dia"] else None}
    return render_template("v22_embudo.html", d=d, graf=graf, vendedores=vendedores,
                           vend=str(vend or ""), desde=desde, hasta=hasta)


# ------------------------------------------------------------------ V27: regularización de guías emitidas en SUNAT
@bp.route("/guias-sunat", methods=["GET", "POST"])
@perm_required("guias.sunat_cargar", "guias.regularizar_inventario", "distribucion.ver")
def sunat_guides():
    import os
    import uuid
    from ..models import SunatGuide
    from ..services import guias_sunat as gs
    back = url_for("v22.sunat_guides")
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "cargar":
            if "guias.sunat_cargar" not in g.perms:
                abort(403)

            def _cargar():
                archivos = [x for x in request.files.getlist("archivos") if x and x.filename]
                if not archivos:
                    raise BusinessError("Elija el PDF o el XML de la guía (puede subir varias a la vez).")
                ok, errores = [], []
                for a in archivos:
                    ext = os.path.splitext(a.filename)[1].lower()
                    if ext not in (".pdf", ".xml"):
                        errores.append(f"{a.filename}: suba el PDF de SUNAT o su XML.")
                        continue
                    nombre = f"guia_sunat_{uuid.uuid4().hex[:10]}{ext}"
                    a.save(os.path.join(_up(), nombre))
                    try:
                        with db().begin_nested():
                            ok.append(gs.registrar(g.user, os.path.join(_up(), nombre), a.filename, nombre))
                    except BusinessError as e:
                        errores.append(f"{a.filename}: {e}")
                if not ok:
                    raise BusinessError(" ".join(errores))
                return ok, errores
            return act(_cargar, lambda r: f"{len(r[0])} guía(s) cargada(s)." + (f" No se cargaron: {' '.join(r[1])}" if r[1] else ""), back)
        gd = db().get(SunatGuide, int(f.get("id") or 0)) or abort(404)
        if acc == "unir":
            return act(lambda: gs.unir(g.user, gd, f.get("order_id") or None, f.get("sap_ov", "")), "Guía unida a su OV.", back)
        if acc == "inventario":
            return act(lambda: gs.decidir_inventario(g.user, gd, f.get("decision"), f.get("nota", "")),
                       lambda x: "Inventario: " + ("descontado del lote." if x.inventario["decision"] == "DESCONTADO" else
                                                   "ya estaba descontado (no se cambió el stock)."), back)
        if acc == "sap":
            # V35: si SAP la rechaza se guarda el error (y el préstamo, si es por inventario negativo) para verlo después
            from flask import flash
            from ..services.core import BusinessError
            try:
                x = gs.enviar_sap(g.user, gd)
                db().commit()
                flash(f"Guía registrada en SAP (entrega {x.sap.get('docnum')}).", "ok")
            except BusinessError as e:
                db().commit()
                msg = str(e)
                if (gd.prestamo or {}).get("estado") == "PENDIENTE":
                    msg += (" · SAP ya no tiene ese stock (p. ej. se descontó por reconteo): se generó el PRÉSTAMO y se avisó "
                            "a la Jefatura de Operaciones, Distribución y Logística para registrar el ingreso de mercadería.")
                flash(msg, "error")
            return redirect(back)
        abort(400)
    guias = list(db().execute(select(SunatGuide).order_by(SunatGuide.id.desc()).limit(200)).scalars())
    return render_template("guias_sunat.html", guias=paginate(guias, 25), cand={x.id: gs.candidatas(x) for x in guias if not x.order_id})


@bp.route("/ingresos-mercaderia", methods=["GET", "POST"])
@perm_required("stock.ingreso_sap", "guias.regularizar_inventario")
def goods_receipts():
    """V35: ingreso de mercadería a SAP (préstamo de stock para registrar una guía SUNAT y otros casos)."""
    from ..models import GoodsReceipt, SunatGuide, Warehouse
    from ..services import ingresos_sap as ing
    back = url_for("v22.goods_receipts")
    guia = db().get(SunatGuide, int(request.values.get("guia") or 0)) if request.values.get("guia") else None
    if request.method == "POST":
        f = request.form
        filas = [{"codigo": c, "lote": l, "cantidad": q, "fp": fp, "fv": fv, "precio": pr}
                 for c, l, q, fp, fv, pr in zip(f.getlist("codigo"), f.getlist("lote"), f.getlist("cantidad"),
                                                f.getlist("fp"), f.getlist("fv"), f.getlist("precio"))]

        def _do():
            r = ing.registrar(g.user, f.get("fecha"), f.get("almacen"), f.get("motivo"), filas, guia)
            return r
        return act(_do, lambda r: (f"Ingreso #{r.id} registrado en SAP (entrada {r.sap.get('docnum')})."
                                   + (" La guía se volvió a enviar a SAP." if r.guia_id and not r.sap.get('guia_error') else "")
                                   + (f" La guía aún no pasa: {r.sap['guia_error']}" if r.sap.get("guia_error") else ""))
                   if r.estado == "EN_SAP" else f"Ingreso #{r.id} guardado, pero SAP lo rechazó: {r.sap.get('error')}", back)
    ingresos = paginate(list(db().execute(select(GoodsReceipt).order_by(GoodsReceipt.id.desc())).scalars()), 25)
    pendientes = [x for x in db().execute(select(SunatGuide)).scalars() if (x.prestamo or {}).get("estado") == "PENDIENTE"]
    almacenes = list(db().execute(select(Warehouse).where(Warehouse.habilitado.is_(True)).order_by(Warehouse.code)).scalars())
    from ..models import Product
    productos = list(db().execute(select(Product).order_by(Product.code)).scalars())
    return render_template("v35_ingresos.html", ingresos=ingresos, pendientes=pendientes, guia=guia, almacenes=almacenes,
                           productos=productos, hoy=__import__("datetime").date.today(),
                           puede="stock.ingreso_sap" in g.perms)
