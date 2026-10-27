#include "proto.h"
#include <WiFi.h>

// One reusable receive scratch buffer instead of a per-frame allocation. There is
// exactly one reader (NetClient, driven from loop()), so a static is safe -- and
// allocating/freeing up to 16 KB per inbound frame is how ESP32 heap
// fragmentation eventually makes reads fail and decodes silently stop.
static uint8_t g_rx_scratch[MAX_FRAME];

bool write_all(WiFiClient& client, const uint8_t* buf, size_t len, uint32_t timeout_ms) {
  size_t done = 0;
  uint32_t start = millis();
  while (done < len) {
    const int w = client.write(buf + done, len - done);
    if (w > 0) {
      done += (size_t)w;
      start = millis();  // progress resets the deadline
      continue;
    }
    if ((int32_t)(millis() - start) > (int32_t)timeout_ms) return false;
    delay(1);
  }
  return true;
}

// Read exactly n bytes, chunk-wise, tolerating a socket that dribbles.
// Returns the byte count read (< n on timeout/EOF).
static size_t read_exact(WiFiClient& client, uint8_t* dst, size_t n, uint32_t timeout_ms) {
  size_t got = 0;
  uint32_t start = millis();
  while (got < n) {
    const int avail = client.available();
    if (avail > 0) {
      const size_t want = ((size_t)avail < (n - got)) ? (size_t)avail : (n - got);
      const int r = client.read(dst + got, want);
      if (r <= 0) break;
      got += (size_t)r;
      start = millis();
      continue;
    }
    if ((int32_t)(millis() - start) > (int32_t)timeout_ms) break;
    delay(1);
  }
  return got;
}

int read_frame(WiFiClient& client, JsonDocument& doc, uint32_t timeout_ms) {
  uint8_t hdr[4];
  if (read_exact(client, hdr, 4, timeout_ms) != 4) return 0;

  const uint32_t n = ((uint32_t)hdr[0] << 24) | ((uint32_t)hdr[1] << 16) |
                     ((uint32_t)hdr[2] << 8) | (uint32_t)hdr[3];
  if (n == 0 || n > MAX_FRAME) return -1;  // framing error: caller must drop the socket

  if (read_exact(client, g_rx_scratch, n, timeout_ms) != n) return -1;

  const DeserializationError err = deserializeJson(doc, g_rx_scratch, (size_t)n);
  return err ? -1 : 1;
}

void set_cmd(JsonDocument& doc, const char* cmd) {
  doc["cmd"] = cmd;
}
