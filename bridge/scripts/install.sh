#!/usr/bin/env bash
# Install xteink-ft8 autostart on the Raspberry Pi:
#   * bridge systemd service
#   * WSJT-X headless autostart (Xvfb virtual display)
# Run once at home with sudo. After this, field boots start everything with no
# keyboard/mouse/screen.
#
# Env:     REPO (default $HOME/xteink-ft8), USER_PI (default pi)
set -euo pipefail

REPO="${REPO:-$HOME/xteink-ft8}"
USER_PI="${USER_PI:-pi}"
SCRIPTS="$REPO/bridge/scripts"

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: $0" >&2
  exit 1
fi

# Dependencies for headless operation.
apt-get update -y
apt-get install -y xvfb wsjtx || {
  echo "WSJT-X may not be in this distro's repos; install it manually and re-run."
  echo "Headless display still needs: xvfb"
}

chmod +x "$SCRIPTS"/*.sh

# Install and enable the bridge service.
install -m 644 "$SCRIPTS/xteink-bridge.service" /etc/systemd/system/
# Fix the ExecStart %h -> actual home for the service user.
sed -i "s|%h|$HOME|" /etc/systemd/system/xteink-bridge.service
sed -i "s|^User=.*|User=$USER_PI|" /etc/systemd/system/xteink-bridge.service

# Install and enable the headless WSJT-X service.
install -m 644 "$SCRIPTS/xteink-wsjtx.service" /etc/systemd/system/
sed -i "s|%h|$HOME|" /etc/systemd/system/xteink-wsjtx.service
sed -i "s|^User=.*|User=$USER_PI|" /etc/systemd/system/xteink-wsjtx.service

systemctl daemon-reload
systemctl enable xteink-bridge.service xteink-wsjtx.service

if [ ! -d "$HOME/.cache" ]; then
  mkdir -p "$HOME/.cache"
  chown "$USER_PI":"$USER_PI" "$HOME/.cache"
fi

echo "Installed. Services start on boot:"
echo "  * xteink-bridge.service  (the WSJT-X -> X4 Pro relay)"
echo "  * xteink-wsjtx.service   (WSJT-X on a virtual display)"
echo ""
echo "Next steps (do once at home):"
echo "  1. sudo $SCRIPTS/setup_ap.sh            # bring up the WiFi AP"
echo "  2. WSJTXCALL=W9XYZ WSJTXGRID=EM48 $SCRIPTS/preseed_wsjtx.sh"
echo "     (or open WSJT-X over VNC once and set UDP Server 127.0.0.1:2238 +"
echo "      'Accept UDP requests' manually)"
echo "  3. Edit firmware/include/config.h (SSID/pass/bridge IP) and flash the X4 Pro."
echo ""
echo "Field boot: power on the Pi, wait ~1-2 min, power on the X4 Pro. No"
echo "keyboard/mouse/screen needed."