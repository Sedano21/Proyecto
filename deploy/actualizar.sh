#!/usr/bin/env bash
# Actualización automática desde GitHub (la ejecuta el temporizador operaciones-actualizar.timer cada 5 minutos).
# Si hay commits nuevos en la rama: respaldo de la base → código nuevo → dependencias → migraciones → catálogos →
# reinicio → verificación. Si la aplicación no responde después del reinicio, vuelve al commit anterior.
# Uso manual: sudo bash /opt/operaciones/deploy/actualizar.sh [--forzar]
set -euo pipefail
DIR=/opt/operaciones
ENVF=/etc/operaciones/operaciones.env
RAMA="${RAMA:-claude/automatizacion-corporativa-app-1cu2g5}"
LOG=/var/log/operaciones-actualizar.log
exec >>"$LOG" 2>&1
como() { runuser -u operaciones -- "$@"; }
app() { runuser -u operaciones -- bash -c "set -a; . $ENVF; cd $DIR; $*"; }

cd "$DIR"
como git fetch -q origin "$RAMA"
ANTES=$(como git rev-parse HEAD)
NUEVO=$(como git rev-parse "origin/$RAMA")
if [ "$ANTES" = "$NUEVO" ] && [ "${1:-}" != "--forzar" ]; then exit 0; fi
echo "== $(date '+%F %T') actualizando ${ANTES:0:7} -> ${NUEVO:0:7}"
if ! como git merge --ff-only -q "origin/$RAMA"; then
  echo "!! Hay cambios locales en $DIR que impiden actualizar (revise 'git status'). No se cambió nada."; exit 1
fi
mkdir -p /var/backups/operaciones
runuser -u postgres -- pg_dump operaciones | gzip > "/var/backups/operaciones/bd_antes_${NUEVO:0:7}_$(date +%F_%H%M).sql.gz"
como "$DIR/.venv/bin/pip" install -q -r requirements.txt gunicorn
app ".venv/bin/alembic upgrade head"
app ".venv/bin/python -m app.cli init"
install -m 644 "$DIR/deploy/operaciones.service" /etc/systemd/system/operaciones.service
systemctl daemon-reload
systemctl restart operaciones
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null http://127.0.0.1:8000/login; then echo "OK $(date '+%F %T') en ${NUEVO:0:7}"; exit 0; fi
  sleep 3
done
echo "!! La aplicación no respondió tras actualizar: se vuelve a ${ANTES:0:7} (la base queda como está; respaldo en /var/backups/operaciones)"
como git reset -q --hard "$ANTES"
como "$DIR/.venv/bin/pip" install -q -r requirements.txt gunicorn
systemctl restart operaciones
exit 1
