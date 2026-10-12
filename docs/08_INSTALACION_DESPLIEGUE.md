# Instalación, configuración y despliegue

> **Cambios de estructura de la base de datos.** El prototipo crea las tablas al iniciar y no migra tablas existentes. Tras actualizar a una versión con columnas nuevas (p. ej. la del 12-oct-2026), recree la base de demostración con `python -m app.cli demo`. Para una instalación con datos reales se debe incorporar una herramienta de migraciones (Alembic) antes del piloto.

## 1. Requisitos

- Python 3.10 o superior (probado con 3.13).
- Windows, Linux o macOS. Sin dependencias de nube.
- Navegador moderno (Chrome, Edge, Firefox).

## 2. Instalación local (demostración)

```bash
git clone <repositorio> && cd Proyecto
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m app.cli demo        # crea instance/operaciones.db con catálogos y datos FICTICIOS
python run.py                 # abre http://127.0.0.1:5000
```

Usuarios de demostración: uno por rol (`gerente.general`, `sistemas`, `coord.ventas`, `asist.ventas`, `vendedor1`,
`coord.almacen`, `jefe.logistica`, `jefe.produccion`, `jefe.calidad`, `compras`, `importaciones`, `coord.distribucion`,
`aux.despacho`, `seguridad`, …). Contraseña: `Demo2026!`. La lista completa aparece en la pantalla de ingreso mientras
`DEMO_MODE=1`.

Reiniciar la demostración (solo SQLite local, borra la base local): `python -m app.cli reset-demo`.

Archivos Excel ficticios para probar cargas: carpeta `sample_data/` (mismos encabezados que las exportaciones reales).

## 3. Pruebas

```bash
pip install -r requirements-dev.txt
python -m pytest tests -v
```

## 4. Variables de entorno

| Variable | Uso | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | Base de datos SQLAlchemy (`postgresql+psycopg://usuario:clave@host/bd`, `mssql+pyodbc://…`) | SQLite en `instance/operaciones.db` |
| `SECRET_KEY` | Firma de sesiones (obligatoria en producción, 32+ bytes aleatorios) | Se genera en `instance/secret_key` |
| `UPLOAD_DIR` | Carpeta de archivos cargados y evidencias de entrega | `instance/uploads` |
| `MAX_UPLOAD_MB` | Tamaño máximo de archivo | 40 |
| `DEMO_MODE` | `1` muestra aviso de demo y lista de usuarios demo en el ingreso; **`0` en producción** | 1 |
| `SESSION_COOKIE_SECURE` | `1` cuando se publica por HTTPS | 0 |
| `CHECK_INTERVAL_MIN` | Ejecuta verificaciones automáticas (retrasos, fases, vencimientos, reposición, correo) cada N minutos | 0 (desactivado) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | Envío de correo de alertas | Sin SMTP → correos quedan como SIN_SMTP |
| `HOST`, `PORT` | Dirección del servidor de desarrollo | 127.0.0.1:5000 |

Alternativa a `CHECK_INTERVAL_MIN`: programar `python -m app.cli verificar` con cron o el Programador de tareas de Windows.

## 5. Puesta en marcha en la organización (sin datos de demostración)

1. Crear la base (PostgreSQL recomendado) y definir `DATABASE_URL`, `SECRET_KEY`, `DEMO_MODE=0`, SMTP.
2. `pip install -r requirements.txt psycopg[binary]` (o el controlador del motor elegido).
3. `python -m app.cli init` → crea tablas y catálogos (roles, permisos, alertas, parámetros, almacenes, plazos, líneas).
4. `python -m app.cli crear-usuario sistemas.admin SISTEMAS "Nombre" correo@empresa` (pide la contraseña, mín. 10 caracteres).
5. Con ese usuario: revisar *Configuración* (parámetros PENDIENTE/DEMO, almacenes, plazos, líneas, fases), *Usuarios y
   permisos* y *Configurar alertas*.
6. Cargar en este orden (*Almacén → Cargas de archivos*): maestro de artículos (DATA) → stock por lote (STOCK_LOTE, base
   inicial) → lista de materiales → historial de salidas (Qy) → OV (OVS).
7. Completar en el catálogo de artículos las categorías de reposición, stock mínimo, grupos PCC1 y pesos faltantes.

## 6. Despliegue en servidor

La aplicación es WSGI estándar (`run:app`). Ejemplo Linux:

```bash
pip install gunicorn
gunicorn -w 3 -b 127.0.0.1:8000 run:app
```

En Windows Server: `pip install waitress` y `waitress-serve --listen=127.0.0.1:8000 run:app`.
Publicar detrás de un proxy inverso (Nginx / IIS) con **HTTPS** y `SESSION_COOKIE_SECURE=1`.
Si se usan varios procesos, ejecutar las verificaciones periódicas con cron/Programador de tareas (no con `CHECK_INTERVAL_MIN`).
Respaldar la base de datos y la carpeta `UPLOAD_DIR` (evidencias) diariamente.

## 7. Estructura del proyecto

```
app/
  __init__.py        fábrica de la aplicación
  catalogs.py        roles, permisos, alertas, parámetros, almacenes, plazos (con su fuente documental)
  models.py          modelo de datos (ver docs/06)
  seed.py            carga de catálogos y demostración
  demo_data.py       generador de Excel ficticios
  cli.py             comandos de administración
  services/          lógica de negocio (stock, orders, production, quality, purchasing, imports,
                     distribution, transfers, repack, inventory, uploads, alerts, mailer, kpis, scheduler)
  views/             pantallas por módulo
  templates/, static/
tests/               55 pruebas automatizadas
docs/                especificación, trazabilidad, pruebas, estado, modelo, permisos, despliegue, seguridad
sample_data/         Excel ficticios de ejemplo
scripts/gen_docs.py  regenera docs/06 y docs/07 desde el código
```
