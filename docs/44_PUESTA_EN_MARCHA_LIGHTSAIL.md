# 44 · Puesta en marcha en AWS Lightsail: continuar la configuración (07-nov-2026)

Situación de partida:
- La instancia de Lightsail ya está creada.
- Ya se ejecutaron los comandos de instalación de paquetes: `apt update/upgrade`, `curl git ufw htop net-tools
  software-properties-common wireguard`, `postgresql postgresql-contrib`, `python3-pip python3-venv build-essential
  libpq-dev`. Esos paquetes son compatibles con el instalador del módulo y no hay que repetirlos ni quitarlos.
- **Instalación nueva:** no se migra nada del servidor de AWS Académico. Ese queda como entorno de prueba (paso 13).
- **Dominio:** se usará el de la empresa, con un subdominio propio para el sistema: **`operaciones.corporacionproductiva.com`**.
  La página de marketing (`www.corporacionproductiva.com`) y el correo no se tocan.
- **GitHub:** el repositorio `Sedano21/Proyecto` es **público**. El servidor revisa la rama cada 5 minutos y, si hay
  cambios, se actualiza solo: respalda, migra y vuelve atrás si algo falla.

Convención: `$` = comando en el servidor (usuario `ubuntu`). ☐ = acción en una consola web.
Todos los comandos se pueden copiar tal cual, salvo lo que está entre `< >`.

---

## Paso 0. Seguridad: la contraseña del FTP

La contraseña del FTP de la página web se compartió por chat. **Pida a marketing o al proveedor del hosting que la
cambie hoy.** El FTP **no se necesita** para el sistema: solo sirve para subir archivos de la página web y no da acceso
al DNS. Lo que sí se necesita es el acceso al **panel del dominio o del hosting** (paso 3).

---

## Paso 1. Revisión de la instancia en Lightsail (consola web)

| ☐ | Qué | Correcto si… |
|---|---|---|
| ☐ | Plan | 16 GB RAM · 4 vCPU · 320 GB SSD |
| ☐ | Sistema | Ubuntu 24.04 LTS (o 22.04) |
| ☐ | **Networking → Static IP** | Hay una IP estática **asociada** a la instancia. Anótela: es `<IP_FIJA>` |
| ☐ | **IPv4 Firewall** | Solo: SSH 22 (idealmente restringido a la IP de la oficina, con «Allow Lightsail browser SSH»), HTTP 80, HTTPS 443 y UDP 51820 (solo desde la IP pública de la empresa) |
| ☐ | **IPv6 Firewall** | Las mismas reglas (22, 80, 443) o ninguna regla si no usarán IPv6 |
| ☐ | **Snapshots → Automatic snapshots** | Activadas, a las 09:00 UTC (04:00 de Lima) |
| ☐ | **Metrics** | Alarma de CPU (> 80 % por 15 min) y de *Status check failed*, con correo de Sistemas confirmado |
| ☐ | Cuenta AWS | MFA en el usuario raíz y presupuesto mensual con aviso (*Billing → Budgets*) |

Detalle de cada punto: `docs/43` §1.

---

## Paso 2. Terminar de preparar el sistema operativo

```bash
# 2.1 Comprobar el equipo
$ lsb_release -d; nproc; free -h | head -2; df -h / | tail -1
$ curl -s https://checkip.amazonaws.com          # debe ser la <IP_FIJA>

# 2.2 Zona horaria y nombre
$ sudo timedatectl set-timezone America/Lima
$ sudo hostnamectl set-hostname operaciones-cp
$ timedatectl | grep -E "Time zone|synchronized"  # America/Lima · yes

# 2.3 Memoria de intercambio (4 GB)
$ sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
$ echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
$ echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf && sudo sysctl -p /etc/sysctl.d/99-swap.conf

# 2.4 Herramientas para revisar el DNS
$ sudo apt-get install -y dnsutils

# 2.5 Actualizaciones de seguridad automáticas (deben decir "enabled" y "1")
$ systemctl is-enabled unattended-upgrades; cat /etc/apt/apt.conf.d/20auto-upgrades

# 2.6 SSH solo con llave (debe decir "passwordauthentication no")
$ sudo sshd -T | grep -Ei '^(passwordauthentication|permitrootlogin)'
```

### 2.7 Firewall `ufw` (ya está instalado)
El firewall de Lightsail ya protege la instancia; `ufw` es una segunda capa opcional.

**Si decide activarlo, permita SSH antes de habilitarlo.** Si no, perderá el acceso al servidor:
```bash
$ sudo ufw allow OpenSSH
$ sudo ufw allow 80/tcp
$ sudo ufw allow 443/tcp
$ sudo ufw allow 51820/udp
$ sudo ufw --force enable
$ sudo ufw status verbose
```
Si no lo va a usar, déjelo desactivado: `sudo ufw status` debe decir `inactive`.

```bash
# 2.8 Reiniciar una vez y volver a conectarse
$ sudo reboot
```

---

## Paso 3. Dominio: `operaciones.corporacionproductiva.com`

**Sí se puede usar el dominio de la empresa.** Se crea un **subdominio** que apunta a la IP fija de Lightsail. La página
de marketing y el correo siguen en su hosting, sin cambios.

### 3.1 Averiguar dónde se administra el DNS
```bash
$ dig NS corporacionproductiva.com +short     # quién administra el DNS
$ dig A  corporacionproductiva.com +short     # dónde está la página web
$ dig MX corporacionproductiva.com +short     # dónde está el correo (no se toca)
```

| Si los servidores NS son… | El registro se crea en… |
|---|---|
| del hosting de la página (p. ej. `ns1.<hosting>.com`; con `ftp.dominio` suele ser cPanel) | **cPanel → Dominios → Zone Editor (Editor de zonas)** del hosting. Necesita el usuario de **cPanel**, no el de FTP; lo tiene marketing o el proveedor |
| `*.cloudflare.com` | Panel de Cloudflare del dominio |
| `*.awsdns-*` | Route 53, en AWS |
| del registrador (GoDaddy, Punto.pe, etc.) | Panel DNS del registrador |

### 3.2 Crear el registro
☐ En el panel que corresponda, **agregar** (no modificar los existentes):

| Tipo | Nombre / Host | Valor / Apunta a | TTL |
|---|---|---|---|
| **A** | `operaciones` | `<IP_FIJA>` | 300 (5 min) |

- **No** cambie los registros `@`, `www`, `mail`, `ftp` ni `MX`: son de la página web y del correo.
- Si es **Cloudflare**, deje el registro en **«DNS only» (nube gris)**. Así Caddy obtiene el certificado HTTPS
  directamente.
- Si el panel pide el nombre completo, escriba `operaciones.corporacionproductiva.com`.

### 3.3 Verificar (a los 5–15 minutos)
```bash
$ dig A operaciones.corporacionproductiva.com +short       # debe mostrar <IP_FIJA>
$ dig A operaciones.corporacionproductiva.com @8.8.8.8 +short
```
**No continúe con el paso 4 hasta que responda la IP fija:** el certificado HTTPS se emite con ese registro.

Si marketing no tiene acceso al panel DNS, como solución temporal se puede usar el subdominio de DuckDNS. Más
adelante se cambia al dominio de la empresa repitiendo solo el paso 4.3.

---

## Paso 4. Instalar el módulo

```bash
# 4.1 Código (repositorio público)
$ sudo git clone --branch claude/automatizacion-corporativa-app-1cu2g5 https://github.com/Sedano21/Proyecto.git /opt/operaciones

# 4.2 Instalador: Caddy (HTTPS), entorno Python, base PostgreSQL, servicio, ajuste de PostgreSQL para 16 GB,
#     respaldo diario y rotación de registros. Al final muestra la línea DATABASE_URL: CÓPIELA.
$ sudo bash /opt/operaciones/deploy/instalar_ubuntu.sh operaciones.corporacionproductiva.com
```

Si necesita volver a ver la línea de la base (solo la muestra la primera vez), cree una clave nueva:
```bash
$ CLAVE=$(openssl rand -hex 16); sudo -u postgres psql -c "ALTER USER operaciones WITH PASSWORD '$CLAVE';"; echo "postgresql+psycopg://operaciones:$CLAVE@127.0.0.1:5432/operaciones"
```

### 4.3 Comprobar
```bash
$ systemctl is-active postgresql caddy                    # active active
$ sudo -u postgres psql -tAc "show shared_buffers"        # 4GB
$ cat /etc/caddy/Caddyfile | grep corporacionproductiva    # el dominio quedó configurado
```

---

## Paso 5. Variables del servidor (secretos solo aquí)

```bash
$ openssl rand -hex 32                     # copie el resultado: será SECRET_KEY
$ sudo nano /etc/operaciones/operaciones.env
```
Deje el archivo así; reemplace todo lo que está entre `< >`:
```ini
SECRET_KEY=<resultado de openssl rand -hex 32>
DATABASE_URL=<la línea que mostró el instalador>
UPLOAD_DIR=/var/lib/operaciones/archivos
SESSION_COOKIE_SECURE=1
DEMO_MODE=0
SCHEMA_AUTO_CREATE=0
APP_TZ=America/Lima

SAP_SL_URL=https://172.18.103.1:50000/
SAP_SL_COMPANY=ZZZ_CORPRODUC_TEST260826
SAP_SL_USER=<usuario de integración de SAP>
SAP_SL_PASSWORD=<su contraseña>
SAP_SL_CA=/etc/operaciones/sap_ca.pem
SAP_SYNC_MIN=1
SAP_SYNC_USER=sistemas

M365_TENANT_ID=<Id. de directorio>
M365_CLIENT_ID=<Id. de aplicación>
M365_CLIENT_SECRET=<secreto de cliente>
M365_REDIRECT_URI=https://operaciones.corporacionproductiva.com/auth/microsoft/callback

VAPID_SUB=mailto:sistemas@corporacionproductiva.com
RESPALDO_S3=
GEOSAT_API_URL=
GEOSAT_TOKEN=
```
- No escriba `SIMULACION_HABILITADA`: la simulación es solo para el entorno de pruebas.
- Si todavía no tiene los datos de SAP o de Microsoft 365, déjelos vacíos y complételos después (pasos 9 y 11). Tras
  cada cambio del archivo: `sudo systemctl restart operaciones`.

```bash
$ sudo chown root:root /etc/operaciones/operaciones.env && sudo chmod 600 /etc/operaciones/operaciones.env
$ sudo stat -c '%a %U' /etc/operaciones/operaciones.env          # 600 root
```

---

## Paso 6. Crear la base (nueva) y la cuenta de Sistemas

```bash
$ app() { sudo -u operaciones bash -c "set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; $*"; }
$ app ".venv/bin/alembic upgrade head"                 # crea todas las tablas (versión 0037)
$ app ".venv/bin/python -m app.cli init"               # catálogos, perfiles, permisos y parámetros; sin datos de demostración
$ app ".venv/bin/python -m app.cli esquema"            # «La base coincide con el código.»
$ app ".venv/bin/python -m app.cli crear-usuario sistemas SISTEMAS 'Administrador de Sistemas' <correo>@corporacionproductiva.com"
```
- `crear-usuario` pide la contraseña en pantalla; no queda en el historial.
- Tome nota: la función `app()` hay que definirla de nuevo cada vez que abra una sesión SSH nueva.

---

## Paso 7. Arrancar y conectar GitHub (actualización automática)

```bash
$ sudo systemctl enable --now operaciones
$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/login                               # 200
$ curl -s -o /dev/null -w '%{http_code}\n' https://operaciones.corporacionproductiva.com/login       # 200

# Detección de cambios en GitHub: cada 5 minutos
$ sudo systemctl enable --now operaciones-actualizar.timer
$ systemctl list-timers operaciones-actualizar.timer      # muestra la próxima revisión
$ sudo bash /opt/operaciones/deploy/actualizar.sh --forzar && sudo tail -5 /var/log/operaciones-actualizar.log   # prueba: «OK … en <versión>»
```

**Cómo funciona.** Cada 5 minutos el servidor compara su versión con la rama
`claude/automatizacion-corporativa-app-1cu2g5` de GitHub. Si hay un commit nuevo:
1. respalda la base en `/var/backups/operaciones/bd_antes_<versión>_…`;
2. descarga el código e instala las dependencias;
3. aplica las migraciones (`alembic upgrade head`) y los catálogos nuevos (`init`);
4. reinicia el servicio y comprueba que responda;
5. **si no responde, vuelve sola a la versión anterior.**

Todo queda en `/var/log/operaciones-actualizar.log`. Para ver en qué versión está: `git -C /opt/operaciones log --oneline -1`.

**Reglas para que no se trabe:**
- No editar archivos dentro de `/opt/operaciones` en el servidor. La configuración va solo en
  `/etc/operaciones/operaciones.env`. Los cambios del módulo se hacen en GitHub.
- Para pausar las actualizaciones (p. ej. durante un cierre de mes):
  `sudo systemctl stop operaciones-actualizar.timer`. Para reanudarlas: `sudo systemctl start operaciones-actualizar.timer`.

---

## Paso 8. Verificación automática

```bash
$ sudo bash /opt/operaciones/deploy/verificar_servidor.sh operaciones.corporacionproductiva.com
```
Debe terminar con **0 fallas**. En este punto son normales los avisos de SAP, Microsoft 365, VPN y S3: se resuelven en
los pasos siguientes. Repítalo al final de todo, con `--sap`.

---

## Paso 9. Conexión con SAP por VPN (WireGuard; el paquete ya está instalado)

```bash
# 9.1 Claves del servidor: muestra la CLAVE PÚBLICA del servidor (no es secreta)
$ sudo bash /opt/operaciones/deploy/vpn/instalar_wireguard_servidor.sh
```
9.2 ☐ En la empresa, en una pasarela Linux siempre encendida (opción A) o en el servidor SAP con WireGuard para Windows
(opción B), cree la configuración con los ejemplos `deploy/vpn/wg-pasarela-linux.conf.ejemplo` o
`deploy/vpn/wg-sap-windows.conf.ejemplo`. Coloque la clave pública del servidor y `Endpoint = <IP_FIJA>:51820`, y
active el túnel.

```bash
# 9.3 Registrar el equipo de la empresa (con SU clave pública) y probar
$ sudo bash /opt/operaciones/deploy/vpn/instalar_wireguard_servidor.sh <CLAVE_PUBLICA_EQUIPO_EMPRESA> 172.18.103.1
$ sudo wg show                                                     # «latest handshake: … seconds ago»
$ curl -k -s -o /dev/null -w '%{http_code}\n' https://172.18.103.1:50000/b1s/v1/     # cualquier código = llega a SAP

# 9.4 Certificado del Service Layer (lo entrega el partner; o se obtiene así y se confirma la huella con él)
$ openssl s_client -connect 172.18.103.1:50000 -showcerts </dev/null 2>/dev/null | sed -n '/BEGIN CERT/,/END CERT/p' | sudo tee /etc/operaciones/sap_ca.pem
$ sudo chmod 644 /etc/operaciones/sap_ca.pem

# 9.5 Prueba de conexión (solo lectura) y diagnóstico
$ sudo systemctl restart operaciones
$ app ".venv/bin/python -m app.cli sap-probar"          # {'version': …}
$ app ".venv/bin/python -m app.cli sap-diagnostico"
```
- Si `sap-probar` falla por el nombre del certificado: agregue `SAP_SL_VERIFY=0` al `.env` de forma temporal y pida al
  partner un certificado que incluya la IP.
- Con la opción B, use `SAP_SL_URL=https://10.77.0.2:50000/` (`docs/36` §5).

### 9.6 Datos iniciales desde SAP (la base está vacía)
```bash
$ app ".venv/bin/python -m app.cli sap-traer CLIENTES sistemas"
$ app ".venv/bin/python -m app.cli sap-traer PRODUCTOS sistemas"
$ app ".venv/bin/python -m app.cli sap-traer OV sistemas"
```
Cada comando crea una **carga para revisar**. Se confirman en el sistema, en **Cargas de archivos**. El stock por lote
se trae según `docs/36` (consulta `sap-consulta-stock`) o con la carga Excel de SAP.

---

## Paso 10. Respaldos

```bash
# 10.1 Respaldo diario local (ya programado): 03:00 base y 03:15 archivos, guarda 14 días
$ cat /etc/cron.d/operaciones-respaldo
$ sudo -u postgres pg_dump operaciones | gzip | sudo tee /var/backups/operaciones/bd_prueba_$(date +%F).sql.gz >/dev/null && ls -lh /var/backups/operaciones/
```

### 10.2 Copia externa en S3
Lightsail no admite rol IAM: se usa un usuario IAM solo para el respaldo.

1. ☐ **S3 → Create bucket** `cp-operaciones-respaldos`, en la misma región, con *Block all public access* activado.
2. ☐ **IAM → Users → Create user** `respaldo-operaciones`, sin consola, con esta política en línea:
   ```json
   {"Version": "2012-10-17", "Statement": [
     {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::cp-operaciones-respaldos"},
     {"Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject"], "Resource": "arn:aws:s3:::cp-operaciones-respaldos/*"}]}
   ```
   Cree una *Access key*. No la envíe a nadie.
3. En el servidor:
   ```bash
   $ sudo snap install aws-cli --classic
   $ sudo aws configure                     # Access key, Secret key, región del bucket, json
   $ sudo chmod 600 /root/.aws/credentials
   $ sudo sed -i 's#^RESPALDO_S3=.*#RESPALDO_S3=s3://cp-operaciones-respaldos/operaciones#' /etc/operaciones/operaciones.env
   $ sudo bash /opt/operaciones/deploy/respaldo_s3.sh && tail -1 /var/log/operaciones-respaldo-s3.log
   $ echo '45 3 * * * root bash /opt/operaciones/deploy/respaldo_s3.sh' | sudo tee /etc/cron.d/operaciones-s3
   ```

---

## Paso 11. Microsoft 365

☐ En https://entra.microsoft.com → la aplicación registrada → **Autenticación → URI de redirección (Web)**: agregue
`https://operaciones.corporacionproductiva.com/auth/microsoft/callback`. Si todavía no está registrada, siga el
`docs/25` §4.1. Copie los tres datos al `.env` (paso 5) y reinicie: `sudo systemctl restart operaciones`.

---

## Paso 12. Usuarios y verificación final

1. Ingrese con la cuenta `sistemas` y cargue los usuarios por Excel (*Usuarios y permisos → Cargar usuarios desde Excel*; formato en
   `docs/25` §8.1).
2. Verificación completa:
   ```bash
   $ sudo bash /opt/operaciones/deploy/verificar_servidor.sh operaciones.corporacionproductiva.com --sap
   ```
3. Pruebas en PC y celular:

| ☐ | Prueba | Resultado esperado |
|---|---|---|
| ☐ | `https://operaciones.corporacionproductiva.com` | Candado HTTPS, sin la franja de «demostración» |
| ☐ | Ingreso con Microsoft 365 | Entra |
| ☐ | Subir una foto, descargar un PDF y un Excel | Funciona |
| ☐ | Celular: «Activar» notificaciones → «Enviar una notificación de prueba» | Llega |
| ☐ | *Configuración → Integración SAP* | Conexión OK y sincronización reciente |
| ☐ | `sudo reboot` y abrir el sistema a los 2 minutos | Todo vuelve solo |
| ☐ | Lightsail → *Create snapshot* manual «puesta-en-marcha» | Creada |

---

## Paso 13. El servidor de AWS Académico

Queda como **entorno de pruebas**: no se copia nada de él. Para que **no choque** con el servidor de producción:
- **No dejar los dos sincronizando con SAP a la vez.** En el académico, ponga `SAP_SYNC_MIN=0` en su `.env` (o vacíe
  los datos de SAP) y reinicie el servicio. Así no se crean OV duplicadas en la base de pruebas de SAP ni se
  confunden las cargas.
- Si se quiere usar para probar la simulación (`docs/41`), solo ahí se define `SIMULACION_HABILITADA=1`.
- El túnel `deploy/tunel_sap.bat` de la máquina virtual apuntaba al académico: retírelo cuando la VPN del paso 9
  funcione.
