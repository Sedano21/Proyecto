# Instalación, configuración y despliegue

> **Listas de precios mínimos.** El Jefe Comercial las carga en *Comercial → Listas de precios* con los Excel actuales (PRICE_LIST y PRICE_LIST_GRANEL, sin cambiar el formato). El costo de la empresa se lee solo para validar y no se guarda.

> **Instalación definida (13-oct-2026):** servidor local administrado por Sistemas, base **PostgreSQL**, ingreso con
> **Microsoft 365**, alertas solo en el sistema (sin servidor de correo). Ver §8 a §10.

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
| `GEOSAT_API_URL` / `GEOSAT_TOKEN` | Servicio de posiciones de GEOSATELITAL (rastreo de unidades). Sin valor no se conecta | vacío |
| `CHECK_INTERVAL_MIN` | Ejecuta verificaciones automáticas (retrasos, fases, vencimientos, reposición, correo) cada N minutos (0 las desactiva) | 1 (cada minuto) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | Envío de correo de alertas | Sin SMTP → correos quedan como SIN_SMTP |
| `HOST`, `PORT` | Dirección del servidor de desarrollo | 127.0.0.1:5000 |
| `SCHEMA_AUTO_CREATE` | `0` en producción: el esquema lo crea y actualiza Alembic (`alembic upgrade head`) | 1 |
| `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `M365_TENANT_ID`, `M365_REDIRECT_URI` | Ingreso con Microsoft 365 (ver §9) | Desactivado |
| `APP_VERSION` | Versión que se muestra en el menú y queda registrada en cada observación de los usuarios | 1.0.0-mb |
| `LOCAL_LOGIN` | `0` = solo Microsoft 365 (oculta usuario/contraseña locales). Se recomienda dejar 1 cuenta local de emergencia de Sistemas | 1 |

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
Con varios procesos, un candado de archivo (`instance/verificaciones.lock`) hace que solo uno ejecute cada ronda; también puede desactivarse (`CHECK_INTERVAL_MIN=0`) y programarse `python -m app.cli verificar` con cron o el Programador de tareas.
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
tests/               pruebas automatizadas (SQLite por defecto; TEST_DATABASE_URL para PostgreSQL)
migrations/          migraciones Alembic (0001 = esquema inicial)
scripts/             respaldo_postgres.sh, restaurar_prueba.sh, gen_docs.py
docs/                especificación, trazabilidad, pruebas, estado, modelo, permisos, despliegue, seguridad
sample_data/         Excel ficticios de ejemplo
scripts/gen_docs.py  regenera docs/06 y docs/07 desde el código
```


## 8. Instalación local con PostgreSQL (decisión del 13-oct-2026)

1. Instalar PostgreSQL 16 en el servidor local. Crear un usuario de aplicación y la base, **sin** privilegios de
   superusuario:
   ```sql
   CREATE ROLE operaciones_app LOGIN PASSWORD '<clave larga generada>';
   CREATE DATABASE operaciones OWNER operaciones_app;
   CREATE ROLE operaciones_respaldo LOGIN PASSWORD '<otra clave>';           -- solo lectura, para pg_dump
   GRANT CONNECT ON DATABASE operaciones TO operaciones_respaldo;
   -- tras crear el esquema: GRANT SELECT ON ALL TABLES IN SCHEMA public TO operaciones_respaldo;
   ```
   En `pg_hba.conf` permitir solo conexiones locales (o de la IP del servidor de la aplicación) con `scram-sha-256`.
2. Variables: `DATABASE_URL=postgresql+psycopg://operaciones_app:<clave>@localhost:5432/operaciones`,
   `SCHEMA_AUTO_CREATE=0`, `DEMO_MODE=0`, `SECRET_KEY=<64 caracteres aleatorios>`, `UPLOAD_DIR=<carpeta con respaldo>`.
3. Crear el esquema con las migraciones: `alembic upgrade head`. Cada versión nueva del sistema trae su migración y se
   aplica con el mismo comando (antes, respaldo).
4. `python -m app.cli init` (catálogos) y `python -m app.cli crear-usuario …` para el administrador de Sistemas.
5. Verificado en esta entrega: las 103 pruebas funcionales pasan también contra PostgreSQL 16 (`TEST_DATABASE_URL=...`), y la
   demo se creó sobre un esquema generado por Alembic.

## 9. Ingreso con Microsoft 365 (Entra ID)

1. En el portal de Entra ID (Sistemas / TI): *Registros de aplicaciones → Nuevo registro*; tipo "solo cuentas de este
   directorio"; URI de redirección web `https://<servidor>/auth/microsoft/callback`.
2. Crear un secreto de cliente y anotar *Id. de aplicación (cliente)* e *Id. de directorio (inquilino)*. Permiso
   delegado `User.Read` (viene por defecto).
3. Definir `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `M365_TENANT_ID` (y `M365_REDIRECT_URI` si hay proxy).
4. Crear cada usuario en el sistema con **su correo corporativo** y su rol. Al ingresar con Microsoft 365, el sistema
   busca el usuario por ese correo; si no existe o está inactivo, no deja entrar. Los roles se administran en el sistema.
5. La librería oficial MSAL valida el `state`, el `nonce` y la firma del token. Sin estas variables el botón no aparece.
   **No se probó contra un tenant real** (requiere el registro anterior); sí con un servidor de identidad simulado.

## 10. Respaldos y restauración (buenas prácticas)

- `scripts/respaldo_postgres.sh` (programarlo a diario, p. ej. 23:00, con cron o el Programador de tareas):
  - `pg_dump` en formato personalizado con el usuario de solo lectura (`~/.pgpass` con permisos 600);
  - empaqueta `UPLOAD_DIR` (fotos, guías, facturas, certificados) y **cifra** ambos con una clave pública GPG (la clave
    privada se guarda fuera del servidor, p. ej. en custodia de Gerencia/Sistemas);
  - suma SHA-256 de cada archivo, permisos 600, rotación de `RETENCION_DIAS` (30 por defecto);
  - copia a `COPIA_REMOTA` (disco u otro equipo; regla 3-2-1: 3 copias, 2 medios, 1 fuera del local).
- `scripts/restaurar_prueba.sh`: verifica la suma, restaura el último respaldo en una base **temporal**, cuenta
  registros y la elimina. Hacerlo al menos una vez al mes y registrar el resultado.
- Para recuperar a un punto en el tiempo (no solo al último respaldo), activar el archivado de WAL de PostgreSQL
  (`archive_mode=on`) y respaldos base semanales con `pg_basebackup`.
- Ambos scripts se probaron en esta entrega con PostgreSQL 16 y GPG: respaldo cifrado, verificación y restauración correctas.
- Depuración de datos personales: `python -m app.cli depurar` lista las fotos de entrega más antiguas que el plazo
  `retencion_datos_personales_dias` (vacío = no depura); con `--aplicar` las elimina y lo registra en la auditoría.

## 11. Actualización a v0.6 (migraciones 0002 y 0003)

En una instalación existente con PostgreSQL: respaldo (§10) y luego `alembic upgrade head`. Se agregan costos, precios
de mercado, fichas y lugares de entrega de clientes, plan de producción, costos de importación y campos nuevos de OV,
traslados, rutas e incidencias. En la demostración local con SQLite basta recrear la base: borrar
`instance\operaciones.db` y ejecutar `python -m app.cli demo`.

## 12. Servicio de mapas (opcional) y firma del certificado

- **Mapa embebido, tiempo con tráfico y alertas de tráfico:** Sistemas crea una clave de Google Maps Platform (APIs
  *Distance Matrix* y *Maps Embed*), la restringe por IP del servidor y la define como variable de entorno
  `GOOGLE_MAPS_API_KEY`. Sin la clave, la ruta muestra el enlace «Abrir la ruta en Google Maps» y un tiempo
  estimado aproximado sin tráfico. El servicio tiene costo por consulta según el plan de Google.
- **Firma del certificado de calidad:** Sistemas la carga en *Calidad → Certificados* (PNG). Se guarda en
  `instance/firmas/` (fuera del repositorio) y solo se imprime en certificados aprobados.
- **Logos:** `app/static/img/` (recortados del certificado CA0764). Si se dispone de los archivos originales en alta
  resolución, reemplazarlos con el mismo nombre.
