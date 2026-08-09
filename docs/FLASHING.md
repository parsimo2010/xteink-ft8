# xteink-ft8 — Flashing the Xteink X4 Pro

This replaces the stock Xteink OS on the X4 Pro with the xteink-ft8 firmware.
**You can restore the stock firmware later** (see "Restoring stock firmware").

> **Status:** this is a first prototype. It has not yet been run on real
> hardware. Proceed on hardware you are willing to experiment on.

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

## Option A — Build and flash with PlatformIO (recommended)

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
project's partition layout (bootloader → partitions → OTA stub → app).

---

## Verifying it booted

* With `pio device monitor` (or a serial terminal at 115200 baud) you should
  see the serial log showing display init, WiFi, and bridge connection.
* The e-ink screen should show the status bar with your band/mode and
  **NO-LINK** (until the Pi AP + bridge are up).

---

## Restoring stock firmware

Flashing is fully reversible. To restore the original Xteink OS use the
official Xteink update method (web flasher / recovery), or:

* If you have a copy of the stock firmware image, flash it with `esptool
  write_flash` at the same offsets the stock image used.
* The device is put into the same **download mode** to re-flash.

> Keep the stock firmware image somewhere safe before replacing it.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `pio run` fails with a Python version error | Use a 3.10–3.13 interpreter (e.g. `python3.12 -m platformio run -e x4pro`). |
| Device not detected | Not in download mode. Hold the left/up button + reset. |
| Upload times out | Check the port; try `--baud 115200` (slower, more reliable). |
| Screen blank after flash | Confirm the panel/EPD pins in `config.h` match your unit; the FreeInk X4 Pro profile is mostly hardware-confirmed but a few details are still pending validation. |
| No `NO-LINK` → not connecting | The Pi AP must be up and `BRIDGE_HOST` must match the Pi's AP IP. |