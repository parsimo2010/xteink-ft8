# xteink-ft8 firmware (Xteink X4 Pro + Seeed reTerminal Sticky)

FT8 field UI for ESP32-S3 e-ink readers. Built on the **FreeInk SDK** (the same
display/input stack used by CrossPoint), vendored as a git submodule at
`freeink-sdk/`. One source tree, two build envs:

| env | device | panel / touch | buttons | battery gauge | console |
|-----|--------|---------------|---------|---------------|---------|
| `x4pro` | Xteink X4 Pro | SSD1677 800x480, **portrait UI**, GT911 (shared I2C bus) | UP0 DOWN7 PWR3 | CW2017 @0x63 | native USB CDC |
| `sticky` | Seeed reTerminal Sticky | SSD1677 800x480, **landscape UI** (glass mounted 180°), GT911 (own I2C bus) | UP5 DOWN6 + shared AI/OK/PWR4 | BQ27220 @0x55 (`Wire1`) | UART0 → CH343 on USB-C |

## Prereqs

* PlatformIO Core (`pipx install platformio`, or the CLI bundled with VS Code)
* **Python 3.10–3.13.** The Arduino-ESP32 toolchain does **not** support 3.14.
  Use `python3.12` / `py -3.12` if your default is 3.14.
* A submodule checkout: `git clone --recurse-submodules ...` or
  `git submodule update --init --recursive`
* Your WiFi credentials (and bridge address) set in `include/config.h`

## Build & flash

```bash
pio run                    # compile both targets
pio run -e x4pro           # compile one target
pio run -e x4pro -t upload # flash over USB (put the X4 Pro in download mode first)
pio device monitor         # serial logs (optional)

pio run -e sticky -t upload --upload-port <port>   # Sticky: the CH343 "USB Single Serial" port
```

The Sticky needs no download-mode dance (its CH343 bridge auto-resets the S3)
and is flashed **DIO / 32 MB**; see `../docs/FLASHING.md`. Always pass `-e <env>`
for uploads — a bare `pio run -t upload` would try both boards in turn.

> **Entering download mode:** hold the left/up nav button (GPIO0) while
> pressing reset / power-cycling. See **`../docs/FLASHING.md`** for full
> flashing-from-stock instructions, download-mode details, and how to restore
> the stock firmware.

## Layout

| file | purpose |
|------|---------|
| `include/config.h` | WiFi, bridge address, your call/grid, pins, UI tuning |
| `include/font5x7.h` | embedded 5x7 bitmap font |
| `include/proto.h` / `src/proto.cpp` | length-framed JSON protocol |
| `include/net_client.h` / `src/net_client.cpp` | WiFi + TCP client with reconnect |
| `include/ui.h` / `src/ui.cpp` | 1-bit framebuffer renderer |
| `src/main.cpp` | app: message handling, input, screens, rendering |
| `freeink-sdk/` | FreeInk SDK (submodule) |

## Configuration

Edit `include/config.h`:
* `WIFI_SSID` / `WIFI_PASSWORD` — the Pi access point (must match `setup_ap.sh`).
* `BRIDGE_HOST` / `BRIDGE_PORT` — the Pi AP IP (`192.168.4.1`) and port (`4510`).
* `MY_CALL` / `MY_GRID` — optional; the callsign configured in WSJT-X is used
  as the source of truth once connected.

## How it works

* Connects to the Pi's WiFi AP, then the bridge TCP server (port 4510).
* On `hello`, the bridge returns your call/grid, band, mode, and a CQ snapshot.
* Incoming `decode` messages keep a live list of CQ stations (sorted by SNR).
* Tap a row → sends `reply` → WSJT-X answers that station and drives the QSO.
* Bottom bar: **CQ** (send CQ), **<< / >>** (band change), **RFR** (re-fetch
  decodes), **Halt** (stop TX). In the QSO detail view: **Back / Halt**.
* The nav buttons (Up/Down) scroll the list.

## Sticky specifics

* Landscape UI: `UI_ROTATION = 3` (the glass is mounted 180° from the panel's
  native scan, which is what Seeed's own display layer does). Override per
  build with `-DXTEINK_UI_ROTATION=0..3` if a unit disagrees.
* Three buttons, not three independent ones: UP/DOWN scroll, and the **AI key
  (GPIO4) is shared** with the power key — the FreeInk `InputManager` reports a
  click as `BTN_CONFIRM` (re-fetch decodes, or Back from the QSO screen) and a
  hold as `BTN_POWER` (1.5 s → deep sleep). Wake is EXT1 on the same pin.
* The board is held on by a power latch (PWR_HOLD 45 / PWR_LOCK 46); it is
  asserted at boot via `BoardConfig::holdPowerRails()` and latched through deep
  sleep so the wake pin stays live.
* Battery % comes from a BQ27220 gauge on `Wire1` (the touch owns `Wire`);
  `BatteryMonitor` picks the backend from the board profile.
* The microSD card shares the panel's SPI bus, so `setup()` re-powers that rail
  (`BoardConfig::releaseSdRail()`) before touching the display — a rail a
  previous sleep latched off would clamp SCLK/MOSI.
* The PDM mic, buzzer, RTC, SHT40 and IMU are on this board but unused here, so
  their SDK libraries are not in `lib_deps`.

## Hardware status

* **X4 Pro (`x4pro`): validated on real hardware** (2026-09-12 bring-up).
  Portrait e-ink rendering on the SSD1677, GT911 touch with the correct
  rotation mapping, tap-flash feedback, page-button scrolling and hold-power
  deep sleep with power-button wake all work. The X4 Pro profile in the FreeInk
  SDK is hardware-confirmed for everything this app uses.
* **Sticky (`sticky`): compiles clean, never flashed.** Treat the first session
  as bring-up: see "Sticky specifics" above and the Sticky section of
  `../docs/FLASHING.md` for the ordered checklist.

> **The `cfg::EPD_*` constants are documentation, not the source of truth.**
> `FreeInkDisplay::begin()` re-derives the panel pins from the active
> `BoardConfig` profile (`FREEINK_DEVICE_X4PRO` / `FREEINK_DEVICE_STICKY`), so
> if a panel does not paint the fix is the device flag / SDK profile, not
> `config.h`.