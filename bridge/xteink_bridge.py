#!/usr/bin/env python3
"""xteink-ft8 bridge: relay WSJT-X FT8 data to an Xteink X4 Pro.

Runs on the Raspberry Pi next to WSJT-X. Receives WSJT-X UDP messages, keeps
the latest FT8 CQ decodes, and pushes them to the X4 Pro over a TCP link. Acts
on device commands by sending WSJT-X control messages back.

Ports (see docs/SETUP.md):
  * --rx-host/--rx-port   where WSJT-X SENDS outgoing messages (default 2238)
  * --ctrl-host/--ctrl-port  where WSJT-X LISTENS for control messages
                            (default 127.0.0.1:2237, "Accept UDP requests")
  * --listen/--port       TCP server for the X4 Pro (default 0.0.0.0:4510)
"""

import argparse
import logging
import socket
import struct
import threading
import time

import device_server
import qso_tracker
import rigctl
import wsjtx_udp

log = logging.getLogger("bridge")

STATUS_EMPTY = {
    "dial_frequency": 0,
    "mode": "",
    "dx_call": "",
    "report": "",
    "tx_mode": "",
    "tx_enabled": False,
    "transmitting": False,
    "decoding": False,
    "de_call": "",
    "de_grid": "",
    "dx_grid": "",
    "tx_message": "",
    "sub_mode": "",
    "special_operation_mode": 0,
    "tr_period": 0,
}


class Bridge:
    def __init__(self, args):
        self.args = args
        self.tracker = qso_tracker.QsoTracker()
        self.status = dict(STATUS_EMPTY)
        self.rig = rigctl.RigCtl(args.rig_host, args.rig_port) if args.rig_host else None

        self.server = device_server.DeviceServer(
            host=args.listen,
            port=args.port,
            handler=self.handle_command,
            on_connect=self.on_device_connect,
        )

        self._ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._ctrl_addr = (args.ctrl_host, args.ctrl_port)

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        self.server.start()
        rx = threading.Thread(target=self._udp_loop, name="wsjtx-rx", daemon=True)
        rx.start()
        log.info(
            "bridge ready: rx=%s:%d ctrl=%s:%d device=%s:%d on=%s/%s",
            self.args.rx_host,
            self.args.rx_port,
            self.args.ctrl_host,
            self.args.ctrl_port,
            self.args.listen,
            self.args.port,
            self.status["de_call"] or "?",
            self.status["de_grid"] or "?",
        )
        # Keep the main thread alive.
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            log.info("shutting down")
            self.server.stop()

    # -- WSJT-X receive ------------------------------------------------------
    def _udp_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.args.rx_host, self.args.rx_port))
        self._rx_sock = sock
        log.info("UDP rx bound on %s:%d", self.args.rx_host, self.args.rx_port)
        while True:
            data, addr = sock.recvfrom(65535)
            try:
                self._on_wsjtx_datagram(data, addr)
            except Exception:  # noqa: BLE001 - never die on a bad datagram
                log.exception("error handling WSJT-X datagram")

    def _on_wsjtx_datagram(self, data, addr):
        msg_type, client_id, payload = wsjtx_udp.parse_message(data)

        if msg_type == wsjtx_udp.HEARTBEAT:
            # Answer with our own Heartbeat so WSJT-X negotiates this client
            # up to schema 3 (until then it streams schema-2 messages whose
            # float/QDateTime encoding we cannot parse).
            self._rx_sock.sendto(wsjtx_udp.build_heartbeat("xteink"), addr)
            log.info(
                "heartbeat from WSJT-X %s (%s) max_schema=%d; replied schema %d",
                payload.get("version"),
                payload.get("revision"),
                payload.get("max_schema"),
                wsjtx_udp.SCHEMA,
            )
            return

        if msg_type == wsjtx_udp.STATUS:
            self.status = payload
            self._push_status()
            return

        if msg_type == wsjtx_udp.DECODE:
            now = time.time()
            d = self.tracker.add(payload, now)
            if d and d.is_cq:
                self.server.broadcast({"type": "decode", **d.as_dict()})
            return

        if msg_type == wsjtx_udp.CLEAR:
            self.tracker.clear()
            self.server.broadcast({"type": "clear_decodes"})
            return

        if msg_type == wsjtx_udp.QSO_LOGGED:
            self.server.broadcast({"type": "qso_logged", **payload})
            return

        # Other types (Replay, WSPR, etc.) are ignored.

    # -- device command dispatch --------------------------------------------
    def handle_command(self, obj):
        cmd = obj.get("cmd")
        log.debug("device cmd: %s", cmd)
        m = {
            "hello": self._cmd_hello,
            "get_status": self._cmd_get_status,
            "get_decodes": self._cmd_get_decodes,
            "reply": self._cmd_reply,
            "send_cq": self._cmd_send_cq,
            "send_freetext": self._cmd_send_freetext,
            "halt_tx": self._cmd_halt_tx,
            "clear": self._cmd_clear,
            "qsy": self._cmd_qsy,
            "decodes_ack": self._cmd_decodes_ack,
            "ping": lambda _o: {"type": "pong"},
        }
        fn = m.get(cmd)
        if fn is None:
            return {"type": "error", "message": "unknown command: %s" % cmd}
        return fn(obj)

    def _cmd_hello(self, obj):
        return {
            "type": "hello",
            "ok": True,
            "version": 1,
            "my_call": self.status["de_call"],
            "my_grid": self.status["de_grid"],
            "mode": self.status["mode"],
            "band": self._band(self.status["dial_frequency"]),
            "status": self.status,
            "decodes": self.tracker.snapshot(time.time()),
        }

    def _cmd_get_status(self, _obj):
        return self._status_frame()

    def _status_frame(self):
        return {
            "type": "status",
            "band": self._band(self.status.get("dial_frequency", 0)),
            **self.status,
        }

    def _cmd_get_decodes(self, _obj):
        return {"type": "decodes", **self.tracker.snapshot(time.time())}

    def _cmd_reply(self, obj):
        did = obj.get("decode_id")
        d = self.tracker.get(did)
        if d is None:
            return {"type": "no_such_decode", "decode_id": did}
        packet = wsjtx_udp.build_reply("xteink", _decode_to_dict(d))
        self._send_ctrl(packet)
        log.info("reply to %s (%s) @ %d Hz", d.call, d.grid, d.delta_freq)
        return {"type": "ok_dispatch", "decode_id": did}

    def _cmd_send_cq(self, obj):
        text = obj.get("text") or ""
        if not text:
            text = "CQ %s %s" % (self.status["de_call"], self.status["de_grid"])
            text = text.strip()
        packet = wsjtx_udp.build_freetext("xteink", text, True)
        self._send_ctrl(packet)
        log.info("free text TX: %s", text)
        return {"type": "ok_dispatch", "text": text}

    def _cmd_send_freetext(self, obj):
        packet = wsjtx_udp.build_freetext("xteink", obj.get("text") or "", bool(obj.get("send", False)))
        self._send_ctrl(packet)
        return {"type": "ok_dispatch"}

    def _cmd_halt_tx(self, obj):
        packet = wsjtx_udp.build_halt_tx("xteink", bool(obj.get("auto_only", False)))
        self._send_ctrl(packet)
        return {"type": "ok_dispatch"}

    def _cmd_clear(self, obj):
        packet = wsjtx_udp.build_clear("xteink", int(obj.get("window", 0)))
        self._send_ctrl(packet)
        return {"type": "ok_dispatch"}

    def _cmd_qsy(self, obj):
        if self.rig is None:
            return {"type": "not_supported", "cmd": "qsy"}
        band = obj.get("band")
        freq = obj.get("freq_hz")
        if not freq and band:
            freq = rigctl.RigCtl.band_to_freq(band)
        if not freq:
            return {"type": "error", "message": "missing band or freq_hz"}
        ok, detail = self.rig.set_frequency(int(freq))
        if not ok:
            return {"type": "not_supported", "cmd": "qsy", "detail": detail}
        log.info("qsy to %d Hz", int(freq))
        return {"type": "ok_dispatch", "freq_hz": int(freq)}

    def _cmd_decodes_ack(self, obj):
        self.tracker.ack(obj.get("seq"))
        return None

    # -- helpers ------------------------------------------------------------
    def _send_ctrl(self, packet):
        try:
            self._ctrl_sock.sendto(packet, self._ctrl_addr)
        except OSError as e:
            log.error("failed to send control to %s: %s", self._ctrl_addr, e)

    def _push_status(self):
        self.server.broadcast(self._status_frame())

    def on_device_connect(self, addr):
        log.info("device link opened: %s", addr)

    @staticmethod
    def _band(freq_hz):
        if not freq_hz:
            return ""
        mhz = freq_hz / 1e6
        for band_center, name in sorted(((v, k) for k, v in rigctl.BAND_CENTERS.items()), reverse=True):
            if mhz >= (band_center / 1e6) - 2 and mhz <= (band_center / 1e6) + 3:
                return name
        return "%.1fM" % mhz


def _decode_to_dict(d):
    return {
        "time": d.time,
        "snr": d.snr,
        "delta_time": d.delta_time,
        "delta_freq": d.delta_freq,
        "mode": d.mode,
        "message": d.message,
        "low_confidence": d.low_confidence,
    }


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="xteink-ft8 bridge")
    p.add_argument("--rx-host", default="127.0.0.1", help="WSJT-X sends *to* here (default 127.0.0.1)")
    p.add_argument("--rx-port", type=int, default=2238, help="WSJT-X outgoing UDP port (default 2238)")
    p.add_argument("--ctrl-host", default="127.0.0.1", help="WSJT-X 'Accept UDP requests' host (default 127.0.0.1)")
    p.add_argument("--ctrl-port", type=int, default=2237, help="WSJT-X control listen port (default 2237)")
    p.add_argument("--listen", default="0.0.0.0", help="device server bind address (default 0.0.0.0)")
    p.add_argument("--port", type=int, default=4510, help="device server port (default 4510)")
    p.add_argument("--rig-host", default="127.0.0.1", help="rigctld host for band changes (default 127.0.0.1; empty string disables)")
    p.add_argument("--rig-port", type=int, default=4532, help="rigctld port (default 4532)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return p.parse_args(argv)


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    Bridge(args).start()


if __name__ == "__main__":
    main()