"""TCP server that the e-ink device connects to.

Framing: 4-byte big-endian length + JSON payload (see docs/PROTOCOL.md).
Supports multiple concurrent device connections; each command is dispatched to
a user-supplied handler (a callable `(json_obj) -> dict` returning a response
payload, or None to send nothing). Server-initiated pushes go to
`broadcast()`.

One writer per connection
-------------------------
Every connection owns a bounded outbound queue and exactly ONE writer thread,
and both the command responses and `broadcast()` only ever *enqueue*. That buys
two properties the previous implementation did not have:

* `broadcast()` can never block the caller. Before, a device that stopped
  reading (deep sleep, powered off, half-open TCP) made `sendall()` block the
  caller forever - and the caller was the single WSJT-X receive thread, so the
  whole station went deaf while systemd still reported the service healthy.
  Now a stalled device costs it a queue of dropped stale frames and nobody else
  anything.
* Frame bytes can never interleave: one writer per socket, always.

Readers use `select()` with an idle deadline, so a peer that vanished without a
FIN is reaped (the firmware pings every 20 s; see docs/PROTOCOL.md) instead of
parking a thread and a socket forever.
"""

import json
import logging
import queue
import select
import socket
import struct
import threading
import time

log = logging.getLogger("device_server")

MAX_FRAME = 16384
BACKLOG = 4
SEND_TIMEOUT = 5.0          # max block on a single socket write/read syscall
RECV_IDLE_TIMEOUT = 120.0   # reap a silent peer (device ping interval is 20 s)
MAX_CLIENTS = 4             # one field station needs one device, not four
OUT_QUEUE_DEPTH = 32        # frames buffered per device before the oldest is dropped


def _encode(obj):
    payload = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_FRAME:
        raise ValueError("refusing to send %d byte frame (max %d)" % (len(payload), MAX_FRAME))
    return struct.pack(">L", len(payload)) + payload


class Client:
    """One device connection: its socket, its bounded out queue, its writer thread."""

    def __init__(self, server, conn, addr):
        self.server = server
        self.conn = conn
        self.addr = addr
        self.last_seen = time.monotonic()
        self.dropped = 0
        self._out = queue.Queue(maxsize=OUT_QUEUE_DEPTH)
        self._closed = threading.Event()
        self._writer = threading.Thread(target=self._write_loop,
                                        name="device-tx-%s" % _port(addr), daemon=True)

    # -- outbound ----------------------------------------------------------
    def start_writer(self):
        self._writer.start()

    def post(self, obj):
        """Queue one frame for this device. Never blocks.

        When the device cannot keep up, the OLDEST queued frame is dropped: for
        a live decode feed the newest event is the useful one, and the device
        re-syncs with `get_decodes` on its own.
        """
        if self._closed.is_set():
            return False
        try:
            self._out.put_nowait(obj)
            return True
        except queue.Full:
            pass
        try:
            self._out.get_nowait()
        except queue.Empty:
            pass
        else:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                log.warning("%s is not reading: dropped %d stale frames", self.addr, self.dropped)
        try:
            self._out.put_nowait(obj)
        except queue.Full:
            self.dropped += 1
            return False
        return True

    def _write_loop(self):
        while not self._closed.is_set():
            try:
                obj = self._out.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                frame = _encode(obj)
            except (TypeError, ValueError) as e:
                log.error("cannot encode frame for %s: %s", self.addr, e)
                continue
            try:
                self.conn.sendall(frame)          # the only writer on this socket
            except OSError as e:
                log.info("%s is not writable (%s); closing link", self.addr, e)
                self.close()
                return

    # -- inbound -----------------------------------------------------------
    def read_loop(self):
        try:
            while not self._closed.is_set():
                try:
                    ready, _, _ = select.select([self.conn], [], [], RECV_IDLE_TIMEOUT)
                except (OSError, ValueError):
                    break                       # socket closed underneath us
                if not ready:
                    log.warning("%s silent for %.0fs (no ping?); reaping link",
                                self.addr, RECV_IDLE_TIMEOUT)
                    break
                header = self._recv_exact(4)
                if header is None:
                    break
                (length,) = struct.unpack(">L", header)
                if length <= 0 or length > MAX_FRAME:
                    log.warning("bad frame length %d from %s", length, self.addr)
                    break
                payload = self._recv_exact(length)
                if payload is None:
                    break
                self.last_seen = time.monotonic()
                try:
                    obj = json.loads(payload.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self.post({"type": "error", "message": "invalid json"})
                    continue
                if not isinstance(obj, dict):
                    self.post({"type": "error", "message": "expected object"})
                    continue
                try:
                    resp = self.server.handler(obj) if self.server.handler else None
                except Exception:  # noqa: BLE001 - one bad command must not kill the link
                    log.exception("handler failed for %r", obj.get("cmd"))
                    self.post({"type": "error", "message": "handler failed"})
                    continue
                if resp is not None:
                    self.post(resp)
        finally:
            self.close()

    def _recv_exact(self, n):
        chunks = bytearray()
        while len(chunks) < n:
            try:
                data = self.conn.recv(n - len(chunks))
            except OSError:
                return None
            if not data:
                return None
            chunks += data
        return bytes(chunks)

    # -- teardown ----------------------------------------------------------
    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        self.server._remove(self)
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.conn.close()
        except OSError:
            pass
        log.info("device disconnected: %s", self.addr)
        if self.server.on_disconnect:
            try:
                self.server.on_disconnect(self.addr)
            except Exception:  # noqa: BLE001
                log.exception("on_disconnect hook failed")

    def info(self):
        return {"addr": list(self.addr), "queued": self._out.qsize(),
                "dropped": self.dropped, "idle": round(time.monotonic() - self.last_seen, 1)}


def _port(addr):
    try:
        return addr[1]
    except (TypeError, IndexError):
        return 0


class DeviceServer:
    def __init__(self, host="0.0.0.0", port=4510, handler=None, on_connect=None,
                 on_disconnect=None, max_clients=MAX_CLIENTS):
        self.host = host
        self.port = port
        self.handler = handler          # fun(json_obj) -> dict|None
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.max_clients = max_clients
        self._clients = set()
        self._lock = threading.Lock()
        self._sock = None
        self._thread = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(BACKLOG)
        self._thread = threading.Thread(target=self._accept_loop, name="device-server", daemon=True)
        self._thread.start()
        log.info("device server listening on %s:%d (max %d devices)",
                 self.host, self.port, self.max_clients)

    def _accept_loop(self):
        while True:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break                 # listening socket closed by stop()
            try:
                self._add_client(conn, addr)
            except Exception as e:  # noqa: BLE001 - one bad client must not kill accept
                log.exception("failed to adopt connection from %s", addr)
                try:
                    conn.close()
                except OSError:
                    pass

    def _add_client(self, conn, addr):
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.settimeout(SEND_TIMEOUT)
        client = Client(self, conn, addr)
        evicted = None
        with self._lock:
            if len(self._clients) >= self.max_clients:
                evicted = min(self._clients, key=lambda c: c.last_seen)
                # A device is single-purpose here: prefer the newest connection and
                # evict the least recently active one rather than rejecting the field.
                self._clients.add(client)
            else:
                self._clients.add(client)
        if evicted is not None:
            log.warning("device limit (%d) reached: evicting least recently active %s",
                        self.max_clients, evicted.addr)
            evicted.close()
        log.info("device connected: %s", addr)
        if self.on_connect:
            try:
                self.on_connect(addr)
            except Exception:  # noqa: BLE001
                log.exception("on_connect hook failed")
        client.start_writer()
        threading.Thread(target=client.read_loop,
                         name="device-rx-%s" % _port(addr), daemon=True).start()

    def _remove(self, client):
        with self._lock:
            self._clients.discard(client)

    def broadcast(self, obj):
        """Queue `obj` to every connected device. Never blocks the caller."""
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            client.post(obj)

    def stats(self):
        with self._lock:
            clients = list(self._clients)
        return [c.info() for c in clients]

    def stop(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            client.close()
