"""V66 (marcha blanca almacén): etiquetas que Calidad indica para el despacho (p. ej. producto con marca de terceros).

Calidad registra, por producto y, si aplica, por cliente: la marca, las instrucciones (qué etiqueta, cuántas por bulto,
dónde va) y la foto de la etiqueta. En el picking se muestran las de los productos y el cliente de la OV, para que
Almacén las pegue sin esperar a Calidad. El procedimiento detallado lo define Calidad.
"""
from sqlalchemy import or_, select

from ..db import db
from ..models import Customer, LabelSpec, Product
from .core import BusinessError, audit, has_perm


def _require(user):
    if not has_perm(user, "calidad.etiquetas"):
        raise BusinessError("Registra las etiquetas Calidad.")


def guardar(user, product_code, customer_id=None, marca="", instrucciones="", foto="", eid=None):
    _require(user)
    code = (product_code or "").strip().upper().split(" ")[0]
    if db().get(Product, code) is None:
        raise BusinessError("Elija el producto de la lista.")
    if not (instrucciones or "").strip() and not foto:
        raise BusinessError("Indique las instrucciones de la etiqueta o suba su foto.")
    cid = int(customer_id) if str(customer_id or "").isdigit() else None
    if cid and db().get(Customer, cid) is None:
        raise BusinessError("Cliente no válido.")
    e = db().get(LabelSpec, int(eid)) if eid else None
    if e is None:
        e = LabelSpec(product_code=code)
        db().add(e)
    e.product_code, e.customer_id = code, cid
    e.marca = (marca or "").strip()[:120]
    e.instrucciones = (instrucciones or "").strip()
    if foto:
        e.foto = foto
    e.activa = True
    e.user_id = user.id
    db().flush()
    audit(user, "ETIQUETA_GUARDADA", "LabelSpec", e.id, {"producto": code, "cliente": cid, "marca": e.marca})
    return e


def desactivar(user, e):
    _require(user)
    e.activa = False
    audit(user, "ETIQUETA_DESACTIVADA", "LabelSpec", e.id, {})


def listar():
    return list(db().execute(select(LabelSpec).where(LabelSpec.activa.is_(True))
                             .order_by(LabelSpec.product_code, LabelSpec.id)).scalars())


def para_orden(order):
    """Etiquetas de los productos de la OV: las generales del producto y las del cliente de la OV."""
    if order is None:
        return []
    codes = [l.product_code for l in order.lines if l.activa]
    if not codes:
        return []
    return list(db().execute(select(LabelSpec).where(
        LabelSpec.activa.is_(True), LabelSpec.product_code.in_(codes),
        or_(LabelSpec.customer_id.is_(None), LabelSpec.customer_id == order.customer_id))
        .order_by(LabelSpec.product_code)).scalars())
