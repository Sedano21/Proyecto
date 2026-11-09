#!/bin/bash
# Instala el guardián de la sesión remota (ver guardian_rdp.sh). Uso: sudo bash deploy/rdp/instalar_guardian_rdp.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Ejecútelo con sudo"; exit 1; }
apt-get update -qq
if apt-cache show freerdp3-x11 >/dev/null 2>&1; then apt-get install -y -qq freerdp3-x11 xvfb xauth; else apt-get install -y -qq freerdp2-x11 xvfb xauth; fi
id rdpguard >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/rdpguard --shell /usr/sbin/nologin rdpguard
touch /var/log/operaciones-rdp.log && chown rdpguard:rdpguard /var/log/operaciones-rdp.log
if [ ! -f /etc/operaciones/rdp.env ]; then
  cat > /etc/operaciones/rdp.env <<'CONF'
# Sesión remota a la VM del partner (la misma que usan para entrar por Escritorio remoto)
RDP_HOST=
RDP_PUERTO=3389
RDP_USUARIO=
RDP_DOMINIO=
RDP_CLAVE=
CONF
fi
chown root:root /etc/operaciones/rdp.env && chmod 600 /etc/operaciones/rdp.env
install -m 644 /opt/operaciones/deploy/rdp/operaciones-rdp.service /etc/systemd/system/operaciones-rdp.service
cat > /etc/logrotate.d/operaciones-rdp <<'CONF'
/var/log/operaciones-rdp.log {
  weekly
  rotate 8
  compress
  missingok
  notifempty
  copytruncate
}
CONF
systemctl daemon-reload
echo "Listo. Complete /etc/operaciones/rdp.env (sudo nano /etc/operaciones/rdp.env) y luego:"
echo "  sudo systemctl enable --now operaciones-rdp && sudo tail -f /var/log/operaciones-rdp.log"
