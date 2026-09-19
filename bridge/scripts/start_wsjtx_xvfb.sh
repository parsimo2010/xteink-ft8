#!/usr/bin/env bash
# Start WSJT-X on a virtual framebuffer so the whole stack runs with no
# keyboard, mouse, or screen attached. WSJT-X is a Qt GUI app, so it needs an
# X display; Xvfb provides one headlessly. The X4 Pro is the real UI, so the
# WSJT-X window itself never needs to be seen in the field.
#
# Requires: xvfb, wsjtx. Optionally x11vnc to view it over VNC.
set -euo pipefail

export DISPLAY="${DISPLAY:-:1}"
XVFB_SCREEN="${XVFB_SCREEN:-1280x800x24}"

# Start Xvfb once; it is left running across WSJT-X restarts. Its output goes
# to stdout (the systemd journal) - do NOT log to /var/log, the service runs
# as a non-root user and could not create the file.
if ! pgrep -x Xvfb >/dev/null 2>&1; then
  echo "starting Xvfb on $DISPLAY"
  Xvfb "$DISPLAY" -screen 0 "$XVFB_SCREEN" &
  sleep 2
fi

echo "starting WSJT-X on $DISPLAY"
exec wsjtx