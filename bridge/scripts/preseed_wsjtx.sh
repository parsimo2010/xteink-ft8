#!/usr/bin/env bash
# Best-effort preseed of WSJT-X settings so field boots need no manual config.
#
# WSJT-X writes its config to ~/.config/WSJT-X/WSJT-X.ini (older) or
# ~/.config/wsjt-x/wsjt-x.ini (newer). The INI key names have shifted across
# releases, so this sets the common spellings and reports what it touched.
# Run it once at home (optionally over VNC). A one-time visual check is still
# recommended: WSJT-X >= 2.6 moved some settings into new groups.
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

# Locate the config file.
for p in "$HOME/.config/wsjt-x/wsjt-x.ini" "$HOME/.config/WSJT-X/WSJT-X.ini"; do
  [ -f "$p" ] && INI="$p" && break
done
if [ -z "${INI:-}" ]; then
  echo "WSJT-X config not found. Launch WSJT-X once (over VNC) so it creates"
  echo "its config, then re-run this script."
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
set_key Network udpServerPort "$UDPPORT"
set_key Network udpServer "$UDPSERVER"
set_key Network acceptUDPRequests "1"
# Alternate spellings seen across versions:
set_key Network UDP_Server_Port "$UDPPORT"
set_key Network Accept_UDP_Requests "1"

echo "Preseeded callsign=$WSJTXCALL grid=$WSJTXGRID udp=${UDPSERVER}:${UDPPORT} ctrl=${CTRLPORT}"
echo "NOTE: verify in WSJT-X (Settings -> Reporting) that 'UDP Server' is"
echo "      ${UDPSERVER}:${UDPPORT} and 'Accept UDP requests' is checked."
echo "Backup saved to $INI.bak.*"