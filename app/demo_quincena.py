"""V24 (07-nov-2026): 15 días de operación FICTICIA en que todas las áreas ya registraron.

Se ejecuta después del flujo completo (python -m app.cli demo-dia). Sobre las OV ficticias de los últimos 15 días
hábiles deja lo que cada área habría registrado:
- Almacén: tareas de picking terminadas con sus registros (lote, cantidad, bultos) y fotos de muestra.
- Distribución: rutas cerradas por día y vehículo (chofer, auxiliares, hora de salida y retorno, km), paradas con su
  guía, receptor y hora de entrega; transporte externo con su costo; algunas entregas parciales o rechazadas con su
  incidencia; combustible cada tres días.
- Chofer y Seguridad: checklist vehicular COMPLETO de salida y de retorno (todos los ítems marcados, km), con
  observaciones y puntos marcados sobre el dibujo del vehículo, validado por Seguridad.
- Calidad: registros diarios (recepción de MP, control de pesos, control de granos) y certificados.
- Saneamiento: limpieza diaria de zonas y fumigación semanal.
- Personal: asistencia diaria de todos los colaboradores (con alguna falta y tardanza).
- Finanzas: pagos reportados y confirmados de las facturas pagadas.
- Comercial: oportunidades y cotizaciones de las dos últimas semanas.
Todo es inventado (guías «T001-», personas «Receptor demo», fotos de muestra).
"""
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from .db import db
from .models import (Attendance, Certificate, Customer, CustomerInvoice, CustomerPayment, Driver, FuelLog, Incident,
                     Opportunity, PickingRecord, PickingTask, QualityRecord, Quote, Route, RouteStop, SalesOrder,
                     SanitationLog, SanitationZone, StockLot, User, Vehicle, VehicleChecklist, Worker)

MARCA = "DEMO-QUINCENA"


def _u(username):
    return db().execute(select(User).where(User.username == username)).scalars().first()


def _dt(d, h, m=0):
    return datetime.combine(d, time(h % 24, m % 60))


def ya_cargado():
    return db().execute(select(Route).where(Route.zona == MARCA)).first() is not None


def _habiles(hoy, n=15):
    out, d = [], hoy - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 6:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def seed_quincena(upload_dir=None, hoy=None):
    from .catalogs import CHECKLIST_VEHICULAR, PARTES_VEHICULO
    from .demo_dia import _foto
    s = db()
    hoy = hoy or date.today()
    if ya_cargado():
        return None
    rnd = random.Random(15)
    res = {"rutas": 0, "paradas": 0, "checklists": 0, "picking": 0, "calidad": 0, "asistencia": 0, "pagos": 0,
           "oportunidades": 0, "incidencias": 0}
    up = upload_dir or "."
    foto_pick = _foto(up, "demo_picking.jpg", "Picking listo\n(muestra)", (40, 90, 140)) if upload_dir else ""
    foto_ent = _foto(up, "demo_entrega.jpg", "Entrega conforme\n(muestra)", (20, 110, 60)) if upload_dir else ""
    seg = _u("seguridad")
    alm = _u("aux.almacen") or _u("coord.almacen")
    calidad = _u("asist.calidad") or _u("jefe.calidad")
    vehs = [v for v in s.execute(select(Vehicle).order_by(Vehicle.capacidad_kg)).scalars()]
    propios = [v for v in vehs if v.propio]
    externo = next((v for v in vehs if not v.propio), None)
    drivers = {d.id: d for d in s.execute(select(Driver)).scalars()}
    choferes = [d for d in drivers.values() if not d.externo]
    chofer_ext = next((d for d in drivers.values() if d.externo), None)
    auxs = [u for u in s.execute(select(User).where(User.role_code == "AUX_DESPACHO")).scalars()]
    lotes = {}
    for l in s.execute(select(StockLot).where(StockLot.cantidad > 0).order_by(StockLot.id)).scalars():
        lotes.setdefault(l.product_code, l)
    km = {v.id: 40000 + 7000 * i for i, v in enumerate(vehs)}
    n_guia = [100]
    for d in _habiles(hoy):
        ovs = [o for o in s.execute(select(SalesOrder).where(SalesOrder.numero.like("DF-%"),
                                                             SalesOrder.estado.in_(("ENTREGADA", "ENTREGA_PARCIAL")))).scalars()
               if o.salida_ts and o.salida_ts.date() == d]
        if not ovs:
            continue
        # picking del día anterior a la salida
        for o in ovs:
            t = PickingTask(order_id=o.id, warehouse_code="ALM-001", fecha=d - timedelta(days=1),
                            asignados=[alm.id] if alm else [], asignado_por=alm.id if alm else None, estado="LISTO",
                            inicio_ts=_dt(d - timedelta(days=1), 14, rnd.randint(0, 50)),
                            fin_ts=_dt(d - timedelta(days=1), 16, rnd.randint(0, 50)), foto_inicio=foto_pick,
                            foto_listo=foto_pick, observacion=f"{MARCA}: picking ficticio")
            s.add(t)
            s.flush()
            for l in o.lines:
                lot = lotes.get(l.product_code)
                s.add(PickingRecord(order_id=o.id, line_id=l.id, task_id=t.id, lote=lot.lote if lot else "DEMO",
                                    cantidad=l.preparado or l.cantidad, bultos=max(1, int((l.cantidad or 0) // 20)),
                                    fecha_venc=lot.fecha_venc if lot else None, user_id=alm.id if alm else None,
                                    ts=t.fin_ts))
            res["picking"] += 1
        # rutas: 3-4 OV por vehículo; la última del día con transporte externo
        grupos = [ovs[i:i + 4] for i in range(0, len(ovs), 4)]
        for gi, grupo in enumerate(grupos):
            usa_ext = externo is not None and gi == len(grupos) - 1 and len(grupos) > 1
            v = externo if usa_ext else propios[gi % len(propios)]
            dr = chofer_ext if usa_ext else choferes[gi % len(choferes)]
            ax = [auxs[(gi + k) % len(auxs)].id for k in range(1 if gi % 2 else 2)] if auxs and not usa_ext else []
            salida = min(o.salida_ts for o in grupo)
            km0 = km[v.id]
            dist = rnd.choice((38, 52, 64, 85, 110))
            km[v.id] += dist
            trans = ({"tipo": "TERCERO", "costo": rnd.choice((320, 380, 450)), "proveedor": "Transportes Demo SAC"}
                     if usa_ext else {"tipo": "CHOFER"})
            r = Route(fecha=d, vehicle_id=v.id, driver_id=dr.id if dr else None, requiere_externo=usa_ext, zona=MARCA,
                      estado="CERRADA", manual=gi % 3 == 0, auxiliares=ax, auxiliar_id=ax[0] if ax else None,
                      transportista=trans, hora_salida_prog=f"{salida:%H}:00", salida_ts=salida,
                      retorno_ts=salida + timedelta(hours=rnd.choice((5, 6, 7))), cierre_ts=salida + timedelta(hours=8),
                      km_salida=km0, km_retorno=km0 + dist, distancia_km=dist,
                      costo_transporte=trans.get("costo"), peso_total=0, advertencias=[],
                      salida_confirmada_por=seg.id if seg else None, vistos_buenos=[])
            s.add(r)
            s.flush()
            peso = 0.0
            for k, o in enumerate(grupo):
                n_guia[0] += 1
                kg = sum((l.cantidad or 0) * ((l.product.peso_kg if l.product else 1) or 1) for l in o.lines)
                peso += kg
                parcial = o.estado == "ENTREGA_PARCIAL"
                st = RouteStop(route_id=r.id, order_id=o.id, orden=k + 1, peso_kg=round(kg, 1),
                               estado="ENTREGA_PARCIAL" if parcial else "ENTREGADO",
                               llegada_ts=o.entrega_ts - timedelta(minutes=20) if o.entrega_ts else None,
                               entrega_ts=o.entrega_ts, guia_numero=f"T001-{n_guia[0]:06d}", guia_origen="SISTEMA",
                               fecha_guia=d, guia_estado="ACEPTADA", foto_path=foto_ent,
                               receptor_nombre=f"Receptor demo {rnd.randint(1, 40)}", receptor_dni=f"4{rnd.randint(1000000, 9999999)}",
                               receptor_tipo_doc="DNI", observacion="Entrega parcial: faltó un producto" if parcial else "")
                s.add(st)
                s.flush()
                res["paradas"] += 1
                if parcial:
                    s.add(Incident(tipo="ENTREGA_PARCIAL", grupo="Entrega", route_id=r.id, stop_id=st.id, order_id=o.id,
                                   descripcion="El cliente recibió parcialmente (ficticio).", estado="CERRADA",
                                   user_id=dr.user_id if dr and dr.user_id else None, ts=o.entrega_ts or _dt(d, 12)))
                    res["incidencias"] += 1
            r.peso_total = round(peso, 1)
            r.guia_numero = f"T001-{n_guia[0]:06d}"
            res["rutas"] += 1
            # checklist vehicular completo de salida y retorno, validado por Seguridad
            for momento, hora, kmv in (("SALIDA", salida, km0), ("RETORNO", r.retorno_ts, km0 + dist)):
                vals = {code: ("NA" if (code.startswith("LUZ_FURGON") and v.tipo_unidad == "CAMIONETA") else "B")
                        for code, _z, _i, _nn in CHECKLIST_VEHICULAR}
                obs, marcas = "", []
                if rnd.random() < 0.25:
                    malos = [c for c, _z, _i, nn in CHECKLIST_VEHICULAR if not nn]
                    c = rnd.choice(malos)
                    vals[c] = "M"
                    parte = rnd.choice(PARTES_VEHICULO[:-1])
                    nota = rnd.choice(("rayón leve", "abolladura pequeña", "luz intermitente", "desgaste visible"))
                    marcas = [{"x": round(rnd.uniform(15, 85), 1), "y": round(rnd.uniform(20, 80), 1), "parte": parte,
                               "nota": nota, "vista": 0}]
                    obs = f"Punto 1: {parte} – {nota}"
                s.add(VehicleChecklist(vehicle_id=v.id, route_id=r.id, momento=momento, fecha=d,
                                       driver_id=dr.id if dr else None, items=vals, observaciones=obs, km=kmv,
                                       nn_fallidos=[], marcas=marcas, estado="VALIDADO",
                                       registrado_por=dr.user_id if dr and dr.user_id else None, registrado_ts=hora,
                                       validado_por=seg.id if seg else None, validado_ts=hora + timedelta(minutes=10),
                                       km_seguridad=kmv, nota_seguridad="Conforme (demo)"))
                res["checklists"] += 1
            if v.propio and rnd.random() < 0.35:
                s.add(FuelLog(vehicle_id=v.id, fecha=d, km=km0 + dist, galones=round(rnd.uniform(8, 25), 1),
                              monto=round(rnd.uniform(140, 420), 2), route_id=r.id, driver_id=dr.id if dr else None))
    s.flush()
    # calidad: registros diarios y certificados
    for d in _habiles(hoy):
        for fmt in ("RECEPCION_MP", "CONTROL_PESOS", "CONTROL_GRANOS"):
            s.add(QualityRecord(formato=fmt, fecha=d, product_code=rnd.choice(("MP-901", "MP-902", "PT-901", "PT-905")),
                                lote=f"DF{d:%y%m%d}", datos={"humedad": round(rnd.uniform(11, 13.5), 1),
                                                             "impurezas": round(rnd.uniform(0.1, 0.8), 2),
                                                             "peso_promedio": round(rnd.uniform(0.498, 0.505), 3)},
                                resultado="CONFORME" if rnd.random() > 0.08 else "OBSERVADO", estado="REGISTRADO",
                                observaciones=f"{MARCA}", user_id=calidad.id if calidad else None, ts=_dt(d, 10)))
            res["calidad"] += 1
    n_cert = 0
    for o in s.execute(select(SalesOrder).where(SalesOrder.numero.like("DF-%"), SalesOrder.estado == "ENTREGADA",
                                                SalesOrder.salida_ts >= _dt(hoy - timedelta(days=21), 0))).scalars():
        if n_cert >= 25:
            break
        n_cert += 1
        l = o.lines[0]
        s.add(Certificate(numero=f"CC-DEMO-{n_cert:04d}", serie="CC", order_id=o.id, product_code=l.product_code,
                          datos={"lote": (lotes.get(l.product_code).lote if lotes.get(l.product_code) else "DEMO"),
                                 "resultado": "CONFORME"}, estado="EMITIDO", generado_ts=o.salida_ts - timedelta(hours=3),
                          revisado_por=calidad.id if calidad else None, revisado_ts=o.salida_ts - timedelta(hours=2)))
    res["certificados"] = n_cert
    # saneamiento: limpieza diaria y fumigación semanal
    zonas = list(s.execute(select(SanitationZone)).scalars())
    for d in _habiles(hoy):
        for z in zonas[:6]:
            s.add(SanitationLog(zone_id=z.id, tipo="LIMPIEZA", fecha=d, responsable="Personal de limpieza (demo)",
                                observacion=MARCA))
        if d.weekday() == 0:
            for z in zonas[:3]:
                s.add(SanitationLog(zone_id=z.id, tipo="FUMIGACION", fecha=d, responsable="Empresa fumigadora (demo)",
                                    producto="Fosfina (demo)", certificado=f"FUM-{d:%y%m%d}", vence=d + timedelta(days=30),
                                    observacion=MARCA))
    # asistencia de todos los colaboradores
    trabajadores = list(s.execute(select(Worker).where(Worker.activo.is_(True))).scalars())
    for d in _habiles(hoy):
        hechos = {a.worker_id for a in s.execute(select(Attendance).where(Attendance.fecha == d)).scalars()}
        for w in trabajadores:
            if w.id in hechos:
                continue
            r = rnd.random()
            est = "ASISTENCIA" if r < 0.92 else ("TARDANZA" if r < 0.97 else "FALTA")
            s.add(Attendance(worker_id=w.id, fecha=d, estado=est, observacion="" if est == "ASISTENCIA" else "(demo)"))
            res["asistencia"] += 1
    # pagos de las facturas pagadas
    for i in s.execute(select(CustomerInvoice).where(CustomerInvoice.observacion.like("DEMO-FLUJO%"),
                                                     CustomerInvoice.estado == "PAGADA")).scalars():
        if s.execute(select(CustomerPayment).where(CustomerPayment.invoice_id == i.id)).first():
            continue
        f = min((i.vencimiento or i.fecha) - timedelta(days=rnd.randint(0, 5)), hoy - timedelta(days=1))
        s.add(CustomerPayment(customer_id=i.customer_id, invoice_id=i.id, fecha=f, monto=i.monto, medio="Transferencia",
                              operacion=f"OP{i.id:06d}", estado="CONFIRMADO", observacion=MARCA,
                              confirmado_por=(_u("coord.finanzas") or seg).id if (_u("coord.finanzas") or seg) else None,
                              confirmado_ts=_dt(f, 11)))
        res["pagos"] += 1
    # comercial: oportunidades y cotizaciones de las dos últimas semanas
    clientes = [c for c in s.execute(select(Customer)).scalars() if not c.es_prospecto]
    vends = [u for u in s.execute(select(User).where(User.role_code == "EJECUTIVO_VENTAS")).scalars()]
    estados = ["ABIERTA", "ABIERTA", "COTIZADA", "NEGOCIACION", "GANADA", "GANADA", "PERDIDA"]
    motivos = ["Precio más alto que la competencia", "El cliente pospuso la compra", "Sin stock en la fecha pedida"]
    for k in range(20):
        d = hoy - timedelta(days=rnd.randint(0, 14))
        c = rnd.choice(clientes)
        est = rnd.choice(estados)
        code = rnd.choice(("PT-901", "PT-902", "PT-903", "PT-904", "PT-905", "MP-901", "GR-901"))
        op = Opportunity(customer_id=c.id, vendedor_id=rnd.choice(vends).id if vends else None,
                         titulo=f"Oportunidad demo {k + 1}: {code}", productos=code,
                         proyeccion_mensual=float(rnd.choice((1500, 3000, 5000, 8000))),
                         proyeccion_kg=float(rnd.choice((300, 600, 1200))),
                         detalle_productos=[{"product_code": code, "kg_mes": 600, "soles_mes": 3000}],
                         estado=est, tipo=rnd.choice(("NUEVO", "ADICIONAL")),
                         motivo_cierre=(rnd.choice(motivos) if est == "PERDIDA" else ("Cliente aceptó la propuesta"
                                                                                      if est == "GANADA" else "")),
                         creado_ts=_dt(d, 10), cerrado_ts=_dt(d + timedelta(days=3), 12) if est in ("GANADA", "PERDIDA") else None)
        s.add(op)
        s.flush()
        if est in ("COTIZADA", "NEGOCIACION", "GANADA", "PERDIDA"):
            s.add(Quote(numero=f"COT-DEMO-{k + 1:04d}", customer_id=c.id, opportunity_id=op.id, fecha=d,
                        vigencia=d + timedelta(days=15), lineas=[{"product_code": code, "cantidad": 100, "precio": 4.5}],
                        total=450.0, estado="ACEPTADA" if est == "GANADA" else ("RECHAZADA" if est == "PERDIDA" else "EMITIDA"),
                        observacion=MARCA, user_id=op.vendedor_id))
        res["oportunidades"] += 1
    # centros de costo ficticios (los reales se cargan desde el Excel de la empresa) y rendiciones / movilidad
    from .models import CostCenter, ExpenseReport
    if not s.execute(select(CostCenter)).first():
        for cod, grupo, area, centro, desc in (
                ("9101", "ADMINISTRACIÓN", "Administración y Finanzas", "Gerencias", "Gerencia (demo)"),
                ("9102", "ADMINISTRACIÓN", "Administración y Finanzas", "Finanzas", "Tesorería (demo)"),
                ("9201", "OPERACIONES", "Logística", "Almacén PT", "Almacén producto terminado (demo)"),
                ("9202", "OPERACIONES", "Logística", "Distribución", "Flota propia (demo)"),
                ("9301", "OPERACIONES", "Producción", "Envasado", "Línea de envasado (demo)"),
                ("9401", "COMERCIAL", "Comercial", "Ventas", "Fuerza de ventas (demo)"),
                ("9501", "MANTENIMIENTO", "Mantenimiento", "Planta", "Mantenimiento de planta (demo)")):
            s.add(CostCenter(codigo=cod, grupo=grupo, area=area, centro=centro, descripcion=desc))
        s.flush()
    comp = _u("compras")
    for k in range(12):
        d = _habiles(hoy)[k % 15]
        tipo = "RENDICION" if k % 3 else "MOVILIDAD"
        s.add(ExpenseReport(tipo=tipo, fecha=d, responsable=comp.nombre if comp else "Compras",
                            concepto=("Taxi a proveedor de granos (demo)" if tipo == "MOVILIDAD" else
                                      rnd.choice(("Sacos y rafia en mercado (demo)", "Etiquetas urgentes (demo)",
                                                  "Repuesto de balanza (demo)"))),
                            comprobante="" if tipo == "MOVILIDAD" else f"F001-{1000 + k}",
                            proveedor="" if tipo == "MOVILIDAD" else "Proveedor menor demo",
                            monto=round(rnd.uniform(25, 60) if tipo == "MOVILIDAD" else rnd.uniform(120, 900), 2),
                            centro_costo=rnd.choice(("", "9201", "9301", "9501")), user_id=comp.id if comp else None))
    res["rendiciones"] = 12
    s.flush()
    return res
