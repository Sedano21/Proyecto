"""Catálogo comercial (observaciones del módulo V7): carpeta por producto (ficha técnica, fotos, certificados,
recetas y estrategias), actualización de la foto principal, producto del mes / de temporada y alta de productos
(con el código de SAP: si aún no existe en SAP queda marcado para crearlo allí con el mismo código)."""
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import Product, ProductDocument, now
from .core import BusinessError, audit, has_perm

CARPETAS = {"FICHA_TECNICA": "Ficha técnica", "FOTOS": "Fotos", "CERTIFICADOS": "Certificados", "RECETAS": "Recetas",
            "ESTRATEGIAS": "Estrategias comerciales"}
DESTACADOS = {"MES": "Producto del mes", "TEMPORADA": "Producto de temporada"}


def _req(user):
    if not has_perm(user, "catalogo.fotos"):
        raise BusinessError("Su rol no actualiza el catálogo.")


def add_document(user, product, carpeta, archivo, nombre=""):
    _req(user)
    if carpeta not in CARPETAS:
        raise BusinessError("Carpeta no válida.")
    if not archivo:
        raise BusinessError("Adjunte el archivo.")
    d = ProductDocument(product_code=product.code, carpeta=carpeta, nombre=(nombre or "").strip()[:200] or archivo,
                        archivo=archivo, user_id=user.id)
    db().add(d)
    db().flush()
    if carpeta == "FOTOS" and not product.foto:
        product.foto = archivo
    audit(user, "CATALOGO_DOCUMENTO", "Product", product.code, {"carpeta": carpeta, "archivo": archivo})
    return d


def retire_document(user, doc):
    _req(user)
    doc.vigente = False
    audit(user, "CATALOGO_DOCUMENTO_RETIRADO", "Product", doc.product_code, {"carpeta": doc.carpeta, "archivo": doc.archivo})


def set_photo(user, product, archivo):
    _req(user)
    if not archivo:
        raise BusinessError("Adjunte la foto.")
    anterior = product.foto
    product.foto = archivo
    db().add(ProductDocument(product_code=product.code, carpeta="FOTOS", nombre="Foto principal", archivo=archivo,
                             user_id=user.id))
    audit(user, "CATALOGO_FOTO", "Product", product.code, {"anterior": anterior, "nueva": archivo})


def set_featured(user, product, destacado, nota="", hasta=None):
    if not (has_perm(user, "catalogo.fotos") or has_perm(user, "comercial.configurar")):
        raise BusinessError("Su rol no destaca productos del catálogo.")
    if destacado and destacado not in DESTACADOS:
        raise BusinessError("Elija producto del mes o de temporada.")
    product.destacado = destacado or ""
    product.destacado_nota = (nota or "").strip()[:200]
    product.destacado_hasta = hasta if destacado else None
    db().flush()
    audit(user, "CATALOGO_DESTACADO", "Product", product.code, {"destacado": destacado, "nota": nota, "hasta": hasta})


def featured(hoy=None):
    hoy = hoy or date.today()
    return [p for p in db().execute(select(Product).where(Product.destacado != "")).scalars()
            if not p.destacado_hasta or p.destacado_hasta >= hoy]


def documents(product):
    out = {k: [] for k in CARPETAS}
    for d in db().execute(select(ProductDocument).where(ProductDocument.product_code == product.code,
                                                        ProductDocument.vigente.is_(True))
                          .order_by(ProductDocument.ts.desc())).scalars():
        out.setdefault(d.carpeta, []).append(d)
    return out


def add_product(user, datos):
    """Alta de un producto en el catálogo con su código de SAP."""
    _req(user)
    code = (datos.get("code") or "").strip().upper()
    if not code or " " in code:
        raise BusinessError("Indique el código del producto (el mismo de SAP).")
    if db().get(Product, code) is not None:
        raise BusinessError(f"El producto {code} ya existe.")
    desc = " ".join((datos.get("descripcion") or "").split()).upper()
    if not desc:
        raise BusinessError("Indique la descripción.")
    tipo = (datos.get("tipo") or "PT").upper()
    if tipo not in ("PT", "GR", "MP"):
        raise BusinessError("Tipo no válido.")
    peso = datos.get("peso_kg")
    try:
        peso = float(peso) if peso not in (None, "") else None
    except ValueError:
        raise BusinessError("Peso inválido.")
    p = Product(code=code, descripcion=desc, tipo=tipo, um=(datos.get("um") or "UNIDAD").upper(), peso_kg=peso,
                marca=(datos.get("marca") or "").strip(), presentacion=(datos.get("presentacion") or "").strip(),
                producto_base=(datos.get("producto_base") or "").strip().upper())
    db().add(p)
    db().flush()
    audit(user, "CATALOGO_PRODUCTO_NUEVO", "Product", code, {"descripcion": desc, "tipo": tipo, "ts": now().isoformat(),
                                                             "nota": "Crear en SAP con el mismo código si aún no existe"})
    return p
