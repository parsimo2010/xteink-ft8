#pragma once

// ---------------------------------------------------------------------------
// xteink-ft8 X4 Pro firmware configuration.
//
// EDIT THESE for your field deployment:
//   WIFI_SSID / WIFI_PASSWORD  -> the Pi's ad-hoc AP credentials
//   BRIDGE_HOST / BRIDGE_PORT  -> the bridge TCP server (Pi AP IP)
//   MY_CALL / MY_GRID          -> your station identity (used for the CQ text)
// ---------------------------------------------------------------------------

namespace cfg {

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

// --- Xteink X4 Pro display pins (BoardConfig::XTEINK_X4_PRO) -----------------
// SSD1677 SPI: SCLK=12 MOSI=11 CS=13 DC=18 RST=14 BUSY=6 (hardware-confirmed).
inline constexpr int EPD_SCLK = 12;
inline constexpr int EPD_MOSI = 11;
inline constexpr int EPD_CS = 13;
inline constexpr int EPD_DC = 18;
inline constexpr int EPD_RST = 14;
inline constexpr int EPD_BUSY = 6;

// --- UI tuning ----------------------------------------------------------------
inline constexpr int MAX_DECODES = 60;        // rows we keep locally
inline constexpr int VISIBLE_ROWS = 16;        // rows on screen at once
inline constexpr uint16_t ROW_H = 24;          // px per list row
inline constexpr uint16_t STATUS_H = 24;       // top status bar height
inline constexpr uint16_t ACTION_H = 34;       // bottom action bar height
inline constexpr uint32_t REDRAW_DEBOUNCE_MS = 250;  // min time between e-ink refreshes

// --- Networking ---------------------------------------------------------------
inline constexpr uint32_t RECONNECT_MS = 5000;      // retry delay if link drops
inline constexpr uint32_t PING_INTERVAL_MS = 20000; // keepalive to bridge

}  // namespace cfg