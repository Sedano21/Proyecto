#!/usr/bin/env bash
# Prueba de restauración (mensual recomendada): restaura el último respaldo en una base TEMPORAL y cuenta registros.
# Nunca restaura sobre la base productiva. Variables: RESPALDO_DIR, PGHOST, PGPORT, PGUSER (con permiso CREATEDB).
set -euo pipefail
RESPALDO_DIR="${RESPALDO_DIR:-/var/backups/operaciones}"
ULT="$(ls -1t "$RESPALDO_DIR"/operaciones_*.dump* 2>/dev/null | grep -v sha256 | head -1)"
[ -n "$ULT" ] || { echo "No hay respaldos"; exit 1; }
sha256sum -c "$ULT.sha256"
TMPDB="restauracion_prueba_$(date +%s)"
createdb "$TMPDB"
trap 'dropdb --if-exists "$TMPDB"' EXIT
if [[ "$ULT" == *.gpg ]]; then gpg --batch -d "$ULT" | pg_restore --no-owner -d "$TMPDB"; else pg_restore --no-owner -d "$TMPDB" "$ULT"; fi
psql -d "$TMPDB" -Atc "select 'ordenes_venta', count(*) from sales_orders union all select 'lotes', count(*) from stock_lots union all select 'auditoria', count(*) from audit_log"
echo "Restauración de prueba correcta: $ULT"
