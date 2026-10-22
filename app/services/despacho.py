"""Etapa de carga y documentos del despacho según el TO-BE COPROD-ONE (L5).

Secuencia TO-BE: ruta aprobada → montacarguista traslada → auxiliar sube foto del vehículo antes de la estiba y genera
pre-guía → Seguridad visualiza pre-guía, sigue la carga (foto de inicio) y registra incidencias con foto, motivo y hora →
auxiliar valida productos (si hay incongruencias avisa al almacenero para validación cruzada) → valida carga completa con
foto de mercadería cargada → alerta de camión cargado → Facturación factura y carga la factura; Distribución genera/carga la
guía e imprime el folio → Seguridad revisa que los documentos estén completos (si faltan, reporta) → el Líder Operativo
autoriza la salida (decisión Q16, 12-oct-2026). Una discrepancia carga vs guía bloquea la salida salvo que el Jefe o el
Coordinador de Logística la apruebe mientras se resuelve la guía (Q8).
"""
from sqlalchemy import select

from ..db import db
from ..models import Certificate, Incident, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

ETAPAS_FOTO = {
    "vehiculo": ("Foto del vehículo antes de la estiba", "distribucion.carga"),
    "inicio_carga": ("Foto del inicio de la carga (Seguridad)", "distribucion.seguridad"),
    "mercaderia_cargada": ("Foto de la mercadería cargada", "distribucion.carga"),
    "incidencia_carga": ("Foto de incidencia durante la carga (Seguridad)", "distribucion.seguridad"),
    "seguridad_guia": ("Foto de la validación contra la guía (Seguridad)", "distribucion.seguridad"),
    # observaciones al demo v0.6: el chofer registra cómo saca y cómo devuelve el vehículo
    "vehiculo_salida": ("Foto del vehículo al salir (chofer)", "distribucion.carga"),
    "vehiculo_retorno": ("Foto del vehículo al retornar (chofer)", "distribucion.carga"),
}


def _route_ready(route):
    if route.estado != "CONFIRMADA":
        raise BusinessError("La ruta debe estar aprobada (confirmada) por Distribución.")


def add_photo(route, user, etapa, archivo, nota=""):
    if etapa not in ETAPAS_FOTO:
        raise BusinessError("Etapa de foto no válida.")
    nombre, perm = ETAPAS_FOTO[etapa]
    if not has_perm(user, perm):
        raise BusinessError(f"Su rol no registra: {nombre}.")
    if etapa == "vehiculo_retorno":
        if route.estado not in ("EN_RUTA", "CERRADA"):
            raise BusinessError("La foto de retorno se registra al volver de la ruta.")
    else:
        _route_ready(route)
    if not archivo:
        raise BusinessError("Adjunte la fotografía.")
    fotos = dict(route.fotos or {})
    fotos.setdefault(etapa, []).append({"archivo": archivo, "user": user.nombre, "ts": now().isoformat(), "nota": nota})
    route.fotos = fotos
    audit(user, "RUTA_FOTO", "Route", route.id, {"etapa": etapa, "archivo": archivo})


def register_loading_incident(route, user, archivo, motivo, hora=""):
    """Seguridad: incidencia durante la carga con foto, motivo y hora (TO-BE)."""
    if not motivo.strip():
        raise BusinessError("Indique el motivo de la incidencia.")
    hora = hora or f"{now():%H:%M}"
    add_photo(route, user, "incidencia_carga", archivo, f"{hora} {motivo}")
    inc = Incident(tipo="INCIDENCIA_CARGA", route_id=route.id, descripcion=f"{motivo} (hora {hora}; foto {archivo})",
                   user_id=user.id)
    db().add(inc)
    db().flush()
    a = alerts.emit("INC_CARGA", f"Incidencia durante la carga de la ruta #{route.id}", f"{motivo} (hora {hora})", "Route",
                    route.id, creado_por=user)
    inc.alert_id = a.id if a else None
    return inc


def preguia(route):
    """Pre-guía: productos, cantidades preparadas, lotes y fechas por pedido."""
    out = []
    for st in route.stops:
        o = st.order
        items = []
        for l in o.lines:
            if not l.activa:
                continue
            res = [r for r in l.reservations if r.estado in ("ACTIVA", "CONSUMIDA")]
            items.append({"order_line_id": l.id, "codigo": l.product_code, "descripcion": l.product.descripcion,
                          "cantidad": l.preparado if l.preparado > 0 else sum(r.cantidad for r in res if r.estado == "ACTIVA"),
                          "lotes": [{"lote": r.lot.lote, "fp": r.lot.fecha_fab, "fv": r.lot.fecha_venc, "cantidad": r.cantidad}
                                    for r in res]})
        whs = [r.lot.warehouse_code for l in o.lines if l.activa for r in l.reservations if r.estado in ("ACTIVA", "CONSUMIDA")]
        out.append({"stop": st, "order": o, "items": items, "almacen": whs[0] if whs else "", "motivo": "Venta"})
    return out


def validate_load(route, user, lineas, observacion=""):
    """Auxiliar (y chofer): ¿productos correctos o completos? lineas: {order_line_id: {cargado, correcto}}.
    Si hay incongruencias se avisa al almacenero (validación cruzada); si todo está correcto se exige la foto de la
    mercadería cargada y se emite la alerta de camión cargado."""
    if not has_perm(user, "distribucion.conformidad_producto"):
        # obs. demo v0.7: el chofer no da conformidad del estado del producto (compete a Calidad, Distribución y Almacén)
        raise BusinessError("La conformidad del producto la dan Calidad, Distribución o Almacén (no el chofer).")
    _route_ready(route)
    if not (route.fotos or {}).get("vehiculo"):
        raise BusinessError("Primero suba la foto del vehículo antes de la estiba.")
    incongruencias = []
    detalle = []
    for grupo in preguia(route):
        for it in grupo["items"]:
            v = lineas.get(str(it["order_line_id"]), {})
            cargado = float(v.get("cargado") if v.get("cargado") not in (None, "") else it["cantidad"])
            correcto = v.get("correcto", True)
            detalle.append({"ov": grupo["order"].numero, "producto": it["codigo"], "preguia": it["cantidad"], "cargado": cargado,
                            "correcto": bool(correcto)})
            if abs(cargado - it["cantidad"]) > 1e-9 or not correcto:
                incongruencias.append(f"OV {grupo['order'].numero} {it['codigo']}: pre-guía {it['cantidad']:g}, cargado {cargado:g}"
                                      + ("" if correcto else ", producto/presentación incorrecta"))
    route.carga = {"user": user.nombre, "ts": now().isoformat(), "lineas": detalle, "incongruencias": incongruencias,
                   "observacion": observacion}
    if incongruencias:
        route.carga_validada = False
        alerts.emit("CARGA_INCONGRUENCIA", f"Ruta #{route.id}: incongruencias en el pedido picado",
                    "; ".join(incongruencias) + ". Cambiar producto observado o regresar sobrante y volver a validar.",
                    "Route", route.id, creado_por=user)
        audit(user, "CARGA_INCONGRUENCIA", "Route", route.id, route.carga)
        return incongruencias
    if not (route.fotos or {}).get("mercaderia_cargada"):
        raise BusinessError("Suba la foto de la mercadería cargada para validar la carga completa.")
    route.carga_validada = True
    alerts.emit("CAMION_CARGADO", f"Camión cargado: ruta #{route.id} ({route.vehicle.placa if route.vehicle else '-'})",
                ", ".join(f"OV {st.order.numero}" for st in route.stops) + ". Facturación: evaluar pedidos y cargar facturas.",
                "Route", route.id, creado_por=user)
    audit(user, "CAMION_CARGADO", "Route", route.id, route.carga)
    return []


def set_guide(stop, user, numero, origen, archivo="", motivo=None):
    """Distribución: registrar la guía de SAP (la válida, con su número y archivo) o, si SAP no está disponible,
    generarla en el sistema como contingencia (marcha blanca, 22-oct-2026), indicando el motivo."""
    if not has_perm(user, "distribucion.documentos"):
        raise BusinessError("La guía la genera o carga Distribución.")
    if origen not in ("SAP", "SISTEMA"):
        raise BusinessError("Origen de guía no válido.")
    if origen == "SAP" and not (numero.strip() and archivo):
        raise BusinessError("Para una guía de SAP registre el número y cargue el archivo.")
    if origen == "SISTEMA" and motivo is not None and not motivo.strip():
        raise BusinessError("La guía del sistema es de contingencia: indique el motivo (por ejemplo, SAP no disponible).")
    if origen == "SISTEMA" and motivo:
        stop.observacion = ((stop.observacion or "") + f"\nGuía generada en el sistema (contingencia): {motivo.strip()}").strip()
    if origen == "SISTEMA" and not numero.strip():
        numero = f"GS-{stop.route_id}-{stop.order.numero}"
    if stop.guia_numero and stop.guia_numero != numero.strip():
        stop.guia_aprobada = {}  # una guía nueva o corregida vuelve a aprobarse
    stop.guia_numero = numero.strip()
    stop.guia_origen = origen
    if archivo:
        stop.guia_path = archivo
    if not stop.route.guia_numero or stop.route.guia_numero.startswith("PRE-GUIA"):
        stop.route.guia_numero = stop.guia_numero
    audit(user, "GUIA_REGISTRADA", "SalesOrder", stop.order.numero, {"guia": stop.guia_numero, "origen": origen,
                                                                     "contingencia": (motivo or "").strip()})


def approve_guide(stop, user, comentario=""):
    """Obs. demo v0.7: el Coordinador y el Asistente de Distribución revisan la pre-guía y aprueban la guía."""
    if not has_perm(user, "distribucion.aprobar_guia"):
        raise BusinessError("La guía la aprueban el Coordinador o el Asistente de Distribución.")
    if not stop.guia_numero:
        raise BusinessError("Primero genere o registre la guía (revise la pre-guía).")
    if stop.guia_aprobada:
        raise BusinessError("La guía ya está aprobada.")
    stop.guia_aprobada = {"user": user.nombre, "rol": user.role_code, "ts": now().isoformat(), "comentario": (comentario or "").strip()}
    audit(user, "GUIA_APROBADA", "SalesOrder", stop.order.numero, {"guia": stop.guia_numero, **stop.guia_aprobada})


def billing_status(stop):
    """¿Está completo según la OV? (despachado/preparado vs solicitado)."""
    o = stop.order
    dif = []
    for l in o.lines:
        if not l.activa:
            continue
        q = l.despachado if l.despachado > 0 else l.preparado
        if abs(q - l.cantidad) > 1e-9:
            dif.append(f"{l.product_code}: OV {l.cantidad:g} / cargado {q:g}")
    return dif


def set_invoice(stop, user, numero, archivo):
    """Facturación: evalúa el pedido validado, genera la factura en SAP (con modificaciones si no está completo) y la carga."""
    if not has_perm(user, "facturacion.cargar"):
        raise BusinessError("La factura la carga Facturación.")
    if not stop.route.carga_validada:
        raise BusinessError("La carga aún no está validada (camión cargado).")
    if not numero.strip() or not archivo:
        raise BusinessError("Registre el número de factura y cargue el archivo.")
    dif = billing_status(stop)
    stop.factura_numero = numero.strip()
    stop.factura_path = archivo
    stop.factura_con_modificaciones = bool(dif)
    stop.factura_ts = now()
    audit(user, "FACTURA_CARGADA", "SalesOrder", stop.order.numero, {"factura": numero, "con_modificaciones": dif})
    return dif


def missing_documents(route):
    req = param("documentos_salida", ["GUIA", "FACTURA", "CERTIFICADO"]) or []
    faltan = []
    for st in route.stops:
        o = st.order
        if "GUIA" in req and not st.guia_numero:
            faltan.append(f"OV {o.numero}: guía")
        if "FACTURA" in req and not st.factura_numero:
            faltan.append(f"OV {o.numero}: factura")
        if "CERTIFICADO" in req:
            certs = list(db().execute(select(Certificate).where(Certificate.order_id == o.id, Certificate.estado != "ANULADO")).scalars())
            if not certs:
                faltan.append(f"OV {o.numero}: certificado de calidad")
            elif any(c.estado != "APROBADO" for c in certs):
                faltan.append(f"OV {o.numero}: certificado sin aprobar por Calidad")
    return faltan


def review_documents(route, user, impresos=False):
    """Seguridad: revisa en el sistema que todos los documentos estén cargados e impresos (TO-BE).
    La autorización de la salida la da después el Líder Operativo (Q16)."""
    if not has_perm(user, "distribucion.seguridad"):
        raise BusinessError("La revisión de documentos la hace Seguridad.")
    _route_ready(route)
    if not route.carga_validada:
        raise BusinessError("La carga no está validada por el auxiliar.")
    faltan = missing_documents(route)
    if not impresos:
        faltan.append("Folio de documentos impreso (confirmar)")
    if faltan:
        alerts.emit("DOCUMENTOS_FALTANTES", f"Ruta #{route.id}: documentos faltantes para la salida", "; ".join(faltan),
                    "Route", route.id, dedup_key=f"DOCS:{route.id}", creado_por=user)
        audit(user, "DOCUMENTOS_FALTANTES", "Route", route.id, {"faltan": faltan})
        return faltan
    alerts.close_by_system(f"DOCS:{route.id}", "Documentos completos")
    route.autorizacion_seguridad = {"user": user.nombre, "ts": now().isoformat()}
    vb = dict(route.vistos_buenos or {})
    vb["SEGURIDAD"] = {"user": user.nombre, "user_id": user.id, "ts": now().isoformat(), "detalle": "Documentos completos"}
    route.vistos_buenos = vb
    audit(user, "DOCUMENTOS_REVISADOS_SEGURIDAD", "Route", route.id)
    return []


VB_LABEL = {"SEGURIDAD": "Seguridad (documentos completos)", "AUX_DESPACHO": "Auxiliar de Despacho",
            "LIDER_ALMACEN": "Líder Operativo"}


def required_exit_approvals():
    return list(param("vistos_buenos_salida", ["SEGURIDAD", "AUX_DESPACHO", "LIDER_ALMACEN"]) or [])


def give_exit_ok(route, user, nota=""):
    """Q16 (13-oct-2026): visto bueno del Auxiliar de Despacho a la salida (carga validada y conforme)."""
    if not has_perm(user, "distribucion.visto_bueno_salida"):
        raise BusinessError("El visto bueno de salida lo da el Auxiliar de Despacho (Q16).")
    _route_ready(route)
    if not route.carga_validada:
        raise BusinessError("Primero valide la carga (camión cargado).")
    vb = dict(route.vistos_buenos or {})
    vb["AUX_DESPACHO"] = {"user": user.nombre, "user_id": user.id, "ts": now().isoformat(), "detalle": nota}
    route.vistos_buenos = vb
    audit(user, "VISTO_BUENO_SALIDA", "Route", route.id, {"rol": "AUX_DESPACHO", "nota": nota})


def missing_exit_approvals(route, excluir=("LIDER_ALMACEN",)):
    vb = route.vistos_buenos or {}
    return [r for r in required_exit_approvals() if r not in excluir and r not in vb]


def approve_exit_with_discrepancy(route, user, motivo):
    """Q8: la discrepancia con la guía bloquea la salida; el Jefe o el Coordinador de Logística puede aprobarla
    mientras se resuelve la guía. La alerta de discrepancia queda abierta hasta registrar la resolución."""
    if not has_perm(user, "distribucion.aprobar_salida_discrepancia"):
        raise BusinessError("La salida con discrepancia la aprueba el Jefe o el Coordinador de Logística (Q8).")
    _route_ready(route)
    if not (route.seguridad or {}).get("discrepancias"):
        raise BusinessError("La ruta no tiene discrepancias carga vs guía.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo y cómo se resolverá la guía.")
    route.aprobacion_discrepancia = {"user": user.nombre, "user_id": user.id, "rol": user.role_code,
                                     "ts": now().isoformat(), "motivo": motivo.strip(), "resuelta": False}
    alerts.emit("SALIDA_CON_DISCREPANCIA", f"Ruta #{route.id}: salida aprobada con guía por resolver",
                f"Aprobó {user.nombre}. Motivo: {motivo}. Discrepancias: " + "; ".join(route.seguridad["discrepancias"]),
                "Route", route.id, creado_por=user)
    audit(user, "SALIDA_DISCREPANCIA_APROBADA", "Route", route.id, route.aprobacion_discrepancia)


def resolve_guide_discrepancy(route, user, detalle):
    """Registra que la guía observada quedó resuelta (cierra la alerta de discrepancia)."""
    if not (has_perm(user, "distribucion.documentos") or has_perm(user, "distribucion.aprobar_salida_discrepancia")):
        raise BusinessError("Registra la resolución Distribución o Logística.")
    ap = dict(route.aprobacion_discrepancia or {})
    if not ap or ap.get("resuelta"):
        raise BusinessError("No hay una discrepancia de guía pendiente de resolver.")
    if not (detalle or "").strip():
        raise BusinessError("Describa cómo se resolvió la guía.")
    ap.update({"resuelta": True, "resuelta_por": user.nombre, "resuelta_ts": now().isoformat(), "resolucion": detalle.strip()})
    route.aprobacion_discrepancia = ap
    alerts.close_by_system(f"GUIA:{route.id}", f"Guía resuelta: {detalle}")
    audit(user, "GUIA_DISCREPANCIA_RESUELTA", "Route", route.id, ap)


def needs_vehicle_photos(route):
    return bool(param("exigir_fotos_vehiculo", True)) and route.vehicle is not None and route.vehicle.propio


def register_return(route, user, km_retorno=None):
    if not (has_perm(user, "distribucion.entrega") or has_perm(user, "distribucion.carga")):
        raise BusinessError("Sin permiso.")
    if route.estado not in ("EN_RUTA", "CERRADA"):
        raise BusinessError("La ruta no está en curso.")
    if needs_vehicle_photos(route) and not (route.fotos or {}).get("vehiculo_retorno"):
        raise BusinessError("El chofer debe subir la foto de cómo devuelve el vehículo.")
    if km_retorno is not None:
        if route.km_salida is not None and km_retorno < route.km_salida:
            raise BusinessError("El kilometraje de retorno no puede ser menor al de salida.")
        route.km_retorno = km_retorno
        if route.vehicle and (route.vehicle.km_actual is None or km_retorno > route.vehicle.km_actual):
            route.vehicle.km_actual = km_retorno
    route.retorno_ts = now()
    audit(user, "RETORNO_BASE", "Route", route.id)
