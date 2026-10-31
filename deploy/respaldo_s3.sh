#!/usr/bin/env bash
# Copia diaria de los respaldos (base y archivos) a un bucket S3, fuera del servidor (si la instancia se pierde, los
# respaldos siguen disponibles). Requiere: AWS CLI instalado, un bucket privado y un rol IAM de la instancia con permiso
# s3:PutObject/ListBucket sobre ese bucket. Variable en /etc/operaciones/operaciones.env:
#   RESPALDO_S3=s3://nombre-del-bucket/operaciones
# Programar (root): echo '45 3 * * * root bash /opt/operaciones/deploy/respaldo_s3.sh' > /etc/cron.d/operaciones-s3
set -euo pipefail
set -a; . /etc/operaciones/operaciones.env; set +a
[ -n "${RESPALDO_S3:-}" ] || { echo "Defina RESPALDO_S3 en /etc/operaciones/operaciones.env"; exit 1; }
aws s3 sync /var/backups/operaciones "$RESPALDO_S3/$(hostname)/" --only-show-errors
echo "$(date '+%F %T') respaldo copiado a $RESPALDO_S3" >> /var/log/operaciones-respaldo-s3.log
