# xteink-ft8 — Flashing the device

Two e-ink targets are supported; pick the section for your hardware:

| device | build env | console / flashing |
|--------|-----------|--------------------|
| **Xteink X4 Pro** | `x4pro` | native USB CDC (`/dev/ttyACM0`, `COMx`) — needs download mode |
| **Seeed reTerminal Sticky** | `sticky` | USB-C → WCH CH343 bridge on UART0 (port named **USB Single Serial**) — see [Flashing the Seeed reTerminal Sticky](#flashing-the-seeed-reterminal-sticky-envsticky) |

The build steps, config file and PlatformIO setup below apply to both devices;
only the env name and how the board is put into its bootloader differ. Flashing
replaces the stock firmware, and is reversible — see "Restoring stock firmware".

> **Status:** the **X4 Pro** target has been flashed and **boots on real
> hardware** (portrait e-ink, touch, and deep sleep confirmed). The **Sticky**
> target compiles clean but has **not been run on hardware yet** — see its
> section for what to expect and how to tune it.

---

## Prereqs

* A computer (Windows/Linux/macOS) with a USB cable (USB-C).
* **Python 3.10–3.13.** The Arduino-ESP32 toolchain used here does **not**
  support Python 3.14. Check with `python3 --version` (or `py -0` on Windows).
  If you have 3.14, use `python3.12` / `py -3.12` instead.
* Either **PlatformIO Core** (for Option A) or **esptool** (for Option B).

---

## Install PlatformIO / esptool

**PlatformIO** (needed to build, and can also flash):

```bash
# Linux/macOS
pipx install platformio
# or, if you already have a 3.10-3.13 interpreter:
python3.12 -m pip install --user platformio

# Windows
py -3.12 -m pip install --user platformio
```

**esptool** (only needed if you flash a prebuilt `.bin` instead of building):

```bash
python3.12 -m pip install --user esptool
# or: pip install esptool
```

---

## Set your configuration

Edit `firmware/include/config.h` and set (at minimum):

* `WIFI_SSID` / `WIFI_PASSWORD` — must match the Pi access point
  (default `XTEINK-FT8` / `ft8field` from `setup_ap.sh`).
* `BRIDGE_HOST` — the Pi's AP IP (`192.168.4.1`).
* `BRIDGE_PORT` — `4510`.
* `MY_CALL` / `MY_GRID` — **optional** fallback; the callsign configured in
  WSJT-X is used as the source of truth once connected.

```cpp
inline constexpr const char* WIFI_SSID = "XTEINK-FT8";
inline constexpr const char* WIFI_PASSWORD = "ft8field";
inline constexpr const char* BRIDGE_HOST = "192.168.4.1";
inline constexpr uint16_t BRIDGE_PORT = 4510;
```

---

## Option A — Build and flash with PlatformIO (recommended, X4 Pro)

Get the source (including the FreeInk SDK submodule):

```bash
git clone --recurse-submodules https://github.com/parsimo2010/xteink-ft8.git
cd xteink-ft8/firmware
```

Put the X4 Pro into **download mode** (see below), then:

```bash
pio run -e x4pro            # compile
pio run -e x4pro -t upload  # flash over USB
pio device monitor          # optional: view serial logs
```

PlatformIO writes the bootloader, partition table, OTA stub, and app together,
so this is the most reliable path.

---

## Entering download mode on the X4 Pro

ESP32-S3 boards enter "download mode" when GPIO0 is held low during reset:

1. Hold the **left / up nav button** (this is GPIO0 on the X4 Pro).
2. While holding it, briefly press **reset** (or power-cycle the device).
3. Release the button. The device is now in download mode.

> The exact button may vary by unit. If the left button doesn't work, try the
> other page-turn button. On Windows, the device appears as a serial port
> (e.g. `COM3`); on Linux as `/dev/ttyACM0`. If nothing enumerates, you are not
> in download mode.

---

## Option B — Flash a prebuilt release (future)

> Not yet published. Once a release exists, download
> `xteink-ft8-firmware-<version>.zip`, extract it, and run:

```bash
# Put the X4 Pro in download mode first, then:
esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 921600 write_flash -z \
  0x0      bootloader.bin \
  0x8000   partitions.bin \
  0xe000   boot_app0.bin \
  0x10000  firmware.bin
```

On Windows use `--port COM3` (your actual port). The offsets above are the
project's partition layout (bootloader → partitions → OTA stub → app) and are
the same for both targets; a Sticky release zip, when one exists, carries the
`sticky` build of those files and needs `--flash-mode dio --flash-size 32MB`
added (see the Sticky section below).

---

## Verifying it booted

* With `pio device monitor` (or a serial terminal at 115200 baud) you should
  see the serial log showing display init, WiFi, and bridge connection.
* The e-ink screen should show the status bar with your band/mode and
  **NO-LINK** (until the Pi AP + bridge are up).

---

## Flashing the Seeed reTerminal Sticky (env:sticky)

The Sticky is a Seeed ESP32-S3 card (3.97" 800x480 SSD1677 + GT911 touch, 8 MB
PSRAM, 32 MB flash). It shares the app with the X4 Pro but NOT the pinout, so
build the `sticky` env for it.

> **Status: builds clean, not yet run on hardware.** The pin map below is
> Seeed's own (hardware overview + vendor peripheral demo) and matches the
> FreeInk `FREEINK_DEVICE_STICKY` profile. The likeliest first-session tuning is
> panel orientation and touch mirroring — see "Tuning the Sticky display".

### Wiring up and finding the port

The USB-C socket on the Sticky is **not** native USB: it goes through an
on-board **WCH CH343** USB-UART bridge (`1a86:55d3`, port name *USB Single
Serial*), which is tied to UART0 (GPIO43/44). That port is used for flashing
AND for the serial log — the same port for both.

* Use a **data** USB-C cable (charge-only cables power the board but enumerate
  nothing).
* The ESP32-S3 ROM bootloader is entered automatically via DTR/RTS, so there is
  no download-mode button dance. If `esptool` cannot sync, use the reset hole.
* Back up the factory image before overwriting it (the stock firmware's own
  partition layout is different, and Seeed ships no restore image):

```bash
esptool --port $PORT read-flash 0 0x2000000 sticky-stock-32MB.bin
```

### Build + flash

```bash
cd xteink-ft8/firmware
pio run -e sticky                   # compile
pio run -e sticky -t upload --upload-port $PORT   # Windows: --upload-port COM5
pio device monitor --port $PORT --baud 115200     # UART0 console
```

The image is built **DIO @ 80 MHz** and declares **32 MB** of flash (Seeed's
part is a 32 MB QSPI device); the repo's shared `partitions.csv` occupies the
first 16 MB of it, so the flash offsets are identical to the X4 Pro:

```bash
esptool --chip esp32s3 --port $PORT --baud 460800 write_flash -z \
  --flash-mode dio --flash-freq 80m --flash-size 32MB \
  0x0      bootloader.bin \
  0x8000   partitions.bin \
  0xe000   boot_app0.bin \
  0x10000  firmware.bin
```

(`.pio/build/sticky/` holds those four files after a build. If the bridge
baud rate drops bytes, add `--baud 115200`.)

### Sticky hardware map (for reference)

| thing | pins |
|-------|------|
| SSD1677 panel | SCLK 13, MOSI 14, CS 15, DC 16, RST 17, BUSY 18, panel EN 47 |
| GT911 touch | SDA 3, SCL 2, INT 21, RST 41, TOUCH_EN 42 (its own I2C bus) |
| buttons | UP 5, DOWN 6, and a shared **AI/OK/PWR on GPIO4** (also the deep-sleep wake pin) |
| battery | BQ27220 gauge at 0x55 on the sensor bus SDA 1 / SCL 0 (`Wire1`) |
| power latch | PWR_HOLD 45 + PWR_LOCK 46 (asserted at boot, held through sleep) |
| microSD | shares the panel's SPI bus: CS 8, MISO 12, card power 10 |
| console | UART0 on GPIO43/44 → CH343 → USB-C |

The app uses: UP/DOWN to scroll, a **tap of the AI key** to re-fetch decodes
(or go back from the QSO screen), and a **1.5 s hold of the AI key** to sleep.
Battery % comes from the BQ27220 instead of the X4 Pro's CW2017 — the SDK picks
the backend from the board profile, so there is nothing to configure.

### Tuning the Sticky display

The Sticky is a **landscape** card whose glass is mounted 180 degrees from the
controller's native scan; Seeed's own display layer applies that rotation, and
so does this firmware (`UI_ROTATION = 3`). If the image comes up upside down or
mirrored, override the rotation without editing code, then reflash:

```bash
# 0 = landscape native, 1 = portrait 90 CW, 2 = portrait 90 CCW,
# 3 = landscape rotated 180 deg  <- Sticky default (no flag needed)
PLATFORMIO_BUILD_FLAGS=-DXTEINK_UI_ROTATION=0 pio run -e sticky            # bash
$env:PLATFORMIO_BUILD_FLAGS="-DXTEINK_UI_ROTATION=0"; pio run -e sticky    # PowerShell
```

(Or just edit `UI_ROTATION` in `include/config.h`; the override flag exists so a
unit can be tuned without touching the source.)

Touch taps are rotated with the same constant, so the glass and the digitizer
stay aligned; if only touch is misaligned (image correct), the digitizer mapping
lives in the FreeInk Sticky profile (`BoardConfig::STICKY.touch`), not here.

The NET DIAGNOSTIC screen (shown until the first bridge link) prints
`DEV sticky rot 3` so you can confirm which target and orientation a build is
using, without a serial cable.

---

## Which pins actually count

`include/config.h` documents the panel pins per target, but the driver reads
them from the FreeInk board profile (`BoardConfig::ACTIVE`) chosen by
`-DFREEINK_DEVICE_X4PRO` / `-DFREEINK_DEVICE_STICKY` in `platformio.ini`. If a
panel does not respond, change the **device flag / SDK profile**, not
`config.h`. UI orientation is the one exception: that is genuinely ours and is
set by `cfg::UI_ROTATION` (overridable with `-DXTEINK_UI_ROTATION`).

---

## Restoring stock firmware

Flashing is fully reversible. To restore the original Xteink OS use the
official Xteink update method (web flasher / recovery), or:

* On the **Sticky**, restore the 32 MB dump you took before flashing
  (`esptool --port $PORT write-flash 0 sticky-stock-32MB.bin`); Seeed ships no
  public stock image, so that dump is the only way back.

* If you have a copy of the stock firmware image, flash it with `esptool
  write_flash` at the same offsets the stock image used.
* The device is put into the same **download mode** to re-flash.

> Keep the stock firmware image somewhere safe before replacing it.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `pio run` fails with a Python version error | Use a 3.10–3.13 interpreter (e.g. `python3.12 -m platformio run -e x4pro`). |
| Device not detected | **X4 Pro:** not in download mode — hold the left/up button, then reset / power-cycle. **Sticky:** use a *data* USB-C cable; the CH343 port is named *USB Single Serial*. |
| Upload times out | Check the port; try `--baud 115200` (slower, more reliable). |
| Screen blank after flash | Check you flashed the right env for the device (`x4pro` vs `sticky`): the panel pins come from the FreeInk board profile selected by `-DFREEINK_DEVICE_*`, **not** from the decorative `cfg::EPD_*` values in `config.h`. The X4 Pro profile is hardware-confirmed; the Sticky profile is Seeed's pin map, not yet run here. |
| Sticky paints upside down | `-DXTEINK_UI_ROTATION=0` (see "Tuning the Sticky display"); the NET DIAGNOSTIC screen prints `DEV sticky rot N`. |
| No `NO-LINK` → not connecting | The Pi AP must be up and `BRIDGE_HOST` must match the Pi's AP IP. |