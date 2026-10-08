#!/usr/bin/env bash
set -euo pipefail

# Requires root
if [[ "$EUID" -ne 0 ]]; then
    echo "Run this script as root:"
    echo "  sudo $0"
    exit 1
fi

if [ ! -v AP_PASSWORD ];  then
    echo "Give the password you want for the wifi AP:"
    echo "  sudo env AP_PASSORD=SuperPassword ./setup.sh"
    exit 1
fi

user=$(id -nu 1000)

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

usermod -aG video $user

cat > /etc/sudoers.d/yaki-reboot <<EOF
$user ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
EOF

# Configuration
AP_CONNECTION="YakiHotSpot"
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
    apt-get install -y network-manager dnsmasq imx500-all rpicam-apps
else
    echo "Warning: no network connection; skipping package installation."
fi


if [[ ! -f "/usr/share/imx500-models/imx500_network_yolo11n_pp.rpk" ]]; then
    echo "Downloading Yolo11n_pp imx500 rpk"
    curl -L -o /usr/share/imx500-models/imx500_network_yolo11n_pp.rpk https://github.com/raspberrypi/imx500-models/raw/refs/heads/main/imx500_network_yolo11n_pp.rpk
fi


if [[ ! -f "/home/$user/.local/bin/uv" ]]; then
    echo "Setting Up uv..."
    runuser -u $user -- bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi


if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "Setting Up venv..."
    runuser -u $user -- bash -c 'uv venv --system-site-packages -p 3.13'
fi

echo "Enabling NetworkManager..."
systemctl enable --now NetworkManager

echo "Stopping dnsmasq while configuring..."
systemctl stop dnsmasq 2>/dev/null || true

echo "Removing old NetworkManager profiles..."
nmcli connection delete "$AP_CONNECTION" 2>/dev/null || true
nmcli connection delete "$ETH_CONNECTION" 2>/dev/null || true

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

sudo nmcli connection add type wifi ifname $WIFI_IFACE con-name $AP_CONNECTION ssid $AP_SSID
sudo nmcli connection modify $AP_CONNECTION \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk $AP_PASSWORD \
  wifi-sec.proto rsn \
  wifi-sec.group ccmp \
  wifi-sec.pairwise ccmp \
  ipv4.method shared \
  ipv4.addresses "$WIFI_IP/24" \
  ipv6.method ignore \
  connection.autoconnect yes


echo "Backing up dnsmasq configuration..."
if [[ -f /etc/dnsmasq.conf ]]; then
    cp -a /etc/dnsmasq.conf \
        "/etc/dnsmasq.conf.backup.$(date +%Y%m%d-%H%M%S)"
fi

cat > /etc/dnsmasq.conf <<EOF
# Listen only on the local Ethernet and Wi-Fi interfaces
#interface=$ETH_IFACE $WIFI_IFACE lo
bind-interfaces

# Local interface addresses
# listen-address=$ETH_IP 
#listen-address=$WIFI_IP 
#listen-address=127.0.0.1

# DHCP server on eth0
dhcp-range=$ETH_IFACE,10.0.10.20,10.0.10.250,255.255.255.0,12h
dhcp-option=$ETH_IFACE,3,$ETH_IP
dhcp-option=$ETH_IFACE,6,$ETH_IP

# Catch-all DNS.
# Every queried hostname resolves to the Wi-Fi/AP address.
#address=/yaki.local/127.0.0.1
#address=/yaki.local/127.0.0.1

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

echo "Enabling dnsmasq..."
systemctl disable dnsmasq
systemctl stop dnsmasq

echo "setting up yaki service"

# ExecStart=nmcli radio wifi on
# ExecStart=nmcli device wifi hotspot ifname $WIFI_IFACE ssid $AP_SSID password $AP_PASSWORD

cat > /etc/systemd/system/yaki-hotspot.service <<EOF
[Unit]
Description=yaki hotspot
After=NetworkManager.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=nmcli radio wifi on
ExecStart=nmcli connection up "$AP_CONNECTION"
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/yaki-camera.service <<EOF
[Unit]
Description=yaki camera service
After=yaki-hotspot.service systemd-udev-settle.service
Wants=network-online.target

[Service]
Type=simple
User=$user
Group=$user
SupplementaryGroups=video
ExecStart=/home/$user/.local/bin/uv run --directory $SCRIPT_DIR yaki-camera
StandardOutput=syslog
StandardError=syslog
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/yaki-server.service <<EOF
[Unit]
Description=yaki server service
After=yaki-hotspot.service
Wants=network-online.target

[Service]
Type=simple
User=$user
Group=$user
ExecStart=/home/$user/.local/bin/uv run --directory $SCRIPT_DIR yaki-server
StandardOutput=syslog
StandardError=syslog
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

systemctl enable yaki-hotspot
systemctl enable yaki-server
systemctl enable yaki-camera
systemctl restart yaki-hotspot
systemctl restart yaki-server
systemctl restart yaki-camera

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
