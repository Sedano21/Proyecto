#!/usr/bin/env bash
# Instalación en una VM Ubuntu 22.04/24.04 (AWS Lightsail, Oracle Cloud u otra). Uso: sudo bash instalar_ubuntu.sh DOMINIO
# No contiene credenciales: las variables se completan en /etc/operaciones/operaciones.env.
set -euo pipefail
DOMINIO="${1:?Indique el dominio, p. ej. operaciones-cp.duckdns.org}"
REPO="${REPO:-https://github.com/sedano21/proyecto.git}"
RAMA="${RAMA:-claude/automatizacion-corporativa-app-1cu2g5}"

apt-get update
apt-get install -y python3-venv python3-pip git postgresql debian-keyring debian-archive-keyring apt-transport-https curl
# Caddy (HTTPS automático)
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy

id operaciones >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/operaciones operaciones
mkdir -p /opt/operaciones /var/lib/operaciones/archivos /etc/operaciones /var/backups/operaciones
chown postgres:postgres /var/backups/operaciones
if [ ! -d /opt/operaciones/.git ]; then git clone --branch "$RAMA" "$REPO" /opt/operaciones; fi
python3 -m venv /opt/operaciones/.venv
/opt/operaciones/.venv/bin/pip install -r /opt/operaciones/requirements.txt gunicorn
chown -R operaciones:operaciones /opt/operaciones /var/lib/operaciones

# Base de datos PostgreSQL local (sin costo)
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='operaciones'" | grep -q 1; then
  CLAVE=$(openssl rand -hex 16)
  sudo -u postgres psql -c "CREATE USER operaciones WITH PASSWORD '$CLAVE';"
  sudo -u postgres psql -c "CREATE DATABASE operaciones OWNER operaciones;"
  echo "Clave de la base generada: guárdela en DATABASE_URL de /etc/operaciones/operaciones.env"
  echo "  postgresql+psycopg://operaciones:$CLAVE@127.0.0.1:5432/operaciones"
fi
[ -f /etc/operaciones/operaciones.env ] || install -m 600 /opt/operaciones/deploy/operaciones.env.example /etc/operaciones/operaciones.env
echo ">> Complete /etc/operaciones/operaciones.env (SECRET_KEY, DATABASE_URL, SAP, M365) y vuelva a ejecutar los pasos finales:"
echo "   sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/alembic upgrade head; .venv/bin/python -m app.cli init'"

install -m 644 /opt/operaciones/deploy/operaciones.service /etc/systemd/system/operaciones.service
sed "s/DOMINIO/$DOMINIO/" /opt/operaciones/deploy/Caddyfile > /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable operaciones caddy
systemctl restart caddy
# Respaldo diario de la base y de los archivos (03:00), 14 días
cat > /etc/cron.d/operaciones-respaldo <<CRON
0 3 * * * postgres pg_dump operaciones | gzip > /var/backups/operaciones/bd_\$(date +\%F).sql.gz
15 3 * * * root tar czf /var/backups/operaciones/archivos_\$(date +\%F).tgz -C /var/lib/operaciones archivos && find /var/backups/operaciones -mtime +14 -delete
CRON
echo "Listo. Inicie el servicio con: systemctl start operaciones"
