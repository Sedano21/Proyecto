"""Compras nacionales (IF §10) y análisis de reposición (IF §7)."""
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


def create_request(user, product_code, cantidad, fecha_necesidad=None, origen="ALMACEN", order=None, analisis=None,
                   enviar=True, sistema=False):
    """sistema=True: pre-solicitud automática por faltante (Q15); pasa a aprobación del Jefe de Logística (Q14)."""
    if origen != "REPOSICION" and not sistema and not has_perm(user, "compras.solicitar"):
        raise BusinessError("En la primera etapa las solicitudes de compra nacen en Almacén (IF §7, §10.1).")
    if db().get(Product, product_code) is None:
        raise BusinessError("Producto no existe.")
    if cantidad is None or cantidad <= 0:
        raise BusinessError("Cantidad inválida.")
    r = PurchaseRequest(product_code=product_code, cantidad=cantidad, fecha_necesidad=fecha_necesidad, origen=origen,
                        order_id=order.id if order else None, analisis=analisis or {},
                        mayor_volumen=is_mayor_volumen(cantidad, db().get(Product, product_code)),
                        creado_por=user.id if user else None)
    db().add(r)
    db().flush()
    audit(user, "COMPRA_CREADA", "PurchaseRequest", r.id, {"producto": product_code, "cantidad": cantidad, "origen": origen})
    if enviar:
        send(r, user)
    return r


def send(r, user):
    """Almacén envía la solicitud (o el sistema la pre-solicita, Q15) y queda pendiente del Jefe de Logística (Q14)."""
    if r.estado != "BORRADOR":
        raise BusinessError("Solo se envían solicitudes en borrador.")
    if user is not None and not has_perm(user, "compras.solicitar"):
        raise BusinessError("Almacén revisa y envía la solicitud.")
    r.estado = "PENDIENTE_LOGISTICA"
    alerts.emit("COMPRA_APROBACION_LOGISTICA", f"Aprobar solicitud de compra #{r.id}: {r.product_code} × {r.cantidad:g}",
                f"Necesidad: {r.fecha_necesidad or '-'}. Origen: {r.origen}." +
                (f" OV {r.order.numero}." if r.order_id and r.order else "") +
                (" Compra de mayor volumen." if r.mayor_volumen else ""), "PurchaseRequest", r.id,
                dedup_key=f"COMPRA_LOG:{r.id}", creado_por=user)
    audit(user, "COMPRA_ENVIADA", "PurchaseRequest", r.id)


def approve_logistics(r, user, aprobar, comentario=""):
    """Q14 (12-oct-2026): el Jefe de Logística aprueba la solicitud antes de que pase a Compras."""
    if not has_perm(user, "compras.aprobar_solicitud"):
        raise BusinessError("La solicitud de compra la aprueba el Jefe de Logística (Q14).")
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


def quote(r, user, proveedor, cotizacion, precio=None, requiere_muestra=False):
    _require_compras(user)
    if r.estado not in ("SOLICITADA", "EN_COTIZACION", "MUESTRA_RECHAZADA"):
        raise BusinessError("La solicitud no está en etapa de cotización.")
    if not proveedor.strip():
        raise BusinessError("Indique el proveedor.")
    r.proveedor = proveedor.strip()
    r.cotizacion = cotizacion
    r.precio = precio
    r.requiere_muestra = bool(requiere_muestra)
    r.mayor_volumen = is_mayor_volumen(r.cantidad, r.product, precio)
    check_max_cost(r, user)
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


def needs_go_approval(r):
    return r.mayor_volumen and bool(param("mayor_volumen_requiere_go", True)) and not r.aprobado_gerencia_por


def request_go_approval(r, user):
    _require_compras(user)
    if not needs_go_approval(r):
        raise BusinessError("La compra no requiere aprobación de Gerencia de Operaciones.")
    r.estado = "PENDIENTE_APROBACION"
    alerts.emit("COMPRA_APROBACION_GERENCIA", f"Aprobar compra de mayor volumen #{r.id}",
                f"{r.product_code} × {r.cantidad:g} (umbral {param('umbral_mayor_volumen')}). Proveedor {r.proveedor}.",
                "PurchaseRequest", r.id, dedup_key=f"COMPRA_GO:{r.id}", creado_por=user)


def approve_go(r, user, aprobar, comentario=""):
    if not has_perm(user, "compras.aprobar_mayor_volumen"):
        raise BusinessError("Aprueba Gerencia de Operaciones.")
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
        raise BusinessError("Compra de mayor volumen: requiere aprobación de Gerencia de Operaciones.")
    if not numero_oc.strip() or not fecha_prevista:
        raise BusinessError("Indique número de orden y fecha prevista de recepción.")
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
        raise BusinessError("Solo Gerencia de Operaciones autoriza recibir bajo observaciones (IF §10.8).")
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


def analyze_product(product, ref=None):
    """Análisis de reposición (IF §7). Usa solo datos disponibles; informa los faltantes de datos."""
    ref = ref or date.today()
    s = db()
    out = {"producto": product.code, "descripcion": product.descripcion, "avisos": []}
    periodo = product.periodo_analisis_dias or param("periodo_analisis_dias", 15) or 15
    desde = ref - timedelta(days=int(periodo))
    salidas = s.execute(select(func.coalesce(func.sum(SalesHistory.cantidad), 0)).where(
        SalesHistory.product_code == product.code, SalesHistory.fecha >= desde, SalesHistory.fecha < ref)).scalar() or 0
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
    necesidad = demanda_lead + falt_ov + stock_min + seg - disponible - en_camino
    out.update({"plazo_dias": plazo, "margen_dias": margen, "lead_total": lead_total, "disponible": disponible,
                "reservado": reservado, "faltante_ov": falt_ov, "en_camino": en_camino, "stock_minimo": stock_min,
                "stock_seguridad": seg, "demanda_durante_plazo": demanda_lead,
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


def run_replenishment(user=None, product_codes=None, ref=None):
    """Genera alertas y solicitudes preliminares (BORRADOR, para que Almacén revise y envíe)."""
    s = db()
    q = select(Product).where((Product.categoria_reposicion != "") | (Product.stock_minimo.is_not(None)))
    if product_codes:
        q = select(Product).where(Product.code.in_(product_codes))
    creadas = []
    for p in s.execute(q).scalars():
        a = analyze_product(p, ref)
        if not a["requiere_compra"]:
            continue
        abierta = s.execute(select(PurchaseRequest).where(PurchaseRequest.product_code == p.code,
                                                          PurchaseRequest.estado.in_(("BORRADOR",)))).scalars().first()
        analisis = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in a.items()}
        if abierta:
            abierta.cantidad = a["cantidad_sugerida"]
            abierta.analisis = analisis
            abierta.fecha_necesidad = a.get("fecha_necesidad")
            continue
        r = create_request(user, p.code, a["cantidad_sugerida"], a.get("fecha_necesidad"), origen="REPOSICION",
                           analisis=analisis, enviar=False)
        creadas.append(r)
        alerts.emit("REPOSICION_SUGERIDA", f"Reposición sugerida: {p.code} × {a['cantidad_sugerida']:g}",
                    f"Fecha estimada de necesidad: {a.get('fecha_necesidad') or '-'}; límite de pedido: "
                    f"{a.get('fecha_limite_pedido') or '-'}. Solicitud preliminar #{r.id} en borrador para revisión de Almacén.",
                    "PurchaseRequest", r.id, dedup_key=f"REPOSICION:{p.code}", creado_por=user)
    return creadas


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
