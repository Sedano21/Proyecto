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


TIPOS = ("MP", "PT")  # V74: la etiqueta es solo para materia prima y producto terminado
MARCAS = ["Cantaclaro", "Cosecha Andina"]  # V74: sugeridas; la marca es opcional


def productos():
    return list(db().execute(select(Product).where(Product.tipo.in_(TIPOS)).order_by(Product.code)).scalars())


def _cliente(customer_id):
    """Acepta el id o el texto «nombre · RUC» elegido de la lista que filtra al escribir."""
    v = str(customer_id or "").strip()
    if not v:
        return None
    if v.isdigit():
        return int(v)
    partes = [x.strip() for x in v.split(" · ")]
    c = None
    if len(partes) > 1 and partes[-1]:
        c = db().execute(select(Customer).where(Customer.ruc == partes[-1])).scalars().first()
    if c is None:
        c = db().execute(select(Customer).where(Customer.nombre == partes[0])).scalars().first()
    if c is None:
        raise BusinessError("Elija el cliente de la lista (escriba y seleccione).")
    return c.id


def guardar(user, product_code, customer_id=None, marca="", instrucciones="", foto="", eid=None, lote="",
            fecha_vencimiento=None):
    _require(user)
    code = (product_code or "").strip().upper().split(" ")[0]
    p = db().get(Product, code)
    if p is None:
        raise BusinessError("Elija el producto de la lista.")
    if (p.tipo or "").upper() not in TIPOS:
        raise BusinessError("La etiqueta es solo para materia prima (MP) y producto terminado (PT).")
    if not (instrucciones or "").strip() and not foto:
        raise BusinessError("Indique las instrucciones de la etiqueta o suba su foto.")
    cid = _cliente(customer_id)
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
    e.lote = (lote or "").strip()[:60]
    if isinstance(fecha_vencimiento, str):
        from datetime import date
        try:
            fecha_vencimiento = date.fromisoformat(fecha_vencimiento[:10]) if fecha_vencimiento.strip() else None
        except ValueError:
            raise BusinessError("Fecha de vencimiento no válida.") from None
    e.fecha_vencimiento = fecha_vencimiento
    e.activa = True
    e.user_id = user.id
    db().flush()
    audit(user, "ETIQUETA_GUARDADA", "LabelSpec", e.id, {"producto": code, "cliente": cid, "marca": e.marca, "lote": e.lote,
                                                         "vence": e.fecha_vencimiento})
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
