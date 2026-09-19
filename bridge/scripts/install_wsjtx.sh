#!/usr/bin/env bash
# Install WSJT-X_improved (Uwe Risse DG2YCB's enhanced WSJT-X fork): always
# the LATEST Raspberry Pi .deb from SourceForge matching this OS and
# architecture. Falls back to the distro "wsjtx-improved" (Debian trixie+) or
# "wsjtx" package if the download or install fails.
#
# wsjtx-improved is a drop-in replacement: same /usr/bin/wsjtx binary, same
# ~/.config/WSJT-X/WSJT-X.ini, same UDP protocol (v3 only appends fields, e.g.
# "itone" in Status, which the bridge ignores), so the rest of the setup and
# preseed_wsjtx.sh work unchanged.
#
# Run as root; install.sh calls this automatically.
#
# Env: WSJTX_VARIANT   plain (default) | widescreen | AL   (GUI layouts)
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: $0" >&2
  exit 1
fi

apt-get install -y --no-install-recommends wget ca-certificates

ARCH="$(dpkg --print-architecture)"
CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-stable}")"
case "${WSJTX_VARIANT:-plain}" in
  plain)      VPAT="_improved_PLUS_" ;;
  widescreen) VPAT="_improved_widescreen_PLUS_" ;;
  AL)         VPAT="_improved_AL_PLUS_" ;;
  *) echo "unknown WSJTX_VARIANT '${WSJTX_VARIANT}' (plain|widescreen|AL)" >&2; exit 1 ;;
esac

ok=0
echo "==> wsjtx-improved: looking for the latest Rpi ${CODENAME} ${ARCH} build"
FILES_PAGE="$(wget -qO- "https://sourceforge.net/projects/wsjt-x-improved/files/" || true)"
FOLDER="$(printf '%s\n' "$FILES_PAGE" | grep -o 'WSJT-X_v[0-9.]*' | sort -uV | tail -n1 || true)"
if [ -n "$FOLDER" ]; then
  RSS="$(wget -qO- "https://sourceforge.net/projects/wsjt-x-improved/rss?path=/${FOLDER}/Raspberry%20Pi" || true)"
  URL="$(printf '%s\n' "$RSS" \
    | grep -o 'https://sourceforge.net/projects/wsjt-x-improved/files/[^<]*\.deb/download' \
    | grep -F "Rpi_${CODENAME}_${ARCH}.deb/download" \
    | grep -F "$VPAT" \
    | head -n1 || true)"
  if [ -n "$URL" ]; then
    DEB="/tmp/$(basename "${URL%/download}")"
    echo "==> wsjtx-improved: downloading $FOLDER ($(basename "$DEB"), ~60 MB)"
    if wget -qO "$DEB" "$URL" && apt-get install -y "$DEB"; then
      ok=1
    else
      echo "WARNING: download/install of $DEB failed" >&2
    fi
  else
    echo "WARNING: no ${VPAT} Rpi_${CODENAME}_${ARCH} .deb found in $FOLDER" >&2
  fi
fi

if [ "$ok" -ne 1 ]; then
  echo "WARNING: falling back to distro packages" >&2
  apt-get install -y wsjtx-improved || apt-get install -y wsjtx || {
    echo "ERROR: could not install WSJT-X." >&2
    echo "Install manually: https://sourceforge.net/projects/wsjt-x-improved/files/" >&2
    exit 1
  }
fi

echo "==> wsjtx installed: $(dpkg-query -W -f='${Package} ${Version}' wsjtx-improved wsjtx 2>/dev/null | head -n1 || true)"
