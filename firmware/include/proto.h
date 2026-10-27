#pragma once
// Length-framed JSON protocol between the X4 Pro and the bridge.
// See docs/PROTOCOL.md. Framing: [u32 BE length][UTF-8 JSON].
#include <ArduinoJson.h>
#include <WiFiClient.h>
#include <cstdint>

// Maximum frame payload (bytes), matching the bridge's cap.
inline constexpr uint32_t MAX_FRAME = 16384;

// Write every byte of buf, retrying short writes, or fail after timeout_ms.
// The single rule that keeps a framed stream readable on the other end.
bool write_all(WiFiClient& client, const uint8_t* buf, size_t len, uint32_t timeout_ms);

// Block (with a timeout) reading one framed message into `doc`.
// Returns 1 on success, 0 on clean EOF, -1 on timeout/error.
int read_frame(WiFiClient& client, JsonDocument& doc, uint32_t timeout_ms);

// Small string helpers for building messages.
void set_cmd(JsonDocument& doc, const char* cmd);