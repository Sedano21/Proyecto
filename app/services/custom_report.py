"""Informe personalizado: «arme su informe» (obs. demo v0.7).

El usuario elige una fuente de datos que su rol puede consultar, las columnas, el periodo, un texto a buscar y,
opcionalmente, una columna para agrupar (cuenta y suma de las columnas numéricas). Se ve en pantalla y se descarga en
PDF o Excel. Solo lee datos; no modifica nada.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Alert, Incident, PickingTask, ProductionReport, ProductionRequest, PurchaseRequest, Route,
                      SalesOrder, SalesOrderLine, StockLot)
from .core import has_perm


def _v(x, *attrs):
    for a in attrs:
        x = getattr(x, a, None) if x is not None else None
    return x


def _monto(o):
    from .orders import order_amount
    return round(order_amount(o), 2)


# fuente -> (título, permisos (basta uno), consulta, campo fecha, columnas [(clave, título, función, numérica)])
FUENTES = {
    "ov": ("Órdenes de venta", ("ov.ver",), lambda: select(SalesOrder), SalesOrder.fecha_compromiso, [
        ("numero", "OV", lambda o: o.numero, False),
        ("cliente", "Cliente", lambda o: _v(o, "customer", "nombre"), False),
        ("grupo", "Grupo", lambda o: _v(o, "customer", "grupo"), False),
        ("canal", "Canal", lambda o: o.canal_precio, False),
        ("vendedor", "Vendedor", lambda o: o.vendedor_nombre, False),
        ("emision", "Emisión", lambda o: o.fecha_emision, False),
        ("compromiso", "Comprometida", lambda o: o.fecha_compromiso, False),
        ("estado", "Estado", lambda o: o.estado, False),
        ("cobertura", "Cobertura", lambda o: o.estado_stock, False),
        ("cob_pct", "Cobertura unid. %", lambda o: o.cobertura_unidades, True),
        ("monto", "Monto S/", _monto, True),
        ("urgente", "Urgente", lambda o: "Sí" if o.urgente else "No", False),
        ("distrito", "Distrito", lambda o: o.distrito, False)]),
    "ov_lineas": ("Líneas de OV (productos pedidos)", ("ov.ver",), lambda: select(SalesOrderLine).join(SalesOrder)
                  .where(SalesOrderLine.activa.is_(True)), SalesOrder.fecha_compromiso, [
        ("ov", "OV", lambda l: l.order.numero, False),
        ("cliente", "Cliente", lambda l: _v(l, "order", "customer", "nombre"), False),
        ("compromiso", "Comprometida", lambda l: l.order.fecha_compromiso, False),
        ("producto", "Producto", lambda l: l.product_code, False),
        ("descripcion", "Descripción", lambda l: _v(l, "product", "descripcion"), False),
        ("cantidad", "Cantidad", lambda l: l.cantidad, True),
        ("preparado", "Preparado", lambda l: l.preparado, True),
        ("despachado", "Despachado", lambda l: l.despachado, True),
        ("entregado", "Entregado", lambda l: l.entregado, True),
        ("precio", "Precio S/", lambda l: l.precio_unitario, True),
        ("importe", "Importe S/", lambda l: round((l.cantidad or 0) * (l.precio_unitario or 0), 2), True),
        ("estado", "Estado OV", lambda l: l.order.estado, False)]),
    "stock": ("Stock por lote", ("stock.ver",), lambda: select(StockLot).where(StockLot.cantidad > 0), StockLot.fecha_venc, [
        ("producto", "Producto", lambda x: x.product_code, False),
        ("descripcion", "Descripción", lambda x: _v(x, "product", "descripcion"), False),
        ("almacen", "Almacén", lambda x: x.warehouse_code, False),
        ("lote", "Lote", lambda x: x.lote, False),
        ("cantidad", "Cantidad", lambda x: x.cantidad, True),
        ("vence", "Vence", lambda x: x.fecha_venc, False),
        ("fabricacion", "Fabricación", lambda x: x.fecha_fab, False),
        ("estado", "Estado", lambda x: x.estado, False)]),
    "picking": ("Picking (tareas de preparación)", ("preparacion.registrar", "picking.asignar", "tareas.ejecutar"),
                lambda: select(PickingTask), PickingTask.fecha, [
        ("tarea", "Tarea", lambda t: t.id, False),
        ("ov", "OV", lambda t: _v(t, "order", "numero"), False),
        ("almacen", "Almacén", lambda t: t.warehouse_code, False),
        ("fecha", "Fecha", lambda t: t.fecha, False),
        ("estado", "Estado", lambda t: t.estado, False),
        ("personas", "N.° personas", lambda t: len(t.asignados or []), True),
        ("inicio", "Inicio", lambda t: t.inicio_ts, False),
        ("fin", "Fin", lambda t: t.fin_ts, False)]),
    "produccion": ("Solicitudes de producción", ("produccion.ver",), lambda: select(ProductionRequest),
                   ProductionRequest.fecha_requerida, [
        ("id", "#", lambda r: r.id, False),
        ("producto", "Producto", lambda r: r.product_code, False),
        ("cantidad", "Cantidad", lambda r: r.cantidad, True),
        ("requerida", "Fecha requerida", lambda r: r.fecha_requerida, False),
        ("programada", "Fecha programada", lambda r: r.fecha_programada, False),
        ("linea", "Línea", lambda r: r.line_code, False),
        ("estado", "Estado", lambda r: r.estado, False),
        ("ov", "OV", lambda r: _v(r, "order", "numero"), False)]),
    "partes": ("Partes de producción", ("produccion.ver",), lambda: select(ProductionReport), ProductionReport.fecha, [
        ("fecha", "Fecha", lambda r: r.fecha, False),
        ("linea", "Línea", lambda r: r.linea, False),
        ("producto", "Producto", lambda r: r.product_code, False),
        ("entrada", "Entrada kg", lambda r: r.peso_entrada_kg, True),
        ("granel", "Granel kg", lambda r: r.granel_kg, True),
        ("desmedro", "Desmedro kg", lambda r: r.desmedro_kg, True),
        ("rendimiento", "Rendimiento %", lambda r: r.rendimiento_pct, True),
        ("parada", "Parada min", lambda r: r.parada_min, True),
        ("motivo", "Motivo de parada", lambda r: r.motivo_parada, False)]),
    "compras": ("Compras nacionales", ("compras.ver",), lambda: select(PurchaseRequest), PurchaseRequest.fecha_necesidad, [
        ("id", "#", lambda r: r.id, False),
        ("producto", "Producto", lambda r: r.product_code, False),
        ("cantidad", "Cantidad", lambda r: r.cantidad, True),
        ("necesidad", "Fecha de necesidad", lambda r: r.fecha_necesidad, False),
        ("estado", "Estado", lambda r: r.estado, False),
        ("origen", "Origen", lambda r: r.origen, False),
        ("ov", "OV de origen", lambda r: _v(r, "order", "numero"), False),
        ("proveedor", "Proveedor", lambda r: r.proveedor, False),
        ("precio", "Precio", lambda r: r.precio, True),
        ("prevista", "Llegada prevista", lambda r: r.fecha_prevista, False)]),
    "rutas": ("Rutas de despacho", ("distribucion.ver",), lambda: select(Route), Route.fecha, [
        ("ruta", "Ruta", lambda r: r.id, False),
        ("fecha", "Fecha", lambda r: r.fecha, False),
        ("vehiculo", "Vehículo", lambda r: _v(r, "vehicle", "placa"), False),
        ("conductor", "Conductor", lambda r: _v(r, "driver", "nombre"), False),
        ("zona", "Zona", lambda r: r.zona, False),
        ("estado", "Estado", lambda r: r.estado, False),
        ("pedidos", "Pedidos", lambda r: len(r.stops), True),
        ("peso", "Peso kg", lambda r: r.peso_total, True),
        ("km", "Distancia km", lambda r: r.distancia_km, True),
        ("costo", "Costo transporte S/", lambda r: r.costo_transporte, True)]),
    "incidencias": ("Incidencias", ("distribucion.ver", "alertas.ver"), lambda: select(Incident), Incident.ts, [
        ("id", "#", lambda i: i.id, False),
        ("fecha", "Fecha", lambda i: i.ts, False),
        ("tipo", "Tipo", lambda i: i.tipo, False),
        ("grupo", "Grupo", lambda i: i.grupo, False),
        ("ov", "OV", lambda i: _v(i, "order", "numero"), False),
        ("estado", "Estado", lambda i: i.estado, False),
        ("cantidad", "Cantidad afectada", lambda i: i.cantidad_afectada, True),
        ("descripcion", "Descripción", lambda i: i.descripcion, False)]),
    "alertas": ("Alertas y tareas", ("alertas.ver",), lambda: select(Alert), Alert.creado_ts, [
        ("id", "#", lambda a: a.id, False),
        ("creada", "Creada", lambda a: a.creado_ts, False),
        ("tipo", "Tipo", lambda a: _v(a, "type", "nombre"), False),
        ("area", "Área", lambda a: a.area, False),
        ("urgencia", "Urgencia", lambda a: a.prioridad, False),
        ("estado", "Estado", lambda a: a.estado, False),
        ("titulo", "Qué ocurrió", lambda a: a.titulo, False),
        ("responsable", "Responsable", lambda a: _v(a, "asignado", "nombre") or a.asignado_rol, False),
        ("cerrada", "Cerrada", lambda a: a.cerrado_ts, False),
        ("horas", "Horas hasta el cierre", lambda a: round((a.cerrado_ts - a.creado_ts).total_seconds() / 3600, 1)
         if a.cerrado_ts and a.creado_ts else None, True)]),
}


def sources_for(user):
    return {k: v[0] for k, v in FUENTES.items() if has_perm(user, "vista.total") or any(has_perm(user, p) for p in v[1])}


def columns(fuente):
    return [(c, t, num) for c, t, _, num in FUENTES[fuente][4]]


def _fmt(v):
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float):
        return round(v, 2)
    return v


def run(user, fuente, cols=None, desde=None, hasta=None, texto="", agrupar="", limite=5000):
    """Devuelve {titulo, columnas, filas, total, notas}. Si 'agrupar' es una columna, agrupa con cuenta y sumas."""
    from .alerts import can_see
    if fuente not in sources_for(user):
        raise PermissionError("Fuente no autorizada para su rol.")
    titulo, _, consulta, campo, defs = FUENTES[fuente]
    defs_map = {c: (t, fn, num) for c, t, fn, num in defs}
    cols = [c for c in (cols or []) if c in defs_map] or [c for c, *_ in defs]
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=90)
    q = consulta()
    es_ts = str(campo.type).upper().startswith("DATETIME")
    q = q.where(campo >= (datetime.combine(desde, datetime.min.time()) if es_ts else desde),
                campo <= (datetime.combine(hasta, datetime.max.time()) if es_ts else hasta))
    filas = []
    texto = (texto or "").strip().lower()
    for x in db().execute(q).scalars():
        if fuente == "alertas" and not can_see(user, x):
            continue
        vals = [defs_map[c][1](x) for c in cols]
        if texto and texto not in " ".join(str(v) for v in vals if v is not None).lower():
            continue
        filas.append([_fmt(v) for v in vals])
        if len(filas) >= limite:
            break
    cab = [defs_map[c][0] for c in cols]
    notas = [f"Fuente: {titulo}. Periodo ({FUENTES[fuente][3].key.replace('_', ' ')}): {desde:%d/%m/%Y} – {hasta:%d/%m/%Y}."
             + (f" Filtro: «{texto}»." if texto else "")]
    if agrupar and agrupar in cols:
        i = cols.index(agrupar)
        nums = [j for j, c in enumerate(cols) if defs_map[c][2] and j != i]
        grupos = {}
        for f in filas:
            g = grupos.setdefault(f[i], [0] + [0.0] * len(nums))
            g[0] += 1
            for k, j in enumerate(nums):
                g[k + 1] += float(f[j] or 0)
        cab = [defs_map[agrupar][0], "Registros"] + [f"Suma de {defs_map[cols[j]][0]}" for j in nums]
        filas = [[k, v[0]] + [round(s, 2) for s in v[1:]] for k, v in sorted(grupos.items(), key=lambda kv: -kv[1][0])]
        notas.append(f"Agrupado por {defs_map[agrupar][0]}.")
    return {"titulo": titulo, "columnas": cab, "filas": filas, "total": len(filas), "notas": notas,
            "desde": desde, "hasta": hasta, "cols": cols}
