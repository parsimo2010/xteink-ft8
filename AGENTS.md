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
- **2026-09 (Pi + QMX + X4 Pro field bring-up): MOSTLY WORKING.** Validated on
  real hardware: WiFi AP join (needed WPA2-RSN pinning — ESP32 rejects
  WPA/WPA2-TKIP mixed APs with reason 211), DHCP, stable TCP device link
  (after the ArduinoJson framing fix), WSJT-X schema negotiation (bridge
  answers heartbeats), wsjtx-improved 3.2 from SourceForge, latest hamlib
  (/opt/hamlib, QMX model 2057), and **band change end-to-end**: X4 Pro
  buttons -> bridge qsy -> rigctld -> QMX QSY with WSJT-X following via NET
  rigctl. Battery % + NET DIAGNOSTIC screen work.
- **STILL BROKEN / UNVALIDATED:**
  * **CQ button does not key the radio.** Bridge sends FreeText(send=1) to
    127.0.0.1:2237 and logs it; no TX. Suspects (check in this order):
    (1) "Accept UDP requests" unchecked in WSJT-X / nothing on 2237
    (`ss -lunp | grep 2237` must show wsjtx); (2) wsjtx-improved 3.x
    validating the command source — bridge now sends controls from the rx
    socket (the addr:port WSJT-X registered for client "xteink" via the
    heartbeat reply); (3) verify reception by watching the Tx5 field when
    tapping CQ. Per WSJT-X docs free_text send=true keys the radio directly
    (Enable Tx not required; there is no UDP command for Enable Tx).
  * Real over-the-air QSO (tap decode -> Reply -> Auto Seq) — needs signals.
  * Headless Pi boot; `flash.sh` from a release zip. Do NOT tag a release
    until docs/RELEASE.md is green.
- **2026-10-27: full code review + fix batch** (branch `fix/review-2026-10-27`,
  findings logged as GitHub issues 1-12). What changed:
  * `device_server.py` rewritten around **one bounded queue + one writer thread per
    connection**. `broadcast()` can no longer block its caller - it used to
    `sendall()` from the single `wsjtx-rx` thread, so one device that stopped
    reading silenced the whole station while systemd still reported healthy (the
    Blocker). Responses and pushes can no longer interleave on a socket, readers
    use `select()` with a 120 s idle deadline so half-open peers are reaped, and
    connections are capped at 4 with least-recently-active eviction.
  * `QsoTracker` has a lock: an `ack()` racing an `add()` could delete a decode the
    device already had on screen (`no_such_decode` on tap). Reproduced, now pinned
    by a test that fails without the lock.
  * CQ classification is token-based: `CQ DX|POTA|SOTA|WW|TEST|<ref> <call> <grid>`
    and a directed `CQ W1AW K1ABC FN20` are recognised, `call` is the **transmitter**
    (last callsign-shaped token), and a bare `CQ DX` is no longer a callable station
    named DX.
  * Boundary validation on the unauthenticated device port: free text must be
    printable ASCII and <= `--max-text` (default **13**, the WSJT-X transmit limit -
    a 6-character callsign needs `--max-text 14`), and `qsy` is refused outside the
    amateur allocations unless `--no-band-check`. `setup_ap.sh` validates
    AP_SSID/AP_PASS and writes `hostapd.conf` mode 0600.
  * `rigctl` parses `RPRT <code>`: a refused QSY answers `qsy_failed` instead of
    `ok_dispatch`. The firmware ignores unknown message types today, so on a refused
    QSY the device stays silent-but-correct - showing `qsy_failed` is an open
    firmware follow-up.
  * Firmware networking: one framing path (`write_all()` + peek-then-commit; the
    dead-but-correct `send_frame()` is deleted), a **static** 16 KB rx scratch
    instead of a per-frame `new[]`, and a byte-bounded rx queue (`NC_QUEUE` 16 -> 6
    plus `NC_QUEUE_BYTES`). Static RAM rises 51.6 KB -> 67.9 KB by design; what goes
    away is the unbounded heap dependency. **Not re-flashed on hardware yet.**
  * `install.sh` grants **audio** as well as dialout and the units set `AuxGroups=`
    (a systemd service is not a logind session, so without this the QMX sound card
    is listed by `aplay -l` but uncapturable). The issue-11 check on a real Pi is
    still to be done.
  * CI: new `.github/workflows/ci.yml` runs the bridge tests and both firmware builds
    on every push/PR; PlatformIO pinned to 6.1.19 in both workflows; `release.yml`
    hard-fails on a missing firmware blob instead of `|| true`, prints each zip's
    contents, and ships + runs `test_bridge.py` in the bridge zip.
  * A firmware version exists at last: `-DXTEINK_FW_VERSION` (PlatformIO needs the
    nested form `-D...='"0.1.0-dev"'`, otherwise gcc sees a bare number), shown on
    NET DIAGNOSTIC, sent as `fw_version` in `hello`, logged by the bridge.
  * Verified by: `python test_bridge.py` **62/62**; `pio run` x4pro + sticky SUCCESS,
    0 warnings; image header bytes identical to the pre-change baseline; `bash -n`
    on every script. NOT verified on hardware or on a Pi.
- Bridge: implemented + passing (62/62; Python, stdlib only).
- Firmware: compiles clean; built current `firmware.bin` ~1.0 MB.
- **2026-10: second build target `env:sticky` added** for the **Seeed reTerminal
  Sticky** (ESP32-S3R8, 3.97" 800x480 SSD1677 + GT911). **Compiles clean, NOT
  yet flashed on hardware.** FreeInk already shipped a validated `STICKY`
  board profile in-tree, so this was mostly wiring up the env + removing the
  X4-Pro-only assumptions. See "Sticky target" below.
- Docs are complete for operators (SETUP / FLASHING / PROTOCOL / RELEASE).
- **2026-10-25 repo review pass (docs + hygiene only, no code behavior
  changed):** README / firmware+bridge README / SETUP / FLASHING / PROTOCOL /
  RELEASE were still single-target (X4 Pro) and partly stale — they said the
  firmware had "never been run on hardware" and quoted 14/14 bridge tests.
  Now: both targets documented everywhere, Supported-devices table in README,
  `config.h` EPD pins explicitly labelled decorative vs the authoritative
  `BoardConfig` profile, Sticky first-boot guidance in FLASHING.md + its
  RELEASE checklist. Deleted a stray empty `package-lock.json`, added the
  missing trailing newline to `release.yml`, and reworded X4-Pro-only text in
  the Pi scripts' echo lines. Verified: `pio run` builds `x4pro` + `sticky`
  clean, `test_bridge.py` 16/16, `bash -n` on all scripts, submodule pin
  `e70baa2` is on the SDK's `origin/main` (so a fresh clone resolves).
- **Findings from the 2026-10 review.** Fixed in the 2026-10-27 batch (see the dated
  entry above): the rigctld `RPRT` omission, the two-writer `sendall()` race, the
  `_client.print()` short-write path in `NetClient::update()`, the unlocked
  `QsoTracker`, and the duplicate `maybe_enter_sleep()` declaration. Still open, and
  needing hardware or a decision rather than a blind guess:
  * Firmware sorts pushed `decode` rows by SNR but ingests `decodes`/`hello`
    snapshots in bridge order, so the list can be unsorted right after link-up.
  * Showing `qsy_failed` on the device: the bridge sends it, the firmware today
    ignores message types it does not know.
  * `CHANGELOG.md` still does not exist, and `--no-band-check` / `--max-text` are not
    in the `docs/SETUP.md` service example yet.
  * systemd `ProtectSystem=` / `PrivateTmp=` hardening was deliberately NOT applied:
    `PrivateTmp` breaks the documented x11vnc workflow (the X11 socket lives in /tmp)
    and `ProtectSystem=strict` stops WSJT-X writing its INI in `$HOME`.
  * WiFi credentials in `config.h` are still literals (no `-D` override).

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
- **UI orientation is per-target** (X4 Pro = PORTRAIT 480x800, Sticky =
  LANDSCAPE 800x480 rotated 180°) via a per-pixel software transform in
  `ui.cpp` (the panel RAM is landscape-native; rotation is NOT expressible in
  the SSD1677/UC8179/UC8279 controller). It stays a one-constant change:
  `cfg::UI_ROTATION` in `config.h` — 0 = landscape native, 1 = portrait CW,
  2 = portrait CCW, **3 = landscape 180° (added for the Sticky)**. Drawing and
  the touch-tap mapping both key off that one constant.
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
  `true`/`false`). Rig keys exist too (`Rig` = NAME string, e.g. "Hamlib NET
  rigctl" — not a number; `CATNetworkPort` = "host:port"; `PTTMethod` int:
  0=VOX 1=CAT 2=DTR 3=RTS; `PTTport`; `DataMode` int: 0=None 1=USB 2=Data) but
  the project no longer preseeds them — rig/audio are configured manually
  once in the GUI (a first field attempt at preseeding rig+audio keys was
  reverted). Config file path differs by version: **3.x/wsjtx-improved:
  `~/.config/WSJT-X.ini`; 2.x: `~/.config/WSJT-X/WSJT-X.ini`** — preseed
  searches both. There is NO `[Network]` group. WSJT-X rewrites the INI on
  exit, so `preseed_wsjtx.sh` refuses to run while wsjtx is running.
- **Band change is ON BY DEFAULT for the QRP Labs QMX/QMX+** (the field rig).
  `xteink-rigctld.service` runs `start_rigctld.sh`: auto-detects the QMX USB
  serial port (`/dev/serial/by-id/*QRP*`, waits if unplugged), resolves the
  hamlib model (QMX=2057 if available, else QCX/QDX 2052, else TS-480 2028 —
  QMX CAT is a TS-480 subset), always passes `--serial-speed=115200` (the QMX
  backend's 256000 default is rejected by termios). WSJT-X must be pointed at
  "Hamlib NET rigctl" @ 127.0.0.1:4532 (manual GUI step, see SETUP.md §4) so
  ONE rigctld owns the radio for both WSJT-X and the bridge (`--rig-host`
  defaults to 127.0.0.1). **Port ownership gotcha:** while xteink-rigctld
  runs, WSJT-X configured for direct serial CAT (/dev/ttyACM0) can never open
  the port — Test CAT stays red; either use NET rigctl or `systemctl disable
  --now xteink-rigctld` (band buttons then report not_supported). Overrides in
  `/etc/default/xteink-rigctld`. QMX facts: hamlib model 2057 exists only in
  hamlib ≥ 4.6.1; Bookworm ships 4.5.4, Trixie ships 4.6.2 — that's why
  `build_hamlib.sh` builds the LATEST hamlib release into `/opt/hamlib`
  (private prefix, `start_rigctld.sh` prefers it; distro packages untouched).
- **QMX audio is a MANUAL WSJT-X setting — do NOT try to make it the system
  default.** Learned the hard way (2026, real Pi): forcing `snd_usb_audio
  index=0` via modprobe makes the QMX sound probe fail with -16/EBUSY
  ("cannot create card instance 0") because the Pi's HDMI/vc4 card already
  holds index 0 (an `snd_bcm2835 index=1` option does not reliably free it).
  The former `setup_qmx_audio.sh` was deleted; if a Pi ever shows that dmesg
  error, remove `/etc/modprobe.d/xteink-qmx-audio.conf` and any
  `/etc/asound.conf` pin and reboot. WSJT-X device strings
  (`SoundInName`/`SoundOutName`) are backend-dependent (ALSA vs
  Pulse/PipeWire, Qt5 vs Qt6), so they are not preseedable — select the QMX
  USB card in Settings → Audio once, manually.
- **WSJT-X flavor = wsjtx-improved (DG2YCB fork), always latest.**
  `install_wsjtx.sh` scrapes the SourceForge files page for the newest
  `WSJT-X_vX.Y.Z` folder (sort -uV), reads that folder's RSS, and installs the
  plain `_improved_PLUS_..._Rpi_<codename>_<arch>.deb` (~60 MB; widescreen/AL
  variants via WSJTX_VARIANT). Fallbacks: apt `wsjtx-improved` (Debian trixie+)
  then apt `wsjtx`. Drop-in: same `/usr/bin/wsjtx` binary, same UDP schema
  3 (v3.x only APPENDS fields, e.g. `itone` in Status — `wsjtx_udp.py`
  `_parse_status` ignores trailing bytes, so the bridge is compatible), but
  3.x moved the INI to `~/.config/WSJT-X.ini` (see above).
- **WSJT-X MessageServer client model** (verified against WSJT-X source):
  clients are registered **by id string** (any inbound message registers;
  Heartbeat negotiates the schema and gets a reply); incoming commands are
  dispatched by id and (in 2.x) NOT source-port validated, but the bridge
  nonetheless sends all controls from the **rx socket** — the addr:port WSJT-X
  registered for id "xteink" — mirroring a real MessageClient and covering
  stricter 3.x builds. Incoming command handling is gated by WSJT-X's
  `accept_udp_requests` config ("Accept UDP requests" checkbox).
- **WSJT-X schema negotiation is REQUIRED:** WSJT-X streams **schema 2** to a
  UDP client until that client answers a Heartbeat with its own Heartbeat
  declaring max_schema 3 (found on real hardware 2026: bridge logged
  "unsupported schema 2" until this was implemented). The bridge replies to
  every Heartbeat (`wsjtx_udp.build_heartbeat`) on the rx socket; schema-2
  non-heartbeat messages are unparseable (Qt_5_0 float/QDateTime encoding)
  and are dropped until negotiation completes.
- **All `bridge/scripts/*.sh` are committed with the exec bit (100755).**
  A checkout with mode 644 makes systemd fail `xteink-wsjtx` with
  "EXEC spawn ... permission denied" — `git pull` resets the worktree mode to
  the index mode, so install.sh's `chmod +x` alone does not survive updates.
- **ArduinoJson GOTCHA (caused the eternal NO-LINK, fixed 2026):**
  `serializeJson(doc, String)` CLEARS the String first (ArduinoJson's
  `Writer<::String>` ctor assigns null). `NetClient::send()` used to concat
  the 4-byte length header into the String and THEN serialize — wiping the
  header, so every frame hit the bridge as raw `{"cm...` → "bad frame length
  2065851245" (0x7B22636D) → socket closed → 5 s reconnect loop. Always
  serialize first, then build header+payload. The Python bridge tests can't
  catch this (they frame correctly in Python); only real hardware exercises
  NetClient::send().
- **X4 Pro network diagnostics:** until the FIRST successful bridge link the
  device shows a full-screen **NET DIAGNOSTIC** instead of the decode list:
  target SSID, raw WiFi.status() code + meaning (0 IDLE, 1 NO-SSID,
  3 CONNECTED, 4 AUTH-FAIL, 6 DISCONNECTED), a real `WiFi.scanNetworks()`
  every 15 s ("sees XTEINK-FT8 -52dBm" vs "NOT seen" — distinguishes radio/
  SSID problems from auth problems), DHCP IP, and TCP try/fail counters for
  192.168.4.1:4510. First link-up latches `g_everLinked` and switches to the
  normal screens permanently (taps gated while diag is up). Status bar tags
  after that: no tag = link up; `NO-WIFI`/`NO-SSID` = not associated;
  `<ip> NO-LINK` = on WiFi, bridge TCP down. Same info on USB serial
  (`[net] ...` @115200) when the pogo pins cooperate. Backed by
  `NetClient::wifi_connected()/wifi_status()/wifi_ip()/scan_*()/tcp_tries()`.
- **Battery % is shown on both screens** (status bar right side, next to TX;
  and as a `BATT` line on NET DIAGNOSTIC). Source: the X4 Pro's **CW2017 I2C
  fuel gauge at 0x63 on the shared touch bus SDA39/SCL38** — the SDK
  `BatteryMonitor` lib (add it to `lib_deps` as a symlink like the other SDK
  libs) uploads the OEM 80-byte BATINFO profile and reads SoC; gauge reports
  0%/invalid until ready, so the UI retries every 3 s until the first good
  read, then polls every 60 s and keeps the last good value (`--` when
  unknown). `batteryAdc` is PIN_UNASSIGNED on X4 Pro; the gauge backend is
  selected at runtime and gated by `FREEINK_DEVICE_X4PRO`.
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

## Sticky target (Seeed reTerminal Sticky) — what differs from the X4 Pro

Device-specific values are isolated in `include/config.h` keyed off
`FREEINK_DEVICE_STICKY`; `main.cpp`/`ui.cpp` are device-neutral (the only
compiled-out X4-Pro-specific bit is the sleep latch hold).

- **Panel:** SSD1677 800x480, SCLK13 MOSI14 CS15 DC16 RST17 BUSY18 + panel
  power-enable 47 (all taken from the FreeInk `STICKY` profile, which matches
  Seeed's hardware overview and the vendor demo pin-for-pin).
- **Landscape UI.** The card is 106x65.5 mm and Seeed's own display layer
  rotates 180°, so Sticky builds default to `UI_ROTATION = 3` (landscape + 180,
  a mode added to `Ui` for this target) while the X4 Pro stays `1` (portrait).
  Tune without editing code: `PLATFORMIO_BUILD_FLAGS=-DXTEINK_UI_ROTATION=0..3`
  (`pio run` has no `--build-flag` option; the env var DOES append to env flags).
  The NET DIAGNOSTIC screen prints `DEV sticky rot 3` so orientation is
  verifiable with no serial cable.
- **Console is UART0, not USB CDC.** The Sticky's USB-C is a WCH CH343 bridge
  (`1a86:55d3`, port name "USB Single Serial") on GPIO43/44; native USB D+/D-
  (GPIO19/20) are wired to the PDM mic instead. All logging therefore goes
  through `cfg::serial()` = `BoardConfig::serialTransport()` (Serial0 on the
  Sticky, `Serial` on the X4 Pro). Never use bare `Serial` in this codebase.
- **Buttons: 3, but the third is shared.** UP=GPIO5, DOWN=GPIO6 scroll; the
  AI/OK/PWR key is GPIO4 for both confirm and power
  (`InputStyle::DigitalConfirmPowerHold`): a click surfaces as `BTN_CONFIRM`
  (we map it to re-fetch decodes / Back), a hold past the SDK's internal
  400 ms surfaces as `BTN_POWER`, so `POWER_HOLD_SLEEP_MS = 1500` still sleeps
  it. GPIO4 is also the EXT1 wake pin. There is no capacitive Home key.
- **Power latch must survive sleep.** PWR_HOLD 45 + PWR_LOCK 46 hold a 74AHC1G79
  that keeps the board on; `latchPowerRailsForSleep()` in main.cpp gpio-holds
  them HIGH before `deepSleepUntilPowerButton()` (Sticky-only — the X4 Pro's
  latch0 is a rail enable and its sleep path is already hardware-validated).
- **microSD shares the panel's SPI bus** (CS8, MISO12, card power EN10). A rail
  a previous sleep latched off clamps SCLK/MOSI, so `setup()` calls
  `BoardConfig::releaseSdRail()` when `sd.sclk == display.sclk` (true on the
  Sticky, false on the X4 Pro — no behavior change there).
- **Battery:** BQ27220 @0x55 on the sensor bus SDA1/SCL0 served on **Wire1**
  (the GT911 owns `Wire` on SDA3/SCL2); the X4 Pro uses a CW2017 @0x63 on the
  shared touch bus. `BatteryMonitor`'s default ctor dispatches on the profile,
  so nothing in the app changes.
- **Unused Sticky silicon** (PDM mic, buzzer GPIO48, PCF8563, SHT40, LSM6DS3):
  their SDK caps auto-enable for the device but the libraries are NOT in
  `lib_deps`, so no code is pulled in and no pins are touched.

## Build & test commands

- Bridge tests: `cd bridge && python test_bridge.py` (expect 62/62 pass; CI now runs
  this on every push and PR, and it must stay a plain `python` invocation - the
  bridge has no third-party dependencies).
- Firmware build: `cd firmware && ~/.platformio/penv/Scripts/pio.exe run -e x4pro`
  (or `-e sticky`, or bare `pio run` for both — `default_envs = x4pro, sticky`).
- Firmware flash: `pio run -e x4pro -t upload` / `pio run -e sticky -t upload --upload-port <COM>`
- **Python situation on this box (rechecked 2026-10):** there is **no `py -3.12`
  any more** — the only system Python is 3.14, which the pioarduino platform
  rejects outright ("Python version must be 3.10–3.13"). The working
  interpreter + PlatformIO is the installer's venv:
  **`%USERPROFILE%\.platformio\penv\Scripts\pio.exe`** (Python 3.12.10). Use it
  for builds and for `-m esptool`.
- PlatformIO/toolchain lives in `%USERPROFILE%\.platformio`. Build artifacts in
  `firmware/.pio/build/x4pro/` (bootloader.bin, partitions.bin, firmware.bin).
- Flash offsets (verified): bootloader `0x0`, partitions `0x8000`, boot_app0
  `0xe000`, app `0x10000`. Release workflow uses these (same for both targets —
  `partitions.csv` is shared and spans the first 16 MB).
- **pioarduino flash-size/flash-mode gotchas** (learned while adding the Sticky
  target): the image header's flash size comes from the board manifest key
  `upload.flash_size`, so override it with **`board_upload.flash_size`** —
  `board_build.flash_size` does NOT reach `esptool elf2image` (the sticky env
  silently built an 8 MB image until this was fixed). And `_get_board_flash_mode()`
  in the platform **maps qio/qout → dio** anyway (opi memory types → dout), so
  every image here is DIO; the Sticky wants DIO @ 80 MHz / 32 MB, which is what
  Seeed's demos and the community firmware use for its 32 MB QSPI part.
- **esptool v5:** `--flash-mode/-fm`, `-ff`, `-fs` are options of the
  `write-flash` subcommand, NOT global options (global placement = "No such
  option"), and `write_flash`/`read-flash` spellings are mixed-deprecated. The
  sticky env uses `board = esp32-s3-devkitc-1` (no PSRAM declared — FreeInk
  keeps the 48 KB framebuffer in internal DRAM for this device) with
  `upload_speed = 460800`; the CH343 bridge auto-enters the bootloader, so there
  is no download-mode button on this device.
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

## Operator-facing docs — keep in sync when a target changes

README (both-target table), `firmware/README.md`, `docs/FLASHING.md` (per-device
section + troubleshooting), `docs/SETUP.md`, `docs/PROTOCOL.md`,
`docs/RELEASE.md` (checklist + the test count CI reports). A new build target is
not "done" until these mention it and its validation status.

## When hardware arrives — validation checklist (from docs/RELEASE.md)

1. ✅ DONE (2026-09-12) Firmware boots on real X4 Pro; portrait e-ink + GT911
   touch + buttons + deep-sleep splash all confirmed.
2. ⬜ X4 Pro joins Pi AP and connects to bridge (device has only shown NO-LINK).
3. ⬜ CQ decodes appear; tapping completes a QSO with WSJT-X (Auto Seq on).
4. ⬜ Headless Pi boot brings up AP + WSJT-X + bridge.
5. ⬜ `flash.sh` works from a fresh download.
6. ⬜ **Sticky (`env:sticky`) on real hardware** — builds clean but never
   flashed. Check in this order: does the panel paint at all (SSD1677 + EN47),
   is it upside down (`DEV sticky rot 3` on the NET DIAGNOSTIC screen; try
   `-DXTEINK_UI_ROTATION=0`), do touch taps land under the finger (the digitizer
   mapping is in the FreeInk `STICKY` profile, not our code), UP/DOWN scroll,
   AI-click re-fetch, 1.5 s AI-hold → SLEEPING → power-button wake (the power
   latch is the thing to suspect if it will not wake), battery % from BQ27220.

Still to exercise on hardware: the Pi/AP link and a real QSO end-to-end, and
WSJT-X UDP schema across versions. EPD pins, UI metrics, and touch orientation
are now validated and should NOT need re-tuning.

## Release process (only AFTER validation)

`git tag v0.1.0 && git push origin v0.1.0` → `.github/workflows/release.yml`
builds `firmware-<ver>.zip` (x4pro) + `firmware-sticky-<ver>.zip` (sticky) +
`bridge-<ver>.zip` and attaches them to a GitHub Release. Keep `docs/RELEASE.md`
checklist up to date. The sticky zip's `flash.sh` differs from the X4 Pro one:
it adds `-fm dio -ff 80m -fs 32MB` and assumes the CH343 auto-resets the chip.

## Style / conventions

- Firmware: C++17, no comments unless asked, single-loop immediate-mode UI,
  embedded 5x7 font (`include/font5x7.h`).
- Bridge: pure Python 3 stdlib (deliberately no third-party deps so the Pi zip
  needs no pip install).