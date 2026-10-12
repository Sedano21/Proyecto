"""Inicio de sesión con Microsoft 365 (Microsoft Entra ID) mediante OpenID Connect con la librería oficial MSAL.

Se activa con las variables de entorno M365_CLIENT_ID, M365_CLIENT_SECRET y M365_TENANT_ID (registro de la aplicación
en Entra ID; URI de redirección: https://<servidor>/auth/microsoft/callback, o M365_REDIRECT_URI). MSAL valida el
estado (state), el nonce y la firma del token. La persona debe existir antes como usuario activo del sistema con el mismo
correo corporativo: los roles se asignan en el sistema (Sistemas), no en Microsoft 365.
"""
import os

from flask import Blueprint, abort, current_app, flash, redirect, request, session, url_for
from sqlalchemy import func, select

from ..db import db
from ..models import User
from ..services.core import audit

bp = Blueprint("m365", __name__)


def enabled():
    return all(os.environ.get(k) for k in ("M365_CLIENT_ID", "M365_CLIENT_SECRET", "M365_TENANT_ID"))


def _client():
    import msal
    return msal.ConfidentialClientApplication(
        os.environ["M365_CLIENT_ID"], client_credential=os.environ["M365_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{os.environ['M365_TENANT_ID']}")


def _redirect_uri():
    return os.environ.get("M365_REDIRECT_URI") or url_for("m365.callback", _external=True)


@bp.route("/login/microsoft")
def start():
    if not enabled():
        abort(404)
    flow = _client().initiate_auth_code_flow(["User.Read"], redirect_uri=_redirect_uri())
    session["m365_flow"] = flow
    return redirect(flow["auth_uri"])


def login_with_claims(claims):
    """Busca el usuario por el correo del token y abre la sesión. Devuelve el usuario o None."""
    email = (claims.get("preferred_username") or claims.get("email") or claims.get("upn") or "").strip().lower()
    if not email:
        return None
    u = db().execute(select(User).where(func.lower(User.email) == email)).scalars().first()
    if u is None or not u.activo:
        audit(None, "LOGIN_M365_RECHAZADO", "User", email, {"motivo": "usuario no registrado o inactivo"})
        db().commit()
        return None
    tok = session.get("_csrf")
    session.clear()
    session["uid"] = u.id
    session["auth"] = "M365"
    if tok:
        session["_csrf"] = tok
    audit(u, "LOGIN", "User", u.id, {"metodo": "Microsoft 365", "tenant": claims.get("tid")})
    db().commit()
    return u


@bp.route("/auth/microsoft/callback")
def callback():
    if not enabled():
        abort(404)
    flow = session.pop("m365_flow", None)
    if not flow:
        flash("La sesión de inicio con Microsoft expiró; intente de nuevo.", "error")
        return redirect(url_for("main.login"))
    try:
        result = _client().acquire_token_by_auth_code_flow(flow, request.args.to_dict())
    except ValueError:  # state no coincide (posible CSRF)
        flash("Respuesta de Microsoft no válida.", "error")
        return redirect(url_for("main.login"))
    if "error" in result:
        current_app.logger.warning("M365 login error: %s", result.get("error"))
        flash("No se pudo iniciar sesión con Microsoft 365.", "error")
        return redirect(url_for("main.login"))
    if login_with_claims(result.get("id_token_claims") or {}) is None:
        flash("Su cuenta de Microsoft 365 no está registrada como usuario activo del sistema. Pida a Sistemas que lo cree "
              "con su correo corporativo.", "error")
        return redirect(url_for("main.login"))
    return redirect(url_for("main.dashboard"))
