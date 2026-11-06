"""V22 (06-nov-2026): un día de operación FICTICIO para recorrer el sistema con cada perfil.

Se ejecuta sobre la demostración (python -m app.cli demo, y luego python -m app.cli demo-dia). Todo es inventado:
clientes «DEMO», placas DEM-/TER-, personas «Colaborador demo N», fotos de muestra generadas con texto. Deja casuísticas
para validar: rutas automáticas y manuales con varios clientes, auxiliares múltiples, un vendedor que lleva carga, un
tercero con traslado entre almacenes, sobrecarga, cambios con motivo, pernocte, choferes de vacaciones o con descanso
médico, faltas justificadas e injustificadas, devoluciones por recibir (a tiempo, vencida y observada), tickets de
averías y de Sistemas, trabajos de mantenimiento en cada estado con fotos antes/después, avisos 7/3/0, bitácora de
máquinas, paradas con fotos, limpieza programada con y sin marcar, asistencia, presupuesto superado, oportunidades para
el embudo y antecedentes (rutas, terceros, averías) para que aparezcan las sugerencias de eficiencia.
"""
import os
from datetime import date, datetime, timedelta

from sqlalchemy import select

from .db import db
from .models import (AreaBudget, Attendance, Breakdown, BudgetLine, CleaningAssignment, Customer, CustomerAction, Driver,
                     MachineLog, Opportunity, ProductionReport, Route, RouteStop, SalesOrder, StockLot, ThirdPartyTransport,
                     Ticket, User, Vehicle, WorkOrder, Worker, now)

MARCA = "DEMO-DIA"


def _foto(upload_dir, nombre, texto, color=(11, 107, 58)):
    """Imagen de muestra (no es una foto real)."""
    from PIL import Image, ImageDraw
    os.makedirs(upload_dir, exist_ok=True)
    ruta = os.path.join(upload_dir, nombre)
    if not os.path.exists(ruta):
        im = Image.new("RGB", (480, 320), color)
        d = ImageDraw.Draw(im)
        d.rectangle((10, 10, 470, 310), outline=(255, 255, 255), width=3)
        for i, linea in enumerate(texto.split("\n")):
            d.text((24, 30 + 26 * i), linea, fill=(255, 255, 255))
        d.text((24, 280), "FOTO DE MUESTRA - DATOS FICTICIOS", fill=(255, 255, 210))
        im.save(ruta, quality=80)
    return nombre


def _precio(code, cliente):
    """Precio de la lista del canal del cliente + 5 % (ficticio); si no hay lista, un precio de referencia demo."""
    from .models import Product
    from .services.prices import price_for
    p, _ = price_for(db().get(Product, code), cliente)
    return round(p * 1.05, 2) if p else {"PT-901": 4.5, "PT-902": 38.0, "PT-903": 4.2, "PT-904": 42.0, "PT-905": 3.8,
                                         "PT-906": 4.1}.get(code, 10.0)


def _u(username):
    return db().execute(select(User).where(User.username == username)).scalars().first()


def ya_cargado():
    return db().execute(select(Ticket).where(Ticket.descripcion.like(f"%{MARCA}%"))).first() is not None


def seed_operation_day(upload_dir, hoy=None):
    """Crea el día de operación ficticio. Devuelve un resumen de lo creado (o None si ya existía)."""
    from .services import (ausencias, devoluciones, limpieza, mant_trabajos, rutas_manual, tickets, transfers)
    from .services.orders import create_order
    s = db()
    hoy = hoy or date.today()
    if ya_cargado():
        return None
    res = {}
    F = lambda n, t, c=(11, 107, 58): _foto(upload_dir, f"demo_{n}.jpg", t, c)  # noqa: E731

    # ---------------------------------------------------------------- clientes adicionales
    extra = [("20000000006", "CLIENTE DEMO BODEGAS DEL NORTE S.A.C.", "MAYORISTA", "AV. NORTE DEMO 10", "COMAS"),
             ("20000000007", "CLIENTE DEMO MINIMARKET SUR E.I.R.L.", "AUTOSERVICIOS", "JR. SUR DEMO 20", "CHORRILLOS"),
             ("20000000008", "CLIENTE DEMO HOTEL CENTRO S.A.", "HOTELES - RESTAURANTES", "AV. CENTRO DEMO 30", "LIMA")]
    for ruc, nombre, grupo, dirc, dist in extra:
        if not s.execute(select(Customer).where(Customer.ruc == ruc)).first():
            s.add(Customer(ruc=ruc, nombre=nombre, grupo=grupo, direccion=dirc, distrito=dist, provincia="LIMA",
                           horario_recepcion="08:00-17:00"))
    s.flush()
    clientes = list(s.execute(select(Customer).order_by(Customer.ruc)).scalars())

    # ---------------------------------------------------------------- personal (colaboradores sin cuenta y con cuenta)
    def worker(nombre, area, puesto="", linea="", username=None):
        w = s.execute(select(Worker).where(Worker.nombre == nombre)).scalars().first()
        if w is None:
            w = Worker(nombre=nombre, area=area, puesto=puesto, linea=linea)
            s.add(w)
        if username:
            u = _u(username)
            w.user_id = u.id if u else None
        return w
    tec1 = worker("TECNICO DEMO 1", "Mantenimiento", "Técnico de mantenimiento", username="tecnico.mant1")
    tec2 = worker("TECNICO DEMO 2", "Mantenimiento", "Electricista", username="tecnico.mant2")
    lim1 = worker("LIMPIEZA DEMO 1", "Mantenimiento", "Limpieza", username="limpieza1")
    lim2 = worker("LIMPIEZA DEMO 2", "Mantenimiento", "Limpieza", username="limpieza2")
    lim3 = worker("LIMPIEZA DEMO 3", "Mantenimiento", "Limpieza")
    prod_w = [worker(f"COLABORADOR DEMO {i}", "Producción", "Operario", ["R1", "R1", "TRUER", "CIMBRIA", "SEL_MANUAL", "R2"][i - 1])
              for i in range(1, 7)]
    s.flush()

    # ---------------------------------------------------------------- vehículos: capacidad real, carga habitual, imagen
    veh = {v.placa: v for v in s.execute(select(Vehicle)).scalars()}
    for placa, real, hab, img, tipo in (("DEM-450", 500, 420, "FURGON", "FURGON LIVIANO"),
                                        ("DEM-4T5", 4800, 4000, "CAMION", "CAMION 4.5 TN"),
                                        ("DEM-10T", 10500, 8500, "CAMION_CABINA", "CAMION 10 TN"),
                                        ("DEM-25T", 26000, 20000, "TRACTO", "TRACTO 25 TN"),
                                        ("TER-2T", 2200, 1800, "CAMION", "CAMION 2 TN")):
        v = veh.get(placa)
        if v is not None:
            v.capacidad_real_kg, v.carga_habitual_kg, v.imagen_checklist, v.tipo_unidad = real, hab, img, tipo
    drivers = {d.nombre: d for d in s.execute(select(Driver)).scalars()}

    # ---------------------------------------------------------------- disponibilidad del personal
    jefe_dist, jefe_mant, gh = _u("coord.distribucion"), _u("jefe.mantenimiento"), _u("gestion.humana")
    aus = []
    for clave, tipo, d0, d1, motivo, quien in (
            (f"DRIVER:{drivers['Chofer 3'].id}", "VACACIONES", hoy - timedelta(days=2), hoy + timedelta(days=5), "", jefe_dist),
            (f"DRIVER:{drivers['Chofer 4'].id}", "DESCANSO_MEDICO", hoy, hoy + timedelta(days=2), "Descanso médico (demo)", jefe_dist),
            (f"USER:{_u('aux.despacho3').id}", "FALTA_JUSTIFICADA", hoy, hoy, "Duelo familiar", jefe_dist),
            (f"WORKER:{prod_w[1].id}", "FALTA_INJUSTIFICADA", hoy, hoy, "", gh),
            (f"WORKER:{prod_w[1].id}", "FALTA_INJUSTIFICADA", hoy - timedelta(days=6), hoy - timedelta(days=6), "", gh),
            (f"WORKER:{prod_w[1].id}", "FALTA_INJUSTIFICADA", hoy - timedelta(days=13), hoy - timedelta(days=13), "", gh),
            (f"WORKER:{lim3.id}", "VACACIONES", hoy + timedelta(days=3), hoy + timedelta(days=10), "", jefe_mant)):
        aus.append(ausencias.register(quien, clave, tipo, d0, d1, motivo,
                                      F("dm", "Descanso médico\n(documento de muestra)") if tipo == "DESCANSO_MEDICO" else ""))
    res["ausencias"] = len(aus)

    # ---------------------------------------------------------------- asistencia de hoy
    marcas = {w.id: "ASISTENCIA" for w in prod_w + [tec1, tec2, lim1, lim2]}
    marcas[prod_w[4].id] = "TARDANZA"
    for wid, est in marcas.items():
        if not s.execute(select(Attendance).where(Attendance.worker_id == wid, Attendance.fecha == hoy)).first():
            s.add(Attendance(worker_id=wid, fecha=hoy, estado=est, user_id=jefe_mant.id))

    # ---------------------------------------------------------------- OV del día (varios clientes por vehículo)
    vend = _u("vendedor1")
    ventas = _u("coord.ventas")
    ovs = []
    pedidos = [(0, [("PT-905", 120)]), (1, [("PT-902", 6)]), (2, [("PT-906", 30)]), (3, [("PT-901", 40)]),
               (4, [("PT-904", 8)]), (5, [("PT-905", 200)]), (6, [("PT-902", 10)]), (7, [("PT-906", 20)]),
               (1, [("PT-905", 40)])]
    for i, (ci, lineas) in enumerate(pedidos, 1):
        try:
            # se registran con anticipación (como si se hubieran emitido ayer) y se despachan hoy
            cli = clientes[ci % len(clientes)]
            o = create_order(ventas, f"DEMO-DIA-{i:02d}", cli.id, hoy + timedelta(days=3),
                             [{"product_code": c, "cantidad": q, "precio_unitario": _precio(c, cli)} for c, q in lineas],
                             vendedor_id=vend.id, oc_archivo=F("oc", "Orden de compra\n(muestra)"))
            o.fecha_compromiso = hoy
            o.fecha_emision = hoy - timedelta(days=1)
            ovs.append(o)
        except Exception:  # noqa: BLE001  una OV que no se pueda crear (stock) no detiene la demostración
            s.rollback()
    s.flush()
    # las propuestas automáticas que se generaron al evaluar (con la fecha de registro) se rehacen para hoy
    for r in s.execute(select(Route).where(Route.estado == "PROPUESTA", Route.manual.is_(False),
                                           Route.fecha == hoy + timedelta(days=3))).scalars():
        s.delete(r)
    s.flush()
    res["ov"] = len(ovs)
    usables = [o for o in ovs if o.estado not in ("CANCELADA", "BORRADOR", "BLOQUEADA")]


    # ---------------------------------------------------------------- traslados entre almacenes
    lote = s.execute(select(StockLot).where(StockLot.product_code == "MP-901", StockLot.cantidad > 100)).scalars().first()
    trs = []
    if lote is not None:
        for q in (150, 80):
            t = transfers.request_transfer(_u("coord.logistica"), lote.id, "ALM-001", q, observacion="Abastecer línea (demo)")
            s.flush()
            transfers.authorize(t, _u("jefe.logistica"), True, "Autorizado (demo)")
            trs.append(t)
    s.flush()

    # ---------------------------------------------------------------- rutas del día
    dist = jefe_dist
    auxs = [_u("aux.despacho").id, _u("aux.despacho2").id]
    rutas = []

    def ruta(datos, o_ids, t_ids=(), aux=()):
        try:
            r = rutas_manual.create_manual(dist, hoy, datos, o_ids, t_ids, aux)
            s.flush()
            rutas.append(r)
            return r
        except Exception as e:  # noqa: BLE001
            res.setdefault("avisos", []).append(f"Ruta no creada: {e}")
            return None
    r1 = ruta({"tipo_transportista": "CHOFER", "vehicle_id": veh["DEM-4T5"].id, "driver_id": drivers["Chofer 1"].id,
               "hora_salida": "07:30", "zona": "Lima Este y Centro"}, [o.id for o in usables[:3]], (), auxs)
    r2 = ruta({"tipo_transportista": "CHOFER", "vehicle_id": veh["DEM-450"].id, "driver_id": drivers["Chofer 2"].id,
               "hora_salida": "08:00", "zona": "Surco"}, [o.id for o in usables[3:4]], (), [_u("aux.despacho4").id])
    if r2 is not None:
        rutas_manual.set_real_weight(r2, dist, 520)  # pesado en balanza: supera lo permitido (450) y la capacidad real
    r3 = ruta({"tipo_transportista": "TRABAJADOR", "t_nombre": vend.nombre, "t_area": "Comercial",
               "t_vehiculo": "Camioneta del ejecutivo (demo)", "t_placa": "DEM-VEN", "t_user_id": str(vend.id),
               "t_motivo": "El cliente está en su ruta de visitas de hoy"}, [o.id for o in usables[4:5]])
    r4 = ruta({"tipo_transportista": "TERCERO", "vehicle_id": veh["TER-2T"].id, "driver_id": drivers["Chofer externo"].id,
               "hora_salida": "09:00", "zona": "Traslado a ALM-001 y Comas"}, [o.id for o in usables[5:6]],
              [t.id for t in trs[:1]])
    from .services.distribution import propose_routes
    auto = propose_routes(hoy, jefe_dist, orders=usables[6:8], require_prepared=False)  # programación del sistema
    res["rutas_automaticas"] = len(auto)
    if r1 is not None and len(usables) > 8:  # cambio a una ruta programada, con motivo
        rutas_manual.modify(r1, dist, "El cliente pidió adelantar su pedido (demo)", agregar_ov=[usables[8].id])
    if r4 is not None:
        r4.externo_validacion = {"validado": True, "user": dist.nombre, "ts": now().isoformat(timespec="minutes"),
                                 "comentario": "Tarifa según tarifario (demo)"}
    from .services.distribution import confirm_route
    for r in (r1, r4):  # rutas ya aprobadas: el chofer las ve en «Mis entregas»
        if r is not None:
            try:
                confirm_route(r, dist)
            except Exception as e:  # noqa: BLE001
                res.setdefault("avisos", []).append(f"Ruta #{r.id} sin confirmar: {e}")
    res["rutas_hoy"] = len(rutas)

    # ruta de ayer con pernocte (lo que quedó en el vehículo)
    ayer = Route(fecha=hoy - timedelta(days=1), vehicle_id=veh["DEM-10T"].id, driver_id=drivers["Chofer 5"].id,
                 zona="Callao (demo)", estado="CERRADA", peso_total=6200, peso_real_kg=6350, manual=True,
                 transportista={"tipo": "CHOFER"}, auxiliares=[_u("aux.despacho5").id],
                 pernocte=[{"fotos": [F("pernocte", "Pernocte: 12 sacos en el furgón\npara entregar a primera hora")],
                            "nota": "12 sacos para entregar mañana a primera hora (demo)", "user": "Chofer 5",
                            "ts": (now() - timedelta(hours=14)).isoformat(timespec="minutes")}], creado_por=dist.id)
    s.add(ayer)

    # antecedentes (30 días): sobrecargas de DEM-450 y rutas con tercero (para el análisis y las sugerencias)
    for i in range(1, 9):
        s.add(Route(fecha=hoy - timedelta(days=i * 3), vehicle_id=veh["DEM-450"].id, driver_id=drivers["Chofer 2"].id,
                    zona="Antecedente demo", estado="CERRADA", peso_total=430 if i % 2 else 480,
                    peso_real_kg=470 + i * 5 if i % 2 == 0 else None, creado_por=dist.id))
    for i in range(1, 7):
        s.add(ThirdPartyTransport(proveedor="TRANSPORTES DEMO S.A.C.", tipo_vehiculo="CAMION 2 TN", motivo="DESPACHO VENTA",
                                  origen="ALM-001", destino="Lima (demo)", fecha_servicio=hoy - timedelta(days=i * 8),
                                  monto=850 + i * 20, estado="PAGADO", creado_por=dist.id))

    # ---------------------------------------------------------------- devoluciones por recibir
    alm = _u("coord.almacen")
    devs = []
    for o, tipo in zip(usables[:3], ("PARCIAL", "TOTAL", "PARCIAL")):
        l = o.lines[0]
        r = devoluciones.create_for(o, dist, tipo, lineas=[{"line_id": l.id, "devuelto": max(round(l.cantidad / 4, 2), 1)}])
        if r is not None:
            devs.append(r)
    if len(devs) >= 3:
        devs[1].plazo = hoy - timedelta(days=1)  # vencida: no se recibió a tiempo
        devs[1].ts = now() - timedelta(days=1, hours=3)
        e = devs[2].esperado[0]
        devoluciones.receive(alm, devs[2], {str(e["line_id"]): {"cantidad": e["cantidad"] - 1, "presentacion_ok": "1",
                                                                 "danado": "1", "detalle": "Saco roto (demo)"}},
                             [F("dev", "Devolución: saco roto\n(evidencia de muestra)", (150, 40, 40))],
                             "Llegó un saco menos y otro roto (demo)")
    res["devoluciones"] = len(devs)

    # ---------------------------------------------------------------- tickets («Reportar avería»)
    tks = []
    for user, dest, cat, desc, lugar, urg, foto in (
            ("aux.almacen", "MANTENIMIENTO", "Luz / eléctrico", "Fluorescente quemado en el pasillo", "Almacén Producto Terminado – Zona B", True, "luz"),
            ("asist.produccion", "MANTENIMIENTO", "Máquina de producción", "Ruido anormal en la faja de la Cimbria", "Línea de Selección Automática – Cimbria", False, "cimbria"),
            ("superv.calidad", "MANTENIMIENTO", "Gasfitería / agua", "Fuga en el lavadero de manos", "Selección Manual", False, ""),
            ("vendedor2", "SISTEMAS", "Tintas / tóner", "Se acabó el tóner de la impresora de ventas", "Oficina comercial", False, ""),
            ("coord.finanzas", "SISTEMAS", "Laptop / PC", "La laptop no enciende", "Finanzas", True, ""),
            ("lider.almacen", "SISTEMAS", "Red / internet", "Sin wifi en la zona de despacho", "Despacho", False, "")):
        t = tickets.create(_u(user), dest, cat, f"{desc} ({MARCA})", lugar, urg,
                           [F(f"tk_{foto}", f"Ticket: {desc}", (60, 60, 60))] if foto else [])
        tks.append(t)
    s.flush()
    tickets.assign(jefe_mant, tks[0], tec2.id, "Cambiar hoy (demo)")
    wo_tk = tickets.to_work_order(jefe_mant, tks[1], hoy + timedelta(days=1), tec1.id)
    tickets.set_state(_u("sistemas"), tks[3], "RESUELTO", "Se instaló tóner nuevo (demo)")
    tks[3].ts = now() - timedelta(hours=26)
    tks[3].atendido_ts = now() - timedelta(hours=24)
    res["tickets"] = len(tks)

    # ---------------------------------------------------------------- trabajos de mantenimiento
    zonas = {z.nombre: z for z in limpieza.zones()}
    z = lambda n: zonas[n].id if n in zonas else None  # noqa: E731
    ots = []
    for tipo, titulo, fecha, zona, maq, tec, calidad in (
            ("PREVENTIVO", "Lubricación y revisión de fajas", hoy + timedelta(days=7), None, "CIMBRIA", None, False),
            ("PREVENTIVO", "Calibración de sensores ópticos", hoy + timedelta(days=3), None, "TRUER", tec1.id, False),
            ("PREVENTIVO", "Fumigación del contenedor", hoy, z("Contenedor de fumigación 1"), "", tec2.id, True),
            ("CORRECTIVO", "Cambio de luminarias", hoy, z("Almacén Producto Terminado – Zona B"), "", tec2.id, False),
            ("PREVENTIVO", "Revisión de miniracks y anclajes", hoy - timedelta(days=1), z("Almacén Producto Terminado – Miniracks"), "", tec1.id, False),
            ("PREVENTIVO", "Mantenimiento de mesas de selección", hoy - timedelta(days=3), z("Selección Manual"), "", None, False),
            ("CORRECTIVO", "Reparar puerta corrediza", hoy - timedelta(days=5), z("Almacén Producto Terminado – Zona C"), "", tec1.id, False),
            ("PREVENTIVO", "Limpieza de tolvas", hoy - timedelta(days=2), None, "R1", None, False),
            ("PREVENTIVO", "Ajuste de selladora", hoy + timedelta(days=14), None, "R2", None, False)):
        ots.append(mant_trabajos.save(jefe_mant, {"tipo": tipo, "titulo": titulo, "fecha_programada": fecha, "zone_id": zona,
                                                  "maquina": maq, "asignado_worker_id": tec if fecha >= hoy else None,
                                                  "con_calidad": "1" if calidad else "", "origen": "CRONOGRAMA"}))
    tec_u1, tec_u2 = _u("tecnico.mant1"), _u("tecnico.mant2")
    ots[3].asignado_worker_id = tec2.id
    mant_trabajos.start(tec_u2, ots[3], [F("ot_antes", "ANTES: luminarias apagadas", (90, 90, 90))])
    ots[4].asignado_worker_id = tec1.id
    ots[4].estado = "ASIGNADA"
    mant_trabajos.start(tec_u1, ots[4], [F("ot4_antes", "ANTES: anclaje flojo", (90, 90, 90))])
    mant_trabajos.finish(tec_u1, ots[4], [F("ot4_despues", "DESPUÉS: anclajes ajustados")], "Se ajustaron 8 anclajes (demo)",
                         [{"pieza": "Perno de anclaje", "cantidad": "8", "costo": "40"}], 40)
    ots[4].inicio_ts = now() - timedelta(days=1, hours=3)
    ots[4].fin_ts = now() - timedelta(days=1, hours=1)
    mant_trabajos.check_alerts(hoy)
    res["trabajos"] = len(ots) + 1

    # ---------------------------------------------------------------- máquinas
    jp = _u("jefe.produccion")
    mant_trabajos.log_machine(jefe_mant, "CIMBRIA", "CALIBRACION", "Calibración de cámaras de color (demo)",
                              parametros={"sensibilidad": "72 %", "velocidad de faja": "1.2 m/s"},
                              evidencias=[F("maq_cimbria", "Calibración Cimbria (muestra)")], proxima=hoy + timedelta(days=30))
    mant_trabajos.log_machine(jefe_mant, "TRUER", "CONFIGURACION", "Configuración para quinua (demo)",
                              parametros={"tamiz": "2.0 mm", "caudal": "1 800 kg/h"})
    mant_trabajos.log_machine(jp, "R1", "CAMBIO_PIEZA", "Cambio de mordaza de sellado (demo)", pieza="Mordaza de sellado", costo=180)

    # ---------------------------------------------------------------- paradas de producción con fotos (antecedentes)
    for linea, dias, causa, mins in (("CIMBRIA", 2, "MANTENIMIENTO PREVENTIVO", 180), ("CIMBRIA", 5, "MANTENIMIENTO PREVENTIVO", 150),
                                     ("R1", 1, "REFRIGERIO", 45), ("TRUER", 3, "MANTENIMIENTO PREVENTIVO", 60)):
        ini = datetime.combine(hoy - timedelta(days=dias), datetime.min.time()) + timedelta(hours=9)
        ev = [F(f"parada_{linea}", f"Parada {linea}: {causa}", (120, 60, 0))]
        s.add(ProductionReport(linea=linea, tipo="SELECCION" if linea in ("CIMBRIA", "TRUER") else "ENVASADO",
                               fecha=hoy - timedelta(days=dias), product_code="GR-901" if linea in ("CIMBRIA", "TRUER") else "PT-905",
                               peso_entrada_kg=1000, user_id=_u("asist.produccion").id, estado="PENDIENTE",
                               pausas=[{"inicio": ini.isoformat(timespec="seconds"),
                                        "fin": (ini + timedelta(minutes=mins)).isoformat(timespec="seconds"),
                                        "causa": causa, "foto": ev[0], "evidencias": ev, "user": "Asistente de Producción 1"}]))

    # parte de hoy en la línea R1: en proceso y pausado con foto (cambio de bobina)
    from .services import parte
    try:
        pr = parte.start(_u("asist.produccion"), {"linea": "R1", "product_code": "PT-905", "peso_entrada_kg": 600,
                                                  "lote_pt": "905100DM"})
        s.flush()
        causa = next(iter(parte.causes(pr.tipo)), None)
        if causa:
            parte.pause(_u("asist.produccion"), pr, causa, evidencias=[F("parada_hoy", f"Parada R1: {causa}", (120, 60, 0))])
    except Exception as e:  # noqa: BLE001
        res.setdefault("avisos", []).append(f"Parte de hoy: {e}")
    # fumigaciones y limpiezas registradas en la bitácora de saneamiento (Calidad)
    from .models import SanitationLog
    for nombre, tipo, dias, vence in (("Contenedor de fumigación 1", "FUMIGACION", 20, 10),
                                      ("Contenedor de fumigación 2", "FUMIGACION", 35, -5),
                                      ("Almacén Producto Terminado – Zona A", "FUMIGACION", 12, 18),
                                      ("Selección Manual", "LIMPIEZA", 1, 6)):
        if nombre in zonas:
            s.add(SanitationLog(zone_id=zonas[nombre].id, tipo=tipo, fecha=hoy - timedelta(days=dias),
                                responsable="Empresa de fumigación DEMO" if tipo == "FUMIGACION" else "Limpieza",
                                producto="Fosfina (demo)" if tipo == "FUMIGACION" else "", vence=hoy + timedelta(days=vence),
                                user_id=_u("superv.calidad").id))

    # ---------------------------------------------------------------- limpieza: hoy y la semana pasada
    plan = {lim1.id: [("Almacén Producto Terminado – Zona A", 2), ("Almacén Producto Terminado – Zona B", 2),
                      ("Almacén Producto Terminado – Miniracks", 1)],
            lim2.id: [("Selección Manual", 3), ("Contenedor de fumigación 1", 1), ("Almacén Producto Terminado – Zona C", 1)]}
    for d in range(7, -1, -1):
        fecha = hoy - timedelta(days=d)
        for wid, zs in plan.items():
            for nombre, veces in zs:
                if nombre not in zonas:
                    continue
                c = CleaningAssignment(fecha=fecha, worker_id=wid, zone_id=zonas[nombre].id, veces=veces, turno="Mañana",
                                       user_id=jefe_mant.id)
                hechas = veces if d > 1 else (veces - 1 if d == 1 else (1 if wid == lim1.id else 0))
                if wid == lim2.id and nombre == "Selección Manual" and d > 0:
                    hechas = 1  # zona que suele quedar incompleta (para la sugerencia)
                c.checks = [{"ts": f"{fecha.isoformat()}T{8 + k * 3:02d}:15", "user": "demo", "foto": ""} for k in range(hechas)]
                s.add(c)
    s.flush()
    limpieza.check_unfinished(hoy)

    # ---------------------------------------------------------------- averías repetidas de una unidad
    for i in range(3):
        s.add(Breakdown(vehicle_id=veh["DEM-10T"].id, descripcion=f"Falla de frenos (demo {i + 1})", severidad="MEDIA",
                        estado="CERRADA", ts=now() - timedelta(days=10 + i * 20), user_id=dist.id))

    # ---------------------------------------------------------------- presupuesto: Distribución superado
    b = s.execute(select(AreaBudget).where(AreaBudget.area == "Distribución", AreaBudget.anio == hoy.year)).scalars().first()
    if b is None:
        b = AreaBudget(area="Distribución", anio=hoy.year, estado="APROBADO", creado_por=dist.id)
        s.add(b)
        s.flush()
        s.add(BudgetLine(budget_id=b.id, categoria="COMBUSTIBLE", concepto="Combustible flota propia (demo)",
                         presupuesto={str(m): 8000 for m in range(1, 13)},
                         real={str(m): 8000 * (1.18 if m == hoy.month else 1.0) for m in range(1, hoy.month + 1)}))
        s.add(BudgetLine(budget_id=b.id, categoria="MANTENIMIENTO", concepto="Mantenimiento de flota (demo)",
                         presupuesto={str(m): 3000 for m in range(1, 13)},
                         real={str(m): 3200 for m in range(1, hoy.month + 1)}))
    s.flush()
    from .services import budget
    budget.check_consumption(hoy)

    # ---------------------------------------------------------------- oportunidades para el embudo
    estados = ["ABIERTA", "ABIERTA", "COTIZADA", "COTIZADA", "NEGOCIACION", "NEGOCIACION", "GANADA", "GANADA", "GANADA",
               "PERDIDA", "PERDIDA", "ABIERTA"]
    motivos = {9: "Precio más alto que la competencia", 10: "El cliente no tenía presupuesto"}
    for i, est in enumerate(estados):
        o = Opportunity(customer_id=clientes[i % len(clientes)].id, vendedor_id=(vend if i % 2 else _u("vendedor2")).id,
                        titulo=f"Oportunidad demo {i + 1}", estado=est, proyeccion_mensual=1500 + 500 * i,
                        motivo_cierre=motivos.get(i, ""), creado_ts=now() - timedelta(days=5 + i * 3))
        s.add(o)
        s.flush()
        if i % 3 != 0:
            s.add(CustomerAction(customer_id=o.customer_id, opportunity_id=o.id, tipo="VISITA", fecha=hoy - timedelta(days=i),
                                 resultado="Visita de presentación (demo)", user_id=o.vendedor_id))
    s.flush()
    from .services import sugerencias
    res["sugerencias"] = len(sugerencias.all_suggestions(hoy))
    return res
