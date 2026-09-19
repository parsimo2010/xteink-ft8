"""TCP server that the Xteink X4 Pro connects to.

Framing: 4-byte big-endian length + JSON payload (see docs/PROTOCOL.md).
Supports multiple concurrent device connections; each command is dispatched to
a user-supplied handler (a callable `(json_obj) -> dict` returning a response
payload, or None to send nothing). Incoming pushes are broadcast to all
connected devices.
"""

import json
import logging
import socket
import struct
import threading

log = logging.getLogger("device_server")

MAX_FRAME = 16384
BACKLOG = 4


class DeviceServer:
    def __init__(self, host="0.0.0.0", port=4510, handler=None, on_connect=None, on_disconnect=None):
        self.host = host
        self.port = port
        self.handler = handler  # fun(json_obj) -> dict|None
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
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
        log.info("device server listening on %s:%d", self.host, self.port)

    def _accept_loop(self):
        while True:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            t = threading.Thread(target=self._client_loop, args=(conn, addr), daemon=True)
            t.start()

    def _client_loop(self, conn, addr):
        log.info("device connected: %s", addr)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._lock:
            self._clients.add(conn)
        if self.on_connect:
            self.on_connect(addr)
        try:
            while True:
                header = self._recv_exact(conn, 4)
                if not header:
                    break
                (length,) = struct.unpack(">L", header)
                if length <= 0 or length > MAX_FRAME:
                    log.warning("bad frame length %d from %s", length, addr)
                    break
                payload = self._recv_exact(conn, length)
                if payload is None:
                    break
                try:
                    obj = json.loads(payload.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._send(conn, {"type": "error", "message": "invalid json"})
                    continue
                if not isinstance(obj, dict):
                    self._send(conn, {"type": "error", "message": "expected object"})
                    continue
                resp = self.handler(obj) if self.handler else None
                if resp is not None:
                    self._send(conn, resp)
        finally:
            with self._lock:
                self._clients.discard(conn)
            conn.close()
            if self.on_disconnect:
                self.on_disconnect(addr)
            log.info("device disconnected: %s", addr)

    @staticmethod
    def _recv_exact(conn, n):
        chunks = bytearray()
        while len(chunks) < n:
            try:
                data = conn.recv(n - len(chunks))
            except OSError:
                return None
            if not data:
                return None
            chunks += data
        return bytes(chunks)

    def _send(self, conn, obj):
        payload = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        try:
            conn.sendall(struct.pack(">L", len(payload)) + payload)
        except OSError:
            pass

    def broadcast(self, obj):
        payload = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        frame = struct.pack(">L", len(payload)) + payload
        dead = []
        with self._lock:
            clients = list(self._clients)
        for conn in clients:
            try:
                conn.sendall(frame)
            except OSError:
                dead.append(conn)
        if dead:
            with self._lock:
                for conn in dead:
                    self._clients.discard(conn)

    def stop(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass