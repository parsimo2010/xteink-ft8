#!/usr/bin/env bash
# Build the LATEST Hamlib release into a private prefix (/opt/hamlib).
# The distro hamlib and WSJT-X packages are left untouched.
#
# Why: the QRP Labs QMX/QMX+ backend (rig model 2057) first shipped in Hamlib
# 4.6.1. Raspberry Pi OS Bookworm only ships 4.5.4, so without this the QMX
# has to fall back to the generic Kenwood TS-480 backend. start_rigctld.sh
# prefers /opt/hamlib/bin/rigctld whenever it exists.
#
# Run as root; install.sh calls this automatically (skip: SKIP_HAMLIB_BUILD=1).
# Needs internet. The build takes ~5-15 min on a Pi.
#
# Env: HAMLIB_VERSION  default: latest GitHub release (e.g. 4.7.2)
#      HAMLIB_PREFIX   default: /opt/hamlib
#      HAMLIB_JOBS     default: $(nproc)
set -euo pipefail

PREFIX="${HAMLIB_PREFIX:-/opt/hamlib}"
VERSION="${HAMLIB_VERSION:-}"
JOBS="${HAMLIB_JOBS:-$(nproc)}"
BUILD_DIR="${TMPDIR:-/tmp}/hamlib-build"

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: $0" >&2
  exit 1
fi

echo "==> hamlib: installing build dependencies"
apt-get install -y --no-install-recommends \
  build-essential autoconf automake libtool pkg-config \
  libusb-1.0-0-dev wget ca-certificates xz-utils

if [ -z "$VERSION" ]; then
  echo "==> hamlib: looking up latest release"
  VERSION="$(wget -qO- https://api.github.com/repos/Hamlib/Hamlib/releases/latest \
    | sed -n 's/.*"tag_name": *"v\{0,1\}\([^"]*\)".*/\1/p' | head -n1 || true)"
fi
if [ -z "$VERSION" ]; then
  echo "ERROR: cannot determine latest Hamlib version (no internet?)." >&2
  echo "       Re-run with: HAMLIB_VERSION=4.7.2 $0" >&2
  exit 1
fi
echo "==> hamlib: building $VERSION into $PREFIX (make -j$JOBS)"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

TARBALL="hamlib-${VERSION}.tar.gz"
if ! wget -q "https://github.com/Hamlib/Hamlib/releases/download/${VERSION}/${TARBALL}" \
   && ! wget -q "https://github.com/Hamlib/Hamlib/releases/download/v${VERSION}/${TARBALL}"; then
  # Last resort: git snapshot (needs autotools bootstrap).
  echo "==> hamlib: release tarball not found, using git snapshot"
  wget -qO "$TARBALL" "https://github.com/Hamlib/Hamlib/archive/refs/tags/${VERSION}.tar.gz" \
    || wget -qO "$TARBALL" "https://github.com/Hamlib/Hamlib/archive/refs/tags/v${VERSION}.tar.gz"
  tar xzf "$TARBALL"
  cd "Hamlib-${VERSION}"
  autoreconf -fi
else
  tar xzf "$TARBALL"
  cd "hamlib-${VERSION}"
fi

./configure --prefix="$PREFIX" >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null

if "$PREFIX/bin/rigctld" --list 2>/dev/null | grep -qi QMX; then
  echo "==> hamlib: OK, $PREFIX/bin/rigctld has the QRP Labs QMX backend"
else
  echo "WARNING: built rigctld does not list a QMX backend." >&2
fi
echo "==> hamlib: done ($("$PREFIX/bin/rigctld" --version 2>&1 | head -n1 || true))"
