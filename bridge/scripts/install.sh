#!/usr/bin/env bash
# Install xteink-ft8 autostart on the Raspberry Pi:
#   * bridge systemd service
#   * WSJT-X headless autostart (Xvfb virtual display)
#   * rigctld (band control for the device's << / >> buttons; QRP Labs QMX/QMX+
#     auto-detected, no extra setup)
#   * latest wsjtx-improved + latest hamlib (if the network allows)
# Run once at home with sudo. After this, field boots start everything with no
# keyboard/mouse/screen.
#
# Env:     REPO (default: derived from this script's location),
#          USER_PI (default: the user who invoked sudo, else "pi"),
#          SKIP_HAMLIB_BUILD=1 (use the distro hamlib only),
#          SKIP_WSJTX_INSTALL=1 (keep whatever WSJT-X is installed)
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

chmod +x "$SCRIPTS"/*.sh

# WSJT-X_improved (latest Raspberry Pi build from SourceForge; falls back to
# the distro wsjtx-improved / wsjtx packages). A failure must not abort the
# install - the user can install WSJT-X manually instead.
if [ "${SKIP_WSJTX_INSTALL:-0}" != "1" ]; then
  bash "$SCRIPTS/install_wsjtx.sh" || {
    echo "WARNING: could not install WSJT-X automatically."
    echo "Install it from https://sourceforge.net/projects/wsjt-x-improved/files/"
    echo "(.deb), then: sudo systemctl restart xteink-wsjtx"
  }
fi

# Latest hamlib into /opt/hamlib (private prefix). Needed for the native QMX
# backend (model 2057) on Bookworm, whose distro hamlib predates it. Best
# effort: start_rigctld.sh falls back to the system rigctld with the
# QCX/QDX or TS-480 backend, which also drives a QMX.
if [ "${SKIP_HAMLIB_BUILD:-0}" != "1" ]; then
  bash "$SCRIPTS/build_hamlib.sh" || {
    echo "WARNING: could not build the latest hamlib into /opt/hamlib."
    echo "Band control will use the system rigctld (TS-480-compatible fallback)."
  }
fi

# Device access for the service user.
#   dialout - the QMX/QMX+ USB CDC serial port, used by rigctld.
#   audio   - /dev/snd/*, used by WSJT-X for QMX audio in and out.
# The audio group is not optional in a headless install: a systemd *system
# service* is not a logind session, so it never receives the udev ACLs that let a
# desktop user open the sound card. Without it the QMX shows up in `aplay -l` and
# still cannot be captured from, which looks exactly like "WSJT-X decoded nothing".
# xteink-wsjtx.service additionally sets AuxGroups= for the case where the operator
# runs the service under a different user than the one edited here.
for grp in dialout audio; do
  if getent group "$grp" >/dev/null 2>&1; then
    if id -nG "$USER_PI" | grep -qw "$grp"; then
      echo "  $USER_PI is already in '$grp'"
    else
      usermod -aG "$grp" "$USER_PI" || true
      echo "  added $USER_PI to '$grp' (takes effect on the next service restart)"
    fi
  else
    echo "  WARNING: group '$grp' does not exist on this system" >&2
  fi
done

# Install and enable the bridge service.
install -m 644 "$SCRIPTS/xteink-bridge.service" /etc/systemd/system/
# Point %h at the service user's real home and fix the User= line.
sed -i "s|%h|$USER_HOME|" /etc/systemd/system/xteink-bridge.service
sed -i "s|^User=.*|User=$USER_PI|" /etc/systemd/system/xteink-bridge.service

# Install and enable the headless WSJT-X service.
install -m 644 "$SCRIPTS/xteink-wsjtx.service" /etc/systemd/system/
sed -i "s|%h|$USER_HOME|" /etc/systemd/system/xteink-wsjtx.service
sed -i "s|^User=.*|User=$USER_PI|" /etc/systemd/system/xteink-wsjtx.service

# Install and enable rigctld (shared by WSJT-X and the bridge; this is what
# makes the device's band buttons work with the QMX/QMX+ by default).
install -m 644 "$SCRIPTS/xteink-rigctld.service" /etc/systemd/system/
sed -i "s|%h|$USER_HOME|" /etc/systemd/system/xteink-rigctld.service
sed -i "s|^User=.*|User=$USER_PI|" /etc/systemd/system/xteink-rigctld.service
if [ ! -f /etc/default/xteink-rigctld ]; then
  install -m 644 "$SCRIPTS/xteink-rigctld.default" /etc/default/xteink-rigctld
fi

systemctl daemon-reload
systemctl enable xteink-bridge.service xteink-wsjtx.service xteink-rigctld.service

mkdir -p "$USER_HOME/.cache"
chown "$USER_PI":"$USER_PI" "$USER_HOME/.cache"

echo "Installed. Services start on boot:"
echo "  * xteink-bridge.service  (the WSJT-X -> e-ink device relay)"
echo "  * xteink-wsjtx.service   (WSJT-X on a virtual display)"
echo "  * xteink-rigctld.service (band control; QMX/QMX+ auto-detected on USB)"
echo ""
echo "Next steps (do once at home):"
echo "  1. sudo $SCRIPTS/setup_ap.sh            # bring up the WiFi AP"
echo "  2. Configure WSJT-X manually (desktop or VNC) - one time:"
echo "     Radio:   Rig = 'Hamlib NET rigctl', Network Server = 127.0.0.1:4532,"
echo "              PTT Method = CAT  (xteink-rigctld OWNS the QMX serial port;"
echo "              do NOT point WSJT-X directly at /dev/ttyACM0 or Test CAT fails)"
echo "     Audio:   select the QMX USB sound card for input and output"
echo "     Reporting: UDP Server 127.0.0.1:2238, check 'Accept UDP requests'"
echo "     General: enable 'Auto Seq'"
echo "     Station: callsign + grid"
echo "     Optionally preseed call/grid/UDP keys with WSJT-X CLOSED:"
echo "       WSJTXCALL=W9XYZ WSJTXGRID=EM48 $SCRIPTS/preseed_wsjtx.sh  (as $USER_PI)"
echo "     To use direct serial CAT instead, disable the shared rigctld first:"
echo "       sudo systemctl disable --now xteink-rigctld   (band buttons stop working)"
echo "  3. Edit firmware/include/config.h (SSID/pass/bridge IP) and flash the device"
echo "     (pio run -e x4pro / -e sticky; see docs/FLASHING.md)."
echo ""
echo "Field boot: power on the Pi, wait ~1-2 min, power on the device. No"
echo "keyboard/mouse/screen needed."
