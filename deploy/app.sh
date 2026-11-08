#!/bin/bash
# Ejecuta un comando de la aplicación como el usuario «operaciones» con las variables del servidor.
# El archivo de variables es 600 root: lo lee root y el comando corre como «operaciones» con esas variables.
# Uso:  sudo bash /opt/operaciones/deploy/app.sh .venv/bin/alembic upgrade head
#       sudo bash /opt/operaciones/deploy/app.sh .venv/bin/python -m app.cli esquema
ENVF=/etc/operaciones/operaciones.env
DIR=/opt/operaciones
[ "$(id -u)" = 0 ] || { echo "Ejecútelo con sudo"; exit 1; }
[ -r "$ENVF" ] || { echo "No existe $ENVF"; exit 1; }
set -a; . "$ENVF"; set +a
[ -n "$DATABASE_URL" ] || { echo "DATABASE_URL vacía en $ENVF"; exit 1; }
cd "$DIR" || exit 1
exec setpriv --reuid=operaciones --regid=operaciones --init-groups env HOME="$DIR" USER=operaciones LOGNAME=operaciones bash -c "$*"
