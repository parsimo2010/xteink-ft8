# xteink-ft8 firmware (Xteink X4 Pro)

FT8 field UI for the Xteink X4 Pro (ESP32-S3 e-ink reader). Built on the
**FreeInk SDK** (the same display/input stack used by CrossPoint), vendored as a
git submodule at `freeink-sdk/`.

## Prereqs

* PlatformIO Core (`pipx install platformio`, or the CLI bundled with VS Code)
* **Python 3.10–3.13.** The Arduino-ESP32 toolchain does **not** support 3.14.
  Use `python3.12` / `py -3.12` if your default is 3.14.
* A submodule checkout: `git clone --recurse-submodules ...` or
  `git submodule update --init --recursive`
* Your WiFi credentials (and bridge address) set in `include/config.h`

## Build & flash

```bash
pio run -e x4pro             # compile
pio run -e x4pro -t upload   # flash over USB (put the X4 Pro in download mode first)
pio device monitor           # serial logs (optional)
```

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

## Notes / prototype status

* The X4 Pro hardware profile in the FreeInk SDK is mostly hardware-confirmed;
  a few items (frontlight GPIO mapping, some orientation details) are still
  pending validation. If the panel doesn't come up, check the EPD pins in
  `config.h` against your unit.
* The firmware has not yet been run on hardware. Expect UI/metrics tuning on
  the real 800x480 panel.