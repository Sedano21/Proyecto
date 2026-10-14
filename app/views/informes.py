"""Informes por área con gráficos, tendencias y recomendaciones (observaciones al demo v0.5, 13-oct)."""
from flask import Blueprint, abort, g, render_template, request

from ..services import charts
from ..services import reports as rsvc
from .common import f_date, login_required

bp = Blueprint("rep", __name__, url_prefix="/informes")

# informe -> (título, permisos que lo habilitan)
INFORMES = {
    "comercial": ("Comercial", ("informes.comercial",)),
    "reempaque": ("Reempaque", ("informes.reempaque",)),
    "produccion": ("Producción", ("informes.produccion",)),
    "distribucion": ("Distribución", ("informes.distribucion",)),
}


def disponibles():
    return [(k, t) for k, (t, perms) in INFORMES.items() if any(p in g.perms for p in perms)]


def _periodo():
    try:
        return f_date("desde"), f_date("hasta")
    except Exception:  # noqa: BLE001
        return None, None


@bp.route("/")
@login_required
def home():
    items = disponibles()
    if not items:
        abort(403)
    return render_template("informes_home.html", items=items)


@bp.route("/<nombre>")
@login_required
def show(nombre):
    if nombre not in INFORMES or nombre not in dict(disponibles()):
        abort(403)
    desde, hasta = _periodo()
    if nombre == "comercial":
        d = rsvc.comercial(desde, hasta, ver_costos="costos.ver" in g.perms)
        graf = {"semanal": charts.line([("Ventas S/", d["serie_semanal"])], "S/", title="Ventas semanales"),
                "vend_soles": charts.bars([(k, v["soles"]) for k, v in d["vendedores"]], "S/", title="Ventas por vendedor (S/)"),
                "vend_kg": charts.bars([(k, v["kg"]) for k, v in d["vendedores"]], "kg", title="Ventas por vendedor (kg)", color=2),
                "top": charts.bars([(f"{k} {n[:18]}", v) for k, n, v, _ in d["top_productos"]], "S/", title="Productos más vendidos"),
                "pres": charts.bars([(str(k), v) for k, v in d["presentaciones"]], "", title="Presentaciones preferidas", color=6),
                "margen": charts.bars([(f"{k} {n[:16]}", m) for k, n, m in d["margen_producto"][:15]], "%",
                                      title="Margen por producto (menores primero)", color=2)}
        return render_template("informe_comercial.html", d=d, graf=graf, items=disponibles(), actual=nombre)
    fn = getattr(rsvc, nombre)
    d = fn(desde, hasta)
    return render_template(f"informe_{nombre}.html", d=d, charts=charts, items=disponibles(), actual=nombre)
