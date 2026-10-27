#pragma once

// ---------------------------------------------------------------------------
// xteink-ft8 firmware configuration.
//
// One source tree, two e-ink targets:
//   * env:x4pro  -> Xteink X4 Pro        (-DFREEINK_DEVICE_X4PRO=1)
//   * env:sticky -> Seeed reTerminal Sticky (-DFREEINK_DEVICE_STICKY=1)
// Both are ESP32-S3 + SSD1677 800x480 + GT911 touch, but their pinouts,
// button set, console wiring and panel mounting differ; everything that
// changes between them is isolated in this file.
//
// EDIT THESE for your field deployment:
//   WIFI_SSID / WIFI_PASSWORD  -> the Pi's ad-hoc AP credentials
//   BRIDGE_HOST / BRIDGE_PORT  -> the bridge TCP server (Pi AP IP)
//   MY_CALL / MY_GRID          -> your station identity (used for the CQ text)
// ---------------------------------------------------------------------------

#include <BoardConfig.h>

// A build env must pick exactly one device. Without this, forgetting the
// -DFREEINK_DEVICE_<NAME> flag silently compiles the X4 Pro pinout onto whatever
// board you are holding - which on the Sticky means an unlit panel and a mystery.
// NOTE: test the VALUES, not definedness: BoardConfig.h defines every
// FREEINK_DEVICE_* (to 0 unless the command line says otherwise).
#if FREEINK_DEVICE_X4PRO && FREEINK_DEVICE_STICKY
#error "Both FREEINK_DEVICE_X4PRO and FREEINK_DEVICE_STICKY are enabled; pick one"
#endif
#if !FREEINK_DEVICE_X4PRO && !FREEINK_DEVICE_STICKY
#error "No device selected: build with -DFREEINK_DEVICE_X4PRO=1 or -DFREEINK_DEVICE_STICKY=1 (see the platformio.ini envs)"
#endif

namespace cfg {

// Firmware build identity, passed in by platformio.ini (-DXTEINK_FW_VERSION=...).
// Kept as a string so it can ride in the hello frame and on the diagnostic screen.
#ifdef XTEINK_FW_VERSION
#define XTEINK_VERSION_STR XTEINK_FW_VERSION
#else
#define XTEINK_VERSION_STR "unknown"
#endif
inline constexpr const char* FW_VERSION = XTEINK_VERSION_STR;

// --- WiFi (Pi ad-hoc access point) -----------------------------------------
inline constexpr const char* WIFI_SSID = "XTEINK-FT8";
inline constexpr const char* WIFI_PASSWORD = "ft8field";
inline constexpr uint32_t WIFI_TIMEOUT_MS = 15000;

// --- Bridge TCP server (the Raspberry Pi) -----------------------------------
inline constexpr const char* BRIDGE_HOST = "192.168.4.1";
inline constexpr uint16_t BRIDGE_PORT = 4510;
inline constexpr uint32_t TCP_TIMEOUT_MS = 10000;

// --- Your station -----------------------------------------------------------
inline constexpr const char* MY_CALL = "W9XYZ";
inline constexpr const char* MY_GRID = "EM48";

// --- Console serial ---------------------------------------------------------
// The X4 Pro exposes its console on native USB CDC. The Sticky's USB-C is a
// WCH CH343 bridge wired to UART0 (GPIO43/44), so the SDK routes its console
// to Serial0 there; BoardConfig::serialTransport() picks the right one per
// device and every log line in the app goes through this.
inline auto& serial() { return BoardConfig::serialTransport(); }

// --- Device identity / panel pins -------------------------------------------
// The FreeInk display driver takes its pins from the active BoardProfile
// (BoardConfig::ACTIVE), NOT from the values below -- these document the
// hardware and feed the FreeInkDisplay constructor for compatibility only.
#if FREEINK_DEVICE_STICKY
// Seeed reTerminal Sticky (BoardConfig::STICKY): SSD1677 SPI SCLK=13 MOSI=14
// CS=15 DC=16 RST=17 BUSY=18 + panel power-enable 47. GT911 touch on its own
// I2C bus (SDA=3 SCL=2 INT=21 RST=41 TOUCH_EN=42), BQ27220 gauge on the sensor
// bus (SDA=1 SCL=0, Wire1), buttons UP=5 DOWN=6 and a shared AI/OK/PWR on 4.
inline constexpr const char* DEVICE_NAME = "sticky";
inline constexpr int EPD_SCLK = 13;
inline constexpr int EPD_MOSI = 14;
inline constexpr int EPD_CS = 15;
inline constexpr int EPD_DC = 16;
inline constexpr int EPD_RST = 17;
inline constexpr int EPD_BUSY = 18;
#else
// Xteink X4 Pro (BoardConfig::XTEINK_X4_PRO): SSD1677 SPI SCLK=12 MOSI=11
// CS=13 DC=18 RST=14 BUSY=6 (hardware-confirmed). GT911 touch on the shared
// bus SDA=39 SCL=38 INT=10 RST=4, CW2017 gauge at 0x63 on the same bus,
// buttons UP=0 DOWN=7 POWER=3, master rail enable GPIO1.
inline constexpr const char* DEVICE_NAME = "x4pro";
inline constexpr int EPD_SCLK = 12;
inline constexpr int EPD_MOSI = 11;
inline constexpr int EPD_CS = 13;
inline constexpr int EPD_DC = 18;
inline constexpr int EPD_RST = 14;
inline constexpr int EPD_BUSY = 6;
#endif

// --- Physical orientation -----------------------------------------------------
// The SSD1677 panel is landscape-native (800x480); any other view is a
// software transform of the framebuffer in the Ui renderer (the panel
// controller cannot express it).
//   UI_ROTATION 0 = landscape, panel native
//               1 = portrait, 90 deg clockwise
//               2 = portrait, 90 deg counter-clockwise
//               3 = landscape, 180 deg (panel mounted upside down)
// The X4 Pro is held portrait (validated on hardware). The Sticky is a
// landscape card whose glass is mounted 180 deg from the controller's native
// scan -- Seeed's own display layer applies that same 180 deg rotation, so the
// Sticky default is 3. Override without editing this file by passing
// -DXTEINK_UI_ROTATION=<0..3> in the build env if a unit mounts differently.
#ifdef XTEINK_UI_ROTATION
inline constexpr int UI_ROTATION = XTEINK_UI_ROTATION;
#elif FREEINK_DEVICE_STICKY
inline constexpr int UI_ROTATION = 3;
#else
inline constexpr int UI_ROTATION = 1;
#endif

// True when the logical UI is taller than it is wide (rotation 1 or 2).
inline constexpr bool UI_PORTRAIT = UI_ROTATION == 1 || UI_ROTATION == 2;

// Bezel-safe margin around the whole UI, in logical pixels.
inline constexpr uint16_t UI_MARGIN = 5;

// --- Power button ---------------------------------------------------------------
// Hold the power button this long to enter deep sleep. The panel keeps the
// last image without power; any press of the power button wakes the device
// with a cold boot.
//   X4 Pro: dedicated power key (GPIO3).
//   Sticky: the AI/OK key (GPIO4) is shared. The SDK reports it as BTN_CONFIRM
//     on a click and as BTN_POWER once it has been held past
//     InputManager's 400 ms confirm-hold window, so this value must stay
//     comfortably above that (a short tap never reaches the sleep path).
inline constexpr uint32_t POWER_HOLD_SLEEP_MS = 1500;

// How long a tapped control stays drawn inverted (visual tap feedback).
inline constexpr uint32_t TAP_FLASH_MS = 550;

// --- UI tuning ----------------------------------------------------------------
inline constexpr int MAX_DECODES = 60;        // rows we keep locally
inline constexpr uint16_t ROW_H = 24;         // px per list row
inline constexpr uint16_t STATUS_H = 24;      // top status bar height
inline constexpr uint16_t ACTION_H = 34;      // bottom action bar height
inline constexpr uint32_t REDRAW_DEBOUNCE_MS = 250;  // min time between e-ink refreshes

// --- Networking ---------------------------------------------------------------
inline constexpr uint32_t RECONNECT_MS = 5000;      // retry delay if link drops
inline constexpr uint32_t PING_INTERVAL_MS = 20000; // keepalive to bridge

}  // namespace cfg
