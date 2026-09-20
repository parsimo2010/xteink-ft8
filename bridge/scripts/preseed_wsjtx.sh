#!/usr/bin/env bash
# Best-effort preseed of the WSJT-X callsign/grid/UDP keys so field boots need
# less manual config. OPTIONAL: everything this writes can also be set in the
# WSJT-X GUI. Rig, PTT and audio are deliberately NOT touched - configure
# those manually once in WSJT-X (see docs/SETUP.md step 4).
#
# Config file location (verified against WSJT-X user guide + source):
#   * WSJT-X 3.x / wsjtx-improved 3.x:  ~/.config/WSJT-X.ini
#   * WSJT-X 2.x:                       ~/.config/WSJT-X/WSJT-X.ini
# All keys live in the single [Configuration] group; booleans are written the
# way QSettings writes them ("true"/"false"). The keys this script sets:
#   MyCall, MyGrid, UDPServer, UDPServerPort, AcceptUDPRequests
#
# IMPORTANT: WSJT-X rewrites its INI on exit, so it must NOT be running while
# this script edits the file. Run it as the desktop user (NOT sudo).
#
# Required env / args:
#   WSJTXCALL  your callsign
#   WSJTXGRID  your grid square
#   UDPSERVER    default 127.0.0.1
#   UDPPORT      default 2238   (where WSJT-X SENDS; the bridge listens here)
#   CTRLPORT     default 2237   (WSJT-X "Accept UDP requests" listen port)
set -euo pipefail

WSJTXCALL="${WSJTXCALL:?set WSJTXCALL (your callsign)}"
WSJTXGRID="${WSJTXGRID:?set WSJTXGRID (your grid)}"
UDPSERVER="${UDPSERVER:-127.0.0.1}"
UDPPORT="${UDPPORT:-2238}"
CTRLPORT="${CTRLPORT:-2237}"

if [ "$(id -u)" -eq 0 ]; then
  echo "do NOT run with sudo - WSJT-X config lives in the desktop user's home." >&2
  exit 1
fi

if pgrep -x wsjtx >/dev/null 2>&1; then
  echo "WSJT-X is running. Close it first (it overwrites its INI on exit):" >&2
  echo "  sudo systemctl stop xteink-wsjtx   # or close the window" >&2
  exit 1
fi

# Locate the config file (3.x flat file first, then 2.x directory layout).
INI=""
for p in "$HOME/.config/WSJT-X.ini" "$HOME/.config/WSJT-X/WSJT-X.ini" "$HOME/.config/wsjt-x/wsjt-x.ini"; do
  [ -f "$p" ] && INI="$p" && break
done
if [ -z "$INI" ]; then
  echo "WSJT-X config not found. Launch WSJT-X once so it creates its config,"
  echo "close it, then re-run this script. Expected locations:"
  echo "  ~/.config/WSJT-X.ini           (WSJT-X 3.x / wsjtx-improved)"
  echo "  ~/.config/WSJT-X/WSJT-X.ini    (WSJT-X 2.x)"
  exit 1
fi
echo "Found WSJT-X config: $INI"
cp "$INI" "$INI.bak.$(date +%s)"

# set_key <group> <key> <value> : insert or replace a key under a group.
set_key() {
  local group="$1" key="$2" value="$3"
  if ! grep -q "^\[$group\]" "$INI"; then
    printf '\n[%s]\n' "$group" >>"$INI"
  fi
  # Replace within the group if present, else append after the group header.
  if grep -q "^$key=" "$INI"; then
    sed -i "s|^$key=.*|$key=$value|" "$INI"
  else
    sed -i "/^\[$group\]/a $key=$value" "$INI"
  fi
}

set_key Configuration MyCall "$WSJTXCALL"
set_key Configuration MyGrid "$WSJTXGRID"
set_key Configuration UDPServer "$UDPSERVER"
set_key Configuration UDPServerPort "$UDPPORT"
set_key Configuration AcceptUDPRequests "true"

echo "Preseeded callsign=$WSJTXCALL grid=$WSJTXGRID udp=${UDPSERVER}:${UDPPORT} ctrl=${CTRLPORT}"
echo "Still to set manually in WSJT-X (once):"
echo "  Radio:  Rig='Hamlib NET rigctl', Network Server=127.0.0.1:4532, PTT=CAT"
echo "          (xteink-rigctld owns the QMX serial port - don't use /dev/ttyACM0"
echo "          directly, or disable that service first)"
echo "  Audio:  select the QMX USB sound card (in and out)"
echo "  General: enable 'Auto Seq'"
echo "Backup saved to $INI.bak.*"
