"""Informe personalizado: «arme su informe» (obs. demo v0.7).

El usuario elige una fuente de datos que su rol puede consultar, las columnas, el periodo, un texto a buscar y,
opcionalmente, una columna para agrupar (cuenta y suma de las columnas numéricas). Se ve en pantalla y se descarga en
PDF o Excel. Solo lee datos; no modifica nada.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Alert, Attendance, Certificate, CustomerAction, CustomerInvoice, CustomerPayment, ImportShipment,
                      Incident, Liquidation, Opportunity, PickingTask, ProductionReport, ProductionRequest, PurchaseRequest,
                      QualityRecord, Quote, RepackRequest, Route, SalesOrder, SalesOrderLine, StockLot, Transfer)
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
        ("maquina", "Máquina", lambda r: r.maquina or r.linea, False),
        ("turno", "Turno", lambda r: r.turno, False),
        ("of", "OF", lambda r: r.of, False),
        ("producto", "Producto", lambda r: r.product_code, False),
        ("cliente", "Cliente", lambda r: r.cliente, False),
        ("estado", "Estado", lambda r: r.estado, False),
        ("entrada", "Entrada kg", lambda r: r.peso_entrada_kg, True),
        ("granel", "Producido kg", lambda r: r.granel_kg, True),
        ("unidades", "Unidades", lambda r: r.unidades, True),
        ("desmedro", "Desmedro kg", lambda r: r.desmedro_kg, True),
        ("rendimiento", "Rendimiento %", lambda r: r.rendimiento_pct, True),
        ("desmedro_pct", "Desmedro %", lambda r: r.desmedro_pct, True),
        ("horas", "Horas", lambda r: r.horas, True),
        ("horas_ef", "Horas efectivas", lambda r: (r.indicadores or {}).get("horas_efectivas"), True),
        ("operarios", "Operarios", lambda r: r.operarios, True),
        ("kg_h", "kg/h", lambda r: r.ratio_kg_hora, True),
        ("oee", "OEE %", lambda r: (r.indicadores or {}).get("oee"), True),
        ("disponibilidad", "Disponibilidad %", lambda r: (r.indicadores or {}).get("disponibilidad"), True),
        ("rend_oee", "Rendimiento OEE %", lambda r: (r.indicadores or {}).get("rendimiento_oee"), True),
        ("calidad", "Calidad %", lambda r: (r.indicadores or {}).get("calidad"), True),
        ("defectos", "Defectuosos", lambda r: sum((r.defectos or {}).values()), True),
        ("sobrepeso", "kg de más (peso)", lambda r: (r.indicadores or {}).get("kg_sobrepeso"), True),
        ("parada", "Parada min", lambda r: r.parada_min, True),
        ("motivo", "Motivo de parada", lambda r: r.motivo_parada, False)]),
    "liquidaciones": ("Liquidaciones de producción", ("produccion.ver", "produccion.recibir_pt"), lambda: select(Liquidation),
                      Liquidation.fecha, [
        ("documento", "Documento (OF)", lambda l: l.numero_documento, False),
        ("fecha", "Fecha", lambda l: l.fecha, False),
        ("producto", "Producto", lambda l: l.product_code, False),
        ("lote", "Lote", lambda l: l.lote, False),
        ("planificada", "Planificada", lambda l: l.cantidad_planificada, True),
        ("completada", "Completada", lambda l: l.cantidad_completada, True),
        ("recibida", "Recibida", lambda l: l.cantidad_recibida, True),
        ("diferencia", "Diferencia", lambda l: l.diferencia, True),
        ("horas", "Horas", lambda l: l.horas, True),
        ("operarios", "Operarios", lambda l: l.operarios, True),
        ("estado", "Estado", lambda l: l.estado, False),
        ("origen", "Origen", lambda l: l.origen, False)]),
    "asistencia": ("Asistencia del personal de Producción", ("produccion.ver",), lambda: select(Attendance), Attendance.fecha, [
        ("fecha", "Fecha", lambda a: a.fecha, False),
        ("colaborador", "Colaborador", lambda a: _v(a, "worker", "nombre"), False),
        ("linea", "Línea", lambda a: _v(a, "worker", "linea"), False),
        ("estado", "Estado", lambda a: a.estado, False),
        ("registros", "Registros", lambda a: 1, True)]),
    "certificados": ("Certificados de calidad", ("calidad.ver",), lambda: select(Certificate), Certificate.generado_ts, [
        ("numero", "Número", lambda c: c.numero, False),
        ("producto", "Producto", lambda c: c.product_code, False),
        ("ov", "OV", lambda c: _v(c, "order", "numero"), False),
        ("estado", "Estado", lambda c: c.estado, False),
        ("generado", "Generado", lambda c: c.generado_ts, False),
        ("revisado", "Revisado", lambda c: c.revisado_ts, False)]),
    "registros_calidad": ("Registros de Calidad (formatos)", ("calidad.ver",), lambda: select(QualityRecord), QualityRecord.fecha, [
        ("fecha", "Fecha", lambda q: q.fecha, False),
        ("formato", "Formato", lambda q: q.formato, False),
        ("producto", "Producto", lambda q: q.product_code, False),
        ("lote", "Lote", lambda q: q.lote, False),
        ("resultado", "Resultado", lambda q: q.resultado, False),
        ("estado", "Estado", lambda q: q.estado, False),
        ("registros", "Registros", lambda q: 1, True)]),
    "reempaques": ("Reempaques y fumigaciones", ("calidad.ver", "reempaque.ejecutar", "stock.ver"), lambda: select(RepackRequest),
                   RepackRequest.ts, [
        ("id", "#", lambda r: r.id, False),
        ("tipo", "Tipo", lambda r: r.tipo, False),
        ("destino", "Producto destino", lambda r: r.producto_destino, False),
        ("cantidad", "Cantidad", lambda r: r.cantidad, True),
        ("estado", "Estado", lambda r: r.estado, False),
        ("motivo", "Motivo", lambda r: r.motivo, False),
        ("fecha", "Solicitado", lambda r: r.ts, False)]),
    "traslados": ("Traslados entre almacenes", ("stock.ver", "traslado.autorizar"), lambda: select(Transfer), Transfer.ts, [
        ("id", "#", lambda x: x.id, False),
        ("producto", "Producto", lambda x: _v(x, "lot", "product_code"), False),
        ("destino", "Destino", lambda x: x.destino_code, False),
        ("cantidad", "Cantidad", lambda x: x.cantidad, True),
        ("recibida", "Recibida", lambda x: x.cantidad_recibida, True),
        ("estado", "Estado", lambda x: x.estado, False),
        ("fecha", "Solicitado", lambda x: x.ts, False)]),
    "importaciones": ("Importaciones", ("importaciones.ver", "importaciones.gestionar", "compras.ver"), lambda: select(ImportShipment),
                      ImportShipment.fecha_llegada_estimada, [
        ("referencia", "Referencia", lambda x: x.referencia, False),
        ("proveedor", "Proveedor", lambda x: x.proveedor, False),
        ("producto", "Producto", lambda x: x.product_code, False),
        ("cantidad", "Cantidad", lambda x: x.cantidad, True),
        ("recibida", "Recibida", lambda x: x.cantidad_recibida, True),
        ("llegada", "Llegada estimada", lambda x: x.fecha_llegada_estimada, False),
        ("estado", "Estado", lambda x: x.estado, False)]),
    "facturas": ("Facturas y notas de crédito", ("finanzas.ver",), lambda: select(CustomerInvoice), CustomerInvoice.fecha, [
        ("numero", "Número", lambda i: i.numero, False),
        ("tipo", "Tipo", lambda i: i.tipo, False),
        ("cliente", "Cliente", lambda i: _v(i, "customer", "nombre"), False),
        ("vendedor", "Vendedor", lambda i: _v(i, "customer", "vendedor", "nombre"), False),
        ("ov", "OV", lambda i: _v(i, "order", "numero"), False),
        ("fecha", "Emisión", lambda i: i.fecha, False),
        ("vence", "Vencimiento", lambda i: i.vencimiento, False),
        ("monto", "Monto S/", lambda i: i.monto, True),
        ("saldo", "Saldo S/", lambda i: i.saldo, True),
        ("estado", "Estado", lambda i: i.estado, False)]),
    "pagos": ("Pagos de clientes", ("finanzas.ver",), lambda: select(CustomerPayment), CustomerPayment.fecha, [
        ("fecha", "Fecha", lambda p: p.fecha, False),
        ("cliente", "Cliente", lambda p: _v(p, "customer", "nombre"), False),
        ("factura", "Factura", lambda p: _v(p, "invoice", "numero"), False),
        ("monto", "Monto S/", lambda p: p.monto, True),
        ("medio", "Medio", lambda p: p.medio, False),
        ("estado", "Estado", lambda p: p.estado, False),
        ("registro", "Registró", lambda p: _v(p, "user", "nombre"), False)]),
    "acciones": ("Acciones con clientes (oportunidades)", ("oportunidades.registrar", "oportunidades.ver_todas"),
                 lambda: select(CustomerAction), CustomerAction.fecha, [
        ("fecha", "Fecha", lambda a: a.fecha, False),
        ("tipo", "Tipo", lambda a: a.tipo, False),
        ("cliente", "Cliente", lambda a: _v(a, "customer", "nombre"), False),
        ("vendedor", "Vendedor", lambda a: _v(a, "user", "nombre"), False),
        ("oportunidad", "Oportunidad", lambda a: _v(a, "opportunity", "titulo"), False),
        ("gasto", "Gasto S/", lambda a: a.gasto, True),
        ("resultado", "Resultado", lambda a: a.resultado, False)]),
    "oportunidades": ("Oportunidades", ("oportunidades.registrar", "oportunidades.ver_todas"), lambda: select(Opportunity),
                      Opportunity.creado_ts, [
        ("titulo", "Oportunidad", lambda o: o.titulo, False),
        ("cliente", "Cliente", lambda o: _v(o, "customer", "nombre"), False),
        ("vendedor", "Vendedor", lambda o: _v(o, "vendedor", "nombre"), False),
        ("tipo", "Tipo", lambda o: o.tipo, False),
        ("estado", "Estado", lambda o: o.estado, False),
        ("proyeccion", "Proyección S/ mes", lambda o: o.proyeccion_mensual, True),
        ("creada", "Creada", lambda o: o.creado_ts, False)]),
    "cotizaciones": ("Cotizaciones", ("oportunidades.registrar", "oportunidades.ver_todas"), lambda: select(Quote), Quote.fecha, [
        ("numero", "Número", lambda q: q.numero, False),
        ("cliente", "Cliente", lambda q: _v(q, "customer", "nombre"), False),
        ("vendedor", "Vendedor", lambda q: _v(q, "user", "nombre"), False),
        ("fecha", "Fecha", lambda q: q.fecha, False),
        ("total", "Total S/", lambda q: q.total, True),
        ("estado", "Estado", lambda q: q.estado, False)]),
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


AREA_FUENTE = {"ov": "Comercial", "ov_lineas": "Comercial", "acciones": "Comercial", "oportunidades": "Comercial",
               "cotizaciones": "Comercial", "facturas": "Finanzas", "pagos": "Finanzas", "stock": "Almacén",
               "picking": "Almacén", "traslados": "Almacén", "produccion": "Producción", "partes": "Producción",
               "liquidaciones": "Producción", "asistencia": "Producción", "certificados": "Calidad",
               "registros_calidad": "Calidad", "reempaques": "Calidad", "compras": "Compras", "importaciones": "Compras",
               "rutas": "Distribución", "incidencias": "Distribución", "alertas": "General"}


def sources_by_area(user):
    out = {}
    for k, t in sources_for(user).items():
        out.setdefault(AREA_FUENTE.get(k, "General"), []).append((k, t))
    return out


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
        # los porcentajes se promedian (sin contar vacíos); el resto se suma
        pct = {j: "%" in defs_map[cols[j]][0] for j in nums}
        grupos = {}
        for f in filas:
            g = grupos.setdefault(f[i], [0] + [[0.0, 0] for _ in nums])
            g[0] += 1
            for k, j in enumerate(nums):
                if f[j] not in (None, ""):
                    g[k + 1][0] += float(f[j])
                    g[k + 1][1] += 1
        cab = [defs_map[agrupar][0], "Registros"] + [("Promedio de " if pct[j] else "Suma de ") + defs_map[cols[j]][0] for j in nums]
        filas = [[k, v[0]] + [round(s / n, 2) if pct[nums[q]] and n else (None if pct[nums[q]] else round(s, 2))
                              for q, (s, n) in enumerate(v[1:])]
                 for k, v in sorted(grupos.items(), key=lambda kv: -kv[1][0])]
        notas.append(f"Agrupado por {defs_map[agrupar][0]}.")
    res = {"titulo": titulo, "columnas": cab, "filas": filas, "total": len(filas), "notas": notas,
           "desde": desde, "hasta": hasta, "cols": cols, "agrupado": bool(agrupar and agrupar in cols)}
    res["kpis"] = _kpis(res)
    res["recomendaciones"] = _recommendations(res)
    return res


def _numeric_cols(r):
    out = []
    for j, c in enumerate(r["columnas"]):
        vals = [f[j] for f in r["filas"] if f[j] not in (None, "")]
        if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            out.append(j)
    return out


def _kpis(r):
    k = [("Registros", r["total"] if not r["agrupado"] else sum(f[1] for f in r["filas"]))]
    for j in _numeric_cols(r)[:4]:
        if r["agrupado"] and j == 1:
            continue
        col = r["columnas"][j]
        vals = [f[j] for f in r["filas"] if isinstance(f[j], (int, float))]
        es_pct = "%" in col
        k.append((("Promedio de " if es_pct else "Total de ") + col.replace("Suma de ", "").replace("Promedio de ", "").lower(),
                  round(sum(vals) / len(vals), 1) if es_pct and vals else round(sum(vals), 2)))
    return k


def chart(r, tipo="barras", medida=None):
    """Gráfico del informe: por grupo (si está agrupado) o por la primera columna de texto; medida = índice de columna."""
    from . import charts
    nums = _numeric_cols(r)
    if not r["filas"] or not nums:
        return None
    j = medida if medida in nums else (nums[1] if r["agrupado"] and len(nums) > 1 else nums[0])
    from collections import defaultdict
    acc = defaultdict(float)
    for f in r["filas"]:
        acc[str(f[0])] += float(f[j] or 0)
    items = sorted(acc.items(), key=lambda x: -x[1])[:15]
    titulo = f"{r['columnas'][j]} por {r['columnas'][0].lower()}"
    if tipo == "columnas":
        return charts.columns([k for k, _ in items], [(r["columnas"][j], [v for _, v in items])], title=titulo)
    if tipo == "lineas":
        return charts.line([(r["columnas"][j], sorted(acc.items()))], title=titulo)
    return charts.bars(items, title=titulo)


def _recommendations(r):
    """Reglas explícitas sobre el informe (sugerencias para revisión, no decisiones)."""
    out = []
    nums = _numeric_cols(r)
    if not r["filas"]:
        return ["Sin registros en el periodo: revise el filtro o que los datos se estén registrando."]
    if nums:
        j = nums[1] if r["agrupado"] and len(nums) > 1 else nums[0]
        col = r["columnas"][j]
        from collections import defaultdict
        acc = defaultdict(float)
        for f in r["filas"]:
            acc[str(f[0])] += float(f[j] or 0)
        total = sum(acc.values())
        if total and len(acc) > 1:
            top, v = max(acc.items(), key=lambda x: x[1])
            low, w = min(acc.items(), key=lambda x: x[1])
            if "%" not in col and v / total >= 0.5:
                out.append(f"{top} concentra el {100 * v / total:.0f}% de {col.lower()}: dependencia alta.")
            if "%" in col:
                out.append(f"Mayor {col.lower()}: {top} ({v:g}); menor: {low} ({w:g}). Revisar la causa de la diferencia.")
            else:
                out.append(f"Mayor {col.lower()}: {top}; menor: {low}.")
    vacias = [(c, sum(1 for f in r["filas"] if f[j] in (None, ""))) for j, c in enumerate(r["columnas"])]
    vacias = [(c, n) for c, n in vacias if n and n >= max(1, len(r["filas"]) // 5)]
    for c, n in vacias[:2]:
        out.append(f"{n} registro(s) sin «{c}»: completar el dato mejora el análisis.")
    return out
