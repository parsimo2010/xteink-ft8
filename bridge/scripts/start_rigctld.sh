#!/usr/bin/env bash
# Start Hamlib rigctld for xteink-ft8, defaulting to a QRP Labs QMX/QMX+ on
# USB with zero configuration. Both WSJT-X (as "Hamlib NET rigctl") and the
# bridge connect to 127.0.0.1:4532, so the X4 Pro's << / >> band buttons work
# out of the box and WSJT-X sees the frequency change.
#
# Installed as xteink-rigctld.service by install.sh. All settings are
# optional and read from /etc/default/xteink-rigctld:
#   RIGCTLD_BIN  rigctld binary (default: /opt/hamlib/bin/rigctld if present,
#                else the system rigctld)
#   RIG_MODEL    "auto", a model number (e.g. 2057), or a model name fragment
#                (default: auto = QMX backend if this hamlib has it, else
#                QRPLabs QCX/QDX, else Kenwood TS-480 - the QMX CAT protocol
#                is a TS-480 subset, so both fallbacks control a QMX fine)
#   RIG_FILE     "auto" or a serial device (default: auto = first QRP Labs
#                USB serial port, else /dev/ttyACM0, else /dev/ttyUSB0;
#                waits for the device so the radio may be plugged in later)
#   RIG_PORT     TCP port (default 4532)
#   RIG_SPEED    serial speed (default 115200; the QMX USB CDC port ignores
#                it, but hamlib's QMX backend defaults to 256000 baud which
#                termios rejects, so we always pass a supported rate)
set -u

[ -r /etc/default/xteink-rigctld ] && . /etc/default/xteink-rigctld

RIG_PORT="${RIG_PORT:-4532}"
RIG_MODEL="${RIG_MODEL:-auto}"
RIG_FILE="${RIG_FILE:-auto}"
RIG_SPEED="${RIG_SPEED:-115200}"

# Prefer the fresh hamlib from build_hamlib.sh: Bookworm's system hamlib
# (4.5.4) predates the QMX backend (2057, added in 4.6.1).
if [ -z "${RIGCTLD_BIN:-}" ] && [ -x /opt/hamlib/bin/rigctld ]; then
  RIGCTLD_BIN=/opt/hamlib/bin/rigctld
  LD_LIBRARY_PATH="/opt/hamlib/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export LD_LIBRARY_PATH
fi
if [ -z "${RIGCTLD_BIN:-}" ]; then
  RIGCTLD_BIN="$(command -v rigctld || true)"
fi
if [ -z "$RIGCTLD_BIN" ]; then
  echo "rigctld not found; install libhamlib-utils or run build_hamlib.sh" >&2
  exit 1
fi

detect_device() {
  local p
  for p in /dev/serial/by-id/*QRP*if00 /dev/serial/by-id/*QRP* /dev/serial/by-id/*QMX*; do
    if [ -e "$p" ]; then readlink -f "$p"; return 0; fi
  done
  for p in /dev/ttyACM0 /dev/ttyUSB0; do
    if [ -e "$p" ]; then echo "$p"; return 0; fi
  done
  return 1
}

model_id() {
  "$RIGCTLD_BIN" --list 2>/dev/null | grep -im1 -- "$1" | awk '{print $1}'
}

case "$RIG_MODEL" in
  ''|auto)
    for cand in QMX QCX TS-480; do
      id="$(model_id "$cand" || true)"
      [ -n "$id" ] && RIG_MODEL="$id" && break
    done
    [ "$RIG_MODEL" = auto ] && RIG_MODEL=2057
    ;;
  *[!0-9]*)
    id="$(model_id "$RIG_MODEL" || true)"
    [ -n "$id" ] && RIG_MODEL="$id"
    ;;
esac

if [ "$RIG_FILE" = auto ]; then
  echo "waiting for the QRP Labs rig on USB (RIG_FILE=auto)..."
  while true; do
    RIG_FILE="$(detect_device)" && break
    sleep 5
  done
fi

echo "starting rigctld: bin=$RIGCTLD_BIN model=$RIG_MODEL file=$RIG_FILE speed=$RIG_SPEED port=$RIG_PORT"
exec "$RIGCTLD_BIN" \
  --model="$RIG_MODEL" \
  --rig-file="$RIG_FILE" \
  --serial-speed="$RIG_SPEED" \
  --listen-addr=127.0.0.1 \
  --port="$RIG_PORT"
