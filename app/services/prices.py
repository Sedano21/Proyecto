"""Listas de precios (decisión Q11 del 13-oct-2026).

- Se cargan desde los Excel actuales: PRICE_LIST (precio por canal; columnas MAYORISTA, INSTITUCIONAL, …) y
  PRICE_LIST_GRANEL (precio por kg y por saco). Si una celda de precio es fórmula sin valor calculado, se recalcula como
  en el Excel: costo / (1 − margen del canal) o precio por saco / kg por saco. El costo no se guarda.
- Solo el Jefe Comercial (permiso exclusivo 'precios.editar') carga o modifica precios; cada cambio queda versionado y
  auditado.
- La lista es el PRECIO MÍNIMO de venta por canal (aclaración del 13-oct-2026): los ejecutivos de venta o responsables de
  canal deben vender por encima. Al registrar, importar o modificar una OV, cada línea se compara con el mínimo del canal
  del cliente (grupo de cliente → columna, parámetro 'canal_precio_por_grupo') y, si el precio está en el límite o por
  debajo, se alerta al vendedor y a Comercial (OV_PRECIO_BAJO_MINIMO). El sistema no cambia el precio de la OV.
- La fecha de vencimiento de la OV es la fecha comprometida de despacho.
"""
from sqlalchemy import select

from ..db import db
from ..models import PriceItem, now
from .core import BusinessError, audit, has_perm, param


def _require(user):
    if not has_perm(user, "precios.editar"):
        raise BusinessError("Solo el Jefe Comercial puede cargar o modificar precios (Q11).")


def vigentes(lista=None, texto="", canal=""):
    q = select(PriceItem).where(PriceItem.vigente.is_(True))
    if lista:
        q = q.where(PriceItem.lista == lista)
    if canal:
        q = q.where(PriceItem.canal == canal)
    rows = list(db().execute(q.order_by(PriceItem.lista, PriceItem.product_code, PriceItem.canal)).scalars())
    if texto:
        t = texto.upper()
        rows = [r for r in rows if t in r.product_code.upper() or t in (r.descripcion or "").upper()]
    return rows


def canales():
    return sorted({c for c in db().execute(select(PriceItem.canal).where(PriceItem.vigente.is_(True),
                                                                         PriceItem.lista == "GENERAL")).scalars() if c})


def replace_list(lista, items, user, origen):
    """Reemplaza la lista completa (carga de archivo). items: dicts con product_code, descripcion, canal, precio… ."""
    _require(user)
    s = db()
    ts = now()
    anteriores = {(i.product_code, i.canal): i for i in s.execute(select(PriceItem).where(
        PriceItem.lista == lista, PriceItem.vigente.is_(True))).scalars()}
    cambios = nuevos = 0
    for it in items:
        old = anteriores.pop((it["product_code"], it.get("canal", "")), None)
        if old is not None:
            iguales = all(abs((getattr(old, k) or 0) - (it.get(k) or 0)) < 1e-9 for k in ("precio", "precio_kg", "precio_saco", "kg_saco"))
            if iguales:
                old.descripcion = it.get("descripcion") or old.descripcion
                continue
            old.vigente, old.hasta = False, ts
            cambios += 1
        else:
            nuevos += 1
        s.add(PriceItem(lista=lista, product_code=it["product_code"], descripcion=it.get("descripcion", ""),
                        canal=it.get("canal", ""), precio=it.get("precio"), precio_kg=it.get("precio_kg"),
                        precio_saco=it.get("precio_saco"), kg_saco=it.get("kg_saco"), desde=ts, origen=origen,
                        user_id=user.id))
    retirados = 0
    for old in anteriores.values():
        old.vigente, old.hasta = False, ts
        retirados += 1
    audit(user, "LISTA_PRECIOS_CARGADA", "PriceItem", lista, {"origen": origen, "nuevos": nuevos, "modificados": cambios,
                                                              "retirados": retirados})
    return {"nuevos": nuevos, "modificados": cambios, "retirados": retirados}


def edit_item(item, user, motivo="", **valores):
    """Modificación puntual de un precio por el Jefe Comercial (versión nueva; la anterior queda en el historial)."""
    _require(user)
    if not item.vigente:
        raise BusinessError("Solo se modifica la versión vigente.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo del cambio de precio.")
    campos = {k: v for k, v in valores.items() if k in ("precio", "precio_kg", "precio_saco", "kg_saco") and v is not None}
    if not campos:
        raise BusinessError("Indique el nuevo precio.")
    if any(v <= 0 for v in campos.values()):
        raise BusinessError("El precio debe ser mayor que cero.")
    ts = now()
    item.vigente, item.hasta = False, ts
    nuevo = PriceItem(lista=item.lista, product_code=item.product_code, descripcion=item.descripcion, canal=item.canal,
                      precio=item.precio, precio_kg=item.precio_kg, precio_saco=item.precio_saco, kg_saco=item.kg_saco,
                      desde=ts, origen="Edición manual", motivo=motivo.strip(), user_id=user.id)
    for k, v in campos.items():
        setattr(nuevo, k, v)
    if item.lista == "GRANEL" and "precio_saco" in campos and "precio_kg" not in campos and nuevo.kg_saco:
        nuevo.precio_kg = nuevo.precio_saco / nuevo.kg_saco
    db().add(nuevo)
    db().flush()
    audit(user, "PRECIO_MODIFICADO", "PriceItem", f"{item.lista}:{item.product_code}:{item.canal}",
          {"antes": {k: getattr(item, k) for k in campos}, "despues": campos, "motivo": motivo})
    return nuevo


def history(product_code):
    return list(db().execute(select(PriceItem).where(PriceItem.product_code == product_code)
                             .order_by(PriceItem.lista, PriceItem.canal, PriceItem.desde.desc())).scalars())


def _es_kg(product):
    um = ((product.um if product else "") or "").upper()
    return um.startswith("K")


def price_for(product, customer):
    """(precio, origen) para una línea de OV, o (None, motivo) si no hay precio."""
    if product is None or customer is None:
        return None, "Sin precio: producto o cliente no identificado"
    grupo = (customer.grupo or "").strip().upper()
    canal = (param("canal_precio_por_grupo", {}) or {}).get(grupo)
    if not canal:
        return None, f"Sin precio: el grupo de cliente '{customer.grupo or '-'}' no tiene columna en la lista"
    s = db()
    if canal in (param("lista_granel_canales", []) or []):
        g = s.execute(select(PriceItem).where(PriceItem.lista == "GRANEL", PriceItem.vigente.is_(True),
                                              PriceItem.product_code == product.code)).scalars().first()
        if g is not None:
            if _es_kg(product) and g.precio_kg:
                return g.precio_kg, "Lista mayorista granel (por kg)"
            if g.precio_saco:
                return g.precio_saco, "Lista mayorista granel (por saco)"
    it = s.execute(select(PriceItem).where(PriceItem.lista == "GENERAL", PriceItem.vigente.is_(True),
                                           PriceItem.product_code == product.code, PriceItem.canal == canal)).scalars().first()
    if it is None or not it.precio:
        return None, f"Sin precio: {product.code} no figura en la lista para el canal {canal}"
    return it.precio, f"Lista de precios, canal {canal}"


def check_order_prices(order, user=None):
    """Compara el precio de venta de cada línea con el mínimo de lista y alerta si está en el límite o por debajo."""
    from . import alerts
    margen = float(param("margen_alerta_precio_pct", 0) or 0)
    observadas, sin_precio = [], []
    for l in order.lines:
        if not l.activa:
            continue
        minimo, origen = price_for(l.product, order.customer)
        l.precio_minimo = minimo
        if minimo is None:
            l.precio_origen = origen
            continue
        if not l.precio_unitario:
            l.precio_origen = f"Sin precio de venta en la OV: no se puede validar (mínimo {minimo:.4f}, {origen})"
            sin_precio.append(l.product_code)
            continue
        limite = minimo * (1 + margen / 100.0)
        if l.precio_unitario < minimo - 1e-9:
            l.precio_origen = f"POR DEBAJO del mínimo {minimo:.4f} ({origen})"
            observadas.append(f"{l.product_code}: {l.precio_unitario:.4f} < mínimo {minimo:.4f}")
        elif l.precio_unitario <= limite + 1e-9:
            l.precio_origen = f"EN EL LÍMITE del mínimo {minimo:.4f} ({origen})"
            observadas.append(f"{l.product_code}: {l.precio_unitario:.4f} en el límite (mínimo {minimo:.4f})")
        else:
            l.precio_origen = f"Sobre el mínimo {minimo:.4f} ({origen})"
    key = f"PRECIO:{order.id}"
    if observadas:
        a = alerts.emit("OV_PRECIO_BAJO_MINIMO", f"OV {order.numero}: precio en el límite o por debajo de la lista",
                        f"Cliente {order.customer.nombre} ({order.customer.grupo or '-'}), vendedor {order.vendedor_nombre or '-'}. "
                        + "; ".join(observadas), "SalesOrder", order.id, dedup_key=key,
                        extra_users=[order.vendedor_id] if order.vendedor_id else None, creado_por=user)
        if a is not None and a.mensaje and "; ".join(observadas) not in a.mensaje:
            from ..models import AlertEvent
            db().add(AlertEvent(alert_id=a.id, accion="ACTUALIZADA", comentario="Precios observados: " + "; ".join(observadas)))
    else:
        alerts.close_by_system(key, "Precios sobre el mínimo de lista")
    return observadas, sin_precio
