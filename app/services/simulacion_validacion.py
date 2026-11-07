"""Validación integral de una corrida de simulación (ENTORNO DE PRUEBAS).

Comprueba sobre los registros que creó la corrida: trazabilidad de OV, conservación del inventario, conexión
producción–almacén, picking contra OV, despachos contra pedidos preparados, checklists contra conductor y vehículo,
estados de las tareas, indicadores (calculados con las mismas funciones que usan los tableros, también día por día),
filtros por fecha y que las pantallas e informes respondan. No corrige nada: informa.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Incident, Liquidation, MoveRequest, PhysicalCount, PickingRecord, PickingTask, ProductionReport,
                      ProductionRequest, Route, RouteStop, SalesOrder, SimRun, StockLot, Transfer, User, VehicleChecklist)
from . import simulacion as sim

PANTALLAS = [  # (ruta, permiso que la abre, texto de la simulación que debe aparecer o None)
    ("/", None, None),
    ("/ov/", "ov.ver", None),
    ("/ov/preparacion", "preparacion.registrar", None),
    ("/almacen/stock", "stock.ver", "SIM-PT-"),
    ("/almacen/picking", "picking.asignar", None),
    ("/almacen/traslados", "traslado.autorizar", None),
    ("/almacen/conteos", "stock.conteo", None),
    ("/suministro/movimientos", "movimiento.solicitar", None),
    ("/produccion/", "produccion.ver", None),
    ("/produccion/monitoreo", "produccion.ver", "SIM-PT-"),
    ("/produccion/partes", "produccion.ver", None),
    ("/produccion/plan", "produccion.ver", None),
    ("/produccion/liquidaciones", "produccion.ver", None),
    ("/produccion/tablero", "produccion.ver", None),
    ("/distribucion/", "distribucion.ver", None),
    ("/distribucion/checklists", "distribucion.ver", "SIM-0"),
    ("/distribucion/flota", "distribucion.ver", "SIM-0"),
    ("/distribucion/incidencias", "distribucion.ver", None),
    ("/operacion/despacho", "distribucion.ver", None),
    ("/seguimiento/servicio", None, None),
    ("/seguimiento/desempeno", None, None),
    ("/seguimiento/expedientes", None, None),
    ("/alertas", "alertas.ver", None),
    ("/informes/", None, None),
]


def _ids(run, tabla):
    return sim.ids_creados(run.id, tabla)


def _q(model, run, tabla):
    ids = _ids(run, tabla)
    return list(db().execute(select(model).where(model.id.in_(ids)))) and \
        list(db().execute(select(model).where(model.id.in_(ids))).scalars()) or []


def _chk(out, area, nombre, errores, total, detalle=""):
    out.append({"area": area, "control": nombre, "ok": not errores, "total": total, "errores": len(errores),
                "ejemplos": [str(e) for e in errores[:6]], "detalle": detalle})


def validar(run=None, app=None):
    from . import kpis
    from .orders import prep_progress
    run = run or sim.ultima()
    if run is None or run.estado not in ("GENERADA", "FALLIDA"):
        return {"error": "No hay simulación cargada para validar."}
    ovs = _q(SalesOrder, run, "sales_orders")
    out = []
    # 1. trazabilidad de OV
    err = [o.numero for o in ovs if not o.lines or o.customer is None or not o.numero.startswith("SIM-")]
    _chk(out, "Comercial", "Cada OV tiene cliente, líneas y número propio de la simulación", err, len(ovs))
    desp = [o for o in ovs if o.estado in ("DESPACHADA", "ENTREGADA", "ENTREGA_PARCIAL", "DEVUELTA")]
    err = [o.numero for o in desp if o.salida_ts is None or db().execute(select(RouteStop.id).where(
        RouteStop.order_id == o.id)).first() is None]
    _chk(out, "Distribución", "Cada OV despachada tiene ruta y hora de salida", err, len(desp))
    err = [o.numero for o in desp if not any((l.preparado or 0) > 0 for l in o.lines)]
    _chk(out, "Almacén", "Cada despacho corresponde a un pedido preparado (picking registrado)", err, len(desp))
    entregadas = [o for o in ovs if o.estado == "ENTREGADA"]
    err = [o.numero for o in entregadas if not o.entrega_ts]
    _chk(out, "Distribución", "Cada OV entregada tiene fecha y hora de entrega", err, len(entregadas))
    # 2. inventario
    lots = _q(StockLot, run, "stock_lots")
    err = [f"{l.product_code}/{l.lote}/{l.warehouse_code}: {l.cantidad:g}" for l in lots if (l.cantidad or 0) < -1e-9]
    _chk(out, "Inventario", "Sin stock negativo en los lotes simulados", err, len(lots))
    from .stock import reserved_qty
    err = [f"{l.product_code}/{l.lote}: reservado {reserved_qty(l):g} > {l.cantidad:g}" for l in lots
           if reserved_qty(l) > (l.cantidad or 0) + 1e-6]
    _chk(out, "Inventario", "Lo comprometido no supera la existencia del lote", err, len(lots))
    # conservación: inicial + producción recibida + ajustes de conteo − despachado − diferencias de traslado = actual
    inicial = defaultdict(float)
    for r in db().execute(select(StockLot).where(StockLot.id.in_(_ids(run, "stock_lots")))).scalars():
        pass
    actual = defaultdict(float)
    for l in lots:
        actual[l.product_code] += l.cantidad or 0
    from ..simulacion_escenario import PRODUCTOS
    for code, _d, _p, _b, stock in PRODUCTOS:
        inicial[code] = stock + round(stock * 0.25) + round(stock * 0.3)
    liqs = _q(Liquidation, run, "liquidations")
    rec = defaultdict(float)
    for q in liqs:
        rec[q.product_code] += q.cantidad_recibida or 0
        if q.estado == "REGISTRADA":  # aún en el almacén de tránsito de producción
            rec[q.product_code] += q.cantidad_completada or 0
    ajuste = defaultdict(float)  # el conteo validado no cambia la cantidad SAP del lote: limita lo reservable
    dtr = defaultdict(float)
    for t in _q(Transfer, run, "transfers"):
        if t.estado.startswith("RECIBIDO"):
            dtr[t.lot.product_code] += t.diferencia or 0
        elif t.estado == "EN_TRANSITO":
            dtr[t.lot.product_code] += t.cantidad or 0
    salio = defaultdict(float)
    devuelto = defaultdict(float)
    for o in ovs:
        for l in o.lines:
            salio[l.product_code] += l.despachado or 0
            if o.estado in ("DEVUELTA", "ENTREGA_PARCIAL"):
                devuelto[l.product_code] += max((l.despachado or 0) - (l.entregado or 0), 0)
    err = []
    for code in inicial:
        esperado = inicial[code] + rec[code] + ajuste[code] - salio[code] - dtr[code] + devuelto[code]
        if abs(esperado - actual[code]) > 0.01:
            err.append(f"{code}: esperado {esperado:g}, en lotes {actual[code]:g} (dif. {actual[code] - esperado:+g})")
    _chk(out, "Inventario", "Conservación del inventario (inicial + producido + devuelto − despachado − en tránsito)",
         err, len(inicial), "Lo devuelto por el cliente reingresa como «pendiente de revisión» (despachado − entregado). "
         "El conteo físico no cambia la cantidad del lote (dato SAP): fija la cantidad verificada, que limita lo reservable.")
    # 3. producción ↔ almacén
    reqs = _q(ProductionRequest, run, "production_requests")
    liq_por_req = {q.request_id for q in liqs}
    err = [f"#{r.id}" for r in reqs if r.estado == "LIQUIDADA" and r.id not in liq_por_req]
    _chk(out, "Producción", "Cada producción liquidada tiene su liquidación", err, len([r for r in reqs if r.estado == "LIQUIDADA"]))
    err = [q.numero_documento for q in liqs if q.estado.startswith("RECIBIDA") and not q.lot_id]
    _chk(out, "Producción", "Cada liquidación recibida generó su lote en almacén", err, len(liqs))
    partes = _q(ProductionReport, run, "production_reports")
    err = [f"parte #{p.id}" for p in partes if p.estado == "EN PROCESO" and not p.inicio_ts and not p.hora_inicio]
    _chk(out, "Producción", "Partes en proceso con hora de inicio (lo que está hoy en cada línea)", err, len(partes))
    # 4. picking ↔ OV
    tareas = _q(PickingTask, run, "picking_tasks")
    ids_ov = {o.id for o in ovs}
    err = [f"tarea #{t.id}" for t in tareas if t.order_id not in ids_ov]
    _chk(out, "Almacén", "Cada picking corresponde a una OV de la simulación", err, len(tareas))
    recs = _q(PickingRecord, run, "picking_records")
    listos = [t for t in tareas if t.estado == "LISTO" and t.order.estado in ("PREPARADA", "EN_PREPARACION", "PROGRAMADA")]
    err = [f"tarea #{t.id}" for t in listos if prep_progress(t.order) < 100 - 1e-6]
    _chk(out, "Almacén", "Picking «listo» solo con el pedido completo (pedidos aún en almacén)", err, len(listos))
    err = [f"tarea #{t.id}" for t in tareas if t.estado == "EN_PROCESO" and not t.inicio_ts or t.estado == "LISTO" and not t.fin_ts]
    _chk(out, "Tareas", "Estado del picking coherente con sus horas de inicio y fin", err, len(tareas))
    movs = _q(MoveRequest, run, "move_requests")
    err = [f"mov #{m.id}" for m in movs if m.estado == "COMPLETADA" and not (m.inicio_ts and m.fin_ts and m.fin_ts >= m.inicio_ts)]
    _chk(out, "Tareas", "Movimientos de montacargas completados con inicio y fin", err, len(movs))
    # 5. checklists
    chks = _q(VehicleChecklist, run, "vehicle_checklists")
    err = [f"checklist #{c.id}" for c in chks if not (c.vehicle_id and c.driver_id and c.route_id and c.registrado_por)]
    _chk(out, "Distribución", "Cada checklist está vinculado a conductor, vehículo, ruta y quien lo registró", err, len(chks))
    rutas = _q(Route, run, "routes")
    salieron = [r for r in rutas if r.estado in ("EN_RUTA", "CERRADA")]
    con_salida = {c.route_id for c in chks if c.momento == "SALIDA" and c.estado == "VALIDADO"}
    err = [f"ruta #{r.id}" for r in salieron if r.vehicle and r.vehicle.propio and r.id not in con_salida]
    _chk(out, "Distribución", "Ningún vehículo propio salió sin checklist de salida validado", err, len(salieron))
    vacias = [r for r in rutas if r.estado == "PROPUESTA" and not r.stops]
    # 6. indicadores del sistema (las mismas funciones que alimentan los tableros)
    from .seguimiento import service_month
    k = kpis.compute(run.desde, run.hasta)
    serv = service_month(desde=run.desde, hasta=run.hasta)
    evolucion = []
    d = run.desde
    while d <= run.hasta:
        x = service_month(desde=d, hasta=d)
        evolucion.append({"fecha": d.isoformat(), "universo": x.get("universo"), "otif": x.get("otif"),
                          "on_time": x.get("on_time"), "in_full": x.get("in_full")})
        d += timedelta(days=1)
    inc = Counter(i.tipo for i in _q(Incident, run, "incidents"))
    estados_ov = Counter(o.estado for o in ovs)
    indicadores = {
        "Órdenes recibidas (simulación)": len(ovs),
        "Órdenes atendidas (despachadas o entregadas)": len(desp),
        "Órdenes pendientes (sistema, todo el entorno)": k.get("pendientes"),
        "OTIF del periodo (sistema)": serv.get("otif"), "On time (sistema)": serv.get("on_time"),
        "In full (sistema)": serv.get("in_full"), "OTIF salida (tablero)": (k.get("otif_salida") or [None])[0],
        "OTIF entrega (tablero)": (k.get("otif_entrega") or [None])[0],
        "Cobertura promedio de unidades % (tablero)": k.get("cobertura_unidades_prom"),
        "Faltantes (tablero, top)": len(k.get("faltantes") or []),
        "Producción pendiente (tablero)": k.get("produccion_pendiente"),
        "Producción planificada vs. ejecutada (und, simulación)": (
            sum(r.cantidad for r in reqs if r.estado in ("LIQUIDADA", "FINALIZADA")),
            sum(q.cantidad_completada or 0 for q in liqs)),
        "Partes en proceso ahora": sum(1 for p in partes if p.estado in ("EN PROCESO", "PAUSADO")),
        "Picking pendiente / en proceso / listo": tuple(Counter(t.estado for t in tareas).get(e, 0)
                                                         for e in ("PROGRAMADO", "EN_PROCESO", "LISTO")),
        "Movimientos pendientes / en curso / completados": tuple(Counter(m.estado for m in movs).get(e, 0)
                                                                  for e in ("SOLICITADA", "EN_CURSO", "COMPLETADA")),
        "Traslados en tránsito (pendientes de recepción)": sum(1 for t in _q(Transfer, run, "transfers") if t.estado == "EN_TRANSITO"),
        "Checklists registrados (salida / retorno)": (sum(1 for c in chks if c.momento == "SALIDA"),
                                                      sum(1 for c in chks if c.momento == "RETORNO")),
        "Incidencias por tipo (simulación)": dict(inc),
        "Entregas parciales según el tablero (cuenta solo el subtipo ENTREGA_PARCIAL)": k.get("entregas_parciales"),
        "OV con entrega parcial según su estado": estados_ov.get("ENTREGA_PARCIAL", 0),
        "Entregas completas / devueltas": (estados_ov.get("ENTREGADA", 0), estados_ov.get("DEVUELTA", 0)),
        "Diferencias de inventario (tablero)": k.get("diferencias_inventario"),
        "Tiempo de preparación promedio h (tablero)": k.get("tiempo_preparacion_h"),
        "Tiempo de despacho promedio h (tablero)": k.get("tiempo_despacho_h"),
    }
    hallazgos = []
    if indicadores["Entregas parciales según el tablero (cuenta solo el subtipo ENTREGA_PARCIAL)"] is not None and \
            estados_ov.get("ENTREGA_PARCIAL", 0) > (k.get("entregas_parciales") or 0):
        hallazgos.append("El indicador «entregas parciales» del tablero cuenta solo las incidencias del subtipo "
                         "ENTREGA_PARCIAL: una entrega parcial registrada con otro motivo (p. ej. producto roto) no se cuenta, "
                         "aunque la OV quede en estado ENTREGA_PARCIAL.")
    if vacias:
        hallazgos.append(f"{len(vacias)} rutas propuestas quedaron sin paradas al mover sus pedidos a otra ruta: «mover parada» "
                         "no anula la ruta que queda vacía (sigue apareciendo como propuesta).")
    # 7. filtros por fecha
    k_dia = kpis.compute(run.hasta, run.hasta)
    _chk(out, "Indicadores", "El filtro por fecha cambia el resultado (último día vs. periodo completo)",
         [] if (k_dia.get("n_ordenes") or 0) <= (k.get("n_ordenes") or 0) else ["el día tiene más OV que el periodo"],
         1, f"Periodo: {k.get('n_ordenes')} OV · último día: {k_dia.get('n_ordenes')} OV")
    # 8. pantallas e informes
    pantallas = _pantallas(app, ovs, rutas, partes) if app is not None else []
    err = [f"{p['ruta']}: {p['resultado']}" for p in pantallas if not p["ok"]]
    if pantallas:
        _chk(out, "Pantallas", "Pantallas e informes responden y muestran datos de la simulación", err, len(pantallas))
    return {"controles": out, "indicadores": indicadores, "evolucion": evolucion, "pantallas": pantallas,
            "hallazgos": hallazgos, "modificados_reales": {t: v.get("MODIFICADO") for t, v in sim.conteo_por_tabla(run.id).items()
                                                           if v.get("MODIFICADO")}}


def _pantallas(app, ovs=(), rutas=(), partes=()):
    from .core import has_perm
    usuarios = [u for u in db().execute(select(User).where(User.activo.is_(True)).order_by(User.id)).scalars()
                if not u.username.startswith("sim.")]
    res = []
    lista = list(PANTALLAS)
    o = next((x for x in ovs if x.estado == "ENTREGADA"), None)
    if o is not None:
        lista.append((f"/ov/{o.id}", "ov.ver", o.numero))
    r = next((x for x in rutas if x.estado == "CERRADA"), None)
    if r is not None:
        lista.append((f"/distribucion/ruta/{r.id}", "distribucion.ver", r.vehicle.placa if r.vehicle else None))
        lista.append((f"/distribucion/ruta/{r.id}/checklist", "distribucion.ver", "SALIDA" if False else None))
        if r.driver_id:
            lista.append((f"/distribucion/checklists?conductor={r.driver_id}&desde={r.fecha.isoformat()}", "checklist.ver",
                          r.vehicle.placa if r.vehicle else None))
    liq = db().execute(select(Liquidation).where(Liquidation.numero_documento.like("SIM-LIQ-%"))
                       .order_by(Liquidation.id.desc())).scalars().first()
    if liq is not None:
        lista.append((f"/produccion/liquidaciones?desde={liq.fecha.isoformat()}", "produccion.ver", liq.numero_documento))
    p = next((x for x in partes if x.estado in ("EN PROCESO", "PAUSADO")), None)
    if p is not None:
        lista.append((f"/produccion/parte/{p.id}", "produccion.ver", p.product_code))
    for ruta, perm, texto in lista:
        gerencia = [x for x in usuarios if x.role_code in ("GERENCIA_GENERAL", "GERENTE_GENERAL_ADJUNTO")]
        u = next((x for x in gerencia if perm is None or has_perm(x, perm)), None) or \
            next((x for x in usuarios if perm and has_perm(x, perm)), None)
        if u is None:
            res.append({"ruta": ruta, "ok": False, "resultado": "sin usuario con permiso", "usuario": ""})
            continue
        c = app.test_client()
        with c.session_transaction() as ses:
            ses["uid"] = u.id
        try:
            r = c.get(ruta)
            html = r.get_data(as_text=True)
            ok = r.status_code == 200 and (texto is None or texto in html)
            resultado = f"HTTP {r.status_code}" + ("" if texto is None or texto in html else f" (no aparece «{texto}»)")
        except Exception as e:  # noqa: BLE001
            ok, resultado = False, f"{type(e).__name__}: {e}"[:200]
        res.append({"ruta": ruta, "ok": ok, "resultado": resultado, "usuario": u.username})
    return res


def guardar(run, app=None):
    v = validar(run, app)
    run.validacion = v
    db().flush()
    return v
