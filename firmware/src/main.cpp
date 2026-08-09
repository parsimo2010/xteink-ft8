#include <Arduino.h>
#include <BoardConfig.h>
#include <EInkDisplay.h>
#include <InputManager.h>
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
};
StatusInfo g_status = {"", "", "", "FT8", "", false, false};

// Scroll offset into g_rows.
int g_scroll = 0;

// --- UI state ----------------------------------------------------------------
enum class Screen { List, QsoDetail };
Screen g_screen = Screen::List;
uint32_t g_detailId = 0;          // decode id shown in QSO detail
char g_detailCall[11] = "";
char g_detailGrid[5] = "";

bool g_dirty = true;
uint32_t g_lastRefresh = 0;

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

void send_cmd_qsy(int dir) {
  JsonDocument cmd;
  set_cmd(cmd, "qsy");
  // dir: -1 = down a band, +1 = up a band. The bridge maps band names to
  // frequencies; we send the currently shown band hint for a centered move.
  // For simplicity the first prototype sends a fixed band step via freq_hz.
  // (A more complete implementation tracks a band ladder.)
  cmd["band"] = g_status.band;
  net.send(std::move(cmd));
  g_dirty = true;
}

// ===========================================================================
// Input
// ===========================================================================
void on_tap(int xPx, int yPx) {
  uint16_t W = display.getDisplayWidth();
  uint16_t H = display.getDisplayHeight();

  if (g_screen == Screen::QsoDetail) {
    // Back / Halt regions at the bottom.
    if (yPx >= H - cfg::ACTION_H) {
      if (xPx < W / 2) {
        g_screen = Screen::List;
        g_dirty = true;
      } else {
        send_halt();
      }
    }
    return;
  }

  // Action bar.
  if (yPx >= H - cfg::ACTION_H) {
    int n = 5;  // CQ, <<, >>, Refresh, Halt
    int bw = W / n;
    int idx = xPx / bw;
    switch (idx) {
      case 0: send_cq(); break;
      case 1: send_cmd_qsy(-1); break;
      case 2: send_cmd_qsy(1); break;
      case 3: {
        JsonDocument c;
        set_cmd(c, "get_decodes");
        net.send(std::move(c));
        g_dirty = true;
        break;
      }
      case 4: send_halt(); break;
    }
    g_dirty = true;
    return;
  }

  // List area: tap a row to reply.
  int rowFirst = cfg::STATUS_H;
  int rowH = cfg::ROW_H;
  int idx = (yPx - rowFirst) / rowH + g_scroll;
  if (idx >= 0 && idx < g_rowCount) {
    const Decode& d = g_rows[idx];
    send_reply(d);
    g_detailId = d.id;
    strlcpy(g_detailCall, d.call, sizeof(g_detailCall));
    strlcpy(g_detailGrid, d.grid, sizeof(g_detailGrid));
    g_screen = Screen::QsoDetail;
    g_dirty = true;
  }
}

// ===========================================================================
// Rendering
// ===========================================================================
void render_status_bar() {
  char line[64];
  snprintf(line, sizeof(line), "%s%s %s %s %s", g_status.link ? "" : "NO-LINK ",
           g_status.band, g_status.mode, g_status.myCall, g_status.myGrid);
  ui.text(4, (cfg::STATUS_H - 7) / 2, line, true);
  if (g_status.transmitting) {
    ui.text(cfg::STATUS_H + 4 + 400, (cfg::STATUS_H - 7) / 2, "TX", true);
  }
  ui.hline(0, cfg::STATUS_H - 1, display.getDisplayWidth(), true);
}

void render_list() {
  int y = cfg::STATUS_H;
  int rowH = cfg::ROW_H;
  int first = g_scroll;
  int last = first + cfg::VISIBLE_ROWS;
  if (last > g_rowCount) last = g_rowCount;

  for (int i = first; i < last; i++, y += rowH) {
    const Decode& d = g_rows[i];
    char line[64];
    // Call + grid + snr + offset, padded for readability.
    char callPart[12];
    snprintf(callPart, sizeof(callPart), "%-10.10s", d.call);
    char gridPart[5];
    snprintf(gridPart, sizeof(gridPart), "%s", d.grid);
    snprintf(line, sizeof(line), "%s %s %3ddB %5d",
             callPart, gridPart, d.snr, d.dfreq);
    ui.text(6, y + (rowH - 7) / 2, line, true);
    ui.hline(0, y + rowH - 1, display.getDisplayWidth(), false);
  }
  if (g_rowCount == 0) {
    ui.text(6, cfg::STATUS_H + 20, "Waiting for CQ decodes...", true);
  }
}

void render_action_bar() {
  int y = display.getDisplayHeight() - cfg::ACTION_H;
  int n = 5;
  int bw = display.getDisplayWidth() / n;
  const char* labels[5] = {"CQ", "<<", ">>", "RFR", "Halt"};
  for (int i = 0; i < n; i++) {
    int x = i * bw;
    ui.rect(x, y, bw, cfg::ACTION_H, true);
    ui.text(x + (bw - ui.textWidth(labels[i])) / 2, y + (cfg::ACTION_H - 7) / 2, labels[i], true);
  }
}

void render_detail() {
  ui.clear();
  char line[64];
  snprintf(line, sizeof(line), "QSO: %s %s", g_detailCall, g_detailGrid);
  ui.text(6, 20, line, true);

  snprintf(line, sizeof(line), "TX: %s", g_status.txMessage);
  ui.text(6, 40, line, true);

  snprintf(line, sizeof(line), "View: %s %s %s", g_status.band, g_status.mode, g_status.transmitting ? "TX" : "RX");
  ui.text(6, 60, line, true);

  int W = display.getDisplayWidth();
  int H = display.getDisplayHeight();
  int bw = W / 2;
  int y = H - cfg::ACTION_H;
  ui.rect(0, y, bw, cfg::ACTION_H, true);
  ui.text(bw / 2 - ui.textWidth("Back") / 2, y + (cfg::ACTION_H - 7) / 2, "Back", true);
  ui.rect(bw, y, bw, cfg::ACTION_H, true);
  ui.text(bw + bw / 2 - ui.textWidth("Halt") / 2, y + (cfg::ACTION_H - 7) / 2, "Halt", true);
}

void render() {
  uint8_t* fb = display.getFrameBuffer();
  ui.setTarget(fb, display.getDisplayWidth(), display.getDisplayHeight());
  ui.clear();

  if (g_screen == Screen::List) {
    render_status_bar();
    render_list();
    render_action_bar();
  } else {
    render_detail();
  }
  display.displayBuffer(EPD::FAST_REFRESH);
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

  input.begin();
  net.begin();
  g_dirty = true;
}

void loop() {
  input.update();
  net.update();

  // Drain network messages.
  JsonDocument doc;
  while (net.poll(doc)) {
    handle_msg(doc);
  }

  // Input: nav buttons for scrolling.
  if (g_screen == Screen::List) {
    if (input.wasPressed(InputManager::BTN_DOWN)) {
      if (g_scroll + cfg::VISIBLE_ROWS < g_rowCount) { g_scroll++; g_dirty = true; }
    }
    if (input.wasPressed(InputManager::BTN_UP)) {
      if (g_scroll > 0) { g_scroll--; g_dirty = true; }
    }
  }

  // Touch taps.
  float nx, ny;
  if (input.wasTouchTap(nx, ny)) {
    int x = (int)(nx * display.getDisplayWidth());
    int y = (int)(ny * display.getDisplayHeight());
    on_tap(x, y);
  }

  // Debounced repaint.
  if (g_dirty && millis() - g_lastRefresh >= cfg::REDRAW_DEBOUNCE_MS) {
    g_lastRefresh = millis();
    g_dirty = false;
    render();
  }

  delay(10);
}