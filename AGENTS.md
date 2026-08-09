# AGENTS.md — xteink-ft8

Guide for future sessions. This project is a field FT8 setup: a Raspberry Pi
running WSJT-X + a relay bridge, and an **Xteink X4 Pro e-ink reader** running
custom firmware that shows FT8 CQ decodes and drives contacts.

Repo: https://github.com/parsimo2010/xteink-ft8 (owner GitHub account: parsimo2010)

## Current status (as of last session)

- **First prototype, NOT yet run on real hardware.** User will test in a few
  days. Do NOT publish a release or tag until hardware is validated.
- Bridge: implemented + passing (Python, stdlib only).
- Firmware: compiles cleanly, but untested on device.
- Docs are complete for operators (SETUP / FLASHING / PROTOCOL / RELEASE).

## Key architectural facts (do not "relearn" these)

- **The Xteink X4 Pro is NOT a smartwatch.** It is an ESP32-S3 *e-ink e-reader*:
  800x480 SSD1677 panel, GT911 touch, WiFi 2.4GHz + BLE, page-turn buttons.
- Firmware is built on the **FreeInk SDK** (the display/input stack CrossPoint
  uses), vendored as a git submodule at `firmware/freeink-sdk/`
  (https://github.com/Free-Ink/freeink-sdk). Reference clones live in
  `.reference/` (git-ignored): `crosspoint-reader` and `freeink-sdk`.
- **X4 Pro display pins** (hardware-confirmed in SDK profile): SCLK=12 MOSI=11
  CS=13 DC=18 RST=14 BUSY=6. Buttons: power=GPIO3, up=GPIO0, down=GPIO7.
  Touch GT911 on SDA39/SCL38, IRQ10, RST4. Power rail latch GPIO1 HIGH.
- **WSJT-X two-port trick:** bridge *receives* on 127.0.0.1:**2238** (set WSJT-X
  "UDP Server" to this) and *sends control messages* to 127.0.0.1:**2237**
  (WSJT-X "Accept UDP requests"). Same host, so the two roles must use
  different ports.
- **Device leg is TCP** (port 4510, length-framed JSON), not UDP. WSJT-X↔bridge
  is UDP. See `docs/PROTOCOL.md`.
- **FT8 contacts ARE auto-sequenced by WSJT-X** once the bridge sends a `Reply`
  packet (the device's tap). For hands-free completion WSJT-X "Auto Seq" must
  be on.
- **Callsign source of truth = WSJT-X** (bridge reads `de_call`/`de_grid` from
  Status). Firmware `send_cq()` uses the WSJT-X-sourced call, falling back to
  `cfg::MY_CALL`/`MY_GRID` only until the first Status/hello.

## Build & test commands

- Bridge tests: `cd bridge && python test_bridge.py` (expect 10/10 pass).
- Firmware build: `cd firmware && py -3.12 -m platformio run -e x4pro`
- Firmware flash: `py -3.12 -m platformio run -e x4pro -t upload`
- **PlatformIO is installed under Python 3.12 only** (`py -3.12 -m platformio`).
  The Arduino-ESP32 toolchain **rejects Python 3.14** (system default).
- PlatformIO/toolchain lives in `%USERPROFILE%\.platformio`. Build artifacts in
  `firmware/.pio/build/x4pro/` (bootloader.bin, partitions.bin, firmware.bin).
- Flash offsets (verified): bootloader `0x0`, partitions `0x8000`, boot_app0
  `0xe000`, app `0x10000`. Release workflow uses these.

## Environment notes

- Shell is **Windows PowerShell 5.1**; OS win32. No `rg`; use `grep`/`glob` tools.
- `git` config user = parsimo2010. Repo uses CRLF warnings (cosmetic, no LF attr).
- `gh` authenticated as parsimo2010.

## When hardware arrives — validation checklist (from docs/RELEASE.md)

1. Firmware boots on real X4 Pro; e-ink + touch confirmed.
2. X4 Pro joins Pi AP and connects to bridge.
3. CQ decodes appear; tapping completes a QSO with WSJT-X.
4. Headless Pi boot brings up AP + WSJT-X + bridge.
5. `flash.sh` works from a fresh download.

Likely things needing tuning on real hardware: EPD pins in `config.h` if panel
doesn't come up, UI metrics on the 800x480 panel, GT911 touch orientation, and
WSJT-X UDP schema across versions.

## Release process (only AFTER validation)

`git tag v0.1.0 && git push origin v0.1.0` → `.github/workflows/release.yml`
builds `firmware-<ver>.zip` + `bridge-<ver>.zip` and attaches them to a GitHub
Release. Keep `docs/RELEASE.md` checklist up to date.

## Style / conventions

- Firmware: C++17, no comments unless asked, single-loop immediate-mode UI,
  embedded 5x7 font (`include/font5x7.h`).
- Bridge: pure Python 3 stdlib (deliberately no third-party deps so the Pi zip
  needs no pip install).