"""Vistas de Distribución de la ronda V12 (29-oct-2026): checklist vehicular, flujo de incidencias, pre-guías,
transporte tercero y presupuesto del área. Se registran en el blueprint de Distribución."""
import os
from datetime import date

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import db
from ..models import AreaBudget, BudgetLine, Breakdown, Customer, Incident, Route, SalesOrder, ThirdPartyTransport, \
    VehicleChecklist, VehicleMaintenance
from ..services import budget as bsvc
from ..services import guides as gsvc
from ..services import incidents_flow as fl
from ..services import third_party as tp
from ..services import vehicle_checklist as vc
from ..services.core import BusinessError, has_perm, param
from ..services.distribution import save_upload
from .common import act, f_date, f_float, paginate, perm_required
from .distribucion import bp


def _up(campo, prefijo):
    return save_upload(request.files.get(campo), current_app.config["UPLOAD_DIR"], prefijo)


# ------------------------------------------------------------------ checklist vehicular
@bp.route("/checklists")
@perm_required("checklist.ver", "distribucion.checklist_validar")
def checklists():
    """V18: todos los checklists vehiculares (Distribución, Jefe de Logística, Jefatura de Operaciones)."""
    from datetime import date as _d, timedelta as _td
    desde = f_date("desde") or (_d.today() - _td(days=7))
    q = select(VehicleChecklist).where(VehicleChecklist.fecha >= desde).order_by(VehicleChecklist.id.desc())
    if request.args.get("estado"):
        q = q.where(VehicleChecklist.estado == request.args["estado"])
    # simulación integral (07-nov-2026): el registro de cada conductor y de cada vehículo
    if request.args.get("conductor"):
        q = q.where(VehicleChecklist.driver_id == int(request.args["conductor"]))
    if request.args.get("vehiculo"):
        q = q.where(VehicleChecklist.vehicle_id == int(request.args["vehiculo"]))
    from ..models import Driver, Vehicle
    conductores = list(db().execute(select(Driver).order_by(Driver.nombre)).scalars())
    vehiculos = list(db().execute(select(Vehicle).order_by(Vehicle.placa)).scalars())
    return render_template("checklists.html", lista=paginate(q, 20), desde=desde,
                           items=dict((c, i) for c, _, i, _ in vc.items()), f=request.args, conductores=conductores,
                           vehiculos=vehiculos)


@bp.route("/ruta/<int:rid>/checklist", methods=["GET", "POST"])
@perm_required("distribucion.ver", "distribucion.checklist", "distribucion.checklist_validar", "checklist.ver")
def checklist(rid):
    r = db().get(Route, rid) or abort(404)
    back = url_for("dist.checklist", rid=rid)
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "validar":
            c = db().get(VehicleChecklist, int(f.get("cid") or 0)) or abort(404)
            return act(lambda: vc.validate(g.user, c, f.get("aprobar") == "1", f.get("km"), f.get("nota", "")),
                       "Checklist revisado por Seguridad; kilometraje registrado.", back)
        valores = {k[2:]: v for k, v in f.items() if k.startswith("i_")}
        return act(lambda: vc.register(g.user, r, f.get("momento"), valores, f.get("km"), f.get("observaciones", ""),
                                       f.get("marcas", "")),
                   lambda c: "Checklist registrado." + (" Puntos NO NEGOCIABLES en mal estado: el vehículo no puede salir."
                                                        if c.nn_fallidos else ""), back)
    lista = list(db().execute(select(VehicleChecklist).where(VehicleChecklist.route_id == rid)
                              .order_by(VehicleChecklist.id.desc())).scalars())
    from ..catalogs import IMAGENES_CHECKLIST, PARTES_VEHICULO
    clave = (r.vehicle.imagen_checklist if r.vehicle else "") or _imagen_por_tipo(r.vehicle)
    return render_template("checklist.html", r=r, lista=lista, zonas=vc.zonas(), items=dict((c, i) for c, _, i, _ in vc.items()),
                           pend_paso2=vc.pending_part2(r), puede_salir=vc.can_depart(r),
                           imagenes=IMAGENES_CHECKLIST.get(clave, (None, []))[1], partes=PARTES_VEHICULO)


def _imagen_por_tipo(v):
    """V22: imagen del checklist según el tipo de unidad cuando no se eligió una en la flota."""
    if v is None:
        return ""
    t = f"{v.tipo_unidad} {v.descripcion}".upper()
    if "TRACTO" in t or "SEMI" in t:
        return "TRACTO"
    if "CAMIONETA" in t or "PICK" in t or "SUV" in t:
        return "CAMIONETA"
    if "LIVIAN" in t or "FURG" in t or "PANEL" in t:
        return "FURGON"
    if "CAMI" in t or "TN" in t:
        return "CAMION"
    return ""


# ------------------------------------------------------------------ incidencia: paso 2, flujo y modificaciones
@bp.route("/incidencias/<int:iid>", methods=["GET", "POST"])
@perm_required("distribucion.ver", "stock.cambiar_estado", "finanzas.gestionar", "distribucion.incidencia_editar", "calidad.ver")
def incident_detail(iid):
    i = db().get(Incident, iid) or abort(404)
    back = url_for("dist.incident_detail", iid=iid)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "paso2":
            lineas = [{"producto": p, "cantidad": q} for p, q in zip(f.getlist("producto"), f.getlist("cantidad")) if (p or "").strip()]
            return act(lambda: fl.register_part2(g.user, i, lineas, f.get("observacion", "")),
                       "Paso 2 registrado: se avisó a Almacén para confirmar lo devuelto.", back)
        if acc == "almacen":
            return act(lambda: fl.warehouse_confirm(g.user, i, f.get("conforme") == "1", f.get("observacion", "")),
                       "Retorno confirmado por Almacén.", back)
        if acc == "finanzas":
            return act(lambda: fl.finance_validate(g.user, i, f.get("procede") == "1", f.get("observacion", "")),
                       "Validación de Finanzas registrada.", back)
        if acc == "solicitud":
            return act(lambda: fl.request_return(g.user, i, f.get("numero", ""), f.get("observacion", "")),
                       "Solicitud registrada; incidencia cerrada.", back)
        if acc == "editar":
            cambios = {k: f.get(k) for k in fl.EDITABLES}
            return act(lambda: fl.edit(g.user, i, cambios, f.get("motivo", "")), "Incidencia modificada (queda registro).", back)
        abort(400)
    from ..catalogs import INCIDENT_TYPES
    from ..services.catalogs_helpers import incident_type_name
    return render_template("incident_detail.html", i=i, factura=fl.invoice_of(i), necesita=fl.needs_part2(i),
                           nombre=incident_type_name, tipos=INCIDENT_TYPES)


# ------------------------------------------------------------------ pre-guías
@bp.route("/preguias", methods=["GET", "POST"])
@perm_required("distribucion.ver", "distribucion.guia_modificar")
def preguias():
    back = url_for("dist.preguias")
    if request.method == "POST":
        f = request.form
        o = db().get(SalesOrder, int(f.get("oid") or 0)) or abort(404)
        if f.get("accion") == "fecha":
            return act(lambda: gsvc.change_date(g.user, o, f_date("fecha", True), f.get("motivo", "")),
                       "Fecha de la guía cambiada (se envía a SAP si ya está registrada).", back)
        return act(lambda: gsvc.validate(g.user, o, f.get("aprobar") == "1", f.get("observacion", ""), f_date("fecha")),
                   lambda pg: "Pre-guía validada." + (" Registrada en SAP." if (pg.get("sap") or {}).get("estado") == "ENVIADA" else
                                                      " Se registrará en SAP cuando la conexión esté disponible.")
                   if pg.get("estado") == "VALIDADA" else "Pre-guía observada.", back)
    pend = gsvc.pending_validation()
    recientes = [o for o in db().execute(select(SalesOrder).order_by(SalesOrder.id.desc()).limit(300)).scalars()
                 if (o.preguia or {}).get("estado") == "VALIDADA"][:40]
    # V18: indicador de cambios en guías emitidas (Jefe de Logística, Jefe de Operaciones y gerencias)
    indicador = gsvc.change_rate(f_date("desde"), f_date("hasta")) if g.user.role_code in INDICADOR_GUIAS_ROLES or \
        has_perm(g.user, "vista.total") else None
    return render_template("preguias.html", pend=pend, recientes=recientes, corte=param("hora_corte_rutas", "15:00"),
                           indicador=indicador, dur=gsvc.durations)


INDICADOR_GUIAS_ROLES = ("JEFE_LOGISTICA", "JEFE_OPERACIONES", "GERENTE_GENERAL", "GERENTE_GENERAL_ADJUNTO",
                         "COORD_DISTRIBUCION")


@bp.route("/preguia/<int:oid>", methods=["GET", "POST"])
@perm_required("distribucion.ver", "distribucion.guia_modificar")
def preguia_detail(oid):
    """V18: revisión de la pre-guía como el precertificado de Calidad: todos los campos a la vista y editables; al
    aprobar se emite la guía (SAP) y queda imprimible. Emitida, solo se cambian fecha, cantidades o presentación con el
    lápiz, con motivo y rastro. Se llega igual desde la alerta o desde Pre-guías: lo aprobado en un lugar se ve en todos."""
    o = db().get(SalesOrder, oid) or abort(404)
    if not o.preguia:
        abort(404)
    back = url_for("dist.preguia_detail", oid=oid)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion", "guardar")
        if acc == "lapiz":
            return act(lambda: gsvc.edit_emitted(g.user, o, f.get("campo", ""), f.get("motivo", ""), f.get("idx", type=int),
                                                 f.get("valor")), "Cambio guardado con su rastro.", back)
        if acc in ("aprobar", "observar"):  # como el precertificado: lo revisado se guarda aunque la aprobación falle
            try:
                gsvc.review(g.user, o, f)
                db().commit()
            except BusinessError as e:
                db().rollback()
                flash(str(e), "error")
                return redirect(back)
        if acc == "observar":
            return act(lambda: gsvc.validate(g.user, o, False, f.get("observacion", "")), "Pre-guía observada.", back)
        if acc == "aprobar":
            return act(lambda: gsvc.validate(g.user, o, True, f.get("observacion", "")), lambda pg: "Pre-guía aprobada: guía emitida" + (f" (SAP N.° {pg['sap'].get('docnum')})."
                                                                              if (pg.get("sap") or {}).get("docnum") else
                                                                              "; se registrará en SAP cuando la conexión esté disponible."), back)
        return act(lambda: gsvc.review(g.user, o, f), "Revisión guardada.", back)
    if "distribucion.guia_modificar" in g.perms and request.args.get("imprimir") != "1":
        gsvc.start_review(g.user, o)
        db().commit()
    pg = o.preguia
    st = gsvc._stop(o)
    r = st.route if st is not None else None
    fecha = date.fromisoformat(pg["fecha_guia"]) if pg.get("fecha_guia") else date.today()
    items = [dict(x, cantidad=x.get("preparado"),
                  lotes=[dict(l, fp=_d(l.get("fp")), fv=_d(l.get("fv"))) for l in x.get("lotes") or []]) for x in pg.get("items") or []]
    doc_g = {"stop": st or {"guia_numero": (pg.get("sap") or {}).get("docnum") or ""}, "order": o, "items": items,
             "almacen": "", "motivo": pg.get("motivo") or "Venta"}
    doc_r = {"fecha": fecha, "vehicle": r.vehicle if r else None, "driver": r.driver if r else None}

    def peso_de(it):
        from ..models import Product
        p = db().get(Product, it["codigo"])
        if p is None or it.get("cantidad") is None:
            return None
        return it["cantidad"] if (p.um or "").upper().startswith("K") else (it["cantidad"] * p.peso_kg if p.peso_kg else None)
    editable = pg.get("estado") in ("POR_VALIDAR", "OBSERVADA") and "distribucion.guia_modificar" in g.perms
    return render_template("preguia_detail.html", o=o, pg=pg, editable=editable, dur=gsvc.durations(pg), doc_g=doc_g,
                           doc_r=doc_r, peso_de=peso_de, ruc=param("empresa_ruc", ""),
                           print_mode=request.args.get("imprimir") == "1",
                           lapiz="distribucion.guia_modificar" in g.perms and pg.get("estado") == "VALIDADA")


def _d(v):
    try:
        return date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ transporte tercero
@bp.route("/terceros", methods=["GET", "POST"])
@perm_required("terceros.ver", "terceros.registrar", "terceros.aprobar", "terceros.finanzas", "terceros.oc")
def terceros():
    back = url_for("dist.terceros")
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "tarifario":
            filas = [{"id": i, "proveedor": p, "tipo_vehiculo": tv, "origen": o, "destino": d, "precio": pr, "vigente": v}
                     for i, p, tv, o, d, pr, v in zip(f.getlist("id"), f.getlist("proveedor"), f.getlist("tipo_vehiculo"),
                                                       f.getlist("origen"), f.getlist("destino"), f.getlist("precio"),
                                                       f.getlist("vigente"))]
            return act(lambda: tp.save_rates(g.user, filas, f.get("motivo", "")),
                       lambda c: f"Tarifario actualizado ({len(c)} cambio(s)); se avisó a Operaciones y Finanzas.", back)
        if f.get("accion") == "incidencia":
            sv = db().get(ThirdPartyTransport, int(f["servicio_id"])) if (f.get("servicio_id") or "").isdigit() else None
            return act(lambda: tp.register_incident(g.user, f.get("proveedor", ""), f.get("tipo", ""), f.get("descripcion", ""),
                                                    sv, f_date("fecha")), "Incidencia del proveedor registrada.", back)
        return act(lambda: tp.request_service(g.user, f), lambda t: f"Servicio #{t.id} registrado: pendiente de aprobación de "
                   "Gerencia de Operaciones.", back, redirect_fn=lambda t: url_for("dist.tercero", tid=t.id))
    from ..models import TransportRate
    return render_template("terceros.html", servicios=tp.services_for(g.user), indicadores=tp.provider_indicators(),
                           tarifas=list(db().execute(select(TransportRate).order_by(TransportRate.destino)).scalars()),
                           clientes=list(db().execute(select(Customer).where(Customer.es_prospecto.is_(False))
                                                      .order_by(Customer.nombre)).scalars()), motivos=tp.MOTIVOS)


@bp.route("/terceros/<int:tid>", methods=["GET", "POST"])
@perm_required("terceros.ver", "terceros.registrar", "terceros.aprobar", "terceros.finanzas", "terceros.oc")
def tercero(tid):
    t = db().get(ThirdPartyTransport, tid) or abort(404)
    back = url_for("dist.tercero", tid=tid)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "aprobar":
            return act(lambda: tp.approve(g.user, t, f.get("aprobar") == "1", f.get("comentario", "")), "Decisión registrada.", back)
        if acc == "factura":
            return act(lambda: tp.register_invoice(g.user, t, f, _up("archivo", f"terc{t.id}_fact")),
                       "Factura registrada; Compras recibió la tarea de la OC.", back)
        if acc == "guia":
            return act(lambda: tp.fetch_guide(g.user, t, f.get("guia_numero", "").strip().upper()), "Guía traída al expediente.", back)
        if acc == "validar_guia":
            return act(lambda: tp.validate_guide(g.user, t, f.get("correcta") == "1", f_date("fecha")), "Guía revisada.", back)
        if acc == "oc":
            return act(lambda: tp.register_po(g.user, t, f.get("oc_numero", ""), _up("archivo", f"terc{t.id}_oc")),
                       "OC registrada.", back)
        if acc == "validar":
            return act(lambda: tp.finance_validate(g.user, t, f.get("observacion", "")), "Expediente validado.", back)
        if acc == "programar":
            return act(lambda: tp.schedule_payment(g.user, t, f_date("fecha", True), f.get("monto"), f.get("observacion", "")),
                       "Pago programado.", back)
        if acc == "pagar":
            return act(lambda: tp.register_payment(g.user, t, f.get("n"), _up("comprobante", f"terc{t.id}_pago"),
                                                   f_date("fecha_pago"), f.get("observacion", "")), "Pago registrado.", back)
        abort(400)
    return render_template("tercero_detail.html", t=t, exp=tp.expediente(t), tipos=param("terceros_tipos_servicio", {}) or {},
                           centros=param("terceros_centros_costo", []) or [], igv=float(param("igv_pct", 18) or 18))


# ------------------------------------------------------------------ presupuesto del área
@bp.route("/presupuesto", methods=["GET", "POST"])
@perm_required("presupuesto.ver", "presupuesto.registrar", "presupuesto.aprobar")
def presupuesto():
    anio = int(request.args.get("anio") or date.today().year)
    back = url_for("dist.presupuesto", anio=anio)
    b = bsvc.get("Distribución", anio)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        if acc == "excel":
            def _x():
                arch = request.files.get("archivo")
                if not arch or not arch.filename.lower().endswith((".xlsx", ".xlsm")):
                    raise BusinessError("Suba el presupuesto en Excel (modelo de Logística).")
                up = current_app.config["UPLOAD_DIR"]
                os.makedirs(up, exist_ok=True)
                path = os.path.join(up, f"presupuesto_{os.urandom(4).hex()}.xlsx")
                arch.save(path)
                try:
                    return bsvc.import_excel(g.user, path, anio)
                finally:
                    os.remove(path)  # puede contener datos del personal: no se conserva
            return act(_x, lambda x: f"Presupuesto {x.anio} cargado: {len(x.lines)} partidas.", back)
        if b is None and acc in ("partida",):
            b = bsvc.get("Distribución", anio, True, g.user)
        if b is None:
            abort(400)
        if acc == "partida":
            line = db().get(BudgetLine, int(f["lid"])) if (f.get("lid") or "").isdigit() else None
            return act(lambda: bsvc.save_line(g.user, b, f, line), "Partida guardada.", back)
        if acc == "real":
            line = db().get(BudgetLine, int(f.get("lid") or 0)) or abort(404)
            return act(lambda: bsvc.register_real(g.user, line, int(f.get("mes")), f_float("monto", True)), "Gasto real registrado.", back)
        if acc == "enviar":
            return act(lambda: bsvc.submit(g.user, b), "Presupuesto enviado a Administración y Finanzas.", back)
        if acc == "decidir":
            return act(lambda: bsvc.decide(g.user, b, f.get("aprobar") == "1", f.get("comentario", "")), "Decisión registrada.", back)
        abort(400)
    c = bsvc.consumption(b) if b else None
    return render_template("presupuesto.html", pres=b, c=c, anio=anio, umbral=float(param("presupuesto_alerta_pct", 75) or 75))


# ------------------------------------------------------------------ mantenimiento: informe, factura e incidencia con el taller
@bp.route("/mantenimiento/<tipo>/<int:mid>", methods=["POST"])
@perm_required("mantenimiento.flota", "distribucion.flota", "mantenimiento.factura")
def maintenance_docs(tipo, mid):
    from ..services import maintenance as mt
    obj = db().get(VehicleMaintenance if tipo == "preventivo" else Breakdown, mid) or abort(404)
    f = request.form
    back = request.referrer or url_for("dist.fleet")
    if f.get("accion") == "incidencia":
        return act(lambda: mt.workshop_incident(g.user, obj, f.get("motivo", ""), f.get("dias_fuera"), f.get("detalle", ""),
                                                f.get("taller", "")), "Incidencia con el taller registrada.", back)
    return act(lambda: mt.attach_document(g.user, obj, f.get("tipo_doc"), f.get("numero", ""), _up("archivo", f"mant{mid}")),
               "Documento adjuntado.", back)
