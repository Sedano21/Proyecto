"""Vistas generales: acceso, tablero, alertas, configuración, usuarios/permisos, auditoría y exportación."""
import io
import os
import time
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, send_file, send_from_directory,
                   session, url_for)
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import db
from ..models import (Alert, AlertType, AuditLog, Customer, EmailOutbox, GGAlertPreference, ImportPhaseTemplate,
                      LeadTime, Param, ParamHistory, Permission, Product, ProductionLine, PurchaseVariationRule, Role,
                      RolePermission, User, Warehouse)
from ..services import alerts as alert_svc
from ..services import prices as prices_svc
from ..services.core import BusinessError, audit, coerce_param, set_param
from .common import act, f_date, f_float, install, login_required, perm_required

bp = Blueprint("main", __name__)
_FAILS = {}


def register_views(app):
    install(app)
    from . import calidad, comercial, compras, distribucion, produccion, almacen
    from . import comercial_mb2, produccion_mb2  # noqa: F401  (rutas de la ronda 23-oct-2026 en los mismos blueprints)
    app.register_blueprint(bp)
    app.register_blueprint(comercial.bp)
    app.register_blueprint(almacen.bp)
    app.register_blueprint(produccion.bp)
    app.register_blueprint(calidad.bp)
    app.register_blueprint(compras.bp)
    app.register_blueprint(distribucion.bp)
    from . import finanzas, m365, informes, marcha
    app.register_blueprint(finanzas.bp)
    app.register_blueprint(m365.bp)
    app.register_blueprint(informes.bp)
    app.register_blueprint(marcha.bp)
    from . import mantenimiento, suministro
    app.register_blueprint(mantenimiento.bp)
    app.register_blueprint(suministro.bp)

    @app.errorhandler(403)
    def _403(e):
        return render_template("error.html", code=403, msg="Su rol no tiene permiso para esta función."), 403

    @app.errorhandler(404)
    def _404(e):
        return render_template("error.html", code=404, msg="No encontrado."), 404

    @app.errorhandler(400)
    def _400(e):
        return render_template("error.html", code=400, msg=str(getattr(e, "description", e))), 400


# ------------------------------- acceso ------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    from .m365 import enabled as m365_enabled
    if request.method == "POST":
        if os.environ.get("LOCAL_LOGIN", "1") == "0":
            abort(403)  # solo Microsoft 365
        username = (request.form.get("username") or "").strip().lower()
        u = db().execute(select(User).where(User.username == username)).scalars().first()
        ahora = datetime.now()
        if u is not None and u.bloqueado_hasta and u.bloqueado_hasta > ahora:
            audit(None, "LOGIN_BLOQUEADO", "User", username)
            db().commit()
            flash("Usuario bloqueado por intentos fallidos. " + ("Pida a Sistemas que lo desbloquee."
                  if u.bloqueado_hasta.year >= 9000 else f"Intente después de las {u.bloqueado_hasta:%H:%M}."), "error")
            return render_template("login.html", local_login=True)
        fails = [t for t in _FAILS.get(username, []) if time.time() - t < 300]  # usuarios inexistentes
        if u is None and len(fails) >= 5:
            flash("Demasiados intentos. Espere unos minutos.", "error")
            return render_template("login.html", local_login=True)
        if u and u.activo and check_password_hash(u.password_hash, request.form.get("password") or ""):
            tok = session.get("_csrf")
            session.clear()
            session["uid"] = u.id
            if tok:
                session["_csrf"] = tok
            u.intentos_fallidos, u.bloqueado_hasta = 0, None
            _FAILS.pop(username, None)
            audit(u, "LOGIN", "User", u.id)
            db().commit()
            nxt = request.args.get("next") or url_for("main.dashboard")
            seguro = nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt
            return redirect(nxt if seguro else url_for("main.dashboard"))
        if u is not None:  # marcha blanca: bloqueo tras N intentos fallidos seguidos
            from ..services.core import param
            u.intentos_fallidos = (u.intentos_fallidos or 0) + 1
            limite = int(param("clave_intentos_bloqueo", 5) or 5)
            if u.intentos_fallidos >= limite:
                mins = int(param("clave_minutos_bloqueo", 15) or 0)
                u.bloqueado_hasta = ahora + timedelta(minutes=mins) if mins else datetime(9999, 1, 1)
                u.intentos_fallidos = 0
                audit(None, "USUARIO_BLOQUEADO", "User", username, {"intentos": limite, "minutos": mins or "hasta desbloqueo"})
        else:
            fails.append(time.time())
            _FAILS[username] = fails
        audit(None, "LOGIN_FALLIDO", "User", username)
        db().commit()
        flash("Usuario o contraseña incorrectos.", "error")
    demo_users = []
    if g.get("user") is None and _demo():
        demo_users = list(db().execute(select(User).order_by(User.role_code)).scalars())
    return render_template("login.html", demo_users=demo_users, m365=m365_enabled(),
                           local_login=os.environ.get("LOCAL_LOGIN", "1") != "0")


def _demo():
    from flask import current_app
    return current_app.config.get("DEMO_MODE")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


def check_new_password(user, nueva):
    """Política de contraseñas (marcha blanca): longitud mínima configurable y distinta del usuario."""
    from ..services.core import param
    minimo = int(param("clave_longitud_minima", 8) or 8)
    if len(nueva or "") < minimo:
        raise BusinessError(f"La contraseña debe tener al menos {minimo} caracteres.")
    if user is not None and (nueva or "").lower() == user.username.lower():
        raise BusinessError("La contraseña no puede ser igual al usuario.")


@bp.route("/cambiar-clave", methods=["GET", "POST"])
@login_required
def change_password():
    from ..services.core import param
    if request.method == "POST":
        def _do():
            if not check_password_hash(g.user.password_hash, request.form.get("actual") or ""):
                raise BusinessError("La contraseña actual no es correcta.")
            nueva = request.form.get("nueva") or ""
            if nueva != (request.form.get("repetir") or ""):
                raise BusinessError("La nueva contraseña y su confirmación no coinciden.")
            check_new_password(g.user, nueva)
            if check_password_hash(g.user.password_hash, nueva):
                raise BusinessError("La nueva contraseña debe ser distinta de la actual.")
            g.user.password_hash = generate_password_hash(nueva)
            g.user.debe_cambiar_clave = False
            g.user.clave_ts = datetime.now()
            audit(g.user, "CLAVE_CAMBIADA", "User", g.user.id)
        nxt = request.args.get("next") or ""
        return act(_do, "Contraseña actualizada.", nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("main.dashboard"))
    dias = int(param("clave_dias_vigencia", 0) or 0)
    vencida = bool(dias and (g.user.clave_ts is None or datetime.now() - g.user.clave_ts > timedelta(days=dias)))
    return render_template("change_password.html", minimo=int(param("clave_longitud_minima", 8) or 8), dias=dias,
                           obligatorio=g.user.debe_cambiar_clave or vencida, vencida=vencida and not g.user.debe_cambiar_clave)


@bp.route("/aviso-datos", methods=["GET", "POST"])
@login_required
def privacy_notice():
    """Aviso de datos personales (Ley 29733) y responsabilidad por el usuario y la contraseña: se acepta al primer
    ingreso y cada vez que cambia su versión."""
    from ..services.core import param
    version = param("aviso_datos_version", "") or ""
    if request.method == "POST":
        if request.form.get("accion") == "rechazar":
            audit(g.user, "AVISO_DATOS_RECHAZADO", "User", g.user.username, {"version": version})
            db().commit()
            session.clear()
            flash("Para usar el sistema debe aceptar el aviso de datos personales y la responsabilidad por su usuario.", "error")
            return redirect(url_for("main.login"))
        if not (request.form.get("acepto_datos") and request.form.get("acepto_responsabilidad")):
            flash("Marque ambas casillas para continuar.", "error")
            return redirect(url_for("main.privacy_notice", next=request.args.get("next")))
        g.user.aviso_aceptado = {"version": version, "ts": datetime.now().isoformat(timespec="seconds"),
                                 "ip": request.headers.get("X-Forwarded-For", request.remote_addr or "")}
        audit(g.user, "AVISO_DATOS_ACEPTADO", "User", g.user.username, {"version": version})
        db().commit()
        nxt = request.args.get("next") or ""
        return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("main.dashboard"))
    return render_template("privacy_notice.html", texto=param("aviso_datos_texto", "") or "", version=version,
                           aceptado=(g.user.aviso_aceptado or {}))


# ------------------------------- tablero -----------------------------------
@bp.route("/")
@login_required
def dashboard():
    from ..services.kpis import compute
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    k = compute(date.fromisoformat(desde) if desde else None, date.fromisoformat(hasta) if hasta else None) \
        if "dashboard.ver" in g.perms else None
    tareas = alert_svc.my_tasks(g.user)
    ids = {a.id for a in tareas}
    mis = [a for a in alert_svc.inbox(g.user, solo_abiertas=True) if a.id not in ids][:40]
    from ..services.shifts import pending_carryover
    return render_template("dashboard.html", k=k, mis_alertas=mis, tareas=tareas, desde=desde or "", hasta=hasta or "",
                           estado_txt=alert_svc.ESTADO_TXT, arrastre=pending_carryover(g.user))


@bp.route("/verificaciones", methods=["POST"])
@perm_required("alertas.configurar", "config.editar", "dashboard.ver")
def run_checks():
    from ..services.scheduler import run_checks as rc
    return act(lambda: rc(g.user), lambda r: f"Verificaciones ejecutadas: {r}", request.referrer or url_for("main.dashboard"))


# ------------------------------- alertas -----------------------------------
@bp.route("/alertas")
@login_required
def alerts():
    f = {k: request.args.get(k) or None for k in ("estado", "area", "prioridad", "grupo", "type_code")}
    tipos = alert_svc.visible_types(g.user)
    codes = {t.code for t in tipos}
    if f["type_code"] and f["type_code"] not in codes:
        f["type_code"] = None
    rows = alert_svc.inbox(g.user, **f)  # solo los tipos de su área o que se comunican con ella
    naturaleza = request.args.get("naturaleza") or ""
    if naturaleza in ("TAREA", "INFORMATIVA"):
        rows = [a for a in rows if alert_svc.nature_for(g.user, a) == naturaleza]
    agrupar = request.args.get("agrupar")
    grupos = {}
    if agrupar:
        for a in rows:
            key = (a.area if agrupar == "area" else a.type.grupo if agrupar == "grupo" else a.type.nombre, a.prioridad)
            grupos.setdefault(key, []).append(a)
        grupos = dict(sorted(grupos.items(), key=lambda kv: (alert_svc.PRIORIDAD_ORDEN.get(kv[0][1], 9), kv[0][0])))
    return render_template("alerts.html", rows=rows, f=f, tipos=tipos, agrupar=agrupar, grupos=grupos,
                           areas=sorted({t.area for t in tipos}), grupos_tipo=sorted({t.grupo for t in tipos}),
                           estados=alert_svc.ESTADOS, estado_txt=alert_svc.ESTADO_TXT, naturaleza=naturaleza)


@bp.route("/alertas/estado.json")
@login_required
def alerts_status():
    """Estado de alertas para el aviso sonoro: tareas abiertas que el usuario puede accionar, importantes (ALTA) y las
    más recientes visibles. Las importantes suenan distinto y se repiten hasta que se resuelvan (obs. demo v0.7)."""
    from ..services.core import param
    rows = alert_svc.inbox(g.user, solo_abiertas=True)
    tareas = [a for a in rows if alert_svc.can_act(g.user, a)]
    criticas = [a for a in tareas if a.prioridad == "ALTA"]
    recientes = sorted(rows, key=lambda a: -a.id)[:5]
    # versión: último movimiento (creación, designación, avance, cierre, comentario) de una alerta que el usuario ve;
    # si cambia, las pantallas de alertas abiertas se actualizan solas (obs. demo v0.7: información siempre certera)
    from ..models import AlertEvent
    desde = request.args.get("desde", type=int) or 0
    version, cambios = 0, []
    for ev in db().execute(select(AlertEvent).order_by(AlertEvent.id.desc()).limit(200)).scalars():
        if ev.alert is None or not alert_svc.can_see(g.user, ev.alert):
            continue
        version = max(version, ev.id)
        if desde and ev.id > desde and ev.user_id and ev.user_id != g.user.id and len(cambios) < 5:
            cambios.append({"alerta": ev.alert_id, "titulo": ev.alert.titulo, "accion": alert_svc.ESTADO_TXT.get(ev.accion, ev.accion),
                            "usuario": ev.user.nombre if ev.user else "Sistema",
                            "url": url_for("main.alert_detail", aid=ev.alert_id)})
    return {"abiertas": len(rows), "tareas": len(tareas), "criticas": len(criticas), "version": version, "cambios": cambios,
            "actualizar_seg": int(param("alerta_actualizacion_seg", 10) or 10),
            "ultimo_id": max([a.id for a in rows], default=0),
            "recientes": [{"id": a.id, "titulo": a.titulo, "prioridad": a.prioridad,
                           "tarea": alert_svc.can_act(g.user, a), "url": url_for("main.alert_detail", aid=a.id)}
                          for a in recientes],
            "consulta_seg": int(param("alerta_sonido_consulta_seg", 60) or 60),
            "repetir_seg": int(param("alerta_sonido_repetir_seg", 120) or 120)}


@bp.route("/alertas/<int:aid>")
@login_required
def alert_detail(aid):
    from ..services import alert_actions
    a = db().get(Alert, aid) or abort(404)
    if not alert_svc.can_see(g.user, a):
        abort(403)
    users, roles = alert_svc.assignable(g.user)
    todos = list(db().execute(select(User).where(User.activo.is_(True)).order_by(User.nombre)).scalars())
    roles_nombre = {r.code: r.nombre for r in db().execute(select(Role)).scalars()}
    entidad_txt = {"SalesOrder": "OV", "Route": "Ruta", "ProductionRequest": "Solicitud de producción", "PurchaseRequest": "Compra",
                   "RepackRequest": "Reempaque", "Transfer": "Traslado", "ImportShipment": "Importación", "Certificate": "Certificado",
                   "StockLot": "Lote", "UploadBatch": "Carga", "PriceListMeta": "Lista de precios", "Liquidation": "Liquidación",
                   "OVChangeRequest": "Solicitud de modificación", "PhysicalCount": "Conteo", "Alert": "Tarea", "Vehicle": "Vehículo",
                   "Customer": "Cliente", "Incident": "Incidencia", "MarketPrice": "Precio de mercado", "Product": "Producto"}
    return render_template("alert_detail.html", a=a, users=users, roles=roles, todos=todos, svc=alert_svc,
                           roles_nombre=roles_nombre, entidad_txt=entidad_txt,
                           puede_decidir=alert_actions.can_decide(a) and alert_actions.user_can_decide(g.user, a),
                           motivo_aprobar=alert_actions.motivo_obligatorio(a),
                           estado_txt=alert_svc.ESTADO_TXT)


@bp.route("/alertas/<int:aid>/<accion>", methods=["POST"])
@login_required
def alert_action(aid, accion):
    from flask import current_app
    from ..models import AlertIncident
    from ..services import alert_actions
    from ..services.distribution import save_upload
    a = db().get(Alert, aid) or abort(404)
    f = request.form

    def _completar():
        ev = save_upload(request.files.get("evidencia"), current_app.config["UPLOAD_DIR"], f"tarea{a.id}")
        alert_svc.complete(a, g.user, f.get("motivo", ""), f.get("accion", ""), ev, f.get("proceso_pendiente", ""))

    def _resolver():
        inc = db().get(AlertIncident, int(f.get("inc_id") or 0))
        if inc is None or inc.alert_id != a.id:
            raise BusinessError("Incidencia no encontrada.")
        alert_svc.resolve_incident(inc, g.user, f.get("resolucion", ""), f.get("acciones", ""))
    fn = {
        "asignar": lambda: alert_svc.assign(a, g.user, f.get("user_id") or None, f.get("comentario", ""), rol=f.get("rol") or None),
        "tomar": lambda: alert_svc.take(a, g.user),
        "atender": lambda: alert_svc.attend(a, g.user, f.get("comentario", "")),
        "comentar": lambda: alert_svc.comment(a, g.user, f.get("comentario", "")),
        "completar": _completar,
        "cerrar": lambda: alert_svc.close(a, g.user, f.get("motivo", ""), f.get("accion", "")),
        "reconocer": lambda: alert_svc.acknowledge(a, g.user, f.get("comentario", "")),
        "incidencia": lambda: alert_svc.open_incident(a, g.user, f.get("situacion", ""), f.get("acciones", ""),
                                                      f.get("responsable_id") or None),
        "resolver": _resolver,
        "iniciar_foto": lambda: alert_svc.start_with_photo(
            a, g.user, save_upload(request.files.get("foto"), current_app.config["UPLOAD_DIR"], f"tarea{a.id}_ini"),
            f.get("comentario", "")),
        "terminar_foto": lambda: alert_svc.finish_with_photo(
            a, g.user, save_upload(request.files.get("foto"), current_app.config["UPLOAD_DIR"], f"tarea{a.id}_fin"),
            f.get("observacion", "")),
        "aprobar": lambda: alert_actions.decide(a, g.user, True, f.get("motivo", "")),
        "desaprobar": lambda: alert_actions.decide(a, g.user, False, f.get("motivo", "")),
    }.get(accion) or abort(404)
    return act(fn, "Alerta actualizada.", url_for("main.alert_detail", aid=aid))


@bp.route("/alertas/configuracion", methods=["GET", "POST"])
@perm_required("alertas.configurar")
def alert_config():
    tipos = list(db().execute(select(AlertType).order_by(AlertType.area, AlertType.code)).scalars())
    roles = list(db().execute(select(Role).order_by(Role.area, Role.nombre)).scalars())
    users = list(db().execute(select(User).order_by(User.nombre)).scalars())
    from ..services import shifts as ssvc
    from ..services.core import param
    if request.method == "POST" and request.form.get("accion") == "plazos":
        return act(lambda: ssvc.save_deadlines(g.user, request.form), "Plazos de atención guardados.",
                   url_for("main.alert_config") + "#plazos")
    if request.method == "POST":
        def _do():
            t = db().get(AlertType, request.form["code"])
            antes = {"roles": t.roles, "prioridad": t.prioridad, "correo": t.enviar_correo, "activo": t.activo,
                     "usuarios": t.usuarios}
            t.roles = request.form.getlist("roles")
            t.usuarios = [int(x) for x in request.form.getlist("usuarios")]
            t.prioridad = request.form.get("prioridad", t.prioridad)
            if request.form.get("naturaleza") in ("TAREA", "INFORMATIVA"):
                antes["naturaleza"] = t.naturaleza
                t.naturaleza = request.form["naturaleza"]
            t.enviar_correo = request.form.get("enviar_correo") == "1"
            t.activo = request.form.get("activo") == "1"
            t.origen_destinatarios = "DEFINIDO" if request.form.get("validado") == "1" else t.origen_destinatarios
            audit(g.user, "ALERTA_TIPO_EDITADO", "AlertType", t.code, {"antes": antes, "despues": {
                "roles": t.roles, "prioridad": t.prioridad, "correo": t.enviar_correo, "activo": t.activo, "usuarios": t.usuarios}})
        return act(_do, "Configuración de alerta guardada.", url_for("main.alert_config") + f"#{request.form['code']}")
    import os
    return render_template("alert_config.html", tipos=tipos, roles=roles, users=users, prioridades=ssvc.PRIORIDADES,
                           areas=sorted({t.area for t in tipos if t.naturaleza == "TAREA"}),
                           plazo_general=param("horas_plazo_tarea", {}) or {},
                           plazo_area=param("minutos_plazo_tarea_por_area", {}) or {},
                           fin_turno=param("minutos_antes_fin_turno_por_area", {}) or {},
                           intervalo=int(os.environ.get("CHECK_INTERVAL_MIN", "1") or 0))


@bp.route("/alertas/preferencias", methods=["GET", "POST"])
@login_required
def gg_prefs():
    if g.user.role_code != "GERENCIA_GENERAL":
        abort(403)
    tipos = list(db().execute(select(AlertType).order_by(AlertType.area, AlertType.nombre)).scalars())
    if request.method == "POST":
        def _do():
            marcados = set(request.form.getlist("directo"))
            for t in tipos:
                p = db().execute(select(GGAlertPreference).where(GGAlertPreference.user_id == g.user.id,
                                                                 GGAlertPreference.type_code == t.code)).scalars().first()
                if p is None:
                    p = GGAlertPreference(user_id=g.user.id, type_code=t.code)
                    db().add(p)
                p.recibir_directo = t.code in marcados
            audit(g.user, "GG_PREFERENCIAS", "User", g.user.id, {"directas": sorted(marcados)})
        return act(_do, "Preferencias guardadas.", url_for("main.gg_prefs"))
    prefs = {p.type_code for p in db().execute(select(GGAlertPreference).where(
        GGAlertPreference.user_id == g.user.id, GGAlertPreference.recibir_directo.is_(True))).scalars()}
    return render_template("gg_prefs.html", tipos=tipos, prefs=prefs)


@bp.route("/correo", methods=["GET", "POST"])
@perm_required("alertas.configurar")
def outbox():
    from ..services.mailer import flush_outbox, smtp_configured
    if request.method == "POST":
        return act(flush_outbox, lambda r: f"Resultado: {r}", url_for("main.outbox"))
    rows = list(db().execute(select(EmailOutbox).order_by(EmailOutbox.id.desc()).limit(300)).scalars())
    return render_template("outbox.html", rows=rows, smtp=smtp_configured())


# ------------------------------- manual de usuario -------------------------
@bp.route("/ayuda")
@login_required
def help():
    """Manual de usuario por rol: el del propio rol; Sistemas y Gerencia General pueden consultar el de cualquier rol."""
    from .. import manual
    rol = request.args.get("rol") or g.user.role_code
    if rol != g.user.role_code and g.user.role_code not in ("SISTEMAS", "GERENCIA_GENERAL"):
        rol = g.user.role_code
    r = db().get(Role, rol) or abort(404)
    return render_template("help.html", m=manual.for_role(r), rol=r,
                           roles=list(db().execute(select(Role).order_by(Role.nombre)).scalars()))


# ------------------------------- configuración -----------------------------
@bp.route("/configuracion")
@perm_required("config.ver")
def config():
    s = db()
    from .. import catalogs
    vigentes = {x[0] for x in catalogs.PARAMS}  # los parámetros retirados del catálogo no se muestran (no se borran)
    params = [p for p in s.execute(select(Param).order_by(Param.grupo, Param.key)).scalars() if p.key in vigentes]
    return render_template("config.html", params=params,
                           warehouses=list(s.execute(select(Warehouse).order_by(Warehouse.uso, Warehouse.prioridad, Warehouse.code)).scalars()),
                           lead_times=list(s.execute(select(LeadTime).order_by(LeadTime.categoria)).scalars()),
                           lines=list(s.execute(select(ProductionLine)).scalars()),
                           grupos_cap={lc: gr for gr in (__import__("app.services.core", fromlist=["x"]).param("capacidad_lineas", []) or [])
                                       for lc in (gr.get("lineas") or [])},
                           phases=list(s.execute(select(ImportPhaseTemplate).order_by(ImportPhaseTemplate.orden)).scalars()),
                           roles=list(s.execute(select(Role).order_by(Role.nombre)).scalars()),
                           var_rules=list(s.execute(select(PurchaseVariationRule).where(PurchaseVariationRule.activo.is_(True))
                                                    .order_by(PurchaseVariationRule.alcance, PurchaseVariationRule.canal)).scalars()),
                           canales=sorted(set(prices_svc.canales()) | {c.canal_precio for c in s.execute(
                               select(Customer).where(Customer.canal_precio != "")).scalars() if c.canal_precio}),
                           clientes=list(s.execute(select(Customer).order_by(Customer.nombre)).scalars()))


@bp.route("/configuracion/variacion-compra", methods=["POST"])
@perm_required("config.editar")
def variation_rule_edit():
    from ..services import customer_behavior as cb
    fm = request.form
    if fm.get("accion") == "baja":
        def _baja():
            r = db().get(PurchaseVariationRule, int(fm.get("id") or 0))
            if r is None:
                raise BusinessError("Regla no encontrada.")
            cb.remove_variation_rule(g.user, r)
        return act(_baja, "Regla desactivada.", url_for("main.config") + "#variacion")
    return act(lambda: cb.save_variation_rule(g.user, fm.get("alcance"), fm.get("canal"), fm.get("customer_id"),
                                              f_float("umbral_pct"), int(fm["dias"]) if fm.get("dias") else None,
                                              fm.get("alerta", "1") == "1", fm.get("id")),
               "Regla de variación de compra guardada.", url_for("main.config") + "#variacion")


@bp.route("/configuracion/param/<key>", methods=["POST"])
@perm_required("config.editar")
def param_edit(key):
    p = db().get(Param, key) or abort(404)
    def _do():
        try:
            val = coerce_param(p.tipo, request.form.get("valor"))
        except Exception as e:  # noqa: BLE001
            raise BusinessError(f"Valor inválido para {key} ({p.tipo}): {e}")
        set_param(key, val, g.user, request.form.get("estado") or None)
    return act(_do, f"Parámetro {key} actualizado (nueva versión).", url_for("main.config") + "#params")


@bp.route("/configuracion/param/<key>/historial")
@perm_required("config.ver")
def param_history(key):
    rows = list(db().execute(select(ParamHistory).where(ParamHistory.key == key).order_by(ParamHistory.version.desc())).scalars())
    return render_template("simple_table.html", title=f"Historial del parámetro {key}",
                           headers=["Versión", "Valor", "Estado", "Fecha", "Usuario"],
                           rows=[[r.version, r.valor.get("v"), r.estado, r.ts, r.user_id] for r in rows])


@bp.route("/configuracion/almacen", methods=["POST"])
@perm_required("config.editar")
def warehouse_edit():
    def _do():
        code = request.form["code"].strip()
        w = db().get(Warehouse, code)
        if w is None:
            w = Warehouse(code=code, nombre=code)
            db().add(w)
        antes = {"nombre": w.nombre, "uso": w.uso, "prioridad": w.prioridad, "reservable": w.reservable, "habilitado": w.habilitado}
        w.nombre = request.form.get("nombre", w.nombre)
        w.uso = request.form.get("uso", w.uso)
        w.prioridad = int(request.form.get("prioridad") or 99)
        w.reservable = request.form.get("reservable") == "1"
        if "habilitado" in request.form:
            w.habilitado = request.form.get("habilitado") == "1"
        w.observacion = request.form.get("observacion", w.observacion)
        audit(g.user, "ALMACEN_EDITADO", "Warehouse", code, {"antes": antes, "despues": {
            "nombre": w.nombre, "uso": w.uso, "prioridad": w.prioridad, "reservable": w.reservable, "habilitado": w.habilitado}})
    return act(_do, "Almacén guardado.", url_for("main.config") + "#almacenes")


@bp.route("/configuracion/plazo", methods=["POST"])
@perm_required("config.editar")
def leadtime_edit():
    def _do():
        lid = request.form.get("id")
        lt = db().get(LeadTime, int(lid)) if lid else None
        if lt is None:
            lt = LeadTime(categoria=request.form["categoria"], dias_min=0, dias_max=0, fuente="Configuración")
            db().add(lt)
        lt.categoria = request.form.get("categoria", lt.categoria)
        lt.dias_min = int(request.form.get("dias_min") or 0)
        lt.dias_max = int(request.form.get("dias_max") or 0)
        lt.mes_desde = int(request.form["mes_desde"]) if request.form.get("mes_desde") else None
        lt.mes_hasta = int(request.form["mes_hasta"]) if request.form.get("mes_hasta") else None
        if lt.dias_min > lt.dias_max:
            raise BusinessError("Plazo mínimo mayor que el máximo.")
        audit(g.user, "PLAZO_EDITADO", "LeadTime", lt.categoria, {"min": lt.dias_min, "max": lt.dias_max,
                                                                  "meses": [lt.mes_desde, lt.mes_hasta]})
    return act(_do, "Plazo guardado.", url_for("main.config") + "#plazos")


@bp.route("/configuracion/linea", methods=["POST"])
@perm_required("config.editar", "produccion.programar")
def line_edit():
    def _do():
        from ..services.core import param
        ln = db().get(ProductionLine, request.form["code"]) or abort(404)
        cap = f_float("capacidad_kg_dia")
        grupos = [dict(x) for x in (param("capacidad_lineas", []) or [])]
        for gr in grupos:  # la capacidad de un grupo de líneas se edita en el grupo (parámetro capacidad_lineas)
            if ln.code in (gr.get("lineas") or []) and cap is not None and cap != gr.get("kg_dia"):
                gr["kg_dia"] = cap
                set_param("capacidad_lineas", grupos, g.user)
                break
        ln.capacidad_kg_dia = cap if len(next((gr["lineas"] for gr in grupos if ln.code in (gr.get("lineas") or [])), [ln.code])) == 1 else None
        ln.activa = request.form.get("activa") == "1"
        audit(g.user, "LINEA_EDITADA", "ProductionLine", ln.code, {"capacidad": ln.capacidad_kg_dia, "activa": ln.activa})
    return act(_do, "Línea guardada.", request.referrer or url_for("main.config"))


@bp.route("/configuracion/fase", methods=["POST"])
@perm_required("config.editar", "importaciones.gestionar")
def phase_edit():
    def _do():
        pid = request.form.get("id")
        ph = db().get(ImportPhaseTemplate, int(pid)) if pid else None
        if request.form.get("eliminar") == "1" and ph is not None:
            db().delete(ph)
            audit(g.user, "FASE_PLANTILLA_ELIMINADA", "ImportPhaseTemplate", pid)
            return
        if ph is None:
            ph = ImportPhaseTemplate(orden=0, nombre="")
            db().add(ph)
        ph.orden = int(request.form.get("orden") or 0)
        ph.nombre = request.form.get("nombre", "").strip()
        ph.dias_desde_inicio = int(request.form.get("dias_desde_inicio") or 0)
        ph.recordatorio_dias = int(request.form.get("recordatorio_dias") or 0)
        ph.responsable_rol = request.form.get("responsable_rol") or "IMPORTACIONES"
        ph.estado_def = request.form.get("estado_def") or "PROPUESTO"
        if not ph.nombre:
            raise BusinessError("Nombre de fase obligatorio.")
        audit(g.user, "FASE_PLANTILLA_EDITADA", "ImportPhaseTemplate", ph.nombre)
    return act(_do, "Fase guardada.", url_for("main.config") + "#fases")


@bp.route("/configuracion/productos")
@perm_required("config.ver")
def products():
    q = (request.args.get("q") or "").strip().upper()
    stmt = select(Product).order_by(Product.code)
    if q:
        stmt = stmt.where((Product.code.like(f"%{q}%")) | (Product.descripcion.like(f"%{q}%")))
    rows = list(db().execute(stmt.limit(300)).scalars())
    from ..catalogs import PCC1_HUMEDAD
    cats = [lt.categoria for lt in db().execute(select(LeadTime)).scalars()]
    return render_template("products.html", rows=rows, q=q, cats=sorted(set(cats)), pcc1=PCC1_HUMEDAD)


@bp.route("/configuracion/productos/<code>", methods=["POST"])
@perm_required("config.editar")
def product_edit(code):
    p = db().get(Product, code) or abort(404)
    def _do():
        antes = {k: getattr(p, k) for k in ("peso_kg", "tipo", "um", "categoria_reposicion", "stock_minimo", "periodo_analisis_dias",
                                            "margen_seguridad_dias", "merma_pct", "tiempo_max_almacen_dias", "grupo_humedad",
                                            "producto_base", "calidad", "marca", "presentacion", "costo_max_compra")}
        for k in ("tipo", "um", "categoria_reposicion", "grupo_humedad", "producto_base", "calidad", "marca", "presentacion",
                  "proveedor_habitual"):
            if k in request.form:
                setattr(p, k, request.form.get(k, "").strip())
        for k in ("peso_kg", "stock_minimo", "merma_pct", "costo_max_compra", "unidades_por_bulto"):
            if k in request.form:
                setattr(p, k, f_float(k))
        for k in ("periodo_analisis_dias", "margen_seguridad_dias", "tiempo_max_almacen_dias"):
            if k in request.form:
                v = request.form.get(k, "").strip()
                setattr(p, k, int(v) if v else None)
        audit(g.user, "PRODUCTO_EDITADO", "Product", code, {"antes": antes})
    return act(_do, f"Producto {code} actualizado.", url_for("main.products", q=request.form.get("q", "")))


@bp.route("/configuracion/clientes", methods=["GET", "POST"])
@perm_required("config.ver", "ov.crear")
def customers():
    if request.method == "POST":
        if "config.editar" not in g.perms and "ov.crear" not in g.perms:
            abort(403)
        def _do():
            cid = request.form.get("id")
            c = db().get(Customer, int(cid)) if cid else None
            if c is None:
                ruc = request.form.get("ruc", "").strip()
                if not ruc:
                    raise BusinessError("RUC obligatorio.")
                if db().execute(select(Customer).where(Customer.ruc == ruc)).scalars().first():
                    raise BusinessError("El RUC ya existe.")
                c = Customer(ruc=ruc, nombre="")
                db().add(c)
            for k in ("nombre", "grupo", "direccion", "distrito", "provincia", "horario_recepcion"):
                if k in request.form:
                    setattr(c, k, request.form.get(k, "").strip())
            if "canal_precio" in request.form and request.form.get("canal_precio", "") != (c.canal_precio or ""):
                if "clientes.canal" not in g.perms:
                    raise BusinessError("El canal de precios del cliente lo asigna el Jefe Comercial o Sistemas.")
                audit(g.user, "CLIENTE_CANAL", "Customer", c.ruc, {"antes": c.canal_precio, "despues": request.form["canal_precio"]})
                c.canal_precio = request.form["canal_precio"].strip()
            c.requiere_cita = request.form.get("requiere_cita") == "1"
            v = request.form.get("vida_util_min_dias", "").strip()
            c.vida_util_min_dias = int(v) if v else None
            if not c.nombre:
                raise BusinessError("Nombre obligatorio.")
            audit(g.user, "CLIENTE_GUARDADO", "Customer", c.ruc)
        return act(_do, "Cliente guardado.", url_for("main.customers"))
    rows = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    from ..services import prices as psvc
    from ..services.core import param
    canales = sorted(set(psvc.canales()) | set(param("lista_granel_canales", []) or []))
    from ..services.customers import customer_groups
    return render_template("customers.html", rows=rows, canales=canales, canal_de=psvc.channel_of, grupos=customer_groups())


@bp.route("/configuracion/guia", methods=["POST"])
@perm_required("config.editar")
def guide_data():
    """Datos de la guía de remisión (correo, web y dirección de partida por almacén), modificables (16-oct)."""
    from ..services.core import param
    f = request.form

    def _do():
        set_param("empresa_correo_documentos", f.get("correo", "").strip(), g.user)
        set_param("empresa_web", f.get("web", "").strip(), g.user)
        dirs = dict(param("direccion_partida_por_almacen", {}) or {})
        for k, v in f.items():
            if k.startswith("partida_"):
                code = k[len("partida_"):]
                if v.strip():
                    dirs[code] = v.strip()
                else:
                    dirs.pop(code, None)
        set_param("direccion_partida_por_almacen", dirs, g.user)
    return act(_do, "Datos de la guía de remisión guardados.", url_for("main.config") + "#guia")


@bp.route("/configuracion/feriados", methods=["GET", "POST"])
@perm_required("config.editar", "produccion.programar")
def holidays():
    """Feriados: carga anual (Excel o PDF) o uno por uno; cada feriado puede marcarse «se trabaja» (16-oct)."""
    from ..services import calendar as cal
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        volver = url_for("main.holidays")
        if acc == "trabaja":
            return act(lambda: cal.set_worked(g.user, f.get("fecha", ""), f.get("se_trabaja") == "1"),
                       "Feriado actualizado.", volver)
        if acc == "quitar":
            return act(lambda: cal.remove_holiday(g.user, f.get("fecha", "")), "Feriado quitado.", volver)
        if acc == "archivo":
            def _imp():
                import os
                import tempfile
                fa = request.files.get("archivo")
                if fa is None or not fa.filename:
                    raise BusinessError("Seleccione el archivo de feriados (Excel o PDF).")
                suf = ".pdf" if fa.filename.lower().endswith(".pdf") else ".xlsx"
                with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
                    fa.save(tmp.name)
                try:
                    n, errores, anios = cal.import_holidays(g.user, tmp.name, fa.filename)
                finally:
                    os.unlink(tmp.name)
                for e in errores[:20]:
                    flash(e, "error")
                return n, anios
            return act(_imp, lambda r: f"{r[0]} feriado(s) cargados para {', '.join(r[1])} (reemplazan los de ese año).", volver)
        return act(lambda: cal.add_holiday(g.user, f_date("fecha", True), f.get("nombre", ""), f.get("se_trabaja") == "1"),
                   "Feriado registrado.", volver)
    anio = request.args.get("anio", type=int) or date.today().year
    todos = cal.holidays()
    anios = sorted({int(k[:4]) for k in todos} | {date.today().year})
    return render_template("holidays.html", filas=[v for k, v in todos.items() if k.startswith(str(anio))], anio=anio,
                           anios=anios, dias=["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"])


@bp.route("/configuracion/canales", methods=["GET", "POST"])
@perm_required("canales.gestionar")
def channels():
    """Canales de precios y grupos de cliente (obs. demo v0.7): los agregan el Coordinador de Ventas, el Jefe de Ventas
    y Sistemas cuando es necesario."""
    from ..services import customers as csvc
    from ..services import prices as psvc
    from ..services.core import param
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "grupo":
            return act(lambda: csvc.add_group(g.user, f.get("nombre", ""), f.get("canal", "")),
                       lambda n: f"Grupo {n} agregado.", url_for("main.channels"))
        return act(lambda: csvc.add_channel(g.user, f.get("nombre", "")), lambda n: f"Canal {n} agregado.",
                   url_for("main.channels"))
    mapa = param("canal_precio_por_grupo", {}) or {}
    return render_template("channels.html", canales=psvc.canales(), adicionales=param("canales_adicionales", []) or [],
                           grupos=csvc.customer_groups(), mapa=mapa)


# ------------------------------- usuarios ----------------------------------
@bp.route("/usuarios", methods=["GET", "POST"])
@perm_required("usuarios.administrar")
def users():
    s = db()
    if request.method == "POST":
        def _do():
            uid = request.form.get("id")
            if uid:
                u = s.get(User, int(uid))
                if request.form.get("accion") == "desbloquear":  # solo desbloquea; no toca el resto de la ficha
                    u.bloqueado_hasta, u.intentos_fallidos = None, 0
                    audit(g.user, "USUARIO_DESBLOQUEADO", "User", u.username)
                    return
                antes = {"rol": u.role_code, "activo": u.activo, "nombre": u.nombre, "almacen": u.almacen}
                if s.get(Role, request.form.get("role_code", u.role_code)) is None:
                    raise BusinessError("Perfil inexistente.")
                u.role_code = request.form.get("role_code", u.role_code)
                u.nombre = (request.form.get("nombre") or u.nombre).strip()
                u.almacen = request.form.get("almacen", u.almacen) or ""
                u.activo = request.form.get("activo") == "1"
                u.email = request.form.get("email", u.email)
                if request.form.get("password"):
                    check_new_password(u, request.form["password"])
                    u.password_hash = generate_password_hash(request.form["password"])
                    u.debe_cambiar_clave = True  # la clave asignada por Sistemas se cambia en el primer ingreso
                    u.bloqueado_hasta, u.intentos_fallidos = None, 0
                audit(g.user, "USUARIO_EDITADO", "User", u.username, {"antes": antes, "rol": u.role_code, "activo": u.activo})
            else:
                from ..seed import create_user
                pwd = request.form.get("password") or ""
                un = request.form.get("username", "").strip().lower()
                check_new_password(None, pwd)
                if not un or s.execute(select(User).where(User.username == un)).first():
                    raise BusinessError("Usuario vacío o existente.")
                if s.get(Role, request.form.get("role_code", "")) is None:
                    raise BusinessError("Elija el perfil del usuario.")
                u = create_user(un, (request.form.get("nombre") or un).strip(), request.form["role_code"], pwd,
                                request.form.get("email") or None)
                u.almacen = request.form.get("almacen", "")
                u.debe_cambiar_clave = True
                audit(g.user, "USUARIO_CREADO", "User", un, {"rol": u.role_code})
        return act(_do, "Usuario guardado.", url_for("main.users"))
    roles = list(s.execute(select(Role).order_by(Role.area, Role.nombre)).scalars())
    from ..services.core import param
    from ..models import Warehouse
    return render_template("users.html", users=list(s.execute(select(User).order_by(User.role_code, User.username)).scalars()), roles=roles,
                           almacenes=list(s.execute(select(Warehouse).order_by(Warehouse.code)).scalars()),
                           now_=datetime.now(), minimo=int(param("clave_longitud_minima", 8) or 8))


@bp.route("/usuarios/permisos")
@perm_required("usuarios.administrar")
def permissions():
    """Permisos por rol con una vista amigable (observaciones al demo v0.5): por rol con interruptores agrupados por
    módulo, o matriz compacta filtrable por área."""
    s = db()
    roles = list(s.execute(select(Role).order_by(Role.area, Role.nombre)).scalars())
    perms = list(s.execute(select(Permission).order_by(Permission.modulo, Permission.code)).scalars())
    matrix = {}
    for rp in s.execute(select(RolePermission)).scalars():
        matrix[(rp.role_code, rp.perm_code)] = rp
    rol = request.args.get("rol") or (roles[0].code if roles else "")
    modulos = {}
    for p in perms:
        modulos.setdefault(p.modulo, []).append(p)
    conteo = {r.code: sum(1 for (rc, _pc) in matrix if rc == r.code) for r in roles}
    areas = sorted({r.area for r in roles})
    return render_template("permissions.html", roles=roles, perms=perms, matrix=matrix, rol=rol, modulos=modulos,
                           conteo=conteo, areas=areas, vista=request.args.get("vista", "rol"),
                           area=request.args.get("area", ""))


@bp.route("/usuarios/permiso", methods=["POST"])
@perm_required("usuarios.administrar")
def perm_toggle():
    def _do():
        role, perm = request.form["role_code"], request.form["perm_code"]
        rp = db().execute(select(RolePermission).where(RolePermission.role_code == role,
                                                       RolePermission.perm_code == perm)).scalars().first()
        if rp:
            db().delete(rp)
            audit(g.user, "PERMISO_RETIRADO", "RolePermission", f"{role}:{perm}", {"origen": rp.origen})
        else:
            db().add(RolePermission(role_code=role, perm_code=perm, origen="PROPUESTO",
                                    fuente=f"Asignado por {g.user.nombre} (configuración)"))
            audit(g.user, "PERMISO_OTORGADO", "RolePermission", f"{role}:{perm}")
    volver = request.form.get("volver") or ""
    return act(_do, "Permisos actualizados.", volver if volver.startswith("/usuarios/permisos") else url_for("main.permissions"))


# ------------------------------- auditoría ---------------------------------
@bp.route("/auditoria", endpoint="audit")
@perm_required("auditoria.ver")
def audit_view():
    q = select(AuditLog).order_by(AuditLog.id.desc())
    ent = request.args.get("entidad")
    acc = request.args.get("accion")
    if ent:
        q = q.where(AuditLog.entidad == ent)
    if acc:
        q = q.where(AuditLog.accion.like(f"%{acc.upper()}%"))
    uid = request.args.get("user_id")
    if uid and uid.isdigit():
        q = q.where(AuditLog.user_id == int(uid))
    eid = (request.args.get("entidad_id") or "").strip()
    if eid:
        q = q.where(AuditLog.entidad_id == eid)
    d1, d2 = request.args.get("desde"), request.args.get("hasta")
    if d1:
        q = q.where(AuditLog.ts >= datetime.combine(date.fromisoformat(d1), datetime.min.time()))
    if d2:
        q = q.where(AuditLog.ts <= datetime.combine(date.fromisoformat(d2), datetime.max.time()))
    rows = list(db().execute(q.limit(1000)).scalars())
    usuarios = list(db().execute(select(User).order_by(User.nombre)).scalars())
    entidades = sorted({e for e in db().execute(select(AuditLog.entidad).distinct()).scalars() if e})
    return render_template("audit.html", rows=rows, ent=ent or "", acc=acc or "", usuarios=usuarios, entidades=entidades,
                           f=request.args)


# ------------------------------- exportación -------------------------------
EXPORTS = {
    "ov": ("ov.ver", "Órdenes de venta"), "stock": ("stock.ver", "Stock por lote"), "alertas": ("alertas.ver", "Alertas"),
    "auditoria": ("auditoria.ver", "Auditoría"), "compras": ("compras.ver", "Compras"),
    "produccion": ("produccion.ver", "Producción"), "incidencias": ("distribucion.ver", "Incidencias"),
    "rutas": ("distribucion.ver", "Rutas"), "calidad": ("calidad.ver", "Registros de calidad"),
    "liquidaciones": ("produccion.ver", "Liquidaciones"),
}


@bp.route("/exportar/<entidad>.xlsx")
@login_required
def export(entidad):
    import openpyxl
    from .exports import build_rows
    if entidad not in EXPORTS:
        abort(404)
    perm, nombre = EXPORTS[entidad]
    if perm not in g.perms or "export.datos" not in g.perms:
        abort(403)
    headers, rows = build_rows(entidad, g.user)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = nombre[:30]
    ws.append(headers)
    for r in rows:
        ws.append([v if not isinstance(v, (list, dict)) else str(v) for v in r])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    audit(g.user, "EXPORTACION", entidad, "", {"filas": len(rows)})
    db().commit()
    return send_file(bio, as_attachment=True, download_name=f"{entidad}_{date.today():%Y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/evidencias/<path:name>")
@perm_required("distribucion.ver", "ov.ver")
def evidence(name):
    from flask import current_app
    return send_from_directory(current_app.config["UPLOAD_DIR"], os.path.basename(name))
