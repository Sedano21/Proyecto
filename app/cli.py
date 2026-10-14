"""Comandos de administración.

    python -m app.cli init            # crea tablas y catálogos (sin datos de demostración)
    python -m app.cli demo            # crea tablas, catálogos y datos FICTICIOS de demostración
    python -m app.cli reset-demo      # BORRA la base local y recrea la demostración (solo SQLite local)
    python -m app.cli verificar       # ejecuta verificaciones periódicas (alertas automáticas, correo)
    python -m app.cli crear-usuario <usuario> <rol> <nombre> <email>
    python -m app.cli muestras <carpeta>   # genera los Excel ficticios de ejemplo
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
            print("Demostración creada" if r else "Ya existían usuarios; no se modificó nada")
        elif cmd == "depurar":
            from .services.retention import purge_photos
            r = purge_photos(app.config["UPLOAD_DIR"], aplicar="--aplicar" in argv)
            s.commit()
            print(r)
        elif cmd == "verificar":
            from .services.scheduler import run_checks
            print(run_checks())
        elif cmd == "crear-usuario":
            if len(argv) < 5:
                print("Uso: crear-usuario <usuario> <rol> <nombre> <email>")
                return 2
            from .seed import create_user
            pwd = getpass.getpass("Contraseña: ")
            if len(pwd) < 10:
                print("La contraseña debe tener al menos 10 caracteres.")
                return 2
            create_user(argv[1], argv[3], argv[2], pwd, argv[4])
            print("Usuario creado")
        elif cmd == "muestras":
            from .demo_data import write_all
            print(write_all(argv[1] if len(argv) > 1 else "sample_data"))
        else:
            print(__doc__)
            return 1
        s.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
