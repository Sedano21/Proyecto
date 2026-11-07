# 43 · Migración a AWS Lightsail: verificación y configuración completa del servidor (07-nov-2026)

Guía de principio a fin para dejar el Módulo de Operaciones funcionando en la instancia de **AWS Lightsail** ya
contratada, y para **comprobar que lo que ya se configuró está bien**. Siga los pasos en orden: cada uno indica cómo
verificarlo. Al final, el script `deploy/verificar_servidor.sh` revisa todo el servidor de forma automática y responde
OK / AVISO / FALLA en cada punto.

**Reglas para todo el proceso**
- Ninguna contraseña, token, clave ni secreto se envía por chat ni por correo, ni se guarda en el repositorio. Los
  secretos se escriben solo en el servidor, en `/etc/operaciones/operaciones.env` (permisos 600) o en
  `/root/.aws/credentials`.
- En esta guía, `DOMINIO` es el nombre con el que se entrará al sistema (p. ej. `operaciones.corporacionproductiva.com`
  o el subdominio de DuckDNS). Reemplácelo en cada comando.
- Lo que se ejecuta en el servidor va precedido de `$`; lo que se hace en la consola web de AWS se indica con ☐.

---

## 0. Qué tener a la mano antes de empezar

| Dato | Para qué | Dónde se usa |
|---|---|---|
| Acceso a la consola de AWS (usuario con MFA) | Revisar la instancia, IP, firewall e instantáneas | §1 |
| La llave SSH de la instancia (`.pem`) o la consola SSH del navegador | Entrar al servidor | §2 |
| El dominio y acceso al proveedor de DNS (o DuckDNS) | Apuntar el dominio a la IP fija | §4 |
| Usuario de integración de SAP y su contraseña | Conexión con SAP (va solo al servidor) | §6, §9 |
| Certificado (CA) del Service Layer, `.pem`/`.crt` | Verificar la conexión cifrada con SAP | §9 |
| Tenant ID, Client ID y Client secret de Microsoft 365 | Ingreso con el correo corporativo | §6, §11 |
| Acceso SSH al **servidor anterior** (si hay datos que migrar) | Copiar base, archivos y claves | §7 |
| IP pública de la oficina | Restringir SSH y la VPN | §1.3 |

**Ventana de corte:** la migración de datos requiere detener el servidor anterior unos 30–60 minutos (según el tamaño de
la base y de las fotos). Elija un horario sin operación (p. ej. después de las 21:00 o un domingo) y avise a los usuarios.

---

## 1. Revisar la instancia en la consola de Lightsail

Entre a https://lightsail.aws.amazon.com y abra la instancia. Compare cada punto con lo esperado:

### 1.1 Instancia

| ☐ | Qué revisar | Valor esperado | Si no coincide |
|---|---|---|---|
| ☐ | Plan | **16 GB RAM, 4 vCPU, 320 GB SSD**, 6 TB de transferencia (aprobado en la propuesta al Directorio, docs/37) | Un plan no se cambia en el lugar: se crea una instantánea y desde ella una instancia del plan correcto |
| ☐ | Sistema (blueprint) | **OS Only → Ubuntu 24.04 LTS** (22.04 también sirve) | Si se eligió una aplicación (WordPress, LAMP, etc.) o Amazon Linux/Windows, **recree la instancia** con Ubuntu: el instalador es para Ubuntu |
| ☐ | Región | La elegida en la propuesta (São Paulo `sa-east-1` por cercanía a Lima, o N. Virginia `us-east-1`) | La región no se cambia; solo importa si se eligió una lejana (Asia, Europa): recrear |
| ☐ | Red | Doble pila (IPv4 + IPv6) o solo IPv4 | Ver §1.3 sobre el firewall IPv6 |
| ☐ | Nombre | Descriptivo, p. ej. `operaciones-cp` | Es solo una etiqueta |
| ☐ | Estado | **Running** | Iniciar |

### 1.2 IP fija (Static IP)
| ☐ | Qué revisar | Esperado |
|---|---|---|
| ☐ | Pestaña **Networking** → *Public IPv4* | Debe decir **Static IP** con un nombre (no solo «Public IP») |
| ☐ | Si no hay IP estática | *Networking → Attach static IP* → crear y asociar a la instancia. Es gratuita mientras esté asociada. |
| ☐ | Anote la IP | Es la IP que va en el DNS (§4) y en la VPN (§9) |

> Una IP estática **sin asociar** a una instancia sí tiene costo: si se creó alguna de prueba, libérela.

### 1.3 Firewall de la instancia (pestaña Networking)
Lightsail tiene **dos firewalls separados: IPv4 e IPv6**. Revise los dos; la regla que falte en IPv6 deja la puerta
abierta o cerrada por ese lado aunque IPv4 esté bien.

**IPv4 Firewall — deben quedar exactamente estas reglas:**

| ☐ | Aplicación | Protocolo | Puerto | Origen permitido |
|---|---|---|---|---|
| ☐ | SSH | TCP | 22 | **Restringido a la IP pública de la oficina** (si es fija). Si no es fija, déjelo abierto: el ingreso es solo con llave. Marque también *Allow Lightsail browser SSH* para poder usar la consola del navegador. |
| ☐ | HTTP | TCP | 80 | Cualquiera (Let's Encrypt lo usa para emitir el certificado; Caddy redirige todo a HTTPS) |
| ☐ | HTTPS | TCP | 443 | Cualquiera |
| ☐ | Custom (VPN WireGuard) | **UDP** | **51820** | **Solo la IP pública de la empresa** (o del equipo que hará la VPN, §9) |

**No deben existir** reglas para 5432 (PostgreSQL), 8000 (aplicación), 3389, 50000 ni «All TCP/All protocols».

**IPv6 Firewall:** deje las mismas reglas (22, 80, 443) o, si no usarán IPv6, borre todas sus reglas.

### 1.4 Instantáneas automáticas (copia completa del servidor)
| ☐ | Pestaña **Snapshots** → *Automatic snapshots* | **Activadas** |
| ☐ | Hora | **09:00 UTC** (04:00 de Lima), después del respaldo de la base de las 03:00 |
| | Lightsail conserva las últimas 7 automáticas. | |

### 1.5 Alertas de la instancia
| ☐ | Pestaña **Metrics** → *CPU utilization* → *Add alarm* | Aviso si supera **80 % durante 15 minutos** |
| ☐ | *Status check failed* → *Add alarm* | Aviso si falla **1 vez** |
| ☐ | Contacto de notificación | Correo de Sistemas registrado y **confirmado** (Lightsail envía un correo de verificación) |

### 1.6 Cuenta de AWS
| ☐ | Usuario raíz con **MFA** (doble factor) activado | Obligatorio |
| ☐ | Trabajo diario con un usuario IAM (no el raíz) con MFA | Recomendado |
| ☐ | *Billing → Budgets*: presupuesto mensual con aviso | p. ej. **USD 120/mes** (plan 16 GB ≈ USD 84 + instantáneas y S3) |
| ☐ | Facturación a la tarjeta / datos de la empresa | |

---

## 2. Primera conexión y verificación del equipo

Conéctese con el botón **Connect using SSH** de la consola, o desde una PC:
```bash
ssh -i LightsailDefaultKey-<region>.pem ubuntu@<IP_FIJA>
```

Compruebe que el equipo es el contratado:
```bash
$ lsb_release -d                 # Ubuntu 24.04.x LTS
$ nproc                          # 4
$ free -h                        # Mem total ≈ 15–16 Gi
$ df -h /                        # tamaño ≈ 300+ G
$ curl -s https://checkip.amazonaws.com    # debe ser la IP FIJA del §1.2
```

---

## 3. Preparar el sistema operativo

### 3.1 Actualizar y zona horaria
```bash
$ sudo apt-get update && sudo apt-get -y full-upgrade
$ sudo timedatectl set-timezone America/Lima
$ timedatectl                    # «Time zone: America/Lima», «System clock synchronized: yes»
$ sudo hostnamectl set-hostname operaciones-cp
```

### 3.2 Actualizaciones de seguridad automáticas
Vienen activas en Ubuntu. Confírmelo:
```bash
$ systemctl is-enabled unattended-upgrades      # enabled
$ cat /etc/apt/apt.conf.d/20auto-upgrades       # ambos valores en "1"
```
Si no están: `sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades`.

### 3.3 Memoria de intercambio (swap) de 4 GB
Evita que un pico de memoria (exportaciones grandes) detenga procesos:
```bash
$ sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
$ sudo mkswap /swapfile && sudo swapon /swapfile
$ echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
$ echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf && sudo sysctl -p /etc/sysctl.d/99-swap.conf
$ free -h                                        # Swap: 4.0Gi
```

### 3.4 SSH
Lightsail ya entra solo con llave. Confírmelo:
```bash
$ sudo sshd -T | grep -Ei '^(passwordauthentication|permitrootlogin)'
# passwordauthentication no
# permitrootlogin without-password   (o prohibit-password / no)
```
Si `passwordauthentication` dice `yes`:
```bash
$ echo 'PasswordAuthentication no' | sudo tee /etc/ssh/sshd_config.d/10-sin-clave.conf && sudo systemctl reload ssh
```

### 3.5 Reiniciar una vez
```bash
$ sudo reboot        # espere 1 minuto y vuelva a conectarse
```

---

## 4. Dominio (DNS)

1. En el proveedor del dominio, cree o cambie un **registro A**: `DOMINIO → <IP_FIJA>`. TTL de 300 segundos (5 min).
   - Si es DuckDNS: en https://www.duckdns.org escriba la IP fija en *current ip* → *update ip*.
   - Si hay IPv6 y quiere usarla: registro **AAAA** con la IPv6 de la instancia. Si no, no cree AAAA.
2. **Si el dominio hoy apunta al servidor anterior**, **no lo cambie todavía**: hágalo en el §7.4, durante el corte.
   Lo que sí conviene hacer ahora es **bajar su TTL a 300**, al menos 24 h antes del corte, para que el cambio se
   propague rápido.
3. Verificación (desde el servidor o cualquier PC):
   ```bash
   $ getent ahostsv4 DOMINIO        # debe devolver la IP FIJA
   $ nslookup DOMINIO 8.8.8.8
   ```

---

## 5. Instalar el módulo

### 5.1 Código
El servidor descarga el código de `github.com/sedano21/proyecto`, rama `claude/automatizacion-corporativa-app-1cu2g5`.
Si el repositorio es **privado**, cree primero una llave de despliegue de solo lectura:
```bash
$ sudo ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519 && sudo cat /root/.ssh/id_ed25519.pub
```
En GitHub: *Settings → Deploy keys → Add deploy key*, pegue la llave **sin** marcar «Allow write access». Luego use
`REPO=git@github.com:sedano21/proyecto.git` en los comandos siguientes. Si es público, no se necesita nada.

### 5.2 Instalador
```bash
$ sudo apt-get install -y git
$ sudo git clone --branch claude/automatizacion-corporativa-app-1cu2g5 https://github.com/sedano21/proyecto.git /opt/operaciones
$ sudo bash /opt/operaciones/deploy/instalar_ubuntu.sh DOMINIO
```

El instalador hace lo siguiente:
- instala Python, PostgreSQL y Caddy (HTTPS automático con Let's Encrypt);
- crea el usuario de sistema `operaciones`, las carpetas y la base de datos;
- instala el servicio `operaciones` (gunicorn) y su temporizador de actualización (sin activarlo);
- configura Caddy con el dominio y aplica a PostgreSQL el ajuste para 16 GB (`deploy/postgresql-operaciones.conf`);
- programa el respaldo diario (03:00, guarda 14 días) y la rotación de registros.

**Al final muestra una línea `postgresql+psycopg://operaciones:<clave>@127.0.0.1:5432/operaciones`: cópiela**, va en
`DATABASE_URL` (§6). Solo se muestra la primera vez.

Verificación:
```bash
$ systemctl is-active postgresql caddy                     # active, active
$ sudo -u postgres psql -c "show shared_buffers"           # 4GB
$ ls -ld /opt/operaciones /var/lib/operaciones/archivos    # dueño operaciones
```

---

## 6. Variables del servidor (todos los ajustes y secretos)

```bash
$ sudo nano /etc/operaciones/operaciones.env
$ sudo chown root:root /etc/operaciones/operaciones.env && sudo chmod 600 /etc/operaciones/operaciones.env
```

Contenido completo. Los valores entre `< >` se reemplazan; no deje ninguno de ejemplo.
```ini
# --- Aplicación ---
SECRET_KEY=<salida de: openssl rand -hex 32>     # si migra, puede reutilizar la del servidor anterior (las sesiones siguen)
DATABASE_URL=postgresql+psycopg://operaciones:<clave que mostró el instalador>@127.0.0.1:5432/operaciones
UPLOAD_DIR=/var/lib/operaciones/archivos
SESSION_COOKIE_SECURE=1
DEMO_MODE=0                                     # OBLIGATORIO en producción
SCHEMA_AUTO_CREATE=0                            # el esquema lo gestiona Alembic
APP_TZ=America/Lima
# SIMULACION_HABILITADA                         # NO definir en producción

# --- SAP Business One (Service Layer) ---
SAP_SL_URL=https://172.18.103.1:50000/          # con la VPN de §9; con la opción B: https://10.77.0.2:50000/
SAP_SL_COMPANY=ZZZ_CORPRODUC_TEST260826         # base de PRUEBAS durante la marcha blanca
SAP_SL_USER=<usuario de integración>            # nunca «manager»
SAP_SL_PASSWORD=<contraseña del usuario de integración>
SAP_SL_CA=/etc/operaciones/sap_ca.pem
SAP_SYNC_MIN=1
SAP_SYNC_USER=sistemas

# --- Microsoft 365 ---
M365_TENANT_ID=<Id. de directorio>
M365_CLIENT_ID=<Id. de aplicación>
M365_CLIENT_SECRET=<valor del secreto>
M365_REDIRECT_URI=https://DOMINIO/auth/microsoft/callback

# --- Notificaciones push ---
VAPID_SUB=mailto:sistemas@corporacionproductiva.com

# --- Copia externa de respaldos (§10) ---
RESPALDO_S3=s3://<nombre-del-bucket>/operaciones

# --- GEOSATELITAL (solo si el proveedor da una API; el panel no lo necesita) ---
GEOSAT_API_URL=
GEOSAT_TOKEN=
```
Los ajustes de rendimiento (`GUNICORN_WORKERS`, `GUNICORN_THREADS`, límites por minuto) se dejan comentados: los
valores por defecto ya se ajustan a 4 procesadores (5 procesos × 4 hilos).

Verificación:
```bash
$ sudo stat -c '%a %U' /etc/operaciones/operaciones.env      # 600 root
$ sudo grep -c 'CLAVE_BD\|cambiar-por' /etc/operaciones/operaciones.env   # 0
```

---

## 7. Base de datos: instalación nueva **o** migración desde el servidor anterior

Atajo para ejecutar comandos de la aplicación con sus variables:
```bash
$ app() { sudo -u operaciones bash -c "set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; $*"; }
```

### 7.A Si NO hay datos que migrar (base nueva)
```bash
$ app ".venv/bin/alembic upgrade head"
$ app ".venv/bin/python -m app.cli init"
$ app ".venv/bin/python -m app.cli crear-usuario sistemas SISTEMAS 'Administrador de Sistemas' <correo>@corporacionproductiva.com"
$ app ".venv/bin/python -m app.cli esquema"        # «La base coincide con el código.»
```
`crear-usuario` pide la contraseña en pantalla. Continúe en el §8.

### 7.B Si hay un servidor anterior con datos (migración)

Se copian **cuatro cosas**:
1. la base PostgreSQL;
2. la carpeta de archivos (fotos y documentos);
3. la clave de notificaciones `instance/vapid_privada.pem`, para que los celulares no tengan que volver a «Activar»;
4. los valores del `.env`, que se escriben a mano, sin copiar el archivo por chat.

**7.B.1 Antes del corte (con el sistema anterior funcionando)**
- Compruebe en el servidor anterior la versión de PostgreSQL (`psql --version`). La del nuevo debe ser igual o mayor;
  Ubuntu 24.04 trae la 16.
- Anote los conteos de control en el servidor anterior (sirven para comparar después):
  ```bash
  (anterior)$ sudo -u postgres psql -d operaciones -tAc "select 'ov',count(*) from sales_orders union all select 'usuarios',count(*) from users union all select 'lotes',count(*) from stock_lots union all select 'alertas',count(*) from alerts union all select 'auditoria',count(*) from audit_log"
  (anterior)$ sudo -u postgres psql -d operaciones -tAc "select version_num from alembic_version"
  (anterior)$ sudo du -sh /var/lib/operaciones/archivos
  ```
- Si no se usa ya, baje el TTL del DNS (§4).

**7.B.2 Corte: detener el servidor anterior y exportar**
```bash
(anterior)$ sudo systemctl stop operaciones-actualizar.timer operaciones
(anterior)$ sudo -u postgres pg_dump -Fc operaciones -f /tmp/operaciones.dump
(anterior)$ sudo tar czf /tmp/archivos.tgz -C /var/lib/operaciones archivos
(anterior)$ sudo tar czf /tmp/instance.tgz -C /opt/operaciones instance/vapid_privada.pem   # si dice que no existe, nadie activó notificaciones: omita este archivo en adelante
(anterior)$ cd /tmp && sudo sha256sum operaciones.dump archivos.tgz instance.tgz | sudo tee migracion.sha256
(anterior)$ sudo chmod 644 /tmp/operaciones.dump /tmp/archivos.tgz /tmp/instance.tgz /tmp/migracion.sha256
```

**7.B.3 Llevar los archivos al servidor nuevo** (directo entre servidores, con una llave temporal)
```bash
(nuevo)$ ssh-keygen -t ed25519 -N "" -f ~/.ssh/migracion && cat ~/.ssh/migracion.pub
#   copie esa línea en el servidor anterior:  echo '<línea>' >> ~/.ssh/authorized_keys
(nuevo)$ mkdir -p ~/migracion && scp -i ~/.ssh/migracion <usuario>@<IP_ANTERIOR>:/tmp/{operaciones.dump,archivos.tgz,instance.tgz,migracion.sha256} ~/migracion/
(nuevo)$ cd ~/migracion && sha256sum -c migracion.sha256        # las tres líneas deben decir «OK»
```
Si el servidor anterior solo acepta SSH desde ciertas IP, haga la copia en dos tramos a través de su PC: `scp` de allá a
la PC y de la PC al nuevo.

**7.B.4 Importar en el servidor nuevo**
```bash
(nuevo)$ sudo systemctl stop operaciones
# base: se recrea vacía y se restaura. ¡SOLO en el servidor NUEVO y antes de que nadie lo use! (borra su base)
(nuevo)$ sudo install -o postgres -m 600 ~/migracion/operaciones.dump /tmp/operaciones.dump
(nuevo)$ sudo -u postgres psql -c "DROP DATABASE IF EXISTS operaciones;" -c "CREATE DATABASE operaciones OWNER operaciones;"
(nuevo)$ sudo -u postgres pg_restore --no-owner --role=operaciones -d operaciones /tmp/operaciones.dump
(nuevo)$ sudo rm -f /tmp/operaciones.dump
# archivos y clave de notificaciones
(nuevo)$ sudo tar xzf ~/migracion/archivos.tgz -C /var/lib/operaciones
(nuevo)$ sudo -u operaciones mkdir -p /opt/operaciones/instance
(nuevo)$ sudo tar xzf ~/migracion/instance.tgz -C /opt/operaciones
(nuevo)$ sudo chown -R operaciones:operaciones /var/lib/operaciones/archivos /opt/operaciones/instance
(nuevo)$ sudo chmod 600 /opt/operaciones/instance/vapid_privada.pem
# migraciones pendientes (si el servidor anterior tenía una versión más antigua del código)
(nuevo)$ app ".venv/bin/alembic current"          # debe mostrar la versión anotada en 7.B.1
(nuevo)$ app ".venv/bin/alembic upgrade head"
(nuevo)$ app ".venv/bin/python -m app.cli init"   # agrega catálogos nuevos sin tocar lo configurado
(nuevo)$ app ".venv/bin/python -m app.cli esquema"   # «La base coincide con el código.»
```
- Si `alembic current` no muestra versión, siga el anexo «Base creada sin versión de Alembic» de `docs/25` antes de
  `upgrade`.
- `pg_restore` puede mostrar avisos sobre la extensión `plpgsql`; no tienen importancia. Cualquier otro **error** debe
  revisarse antes de seguir.

**7.B.5 Comparar con el servidor anterior**
```bash
(nuevo)$ sudo -u postgres psql -d operaciones -tAc "select 'ov',count(*) from sales_orders union all select 'usuarios',count(*) from users union all select 'lotes',count(*) from stock_lots union all select 'alertas',count(*) from alerts union all select 'auditoria',count(*) from audit_log"
(nuevo)$ sudo du -sh /var/lib/operaciones/archivos
```
Los conteos deben ser **iguales** a los del §7.B.1, y el tamaño de los archivos, igual o casi igual.

**7.B.6 Limpieza de la migración**
```bash
(nuevo)$ rm -rf ~/migracion ~/.ssh/migracion ~/.ssh/migracion.pub
(anterior)$ sed -i '/migracion/d' ~/.ssh/authorized_keys ; sudo rm -f /tmp/operaciones.dump /tmp/archivos.tgz /tmp/instance.tgz
```
**No borre ni apague definitivamente el servidor anterior todavía:** queda detenido como respaldo (§13).

> Si el servidor anterior usaba **SQLite** (archivo `instance/operaciones.db`) en vez de PostgreSQL, no use este
> procedimiento: la conversión es distinta. Pídala antes del corte.

---

## 8. Arrancar y dejarlo automático

```bash
$ sudo systemctl enable --now operaciones
$ sudo systemctl status operaciones --no-pager            # active (running)
$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/login     # 200
$ curl -s -o /dev/null -w '%{http_code}\n' https://DOMINIO/login           # 200 (sin -k: el certificado es válido)
```
Si el segundo falla, Caddy no obtuvo el certificado: revise `sudo journalctl -u caddy -n 50 --no-pager`. Las causas
habituales son el DNS (§4), que aún no apunta a esta IP, y el puerto 80 cerrado en el firewall (§1.3).

**Actualización automática desde GitHub** (revisa cada 5 minutos; respalda, migra y vuelve atrás si algo falla). Es
una decisión de la empresa:
- **activarla** (recomendado durante la marcha blanca, para recibir las correcciones sin intervención):
  ```bash
  $ sudo systemctl enable --now operaciones-actualizar.timer
  $ systemctl list-timers operaciones-actualizar.timer     # muestra la próxima ejecución
  ```
- **o** actualizar a mano cuando Sistemas lo decida: `sudo bash /opt/operaciones/deploy/actualizar.sh --forzar`.

Registro de las actualizaciones: `/var/log/operaciones-actualizar.log`.

---

## 9. Conexión con SAP (VPN WireGuard)

El Service Layer (`172.18.103.1:50000`) está en la red privada de la empresa. El servidor de AWS llega a él por una
VPN WireGuard cifrada, que **sale desde la empresa**: no se abren puertos en el router de la empresa ni se expone SAP a
internet.

1. ☐ Firewall de Lightsail: regla **UDP 51820** solo desde la IP pública de la empresa (§1.3).
2. En el servidor:
   ```bash
   $ sudo bash /opt/operaciones/deploy/vpn/instalar_wireguard_servidor.sh
   ```
   Muestra la **clave pública del servidor**. No es secreta: se usa en el equipo de la empresa.
3. En la empresa, elija una opción:
   - **A (recomendada):** una pasarela Linux siempre encendida. Use `deploy/vpn/wg-pasarela-linux.conf.ejemplo` y
     complete la clave pública del servidor y la IP fija de AWS.
   - **B:** WireGuard para Windows en el servidor de SAP, como servicio. Use `deploy/vpn/wg-sap-windows.conf.ejemplo`.

   En ese equipo genere sus claves (`wg genkey | tee privada.key | wg pubkey > publica.pub`) y active el túnel.
4. De vuelta en el servidor, con la **clave pública del equipo de la empresa**:
   ```bash
   $ sudo bash /opt/operaciones/deploy/vpn/instalar_wireguard_servidor.sh <CLAVE_PUBLICA_EMPRESA> 172.18.103.1
   $ sudo wg show                  # «latest handshake: … seconds ago»
   $ curl -k -s -o /dev/null -w '%{http_code}\n' https://172.18.103.1:50000/b1s/v1/     # cualquier código (401/404) = llega
   ```
5. Certificado del Service Layer (lo entrega el partner):
   ```bash
   $ sudo nano /etc/operaciones/sap_ca.pem          # pegue el certificado de la CA
   $ sudo chmod 644 /etc/operaciones/sap_ca.pem
   ```
   Si es autofirmado, puede obtenerse con:
   ```bash
   $ openssl s_client -connect 172.18.103.1:50000 -showcerts </dev/null 2>/dev/null | sed -n '/BEGIN CERT/,/END CERT/p' | sudo tee /etc/operaciones/sap_ca.pem
   ```
   Confirme su huella con el partner. El certificado suele estar emitido a un nombre y no a la IP: si la prueba del
   paso 6 falla por el nombre, use temporalmente `SAP_SL_VERIFY=0` en el `.env` y solicite al partner un certificado
   que incluya la IP.
6. Prueba (solo lectura) y diagnóstico:
   ```bash
   $ app ".venv/bin/python -m app.cli sap-probar"          # {'version': …, 'timeout_min': …}
   $ app ".venv/bin/python -m app.cli sap-diagnostico"
   $ sudo systemctl restart operaciones                     # activa la sincronización cada minuto (06:00–21:00)
   ```
7. En el sistema: **Configuración → Integración SAP**. La escritura de OV debe estar habilitada **solo** para la base de
   pruebas (`sap_escritura_empresas`) hasta que la Gerencia decida pasar a la base real (`docs/30` §5).
8. Si antes se usaba el túnel `deploy/tunel_sap.bat` desde la máquina virtual, quítelo del inicio de esa máquina
   **después** de comprobar la VPN.

---

## 10. Respaldos

### 10.1 Respaldo diario en el servidor (ya programado por el instalador)
```bash
$ cat /etc/cron.d/operaciones-respaldo             # 03:00 base y 03:15 archivos, guarda 14 días
$ sudo -u postgres pg_dump operaciones | gzip > /var/backups/operaciones/bd_prueba_$(date +%F).sql.gz   # prueba manual
$ ls -lh /var/backups/operaciones/
```

### 10.2 Copia fuera del servidor (S3)
Lightsail **no admite rol IAM** en la instancia. Por eso se usa un usuario IAM exclusivo para el respaldo, con permiso
solo sobre un bucket.

1. ☐ **S3 → Create bucket** en la misma región, p. ej. `cp-operaciones-respaldos`, con *Block all public access*
   **activado**. Opcional pero recomendado: *Versioning* activado y, en *Management → Lifecycle*, borrar las versiones
   con más de 90 días.
2. ☐ **IAM → Users → Create user** `respaldo-operaciones`, **sin** acceso a la consola. Agregue esta política en línea
   (cambie el nombre del bucket):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::cp-operaciones-respaldos"},
       {"Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject"], "Resource": "arn:aws:s3:::cp-operaciones-respaldos/*"}
     ]
   }
   ```
   Cree una **Access key** («Application running outside AWS»). Se muestra una vez y **no se envía a nadie**.
3. En el servidor:
   ```bash
   $ sudo snap install aws-cli --classic
   $ sudo aws configure            # pega Access key y Secret key; región del bucket; formato json
   $ sudo chmod 600 /root/.aws/credentials
   $ echo 'RESPALDO_S3=s3://cp-operaciones-respaldos/operaciones' | sudo tee -a /etc/operaciones/operaciones.env
   $ sudo bash /opt/operaciones/deploy/respaldo_s3.sh && tail -1 /var/log/operaciones-respaldo-s3.log
   $ echo '45 3 * * * root bash /opt/operaciones/deploy/respaldo_s3.sh' | sudo tee /etc/cron.d/operaciones-s3
   ```
4. ☐ En la consola de S3, confirme que aparecieron los archivos.

### 10.3 Probar que el respaldo sirve (una vez, antes de operar)
```bash
$ sudo -u postgres createdb prueba_restauracion
$ gunzip -c $(ls -t /var/backups/operaciones/bd_*.sql.gz | head -1) | sudo -u postgres psql -q prueba_restauracion
$ sudo -u postgres psql -d prueba_restauracion -tAc "select count(*) from sales_orders"
$ sudo -u postgres dropdb prueba_restauracion
```

---

## 11. Microsoft 365

En https://entra.microsoft.com, en la aplicación ya registrada: **Autenticación → URI de redirección**, debe estar
exactamente `https://DOMINIO/auth/microsoft/callback`. Si el dominio cambió con la migración, agregue el nuevo y, al
terminar la marcha blanca, quite el anterior.

Compruebe también que el **secreto de cliente** no esté vencido y anote su vencimiento en el calendario. El
procedimiento completo de registro está en `docs/25` §4.

---

## 12. Verificación final

### 12.1 Verificación automática del servidor
```bash
$ sudo bash /opt/operaciones/deploy/verificar_servidor.sh DOMINIO --sap
```
Revisa más de 60 puntos y no cambia nada:
- equipo, zona horaria y NTP, actualizaciones;
- IP fija contra DNS, puertos expuestos;
- HTTPS, certificado y cabeceras;
- servicios y arranque automático;
- variables, sin mostrar sus valores: `DEMO_MODE=0`, simulación deshabilitada, cookie segura, permisos 600;
- migraciones y esquema, sin simulaciones cargadas;
- ajuste de PostgreSQL, clave de notificaciones;
- respaldos locales y en S3, rotación de registros;
- VPN y SAP;
- SSH.

**Debe terminar con 0 fallas.** Los avisos deben revisarse uno por uno: algunos son decisiones (p. ej. la
actualización automática).

### 12.2 Verificación funcional (en el navegador y en un celular)

| ☐ | Prueba | Resultado esperado |
|---|---|---|
| ☐ | Abrir `https://DOMINIO` en PC y celular | Candado de HTTPS y la pantalla de ingreso, **sin** la franja de «Entorno de demostración» |
| ☐ | Ingresar con Microsoft 365 (cuenta de Sistemas) | Entra a su inicio |
| ☐ | Ingresar con un usuario y contraseña del módulo | Entra |
| ☐ | Si hubo migración: abrir OV, clientes, stock y alertas recientes | Los mismos datos que en el servidor anterior |
| ☐ | Abrir una foto o documento antiguo (p. ej. una entrega) | Se ve (los archivos se migraron) |
| ☐ | Subir una foto en cualquier formulario | Se guarda y se ve |
| ☐ | Descargar un informe en PDF y otro en Excel | Se descargan |
| ☐ | En el celular: «Activar» notificaciones y «Enviar una notificación de prueba» | Llega la notificación |
| ☐ | Ejecutar «Ejecutar verificaciones» en Alertas | Termina sin error |
| ☐ | Configuración → Integración SAP | Conexión «OK» y última sincronización reciente |
| ☐ | **Reinicio completo:** `sudo reboot`; a los 2 minutos abrir el sistema | Todo vuelve solo (servicio, VPN, Caddy) |
| ☐ | Lightsail → Snapshots → *Create snapshot* manual «post-migración» | Se crea (punto de retorno conocido) |

---

## 13. Corte del DNS y plan de retorno

Si hubo migración y el dominio apuntaba al servidor anterior:
1. Con el §12 sin fallas, cambie el registro A del dominio a la **IP fija nueva**. Con TTL de 300 s, el cambio se
   propaga en minutos.
2. Caddy obtiene el certificado del dominio en cuanto el DNS apunta a la IP nueva. Repita `verificar_servidor.sh`.
3. **Retorno, si algo grave falla en los primeros días:** vuelva el registro A a la IP anterior y arranque allá
   `sudo systemctl start operaciones`. Lo registrado en el servidor nuevo durante ese tiempo tendría que volver a
   migrarse: decida el retorno lo antes posible.
4. Mantenga el servidor anterior **detenido pero intacto** de 7 a 14 días. Después, tome una instantánea final de él y
   elimínelo para no seguir pagándolo.

---

## 14. Después de la puesta en marcha

- ☐ Retire las llaves SSH temporales (`~/.ssh/authorized_keys` de `ubuntu`) que se hayan agregado para la instalación.
- ☐ Documente en un lugar seguro de la empresa: IP fija, dominio, región, nombre de la instancia, bucket de respaldo y
  dónde están las llaves.
- ☐ Anote en el calendario los vencimientos: secreto de Microsoft 365, certificado del Service Layer y SOAT de la flota.
- ☐ Pase a la base real de SAP solo con la decisión de la Gerencia y la lista del `docs/30` §5.
- ☐ Una vez al mes: ejecute `verificar_servidor.sh` y revise el uso de disco y la factura de AWS.

## 15. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `https://DOMINIO` no carga y Caddy dice «challenge failed» | DNS no apunta a la IP fija, o puerto 80 cerrado | §4 y §1.3; luego `sudo systemctl restart caddy` |
| «502 Bad Gateway» | La aplicación no está corriendo | `sudo journalctl -u operaciones -n 100 --no-pager` |
| El servicio no arranca: error de `DATABASE_URL` | Clave mal copiada | Revise la línea del instalador (§5.2) |
| `alembic upgrade` dice «relation … already exists» | La base se creó sin Alembic | Anexo de `docs/25` |
| La franja «Entorno de demostración» aparece | `DEMO_MODE` no es 0 | §6 y `sudo systemctl restart operaciones` |
| Las notificaciones dejaron de llegar tras migrar | No se copió `instance/vapid_privada.pem` | §7.B.4; si no hay respaldo, cada usuario vuelve a «Activar» |
| «SAP sin conexión» | VPN caída o equipo de la empresa apagado | `sudo wg show`; encender la pasarela |
| La copia a S3 falla con `AccessDenied` | Política IAM con otro nombre de bucket | §10.2 |
| Disco lleno | Fotos y respaldos | `sudo du -sh /var/lib/operaciones/archivos /var/backups/operaciones`; `python -m app.cli depurar` |
