#!/usr/bin/env bash
# Verificación completa del servidor del Módulo de Operaciones (AWS Lightsail, Ubuntu 22.04/24.04).
# Revisa: equipo, sistema, red y DNS, HTTPS, servicios, variables (sin mostrar secretos), base de datos y migraciones,
# archivos, tareas programadas, respaldos, VPN/SAP y seguridad. Solo LEE: no cambia nada.
# Uso:   sudo bash /opt/operaciones/deploy/verificar_servidor.sh DOMINIO [--sap]
#        --sap  además prueba el inicio de sesión en el Service Layer (solo lectura)
set -uo pipefail
DOMINIO="${1:?Indique el dominio, p. ej. operaciones.corporacionproductiva.com}"
PROBAR_SAP="${2:-}"
DIR=/opt/operaciones
ENVF=/etc/operaciones/operaciones.env
OK=0; AV=0; FA=0
ok()    { printf '  \033[32mOK\033[0m     %s\n' "$*"; OK=$((OK+1)); }
aviso() { printf '  \033[33mAVISO\033[0m  %s\n' "$*"; AV=$((AV+1)); }
falla() { printf '  \033[31mFALLA\033[0m  %s\n' "$*"; FA=$((FA+1)); }
titulo(){ printf '\n\033[1m%s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Ejecute con sudo."; exit 2; }

titulo "1. Equipo (plan contratado: 4 vCPU, 16 GB RAM, 320 GB SSD)"
. /etc/os-release
case "$VERSION_ID" in 24.04|22.04) ok "Sistema: $PRETTY_NAME";; *) aviso "Sistema $PRETTY_NAME (probado en Ubuntu 22.04/24.04)";; esac
CPU=$(nproc); [ "$CPU" -ge 4 ] && ok "Procesadores: $CPU" || aviso "Procesadores: $CPU (se esperaban 4)"
RAM=$(awk '/MemTotal/{printf "%d", $2/1024/1024+0.5}' /proc/meminfo); [ "$RAM" -ge 15 ] && ok "Memoria: ${RAM} GB" || aviso "Memoria: ${RAM} GB (se esperaban 16)"
DISCO=$(df -BG --output=size / | tail -1 | tr -dc 0-9); USO=$(df --output=pcent / | tail -1 | tr -dc 0-9)
[ "$DISCO" -ge 300 ] && ok "Disco: ${DISCO} GB" || aviso "Disco: ${DISCO} GB (se esperaban 320)"
[ "$USO" -lt 80 ] && ok "Disco usado: ${USO} %" || falla "Disco usado: ${USO} % (liberar espacio o ampliar)"
SWAP=$(awk '/SwapTotal/{print int($2/1024)}' /proc/meminfo); [ "$SWAP" -gt 0 ] && ok "Swap: ${SWAP} MB" || aviso "Sin swap (recomendado 4 GB; ver guía §4.3)"

titulo "2. Sistema"
TZ_SIS=$(timedatectl show -p Timezone --value 2>/dev/null)
[ "$TZ_SIS" = "America/Lima" ] && ok "Zona horaria: America/Lima" || aviso "Zona horaria del sistema: $TZ_SIS (recomendado America/Lima, para que el respaldo de las 03:00 sea hora de Perú)"
[ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ] && ok "Hora sincronizada (NTP)" || falla "Hora NO sincronizada (NTP)"
systemctl is-enabled -q unattended-upgrades 2>/dev/null && ok "Actualizaciones de seguridad automáticas activas" || aviso "unattended-upgrades no activo"
[ -f /var/run/reboot-required ] && aviso "El sistema pide reinicio (aplique en horario sin operación)" || ok "No hay reinicio pendiente"

titulo "3. Red, IP fija y DNS"
IP_PUB=$(curl -fs --max-time 8 https://checkip.amazonaws.com | tr -d '[:space:]')
IP_DNS=$(getent ahostsv4 "$DOMINIO" | awk 'NR==1{print $1}')
[ -n "$IP_PUB" ] && ok "IP pública del servidor: $IP_PUB" || falla "No se pudo obtener la IP pública (¿salida a internet?)"
if [ -z "$IP_DNS" ]; then falla "El dominio $DOMINIO no resuelve (registro DNS A pendiente)"
elif [ "$IP_DNS" = "$IP_PUB" ]; then ok "El dominio $DOMINIO apunta a este servidor ($IP_DNS)"
else falla "El dominio apunta a $IP_DNS y este servidor es $IP_PUB (corregir el registro A o asignar la IP estática)"; fi
puerto() { ss -Hltnu | awk '{print $5}' | grep -E "[:.]$1\$" ; }
L8000=$(puerto 8000); [ -n "$L8000" ] && { echo "$L8000" | grep -qv '^127.0.0.1' && falla "gunicorn escucha fuera de 127.0.0.1 ($L8000)" || ok "Aplicación solo en 127.0.0.1:8000"; } || falla "Nada escucha en el puerto 8000 (servicio operaciones caído)"
L5432=$(puerto 5432); [ -n "$L5432" ] && { echo "$L5432" | grep -Eqv '^(127.0.0.1|\[::1\])' && falla "PostgreSQL escucha fuera de localhost ($L5432)" || ok "PostgreSQL solo local"; } || falla "PostgreSQL no escucha"
[ -n "$(puerto 443)" ] && ok "HTTPS 443 escuchando" || falla "Nada escucha en 443 (Caddy)"
[ -n "$(puerto 80)" ] && ok "HTTP 80 escuchando (redirige a HTTPS)" || aviso "Nada escucha en 80"

titulo "4. HTTPS y aplicación"
CODIGO=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://$DOMINIO/login")
[ "$CODIGO" = 200 ] && ok "https://$DOMINIO/login responde 200 con certificado válido" || falla "https://$DOMINIO/login respondió '$CODIGO' (revise Caddy: journalctl -u caddy)"
FIN=$(echo | openssl s_client -connect "$DOMINIO:443" -servername "$DOMINIO" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
[ -n "$FIN" ] && ok "Certificado vence: $FIN (Caddy lo renueva solo)" || falla "No se pudo leer el certificado"
CAB=$(curl -sI --max-time 15 "https://$DOMINIO/login")
echo "$CAB" | grep -qi strict-transport-security && ok "Cabecera HSTS presente" || aviso "Sin cabecera HSTS"
R80=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://$DOMINIO/login"); [[ "$R80" =~ ^30 ]] && ok "HTTP redirige a HTTPS ($R80)" || aviso "HTTP respondió $R80"
[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/login)" = 200 ] && ok "gunicorn responde en local" || falla "gunicorn no responde en 127.0.0.1:8000"

titulo "5. Servicios"
for s in operaciones caddy postgresql; do
  systemctl is-active -q "$s" && ok "Servicio $s activo" || falla "Servicio $s NO activo"
  systemctl is-enabled -q "$s" && ok "Servicio $s arranca solo al reiniciar" || falla "Servicio $s no habilitado al arranque"
done
if systemctl is-enabled -q operaciones-actualizar.timer 2>/dev/null; then ok "Actualización automática desde GitHub activa (cada 5 min)"
else aviso "Actualización automática desactivada (operaciones-actualizar.timer): las versiones se instalan a mano"; fi
REIN=$(systemctl show operaciones -p NRestarts --value); [ "${REIN:-0}" -le 3 ] && ok "Reinicios del servicio: ${REIN:-0}" || aviso "El servicio se reinició ${REIN} veces (revise journalctl -u operaciones)"

titulo "6. Variables del servidor ($ENVF) — no se muestran valores"
if [ ! -f "$ENVF" ]; then falla "No existe $ENVF"; else
  P=$(stat -c '%a %U' "$ENVF"); [ "$P" = "600 root" ] && ok "Permisos 600, dueño root" || falla "Permisos $P (deben ser 600 root: chmod 600, chown root)"
  # se leen en un subproceso; solo se informa si están y cómo son
  eval "$(set -a; . "$ENVF" >/dev/null 2>&1; for v in SECRET_KEY DATABASE_URL UPLOAD_DIR SESSION_COOKIE_SECURE DEMO_MODE SCHEMA_AUTO_CREATE SIMULACION_HABILITADA APP_TZ SAP_SL_URL SAP_SL_COMPANY SAP_SL_USER SAP_SL_PASSWORD SAP_SL_CA SAP_SL_VERIFY M365_TENANT_ID M365_CLIENT_ID M365_CLIENT_SECRET M365_REDIRECT_URI VAPID_SUB RESPALDO_S3; do printf 'E_%s=%q\n' "$v" "${!v:-}"; done)"
  [ ${#E_SECRET_KEY} -ge 32 ] && [ "$E_SECRET_KEY" != cambiar-por-un-valor-aleatorio-largo ] && ok "SECRET_KEY definida (${#E_SECRET_KEY} caracteres)" || falla "SECRET_KEY vacía, corta o de ejemplo (openssl rand -hex 32)"
  [[ "$E_DATABASE_URL" == postgresql* ]] && ok "DATABASE_URL apunta a PostgreSQL" || falla "DATABASE_URL no es PostgreSQL"
  [[ "$E_DATABASE_URL" == *CLAVE_BD* ]] && falla "DATABASE_URL todavía tiene CLAVE_BD de ejemplo"
  [ "$E_DEMO_MODE" = 0 ] && ok "DEMO_MODE=0 (producción)" || falla "DEMO_MODE no es 0: el sistema se presenta como demostración y permite la simulación"
  [ -z "$E_SIMULACION_HABILITADA" ] && ok "Simulación deshabilitada (SIMULACION_HABILITADA vacía)" || falla "SIMULACION_HABILITADA está definida: quítela en producción"
  [ "$E_SESSION_COOKIE_SECURE" = 1 ] && ok "Cookie de sesión solo por HTTPS" || falla "SESSION_COOKIE_SECURE debe ser 1"
  [ "$E_SCHEMA_AUTO_CREATE" = 0 ] && ok "Esquema gestionado por Alembic (SCHEMA_AUTO_CREATE=0)" || falla "SCHEMA_AUTO_CREATE debe ser 0"
  [ "${E_APP_TZ:-America/Lima}" = America/Lima ] && ok "Hora de la aplicación: America/Lima" || aviso "APP_TZ=$E_APP_TZ"
  [ -n "$E_UPLOAD_DIR" ] && [ -d "$E_UPLOAD_DIR" ] && [ "$(stat -c %U "$E_UPLOAD_DIR")" = operaciones ] && ok "Carpeta de archivos $E_UPLOAD_DIR (dueño operaciones)" || falla "UPLOAD_DIR no existe o no es del usuario operaciones"
  [ -n "$E_M365_TENANT_ID" ] && [ -n "$E_M365_CLIENT_ID" ] && [ -n "$E_M365_CLIENT_SECRET" ] && ok "Microsoft 365 configurado" || aviso "Microsoft 365 incompleto (solo funcionará el ingreso con usuario y contraseña)"
  [ "$E_M365_REDIRECT_URI" = "https://$DOMINIO/auth/microsoft/callback" ] && ok "M365_REDIRECT_URI coincide con el dominio" || aviso "M365_REDIRECT_URI ($E_M365_REDIRECT_URI) no es https://$DOMINIO/auth/microsoft/callback; debe coincidir también en Entra ID"
  if [ -n "$E_SAP_SL_URL" ]; then
    [ -n "$E_SAP_SL_COMPANY" ] && [ -n "$E_SAP_SL_USER" ] && [ -n "$E_SAP_SL_PASSWORD" ] && ok "SAP configurado (base $E_SAP_SL_COMPANY)" || falla "SAP incompleto (COMPANY/USER/PASSWORD)"
    [ "${E_SAP_SL_USER,,}" = manager ] && falla "SAP_SL_USER es manager: use el usuario de integración"
    if [ "$E_SAP_SL_VERIFY" = 0 ]; then aviso "SAP_SL_VERIFY=0: no se verifica el certificado de SAP (usar SAP_SL_CA)"
    elif [ -n "$E_SAP_SL_CA" ] && [ -f "$E_SAP_SL_CA" ]; then ok "Certificado de SAP: $E_SAP_SL_CA"
    else aviso "SAP_SL_CA no existe ($E_SAP_SL_CA)"; fi
  else aviso "SAP sin configurar (SAP_SL_URL vacío)"; fi
  [ -n "$E_VAPID_SUB" ] && ok "Contacto de notificaciones (VAPID_SUB) definido" || aviso "VAPID_SUB vacío (se usa un contacto genérico)"
fi

titulo "7. Base de datos y versión del código"
cd "$DIR" || exit 2
RAMA=$(runuser -u operaciones -- git rev-parse --abbrev-ref HEAD 2>/dev/null); COMMIT=$(runuser -u operaciones -- git rev-parse --short HEAD 2>/dev/null)
ok "Código: rama $RAMA, versión $COMMIT"
[ -z "$(runuser -u operaciones -- git status --porcelain --untracked-files=no 2>/dev/null)" ] && ok "Sin cambios locales en el código" || falla "Hay cambios locales en $DIR (impiden la actualización automática)"
app() { bash "$DIR/deploy/app.sh" "$*" 2>&1; }
ACT=$(app ".venv/bin/alembic current" | grep -Eo '^[0-9a-z_]+' | tail -1)
CAB=$(app ".venv/bin/alembic heads" | grep -Eo '^[0-9a-z_]+' | tail -1)
if [ -z "$ACT" ]; then falla "La base no tiene versión de Alembic (ver guía §7, anexo de docs/25)"
elif [ "$ACT" = "$CAB" ]; then ok "Migraciones al día (versión $ACT)"
else falla "Base en versión $ACT y el código en $CAB: ejecute alembic upgrade head"; fi
ESQ=$(app ".venv/bin/python -m app.cli esquema"); echo "$ESQ" | grep -q "coincide" && ok "El esquema de la base coincide con el código" || falla "Diferencias de esquema: python -m app.cli esquema"
N=$(runuser -u postgres -- psql -tAc "select count(*) from users where activo" operaciones 2>/dev/null)
[ -n "$N" ] && ok "Usuarios activos en la base: $N" || falla "No se pudo leer la base operaciones"
SIM=$(runuser -u postgres -- psql -tAc "select count(*) from sim_runs where estado <> 'LIMPIADA'" operaciones 2>/dev/null)
[ "${SIM:-0}" = 0 ] && ok "Sin datos de simulación cargados" || falla "Hay $SIM simulación(es) cargada(s): límpielas antes de operar"
TAM=$(runuser -u postgres -- psql -tAc "select pg_size_pretty(pg_database_size('operaciones'))" 2>/dev/null); ok "Tamaño de la base: $TAM"
SB=$(runuser -u postgres -- psql -tAc "show shared_buffers" 2>/dev/null)
[ "$SB" = "128MB" ] && aviso "PostgreSQL con valores por defecto (shared_buffers 128MB): aplique deploy/postgresql-operaciones.conf" || ok "PostgreSQL ajustado (shared_buffers $SB)"

titulo "8. Archivos de la aplicación"
for f in instance/vapid_privada.pem; do
  [ -f "$DIR/$f" ] && ok "$f presente (las suscripciones a notificaciones siguen válidas)" || aviso "$f no existe: se crea sola, pero si se migró de otro servidor cópiela de allá o los celulares deberán volver a «Activar»"
done
[ "$(stat -c %U "$DIR/instance" 2>/dev/null)" = operaciones ] && ok "instance/ pertenece a operaciones" || falla "instance/ no pertenece al usuario operaciones"

titulo "9. Respaldos"
[ -f /etc/cron.d/operaciones-respaldo ] && ok "Respaldo diario programado (/etc/cron.d/operaciones-respaldo)" || falla "Falta el respaldo diario"
ULT=$(ls -t /var/backups/operaciones/bd_*.sql.gz 2>/dev/null | head -1)
if [ -z "$ULT" ]; then aviso "Aún no hay respaldos de la base (el primero sale a las 03:00)"
else EDAD=$(( ( $(date +%s) - $(stat -c %Y "$ULT") ) / 3600 )); TAMR=$(stat -c %s "$ULT")
  [ "$EDAD" -le 26 ] && [ "$TAMR" -gt 1000 ] && ok "Último respaldo hace ${EDAD} h ($(basename "$ULT"))" || falla "Último respaldo con ${EDAD} h o vacío ($(basename "$ULT"))"; fi
if [ -f /etc/cron.d/operaciones-s3 ]; then
  command -v aws >/dev/null && ok "Copia externa a S3 programada" || falla "Copia a S3 programada pero falta aws (snap install aws-cli --classic)"
  tail -1 /var/log/operaciones-respaldo-s3.log 2>/dev/null | grep -q "$(date +%F)\|$(date -d yesterday +%F)" && ok "Copia a S3 reciente" || aviso "No hay registro de copia a S3 de hoy o ayer"
else aviso "Sin copia externa a S3 (recomendada: guía §10)"; fi
[ -f /etc/logrotate.d/operaciones ] && ok "Rotación de registros configurada" || aviso "Falta /etc/logrotate.d/operaciones"

titulo "10. VPN y SAP"
if command -v wg >/dev/null && ip link show wg0 >/dev/null 2>&1; then
  HS=$(wg show wg0 latest-handshakes | awk '{print $2}' | sort -n | tail -1)
  [ -n "$HS" ] && [ "$HS" -gt 0 ] && [ $(( $(date +%s) - HS )) -lt 300 ] && ok "VPN WireGuard conectada (último saludo hace $(( $(date +%s) - HS )) s)" || falla "VPN wg0 sin saludo reciente (¿equipo de la empresa apagado?)"
  systemctl is-enabled -q wg-quick@wg0 && ok "VPN arranca sola" || falla "wg-quick@wg0 no habilitado"
else aviso "Sin VPN WireGuard (si SAP se alcanza por otro medio, ignore este aviso)"; fi
if [ "$PROBAR_SAP" = --sap ]; then
  R=$(app ".venv/bin/python -m app.cli sap-probar"); echo "$R" | tail -3 | sed 's/^/         /'
  echo "$R" | grep -q "'version'" && ok "Inicio de sesión en SAP correcto" || falla "La prueba con SAP falló (vea el mensaje arriba)"
fi

titulo "11. Seguridad"
SSHD=$(sshd -T 2>/dev/null)
echo "$SSHD" | grep -qi '^passwordauthentication no' && ok "SSH sin contraseña (solo llave)" || falla "SSH acepta contraseña: PasswordAuthentication no"
echo "$SSHD" | grep -Eqi '^permitrootlogin (no|prohibit-password|without-password)' && ok "Root no entra con contraseña por SSH" || falla "Revise PermitRootLogin en SSH"
[ -f "$DIR/instance/operaciones.db" ] && aviso "Existe instance/operaciones.db (SQLite): en producción la base es PostgreSQL; no debe usarse" || ok "Sin base SQLite suelta"
ls /home/*/.ssh/authorized_keys >/dev/null 2>&1 && ok "Llaves SSH autorizadas: $(cat /home/*/.ssh/authorized_keys 2>/dev/null | grep -c ssh-) (retire las temporales al terminar)"

printf '\n\033[1mResultado: %d OK · %d avisos · %d fallas\033[0m\n' "$OK" "$AV" "$FA"
[ "$FA" -eq 0 ] && echo "Sin fallas: el servidor está listo para la verificación funcional (guía §12)." || echo "Corrija las FALLAS y vuelva a ejecutar."
exit $(( FA > 0 ))
