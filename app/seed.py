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
    # username, nombre, rol. Una cuenta por persona según los organigramas, con el nombre del puesto (sin nombres reales).
    ("gerente.general", "Gerencia General", "GERENCIA_GENERAL"),
    ("gerente.operaciones", "Gerencia de Operaciones", "GERENCIA_OPERACIONES"),
    ("sistemas", "Administrador de Sistemas", "SISTEMAS"),
    ("gerente.comercial", "Gerente Comercial", "GERENTE_COMERCIAL"),
    ("jefe.ventas", "Jefe Comercial", "JEFE_VENTAS"),
    ("coord.ventas", "Coordinador de Ventas", "COORD_VENTAS"),
    ("asist.ventas", "Asistente de Ventas", "ASIST_VENTAS"),
    ("vendedor1", "Ejecutivo de Ventas 1", "EJECUTIVO_VENTAS"),
    ("vendedor2", "Ejecutivo de Ventas 2", "EJECUTIVO_VENTAS"),
    # Logística (organigrama del 23-oct-2026)
    ("jefe.logistica", "Jefe de Logística", "JEFE_LOGISTICA"),
    ("coord.logistica", "Coordinador de Logística", "COORD_LOGISTICA"),
    ("coord.almacen", "Supervisor de 1524 y 1560", "COORD_ALMACEN"),
    ("coord.almacen.mp", "Coordinación de Almacén 1524", "COORD_ALMACEN_MP"),
    ("superv.almacen", "Supervisor de Almacén 1560", "SUPERV_ALMACEN"),
    ("lider.almacen", "Líder Operativo 1560", "LIDER_ALMACEN"),
    ("aux.almacen", "Auxiliar de Almacén 1", "AUX_ALMACEN"),
    ("aux.almacen2", "Auxiliar de Almacén 2", "AUX_ALMACEN"),
    ("aux.almacen3", "Auxiliar de Almacén 3", "AUX_ALMACEN"),
    ("aux.almacen4", "Auxiliar de Almacén 4", "AUX_ALMACEN"),
    ("montacarguista", "Montacarguista 1", "MONTACARGUISTA"),
    ("lider.almacen2", "Líder Operativo 1560 turno tarde", "LIDER_ALMACEN"),
    ("montacarguista2", "Montacarguista 2 turno tarde", "MONTACARGUISTA"),
    ("superv.almacen.mp", "Supervisor de Almacenes 1524 / Externos", "SUPERV_ALMACEN"),
    ("aux.almacen.mp", "Auxiliar de Almacén 1524", "AUX_ALMACEN"),
    ("montacarguista.mp", "Montacarguista 1524", "MONTACARGUISTA"),
    ("coord.distribucion", "Coordinador de Distribución", "COORD_DISTRIBUCION"),
    ("asist.distribucion", "Asistente de Distribución", "ASIST_DISTRIBUCION"),
    ("conductor1", "Chofer 1", "CONDUCTOR"),
    ("conductor2", "Chofer 2", "CONDUCTOR"),
    ("conductor3", "Chofer 3", "CONDUCTOR"),
    ("conductor4", "Chofer 4", "CONDUCTOR"),
    ("conductor5", "Chofer 5", "CONDUCTOR"),
    ("aux.despacho", "Auxiliar de Despacho 1", "AUX_DESPACHO"),
    ("aux.despacho2", "Auxiliar de Despacho 2", "AUX_DESPACHO"),
    ("aux.despacho3", "Auxiliar de Despacho 3", "AUX_DESPACHO"),
    ("aux.despacho4", "Auxiliar de Despacho 4", "AUX_DESPACHO"),
    ("aux.despacho5", "Auxiliar de Despacho 5", "AUX_DESPACHO"),
    ("jefe.produccion", "Jefe de Producción", "JEFE_PRODUCCION"),
    ("asist.produccion", "Asistente de Producción 1", "ASIST_PRODUCCION"),
    ("asist.produccion2", "Asistente de Producción 2", "ASIST_PRODUCCION"),
    ("jefe.calidad", "Jefe de Calidad", "JEFE_CALIDAD"),
    ("superv.calidad", "Supervisor de Calidad", "SUPERV_CALIDAD"),
    ("asist.calidad", "Asistente de Calidad", "ASIST_CALIDAD"),
    ("compras", "Coordinador de Compras", "COMPRAS"),
    ("importaciones", "Importaciones", "IMPORTACIONES"),
    ("seguridad", "Seguridad", "SEGURIDAD"),
    ("facturacion", "Facturación", "FACTURACION"),
    ("coord.finanzas", "Coordinación de Finanzas", "COORD_FINANZAS"),
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
    n += _retire_permissions()
    n += _apply_alert_role_changes()
    n += _rename_roles()
    n += _rename_demo_users()
    return n


def _apply_alert_role_changes():
    """Cambios de destinatarios de alertas decididos por el usuario (una sola vez; queda en la auditoría)."""
    from .models import AuditLog
    s = db()
    n = 0
    for code, quitar, agregar in getattr(C, "ALERTAS_ROLES_CAMBIO", []):
        clave = f"{code}:-{','.join(quitar)}:+{','.join(agregar)}"[:60]
        if s.execute(select(AuditLog).where(AuditLog.accion == "ALERTA_ROLES_CATALOGO", AuditLog.entidad_id == clave)).first():
            continue
        t = s.get(AlertType, code)
        if t is not None:
            roles = [r for r in (t.roles or []) if r not in quitar] + [r for r in agregar if r not in (t.roles or [])]
            if roles != list(t.roles or []):
                t.roles = roles
                n += 1
        s.add(AuditLog(user_id=None, accion="ALERTA_ROLES_CATALOGO", entidad="AlertType", entidad_id=clave,
                       detalle={"quitar": quitar, "agregar": agregar}))
    s.flush()
    return n


def _rename_roles():
    """Nomenclatura de puestos decidida por el usuario (p. ej. «Supervisor de 1524 y 1560»)."""
    s = db()
    n = 0
    for code, nombre in getattr(C, "ROLES_RENOMBRE", {}).items():
        r = s.get(Role, code)
        if r is not None and r.nombre != nombre:
            r.nombre = nombre
            n += 1
    for u in s.execute(select(User).where(User.username == "coord.almacen")).scalars():
        if u.nombre in ("Coordinador de Almacenes", "Coordinación de Almacén 1560 (demo)"):
            u.nombre = "Supervisor de 1524 y 1560"
            n += 1
    return n


def _retire_permissions():
    """Retira una sola vez las asignaciones que el usuario decidió quitar (C.PERMISOS_RETIRADOS); queda en la auditoría."""
    from .models import AuditLog
    s = db()
    n = 0
    for code, tipo in C.PERMISOS_TIPO.items():
        p = s.get(Permission, code)
        if p is not None and p.tipo != tipo:
            p.tipo = tipo
    for role, perm, fuente in C.PERMISOS_RETIRADOS:
        clave = f"{role}:{perm}"
        if s.execute(select(AuditLog).where(AuditLog.accion == "PERMISO_RETIRADO_CATALOGO",
                                            AuditLog.entidad_id == clave)).first():
            continue
        rp = s.execute(select(RolePermission).where(RolePermission.role_code == role,
                                                    RolePermission.perm_code == perm)).scalars().first()
        if rp is not None:
            s.delete(rp)
            n += 1
        s.add(AuditLog(user_id=None, accion="PERMISO_RETIRADO_CATALOGO", entidad="RolePermission", entidad_id=clave,
                       detalle={"fuente": fuente, "existia": rp is not None}))
    s.flush()
    return n


def _rename_demo_users():
    """Quita «demo» del nombre de las cuentas de ejemplo ya creadas (usa el nombre del puesto). No toca otros usuarios."""
    s = db()
    n = 0
    nombres = {u: nm for u, nm, _ in DEMO_USERS}
    for u in s.execute(select(User).where(User.username.in_(list(nombres)))).scalars():
        if "demo" in (u.nombre or "").lower() and u.nombre != nombres[u.username]:
            u.nombre = nombres[u.username]
            n += 1
    return n


def add_missing_demo_users():
    """Solo para la base de demostración: crea las cuentas de ejemplo que falten (una por puesto del organigrama)."""
    s = db()
    from .services.core import param as _param
    existentes = set(s.execute(select(User.username)).scalars())
    nuevos = []
    for username, nombre, rol in DEMO_USERS:
        if username in existentes or s.get(Role, rol) is None:
            continue
        u = create_user(username, nombre, rol)
        u.aviso_aceptado = {"version": _param("aviso_datos_version", ""), "ts": "demo", "ip": ""}
        u.clave_ts = datetime.now()
        if rol in ("AUX_ALMACEN", "AUX_DESPACHO", "LIDER_ALMACEN", "MONTACARGUISTA", "SUPERV_ALMACEN"):
            u.almacen = "EXT-002" if username.endswith(".mp") else "ALM-001"
        nuevos.append(username)
    return nuevos


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
        if u.role_code in ("AUX_ALMACEN", "AUX_DESPACHO", "LIDER_ALMACEN", "MONTACARGUISTA", "SUPERV_ALMACEN"):
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
    drivers = [Driver(nombre=f"Chofer {i}", licencia=f"Q0000000{i}", user_id=users[f"conductor{i}"].id) for i in (1, 2, 3)]
    drivers.append(Driver(nombre="Chofer externo", licencia="Q00000009", externo=True))
    drivers += [Driver(nombre=f"Chofer {i}", licencia=f"Q0000000{i}", user_id=users[f"conductor{i}"].id) for i in (4, 5)]
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
    from .models import VehicleDocument
    for i, v in enumerate(s.execute(select(Vehicle)).scalars()):  # SOAT ficticio vigente: sin él la unidad no se asigna
        s.add(VehicleDocument(vehicle_id=v.id, tipo="SOAT", numero=f"SOAT-DEMO-{i + 1:03d}", fecha=today - timedelta(days=60),
                              vencimiento=today + timedelta(days=300), estado="VIGENTE", observacion="Dato ficticio"))
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
