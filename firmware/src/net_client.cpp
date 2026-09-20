#include "net_client.h"
#include "config.h"
#include "proto.h"

void NetClient::begin() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(cfg::WIFI_SSID, cfg::WIFI_PASSWORD);
  WiFi.setSleep(false);
}

void NetClient::update() {
  // --- WiFi ---------------------------------------------------------------
  if (!_wifi_ok()) {
    _connected = false;
    if (_client) _client.stop();
    delay(50);
    return;
  }

  // --- TCP connect / reconnect -------------------------------------------
  if (!_connected) {
    if (_client.connected()) {
      _connected = true;
      _last_ping = millis();
    } else if (millis() - _last_attempt >= cfg::RECONNECT_MS) {
      _last_attempt = millis();
      connect_tcp();
    }
  }

  if (!_connected) return;

  // Keepalive.
  if (millis() - _last_ping >= cfg::PING_INTERVAL_MS) {
    _last_ping = millis();
    JsonDocument doc;
    set_cmd(doc, "ping");
    send(std::move(doc));
  }

  // --- Read inbound frames into the queue ---------------------------------
  // Only enter the blocking read when bytes are actually waiting, and drop +
  // reconnect on any framing error so a corrupt frame can't desync the stream.
  if (_client.connected()) {
    while (_client.available()) {
      JsonDocument doc;
      int r = read_frame(_client, doc, cfg::TCP_TIMEOUT_MS);
      if (r == 1) {
        String s;
        serializeJson(doc, s);
        enqueue_rx(s);
        continue;
      }
      _client.stop();
      _connected = false;
      break;
    }
  } else {
    _connected = false;
  }

  // --- Flush outbound queue ----------------------------------------------
  String out;
  while (_client.connected() && dequeue_tx(out)) {
    _client.print(out);  // raw payload already framed
  }
}

void NetClient::connect_tcp() {
  _tcp_tries++;
  if (!_client.connect(cfg::BRIDGE_HOST, cfg::BRIDGE_PORT)) {
    _tcp_fails++;
    Serial.printf("[net] tcp %s:%u FAILED\n", cfg::BRIDGE_HOST, (unsigned)cfg::BRIDGE_PORT);
    _client.stop();
    return;
  }
  Serial.printf("[net] tcp %s:%u ok\n", cfg::BRIDGE_HOST, (unsigned)cfg::BRIDGE_PORT);
  _connected = true;
  // Announce to the bridge.
  JsonDocument doc;
  set_cmd(doc, "hello");
  doc["version"] = 1;
  send(std::move(doc));
}

bool NetClient::send(JsonDocument&& doc) {
  size_t n = measureJson(doc);
  if (n == 0 || n > MAX_FRAME) return false;
  String s;
  s.reserve(n + 8);
  uint8_t hdr[4];
  hdr[0] = (n >> 24) & 0xFF;
  hdr[1] = (n >> 16) & 0xFF;
  hdr[2] = (n >> 8) & 0xFF;
  hdr[3] = n & 0xFF;
  s.concat((char*)hdr, 4);
  serializeJson(doc, s);
  return enqueue_tx(s);
}

bool NetClient::poll(JsonDocument& out) {
  if (_rx_count == 0) return false;
  String s = _rx[_rx_head];
  _rx_head = (_rx_head + 1) % NC_QUEUE;
  _rx_count--;
  DeserializationError err = deserializeJson(out, s);
  return !err;
}

void NetClient::enqueue_rx(const String& s) {
  if (_rx_count >= NC_QUEUE) return;  // drop oldest? keep simple: drop new
  _rx[_rx_tail] = s;
  _rx_tail = (_rx_tail + 1) % NC_QUEUE;
  _rx_count++;
}

bool NetClient::enqueue_tx(const String& s) {
  if (_tx_count >= TX_QUEUE) return false;
  _tx[_tx_tail] = s;
  _tx_tail = (_tx_tail + 1) % TX_QUEUE;
  _tx_count++;
  return true;
}

bool NetClient::dequeue_tx(String& out) {
  if (_tx_count == 0) return false;
  out = _tx[_tx_head];
  _tx_head = (_tx_head + 1) % TX_QUEUE;
  _tx_count--;
  return true;
}