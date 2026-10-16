"""Producción: lista de materiales, cálculo proporcional con merma, solicitud preliminar, validación,
programación, inicio/fin, liquidación y recepción de PT (IF §8)."""
from datetime import date, timedelta

from sqlalchemy import func, select

from ..db import db
from ..models import (BOMLine, BOMVersion, Liquidation, Product, ProductionLine, ProductionRequest, SalesHistory,
                      SalesOrder, StockLot, Warehouse, now)
from . import alerts
from .core import BusinessError, audit, param


def active_bom():
    return db().execute(select(BOMVersion).where(BOMVersion.activa.is_(True)).order_by(BOMVersion.version.desc())).scalars().first()


def _is_material(code):
    return not any(code.startswith(p) for p in (param("prefijos_no_material_bom", ["RE-"]) or []))


def is_desmedro(code, desc=""):
    """Componente de desmedro (= merma) en la lista de materiales: artículos ME-… 'X - DESMEDRO' (13-oct)."""
    return any(code.startswith(p) for p in (param("prefijos_desmedro_bom", ["ME-"]) or [])) or "DESMEDRO" in (desc or "").upper()


def bom_merma_projection(product_code, version=None):
    """Merma proyectada según el desmedro de la lista de materiales: kg de desmedro por kg del producto padre.
    Valores ≤ 0.001 por unidad se tratan como simbólicos (SAP exige cantidad > 0) y se informan como tales."""
    v = version or active_bom()
    if v is None:
        return None
    lines = [bl for bl in db().execute(select(BOMLine).where(BOMLine.version_id == v.id, BOMLine.padre == product_code)).scalars()
             if is_desmedro(bl.componente, bl.componente_desc)]
    if not lines:
        return None
    p = db().get(Product, product_code)
    kg_padre = (p.peso_kg if p and p.peso_kg else (1.0 if p and (p.um or "").upper().startswith("K") else None))
    por_unidad = sum(bl.cantidad / (bl.cantidad_bom or 1) for bl in lines)
    simbolico = por_unidad <= 0.001 + 1e-12
    pct = round(100 * por_unidad / kg_padre, 3) if kg_padre and not simbolico else None
    return {"componentes": [bl.componente for bl in lines], "kg_por_unidad": por_unidad, "pct": pct, "simbolico": simbolico}


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


def available_by_warehouse(product_code, excluir=None):
    """Stock libre utilizable del componente en cada almacén (para cubrir faltantes desde almacenes externos)."""
    from .stock import free_qty, lot_usable
    out = {}
    for lot in db().execute(select(StockLot).where(StockLot.product_code == product_code, StockLot.cantidad > 0)).scalars():
        if excluir and lot.warehouse_code in excluir:
            continue
        if lot_usable(lot)[0]:
            q = free_qty(lot)
            if q > 1e-9:
                out[lot.warehouse_code] = out.get(lot.warehouse_code, 0.0) + q
    return out


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
    excepciones = (param("excepciones_bom", {}) or {}).get(product_code, {}) or {}
    for bl in lines:
        base = bl.cantidad / (bl.cantidad_bom or 1) * cantidad
        if bl.componente in excepciones:  # excepción a la proporcionalidad lineal (cantidad fija por orden)
            base = float(excepciones[bl.componente])
            res["avisos"].append(f"{bl.componente}: cantidad fija {base:g} por orden (excepción configurada).")
        if not _is_material(bl.componente):
            res["recursos"].append({"componente": bl.componente, "descripcion": bl.componente_desc, "requerido": base})
            continue
        if is_desmedro(bl.componente, bl.componente_desc):
            # el desmedro es la merma proyectada (salida), no un material a consumir
            res.setdefault("desmedro", []).append({"componente": bl.componente, "descripcion": bl.componente_desc,
                                                   "proyectado": base})
            continue
        merma, nivel = _merma_pct(product_code, bl.componente) if aplicar_merma else (0.0, "no aplica")
        requerido = base * (1 + (merma or 0) / 100.0)
        disp_bom = available_in(bl.componente, [bl.almacen_comp] if bl.almacen_comp else None)
        disp_total = available_in(bl.componente)
        falt = max(requerido - disp_bom, 0)
        comp = db().get(Product, bl.componente)
        externos = {}
        if falt > 1e-9:
            factible = False
            # observaciones al demo v0.6: si falta materia prima, revisar si hay en almacenes externos
            externos = available_by_warehouse(bl.componente, [bl.almacen_comp] if bl.almacen_comp else None)
            cubre = sum(externos.values())
            if externos:
                res["avisos"].append(
                    f"{bl.componente}: faltan {falt:g} en el almacén de la lista; hay {cubre:g} en otros almacenes ("
                    + ", ".join(f"{w} {q:g}" for w, q in sorted(externos.items(), key=lambda x: -x[1])) + ")"
                    + (": se puede cubrir con un traslado." if cubre >= falt - 1e-9 else ": cubre solo una parte."))
        res["materiales"].append({
            "componente": bl.componente, "descripcion": bl.componente_desc, "por_unidad": bl.cantidad / (bl.cantidad_bom or 1),
            "requerido_base": base, "merma_pct": merma, "merma_nivel": nivel, "requerido": requerido,
            "almacen": bl.almacen_comp, "disponible_almacen": disp_bom, "disponible_total": disp_total, "faltante": falt,
            "tipo": comp.tipo if comp else bl.componente[:2], "es_mp_granel": bl.componente[:2] in ("MP", "GR", "C3"),
            "otros_almacenes": externos, "cubre_con_traslado": bool(externos) and sum(externos.values()) >= falt - 1e-9,
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
    """Obs. demo v0.7: se puede aprobar la producción aunque no alcancen los materiales; en ese caso el sistema genera
    las presolicitudes de compra de lo que falta, alerta el quiebre de stock y el plazo de reposición."""
    if req.estado != "ENVIADA":
        raise BusinessError("Solo se validan solicitudes enviadas.")
    if aprobar and not (lista_ok and capacidad_ok and plazo_ok):
        raise BusinessError("Para validar deben confirmarse lista de insumos, capacidad y plazo (IF §8.2).")
    if not aprobar and not comentario.strip():
        raise BusinessError("Indique el motivo del rechazo.")
    req.validacion = {"lista_ok": lista_ok, "disponibilidad_ok": disponibilidad_ok, "capacidad_ok": capacidad_ok,
                      "plazo_ok": plazo_ok, "comentario": comentario, "ts": now().isoformat(), "user": user.nombre}
    req.validado_por = user.id
    req.estado = "VALIDADA" if aprobar else "RECHAZADA"
    compras = purchase_missing_materials(req, user) if aprobar else []
    if compras:
        req.validacion = dict(req.validacion, presolicitudes_compra=[r.id for r in compras])
    alerts.emit("PRODUCCION_RESPUESTA", f"Solicitud de producción #{req.id} {req.estado.lower()}",
                comentario + (f" Materiales faltantes: presolicitudes de compra {', '.join('#' + str(r.id) for r in compras)}."
                              if compras else ""), "ProductionRequest", req.id,
                extra_users=[req.order.vendedor_id] if req.order and req.order.vendedor_id else None, creado_por=user)
    audit(user, f"PRODUCCION_{req.estado}", "ProductionRequest", req.id, req.validacion)


def purchase_missing_materials(req, user=None):
    """Presolicitudes de compra de los materiales que faltan para producir (obs. demo v0.7). Se descuenta lo que ya
    está pedido en compras abiertas del mismo material; la presolicitud lleva la OV de origen y el motivo."""
    from .purchasing import OPEN_STATES, create_request
    from ..models import PurchaseRequest
    req_mat = material_requirements(req.product_code, req.cantidad)
    if not req_mat.get("bom_encontrada"):
        return []
    out = []
    for m in req_mat["materiales"]:
        falt = float(m.get("faltante") or 0)
        if falt <= 1e-9:
            continue
        pedido = sum(r.cantidad for r in db().execute(select(PurchaseRequest).where(
            PurchaseRequest.product_code == m["componente"], PurchaseRequest.estado.in_(OPEN_STATES))).scalars())
        q = falt - pedido
        if q <= 1e-9 or db().get(Product, m["componente"]) is None:
            continue
        fecha = req.fecha_requerida or (req.order.fecha_compromiso if req.order else None)
        r = create_request(None, m["componente"], round(q, 4), fecha, origen="PRODUCCION", order=req.order, sistema=True)
        extra = f" Para producir {req.product_code} × {req.cantidad:g} (solicitud de producción #{req.id})."
        if extra not in (r.motivo or ""):
            r.motivo = (r.motivo or "") + extra
        out.append(r)
    return out


def missing_materials_tracking(req):
    """Seguimiento de lo que falta para producir (obs. demo v0.7, Asistente de Producción): por material, faltante, compras
    abiertas y fecha estimada de llegada (OC prevista o plazo de reposición)."""
    from .purchasing import OPEN_STATES, lead_time_for
    from ..models import ImportShipment, PurchaseRequest
    from datetime import timedelta
    req_mat = material_requirements(req.product_code, req.cantidad)
    out = []
    for m in req_mat.get("materiales", []):
        falt = float(m.get("faltante") or 0)
        if falt <= 1e-9:
            continue
        compras = list(db().execute(select(PurchaseRequest).where(PurchaseRequest.product_code == m["componente"],
                                                                   PurchaseRequest.estado.in_(OPEN_STATES))
                                    .order_by(PurchaseRequest.id)).scalars())
        imps = [x for x in db().execute(select(ImportShipment).where(ImportShipment.product_code == m["componente"])).scalars()
                if x.estado not in ("RECIBIDA", "RECIBIDA_CON_DIFERENCIAS", "CERRADA", "ANULADA")]
        llegadas = [(c.fecha_prevista, f"OC {c.numero_oc} (compra #{c.id})") for c in compras if c.fecha_prevista]
        llegadas += [(x.fecha_llegada_estimada, f"importación {x.referencia}") for x in imps if x.fecha_llegada_estimada]
        estimada, fuente = (min(llegadas) if llegadas else (None, ""))
        if estimada is None and compras:
            p = db().get(Product, m["componente"])
            lt, _ = lead_time_for(p) if p else (None, None)
            if lt is not None:
                estimada, fuente = (compras[0].ts.date() if compras[0].ts else date.today()) + timedelta(days=lt.dias_max), \
                    "estimada con el plazo de reposición"
        out.append({"componente": m["componente"], "descripcion": m.get("descripcion"), "faltante": falt,
                    "compras": compras, "importaciones": imps, "llegada": estimada, "fuente": fuente})
    return out


def line_load_kg(line_code, fecha, exclude_id=None):
    total = 0.0
    q = select(ProductionRequest).where(ProductionRequest.line_code == line_code, ProductionRequest.fecha_programada == fecha,
                                        ProductionRequest.estado.in_(["PROGRAMADA", "EN_PROCESO"]))
    for r in db().execute(q).scalars():
        if r.id == exclude_id:
            continue
        total += r.cantidad * (r.product.peso_kg or 0)
    return total


def capacity_group(line_code):
    """Grupo de capacidad (parámetro capacidad_lineas) al que pertenece la línea, o None."""
    for g in param("capacidad_lineas", []) or []:
        if line_code in (g.get("lineas") or []):
            return g
    return None


def day_factor(d):
    """Jornada del día: 1 completa, 0,5 sábado (hasta mediodía), 0 domingo o feriado que no se trabaja."""
    from .calendar import day_factor as _f
    return _f(d)


def schedule(req, user, line_code, fecha):
    if req.estado not in ("VALIDADA", "PROGRAMADA"):
        raise BusinessError("Solo se programan solicitudes validadas.")
    line = db().get(ProductionLine, line_code)
    if line is None or not line.activa:
        raise BusinessError("Línea de producción no válida.")
    avisos = []
    kg = req.cantidad * (req.product.peso_kg or 0)
    grupo = capacity_group(line_code)
    factor = day_factor(fecha)
    if factor <= 0:
        raise BusinessError(f"El {fecha:%d/%m/%Y} no se opera (domingo o feriado): elija otra fecha.")
    if grupo:  # capacidad por grupo de líneas (tabla de capacidades del 14/15-oct), ajustada a la jornada del día
        cap = float(grupo["kg_dia"]) * factor
        carga = sum(line_load_kg(lc, fecha, req.id) for lc in grupo["lineas"]) + kg
        if carga > cap + 1e-9:
            raise BusinessError(f"Capacidad excedida en {grupo['grupo']} el {fecha:%d/%m/%Y}: {carga:,.0f} kg > "
                                f"{cap:,.0f} kg ({grupo['kg_dia']:,.0f} kg/día{' × media jornada' if factor < 1 else ''}).")
    elif line.capacidad_kg_dia:
        cap = line.capacidad_kg_dia * factor
        carga = line_load_kg(line_code, fecha, req.id) + kg
        if carga > cap + 1e-9:
            raise BusinessError(f"Capacidad excedida en {line.nombre} el {fecha:%d/%m/%Y}: {carga:,.0f} kg > "
                                f"{cap:,.0f} kg.")
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
    from .quality import lot_entries_vs_liquidation  # obs. demo v0.7: contraste con el lote registrado por Calidad
    c = lot_entries_vs_liquidation(liq)
    if c and not c["coincide"]:
        alerts.emit("CALIDAD_VS_LIQUIDACION", f"Lote {lote}: Calidad registró {c['calidad']:g} y se liquidó {c['liquidado']:g}",
                    f"{product_code}, liquidación {liq.numero_documento}. Revisar antes de que Almacén confirme la recepción.",
                    "Liquidation", liq.id, dedup_key=f"CAL_LIQ:{liq.id}", creado_por=user)
    audit(user, "LIQUIDACION_REGISTRADA", "Liquidation", liq.numero_documento,
          {"producto": product_code, "cantidad": cantidad_completada, "lote": lote, "origen": origen})
    return liq


def merma_real_pct(liq):
    """% de merma real: desmedro de los partes de producción de la OF (desmedro / peso de entrada); si no hay parte, la
    merma registrada en la liquidación."""
    from ..models import ProductionReport
    partes = list(db().execute(select(ProductionReport).where(ProductionReport.of == liq.numero_documento)).scalars())
    if partes:
        entrada = sum(r.peso_entrada_kg for r in partes)
        perdida = sum(_perdida_kg(r) for r in partes)
        return round(100.0 * perdida / entrada, 3) if entrada else None
    p = liq.product
    if not is_desmedro(liq.product_code):
        # desmedro liquidado en el mismo documento (artículo ME-…)
        mes = [x for x in db().execute(select(Liquidation).where(Liquidation.numero_documento == liq.numero_documento)).scalars()
               if is_desmedro(x.product_code) and x.id != liq.id]
        if mes and p:
            prod_kg = liq.cantidad_completada * (p.peso_kg or (1 if (p.um or "").upper().startswith("K") else 0))
            merma_kg = sum(x.cantidad_completada for x in mes)
            total = prod_kg + merma_kg
            return round(100.0 * merma_kg / total, 3) if total else None
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


def merma_comparison(desde=None, hasta=None):
    """Merma proyectada (desmedro de la lista de materiales; si es simbólico, la merma configurada) vs merma ejecutada
    (partes de producción o desmedro liquidado), por liquidación (IF §17; observaciones del 13-oct)."""
    out = []
    q = select(Liquidation).order_by(Liquidation.fecha.desc())
    if desde:
        q = q.where(Liquidation.fecha >= desde)
    if hasta:
        q = q.where(Liquidation.fecha <= hasta)
    tol = float(param("tolerancia_merma_pp", 1) or 1)
    for liq in db().execute(q).scalars():
        if is_desmedro(liq.product_code):
            continue
        real = merma_real_pct(liq)
        bom = bom_merma_projection(liq.product_code)
        if bom and bom["pct"] is not None:
            prevista, fuente = bom["pct"], "Lista de materiales (desmedro " + ", ".join(bom["componentes"]) + ")"
        else:
            prevista, nivel = _merma_pct(liq.product_code, liq.product_code)
            prevista = prevista if nivel != "sin definir" else None
            fuente = (f"Configuración ({nivel})" if prevista is not None else "Sin merma proyectada") + (
                " – el desmedro de la lista es simbólico" if bom and bom["simbolico"] else "")
        desv = round(real - prevista, 2) if real is not None and prevista is not None else None
        out.append({"liq": liq, "real": real, "prevista": prevista, "fuente": fuente, "desviacion": desv,
                    "fuera": desv is not None and abs(desv) > tol})
    return out


def bom_products():
    v = active_bom()
    if v is None:
        return []
    return list(db().execute(select(BOMLine.padre, func.min(BOMLine.padre_desc)).where(BOMLine.version_id == v.id)
                             .group_by(BOMLine.padre).order_by(BOMLine.padre)).all())


# ----------------------------- partes de producción -------------------------
LINEAS_ENVASADO = ("R1", "R2", "R3", "ENV_MANUAL")


def _perdida_kg(r):
    if r.tipo == "ENVASADO":
        return max(r.peso_entrada_kg - (r.unidades or 0) * (r.presentacion_kg or 0), 0)
    return r.desmedro_kg or 0


def register_report(user, linea, fecha, product_code, peso_entrada_kg, granel_kg=0, mp_kg=0, cal3_kg=0, desmedro_kg=0,
                    presentacion_kg=None, unidades=None, sobrante_kg=0, of="", op="", turno="", hora_inicio="", hora_fin="",
                    horas=None, operarios=None, cliente="", mp_codigo="", lote="", estado="EN PROCESO", observacion="",
                    parada_min=None, motivo_parada=""):
    """Registra el parte de producción con las fórmulas de los formatos actuales:
    selección (Truer, Cimbria, selección manual): total = granel + MP + cal3 + desmedro; % rendimiento = granel / peso;
    % desmedro = desmedro / peso. Envasado (R1-R3): unidades teóricas = peso MP / presentación; % rendimiento =
    unidades / teóricas; desmedro = kg de MP no convertidos en unidades."""
    from ..models import ProductionReport
    from .core import has_perm
    if not has_perm(user, "produccion.liquidar"):
        raise BusinessError("Registra el parte Producción (asistentes de producción).")
    lineas = {c for c, _, _ in __import__("app.catalogs", fromlist=["x"]).PRODUCTION_LINES}
    if linea not in lineas:
        raise BusinessError("Línea de producción no válida.")
    if not product_code or db().get(Product, product_code) is None:
        raise BusinessError("Producto no existe.")
    if not peso_entrada_kg or peso_entrada_kg <= 0:
        raise BusinessError("Indique el peso de entrada (kg de materia prima).")
    tipo = "ENVASADO" if linea in LINEAS_ENVASADO else "SELECCION"
    if estado == "PROGRAMADO":
        # parte programado: lo que se producirá (kg de entrada previstos); los resultados se completan después
        r = ProductionReport(linea=linea, tipo=tipo, fecha=fecha or date.today(), op=op, of=(of or "").strip(), turno=turno,
                             cliente=cliente, product_code=product_code, mp_codigo=mp_codigo, lote=lote,
                             peso_entrada_kg=peso_entrada_kg, presentacion_kg=presentacion_kg, estado="PROGRAMADO",
                             observacion=observacion, user_id=user.id)
        db().add(r)
        db().flush()
        audit(user, "PARTE_PROGRAMADO", "ProductionReport", r.id, {"linea": linea, "fecha": r.fecha.isoformat()})
        return r
    r = ProductionReport(linea=linea, tipo=tipo, fecha=fecha or date.today(), op=op, of=(of or "").strip(), turno=turno,
                         hora_inicio=hora_inicio, hora_fin=hora_fin, horas=horas, operarios=operarios, cliente=cliente,
                         product_code=product_code, mp_codigo=mp_codigo, lote=lote, peso_entrada_kg=peso_entrada_kg,
                         granel_kg=granel_kg or 0, mp_kg=mp_kg or 0, cal3_kg=cal3_kg or 0, desmedro_kg=desmedro_kg or 0,
                         presentacion_kg=presentacion_kg, unidades=unidades, sobrante_kg=sobrante_kg or 0, estado=estado,
                         observacion=observacion, user_id=user.id, parada_min=parada_min,
                         motivo_parada=(motivo_parada or "").strip())
    if tipo == "ENVASADO":
        if not presentacion_kg or unidades is None:
            raise BusinessError("En envasado indique la presentación (kg) y las unidades producidas.")
        teoricas = peso_entrada_kg / presentacion_kg
        r.rendimiento_pct = round(100 * unidades / teoricas, 2) if teoricas else None
        r.granel_kg = unidades * presentacion_kg
        r.desmedro_kg = _perdida_kg(r)
        r.diferencia_kg = round(r.desmedro_kg - (r.cal3_kg or 0) - (r.sobrante_kg or 0), 3)
    else:
        total = r.granel_kg + r.mp_kg + r.cal3_kg + r.desmedro_kg
        r.rendimiento_pct = round(100 * r.granel_kg / peso_entrada_kg, 2)
        r.diferencia_kg = round(peso_entrada_kg - total, 3)
    r.desmedro_pct = round(100 * _perdida_kg(r) / peso_entrada_kg, 2)
    if horas:
        r.ratio_kg_hora = round(r.granel_kg / horas, 1)
    db().add(r)
    db().flush()
    umbral = param("umbral_merma_pct")
    if umbral is not None and r.desmedro_pct > float(umbral):
        alerts.emit("MERMA_FUERA_PARAMETRO", f"Desmedro {r.desmedro_pct}% en {linea} (OF {r.of or '-'})",
                    f"Umbral configurado {umbral}%. Producto {product_code}, lote {lote}. Rendimiento {r.rendimiento_pct}%.",
                    "ProductionRequest", "", creado_por=user)
    audit(user, "PARTE_PRODUCCION", "ProductionReport", r.id, {"linea": linea, "of": r.of, "desmedro_pct": r.desmedro_pct,
                                                               "rendimiento_pct": r.rendimiento_pct})
    return r


# ----------------------------- planeamiento (13-oct) -------------------------
def _inicio(periodo, f):
    if periodo == "SEMANA":
        return f - timedelta(days=f.weekday())
    if periodo == "MES":
        return f.replace(day=1)
    return f


def _fin(periodo, f):
    if periodo == "SEMANA":
        return f + timedelta(days=6)
    if periodo == "MES":
        nxt = (f.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt - timedelta(days=1)
    return f


def add_plan(user, periodo, fecha, product_code, cantidad, line_code=None, comentario=""):
    """Producción ingresa lo que producirá (día, semana o mes) para contrastarlo con la liquidación."""
    from ..models import ProductionPlan
    from .core import has_perm
    if not (has_perm(user, "produccion.programar") or has_perm(user, "produccion.liquidar")):
        raise BusinessError("El planeamiento lo registra Producción.")
    periodo = (periodo or "DIA").upper()
    if periodo not in ("DIA", "SEMANA", "MES"):
        raise BusinessError("Periodo inválido (DIA, SEMANA o MES).")
    if fecha is None:
        raise BusinessError("Indique la fecha.")
    if db().get(Product, product_code) is None:
        raise BusinessError(f"Producto {product_code} no existe.")
    if not cantidad or cantidad <= 0:
        raise BusinessError("La cantidad planificada debe ser mayor que cero.")
    pl = ProductionPlan(periodo=periodo, fecha=_inicio(periodo, fecha), product_code=product_code, cantidad=cantidad,
                        line_code=line_code or None, comentario=comentario, user_id=user.id)
    db().add(pl)
    db().flush()
    audit(user, "PLAN_PRODUCCION", "ProductionPlan", pl.id, {"periodo": periodo, "fecha": pl.fecha.isoformat(),
                                                             "producto": product_code, "cantidad": cantidad})
    return pl


def update_plan(user, pl, cantidad, comentario):
    """La programación puede variar manualmente por una variable no contemplada (observaciones al demo v0.6). La
    preprogramada por el sistema la edita el Jefe de Producción (obs. demo v0.7)."""
    from .core import has_perm
    if not (has_perm(user, "produccion.programar") or has_perm(user, "produccion.liquidar")):
        raise BusinessError("La programación la modifica Producción.")
    if pl.origen == "SISTEMA" and not has_perm(user, "produccion.programar"):
        raise BusinessError("El planeamiento preprogramado por el sistema lo edita el Jefe de Producción.")
    if not (comentario or "").strip():
        raise BusinessError("Indique el motivo del cambio de la programación.")
    antes = pl.cantidad
    if cantidad is None or cantidad < 0:
        raise BusinessError("Cantidad inválida.")
    if cantidad == 0:
        db().delete(pl)
    else:
        pl.cantidad = cantidad
        pl.comentario = (pl.comentario + "\n" if pl.comentario else "") + f"{user.nombre}: {antes:g} → {cantidad:g} ({comentario.strip()})"
    audit(user, "PLAN_PRODUCCION_MODIFICADO", "ProductionPlan", pl.id, {"antes": antes, "despues": cantidad,
                                                                         "motivo": comentario.strip()})


def plan_vs_real(periodo="DIA", desde=None, hasta=None):
    """Cumplimiento del plan: por periodo y producto, plan vs cantidad liquidada. Tasa = Σ min(real, plan) / Σ plan."""
    from ..models import ProductionPlan
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=30)
    s = db()
    plans = list(s.execute(select(ProductionPlan).where(ProductionPlan.periodo == periodo, ProductionPlan.fecha >= _inicio(periodo, desde),
                                                        ProductionPlan.fecha <= hasta)).scalars())
    liqs = list(s.execute(select(Liquidation).where(Liquidation.fecha >= _inicio(periodo, desde),
                                                    Liquidation.fecha <= _fin(periodo, hasta))).scalars())
    real = {}
    for l in liqs:
        k = (_inicio(periodo, l.fecha), l.product_code)
        real[k] = real.get(k, 0) + (l.cantidad_completada or 0)
    plan = {}
    for p in plans:
        k = (p.fecha, p.product_code)
        plan[k] = plan.get(k, 0) + p.cantidad
    filas = []
    for k in sorted(set(plan) | {k for k in real if k[0] >= _inicio(periodo, desde)}):
        pl, re_ = plan.get(k), real.get(k, 0)
        filas.append({"inicio": k[0], "fin": _fin(periodo, k[0]), "producto": k[1], "plan": pl, "real": re_,
                      "cumplimiento": round(100 * min(re_, pl) / pl, 1) if pl else None, "sin_plan": pl is None})
    con_plan = [f for f in filas if f["plan"]]
    tasa = round(100 * sum(min(f["real"], f["plan"]) for f in con_plan) / sum(f["plan"] for f in con_plan), 1) if con_plan else None
    por_periodo = {}
    for f in filas:
        d = por_periodo.setdefault(f["inicio"], {"plan": 0, "real": 0})
        d["plan"] += f["plan"] or 0
        d["real"] += f["real"]
    return {"periodo": periodo, "desde": desde, "hasta": hasta, "filas": filas, "tasa": tasa,
            "serie": sorted(por_periodo.items()), "planes": plans}


# ----------------------------- revisión de la lista de materiales -------------
def review_bom(req, user, conforme, comentario=""):
    """Producción visualiza la lista de materiales asignada a la solicitud y confirma que es la correcta (o la observa)."""
    from .core import has_perm
    if not has_perm(user, "produccion.bom_aprobar"):
        raise BusinessError("La lista de materiales la revisa y aprueba el Jefe o el Asistente de Producción (no Almacén).")
    if not conforme and not (comentario or "").strip():
        raise BusinessError("Indique qué está mal en la lista de materiales.")
    v = active_bom()
    req.bom_revision = {"conforme": bool(conforme), "comentario": (comentario or "").strip(), "user": user.nombre,
                        "ts": now().isoformat(), "version": v.version if v else None}
    if not conforme:
        alerts.emit("BOM_OBSERVADA", f"Lista de materiales observada: {req.product_code}",
                    f"Solicitud #{req.id}: {comentario}", "ProductionRequest", req.id, creado_por=user)
    audit(user, "BOM_REVISADA", "ProductionRequest", req.id, req.bom_revision)
    return req


def complete_report(r, user, **valores):
    """Completa un parte PROGRAMADO con los resultados reales (mismas fórmulas que register_report)."""
    if r.estado != "PROGRAMADO":
        raise BusinessError("Solo se completa un parte programado.")
    datos = {k: getattr(r, k) for k in ("linea", "fecha", "product_code", "peso_entrada_kg", "of", "op", "turno", "cliente",
                                        "mp_codigo", "lote", "observacion")}
    datos.update({k: v for k, v in valores.items() if v not in (None, "")})
    estado = valores.get("estado") or "EN PROCESO"
    if estado == "PROGRAMADO":
        estado = "EN PROCESO"
    nuevo = register_report(user, datos["linea"], datos["fecha"], datos["product_code"], datos["peso_entrada_kg"],
                            valores.get("granel_kg") or 0, valores.get("mp_kg") or 0, valores.get("cal3_kg") or 0,
                            valores.get("desmedro_kg") or 0, valores.get("presentacion_kg"), valores.get("unidades"),
                            valores.get("sobrante_kg") or 0, datos["of"], datos["op"], datos["turno"],
                            valores.get("hora_inicio", ""), valores.get("hora_fin", ""), valores.get("horas"),
                            valores.get("operarios"), datos["cliente"], datos["mp_codigo"], datos["lote"], estado,
                            datos["observacion"])
    db().delete(r)
    db().flush()
    audit(user, "PARTE_PROGRAMADO_COMPLETADO", "ProductionReport", nuevo.id, {"programado": r.id})
    return nuevo


# --------------- requerimientos consolidados y preprogramación (obs. demo v0.7) ---------------
OPEN_REQ = ("BORRADOR", "ENVIADA", "VALIDADA", "PROGRAMADA")


def requirements(periodo="SEMANA", desde=None, hasta=None):
    """Consolidado de lo que Producción debe tener por producto y periodo: solicitudes de producción abiertas (por OV o
    manuales) y faltantes de OV de productos con lista de materiales que aún no tienen solicitud."""
    from .stock import ORDEN_ESTADOS_CERRADOS, line_reserved
    periodo = (periodo or "SEMANA").upper()
    desde = desde or date.today()
    hasta = hasta or desde + timedelta(days={"DIA": 7, "SEMANA": 35, "MES": 92}.get(periodo, 35))
    s = db()
    acc = {}

    def sumar(prod, fecha, cant, fuente, ref):
        if fecha is None or not (desde <= fecha <= hasta) or cant <= 1e-9:
            return
        k = (_inicio(periodo, fecha), prod)
        a = acc.setdefault(k, {"inicio": k[0], "fin": _fin(periodo, k[0]), "producto": prod, "cantidad": 0.0,
                               "primera_fecha": fecha, "fuentes": []})
        a["cantidad"] += cant
        a["primera_fecha"] = min(a["primera_fecha"], fecha)
        a["fuentes"].append(f"{fuente} {ref}")
    con_solicitud = set()
    for r in s.execute(select(ProductionRequest).where(ProductionRequest.estado.in_(OPEN_REQ))).scalars():
        f = r.fecha_programada or r.fecha_requerida or (r.order.fecha_compromiso if r.order else None)
        sumar(r.product_code, f, r.cantidad, "Solicitud", f"#{r.id}" + (f" (OV {r.order.numero})" if r.order else ""))
        if r.order_id:
            con_solicitud.add((r.order_id, r.product_code))
    con_bom = {p for p, _ in bom_products()}
    for o in s.execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS),
                                                SalesOrder.estado_stock.in_(("INCOMPLETA", "SIN_STOCK")))).scalars():
        for l in o.lines:
            if not l.activa or l.product_code not in con_bom or (o.id, l.product_code) in con_solicitud:
                continue
            falt = l.cantidad - l.despachado - line_reserved(l)
            sumar(l.product_code, o.fecha_compromiso, falt, "Faltante OV", o.numero)
    planificado = {}
    from ..models import ProductionPlan
    for pl in s.execute(select(ProductionPlan).where(ProductionPlan.periodo == periodo, ProductionPlan.fecha >= _inicio(periodo, desde),
                                                     ProductionPlan.fecha <= hasta)).scalars():
        planificado[(pl.fecha, pl.product_code)] = planificado.get((pl.fecha, pl.product_code), 0) + pl.cantidad
    filas = sorted(acc.values(), key=lambda a: (a["inicio"], a["producto"]))
    for a in filas:
        a["planificado"] = planificado.get((a["inicio"], a["producto"]), 0)
        a["por_planificar"] = max(a["cantidad"] - a["planificado"], 0)
    return {"periodo": periodo, "desde": desde, "hasta": hasta, "filas": filas}


def preschedule_plan(user, periodo="SEMANA", desde=None, hasta=None):
    """El sistema preprograma el planeamiento con los requerimientos consolidados (lo que falta planificar); el Jefe de
    Producción lo revisa y edita. Devuelve las entradas creadas."""
    from ..models import ProductionPlan
    from .core import has_perm
    if user is not None and not (has_perm(user, "produccion.programar") or has_perm(user, "produccion.liquidar")):
        raise BusinessError("El planeamiento lo actualiza Producción.")
    d = requirements(periodo, desde, hasta)
    nuevas = []
    for a in d["filas"]:
        if a["por_planificar"] <= 1e-9:
            continue
        pl = ProductionPlan(periodo=d["periodo"], fecha=a["inicio"], product_code=a["producto"], cantidad=round(a["por_planificar"], 4),
                            comentario="Preprogramado por el sistema: " + "; ".join(a["fuentes"][:6]), origen="SISTEMA",
                            user_id=user.id if user else None)
        db().add(pl)
        nuevas.append(pl)
    db().flush()
    if nuevas:
        audit(user, "PLAN_PREPROGRAMADO", "ProductionPlan", ",".join(str(p.id) for p in nuevas),
              {"periodo": d["periodo"], "entradas": len(nuevas)})
    return nuevas
