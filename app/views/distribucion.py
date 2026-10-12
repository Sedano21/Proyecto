"""Vistas de Distribución: programación de rutas, salida, Seguridad, entrega con evidencia, incidencias y flota."""
from datetime import date

from flask import Blueprint, abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..catalogs import INCIDENT_TYPES
from ..db import db
from ..models import Certificate, Driver, Incident, Route, RouteStop, SalesOrder, Vehicle
from ..services import despacho as dsp
from ..services import distribution as dsvc
from ..services.core import BusinessError
from ..services.core import audit
from .common import act, f_bool, f_date, f_float, perm_required

bp = Blueprint("dist", __name__, url_prefix="/distribucion")


@bp.route("/", methods=["GET", "POST"])
@perm_required("distribucion.ver")
def routes():
    fecha = f_date("fecha") or date.today()
    if request.method == "POST":
        return act(lambda: dsvc.propose_routes(fecha, g.user), lambda r: f"{len(r)} ruta(s) propuesta(s).",
                   url_for("dist.routes", fecha=fecha.isoformat()))
    rows = list(db().execute(select(Route).where(Route.fecha == fecha).order_by(Route.id)).scalars())
    otras = list(db().execute(select(Route).where(Route.estado.in_(["PROPUESTA", "CONFIRMADA", "EN_RUTA"]), Route.fecha != fecha)
                              .order_by(Route.fecha)).scalars())
    pend = dsvc.dispatchable_orders(fecha)
    from ..services.orders import order_weight_kg
    return render_template("routes.html", rows=rows, otras=otras, fecha=fecha, pend=pend, peso=lambda o: order_weight_kg(o)[0])


@bp.route("/ruta/<int:rid>", methods=["GET", "POST"])
@perm_required("distribucion.ver")
def route_detail(rid):
    r = db().get(Route, rid) or abort(404)
    back = url_for("dist.route_detail", rid=rid)
    if request.method == "POST":
        acc = request.form.get("accion")
        u = g.user
        f = request.form
        if acc == "ajustar":
            fn = lambda: dsvc.update_route(r, u, f.get("vehicle_id") or None, f.get("driver_id") or None)  # noqa: E731
        elif acc == "mover":
            stop = db().get(RouteStop, int(f["stop_id"]))
            target = db().get(Route, int(f["target"]))
            fn = lambda: dsvc.move_stop(stop, u, target)  # noqa: E731
        elif acc == "confirmar":
            fn = lambda: dsvc.confirm_route(r, u)  # noqa: E731
        elif acc == "seguridad":
            lineas = []
            for e in dsvc.expected_lines(r):
                i = e["order_line_id"]
                lineas.append({**e, "guia": f_float(f"guia_{i}", default=0), "cargado": f_float(f"cargado_{i}", default=0),
                               "presentacion_ok": f.get(f"pres_{i}", "1") == "1"})
            fn = lambda: dsvc.register_security_check(r, u, f.get("guia_numero", ""), lineas)  # noqa: E731
        elif acc == "salida":
            fn = lambda: dsvc.confirm_departure(r, u, {k: f_bool(k) for k, _ in dsvc.CHECKLIST})  # noqa: E731
        elif acc == "llegada":
            fn = lambda: dsvc.register_arrival(db().get(RouteStop, int(f["stop_id"])), u)  # noqa: E731
        elif acc == "entrega":
            stop = db().get(RouteStop, int(f["stop_id"]))

            def fn():
                updir = current_app.config["UPLOAD_DIR"]
                foto = dsvc.save_upload(request.files.get("foto"), updir, f"foto_{stop.order.numero}")
                guia = dsvc.save_upload(request.files.get("guia"), updir, f"guia_{stop.order.numero}")
                entregas = {k[4:]: v for k, v in f.items() if k.startswith("ent_") and v != ""}
                dsvc.register_delivery(stop, u, foto, guia, entregas, f.get("observacion", ""))
        elif acc == "foto":
            def fn():
                arch = dsvc.save_upload(request.files.get("archivo"), current_app.config["UPLOAD_DIR"], f"ruta{r.id}_{f.get('etapa')}")
                dsp.add_photo(r, u, f.get("etapa"), arch, f.get("nota", ""))
        elif acc == "incidencia_carga":
            def fn():
                arch = dsvc.save_upload(request.files.get("archivo"), current_app.config["UPLOAD_DIR"], f"ruta{r.id}_incid")
                if not arch:
                    raise BusinessError("Adjunte la foto de la incidencia.")
                dsp.register_loading_incident(r, u, arch, f.get("motivo", ""), f.get("hora", ""))
        elif acc == "validar_carga":
            lineas = {k[4:]: {"cargado": v, "correcto": f.get(f"ok_{k[4:]}", "1") == "1"} for k, v in f.items() if k.startswith("car_")}
            fn = lambda: dsp.validate_load(r, u, lineas, f.get("observacion", ""))  # noqa: E731
        elif acc == "guia":
            stop = db().get(RouteStop, int(f["stop_id"]))

            def fn():
                arch = dsvc.save_upload(request.files.get("archivo"), current_app.config["UPLOAD_DIR"], f"guia_{stop.order.numero}")
                dsp.set_guide(stop, u, f.get("numero", ""), f.get("origen", "SISTEMA"), arch)
        elif acc == "factura":
            stop = db().get(RouteStop, int(f["stop_id"]))

            def fn():
                arch = dsvc.save_upload(request.files.get("archivo"), current_app.config["UPLOAD_DIR"], f"factura_{stop.order.numero}")
                return dsp.set_invoice(stop, u, f.get("numero", ""), arch)
        elif acc == "revisar_documentos":
            fn = lambda: dsp.review_documents(r, u, f_bool("impresos"))  # noqa: E731
        elif acc == "aprobar_discrepancia":
            fn = lambda: dsp.approve_exit_with_discrepancy(r, u, f.get("motivo", ""))  # noqa: E731
        elif acc == "visto_bueno":
            fn = lambda: dsp.give_exit_ok(r, u, f.get("nota", ""))  # noqa: E731
        elif acc == "resolver_guia":
            fn = lambda: dsp.resolve_guide_discrepancy(r, u, f.get("detalle", ""))  # noqa: E731
        elif acc == "retorno":
            fn = lambda: dsp.register_return(r, u)  # noqa: E731
        elif acc == "incidencia":
            stop = db().get(RouteStop, int(f["stop_id"])) if f.get("stop_id") else None
            fn = lambda: dsvc.register_incident(u, f.get("tipo"), f.get("descripcion", ""), stop=stop, route=r,  # noqa: E731
                                                cantidad=f_float("cantidad"))
        else:
            abort(404)
        msgs = {"validar_carga": lambda res: ("Incongruencias: " + "; ".join(res) + ". Se avisó al almacén.") if res else
                "Carga validada: camión cargado (alerta enviada).",
                "revisar_documentos": lambda res: ("Documentos faltantes: " + "; ".join(res) + ". Se reportó a las áreas.") if res
                else "Documentos completos: Seguridad dio conformidad. Falta la autorización de salida del Líder Operativo.",
                "factura": lambda res: "Factura cargada" + (" (con modificaciones respecto a la OV: " + "; ".join(res) + ")" if res else ".")}
        return act(fn, msgs.get(acc, "Ruta actualizada."), back)
    vehicles = list(db().execute(select(Vehicle).where(Vehicle.disponible.is_(True)).order_by(Vehicle.capacidad_kg)).scalars())
    drivers = list(db().execute(select(Driver).where(Driver.disponible.is_(True))).scalars())
    others = list(db().execute(select(Route).where(Route.fecha == r.fecha, Route.id != r.id,
                                                   Route.estado.in_(["PROPUESTA", "CONFIRMADA"]))).scalars())
    certs = {st.id: list(db().execute(select(Certificate).where(Certificate.order_id == st.order_id,
                                                                  Certificate.estado != "ANULADO")).scalars()) for st in r.stops}
    return render_template("route_detail.html", r=r, vehicles=vehicles, drivers=drivers, others=others,
                           checklist=dsvc.CHECKLIST, expected=dsvc.expected_lines(r), tipos=INCIDENT_TYPES,
                           preguia=dsp.preguia(r), etapas=dsp.ETAPAS_FOTO, certs=certs,
                           faltan=dsp.missing_documents(r) if r.estado == "CONFIRMADA" else [],
                           billing=dsp.billing_status, vb_req=dsp.required_exit_approvals(), vb_label=dsp.VB_LABEL)


@bp.route("/ruta/<int:rid>/folio")
@perm_required("distribucion.ver")
def folio(rid):
    """Pre-guía / guía del sistema y folio de documentos por pedido (imprimible)."""
    r = db().get(Route, rid) or abort(404)
    certs = {st.id: list(db().execute(select(Certificate).where(Certificate.order_id == st.order_id,
                                                                  Certificate.estado != "ANULADO")).scalars()) for st in r.stops}
    from ..services.core import param
    return render_template("folio.html", r=r, preguia=dsp.preguia(r), certs=certs, empresa=param("empresa_razon_social", ""),
                           ruc=param("empresa_ruc", ""), tipo=request.args.get("tipo", "folio"))


@bp.route("/incidencias", methods=["GET", "POST"])
@perm_required("distribucion.ver")
def incidents():
    if request.method == "POST":
        o = db().execute(select(SalesOrder).where(SalesOrder.numero == request.form.get("ov", "").strip())).scalars().first()
        return act(lambda: dsvc.register_incident(g.user, request.form.get("tipo"), request.form.get("descripcion", ""), order=o,
                                                  cantidad=f_float("cantidad")), "Incidencia registrada y alertada.",
                   url_for("dist.incidents"))
    rows = list(db().execute(select(Incident).order_by(Incident.id.desc())).scalars())
    return render_template("incidents.html", rows=rows, tipos=INCIDENT_TYPES)


@bp.route("/flota", methods=["GET", "POST"])
@perm_required("distribucion.flota")
def fleet():
    s = db()
    if request.method == "POST":
        f = request.form

        def _do():
            if f.get("tipo") == "vehiculo":
                v = s.get(Vehicle, int(f["id"])) if f.get("id") else None
                if v is None:
                    v = Vehicle(placa=f["placa"].strip().upper(), capacidad_kg=0)
                    s.add(v)
                v.descripcion = f.get("descripcion", v.descripcion)
                v.propio = f.get("propio") == "1"
                v.capacidad_kg = f_float("capacidad_kg", True)
                v.volumen_m3 = f_float("volumen_m3")
                v.disponible = f.get("disponible") == "1"
                v.conductor_habitual_id = int(f["conductor_habitual_id"]) if f.get("conductor_habitual_id") else None
                audit(g.user, "VEHICULO_GUARDADO", "Vehicle", v.placa, {"capacidad": v.capacidad_kg, "disponible": v.disponible})
            else:
                d = s.get(Driver, int(f["id"])) if f.get("id") else None
                if d is None:
                    d = Driver(nombre=f["nombre"].strip())
                    s.add(d)
                d.licencia = f.get("licencia", d.licencia)
                d.externo = f.get("externo") == "1"
                d.disponible = f.get("disponible") == "1"
                audit(g.user, "CONDUCTOR_GUARDADO", "Driver", d.nombre, {"disponible": d.disponible})
        return act(_do, "Guardado.", url_for("dist.fleet"))
    return render_template("fleet.html", vehicles=list(s.execute(select(Vehicle).order_by(Vehicle.capacidad_kg)).scalars()),
                           drivers=list(s.execute(select(Driver).order_by(Driver.nombre)).scalars()))
