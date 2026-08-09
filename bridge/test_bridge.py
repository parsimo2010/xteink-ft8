#!/usr/bin/env python3
"""End-to-end test for the bridge using real sockets (no hardware needed).

Simulates:
  * WSJT-X sending Heartbeat / Status / Decode over UDP to the bridge rx port.
  * A device connecting over TCP, receiving decodes, and issuing a `reply`.

Run:  python3 test_bridge.py
"""

import socket
import struct
import threading
import time

import qso_tracker
import wsjtx_udp
import xteink_bridge

RX_PORT = 23238
CTRL_PORT = 23237
DEV_PORT = 24510

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("PASS  %s" % name)
    else:
        FAIL.append(name)
        print("FAIL  %s  %s" % (name, detail))


def build_heartbeat():
    return wsjtx_udp._pack_header(wsjtx_udp.HEARTBEAT) + struct.pack(">L", 3) + wsjtx_udp._pack_string("WSJT-X") + wsjtx_udp._pack_string("2.6.0")


def build_status():
    fields = {
        "dial_frequency": 14074000,
        "mode": "FT8",
        "dx_call": "",
        "report": "",
        "tx_mode": "CQ",
        "tx_enabled": True,
        "transmitting": False,
        "decoding": True,
        "rx_df": 1500,
        "tx_df": 1500,
        "de_call": "W9XYZ",
        "de_grid": "EM48",
        "dx_grid": "",
        "tx_watchdog": False,
        "sub_mode": "NA",
        "fast_mode": False,
        "special_operation_mode": 0,
        "frequency_tolerance": 0xFFFFFFFF,
        "tr_period": 15,
        "configuration_name": "Default",
        "tx_message": "CQ W9XYZ EM48",
    }
    def s(v):
        return wsjtx_udp._pack_string(v)
    payload = (
        struct.pack(">Q", fields["dial_frequency"])
        + s(fields["mode"]) + s(fields["dx_call"]) + s(fields["report"]) + s(fields["tx_mode"])
        + struct.pack(">?", fields["tx_enabled"]) + struct.pack(">?", fields["transmitting"]) + struct.pack(">?", fields["decoding"])
        + struct.pack(">L", fields["rx_df"]) + struct.pack(">L", fields["tx_df"])
        + s(fields["de_call"]) + s(fields["de_grid"]) + s(fields["dx_grid"])
        + struct.pack(">?", fields["tx_watchdog"]) + s(fields["sub_mode"])
        + struct.pack(">?", fields["fast_mode"]) + struct.pack(">B", fields["special_operation_mode"])
        + struct.pack(">L", fields["frequency_tolerance"]) + struct.pack(">L", fields["tr_period"])
        + s(fields["configuration_name"]) + s(fields["tx_message"])
    )
    return wsjtx_udp._pack_header(wsjtx_udp.STATUS) + payload


def build_decode(msg, snr=-8, df=800, new=1):
    def s(v):
        return wsjtx_udp._pack_string(v)
    payload = (
        struct.pack(">?", new)
        + struct.pack(">L", 43800)
        + struct.pack(">l", snr)
        + struct.pack(">d", 0.4)
        + struct.pack(">L", df)
        + s("FT8") + s(msg)
        + struct.pack(">?", False) + struct.pack(">?", False)
    )
    return wsjtx_udp._pack_header(wsjtx_udp.DECODE) + payload


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        d = conn.recv(n - len(buf))
        if not d:
            return None
        buf += d
    return buf


def recv_frame(conn):
    hdr = recv_exact(conn, 4)
    if not hdr:
        return None
    (length,) = struct.unpack(">L", hdr)
    payload = recv_exact(conn, length)
    import json
    return json.loads(payload.decode("utf-8"))


def main():
    args = xteink_bridge.parse_args([
        "--rx-port", str(RX_PORT),
        "--ctrl-port", str(CTRL_PORT),
        "--port", str(DEV_PORT),
    ])
    bridge = xteink_bridge.Bridge(args)
    bridge.server.start()
    rx = threading.Thread(target=bridge._udp_loop, daemon=True)
    rx.start()
    time.sleep(0.3)

    # --- simulate WSJT-X ---------------------------------------------------
    wsjtx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    wsjtx_addr = ("127.0.0.1", RX_PORT)

    wsjtx.sendto(build_status(), wsjtx_addr)
    time.sleep(0.05)
    wsjtx.sendto(build_decode("CQ K1ABC FN20", snr=-8, df=800), wsjtx_addr)
    time.sleep(0.05)
    wsjtx.sendto(build_decode("CQ VE3DEF", snr=-15, df=1600), wsjtx_addr)
    time.sleep(0.05)
    wsjtx.sendto(build_decode("K1ABC W9XYZ -12", snr=-12, df=900), wsjtx_addr)  # not a CQ
    time.sleep(0.3)

    # tracker sanity
    cq = bridge.tracker.cq_list(time.time())
    check("tracker keeps only CQ decodes", len(cq) == 2, "got %d" % len(cq))
    check("CQ call parsed", cq[0].call == "K1ABC" and cq[0].grid == "FN20")
    check("status captured", bridge.status["de_call"] == "W9XYZ")

    # --- simulate device ---------------------------------------------------
    dev = socket.create_connection(("127.0.0.1", DEV_PORT), timeout=3)
    import json
    dev.sendall(struct.pack(">L", len(json.dumps({"cmd": "hello"}))) + json.dumps({"cmd": "hello"}).encode())
    hello = recv_frame(dev)
    check("hello ok", hello.get("ok") is True and hello.get("my_call") == "W9XYZ")
    check("hello carries decodes", len(hello.get("decodes", {}).get("decodes", [])) == 2)

    # push a new CQ and confirm the device receives it
    wsjtx.sendto(build_decode("CQ 9M2AX OI88", snr=-20, df=2400), wsjtx_addr)
    pushed = recv_frame(dev)
    check("device receives pushed decode", pushed.get("type") == "decode" and pushed.get("call") == "9M2AX")

    # reply command -> expect a Reply packet on the ctrl port
    ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ctrl.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ctrl.bind(("127.0.0.1", CTRL_PORT))
    ctrl.settimeout(3)
    target_id = hello["decodes"]["decodes"][0]["id"]
    dev.sendall(struct.pack(">L", len(json.dumps({"cmd": "reply", "decode_id": target_id}))) + json.dumps({"cmd": "reply", "decode_id": target_id}).encode())
    resp = recv_frame(dev)
    check("reply response ok", resp.get("type") == "ok_dispatch")
    data, _ = ctrl.recvfrom(65535)
    msg_type, _cid, payload = wsjtx_udp.parse_message(data)
    check("bridge sent a Reply packet to WSJT-X", msg_type == wsjtx_udp.REPLY, "got type %d" % msg_type)
    check("Reply carries the CQ message", payload["message"].startswith("CQ "))

    # qsy without rig -> not_supported
    dev.sendall(struct.pack(">L", len(json.dumps({"cmd": "qsy", "band": "20m"}))) + json.dumps({"cmd": "qsy", "band": "20m"}).encode())
    qsy = recv_frame(dev)
    check("qsy without rigctld -> not_supported", qsy.get("type") == "not_supported")

    print("\n==== %d passed, %d failed ====" % (len(PASS), len(FAIL)))
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()