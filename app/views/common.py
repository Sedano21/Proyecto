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


def act(fn, ok_msg, redirect_to):
    """Ejecuta una acción de negocio con commit; ante BusinessError hace rollback y muestra el mensaje."""
    try:
        result = fn()
        db().commit()
        if ok_msg:
            flash(ok_msg if not callable(ok_msg) else ok_msg(result), "ok")
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


def install(app):
    @app.before_request
    def _load_user():
        g.user = current_user()
        g.perms = user_perms(g.user) if g.user else set()
        check_csrf()

    @app.context_processor
    def _ctx():
        from ..services.stock import stock_freshness
        from ..services.alerts import visible_alerts
        u = g.get("user")
        abiertas = 0
        if u is not None:
            try:
                abiertas = len([a for a in visible_alerts(u, solo_abiertas=True)])
            except Exception:  # noqa: BLE001
                abiertas = 0
        return {"csrf_token": csrf_token, "user": u, "perms": g.get("perms", set()), "can": lambda p: p in g.get("perms", set()),
                "fmt_date": fmt_date, "fmt_num": fmt_num, "stock_info": stock_freshness() if u else None,
                "alertas_abiertas": abiertas, "today": date.today(), "demo_mode": app.config.get("DEMO_MODE")}

    app.jinja_env.globals["csrf_token"] = csrf_token

    def cond_cliente(customer):
        from ..services.customer_conditions import summary
        return summary(customer)
    app.jinja_env.globals["cond_cliente"] = cond_cliente
    app.jinja_env.filters["d"] = fmt_date
    app.jinja_env.filters["n"] = fmt_num


def fail(msg, redirect_to):
    flash(msg, "error")
    return redirect(redirect_to)
