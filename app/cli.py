"""Comandos de administración.

    python -m app.cli init            # crea tablas y catálogos (sin datos de demostración)
    python -m app.cli demo            # crea tablas, catálogos y datos FICTICIOS de demostración
    python -m app.cli reset-demo      # BORRA la base local y recrea la demostración (solo SQLite local)
    python -m app.cli sap-probar      # prueba la conexión con SAP Service Layer (solo lectura)
    python -m app.cli sap-traer TIPO USUARIO   # trae de SAP un tipo de dato y crea la carga para revisar
    python -m app.cli verificar       # ejecuta verificaciones periódicas (alertas automáticas, correo)
    python -m app.cli esquema         # compara la base con el modelo del código (tablas/columnas que faltan o sobran)
    python -m app.cli crear-usuario <usuario> <rol> <nombre> <email>
    python -m app.cli usuarios        # lista los usuarios (usuario, nombre, perfil, correo, activo)
    python -m app.cli cargas          # últimas cargas (tipo, estado, filas con error) y quién las confirma
    python -m app.cli carga <n>       # errores y advertencias de la carga n.° n
    python -m app.cli sap-diagnostico # lectura de SAP, maestros, almacenes, cola de OV y estado de la conexión
    python -m app.cli sap-series      # series de las órdenes de venta en SAP y cuáles cuentan como órdenes de servicio
    python -m app.cli sap-consulta-stock  # crea en SAP la consulta guardada del stock por lote (solo la consulta)
    python -m app.cli eliminar-usuario <usuario> [--confirmar]  # borra un usuario creado por error (o lo da de baja si tiene registros)
    python -m app.cli clave <usuario> # asigna una contraseña nueva (la pide en pantalla; se cambia en el primer ingreso)
    python -m app.cli muestras <carpeta>   # genera los Excel ficticios de ejemplo
    python -m app.cli demo-dia        # agrega un día de operación FICTICIO con todas las casuísticas y el flujo completo
                                      # (historial de OV, OV en cada estado, producción, proyección; sobre la demostración)
    python -m app.cli simulacion generar|validar|estado|limpiar|regenerar [usuario]
                                      # ENTORNO DE PRUEBAS: 14 días de operación ficticia por los servicios del sistema,
                                      # validación integral y limpieza de SOLO lo simulado
    python -m app.cli depurar [--aplicar]  # fotos de entrega más antiguas que la retención configurada (sin --aplicar: solo lista)
"""
import getpass
import os
import sys

from . import create_app
from .db import SessionLocal, drop_all


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    os.environ["CHECK_INTERVAL_MIN"] = "0"  # los comandos de consola no arrancan el hilo de verificaciones
    app = create_app()
    with app.app_context():
        s = SessionLocal()
        from .seed import seed_catalogs, seed_demo
        if cmd == "init":
            if seed_catalogs():
                print("Catálogos creados")
            else:
                from .seed import sync_catalogs
                n = sync_catalogs()
                s.commit()
                print(f"Catálogos ya existían; se agregaron {n} registros nuevos del catálogo (sin modificar lo configurado)")
        elif cmd in ("demo", "reset-demo"):
            if cmd == "reset-demo":
                if not app.config["DATABASE_URL"].startswith("sqlite"):
                    print("reset-demo solo se permite sobre SQLite local.")
                    return 2
                drop_all()
                from .db import create_all
                create_all()
            seed_catalogs()
            r = seed_demo(os.path.join(app.instance_path, "demo_files"))
            if r:
                print("Demostración creada")
            else:
                from .seed import _rename_demo_users, add_missing_demo_users
                nuevos = add_missing_demo_users()
                ren = _rename_demo_users()
                s.commit()
                print(f"Ya existía la demostración; cuentas agregadas: {', '.join(nuevos) or 'ninguna'}; nombres actualizados: {ren}")
        elif cmd == "demo-dia":
            from .demo_dia import seed_operation_day
            from .seed import add_missing_demo_users
            seed_catalogs()
            if seed_demo(os.path.join(app.instance_path, "demo_files")) is False:
                add_missing_demo_users()
            from .seed import sync_catalogs
            sync_catalogs()
            s.commit()
            r = seed_operation_day(app.config["UPLOAD_DIR"])
            s.commit()
            print("Ya estaba cargado el día de operación." if r is None else f"Día de operación ficticio creado: {r}")
            from .demo_flujo import seed_flow  # V23: flujo completo (historial, OV en cada estado, producción, proyección)
            f = seed_flow(app.config["UPLOAD_DIR"])
            s.commit()
            print("Ya estaba cargado el flujo completo." if f is None else f"Flujo completo ficticio creado: {f}")
            from .demo_flujo import seed_v24  # V24: compras nacionales, importaciones, costos y tipo de cambio
            v = seed_v24(app.config["UPLOAD_DIR"])
            s.commit()
            print("Ya estaban cargados los datos V24." if v is None else f"Datos V24 ficticios creados: {v}")
            from .demo_quincena import seed_quincena  # 15 días en que todas las áreas ya registraron
            q = seed_quincena(app.config["UPLOAD_DIR"])
            s.commit()
            print("Ya estaban cargados los 15 días de operación." if q is None else f"15 días de operación ficticios: {q}")
        elif cmd == "depurar":
            from .services.retention import purge_photos
            r = purge_photos(app.config["UPLOAD_DIR"], aplicar="--aplicar" in argv)
            s.commit()
            print(r)
        elif cmd == "sap-probar":
            from .services import sap_sl
            print(sap_sl.test_connection())
        elif cmd == "sap-traer":
            # sap-traer TIPO USUARIO: trae de SAP (solo lectura) y crea la carga con el perfil del usuario indicado
            if len(argv) < 3:
                print("Uso: sap-traer <OV|CLIENTES|PRODUCTOS|DESPACHOS|STOCK|LIQUIDACION> <usuario>")
                return 2
            from sqlalchemy import select
            from .models import User
            from .services import sap_sl
            u = s.execute(select(User).where(User.username == argv[2])).scalars().first()
            if u is None:
                print("Usuario no encontrado")
                return 2
            b = sap_sl.sync(argv[1].upper(), u, app.config["UPLOAD_DIR"])
            s.commit()
            print(f"Carga #{b.id}: {b.estado} ({len(b.rows)} filas)")
        elif cmd == "esquema":
            from alembic.autogenerate import compare_metadata
            from alembic.migration import MigrationContext
            from . import db as dbmod
            from .models import Base
            with dbmod.engine.connect() as c:
                ctx = MigrationContext.configure(c)
                dif = [d for d in compare_metadata(ctx, Base.metadata)
                       if not (isinstance(d, tuple) and d[0] in ("add_index", "remove_index"))]
                print(f"Versión de migración registrada: {ctx.get_current_revision() or 'NINGUNA'}")
            if dif:
                print("Diferencias entre la base y el código:")
                for d in dif:
                    d = d[0] if isinstance(d, list) else d
                    k, o = d[0], d[-1] if d[0] != "add_column" else d[3]
                    if k == "add_table":
                        print(f"   falta la tabla {o.name}")
                    elif k == "remove_table":
                        print(f"   sobra la tabla {o.name} (no está en el código)")
                    elif k == "add_column":
                        print(f"   falta la columna {d[2]}.{o.name}")
                    elif k == "remove_column":
                        print(f"   sobra la columna {d[2]}.{d[3].name}")
                    else:
                        print(f"   {k}: {d[1:4]}")
                return 1
            print("La base coincide con el código.")
        elif cmd == "verificar":
            from .services.scheduler import run_checks
            print(run_checks())
        elif cmd == "crear-usuario":
            if len(argv) < 5:
                print("Uso: crear-usuario <usuario> <rol> <nombre> <email>")
                return 2
            from .seed import create_user
            pwd = getpass.getpass("Contraseña: ")
            from .services.core import param
            minimo = int(param("clave_longitud_minima", 8) or 8)
            if len(pwd) < minimo:
                print(f"La contraseña debe tener al menos {minimo} caracteres.")
                return 2
            u = create_user(argv[1], argv[3], argv[2], pwd, argv[4])
            u.debe_cambiar_clave = True  # la cambia en su primer ingreso
            print("Usuario creado")
        elif cmd == "usuarios":
            from sqlalchemy import select
            from .models import User
            print(f"{'USUARIO':<24}{'PERFIL':<24}{'ACTIVO':<8}{'NOMBRE':<32}CORREO")
            for u in s.execute(select(User).order_by(User.username)).scalars():
                print(f"{u.username:<24}{u.role_code:<24}{'sí' if u.activo else 'no':<8}{(u.nombre or '')[:30]:<32}{u.email or ''}")
        elif cmd == "eliminar-usuario":
            # 09-nov-2026: quitar usuarios creados por error. Si el usuario no tiene ningún registro asociado se BORRA;
            # si tiene (auditoría, OV, alertas…) se DA DE BAJA: queda inactivo y con el nombre liberado, para no perder
            # la trazabilidad. Sin --confirmar solo muestra lo que haría.
            if len(argv) < 2:
                print("Uso: eliminar-usuario <usuario> [--confirmar]")
                return 2
            from sqlalchemy import func, select
            from .models import Base, User
            from .services.core import audit
            u = s.execute(select(User).where(User.username == argv[1])).scalars().first()
            if u is None:
                print("Usuario no encontrado. Vea la lista con: python -m app.cli usuarios")
                return 2
            if u.role_code == "SISTEMAS" and u.activo and s.execute(select(func.count()).select_from(User).where(
                    User.role_code == "SISTEMAS", User.activo.is_(True))).scalar() <= 1:
                print("Es la única cuenta de Sistemas activa: cree otra antes de quitar esta.")
                return 2
            refs = []
            for t in Base.metadata.sorted_tables:
                if t.name == "users":
                    continue
                for col in t.columns:
                    if any(fk.column.table.name == "users" for fk in col.foreign_keys):
                        n = s.execute(select(func.count()).select_from(t).where(col == u.id)).scalar() or 0
                        if n:
                            refs.append(f"{t.name}.{col.name}: {n}")
            print(f"Usuario {u.username} ({u.nombre}, {u.role_code}, {'activo' if u.activo else 'inactivo'})")
            print("Registros asociados: " + (", ".join(refs) if refs else "ninguno"))
            accion = "DAR DE BAJA (inactivo, nombre de usuario liberado)" if refs else "BORRAR"
            if "--confirmar" not in argv:
                print(f"Se haría: {accion}. Para hacerlo, repita el comando con --confirmar")
                return 0
            if refs:
                antes = u.username
                u.activo = False
                u.username = f"{antes}.baja{u.id}"[:60]
                audit(None, "USUARIO_DADO_DE_BAJA_CONSOLA", "User", u.id, {"usuario": antes, "referencias": refs})
                print(f"{antes} dado de baja: ya no puede ingresar; el nombre «{antes}» quedó libre para crearlo bien.")
            else:
                antes = u.username
                audit(None, "USUARIO_BORRADO_CONSOLA", "User", u.id, {"usuario": antes, "nombre": u.nombre, "rol": u.role_code})
                s.flush()
                s.delete(u)
                print(f"{antes} borrado.")
        elif cmd == "clave":
            if len(argv) < 2:
                print("Uso: clave <usuario>")
                return 2
            from sqlalchemy import select
            from werkzeug.security import generate_password_hash
            from .models import User
            from .seed import _hash_opts
            from .services.core import audit, param
            u = s.execute(select(User).where(User.username == argv[1])).scalars().first()
            if u is None:
                print("Usuario no encontrado. Vea la lista con: python -m app.cli usuarios")
                return 2
            pwd = getpass.getpass("Contraseña nueva: ")
            minimo = int(param("clave_longitud_minima", 8) or 8)
            if len(pwd) < minimo:
                print(f"La contraseña debe tener al menos {minimo} caracteres.")
                return 2
            if pwd != getpass.getpass("Repita la contraseña: "):
                print("Las contraseñas no coinciden.")
                return 2
            u.password_hash = generate_password_hash(pwd, **_hash_opts())
            u.debe_cambiar_clave = True  # el usuario la cambia en su siguiente ingreso
            u.activo = True
            audit(None, "CLAVE_ASIGNADA_CONSOLA", "User", u.id, {"usuario": u.username})
            print(f"Contraseña asignada a {u.username}; la cambiará en su siguiente ingreso.")
        elif cmd == "cargas":
            from sqlalchemy import select
            from .models import UploadBatch
            from .services.uploads import SPECS
            print(f"{'N.°':<6}{'TIPO':<14}{'ESTADO':<22}{'FILAS':>6}{'ERRORES':>9}  CONFIRMA (permiso)  ARCHIVO")
            for b in s.execute(select(UploadBatch).order_by(UploadBatch.id.desc()).limit(20)).scalars():
                filas = [r for r in b.rows if not r.excluida]
                err = sum(1 for r in filas if r.errores)
                print(f"{b.id:<6}{b.tipo:<14}{b.estado:<22}{len(filas):>6}{err:>9}  {SPECS.get(b.tipo, {}).get('confirm_perm', '-'):<19} {b.archivo}")
        elif cmd == "carga":
            from .models import UploadBatch
            b = s.get(UploadBatch, int(argv[1])) if len(argv) > 1 and argv[1].isdigit() else None
            if b is None:
                print("Uso: carga <n>  (vea los números con: python -m app.cli cargas)")
                return 2
            print(f"Carga #{b.id} {b.tipo} · {b.estado} · {len(b.rows)} filas")
            vistos = {}
            for r in b.rows:
                for e in r.errores or []:
                    vistos[e] = vistos.get(e, 0) + 1
            for e, n in sorted(vistos.items(), key=lambda x: -x[1])[:15]:
                print(f"  {n:>5} fila(s): {e}")
            ej = next((r for r in b.rows if r.errores), None)
            if ej is not None:
                print("Ejemplo de fila con error:", {k: v for k, v in (ej.datos or {}).items() if v not in (None, "")})
            if not vistos:
                print("Sin errores.")
        elif cmd == "sap-consulta-stock":
            from .services import sap_sl
            r = sap_sl.create_stock_query()
            s.commit()
            print(f"Consulta {sap_sl.STOCK_SQL_CODE} {'creada' if r['creada'] else 'ya existía'}; filas de stock leídas: {r['filas']}")
            if r["ejemplo"]:
                print("Ejemplo:", r["ejemplo"])
            print("Ahora: python -m app.cli sap-traer STOCK <usuario de Almacén> y confirmar la carga en Almacén → Cargas de archivos.")
        elif cmd == "sap-series":
            # V29: para decidir qué serie es de órdenes de servicio (parámetro sap_series_orden_servicio). Solo lee.
            from collections import Counter
            from .services import sap_sl, sap_v29
            with sap_sl.ServiceLayer() as sl:
                series = sap_v29.series_ordenes(sl)
                desde = (__import__("datetime").date.today() - __import__("datetime").timedelta(days=90)).isoformat()
                docs = sl.get_all("Orders", {"$filter": f"DocDate ge '{desde}'", "$select": "DocNum,Series,DocType"})
            n = Counter(d.get("Series") for d in docs)
            tipo_srv = Counter(d.get("Series") for d in docs if d.get("DocType") == "dDocument_Service")
            print("Serie (código) | Nombre | Órdenes de los últimos 90 días | De tipo servicio | Clase en el módulo")
            for cod in sorted(set(series) | set(n), key=lambda x: str(x)):
                clase = sap_v29.clase_de({"Series": cod})
                print(f"{cod} | {series.get(cod, '?')} | {n.get(cod, 0)} | {tipo_srv.get(cod, 0)} | {clase}")
            print("Para marcar una serie como de órdenes de servicio: Parámetros → sap_series_orden_servicio con su CÓDIGO, p. ej. [\"23\"].")
        elif cmd == "sap-diagnostico":
            from .services import sap_sl
            for linea in sap_sl.diagnostics():
                print(linea)
        elif cmd == "simulacion":
            # ENTORNO DE PRUEBAS: simulación integral de 14 días (generar | validar | estado | limpiar | regenerar)
            from sqlalchemy import select
            from .models import User
            from .services import simulacion as simsvc
            sub = argv[1] if len(argv) > 1 else "estado"
            usuario = s.execute(select(User).where(User.username == (argv[2] if len(argv) > 2 else "sistemas"))).scalars().first()
            up = app.config["UPLOAD_DIR"]
            if sub in ("limpiar", "regenerar"):
                print("Limpieza:", simsvc.limpiar(usuario, up))
                s.commit()
            if sub in ("generar", "regenerar"):
                from .simulacion_escenario import generar
                run = generar(usuario, up, progreso=lambda i, n, d: print(f"  día {i}/{n}: {d:%d/%m/%Y}", flush=True))
                print(f"Simulación #{run.id} {run.estado}: {run.resumen.get('conteos')}")
                print(f"Pasos rechazados por reglas: {run.resumen.get('rechazos_total')} · fallas: {run.resumen.get('fallas_total')}")
                sub = "validar"
            if sub == "validar":
                from .services import simulacion_validacion as sv
                run = simsvc.ultima()
                v = sv.guardar(run, app)
                s.commit()
                for c in v.get("controles", []):
                    print(("OK  " if c["ok"] else "ERR ") + f"{c['area']}: {c['control']} ({c['errores']}/{c['total']})")
                for h in v.get("hallazgos", []):
                    print("Hallazgo:", h)
            if sub == "estado":
                run = simsvc.ultima()
                print("Sin simulaciones." if run is None else f"Simulación #{run.id}: {run.estado} ({run.desde} a {run.hasta})")
                print("Entorno:", simsvc.habilitada(app) or "habilitado para simular")
        elif cmd == "muestras":
            from .demo_data import write_all
            print(write_all(argv[1] if len(argv) > 1 else "sample_data"))
        else:
            print(__doc__)
            return 1
        s.commit()
    return 0


if __name__ == "__main__":
    from .services.core import BusinessError as _BE
    try:
        sys.exit(main(sys.argv[1:]))
    except _BE as e:  # mensaje claro, sin el detalle técnico de Python
        print(f"ERROR: {e}")
        sys.exit(1)
