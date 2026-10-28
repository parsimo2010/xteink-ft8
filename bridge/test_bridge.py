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
import rigctl
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


def build_heartbeat_schema2():
    """What a real WSJT-X sends first: schema 2 until the client negotiates."""
    hdr = struct.pack(">LLL", wsjtx_udp.MAGIC, 2, wsjtx_udp.HEARTBEAT)
    hdr += wsjtx_udp._pack_string("WSJT-X")
    return hdr + struct.pack(">L", 3) + wsjtx_udp._pack_string("WSJT-X") + wsjtx_udp._pack_string("3.2.0")


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


def build_qso_logged(timespec=1):
    """QSOLogged with a variable-length QDateTime (13 bytes unless spec==2)."""
    def s(v):
        return wsjtx_udp._pack_string(v)
    dt = struct.pack(">qLB", 2460000, 43800000, timespec) + (struct.pack(">l", 0) if timespec == 2 else b"")
    payload = (
        dt
        + s("K1ABC") + s("FN20") + struct.pack(">Q", 14074000) + s("FT8")
        + s("-12") + s("-15") + s("10") + s("") + s("")
        + dt
        + s("") + s("W9XYZ") + s("EM48") + s("") + s("") + s("")
    )
    return wsjtx_udp._pack_header(wsjtx_udp.QSO_LOGGED) + payload


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


def send_cmd(conn, obj):
    import json
    body = json.dumps(obj).encode("utf-8")
    conn.sendall(struct.pack(">L", len(body)) + body)


def classify_cases():
    """FT8 CQ classification (issue 4): the call we report must be the transmitter."""
    callable_cases = [
        ("CQ K1ABC FN20", "K1ABC", "FN20"),
        ("CQ VE3DEF", "VE3DEF", ""),
        ("CQ 9M2AX OI88", "9M2AX", "OI88"),
        ("CQ DX K1ABC FN20", "K1ABC", "FN20"),        # the common DX CQ
        ("CQ POTA K1ABC FN20", "K1ABC", "FN20"),
        ("CQ SOTA K1ABC FN20", "K1ABC", "FN20"),
        ("CQ WW K1ABC FN20", "K1ABC", "FN20"),
        ("CQ TEST K1ABC FN20", "K1ABC", "FN20"),
        ("CQ NA-012 K1ABC FN20", "K1ABC", "FN20"),    # reference between CQ and call
        ("CQ DE K1ABC FN20", "K1ABC", "FN20"),
        ("CQ CQ K1ABC FN20", "K1ABC", "FN20"),
        ("CQ W1AW K1ABC FN20", "K1ABC", "FN20"),      # directed CQ: answer the sender
        ("CQ K1ABC/P FN20", "K1ABC", "FN20"),         # portable suffix stripped
        ("QRZ W9XYZ", "W9XYZ", ""),
        ("QRZ K1ABC FN20", "K1ABC", "FN20"),
        ("cq dx k1abc fn20", "K1ABC", "FN20"),        # case insensitive
    ]
    not_callable = [
        "CQ DX",                    # no station in it at all
        "CQ",
        "QRZ",
        "K1ABC W9XYZ -12",          # ordinary exchange
        "CQ FN20 FN20",             # no callsign
        "73 de K1ABC", "", None,
    ]
    for msg, want_call, want_grid in callable_cases:
        is_cq, call, grid = qso_tracker.classify(msg)
        check("classify callable: %r" % msg,
              is_cq and call == want_call and grid == want_grid,
              "got %r %r %r" % (is_cq, call, grid))
    for msg in not_callable:
        is_cq, call, grid = qso_tracker.classify(msg)
        check("classify rejected: %r" % msg, not is_cq, "got %r %r" % (call, grid))


def tracker_survives_concurrent_ack():
    """Issue 2: add() on one thread must not lose rows to ack() on another.

    Preemption is forced to the tightest possible interval so the read-modify-write
    window in ack()/_prune() is actually hit; without the tracker lock this loses
    rows that were already pushed to the device (which then get no_such_decode).
    """
    import sys
    original = sys.getswitchinterval()
    n = 1500
    tracker = qso_tracker.QsoTracker(max_decodes=10 ** 7, ttl_seconds=10 ** 9)
    added = []

    def raw(msg="CQ K1ABC FN20"):
        return {"time": 1, "snr": 0, "delta_time": 0.4, "delta_freq": 500,
                "mode": "FT8", "message": msg, "low_confidence": False, "off_air": False}

    def feeder():
        for _ in range(n):
            added.append(tracker.add(raw(), 1.0).id)

    def acker():
        for seq in range(0, n, 3):
            tracker.ack(seq)

    sys.setswitchinterval(1e-9)
    try:
        threads = [threading.Thread(target=feeder), threading.Thread(target=acker)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(original)

    kept = {d.id for d in tracker.cq_list()}
    lost = sorted(set(added) - kept)
    check("tracker loses no decode to a concurrent ack", not lost,
          "%d of %d lost: %s" % (len(lost), n, lost[:5]))
    check("tracker kept every decode", len(kept) == n, "kept=%d" % len(kept))


def boundary_cases():
    """Issue 6: the device port is unauthenticated, so its input is untrusted."""
    args = xteink_bridge.parse_args([
        "--rx-port", str(RX_PORT + 1), "--ctrl-port", "23999",
        "--port", str(DEV_PORT + 1), "--rig-host", "",
    ])
    b = xteink_bridge.Bridge(args)
    b.status["de_call"] = "W9XYZ"
    b.status["de_grid"] = "EM48"

    ok = b.handle_command({"cmd": "send_freetext", "text": "CQ W9XYZ EM48", "send": True})
    check("13-character free text accepted", ok.get("type") == "ok_dispatch", str(ok))
    for label, text in [("14 characters", "CQ W9XYZ EM48!"),
                        ("control character", "CQ\nCQ W9"),
                        ("non-ASCII", "CQ W9XYZ\u00c5"),
                        ("empty", "")]:
        resp = b.handle_command({"cmd": "send_freetext", "text": text, "send": True})
        check("free text rejected: %s" % label, resp.get("type") == "text_rejected", str(resp))

    cq = b.handle_command({"cmd": "send_cq"})
    check("composed CQ uses the WSJT-X callsign", cq.get("text") == "CQ W9XYZ EM48", str(cq))
    b.status["de_call"] = "VE3DEF"          # 6-char call -> "CQ VE3DEF FN20" is 14
    b.status["de_grid"] = "FN20"
    long_cq = b.handle_command({"cmd": "send_cq"})
    check("over-long composed CQ is refused, not keyed",
          long_cq.get("type") == "text_rejected", str(long_cq))

    check("qsy outside amateur allocations rejected",
          b.handle_command({"cmd": "qsy", "freq_hz": 100_000_000}).get("type") == "error")
    check("qsy inside amateur allocations reaches the rig path",
          b.handle_command({"cmd": "qsy", "freq_hz": 14_074_000}).get("type") == "not_supported",
          "rig disabled -> not_supported is the pass-through signal")
    check("rigctl band-edge table covers the FT8 band centres",
          all(rigctl.freq_is_allowed(f) for f in rigctl.BAND_CENTERS.values()))


def rigctl_replies_are_checked():
    """Issue 5: a rigctld rejection must not reach the device as success."""
    pending = [b"RPRT 0\n"]
    stop_serving = threading.Event()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    srv.settimeout(0.2)                    # accept() must be exitable, see below
    port = srv.getsockname()[1]

    def serve():
        while not stop_serving.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return                     # listening socket closed
            with conn:
                conn.recv(4096)
                conn.sendall(pending.pop(0) if pending else b"RPRT 0\n")

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()
    rig = rigctl.RigCtl("127.0.0.1", port)

    state, _d = rig.set_frequency(14_074_000)
    check("rigctld RPRT 0 -> ok", state == "ok", state)

    pending[:] = [b"14074000\nRPRT 0\n"]   # some builds echo the read-back first
    check("rigctld echo + RPRT 0 -> ok", rig.set_frequency(14_074_000)[0] == "ok")

    pending[:] = [b"RPRT -6\n"]
    state, detail = rig.set_frequency(14_074_000)
    check("rigctld RPRT -6 -> rejected", state == "rejected", "%s %s" % (state, detail))
    check("rejection detail names the code", "-6" in detail, detail)

    pending[:] = [b"what is this\n"]
    check("unparsable rigctld reply is NOT success",
          rig.set_frequency(14_074_000)[0] == "rejected")

    # Shut the fake rig down deterministically BEFORE probing for "unreachable":
    # closing a listening socket that another thread is blocked in accept() on does
    # not reliably stop it serving (on Linux the connection still succeeded, which is
    # what CI caught). Ask the thread to stop, join it, then close.
    stop_serving.set()
    server_thread.join(timeout=2)
    srv.close()

    # A port nothing holds: bound once to get a free number, then released.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()
    dead = rigctl.RigCtl("127.0.0.1", dead_port)
    state, detail = dead.set_frequency(14_074_000)
    check("no rigctld listening -> unreachable", state == "unreachable",
          "%s %s" % (state, detail))

    # And through the bridge: the device must see qsy_failed, not ok_dispatch.
    srv2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv2.bind(("127.0.0.1", 0))
    srv2.listen(4)
    port2 = srv2.getsockname()[1]

    def serve2():
        while True:
            try:
                conn, _ = srv2.accept()
            except OSError:
                return
            with conn:
                conn.recv(4096)
                conn.sendall(b"RPRT -4\n")

    threading.Thread(target=serve2, daemon=True).start()
    args = xteink_bridge.parse_args(["--rx-port", str(RX_PORT + 2), "--ctrl-port", "23998",
                                     "--port", str(DEV_PORT + 2),
                                     "--rig-host", "127.0.0.1", "--rig-port", str(port2)])
    b = xteink_bridge.Bridge(args)
    resp = b.handle_command({"cmd": "qsy", "band": "20m"})
    check("bridge reports qsy_failed when the rig refuses", resp.get("type") == "qsy_failed", str(resp))
    srv2.close()


def stalled_device_cannot_block_broadcast(server):
    """Issue 1: a device that stops reading must not be able to wedge the caller.

    Before the fix this call chain blocked inside conn.sendall() forever, and in
    production the caller is the single WSJT-X receive thread. A watchdog turns
    a regression into a loud failure instead of a hung CI job.
    """
    import faulthandler
    stalled = socket.create_connection(("127.0.0.1", DEV_PORT), timeout=3)
    send_cmd(stalled, {"cmd": "hello"})   # register it, then never read again
    time.sleep(0.2)

    faulthandler.dump_traceback_later(20, exit=True)
    t0 = time.monotonic()
    for i in range(5000):
        server.broadcast({"type": "decode", "id": 80000 + i,
                          "call": "STALLED", "grid": "FN20"})
    elapsed = time.monotonic() - t0
    faulthandler.cancel_dump_traceback_later()

    check("broadcast() does not block a stalled device's caller", elapsed < 2.0,
          "took %.2f s for 5000 frames" % elapsed)
    stats = server.stats()
    check("stalled device's stale frames are counted as dropped",
          any(s["dropped"] > 0 for s in stats), str(stats))
    stalled.close()


def concurrent_writes_keep_framing(server):
    """#3: responses and pushes share a socket; the stream must stay framed.

    The reader is deliberately slow, so the kernel send buffer fills and the
    writer blocks mid-frame - exactly the condition under which two threads
    calling sendall() on one socket interleave their bytes.
    """
    dev2 = socket.create_connection(("127.0.0.1", DEV_PORT), timeout=5)
    send_cmd(dev2, {"cmd": "hello"})
    if recv_frame(dev2) is None:
        check("concurrent writes keep framing", False, "no hello back")
        return

    stop = threading.Event()

    def pusher():
        i = 0
        while not stop.is_set():
            server.broadcast({"type": "decode", "id": 90000 + i,
                              "call": "VE3DEF", "grid": "FN20"})
            i += 1
            time.sleep(0.0005)

    p = threading.Thread(target=pusher, daemon=True)
    p.start()
    frames = 0
    bad = ""
    try:
        for _ in range(150):
            send_cmd(dev2, {"cmd": "get_decodes"})   # ~9 KB response
            while True:
                frame = recv_frame(dev2)
                if frame is None:
                    raise AssertionError("link dropped after %d frames" % frames)
                if frame.get("type") == "decodes":
                    frames += 1
                    break
            time.sleep(0.003)                        # force backpressure
    except Exception as e:                           # noqa: BLE001
        bad = str(e)
    stop.set()
    p.join(timeout=1)
    check("responses and pushes never interleave on one socket",
          frames == 150 and not bad, "frames=%d %s" % (frames, bad))
    dev2.close()


def main():
    classify_cases()
    tracker_survives_concurrent_ack()
    boundary_cases()
    rigctl_replies_are_checked()

    args = xteink_bridge.parse_args([
        "--rx-port", str(RX_PORT),
        "--ctrl-port", str(CTRL_PORT),
        "--port", str(DEV_PORT),
        "--rig-host", "",  # keep the qsy test deterministic even if a rigctld runs on 4532
    ])
    bridge = xteink_bridge.Bridge(args)
    bridge.server.start()
    rx = threading.Thread(target=bridge._udp_loop, daemon=True)
    rx.start()
    time.sleep(0.3)

    # --- simulate WSJT-X ---------------------------------------------------
    wsjtx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    wsjtx_addr = ("127.0.0.1", RX_PORT)

    # schema negotiation: WSJT-X opens with a schema-2 Heartbeat; the bridge
    # must answer with a schema-3 Heartbeat so WSJT-X upgrades this client.
    wsjtx.settimeout(3)
    wsjtx.sendto(build_heartbeat_schema2(), wsjtx_addr)
    hb = wsjtx.recvfrom(65535)[0]
    magic, schema, mtype = struct.unpack_from(">LLL", hb, 0)
    check("bridge answers schema-2 heartbeat with schema 3",
          magic == wsjtx_udp.MAGIC and schema == 3 and mtype == wsjtx_udp.HEARTBEAT,
          "magic=%x schema=%d type=%d" % (magic, schema, mtype))
    _t, _c, hp = wsjtx_udp.parse_message(hb)
    check("heartbeat reply declares max_schema 3", hp.get("max_schema") == 3, str(hp))

    wsjtx.sendto(build_status(), wsjtx_addr)
    time.sleep(0.05)
    wsjtx.sendto(build_decode("CQ K1ABC FN20", snr=-8, df=800), wsjtx_addr)
    time.sleep(0.05)
    wsjtx.sendto(build_decode("CQ VE3DEF", snr=-15, df=1600), wsjtx_addr)
    time.sleep(0.05)
    wsjtx.sendto(build_decode("K1ABC W9XYZ -12", snr=-12, df=900), wsjtx_addr)  # not a CQ
    time.sleep(0.3)

    # tracker sanity
    cq = bridge.tracker.cq_list()
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

    # QSOLogged parsing with variable-length QDateTime (UTC and offset specs)
    for spec in (1, 2):
        t, _cid, p = wsjtx_udp.parse_message(build_qso_logged(spec))
        check("QSOLogged parses (timespec=%d)" % spec,
              t == wsjtx_udp.QSO_LOGGED and p["dx_call"] == "K1ABC" and p["my_call"] == "W9XYZ",
              str(p)[:80])

    # decodes_ack must NOT drop CQ decodes (the device replies to them later)
    dev.sendall(struct.pack(">L", len(json.dumps({"cmd": "decodes_ack", "seq": target_id}))) + json.dumps({"cmd": "decodes_ack", "seq": target_id}).encode())
    dev.sendall(struct.pack(">L", len(json.dumps({"cmd": "reply", "decode_id": target_id}))) + json.dumps({"cmd": "reply", "decode_id": target_id}).encode())
    resp = recv_frame(dev)
    check("reply still works after decodes_ack", resp.get("type") == "ok_dispatch", str(resp)[:80])

    # status push carries the band name derived from the dial frequency
    wsjtx.sendto(build_status(), wsjtx_addr)
    st = recv_frame(dev)
    check("status push includes band", st.get("type") == "status" and st.get("band") == "20m", str(st)[:80])

    # #1 / #3: socket-safety regressions (run last: these flood every client)
    stalled_device_cannot_block_broadcast(bridge.server)
    concurrent_writes_keep_framing(bridge.server)

    print("\n==== %d passed, %d failed ====" % (len(PASS), len(FAIL)))
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()