#include <Arduino.h>
#include <BoardConfig.h>
#include <EInkDisplay.h>
#include <InputManager.h>
#include <PowerManager.h>
#include <XteinkDetect.h>

#include "config.h"
#include "net_client.h"
#include "proto.h"
#include "ui.h"

using EPD = freeink::FreeInkDisplay;

// ---------------------------------------------------------------------------
// Hardware (Xteink X4 Pro)
// ---------------------------------------------------------------------------
EPD display(cfg::EPD_SCLK, cfg::EPD_MOSI, cfg::EPD_CS, cfg::EPD_DC, cfg::EPD_RST, cfg::EPD_BUSY);
InputManager input;
NetClient net;
Ui ui;

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------
struct Decode {
  uint32_t id;
  char call[11];
  char grid[5];
  int snr;
  int32_t dfreq;
  uint32_t time;
};
constexpr int MAX_ROWS = 60;
Decode g_rows[MAX_ROWS];
int g_rowCount = 0;

struct StatusInfo {
  char myCall[11];
  char myGrid[5];
  char band[8];
  char mode[6];
  char txMessage[64];
  bool transmitting;
  bool link;
  bool wifi;
  uint8_t wifiStatus;
  char ip[16];
};
StatusInfo g_status = {"", "", "", "FT8", "", false, false, false, 0, ""};

// Scroll offset into g_rows.
int g_scroll = 0;

// --- Layout metrics (logical space; portrait = transformed by Ui) -----------
int g_lw = 800, g_lh = 480;      // logical screen size
int g_visRows = 16;              // list rows that fit between the bars

inline int contentW() { return g_lw - 2 * cfg::UI_MARGIN; }
inline int contentH() { return g_lh - 2 * cfg::UI_MARGIN; }
inline int rowsTop() { return cfg::UI_MARGIN + cfg::STATUS_H; }
inline int actionBarTop() { return cfg::UI_MARGIN + contentH() - cfg::ACTION_H; }

// --- UI state ----------------------------------------------------------------
enum class Screen { List, QsoDetail };
Screen g_screen = Screen::List;
uint32_t g_detailId = 0;          // decode id shown in QSO detail
char g_detailCall[11] = "";
char g_detailGrid[5] = "";

bool g_dirty = true;
uint32_t g_lastRefresh = 0;
bool g_qsoLogged = false;         // set on qso_logged, shown on the detail screen

// --- Network diagnostic screen (shown until the first bridge link) ---------
bool g_everLinked = false;
bool g_scanValid = false;
bool g_scanSeen = false;
int g_scanRssi = 0;
int g_scanNets = -1;
uint32_t g_lastScanMs = 0;

// --- Tap visual feedback: one control drawn inverted for a moment ------------
uint32_t g_flashUntil = 0;
int g_fx = 0, g_fy = 0, g_fw = 0, g_fh = 0;
char g_flashLabel[12] = "";
Screen g_flashScreen = Screen::List;   // overlay only draws on its source screen

// ---------------------------------------------------------------------------
// Forward decls
// ---------------------------------------------------------------------------
void render();
void handle_msg(const JsonDocument& doc);
void on_tap(int xPx, int yPx);
void send_reply(const Decode& d);
void send_cmd_qsy(int dir);
void send_halt();
void send_cq();
void maybe_enter_sleep();
void flash_control(int x, int y, int w, int h, const char* label);
void render_sleep();
void render_net_diag();

// ===========================================================================
// Tap feedback
// ===========================================================================
void flash_control(int x, int y, int w, int h, const char* label) {
  g_fx = x;
  g_fy = y;
  g_fw = w;
  g_fh = h;
  strlcpy(g_flashLabel, label, sizeof(g_flashLabel));
  g_flashScreen = g_screen;
  g_flashUntil = millis() + cfg::TAP_FLASH_MS;
  g_dirty = true;
}

// ===========================================================================
// Networking message handling
// ===========================================================================
void handle_msg(const JsonDocument& doc) {
  const char* type = doc["type"] | "";
  if (strcmp(type, "decode") == 0) {
    uint32_t id = doc["id"] | 0;
    // De-dup / replace by id.
    for (int i = 0; i < g_rowCount; i++) {
      if (g_rows[i].id == id) {
        // update existing
        g_rows[i].snr = doc["snr"] | 0;
        strlcpy(g_rows[i].call, doc["call"] | "", sizeof(g_rows[i].call));
        strlcpy(g_rows[i].grid, doc["grid"] | "", sizeof(g_rows[i].grid));
        g_dirty = true;
        return;
      }
    }
    if (g_rowCount < MAX_ROWS) {
      Decode& d = g_rows[g_rowCount++];
      d.id = id;
      d.snr = doc["snr"] | 0;
      d.dfreq = doc["delta_freq"] | 0;
      d.time = doc["time"] | 0;
      strlcpy(d.call, doc["call"] | "", sizeof(d.call));
      strlcpy(d.grid, doc["grid"] | "", sizeof(d.grid));
      // keep list sorted by snr desc (best first) using insertion.
      for (int i = g_rowCount - 1; i > 0 && g_rows[i].snr > g_rows[i - 1].snr; i--) {
        Decode t = g_rows[i];
        g_rows[i] = g_rows[i - 1];
        g_rows[i - 1] = t;
      }
      g_dirty = true;
    }
  } else if (strcmp(type, "clear_decodes") == 0) {
    g_rowCount = 0;
    g_scroll = 0;
    g_dirty = true;
  } else if (strcmp(type, "decodes") == 0) {
    // Snapshot from the bridge (on hello / get_decodes).
    g_rowCount = 0;
    g_scroll = 0;
    JsonArrayConst arr = doc["decodes"].as<JsonArrayConst>();
    for (JsonObjectConst o : arr) {
      if (g_rowCount >= MAX_ROWS) break;
      Decode& d = g_rows[g_rowCount++];
      d.id = o["id"] | 0;
      d.snr = o["snr"] | 0;
      d.dfreq = o["delta_freq"] | 0;
      d.time = o["time"] | 0;
      strlcpy(d.call, o["call"] | "", sizeof(d.call));
      strlcpy(d.grid, o["grid"] | "", sizeof(d.grid));
    }
    g_dirty = true;
  } else if (strcmp(type, "status") == 0) {
    strlcpy(g_status.myCall, doc["de_call"] | "", sizeof(g_status.myCall));
    strlcpy(g_status.myGrid, doc["de_grid"] | "", sizeof(g_status.myGrid));
    strlcpy(g_status.mode, doc["mode"] | "FT8", sizeof(g_status.mode));
    strlcpy(g_status.txMessage, doc["tx_message"] | "", sizeof(g_status.txMessage));
    g_status.transmitting = doc["transmitting"] | false;
    const char* b = doc["band"] | "";
    if (b[0]) strlcpy(g_status.band, b, sizeof(g_status.band));
    g_dirty = true;
  } else if (strcmp(type, "qso_logged") == 0) {
    // Drop the worked station from the list and flag the detail screen.
    const char* dx = doc["dx_call"] | "";
    if (dx[0]) {
      for (int i = 0; i < g_rowCount; i++) {
        if (strcmp(g_rows[i].call, dx) == 0) {
          for (int j = i; j < g_rowCount - 1; j++) g_rows[j] = g_rows[j + 1];
          g_rowCount--;
          if (g_scroll > 0 && g_scroll + g_visRows > g_rowCount) g_scroll--;
          break;
        }
      }
    }
    g_qsoLogged = true;
    g_dirty = true;
  } else if (strcmp(type, "hello") == 0) {
    g_status.link = doc["ok"] | false;
    strlcpy(g_status.myCall, doc["my_call"] | "", sizeof(g_status.myCall));
    strlcpy(g_status.myGrid, doc["my_grid"] | "", sizeof(g_status.myGrid));
    strlcpy(g_status.band, doc["band"] | "", sizeof(g_status.band));
    g_dirty = true;
    // The hello carries a snapshot; ingest it.
    JsonArrayConst arr = doc["decodes"]["decodes"].as<JsonArrayConst>();
    g_rowCount = 0;
    g_scroll = 0;
    for (JsonObjectConst o : arr) {
      if (g_rowCount >= MAX_ROWS) break;
      Decode& d = g_rows[g_rowCount++];
      d.id = o["id"] | 0;
      d.snr = o["snr"] | 0;
      d.dfreq = o["delta_freq"] | 0;
      d.time = o["time"] | 0;
      strlcpy(d.call, o["call"] | "", sizeof(d.call));
      strlcpy(d.grid, o["grid"] | "", sizeof(d.grid));
    }
  } else if (strcmp(type, "no_such_decode") == 0) {
    g_screen = Screen::List;
    g_dirty = true;
  }
}

// ===========================================================================
// Commands to the bridge
// ===========================================================================
void send_reply(const Decode& d) {
  JsonDocument cmd;
  set_cmd(cmd, "reply");
  cmd["decode_id"] = (uint32_t)d.id;
  net.send(std::move(cmd));
  g_qsoLogged = false;
}

void send_cq() {
  JsonDocument cmd;
  set_cmd(cmd, "send_cq");
  char msg[40];
  // Use the callsign/grid from WSJT-X (via the bridge) as the single source of
  // truth; fall back to the config constants only until a Status/hello lands.
  const char* call = g_status.myCall[0] ? g_status.myCall : cfg::MY_CALL;
  const char* grid = g_status.myGrid[0] ? g_status.myGrid : cfg::MY_GRID;
  snprintf(msg, sizeof(msg), "CQ %s %s", call, grid);
  cmd["text"] = msg;
  net.send(std::move(cmd));
}

void send_halt() {
  JsonDocument cmd;
  set_cmd(cmd, "halt_tx");
  cmd["auto_only"] = false;
  net.send(std::move(cmd));
}

// Band ladder for the << / >> buttons (must match rigctl.BAND_CENTERS on the
// bridge, which maps these names to frequencies).
static const char* const BAND_LADDER[] = {
    "160m", "80m", "60m", "40m", "30m", "20m",
    "17m", "15m", "12m", "10m", "6m",
};
static constexpr int BAND_LADDER_N = sizeof(BAND_LADDER) / sizeof(BAND_LADDER[0]);

void send_cmd_qsy(int dir) {
  JsonDocument cmd;
  set_cmd(cmd, "qsy");
  int idx = -1;
  for (int i = 0; i < BAND_LADDER_N; i++) {
    if (strcmp(g_status.band, BAND_LADDER[i]) == 0) { idx = i; break; }
  }
  if (idx < 0) {
    // No/unknown band yet (e.g. no hello received): start at 20m, the usual
    // FT8 watering hole, regardless of direction.
    cmd["band"] = "20m";
  } else {
    int n = idx + dir;
    if (n < 0) n = 0;
    if (n >= BAND_LADDER_N) n = BAND_LADDER_N - 1;
    cmd["band"] = BAND_LADDER[n];
  }
  net.send(std::move(cmd));
  g_dirty = true;
}

// ===========================================================================
// Input
// ===========================================================================
void on_tap(int xPx, int yPx) {
  if (g_screen == Screen::QsoDetail) {
    // Back / Halt regions at the bottom.
    if (yPx >= actionBarTop()) {
      int dx = xPx - cfg::UI_MARGIN;
      if (dx >= 0 && dx < contentW()) {
        int bw = contentW() / 2;
        bool back = dx < contentW() / 2;
        flash_control(cfg::UI_MARGIN + (back ? 0 : bw), actionBarTop(), bw, cfg::ACTION_H,
                      back ? "Back" : "Halt");
        if (back) {
          g_screen = Screen::List;
        } else {
          send_halt();
        }
      }
    }
    return;
  }

  // Action bar.
  if (yPx >= actionBarTop()) {
    int dx = xPx - cfg::UI_MARGIN;
    if (dx < 0 || dx >= contentW()) return;
    int n = 5;  // CQ, <<, >>, Refresh, Halt
    const char* labels[5] = {"CQ", "<<", ">>", "RFR", "Halt"};
    int bw = contentW() / n;
    int idx = dx / bw;
    if (idx >= n) idx = n - 1;
    flash_control(cfg::UI_MARGIN + idx * bw, actionBarTop(), bw, cfg::ACTION_H, labels[idx]);
    switch (idx) {
      case 0: send_cq(); break;
      case 1: send_cmd_qsy(-1); break;
      case 2: send_cmd_qsy(1); break;
      case 3: {
        JsonDocument c;
        set_cmd(c, "get_decodes");
        net.send(std::move(c));
        break;
      }
      case 4: send_halt(); break;
    }
    g_dirty = true;
    return;
  }

  // List area: tap a row to reply. Taps on the status bar do nothing.
  if (yPx >= rowsTop() && yPx < actionBarTop()) {
    int idx = (yPx - rowsTop()) / cfg::ROW_H + g_scroll;
    if (idx >= 0 && idx < g_rowCount && idx < g_scroll + g_visRows) {
      const Decode& d = g_rows[idx];
      send_reply(d);
      g_detailId = d.id;
      strlcpy(g_detailCall, d.call, sizeof(g_detailCall));
      strlcpy(g_detailGrid, d.grid, sizeof(g_detailGrid));
      g_screen = Screen::QsoDetail;
      g_dirty = true;
    }
  }
}

// ===========================================================================
// Power: hold the power button -> panel + chip deep sleep.
// The e-ink image persists without power; any power-button press wakes the
// device with a cold boot.
// ===========================================================================
void maybe_enter_sleep() {
  static bool powerSeenReleased = false;
  if (!input.isPressed(InputManager::BTN_POWER)) {
    powerSeenReleased = true;
    return;
  }
  if (!powerSeenReleased) return;  // ignore a hold that powered the unit on
  if (input.getPowerButtonHeldTime() < cfg::POWER_HOLD_SLEEP_MS) return;

  render_sleep();
  Serial.flush();
  display.deepSleep();
  freeink::PowerManager::powerDownRailsForSleep();
  freeink::PowerManager::deepSleepUntilPowerButton();  // noreturn
}

// ===========================================================================
// Rendering
// ===========================================================================
void render_status_bar() {
  char line[64];
  char netTag[32];
  if (g_status.link) {
    netTag[0] = '\0';
  } else if (g_status.wifi) {
    // On the AP but no bridge TCP: show our IP so DHCP/join is provable.
    snprintf(netTag, sizeof(netTag), "%s NO-LINK ",
             g_status.ip[0] ? g_status.ip : "WIFI");
  } else {
    snprintf(netTag, sizeof(netTag), "%s",
             g_status.wifiStatus == WL_NO_SSID_AVAIL ? "NO-SSID " : "NO-WIFI ");
  }
  snprintf(line, sizeof(line), "%s%s %s %s %s", netTag,
           g_status.band, g_status.mode, g_status.myCall, g_status.myGrid);
  int ty = cfg::UI_MARGIN + (cfg::STATUS_H - Ui::GLYPH_H) / 2;
  ui.text(cfg::UI_MARGIN + 4, ty, line, true);
  if (g_status.transmitting) {
    ui.text(cfg::UI_MARGIN + contentW() - 4 - ui.textWidth("TX"), ty, "TX", true);
  }
  ui.hline(cfg::UI_MARGIN, cfg::UI_MARGIN + cfg::STATUS_H - 1, contentW(), true);
}

void render_list() {
  int y = rowsTop();
  int rowH = cfg::ROW_H;
  int first = g_scroll;
  int last = first + g_visRows;
  if (last > g_rowCount) last = g_rowCount;

  for (int i = first; i < last; i++, y += rowH) {
    const Decode& d = g_rows[i];
    char line[64];
    // Call + grid + snr + offset, padded for readability.
    char callPart[12];
    snprintf(callPart, sizeof(callPart), "%-10.10s", d.call);
    snprintf(line, sizeof(line), "%s %s %3ddB %5d",
             callPart, d.grid, d.snr, d.dfreq);
    ui.text(cfg::UI_MARGIN + 6, y + (rowH - Ui::GLYPH_H) / 2, line, true);
    ui.hline(cfg::UI_MARGIN, y + rowH - 1, contentW(), false);
  }
  if (g_rowCount == 0) {
    ui.text(cfg::UI_MARGIN + 6, rowsTop() + 20, "Waiting for CQ decodes...", true);
  }
}

void render_action_bar() {
  int y = actionBarTop();
  int n = 5;
  int bw = contentW() / n;
  const char* labels[5] = {"CQ", "<<", ">>", "RFR", "Halt"};
  for (int i = 0; i < n; i++) {
    int x = cfg::UI_MARGIN + i * bw;
    ui.rect(x, y, bw, cfg::ACTION_H, true);
    ui.text(x + (bw - ui.textWidth(labels[i])) / 2, y + (cfg::ACTION_H - Ui::GLYPH_H) / 2, labels[i], true);
  }
}

void render_detail() {
  ui.clear();
  char line[64];
  int x = cfg::UI_MARGIN + 6;
  snprintf(line, sizeof(line), "QSO: %s %s", g_detailCall, g_detailGrid);
  ui.text(x, cfg::UI_MARGIN + 24, line, true);

  snprintf(line, sizeof(line), "TX: %.40s", g_status.txMessage);
  ui.text(x, cfg::UI_MARGIN + 52, line, true);

  snprintf(line, sizeof(line), "View: %s %s %s", g_status.band, g_status.mode, g_status.transmitting ? "TX" : "RX");
  ui.text(x, cfg::UI_MARGIN + 80, line, true);

  if (g_qsoLogged) {
    ui.text(x, cfg::UI_MARGIN + 108, "QSO LOGGED", true);
  }

  int y = actionBarTop();
  int bw = contentW() / 2;
  ui.rect(cfg::UI_MARGIN, y, bw, cfg::ACTION_H, true);
  ui.text(cfg::UI_MARGIN + bw / 2 - ui.textWidth("Back") / 2, y + (cfg::ACTION_H - Ui::GLYPH_H) / 2, "Back", true);
  ui.rect(cfg::UI_MARGIN + bw, y, bw, cfg::ACTION_H, true);
  ui.text(cfg::UI_MARGIN + bw + bw / 2 - ui.textWidth("Halt") / 2, y + (cfg::ACTION_H - Ui::GLYPH_H) / 2, "Halt", true);
}

const char* wifi_status_text(uint8_t s) {
  switch (s) {
    case WL_IDLE_STATUS: return "IDLE";
    case WL_NO_SSID_AVAIL: return "NO-SSID";
    case WL_SCAN_COMPLETED: return "SCAN-DONE";
    case WL_CONNECTED: return "CONNECTED";
    case WL_CONNECT_FAILED: return "AUTH-FAIL";
    case WL_CONNECTION_LOST: return "LOST";
    default: return "DISCONNECTED";
  }
}

const char* wifi_err_text(uint8_t r) {
  switch (r) {
    case 0: return "none yet";
    case 2: return "AUTH_EXPIRE";
    case 3: return "AUTH_LEAVE";
    case 4: return "ASSOC_EXPIRE";
    case 5: return "ASSOC_TOOMANY";
    case 8: return "ASSOC_LEAVE";
    case 15: return "4WAY_TIMEOUT";
    case 200: return "BEACON_TIMEOUT";
    case 201: return "NO_AP_FOUND";
    case 202: return "AUTH_FAIL";
    case 203: return "ASSOC_FAIL";
    case 204: return "HANDSHAKE_TIMEOUT";
    default: return "other";
  }
}

void render_net_diag() {
  const int x = cfg::UI_MARGIN + 6;
  int y = cfg::UI_MARGIN + 10;
  char b[88];
  ui.textLarge(x, y, "NET DIAGNOSTIC", true);
  y += Ui::LARGE_H + 16;
  snprintf(b, sizeof(b), "SSID  %s", cfg::WIFI_SSID);
  ui.text(x, y, b, true); y += 22;
  snprintf(b, sizeof(b), "WIFI  %u %s", g_status.wifiStatus, wifi_status_text(g_status.wifiStatus));
  ui.text(x, y, b, true); y += 22;
  snprintf(b, sizeof(b), "LINK  %lu assoc, last drop %u %s",
           (unsigned long)net.assoc_count(), net.last_disconnect_reason(),
           wifi_err_text(net.last_disconnect_reason()));
  ui.text(x, y, b, true); y += 22;
  if (!g_scanValid) {
    ui.text(x, y, "SCAN  scanning...", true);
  } else if (g_scanSeen) {
    snprintf(b, sizeof(b), "SCAN  sees %s %ddBm (%d nets)", cfg::WIFI_SSID, g_scanRssi, g_scanNets);
    ui.text(x, y, b, true);
  } else {
    snprintf(b, sizeof(b), "SCAN  %s NOT seen (%d nets)", cfg::WIFI_SSID, g_scanNets);
    ui.text(x, y, b, true);
  }
  y += 22;
  if (g_status.wifi) {
    snprintf(b, sizeof(b), "IP    %s", g_status.ip[0] ? g_status.ip : "...");
    ui.text(x, y, b, true); y += 22;
  }
  snprintf(b, sizeof(b), "TCP   %s:%u", cfg::BRIDGE_HOST, (unsigned)cfg::BRIDGE_PORT);
  ui.text(x, y, b, true); y += 22;
  snprintf(b, sizeof(b), "      %lu tries %lu failed",
           (unsigned long)net.tcp_tries(), (unsigned long)net.tcp_fails());
  ui.text(x, y, b, true); y += 30;
  ui.hline(cfg::UI_MARGIN, y, contentW(), true); y += 16;
  ui.text(x, y, "auto-switches to decodes on first link", true);
}

void render() {
  uint8_t* fb = display.getFrameBuffer();
  ui.setTarget(fb, g_lw, g_lh, display.getDisplayWidth(), display.getDisplayHeight(), cfg::UI_ROTATION);
  ui.clear();

  if (!g_everLinked) {
    render_net_diag();
  } else if (g_screen == Screen::List) {
    render_status_bar();
    render_list();
    render_action_bar();
  } else {
    render_detail();
  }

  // Momentary inverted overlay on the tapped control (works with no link).
  if (g_flashScreen == g_screen && g_flashUntil && (int32_t)(millis() - g_flashUntil) < 0) {
    ui.fill(g_fx, g_fy, g_fw, g_fh, true);
    uint16_t tw = ui.textWidth(g_flashLabel);
    ui.text(g_fx + (g_fw - (int)tw) / 2, g_fy + (g_fh - Ui::GLYPH_H) / 2, g_flashLabel, false);
  }
  display.displayBuffer(EPD::FAST_REFRESH);
}

void render_sleep() {
  uint8_t* fb = display.getFrameBuffer();
  ui.setTarget(fb, g_lw, g_lh, display.getDisplayWidth(), display.getDisplayHeight(), cfg::UI_ROTATION);
  ui.clear();
  const char* big = "SLEEPING";
  int by = g_lh / 2 - Ui::LARGE_H / 2;
  ui.textLarge((g_lw - (int)ui.textLargeWidth(big)) / 2, by, big, true);
  const char* sub = "Press power to wake";
  ui.text((g_lw - (int)ui.textWidth(sub)) / 2, by + Ui::LARGE_H + 16, sub, true);
  g_flashUntil = 0;
  display.displayBuffer(EPD::FULL_REFRESH);
}

// ===========================================================================
// Arduino entry points
// ===========================================================================
void setup() {
  delay(250);
  Serial.begin(115200);
  delay(50);

  BoardConfig::holdPowerRails();
  freeink::applyXteinkDisplayController();

  display.begin();
  display.clearScreen();
  display.displayBuffer(EPD::FULL_REFRESH);  // initial full refresh

  const bool portrait = cfg::UI_ROTATION != 0;
  g_lw = portrait ? (int)display.getDisplayHeight() : (int)display.getDisplayWidth();
  g_lh = portrait ? (int)display.getDisplayWidth() : (int)display.getDisplayHeight();
  g_visRows = (contentH() - cfg::STATUS_H - cfg::ACTION_H) / cfg::ROW_H;

  input.begin();
  net.begin();
  Serial.printf("[net] joining SSID '%s', bridge %s:%u\n",
                cfg::WIFI_SSID, cfg::BRIDGE_HOST, (unsigned)cfg::BRIDGE_PORT);
  g_dirty = true;
}

void maybe_enter_sleep();

void loop() {
  input.update();
  net.update();
  maybe_enter_sleep();

  // Link indicator follows the TCP state (cleared on drop, set on reconnect).
  if (g_status.link != net.connected()) {
    g_status.link = net.connected();
    Serial.printf("[net] bridge link %s\n", g_status.link ? "UP" : "DOWN");
    if (g_status.link) g_everLinked = true;
    g_dirty = true;
  }

  // WiFi indicator: distinguishes "not on the AP" (NO-WIFI) from "on the AP
  // but the bridge TCP link is down" (shows our IP + NO-LINK).
  const bool wifiNow = net.wifi_connected();
  if (g_status.wifi != wifiNow) {
    g_status.wifi = wifiNow;
    g_dirty = true;
  }
  const uint8_t wsNow = net.wifi_status();
  if (g_status.wifiStatus != wsNow) {
    Serial.printf("[net] wifi status %u -> %u\n", g_status.wifiStatus, wsNow);
    g_status.wifiStatus = wsNow;
    g_dirty = true;
  }
  static uint32_t shownAssoc = 0;
  static uint8_t shownErr = 0;
  if (net.assoc_count() != shownAssoc || net.last_disconnect_reason() != shownErr) {
    shownAssoc = net.assoc_count();
    shownErr = net.last_disconnect_reason();
    g_dirty = true;
  }
  if (wifiNow) {
    String ip = net.wifi_ip();
    if (ip.length() < sizeof(g_status.ip) && strcmp(ip.c_str(), g_status.ip) != 0) {
      strlcpy(g_status.ip, ip.c_str(), sizeof(g_status.ip));
      Serial.printf("[net] wifi ip %s\n", g_status.ip);
      g_dirty = true;
    }
  } else if (g_status.ip[0] != '\0') {
    g_status.ip[0] = '\0';
    g_dirty = true;
  }

  // While still unlinked: scan for the target AP every 15 s so the on-screen
  // diagnostic can distinguish "radio sees nothing" from "sees it, can't join".
  if (!g_everLinked && (!g_scanValid || (int32_t)(millis() - g_lastScanMs) >= 15000)) {
    g_lastScanMs = millis();
    int n = net.scan_networks();
    g_scanNets = n;
    g_scanSeen = false;
    g_scanRssi = 0;
    for (int i = 0; i < n; i++) {
      if (net.scan_ssid(i) == cfg::WIFI_SSID) {
        g_scanSeen = true;
        g_scanRssi = net.scan_rssi(i);
        break;
      }
    }
    net.scan_delete();
    g_scanValid = true;
    g_dirty = true;
  }

  // Drain network messages.
  JsonDocument doc;
  while (net.poll(doc)) {
    handle_msg(doc);
  }

  // Input: nav buttons for scrolling.
  if (g_screen == Screen::List) {
    if (input.wasPressed(InputManager::BTN_DOWN)) {
      if (g_scroll + g_visRows < g_rowCount) { g_scroll++; g_dirty = true; }
    }
    if (input.wasPressed(InputManager::BTN_UP)) {
      if (g_scroll > 0) { g_scroll--; g_dirty = true; }
    }
  }

  // Touch taps: the SDK reports normalized coords in the panel-native
  // landscape frame; undo the UI rotation to get logical coords.
  float nx, ny;
  if (input.wasTouchTap(nx, ny) && g_everLinked) {
    int lx = 0, ly = 0;
    if (cfg::UI_ROTATION == 1) {           // portrait, panel 90 deg CW
      lx = (int)((1.0f - ny) * (g_lw - 1));
      ly = (int)(nx * (g_lh - 1));
    } else if (cfg::UI_ROTATION == 2) {    // portrait, inverted
      lx = (int)(ny * (g_lw - 1));
      ly = (int)((1.0f - nx) * (g_lh - 1));
    } else {
      lx = (int)(nx * (g_lw - 1));
      ly = (int)(ny * (g_lh - 1));
    }
    on_tap(lx, ly);
  }

  // Debounced repaint (also redraws to clear an expired tap flash).
  bool flashActive = g_flashUntil && (int32_t)(millis() - g_flashUntil) < 0;
  static bool flashWasActive = false;
  if (flashWasActive && !flashActive) {
    g_flashUntil = 0;   // arm a fresh window on the next tap; no stale sentinel
    g_dirty = true;
  }
  flashWasActive = flashActive;
  if (g_dirty && millis() - g_lastRefresh >= cfg::REDRAW_DEBOUNCE_MS) {
    g_lastRefresh = millis();
    g_dirty = false;
    render();
  }

  delay(10);
}
