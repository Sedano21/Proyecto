"""Producción: lista de materiales, cálculo proporcional con merma, solicitud preliminar, validación,
programación, inicio/fin, liquidación y recepción de PT (IF §8)."""
from datetime import date

from sqlalchemy import func, select

from ..db import db
from ..models import (BOMLine, BOMVersion, Liquidation, Product, ProductionLine, ProductionRequest, SalesHistory,
                      StockLot, Warehouse, now)
from . import alerts
from .core import BusinessError, audit, param


def active_bom():
    return db().execute(select(BOMVersion).where(BOMVersion.activa.is_(True)).order_by(BOMVersion.version.desc())).scalars().first()


def _is_material(code):
    return not any(code.startswith(p) for p in (param("prefijos_no_material_bom", ["RE-"]) or []))


def _merma_pct(parent_code, comp_code):
    """Nivel de aplicación: material > producto > global (IF §8.1, §16)."""
    s = db()
    comp = s.get(Product, comp_code)
    if comp is not None and comp.merma_pct is not None:
        return comp.merma_pct, "material"
    par = s.get(Product, parent_code)
    if par is not None and par.merma_pct is not None:
        return par.merma_pct, "producto"
    g = param("merma_pct_global")
    if g is not None:
        return float(g), "global"
    return 0.0, "sin definir"


def available_in(product_code, warehouse_codes=None):
    from .stock import free_qty, lot_usable
    q = select(StockLot).where(StockLot.product_code == product_code, StockLot.cantidad > 0)
    if warehouse_codes:
        q = q.where(StockLot.warehouse_code.in_(warehouse_codes))
    total = 0.0
    for lot in db().execute(q).scalars():
        ok, _ = lot_usable(lot)
        if ok:
            total += free_qty(lot)
    return total


def material_requirements(product_code, cantidad, version=None):
    """Cálculo proporcional: requerido = cantidad_componente / cantidad_BOM × cantidad_a_producir × (1 + merma).
    La merma solo se aplica si se confirmó que el Excel NO la incluye (evita doble contabilización)."""
    v = version or active_bom()
    res = {"bom_encontrada": False, "producto": product_code, "cantidad": cantidad, "materiales": [], "recursos": [],
           "factible": False, "avisos": [], "version": v.version if v else None}
    if v is None:
        res["avisos"].append("No hay lista de materiales activa cargada.")
        return res
    lines = list(db().execute(select(BOMLine).where(BOMLine.version_id == v.id, BOMLine.padre == product_code)
                              .order_by(BOMLine.orden.is_(None).desc(), BOMLine.orden)).scalars())
    if not lines:
        res["avisos"].append(f"El producto {product_code} no tiene lista de materiales en la versión {v.version}.")
        return res
    res["bom_encontrada"] = True
    res["incluye_merma"] = v.incluye_merma
    aplicar_merma = v.incluye_merma == "NO"
    if v.incluye_merma == "NO_VERIFICADO":
        res["avisos"].append("Merma NO aplicada: falta confirmar si el Excel ya incorpora pérdidas (IF §8.1).")
    elif v.incluye_merma == "SI":
        res["avisos"].append("Merma NO aplicada: la lista de materiales ya incorpora pérdidas.")
    factible = True
    for bl in lines:
        base = bl.cantidad / (bl.cantidad_bom or 1) * cantidad
        if not _is_material(bl.componente):
            res["recursos"].append({"componente": bl.componente, "descripcion": bl.componente_desc, "requerido": base})
            continue
        merma, nivel = _merma_pct(product_code, bl.componente) if aplicar_merma else (0.0, "no aplica")
        requerido = base * (1 + (merma or 0) / 100.0)
        disp_bom = available_in(bl.componente, [bl.almacen_comp] if bl.almacen_comp else None)
        disp_total = available_in(bl.componente)
        falt = max(requerido - disp_bom, 0)
        comp = db().get(Product, bl.componente)
        if falt > 1e-9:
            factible = False
        res["materiales"].append({
            "componente": bl.componente, "descripcion": bl.componente_desc, "por_unidad": bl.cantidad / (bl.cantidad_bom or 1),
            "requerido_base": base, "merma_pct": merma, "merma_nivel": nivel, "requerido": requerido,
            "almacen": bl.almacen_comp, "disponible_almacen": disp_bom, "disponible_total": disp_total, "faltante": falt,
            "tipo": comp.tipo if comp else bl.componente[:2], "es_mp_granel": bl.componente[:2] in ("MP", "GR", "C3"),
        })
    res["factible"] = factible
    return res


def _json_safe(analisis):
    return {k: v for k, v in analisis.items()}


# ----------------------------- solicitud preliminar ------------------------
def create_request(product_code, cantidad, user, order=None, fecha_requerida=None, origen="OV", repack=None, observacion=""):
    if cantidad <= 0:
        raise BusinessError("La cantidad a producir debe ser mayor que cero.")
    p = db().get(Product, product_code)
    if p is None:
        raise BusinessError(f"Producto {product_code} no existe en el catálogo.")
    analisis = material_requirements(product_code, cantidad)
    v = active_bom()
    r = ProductionRequest(order_id=order.id if order else None, product_code=product_code, cantidad=cantidad,
                          fecha_requerida=fecha_requerida or (order.fecha_compromiso if order else None),
                          origen=origen, repack_id=repack.id if repack else None, analisis=analisis,
                          bom_version_id=v.id if v else None, creado_por=user.id if user else None,
                          observacion=observacion)
    db().add(r)
    db().flush()
    audit(user, "PRODUCCION_SOLICITUD_CREADA", "ProductionRequest", r.id, {"producto": product_code, "cantidad": cantidad})
    return r


def refresh_analysis(req):
    req.analisis = material_requirements(req.product_code, req.cantidad)


def send_request(req, user):
    if req.estado not in ("BORRADOR", "RECHAZADA"):
        raise BusinessError("Solo se envían solicitudes en borrador o rechazadas.")
    refresh_analysis(req)
    req.estado = "ENVIADA"
    req.enviado_por = user.id
    a = req.analisis
    falt = [m for m in a.get("materiales", []) if m["faltante"] > 1e-9]
    alerts.emit("PRODUCCION_SOLICITUD", f"Solicitud de producción #{req.id}: {req.product_code} × {req.cantidad:g}",
                f"Fecha requerida: {req.fecha_requerida or '-'}. OV: {req.order.numero if req.order else '-'}. "
                f"Materiales con faltante: {len(falt)}.", "ProductionRequest", req.id, creado_por=user)
    audit(user, "PRODUCCION_SOLICITUD_ENVIADA", "ProductionRequest", req.id)


def validate_request(req, user, aprobar, lista_ok, disponibilidad_ok, capacidad_ok, plazo_ok, comentario=""):
    if req.estado != "ENVIADA":
        raise BusinessError("Solo se validan solicitudes enviadas.")
    if aprobar and not (lista_ok and disponibilidad_ok and capacidad_ok and plazo_ok):
        raise BusinessError("Para validar deben confirmarse lista de insumos, disponibilidad real, capacidad y plazo (IF §8.2).")
    if not aprobar and not comentario.strip():
        raise BusinessError("Indique el motivo del rechazo.")
    req.validacion = {"lista_ok": lista_ok, "disponibilidad_ok": disponibilidad_ok, "capacidad_ok": capacidad_ok,
                      "plazo_ok": plazo_ok, "comentario": comentario, "ts": now().isoformat(), "user": user.nombre}
    req.validado_por = user.id
    req.estado = "VALIDADA" if aprobar else "RECHAZADA"
    alerts.emit("PRODUCCION_RESPUESTA", f"Solicitud de producción #{req.id} {req.estado.lower()}",
                comentario, "ProductionRequest", req.id,
                extra_users=[req.order.vendedor_id] if req.order and req.order.vendedor_id else None, creado_por=user)
    audit(user, f"PRODUCCION_{req.estado}", "ProductionRequest", req.id, req.validacion)


def line_load_kg(line_code, fecha, exclude_id=None):
    total = 0.0
    q = select(ProductionRequest).where(ProductionRequest.line_code == line_code, ProductionRequest.fecha_programada == fecha,
                                        ProductionRequest.estado.in_(["PROGRAMADA", "EN_PROCESO"]))
    for r in db().execute(q).scalars():
        if r.id == exclude_id:
            continue
        total += r.cantidad * (r.product.peso_kg or 0)
    return total


def schedule(req, user, line_code, fecha):
    if req.estado not in ("VALIDADA", "PROGRAMADA"):
        raise BusinessError("Solo se programan solicitudes validadas.")
    line = db().get(ProductionLine, line_code)
    if line is None or not line.activa:
        raise BusinessError("Línea de producción no válida.")
    avisos = []
    kg = req.cantidad * (req.product.peso_kg or 0)
    if line.capacidad_kg_dia:
        carga = line_load_kg(line_code, fecha, req.id) + kg
        if carga > line.capacidad_kg_dia + 1e-9:
            raise BusinessError(f"Capacidad excedida en {line.nombre} el {fecha:%d/%m/%Y}: {carga:,.0f} kg > "
                                f"{line.capacidad_kg_dia:,.0f} kg/día.")
    else:
        avisos.append(f"Capacidad de {line.nombre} no configurada: no se verifica (dato informado por Producción, IF §8.2).")
    if req.fecha_requerida and fecha > req.fecha_requerida:
        avisos.append(f"Fecha programada posterior a la fecha requerida ({req.fecha_requerida:%d/%m/%Y}).")
    req.line_code = line_code
    req.fecha_programada = fecha
    req.estado = "PROGRAMADA"
    audit(user, "PRODUCCION_PROGRAMADA", "ProductionRequest", req.id, {"linea": line_code, "fecha": fecha, "avisos": avisos})
    return avisos


def start(req, user):
    if req.estado != "PROGRAMADA":
        raise BusinessError("Solo se inician órdenes programadas.")
    req.estado = "EN_PROCESO"
    req.inicio_ts = now()
    audit(user, "PRODUCCION_INICIO", "ProductionRequest", req.id)


def finish(req, user):
    if req.estado != "EN_PROCESO":
        raise BusinessError("Solo se finalizan órdenes en proceso.")
    req.estado = "FINALIZADA"
    req.fin_ts = now()
    audit(user, "PRODUCCION_FIN", "ProductionRequest", req.id)


# ----------------------------- liquidación ---------------------------------
def register_liquidation(user, numero_documento, product_code, cantidad_completada, lote, fecha_fab=None, fecha_venc=None,
                         cantidad_planificada=None, request=None, origen="MANUAL", almacen="", valorizado=None,
                         realizado_por="", merma_mp_kg=None, merma_granel_kg=None, merma_insumos=None, fecha=None):
    s = db()
    if not numero_documento:
        raise BusinessError("Número de documento obligatorio.")
    if s.execute(select(Liquidation).where(Liquidation.numero_documento == str(numero_documento),
                                           Liquidation.lote == str(lote or ""))).scalars().first():
        raise BusinessError(f"La liquidación {numero_documento} / lote {lote} ya fue registrada (se evita duplicado).")
    if s.get(Product, product_code) is None:
        raise BusinessError(f"Producto {product_code} no existe.")
    if cantidad_completada is None or cantidad_completada < 0:
        raise BusinessError("Cantidad completada inválida.")
    if not lote:
        raise BusinessError("El lote es obligatorio (alimenta certificados de Calidad).")
    liq = Liquidation(numero_documento=str(numero_documento), request_id=request.id if request else None,
                      product_code=product_code, cantidad_planificada=cantidad_planificada or (request.cantidad if request else 0),
                      cantidad_completada=cantidad_completada, lote=lote, fecha_fab=fecha_fab, fecha_venc=fecha_venc,
                      origen=origen, almacen=almacen, valorizado=valorizado, realizado_por=realizado_por,
                      merma_mp_kg=merma_mp_kg, merma_granel_kg=merma_granel_kg, merma_insumos=merma_insumos or {},
                      fecha=fecha or date.today())
    s.add(liq)
    s.flush()
    if request is not None:
        if request.estado in ("PROGRAMADA", "EN_PROCESO"):
            request.fin_ts = request.fin_ts or now()
        request.estado = "LIQUIDADA"
    # consumo de materiales (para historial de reposición). El stock de materiales se actualiza con la carga SAP.
    req_mat = material_requirements(product_code, cantidad_completada)
    for m in req_mat.get("materiales", []):
        s.add(SalesHistory(product_code=m["componente"], fecha=liq.fecha, cantidad=m["requerido_base"],
                           documento=f"LIQ-{liq.numero_documento}", origen="CONSUMO_PRODUCCION"))
    transito = _transit_wh()
    if transito and cantidad_completada > 0:
        # Q5: Producción deja el producto terminado en el almacén virtual de tránsito (ALM-003) hasta que
        # Almacén lo valida y lo pasa al almacén de producto terminado.
        from .stock import add_or_increase_lot
        add_or_increase_lot(product_code, transito, lote, cantidad_completada, "PENDIENTE_REVISION", fecha_venc, fecha_fab,
                            origen=f"LIQ-{liq.numero_documento}")
    alerts.emit("LIQUIDACION_MONTACARGUISTA", f"Liquidación {liq.numero_documento}: mover PT {product_code}",
                f"Lote {lote}, cantidad {cantidad_completada:g}"
                + (f" en tránsito {transito}" if transito else "") + ". Trasladar producto terminado a almacén para su validación.",
                "Liquidation", liq.id, creado_por=user)
    _check_merma(liq, user)
    audit(user, "LIQUIDACION_REGISTRADA", "Liquidation", liq.numero_documento,
          {"producto": product_code, "cantidad": cantidad_completada, "lote": lote, "origen": origen})
    return liq


def merma_real_pct(liq):
    p = liq.product
    if liq.merma_mp_kg is None or not p or not p.peso_kg:
        return None
    producido_kg = liq.cantidad_completada * p.peso_kg
    total = producido_kg + liq.merma_mp_kg
    return round(100.0 * liq.merma_mp_kg / total, 3) if total else None


def _check_merma(liq, user):
    umbral = param("umbral_merma_pct")
    real = merma_real_pct(liq)
    if umbral is None or real is None:
        return
    if real > float(umbral):
        alerts.emit("MERMA_FUERA_PARAMETRO", f"Merma {real}% en liquidación {liq.numero_documento}",
                    f"Umbral configurado {umbral}%. Producto {liq.product_code}, lote {liq.lote}.", "Liquidation", liq.id,
                    creado_por=user)


def _transit_wh():
    code = param("almacen_transito_produccion", "ALM-003")
    return code if code and db().get(Warehouse, code) is not None else None


def receive_pt(liq, user, cantidad_recibida, presentacion_ok=True, observacion="", warehouse_code=None):
    """Almacén valida cantidades/presentación y registra diferencias (IF §8.3; cruce AS-IS 'Recep. pt.xlsx')."""
    from .stock import add_or_increase_lot, principal_warehouses
    if liq.estado != "REGISTRADA":
        raise BusinessError("La liquidación ya fue recibida.")
    if cantidad_recibida is None or cantidad_recibida < 0:
        raise BusinessError("Cantidad recibida inválida.")
    dif = liq.cantidad_completada - cantidad_recibida
    liq.cantidad_recibida = cantidad_recibida
    liq.diferencia = dif
    liq.presentacion_ok = presentacion_ok
    liq.observacion = observacion
    liq.recibido_por = user.id
    liq.recibido_ts = now()
    liq.estado = "RECIBIDA_COMPLETA" if abs(dif) < 1e-9 else ("RECIBIDA_FALTANTE" if dif > 0 else "RECIBIDA_SOBRANTE")
    if not warehouse_code:
        whs = principal_warehouses(liq.product)
        if not whs:
            raise BusinessError("No hay almacén principal configurado para el tipo de artículo.")
        warehouse_code = whs[0].code
    from .core import check_warehouse_scope
    check_warehouse_scope(user, warehouse_code)
    liq.warehouse_code = warehouse_code
    transito = _transit_wh()
    if transito:  # Q5: sale del tránsito de Producción todo lo liquidado; lo recibido entra al almacén de PT
        t_lot = db().execute(select(StockLot).where(StockLot.product_code == liq.product_code,
                                                    StockLot.warehouse_code == transito, StockLot.lote == liq.lote)
                             ).scalars().first()
        if t_lot is not None:
            t_lot.cantidad = max(t_lot.cantidad - liq.cantidad_completada, 0)
    if cantidad_recibida > 0:
        lot = add_or_increase_lot(liq.product_code, warehouse_code, liq.lote, cantidad_recibida, "PENDIENTE_REVISION",
                                  liq.fecha_venc, liq.fecha_fab, origen=f"LIQ-{liq.numero_documento}")
        liq.lot_id = lot.id
        alerts.emit("STOCK_PENDIENTE_REVISION", f"PT recibido pendiente de liberación: lote {liq.lote}",
                    f"{liq.product_code} × {cantidad_recibida:g} en {warehouse_code}.", "StockLot", lot.id, creado_por=user)
    if abs(dif) > 1e-9 or not presentacion_ok:
        alerts.emit("LIQUIDACION_DIFERENCIA", f"Diferencia en recepción de liquidación {liq.numero_documento}",
                    f"Completado {liq.cantidad_completada:g}, recibido {cantidad_recibida:g} ({liq.estado}). "
                    f"Presentación {'conforme' if presentacion_ok else 'NO conforme'}. {observacion}",
                    "Liquidation", liq.id, creado_por=user)
    audit(user, "LIQUIDACION_RECIBIDA", "Liquidation", liq.numero_documento,
          {"recibido": cantidad_recibida, "diferencia": dif, "estado": liq.estado})


def merma_comparison():
    """Merma prevista (BOM/configuración) vs real (liquidaciones), cuando hay datos (IF §17)."""
    out = []
    for liq in db().execute(select(Liquidation).order_by(Liquidation.fecha.desc())).scalars():
        real = merma_real_pct(liq)
        prevista, nivel = _merma_pct(liq.product_code, liq.product_code)
        out.append({"liq": liq, "real": real, "prevista": prevista if nivel != "sin definir" else None})
    return out


def bom_products():
    v = active_bom()
    if v is None:
        return []
    return list(db().execute(select(BOMLine.padre, func.min(BOMLine.padre_desc)).where(BOMLine.version_id == v.id)
                             .group_by(BOMLine.padre).order_by(BOMLine.padre)).all())
