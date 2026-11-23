"""V66 (marcha blanca almacén, 20-nov-2026).

1. Consolidado del picking: lo que se debe preparar por sede (lugar de entrega), fecha de despacho, cliente, producto y
   almacén, con la suma por producto (como la tabla dinámica que hoy arma Almacén a mano). Varias OV de un mismo cliente
   para la misma fecha (p. ej. varias sedes) se suman por producto. Se descarga en PDF o Excel.
2. Pedidos grandes de última hora: si una OV para hoy o mañana se registra (o se le aumenta la cantidad) después de la
   hora configurada y supera la cantidad configurada, queda «por validar» por Almacén (Líder, Asistente o Coordinador)
   antes de prepararla. Almacén la valida u observa con motivo; Comercial recibe la respuesta.
"""
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import SalesOrder, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

ABIERTAS = ("REGISTRADA", "EVALUADA", "EN_PREPARACION", "PREPARADA", "PROGRAMADA", "BLOQUEADA", "DESPACHO_PARCIAL")


def consolidado(desde=None, hasta=None, cliente_id=None, producto="", almacen="", sede="", agrupar="cliente"):
    """Filas (OV × línea) pendientes de preparar y la suma por grupo. agrupar: cliente / fecha / sede / producto / almacen."""
    from .orders import kg_unidad
    from .stock import line_reserved
    hoy = date.today()
    desde = desde or hoy
    hasta = hasta or desde + timedelta(days=2)
    q = select(SalesOrder).where(SalesOrder.fecha_compromiso >= desde, SalesOrder.fecha_compromiso <= hasta,
                                 SalesOrder.estado.in_(ABIERTAS))
    if cliente_id:
        q = q.where(SalesOrder.customer_id == int(cliente_id))
    filas = []
    for o in db().execute(q.order_by(SalesOrder.fecha_compromiso, SalesOrder.id)).scalars():
        lugar = (o.lugar_entrega or o.distrito or o.direccion or "-").strip()
        if sede and sede.upper() not in lugar.upper():
            continue
        for l in o.lines:
            if not l.activa:
                continue
            pend = max(0.0, (l.cantidad or 0) - (l.despachado or 0))
            if pend <= 1e-9:
                continue
            if producto and producto.upper() not in (l.product_code + " " + (l.product.descripcion if l.product else "")).upper():
                continue
            almacenes = sorted({r.lot.warehouse_code for r in l.reservations if r.estado == "ACTIVA" and r.lot}) or ["(sin reserva)"]
            alm = ", ".join(almacenes)
            if almacen and almacen not in almacenes:
                continue
            filas.append({"o": o, "fecha": o.fecha_compromiso, "cliente": o.customer.nombre if o.customer else "-",
                          "sede": lugar, "codigo": l.product_code, "descripcion": l.product.descripcion if l.product else "",
                          "almacen": alm, "cantidad": round(pend, 4), "preparado": round(l.preparado or 0, 4),
                          "reservado": round(line_reserved(l), 4), "kg": round(pend * kg_unidad(l.product), 2),
                          "um": "KG" if l.product and (l.product.um or "").upper().startswith("K") else "UND"})
    clave = {"cliente": lambda f: (f["cliente"], f["fecha"]), "fecha": lambda f: (f["fecha"],),
             "sede": lambda f: (f["sede"], f["fecha"]), "producto": lambda f: (f["codigo"],),
             "almacen": lambda f: (f["almacen"], f["fecha"])}.get(agrupar) or (lambda f: (f["cliente"], f["fecha"]))
    grupos = OrderedDict()
    for f in sorted(filas, key=lambda f: tuple(str(x) for x in clave(f)) + (f["codigo"],)):
        g = grupos.setdefault(clave(f), {"clave": clave(f), "productos": OrderedDict(), "ovs": set(), "kg": 0.0})
        p = g["productos"].setdefault(f["codigo"], {"codigo": f["codigo"], "descripcion": f["descripcion"], "um": f["um"],
                                                     "cantidad": 0.0, "kg": 0.0, "ovs": set(), "sedes": set(), "almacen": set()})
        p["cantidad"] += f["cantidad"]
        p["kg"] += f["kg"]
        p["ovs"].add(f["o"].numero)
        p["sedes"].add(f["sede"])
        p["almacen"].update(x.strip() for x in f["almacen"].split(","))
        g["ovs"].add(f["o"].numero)
        g["kg"] += f["kg"]
    total = defaultdict(lambda: {"cantidad": 0.0, "kg": 0.0, "descripcion": "", "um": ""})
    for f in filas:
        t = total[f["codigo"]]
        t["cantidad"] += f["cantidad"]
        t["kg"] += f["kg"]
        t["descripcion"], t["um"] = f["descripcion"], f["um"]
    return {"desde": desde, "hasta": hasta, "filas": filas, "grupos": list(grupos.values()), "agrupar": agrupar,
            "total": sorted(total.items()), "kg": round(sum(f["kg"] for f in filas), 2),
            "n_ovs": len({f["o"].numero for f in filas})}


def tabla_pdf(d):
    """Columnas y filas para el PDF o Excel del consolidado (una fila por grupo y producto)."""
    nombres = {"cliente": ("Cliente", "Fecha"), "fecha": ("Fecha",), "sede": ("Sede", "Fecha"), "producto": ("Producto",),
               "almacen": ("Almacén", "Fecha")}[d["agrupar"]]
    cols = list(nombres) + ["Código", "Descripción", "Cantidad", "UM", "Kg", "OV", "Sedes", "Almacén"]
    filas = []
    for g in d["grupos"]:
        cab = [x.strftime("%d/%m/%Y") if isinstance(x, date) else str(x) for x in g["clave"]]
        for p in g["productos"].values():
            filas.append(cab + [p["codigo"], p["descripcion"], f"{p['cantidad']:,.2f}", p["um"], f"{p['kg']:,.2f}",
                                ", ".join(sorted(p["ovs"])), ", ".join(sorted(p["sedes"])), ", ".join(sorted(p["almacen"]))])
    return cols, filas


# ------------------------------------------------------------------ pedidos grandes de última hora
def _unidades(o):
    return sum(max(0.0, (l.cantidad or 0) - (l.despachado or 0)) for l in o.lines if l.activa)


def revisar_tardia(order, user=None, motivo="REGISTRO", ahora=None):
    """Marca la OV por validar por Almacén si es un pedido grande de última hora. Devuelve True si quedó por validar."""
    if not param("almacen_ov_tardia_activa", True) or order.origen != "MODULO":
        return False
    if (order.validacion_almacen or {}).get("estado") in ("PENDIENTE", "VALIDADA"):
        return False
    ahora = ahora or datetime.now()
    hoy = ahora.date()
    if not order.fecha_compromiso or not (hoy <= order.fecha_compromiso <= hoy + timedelta(days=1)):
        return False
    hora = str(param("almacen_ov_tardia_hora", "09:00") or "09:00")[:5]
    if ahora.strftime("%H:%M") < hora and order.fecha_compromiso > hoy:
        return False  # para mañana, registrada temprano: no es de última hora
    umbral = float(param("almacen_ov_tardia_unidades", 500) or 0)
    q = _unidades(order)
    if q <= umbral:
        return False
    order.validacion_almacen = {"estado": "PENDIENTE", "motivo": motivo, "unidades": q,
                                "ts": now().isoformat(timespec="seconds"), "por": user.nombre if user else ""}
    alerts.emit("OV_VALIDAR_ALMACEN", f"OV {order.numero}: pedido grande de última hora por validar",
                f"{order.customer.nombre if order.customer else ''}: {q:,.0f} unidades/kg para el "
                f"{order.fecha_compromiso:%d/%m}. Valide (o observe) antes de prepararla.", "SalesOrder", order.id,
                dedup_key=f"OV_VAL_ALM:{order.id}", creado_por=user)
    audit(user, "OV_VALIDACION_ALMACEN_PEDIDA", "SalesOrder", order.numero, {"unidades": q, "motivo": motivo})
    return True


def pendiente(order):
    return (order.validacion_almacen or {}).get("estado") == "PENDIENTE"


def validar(user, order, aprobar, comentario=""):
    if not has_perm(user, "almacen.validar_ov_tardia"):
        raise BusinessError("Validan el Líder, el Asistente o el Coordinador de Almacén.")
    if not pendiente(order):
        raise BusinessError("La OV no está por validar por Almacén.")
    if not aprobar and not (comentario or "").strip():
        raise BusinessError("Indique el motivo de la observación.")
    v = dict(order.validacion_almacen or {})
    v.update({"estado": "VALIDADA" if aprobar else "OBSERVADA", "comentario": (comentario or "").strip(),
              "user": user.nombre, "user_id": user.id, "ts_resp": now().isoformat(timespec="seconds")})
    order.validacion_almacen = v
    alerts.close_by_system(f"OV_VAL_ALM:{order.id}", "Validada por Almacén" if aprobar else "Observada por Almacén")
    alerts.emit("OV_ESTADO", f"OV {order.numero}: Almacén {'validó' if aprobar else 'observó'} el pedido de última hora",
                (comentario or "").strip() or "Se prepara según lo programado.", "SalesOrder", order.id,
                extra_users=[order.vendedor_id] if order.vendedor_id else None, creado_por=user)
    audit(user, "OV_VALIDACION_ALMACEN", "SalesOrder", order.numero, {"aprobar": aprobar, "comentario": comentario})
    return v


def por_validar():
    return [o for o in db().execute(select(SalesOrder).where(SalesOrder.estado.in_(ABIERTAS))
                                    .order_by(SalesOrder.fecha_compromiso)).scalars() if pendiente(o)]
