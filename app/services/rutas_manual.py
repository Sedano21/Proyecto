"""V22 (06-nov-2026): Distribución registra y modifica rutas a mano.

- Ruta manual del día: vehículo, chofer, una o varias OV (de uno o varios clientes) y traslados entre almacenes.
- Cambios en rutas programadas (agregar o quitar OV y traslados, cambiar vehículo o chofer) con motivo y rastro.
- Varios auxiliares de despacho por ruta (botón +).
- Ruta llevada por otro trabajador (p. ej. un vendedor): nombre, área, vehículo y motivo.
- Peso permitido del vehículo (tarjeta) frente a su capacidad real y a lo que suele cargar: se alerta la sobrecarga y se
  analiza por vehículo.
- Cuadro diario de despacho: por vehículo, clientes, OV, guías, peso y valor de lo que lleva.
- Pernocte: el chofer deja foto de lo que queda en el vehículo.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Driver, Route, RouteStop, RouteTransfer, SalesOrder, Transfer, User, Vehicle, now
from . import alerts
from .core import BusinessError, audit, has_perm, param
from .orders import order_amount, order_weight_kg

EDITABLES = ("PROPUESTA", "CONFIRMADA")


def _req(user):
    if not has_perm(user, "distribucion.programar"):
        raise BusinessError("Las rutas las registra y modifica Distribución.")


def _log(route, user, campo, de, a, motivo=""):
    route.cambios = list(route.cambios or []) + [{"campo": campo, "de": de, "a": a, "motivo": (motivo or "").strip(),
                                                  "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]


# ------------------------------------------------------------------ pesos
def transfer_weight(t):
    """Peso de un traslado: cantidad × peso unitario (o la cantidad si el producto se maneja en kilos)."""
    p = t.lot.product if t.lot is not None else None
    if p is None:
        return 0.0
    if (p.um or "").upper().startswith("K"):
        return float(t.cantidad or 0)
    return float(t.cantidad or 0) * float(p.peso_kg or 0)


def route_transfers(route):
    return list(db().execute(select(RouteTransfer).where(RouteTransfer.route_id == route.id)
                             .order_by(RouteTransfer.orden, RouteTransfer.id)).scalars())


def route_weight(route):
    return round(sum(st.peso_kg or 0 for st in route.stops) + sum(rt.peso_kg or 0 for rt in route_transfers(route)), 2)


def peso_ov(o):
    """Peso de la OV en la ruta: lo reservado o preparado; si aún no tiene reserva, lo pedido."""
    return order_weight_kg(o)[0] or order_weight_kg(o, "solicitado")[0]


def capacidad(vehicle):
    """(permitido, real): el peso permitido (tarjeta de propiedad) y lo que físicamente puede cargar."""
    if vehicle is None:
        return None, None
    return vehicle.capacidad_kg, vehicle.capacidad_real_kg or vehicle.capacidad_kg


def overload(route):
    """Texto de la sobrecarga de la ruta o None. Usa el peso real pesado si se registró."""
    v = route.vehicle if route.vehicle_id else None
    if v is None:
        return None
    peso = route.peso_real_kg or route.peso_total or 0
    perm, real = capacidad(v)
    tol = float(param("sobrecarga_tolerancia_pct", 0) or 0)
    if real and peso > real + 1e-9:
        return f"{peso:,.0f} kg supera la capacidad real de {v.placa} ({real:,.0f} kg)"
    if perm and peso > perm * (1 + tol / 100) + 1e-9:
        return f"{peso:,.0f} kg supera el peso permitido de {v.placa} ({perm:,.0f} kg)"
    return None


def _check_overload(route, user):
    msg = overload(route)
    if msg:
        alerts.emit("RUTA_SOBRECARGA", f"Ruta #{route.id}: sobrecarga", msg + ". Revise la carga o reparta en otra unidad.",
                    "Route", route.id, dedup_key=f"SOBRECARGA:{route.id}", creado_por=user)
    return msg


def _recalc(route, user=None):
    route.peso_total = route_weight(route)
    if user is not None:
        _check_overload(route, user)


# ------------------------------------------------------------------ disponibilidad
def _driver_free(driver, fecha, route=None):
    from . import ausencias
    if driver is None:
        return
    if not driver.disponible:
        raise BusinessError(f"{driver.nombre} está marcado como no disponible.")
    aus = ausencias.ausencia_de("DRIVER", driver.id, fecha) or (ausencias.ausencia_de("USER", driver.user_id, fecha)
                                                                 if driver.user_id else None)
    if aus:
        raise BusinessError(f"{driver.nombre} no está disponible el {fecha:%d/%m/%Y}: {ausencias.texto(aus)}.")
    otra = db().execute(select(Route).where(Route.fecha == fecha, Route.driver_id == driver.id,
                                            Route.estado.in_(("PROPUESTA", "CONFIRMADA", "EN_RUTA")),
                                            Route.id != (route.id if route is not None else -1))).scalars().first()
    if otra is not None:
        raise BusinessError(f"{driver.nombre} ya tiene la ruta #{otra.id} ese día.")


def _vehicle_free(vehicle, fecha, route=None):
    otra = db().execute(select(Route).where(Route.fecha == fecha, Route.vehicle_id == vehicle.id,
                                            Route.estado.in_(("PROPUESTA", "CONFIRMADA", "EN_RUTA")),
                                            Route.id != (route.id if route is not None else -1))).scalars().first()
    if otra is not None:
        raise BusinessError(f"La unidad {vehicle.placa} ya tiene la ruta #{otra.id} ese día.")
    from .fleet import check_soat
    check_soat(vehicle, fecha)


def automatic_proposal(o, route=None):
    """Ruta PROPUESTA por el sistema (no manual, no confirmada) donde está la OV: Distribución puede tomarla de allí."""
    st = db().execute(select(RouteStop).join(Route).where(RouteStop.order_id == o.id, Route.estado == "PROPUESTA",
                                                          Route.manual.is_(False),
                                                          Route.id != (route.id if route is not None else -1))).scalars().first()
    return st


def _take_from_proposal(o, user, route=None):
    st = automatic_proposal(o, route)
    if st is None:
        return
    r = st.route
    r.stops.remove(st)
    db().delete(st)
    db().flush()
    _log(r, user, "OV pasada a una ruta manual", o.numero, f"ruta #{route.id}" if route is not None and route.id else "ruta manual")
    if not r.stops and not route_transfers(r):
        r.estado = "ANULADA"
        r.advertencias = list(r.advertencias or []) + ["Anulada: sus OV pasaron a rutas registradas por Distribución."]
    else:
        _recalc(r)


def _orders_ok(ids, route=None):
    from .distribution import orders_in_active_route
    usados = orders_in_active_route()
    actuales = {st.order_id for st in route.stops} if route is not None else set()
    out = []
    for i in ids:
        o = db().get(SalesOrder, int(i))
        if o is None:
            raise BusinessError("OV no encontrada.")
        if o.id in usados and o.id not in actuales and automatic_proposal(o, route) is None:
            raise BusinessError(f"La OV {o.numero} ya está en otra ruta activa.")
        if o.estado in ("CANCELADA", "DESPACHADA", "ENTREGADA", "BORRADOR", "BLOQUEADA"):
            raise BusinessError(f"La OV {o.numero} está {o.estado.lower()}: no se programa.")
        out.append(o)
    return out


def _transfers_ok(ids, route=None):
    out = []
    for i in ids:
        t = db().get(Transfer, int(i))
        if t is None:
            raise BusinessError("Traslado no encontrado.")
        if t.estado not in ("AUTORIZADO", "SOLICITADO"):
            raise BusinessError(f"El traslado #{t.id} está {t.estado.lower()}: no se programa.")
        ya = db().execute(select(RouteTransfer).join(Route).where(RouteTransfer.transfer_id == t.id,
                                                                    Route.estado.in_(("PROPUESTA", "CONFIRMADA", "EN_RUTA")),
                                                                    Route.id != (route.id if route is not None else -1))
                          ).scalars().first()
        if ya is not None:
            raise BusinessError(f"El traslado #{t.id} ya está en la ruta #{ya.route_id}.")
        out.append(t)
    return out


def _auxiliares(ids, fecha):
    from . import ausencias
    out = []
    for i in dict.fromkeys(int(x) for x in ids if str(x).strip()):
        u = db().get(User, i)
        if u is None or not u.activo or u.role_code != "AUX_DESPACHO":
            raise BusinessError("Elija auxiliares de despacho activos.")
        aus = ausencias.ausencia_de("USER", u.id, fecha)
        if aus:
            raise BusinessError(f"{u.nombre} no está disponible el {fecha:%d/%m/%Y}: {ausencias.texto(aus)}.")
        out.append(u.id)
    return out


TIPOS_TRANSPORTISTA = ("CHOFER", "TRABAJADOR", "TERCERO")


def _hora(v):
    """V24: la hora se elige de la lista o se escribe (7:30, 0730, 7.30 → 07:30)."""
    t = (v or "").strip().replace(".", ":").replace("h", ":").rstrip(":")
    if not t:
        return ""
    if ":" not in t and t.isdigit() and len(t) in (3, 4):
        t = t[:-2] + ":" + t[-2:]
    if ":" not in t and t.isdigit():
        t += ":00"
    try:
        hh, mm = (int(x) for x in t.split(":")[:2])
    except ValueError:
        raise BusinessError("Hora de salida no válida (use HH:MM).") from None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise BusinessError("Hora de salida no válida (use HH:MM).")
    return f"{hh:02d}:{mm:02d}"


def _transportista(datos):
    tipo = (datos.get("tipo_transportista") or "CHOFER").upper()
    if tipo not in TIPOS_TRANSPORTISTA:
        raise BusinessError("Tipo de transportista no válido.")
    if tipo == "TERCERO":
        # V24 (07-nov): si es transporte externo se ingresa su costo
        try:
            costo = float(str(datos.get("costo_tercero") or "").replace(",", "."))
        except ValueError:
            costo = 0
        if costo <= 0:
            raise BusinessError("Indique el costo del transporte externo (S/).")
        return {"tipo": tipo, "costo": round(costo, 2), "proveedor": (datos.get("proveedor_tercero") or "").strip()[:120]}
    if tipo != "TRABAJADOR":
        return {"tipo": tipo}
    # V24: el trabajador se elige de la lista (con su área) o «Otro» se escribe
    if datos.get("t_user_id") and str(datos.get("t_user_id")) != "__OTRO__":
        from ..models import User
        u = db().get(User, int(datos["t_user_id"]))
        if u is not None:
            datos = dict(datos)
            datos["t_nombre"] = u.nombre
            datos["t_area"] = datos.get("t_area") or (u.role.area if u.role else "")
    elif str(datos.get("t_user_id") or "") == "__OTRO__":
        datos = dict(datos)
        datos["t_user_id"] = ""
    t = {"tipo": tipo, "nombre": (datos.get("t_nombre") or "").strip(), "area": (datos.get("t_area") or "").strip(),
         "placa": (datos.get("t_placa") or "").strip().upper(), "vehiculo": (datos.get("t_vehiculo") or "").strip(),
         "motivo": (datos.get("t_motivo") or "").strip(), "user_id": int(datos["t_user_id"]) if datos.get("t_user_id") else None}
    falta = [k for k, lbl in (("nombre", "nombre del trabajador"), ("area", "área"), ("vehiculo", "vehículo"),
                              ("motivo", "motivo")) if not t[k]]
    if falta:
        raise BusinessError("Cuando la carga la lleva otro trabajador indique: " + ", ".join(
            lbl for k, lbl in (("nombre", "nombre del trabajador"), ("area", "área"), ("vehiculo", "datos del vehículo"),
                               ("motivo", "motivo")) if k in falta) + ".")
    return t


# ------------------------------------------------------------------ ruta manual
def create_manual(user, fecha, datos, orden_ids=(), traslado_ids=(), auxiliar_ids=()):
    """Ruta registrada a mano por Distribución para el día."""
    _req(user)
    if fecha is None:
        raise BusinessError("Indique la fecha de la ruta.")
    if fecha < date.today():
        raise BusinessError("No se registran rutas en fechas pasadas.")
    ordenes = _orders_ok(orden_ids)
    traslados = _transfers_ok(traslado_ids)
    if not ordenes and not traslados:
        raise BusinessError("Agregue al menos una OV o un traslado a la ruta.")
    trans = _transportista(datos)
    vehicle = driver = None
    if trans["tipo"] != "TRABAJADOR":
        if datos.get("vehicle_id"):
            vehicle = db().get(Vehicle, int(datos["vehicle_id"]))
            if vehicle is None:
                raise BusinessError("Unidad no válida.")
            _vehicle_free(vehicle, fecha)
        if datos.get("driver_id"):
            driver = db().get(Driver, int(datos["driver_id"]))
            _driver_free(driver, fecha)
        if trans["tipo"] == "CHOFER" and (vehicle is None or driver is None):
            raise BusinessError("Elija el vehículo y el chofer de la ruta.")
        if trans["tipo"] == "TERCERO" and vehicle is None:
            raise BusinessError("Elija la unidad del transporte tercero (regístrela en Flota si no existe).")
    auxs = _auxiliares(auxiliar_ids, fecha)
    r = Route(fecha=fecha, vehicle_id=vehicle.id if vehicle else None, driver_id=driver.id if driver else None,
              requiere_externo=bool(vehicle is not None and not vehicle.propio), zona=(datos.get("zona") or "").strip()[:120],
              estado="PROPUESTA", manual=True, auxiliares=auxs, auxiliar_id=auxs[0] if auxs else None, transportista=trans,
              hora_salida_prog=_hora(datos.get("hora_salida")), creado_por=user.id, advertencias=[])
    db().add(r)
    db().flush()
    for o in ordenes:
        _take_from_proposal(o, user, r)
    for i, o in enumerate(ordenes, 1):
        r.stops.append(RouteStop(order_id=o.id, orden=i, peso_kg=peso_ov(o)))
    for i, t in enumerate(traslados, 1):
        db().add(RouteTransfer(route_id=r.id, transfer_id=t.id, orden=i, peso_kg=transfer_weight(t), user_id=user.id))
    db().flush()
    if not r.zona:
        r.zona = ", ".join(sorted({(o.distrito or o.customer.distrito or "").upper() for o in ordenes} - {""}))[:120] or "TRASLADOS"
    _recalc(r, user)
    audit(user, "RUTA_MANUAL", "Route", r.id, {"ov": [o.numero for o in ordenes], "traslados": [t.id for t in traslados],
                                                "transportista": trans, "auxiliares": auxs})
    return r


def modify(route, user, motivo="", agregar_ov=(), quitar_stop=(), agregar_traslado=(), quitar_traslado=(),
           vehicle_id=None, driver_id=None, auxiliar_ids=None, datos=None):
    """Cambios a una ruta programada (propuesta o confirmada) con motivo; quedan en el rastro de la ruta."""
    _req(user)
    if route.estado not in EDITABLES:
        raise BusinessError("Solo se modifican rutas que aún no salen.")
    motivo = (motivo or "").strip()
    if route.estado == "CONFIRMADA" and not motivo:
        raise BusinessError("Indique el motivo del cambio (la ruta ya estaba confirmada).")
    if vehicle_id and int(vehicle_id) != (route.vehicle_id or 0):
        v = db().get(Vehicle, int(vehicle_id)) or None
        if v is None:
            raise BusinessError("Unidad no válida.")
        _vehicle_free(v, route.fecha, route)
        _log(route, user, "vehículo", route.vehicle.placa if route.vehicle else "-", v.placa, motivo)
        route.vehicle_id = v.id
        route.requiere_externo = not v.propio
        db().flush()
        db().refresh(route)
    if driver_id and int(driver_id) != (route.driver_id or 0):
        d = db().get(Driver, int(driver_id))
        _driver_free(d, route.fecha, route)
        _log(route, user, "chofer", route.driver.nombre if route.driver else "-", d.nombre, motivo)
        route.driver_id = d.id
        route.carga_chofer = {}
    if auxiliar_ids is not None:
        auxs = _auxiliares(auxiliar_ids, route.fecha)
        if auxs != list(route.auxiliares or []):
            nombres = lambda ids: ", ".join(db().get(User, i).nombre for i in ids) or "-"  # noqa: E731
            _log(route, user, "auxiliares", nombres(route.auxiliares or ([route.auxiliar_id] if route.auxiliar_id else [])),
                 nombres(auxs), motivo)
            route.auxiliares = auxs
            route.auxiliar_id = auxs[0] if auxs else None
    if datos is not None and (datos.get("tipo_transportista") or "") != "":
        t = _transportista(datos)
        if t != (route.transportista or {}):
            _log(route, user, "transportista", (route.transportista or {}).get("tipo", "CHOFER"), t.get("tipo"), motivo)
            route.transportista = t
    for sid in quitar_stop:
        st = db().get(RouteStop, int(sid))
        if st is None or st.route_id != route.id:
            continue
        _log(route, user, "OV quitada", st.order.numero, "-", motivo)
        route.stops.remove(st)
        db().delete(st)
    for o in _orders_ok(agregar_ov, route):
        if any(st.order_id == o.id for st in route.stops):
            continue
        _take_from_proposal(o, user, route)
        route.stops.append(RouteStop(order_id=o.id, orden=len(route.stops) + 1, peso_kg=peso_ov(o)))
        _log(route, user, "OV agregada", "-", o.numero, motivo)
    for rid in quitar_traslado:
        rt = db().get(RouteTransfer, int(rid))
        if rt is not None and rt.route_id == route.id:
            _log(route, user, "traslado quitado", f"#{rt.transfer_id}", "-", motivo)
            db().delete(rt)
    actuales = {rt.transfer_id for rt in route_transfers(route)}
    for t in _transfers_ok(agregar_traslado, route):
        if t.id in actuales:
            continue
        db().add(RouteTransfer(route_id=route.id, transfer_id=t.id, orden=len(actuales) + 1, peso_kg=transfer_weight(t),
                               user_id=user.id))
        _log(route, user, "traslado agregado", "-", f"#{t.id}", motivo)
    db().flush()
    for i, st in enumerate(sorted(route.stops, key=lambda s: s.orden), 1):
        st.orden = i
    if not route.stops and not route_transfers(route):
        raise BusinessError("La ruta quedaría vacía: anúlela en lugar de quitar todo.")
    _recalc(route, user)
    audit(user, "RUTA_MODIFICADA", "Route", route.id, {"motivo": motivo, "cambios": (route.cambios or [])[-5:]})
    return route


def set_real_weight(route, user, peso):
    """Peso real de lo cargado (balanza o declaración del almacén) para el análisis de sobrecarga."""
    if not (has_perm(user, "distribucion.programar") or has_perm(user, "distribucion.seguridad")
            or has_perm(user, "distribucion.carga")):
        raise BusinessError("Registra el peso real Distribución, Seguridad o quien valida la carga.")
    try:
        peso = float(peso)
    except (TypeError, ValueError):
        raise BusinessError("Peso real inválido.") from None
    if peso <= 0:
        raise BusinessError("Peso real inválido.")
    route.peso_real_kg = round(peso, 2)
    audit(user, "RUTA_PESO_REAL", "Route", route.id, {"peso_real_kg": route.peso_real_kg})
    return _check_overload(route, user)


def register_overnight(route, user, fotos, nota=""):
    """Pernocte: el chofer deja foto de lo que queda en el vehículo durante la noche."""
    es_chofer = route.driver is not None and route.driver.user_id == user.id
    if not (es_chofer or has_perm(user, "distribucion.programar")):
        raise BusinessError("El pernocte lo registra el chofer de la ruta.")
    fotos = [f for f in (fotos or []) if f]
    if not fotos:
        raise BusinessError("Adjunte al menos una foto de lo que queda en el vehículo.")
    route.pernocte = list(route.pernocte or []) + [{"fotos": fotos, "nota": (nota or "").strip(), "user": user.nombre,
                                                    "ts": now().isoformat(timespec="minutes")}]
    audit(user, "RUTA_PERNOCTE", "Route", route.id, {"fotos": len(fotos)})
    return route


# ------------------------------------------------------------------ cuadro diario
def _guias(stop):
    return [stop.guia_numero] if stop.guia_numero else []


def daily_board(fecha):
    """Cuadro de despacho del día: por vehículo, quién lo lleva, clientes, OV, guías, peso y valor."""
    rutas = list(db().execute(select(Route).where(Route.fecha == fecha, Route.estado != "ANULADA")
                              .order_by(Route.hora_salida_prog, Route.id)).scalars())
    filas = []
    tot = {"rutas": 0, "peso": 0.0, "valor": 0.0, "clientes": set(), "ov": 0, "traslados": 0, "sobrecarga": 0}
    for r in rutas:
        trs = route_transfers(r)
        perm, real = capacidad(r.vehicle)
        peso = r.peso_real_kg or r.peso_total or 0
        clientes = defaultdict(list)
        valor = 0.0
        for st in sorted(r.stops, key=lambda s: s.orden):
            m = order_amount(st.order)
            valor += m
            clientes[st.order.customer.nombre].append({"stop": st, "ov": st.order.numero, "guias": _guias(st), "valor": m,
                                                       "peso": st.peso_kg, "distrito": st.order.distrito or st.order.customer.distrito,
                                                       "estado": st.estado})
        auxs = [db().get(User, i) for i in (r.auxiliares or ([r.auxiliar_id] if r.auxiliar_id else []))]
        t = r.transportista or {}
        quien = (f"{t.get('nombre')} ({t.get('area')})" if t.get("tipo") == "TRABAJADOR" else
                 (r.driver.nombre if r.driver else "—"))
        vehiculo = (f"{t.get('vehiculo')} {t.get('placa') or ''}".strip() if t.get("tipo") == "TRABAJADOR" else
                    (f"{r.vehicle.placa} · {r.vehicle.descripcion or r.vehicle.tipo_unidad}" if r.vehicle else "—"))
        sc = overload(r)
        filas.append({"r": r, "quien": quien, "vehiculo": vehiculo, "auxiliares": [a for a in auxs if a],
                      "tipo": t.get("tipo", "TERCERO" if r.requiere_externo else "CHOFER"), "motivo": t.get("motivo", ""),
                      "clientes": dict(clientes), "traslados": trs, "peso": peso, "permitido": perm, "real": real,
                      "uso_pct": round(100 * peso / perm, 1) if perm else None, "valor": round(valor, 2), "sobrecarga": sc})
        tot["rutas"] += 1
        tot["peso"] += peso
        tot["valor"] += valor
        tot["clientes"] |= set(clientes)
        tot["ov"] += len(r.stops)
        tot["traslados"] += len(trs)
        tot["sobrecarga"] += 1 if sc else 0
    tot["clientes"] = len(tot["clientes"])
    return {"fecha": fecha, "filas": filas, "tot": tot}


def board_excel(fecha):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    d = daily_board(fecha)
    wb = Workbook()
    ws = wb.active
    ws.title = "Despacho"
    cab = ["Ruta", "Salida", "Vehículo", "Lleva", "Auxiliares", "Cliente", "OV", "Guía(s)", "Distrito", "Peso kg",
           "Valor S/", "Peso permitido kg", "% uso", "Estado"]
    ws.append([f"Cuadro de despacho {fecha:%d/%m/%Y}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(cab)
    for c in ws[2]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0B6B3A")
    for f in d["filas"]:
        auxs = ", ".join(a.nombre for a in f["auxiliares"])
        primera = True
        for cli, items in f["clientes"].items():
            for it in items:
                ws.append([f["r"].id if primera else "", f["r"].hora_salida_prog if primera else "", f["vehiculo"] if primera else "",
                           f["quien"] if primera else "", auxs if primera else "", cli, it["ov"], ", ".join(it["guias"]),
                           it["distrito"], round(it["peso"] or 0, 1), round(it["valor"], 2),
                           f["permitido"] if primera else "", f["uso_pct"] if primera else "", f["r"].estado if primera else ""])
                primera = False
        for rt in f["traslados"]:
            t = rt.transfer
            ws.append([f["r"].id if primera else "", "", f["vehiculo"] if primera else "", f["quien"] if primera else "", "",
                       f"TRASLADO a {t.destino_code}", f"#{t.id}", "", t.lot.warehouse_code if t.lot else "",
                       round(rt.peso_kg or 0, 1), "", "", "", t.estado])
            primera = False
    ws.append([])
    ws.append(["Total", "", "", "", "", f"{d['tot']['clientes']} clientes", f"{d['tot']['ov']} OV", "", "",
               round(d["tot"]["peso"], 1), round(d["tot"]["valor"], 2)])
    for col, w in zip("ABCDEFGHIJKLMN", (7, 8, 26, 24, 24, 36, 10, 18, 16, 10, 12, 12, 8, 12)):
        ws.column_dimensions[col].width = w
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ------------------------------------------------------------------ análisis de carga por vehículo
def vehicle_load_stats(dias=90, hoy=None):
    """Por vehículo: peso permitido, capacidad real, carga habitual (registrada y la real promedio), máximos y cuántas
    rutas salieron sobrecargadas en el periodo."""
    hoy = hoy or date.today()
    desde = hoy - timedelta(days=dias)
    out = []
    for v in db().execute(select(Vehicle).order_by(Vehicle.placa)).scalars():
        rs = list(db().execute(select(Route).where(Route.vehicle_id == v.id, Route.fecha >= desde, Route.fecha <= hoy,
                                                   Route.estado.in_(("CONFIRMADA", "EN_RUTA", "CERRADA")))).scalars())
        pesos = [r.peso_real_kg or r.peso_total or 0 for r in rs]
        perm = v.capacidad_kg or 0
        sobre = [p for p in pesos if perm and p > perm + 1e-9]
        out.append({"v": v, "rutas": len(rs), "promedio": round(sum(pesos) / len(pesos), 1) if pesos else None,
                    "maximo": round(max(pesos), 1) if pesos else None, "permitido": perm, "real": v.capacidad_real_kg,
                    "habitual": v.carga_habitual_kg, "sobrecargas": len(sobre),
                    "pct_sobrecarga": round(100 * len(sobre) / len(pesos), 1) if pesos else None,
                    "uso_prom_pct": round(100 * (sum(pesos) / len(pesos)) / perm, 1) if pesos and perm else None})
    return out


def driver_clients(driver, dias=90):
    """Clientes que lleva el chofer (últimos días) y sus rutas próximas: para reasignar si no está disponible."""
    desde = date.today() - timedelta(days=dias)
    cont = defaultdict(int)
    for st in db().execute(select(RouteStop).join(Route).where(Route.driver_id == driver.id, Route.fecha >= desde)).scalars():
        cont[st.order.customer.nombre] += 1
    proximas = list(db().execute(select(Route).where(Route.driver_id == driver.id, Route.fecha >= date.today(),
                                                     Route.estado.in_(("PROPUESTA", "CONFIRMADA")))
                                 .order_by(Route.fecha)).scalars())
    return sorted(cont.items(), key=lambda x: -x[1]), proximas


def open_transfers():
    """Traslados entre almacenes por programar (autorizados o solicitados) que no están en una ruta activa."""
    en_ruta = {rt.transfer_id for rt in db().execute(select(RouteTransfer).join(Route).where(
        Route.estado.in_(("PROPUESTA", "CONFIRMADA", "EN_RUTA")))).scalars()}
    return [t for t in db().execute(select(Transfer).where(Transfer.estado.in_(("AUTORIZADO", "SOLICITADO")))
                                    .order_by(Transfer.id)).scalars() if t.id not in en_ruta]


# ------------------------------------------------------------------ V23: cuadro en el formato de la empresa
DIAS_SEMANA = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
ORDINAL_VIAJE = {1: "1ER VIAJE", 2: "2DO VIAJE", 3: "3ER VIAJE", 4: "4TO VIAJE", 5: "5TO VIAJE"}


def cuadro_empresa(fecha):
    """V23 (06-nov-2026): el cuadro diario de rutas en el formato del Excel de Distribución: un bloque por TRANSPORTE
    (unidad propia, otro trabajador o EXTERNO) con CLIENTE, PESO, DIRECCIÓN (con el número de viaje) y HR CITA; además la
    guía y el valor según la OV. Varias rutas de la misma unidad en el día son 1er, 2do y 3er viaje."""
    d = daily_board(fecha)
    grupos = {}
    for f in sorted(d["filas"], key=lambda x: (x["r"].hora_salida_prog or "99:99", x["r"].id)):
        r, t = f["r"], f["r"].transportista or {}
        if t.get("tipo") == "TERCERO" or (r.requiere_externo and r.vehicle is None) or (r.vehicle is not None and not r.vehicle.propio):
            clave = "EXTERNO"
        elif t.get("tipo") == "TRABAJADOR":
            clave = f"{(t.get('vehiculo') or 'VEHÍCULO').upper()} {t.get('placa') or ''}".strip() + f" · {t.get('nombre', '')}"
        elif r.vehicle is not None:
            clave = f"{(r.vehicle.marca or r.vehicle.descripcion or '').upper()[:18]} {r.vehicle.placa}".strip()
        else:
            clave = "POR ASIGNAR"
        g = grupos.setdefault(clave, {"transporte": clave, "viajes": [], "filas": [], "peso": 0.0, "valor": 0.0})
        n = len(g["viajes"]) + 1
        g["viajes"].append(r.id)
        viaje = ORDINAL_VIAJE.get(n, f"{n}° VIAJE")
        for cli, items in f["clientes"].items():
            for it in items:
                o = it["stop"].order
                direc = (o.lugar_entrega or o.direccion or "").strip()
                dist = (it["distrito"] or "").upper()
                texto = f"{dist}{' – ' + direc if direc and dist not in direc.upper() else ''}".strip(" –") or "POR DEFINIR"
                g["filas"].append({"cliente": cli, "peso": round(it["peso"] or 0, 1), "direccion": f"{texto} ({viaje})",
                                   "cita": (o.hora_cita or "") + (" ✓" if o.cita_confirmada else ""), "guias": it["guias"],
                                   "ov": it["ov"], "valor": it["valor"], "ruta": r.id, "viaje": viaje, "estado": it["estado"]})
                g["peso"] += it["peso"] or 0
                g["valor"] += it["valor"] or 0
        for tr in f["traslados"]:
            peso = tr.peso_kg or 0
            dest = tr.transfer.destino_code if getattr(tr, "transfer", None) is not None else ""
            g["filas"].append({"cliente": f"TRASLADO ENTRE ALMACENES → {dest}",
                               "peso": round(peso or 0, 1), "direccion": f"{dest} ({viaje})", "cita": "",
                               "guias": [], "ov": "", "valor": 0.0, "ruta": r.id, "viaje": viaje, "estado": ""})
            g["peso"] += peso or 0
    orden = sorted(grupos.values(), key=lambda g: (g["transporte"] == "EXTERNO", g["transporte"] == "POR ASIGNAR", g["transporte"]))
    return {"fecha": fecha, "dia": DIAS_SEMANA[fecha.weekday()], "grupos": orden, "tot": d["tot"]}


def cuadro_empresa_excel(fecha):
    """Excel con el mismo formato: encabezado verde con el día, transporte combinado por bloque y HR CITA en amarillo."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    d = cuadro_empresa(fecha)
    wb = Workbook()
    ws = wb.active
    ws.title = f"{fecha:%d-%m}"
    verde = PatternFill("solid", fgColor="7DCE8C")
    amarillo = PatternFill("solid", fgColor="FBE3A1")
    gris = PatternFill("solid", fgColor="E7E9EC")
    fino = Side(style="thin", color="999999")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    cab = ["TRANSPORTE", "CLIENTE", "PESO", "DIRECCIÓN", "HR CITA", "GUÍA", "OV", "VALOR S/"]
    ws.merge_cells("A1:H1")
    ws["A1"] = d["dia"]
    ws.merge_cells("A2:H2")
    ws["A2"] = f"{fecha:%d/%m/%Y}"
    ws.append(cab)
    for row in (1, 2, 3):
        for c in ws[row]:
            c.fill, c.font, c.border = verde, Font(bold=True), borde
            c.alignment = Alignment(horizontal="center", vertical="center")
    fila = 4
    for g in d["grupos"]:
        ini = fila
        for x in g["filas"] or [{"cliente": "", "peso": "", "direccion": "", "cita": "", "guias": [], "ov": "", "valor": ""}]:
            ws.append(["", x["cliente"], x["peso"], x["direccion"], x["cita"], ", ".join(x["guias"]), x["ov"], x["valor"]])
            for c in ws[fila]:
                c.border = borde
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.cell(fila, 5).fill = amarillo
            fila += 1
        ws.append(["", "Total del transporte", round(g["peso"], 1), "", "", "", "", round(g["valor"], 2)])
        for c in ws[fila]:
            c.font, c.border = Font(bold=True), borde
        fila += 1
        ws.merge_cells(start_row=ini, start_column=1, end_row=fila - 1, end_column=1)
        a = ws.cell(ini, 1)
        a.value, a.fill, a.font = g["transporte"], gris, Font(bold=True)
        a.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col, w in zip("ABCDEFGH", (18, 34, 10, 48, 12, 18, 14, 12)):
        ws.column_dimensions[col].width = w
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
