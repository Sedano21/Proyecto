"""Ficha de cliente (observaciones al demo v0.5, 13-oct): datos, lugares de entrega, contacto, condiciones, penalidades
y comportamiento de compra. Los datos también se cargan desde el maestro de clientes exportado de SAP."""
from collections import Counter, defaultdict
from statistics import mean

from sqlalchemy import select

from ..db import db
from ..models import Customer, CustomerSite, Incident, SalesOrder
from .core import BusinessError, audit, has_perm

CAMPOS = ("nombre", "grupo", "direccion", "distrito", "provincia", "horario_recepcion", "contacto", "telefono", "correo",
          "codigo_sap", "observaciones")


def _require(user):
    if not (has_perm(user, "ov.crear") or has_perm(user, "config.editar")):
        raise BusinessError("Su rol no edita clientes.")


def save_customer(user, c, datos):
    _require(user)
    nuevo = c is None
    if nuevo:
        ruc = (datos.get("ruc") or "").strip()
        if not ruc.isdigit() or len(ruc) not in (8, 11):
            raise BusinessError("RUC (11 dígitos) o DNI (8 dígitos) obligatorio.")
        if db().execute(select(Customer).where(Customer.ruc == ruc)).scalars().first():
            raise BusinessError("El RUC ya existe.")
        c = Customer(ruc=ruc, nombre="")
        db().add(c)
    for k in CAMPOS:
        if k in datos and datos[k] is not None:
            setattr(c, k, str(datos[k]).strip())
    if "canal_precio" in datos and (datos.get("canal_precio") or "") != (c.canal_precio or ""):
        if not has_perm(user, "clientes.canal"):
            raise BusinessError("El canal de precios del cliente lo asigna el Jefe Comercial o Sistemas.")
        audit(user, "CLIENTE_CANAL", "Customer", c.ruc, {"antes": c.canal_precio, "despues": datos["canal_precio"]})
        c.canal_precio = (datos["canal_precio"] or "").strip()
    if "requiere_cita" in datos:
        c.requiere_cita = str(datos["requiere_cita"]) in ("1", "true", "True", "on")
    if "vida_util_min_dias" in datos:
        v = str(datos.get("vida_util_min_dias") or "").strip()
        c.vida_util_min_dias = int(v) if v else None
    if c.correo and "@" not in c.correo:
        raise BusinessError("Correo inválido.")
    if not c.nombre:
        raise BusinessError("Nombre obligatorio.")
    db().flush()
    audit(user, "CLIENTE_GUARDADO", "Customer", c.ruc, {"nuevo": nuevo})
    return c


def save_site(user, c, datos, site=None):
    _require(user)
    if site is None:
        site = CustomerSite(customer_id=c.id, nombre="")
        db().add(site)
    for k in ("nombre", "direccion", "distrito", "provincia", "referencia", "horario_recepcion", "contacto", "telefono"):
        if k in datos:
            setattr(site, k, (datos.get(k) or "").strip())
    if "activo" in datos:
        site.activo = str(datos["activo"]) in ("1", "on", "true")
    if not site.nombre or not site.direccion or not site.distrito or not site.provincia:
        raise BusinessError("Nombre, dirección, distrito y provincia del lugar de entrega son obligatorios.")
    db().flush()
    audit(user, "CLIENTE_LUGAR_GUARDADO", "Customer", c.ruc, {"lugar": site.nombre})
    return site


def profile(c):
    """Indicadores de compra del cliente a partir de sus OV en el sistema."""
    from .orders import order_amount, order_weight_kg
    ovs = list(db().execute(select(SalesOrder).where(SalesOrder.customer_id == c.id).order_by(SalesOrder.fecha_emision)).scalars())
    validas = [o for o in ovs if o.estado != "CANCELADA"]
    fechas = sorted({o.fecha_emision for o in validas if o.fecha_emision})
    gaps = [(b - a).days for a, b in zip(fechas, fechas[1:])]
    prods = Counter()
    soles_prod = defaultdict(float)
    for o in validas:
        for l in o.lines:
            if l.activa:
                prods[l.product_code] += l.cantidad
                soles_prod[l.product_code] += l.cantidad * (l.precio_unitario or 0)
    incompletas = [o for o in validas if o.estado in ("DESPACHADA", "ENTREGADA") and any(
        l.activa and l.despachado + 1e-9 < l.cantidad for l in o.lines)]
    incid = list(db().execute(select(Incident).join(SalesOrder, Incident.order_id == SalesOrder.id)
                              .where(SalesOrder.customer_id == c.id).order_by(Incident.id.desc())).scalars())
    return {"ovs": list(reversed(ovs))[:50], "n": len(validas), "soles": sum(order_amount(o) for o in validas),
            "kg": sum(order_weight_kg(o, "solicitado")[0] for o in validas),
            "ticket": mean([order_amount(o) for o in validas]) if validas else 0,
            "ultima": fechas[-1] if fechas else None, "frecuencia_dias": round(mean(gaps), 1) if gaps else None,
            "top": [(k, q, soles_prod[k]) for k, q in prods.most_common(10)], "incompletas": len(incompletas),
            "incidencias": incid[:20]}
