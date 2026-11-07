"""Escenario de la simulación integral: 14 días de operación FICTICIA procesados por los servicios del sistema.

ENTORNO DE PRUEBAS. Todo lo que se crea aquí queda registrado en la corrida (``sim_records``) y se elimina con la
limpieza. Datos maestros propios y rotulados (clientes «CLIENTE SIMULADO», productos «SIM-», vehículos «SIM-»,
conductores «Conductor simulado»), para que las transacciones ficticias no reserven ni consuman existencias reales.

Cada paso se ejecuta con el servicio que usaría la persona del área (con su permiso) y a la hora simulada del día. Si un
servicio rechaza el paso, el rechazo se registra (regla de negocio) y el flujo de ese pedido sigue como en la realidad;
si el servicio falla por un error de programación, se registra como falla. No se fuerzan estados.
"""
import random
import traceback
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from .db import db
from .models import (BOMLine, BOMVersion, Customer, Driver, MoveRequest, PickingTask, PriceItem, Product, ProductCost,
                     ProductionLine, ProductionReport, ProductionRequest, Route, SalesOrder, SimRun, StockLot, Transfer,
                     User, Vehicle, VehicleChecklist, Warehouse)
from .services import simulacion as sim
from .services.core import BusinessError, has_perm, param

DOMINGO = 6


# ------------------------------------------------------------------ datos maestros ficticios
PRODUCTOS = [  # código, descripción, peso kg/und, und por bulto, stock inicial, línea sugerida
    ("SIM-PT-01", "ARVEJA PARTIDA SIMULADA * 500 G", 0.5, 20, 5200),
    ("SIM-PT-02", "LENTEJA SIMULADA * 500 G", 0.5, 20, 4600),
    ("SIM-PT-03", "FRIJOL SIMULADO * 1 KG", 1.0, 12, 3200),
    ("SIM-PT-04", "GARBANZO SIMULADO * 5 KG", 5.0, 4, 1500),
    ("SIM-PT-05", "QUINUA SIMULADA * 250 G", 0.25, 40, 450),  # producto con faltantes frecuentes
    ("SIM-PT-06", "PALLAR SIMULADO * 1 KG", 1.0, 12, 2600),
]
MATERIAS = [("SIM-MP-01", "GRANO SIMULADO A GRANEL", 18000), ("SIM-MP-02", "GRANO ANDINO SIMULADO A GRANEL", 6000)]
INSUMO = ("SIM-EN-01", "LAMINA SIMULADA", 60000)
PRECIOS = {"SIM-PT-01": 3.6, "SIM-PT-02": 4.2, "SIM-PT-03": 6.9, "SIM-PT-04": 31.0, "SIM-PT-05": 4.8, "SIM-PT-06": 8.4}
DISTRITOS = ["SIMULACIÓN ZONA NORTE", "SIMULACIÓN ZONA SUR", "SIMULACIÓN ZONA ESTE"]


class Escenario:
    def __init__(self, run, upload_dir, semilla=2026, dias=14, hasta=None):
        self.run = run
        self.up = upload_dir
        self.rnd = random.Random(semilla)
        self.dias = dias
        self.hasta = hasta or date.today()
        self.desde = self.hasta - timedelta(days=dias - 1)
        self.r = {"pasos": Counter(), "rechazos": [], "fallas": [], "no_implementado": [], "notas": [],
                  "conteos": Counter()}
        self.actores = {}
        self.ovs = []
        self.foto = {}

    # ---------------------------------------------------------- utilidades
    def ev(self, nombre):
        if nombre not in self.foto:
            self.foto[nombre] = sim.evidencia(self.up, self.run.id, nombre)
        return self.foto[nombre]

    def paso(self, nombre, fn, *a, **k):
        """Ejecuta un paso con su servicio dentro de un punto de guardado: si falla, solo se deshace ese paso."""
        s = db()
        sp = s.begin_nested()
        try:
            out = fn(*a, **k)
            s.flush()
            sp.commit()
            self.r["pasos"][nombre] += 1
            return out
        except BusinessError as e:
            sp.rollback()
            self.r["rechazos"].append({"paso": nombre, "dia": str(sim.ahora().date()), "detalle": str(e)[:300]})
            return None
        except Exception as e:  # noqa: BLE001
            sp.rollback()
            self.r["fallas"].append({"paso": nombre, "dia": str(sim.ahora().date()), "detalle": f"{type(e).__name__}: {e}"[:300],
                                     "traza": traceback.format_exc(limit=4)[-900:]})
            return None

    def actor(self, perm, almacen=None, excluir_roles=("GERENCIA_GENERAL", "SISTEMAS")):
        """Primer usuario activo (no simulado) con el permiso; con almacén, del alcance de ese almacén."""
        clave = (perm, almacen)
        if clave in self.actores:
            return self.actores[clave]
        u = None
        for x in db().execute(select(User).where(User.activo.is_(True)).order_by(User.id)).scalars():
            if x.username.startswith("sim.") or x.role_code in excluir_roles:
                continue
            if has_perm(x, perm) and (almacen is None or not x.almacen or x.almacen == almacen
                                      or almacen in (x.almacen or "").split(",")):
                u = x
                break
        if u is None:
            self.r["no_implementado"].append(f"No hay usuario activo con el permiso «{perm}»"
                                             + (f" para el almacén {almacen}" if almacen else "") + ": el paso no se simula.")
        self.actores[clave] = u
        return u

    def dias_operativos(self):
        d = self.desde
        while d <= self.hasta:
            if d.weekday() != DOMINGO:
                yield d
            d += timedelta(days=1)

    def siguiente_operativo(self, d, n=1):
        while n > 0:
            d += timedelta(days=1)
            if d.weekday() != DOMINGO:
                n -= 1
        return d

    # ---------------------------------------------------------- maestros
    def maestros(self):
        from werkzeug.security import generate_password_hash
        s = db()
        sim.fijar_hora(self.desde - timedelta(days=1), 7)
        ventas = self.actor("ov.crear")
        vendedores = [u for u in s.execute(select(User).where(User.activo.is_(True), User.role_code == "EJECUTIVO_VENTAS")).scalars()
                      if not u.username.startswith("sim.")] or ([ventas] if ventas else [])
        canales = sorted({c for c in s.execute(select(PriceItem.canal).where(PriceItem.lista == "GENERAL",
                                                                            PriceItem.vigente.is_(True))).scalars() if c})
        if not canales:
            canales = ["SIMULACION"]
            self.r["notas"].append("No hay lista de precios vigente: los clientes simulados usan el canal «SIMULACION».")
        self.canales = canales
        self.clientes = []
        for i in range(12):
            c = Customer(ruc=f"2099900{i + 1:04d}", nombre=f"CLIENTE SIMULADO {i + 1:02d} S.A.C.", grupo="SIMULACIÓN",
                         direccion=f"Av. Ficticia {100 + i * 10}", distrito=DISTRITOS[i % 3], provincia="SIMULACIÓN",
                         horario_recepcion=["08:00-12:00", "09:00-17:00", "07:00-13:00"][i % 3],
                         canal_precio=canales[i % len(canales)], condicion_pago="CREDITO" if i % 3 else "CONTADO",
                         credito_dias=30 if i % 3 else None, condicion_estado="APROBADA",
                         vendedor_id=vendedores[i % len(vendedores)].id if vendedores else None,
                         vida_util_min_dias=None, observaciones="Cliente ficticio de la simulación (ENTORNO DE PRUEBAS).")
            s.add(c)
            self.clientes.append(c)
        self.productos = []
        for code, desc, peso, bulto, _stock in PRODUCTOS:
            p = Product(code=code, descripcion=desc, um="UNIDAD", peso_kg=peso, unidades_por_bulto=bulto, tipo="PT",
                        familia="PRODUCTO TERMINADO", subfamilia="SIMULACIÓN", producto_base=desc.split(" *")[0],
                        presentacion=desc.split("* ")[-1], marca="MARCA SIMULADA")
            s.add(p)
            self.productos.append(p)
        for code, desc, _stock in MATERIAS:
            s.add(Product(code=code, descripcion=desc, um="KILOGRAMO", peso_kg=1, tipo="MP", familia="MATERIA PRIMA",
                          subfamilia="SIMULACIÓN", producto_base=desc))
        s.add(Product(code=INSUMO[0], descripcion=INSUMO[1], um="UNIDAD", tipo="INSUMO", familia="INSUMOS"))
        s.flush()
        # lista de precios y costo (para margen e indicadores de precio)
        for p in self.productos:
            for canal in canales:
                s.add(PriceItem(lista="GENERAL", product_code=p.code, descripcion=p.descripcion, canal=canal,
                                precio=PRECIOS[p.code], vigente=True, origen="SIMULACIÓN"))
            s.add(ProductCost(product_code=p.code, descripcion=p.descripcion, costo=round(PRECIOS[p.code] * 0.78, 3),
                              unidad="UND", origen="SIMULACIÓN"))
        # lista de materiales: se agrega a la versión activa (si no hay, se crea una para la simulación)
        from .services.production import active_bom
        v = active_bom()
        if v is None:
            v = BOMVersion(version=0, archivo="simulacion", activa=True)
            s.add(v)
            s.flush()
            self.r["notas"].append("No había lista de materiales activa: se creó una versión solo para la simulación.")
        for p in self.productos:
            mp = "SIM-MP-02" if "QUINUA" in p.descripcion else "SIM-MP-01"
            for comp, desc, cant, um in ((mp, "GRANO SIMULADO", round(p.peso_kg * 1.03, 4), "KG"),
                                         (INSUMO[0], INSUMO[1], 1, "UND")):
                s.add(BOMLine(version_id=v.id, padre=p.code, padre_desc=p.descripcion, tipo_bom="P", cantidad_bom=1,
                              componente=comp, componente_desc=desc, cantidad=cant, um=um))
        # flota y conductores simulados
        self.vehiculos, self.conductores = [], []
        for i, cap in enumerate((3500, 5000, 8000, 3000, 6000, 4000)):
            u = User(username=f"sim.conductor{i + 1}", nombre=f"Conductor simulado {i + 1}", role_code="CONDUCTOR",
                     password_hash=generate_password_hash(f"no-login-{self.rnd.random()}"), activo=True)
            s.add(u)
            s.flush()
            d = Driver(nombre=u.nombre, licencia=f"SIM-LIC-{i + 1:03d}", user_id=u.id, documento=f"9999000{i}")
            v = Vehicle(placa=f"SIM-{i + 1:03d}", descripcion=f"Camión simulado {cap / 1000:g} t", propio=True,
                        capacidad_kg=cap, km_actual=40000 + 7000 * i, marca="SIMULADA", modelo="FICTICIO", anio=2022,
                        tipo_unidad="CAMION")
            s.add_all([d, v])
            s.flush()
            v.conductor_habitual_id = d.id
            from .models import VehicleDocument
            for tipo in ("SOAT", "REVISION_TECNICA", "TARJETA_CIRCULACION"):
                s.add(VehicleDocument(vehicle_id=v.id, tipo=tipo, numero=f"SIM-{tipo[:3]}-{i + 1:03d}",
                                      fecha=self.desde - timedelta(days=90), vencimiento=self.hasta + timedelta(days=270),
                                      estado="VIGENTE"))
            self.vehiculos.append(v)
            self.conductores.append(d)
        s.flush()
        # existencias iniciales: almacén principal y una parte en el alternativo (para traslados)
        from .services.stock import add_or_increase_lot, alternative_warehouses, principal_warehouses
        alt = alternative_warehouses()
        self.alt = alt[0].code if alt else None
        f0 = self.desde - timedelta(days=1)
        for code, _d, _p, _b, stock in PRODUCTOS:
            p = s.get(Product, code)
            whs = principal_warehouses(p)
            if not whs:
                self.r["no_implementado"].append(f"Sin almacén principal configurado para {code}.")
                continue
            self.pt_wh = whs[0].code
            add_or_increase_lot(code, whs[0].code, f"SIM{code[-2:]}A", stock, "DISPONIBLE", f0 + timedelta(days=300),
                                f0 - timedelta(days=20), origen="SIM-STOCK-INICIAL")
            add_or_increase_lot(code, whs[0].code, f"SIM{code[-2:]}B", round(stock * 0.25), "DISPONIBLE",
                                f0 + timedelta(days=200), f0 - timedelta(days=60), origen="SIM-STOCK-INICIAL")
            if self.alt:
                add_or_increase_lot(code, self.alt, f"SIM{code[-2:]}X", round(stock * 0.3), "DISPONIBLE",
                                    f0 + timedelta(days=250), f0 - timedelta(days=30), origen="SIM-STOCK-INICIAL")
        for code, _d, stock in MATERIAS + [INSUMO]:
            p = s.get(Product, code)
            whs = principal_warehouses(p)
            if whs:
                self.mp_wh = whs[0].code
                add_or_increase_lot(code, whs[0].code, f"SIM{code[-2:]}M", stock, "DISPONIBLE", f0 + timedelta(days=360),
                                    f0 - timedelta(days=10), origen="SIM-STOCK-INICIAL")
        if not self.alt:
            self.r["notas"].append("No hay almacén alternativo habilitado: no se simulan traslados entre almacenes.")
        s.flush()
        self.r["conteos"].update({"clientes": len(self.clientes), "productos": len(self.productos) + 3,
                                  "vehiculos": len(self.vehiculos), "conductores": len(self.conductores)})

    # ---------------------------------------------------------- comercial
    def tamano(self):
        x = self.rnd.random()
        return "GRANDE" if x < 0.1 else ("MEDIANO" if x < 0.42 else "PEQUENO")

    def crear_ovs(self, d):
        from .services.orders import create_order, resolve_delivery
        ventas = self.actor("ov.crear")
        if ventas is None:
            return
        n = self.rnd.randint(7, 10)
        for k in range(n):
            sim.fijar_hora(d, 8, 5 + k * 9)
            c = self.rnd.choice(self.clientes)
            t = self.tamano()
            rango = {"PEQUENO": (6, 40), "MEDIANO": (50, 140), "GRANDE": (220, 480)}[t]
            prods = self.rnd.sample(self.productos, self.rnd.choice((1, 1, 2, 2, 3)))
            if t == "GRANDE" and self.rnd.random() < 0.5:
                prods = [p for p in prods] + ([self.productos[4]] if self.productos[4] not in prods else [])
            lineas = [{"product_code": p.code, "cantidad": float(self.rnd.randint(*rango)),
                       "precio_unitario": round(PRECIOS[p.code] * self.rnd.choice((1.0, 1.02, 1.05, 1.08)), 2)}
                      for p in prods]
            plazo = self.rnd.choice((1, 2, 2, 3, 3, 4, 5, 6, 9))
            comp = self.siguiente_operativo(d, plazo)
            o = self.paso("OV registrada", create_order, ventas, "", c.id, comp, lineas,
                          vendedor_id=c.vendedor_id, entrega=resolve_delivery(c, exigir=False),
                          oc_archivo=self.ev("orden_de_compra"), oc_numero=f"OC-SIM-{d:%m%d}-{k + 1}",
                          comentarios=f"Pedido {t.lower()} de la simulación")
            if o is not None:
                o.fecha_emision = d
                self.ovs.append((o, t))
                self.r["conteos"]["ov"] += 1
                self.r["conteos"][f"ov_{t.lower()}"] += 1

    def atender_faltantes(self, d):
        """Respuesta de Logística a las OV incompletas: producción, traslado del almacén alternativo o despacho parcial."""
        from .services import orders as osvc
        from .services import production as prod
        from .services import transfers as trs
        from .services.stock import free_qty, line_reserved, lots_of
        sim.fijar_hora(d, 10, 30)
        jl = self.actor("ov.aprobar_parcial")
        sol_tr = self.actor("traslado.solicitar") or jl
        ventas = self.actor("ov.crear")
        jp = self.actor("produccion.validar") or self.actor("produccion.programar")
        gg = self.actor("ov.decision_gg", excluir_roles=("SISTEMAS",))
        for o, t in list(self.ovs):
            if o.estado == "BLOQUEADA" and not getattr(o, "_sim_gg", False):
                o._sim_gg = True
                if self.paso("Decisión de Gerencia General solicitada", osvc.request_gg_decision, o, ventas,
                             "El cliente necesita el pedido en esa fecha para su campaña (simulación)") is not None and gg:
                    aprueba = self.rnd.random() < 0.6
                    self.paso("Decisión de Gerencia General", osvc.decide_gg, o, gg, aprueba,
                              "Priorizar producción (simulación)" if aprueba else "No procede: reprogramar con el cliente",
                              "ALTA" if aprueba else "NORMAL")
                continue
            if o.estado in ("CANCELADA", "DESPACHADA", "ENTREGADA") or o.estado_stock != "INCOMPLETA" and o.estado_stock != "SIN_STOCK":
                continue
            if getattr(o, "_sim_atendida", False) or o.fecha_compromiso <= d:
                continue
            o._sim_atendida = True
            x = self.rnd.random()
            faltan = [(l, l.cantidad - line_reserved(l)) for l in o.lines if l.activa and l.cantidad - line_reserved(l) > 1e-9]
            if x < 0.45 and jp is not None:  # producción
                for l, q in faltan:
                    req = self.paso("Solicitud de producción", prod.create_request, l.product_code, round(q * 1.1), ventas,
                                    order=o, fecha_requerida=o.fecha_compromiso - timedelta(days=1))
                    if req is None:
                        continue
                    self.paso("Solicitud de producción enviada", prod.send_request, req, ventas)
                    plazo_ok = self.rnd.random() > 0.2
                    entrega = None if plazo_ok else o.fecha_compromiso
                    self.paso("Solicitud de producción validada", prod.validate_request, req, jp, True, True, True, True,
                              plazo_ok, "Validado en la simulación" if plazo_ok else "Plazo ajustado por carga de línea",
                              entrega)
                    fecha = max(self.siguiente_operativo(d), o.fecha_compromiso - timedelta(days=2))
                    if fecha.weekday() == DOMINGO:
                        fecha = self.siguiente_operativo(fecha)
                    self.programar(req, jp, fecha)
                    self.r["conteos"]["solicitudes_produccion"] += 1
            elif x < 0.65 and self.alt:  # traslado del almacén alternativo
                for l, q in faltan:
                    lot = next((z for z in lots_of(l.product_code, [self.alt]) if free_qty(z) > 0), None)
                    if lot is None:
                        continue
                    cant = min(free_qty(lot), q)
                    tr = self.paso("Traslado solicitado", trs.request_transfer, sol_tr, lot.id, self.pt_wh, cant, order=o,
                                   observacion="Cubrir faltante de la OV (simulación)")
                    if tr is not None:
                        self.r["conteos"]["traslados"] += 1
            elif x < 0.85 and jl is not None and any(line_reserved(l) > 0 for l in o.lines):  # despacho parcial aprobado con saldo reprogramado
                self.paso("Despacho parcial aprobado", osvc.decide_partial, o, jl, True, "Cliente acepta parcial (simulación)",
                          self.siguiente_operativo(o.fecha_compromiso, 3))
            # el resto queda con faltante: se ve en Pendientes y en los indicadores

    def programar(self, req, jp, fecha):
        """Programa en la primera línea y día con capacidad (hasta 4 días después); si no hay, queda validada sin programar."""
        from .services import production as prod
        for k in range(4):
            for linea in self.rnd.sample(self.lineas_env, len(self.lineas_env)):
                s = db()
                sp = s.begin_nested()
                try:
                    prod.schedule(req, jp, linea, fecha)
                    sp.commit()
                    self.r["pasos"]["Producción programada"] += 1
                    return True
                except BusinessError as e:
                    sp.rollback()
                    ultimo_error = str(e)
            fecha = self.siguiente_operativo(fecha)
        self.r["rechazos"].append({"paso": "Producción programada", "dia": str(sim.ahora().date()),
                                   "detalle": f"Sin capacidad en 4 días: {ultimo_error}"[:300]})
        return False

    def traslados(self, d):
        from .services import transfers as trs
        for tr in db().execute(select(Transfer).where(Transfer.id.in_(sim.ids_creados(self.run.id, "transfers")))).scalars():
            if tr.estado == "SOLICITADO":
                sim.fijar_hora(d, 9, 15)
                jl = next((u for u in db().execute(select(User).where(User.activo.is_(True)).order_by(User.id)).scalars()
                           if has_perm(u, "traslado.autorizar") and u.id != tr.solicitado_por
                           and u.role_code not in ("GERENCIA_GENERAL", "SISTEMAS") and not u.username.startswith("sim.")), None)
                self.paso("Traslado autorizado", trs.authorize, tr, jl, True, "Autorizado (simulación)",
                          datetime.combine(d, datetime.min.time()) + timedelta(hours=15))
            if tr.estado == "AUTORIZADO":
                sim.fijar_hora(d, 11, 0)
                self.paso("Traslado despachado", trs.ship, tr, self.actor("traslado.salida", tr.lot.warehouse_code))
            elif tr.estado == "EN_TRANSITO" and d < self.hasta:
                sim.fijar_hora(d, 16, 0)
                dif = 2 if self.rnd.random() < 0.2 else 0
                self.paso("Traslado recibido", trs.receive, tr, self.actor("traslado.recibir", tr.destino_code),
                          tr.cantidad - dif, "Diferencia de conteo (simulación)" if dif else "")

    # ---------------------------------------------------------- producción
    def produccion(self, d, ultimo):
        from .services import parte as pt
        from .services import production as prod
        from .services import quality as qual
        jp = self.actor("produccion.programar") or self.actor("produccion.validar")
        asis = self.actor("produccion.liquidar")
        alm = self.actor("produccion.recibir_pt") or self.actor("traslado.recibir", self.pt_wh)
        cal = self.actor("calidad.liberar")
        reqs = list(db().execute(select(ProductionRequest).where(
            ProductionRequest.id.in_(sim.ids_creados(self.run.id, "production_requests")))).scalars())
        for req in reqs:  # terminan las que empezaron antes (liquidación, recepción y liberación)
            if req.estado == "EN_PROCESO" and req.inicio_ts and req.inicio_ts.date() < d:
                sim.fijar_hora(d, 7, 30)
                parte = db().execute(select(ProductionReport).where(ProductionReport.of == f"PS-{req.id}")).scalars().first()
                rend = self.rnd.uniform(0.9, 1.0) if self.rnd.random() > 0.15 else self.rnd.uniform(0.7, 0.85)
                hechos = round(req.cantidad * rend)
                if parte is not None and parte.estado in ("EN PROCESO", "PAUSADO"):
                    kg = req.cantidad * (req.product.peso_kg or 1)
                    parte.peso_entrada_kg = parte.peso_entrada_kg or round(kg * 1.04, 1)
                    parte.presentacion_kg = parte.presentacion_kg or req.product.peso_kg
                    self.paso("Parte de producción finalizado", pt.finish, asis, parte, {
                        "operarios": self.rnd.randint(4, 8), "unidades": hechos, "refrigerio_min": 30,
                        "desmedro_kg": round(kg * self.rnd.uniform(0.005, 0.03), 1),
                        "observacion": "" if rend > 0.89 else "Rendimiento bajo por atoros en la línea (simulación)"})
                self.paso("Producción finalizada", prod.finish, req, jp)
                liq = self.paso("Liquidación registrada", prod.register_liquidation, asis, f"SIM-LIQ-{req.id}",
                                req.product_code, hechos, f"SIMP{req.id:03d}", fecha_fab=d, fecha_venc=d + timedelta(days=365),
                                request=req, origen="MANUAL", horas=round(self.rnd.uniform(5, 9), 1),
                                operarios=self.rnd.randint(4, 8), mp_kg=round(hechos * (req.product.peso_kg or 1) * 1.03, 1),
                                fecha=d)
                self.r["conteos"]["planificado_und"] += req.cantidad
                self.r["conteos"]["producido_und"] += hechos
                if liq is not None and liq.estado == "REGISTRADA":
                    sim.fijar_hora(d, 9, 0)
                    dif = 0 if self.rnd.random() > 0.15 else self.rnd.randint(1, 6)
                    self.paso("Producto terminado recibido en almacén", prod.receive_pt, liq, alm, hechos - dif, True,
                              "Faltan paquetes en el pallet (simulación)" if dif else "")
                    if liq.lot_id and cal is not None:
                        sim.fijar_hora(d, 10, 0)
                        self.paso("Lote liberado por Calidad", qual.release_lot, db().get(StockLot, liq.lot_id), cal, True, "Conforme (simulación)")
        for req in reqs:  # empiezan las programadas para hoy
            if req.estado == "PROGRAMADA" and req.fecha_programada == d:
                sim.fijar_hora(d, 7, 0)
                self.paso("Producción iniciada", prod.start, req, jp)
                parte = db().execute(select(ProductionReport).where(ProductionReport.of == f"PS-{req.id}")).scalars().first()
                if parte is not None:
                    parte.peso_entrada_kg = round(req.cantidad * (req.product.peso_kg or 1) * 1.04, 1)
                    parte.presentacion_kg = req.product.peso_kg
                    if self.rnd.random() < 0.2:
                        sim.fijar_hora(d, 10, 20)
                        causas = pt.causes(parte.tipo)
                        if causas:
                            self.paso("Parada de línea registrada", pt.pause, asis, parte, causas[0], self.ev("parada_de_linea"))
                            if not ultimo:
                                sim.fijar_hora(d, 11, 5)
                                self.paso("Línea reanudada", pt.resume, asis, parte, "Se corrigió (simulación)")
        if not ultimo:  # partes programados a futuro (ocupación de líneas)
            pass

    # ---------------------------------------------------------- almacén: picking
    def picking(self, d, ultimo):
        from .services import picking as pk
        from .services import orders as osvc
        from .services.orders import prep_progress
        lider = self.actor("picking.asignar")
        prep = self.actor("preparacion.registrar") or lider
        antes = int(param("dias_picking_antes_despacho", 1) or 0)
        for o, t in self.ovs:
            if o.estado not in ("EVALUADA", "EN_PREPARACION") or o.retenida_precio:
                continue
            if not (o.estado_stock == "COMPLETA" or o.decision_parcial == "APROBADA"):
                continue
            objetivo = o.fecha_compromiso - timedelta(days=antes)
            if objetivo.weekday() == DOMINGO:
                objetivo -= timedelta(days=1)
            if d < objetivo:
                continue
            sim.fijar_hora(d, 12 if d == objetivo else 7, self.rnd.randint(0, 50))
            if not getattr(o, "_sim_plan", False):
                self.paso("Planificación de picking validada", osvc.validate_picking_plan, o, prep)
                o._sim_plan = True
            tareas = pk.tasks_of(o) or self.paso("Picking programado", pk.preschedule, o, lider, d) or []
            for tk in tareas:
                if tk.estado == "LISTO":
                    continue
                if not tk.asignados:
                    gente = [u for u in pk.staff(tk.warehouse_code) if not u.username.startswith("sim.")]
                    if gente:
                        self.paso("Picking asignado", pk.assign, tk, lider, [self.rnd.choice(gente).id], fecha=d)
                if ultimo and self.rnd.random() < 0.35:
                    continue  # pendiente de picking hoy
                ejecutor = lider
                if tk.estado == "PROGRAMADO":
                    self.paso("Picking iniciado", pk.start, tk, ejecutor, self.ev("picking_inicio"))
                if tk.estado != "EN_PROCESO":
                    continue
                if ultimo and self.rnd.random() < 0.4:
                    continue  # en preparación ahora
                from .models import PickingRecord
                if db().execute(select(PickingRecord.id).where(PickingRecord.task_id == tk.id)).first() is not None:
                    continue  # ya registrado (picking con diferencia en revisión)
                diferencia = self.rnd.random() < 0.08
                for l in o.lines:
                    for res in [r for r in l.reservations if r.estado == "ACTIVA" and r.lot.warehouse_code == tk.warehouse_code]:
                        cant = res.cantidad - (min(3, res.cantidad - 1) if diferencia and res.cantidad > 3 else 0)
                        self.paso("Picking registrado (lote y cantidad)", pk.record, tk, ejecutor, l.id, cant, res.lot.lote,
                                  comentario="Faltan unidades en la ubicación (simulación)" if cant < res.cantidad else "")
                if diferencia:
                    tk.observacion = (tk.observacion + "\n" if tk.observacion else "") + \
                        "Diferencia: menos unidades que las reservadas (simulación)."
                    self.r["conteos"]["picking_con_diferencia"] += 1
                    continue
                if prep_progress(o) >= 100 - 1e-9:
                    self.paso("Picking terminado (zona de despacho)", pk.finish, tk, ejecutor, self.ev("picking_listo"))
            if o.estado == "PREPARADA":
                self.r["conteos"]["ov_preparadas"] += 1

    # ---------------------------------------------------------- montacargas
    def montacargas(self, d, ultimo):
        from .services import supply as sp
        sol = self.actor("movimiento.solicitar")
        if sol is None:
            return
        ejecutores = [u for u in sp.move_executors() if not u.username.startswith("sim.")]
        for k in range(self.rnd.randint(2, 4)):
            sim.fijar_hora(d, 8 + k * 2, 10)
            m = self.paso("Movimiento solicitado al montacarguista", sp.request_move, sol, "PRODUCCIÓN" if k % 2 else "RACK A",
                          "ZONA DE DESPACHO" if k % 2 else "RACK B", detalle="Pallet de producto simulado",
                          cantidad=str(self.rnd.randint(1, 4)) + " pallets", prioridad=self.rnd.choice(("ALTA", "MEDIA", "BAJA")),
                          asignado_id=self.rnd.choice(ejecutores).id if ejecutores else None)
            if m is None or (ultimo and k >= 1):
                continue
            ej = m.operador or self.actor("movimiento.ejecutar")
            avanzar = sim.avanzar
            avanzar(15)
            self.paso("Movimiento iniciado", sp.start_move, ej, m, self.ev("montacargas_inicio"))
            avanzar(self.rnd.randint(10, 40))
            self.paso("Movimiento terminado", sp.finish_move, ej, m, self.ev("montacargas_fin"))

    # ---------------------------------------------------------- distribución
    def despachar(self, d, ultimo):
        from .services import despacho as dsp
        from .services import distribution as dist
        from .services import quality as qual
        from .services import vehicle_checklist as vc
        from .models import Certificate
        coord = self.actor("distribucion.programar")
        guia = self.actor("distribucion.guia_modificar") or coord
        seg = self.actor("distribucion.checklist_validar")
        aux = self.actor("distribucion.conformidad_producto")
        fact = self.actor("facturacion.cargar")
        cal = self.actor("calidad.certificado_revisar")
        lider = self.actor("distribucion.confirmar_salida")
        listas = [o for o, t in self.ovs if o.estado == "PREPARADA" and o.fecha_compromiso <= d]
        if not listas:
            return
        sim.fijar_hora(d, 13, 30)
        rutas = {}
        for o in listas:
            st = dist.active_stop(o)
            if st is None:
                r = self.paso("Ruta programada", dist.propose_routes, o.fecha_compromiso, coord, orders=[o],
                              require_prepared=True, automatico=True)
                st = dist.active_stop(o)
            if st is not None:
                rutas[st.route.id] = st.route
        por_zona = defaultdict(list)
        for r in rutas.values():
            if r.estado == "PROPUESTA":
                por_zona[r.zona].append(r)
        for zona, rs in por_zona.items():  # Distribución consolida las paradas de la misma zona en una unidad
            base = rs[0]
            for otra in rs[1:]:
                for st in list(otra.stops):
                    if (base.peso_total or 0) + (st.peso_kg or 0) <= max(v.capacidad_kg for v in self.vehiculos):
                        self.paso("Parada movida a otra ruta (consolidación)", dist.move_stop, st, coord, base)
        for r in rutas.values():
            if r.estado != "PROPUESTA" or not r.stops:
                continue
            sin_prep = [st for st in r.stops if st.order.estado not in ("PREPARADA", "PROGRAMADA")]
            if sin_prep:
                if len(sin_prep) == len(r.stops):
                    continue
                destino = next((x for x in rutas.values() if x is not r and x.estado == "PROPUESTA" and x.zona == r.zona
                                and all(st.order.estado not in ("PREPARADA", "PROGRAMADA") for st in x.stops)), None)
                if destino is None:
                    destino = next((x for x in db().execute(select(Route).where(
                        Route.id.in_(sim.ids_creados(self.run.id, "routes")), Route.estado == "PROPUESTA", Route.id != r.id,
                        Route.zona == r.zona)).scalars() if not x.stops), None)
                for st in sin_prep:
                    if destino is not None:
                        self.paso("Pedido sin preparar separado de la ruta", dist.move_stop, st, coord, destino)
                if any(st.order.estado not in ("PREPARADA", "PROGRAMADA") for st in r.stops):
                    continue  # sale cuando terminen de preparar (retraso)
            if r.fecha != d:
                r.fecha = d  # salida reprogramada al día de hoy (pedido atrasado)
            ocup_v, ocup_d = dist._busy(d)
            libres = [(v, dr) for v, dr in zip(self.vehiculos, self.conductores) if v.id not in ocup_v and dr.id not in ocup_d
                      and v.capacidad_kg >= (r.peso_total or 0)]
            if not libres:
                r.advertencias = (r.advertencias or []) + ["Sin unidad libre hoy: sale el siguiente día (simulación)."]
                r.fecha = self.siguiente_operativo(d)
                self.r["conteos"]["rutas_sin_unidad"] += 1
                continue
            v, dr = libres[0]
            self.paso("Vehículo y conductor asignados", dist.update_route, r, coord, vehicle_id=v.id, driver_id=dr.id)
            if self.rnd.random() < 0.08 and not ultimo:
                r.advertencias = (r.advertencias or []) + ["Salida postergada: unidad en mantenimiento (simulación)."]
                self.r["conteos"]["rutas_postergadas"] += 1
                continue
            self.paso("Ruta confirmada", dist.confirm_route, r, coord)
            if r.estado != "CONFIRMADA":
                continue
            chofer = db().get(User, r.driver.user_id) if r.driver and r.driver.user_id else None
            sim.fijar_hora(d, 14, 0)
            vals = {code: ("M" if (self.rnd.random() < 0.05 and not nn) else "B") for code, _z, _i, nn in vc.items()}
            obs = "Llanta de repuesto con poca presión (simulación)" if "M" in vals.values() else ""
            c = self.paso("Checklist vehicular de salida", vc.register, chofer, r, "SALIDA", vals,
                          km=(r.vehicle.km_actual or 0) + 3, observaciones=obs)
            if c is not None:
                self.paso("Checklist de salida validado por Seguridad", vc.validate, seg, c, True, (r.vehicle.km_actual or 0) + 3)
            self.paso("Foto del vehículo", dsp.add_photo, r, aux, "vehiculo", self.ev("vehiculo"))
            self.paso("Foto inicio de carga", dsp.add_photo, r, seg, "inicio_carga", self.ev("inicio_carga"))
            lineas = [{**e, "guia": e["esperado"], "cargado": e["esperado"], "presentacion_ok": True} for e in dist.expected_lines(r)]
            self.paso("Seguridad: carga contra guía", dist.register_security_check, r, seg, f"SIM-T001-{r.id:05d}", lineas)
            self.paso("Foto mercadería cargada", dsp.add_photo, r, aux, "mercaderia_cargada", self.ev("mercaderia_cargada"))
            self.paso("Foto salida del vehículo", dsp.add_photo, r, chofer, "vehiculo_salida", self.ev("vehiculo_salida"))
            self.paso("Chofer revisa la carga", dsp.driver_check_load, r, chofer, {})
            self.paso("Carga validada", dsp.validate_load, r, r.auxiliar if r.auxiliar_id else aux, {})
            for st in r.stops:
                self.paso("Guía de remisión (contingencia simulada)", dsp.set_guide, st, guia, "", "SISTEMA")
                self.paso("Factura registrada (número ficticio)", dsp.set_invoice, st, fact, f"SIM-F001-{st.order.id:06d}",
                          self.ev("factura_ficticia"))
                for cert in db().execute(select(Certificate).where(Certificate.order_id == st.order.id,
                                                                   Certificate.estado == "BORRADOR")).scalars():
                    cambios = {f"org_{i}_resultado": "CONFORME" for i in range(3)}
                    cambios.update({"hum_resultado": "12%", "hum_conclusion": "CONFORME", "tamano_lote": "1000 kg",
                                    "fecha_analisis": d.isoformat()})
                    self.paso("Certificado de calidad aprobado", qual.review_certificate, cert, cal, cambios, True)
            self.paso("Seguridad revisa documentos", dsp.review_documents, r, seg, True)
            self.paso("Visto bueno del chofer", dsp.give_exit_ok, r, chofer)
            sim.fijar_hora(d, 15, self.rnd.randint(0, 40))
            self.paso("Salida confirmada", dist.confirm_departure, r, lider, {k: True for k, _ in dist.CHECKLIST})
            if r.estado == "EN_RUTA":
                self.r["conteos"]["rutas_salieron"] += 1

    def entregar(self, d, ultimo):
        from .services import despacho as dsp
        from .services import distribution as dist
        from .services import vehicle_checklist as vc
        seg = self.actor("distribucion.checklist_validar")
        rutas = list(db().execute(select(Route).where(Route.id.in_(sim.ids_creados(self.run.id, "routes")),
                                                      Route.estado == "EN_RUTA", Route.fecha <= d)).scalars())
        for r in rutas:
            if ultimo and self.rnd.random() < 0.6:
                continue  # en ruta ahora mismo
            chofer = db().get(User, r.driver.user_id) if r.driver and r.driver.user_id else None
            hora = 16
            for st in list(r.stops):
                if st.estado not in ("EN_CAMINO", "LLEGADA"):
                    continue
                sim.fijar_hora(d, hora, self.rnd.randint(0, 50))
                hora = min(hora + 1, 20)
                self.paso("Llegada al cliente", dist.register_arrival, st, chofer)
                x = self.rnd.random()
                if x < 0.07:  # entrega fallida: el cliente no recibe
                    self.paso("Entrega fallida (incidencia)", dist.register_incident, chofer, "CLIENTE_AUSENTE",
                              "Cliente no recibió: local cerrado (simulación)", stop=st, order=st.order, entrega="NINGUNA")
                    self.r["conteos"]["entregas_fallidas"] += 1
                    continue
                if x < 0.17:  # entrega parcial
                    l = next((l for l in st.order.lines if l.activa and l.despachado > 1), None)
                    if l is not None:
                        dev = max(1, round(l.despachado * 0.2))
                        self.paso("Entrega parcial (incidencia)", dist.register_incident, chofer, "PRODUCTO_ROTO",
                                  "Cliente rechazó parte por empaque dañado (simulación)", stop=st, order=st.order,
                                  entrega="PARCIAL", lineas=[{"line_id": l.id, "product_code": l.product_code,
                                                              "recibido": l.despachado - dev, "devuelto": dev,
                                                              "motivo": "Empaque dañado"}])
                        self.r["conteos"]["entregas_parciales"] += 1
                self.paso("Conformidad de entrega", dist.register_delivery, st, chofer, self.ev("entrega"), self.ev("guia_firmada"),
                          receptor_nombre=f"Receptor Simulado {st.id}", receptor_dni=f"{70000000 + st.id:08d}",
                          firma_path=self.ev("firma"))
                if st.estado == "ENTREGADO" or st.order.estado == "ENTREGADA":
                    self.r["conteos"]["entregas_completas"] += 1
            sim.fijar_hora(d, 20, 30)
            from .services import incidents_flow as inc
            from .models import Incident
            for i in db().execute(select(Incident).where(Incident.route_id == r.id)).scalars():
                if inc.needs_part2(i) and not (i.parte2 or {}).get("ts"):
                    vuelve = [{"producto": l.product_code, "cantidad": l.despachado if i.entrega == "NINGUNA"
                               else max(1, round(l.despachado * 0.2))} for l in (i.order.lines if i.order else []) if l.activa][:1]
                    self.paso("Incidencia: mercadería que vuelve (paso 2)", inc.register_part2, chofer, i, vuelve,
                              "Retorno al almacén (simulación)")
            if chofer is not None:
                self.paso("Foto del vehículo al retorno", dsp.add_photo, r, chofer, "vehiculo_retorno", self.ev("vehiculo_retorno"))
            if r.estado in ("EN_RUTA", "CERRADA") and chofer is not None:
                c = self.paso("Checklist vehicular de retorno", vc.register, chofer, r, "RETORNO",
                              {code: "B" for code, _z, _i, _n in vc.items()}, km=(r.km_salida or 0) + self.rnd.randint(25, 140))
                if c is not None:
                    self.paso("Checklist de retorno validado por Seguridad", vc.validate, seg, c, True, c.km)
                self.paso("Retorno registrado", dsp.register_return, r, self.actor("distribucion.carga") or seg,
                          c.km if c is not None else None)

    # ---------------------------------------------------------- inventario, calidad e incidencias
    def inventario(self, d, i):
        from .services import inventory as inv
        from .services.stock import change_lot_state, lots_of
        if i == 4 and getattr(self, "pt_wh", None):  # conteo cíclico con diferencias
            sim.fijar_hora(d, 17, 0)
            u = self.actor("stock.conteo", self.pt_wh)
            v = next((x for x in db().execute(select(User).where(User.activo.is_(True))).scalars()
                      if not x.username.startswith("sim.") and inv.can_validate(x)), None)
            if v is None:
                self.r["no_implementado"].append("No hay usuario que valide conteos (permiso «conteo.validar»).")
            c = self.paso("Conteo físico abierto", inv.open_count, u, self.pt_wh, "", "Conteo cíclico (simulación)",
                          codigos=[p.code for p in self.productos[:3]]) if u is not None else None
            if c is not None:
                vals = {}
                for ln in c.lines:
                    dif = self.rnd.choice((0, 0, -2, 1))
                    vals[str(ln.id)] = {"conteo": (ln.sap or 0) + dif,
                                        "comentario": "Diferencia en el conteo (simulación)" if dif else ""}
                self.paso("Conteo físico registrado", inv.save_lines, c, u, vals)
                self.paso("Conteo cerrado", inv.close_count, c, u)
                if v is not None:
                    self.paso("Conteo validado (ajuste de diferencias)", inv.validate_count, c, v, True, "Ajuste (simulación)")
        if i == 7:  # lote infestado: queda observado y no se reserva
            sim.fijar_hora(d, 9, 40)
            cal = self.actor("calidad.liberar") or self.actor("stock.observar")
            lot = next(iter(lots_of("SIM-PT-06", [self.pt_wh])), None) if getattr(self, "pt_wh", None) else None
            if lot is not None and cal is not None:
                self.paso("Lote infestado observado", change_lot_state, lot, "OBSERVADO", cal,
                          "Presencia de gorgojo en la inspección (simulación)", _calidad=True)
                self.r["conteos"]["lotes_infestados"] += 1

    # ---------------------------------------------------------- tareas del día siguiente: partes programados
    def programar_partes(self, d):
        from .services import parte as pt
        asis = self.actor("produccion.liquidar")
        for k, linea in enumerate(self.lineas_env[:2]):
            f = self.siguiente_operativo(d, k + 1)
            p = self.productos[k]
            self.paso("Parte programado", pt.program, asis, {"linea": linea, "product_code": p.code, "fecha": f,
                                                               "peso_entrada_kg": 800 + 200 * k, "presentacion_kg": p.peso_kg,
                                                               "hora_inicio": "07:00", "hora_fin": "15:00", "turno": "MAÑANA",
                                                               "of": f"SIM-OF-{f:%m%d}-{k + 1}"})

    def lineas_hoy(self, d):
        """Hoy: partes programados e iniciados en las líneas de envasado (lo que se ve en el monitoreo)."""
        from .services import parte as pt
        asis = self.actor("produccion.liquidar")
        for k, linea in enumerate(self.lineas_env[:3]):
            p = self.productos[(k + 2) % len(self.productos)]
            sim.fijar_hora(d, 6, 40)
            r = self.paso("Parte programado para hoy", pt.program, asis, {
                "linea": linea, "product_code": p.code, "fecha": d, "peso_entrada_kg": 1200 + 300 * k,
                "presentacion_kg": p.peso_kg, "hora_inicio": "07:00", "hora_fin": "16:00", "turno": "MAÑANA",
                "of": f"SIM-OF-{d:%m%d}-H{k + 1}"})
            if r is None:
                continue
            sim.fijar_hora(d, 7, 5 + k * 10)
            self.paso("Parte iniciado (línea trabajando ahora)", pt.start, asis, {
                "peso_entrada_kg": 1200 + 300 * k, "lote_pt": f"{900 + k}", "maquinista": "Operario simulado",
                "turno": "MAÑANA"}, r)

    # ---------------------------------------------------------- ejecución
    def ejecutar(self, progreso=None):
        from .services import stock as stk
        s = db()
        self.maestros()
        s.commit()
        from .catalogs import PRODUCTION_LINES
        env = [c for c, _n, tipo in PRODUCTION_LINES if "ENV" in str(tipo).upper() or c.startswith("R")]
        activas = {l.code for l in s.execute(select(ProductionLine).where(ProductionLine.activa.is_(True))).scalars()}
        self.lineas_env = [c for c in env if c in activas] or sorted(activas)[:2]
        if not self.lineas_env:
            self.r["no_implementado"].append("No hay líneas de producción activas: no se simula producción.")
        dias = list(self.dias_operativos())
        for i, d in enumerate(dias):
            ultimo = d == self.hasta
            sim.fijar_hora(d, 6, 30)
            self.paso("Reserva diferida activada (plazo 7 días)", stk.activate_deferred, None, d)
            self.traslados(d)
            if self.lineas_env:
                self.produccion(d, ultimo)
            self.crear_ovs(d)
            self.atender_faltantes(d)
            self.picking(d, ultimo)
            self.montacargas(d, ultimo)
            self.despachar(d, ultimo)
            self.entregar(d, ultimo)
            self.inventario(d, i)
            if ultimo and self.lineas_env:
                self.lineas_hoy(d)
                self.programar_partes(d)
            s.commit()
            if progreso:
                progreso(i + 1, len(dias), d)
        return self.r


def generar(user, upload_dir, dias=14, semilla=2026, hasta=None, progreso=None):
    """Crea una corrida y genera el escenario. Devuelve la corrida (SimRun)."""
    from .services.core import audit
    from .services.simulacion import corrida, habilitada
    motivo = habilitada()
    if motivo:
        raise BusinessError(motivo)
    s = db()
    if s.execute(select(SimRun).where(SimRun.estado.in_(("GENERANDO", "GENERADA", "FALLIDA")))).first():
        raise BusinessError("Ya hay una simulación cargada: límpiela antes de volver a generarla.")
    hasta = hasta or date.today()
    run = SimRun(estado="GENERANDO", dias=dias, semilla=semilla, desde=hasta - timedelta(days=dias - 1), hasta=hasta,
                 user_id=user.id if user else None)
    s.add(run)
    s.commit()
    esc = Escenario(run, upload_dir, semilla, dias, hasta)
    try:
        with corrida(run.id):
            r = esc.ejecutar(progreso)
        run.estado = "GENERADA"
    except Exception as e:  # noqa: BLE001
        s.rollback()
        run = s.get(SimRun, run.id)
        run.estado = "FALLIDA"
        esc.r["fallas"].append({"paso": "Simulación", "dia": "", "detalle": f"{type(e).__name__}: {e}"[:300],
                                "traza": traceback.format_exc(limit=6)[-1500:]})
        r = esc.r
    run.resumen = {"pasos": dict(r["pasos"]), "rechazos": r["rechazos"][:400], "fallas": r["fallas"][:200],
                   "no_implementado": sorted(set(r["no_implementado"])), "notas": r["notas"], "conteos": dict(r["conteos"]),
                   "rechazos_total": len(r["rechazos"]), "fallas_total": len(r["fallas"])}
    run.fin_ts = datetime.now().replace(microsecond=0)
    audit(user, "SIMULACION_GENERADA", "SimRun", run.id, {"estado": run.estado, "dias": dias})
    s.commit()
    return run
