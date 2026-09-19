#!/usr/bin/env bash
# Best-effort preseed of WSJT-X settings so field boots need no manual config.
#
# WSJT-X stores everything in ONE INI group, [Configuration], in
# ~/.config/WSJT-X/WSJT-X.ini (verified against WSJT-X source,
# Configuration.cpp write_settings()). The keys this script sets:
#   MyCall, MyGrid, UDPServer, UDPServerPort, AcceptUDPRequests,
#   Rig, CATNetworkPort, PTTMethod, PTTport, DataMode
# Booleans are written the way QSettings writes them ("true"/"false").
#
# The rig keys point WSJT-X at the local rigctld ("Hamlib NET rigctl" on
# 127.0.0.1:4532) that xteink-rigctld.service runs for the QRP Labs
# QMX/QMX+. Because WSJT-X and the bridge then share ONE rigctld, the X4
# Pro's band buttons retune the WSJT-X session too. PTT stays CAT and the
# TX mode is forced to USB (what FT8 needs on the QMX).
#
# IMPORTANT: WSJT-X rewrites its INI on exit, so it must NOT be running while
# this script edits the file. Run it as the desktop user (NOT sudo).
# A one-time visual check over VNC is still recommended for the AUDIO device
# selection (sound card names are machine-specific and cannot be preseeded
# reliably).
#
# Required env / args:
#   WSJTXCALL  your callsign
#   WSJTXGRID  your grid square
#   UDPSERVER    default 127.0.0.1
#   UDPPORT      default 2238   (where WSJT-X SENDS; the bridge listens here)
#   CTRLPORT     default 2237   (WSJT-X "Accept UDP requests" listen port)
#   WSJTX_RIG    default "Hamlib NET rigctl" (exact rig-dropdown name)
#   RIGCTLD_ADDR default 127.0.0.1:4532 (must match start_rigctld.sh)
#   WSJTX_NO_RIG=1  skip the rig keys entirely
#
# Audio is deliberately NOT written by default: install.sh makes the QMX USB
# sound card the system default (setup_qmx_audio.sh), and WSJT-X falls back to
# the default device when SoundInName/SoundOutName are absent. To pin exact
# device strings instead (from the WSJT-X Settings -> Audio dropdowns), set:
#   WSJTX_SNDIN / WSJTX_SNDOUT
set -euo pipefail

WSJTXCALL="${WSJTXCALL:?set WSJTXCALL (your callsign)}"
WSJTXGRID="${WSJTXGRID:?set WSJTXGRID (your grid)}"
UDPSERVER="${UDPSERVER:-127.0.0.1}"
UDPPORT="${UDPPORT:-2238}"
CTRLPORT="${CTRLPORT:-2237}"
WSJTX_RIG="${WSJTX_RIG:-Hamlib NET rigctl}"
RIGCTLD_ADDR="${RIGCTLD_ADDR:-127.0.0.1:4532}"

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

if [ "${WSJTX_NO_RIG:-0}" != "1" ]; then
  # Route WSJT-X through the shared rigctld (see xteink-rigctld.service).
  # PTTMethod: 0=VOX 1=CAT 2=DTR 3=RTS;  DataMode: 0=None 1=USB 2=Data/Pkt.
  set_key Configuration Rig "$WSJTX_RIG"
  set_key Configuration CATNetworkPort "$RIGCTLD_ADDR"
  set_key Configuration PTTMethod 1
  set_key Configuration PTTport CAT
  set_key Configuration DataMode 1
  echo "Preseeded rig: '$WSJTX_RIG' -> $RIGCTLD_ADDR (PTT=CAT, mode forced USB)"
fi

if [ -n "${WSJTX_SNDIN:-}" ]; then set_key Configuration SoundInName "$WSJTX_SNDIN"; fi
if [ -n "${WSJTX_SNDOUT:-}" ]; then set_key Configuration SoundOutName "$WSJTX_SNDOUT"; fi
if [ -n "${WSJTX_SNDIN:-}${WSJTX_SNDOUT:-}" ]; then
  echo "Preseeded audio: in='${WSJTX_SNDIN:-default}' out='${WSJTX_SNDOUT:-default}'"
else
  echo "Audio left on 'Default' (setup_qmx_audio.sh made the QMX the default card)."
fi

echo "Preseeded callsign=$WSJTXCALL grid=$WSJTXGRID udp=${UDPSERVER}:${UDPPORT} ctrl=${CTRLPORT}"
echo "NOTE: verify in WSJT-X (Settings -> Radio/Reporting) that Rig is"
echo "      '$WSJTX_RIG' (${RIGCTLD_ADDR}), 'UDP Server' is ${UDPSERVER}:${UDPPORT},"
echo "      'Accept UDP requests' is checked, and pick the QMX USB audio devices"
echo "      on Settings -> Audio (device names cannot be preseeded)."
echo "Backup saved to $INI.bak.*"
