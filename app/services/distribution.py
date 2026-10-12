"""Distribución y despacho (IF §12).

Propuesta de rutas: prioriza (fecha, completitud, urgencia), agrupa por zona/distrito, respeta capacidad
(kg) de unidades disponibles (propias primero), ordena paradas por horario de cita y advierte citas no
confirmadas o pesos desconocidos. Si no hay unidad propia suficiente propone transporte externo.
El Coordinador de Distribución ajusta y confirma; nada sale sin verificación.
"""
import os
import uuid
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import Driver, Incident, Route, RouteStop, SalesOrder, Vehicle, now
from . import alerts
from .catalogs_helpers import incident_type_name
from .core import BusinessError, audit, has_perm, param
from .orders import order_weight_kg
from .stock import consume_order, priority_key, release_order

CHECKLIST = [("cantidades", "Cantidades verificadas"), ("documentos", "Documentos (guías, facturas, certificados)"),
             ("carga_fisica", "Carga física verificada"), ("vehiculo", "Vehículo verificado"),
             ("conductor", "Conductor verificado")]
ACTIVE_ROUTE = ("PROPUESTA", "CONFIRMADA", "EN_RUTA")


def _zone(order):
    zonas = param("zonas_distrito", {}) or {}
    d = (order.distrito or order.customer.distrito or "SIN DISTRITO").upper()
    for zona, distritos in zonas.items():
        if d in [x.upper() for x in distritos]:
            return zona
    return d


def orders_in_active_route():
    q = select(RouteStop.order_id).join(Route).where(Route.estado.in_(ACTIVE_ROUTE))
    return set(db().execute(q).scalars())


def dispatchable_orders(fecha=None, require_prepared=True):
    estados = ["PREPARADA"] if require_prepared else ["EVALUADA", "EN_PREPARACION", "PREPARADA"]
    q = select(SalesOrder).where(SalesOrder.estado.in_(estados))
    out = []
    usados = orders_in_active_route()
    for o in db().execute(q).scalars():
        if o.id in usados:
            continue
        if not (o.estado_stock == "COMPLETA" or o.decision_parcial == "APROBADA"):
            continue
        if fecha and o.fecha_compromiso and o.fecha_compromiso > fecha:
            continue
        out.append(o)
    return sorted(out, key=priority_key)


def _busy(fecha):
    rs = db().execute(select(Route).where(Route.fecha == fecha, Route.estado.in_(ACTIVE_ROUTE))).scalars()
    vs, ds = set(), set()
    for r in rs:
        if r.vehicle_id:
            vs.add(r.vehicle_id)
        if r.driver_id:
            ds.add(r.driver_id)
    return vs, ds


def active_stop(order):
    q = select(RouteStop).join(Route).where(RouteStop.order_id == order.id, Route.estado.in_(ACTIVE_ROUTE))
    return db().execute(q).scalars().first()


def sync_order_route(order, user, listo):
    """TO-BE: 'Programar automáticamente la mejor ruta para el despacho' al quedar la OV completa
    (o con parcial aprobado). Mantiene el peso de la parada al día y retira la OV de rutas propuestas si deja de estar lista."""
    stop = active_stop(order)
    if stop is not None:
        route = stop.route
        if not listo and route.estado == "PROPUESTA":
            route.stops.remove(stop)
            db().delete(stop)
            route.peso_total = sum(x.peso_kg for x in route.stops)
            if not route.stops:
                route.estado = "ANULADA"
            return None
        peso = order_weight_kg(order)[0]
        if abs(peso - stop.peso_kg) > 1e-9:
            route.peso_total += peso - stop.peso_kg
            stop.peso_kg = peso
            if route.vehicle and route.peso_total > route.vehicle.capacidad_kg + 1e-9:
                route.advertencias = (route.advertencias or []) + [
                    f"OV {order.numero} cambió su peso: carga {route.peso_total:,.0f} kg supera la capacidad de la unidad."]
        return route
    if listo and param("programar_ruta_automatica", True) and order.estado in ("EVALUADA", "EN_PREPARACION", "PREPARADA"):
        rutas = propose_routes(order.fecha_compromiso, user, orders=[order], require_prepared=False, automatico=True)
        return rutas[0] if rutas else None
    return None


def _merge_into_existing(order, fecha, peso):
    zona = _zone(order)
    for r in db().execute(select(Route).where(Route.fecha == fecha, Route.estado == "PROPUESTA", Route.zona == zona)
                          .order_by(Route.id)).scalars():
        cap = r.vehicle.capacidad_kg if r.vehicle else None
        if cap is not None and r.peso_total + peso <= cap + 1e-9:
            r.stops.append(RouteStop(order=order, orden=len(r.stops) + 1, peso_kg=peso))
            r.peso_total += peso
            ordered = sorted(r.stops, key=lambda st: ((st.order.hora_cita or "99:99"), priority_key(st.order)))
            for i, st in enumerate(ordered, 1):
                st.orden = i
            if order.customer.requiere_cita and not order.cita_confirmada:
                r.advertencias = (r.advertencias or []) + [f"OV {order.numero}: cliente requiere cita y no está confirmada."]
            return r
    return None


def propose_routes(fecha, user, orders=None, require_prepared=True, automatico=False):
    """Genera rutas PROPUESTA para la fecha. Devuelve la lista de rutas creadas o ampliadas.
    automatico=True: programación del sistema (TO-BE); intenta sumar a una ruta propuesta existente."""
    if not automatico and user is not None and not (has_perm(user, "distribucion.programar") or has_perm(user, "ov.aprobar_parcial")):
        raise BusinessError("Su rol no genera programación de distribución.")
    if automatico and orders:
        ampliadas = []
        pendientes = []
        for o in orders:
            r = _merge_into_existing(o, fecha, order_weight_kg(o)[0])
            if r is not None:
                ampliadas.append(r)
                audit(user, "RUTA_AMPLIADA_AUTOMATICA", "Route", r.id, {"ov": o.numero})
            else:
                pendientes.append(o)
        if not pendientes:
            return ampliadas
        orders = pendientes
    s = db()
    candidates = orders if orders is not None else dispatchable_orders(fecha, require_prepared)
    usados = orders_in_active_route()
    candidates = [o for o in candidates if o.id not in usados]
    if not candidates:
        return []
    groups = {}
    for o in sorted(candidates, key=priority_key):
        groups.setdefault(_zone(o), []).append(o)
    busy_v, busy_d = _busy(fecha)
    vehicles = [v for v in s.execute(select(Vehicle).where(Vehicle.disponible.is_(True))).scalars() if v.id not in busy_v]
    drivers = [d for d in s.execute(select(Driver).where(Driver.disponible.is_(True))).scalars() if d.id not in busy_d]
    rutas = []
    # zonas en orden de la mejor prioridad que contienen
    for zona, ords in sorted(groups.items(), key=lambda kv: priority_key(kv[1][0])):
        pending = [(o, *order_weight_kg(o)) for o in ords]
        while pending:
            total = sum(p[1] for p in pending)
            propios = sorted([v for v in vehicles if v.propio], key=lambda v: v.capacidad_kg)
            terceros = sorted([v for v in vehicles if not v.propio], key=lambda v: v.capacidad_kg)
            vehicle = next((v for v in propios if v.capacidad_kg >= total), None) or \
                next((v for v in terceros if v.capacidad_kg >= total), None)
            if vehicle is None and (propios or terceros):
                vehicle = max(propios or terceros, key=lambda v: v.capacidad_kg)
            carga, resto, peso = [], [], 0.0
            cap = vehicle.capacidad_kg if vehicle else float((param("capacidad_externo_kg", [2000, 25000]) or [0, 25000])[-1])
            for item in pending:
                if peso + item[1] <= cap + 1e-9 or not carga:
                    carga.append(item)
                    peso += item[1]
                else:
                    resto.append(item)
            adv = []
            if vehicle is None:
                adv.append("No hay unidad disponible: evaluar contratación de transporte externo (IF §12.1).")
            elif peso > vehicle.capacidad_kg + 1e-9:
                adv.append(f"Un pedido supera la capacidad de la unidad ({peso:,.0f} > {vehicle.capacidad_kg:,.0f} kg); dividir o usar externo.")
            for o, _, sin_peso in carga:
                if sin_peso:
                    adv.append(f"OV {o.numero}: productos sin peso unitario ({', '.join(sin_peso)}); peso subestimado.")
                if o.customer.requiere_cita and not o.cita_confirmada:
                    adv.append(f"OV {o.numero}: cliente requiere cita y no está confirmada.")
            driver = None
            if vehicle is not None:
                if vehicle.conductor_habitual_id and any(d.id == vehicle.conductor_habitual_id for d in drivers):
                    driver = next(d for d in drivers if d.id == vehicle.conductor_habitual_id)
                elif drivers:
                    driver = drivers[0]
                if driver is None:
                    adv.append("Sin conductor disponible.")
            route = Route(fecha=fecha, vehicle_id=vehicle.id if vehicle else None, driver_id=driver.id if driver else None,
                          requiere_externo=(vehicle is None or not vehicle.propio), zona=zona, peso_total=peso,
                          advertencias=adv, creado_por=user.id if user else None)
            carga.sort(key=lambda it: ((it[0].hora_cita or "99:99"), priority_key(it[0])))
            for i, (o, w, _) in enumerate(carga, 1):
                route.stops.append(RouteStop(order_id=o.id, orden=i, peso_kg=w))
            s.add(route)
            s.flush()
            rutas.append(route)
            if vehicle is not None:
                vehicles.remove(vehicle)
            if driver is not None:
                drivers.remove(driver)
            pending = resto
    for r in rutas:
        audit(user, "RUTA_PROPUESTA_AUTOMATICA" if automatico else "RUTA_PROPUESTA", "Route", r.id,
              {"zona": r.zona, "peso": r.peso_total, "paradas": len(r.stops)})
    if automatico:
        return rutas
    alerts.emit("DIST_PROGRAMACION", f"Programación de distribución {fecha:%d/%m/%Y}: {len(rutas)} ruta(s) propuesta(s)",
                "; ".join(f"Ruta #{r.id} {r.zona} {r.peso_total:,.0f} kg ({len(r.stops)} paradas)"
                          + (" EXTERNO" if r.requiere_externo else "") for r in rutas),
                "Route", rutas[0].id, creado_por=user)
    return rutas


def _req(user, perm="distribucion.programar"):
    if not has_perm(user, perm):
        raise BusinessError("Su rol no puede realizar esta acción de distribución.")


def update_route(route, user, vehicle_id=None, driver_id=None):
    _req(user)
    if route.estado not in ("PROPUESTA", "CONFIRMADA"):
        raise BusinessError("La ruta ya salió.")
    if vehicle_id:
        v = db().get(Vehicle, int(vehicle_id))
        if v is None:
            raise BusinessError("Unidad no válida.")
        if route.peso_total > v.capacidad_kg + 1e-9:
            raise BusinessError(f"La carga ({route.peso_total:,.0f} kg) supera la capacidad de {v.placa} ({v.capacidad_kg:,.0f} kg).")
        busy_v, _ = _busy(route.fecha)
        if v.id in busy_v and v.id != route.vehicle_id:
            raise BusinessError("La unidad ya está asignada a otra ruta ese día.")
        route.vehicle_id = v.id
        route.requiere_externo = not v.propio
    if driver_id:
        d = db().get(Driver, int(driver_id))
        if d is None or not d.disponible:
            raise BusinessError("Conductor no disponible.")
        _, busy_d = _busy(route.fecha)
        if d.id in busy_d and d.id != route.driver_id:
            raise BusinessError("El conductor ya está asignado a otra ruta ese día.")
        route.driver_id = d.id
    audit(user, "RUTA_AJUSTADA", "Route", route.id, {"vehicle": vehicle_id, "driver": driver_id})


def move_stop(stop, user, target_route):
    _req(user)
    if stop.route.estado not in ("PROPUESTA", "CONFIRMADA") or target_route.estado not in ("PROPUESTA", "CONFIRMADA"):
        raise BusinessError("Solo se mueven paradas entre rutas no despachadas.")
    if target_route.vehicle and target_route.peso_total + stop.peso_kg > target_route.vehicle.capacidad_kg + 1e-9:
        raise BusinessError("La ruta destino excede la capacidad de su unidad.")
    origin = stop.route
    origin.stops.remove(stop)
    origin.peso_total -= stop.peso_kg
    stop.orden = len(target_route.stops) + 1
    target_route.stops.append(stop)
    target_route.peso_total += stop.peso_kg
    audit(user, "PARADA_MOVIDA", "Route", target_route.id, {"stop": stop.id, "desde": origin.id})


def confirm_route(route, user):
    _req(user)
    if route.estado != "PROPUESTA":
        raise BusinessError("Solo se confirman rutas propuestas.")
    if not route.stops:
        raise BusinessError("La ruta no tiene paradas.")
    if route.vehicle_id is None:
        raise BusinessError("Asigne una unidad (propia o tercera registrada) antes de confirmar.")
    if route.driver_id is None:
        raise BusinessError("Asigne un conductor antes de confirmar.")
    route.estado = "CONFIRMADA"
    for st in route.stops:
        if st.order.estado == "PREPARADA":
            st.order.estado = "PROGRAMADA"
    alerts.emit("DIST_PROGRAMACION", f"Ruta #{route.id} aprobada ({route.fecha:%d/%m/%Y})",
                f"Unidad {route.vehicle.placa}; conductor {route.driver.nombre}; {len(route.stops)} paradas.",
                "Route", route.id, creado_por=user)
    # TO-BE: alerta al chofer y al auxiliar de las rutas asignadas, y al montacarguista para el traslado a despacho
    alerts.emit("RUTA_ASIGNADA", f"Ruta #{route.id} asignada: {route.fecha:%d/%m/%Y} · {route.vehicle.placa}",
                ", ".join(f"{st.order.numero} ({st.order.customer.nombre})" for st in route.stops), "Route", route.id,
                extra_users=[route.driver.user_id] if route.driver.user_id else None, creado_por=user)
    alerts.emit("MONTACARGUISTA_DESPACHO", f"Trasladar mercadería de la ruta #{route.id} a la zona de despacho",
                ", ".join(st.order.numero for st in route.stops), "Route", route.id, creado_por=user)
    audit(user, "RUTA_CONFIRMADA", "Route", route.id)


def register_security_check(route, user, guia_numero, lineas):
    """Seguridad valida cantidades/presentación contra guía (IF §12.2, §13).
    lineas: [{order_line_id, producto, esperado, guia, cargado, presentacion_ok}]"""
    _req(user, "distribucion.seguridad")
    if route.estado not in ("CONFIRMADA",):
        raise BusinessError("La validación de carga se hace sobre rutas confirmadas antes de salir.")
    discrepancias = []
    tol = float(param("tolerancia_discrepancia_guia", 0) or 0) + 1e-9
    for ln in lineas:
        if abs((ln.get("guia") or 0) - (ln.get("cargado") or 0)) > tol:
            discrepancias.append(f"{ln['producto']}: guía {ln.get('guia')} vs cargado {ln.get('cargado')}")
        if abs((ln.get("esperado") or 0) - (ln.get("guia") or 0)) > tol:
            discrepancias.append(f"{ln['producto']}: preparado {ln.get('esperado')} vs guía {ln.get('guia')}")
        if ln.get("presentacion_ok") is False:
            discrepancias.append(f"{ln['producto']}: presentación no coincide con la guía")
    route.guia_numero = guia_numero
    route.seguridad = {"user": user.nombre, "ts": now().isoformat(), "lineas": lineas, "discrepancias": discrepancias,
                       "conforme": not discrepancias}
    if discrepancias:
        alerts.emit("GUIA_DISCREPANCIA", f"Discrepancia carga vs guía en ruta #{route.id}", "; ".join(discrepancias)
                    + (". La salida queda bloqueada hasta corregir o que Logística la apruebe (Q8)."
                       if param("bloquear_salida_con_discrepancia", True) else ""),
                    "Route", route.id, dedup_key=f"GUIA:{route.id}", creado_por=user)
    else:
        alerts.close_by_system(f"GUIA:{route.id}", "Nueva validación de Seguridad conforme")
        route.aprobacion_discrepancia = {}
    audit(user, "SEGURIDAD_VALIDACION", "Route", route.id, route.seguridad)
    return discrepancias


def expected_lines(route):
    out = []
    for st in route.stops:
        for l in st.order.lines:
            if l.activa:
                esperado = l.preparado if l.preparado > 0 else sum(r.cantidad for r in l.reservations if r.estado == "ACTIVA")
                out.append({"order_line_id": l.id, "ov": st.order.numero, "producto": l.product_code,
                            "descripcion": l.product.descripcion, "esperado": esperado})
    return out


def confirm_departure(route, user, checklist):
    """El Líder Operativo autoriza y confirma la salida (decisión Q16, 12-oct-2026) con la verificación del IF §12.2."""
    if not has_perm(user, "distribucion.confirmar_salida"):
        raise BusinessError("La salida del camión la autoriza el Líder Operativo (Q16).")
    if route.estado != "CONFIRMADA":
        raise BusinessError("La ruta debe estar confirmada.")
    faltan = [lbl for k, lbl in CHECKLIST if not checklist.get(k)]
    if faltan:
        raise BusinessError("Antes de la salida verifique: " + ", ".join(faltan) + " (IF §12.2).")
    no_prep = [st.order.numero for st in route.stops if st.order.estado not in ("PREPARADA", "PROGRAMADA")]
    if no_prep:
        raise BusinessError("Pedidos sin preparación completa: " + ", ".join(no_prep))
    if not route.seguridad:
        raise BusinessError("Falta la validación de Seguridad de carga contra guía.")
    if not route.carga_validada:
        raise BusinessError("Falta la validación de la carga por el auxiliar (camión cargado, TO-BE).")
    if not route.autorizacion_seguridad:
        raise BusinessError("Falta la revisión de documentos de Seguridad (documentos completos, TO-BE).")
    from .despacho import VB_LABEL, missing_exit_approvals
    faltan_vb = missing_exit_approvals(route)
    if faltan_vb:
        raise BusinessError("Falta el visto bueno de: " + ", ".join(VB_LABEL.get(r, r) for r in faltan_vb) + " (Q16).")
    if route.seguridad.get("discrepancias"):
        if param("bloquear_salida_con_discrepancia", True) and not route.aprobacion_discrepancia:
            raise BusinessError("Salida bloqueada: discrepancias entre carga y guía. Corrija y vuelva a validar, o el Jefe "
                                "o Coordinador de Logística puede aprobar la salida mientras se resuelve la guía (Q8).")
    route.checklist = {k: bool(checklist.get(k)) for k, _ in CHECKLIST}
    route.checklist["advertencia_discrepancias"] = bool(route.seguridad.get("discrepancias"))
    if route.aprobacion_discrepancia:
        route.checklist["salida_aprobada_por_logistica"] = route.aprobacion_discrepancia.get("user")
    vb = dict(route.vistos_buenos or {})
    vb["LIDER_ALMACEN"] = {"user": user.nombre, "user_id": user.id, "ts": now().isoformat(), "detalle": "Autoriza la salida"}
    route.vistos_buenos = vb
    route.estado = "EN_RUTA"
    route.salida_ts = now()
    route.salida_confirmada_por = user.id
    saldos = []
    for st in route.stops:
        consume_order(st.order, user)
        st.order.estado = "DESPACHADA"
        st.order.salida_ts = now()
        st.estado = "EN_CAMINO"
        if st.order.decision_parcial == "APROBADA":
            from .orders import create_saldo
            sal = create_saldo(st.order, user)  # decisión Q3: el saldo se reprograma
            if sal is not None:
                saldos.append(sal.numero)
    if saldos:
        route.advertencias = (route.advertencias or []) + [f"Saldos reprogramados: {', '.join(saldos)}"]
    alerts.emit("DIST_AVANCE_RUTA", f"Ruta #{route.id} salió ({route.vehicle.placa})",
                ", ".join(f"OV {st.order.numero}" for st in route.stops), "Route", route.id, creado_por=user)
    audit(user, "SALIDA_CONFIRMADA", "Route", route.id, route.checklist)


def register_arrival(stop, user):
    _req(user, "distribucion.entrega")
    if stop.estado != "EN_CAMINO":
        raise BusinessError("La parada no está en camino.")
    stop.estado = "LLEGADA"
    stop.llegada_ts = now()
    alerts.emit("DIST_LLEGADA", f"Llegada al punto de entrega: OV {stop.order.numero}", stop.order.customer.nombre, "Route",
                stop.route_id, creado_por=user)


def save_upload(file_storage, upload_dir, prefix):
    if file_storage is None or not getattr(file_storage, "filename", ""):
        return ""
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".pdf", ".webp", ".heic"):
        raise BusinessError("Formato de evidencia no permitido (jpg, png, pdf, webp, heic).")
    os.makedirs(upload_dir, exist_ok=True)
    name = f"{prefix}_{uuid.uuid4().hex[:10]}{ext}"
    file_storage.save(os.path.join(upload_dir, name))
    return name


def register_delivery(stop, user, foto_path, guia_path, entregas=None, observacion=""):
    """Entrega respaldada con fotografía y guía firmada (IF §12.3). entregas: {order_line_id: cantidad}."""
    _req(user, "distribucion.entrega")
    if stop.estado not in ("EN_CAMINO", "LLEGADA"):
        raise BusinessError("La parada no está en ruta.")
    if not foto_path or not guia_path:
        raise BusinessError("La evidencia de entrega requiere fotografía y guía firmada (IF §12.3).")
    order = stop.order
    parcial = False
    for l in order.lines:
        if not l.activa:
            continue
        q = l.despachado if not entregas or str(l.id) not in entregas else float(entregas[str(l.id)])
        if q > l.despachado + 1e-9:
            raise BusinessError(f"{l.product_code}: lo entregado no puede superar lo despachado ({l.despachado:g}).")
        l.entregado = q
        if q < l.cantidad - 1e-9:
            parcial = True
    stop.foto_path = foto_path
    stop.guia_firmada_path = guia_path
    stop.entrega_ts = now()
    stop.observacion = observacion
    stop.estado = "ENTREGA_PARCIAL" if parcial else "ENTREGADO"
    order.estado = "ENTREGA_PARCIAL" if parcial else "ENTREGADA"
    order.entrega_ts = now()
    if parcial:
        _incident(user, "ENTREGA_PARCIAL", stop, f"Entrega parcial registrada. {observacion}")
    alerts.emit("DIST_ENTREGADO", f"OV {order.numero} {'entregada parcialmente' if parcial else 'entregada con conformidad'}",
                f"{order.customer.nombre}. Evidencia: foto y guía firmada.", "Route", stop.route_id, creado_por=user)
    audit(user, "ENTREGA_REGISTRADA", "SalesOrder", order.numero, {"parcial": parcial})
    _maybe_close_route(stop.route)


def _maybe_close_route(route):
    if all(s.estado in ("ENTREGADO", "ENTREGA_PARCIAL", "RECHAZADO", "DEVUELTO", "NO_ENTREGADO") for s in route.stops):
        route.estado = "CERRADA"
        route.cierre_ts = now()


def _incident(user, tipo, stop=None, descripcion="", order=None, route=None, cantidad=None):
    order = order or (stop.order if stop else None)
    route = route or (stop.route if stop else None)
    inc = Incident(tipo=tipo, route_id=route.id if route else None, stop_id=stop.id if stop else None,
                   order_id=order.id if order else None, descripcion=descripcion, cantidad_afectada=cantidad,
                   user_id=user.id if user else None)
    db().add(inc)
    db().flush()
    code = "INC_RECHAZO_CALIDAD" if tipo == "RECHAZO_CALIDAD" else "INC_GENERAL"
    a = alerts.emit(code, f"{incident_type_name(tipo)}: {('OV ' + order.numero) if order else ('Ruta #' + str(route.id) if route else '')}",
                    descripcion, "Incident", inc.id, extra_users=[order.vendedor_id] if order and order.vendedor_id else None,
                    creado_por=user)
    inc.alert_id = a.id if a else None
    return inc


def register_incident(user, tipo, descripcion, stop=None, order=None, route=None, cantidad=None):
    """Registro de incidencias por el Auxiliar de Despacho (IF §12.3) y su efecto operativo."""
    _req(user, "distribucion.incidencia")
    from ..catalogs import INCIDENT_TYPES
    if tipo not in dict(INCIDENT_TYPES):
        raise BusinessError("Tipo de incidencia no válido.")
    if not descripcion.strip():
        raise BusinessError("Describa la incidencia.")
    inc = _incident(user, tipo, stop, descripcion, order, route, cantidad)
    o = inc.order
    if stop is not None:
        if tipo in ("RECHAZO_CALIDAD", "RECHAZO_OTRO"):
            stop.estado = "RECHAZADO"
            o.estado = "RECHAZADA"
            _return_goods(o, user, f"Rechazo ({incident_type_name(tipo)})")
        elif tipo == "DEVOLUCION":
            stop.estado = "DEVUELTO"
            o.estado = "DEVUELTA"
            _return_goods(o, user, "Devolución")
        elif tipo == "PARTICULARIDAD_DESCARGA":
            pass  # se registra sobre la entrega ya realizada (TO-BE: detección en la misma descarga)
        elif tipo in ("CLIENTE_AUSENTE", "CLIENTE_NO_RETIRA", "RECHAZO_CITA"):
            stop.estado = "NO_ENTREGADO"
            o.estado = "DEVUELTA"
            _return_goods(o, user, incident_type_name(tipo))
        _maybe_close_route(stop.route)
    if tipo == "CONDUCTOR_NO_DISPONIBLE" and route is not None and route.driver is not None:
        route.driver.disponible = False
        route.advertencias = (route.advertencias or []) + [f"Conductor {route.driver.nombre} no disponible: reasignar."]
    audit(user, "INCIDENCIA", "Incident", inc.id, {"tipo": tipo, "descripcion": descripcion})
    return inc


def _return_goods(order, user, motivo):
    """Producto que regresa: ingresa como 'Pendiente de revisión' para evaluación de Calidad (propuesto)."""
    from .stock import add_or_increase_lot
    for l in order.lines:
        devuelto = l.despachado - l.entregado
        if devuelto <= 1e-9:
            continue
        lotes = [r for r in l.reservations if r.estado == "CONSUMIDA"]
        if not lotes:
            continue
        ref = lotes[0].lot
        add_or_increase_lot(l.product_code, ref.warehouse_code, ref.lote, devuelto, "PENDIENTE_REVISION", ref.fecha_venc,
                            ref.fecha_fab, origen=f"RETORNO-{order.numero}")
    alerts.emit("STOCK_PENDIENTE_REVISION", f"Retorno de OV {order.numero}: {motivo}",
                "Producto devuelto ingresó como Pendiente de revisión.", "SalesOrder", order.id, creado_por=user)
