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

  // Inbound queue (JSON strings, compact).
  String _rx[NC_QUEUE];
  int _rx_head = 0, _rx_tail = 0, _rx_count = 0;
  // Outbound queue.
  String _tx[TX_QUEUE];
  int _tx_head = 0, _tx_tail = 0, _tx_count = 0;

  void enqueue_rx(const String& s);
  bool enqueue_tx(const String& s);
  bool dequeue_tx(String& out);

  // Reading state for a partial frame.
  uint8_t _hdr[4];
  size_t _hdr_got = 0;
  uint32_t _frame_len = 0;
  String _frame_buf;
  uint32_t _read_start = 0;
};