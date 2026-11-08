#!/bin/bash
# Túnel SAP de RESPALDO (sin administrador en la VM): prepara el servidor para recibir el túnel SSH inverso.
# Crea el usuario «tunelsap» SIN consola: su llave solo puede abrir 127.0.0.1:50000 en este servidor (nada más).
# Uso: sudo bash deploy/vpn/tunel_ssh_servidor.sh "ssh-ed25519 AAAA... tunel-sap"   (la llave PÚBLICA generada en la VM)
set -euo pipefail
LLAVE="${1:?Pegue entre comillas la llave PÚBLICA (tunel_sap.pub) generada en la VM}"
PUERTO="${2:-50000}"
[ "$(id -u)" = 0 ] || { echo "Ejecútelo con sudo"; exit 1; }
case "$LLAVE" in ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*) ;; *) echo "No parece una llave pública SSH"; exit 1;; esac
id tunelsap >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/tunelsap --shell /usr/sbin/nologin tunelsap
install -d -m 700 -o tunelsap -g tunelsap /var/lib/tunelsap/.ssh
echo "restrict,port-forwarding,permitlisten=\"127.0.0.1:${PUERTO}\",permitopen=\"none\" ${LLAVE}" > /var/lib/tunelsap/.ssh/authorized_keys
chown tunelsap:tunelsap /var/lib/tunelsap/.ssh/authorized_keys; chmod 600 /var/lib/tunelsap/.ssh/authorized_keys
cat > /etc/ssh/sshd_config.d/tunel.conf <<CONF
# Túnel SAP: si la VM se desconecta, el puerto se libera en menos de un minuto para que el reintento lo vuelva a abrir
ClientAliveInterval 15
ClientAliveCountMax 3
Match User tunelsap
    AllowTcpForwarding remote
    GatewayPorts no
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    PasswordAuthentication no
CONF
sshd -t && systemctl reload ssh
echo "Listo. Usuario tunelsap: solo puede publicar 127.0.0.1:${PUERTO} en este servidor."
echo "Pruebe cuando la VM esté conectada:  ss -ltn | grep 127.0.0.1:${PUERTO}"
