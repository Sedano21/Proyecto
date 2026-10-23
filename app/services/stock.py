"""Stock, reservas, cobertura y alternativas (IF §6, §22).

Reglas implementadas:
- Solo se reserva stock en estado DISPONIBLE, verificado, del almacén principal según el tipo de artículo,
  no vencido a la fecha comprometida y que cumpla la vida útil mínima del cliente (si está configurada).
- Orden de consumo de lotes: FEFO (parámetro 'politica_lotes', PROPUESTO).
- Cobertura: % de unidades reservadas y % de líneas totalmente cubiertas.
- Ante faltante: reserva lo disponible, calcula cobertura, alerta y presenta alternativas SIN ejecutarlas.
- Al modificar una OV: conserva reservas válidas, recalcula diferencia y alerta.
"""
from datetime import date, timedelta

from sqlalchemy import func, select

from ..db import db
from ..models import (BOMLine, BOMVersion, Product, Reservation, SalesHistory, SalesOrder, SalesOrderLine,
                      StockLot, UploadBatch, Warehouse, now)
from . import alerts
from .core import BusinessError, audit, param

ESTADOS_LABEL = {
    "DISPONIBLE": "Disponible", "RESERVADO": "Reservado", "NO_UTILIZABLE": "No utilizable", "DANADO": "Dañado",
    "EN_FUMIGACION": "En fumigación", "PENDIENTE_REVISION": "Pendiente de revisión",
    "OBSERVADO": "Producto observado",  # obs. demo v0.7: rotura, infestación o contaminación detectada en el picking
}
ESTADOS_FISICOS = ["DISPONIBLE", "NO_UTILIZABLE", "DANADO", "EN_FUMIGACION", "PENDIENTE_REVISION", "OBSERVADO"]
ORDEN_ESTADOS_CERRADOS = ("CANCELADA", "DESPACHADA", "ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA", "DEVUELTA", "CERRADA",
                          "REGULARIZADA_CERRADA")
PREFIJO_TIPO = {"PT": "PT", "MQ": "PT", "AB": "PT", "GR": "GR", "MP": "MP", "C3": "MP", "EN": "INSUMO", "SU": "INSUMO"}


# ------------------------------ utilidades ---------------------------------
def product_kind(product):
    if product is None:
        return ""
    if product.tipo in ("PT", "GR", "MP", "INSUMO"):
        return product.tipo
    return PREFIJO_TIPO.get(product.code[:2].upper(), product.tipo or "")


def reserved_qty(lot):
    return sum(r.cantidad for r in lot.reservations if r.estado == "ACTIVA")


def base_qty(lot):
    """Cantidad física utilizable: si un conteo verificó una cantidad menor a la de SAP, manda el conteo."""
    if lot.cantidad_verificada is not None:
        return min(lot.cantidad, lot.cantidad_verificada)
    return lot.cantidad


def held_qty(lot):
    """Cantidad retenida por reempaques en curso sobre parte de un lote disponible."""
    from ..models import RepackRequest
    if lot.id is None or lot.estado != "DISPONIBLE":
        return 0.0
    q = select(RepackRequest).where(RepackRequest.lot_id == lot.id,
                                    RepackRequest.estado.in_(["SOLICITADA", "APROBADA", "EN_EJECUCION"]))
    return sum(r.cantidad for r in db().execute(q).scalars())


def free_qty(lot):
    return max(base_qty(lot) - reserved_qty(lot) - held_qty(lot), 0.0)


def enabled_warehouses():
    """Códigos de los almacenes habilitados en Configuración (los demás no se cargan ni se usan)."""
    return [w for w in db().execute(select(Warehouse.code).where(Warehouse.habilitado.is_(True))).scalars()]


def lot_usable(lot, fecha_compromiso=None, customer=None):
    """(bool, motivo). Condiciones de reserva (IF §6.3, §22)."""
    w = db().get(Warehouse, lot.warehouse_code) if lot.warehouse_code else None
    if w is not None and not w.habilitado:
        return False, f"Almacén {lot.warehouse_code} no habilitado en Configuración"
    if lot.estado != "DISPONIBLE":
        return False, f"Estado {ESTADOS_LABEL.get(lot.estado, lot.estado)}"
    if not lot.verificado:
        return False, "Stock no verificado"
    ref = fecha_compromiso or date.today()
    if lot.fecha_venc and lot.fecha_venc < ref:
        return False, f"Vencido a la fecha comprometida ({lot.fecha_venc:%d/%m/%Y})"
    if customer is not None and lot.fecha_venc:
        from .customer_conditions import min_shelf_date, min_shelf_months
        minimo = customer.vida_util_min_dias or 0
        restante = (lot.fecha_venc - ref).days
        if minimo and restante < minimo:
            return False, f"Vida útil restante {restante} d < mínimo del cliente {minimo} d"
        fmin = min_shelf_date(customer, lot.product, ref)  # R1 (13-oct): vida útil restante mínima, meses calendario
        if fmin and lot.fecha_venc < fmin:
            return False, (f"Vida útil restante insuficiente: vence {lot.fecha_venc:%d/%m/%Y}; el cliente exige "
                           f"{min_shelf_months(customer, lot.product)} meses (vencimiento desde {fmin:%d/%m/%Y})")
    return True, ""


def _sort_lots(lots):
    if param("politica_lotes", "FEFO") == "FEFO":
        return sorted(lots, key=lambda l: (l.fecha_venc or date.max, l.id))
    return sorted(lots, key=lambda l: l.id)


def principal_warehouses(product):
    uso = (param("uso_almacen_por_tipo", {}) or {}).get(product_kind(product))
    if not uso:
        return []
    return list(db().execute(select(Warehouse).where(Warehouse.uso == uso, Warehouse.reservable.is_(True),
                                                     Warehouse.habilitado.is_(True)).order_by(Warehouse.prioridad)).scalars())


def alternative_warehouses():
    return list(db().execute(select(Warehouse).where(Warehouse.uso == "ALTERNATIVO", Warehouse.habilitado.is_(True))
                             .order_by(Warehouse.prioridad)).scalars())


def lots_of(product_code, warehouse_codes=None):
    q = select(StockLot).where(StockLot.product_code == product_code, StockLot.cantidad > 0)
    if warehouse_codes is not None:
        q = q.where(StockLot.warehouse_code.in_(warehouse_codes))
    return list(db().execute(q).scalars())


def stock_freshness():
    """Fecha y origen de la última actualización de stock (IF §2, §19)."""
    b = db().execute(select(UploadBatch).where(UploadBatch.tipo == "STOCK", UploadBatch.estado == "CONFIRMADO")
                     .order_by(UploadBatch.confirmado_ts.desc())).scalars().first()
    if b is None:
        return None
    return {"ts": b.confirmado_ts, "archivo": b.archivo, "usuario": b.user.nombre if b.user else "", "id": b.id}


def product_stock_summary(product_code):
    """Cantidades por estado (RESERVADO separado del DISPONIBLE libre)."""
    out = {k: 0.0 for k in ESTADOS_LABEL}
    for lot in lots_of(product_code):
        if lot.estado == "DISPONIBLE":
            r = reserved_qty(lot)
            out["RESERVADO"] += r
            out["DISPONIBLE"] += max(base_qty(lot) - r, 0)
        else:
            out[lot.estado] = out.get(lot.estado, 0) + lot.cantidad
    return out


# ------------------------------ prioridad ----------------------------------
def priority_key(order):
    keys = []
    for crit in param("orden_prioridad", ["fecha_compromiso", "completitud", "urgencia"]) or []:
        if crit == "fecha_compromiso":
            keys.append(order.fecha_compromiso or date.max)
        elif crit == "completitud":
            keys.append(-(order.cobertura_unidades or 0))
        elif crit == "urgencia":
            keys.append(0 if order.urgente else 1)
        elif crit == "penalidad":
            from .customer_conditions import penalty_score
            keys.append(-penalty_score(order.customer))
    keys.append(order.id)
    return tuple(keys)


# ------------------------------ reservas -----------------------------------
def _best_lots(candidatos, usados, maxl, falta):
    """Elige hasta (maxl − lotes ya usados) lotes nuevos que cubran lo que falta con la menor cantidad de lotes,
    respetando FEFO entre opciones equivalentes (condición del cliente: N lotes por SKU)."""
    from itertools import combinations
    cupo = maxl - len(usados)
    if cupo <= 0:
        return [l for l in candidatos if l.id in usados]
    nuevos = [l for l in candidatos if l.id not in usados][:30]
    mejor, mejor_cub = [], -1.0
    for k in range(1, cupo + 1):
        for combo in combinations(nuevos, k):  # en orden FEFO: la primera combinación que cubre es la más antigua
            cub = min(sum(free_qty(l) for l in combo), falta)
            if cub > mejor_cub + 1e-9:
                mejor, mejor_cub = list(combo), cub
            if cub >= falta - 1e-9:
                return [l for l in candidatos if l.id in usados] + list(combo)
    return [l for l in candidatos if l.id in usados] + mejor
def line_reserved(line):
    return sum(r.cantidad for r in line.reservations if r.estado == "ACTIVA")


def _release(res, motivo):
    res.estado = "LIBERADA"
    res.motivo_liberacion = motivo[:200]


def release_order(order, motivo):
    n = 0
    for line in order.lines:
        for r in line.reservations:
            if r.estado == "ACTIVA":
                _release(r, motivo)
                n += 1
    return n


def reserve_from(order):
    """Primer día en que se puede reservar stock para la OV: plazo máximo de reserva antes del despacho (14-oct:
    7 días, por el espacio físico del almacén). None si el parámetro no está definido."""
    dias = param("plazo_max_reserva_dias", 7)
    if dias in (None, "") or order.fecha_compromiso is None:
        return None
    return order.fecha_compromiso - timedelta(days=int(dias))


def is_deferred(order, hoy=None):
    desde = reserve_from(order)
    return desde is not None and (hoy or date.today()) < desde and order.estado in ("REGISTRADA", "EVALUADA")


def _evaluate_deferred(order, user, motivo, por_aprobar=False):
    """Evalúa sin apartar stock (libera lo que tuviera) y calcula la cobertura proyectada con el stock libre:
    - OV con despacho más allá del plazo máximo de reserva: se reserva sola al entrar al plazo (estado DIFERIDA).
    - OV que espera una aprobación (precio en el límite o bajo el mínimo/costo): no se reserva ni se generan
      pre-solicitudes hasta que el Coordinador o el Jefe Comercial apruebe (estado POR_APROBAR, decisión del 14-oct)."""
    customer = order.customer
    resumen = []
    total_req = total_proj = 0.0
    for line in order.lines:
        for r in line.reservations:
            if r.estado == "ACTIVA":
                _release(r, "OV pendiente de aprobación comercial (precio): no se reserva hasta aprobar" if por_aprobar else
                         f"Reserva diferida: la OV sale el {order.fecha_compromiso:%d/%m/%Y} (plazo máximo de reserva)")
        if not line.activa:
            continue
        product = db().get(Product, line.product_code)
        principales = [w.code for w in principal_warehouses(product)]
        necesario = max(line.cantidad - line.despachado, 0)
        libre = sum(free_qty(l) for l in lots_of(line.product_code, principales)
                    if lot_usable(l, order.fecha_compromiso, customer)[0])
        proy = min(libre, necesario)
        total_req += necesario
        total_proj += proy
        resumen.append({"line_id": line.id, "producto": line.product_code, "solicitado": necesario, "reservado": 0,
                        "proyectado": proy, "faltante": max(necesario - proy, 0), "almacenes": principales})
    desde = reserve_from(order)
    order.cobertura_unidades = round(100.0 * total_proj / total_req, 2) if total_req else 100.0
    order.cobertura_lineas = round(100.0 * sum(1 for r in resumen if r["faltante"] <= 1e-9) / len(resumen), 2) if resumen else 100.0
    order.estado_stock = "POR_APROBAR" if por_aprobar else "DIFERIDA"
    order.evaluado_ts = now()
    if order.estado == "REGISTRADA":
        order.estado = "EVALUADA"
    if por_aprobar:
        order.motivo_detencion = ("Detenida por precio: requiere la aprobación del Coordinador o Jefe Comercial. No se reserva "
                                  "stock ni se generan pre-solicitudes hasta aprobar. Cobertura proyectada con stock libre "
                                  f"hoy: {order.cobertura_unidades}%.")
    else:
        order.motivo_detencion = (f"Reserva diferida: se reserva automáticamente desde el {desde:%d/%m/%Y} (plazo máximo de "
                              f"reserva {param('plazo_max_reserva_dias', 7)} días por espacio de almacén). Cobertura "
                              f"proyectada con stock libre hoy: {order.cobertura_unidades}%.")
    falt = [r for r in resumen if r["faltante"] > 1e-9]
    if falt:
        alerts.emit("OV_FALTANTE", f"Faltante proyectado en OV {order.numero} ({order.customer.nombre})",
                    "Con el stock libre de hoy faltaría: " + "; ".join("%s %g" % (r["producto"], r["faltante"]) for r in falt)
                    + (". La OV se reservará cuando se apruebe su precio." if por_aprobar else
                       f". La OV se reserva desde el {desde:%d/%m/%Y}; anticipe reposición o producción."), "SalesOrder",
                    order.id, dedup_key=f"OV_FALTANTE:{order.id}", creado_por=user)
    else:
        alerts.close_by_system(f"OV_FALTANTE:{order.id}", "Sin faltante proyectado.")
    db().flush()
    audit(user, f"OV_EVALUADA_{motivo}", "SalesOrder", order.numero,
          {"por_aprobar": por_aprobar, "diferida_hasta": desde.isoformat() if desde else None,
           "cobertura_proyectada": order.cobertura_unidades, "lineas": resumen})
    from .distribution import sync_order_route
    sync_order_route(order, user, False)
    return resumen


def activate_deferred(user=None, hoy=None):
    """Tarea diaria: reserva las OV diferidas que ya entraron al plazo máximo de reserva (por prioridad)."""
    hoy = hoy or date.today()
    pend = [o for o in db().execute(select(SalesOrder).where(SalesOrder.estado_stock == "DIFERIDA")).scalars()
            if not is_deferred(o, hoy) and o.estado not in ORDEN_ESTADOS_CERRADOS]
    for o in sorted(pend, key=priority_key):
        evaluate_order(o, user, "ACTIVACION_RESERVA", hoy=hoy)
    return len(pend)


def check_expired_reservations(user=None, hoy=None):
    """Reservas activas con más días que el plazo máximo: se alerta para despachar o liberar (no se liberan solas:
    el pedido puede estar en preparación)."""
    hoy = hoy or date.today()
    dias = param("plazo_max_reserva_dias", 7)
    if dias in (None, ""):
        return 0
    lim = now() - timedelta(days=int(dias))
    vencidas = {}
    for r in db().execute(select(Reservation).where(Reservation.estado == "ACTIVA", Reservation.ts < lim)).scalars():
        vencidas.setdefault(r.line.order, []).append(r)
    for o, rs in vencidas.items():
        alerts.emit("RESERVA_VENCIDA", f"OV {o.numero}: stock reservado hace más de {dias} días",
                    f"{len(rs)} reserva(s) desde el {min(r.ts for r in rs):%d/%m/%Y} ocupan espacio en almacén "
                    f"(fecha comprometida {o.fecha_compromiso:%d/%m/%Y}, estado {o.estado}). Despachar, reprogramar o liberar.",
                    "SalesOrder", o.id, dedup_key=f"RESERVA_VENCIDA:{o.id}",
                    extra_users=[o.vendedor_id] if o.vendedor_id else None)
    return len(vencidas)


def evaluate_order(order, user=None, motivo="CREACION", hoy=None):
    """Evalúa y reserva stock para una OV (IF §4.2-4.4, §6.3). Devuelve resumen por línea. 'hoy' permite a la tarea
    programada evaluar el plazo máximo de reserva con su fecha de referencia."""
    s = db()
    if order.estado == "BORRADOR":  # ronda 23-oct-2026: el borrador (sin orden de compra) no reserva stock
        return []
    if order.estado in ORDEN_ESTADOS_CERRADOS:
        raise BusinessError(f"La OV {order.numero} está {order.estado}; no se evalúa.")
    if order.retenida_precio and order.estado in ("REGISTRADA", "EVALUADA"):
        return _evaluate_deferred(order, user, motivo, por_aprobar=True)
    if is_deferred(order, hoy):
        return _evaluate_deferred(order, user, motivo)
    tenia_reservas = any(line_reserved(l) > 0 for l in order.lines)
    customer = order.customer
    resumen = []
    total_req = total_res = 0.0
    lineas_cubiertas = lineas = 0
    for line in order.lines:
        if not line.activa:
            for r in line.reservations:
                if r.estado == "ACTIVA":
                    _release(r, "Línea eliminada de la OV")
            continue
        product = s.get(Product, line.product_code)
        principales = [w.code for w in principal_warehouses(product)]
        # 1) conservar solo reservas válidas
        for r in line.reservations:
            if r.estado != "ACTIVA":
                continue
            ok, why = lot_usable(r.lot, order.fecha_compromiso, customer)
            if not ok:
                _release(r, f"Reserva ya no válida: {why}")
        # 2) si la cantidad bajó, liberar excedente (las más recientes primero)
        reservado = line_reserved(line)
        necesario = max(line.cantidad - line.despachado, 0)
        if reservado > necesario + 1e-9:
            exceso = reservado - necesario
            for r in sorted([r for r in line.reservations if r.estado == "ACTIVA"], key=lambda r: r.id, reverse=True):
                if exceso <= 1e-9:
                    break
                if r.cantidad <= exceso + 1e-9:
                    exceso -= r.cantidad
                    _release(r, "Reducción de cantidad en la OV")
                else:
                    r.cantidad -= exceso
                    exceso = 0
            reservado = line_reserved(line)
        # 3) reservar lo que falta en almacenes principales (respetando el máximo de lotes por SKU del cliente)
        if reservado < necesario - 1e-9:
            from .customer_conditions import max_lots
            maxl = max_lots(customer)
            usados = {r.lot_id for r in line.reservations if r.estado == "ACTIVA"}
            candidatos = [lot for lot in _sort_lots(lots_of(line.product_code, principales))
                          if lot_usable(lot, order.fecha_compromiso, customer)[0] and free_qty(lot) > 1e-9]
            if maxl:
                candidatos = _best_lots(candidatos, usados, maxl, necesario - reservado)
            for lot in candidatos:
                libre = free_qty(lot)
                tomar = min(libre, necesario - reservado)
                res = Reservation(ov_line_id=line.id, lot_id=lot.id, cantidad=tomar, estado="ACTIVA")
                s.add(res)
                line.reservations.append(res)
                lot.reservations.append(res)
                reservado += tomar
                if reservado >= necesario - 1e-9:
                    break
        lineas += 1
        total_req += necesario
        total_res += min(reservado, necesario)
        faltante = max(necesario - reservado, 0)
        if faltante <= 1e-9:
            lineas_cubiertas += 1
        resumen.append({"line_id": line.id, "producto": line.product_code, "solicitado": necesario,
                        "reservado": reservado, "faltante": faltante, "almacenes": principales})
    order.cobertura_unidades = round(100.0 * total_res / total_req, 2) if total_req else 100.0
    order.cobertura_lineas = round(100.0 * lineas_cubiertas / lineas, 2) if lineas else 100.0
    hay_faltante = any(r["faltante"] > 1e-9 for r in resumen)
    order.estado_stock = "COMPLETA" if not hay_faltante else ("SIN_STOCK" if total_res <= 1e-9 else "INCOMPLETA")
    order.evaluado_ts = now()
    if order.estado == "REGISTRADA":
        order.estado = "EVALUADA"
    if hay_faltante and order.decision_parcial != "APROBADA":
        order.motivo_detencion = "Faltante de stock: pendiente de decisión (alternativas / despacho parcial / renegociación)."
    elif not hay_faltante:
        order.motivo_detencion = ""
    s.flush()
    _emit_evaluation_alerts(order, resumen, user, motivo, tenia_reservas)
    from .customer_conditions import check_condition_alerts
    check_condition_alerts(order, user)
    audit(user, f"OV_EVALUADA_{motivo}", "SalesOrder", order.numero,
          {"cobertura_unidades": order.cobertura_unidades, "cobertura_lineas": order.cobertura_lineas,
           "lineas": resumen})
    _after_evaluation(order, user)
    return resumen


def _after_evaluation(order, user):
    """Acciones del TO-BE al quedar la OV completa: aviso, certificado pre-elaborado y ruta automática."""
    from .distribution import sync_order_route
    listo = (order.estado_stock == "COMPLETA" or order.decision_parcial == "APROBADA") and not order.retenida_precio
    if order.estado_stock == "COMPLETA" and not order.completa_notificada:
        order.completa_notificada = True
        alerts.emit("OV_COMPLETA", f"OV {order.numero} completa: stock reservado al 100 %",
                    f"Cliente {order.customer.nombre}; fecha comprometida {order.fecha_compromiso:%d/%m/%Y}.",
                    "SalesOrder", order.id, creado_por=user)
    if listo and param("certificado_previo_al_picking", True):
        from .quality import autogenerate_for_order
        autogenerate_for_order(order, user)
    if listo:  # preprogramación del picking por persona (observaciones al demo v0.6)
        from .picking import preschedule
        preschedule(order, user)
    sync_order_route(order, user, listo)


def _emit_evaluation_alerts(order, resumen, user, motivo, tenia_reservas):
    faltantes = [r for r in resumen if r["faltante"] > 1e-9]
    vendedor = [order.vendedor_id] if order.vendedor_id else []
    if motivo == "MODIFICACION" and tenia_reservas:
        lista = ", ".join("%s=%g" % (r["producto"], r["faltante"]) for r in faltantes) or "ninguno"
        alerts.emit("OV_CAMBIO", f"OV {order.numero} modificada tras reservar (v{order.version})",
                    f"Cobertura recalculada: {order.cobertura_unidades}% unidades / {order.cobertura_lineas}% líneas. "
                    f"Faltantes: {lista}.", "SalesOrder", order.id, creado_por=user)
    if faltantes:
        detalle = "; ".join("%s: solicitado %g, reservado %g, faltante %g"
                            % (r["producto"], r["solicitado"], r["reservado"], r["faltante"]) for r in faltantes)
        a = alerts.emit("OV_FALTANTE", f"Faltante en OV {order.numero} ({order.customer.nombre})",
                        f"Cobertura {order.cobertura_unidades}% unidades / {order.cobertura_lineas}% líneas. {detalle}. "
                        f"Revise alternativas en la OV.", "SalesOrder", order.id,
                        dedup_key=f"OV_FALTANTE:{order.id}", creado_por=user)
        if a is not None and a.mensaje and detalle not in a.mensaje:
            from ..models import AlertEvent
            db().add(AlertEvent(alert_id=a.id, accion="ACTUALIZADA", comentario=f"Reevaluación ({motivo}): {detalle}"))
        from .presolicitudes import generate_for_order
        generate_for_order(order, user)
        if order.cobertura_unidades > 0 and order.decision_parcial in ("", "RECHAZADA"):
            order.decision_parcial = "PENDIENTE"
            order.parcial_aprobaciones = {}
            from .customer_conditions import for_customer
            cond = for_customer(order.customer)
            aviso = ""
            if cond is not None and cond.fill_rate_min_pct and order.cobertura_unidades < cond.fill_rate_min_pct:
                aviso = (f" ATENCIÓN: el cliente penaliza fill rate < {cond.fill_rate_min_pct:g}% "
                         f"({cond.penalidades.splitlines()[0] if cond.penalidades else ''}).")
            alerts.emit("OV_DECISION_PARCIAL", f"Decidir despacho parcial de OV {order.numero}",
                        f"Hay {order.cobertura_unidades}% de unidades reservadas. Decidir despacho parcial, renegociar "
                        f"fecha o cambiar producto.{aviso}", "SalesOrder", order.id, extra_users=vendedor,
                        dedup_key=f"OV_DECISION_PARCIAL:{order.id}", creado_por=user)
    else:
        alerts.close_by_system(f"OV_FALTANTE:{order.id}", "Faltante cubierto tras reevaluación.")
        alerts.close_by_system(f"OV_DECISION_PARCIAL:{order.id}", "OV completa; ya no requiere despacho parcial.")
        if order.decision_parcial == "PENDIENTE":
            order.decision_parcial = ""


def reevaluate_pending(user=None, product_codes=None):
    """Reevalúa OV con faltante por orden de prioridad (al ingresar stock)."""
    s = db()
    q = select(SalesOrder).where(SalesOrder.estado_stock.in_(["INCOMPLETA", "SIN_STOCK"]),
                                 SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS + ("EN_RUTA",)))
    orders = list(s.execute(q).scalars())
    if product_codes is not None:
        pcs = set(product_codes)
        orders = [o for o in orders if any(l.product_code in pcs for l in o.lines)]
    orders.sort(key=priority_key)
    for o in orders:
        evaluate_order(o, user, "REEVALUACION")
    return len(orders)


# ------------------------------ alternativas -------------------------------
def alternatives_for_order(order):
    """Alternativas ante faltante (IF §4.4, §6.2): otros almacenes, reempaque, producción, compra.
    Solo se presentan; las decisiones las toman las personas responsables."""
    s = db()
    out = []
    alt_wh = alternative_warehouses()
    alt_codes = [w.code for w in alt_wh]
    for line in order.lines:
        if not line.activa:
            continue
        necesario = max(line.cantidad - line.despachado, 0)
        falt = necesario - line_reserved(line)
        if falt <= 1e-9:
            continue
        product = s.get(Product, line.product_code)
        item = {"line": line, "faltante": falt, "otros_almacenes": [], "reempaque": [], "produccion": None, "compra": None}
        # a) otros almacenes (no se ejecuta traslado automático)
        for lot in _sort_lots(lots_of(line.product_code, alt_codes)):
            ok, why = lot_usable(lot, order.fecha_compromiso, order.customer)
            libre = free_qty(lot) if ok else 0
            item["otros_almacenes"].append({"lot": lot, "libre": libre, "apto": ok, "motivo": why})
        # b) reempaque: mismo producto con lotes no aptos por fecha / otros productos del mismo producto base
        principales = [w.code for w in principal_warehouses(product)]
        for lot in lots_of(line.product_code, principales + alt_codes):
            ok, why = lot_usable(lot, order.fecha_compromiso, order.customer)
            if not ok and lot.estado == "DISPONIBLE" and ("Vencido" in why or "Vida útil" in why):
                item["reempaque"].append({"tipo": "ACTUALIZACION_FECHA", "lot": lot, "cantidad": free_qty(lot), "motivo": why})
        if product and product.producto_base:
            similares = s.execute(select(Product).where(Product.producto_base == product.producto_base,
                                                        Product.code != product.code)).scalars()
            for p2 in similares:
                for lot in lots_of(p2.code, principales):
                    ok, _ = lot_usable(lot, order.fecha_compromiso, order.customer)
                    libre = free_qty(lot) if ok else 0
                    if libre > 0:
                        tipo = "CONVERSION_CALIDAD" if (p2.calidad and product.calidad and p2.calidad != product.calidad) else "CAMBIO_PRESENTACION"
                        permitidas = param("conversiones_calidad_permitidas", []) or []
                        if tipo == "CONVERSION_CALIDAD" and permitidas and f"{p2.calidad}>{product.calidad}" not in permitidas:
                            continue  # conversión no permitida por la configuración de Calidad
                        item["reempaque"].append({"tipo": tipo, "lot": lot, "cantidad": libre,
                                                  "motivo": f"{p2.code} {p2.descripcion} ({p2.presentacion or '-'})"})
        # c) producción
        from .production import material_requirements
        req = material_requirements(line.product_code, falt)
        if req["bom_encontrada"]:
            item["produccion"] = req
        # d) compra (artículos sin lista de materiales)
        if not req["bom_encontrada"]:
            item["compra"] = {"cantidad": falt, "kind": product_kind(product)}
        out.append(item)
    return out


# ------------------------------ estados de lote ----------------------------
def change_lot_state(lot, nuevo, user, motivo):
    if nuevo not in ESTADOS_FISICOS:
        raise BusinessError("Estado no válido. 'Reservado' se deriva de las reservas.")
    if not motivo.strip():
        raise BusinessError("Indique el motivo del cambio de estado.")
    from .core import check_warehouse_scope
    check_warehouse_scope(user, lot.warehouse_code)
    anterior = lot.estado
    if anterior == nuevo:
        return []
    afectadas = []
    if anterior == "DISPONIBLE":
        for r in list(lot.reservations):
            if r.estado == "ACTIVA":
                _release(r, f"Lote pasó a {ESTADOS_LABEL[nuevo]}")
                afectadas.append(r.line.order)
    twin = db().execute(select(StockLot).where(StockLot.product_code == lot.product_code,
                                               StockLot.warehouse_code == lot.warehouse_code, StockLot.lote == lot.lote,
                                               StockLot.estado == nuevo, StockLot.id != lot.id)).scalars().first()
    if twin is not None:
        # fusiona el segmento con el existente en el estado destino
        twin.cantidad += lot.cantidad
        if twin.cantidad_verificada is not None:
            twin.cantidad_verificada += lot.cantidad
        twin.motivo_estado = motivo.strip()
        twin.estado_anterior = anterior
        lot.cantidad = 0
        lot.cantidad_verificada = 0 if lot.cantidad_verificada is not None else None
        lot.motivo_estado = f"Fusionado en segmento #{twin.id} ({nuevo})"
        lot = twin
    else:
        lot.estado_anterior = anterior
        lot.estado = nuevo
        lot.motivo_estado = motivo.strip()
    audit(user, "LOTE_ESTADO", "StockLot", lot.id, {"de": anterior, "a": nuevo, "motivo": motivo,
                                                     "producto": lot.product_code, "lote": lot.lote})
    if nuevo == "NO_UTILIZABLE":
        alerts.emit("STOCK_NO_UTILIZABLE", f"Lote {lot.lote} de {lot.product_code} no utilizable",
                    f"Almacén {lot.warehouse_code}. Motivo: {motivo}", "StockLot", lot.id, creado_por=user)
    if nuevo == "EN_FUMIGACION" or (anterior == "EN_FUMIGACION"):
        alerts.emit("FUMIGACION", f"Fumigación {'iniciada' if nuevo == 'EN_FUMIGACION' else 'finalizada'}: lote {lot.lote}",
                    f"{lot.product_code} en {lot.warehouse_code}. {motivo}", "StockLot", lot.id, creado_por=user)
    if nuevo == "PENDIENTE_REVISION":
        alerts.emit("STOCK_PENDIENTE_REVISION", f"Lote {lot.lote} pendiente de revisión",
                    f"{lot.product_code} en {lot.warehouse_code}. {motivo}", "StockLot", lot.id, creado_por=user)
    db().flush()
    for o in dict.fromkeys(afectadas):
        alerts.emit("RESERVA_AFECTADA", f"Reserva liberada en OV {o.numero}",
                    f"El lote {lot.lote} pasó a {ESTADOS_LABEL[nuevo]}; se reevalúa la OV.", "SalesOrder", o.id,
                    creado_por=user)
        if o.estado not in ORDEN_ESTADOS_CERRADOS:
            evaluate_order(o, user, "REEVALUACION")
    if nuevo == "DISPONIBLE" and param("reevaluar_tras_carga", True):
        reevaluate_pending(user, [lot.product_code])
    return afectadas


def add_or_increase_lot(product_code, warehouse_code, lote, cantidad, estado, fecha_venc=None, fecha_fab=None,
                        origen="", verificado=True):
    s = db()
    lot = s.execute(select(StockLot).where(StockLot.product_code == product_code, StockLot.warehouse_code == warehouse_code,
                                           StockLot.lote == lote, StockLot.estado == estado)).scalars().first()
    if lot is None:
        lot = StockLot(product_code=product_code, warehouse_code=warehouse_code, lote=lote, cantidad=0, estado=estado,
                       fecha_venc=fecha_venc, fecha_fab=fecha_fab, fecha_admision=date.today(), origen=origen,
                       verificado=verificado, fecha_verificacion=now() if verificado else None)
        s.add(lot)
    lot.cantidad += cantidad
    if lot.cantidad_verificada is not None:
        lot.cantidad_verificada += cantidad
    if fecha_venc and not lot.fecha_venc:
        lot.fecha_venc = fecha_venc
    s.flush()
    return lot


def consume_order(order, user):
    """Descarga el stock reservado/preparado al confirmar la salida del despacho."""
    s = db()
    total = 0.0
    for line in order.lines:
        if not line.activa:
            continue
        a_despachar = line.preparado if line.preparado > 0 else line_reserved(line)
        restante = a_despachar
        for r in sorted([r for r in line.reservations if r.estado == "ACTIVA"], key=lambda r: r.id):
            if restante <= 1e-9:
                _release(r, "Excedente no despachado")
                continue
            q = min(r.cantidad, restante)
            r.lot.cantidad = max(r.lot.cantidad - q, 0)
            if r.lot.cantidad_verificada is not None:
                r.lot.cantidad_verificada = max(r.lot.cantidad_verificada - q, 0)
            restante -= q
            if q < r.cantidad:
                r.cantidad = q
            r.estado = "CONSUMIDA"
        despachado = a_despachar - restante
        line.despachado += despachado
        total += despachado
        if despachado > 0:
            s.add(SalesHistory(product_code=line.product_code, fecha=date.today(), cantidad=despachado,
                               documento=order.numero, origen="DESPACHO"))
    return total


def expiring_lots(dias):
    lim = date.today() + timedelta(days=dias)
    return list(db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.fecha_venc.is_not(None),
                                                    StockLot.fecha_venc <= lim, StockLot.estado == "DISPONIBLE")).scalars())


def has_active_bom(product_code):
    v = db().execute(select(BOMVersion).where(BOMVersion.activa.is_(True))).scalars().first()
    if v is None:
        return False
    return db().execute(select(func.count(BOMLine.id)).where(BOMLine.version_id == v.id,
                                                             BOMLine.padre == product_code)).scalar() > 0
