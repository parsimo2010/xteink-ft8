"""CQ decode tracking and QSO state for the bridge.

Keeps a rolling list of the latest FT8 CQ/QRZ decodes and exposes helpers to
classify messages and build replies. The device only needs to see stations we
can actually call, so non-CQ decodes are filtered out by default.
"""

import json
import re

# FT8 message patterns we surface as "callable" stations.
#   CQ K1ABC FN20
#   CQ K1ABC
#   QRZ K1ABC
#   CQ TEST K1ABC FN20      (some contests)
_CQ_RE = re.compile(
    r"^\s*(?P<cmd>CQ|QRZ)\s+(?P<call>[A-Z0-9]{3,10})(?:\s+(?P<grid>[A-R]{2}[0-9]{2}))?\s*$",
    re.IGNORECASE,
)

MAX_DECODES = 200  # prune the list beyond this many
DECODE_TTL_SECONDS = 600  # drop decodes older than this (10 min)
MAX_SNAPSHOT = 60  # most decodes handed to a device in one snapshot
MAX_SNAPSHOT_BYTES = 12000  # keep snapshots under the 16 KB frame cap


class Decode:
    """A single FT8 decode plus a stable id and parsed call/grid."""

    __slots__ = (
        "id",
        "time",
        "snr",
        "delta_time",
        "delta_freq",
        "mode",
        "message",
        "low_confidence",
        "off_air",
        "is_cq",
        "call",
        "grid",
        "received_at",
    )

    def __init__(self, did, d, received_at):
        self.id = did
        self.time = d["time"]
        self.snr = d["snr"]
        self.delta_time = d["delta_time"]
        self.delta_freq = d["delta_freq"]
        self.mode = d["mode"]
        self.message = d["message"]
        self.low_confidence = d["low_confidence"]
        self.off_air = d["off_air"]
        self.is_cq, self.call, self.grid = classify(d["message"])
        self.received_at = received_at

    def as_dict(self):
        return {
            "id": self.id,
            "is_cq": self.is_cq,
            "time": self.time,
            "snr": self.snr,
            "delta_time": self.delta_time,
            "delta_freq": self.delta_freq,
            "mode": self.mode,
            "raw": self.message,
            "call": self.call,
            "grid": self.grid,
            "low_confidence": self.low_confidence,
            "off_air": self.off_air,
        }


def classify(message):
    """Return (is_cq, call, grid) for a decode message string."""
    m = _CQ_RE.match(message or "")
    if not m:
        return False, "", ""
    return True, m.group("call").upper(), (m.group("grid") or "").upper()


class QsoTracker:
    def __init__(self, max_decodes=MAX_DECODES, ttl_seconds=DECODE_TTL_SECONDS):
        self._decodes = []  # list[Decode], newest last
        self._by_id = {}
        self._next_id = 1
        self._max = max_decodes
        self._ttl = ttl_seconds

    def add(self, raw_decode, now_ts):
        """Feed a raw WSJT-X decode dict; returns the Decode or None."""
        d = Decode(self._next_id, raw_decode, now_ts)
        self._next_id += 1
        self._decodes.append(d)
        self._by_id[d.id] = d
        self._prune(now_ts)
        return d

    def _prune(self, now_ts):
        cutoff = now_ts - self._ttl
        # Drop expired and clear any over the cap (oldest first).
        self._decodes = [d for d in self._decodes if d.received_at >= cutoff]
        if len(self._decodes) > self._max:
            self._decodes = self._decodes[-self._max :]
        self._by_id = {d.id: d for d in self._decodes}

    def clear(self):
        self._decodes.clear()
        self._by_id.clear()

    def get(self, did):
        return self._by_id.get(did)

    def cq_list(self, now_ts):
        """Decodes that are CQ/QRZ, newest last."""
        return [d for d in self._decodes if d.is_cq]

    def snapshot(self, now_ts):
        """Newest CQ decodes, capped so the framed reply stays under 16 KB."""
        entries = [d.as_dict() for d in self.cq_list(now_ts)][-MAX_SNAPSHOT:]
        while entries and sum(len(json.dumps(e, separators=(",", ":"))) + 1 for e in entries) > MAX_SNAPSHOT_BYTES:
            entries.pop(0)
        return {"seq": self._next_id, "decodes": entries}

    def ack(self, seq):
        """Drop decodes with id <= seq (the device has them)."""
        if seq is None:
            return
        self._decodes = [d for d in self._decodes if d.id > seq]
        self._by_id = {d.id: d for d in self._decodes}