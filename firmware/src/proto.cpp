#include "proto.h"
#include <WiFi.h>

bool send_frame(WiFiClient& client, const JsonDocument& doc) {
  size_t n = measureJson(doc);
  if (n == 0 || n > MAX_FRAME) return false;
  uint8_t hdr[4];
  hdr[0] = (n >> 24) & 0xFF;
  hdr[1] = (n >> 16) & 0xFF;
  hdr[2] = (n >> 8) & 0xFF;
  hdr[3] = n & 0xFF;
  if (client.write(hdr, 4) != 4) return false;
  // Stream the JSON directly to the socket.
  return serializeJson(doc, client) == n;
}

int read_frame(WiFiClient& client, JsonDocument& doc, uint32_t timeout_ms) {
  uint8_t hdr[4];
  size_t got = 0;
  uint32_t start = millis();
  while (got < 4) {
    if (client.available()) {
      hdr[got++] = (uint8_t)client.read();
      start = millis();  // reset on any byte
    } else if (millis() - start > timeout_ms) {
      return (got == 0) ? 0 : -1;
    } else {
      delay(1);
    }
  }
  uint32_t n = ((uint32_t)hdr[0] << 24) | ((uint32_t)hdr[1] << 16) | ((uint32_t)hdr[2] << 8) | hdr[3];
  if (n == 0 || n > MAX_FRAME) return -1;

  // Read payload into a buffer, then deserialize.
  uint8_t* buf = new (std::nothrow) uint8_t[n];
  if (!buf) return -1;
  got = 0;
  start = millis();
  while (got < n) {
    if (client.available()) {
      int b = client.read();
      if (b < 0) break;
      buf[got++] = (uint8_t)b;
      start = millis();
    } else if (millis() - start > timeout_ms) {
      break;
    } else {
      delay(1);
    }
  }
  DeserializationError err = DeserializationError::Ok;
  if (got == n) {
    err = deserializeJson(doc, buf, n);
  }
  delete[] buf;
  if (got != n) return (got == 0) ? 0 : -1;
  if (err) return -1;
  return 1;
}

void set_cmd(JsonDocument& doc, const char* cmd) {
  doc["cmd"] = cmd;
}