#!/bin/bash
# Guardián del túnel SAP desde el servidor (09-nov-2026).
# Mantiene abierta, desde este servidor, una sesión de Escritorio remoto (RDP) con la VM del partner, como si alguien
# la tuviera abierta. Al iniciar sesión en la VM, la carpeta Inicio (shell:startup) arranca tunel_sap.bat y el túnel
# vuelve. Si la sesión se cierra (límite de 3 h, reinicio de la VM), el guardián vuelve a entrar solo.
#
# Reglas para no estorbar a las personas que usan ese mismo usuario:
#   - Solo abre la sesión cuando el túnel está CAÍDO (127.0.0.1:50000 no escucha).
#   - Si alguien entra con el mismo usuario y toma la sesión, el guardián se desconecta y NO vuelve mientras el túnel
#     siga arriba (sigue corriendo en la sesión de esa persona).
#   - Si la contraseña falla 3 veces seguidas, espera 30 min (para no bloquear la cuenta) y lo deja en el registro.
# Variables en /etc/operaciones/rdp.env (600 root): RDP_HOST, RDP_PUERTO, RDP_USUARIO, RDP_DOMINIO, RDP_CLAVE
set -u
PUERTO_TUNEL="${PUERTO_TUNEL:-50000}"
: "${RDP_HOST:?Falta RDP_HOST en /etc/operaciones/rdp.env}" "${RDP_USUARIO:?Falta RDP_USUARIO}" "${RDP_CLAVE:?Falta RDP_CLAVE}"
RDP_PUERTO="${RDP_PUERTO:-3389}"
log() { echo "$(date '+%F %T') $*"; }
tunel_arriba() { ss -ltn 2>/dev/null | grep -q "127.0.0.1:${PUERTO_TUNEL} "; }

BIN=$(command -v xfreerdp3 || command -v xfreerdp || true)
[ -n "$BIN" ] || { log "No está instalado FreeRDP (ejecute deploy/rdp/instalar_guardian_rdp.sh)"; exit 1; }
if "$BIN" --version 2>/dev/null | grep -q "version 3"; then CERT="/cert:tofu"; else CERT="/cert-tofu"; fi
DOM=(); [ -n "${RDP_DOMINIO:-}" ] && DOM=("/d:${RDP_DOMINIO}")

fallos=0
while true; do
  if tunel_arriba; then sleep 60; continue; fi
  log "Túnel SAP caído: abriendo sesión remota en ${RDP_HOST}:${RDP_PUERTO} como ${RDP_USUARIO}"
  inicio=$(date +%s)
  # La clave va por la entrada estándar (no queda visible en la lista de procesos)
  printf '%s\n' "$RDP_CLAVE" | xvfb-run -a -s "-screen 0 1280x800x24" "$BIN" "/v:${RDP_HOST}:${RDP_PUERTO}" \
      "/u:${RDP_USUARIO}" "${DOM[@]}" /from-stdin:force "$CERT" /size:1280x800 /bpp:16 -wallpaper -themes \
      +auto-reconnect /auto-reconnect-max-retries:20 /log-level:ERROR &
  pid=$!
  # Esperar a que el túnel suba (hasta 5 min); mientras la sesión siga abierta, vigilarla
  subio=0
  while kill -0 "$pid" 2>/dev/null; do
    if tunel_arriba; then subio=1; fallos=0; fi
    # sesión abierta 5 min sin túnel: algo no arrancó (¿tunel_sap.bat fuera de shell:startup?) → reintentar
    if [ "$subio" = 0 ] && [ $(( $(date +%s) - inicio )) -gt 300 ]; then
      log "La sesión abrió pero el túnel no subió en 5 min: revise que tunel_sap.bat esté en shell:startup del usuario"
      kill "$pid" 2>/dev/null; break
    fi
    sleep 15
  done
  wait "$pid" 2>/dev/null
  dur=$(( $(date +%s) - inicio ))
  if tunel_arriba; then
    log "Sesión remota terminada (${dur} s); el túnel sigue arriba (otra persona tomó la sesión o se desconectó): en espera"
    continue
  fi
  if [ "$dur" -lt 40 ]; then
    fallos=$((fallos + 1))
    log "La sesión remota no se pudo abrir (${dur} s; intento ${fallos}). ¿Clave, usuario o acceso al puerto ${RDP_PUERTO}?"
    if [ "$fallos" -ge 3 ]; then log "3 fallos seguidos: espera de 30 min para no bloquear la cuenta"; sleep 1800; fallos=0; fi
  fi
  sleep 30
done
