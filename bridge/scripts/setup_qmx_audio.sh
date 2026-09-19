#!/usr/bin/env bash
# Make the QRP Labs QMX/QMX+ USB sound card the Raspberry Pi's default audio
# device, so headless WSJT-X works with its audio set to "Default" (plug and
# play - no per-machine device-name guessing).
#
# Two layers:
#   1. Always: /etc/modprobe.d/xteink-qmx-audio.conf forces USB audio to ALSA
#      card index 0, ahead of the Pi's HDMI/headphone audio (snd_bcm2835).
#      The headless WSJT-X service has no PulseAudio/PipeWire session, so its
#      ALSA "default" device is card 0 = the QMX.
#   2. If the QMX is plugged in right now: also pin /etc/asound.conf to the
#      QMX card by its exact ALSA id (stronger than index ordering).
#
# Run as root; install.sh calls this automatically. Re-run any time with the
# QMX plugged in to regenerate /etc/asound.conf.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: $0" >&2
  exit 1
fi

echo "==> audio: forcing USB audio (QMX) to ALSA card index 0"
cat >/etc/modprobe.d/xteink-qmx-audio.conf <<'EOF'
# xteink-ft8: make USB audio (QRP Labs QMX/QMX+ sound card) the default card.
options snd_usb_audio index=0
options snd_bcm2835 index=1
EOF

# Find the QMX card id if it is attached (card long name usually contains QMX).
CARD_NUM=""
for lister in "aplay -l" "arecord -l" "cat /proc/asound/cards"; do
  CARD_NUM="$($lister 2>/dev/null | grep -im1 QMX | grep -oE 'card [0-9]+|^ *[0-9]+' | grep -oE '[0-9]+' | head -n1 || true)"
  [ -n "$CARD_NUM" ] && break
done

if [ -n "$CARD_NUM" ] && [ -r "/proc/asound/card${CARD_NUM}/id" ]; then
  CARD_ID="$(cat "/proc/asound/card${CARD_NUM}/id")"
  echo "==> audio: QMX detected as ALSA card ${CARD_NUM} (id '${CARD_ID}'); pinning /etc/asound.conf"
  cat >/etc/asound.conf <<EOF
# xteink-ft8: default audio = QRP Labs QMX/QMX+ USB sound card.
# Regenerate with the QMX plugged in: sudo bash bridge/scripts/setup_qmx_audio.sh
defaults.pcm.card ${CARD_ID}
defaults.ctl.card ${CARD_ID}
pcm.!default {
    type plug
    slave.pcm "hw:${CARD_ID}"
}
ctl.!default {
    type hw
    card ${CARD_ID}
}
EOF
else
  echo "==> audio: QMX not plugged in right now - skipping /etc/asound.conf."
  echo "    Card-index ordering above still makes it the default when attached."
  echo "    Optional: plug the QMX in and re-run this script to pin /etc/asound.conf."
fi

echo "==> audio: done. In WSJT-X (Settings -> Audio) leave input/output on 'Default',"
echo "    or select the QMX entry explicitly if you prefer."
