"""V17 (02-nov-2026): expedientes agrupados por cliente y despacho, nivel de servicio del mes con su detalle y
desempeño de los equipos operativos."""
from datetime import date

from flask import Blueprint, abort, g, render_template, request
from sqlalchemy import select

from ..db import db
from ..models import Customer, User
from ..services import seguimiento as seg
from .common import f_date, perm_required

bp = Blueprint("seg", __name__, url_prefix="/seguimiento")


@bp.route("/expedientes")
@perm_required("expedientes.ver")
def groups():
    vend = request.args.get("vendedor") or (str(g.user.id) if g.user.role_code == "EJECUTIVO_VENTAS" else "")
    grupos = seg.groups(f_date("desde"), f_date("hasta"), request.args.get("cliente") or None, vend or None)
    clientes = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    vendedores = list(db().execute(select(User).where(User.role_code == "EJECUTIVO_VENTAS").order_by(User.nombre)).scalars())
    return render_template("seg_expedientes.html", grupos=grupos, clientes=clientes, vendedores=vendedores,
                           f=request.args, vend=vend)


@bp.route("/expedientes/<int:cid>/<fecha>")
@perm_required("expedientes.ver")
def group(cid, fecha):
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        abort(404)
    c = db().get(Customer, cid) or abort(404)
    ovs = seg.group_detail(cid, f)
    from ..services.finance import order_documents
    modo = request.args.get("certificados", "producto")
    return render_template("seg_expediente.html", c=c, fecha=f, ovs=ovs, docs={o.id: order_documents(o) for o in ovs},
                           avance={o.id: seg.progress(o) for o in ovs}, area={o.id: seg.order_area(o) for o in ovs},
                           retraso={o.id: seg.delay(o) for o in ovs}, certs=seg.group_certificates(ovs, modo != "consolidado"),
                           modo=modo, imprimir=request.args.get("imprimir") == "1")


@bp.route("/servicio")
@perm_required("indicadores.servicio", "informes.comercial")
def service():
    d = seg.service_month(f_date("mes") or None, request.args.get("cliente") or None, request.args.get("vendedor") or None)
    ver = request.args.get("ver", "")
    filas = d["filas"]
    filtros = {"otif_no": lambda x: not x["otif"], "otif_si": lambda x: x["otif"],
               "tarde": lambda x: x["salio"] and not x["a_tiempo"], "incompletas": lambda x: x["salio"] and not x["completo"],
               "pendientes": lambda x: not x["salio"]}
    if ver in filtros:
        filas = [x for x in filas if filtros[ver](x)]
    clientes = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    return render_template("seg_servicio.html", d=d, filas=filas, ver=ver, f=request.args, clientes=clientes)


@bp.route("/desempeno")
@perm_required("desempeno.equipo")
def performance():
    hoy = date.today()
    desde, hasta = f_date("desde") or hoy, f_date("hasta") or hoy
    if hasta < desde:
        desde, hasta = hasta, desde
    from ..services.attendance import visible_areas
    areas = visible_areas(g.user)
    tiempos = seg.response_times(f_date("t_desde"), f_date("t_hasta"))
    equipo = seg.team_performance(desde, hasta, None if areas is None or g.user.role_code in ("JEFE_OPERACIONES",) else
                                  (areas | {"Almacén", "Distribución"} if g.user.role.area == "Logística" else areas))
    return render_template("seg_desempeno.html", tiempos=tiempos, equipo=equipo, f=request.args)
