"""Cadena de suministro (ronda UX 24-oct-2026): proyección de demanda, stock sin rotación, movimientos punto a punto del
montacarguista y aviso de atraso de la OV por el Jefe de Logística."""
import os

from flask import Blueprint, abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import MoveRequest, Product, SalesOrder, Warehouse
from ..services import supply as ssvc
from ..services.core import BusinessError
from ..services.distribution import save_upload
from .common import act, f_date, perm_required

bp = Blueprint("sup", __name__, url_prefix="/suministro")


@bp.route("/demanda", methods=["GET", "POST"])
@perm_required("demanda.ver", "demanda.cargar")
def demand():
    back = url_for("sup.demand", desde=request.args.get("desde", ""))
    if request.method == "POST":
        f = request.form
        from ..services import demand_plan as dp
        if f.get("accion") == "a_plan":  # V12: preprogramación → planeamiento (Producción)
            return act(lambda: dp.to_plan(g.user, f.get("mes")), lambda r: f"{len(r)} entrada(s) agregadas al planeamiento "
                       "como preprogramación del sistema (el Jefe de Producción las revisa).", back)
        if f.get("accion") == "presolicitud":  # V12: Compras genera la presolicitud de una MP faltante
            return act(lambda: dp.create_presolicitud(g.user, f.get("mes"), f.get("code")),
                       lambda r: f"Presolicitud de compra #{r.id} creada en borrador.", back)
        if "demanda.cargar" not in g.perms:
            abort(403)
        if f.get("accion") == "excel":
            def _x():
                arch = request.files.get("archivo")
                if not arch or not arch.filename.lower().endswith((".xlsx", ".xlsm")):
                    raise BusinessError("Suba la proyección en Excel (.xlsx).")
                up = current_app.config["UPLOAD_DIR"]
                os.makedirs(up, exist_ok=True)
                path = os.path.join(up, f"demanda_{os.urandom(4).hex()}.xlsx")
                arch.save(path)
                return ssvc.import_forecast(g.user, path)
            return act(_x, lambda r: f"{r[0]} fila(s) cargadas." + (f" Errores: {' | '.join(r[1][:5])}" if r[1] else ""), back)
        if f.get("accion") == "grupo":
            filas = [{"product_code": p, "cantidad": q, "canal": c, "customer_id": cl, "observacion": o} for p, q, c, cl, o in
                     zip(f.getlist("product_code"), f.getlist("cantidad"), f.getlist("canal"), f.getlist("customer_id"),
                         f.getlist("observacion"))]
            return act(lambda: ssvc.save_forecast_group(g.user, f.get("mes"), filas),
                       lambda r: f"{r['nuevas']} proyección(es) registradas" + (f"; {r['cambios']} cambio(s) enviados a "
                                                                              "Gerencia General para su autorización" if r["cambios"] else "") + ".",
                       back)
        abort(400)
    d = ssvc.forecast_view(request.args.get("desde") or None, int(request.args.get("meses") or 3))
    prods = list(db().execute(select(Product).where(Product.tipo.in_(["PT", "GR", "MP"])).order_by(Product.code)).scalars())
    from ..models import Customer
    from .comercial_mb2 import _canales
    clientes = list(db().execute(select(Customer).where(Customer.es_prospecto.is_(False)).order_by(Customer.nombre)).scalars())
    from ..services import demand_plan as dp
    mes = (request.args.get("desde") or d["meses"][0])[:7]
    vistas = {v: dp.can_see(g.user, v) for v in ("compras", "llegadas", "produccion")}
    an = dp.analyze(mes) if any(vistas.values()) or "demanda.cargar" in g.perms else None
    return render_template("demand.html", d=d, prods=prods, f=request.args, canales=_canales(), clientes=clientes,
                           pendientes=ssvc.pending_changes(), an=an, vistas=vistas, mes=mes)


@bp.route("/demanda/cambio/<int:fid>", methods=["POST"])
@perm_required("demanda.aprobar_cambio")
def demand_change(fid):
    from ..models import DemandForecast
    fc = db().get(DemandForecast, fid) or abort(404)
    ok = request.form.get("decision") == "aprobar"
    return act(lambda: ssvc.decide_change(fc, g.user, ok, request.form.get("comentario", "")),
               "Cambio autorizado." if ok else "Cambio no autorizado.", url_for("sup.demand"))


@bp.route("/rotacion")
@perm_required("rotacion.ver")
def rotation():
    d = ssvc.rotation_ranking(request.args.get("dias") or None, almacen=request.args.get("almacen") or None)
    almacenes = list(db().execute(select(Warehouse).where(Warehouse.habilitado.is_(True)).order_by(Warehouse.code)).scalars())
    return render_template("rotation.html", d=d, ver_costos="costos.ver" in g.perms, frente=request.args.get("frente", "tiempo"),
                           almacenes=almacenes)


@bp.route("/movimientos", methods=["GET", "POST"])
@perm_required("movimiento.solicitar", "movimiento.ejecutar", "movimiento.ver_todos")
def moves():
    back = url_for("sup.moves")
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        up = current_app.config["UPLOAD_DIR"]
        if acc == "solicitar":
            def _sol():
                prog = None
                if f.get("cuando") == "PROGRAMADO":  # V12: el día y la hora por separado (la hora se puede cambiar)
                    prog = ssvc._when(f.get("prog_fecha"), f.get("prog_hora")) or f.get("programado_para")
                    if prog is None:
                        raise BusinessError("Indique el día del movimiento programado.")
                carga = {k: f.get(f"carga_{k}") for k in ("tipo", "cantidad", "producto", "kg", "mp", "customer_id")}
                return ssvc.request_move(g.user, f.get("origen"), f.get("destino"), f.get("detalle", ""), f.get("cantidad", ""),
                                         f.get("prioridad"), f.get("almacen", ""), f.get("observacion", ""), prog,
                                         f.get("asignado_id") or None, f.get("aviso_min"), carga=carga)
            return act(_sol, "Movimiento solicitado.", back)
        m = db().get(MoveRequest, int(f.get("move_id") or 0)) or abort(404)
        if acc == "iniciar":
            return act(lambda: ssvc.start_move(g.user, m, save_upload(request.files.get("foto"), up, f"mov{m.id}_ini")),
                       "Movimiento iniciado.", back)
        if acc == "terminar":
            return act(lambda: ssvc.finish_move(g.user, m, save_upload(request.files.get("foto"), up, f"mov{m.id}_fin"),
                                                f.get("observacion", "")), "Movimiento completado y validado.", back)
        if acc == "reasignar":
            return act(lambda: ssvc.reassign_move(g.user, m, f.get("asignado_id") or None, f.get("motivo", "")),
                       "Movimiento reasignado (queda registrado el cambio).", back)
        if acc == "reprogramar":
            return act(lambda: ssvc.reschedule_move(g.user, m, f.get("prog_fecha"), f.get("prog_hora"), f.get("motivo", "")),
                       "Movimiento reprogramado.", back)
        if acc == "anular":
            return act(lambda: ssvc.cancel_move(g.user, m, f.get("motivo", "")), "Solicitud eliminada.", back)
        abort(400)
    from ..models import Customer, Product
    prods = list(db().execute(select(Product).order_by(Product.code)).scalars())
    from ..services.stock import product_kind
    return render_template("moves.html", rows=ssvc.moves(g.user), ejecutores=ssvc.move_executors(),
                           tipos_carga=ssvc.TIPOS_CARGA, prod_pt=[p for p in prods if product_kind(p) == "PT"],
                           prod_mp=[p for p in prods if product_kind(p) in ("MP", "GR")],
                           clientes=list(db().execute(select(Customer).order_by(Customer.nombre)).scalars()),
                           hora_def=__import__("app.services.core", fromlist=["x"]).param("hora_movimiento_programado", "08:00"),
                           puntos=ssvc.move_points(g.user.almacen or ""),
                           almacenes=list(db().execute(select(Warehouse).where(Warehouse.habilitado.is_(True))
                                                       .order_by(Warehouse.code)).scalars()))


@bp.route("/ov/<int:oid>/atraso", methods=["POST"])
@perm_required("ov.reportar_atraso")
def order_delay(oid):
    o = db().get(SalesOrder, oid) or abort(404)
    return act(lambda: ssvc.report_delay(g.user, o, request.form.get("motivo", ""), f_date("nueva_fecha")),
               "Aviso de atraso enviado a Comercial.", url_for("com.order_detail", oid=oid))
