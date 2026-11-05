#!/usr/bin/env bash
# V21: VPN punto a punto (WireGuard) entre el servidor del módulo (AWS) y la red de la empresa, para llegar al Service
# Layer de SAP sin el túnel SSH de la máquina virtual. Uso (en el servidor, como root):
#   sudo bash deploy/vpn/instalar_wireguard_servidor.sh <CLAVE_PUBLICA_DEL_EQUIPO_DE_LA_EMPRESA> [IP_SAP=172.18.103.1]
# Primero ejecútelo SIN argumentos: crea las claves del servidor y muestra su clave pública para configurar el otro lado.
set -euo pipefail
WG=/etc/wireguard
IP_SAP="${2:-172.18.103.1}"
apt-get install -y -q wireguard >/dev/null
umask 077
mkdir -p "$WG"
[ -f "$WG/servidor.key" ] || wg genkey | tee "$WG/servidor.key" | wg pubkey > "$WG/servidor.pub"
echo "Clave pública de ESTE servidor (va en el equipo de la empresa, en [Peer] PublicKey):"
cat "$WG/servidor.pub"
if [ -z "${1:-}" ]; then
  echo "Falta la clave pública del equipo de la empresa. Vuelva a ejecutar con ella como primer argumento."; exit 0
fi
cat > "$WG/wg0.conf" <<CONF
# Servidor del módulo de operaciones (AWS). Red del túnel 10.77.0.0/30.
[Interface]
Address = 10.77.0.1/30
ListenPort = 51820
PrivateKey = $(cat "$WG/servidor.key")

[Peer]
# Equipo de la empresa (pasarela Linux o el propio servidor SAP con WireGuard para Windows)
PublicKey = $1
# Solo la IP del túnel del otro lado y la IP del servidor SAP: nada más de la red de la empresa queda expuesto
AllowedIPs = 10.77.0.2/32, ${IP_SAP}/32
CONF
systemctl enable --now wg-quick@wg0
command -v ufw >/dev/null && ufw allow 51820/udp || true
echo "Listo. Abra también el puerto UDP 51820 en el grupo de seguridad de AWS (solo desde la IP pública de la empresa)."
echo "Pruebe con: ping -c3 10.77.0.2 && curl -k https://${IP_SAP}:50000/b1s/v1/ -o /dev/null -w '%{http_code}\n'"
