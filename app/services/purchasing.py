"""Compras nacionales (IF §10) y análisis de reposición (IF §7)."""
from collections import defaultdict
import math
from datetime import date, timedelta

from sqlalchemy import func, select

from ..db import db
from ..models import DateChange, LeadTime, Product, PurchaseRequest, SalesHistory, SalesOrder, now
from . import alerts
from .core import BusinessError, audit, check_warehouse_scope, has_perm, param
from .stock import add_or_increase_lot, free_qty, line_reserved, lot_usable, lots_of, ORDEN_ESTADOS_CERRADOS

OPEN_STATES = ("BORRADOR", "PENDIENTE_LOGISTICA", "SOLICITADA", "EN_COTIZACION", "MUESTRA_EN_CALIDAD", "PENDIENTE_APROBACION", "ORDEN_GENERADA")


def volume_value(cantidad, product=None, precio=None):
    """Valor que se compara con el umbral de mayor volumen según la unidad configurada (KG, UNIDADES o SOLES)."""
    unidad = str(param("umbral_mayor_volumen_unidad", "KG") or "KG").upper()
    if unidad == "SOLES":
        return cantidad * precio if precio else None
    if unidad == "KG":
        if product is not None and (product.um or "").upper().startswith("K"):
            return cantidad
        if product is not None and product.peso_kg:
            return cantidad * product.peso_kg
        return None
    return cantidad


def is_mayor_volumen(cantidad, product=None, precio=None):
    umbral = param("umbral_mayor_volumen")
    if umbral is None:
        return False
    v = volume_value(cantidad, product, precio)
    return v is not None and v >= float(umbral)


AGRUPABLES = ("BORRADOR", "PENDIENTE_LOGISTICA")  # presolicitudes que aún no pasan a Compras


def shortage_reason(product_code, cantidad, order=None, origen=""):
    """Motivo detallado de la presolicitud (obs. demo v0.7): quiebre de stock (libre vs requerido), plazo de reposición
    y pedidos similares abiertos del mismo producto."""
    from .stock import principal_warehouses
    p = db().get(Product, product_code)
    whs = [w.code for w in principal_warehouses(p)] if p else None
    libre = sum(free_qty(l) for l in lots_of(product_code, whs or None) if lot_usable(l)[0])
    partes = [f"Quiebre de stock de {product_code}{' ' + p.descripcion if p else ''}: libre {libre:g}, se requieren {cantidad:g} "
              f"(faltan {max(cantidad - libre, 0):g})."]
    if origen:
        partes.append(f"Origen: {origen.lower()}" + (f" de la OV {order.numero}" if order is not None else "") + ".")
    lt, modo = lead_time_for(p) if p else (None, None)
    if lt is not None:
        partes.append(f"Plazo de reposición {lt.dias_min}–{lt.dias_max} días ({modo}): llegada estimada "
                      f"{date.today() + timedelta(days=lt.dias_max):%d/%m/%Y} si se compra hoy.")
    similares = []
    for o in db().execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS),
                                                   SalesOrder.estado_stock.in_(("INCOMPLETA", "SIN_STOCK")))).scalars():
        if order is not None and o.id == order.id:
            continue
        for l in o.lines:
            if l.activa and l.product_code == product_code and l.cantidad - l.despachado - line_reserved(l) > 1e-9:
                similares.append(f"{o.numero} ({l.cantidad - l.despachado - line_reserved(l):g}, {o.fecha_compromiso:%d/%m})")
    partes.append(f"Pedidos similares con faltante del mismo producto: {', '.join(similares[:10])}"
                  + (f" y {len(similares) - 10} más" if len(similares) > 10 else "") + "." if similares
                  else "No hay otros pedidos con faltante del mismo producto.")
    return " ".join(partes)


def _orden_txt(order, cantidad):
    return {"order_id": order.id, "numero": order.numero, "cantidad": cantidad} if order is not None else None


def create_request(user, product_code, cantidad, fecha_necesidad=None, origen="ALMACEN", order=None, analisis=None,
                   enviar=True, sistema=False):
    """sistema=True: pre-solicitud automática por faltante (Q15); pasa a aprobación de Logística (Q14, obs. v0.7).
    Obs. demo v0.7: si ya hay una presolicitud abierta (aún no enviada a Compras) del mismo producto y la misma fecha de
    entrega, se agrupa en ella (suma la cantidad y registra la OV de origen) para que Compras vea una sola."""
    if origen != "REPOSICION" and not sistema and not has_perm(user, "compras.solicitar"):
        raise BusinessError("En la primera etapa las solicitudes de compra nacen en Almacén (IF §7, §10.1).")
    if db().get(Product, product_code) is None:
        raise BusinessError("Producto no existe.")
    if es_no_comprable(db().get(Product, product_code)):  # V32: el PT lo fabrica la empresa: no se compra
        raise BusinessError(f"{product_code} es producto terminado que fabrica la empresa: no se compra. Genere una "
                            "solicitud de producción. Se compra el granel y, eventualmente, MP o MQ.")
    if cantidad is None or cantidad <= 0:
        raise BusinessError("Cantidad inválida.")
    if param("agrupar_presolicitudes_compra", True):
        g = db().execute(select(PurchaseRequest).where(PurchaseRequest.product_code == product_code,
                                                       PurchaseRequest.fecha_necesidad == fecha_necesidad,
                                                       PurchaseRequest.estado.in_(AGRUPABLES))
                         .order_by(PurchaseRequest.id)).scalars().first()
        if g is not None:
            g.cantidad += cantidad
            ords = list(g.ordenes or [])
            if order is not None:
                ords.append(_orden_txt(order, cantidad))
            g.ordenes = ords
            g.mayor_volumen = is_mayor_volumen(g.cantidad, g.product)
            g.motivo = shortage_reason(product_code, g.cantidad, order, origen) + (
                f" Agrupa {len(ords)} pedido(s): " + ", ".join(f"{x['numero']} ({x['cantidad']:g})" for x in ords) + "." if ords else "")
            audit(user, "COMPRA_AGRUPADA", "PurchaseRequest", g.id, {"producto": product_code, "cantidad": cantidad,
                                                                    "ov": order.numero if order else None, "total": g.cantidad})
            alerts.close_by_system(f"COMPRA_LOG:{g.id}", "Presolicitud actualizada al agrupar otro pedido")
            if g.estado == "PENDIENTE_LOGISTICA":
                _alerta_logistica(g, user)
            return g
    r = PurchaseRequest(product_code=product_code, cantidad=cantidad, fecha_necesidad=fecha_necesidad, origen=origen,
                        order_id=order.id if order else None, analisis=analisis or {},
                        ordenes=[_orden_txt(order, cantidad)] if order is not None else [],
                        motivo=shortage_reason(product_code, cantidad, order, origen),
                        mayor_volumen=is_mayor_volumen(cantidad, db().get(Product, product_code)),
                        creado_por=user.id if user else None)
    db().add(r)
    db().flush()
    audit(user, "COMPRA_CREADA", "PurchaseRequest", r.id, {"producto": product_code, "cantidad": cantidad, "origen": origen})
    if sistema or origen in ("OV", "PRODUCCION", "REPOSICION"):
        alerts.emit("QUIEBRE_STOCK", f"Quiebre de stock: {product_code} (presolicitud de compra #{r.id})", r.motivo,
                    "PurchaseRequest", r.id, dedup_key=f"QUIEBRE:{product_code}:{fecha_necesidad}", creado_por=user)
    if enviar:
        send(r, user)
    return r


def _alerta_logistica(r, user):
    ovs = ", ".join(x["numero"] for x in (r.ordenes or [])) or (r.order.numero if r.order_id and r.order else "")
    alerts.emit("COMPRA_APROBACION_LOGISTICA", f"Aprobar presolicitud de compra #{r.id}: {r.product_code} × {r.cantidad:g}",
                f"Necesidad: {r.fecha_necesidad or '-'}. Origen: {r.origen}." + (f" OV de origen: {ovs}." if ovs else "") +
                (" Compra de mayor volumen." if r.mayor_volumen else "") + (f" {r.motivo}" if r.motivo else ""),
                "PurchaseRequest", r.id, dedup_key=f"COMPRA_LOG:{r.id}", creado_por=user)


def send(r, user):
    """Almacén envía la solicitud (o el sistema la pre-solicita, Q15) y queda pendiente del Jefe de Logística (Q14)."""
    if r.estado != "BORRADOR":
        raise BusinessError("Solo se envían solicitudes en borrador.")
    if user is not None and not has_perm(user, "compras.solicitar"):
        raise BusinessError("Almacén revisa y envía la solicitud.")
    r.estado = "PENDIENTE_LOGISTICA"
    _alerta_logistica(r, user)
    audit(user, "COMPRA_ENVIADA", "PurchaseRequest", r.id)


def approve_logistics(r, user, aprobar, comentario=""):
    """Q14 (12-oct-2026) y obs. demo v0.7: la presolicitud la autoriza el Jefe o el Coordinador de Logística o el
    Supervisor de Almacén antes de que pase a Compras."""
    if not has_perm(user, "compras.aprobar_solicitud"):
        raise BusinessError("La presolicitud de compra la autorizan el Jefe o Coordinador de Logística o el Supervisor de Almacén.")
    if r.estado != "PENDIENTE_LOGISTICA":
        raise BusinessError("La solicitud no está pendiente de aprobación de Logística.")
    if not aprobar and not comentario.strip():
        raise BusinessError("Indique el motivo del rechazo.")
    r.aprobado_logistica_por = user.id if aprobar else None
    r.estado = "SOLICITADA" if aprobar else "ANULADA"
    alerts.close_by_system(f"COMPRA_LOG:{r.id}", "Aprobada" if aprobar else "Rechazada")
    if aprobar:
        alerts.emit("COMPRA_SOLICITUD", f"Solicitud de compra #{r.id}: {r.product_code} × {r.cantidad:g}",
                    f"Aprobada por {user.nombre}. Necesidad: {r.fecha_necesidad or '-'}. Origen: {r.origen}." +
                    (" Compra de mayor volumen." if r.mayor_volumen else ""), "PurchaseRequest", r.id, creado_por=user)
    audit(user, "COMPRA_LOGISTICA_" + ("APROBADA" if aprobar else "RECHAZADA"), "PurchaseRequest", r.id,
          {"comentario": comentario})


def _require_compras(user):
    if not has_perm(user, "compras.gestionar"):
        raise BusinessError("Gestiona el Coordinador de Compras (IF §10).")


def quote(r, user, proveedor, cotizacion, precio=None, requiere_muestra=False, archivo="", plazo=""):
    _require_compras(user)
    if r.estado not in ("SOLICITADA", "EN_COTIZACION", "MUESTRA_RECHAZADA"):
        raise BusinessError("La solicitud no está en etapa de cotización.")
    if not proveedor.strip():
        raise BusinessError("Indique el proveedor.")
    r.proveedor = proveedor.strip()
    r.cotizacion = cotizacion
    r.precio = precio
    # obs. demo v0.7: Compras reúne las cotizaciones; la última registrada queda como elegida (se puede cambiar)
    cots = [dict(c, elegida=False) for c in (r.cotizaciones or [])]
    cots.append({"proveedor": proveedor.strip(), "precio": precio, "detalle": cotizacion or "", "archivo": archivo or "",
                 "plazo": plazo or "", "ts": now().isoformat(), "user": user.nombre, "elegida": True})
    r.cotizaciones = cots
    r.requiere_muestra = bool(requiere_muestra)
    r.mayor_volumen = is_mayor_volumen(r.cantidad, r.product, precio)
    check_max_cost(r, user)
    if precio:
        from .costs import check_quote_impact
        check_quote_impact(r.product, user)
    if requiere_muestra:
        r.estado = "MUESTRA_EN_CALIDAD"
        r.resultado_muestra = ""
        alerts.emit("COMPRA_MUESTRA", f"Evaluar muestra de compra #{r.id} ({r.product_code})",
                    f"Proveedor {r.proveedor}.", "PurchaseRequest", r.id, dedup_key=f"COMPRA_MUESTRA:{r.id}", creado_por=user)
    else:
        r.estado = "EN_COTIZACION"
    audit(user, "COMPRA_COTIZADA", "PurchaseRequest", r.id, {"proveedor": proveedor, "precio": precio,
                                                             "requiere_muestra": requiere_muestra})


def check_max_cost(r, user=None):
    """Costo máximo de compra configurable por artículo (observaciones al demo v0.5): si la cotización lo supera se
    alerta a Compras y Logística antes de generar la OC, para no comprar a pérdida."""
    p = r.product
    key = f"COMPRA_COSTO_MAX:{r.id}"
    if p is not None and p.costo_max_compra and r.precio and r.precio > p.costo_max_compra + 1e-9:
        alerts.emit("COMPRA_SOBRE_COSTO_MAXIMO", f"Compra #{r.id}: precio sobre el costo máximo ({r.product_code})",
                    f"Cotización {r.precio:.4f} vs costo máximo {p.costo_max_compra:.4f} por {p.um.lower()}. Proveedor "
                    f"{r.proveedor or '-'}. Revisar antes de generar la orden de compra.", "PurchaseRequest", r.id,
                    dedup_key=key, creado_por=user)
        return True
    alerts.close_by_system(key, "Precio dentro del costo máximo")
    return False


def evaluate_sample(r, user, aprobar, observacion):
    if not has_perm(user, "calidad.evaluar_muestra"):
        raise BusinessError("Calidad evalúa la muestra (IF §10.3).")
    if r.estado != "MUESTRA_EN_CALIDAD":
        raise BusinessError("No hay muestra pendiente de evaluación.")
    r.resultado_muestra = "APROBADA" if aprobar else "RECHAZADA"
    r.estado = "EN_COTIZACION" if aprobar else "MUESTRA_RECHAZADA"
    r.cotizacion = (r.cotizacion or "") + f"\n[Calidad {now():%d/%m/%Y %H:%M}] Muestra {r.resultado_muestra}: {observacion}"
    alerts.close_by_system(f"COMPRA_MUESTRA:{r.id}", f"Muestra {r.resultado_muestra.lower()}")
    audit(user, f"COMPRA_MUESTRA_{r.resultado_muestra}", "PurchaseRequest", r.id, {"observacion": observacion})


def go_reason(r):
    """Motivo por el que la compra requiere Gerencia de Operaciones: materia prima (siempre, decisión del 14-oct) o
    mayor volumen (IF §7)."""
    p = r.product
    if p is not None and (p.tipo or r.product_code[:2]) in (param("tipos_compra_requieren_go", ["MP"]) or []):
        return "granel" if (p.tipo or r.product_code[:2]) == "GR" else "materia prima"
    if r.mayor_volumen and bool(param("mayor_volumen_requiere_go", True)):
        return "mayor volumen"
    return ""


def needs_go_approval(r):
    """Obs. demo v0.7: la ejecución de toda compra la aprueba Gerencia de Operaciones (parámetro
    'compra_ejecucion_requiere_go'); antes solo materia prima o mayor volumen."""
    if r.aprobado_gerencia_por:
        return False
    return bool(param("compra_ejecucion_requiere_go", True)) or bool(go_reason(r))


def choose_quote(r, user, idx):
    """Compras elige la cotización con la que se pide la aprobación de Gerencia de Operaciones."""
    _require_compras(user)
    cots = [dict(c) for c in (r.cotizaciones or [])]
    if not 0 <= int(idx) < len(cots):
        raise BusinessError("Cotización no encontrada.")
    if r.estado not in ("SOLICITADA", "EN_COTIZACION", "MUESTRA_RECHAZADA"):
        raise BusinessError("La cotización ya no se puede cambiar.")
    for i, c in enumerate(cots):
        c["elegida"] = i == int(idx)
    r.cotizaciones = cots
    c = cots[int(idx)]
    r.proveedor, r.precio, r.cotizacion = c["proveedor"], c.get("precio"), c.get("detalle", "")
    r.mayor_volumen = is_mayor_volumen(r.cantidad, r.product, r.precio)
    audit(user, "COMPRA_COTIZACION_ELEGIDA", "PurchaseRequest", r.id, {"proveedor": r.proveedor, "precio": r.precio})


def request_go_approval(r, user):
    _require_compras(user)
    if not needs_go_approval(r):
        raise BusinessError("La compra no requiere aprobación de Gerencia General.")
    if r.estado != "EN_COTIZACION":
        raise BusinessError("Primero registre las cotizaciones (y la muestra aprobada por Calidad si aplica).")
    minimo = int(param("cotizaciones_minimas_compra", 1) or 1)
    if len(r.cotizaciones or []) < minimo:
        raise BusinessError(f"Para pedir la aprobación de ejecución se requieren al menos {minimo} cotización(es).")
    r.estado = "PENDIENTE_APROBACION"
    motivo = go_reason(r) or "ejecución"
    resumen = "; ".join(f"{c['proveedor']}: {c.get('precio') if c.get('precio') is not None else '-'}" + (" (elegida)" if c.get("elegida") else "")
                        for c in (r.cotizaciones or []))
    alerts.emit("COMPRA_APROBACION_GERENCIA", f"Aprobar {'compra de ' + motivo if motivo != 'ejecución' else 'ejecución de la compra'} #{r.id}",
                f"{r.product_code} × {r.cantidad:g}" + (f" (umbral {param('umbral_mayor_volumen')})" if motivo == "mayor volumen" else "")
                + f". Cotizaciones: {resumen or '-'}." + (f" {r.motivo}" if r.motivo else ""),
                "PurchaseRequest", r.id, dedup_key=f"COMPRA_GO:{r.id}", creado_por=user)


def approve_go(r, user, aprobar, comentario=""):
    if not has_perm(user, "compras.aprobar_mayor_volumen"):
        raise BusinessError("Aprueba el Gerente General Adjunto (o Gerencia General).")
    if r.estado != "PENDIENTE_APROBACION":
        raise BusinessError("La compra no está pendiente de aprobación.")
    if aprobar:
        r.aprobado_gerencia_por = user.id
        r.estado = "EN_COTIZACION"
    else:
        r.estado = "ANULADA"
    alerts.close_by_system(f"COMPRA_GO:{r.id}", "Resuelta")
    audit(user, "COMPRA_GO_" + ("APROBADA" if aprobar else "RECHAZADA"), "PurchaseRequest", r.id, {"comentario": comentario})


def generate_order(r, user, numero_oc, fecha_prevista, warehouse_code):
    _require_compras(user)
    if r.estado != "EN_COTIZACION":
        raise BusinessError("Para generar la orden la solicitud debe estar cotizada (y con muestra aprobada si aplica).")
    if r.requiere_muestra and r.resultado_muestra != "APROBADA":
        raise BusinessError("La muestra debe estar aprobada por Calidad.")
    if needs_go_approval(r):
        raise BusinessError("La ejecución de la compra requiere la aprobación del Gerente General Adjunto "
                            "(pídala con las cotizaciones registradas).")
    if not fecha_prevista:
        raise BusinessError("Indique la fecha prevista de recepción.")
    if not (numero_oc or "").strip():  # V17: el número de la orden de compra lo asigna el sistema
        from .numeracion import next_purchase_order_number
        numero_oc = next_purchase_order_number()
    r.numero_oc = numero_oc.strip()
    r.fecha_prevista = fecha_prevista
    r.warehouse_code = warehouse_code
    r.estado = "ORDEN_GENERADA"
    db().add(DateChange(entidad="COMPRA", entidad_id=r.id, anterior=None, nueva=fecha_prevista, motivo="Fecha inicial",
                        user_id=user.id))
    alerts.emit("COMPRA_RECEPCION_PROGRAMAR", f"Programar recepción OC {r.numero_oc} ({r.product_code})",
                f"Fecha prevista {fecha_prevista:%d/%m/%Y}; {r.cantidad:g} en {warehouse_code}. Coordinar con despachos de salida.",
                "PurchaseRequest", r.id, creado_por=user)
    audit(user, "COMPRA_ORDEN_GENERADA", "PurchaseRequest", r.id, {"oc": numero_oc, "fecha_prevista": fecha_prevista})


def change_date(r, user, nueva, motivo):
    _require_compras(user)
    if r.estado != "ORDEN_GENERADA":
        raise BusinessError("Solo se cambian fechas de órdenes generadas pendientes de recepción.")
    if not motivo.strip():
        raise BusinessError("Indique el motivo del cambio.")
    anterior = r.fecha_prevista
    r.fecha_prevista = nueva
    db().add(DateChange(entidad="COMPRA", entidad_id=r.id, anterior=anterior, nueva=nueva, motivo=motivo, user_id=user.id))
    alerts.emit("COMPRA_FECHA_CAMBIO", f"Cambio de fecha OC {r.numero_oc}: {anterior:%d/%m} → {nueva:%d/%m}",
                f"{r.product_code} × {r.cantidad:g}. Motivo: {motivo}", "PurchaseRequest", r.id, creado_por=user)
    audit(user, "COMPRA_FECHA_CAMBIO", "PurchaseRequest", r.id, {"anterior": anterior, "nueva": nueva, "motivo": motivo})


def receive(r, user, cantidad, lote, fecha_venc=None, diferencias=""):
    if not has_perm(user, "compras.recibir"):
        raise BusinessError("Almacén registra la recepción.")
    if r.estado != "ORDEN_GENERADA":
        raise BusinessError("La compra no está pendiente de recepción.")
    check_warehouse_scope(user, r.warehouse_code)
    if cantidad is None or cantidad < 0 or not lote:
        raise BusinessError("Indique cantidad y lote recibido.")
    r.cantidad_recibida = cantidad
    r.lote_recibido = lote
    hay_dif = abs(cantidad - r.cantidad) > 1e-9 or bool(diferencias.strip())
    r.diferencias = diferencias or (f"Cantidad recibida {cantidad:g} vs ordenada {r.cantidad:g}" if hay_dif else "")
    r.estado = "RECIBIDA_CON_DIFERENCIAS" if hay_dif else "RECIBIDA"
    if cantidad > 0:
        lot = add_or_increase_lot(r.product_code, r.warehouse_code, lote, cantidad, "PENDIENTE_REVISION", fecha_venc,
                                  origen=f"COMPRA-{r.id}")
        alerts.emit("STOCK_PENDIENTE_REVISION", f"Compra recibida pendiente de revisión: lote {lote}",
                    f"{r.product_code} × {cantidad:g} (OC {r.numero_oc}).", "StockLot", lot.id, creado_por=user)
    if hay_dif:
        alerts.emit("COMPRA_DIFERENCIA", f"Diferencias en recepción OC {r.numero_oc}",
                    f"{r.diferencias}. Informar a Compras para subsanación.", "PurchaseRequest", r.id, creado_por=user)
    audit(user, f"COMPRA_{r.estado}", "PurchaseRequest", r.id, {"cantidad": cantidad, "lote": lote, "diferencias": r.diferencias})


def authorize_under_observation(r, user, observaciones):
    if not has_perm(user, "compras.autorizar_bajo_observacion"):
        raise BusinessError("Autoriza recibir bajo observaciones el Gerente General Adjunto (o Gerencia General).")
    if r.estado != "RECIBIDA_CON_DIFERENCIAS":
        raise BusinessError("Solo aplica a recepciones con diferencias.")
    if not observaciones.strip():
        raise BusinessError("Registre las observaciones de la autorización.")
    r.estado = "RECIBIDA_BAJO_OBSERVACION"
    r.autorizacion_observacion_por = user.id
    r.observaciones_recepcion = observaciones
    audit(user, "COMPRA_BAJO_OBSERVACION", "PurchaseRequest", r.id, {"observaciones": observaciones})


def register_rectification(r, user, detalle):
    _require_compras(user)
    if r.estado not in ("RECIBIDA_CON_DIFERENCIAS", "RECIBIDA_BAJO_OBSERVACION"):
        raise BusinessError("No hay diferencias por subsanar.")
    r.diferencias += f"\n[Subsanación {now():%d/%m/%Y}] {detalle}"
    r.estado = "CERRADA"
    audit(user, "COMPRA_SUBSANADA", "PurchaseRequest", r.id, {"detalle": detalle})


def close(r, user):
    if not (has_perm(user, "compras.gestionar") or has_perm(user, "compras.recibir")):
        raise BusinessError("Sin permiso.")
    if r.estado != "RECIBIDA":
        raise BusinessError("Solo se cierran compras recibidas sin diferencias.")
    r.estado = "CERRADA"
    audit(user, "COMPRA_CERRADA", "PurchaseRequest", r.id)


# ----------------------------- reposición ----------------------------------
def lead_time_for(product, ref=None):
    """Plazo en días naturales según categoría, con excepción estacional (campaña de canastería)."""
    ref = ref or date.today()
    if not product.categoria_reposicion:
        return None, None
    rows = list(db().execute(select(LeadTime).where(LeadTime.categoria == product.categoria_reposicion)).scalars())
    seasonal = [r for r in rows if r.mes_desde and r.mes_desde <= ref.month <= (r.mes_hasta or r.mes_desde)]
    base = [r for r in rows if not r.mes_desde]
    lt = (seasonal or base or [None])[0]
    return lt, ("estacional" if seasonal else "normal")


def es_producido(product):
    """V31: PT, MQ y MP los fabrica la empresa (no se compran); se compran el granel, los insumos y lo demás."""
    if product is None:
        return False
    pref = [str(x).strip().upper() for x in (param("prefijos_producidos", ["PT", "MQ", "MP"]) or []) if str(x).strip()]
    return any(product.code.upper().startswith(x) for x in pref)


def es_no_comprable(product):
    """V32: lo que nunca se compra (por defecto, el PT). Compras adquiere el granel y, eventualmente, MP o MQ; su
    reposición normal es una pre-solicitud de producción (es_producido)."""
    if product is None:
        return False
    pref = [str(x).strip().upper() for x in (param("compras_no_comprables", ["PT"]) or []) if str(x).strip()]
    return any(product.code.upper().startswith(x) for x in pref)


def _salidas_periodo(code, desde, ref):
    """V31: salidas del periodo: el historial cargado y, si no lo hay, las guías y consumos de producción leídos de SAP."""
    from ..models import SapMovement
    s = db()
    hist = s.execute(select(func.coalesce(func.sum(SalesHistory.cantidad), 0)).where(
        SalesHistory.product_code == code, SalesHistory.fecha >= desde, SalesHistory.fecha < ref)).scalar() or 0
    if hist:
        return float(hist), "historial cargado"
    sap = s.execute(select(func.coalesce(func.sum(SapMovement.cantidad), 0)).where(
        SapMovement.product_code == code, SapMovement.fecha >= desde, SapMovement.fecha < ref)).scalar() or 0
    return float(sap), "guías y consumos de SAP"


def analyze_product(product, ref=None, demanda_produccion=0.0):
    """Análisis de reposición (IF §7). Usa solo datos disponibles; informa los faltantes de datos.
    V31: se anticipa al quiebre (punto de pedido): consumo durante el plazo + faltante de OV pendientes + stock mínimo +
    stock de seguridad + lo que se necesita para producir (demanda_produccion) − disponible − en camino."""
    ref = ref or date.today()
    s = db()
    out = {"producto": product.code, "descripcion": product.descripcion, "avisos": []}
    periodo = product.periodo_analisis_dias or param("periodo_analisis_dias", 15) or 15
    desde = ref - timedelta(days=int(periodo))
    salidas, fuente = _salidas_periodo(product.code, desde, ref)
    out["fuente_consumo"] = fuente
    consumo_diario = salidas / periodo if periodo else 0
    # período: días completos anteriores a la fecha de análisis
    out.update({"periodo_dias": periodo, "salidas_periodo": salidas, "consumo_diario": consumo_diario})
    lt, modo = lead_time_for(product, ref)
    if lt is None:
        out["avisos"].append("Sin categoría de reposición/plazo configurado: no se calcula fecha de pedido.")
        plazo = None
    else:
        plazo = lt.dias_max
        out["avisos"].append(f"Plazo {lt.categoria} ({modo}): {lt.dias_min}-{lt.dias_max} días naturales; se usa el máximo.")
    por_prov = (param("margen_por_proveedor", {}) or {}).get((product.proveedor_habitual or "").strip())
    if product.margen_seguridad_dias is not None:
        margen = product.margen_seguridad_dias
    elif por_prov is not None:
        margen = por_prov
        out["avisos"].append(f"Margen del proveedor {product.proveedor_habitual}: {por_prov} días.")
    else:
        margen = param("margen_reposicion_dias")
    if margen is None:
        out["avisos"].append("Margen por atrasos no definido (IF §7: valor pendiente); se usa 0.")
        margen = 0
    lead_total = (plazo or 0) + int(margen)
    disponible = reservado = 0.0
    for lot in lots_of(product.code):
        ok, _ = lot_usable(lot)
        if ok:
            disponible += free_qty(lot)
        reservado += sum(r.cantidad for r in lot.reservations if r.estado == "ACTIVA")
    # faltantes de OV pendientes (no reservados)
    falt_ov = 0.0
    for o in s.execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS))).scalars():
        for l in o.lines:
            if l.activa and l.product_code == product.code:
                falt_ov += max(l.cantidad - l.despachado - line_reserved(l), 0)
    en_camino = s.execute(select(func.coalesce(func.sum(PurchaseRequest.cantidad), 0)).where(
        PurchaseRequest.product_code == product.code, PurchaseRequest.estado.in_(OPEN_STATES))).scalar() or 0
    stock_min = product.stock_minimo or 0
    seg = 0.0
    if param("usar_stock_seguridad", False):
        seg = consumo_diario * 30 * float(param("factor_stock_seguridad", 0.3) or 0)
    demanda_lead = consumo_diario * lead_total
    necesidad = demanda_lead + falt_ov + stock_min + seg + (demanda_produccion or 0) - disponible - en_camino
    out.update({"plazo_dias": plazo, "margen_dias": margen, "lead_total": lead_total, "disponible": disponible,
                "reservado": reservado, "faltante_ov": falt_ov, "en_camino": en_camino, "stock_minimo": stock_min,
                "stock_seguridad": seg, "demanda_durante_plazo": demanda_lead, "demanda_produccion": demanda_produccion or 0,
                "necesidad": max(necesidad, 0), "cantidad_sugerida": math.ceil(max(necesidad, 0))})
    if consumo_diario > 0:
        dias_cobertura = max(disponible - falt_ov, 0) / consumo_diario
        out["dias_cobertura"] = round(dias_cobertura, 1)
        out["fecha_necesidad"] = ref + timedelta(days=int(dias_cobertura))
        if plazo is not None:
            out["fecha_limite_pedido"] = out["fecha_necesidad"] - timedelta(days=lead_total)
    else:
        out["dias_cobertura"] = None
        out["fecha_necesidad"] = ref if falt_ov > 0 or disponible < stock_min else None
        if consumo_diario == 0:
            out["avisos"].append("Sin historial de salidas en el período: el consumo diario es 0.")
    out["requiere_compra"] = out["cantidad_sugerida"] > 0
    return out


def _candidatos(product_codes=None):
    """Productos a revisar: los configurados (categoría de reposición o stock mínimo) y, V31, todo PT, MQ, MP y GR con
    stock o con OV pendientes."""
    from ..models import StockLot
    from .stock import product_kind
    s = db()
    if product_codes:
        return list(s.execute(select(Product).where(Product.code.in_(product_codes))).scalars())
    out = {p.code: p for p in s.execute(select(Product).where(
        (Product.categoria_reposicion != "") | (Product.stock_minimo.is_not(None)))).scalars()}
    con_mov = {c for (c,) in s.execute(select(StockLot.product_code).where(StockLot.cantidad > 0).distinct())}
    for o in s.execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS))).scalars():
        con_mov |= {l.product_code for l in o.lines if l.activa}
    for p in s.execute(select(Product).where(Product.code.in_(con_mov or {""}))).scalars():
        if es_producido(p) or product_kind(p) == "GR":
            out.setdefault(p.code, p)
    return list(out.values())


def _orden_produccion(p):
    """PT y MQ primero (su lista de materiales pide MP y granel), luego MP (pide granel) y al final lo que se compra."""
    c = p.code.upper()
    return 0 if c.startswith(("PT", "MQ")) else 1 if es_producido(p) else 2


def run_replenishment(user=None, product_codes=None, ref=None):
    """Reposición anticipada (antes del quiebre de stock), V31:
    - PT, MQ y MP (los fabrica la empresa): si el stock libre no cubre las OV pendientes + el consumo durante el plazo +
      el stock mínimo y de seguridad, se genera una PRE-SOLICITUD DE PRODUCCIÓN (borrador para el Jefe de Producción) y
      su lista de materiales se suma a la necesidad de sus componentes;
    - lo que se compra (granel, insumos, envases…): PRE-SOLICITUD DE COMPRA (borrador para Almacén), con lo mismo más lo
      que hace falta para producir.
    Devuelve las pre-solicitudes de compra creadas (las de producción quedan en el resumen de la alerta)."""
    from .production import create_request as crear_produccion, material_requirements
    from ..models import ProductionRequest
    s = db()
    creadas = []
    demanda_comp = defaultdict(float)
    for p in sorted(_candidatos(product_codes), key=lambda x: (_orden_produccion(x), x.code)):
        a = analyze_product(p, ref, demanda_comp.get(p.code, 0.0))
        if not a["requiere_compra"]:
            continue
        analisis = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in a.items()}
        if es_producido(p):
            req = material_requirements(p.code, a["cantidad_sugerida"])
            for m in req.get("materiales", []):
                demanda_comp[m["componente"]] += float(m.get("requerido") or 0)
            abierta = s.execute(select(ProductionRequest).where(ProductionRequest.product_code == p.code,
                                                                ProductionRequest.origen == "REPOSICION",
                                                                ProductionRequest.estado == "BORRADOR")).scalars().first()
            if abierta:
                abierta.cantidad = a["cantidad_sugerida"]
                abierta.fecha_requerida = a.get("fecha_necesidad")
                abierta.analisis = req
                continue
            r = crear_produccion(p.code, a["cantidad_sugerida"], user, fecha_requerida=a.get("fecha_necesidad"),
                                 origen="REPOSICION", observacion=_motivo(a, "producir"))
            alerts.emit("PRODUCCION_REPOSICION", f"Pre-solicitud de producción: {p.code} × {a['cantidad_sugerida']:g}",
                        _motivo(a, "producir") + f" Pre-solicitud #{r.id} en borrador para revisión del Jefe de Producción.",
                        "ProductionRequest", r.id, dedup_key=f"REPO_PROD:{p.code}", creado_por=user)
            continue
        abierta = s.execute(select(PurchaseRequest).where(PurchaseRequest.product_code == p.code,
                                                          PurchaseRequest.estado.in_(("BORRADOR",)))).scalars().first()
        if abierta:
            abierta.cantidad = a["cantidad_sugerida"]
            abierta.analisis = analisis
            abierta.fecha_necesidad = a.get("fecha_necesidad")
            continue
        r = create_request(user, p.code, a["cantidad_sugerida"], a.get("fecha_necesidad"), origen="REPOSICION",
                           analisis=analisis, enviar=False)
        creadas.append(r)
        alerts.emit("REPOSICION_SUGERIDA", f"Reposición sugerida: {p.code} × {a['cantidad_sugerida']:g}",
                    _motivo(a, "comprar") + f" Fecha estimada de necesidad: {a.get('fecha_necesidad') or '-'}; límite de "
                    f"pedido: {a.get('fecha_limite_pedido') or '-'}. Solicitud preliminar #{r.id} en borrador para revisión "
                    "de Almacén.", "PurchaseRequest", r.id, dedup_key=f"REPOSICION:{p.code}", creado_por=user)
    return creadas


def _motivo(a, que):
    partes = [f"OV pendientes sin reservar {a['faltante_ov']:g}"] if a.get("faltante_ov") else []
    if a.get("demanda_durante_plazo"):
        partes.append(f"consumo durante el plazo {a['demanda_durante_plazo']:.0f} ({a.get('fuente_consumo', '')})")
    if a.get("demanda_produccion"):
        partes.append(f"para producir {a['demanda_produccion']:g}")
    if a.get("stock_minimo"):
        partes.append(f"stock mínimo {a['stock_minimo']:g}")
    if a.get("stock_seguridad"):
        partes.append(f"stock de seguridad {a['stock_seguridad']:.0f}")
    return (f"Hay que {que} {a['cantidad_sugerida']:g} antes de quedarse sin stock: " + ", ".join(partes or ["stock bajo"])
            + f"; libre {a['disponible']:g}, en camino {a['en_camino']:g}.")


def abc_classes(ref=None):
    """Clasificación ABC por consumo acumulado del período de análisis (parámetro clasificacion_abc_pct)."""
    ref = ref or date.today()
    periodo = int(param("periodo_analisis_dias", 15) or 15)
    lim = param("clasificacion_abc_pct", {"A": 80, "B": 95}) or {"A": 80, "B": 95}
    rows = db().execute(select(SalesHistory.product_code, func.sum(SalesHistory.cantidad)).where(
        SalesHistory.fecha >= ref - timedelta(days=periodo), SalesHistory.fecha < ref).group_by(SalesHistory.product_code)).all()
    total = sum(q for _, q in rows) or 0
    out, acum = {}, 0.0
    for code, q in sorted(rows, key=lambda r: -r[1]):
        acum += q
        pct = 100 * acum / total if total else 100
        out[code] = "A" if pct <= float(lim.get("A", 80)) + 1e-9 or not out else ("B" if pct <= float(lim.get("B", 95)) + 1e-9 else "C")
    return out
