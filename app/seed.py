"""Carga de catálogos (desde app/catalogs.py) y de datos FICTICIOS de demostración."""
import os
import tempfile
from datetime import datetime, date, timedelta

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from . import catalogs as C
from .db import db
from .models import (AlertType, Customer, Driver, GGAlertPreference, ImportPhaseTemplate, LeadTime, Param, Permission,
                     Product, ProductionLine, Role, RolePermission, User, Vehicle, Warehouse)

DEMO_PASSWORD = "Demo2026!"

DEMO_USERS = [
    # username, nombre, rol
    ("gerente.general", "Gerencia General (demo)", "GERENCIA_GENERAL"),
    ("gerente.operaciones", "Gerencia de Operaciones (demo)", "GERENCIA_OPERACIONES"),
    ("sistemas", "Administrador de Sistemas (demo)", "SISTEMAS"),
    ("gerente.comercial", "Gerente Comercial (demo)", "GERENTE_COMERCIAL"),
    ("jefe.ventas", "Jefe de Ventas (demo)", "JEFE_VENTAS"),
    ("coord.ventas", "Coordinador de Ventas (demo)", "COORD_VENTAS"),
    ("asist.ventas", "Asistente de Ventas (demo)", "ASIST_VENTAS"),
    ("vendedor1", "VENDEDOR DEMO UNO", "EJECUTIVO_VENTAS"),
    ("vendedor2", "VENDEDOR DEMO DOS", "EJECUTIVO_VENTAS"),
    ("coord.almacen", "Coordinación de Almacén 1560 (demo)", "COORD_ALMACEN"),
    ("coord.almacen.mp", "Coordinación de Almacén 1524 (demo)", "COORD_ALMACEN_MP"),
    ("superv.almacen", "Supervisión de Almacén (demo)", "SUPERV_ALMACEN"),
    ("lider.almacen", "Líder Operativo (demo)", "LIDER_ALMACEN"),
    ("aux.almacen", "Auxiliar de Almacén (demo)", "AUX_ALMACEN"),
    ("montacarguista", "Montacarguista (demo)", "MONTACARGUISTA"),
    # dotación por almacén (observaciones al demo v0.6): 1560 con 4 auxiliares, 2 líderes y 2 montacarguistas;
    # 1524 con 1 auxiliar y 1 montacarguista. Nombres ficticios.
    ("lider.almacen2", "Líder Operativo 2 (demo)", "LIDER_ALMACEN"),
    ("aux.almacen2", "Auxiliar de Almacén 2 (demo)", "AUX_ALMACEN"),
    ("aux.almacen3", "Auxiliar de Almacén 3 (demo)", "AUX_ALMACEN"),
    ("aux.almacen4", "Auxiliar de Almacén 4 (demo)", "AUX_ALMACEN"),
    ("montacarguista2", "Montacarguista 2 (demo)", "MONTACARGUISTA"),
    ("aux.almacen.mp", "Auxiliar de Almacén 1524 (demo)", "AUX_ALMACEN"),
    ("montacarguista.mp", "Montacarguista 1524 (demo)", "MONTACARGUISTA"),
    ("coord.distribucion", "Coordinador de Distribución (demo)", "COORD_DISTRIBUCION"),
    ("asist.distribucion", "Asistente de Distribución (demo)", "ASIST_DISTRIBUCION"),
    ("conductor1", "Conductor Demo Uno", "CONDUCTOR"),
    ("aux.despacho", "Auxiliar de Despacho (demo)", "AUX_DESPACHO"),
    ("jefe.logistica", "Jefatura de Logística (demo)", "JEFE_LOGISTICA"),
    ("coord.logistica", "Coordinación de Logística (demo)", "COORD_LOGISTICA"),
    ("jefe.produccion", "Jefatura de Producción (demo)", "JEFE_PRODUCCION"),
    ("asist.produccion", "Asistente de Producción (demo)", "ASIST_PRODUCCION"),
    ("asist.produccion2", "Asistente de Producción 2 (demo)", "ASIST_PRODUCCION"),
    ("jefe.calidad", "Jefatura de Calidad (demo)", "JEFE_CALIDAD"),
    ("superv.calidad", "Supervisor de Calidad (demo)", "SUPERV_CALIDAD"),
    ("asist.calidad", "Asistente de Calidad (demo)", "ASIST_CALIDAD"),
    ("compras", "Coordinador de Compras (demo)", "COMPRAS"),
    ("importaciones", "Importaciones (demo)", "IMPORTACIONES"),
    ("seguridad", "Seguridad (demo)", "SEGURIDAD"),
    ("facturacion", "Facturación (demo)", "FACTURACION"),
    ("coord.finanzas", "Coordinación de Finanzas (demo)", "COORD_FINANZAS"),
]


def seed_catalogs():
    s = db()
    if s.execute(select(Role)).first():
        return False
    for code, nombre, area, fuente, obs in C.ROLES:
        s.add(Role(code=code, nombre=nombre, area=area, fuente=fuente, observacion=obs))
    for code, nombre, modulo, tipo in C.PERMISSIONS:
        s.add(Permission(code=code, nombre=nombre, modulo=modulo, tipo=tipo))
    s.flush()
    for role, perms in C.ROLE_PERMISSIONS.items():
        seen = {}
        for perm, origen, fuente in perms:
            # DEFINIDO prevalece sobre PROPUESTO si el permiso aparece dos veces
            if perm in seen and seen[perm][0] == "DEFINIDO":
                continue
            seen[perm] = (origen, fuente)
        for perm, (origen, fuente) in seen.items():
            s.add(RolePermission(role_code=role, perm_code=perm, origen=origen, fuente=fuente))
    for code, nombre, area, grupo, prio, roles, origen, fuente, cond, correo in C.ALERT_TYPES:
        s.add(AlertType(code=code, nombre=nombre, area=area, grupo=grupo, prioridad=prio, roles=roles,
                        origen_destinatarios=origen, fuente=fuente, condicion=cond, enviar_correo=correo,
                        naturaleza="INFORMATIVA" if code in C.ALERT_INFORMATIVAS else "TAREA"))
    for key, valor, tipo, grupo, desc, estado, fuente in C.PARAMS:
        s.add(Param(key=key, valor={"v": valor}, tipo=tipo, grupo=grupo, descripcion=desc, estado=estado, fuente=fuente))
    for code, nombre, uso, prio, res, fuente, obs in C.WAREHOUSES:
        s.add(Warehouse(code=code, nombre=nombre, uso=uso, prioridad=prio, reservable=res, fuente=fuente, observacion=obs))
    for cat, dmin, dmax, md, mh, desc in C.LEAD_TIMES:
        s.add(LeadTime(categoria=cat, dias_min=dmin, dias_max=dmax, mes_desde=md, mes_hasta=mh, descripcion=desc,
                       fuente="Informe Funcional §7"))
    cap = {g["lineas"][0]: g["kg_dia"] for g in next(v for k, v, *_ in C.PARAMS if k == "capacidad_lineas")
           if len(g["lineas"]) == 1}  # las líneas de un grupo compartido usan la capacidad del grupo
    for code, nombre, fuente in C.PRODUCTION_LINES:
        s.add(ProductionLine(code=code, nombre=nombre, fuente=fuente, capacidad_kg_dia=cap.get(code)))
    for orden, nombre, dias, rec, rol in C.DEMO_IMPORT_PHASES:
        s.add(ImportPhaseTemplate(orden=orden, nombre=nombre, dias_desde_inicio=dias, recordatorio_dias=rec,
                                  responsable_rol=rol, estado_def="DEMO"))
    s.flush()
    return True



def sync_catalogs():
    """Agrega a una base existente los roles, permisos, asignaciones, tipos de alerta y parámetros nuevos del catálogo,
    sin modificar lo que ya fue configurado (no destructivo). Devuelve cuántos registros agregó."""
    s = db()
    n = 0
    for code, nombre, area, fuente, obs in C.ROLES:
        if s.get(Role, code) is None:
            s.add(Role(code=code, nombre=nombre, area=area, fuente=fuente, observacion=obs))
            n += 1
    for code, nombre, modulo, tipo in C.PERMISSIONS:
        if s.get(Permission, code) is None:
            s.add(Permission(code=code, nombre=nombre, modulo=modulo, tipo=tipo))
            n += 1
    s.flush()
    existentes = {(rp.role_code, rp.perm_code) for rp in s.execute(select(RolePermission)).scalars()}
    for role, perms in C.ROLE_PERMISSIONS.items():
        for perm, origen, fuente in perms:
            if (role, perm) not in existentes:
                s.add(RolePermission(role_code=role, perm_code=perm, origen=origen, fuente=fuente))
                existentes.add((role, perm))
                n += 1
    for code, nombre, area, grupo, prio, roles, origen, fuente, cond, correo in C.ALERT_TYPES:
        if s.get(AlertType, code) is None:
            s.add(AlertType(code=code, nombre=nombre, area=area, grupo=grupo, prioridad=prio, roles=roles,
                            origen_destinatarios=origen, fuente=fuente, condicion=cond, enviar_correo=correo,
                            naturaleza="INFORMATIVA" if code in C.ALERT_INFORMATIVAS else "TAREA"))
            n += 1
    for key, valor, tipo, grupo, desc, estado, fuente in C.PARAMS:
        if s.get(Param, key) is None:
            s.add(Param(key=key, valor={"v": valor}, tipo=tipo, grupo=grupo, descripcion=desc, estado=estado, fuente=fuente))
            n += 1
    s.flush()
    return n

def _hash_opts():
    m = os.environ.get("PASSWORD_HASH_METHOD")  # solo para acelerar pruebas automatizadas
    return {"method": m} if m else {}


def create_user(username, nombre, role, password=DEMO_PASSWORD, email=None):
    s = db()
    u = User(username=username, nombre=nombre, role_code=role, email=email or f"{username}@demo.local",
             password_hash=generate_password_hash(password, **_hash_opts()))
    s.add(u)
    s.flush()
    if role == "GERENCIA_GENERAL":
        for t in C.GG_DIRECT_DEFAULT:
            s.add(GGAlertPreference(user_id=u.id, type_code=t, recibir_directo=True))
    return u


def seed_demo(upload_dir=None, today=None):
    """Usuarios por rol, clientes, flota y datos de stock/BOM/salidas FICTICIOS cargados por el flujo real de cargas."""
    from .demo_data import INSUMOS, PRODUCTS, write_all
    from .services import uploads
    s = db()
    today = today or date.today()
    if s.execute(select(User)).first():
        return False
    users = {u: create_user(u, n, r) for u, n, r in DEMO_USERS}
    from .services.core import param as _param
    for _u in users.values():  # demostración: aviso de datos aceptado (los usuarios reales lo aceptan al primer ingreso)
        _u.aviso_aceptado = {"version": _param("aviso_datos_version", ""), "ts": "demo", "ip": ""}
        _u.clave_ts = datetime.now()
    for u in users.values():  # almacén del personal operativo (para programar el picking)
        if u.role_code in ("AUX_ALMACEN", "AUX_DESPACHO", "LIDER_ALMACEN", "MONTACARGUISTA"):
            u.almacen = "EXT-002" if u.username.endswith(".mp") else "ALM-001"
    admin = users["sistemas"]
    # parámetros de demostración (marcados DEMO; no son valores aprobados)
    for key, val in (("cortes_preparacion", ["09:00", "13:00", "16:00"]), ("dias_vencimiento_proximo", 30)):
        p = s.get(Param, key)
        p.valor = {"v": val}
        p.estado = "DEMO"
    # clientes ficticios
    clientes = [
        ("20000000001", "CLIENTE DEMO MAYORISTA S.A.C.", "MAYORISTA", "AV. DEMO 100", "ATE", "08:00-12:00", False, None),
        ("20000000002", "CLIENTE DEMO RESTAURANTES S.A.C.", "HOTELES - RESTAURANTES", "JR. DEMO 200", "SURCO", "09:00-11:00", True, 120),
        ("20000000003", "CLIENTE DEMO AUTOSERVICIOS S.A.", "AUTOSERVICIOS", "AV. PRUEBA 300", "PUNTA HERMOSA", "07:00-10:00", True, 180),
        ("20000000004", "CLIENTE DEMO CATERING E.I.R.L.", "CATERING", "CALLE FICTICIA 400", "ATE", "10:00-16:00", False, None),
        ("20000000005", "CLIENTE DEMO INSTITUCIONAL S.A.C.", "INSTITUCIONAL", "AV. EJEMPLO 500", "CALLAO", "08:00-17:00", False, None),
    ]
    for ruc, nombre, grupo, dirc, dist, hor, cita, vida in clientes:
        s.add(Customer(ruc=ruc, nombre=nombre, grupo=grupo, direccion=dirc, distrito=dist, provincia="LIMA",
                       horario_recepcion=hor, requiere_cita=cita, vida_util_min_dias=vida))
    # flota ficticia (capacidades tomadas de la tabla de transportes; placas y nombres inventados)
    drivers = [Driver(nombre="Conductor Demo Uno", licencia="Q00000001", user_id=users["conductor1"].id),
               Driver(nombre="Conductor Demo Dos", licencia="Q00000002"),
               Driver(nombre="Conductor Demo Tres", licencia="Q00000003"),
               Driver(nombre="Conductor Externo Demo", licencia="Q00000004", externo=True)]
    s.add_all(drivers)
    s.flush()
    s.add_all([
        Vehicle(placa="DEM-450", descripcion="Unidad liviana (demo)", propio=True, capacidad_kg=450,
                conductor_habitual_id=drivers[3].id, observacion="Conductor externo"),
        Vehicle(placa="DEM-4T5", descripcion="Camión 4.5 TN (demo)", propio=True, capacidad_kg=4500, conductor_habitual_id=drivers[0].id),
        Vehicle(placa="DEM-10T", descripcion="Camión 10 TN (demo)", propio=True, capacidad_kg=10000, conductor_habitual_id=drivers[1].id),
        Vehicle(placa="DEM-25T", descripcion="Camión 25 TN (demo)", propio=True, capacidad_kg=25000, conductor_habitual_id=drivers[2].id),
        Vehicle(placa="TER-2T", descripcion="Transporte externo 2 TN (demo)", propio=False, capacidad_kg=2000, disponible=True),
    ])
    s.flush()
    # archivos ficticios procesados por el mismo flujo de validación/autorización
    folder = upload_dir or tempfile.mkdtemp(prefix="demo_")
    files = write_all(folder, today)
    # Cada carga la autoriza el rol responsable (Sistemas administra pero no aprueba, decisión Q4)
    for tipo, key, opts, quien in (("PRODUCTOS", "productos", {}, "sistemas"), ("STOCK", "stock", {}, "coord.almacen"),
                                   ("BOM", "bom", {"incluye_merma": "NO"}, "jefe.produccion"),
                                   ("SALIDAS", "salidas", {}, "coord.almacen"),
                                   ("PRECIOS", "precios", {}, "jefe.ventas"),
                                   ("PRECIOS_GRANEL", "precios_granel", {}, "jefe.ventas"),
                                   ("CLIENTES_CONDICIONES", "clientes", {}, "jefe.ventas")):
        b = uploads.create_batch(users[quien], tipo, files[key], os.path.basename(files[key]))
        uploads.confirm(b, users[quien], opts)
    # completar catálogo de insumos y parámetros por producto
    for code, desc, cat in INSUMOS:
        p = s.get(Product, code)
        if p is None:
            p = Product(code=code, descripcion=desc)
            s.add(p)
        p.tipo = "INSUMO" if not code.startswith("RE-") else ""
        p.um = "KILOGRAMO" if code.startswith("EN-") else "UNIDAD"
        p.categoria_reposicion = cat
    for code, *_rest, cat in PRODUCTS:
        p = s.get(Product, code)
        p.categoria_reposicion = cat
        if code.startswith("MP") or code.startswith("GR"):
            p.grupo_humedad = "QUINUA_CANIHUA_MOTE" if code.startswith("GR") else "OTROS"
    s.get(Product, "PT-901").producto_base = "ARVEJA VERDE PARTIDA"
    s.get(Product, "PT-902").producto_base = "ARVEJA VERDE PARTIDA"
    s.get(Product, "PT-906").producto_base = "ARVEJA VERDE PARTIDA"
    s.flush()
    return {"usuarios": len(users), "archivos": files}
