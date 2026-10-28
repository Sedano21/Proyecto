"""Utilidades comunes de las vistas: sesión, permisos, CSRF, ejecución de acciones con commit/rollback."""
import secrets
from datetime import date, datetime
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

from ..db import db
from ..models import User
from ..services.core import BusinessError, has_perm, user_perms


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    u = db().get(User, uid)
    if u is None or not u.activo:
        return None
    return u


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if g.user is None:
            return redirect(url_for("main.login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def perm_required(*perms):
    """Requiere AL MENOS uno de los permisos indicados."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if g.user is None:
                return redirect(url_for("main.login", next=request.path))
            if not any(p in g.perms for p in perms):
                # obs. demo v0.7: Gerencia General y de Operaciones visualizan todas las pantallas (solo consulta)
                if not ("vista.total" in g.perms and request.method in ("GET", "HEAD")):
                    abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def check_csrf():
    if request.method == "POST":
        tok = request.form.get("_csrf") or request.headers.get("X-CSRF")
        if not tok or tok != session.get("_csrf"):
            abort(400, "Token CSRF inválido. Recargue la página.")


def act(fn, ok_msg, redirect_to, redirect_fn=None):
    """Ejecuta una acción de negocio con commit; ante BusinessError hace rollback y muestra el mensaje.
    redirect_fn(resultado) permite redirigir al objeto creado cuando la acción tiene éxito."""
    try:
        result = fn()
        db().commit()
        if ok_msg:
            flash(ok_msg if not callable(ok_msg) else ok_msg(result), "ok")
        if redirect_fn:
            return redirect(redirect_fn(result))
    except BusinessError as e:
        db().rollback()
        flash(str(e), "error")
    except (ValueError, TypeError) as e:
        db().rollback()
        flash(f"Dato inválido: {e}", "error")
    return redirect(redirect_to)


def f_date(name, required=False):
    raw = (request.form.get(name) or request.args.get(name) or "").strip()
    if not raw:
        if required:
            raise BusinessError(f"La fecha '{name}' es obligatoria.")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise BusinessError(f"Fecha inválida: {raw}")


def f_float(name, required=False, default=None):
    raw = (request.form.get(name) or "").strip().replace(",", ".")
    if raw == "":
        if required:
            raise BusinessError(f"El valor '{name}' es obligatorio.")
        return default
    try:
        return float(raw)
    except ValueError:
        raise BusinessError(f"Número inválido en '{name}': {raw}")


def f_bool(name):
    return request.form.get(name) in ("1", "on", "true", "si", "sí")


def fmt_date(d):
    if d is None or d == "":
        return ""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y %H:%M")
    return d.strftime("%d/%m/%Y")


def fmt_num(x, dec=2):
    if x is None or x == "":
        return ""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.{dec}f}".replace(",", " ")


_LIBRES = {"static", "main.login", "main.logout", "main.change_password", "main.privacy_notice", "main.alerts_status",
           "main.evidence"}


def access_gate(user):
    """Pantalla obligatoria antes de usar el sistema: aviso de datos (Ley 29733) o cambio de contraseña."""
    from datetime import timedelta
    from ..services.core import param
    version = param("aviso_datos_version", "") or ""
    if version and (user.aviso_aceptado or {}).get("version") != version:
        return "main.privacy_notice"
    if user.debe_cambiar_clave:
        return "main.change_password"
    dias = int(param("clave_dias_vigencia", 0) or 0)
    if dias and (user.clave_ts is None or datetime.now() - user.clave_ts > timedelta(days=dias)):
        return "main.change_password"
    return None


def install(app):
    @app.before_request
    def _load_user():
        g.user = current_user()
        g.perms = user_perms(g.user) if g.user else set()
        check_csrf()
        # marcha blanca: aviso de datos personales y responsabilidad (primer ingreso o nueva versión) y contraseña al día
        if g.user is not None and request.endpoint not in _LIBRES:
            destino = access_gate(g.user)
            if destino:
                return redirect(url_for(destino, next=request.full_path if request.method == "GET" else None))

    def _logo_url():
        """Logotipo oficial si Sistemas lo cargó en static/img (logo_oficial.svg/png); si no, el logo de la empresa
        usado en los formatos impresos."""
        import os
        from flask import url_for
        for n in ("logo_oficial.svg", "logo_oficial.png"):
            if os.path.exists(os.path.join(app.static_folder, "img", n)):
                return url_for("static", filename=f"img/{n}")
        return url_for("static", filename="img/logo_corporacion_productiva.png")

    @app.context_processor
    def _ctx():
        from ..services.stock import stock_freshness
        from ..services.alerts import inbox
        u = g.get("user")
        abiertas = 0
        if u is not None:
            try:
                abiertas = len(inbox(u, solo_abiertas=True))
            except Exception:  # noqa: BLE001
                abiertas = 0
        return {"csrf_token": csrf_token, "user": u, "perms": g.get("perms", set()), "can": lambda p: p in g.get("perms", set()),
                "ve": lambda p: p in g.get("perms", set()) or "vista.total" in g.get("perms", set()),
                "logo_url": _logo_url(), "vi": _vi,
                "fmt_date": fmt_date, "fmt_num": fmt_num, "stock_info": stock_freshness() if u else None,
                "alertas_abiertas": abiertas, "today": date.today(), "demo_mode": app.config.get("DEMO_MODE"),
                "contingencia": _contingencia() if u else {}}

    def _vi(code):
        """El indicador es pertinente para el perfil del usuario (matriz de indicadores); se calcula una vez por pedido."""
        from flask import request
        from ..services.indicators import visible
        cache = request.environ.setdefault("cp.vi", {})  # por pedido HTTP (g puede durar más que un pedido)
        if code not in cache:
            cache[code] = visible(g.get("user"), code)
        return cache[code]

    def _contingencia():
        from ..services.core import contingency
        try:
            return contingency()
        except Exception:  # noqa: BLE001
            return {}

    app.jinja_env.globals["csrf_token"] = csrf_token
    # rediseño de informes (28-oct-2026): cabecera institucional disponible también dentro de las macros
    app.jinja_env.globals["logo_src"] = _logo_url
    app.jinja_env.globals["informe_meta"] = lambda n: __import__("app.services.report_center", fromlist=["x"]).META.get(n, {})
    app.jinja_env.globals["ahora"] = datetime.now

    def es_tarea(a):
        """La alerta es tarea para el usuario actual solo si puede accionarla (si no, se le muestra como información)."""
        from ..services.alerts import can_act
        return can_act(g.get("user"), a)
    app.jinja_env.globals["es_tarea"] = es_tarea
    app.jinja_env.globals["strptime"] = lambda iso: date.fromisoformat(str(iso)[:10])

    def productos_base():
        """Productos base que ofrecemos (lista desplegable para precios de competencia, sustitutos, mercado)."""
        from ..services.market import bases
        return sorted(bases())
    app.jinja_env.globals["productos_base"] = productos_base

    def estado_alerta(a):
        from ..services.alerts import display_state
        return display_state(a)
    app.jinja_env.globals["estado_alerta"] = estado_alerta

    def cond_cliente(customer):
        from ..services.customer_conditions import summary
        return summary(customer)
    app.jinja_env.globals["cond_cliente"] = cond_cliente

    def pd(code):
        """Descripción completa del artículo junto al código (observación del 14-oct: el producto debe mostrar su descripción)."""
        from markupsafe import Markup, escape
        from ..models import Product
        cache = g.setdefault("_pdesc", {})
        if code not in cache:
            p = db().get(Product, code) if code else None
            cache[code] = p.descripcion if p else ""
        return Markup(f'<span class="pd">{escape(cache[code])}</span>') if cache[code] else ""
    app.jinja_env.globals["pd"] = pd

    def doc_param(key, default=None):
        from ..services.core import param
        return param(key, default)
    app.jinja_env.globals["doc_param"] = doc_param
    app.jinja_env.filters["d"] = fmt_date
    app.jinja_env.filters["n"] = fmt_num

    def dictfmt(d):
        """Detalle legible de un registro (clave: valor) en lugar de JSON crudo."""
        from markupsafe import Markup, escape
        if not isinstance(d, dict):
            return escape(d)

        def val(v):
            if isinstance(v, dict):
                return ", ".join(f"{k}: {val(x)}" for k, x in v.items() if x not in (None, "", [], {}))
            if isinstance(v, (list, tuple)):
                return ", ".join(val(x) for x in v) or "—"
            if isinstance(v, bool):
                return "sí" if v else "no"
            return str(v)
        partes = [f"<b>{escape(str(k).replace('_', ' '))}</b>: {escape(val(v))}" for k, v in d.items()
                  if v not in (None, "", [], {})]
        return Markup('<span class="dictfmt">' + " · ".join(partes) + "</span>")
    app.jinja_env.filters["dictfmt"] = dictfmt


def fail(msg, redirect_to):
    flash(msg, "error")
    return redirect(redirect_to)
