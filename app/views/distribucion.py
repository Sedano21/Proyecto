"""Vistas de Distribución: programación de rutas, salida, Seguridad, entrega con evidencia, incidencias y flota."""
from datetime import date

from flask import Blueprint, abort, current_app, g, render_template, request, url_for
from sqlalchemy import select

from ..catalogs import INCIDENT_TYPES
from ..services.core import BusinessError
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
                               "presentacion_ok": f.get(f"pres_{i}", "1") == "1",
                               "conforme": f.get(f"conf_{i}") == "1", "motivo": f.get(f"motivo_{i}", "")})

            def fn():
                arch = dsvc.save_upload(request.files.get("foto"), current_app.config["UPLOAD_DIR"], f"ruta{r.id}_seguridad")
                res = dsvc.register_security_check(r, u, f.get("guia_numero", ""), lineas)
                if arch:
                    dsp.add_photo(r, u, "seguridad_guia", arch, "Validación contra la guía")
                return res
        elif acc == "hora_seguridad":
            fn = lambda: dsvc.register_security_time(r, u, f.get("evento", ""), f.get("hora", ""))  # noqa: E731
        elif acc == "aprobar_guia":
            stop = db().get(RouteStop, int(f["stop_id"]))
            fn = lambda: dsp.approve_guide(stop, u, f.get("comentario", ""))  # noqa: E731
        elif acc == "salida":
            def fn():
                km = f_float("km_salida")
                if km is not None:
                    r.km_salida = km
                    if r.vehicle and (r.vehicle.km_actual is None or km > r.vehicle.km_actual):
                        r.vehicle.km_actual = km
                dsvc.confirm_departure(r, u, {k: f_bool(k) for k, _ in dsvc.CHECKLIST})
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
            def fn():
                arch = dsvc.save_upload(request.files.get("foto"), current_app.config["UPLOAD_DIR"], f"ruta{r.id}_retorno")
                if arch:
                    dsp.add_photo(r, u, "vehiculo_retorno", arch, f.get("nota", ""))
                dsp.register_return(r, u, f_float("km_retorno"))
        elif acc == "costos":
            def fn():
                if "distribucion.programar" not in g.perms:
                    raise BusinessError("Los costos y la hora de salida los registra Distribución.")
                hs = (f.get("hora_salida_prog") or "").strip()
                if hs and (len(hs) != 5 or hs[2] != ":"):
                    raise BusinessError("Hora de salida programada inválida (HH:MM).")
                r.hora_salida_prog = hs
                r.costo_transporte = f_float("costo_transporte")
                r.costo_estiba = f_float("costo_estiba")
                from ..services.core import audit
                audit(u, "RUTA_COSTOS", "Route", r.id, {"hora_salida_prog": hs, "costo_transporte": r.costo_transporte,
                                                        "costo_estiba": r.costo_estiba})
        elif acc in ("externo_ok", "externo_no"):
            fn = lambda: dsvc.validate_external(r, u, acc == "externo_ok", f.get("comentario", ""))  # noqa: E731
        elif acc == "trafico":
            from ..services import maps
            if "distribucion.ver" not in g.perms:
                abort(403)
            def fn():
                res = maps.check_traffic(r, u)
                if res is None:
                    raise BusinessError("El servicio de mapas no está configurado (GOOGLE_MAPS_API_KEY): no hay datos de tráfico.")
                return res
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
    from ..services import maps
    return render_template("route_detail.html", r=r, vehicles=vehicles, drivers=drivers, others=others,
                           gmaps=maps.gmaps_link(r), embed=maps.embed_url(r), estimado=maps.estimate(r) if not maps.api_key() else None,
                           maps_ok=bool(maps.api_key()),
                           checklist=dsvc.CHECKLIST, expected=dsvc.expected_lines(r), tipos=INCIDENT_TYPES,
                           grupos=__import__("app.catalogs", fromlist=["x"]).INCIDENT_GROUPS,
                           subtipos=__import__("app.catalogs", fromlist=["x"]).INCIDENT_SUBTYPES,
                           preguia=dsp.preguia(r), etapas=dsp.ETAPAS_FOTO, certs=certs,
                           faltan=dsp.missing_documents(r) if r.estado == "CONFIRMADA" else [],
                           billing=dsp.billing_status, vb_req=dsp.required_exit_approvals(), vb_label=dsp.VB_LABEL,
                           horas_seg=dsvc.HORAS_SEGURIDAD)


@bp.route("/ruta/<int:rid>/folio")
@perm_required("distribucion.ver")
def folio(rid):
    """Pre-guía / guía del sistema y folio de documentos por pedido (imprimible)."""
    r = db().get(Route, rid) or abort(404)
    certs = {st.id: list(db().execute(select(Certificate).where(Certificate.order_id == st.order_id,
                                                                  Certificate.estado != "ANULADO")).scalars()) for st in r.stops}
    from ..models import Product
    from ..services.core import param
    pg = dsp.preguia(r)
    ov = request.args.get("ov", type=int)
    if ov:  # una sola OV (expediente de la OV)
        pg = [x for x in pg if x["order"].id == ov]

    def peso_de(it):
        p = db().get(Product, it["codigo"])
        if p is None:
            return None
        if (p.um or "").upper().startswith("K"):
            return it["cantidad"]
        return it["cantidad"] * p.peso_kg if p.peso_kg else None
    return render_template("folio.html", r=r, preguia=pg, certs=certs, empresa=param("empresa_razon_social", ""),
                           ruc=param("empresa_ruc", ""), tipo=request.args.get("tipo", "folio"), peso_de=peso_de)


@bp.route("/seguridad/llegadas", methods=["GET", "POST"])
@perm_required("seguridad.llegadas")
def arrivals():
    """Seguridad: cuadro de llegadas de compras nacionales e importaciones (obs. demo v0.7)."""
    from ..services import security as ssvc
    if request.method == "POST":
        f = request.form

        def _do():
            foto = dsvc.save_upload(request.files.get("foto"), current_app.config["UPLOAD_DIR"], f"llegada_{f.get('tipo')}_{f.get('id')}")
            return ssvc.register_arrival_check(g.user, f.get("tipo"), int(f.get("id") or 0), f_float("cantidad"),
                                               f.get("conforme") == "1", f.get("motivo", ""), foto, f.get("placa", ""),
                                               f.get("chofer", ""), f.get("hora", ""))
        return act(_do, lambda c: "Llegada conforme registrada." if c.conforme else "Incidente registrado y notificado.",
                   url_for("dist.arrivals"))
    return render_template("arrivals.html", filas=ssvc.arrivals(int(request.args.get("dias") or 7)))


@bp.route("/incidencias", methods=["GET", "POST"])
@perm_required("distribucion.ver")
def incidents():
    from datetime import date as _date
    if request.method == "POST":
        f = request.form
        o = db().execute(select(SalesOrder).where(SalesOrder.numero == f.get("ov", "").strip())).scalars().first()
        lineas = []
        if o is not None and f.get("entrega") == "PARCIAL":
            for l in o.lines:
                dev = f_float(f"dev_{l.id}")
                if dev:
                    lineas.append({"line_id": l.id, "devuelto": dev, "motivo": f.get(f"mot_{l.id}", "").strip()})
        return act(lambda: dsvc.register_incident(g.user, f.get("tipo"), f.get("descripcion", ""), order=o,
                                                  cantidad=f_float("cantidad"), entrega=f.get("entrega", ""), lineas=lineas),
                   "Incidencia registrada y alertada.", url_for("dist.incidents"))
    try:
        dia = _date.fromisoformat(request.args.get("fecha") or _date.today().isoformat())
    except ValueError:
        dia = _date.today()
    paradas = dsvc.todays_orders(dia)
    rows = list(db().execute(select(Incident).order_by(Incident.id.desc())).scalars())
    from ..catalogs import INCIDENT_GROUPS, INCIDENT_SUBTYPES
    from ..services.catalogs_helpers import incident_group_name, incident_type_name
    return render_template("incidents.html", rows=rows, tipos=INCIDENT_TYPES, grupos=INCIDENT_GROUPS, subtipos=INCIDENT_SUBTYPES,
                           nombre=incident_type_name, grupo_nombre=incident_group_name, paradas=paradas, dia=dia)


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


# ------------------- seguimiento de flota (obs. demo v0.6) -------------------
@bp.route("/flota/seguimiento")
@perm_required("flota.ver", "distribucion.flota")
def fleet_tracking():
    from ..services import fleet
    vehs = list(db().execute(select(Vehicle).order_by(Vehicle.propio.desc(), Vehicle.placa)).scalars())
    return render_template("fleet_tracking.html", filas=[(v, fleet.status(v)) for v in vehs], tipos=fleet.TIPOS_DOC)


@bp.route("/flota/vehiculo/<int:vid>", methods=["GET", "POST"])
@perm_required("flota.ver", "distribucion.flota")
def vehicle_detail(vid):
    from ..models import VehicleDocument, VehicleMaintenance
    from ..services import fleet
    v = db().get(Vehicle, vid) or abort(404)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        up = current_app.config["UPLOAD_DIR"]
        fn = {
            "documento": lambda: fleet.add_document(g.user, v, f.get("tipo"), f.get("numero", ""), f_date("fecha"), f_date("vencimiento"),
                                                    f_float("monto"), f.get("estado", ""), f.get("observacion", ""),
                                                    dsvc.save_upload(request.files.get("archivo"), up, f"veh{v.id}_doc"), f.get("hora", "")),
            "combustible": lambda: fleet.add_fuel(g.user, v, f_date("fecha"), f_float("km", True), f_float("galones", True),
                                                  f_float("monto")),
            "mantenimiento": lambda: fleet.add_maintenance(g.user, v, f_date("fecha"), f.get("tipo", "PREVENTIVO"), f_float("km"),
                                                           f.get("descripcion", ""), f_float("costo"), f_float("proximo_km"),
                                                           f_date("proxima_fecha")),
        }.get(acc) or abort(400)
        return act(fn, "Registro guardado.", url_for("dist.vehicle_detail", vid=vid))
    docs = list(db().execute(select(VehicleDocument).where(VehicleDocument.vehicle_id == v.id)
                             .order_by(VehicleDocument.id.desc())).scalars())
    mants = list(db().execute(select(VehicleMaintenance).where(VehicleMaintenance.vehicle_id == v.id)
                              .order_by(VehicleMaintenance.fecha.desc())).scalars())
    consulta = None
    if request.args.get("fecha"):
        consulta = fleet.who_had(v, f_date("fecha"))
    return render_template("vehicle_detail.html", v=v, st=fleet.status(v), docs=docs, mants=mants, tipos=fleet.TIPOS_DOC,
                           consulta=consulta, fecha_consulta=request.args.get("fecha", ""),
                           rutas=list(db().execute(select(Route).where(Route.vehicle_id == v.id).order_by(Route.fecha.desc())
                                                   .limit(15)).scalars()))
