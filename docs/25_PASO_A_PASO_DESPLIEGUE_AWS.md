# Paso a paso: servidor en AWS, DuckDNS, Microsoft 365 y conexión con SAP (28-oct-2026)

Guía para poner el módulo en un servidor y conectarlo con SAP Business One. Indica qué hace la empresa, en qué orden y qué datos me debe enviar.

**Regla para todo el documento:** ninguna contraseña, token ni clave se envía por chat ni por correo, y nunca se guarda en el repositorio. Las claves se escriben solo en el archivo del servidor `/etc/operaciones/operaciones.env` (permisos 600).

---

## 0. ¿AWS u Oracle?

**Sí: AWS es una buena opción, y es la que recomiendo para la empresa.** Las dos sirven, porque el script de instalación funciona igual en cualquier servidor Ubuntu.

| | AWS Lightsail (recomendado) | Oracle Cloud «Always Free» |
|---|---|---|
| Costo | Desde 12 USD/mes con IPv4 (2 GB RAM, 2 vCPU, 60 GB SSD, 3 TB de tráfico) | 0 USD de forma permanente |
| Periodo gratuito | Los planes de 2 GB califican para el periodo gratuito de Lightsail, que la página de precios anuncia en 3 meses. Además, las cuentas nuevas reciben créditos de prueba (hasta 200 USD por 6 meses), pero **no es gratis para siempre** | Gratis siempre, dentro de los límites «Always Free» |
| Precio fijo y simple | Sí: plan mensual cerrado, que incluye IP fija, firewall e instantáneas | Sí, mientras se usen solo recursos gratuitos |
| Riesgos | Ninguno técnico; es un costo mensual | Oracle puede **recuperar** una VM gratuita poco usada, y a veces no hay capacidad para crear la VM gratuita en la región |
| Soporte y reputación corporativa | Muy alta; facturación en USD a la tarjeta de la empresa | Alta |

Recomendaciones:
- **Lightsail** (no EC2): el precio es fijo y la configuración, mucho más simple.
- **Plan de 2 GB** (12 USD/mes). El plan de 1 GB queda justo para PostgreSQL más la aplicación.
- **Región:** São Paulo (`sa-east-1`) tiene menor latencia desde Lima, pero cuesta algo más. N. Virginia (`us-east-1`) es la más barata. Ambas funcionan; confirme el precio en la consola al elegir.
- Active una **alerta de facturación** en AWS (Billing → Budgets) por, p. ej., 20 USD/mes.

Fuentes (verificadas al 28-oct-2026; confirme el precio en la consola al crear el servidor):
- [Precios de Lightsail](https://aws.amazon.com/lightsail/pricing)
- [Nuevo plan gratuito de AWS con créditos (jul-2025)](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/)
- [Resumen de precios de Lightsail](https://cloudburn.io/blog/amazon-lightsail-pricing)

---

## 1. Resumen: qué necesito de ustedes

| # | Qué | Quién | Qué me envían |
|---|---|---|---|
| 1 | Servidor AWS Lightsail con IP fija | Sistemas / TI | La **IP pública** fija |
| 2 | DuckDNS apuntando a esa IP | Sistemas (ya creado) | El **nombre del subdominio** (p. ej. `operaciones-cp.duckdns.org`). El **token** de DuckDNS no se envía. |
| 3 | Acceso al servidor por SSH | Sistemas | Una de dos opciones (§2.4): (a) Sistemas ejecuta los comandos de esta guía; (b) me agregan una **llave pública SSH** temporal. |
| 4 | Aplicación registrada en Microsoft 365 (Entra ID) | Administrador de Microsoft 365 | **ID de inquilino (tenant)** e **ID de aplicación (cliente)**. El **secreto** se escribe directamente en el servidor. |
| 5 | Puente con Tailscale hacia SAP | Sistemas + quien administre la red de la oficina | Confirmación de que el servidor llega a `172.18.103.1:50000` |
| 6 | Usuario de integración en SAP | Partner/administrador de SAP | Nombre del usuario (la clave va al servidor) y confirmación de su **licencia** |
| 7 | Certificado del Service Layer | Partner/administrador de SAP | Archivo de la **CA** del certificado (`.pem` o `.crt`); no es secreto |
| 8 | Perfiles pendientes de los usuarios | Gerencia | Respuesta a la tabla del §8.2 |

---

## 2. Servidor en AWS Lightsail

### 2.1 Crear la cuenta (si la empresa no tiene)
1. Ingrese a https://aws.amazon.com y elija **Crear una cuenta de AWS**. Use un correo de la empresa (p. ej. el de Sistemas), no uno personal.
2. Registre la tarjeta de la empresa y verifique el teléfono.
3. Active la **verificación en dos pasos (MFA)** del usuario raíz: *Security credentials → Assign MFA*.
4. Recomendado: cree un usuario de trabajo (IAM Identity Center o IAM) y no use el usuario raíz a diario.
5. En *Billing → Budgets*, cree un presupuesto mensual con aviso por correo.

### 2.2 Crear el servidor
1. Abra https://lightsail.aws.amazon.com → **Create instance**.
2. **Región:** São Paulo o N. Virginia (ver §0).
3. **Plataforma:** Linux/Unix. **Blueprint:** *OS Only* → **Ubuntu 24.04 LTS**.
4. **SSH key pair:** use la llave por defecto de la región o cree una y descárguela. Guárdela con cuidado: es la llave del servidor.
5. **Plan:** 2 GB RAM / 2 vCPU / 60 GB SSD, con IPv4.
6. **Nombre:** `operaciones-cp`. Clic en **Create instance**.

### 2.3 IP fija y firewall
1. En la instancia, pestaña **Networking** → **Attach static IP** → créela y asígnela. Esa es la **IP pública** que debe enviarme. Una IP estática asignada a una instancia no tiene costo adicional.
2. En **IPv4 Firewall**, deje solo estas reglas:
   - `SSH 22`: restrinja el origen a la IP de la oficina, si es fija. Si no, déjelo abierto: el ingreso es solo con llave.
   - `HTTP 80`: lo necesita Let's Encrypt para emitir el certificado; Caddy redirige luego a HTTPS.
   - `HTTPS 443`.
3. No abra el puerto de PostgreSQL (5432) ni ningún otro.
4. En la pestaña **Snapshots**, active las **instantáneas automáticas** diarias. Tienen un costo pequeño por GB y permiten recuperar el servidor completo.

### 2.4 Acceso para la instalación
Elija una opción:
- **(a) Sistemas ejecuta los comandos** de los §5 y §6 desde *Connect using SSH* en la consola de Lightsail (se abre en el navegador). Yo acompaño por llamada o chat.
- **(b) Acceso temporal para mí:** les envío una **llave pública** SSH y la agregan en `~/.ssh/authorized_keys` del usuario `ubuntu`. Al terminar la marcha blanca la retiran.

---

## 3. DuckDNS (ya creado)

1. En https://www.duckdns.org, en su subdominio, escriba la **IP fija** del §2.3 en *current ip* y pulse **update ip**.
2. Compruebe desde cualquier PC: `nslookup <subdominio>.duckdns.org` debe responder esa IP.
3. Como la IP de Lightsail es fija, **no hace falta** el programa que actualiza la IP. El **token** de DuckDNS no se instala en el servidor ni se envía a nadie.
4. **Envíeme solo el nombre** del subdominio.

> Si más adelante prefieren un dominio propio (`operaciones.corporacionproductiva.com`), basta con crear un registro DNS `A` hacia la misma IP y repetir el §5.2 con ese nombre.

---

## 4. Microsoft 365 (ingreso con el correo corporativo)

Lo hace un **administrador de Microsoft 365** de la empresa en https://entra.microsoft.com:

1. **Identidad → Aplicaciones → Registros de aplicaciones → Nuevo registro**.
   - Nombre: `Operaciones Corporación Productiva`.
   - Tipos de cuenta: **Solo las cuentas de este directorio organizativo** (un solo inquilino).
   - URI de redirección: plataforma **Web**, valor `https://<subdominio>.duckdns.org/auth/microsoft/callback`.
2. En **Información general**, copie el **Id. de aplicación (cliente)** y el **Id. de directorio (inquilino)**. Envíeme esos dos datos; no son secretos.
3. **Certificados y secretos → Nuevo secreto de cliente**, con vencimiento de 12 o 24 meses. Copie el **valor** en ese momento: se muestra una sola vez.
   - **No lo envíe:** se escribe directamente en el servidor, en `M365_CLIENT_SECRET` (§5.3).
   - Anote en el calendario la fecha de vencimiento.
4. **Permisos de API:**
   - Para el ingreso basta con `User.Read` (delegado), que viene por defecto.
   - Opcional, para enviar el correo de alertas desde una cuenta de la empresa: `Mail.Send` (aplicación). Pulse **Conceder consentimiento de administrador**. Lo recomendable es limitarlo a un buzón con una *Application Access Policy*.
5. Opcional: en **Aplicaciones empresariales → (la aplicación) → Propiedades**, active «¿Se requiere la asignación?» y asigne solo al personal que usará el módulo.

El módulo deja entrar solo a quien cumple las dos condiciones:
- inicia sesión con una cuenta del inquilino de la empresa;
- su correo existe en el módulo con un perfil activo (§8).

---

## 5. Instalación del módulo en el servidor

### 5.1 Acceso al código
El servidor descarga el código del repositorio `sedano21/proyecto`, rama `claude/automatizacion-corporativa-app-1cu2g5`.
- **Repositorio público:** no se necesita nada.
- **Repositorio privado:** el dueño del repositorio crea en GitHub una **clave de despliegue de solo lectura** (*Settings → Deploy keys → Add deploy key*, sin «Allow write access») con la llave pública del servidor:
  ```bash
  sudo ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519 && sudo cat /root/.ssh/id_ed25519.pub
  ```
  Luego se instala con `REPO=git@github.com:sedano21/proyecto.git`.

### 5.2 Ejecutar el instalador
Conectado al servidor (usuario `ubuntu`):
```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone --branch claude/automatizacion-corporativa-app-1cu2g5 https://github.com/sedano21/proyecto.git /opt/operaciones
sudo bash /opt/operaciones/deploy/instalar_ubuntu.sh <subdominio>.duckdns.org
```

El script instala:
- Python, PostgreSQL y Caddy (HTTPS automático con Let's Encrypt);
- el servicio `operaciones` (gunicorn);
- el respaldo diario a las 03:00, guardado 14 días en `/var/backups/operaciones`.

Al final **muestra la clave generada para la base de datos**: cópiela para el paso siguiente.

### 5.3 Completar las variables (secretos solo aquí)
```bash
sudo nano /etc/operaciones/operaciones.env
```

| Variable | Valor |
|---|---|
| `SECRET_KEY` | Un valor aleatorio largo: `openssl rand -hex 32` |
| `DATABASE_URL` | La línea que mostró el instalador |
| `SESSION_COOKIE_SECURE` | `1` |
| `DEMO_MODE` | `0` |
| `SAP_SL_URL` | `https://172.18.103.1:50000/` |
| `SAP_SL_COMPANY` | `ZZZ_CORPRODUC_TEST260826` (base de **pruebas** durante la marcha blanca) |
| `SAP_SL_USER` / `SAP_SL_PASSWORD` | Usuario de integración (§7). **No usar `manager`.** |
| `SAP_SL_CA` | `/etc/operaciones/sap_ca.pem` (§7.3) |
| `SAP_SYNC_MIN` | `1` (cada minuto, de 06:00 a 21:00) |
| `SAP_SYNC_USER` | `sistemas` |
| `M365_TENANT_ID` / `M365_CLIENT_ID` | Datos del §4.2 |
| `M365_CLIENT_SECRET` | Valor del §4.3 |
| `M365_REDIRECT_URI` | `https://<subdominio>.duckdns.org/auth/microsoft/callback` |
| `GEOSAT_API_URL` / `GEOSAT_TOKEN` | Vacíos. El panel de GEOSATELITAL se abre con la sesión de cada usuario; **su usuario y contraseña no se guardan en el módulo**. |

Verifique los permisos del archivo: `sudo ls -l /etc/operaciones/operaciones.env` debe mostrar `-rw-------`.

### 5.4 Crear la base, la cuenta de Sistemas y arrancar
```bash
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/alembic upgrade head; .venv/bin/python -m app.cli init'
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/python -m app.cli crear-usuario sistemas SISTEMAS "Administrador de Sistemas" <correo-de-sistemas>@corporacionproductiva.com'
sudo systemctl start operaciones
sudo systemctl status operaciones --no-pager
```
- `init` crea las tablas y los catálogos, **sin datos de demostración**.
- `crear-usuario` pide la contraseña en pantalla (no queda en el historial).

### 5.5 Comprobación
1. Abra `https://<subdominio>.duckdns.org` desde una PC y desde un celular: debe verse el candado de HTTPS y la pantalla de ingreso.
2. Pruebe **Ingresar con Microsoft 365** con la cuenta de Sistemas. El correo debe coincidir con el que usó en `crear-usuario`.
3. Registros, si algo falla: `sudo journalctl -u operaciones -n 100 --no-pager` y `sudo journalctl -u caddy -n 50 --no-pager`.

---

## 6. Puente seguro hacia SAP (Tailscale)

El Service Layer está en una dirección privada (`172.18.103.1`), visible solo dentro de la red de la oficina. Tailscale crea un túnel cifrado entre el servidor de AWS y **un equipo de la oficina**, sin abrir puertos en el firewall de la empresa ni exponer SAP a internet.

### 6.1 Cuenta
- Cree una cuenta en https://tailscale.com con la cuenta Microsoft de la empresa (p. ej. la de Sistemas).
- El plan **Personal** es gratuito. Si la empresa prefiere un plan de negocio, existe el plan *Starter*, de pago.

### 6.2 Equipo puente en la oficina
Requisitos:
- Windows o Linux, con acceso a `172.18.103.1:50000`. Pruebe en ese equipo: `Test-NetConnection 172.18.103.1 -Port 50000` debe dar `TcpTestSucceeded : True`.
- Encendido de **06:00 a 21:00** como mínimo, sin suspensión. Lo ideal es un servidor o una PC fija.

Pasos:
1. Instale Tailscale desde https://tailscale.com/download e inicie sesión con la cuenta del §6.1.
2. Publique la ruta solo hacia SAP (*subnet router*):
   - **Linux:** `sudo tailscale up --advertise-routes=172.18.103.1/32`. Antes active el reenvío: `echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-tailscale.conf && sudo sysctl -p /etc/sysctl.d/99-tailscale.conf`.
   - **Windows** (consola como administrador): `tailscale up --advertise-routes=172.18.103.1/32`.
3. En https://login.tailscale.com/admin/machines:
   - en ese equipo, menú **…** → **Edit route settings** → apruebe `172.18.103.1/32`;
   - desactive **Key expiry** en el equipo puente y en el servidor, para que no se desconecten a los 180 días.

### 6.3 Servidor de AWS
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --accept-routes          # abre un enlace para autorizar el equipo con la misma cuenta
curl -vk https://172.18.103.1:50000/b1s/v1/ 2>&1 | head -20   # debe responder el Service Layer
```

### 6.4 Recomendaciones de red
- Limite el acceso con las **ACL de Tailscale**: que el servidor solo llegue a `172.18.103.1:50000`.
- Si la oficina tiene un firewall que filtra la salida, Tailscale necesita salida UDP 41641 o, en su defecto, HTTPS 443.

---

## 7. SAP Business One (Service Layer)

### 7.1 Usuario de integración
- Lo crea el **partner o administrador de SAP**. No se usa `manager`: es el superusuario y su clave ya circuló por un canal no seguro.
- Asígnele la **licencia de acceso indirecto / integración** anunciada por el partner.
- Permisos mínimos:
  - **lectura** de pedidos de cliente, socios de negocio, artículos, stock por almacén, entregas y facturas;
  - **creación de ofertas de venta (cotizaciones)** solo en la base de pruebas.
- Use una contraseña nueva y larga. Se escribe solo en `SAP_SL_PASSWORD` (§5.3).

### 7.2 Base de datos
- Durante la marcha blanca: **`ZZZ_CORPRODUC_TEST260826`** (pruebas).
- El módulo **solo escribe cotizaciones** en las bases listadas en el parámetro `sap_escritura_empresas`, que hoy contiene únicamente la de pruebas.
- Pasar a la base productiva es una **decisión de la Gerencia**, posterior a la marcha blanca.

### 7.3 Certificado del Service Layer
- Pida al partner el certificado de la **CA** que firmó el certificado del Service Layer (`.pem` o `.crt`).
- Cópielo al servidor como `/etc/operaciones/sap_ca.pem`.
- Si el certificado es autofirmado, puede obtenerlo así:
  ```bash
  openssl s_client -connect 172.18.103.1:50000 -showcerts </dev/null 2>/dev/null | sed -n '/BEGIN CERT/,/END CERT/p' | sudo tee /etc/operaciones/sap_ca.pem
  ```
  Si lo obtiene de esa forma, confirme su huella con el partner.
- `SAP_SL_VERIFY=0` solo para una prueba puntual, nunca permanente.

### 7.4 Prueba de conexión (solo lectura)
```bash
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/python -m app.cli sap-probar'
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/python -m app.cli sap-traer OV sistemas'
sudo systemctl restart operaciones   # activa la sincronización automática cada minuto (06:00–21:00)
```
- `sap-probar` debe responder con la sesión iniciada y la versión.
- `sap-traer` crea una carga **para revisar**: no se aplica sola.

---

## 8. Usuarios

### 8.1 Carga por Excel
En **Usuarios y permisos → Cargar usuarios desde Excel**:

| Columna | Contenido |
|---|---|
| **Correo** | Correo corporativo; lo usa el ingreso con Microsoft 365 |
| **Apellidos y nombres** | Nombre completo |
| **Rol** | Código o nombre del perfil del sistema |
| **Almacén** | Opcional; p. ej. `ALM-001` = 1560, `EXT-002` = 1524 |

Reglas de la carga:
- El DNI **no se guarda**.
- El nombre de usuario es la parte del correo antes de la «@».
- La clave local es aleatoria: el ingreso es con Microsoft 365.
- Si el correo ya existe, se actualizan el nombre y el perfil (no se duplica).
- **Las filas sin perfil válido o con correo inválido no se cargan** y se informan en pantalla.

Preparé un archivo con los 34 correos recibidos y el perfil propuesto para cada área. Lo entregué por separado y **no está en el repositorio** porque contiene datos personales.

### 8.2 Perfiles que necesitan decisión de la Gerencia
Estas áreas no tienen un perfil equivalente en el módulo. No los inventé: esas filas van con «Rol» vacío y no se cargarán hasta que se defina.

| Área (cantidad) | Pregunta |
|---|---|
| Tesorería (4) | ¿Acceden? ¿Con el perfil de Finanzas (`COORD_FINANZAS`: condición de pago y créditos) o solo lectura? |
| Gerente de Administración y Finanzas (1) | ¿`COORD_FINANZAS`, `GERENCIA_GENERAL` u otro? |
| Costos y Presupuestos (1) | ¿Acceden? Verían costos y márgenes. |
| Marketing: Jefa y Asistente (2) | ¿Acceden? ¿Con qué alcance (catálogo, indicadores comerciales)? |
| Capital Humano (1) | ¿Acceden (turnos y asistencia)? |
| Jefe de Mantenimiento (1) | El mantenimiento de flota hoy lo gestiona Distribución. ¿Se crea un perfil de Mantenimiento? |
| Asistente de Importaciones & Compras (1) | El sistema asigna un perfil por usuario: ¿`IMPORTACIONES` o `COMPRAS`? |

**Dato a corregir:** un correo del listado está incompleto (le falta «.com»). La carga lo rechazará hasta corregirlo.

### 8.3 Datos operativos
1. **Flota → Cargar Excel de GEOSATELITAL:** placas, marca, modelo, año y capacidad. Una unidad sin capacidad no se asigna a rutas.
2. **Comercial → OV desde SAP:**
   - la lista de pedidos de cliente y el detalle de cada OV, como contingencia;
   - con el Service Layer conectado, llegan solos.
3. Revise los parámetros de la marcha blanca en **Configuración**.

---

## 9. Calendario propuesto

| Fecha | Actividad | Responsable |
|---|---|---|
| Mié 28-oct | Cuenta AWS, servidor, IP fija, DuckDNS; registro en Entra ID | Sistemas, admin. M365 |
| Mié 28 / jue 29-oct | Instalación (§5) y equipo puente con Tailscale (§6) | Sistemas + yo |
| Jue 29-oct | Usuario de integración SAP con licencia y CA (§7); `sap-probar` | Partner SAP |
| Jue 29 / vie 30-oct | Carga de usuarios (tras decidir el §8.2), flota y OV; prueba con cada área | Sistemas, Gerencia |
| 29-oct al 1-nov | Capacitación: 1 hora por área y videos cortos | Yo + jefes de área |
| **Lun 2-nov** | **Inicio de la marcha blanca en paralelo con SAP** | Todos |

---

## 10. Seguridad: acciones pendientes de la empresa

1. **Cambiar la contraseña de `manager` en SAP.** Se compartió por un canal no seguro y es el superusuario.
2. **Cambiar la contraseña de la cuenta de GEOSATELITAL** (`logistica1@…`). Se compartió por el mismo canal. El módulo no la guarda.
3. **Activar la verificación en dos pasos (MFA)** en AWS, Microsoft 365, Tailscale y DuckDNS. Si DuckDNS se creó con una cuenta personal, conviene pasarlo a una cuenta de la empresa.
4. **Guardar en un gestor de contraseñas de la empresa:** la llave SSH del servidor, el secreto de Entra ID y la clave del usuario de integración. No usar el chat ni el correo.
5. **Revisar los respaldos:** el diario del servidor y las instantáneas de Lightsail.
   - Probar una restauración una vez al mes. Hoy los respaldos quedan en el mismo servidor; las instantáneas de Lightsail son la copia fuera de él.
   - Opcional: copiar `/var/backups/operaciones` a un bucket S3 privado.

## 11. Qué queda verificado y qué no

**Verificado en este entorno:**
- pruebas automáticas;
- carga de las exportaciones reales de SAP en una base temporal;
- carga de usuarios por Excel con datos ficticios.

**No ejecutado todavía:**
- la creación del servidor;
- la conexión real al Service Layer, porque desde aquí no hay acceso a la red interna;
- el ingreso con el Microsoft 365 de la empresa.

El sistema **no está listo para producción** hasta completar los §2 a §8, ver `sap-probar` en verde y probar con los usuarios de cada área.

## Anexo: cambios de la ronda V9 (respuestas C01–C05)

| Pregunta | Qué se aplicó |
|---|---|
| C01 | Toda regularización exige la **guía de remisión** de lo que salió. Sin guía queda en borrador y no se descuenta stock. Comercial puede adjuntarla o **pedirla a Distribución**, que recibe una alerta y la adjunta. Parámetro `regularizacion_exige_guia`. |
| C02 | Registran la regularización: Asistente, Coordinador, Vendedor, Jefe Comercial y Gerente Comercial. La **cierran** (descuento): Coordinador, Jefe Comercial o Gerente (permiso `ov.regularizar_cerrar`). |
| C03 | En la OV, la alerta y el bloqueo en vivo aparecen solo **por debajo del precio base**; se retiró el aviso de «en el límite». |
| C04 | Ya implementado: penalidades según las condiciones de la ficha del cliente; indicador calculada vs pagada vs desestimada. |
| C05 | Plazo de **7 días** (`penalidad_dias_resolver`) para registrar si se pagó o se desestimó; vencido el plazo se alerta al Jefe Comercial. **Solo el Jefe Comercial desestima** (y la Gerencia General), con motivo obligatorio. |
| Usuarios | Carga por Excel en *Usuarios y permisos*, con dominio corporativo validado (`correo_dominio_corporativo`); sin guardar DNI; sin adivinar perfiles. |
