#!/usr/bin/env bash
# Configure the Raspberry Pi as a standalone WiFi access point (no internet
# needed). Writes hostapd + dnsmasq config and enables them. Run once at home
# with sudo. Field boots then bring up the AP automatically.
#
# Env:     AP_SSID (default XTEINK-FT8), AP_PASS (default ft8field),
#          AP_IP (default 192.168.4.1/24), AP_CHANNEL (default 6)
set -euo pipefail

AP_SSID="${AP_SSID:-XTEINK-FT8}"
AP_PASS="${AP_PASS:-ft8field}"
AP_IP="${AP_IP:-192.168.4.1/24}"
AP_CHANNEL="${AP_CHANNEL:-6}"
IFACE="${AP_IFACE:-wlan0}"

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: $0" >&2
  exit 1
fi

apt-get update -y
apt-get install -y hostapd dnsmasq

cat >/etc/hostapd/hostapd.conf <<EOF
interface=$IFACE
driver=nl80211
ssid=$AP_SSID
hw_mode=g
channel=$AP_CHANNEL
wmm_enabled=0
wpa=2
wpa_passphrase=$AP_PASS
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

sed -i "s|^#DAEMON_CONF=.*|DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"|" /etc/default/hostapd
systemctl unmask hostapd

# Static IP + dnsmasq on the chosen interface.
IP="${AP_IP%/*}"
cat >/etc/dhcpcd.conf <<EOF
interface $IFACE
static ip_address=$AP_IP
nohook wpa_supplicant
EOF

cat >/etc/dnsmasq.conf <<EOF
interface=$IFACE
dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,24h
no-resolv
server=8.8.8.8
EOF

systemctl enable hostapd dnsmasq
systemctl restart dhcpcd hostapd dnsmasq

echo "AP '$AP_SSID' configured on $IFACE ($AP_IP). Bridge listens on ${IP}:4510."
echo "Point the X4 Pro at SSID '$AP_SSID' / bridge host ${IP}."