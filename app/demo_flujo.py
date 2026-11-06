"""V23 (06-nov-2026): flujo completo FICTICIO para revisar todos los perfiles con datos (no en cero).

Se ejecuta sobre la demostración (python -m app.cli demo-dia lo llama al final). Todo es inventado (clientes «DEMO»,
OV «DF-», facturas «F-DEMO-»). Para esta revisión:
- precios mínimos para todos los productos vendibles en todos los canales de la demostración (la OV no se detiene por
  «falta precio mínimo»; en la marcha real se usan los precios reales);
- stock ficticio suficiente para que las OV no queden bloqueadas por faltante (salvo los casos que se dejan a propósito);
- historial de ~75 días de OV en todos los desenlaces: a tiempo y completas, tarde, incompletas (parciales), anuladas y
  con fecha renegociada; con sus facturas (pagadas, por vencer y vencidas) y su historial de ventas;
- OV del mes en curso en cada estado del flujo (registrada, evaluada, en preparación, preparada, programada, en ruta,
  despachada, entregada) para que cada perfil tenga trabajo visible;
- producción: solicitudes en cada estado, partes diarios por línea (60 días) y liquidaciones recibidas;
- proyección de demanda (meses anteriores, mes en curso y siguiente) por producto, metas del mes por ejecutivo,
  importaciones y compras en curso, y alertas de Calidad, Compras, Importaciones y avisos de SAP para la bandeja de
  gerencia.

El historial no pasa por cada pantalla (picking, guía, salida): se registra directamente con su resultado para que los
indicadores tengan base. Lo que ocurre hoy sí se puede operar desde las pantallas.
"""
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from .db import db
from .models import (AuditLog, Customer, CustomerInvoice, DemandForecast, ImportShipment, Liquidation, PriceItem, Product,
                     ProductionReport, ProductionRequest, PurchaseRequest, SalesHistory, SalesOrder, SalesOrderLine,
                     SalesTarget, StockLot, User)

MARCA = "DEMO-FLUJO"
PRECIO_REF = {"PT-901": 4.2, "PT-902": 36.0, "PT-903": 4.0, "PT-904": 40.0, "PT-905": 3.6, "PT-906": 3.9,
              "MP-901": 6.5, "MP-902": 7.2, "MP-903": 8.0, "GR-901": 9.5}


def ya_cargado():
    return db().execute(select(SalesOrder).where(SalesOrder.numero.like("DF-%"))).first() is not None


def _u(username):
    return db().execute(select(User).where(User.username == username)).scalars().first()


def _habiles(desde, hasta):
    d = desde
    while d <= hasta:
        if d.weekday() < 6:  # lunes a sábado
            yield d
        d += timedelta(days=1)


def _dt(d, h, m=0):
    return datetime.combine(d, time(h % 24, m))


def _precios(productos, canales):
    """Precio mínimo ficticio para cada producto vendible en cada canal (si falta)."""
    s = db()
    n = 0
    for p in productos:
        base = PRECIO_REF.get(p.code, 10.0)
        for i, can in enumerate(canales):
            it = s.execute(select(PriceItem).where(PriceItem.lista == "GENERAL", PriceItem.canal == can,
                                                   PriceItem.product_code == p.code, PriceItem.vigente.is_(True))).scalars().first()
            if it is None:
                s.add(PriceItem(lista="GENERAL", canal=can, product_code=p.code, descripcion=p.descripcion,
                                precio=round(base * (1 + 0.02 * (i % 4)), 2), vigente=True))
                n += 1
            elif not it.precio:
                it.precio = round(base, 2)
                n += 1
    s.flush()
    return n


def seed_flow(upload_dir=None, hoy=None):
    """Crea el flujo ficticio. Devuelve un resumen (o None si ya existía)."""
    from .services.orders import condicion_vendible
    from .services.prices import canales, channel_of, price_for
    s = db()
    hoy = hoy or date.today()
    if ya_cargado():
        return None
    rnd = random.Random(2026)
    res = {}
    vend = [u for u in (_u("vendedor1"), _u("vendedor2")) if u]
    coord = _u("coord.ventas")
    clientes = [c for c in s.execute(select(Customer).order_by(Customer.id)).scalars() if not c.es_prospecto]
    for i, c in enumerate(clientes):
        c.vendedor_id = c.vendedor_id or vend[i % len(vend)].id
        c.credito_dias = c.credito_dias or [30, 15, 45, 30, 0, 30, 15, 60][i % 8]
    productos = list(s.execute(select(Product).where(condicion_vendible(True)).order_by(Product.code)).scalars())
    res["precios_agregados"] = _precios(productos, sorted(set(canales()) | {channel_of(c) for c in clientes} - {""}))

    # ---------------------------------------------------------------- stock ficticio suficiente
    for p in productos:
        alm = "ALM-001" if p.code.startswith("PT") else "EXT-002"
        q = 6000 if p.code.startswith("PT") else 40000
        s.add(StockLot(product_code=p.code, warehouse_code=alm, lote=f"DF{hoy:%y%m}-{p.code[-3:]}", cantidad=q,
                       fecha_fab=hoy - timedelta(days=20), fecha_venc=hoy + timedelta(days=330), estado="DISPONIBLE",
                       observacion=f"{MARCA}: stock ficticio para la revisión"))
    s.flush()

    def precio(code, c):
        base, _ = price_for(s.get(Product, code), c)
        return base or PRECIO_REF.get(code, 10.0)

    pts = [p for p in productos if p.code.startswith("PT")]
    graneles = [p for p in productos if not p.code.startswith("PT")]
    numero = [0]

    def nueva_ov(c, fe, fc, estado, lineas_q, precio_factor=None):
        numero[0] += 1
        o = SalesOrder(numero=f"DF-{numero[0]:05d}", customer_id=c.id, vendedor_id=c.vendedor_id, fecha_emision=fe,
                       fecha_compromiso=fc, estado=estado, estado_stock="COMPLETA", cobertura_unidades=100.0,
                       cobertura_lineas=100.0, canal_precio=channel_of(c), direccion=c.direccion or "",
                       distrito=c.distrito or "", provincia=c.provincia or "LIMA", creado_por=coord.id if coord else None,
                       creado_ts=_dt(fe, 9 + rnd.randint(0, 2), rnd.choice((0, 15, 30, 45))),
                       evaluado_ts=_dt(fe, 11), comentarios=f"{MARCA}: OV ficticia")
        s.add(o)
        s.flush()
        for code, q in lineas_q:
            base = precio(code, c)
            f = precio_factor if precio_factor is not None else rnd.choice((1.0, 1.02, 1.05, 1.08, 0.98))
            s.add(SalesOrderLine(order_id=o.id, product_code=code, cantidad=q, precio_unitario=round(base * f, 2),
                                 precio_minimo=base, precio_origen="LISTA"))
        s.flush()
        s.refresh(o)
        return o

    def lineas_al_azar():
        n = rnd.choice((1, 1, 2, 2, 3))
        out = []
        for p in rnd.sample(pts, n):
            out.append((p.code, rnd.choice((20, 40, 60, 80, 120, 200)) if (p.peso_kg or 1) < 1 else rnd.choice((5, 10, 20, 40))))
        if rnd.random() < 0.25:
            g = rnd.choice(graneles)
            out.append((g.code, rnd.choice((250, 500, 1000, 1500))))
        return out

    # cliente nuevo del mes (para «venta a clientes nuevos») y productos que cada cliente aún no compraba (SKU nuevos)
    nuevo = s.execute(select(Customer).where(Customer.ruc == "20000000099")).scalars().first()
    if nuevo is None:
        nuevo = Customer(ruc="20000000099", nombre="CLIENTE DEMO NUEVO DEL MES S.A.C.", grupo="MAYORISTA",
                         direccion="AV. NUEVA DEMO 99", distrito="LOS OLIVOS", provincia="LIMA", credito_dias=15,
                         vendedor_id=vend[-1].id)
        s.add(nuevo)
        s.flush()
    no_compraba = {c.id: pts[i % len(pts)].code for i, c in enumerate(clientes)}
    dejaron = {c.id for c in clientes[-2:]}  # dos clientes que dejaron de comprar hace más de un mes (recompra)
    for o in s.execute(select(SalesOrder).where(SalesOrder.customer_id.in_(dejaron),
                                                SalesOrder.fecha_emision >= hoy - timedelta(days=40))).scalars():
        o.customer_id = clientes[0].id  # sus OV recientes del día de operación pasan a otro cliente

    # ---------------------------------------------------------------- historial (~75 días) con todos los desenlaces
    hist = {"ok": 0, "tarde": 0, "parcial": 0, "anulada": 0, "renegociada": 0}
    facturas = 0
    for d in _habiles(hoy - timedelta(days=75), hoy - timedelta(days=1)):
        for _ in range(rnd.randint(3, 6)):
            c = rnd.choice(clientes)
            if c.id in dejaron and d > hoy - timedelta(days=40):
                c = clientes[0]
            fe = d - timedelta(days=rnd.choice((1, 1, 2, 2, 3, 4)))
            r = rnd.random()
            if r < 0.03:
                o = nueva_ov(c, fe, d, "CANCELADA", lineas_al_azar())
                o.cancelacion_motivo = "Cliente anuló el pedido (ficticio)"
                hist["anulada"] += 1
                continue
            o = nueva_ov(c, fe, d, "ENTREGADA", [x for x in lineas_al_azar() if x[0] != no_compraba[c.id]]
                         or [(rnd.choice([p for p in pts if p.code != no_compraba[c.id]]).code, 20)])
            salida = d
            parcial = False
            if r < 0.11:
                salida = d + timedelta(days=rnd.choice((1, 1, 2)))
                hist["tarde"] += 1
            elif r < 0.19:
                parcial = True
                hist["parcial"] += 1
            else:
                hist["ok"] += 1
            if salida > hoy - timedelta(days=1):
                salida = hoy - timedelta(days=1)
            for i, l in enumerate(o.lines):
                q = l.cantidad
                if parcial and i == 0:
                    q = round(l.cantidad * rnd.choice((0.6, 0.75, 0.9)))
                l.preparado = l.despachado = l.entregado = q
            o.estado = "ENTREGA_PARCIAL" if parcial else "ENTREGADA"
            o.prep_inicio = _dt(salida - timedelta(days=1), 15)
            o.prep_fin = _dt(salida - timedelta(days=1), 17)
            o.salida_ts = _dt(salida, rnd.choice((6, 7, 8, 9)), rnd.choice((0, 20, 40)))
            o.entrega_ts = o.salida_ts + timedelta(hours=rnd.choice((2, 3, 4, 5)))
            if rnd.random() < 0.09:
                s.add(AuditLog(user_id=coord.id if coord else None, accion="OV_CAMBIO_FECHA_SOLICITADO", entidad="SalesOrder",
                               entidad_id=o.numero, ts=_dt(fe, 16),
                               detalle={"nueva_fecha": d.isoformat(), "motivo": "Cliente reprograma la recepción (ficticio)"}))
                hist["renegociada"] += 1
            monto = round(sum(l.entregado * (l.precio_unitario or 0) for l in o.lines), 2)
            venc = o.salida_ts.date() + timedelta(days=c.credito_dias or 0)
            pagada = venc < hoy - timedelta(days=5) and rnd.random() < 0.8 or venc < hoy - timedelta(days=40)
            s.add(CustomerInvoice(customer_id=c.id, order_id=o.id, tipo="FACTURA", numero=f"F-DEMO-{o.numero[3:]}",
                                  fecha=o.salida_ts.date(), vencimiento=venc, monto=monto, saldo=0.0 if pagada else monto,
                                  estado="PAGADA" if pagada else "PENDIENTE", origen="DEMO", observacion=MARCA))
            facturas += 1
            for l in o.lines:
                s.add(SalesHistory(product_code=l.product_code, fecha=o.salida_ts.date(), cantidad=l.entregado,
                                   documento=o.numero, origen=MARCA))
    s.flush()
    res["historial"] = hist
    res["facturas"] = facturas

    # ---------------------------------------------------------------- OV del mes en curso en cada estado del flujo
    manana = hoy + timedelta(days=1)
    while manana.weekday() == 6:
        manana += timedelta(days=1)
    estados_hoy = [("ENTREGADA", hoy), ("ENTREGADA", hoy), ("DESPACHADA", hoy), ("EN_RUTA", hoy), ("EN_RUTA", hoy),
                   ("PROGRAMADA", hoy), ("PREPARADA", manana), ("PREPARADA", manana), ("EN_PREPARACION", manana),
                   ("EN_PREPARACION", manana), ("EVALUADA", manana), ("EVALUADA", manana + timedelta(days=1)),
                   ("REGISTRADA", manana + timedelta(days=2)), ("EVALUADA", manana + timedelta(days=3)),
                   ("EVALUADA", manana + timedelta(days=5)), ("REGISTRADA", manana + timedelta(days=7))]
    actuales = []
    activos = [c for c in clientes if c.id not in dejaron]
    for i, (est, fc) in enumerate(estados_hoy):
        c = nuevo if i in (1, 9) else activos[i % len(activos)]
        lq = lineas_al_azar()
        if i % 3 == 0 and c.id in no_compraba:  # el cliente compra por primera vez este producto
            lq = [(no_compraba[c.id], 30)] + [x for x in lq if x[0] != no_compraba[c.id]]
        o = nueva_ov(c, hoy - timedelta(days=1) if fc == hoy else hoy, fc, est, lq, 1.04)
        if i in (4, 7):
            s.add(AuditLog(user_id=coord.id if coord else None, accion="OV_CAMBIO_FECHA_SOLICITADO", entidad="SalesOrder",
                           entidad_id=o.numero, ts=_dt(hoy, 9),
                           detalle={"nueva_fecha": fc.isoformat(), "motivo": "Cliente pide otra fecha (ficticio)"}))
        if est in ("PREPARADA", "PROGRAMADA", "EN_RUTA", "DESPACHADA", "ENTREGADA"):
            for l in o.lines:
                l.preparado = l.cantidad
            o.prep_inicio, o.prep_fin = _dt(hoy - timedelta(days=1), 15), _dt(hoy - timedelta(days=1), 17)
        if est == "EN_PREPARACION":
            o.prep_inicio = _dt(hoy, 8)
        if est in ("EN_RUTA", "DESPACHADA", "ENTREGADA"):
            for l in o.lines:
                l.despachado = l.cantidad
            o.salida_ts = _dt(hoy, 7, 30)
        if est == "ENTREGADA":
            for l in o.lines:
                l.entregado = l.cantidad
            o.entrega_ts = _dt(hoy, 10, 15)
        if est == "REGISTRADA":
            o.estado_stock = "SIN_EVALUAR"
            o.evaluado_ts = None
        actuales.append(o)
    # casos que se dejan a propósito para revisar las decisiones: una OV con faltante y una con precio bajo el mínimo
    c = clientes[0]
    o = nueva_ov(c, hoy, manana + timedelta(days=2), "EVALUADA", [(pts[0].code, 9000)], 1.04)
    o.estado_stock, o.cobertura_unidades, o.cobertura_lineas = "INCOMPLETA", 66.0, 0.0
    o.motivo_detencion = "Faltante de stock: pendiente de decisión"
    actuales.append(o)
    c = clientes[1 % len(clientes)]
    o = nueva_ov(c, hoy, manana + timedelta(days=2), "BLOQUEADA", [(pts[1 % len(pts)].code, 10)], 0.85)
    o.retenida_precio = True
    o.motivo_detencion = "Precio bajo el mínimo: pendiente de aprobación"
    actuales.append(o)
    s.flush()
    res["ov_mes_en_curso"] = len(actuales)

    # ---------------------------------------------------------------- metas del mes
    mes = f"{hoy:%Y-%m}"
    venta_prom = sum(l.cantidad * (l.precio_unitario or 0) for o in s.execute(select(SalesOrder).where(
        SalesOrder.numero.like("DF-%"), SalesOrder.fecha_compromiso >= hoy - timedelta(days=30),
        SalesOrder.fecha_compromiso < hoy)).scalars() for l in o.lines)
    if not s.execute(select(SalesTarget).where(SalesTarget.mes == mes)).first():
        s.add(SalesTarget(mes=mes, alcance="GENERAL", clave="", soles=round(venta_prom * 1.1, -2), nuevos_clientes=2, nuevos_sku=4))
        for v in vend:
            s.add(SalesTarget(mes=mes, alcance="VENDEDOR", clave=str(v.id), soles=round(venta_prom * 1.1 / len(vend), -2)))

    # ---------------------------------------------------------------- proyección de demanda (meses -3..+1)
    def mes_rel(k):
        y, m = hoy.year, hoy.month + k
        while m < 1:
            y, m = y - 1, m + 12
        while m > 12:
            y, m = y + 1, m - 12
        return f"{y:04d}-{m:02d}"
    vendido = {}
    for p in productos:
        q = sum(l.cantidad for l in s.execute(select(SalesOrderLine).join(SalesOrder).where(
            SalesOrder.numero.like("DF-%"), SalesOrderLine.product_code == p.code,
            SalesOrder.fecha_compromiso >= hoy - timedelta(days=30))).scalars())
        vendido[p.code] = q
    n_proy = 0
    # el mes siguiente se proyecta muy por encima (campaña) para revisar el caso de horas extra, tercero y compras
    for k, factor in ((-2, 1.0), (-1, 1.05), (0, 1.25), (1, 12.0)):
        m = mes_rel(k)
        if s.execute(select(DemandForecast).where(DemandForecast.mes == m)).first():
            continue
        for p in productos:
            base = vendido.get(p.code) or (300 if p.code.startswith("PT") else 2000)
            s.add(DemandForecast(mes=m, product_code=p.code, cantidad=round(base * factor * rnd.uniform(0.9, 1.15)),
                                 observacion=f"{MARCA}: proyección ficticia", user_id=coord.id if coord else None))
            n_proy += 1
    res["proyeccion"] = n_proy

    # ---------------------------------------------------------------- producción
    lineas_env = ["R1", "R2", "R3", "ENV_MANUAL"]
    n_partes = 0
    for d in _habiles(hoy - timedelta(days=60), hoy - timedelta(days=1)):
        for ln in rnd.sample(lineas_env, 2) + [rnd.choice(("CIMBRIA", "TRUER", "SEL_MANUAL"))]:
            seleccion = ln in ("CIMBRIA", "TRUER", "SEL_MANUAL")
            p = rnd.choice(graneles if seleccion else pts)
            entrada = rnd.choice((2500, 3500, 5000, 7000)) if not seleccion else rnd.choice((6000, 9000, 12000))
            rend = rnd.uniform(0.95, 0.99)
            horas = rnd.choice((7.5, 8.0, 8.0, 9.5))
            parada = rnd.choice((0, 0, 0, 15, 30, 45, 90))
            pres = p.peso_kg or 1
            s.add(ProductionReport(linea=ln, tipo="SELECCION" if seleccion else "ENVASADO", fecha=d, product_code=p.code,
                                   peso_entrada_kg=entrada, presentacion_kg=pres, unidades=None if seleccion else round(entrada * rend / pres),
                                   mp_kg=round(entrada * rend, 1), desmedro_kg=round(entrada * (1 - rend) * 0.6, 1),
                                   horas=horas, operarios=rnd.choice((4, 5, 6)), rendimiento_pct=round(rend * 100, 1),
                                   desmedro_pct=round((1 - rend) * 60, 2), ratio_kg_hora=round(entrada / horas, 1),
                                   parada_min=parada, motivo_parada="Cambio de bobina (ficticio)" if parada else "",
                                   estado="LIQUIDADO", turno="DÍA", hora_inicio="07:00",
                                   hora_fin=f"{7 + int(horas):02d}:{int((horas % 1) * 60):02d}",
                                   indicadores={"oee": round(rnd.uniform(62, 88), 1)}, observacion=MARCA))
            n_partes += 1
    res["partes_produccion"] = n_partes
    estados_sol = [("FINALIZADA", -10), ("LIQUIDADA", -6), ("EN_PROCESO", 0), ("PROGRAMADA", 1), ("PROGRAMADA", 2),
                   ("VALIDADA", 3), ("ENVIADA", 4), ("BORRADOR", 6)]
    jp = _u("jefe.produccion")
    for i, (est, dd) in enumerate(estados_sol):
        p = pts[i % len(pts)]
        r = ProductionRequest(product_code=p.code, cantidad=rnd.choice((800, 1200, 2000, 3000)),
                              fecha_requerida=hoy + timedelta(days=dd + 2), estado=est, origen="DEMANDA",
                              line_code=rnd.choice(lineas_env), fecha_programada=hoy + timedelta(days=dd),
                              observacion=f"{MARCA}: solicitud ficticia", creado_por=jp.id if jp else None)
        s.add(r)
        s.flush()
        if est in ("FINALIZADA", "LIQUIDADA"):
            s.add(Liquidation(numero_documento=f"LQ-DEMO-{r.id:04d}", request_id=r.id, product_code=p.code,
                              warehouse_code="ALM-001", fecha=hoy + timedelta(days=dd), cantidad_planificada=r.cantidad,
                              cantidad_completada=r.cantidad * 0.98, lote=f"DFL{r.id:04d}", estado="RECIBIDA_COMPLETA",
                              cantidad_recibida=r.cantidad * 0.98, horas=8, operarios=5, observacion=MARCA))

    # ---------------------------------------------------------------- importaciones y compras en curso
    ga = _u("compras") or coord
    for i, g in enumerate(graneles[:3]):
        s.add(ImportShipment(referencia=f"IMP-DEMO-{i + 1:02d}", proveedor=f"Proveedor exterior demo {i + 1}",
                             product_code=g.code, cantidad=rnd.choice((24000, 48000)), estado="EN_CURSO",
                             fecha_llegada_estimada=hoy + timedelta(days=8 + 6 * i), warehouse_code="EXT-002",
                             creado_por=ga.id if ga else None))
        s.add(PurchaseRequest(product_code=g.code, cantidad=rnd.choice((5000, 8000)), fecha_necesidad=hoy + timedelta(days=12),
                              origen="PROYECCION", estado="ORDEN_GENERADA", numero_oc=f"OC-DEMO-{i + 1:03d}",
                              proveedor=f"Proveedor nacional demo {i + 1}", fecha_prevista=hoy + timedelta(days=5 + 3 * i),
                              warehouse_code="EXT-002", creado_por=ga.id if ga else None))
    s.flush()

    # ---------------------------------------------------------------- oportunidades con su producto (tablero del embudo)
    from .models import Opportunity
    for i, op in enumerate(s.execute(select(Opportunity).order_by(Opportunity.id)).scalars()):
        if not op.detalle_productos:
            p = pts[i % len(pts)] if i % 4 else graneles[i % len(graneles)]
            op.detalle_productos = [{"product_code": p.code, "kg_mes": 500 + 250 * (i % 5),
                                     "soles_mes": round((op.proyeccion_mensual or 3000) * 0.8, 2)}]
            if i % 3 == 0:
                op.tipo = "ADICIONAL"

    # ---------------------------------------------------------------- alertas para revisar la bandeja de gerencia
    from .services import alerts
    emitidas = 0
    for code, titulo, msg in (
            ("LOTE_OBSERVADO", "Lote DF-905 observado por humedad (ficticio)", "Calidad observó el lote en la recepción."),
            ("CALIDAD_NO_CONFORME", "No conformidad: sellado deficiente en R2 (ficticio)", "Se separaron 3 pallets."),
            ("FUMIGACION_PROXIMA", "Fumigación del contenedor 1 en 3 días (ficticio)", "Coordinar con Mantenimiento."),
            ("COMPRA_SOLICITUD", "Solicitud de compra de granel por aprobar (ficticio)", "Arveja verde 8 000 kg."),
            ("IMPORT_LLEGADA", "Importación IMP-DEMO-01 llega en 8 días (ficticio)", "Preparar espacio en EXT-002."),
            ("COMPRA_SOBRE_COSTO_MAXIMO", "Compra sobre el costo máximo (ficticio)", "Lenteja: +6 % sobre el máximo.")):
        try:
            if alerts.emit(code, titulo, msg, "Demo", code, dedup_key=f"{MARCA}:{code}") is not None:
                emitidas += 1
        except Exception:  # noqa: BLE001  tipo no configurado en una base antigua
            pass
    for i in range(12):
        try:
            alerts.emit("SAP_SIN_CONEXION", f"Sin conexión con SAP (intento {i + 1}, ficticio)",
                        "La sincronización se reintenta sola.", "Demo", f"sap{i}", dedup_key=f"{MARCA}:SAP:{i}")
            emitidas += 1
        except Exception:  # noqa: BLE001
            pass
    res["alertas"] = emitidas
    s.flush()
    return res
