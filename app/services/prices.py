"""Listas de precios (decisión Q11 del 13-oct-2026).

- Se cargan desde los Excel actuales: PRICE_LIST (precio por canal; columnas MAYORISTA, INSTITUCIONAL, …) y
  PRICE_LIST_GRANEL (precio por kg y por saco). Si una celda de precio es fórmula sin valor calculado, se recalcula como
  en el Excel: costo / (1 − margen del canal) o precio por saco / kg por saco. El costo no se guarda.
- Solo el Jefe Comercial (permiso exclusivo 'precios.editar') carga o modifica precios; cada cambio queda versionado y
  auditado.
- La lista es el PRECIO MÍNIMO de venta por canal: el precio de la OV se negocia con el cliente y no puede estar por
  debajo. Al registrar, importar o modificar una OV, cada línea (incluidas las muestras comerciales) se compara con el
  mínimo del canal del cliente; si está en el límite o por debajo, se alerta y la OV queda DETENIDA hasta que el
  Coordinador Comercial o el Jefe Comercial la confirme. El sistema no cambia el precio de la OV.
- El canal de precios del cliente lo asigna el Jefe Comercial (o Sistemas) en Configuración → Clientes; si no está
  asignado se deduce del grupo de cliente de SAP. Los clientes del canal granel usan la lista mayorista granel (mínimo
  por kg y por saco); los demás, la lista por canal (presentaciones).
- Productos sin precio mínimo o clientes sin canal generan una alerta para completar la lista (no detienen la OV).
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


def channel_of(customer):
    if customer is None:
        return ""
    if customer.canal_precio:
        return customer.canal_precio
    return (param("canal_precio_por_grupo", {}) or {}).get((customer.grupo or "").strip().upper(), "")


def minimum_for(product, customer):
    """Mínimo aplicable: dict(tipo='GENERAL', precio, canal) o dict(tipo='GRANEL', precio_kg, precio_saco, kg_saco),
    o (None, motivo) si no hay."""
    if product is None or customer is None:
        return None, "producto o cliente no identificado"
    canal = channel_of(customer)
    if not canal:
        return None, f"el cliente {customer.nombre} (grupo '{customer.grupo or '-'}') no tiene canal de precios asignado"
    s = db()
    if canal in (param("lista_granel_canales", []) or []):
        g = s.execute(select(PriceItem).where(PriceItem.lista == "GRANEL", PriceItem.vigente.is_(True),
                                              PriceItem.product_code == product.code)).scalars().first()
        if g is None or not (g.precio_kg or g.precio_saco):
            return None, f"{product.code} no figura en la lista mayorista granel"
        return {"tipo": "GRANEL", "canal": canal, "precio_kg": g.precio_kg, "precio_saco": g.precio_saco,
                "kg_saco": g.kg_saco}, ""
    it = s.execute(select(PriceItem).where(PriceItem.lista == "GENERAL", PriceItem.vigente.is_(True),
                                           PriceItem.product_code == product.code, PriceItem.canal == canal)).scalars().first()
    if it is None or not it.precio:
        return None, f"{product.code} no tiene precio mínimo para el canal {canal}"
    return {"tipo": "GENERAL", "canal": canal, "precio": it.precio}, ""


def price_for(product, customer):
    """(mínimo de referencia en la unidad de venta, descripción) o (None, motivo)."""
    m, motivo = minimum_for(product, customer)
    if m is None:
        return None, "Sin precio mínimo: " + motivo
    if m["tipo"] == "GENERAL":
        return m["precio"], f"Lista de precios, canal {m['canal']}"
    if _es_kg(product):
        return m["precio_kg"], "Lista mayorista granel (por kg)"
    return m["precio_saco"], "Lista mayorista granel (por saco)"


def _compare(line, product, m, margen):
    """Devuelve (estado, detalle). estado: SOBRE / LIMITE / DEBAJO. En granel compara por kg y por saco (ambos)."""
    pv = line.precio_unitario or 0
    checks = []
    if m["tipo"] == "GENERAL":
        checks.append(("unidad", pv, m["precio"]))
    else:
        kg_saco = m.get("kg_saco") or 0
        if _es_kg(product):
            pkg, psaco = pv, pv * kg_saco if kg_saco else None
        else:
            psaco, pkg = pv, (pv / kg_saco if kg_saco else None)
        if m.get("precio_kg") and pkg is not None:
            checks.append(("kg", pkg, m["precio_kg"]))
        if m.get("precio_saco") and psaco is not None:
            checks.append(("saco", psaco, m["precio_saco"]))
    estado = "SOBRE"
    partes = []
    for nombre, v, minimo in checks:
        if v < minimo - 1e-9:
            e = "DEBAJO"
        elif v <= minimo * (1 + margen / 100.0) + 1e-9:
            e = "LIMITE"
        else:
            e = "SOBRE"
        partes.append(f"por {nombre}: {v:.4f} vs mínimo {minimo:.4f}")
        if e == "DEBAJO" or (e == "LIMITE" and estado == "SOBRE"):
            estado = e
    return estado, "; ".join(partes)


ESTADO_TXT = {"DEBAJO": "POR DEBAJO del mínimo", "LIMITE": "EN EL LÍMITE del mínimo", "SOBRE": "Sobre el mínimo"}


def check_order_prices(order, user=None):
    """Valida cada línea contra el mínimo; detiene la OV si alguna está en el límite o por debajo (incluye precio 0,
    p. ej. muestras comerciales) y alerta. Productos o clientes sin mínimo generan PRECIO_FALTANTE."""
    from . import alerts
    margen = float(param("margen_alerta_precio_pct", 0) or 0)
    from .costs import cost_for_line
    observadas, faltantes, bajo_costo = [], [], []
    for l in order.lines:
        if not l.activa:
            continue
        m0, _ = minimum_for(l.product, order.customer)
        costo = cost_for_line(l, (m0 or {}).get("kg_saco") if m0 else None)
        if costo is not None and (l.precio_unitario or 0) < costo - 1e-9 and l.precio_unitario:
            # R4 (13-oct): ninguna venta por debajo del costo. El texto visible en la OV no muestra el costo.
            observadas.append(f"{l.product_code}: precio de venta POR DEBAJO DEL COSTO")
            bajo_costo.append(f"{l.product_code}: {l.precio_unitario:.4f} vs costo {costo:.4f}"
                              f"{' por ' + l.um_venta.lower() if l.um_venta else ''}")
        m, motivo = m0, _
        if m is None:
            m, motivo = minimum_for(l.product, order.customer)
        if m is None:
            l.precio_minimo = None
            l.precio_origen = "Sin precio mínimo: " + motivo
            faltantes.append(motivo)
            continue
        ref, _ = price_for(l.product, order.customer)
        l.precio_minimo = ref
        estado, detalle = _compare(l, l.product, m, margen)
        sin = "" if l.precio_unitario else " (OV sin precio de venta)"
        l.precio_origen = f"{ESTADO_TXT[estado]}{sin}: {detalle} (canal {m['canal']})"
        if estado != "SOBRE":
            observadas.append(f"{l.product_code}: {ESTADO_TXT[estado].lower()}{sin} – {detalle}")
    key = f"PRECIO:{order.id}"
    tipo = f" [{order.tipo_venta}]" if order.tipo_venta else ""
    previas = list(order.precio_observado or [])
    order.precio_observado = observadas
    if observadas:
        aprobada_igual = bool(order.aprobacion_precio) and order.aprobacion_precio.get("lineas") == observadas
        if not aprobada_igual:
            order.aprobacion_precio = {}
            if param("retener_ov_bajo_minimo", True) or (bajo_costo and param("retener_ov_bajo_costo", True)):
                order.retenida_precio = True
                order.motivo_detencion = "Detenida por precio en el límite o bajo el mínimo: requiere confirmación comercial."
        if observadas != previas or not aprobada_igual:
            a = alerts.emit("OV_PRECIO_BAJO_MINIMO", f"OV {order.numero}{tipo}: precio en el límite o por debajo de la lista",
                            f"Cliente {order.customer.nombre} (canal {channel_of(order.customer) or '-'}), vendedor "
                            f"{order.vendedor_nombre or '-'}. " + "; ".join(observadas)
                            + (" La OV queda detenida hasta la confirmación del Coordinador o Jefe Comercial."
                               if order.retenida_precio else ""), "SalesOrder", order.id, dedup_key=key,
                            extra_users=[order.vendedor_id] if order.vendedor_id else None, creado_por=user)
            if a is not None and a.mensaje and "; ".join(observadas) not in a.mensaje:
                from ..models import AlertEvent
                db().add(AlertEvent(alert_id=a.id, accion="ACTUALIZADA", comentario="Precios observados: " + "; ".join(observadas)))
    else:
        if order.retenida_precio:
            order.retenida_precio = False
            if order.motivo_detencion.startswith("Detenida por precio"):
                order.motivo_detencion = ""
        alerts.close_by_system(key, "Precios sobre el mínimo de lista")
    ckey = f"COSTO:{order.id}"
    if bajo_costo:
        alerts.emit("OV_PRECIO_BAJO_COSTO", f"OV {order.numero}{tipo}: precio por debajo del costo",
                    f"Cliente {order.customer.nombre}, vendedor {order.vendedor_nombre or '-'}. " + "; ".join(bajo_costo)
                    + (" La OV queda detenida hasta la confirmación del Coordinador o Jefe Comercial."
                       if order.retenida_precio else ""), "SalesOrder", order.id, dedup_key=ckey, creado_por=user)
    else:
        alerts.close_by_system(ckey, "Precios sobre el costo")
    if faltantes:
        alerts.emit("PRECIO_FALTANTE", f"OV {order.numero}: falta precio mínimo para validar",
                    "; ".join(dict.fromkeys(faltantes)) + ". Complete la lista de precios o asigne el canal del cliente.",
                    "SalesOrder", order.id, dedup_key=f"PRECIO_FALTA:{order.id}", creado_por=user)
    else:
        alerts.close_by_system(f"PRECIO_FALTA:{order.id}", "Precio mínimo disponible")
    return observadas, faltantes


def approve_price(order, user, comentario):
    """Confirmación del Coordinador Comercial o del Jefe Comercial: libera la OV detenida por precio."""
    if not has_perm(user, "ov.aprobar_precio"):
        raise BusinessError("La OV detenida por precio la confirma el Coordinador Comercial o el Jefe Comercial.")
    if not order.retenida_precio:
        raise BusinessError("La OV no está detenida por precio.")
    if not (comentario or "").strip():
        raise BusinessError("Indique el motivo de la confirmación (venta en el límite o bajo el mínimo).")
    order.aprobacion_precio = {"user": user.nombre, "user_id": user.id, "rol": user.role_code, "ts": now().isoformat(),
                               "comentario": comentario.strip(), "lineas": list(order.precio_observado or [])}
    order.retenida_precio = False
    if order.motivo_detencion.startswith("Detenida por precio"):
        order.motivo_detencion = ""
    from . import alerts
    alerts.close_by_system(f"PRECIO:{order.id}", f"Confirmada por {user.nombre}: {comentario}")
    alerts.close_by_system(f"COSTO:{order.id}", f"Confirmada por {user.nombre}: {comentario}")
    audit(user, "OV_PRECIO_CONFIRMADO", "SalesOrder", order.numero, order.aprobacion_precio)
    # Con la aprobación recién se reserva el stock (o queda diferida si sale en más de 7 días) y se generan las
    # pre-solicitudes que correspondan (decisión del 14-oct).
    from .stock import ORDEN_ESTADOS_CERRADOS, evaluate_order
    if order.estado not in ORDEN_ESTADOS_CERRADOS:
        evaluate_order(order, user, "APROBACION_PRECIO")



def reject_price(order, user, comentario):
    """Desaprobación del precio (observaciones al demo v0.6): la OV sigue detenida, sin reservar, hasta que Comercial
    corrija el precio o la anule; el motivo es obligatorio."""
    if not has_perm(user, "ov.aprobar_precio"):
        raise BusinessError("La OV detenida por precio la resuelve el Coordinador Comercial o el Jefe Comercial.")
    if not order.retenida_precio:
        raise BusinessError("La OV no está detenida por precio.")
    if not (comentario or "").strip():
        raise BusinessError("Indique el motivo de la desaprobación.")
    order.motivo_detencion = (f"Detenida por precio: desaprobado por {user.nombre} ({comentario.strip()}). "
                              "Corrija el precio o anule la OV; no se reserva stock.")
    from . import alerts
    alerts.close_by_system(f"PRECIO:{order.id}", f"Desaprobada por {user.nombre}: {comentario}")
    alerts.close_by_system(f"COSTO:{order.id}", f"Desaprobada por {user.nombre}: {comentario}")
    audit(user, "OV_PRECIO_DESAPROBADO", "SalesOrder", order.numero, {"comentario": comentario.strip()})

def add_item(user, lista, product_code, descripcion="", canal="", precio=None, precio_kg=None, precio_saco=None,
             kg_saco=None, motivo=""):
    """El Jefe Comercial completa un precio faltante (alerta PRECIO_FALTANTE)."""
    _require(user)
    code = (product_code or "").strip().upper()
    if not code:
        raise BusinessError("Indique el SKU.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo.")
    if lista == "GENERAL":
        if not canal or not precio or precio <= 0:
            raise BusinessError("Indique canal y precio mínimo.")
    else:
        if not precio_saco or not kg_saco or precio_saco <= 0 or kg_saco <= 0:
            raise BusinessError("Indique precio por saco y kg por saco.")
        precio_kg = precio_kg or precio_saco / kg_saco
        canal = ""
    s = db()
    if s.execute(select(PriceItem).where(PriceItem.lista == lista, PriceItem.product_code == code, PriceItem.canal == canal,
                                         PriceItem.vigente.is_(True))).scalars().first():
        raise BusinessError("Ese precio ya existe: modifíquelo en la lista.")
    from ..models import Product
    p = s.get(Product, code)
    it = PriceItem(lista=lista, product_code=code, descripcion=descripcion or (p.descripcion if p else ""), canal=canal,
                   precio=precio, precio_kg=precio_kg, precio_saco=precio_saco, kg_saco=kg_saco, origen="Alta manual",
                   motivo=motivo.strip(), user_id=user.id)
    s.add(it)
    s.flush()
    audit(user, "PRECIO_AGREGADO", "PriceItem", f"{lista}:{code}:{canal}", {"precio": precio, "precio_saco": precio_saco})
    return it


def set_validity(user, lista, desde=None, hasta=None, archivo=None):
    _require(user)
    from ..models import PriceListMeta
    m = db().get(PriceListMeta, lista) or PriceListMeta(lista=lista)
    db().add(m)
    if desde is not None:
        m.vigencia_desde = desde
    m.vigencia_hasta = hasta
    if archivo:
        m.archivo = archivo
    m.user_id = user.id
    m.ts = now()
    audit(user, "LISTA_PRECIOS_VIGENCIA", "PriceListMeta", lista, {"desde": m.vigencia_desde, "hasta": hasta})
    return m


def check_validity(today):
    """Avisa (no bloquea) si una lista venció o está por vencer."""
    from datetime import timedelta
    from ..models import PriceListMeta
    from . import alerts
    aviso = int(param("aviso_vencimiento_lista_dias", 7) or 0)
    n = 0
    for m in db().execute(select(PriceListMeta)).scalars():
        if m.vigencia_hasta and m.vigencia_hasta <= today + timedelta(days=aviso):
            estado = "venció" if m.vigencia_hasta < today else "vence"
            alerts.emit("LISTA_PRECIOS_VENCIDA", f"La lista de precios {m.lista} {estado} el {m.vigencia_hasta:%d/%m/%Y}",
                        f"Archivo {m.archivo or '-'}. Sigue en uso hasta que se actualice o se amplíe la vigencia.",
                        "PriceListMeta", m.lista, dedup_key=f"LISTA_VENC:{m.lista}:{m.vigencia_hasta}")
            n += 1
    return n
