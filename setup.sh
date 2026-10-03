#!/usr/bin/env bash
set -euo pipefail

# Requires root
if [[ "$EUID" -ne 0 ]]; then
    echo "Run this script as root:"
    echo "  sudo $0"
    exit 1
fi

if [ ! -v AP_PASSWORD ];  then
    echo "Run this script with AP password you want:"
    echo "  sudo env AP_PASSORD=SuperPassword ./setup.sh"
    exit 1
fi

user=$(id -nu 1000)

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Configuration
AP_CONNECTION="HotSpot"
ETH_CONNECTION="local-eth"

AP_SSID="yaki"

ETH_IFACE="eth0"
WIFI_IFACE="wlan0"

ETH_IP="10.0.10.1"
WIFI_IP="10.42.0.1"

ETH_NET="10.0.10.0/24"
WIFI_NET="10.42.0.0/24"

if apt-get update; then
    echo "Installing required packages..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y network-manager dnsmasq
else
    echo "Warning: no network connection; skipping package installation."
fi

echo "Enabling NetworkManager..."
systemctl enable --now NetworkManager

echo "Stopping dnsmasq while configuring..."
systemctl stop dnsmasq 2>/dev/null || true

echo "Removing old NetworkManager profiles..."
nmcli connection delete "$AP_CONNECTION" 2>/dev/null || true
nmcli connection delete "$ETH_CONNECTION" 2>/dev/null || true

# Remove profiles that may already control these interfaces.
while read -r connection; do
    [[ -z "$connection" ]] && continue
    nmcli connection delete "$connection" 2>/dev/null || true
done < <(
    nmcli -t -f NAME,DEVICE connection show |
    awk -F: -v eth="$ETH_IFACE" -v wifi="$WIFI_IFACE" \
        '$2 == eth || $2 == wifi { print $1 }'
)

echo "Creating static Ethernet connection..."
nmcli connection add \
    type ethernet \
    ifname "$ETH_IFACE" \
    con-name "$ETH_CONNECTION" \
    ipv4.method manual \
    ipv4.addresses "$ETH_IP/24" \
    ipv6.method disabled \
    connection.autoconnect yes

echo "Creating Wi-Fi access point..."

nmcli radio wifi on

nmcli device wifi hotspot \
    ifname "$WIFI_IFACE" \
    con-name "$AP_CONNECTION" \
    ssid "$AP_SSID" \
    password  "$AP_PASSWORD" 

echo "Backing up dnsmasq configuration..."
if [[ -f /etc/dnsmasq.conf ]]; then
    cp -a /etc/dnsmasq.conf \
        "/etc/dnsmasq.conf.backup.$(date +%Y%m%d-%H%M%S)"
fi

cat > /etc/dnsmasq.conf <<EOF
# Listen only on the local Ethernet and Wi-Fi interfaces
interface=$ETH_IFACE
bind-interfaces

# Local interface addresses
listen-address=$ETH_IP

# DHCP server on eth0
dhcp-range=$ETH_IFACE,10.0.10.20,10.0.10.250,255.255.255.0,12h
dhcp-option=$ETH_IFACE,3,$ETH_IP
dhcp-option=$ETH_IFACE,6,$ETH_IP

# Catch-all DNS.
# Every queried hostname resolves to the Wi-Fi/AP address.
address=/#/$WIFI_IP

# Do not use upstream DNS servers.
no-resolv
no-poll

# Basic DNS behavior
domain-needed
bogus-priv

# Lease file
dhcp-leasefile=/var/lib/misc/dnsmasq.leases
EOF

echo "setting up iptables"
iptables-restore $SCRIPT_DIR/hotspot.iptables

echo "Testing dnsmasq configuration..."
dnsmasq --test

echo "Bringing interfaces up..."
nmcli connection up "$ETH_CONNECTION"
nmcli connection up "$AP_CONNECTION"

echo "Enabling dnsmasq..."
systemctl enable dnsmasq
systemctl restart dnsmasq



echo "setting up uv"

runuser -u $user -- bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

echo "setting up yaki service"


cat > /etc/systemd/system/yaki-detect.service <<EOF
[Unit]
Description=yaki detect service
After=NetworkManager.service network-online.target
Wants=network-online.target

[Service]
Type=forking
User=$user
Group=$user
ExecStart=/home/$user/.local/bin/uv run --directory $SCRIPT_DIR src/detect.py
StandardOutput=syslog
StandardError=syslog
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/yaki-main.service <<EOF
[Unit]
Description=yaki main service
After=NetworkManager.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$user
Group=$user
ExecStart=/home/$user/.local/bin/uv run --directory $SCRIPT_DIR src/main.py
StandardOutput=syslog
StandardError=syslog
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

systemctl stop yaki-main
systemctl stop yaki-detect
systemctl enable yaki-main
systemctl disable yaki-detect
systemctl stop yaki-main
systemctl start yaki-main
# systemctl start yaki-detect

echo
echo "Setup complete."
echo
echo "NETWORK"
echo
echo "Ethernet:"
echo "  Interface: $ETH_IFACE"
echo "  Address:   $ETH_IP/24"
echo "  DHCP pool: 10.0.10.20 - 10.0.10.250"
echo
echo "Wi-Fi:"
echo "  SSID:      $AP_SSID"
echo "  password:  $AP_PASSWORD"
echo "  Interface: $WIFI_IFACE"
echo "  Address:   $WIFI_IP/24"
echo "  DHCP pool: 10.0.42.100 - 10.0.42.200"
echo
echo "DNS catch-all address: $WIFI_IP"
echo "FIREWALL Redirect to port: 8080"
echo
echo "Check status with:"
echo "  nmcli connection show --active"
echo "  ip address show $ETH_IFACE"
echo "  ip address show $WIFI_IFACE"
echo "  systemctl status dnsmasq"
