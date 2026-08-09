# xteink-ft8 firmware (Xteink X4 Pro)

FT8 field UI for the Xteink X4 Pro (ESP32-S3 e-ink reader). Built on the
**FreeInk SDK** (the same display/input stack used by CrossPoint), vendored as a
git submodule at `freeink-sdk/`.

## Prereqs

* PlatformIO Core (`pipx install platformio`, or the CLI bundled with VS Code)
* A submodule checkout: `git submodule update --init --recursive`
* Your call / grid / WiFi credentials set in `include/config.h`

## Build & flash

```bash
pio run -e x4pro            # compile
pio run -e x4pro -t upload  # flash over USB
pio device monitor         # serial logs (optional)
```

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