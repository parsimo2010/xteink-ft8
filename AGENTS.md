# AGENTS.md — xteink-ft8

Guide for future sessions. This project is a field FT8 setup: a Raspberry Pi
running WSJT-X + a relay bridge, and an **Xteink X4 Pro e-ink reader** running
custom firmware that shows FT8 CQ decodes and drives contacts.

Repo: https://github.com/parsimo2010/xteink-ft8 (owner GitHub account: parsimo2010)

## Current status (as of last session)

- **2026-09-12: first hardware bring-up SUCCEEDED on a real X4 Pro.** Flashed
  via native-USB download mode with esptool v5; every block hash-verified.
  Validated on device: boot, PORTRAIT e-ink rendering (SSD1677), GT911 touch
  with correct rotation mapping, tap-flash feedback, page-button scrolling,
  and hold-power 1.5 s -> SLEEPING splash -> deep sleep with power-button wake.
- **STILL UNVALIDATED on hardware:** Pi AP join + bridge link (device has only
  ever shown NO-LINK), a completed real FT8 QSO, headless Pi boot,
  `flash.sh` from a release zip. Do NOT tag a release until the checklist in
  docs/RELEASE.md is green.
- Bridge: implemented + passing (14/14; Python, stdlib only).
- Firmware: compiles clean; built current `firmware.bin` ~997 KB.
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
- **UI is PORTRAIT (480x800 logical)** via a per-pixel software transpose in
  `ui.cpp` (the panel RAM is landscape-only; 90° is NOT expressible in the
  SSD1677/UC8179/UC8279 controller). Rotating/touch-mapping is a one-constant
  change: `cfg::UI_ROTATION` in `config.h` (1 = portrait CW, 2 = 180° flip).
  Font = 5x7 upscaled to 8x11 per glyph. Taps flash the control inverted for
  `TAP_FLASH_MS` as feedback (works with no link, so touch can be verified
  before the Pi exists). NOTE: the SDK's `begin()` re-derives EPD pins from the
  BoardConfig profile — `cfg::EPD_*` in config.h are decorative, not authoritative.
- **Sleep = deep sleep, wake = cold boot.** Hold power (GPIO3)
  `POWER_HOLD_SLEEP_MS` -> render SLEEPING splash FULL -> `display.deepSleep()`
  -> `PowerManager::powerDownRailsForSleep()` -> `deepSleepUntilPowerButton()`
  (S3 = RTC ext1 on GPIO3). All state (WiFi, decodes, framebuffer) is LOST on
  wake; `setup()` rebuilds. GPIO1 power latch is never driven LOW (no hard-off;
  SDK does not power off an S3 target). Async sleep task in InputManager unused.
- **TCP link is crash-safe:** any framing error drops + reconnects the socket so
  a corrupt/oversized frame cannot permanently desync the stream; a tap on the
  status bar does nothing. Bridge caps `hello`/`get_decodes` snapshots to <16 KB
  (the MAX_FRAME both ends use).
- **WSJT-X INI keys all live in the single `[Configuration]` group** (verified
  against WSJT-X source `Configuration.cpp write_settings()`): `MyCall`,
  `MyGrid`, `UDPServer`, `UDPServerPort`, `AcceptUDPRequests` (bool as
  `true`/`false`). There is NO `[Network]` group. WSJT-X rewrites the INI on
  exit, so `preseed_wsjtx.sh` refuses to run while wsjtx is running.
- **Raspberry Pi OS Bookworm+ uses NetworkManager, not dhcpcd.**
  `setup_ap.sh` detects this and creates an nmcli "shared" AP connection
  (`xteink-ap`, autoconnect yes, 192.168.4.1/24); it only falls back to
  hostapd+dnsmasq+dhcpcd on older OS. NM shared mode provides DHCP itself.
- **`install.sh` resolves paths from the script location + `SUDO_USER`** (under
  sudo, `$HOME` is `/root` — never use it for the service user's paths).
- **`decodes_ack` never GCs CQ decodes** (a later `reply` needs them by id);
  `QSOLogged` QDateTime fields are variable-length (13 bytes unless
  timespec==2) and parsed accordingly. Status pushes include a `band` field
  derived from the dial frequency; the firmware band buttons walk a ladder
  (160m..6m) matching `rigctl.BAND_CENTERS`.

## Build & test commands

- Bridge tests: `cd bridge && python test_bridge.py` (expect 14/14 pass).
- Firmware build: `cd firmware && py -3.12 -m platformio run -e x4pro`
- Firmware flash: `py -3.12 -m platformio run -e x4pro -t upload`
- **PlatformIO is installed under Python 3.12 only** (`py -3.12 -m platformio`).
  The Arduino-ESP32 toolchain **rejects Python 3.14** (system default).
- PlatformIO/toolchain lives in `%USERPROFILE%\.platformio`. Build artifacts in
  `firmware/.pio/build/x4pro/` (bootloader.bin, partitions.bin, firmware.bin).
- Flash offsets (verified): bootloader `0x0`, partitions `0x8000`, boot_app0
  `0xe000`, app `0x10000`. Release workflow uses these.
- **Download mode on the X4 Pro:** hold the LEFT/up page button (GPIO0) while
  plugging USB-C, ~3 s, then release. Screen stays blank (e-ink holds the last
  frame — that is normal, NOT a hang). Windows enumerates it as a COM port.
  esptool v5 works at 921600 and hash-verifies; the device re-enumerates as a
  normal USB-CDC serial device once firmware is running.
- **Two online flashers, two file expectations** (user flashes from a web
  tool, not PlatformIO): (1) the generic Espressif web flasher wants the 4
  separate blobs at their offsets, or a **merged** single image at 0x0
  (`esptool merge-bin`, ~1 MB); (2) a *Custom Firmware*-style OTA flasher reads
  the device's own partition table and wants ONLY `firmware.bin` (app image) —
  it rejects a merged blob with "declared size ... does not match file size".
- `esptool` usable outside PlatformIO: `%USERPROFILE%\.platformio\penv\Scripts\python.exe
  -m esptool ...` (the bundled `tool-esptoolpy/esptool.py` fails on a missing
  `rich_click`; the penv one does not).

## Environment notes

- Shell is **Windows PowerShell 5.1**; OS win32. No `rg`; use `grep`/`glob` tools.
- `git` config user = parsimo2010. Repo uses CRLF warnings (cosmetic, no LF attr).
- `gh` authenticated as parsimo2010.

## When hardware arrives — validation checklist (from docs/RELEASE.md)

1. ✅ DONE (2026-09-12) Firmware boots on real X4 Pro; portrait e-ink + GT911
   touch + buttons + deep-sleep splash all confirmed.
2. ⬜ X4 Pro joins Pi AP and connects to bridge (device has only shown NO-LINK).
3. ⬜ CQ decodes appear; tapping completes a QSO with WSJT-X (Auto Seq on).
4. ⬜ Headless Pi boot brings up AP + WSJT-X + bridge.
5. ⬜ `flash.sh` works from a fresh download.

Still to exercise on hardware: the Pi/AP link and a real QSO end-to-end, and
WSJT-X UDP schema across versions. EPD pins, UI metrics, and touch orientation
are now validated and should NOT need re-tuning.

## Release process (only AFTER validation)

`git tag v0.1.0 && git push origin v0.1.0` → `.github/workflows/release.yml`
builds `firmware-<ver>.zip` + `bridge-<ver>.zip` and attaches them to a GitHub
Release. Keep `docs/RELEASE.md` checklist up to date.

## Style / conventions

- Firmware: C++17, no comments unless asked, single-loop immediate-mode UI,
  embedded 5x7 font (`include/font5x7.h`).
- Bridge: pure Python 3 stdlib (deliberately no third-party deps so the Pi zip
  needs no pip install).