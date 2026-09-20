#!/usr/bin/env bash
# Configure the Raspberry Pi as a standalone WiFi access point (no internet
# needed). Supports both Raspberry Pi OS networking stacks:
#   * Bookworm and newer (NetworkManager)  -> nmcli "shared" hotspot
#   * Bullseye and older (dhcpcd)          -> hostapd + dnsmasq + dhcpcd
# Run once at home with sudo. The AP then comes up automatically on every boot,
# including headless field boots.
#
# Env:     AP_SSID (default XTEINK-FT8), AP_PASS (default ft8field),
#          AP_IP (default 192.168.4.1/24), AP_CHANNEL (default 6),
#          AP_IFACE (default wlan0)
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

IP="${AP_IP%/*}"

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "WARNING: interface '$IFACE' not found (set AP_IFACE=... if yours differs)." >&2
fi

# --- Detect the networking stack -------------------------------------------
USE_NM=0
if command -v nmcli >/dev/null 2>&1 && \
   nmcli -t -f RUNNING general 2>/dev/null | grep -qx 'running'; then
  USE_NM=1
fi

if [ "$USE_NM" = 1 ]; then
  # -------------------------------------------------------------------------
  # NetworkManager (Raspberry Pi OS Bookworm+): a "shared" wifi connection.
  # NM runs its own internal DHCP/NAT for the AP, so no hostapd/dnsmasq/dhcpcd
  # config is needed. autoconnect=yes brings the AP up on every boot.
  # -------------------------------------------------------------------------
  nmcli radio wifi on
  nmcli con delete xteink-ap >/dev/null 2>&1 || true
  nmcli con add type wifi ifname "$IFACE" con-name xteink-ap \
        autoconnect yes ssid "$AP_SSID"
  nmcli con mod xteink-ap \
        802-11-wireless.mode ap \
        802-11-wireless.band bg \
        802-11-wireless.channel "$AP_CHANNEL" \
        ipv4.method shared \
        ipv4.addresses "$AP_IP" \
        ipv6.method ignore \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.proto rsn \
        wifi-sec.pairwise ccmp \
        wifi-sec.group ccmp \
        wifi-sec.pmf disable \
        wifi-sec.psk "$AP_PASS"
  nmcli con up xteink-ap
  echo "NetworkManager hotspot '$AP_SSID' active on $IFACE ($AP_IP)."
  # Show what was actually configured: ESP32 STAs reject anything below
  # WPA2-PSK (esp reason 211, NO_AP_FOUND_IN_AUTHMODE_THRESHOLD), and some NM
  # versions advertise mixed WPA/WPA3 or PMF by default. NOTE: -f needs the
  # canonical field names; the wifi-sec.* aliases only work for con mod.
  nmcli -f 802-11-wireless.ssid,802-11-wireless-security.key-mgmt,802-11-wireless-security.proto,802-11-wireless-security.pmf,ipv4.method \
        con show xteink-ap
else
  # -------------------------------------------------------------------------
  # Legacy stack (Bullseye and older): hostapd + dnsmasq + a static IP via
  # dhcpcd. Appends to /etc/dhcpcd.conf instead of overwriting it.
  # -------------------------------------------------------------------------
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

  if ! grep -q "^interface $IFACE" /etc/dhcpcd.conf 2>/dev/null; then
    cat >>/etc/dhcpcd.conf <<EOF

interface $IFACE
static ip_address=$AP_IP
nohook wpa_supplicant
EOF
  fi

  cat >/etc/dnsmasq.conf <<EOF
interface=$IFACE
dhcp-range=${IP%.*}.10,${IP%.*}.50,255.255.255.0,24h
no-resolv
EOF

  systemctl enable hostapd dnsmasq
  systemctl restart dhcpcd hostapd dnsmasq
  echo "hostapd AP '$AP_SSID' configured on $IFACE ($AP_IP)."
fi

echo "AP '$AP_SSID' ready. Bridge listens on ${IP}:4510."
echo "Point the X4 Pro at SSID '$AP_SSID' / bridge host ${IP}."
