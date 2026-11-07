#!/usr/bin/env bash
# Copia diaria de los respaldos (base y archivos) a un bucket S3, fuera del servidor: si la instancia se pierde, los
# respaldos siguen disponibles.
# IMPORTANTE (Lightsail): las instancias de Lightsail NO admiten rol IAM. Se usa un usuario IAM exclusivo con permiso solo
# sobre ese bucket (política en docs/43 §10) y sus claves se guardan SOLO en /root/.aws/credentials (permisos 600):
#   sudo snap install aws-cli --classic
#   sudo aws configure            # Access key, Secret key (del usuario IAM del respaldo), región del bucket, formato json
# Variable en /etc/operaciones/operaciones.env:
#   RESPALDO_S3=s3://nombre-del-bucket/operaciones
# Programar (root): echo '45 3 * * * root bash /opt/operaciones/deploy/respaldo_s3.sh' > /etc/cron.d/operaciones-s3
set -euo pipefail
set -a; . /etc/operaciones/operaciones.env; set +a
[ -n "${RESPALDO_S3:-}" ] || { echo "Defina RESPALDO_S3 en /etc/operaciones/operaciones.env"; exit 1; }
PATH="$PATH:/snap/bin" aws s3 sync /var/backups/operaciones "$RESPALDO_S3/$(hostname)/" --only-show-errors
echo "$(date '+%F %T') respaldo copiado a $RESPALDO_S3" >> /var/log/operaciones-respaldo-s3.log
