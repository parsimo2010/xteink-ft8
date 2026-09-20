#pragma once
// WiFi client + framed TCP connection to the bridge, with automatic reconnect.
// Polled from the main loop via update(). Received messages are queued and
// drained by the app with poll().
#include <ArduinoJson.h>
#include <WiFi.h>
#include <cstdint>

constexpr int NC_QUEUE = 16;      // max queued inbound messages
constexpr int TX_QUEUE = 8;       // max queued outbound commands

class NetClient {
 public:
  void begin();
  // Drive WiFi + TCP state and read inbound frames. Call frequently.
  void update();
  // True when the TCP link to the bridge is up.
  bool connected() const { return _connected; }
  // True when associated to the WiFi AP (independent of the TCP link).
  bool wifi_connected() const { return _wifi_ok(); }
  // Raw WiFi.status() (WL_* codes) for diagnostics.
  uint8_t wifi_status() const { return (uint8_t)WiFi.status(); }
  // Blocking WiFi scan (diagnostics screen). Returns network count.
  int scan_networks() { return WiFi.scanNetworks(); }
  String scan_ssid(int i) const { return WiFi.SSID(i); }
  int scan_rssi(int i) const { return WiFi.RSSI(i); }
  void scan_delete() { WiFi.scanDelete(); }
  // TCP connect counters (diagnostics screen).
  uint32_t tcp_tries() const { return _tcp_tries; }
  uint32_t tcp_fails() const { return _tcp_fails; }
  // Association counters (diagnostics screen): how many times we (re)associated
  // and the ESP32 reason code of the most recent disconnect.
  uint32_t assoc_count() const { return _assoc_ok; }
  uint8_t last_disconnect_reason() const { return _last_err; }
  // Station IP as dotted text (empty until associated).
  String wifi_ip() const { return _wifi_ok() ? WiFi.localIP().toString() : String(); }
  // Stage a command object to send. Returns false if the TX queue is full.
  bool send(JsonDocument&& doc);
  // Pop the next received message into `out`. Returns true if one was dequeued.
  bool poll(JsonDocument& out);

 private:
  void connect_tcp();
  bool _wifi_ok() const { return WiFi.status() == WL_CONNECTED; }

  WiFiClient _client;
  bool _connected = false;
  uint32_t _last_attempt = 0;
  uint32_t _last_ping = 0;
  uint32_t _tcp_tries = 0;
  uint32_t _tcp_fails = 0;
  uint32_t _assoc_ok = 0;
  uint8_t _last_err = 0;

  // Inbound queue (JSON strings, compact).
  String _rx[NC_QUEUE];
  int _rx_head = 0, _rx_tail = 0, _rx_count = 0;
  // Outbound queue.
  String _tx[TX_QUEUE];
  int _tx_head = 0, _tx_tail = 0, _tx_count = 0;

  void enqueue_rx(const String& s);
  bool enqueue_tx(const String& s);
  bool dequeue_tx(String& out);
};