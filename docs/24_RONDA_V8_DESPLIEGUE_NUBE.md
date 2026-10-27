# Ronda V8 (27-oct-2026): flota, OV desde SAP en Excel, respuestas del cuestionario y despliegue en la nube

## 1. Lo que se implementó

| Tema | Qué se hizo |
|---|---|
| Flota (imagen de GEOSATELITAL) | La unidad tiene ahora nombre en GEOSATELITAL, flota, marca, modelo, año, tipo y odómetro. En *Flota → Cargar Excel de GEOSATELITAL* se sube la lista con las mismas columnas que exporta el panel (más «Capacidad (kg)», opcional). Se identifica por la placa: no se duplica. «Sin marca», «Sin modelo» y «N/A» se toman como vacío. GEOSATELITAL no informa la capacidad: una unidad sin capacidad queda «no disponible» y no se asigna a rutas hasta registrarla. Las placas reales **no** están en el repositorio: se cargan en el servidor con el Excel. |
| OV desde las exportaciones de SAP | Ver §1.1. |
| A01 / A02 | Stock sin rotación «por cantidad» en S/ al costo (si no hay costo, en kg). Ranking consolidado con filtro por almacén. |
| A03 | Puntos de movimiento configurables por almacén (`puntos_movimiento`), con opción de escribir otro. |
| A04 | En un movimiento programado, quien solicita elige con cuánta anticipación se avisa (por defecto 30 min). El aviso llega una sola vez a quien lo ejecutará. |
| A05 | Asigna quien solicita; si no elige, lo toma el primero disponible. Solo quien solicitó reasigna, y cada cambio queda en el historial de la tarjeta (quién, de quién a quién, cuándo y por qué). |
| A06 | Si la diferencia con SAP supera 1 % o 5 kg, se pide **recuento** antes de cerrar el conteo; el recuento reemplaza al primer conteo. Aviso de **conteo cíclico** cada 15 días por almacén. Las zonas aún no están modeladas: el aviso es por almacén. |
| A09 | Contador por lote y por producto. **Alerta a Calidad desde la 2.ª fumigación del mismo lote.** |
| D01 | Auxiliar acompañante cuando la ruta tiene más de 3 paradas, supera 2 000 kg o el cliente lo pide (nuevo campo en su ficha). Al confirmar la ruta se asigna un auxiliar libre; si no hay ninguno, se pide asignarlo. |
| D02 | Visto bueno de salida: **Seguridad, Chofer y Líder Operativo** (antes: Auxiliar de Despacho). Si el chofer es externo sin cuenta, Distribución lo registra por encargo y queda anotado. |
| D03 | Panel por defecto `https://allpa.panel.geosatelital.com/monitoring/dashboard`. El enlace de seguimiento de cada unidad se registra con su vigencia (15 min a 24 h) y el sistema avisa cuando vence. |
| D05 | Quien recibe se identifica con DNI, carné de extranjería o pasaporte. Sin documento: foto de quien recibe y motivo detallado. La firma es siempre obligatoria. |
| G03 | Urgente: sirena insistente que se repite cada 2 minutos hasta atenderla. Media: suena una vez. Baja: sin sonido. Sin horario silencioso. |
| S06 / S07 | Sincronización con SAP cada minuto de 06:00 a 21:00 (`SAP_SYNC_MIN=1` y `sap_sync_horario`); si SAP no cambió, no se crea una carga nueva. Se sincronizan OV, clientes, productos y despachos. La escritura de cotizaciones queda **habilitada solo para la base de pruebas** `ZZZ_CORPRODUC_TEST260826` (`sap_escritura_empresas`). |
| S01 | Basta con poner la dirección del servidor (`https://172.18.103.1:50000/`): el sistema completa la ruta del Service Layer (`/b1s/v1`). |

**Bases ya instaladas.** Los cambios de valores (visto bueno de salida, panel GEOSATELITAL, escritura en SAP, tipos a sincronizar) se aplican una sola vez en bases existentes, y solo si el parámetro conserva el valor anterior.

**Migración.** Es la `0020`.

### 1.1 OV desde las exportaciones de SAP (archivos recibidos)

SAP exporta dos archivos distintos, y el módulo los reconoce solo:

1. **Lista de pedidos de cliente.** Trae una fila por OV, sin productos.
   - Del texto «Pedidos de cliente - C20…» se toman el **código SAP del cliente** y el **RUC**.
   - Las OV **abiertas** quedan esperando su detalle.
   - Las **cerradas** no se importan. Si ya estaban abiertas en el módulo y sin preparar, se cierran como «Atendida en SAP» sin descontar stock.
   - Se puede subir varias veces al día sin duplicar nada.
2. **Detalle de una OV.** Trae los productos, pero no el número de la OV.
   - Se sube desde la fila de esa OV, o nombrando el archivo con su número (`1636048.xlsx`) para subir varios a la vez.
   - Se crea la OV con la **cantidad pendiente**, el precio tras el descuento y el impuesto (EXO/IGV).

**Prueba con los archivos reales.** Se hizo en una base temporal; no se guardaron en el repositorio.
- Lista: 59 OV abiertas en espera y 17 cerradas omitidas.
- Detalle: la OV se creó con sus 4 productos, precios e impuesto.
- Una fila no traía el «C+RUC»: para esos casos se busca el cliente por su nombre exacto.

**Ruta permanente.** Con el Service Layer conectado, todo esto llega automáticamente. Los Excel quedan como contingencia.

## 2. Propuesta de despliegue en la nube (sin costo)

Requisitos dados por la empresa:
- servidor en la nube y gratuito;
- solo lo usa el personal;
- PC y celular;
- ingreso con correo corporativo;
- conexión con SAP B1 HANA, cuyo Service Layer está en una **dirección privada** (172.18.103.1, solo dentro de la red de la empresa).

```
 Personal (PC / celular) ──HTTPS──▶  VM en la nube  ──red privada cifrada (Tailscale)──▶  PC/servidor en la oficina ──▶ SAP Service Layer 172.18.103.1:50000
                                    · Caddy (HTTPS automático)                                (equipo «puente», encendido 06:00–21:00)
                                    · Módulo (gunicorn)
                                    · PostgreSQL + respaldos diarios
```

| Pieza | Propuesta gratuita | Por qué |
|---|---|---|
| Servidor | **Oracle Cloud «Always Free»**: VM Ampere de hasta 4 vCPU y 24 GB de RAM, 200 GB de disco, IP pública fija | Es gratuito de forma permanente (no es una prueba) y sobra para el módulo, la base y las fotos. Al crear la cuenta pide una tarjeta solo para verificar identidad; no cobra si se usan recursos «Always Free». Oracle puede recuperar una VM gratuita que pasa días casi sin uso; con el uso diario no ocurre, y si se quiere evitar del todo se pasa la cuenta a «pago por uso», que sigue sin costo mientras solo se usen recursos «Always Free». |
| Base de datos del módulo (S02) | **PostgreSQL** en la misma VM | Gratuita, estable y escalable. Si crece, se pasa a una base administrada sin cambiar el código. SAP sigue siendo la fuente oficial: el módulo guarda su propia operación (alertas, evidencias, picking, rutas…). |
| Nombre y HTTPS (E02) | Subdominio gratuito **DuckDNS** (p. ej. `operaciones-cp.duckdns.org`) y certificado **Let's Encrypt** renovado solo por **Caddy** | Sin costo y con HTTPS válido en PC y celular. Si la empresa prefiere su dominio (`operaciones.corporacionproductiva.com`), solo cambia el nombre. |
| Acceso solo del personal (E02 / E04) | Ingreso con **Microsoft 365** (correo corporativo; ya implementado) | Solo entran cuentas del dominio de la empresa que además existan en el módulo con su rol. |
| Conexión a SAP (S01) | **Tailscale** (plan gratuito personal; solo se conectan 2 equipos) en la VM y en **un equipo de la oficina** que actúe de «puente» hacia 172.18.103.1 (*subnet router*) | El Service Layer no se expone a internet y no se abren puertos en el firewall de la empresa. La conexión va cifrada. Ese equipo debe estar encendido en el horario de sincronización. |
| Respaldos | Copia diaria de la base y de las fotos a las 03:00, guardada 14 días (incluido en el script); opcionalmente, copia al Object Storage gratuito de Oracle (20 GB) | Recuperación ante errores o fallas. |
| Correo de alertas (E04) | Envío por Microsoft 365/Graph con la misma aplicación registrada (ya implementado) | Sin servidor de correo propio. |

### 2.1 Pasos

**Lo que hace la empresa (requiere sus cuentas):**
1. Crear la cuenta de Oracle Cloud y una VM Ubuntu 24.04 «Ampere A1» (Always Free). Abrir los puertos 80 y 443.
2. Crear el subdominio en duckdns.org y apuntarlo a la IP pública de la VM.
3. En Entra ID (Microsoft 365), registrar la aplicación (docs/08 §9) con la dirección `https://<subdominio>/auth/microsoft/callback`.
4. Instalar Tailscale en un equipo de la oficina con acceso a 172.18.103.1 y publicarlo como *subnet router* de `172.18.103.1/32`.
5. Crear en SAP un **usuario de integración** con la licencia de acceso indirecto (anunciada para el miércoles o jueves), en lugar de `manager`.

**Lo que corre en la VM (script incluido):**
```bash
git clone --branch claude/automatizacion-corporativa-app-1cu2g5 https://github.com/sedano21/proyecto.git /opt/operaciones
sudo bash /opt/operaciones/deploy/instalar_ubuntu.sh <subdominio>.duckdns.org
sudo nano /etc/operaciones/operaciones.env      # SECRET_KEY, DATABASE_URL, SAP_SL_*, M365_* (nunca en el repositorio)
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/alembic upgrade head; .venv/bin/python -m app.cli init'
sudo systemctl start operaciones
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/python -m app.cli sap-probar'
```

Archivos en `deploy/`:
- `instalar_ubuntu.sh`
- `operaciones.service` (systemd)
- `Caddyfile` (HTTPS)
- `operaciones.env.example` (plantilla sin secretos)

### 2.2 Calendario propuesto (E06)

| Fecha | Actividad |
|---|---|
| Mar 27-oct | Cuentas (Oracle, DuckDNS, Entra ID) y equipo puente con Tailscale. |
| Mié 28 / jue 29-oct | Instalación en la VM; conexión al Service Layer de **pruebas** con el usuario de integración; carga de usuarios por área (correo corporativo y rol); unidades de GEOSATELITAL (Excel). Prueba con todos los usuarios. |
| 29-oct al 1-nov | Capacitación (E07): 1 hora por área y videos cortos. Soporte (E08): respuesta el mismo día y correcciones críticas en 24 h. |
| Lun 2-nov | Inicio de la marcha blanca en paralelo con SAP. |

## 3. Seguridad: puntos que requieren acción

**Credenciales de SAP (S03).** Se compartieron por un canal no seguro: `manager` es el superusuario de SAP.
- **Cambiar esa contraseña.**
- Usar un usuario de integración propio, con los permisos mínimos.
- Las credenciales van solo en `/etc/operaciones/operaciones.env` (permisos 600), nunca en el repositorio ni en la base.

**Certificado del Service Layer.** Normalmente es propio de SAP. Se recomienda instalar su CA en la VM (`SAP_SL_CA`); `SAP_SL_VERIFY=0` solo en una prueba puntual.

**Credenciales de GEOSATELITAL.** Tampoco se guardan: el panel se abre con la sesión de cada usuario y los enlaces de seguimiento no llevan usuario ni contraseña.

**Qué no se ha hecho todavía.** El despliegue real y la conexión con SAP aún no se ejecutaron:
- el servidor y las cuentas los crea la empresa;
- desde este entorno no hay acceso a la red interna (172.18.103.1).

Por eso el sistema **no está listo para producción** hasta completar los pasos de §2.1 y probar con los usuarios.
