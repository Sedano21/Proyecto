#!/usr/bin/env bash
# Respaldo diario de PostgreSQL y de los archivos subidos (fotos, guías, facturas, certificados).
# Buenas prácticas aplicadas:
#  - pg_dump en formato personalizado (-Fc), consistente sin detener el sistema; un usuario de respaldo de solo lectura.
#  - Cifrado del respaldo con una clave pública GPG (la clave privada NO se guarda en el servidor).
#  - Suma SHA-256 para verificar integridad; permisos 600; rotación (días configurables).
#  - Copia fuera del servidor (otro equipo o almacenamiento externo) y prueba de restauración periódica (restaurar_prueba.sh).
# Variables: PGHOST PGPORT PGUSER PGDATABASE (y ~/.pgpass con permisos 600), RESPALDO_DIR, UPLOAD_DIR,
#            GPG_DESTINATARIO (id de la clave pública), RETENCION_DIAS (por defecto 30), COPIA_REMOTA (opcional, ruta montada).
set -euo pipefail
umask 077
RESPALDO_DIR="${RESPALDO_DIR:-/var/backups/operaciones}"
RETENCION_DIAS="${RETENCION_DIAS:-30}"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESPALDO_DIR"
DUMP="$RESPALDO_DIR/operaciones_${TS}.dump"
pg_dump -Fc --no-owner --no-privileges -f "$DUMP"
ARCH="$RESPALDO_DIR/archivos_${TS}.tar.gz"
if [ -n "${UPLOAD_DIR:-}" ] && [ -d "$UPLOAD_DIR" ]; then tar -czf "$ARCH" -C "$UPLOAD_DIR" .; fi
for f in "$DUMP" "$ARCH"; do
  [ -f "$f" ] || continue
  if [ -n "${GPG_DESTINATARIO:-}" ]; then
    gpg --batch --yes --trust-model always -r "$GPG_DESTINATARIO" -o "$f.gpg" -e "$f" && shred -u "$f" 2>/dev/null || rm -f "$f"
    f="$f.gpg"
  else
    echo "ADVERTENCIA: respaldo sin cifrar (defina GPG_DESTINATARIO)" >&2
  fi
  sha256sum "$f" > "$f.sha256"
  if [ -n "${COPIA_REMOTA:-}" ]; then cp "$f" "$f.sha256" "$COPIA_REMOTA"/; fi
done
find "$RESPALDO_DIR" -type f -mtime +"$RETENCION_DIAS" -name 'operaciones_*' -delete
find "$RESPALDO_DIR" -type f -mtime +"$RETENCION_DIAS" -name 'archivos_*' -delete
echo "Respaldo terminado: $RESPALDO_DIR ($TS)"
