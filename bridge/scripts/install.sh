#!/usr/bin/env bash
# Install xteink-ft8 autostart on the Raspberry Pi:
#   * bridge systemd service
#   * WSJT-X headless autostart (Xvfb virtual display)
# Run once at home with sudo. After this, field boots start everything with no
# keyboard/mouse/screen.
#
# Env:     REPO (default: derived from this script's location),
#          USER_PI (default: the user who invoked sudo, else "pi")
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${REPO:-$(dirname "$(dirname "$SCRIPTS")")}"

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: $0" >&2
  exit 1
fi

# Under sudo, $HOME is /root - resolve the *service user's* home instead.
USER_PI="${USER_PI:-${SUDO_USER:-pi}}"
if [ "$USER_PI" = "root" ]; then USER_PI=pi; fi
USER_HOME="$(getent passwd "$USER_PI" | cut -d: -f6)"
if [ -z "$USER_HOME" ]; then
  echo "user '$USER_PI' not found; set USER_PI=<your user> and re-run." >&2
  exit 1
fi
echo "repo:    $REPO"
echo "service user: $USER_PI ($USER_HOME)"

if [ ! -f "$REPO/bridge/xteink_bridge.py" ]; then
  echo "$REPO does not look like an xteink-ft8 checkout; set REPO=... and re-run." >&2
  exit 1
fi

apt-get update -y
# Core dependencies (must succeed): virtual display + hamlib tools (rigctld).
apt-get install -y xvfb libhamlib-utils
# WSJT-X is in the Debian/Raspberry Pi OS repos, but a missing package must
# not abort the install (the user may install the official .deb instead).
apt-get install -y wsjtx || {
  echo "WARNING: apt could not install 'wsjtx'."
  echo "Install it from https://wsjt.sourceforge.io/wsjtx-downloads.html"
  echo "(.deb), then: sudo systemctl restart xteink-wsjtx"
}

chmod +x "$SCRIPTS"/*.sh

# Install and enable the bridge service.
install -m 644 "$SCRIPTS/xteink-bridge.service" /etc/systemd/system/
# Point %h at the service user's real home and fix the User= line.
sed -i "s|%h|$USER_HOME|" /etc/systemd/system/xteink-bridge.service
sed -i "s|^User=.*|User=$USER_PI|" /etc/systemd/system/xteink-bridge.service

# Install and enable the headless WSJT-X service.
install -m 644 "$SCRIPTS/xteink-wsjtx.service" /etc/systemd/system/
sed -i "s|%h|$USER_HOME|" /etc/systemd/system/xteink-wsjtx.service
sed -i "s|^User=.*|User=$USER_PI|" /etc/systemd/system/xteink-wsjtx.service

systemctl daemon-reload
systemctl enable xteink-bridge.service xteink-wsjtx.service

mkdir -p "$USER_HOME/.cache"
chown "$USER_PI":"$USER_PI" "$USER_HOME/.cache"

echo "Installed. Services start on boot:"
echo "  * xteink-bridge.service  (the WSJT-X -> X4 Pro relay)"
echo "  * xteink-wsjtx.service   (WSJT-X on a virtual display)"
echo ""
echo "Next steps (do once at home):"
echo "  1. sudo $SCRIPTS/setup_ap.sh            # bring up the WiFi AP"
echo "  2. WSJTXCALL=W9XYZ WSJTXGRID=EM48 $SCRIPTS/preseed_wsjtx.sh"
echo "     (run as $USER_PI, NOT sudo, with WSJT-X closed; or open WSJT-X over"
echo "      VNC once and set UDP Server 127.0.0.1:2238 + 'Accept UDP requests')"
echo "  3. Edit firmware/include/config.h (SSID/pass/bridge IP) and flash the X4 Pro."
echo ""
echo "Field boot: power on the Pi, wait ~1-2 min, power on the X4 Pro. No"
echo "keyboard/mouse/screen needed."
