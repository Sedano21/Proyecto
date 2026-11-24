"""V73 (24-nov-2026): lo que piden los choferes y auxiliares de distribución (capacitación del 24-nov).

- **Checklist de carga por guía.** Por cada OV de la ruta, sus productos de la pre-guía con lote, FP y FV ya puestos. Se
  marca «está bien» o se corrige la cantidad cargada, y se puede anotar si la mercadería va mal paletizada. Lo que no
  cuadra se reporta como faltante o sobrante (Almacén lo resuelve antes de salir).
- **Paso a paso en el cliente.** Llegué → me están atendiendo → conformidad (conforme o con inconformidad) → salí. Así se
  mide cuánto se espera en cada cliente (para reducir el alquiler de unidades de terceros).
- **No me dejan ingresar.** El chofer activa la alerta; le llega a Comercial (el ejecutivo de la OV y la coordinación) y
  a Distribución para que habiliten el acceso.
- **Peaje o combustible.** Deuda de peajes o tarjeta de combustible sin saldo: alerta a Finanzas, a la Coordinación de
  Distribución y a la Jefatura de Operaciones.
- **Parqueo.** El gasto de parqueo, con o sin comprobante (los cuidadores no lo dan), queda registrado en la ruta para su
  reembolso.
- **Correo de coordinación (cita).** Quien arma la ruta adjunta el correo de la cita a la parada para que el chofer lo
  muestre a Seguridad del cliente."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Route, RouteStop, now
from . import alerts
from .core import BusinessError, audit, has_perm


def es_de_la_ruta(user, route):
    drv = route.driver
    return bool((drv is not None and drv.user_id == user.id) or user.id in (route.auxiliares or [])
                or route.auxiliar_id == user.id)


def rutas_de(user):
    """Rutas de ayer a mañana (y las que siguen en ruta) donde el usuario va de chofer o de auxiliar."""
    hoy = date.today()
    rs = db().execute(select(Route).where(Route.estado.in_(("PROPUESTA", "CONFIRMADA", "EN_RUTA")),
                                          Route.fecha >= hoy - timedelta(days=1), Route.fecha <= hoy + timedelta(days=1))
                      .order_by(Route.fecha, Route.id)).scalars()
    return [r for r in rs if es_de_la_ruta(user, r) or has_perm(user, "distribucion.programar")]


def _check_participa(user, route):
    if not (es_de_la_ruta(user, route) or has_perm(user, "distribucion.programar")):
        raise BusinessError("Lo registra el chofer o el auxiliar de la ruta.")


# ------------------------------------------------------------------ checklist de carga por guía
def checklist_guia(route, order_id):
    """Líneas de la pre-guía de una OV de la ruta, con lote, FP y FV."""
    from .despacho import preguia
    for g in preguia(route):
        if g["order"].id == int(order_id):
            return g
    return None


def registrar_checklist(user, route, order_id, lineas, observacion="", mal_paletizado=False):
    """lineas: {order_line_id: {"ok": bool, "cantidad": cargado}}. Lo que no cuadra se reporta como faltante o sobrante."""
    from .carga_v70 import PUEDEN_REPORTAR, reportar_novedad
    if not any(has_perm(user, p) for p in PUEDEN_REPORTAR):
        raise BusinessError("Validan la carga Almacén, el Auxiliar de Despacho, el chofer, Seguridad o Calidad.")
    if route.estado not in ("PROPUESTA", "CONFIRMADA"):
        raise BusinessError("La ruta ya salió.")
    g = checklist_guia(route, order_id)
    if g is None:
        raise BusinessError("Esa OV no es de esta ruta.")
    detalle, novedades = [], []
    for it in g["items"]:
        v = lineas.get(str(it["order_line_id"])) or {}
        ok = v.get("ok") in (True, "1", "on", 1)
        if ok or v.get("cantidad") in (None, ""):
            q = it["cantidad"]
        else:
            try:
                q = float(str(v.get("cantidad")).replace(",", "."))
            except ValueError:
                raise BusinessError(f"{it['codigo']}: cantidad no válida.")
        dif = round(q - it["cantidad"], 6)
        detalle.append({"producto": it["codigo"], "preguia": it["cantidad"], "cargado": q, "ok": abs(dif) < 1e-9,
                        "lotes": [x["lote"] for x in it.get("lotes") or []]})
        if dif < -1e-9:
            novedades.append(reportar_novedad(user, route, "FALTANTE", -dif, it["order_line_id"],
                                              nota=f"Checklist de la guía. {observacion}".strip()))
        elif dif > 1e-9:
            novedades.append(reportar_novedad(user, route, "SOBRANTE", dif, it["order_line_id"],
                                              nota=f"Checklist de la guía. {observacion}".strip()))
    ac = dict(route.aviso_carga or {})
    chk = dict(ac.get("checklists") or {})
    chk[str(order_id)] = {"ov": g["order"].numero, "user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                          "lineas": detalle, "observacion": (observacion or "").strip()[:300],
                          "mal_paletizado": bool(mal_paletizado), "conforme": not novedades and not mal_paletizado}
    ac["checklists"] = chk
    route.aviso_carga = ac
    if mal_paletizado:
        from .carga_v70 import almacenes_de, personal_de
        from .distribution import _incident
        _incident(user, "CARGA_MAL_PALETIZADA", route=route, order=g["order"],
                  descripcion=f"Mercadería mal paletizada (OV {g['order'].numero}). {observacion}".strip())
        alerts.emit("CARGA_INCONGRUENCIA", f"Ruta #{route.id}: mercadería mal paletizada (OV {g['order'].numero})",
                    (observacion or "").strip() or "Revisar y volver a paletizar antes de salir.", "Route", route.id,
                    extra_users=[u.id for k in almacenes_de(route) for u in personal_de(k)], creado_por=user)
    audit(user, "CARGA_CHECKLIST_GUIA", "Route", route.id, chk[str(order_id)])
    return chk[str(order_id)], novedades


# ------------------------------------------------------------------ paso a paso en el cliente
def marcar(user, stop, hito):
    """ATENCION (me están atendiendo / descargando) o SALIDA (salí del cliente)."""
    _check_participa(user, stop.route)
    hito = (hito or "").upper()
    h = dict(stop.hitos or {})
    if hito == "ATENCION":
        if stop.estado not in ("LLEGADA",):
            raise BusinessError("Primero marque «Llegué».")
        if h.get("atencion"):
            raise BusinessError("Ya se marcó la atención.")
    elif hito == "SALIDA":
        if stop.estado not in ("ENTREGADO", "ENTREGA_PARCIAL", "RECHAZADO", "NO_ENTREGADO", "DEVUELTO", "LLEGADA"):
            raise BusinessError("Primero registre la entrega (o la incidencia).")
        if h.get("salida"):
            raise BusinessError("Ya se marcó la salida.")
    else:
        raise BusinessError("Hito no válido.")
    h["atencion" if hito == "ATENCION" else "salida"] = {"ts": now().isoformat(timespec="minutes"), "user": user.nombre}
    stop.hitos = h
    audit(user, "PARADA_" + hito, "RouteStop", stop.id, {})
    return h


def impedimento(user, stop, nota=""):
    """No le permiten el ingreso al cliente: alerta a Comercial y a Distribución."""
    _check_participa(user, stop.route)
    h = dict(stop.hitos or {})
    h["impedimentos"] = list(h.get("impedimentos") or []) + [{"ts": now().isoformat(timespec="minutes"), "user": user.nombre,
                                                                "nota": (nota or "").strip()[:300]}]
    stop.hitos = h
    o = stop.order
    alerts.emit("CHOFER_IMPEDIMENTO_INGRESO", f"No dejan ingresar a la unidad: {o.customer.nombre} (OV {o.numero})",
                f"Ruta #{stop.route_id}. {nota or ''} Habilitar el acceso con el cliente.".strip(), "Route", stop.route_id,
                prioridad="ALTA", extra_users=[o.vendedor_id] if o.vendedor_id else None, creado_por=user)
    audit(user, "PARADA_IMPEDIMENTO", "RouteStop", stop.id, {"nota": nota})


def adjuntar_correo_cita(user, stop, archivo, nota=""):
    if not has_perm(user, "distribucion.programar"):
        raise BusinessError("Adjunta el correo de la cita quien arma las rutas.")
    if not archivo:
        raise BusinessError("Adjunte el correo (foto, PDF o captura).")
    h = dict(stop.hitos or {})
    h["correos_cita"] = list(h.get("correos_cita") or []) + [{"archivo": archivo, "nota": (nota or "")[:200],
                                                                "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]
    stop.hitos = h


# ------------------------------------------------------------------ gastos y avisos del trayecto
TIPOS_GASTO = {"PARQUEO": "Parqueo", "PEAJE": "Deuda de peaje", "COMBUSTIBLE": "Tarjeta de combustible sin saldo",
               "OTRO": "Otro gasto"}


def registrar_gasto(user, route, tipo, monto=None, lugar="", comprobante=False, foto="", nota=""):
    _check_participa(user, route)
    tipo = (tipo or "").upper()
    if tipo not in TIPOS_GASTO:
        raise BusinessError("Elija el tipo.")
    try:
        monto = float(str(monto).replace(",", ".")) if str(monto or "").strip() else None
    except ValueError:
        raise BusinessError("Monto no válido.")
    if tipo == "PARQUEO" and not monto:
        raise BusinessError("Indique cuánto pagó de parqueo.")
    reg = {"n": len(route.gastos or []) + 1, "tipo": tipo, "monto": monto, "lugar": (lugar or "").strip()[:120],
           "comprobante": bool(comprobante), "foto": foto or "", "nota": (nota or "").strip()[:300], "user": user.nombre,
           "user_id": user.id, "ts": now().isoformat(timespec="minutes")}
    route.gastos = list(route.gastos or []) + [reg]
    placa = route.vehicle.placa if route.vehicle else ""
    if tipo in ("PEAJE", "COMBUSTIBLE"):
        alerts.emit("FLOTA_PEAJE_COMBUSTIBLE", f"{TIPOS_GASTO[tipo]}: {placa or 'ruta #' + str(route.id)}",
                    f"Reportó {user.nombre}. {reg['nota']}".strip() + (f" Monto S/ {monto:g}." if monto else ""), "Route",
                    route.id, prioridad="ALTA", creado_por=user)
    else:
        alerts.emit("RUTA_GASTO", f"{TIPOS_GASTO[tipo]} en la ruta #{route.id}: S/ {monto or 0:g}"
                    + ("" if comprobante else " (sin comprobante)"), f"{reg['lugar']} · {user.nombre}. {reg['nota']}".strip(),
                    "Route", route.id, creado_por=user)
    audit(user, "RUTA_GASTO", "Route", route.id, reg)
    return reg


def exceso_peso(route):
    """kg de la ruta frente a la capacidad del vehículo: (peso, capacidad, excede)."""
    cap = route.vehicle.capacidad_kg if route.vehicle else None
    peso = route.peso_total or sum(s.peso_kg or 0 for s in route.stops)
    return peso, cap, bool(cap and peso > cap + 1e-6)


# ------------------------------------------------------------------ demoras en clientes
def _ts(x):
    from datetime import datetime
    if not x:
        return None
    if isinstance(x, datetime):
        return x
    try:
        return datetime.fromisoformat(str(x))
    except ValueError:
        return None


def demoras(desde=None, hasta=None):
    """Por cliente: espera (de «Llegué» a «me están atendiendo»), atención (de ahí a la conformidad) y total en el
    cliente (de la llegada a la salida), en minutos."""
    desde = desde or date.today() - timedelta(days=30)
    hasta = hasta or date.today()
    acc = defaultdict(lambda: {"visitas": 0, "espera": [], "atencion": [], "total": []})
    from datetime import datetime
    for st in db().execute(select(RouteStop).where(RouteStop.llegada_ts >= datetime.combine(desde, datetime.min.time()),
                                                   RouteStop.llegada_ts < datetime.combine(hasta + timedelta(days=1),
                                                                                           datetime.min.time()))).scalars():
        lleg = _ts(st.llegada_ts)
        if lleg is None:
            continue
        h = st.hitos or {}
        aten = _ts((h.get("atencion") or {}).get("ts"))
        sal = _ts((h.get("salida") or {}).get("ts"))
        ent = _ts(st.entrega_ts)
        a = acc[st.order.customer.nombre if st.order and st.order.customer else "—"]
        a["visitas"] += 1
        if aten:
            a["espera"].append((aten - lleg).total_seconds() / 60)
        if aten and ent:
            a["atencion"].append((ent - aten).total_seconds() / 60)
        fin = sal or ent
        if fin:
            a["total"].append((fin - lleg).total_seconds() / 60)
    prom = (lambda xs: round(sum(xs) / len(xs)) if xs else None)
    filas = [{"cliente": c, "visitas": a["visitas"], "espera": prom(a["espera"]), "atencion": prom(a["atencion"]),
              "total": prom(a["total"]), "max_total": round(max(a["total"])) if a["total"] else None} for c, a in acc.items()]
    filas.sort(key=lambda f: -(f["total"] or 0))
    return {"desde": desde, "hasta": hasta, "filas": filas}


def certificados_de(routes):
    """{order_id: [certificados aprobados]} de las OV de las rutas."""
    from ..models import Certificate
    ids = [st.order_id for r in routes for st in r.stops] or [0]
    out = defaultdict(list)
    for c in db().execute(select(Certificate).where(Certificate.order_id.in_(ids), Certificate.estado == "APROBADO")).scalars():
        out[c.order_id].append(c)
    return dict(out)
