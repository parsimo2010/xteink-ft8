#!/usr/bin/env bash
# Best-effort preseed of WSJT-X settings so field boots need no manual config.
#
# WSJT-X stores everything in ONE INI group, [Configuration], in
# ~/.config/WSJT-X/WSJT-X.ini (verified against WSJT-X source,
# Configuration.cpp write_settings()). The keys this script sets:
#   MyCall, MyGrid, UDPServer, UDPServerPort, AcceptUDPRequests
# Booleans are written the way QSettings writes them ("true"/"false").
#
# IMPORTANT: WSJT-X rewrites its INI on exit, so it must NOT be running while
# this script edits the file. Run it as the desktop user (NOT sudo).
# A one-time visual check over VNC is still recommended (rig/audio device
# selection cannot be preseeded reliably).
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

# Locate the config file.
INI=""
for p in "$HOME/.config/WSJT-X/WSJT-X.ini" "$HOME/.config/wsjt-x/wsjt-x.ini"; do
  [ -f "$p" ] && INI="$p" && break
done
if [ -z "$INI" ]; then
  echo "WSJT-X config not found. Launch WSJT-X once (over VNC) so it creates"
  echo "its config, close it, then re-run this script."
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
echo "NOTE: verify in WSJT-X (Settings -> Reporting) that 'UDP Server' is"
echo "      ${UDPSERVER}:${UDPPORT} and 'Accept UDP requests' is checked."
echo "Backup saved to $INI.bak.*"
