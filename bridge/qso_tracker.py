"""CQ decode tracking and QSO state for the bridge.

Keeps a rolling list of the latest FT8 CQ/QRZ decodes and exposes helpers to
classify messages and build replies. The device only needs to see stations we
can actually call, so non-CQ decodes are filtered out by default.
"""

import json
import re

# FT8 messages we surface as "callable" stations. The station to answer is the
# TRANSMITTER, which is the LAST callsign in the message:
#   CQ K1ABC FN20                   general CQ by K1ABC
#   CQ DX K1ABC FN20                general CQ with a modifier
#   CQ POTA|SOTA|WW|TEST K1ABC FN20 contest / activator CQs
#   CQ NA-012 K1ABC FN20            reference between CQ and the call
#   CQ W1AW K1ABC FN20              K1ABC calling W1AW -> we answer K1ABC
#   QRZ K1ABC [FN20]
# "CQ DX" with nothing after it is NOT a callable station.
_CQ_CMDS = {"CQ", "QRZ"}

# A callsign: optional prefix, one district digit, optional suffix, and at least
# one letter. Tokens that look like a Maidenhead grid are excluded, so a bare grid
# is never mistaken for a station (FN20 is a grid, not a call).
_CALL_RE = re.compile(r"^(?=.*[A-Z])[A-Z0-9]{1,3}[0-9][A-Z0-9]{1,3}$")
_GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}$")


def _is_call(token):
    base = token.split("/")[0]           # ignore /P, /MM, /AE style suffixes
    if not base or base == "CQ" or base == "DE" or _GRID_RE.match(base):
        return False
    return bool(_CALL_RE.match(base))

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
    """Return (is_cq, call, grid) for a decode message string.

    `call` is the callsign of the station that transmitted the message (the one a
    `reply` must target), and `grid` is its 4-character Maidenhead locator if the
    message carried one.
    """
    tokens = (message or "").upper().split()
    if not tokens or tokens[0] not in _CQ_CMDS:
        return False, "", ""
    rest = tokens[1:]
    grid = ""
    if rest and _GRID_RE.match(rest[-1]):
        grid = rest[-1]
        rest = rest[:-1]
    candidates = [t for t in rest if _is_call(t)]
    if not candidates:
        return False, "", ""
    return True, candidates[-1].split("/")[0], grid


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
        """Device acknowledged decodes up to seq.

        Only non-CQ rows may be garbage-collected: CQ decodes must survive an
        ack because the device answers them *later* by id (`reply`).
        """
        if seq is None:
            return
        self._decodes = [d for d in self._decodes if d.id > seq or d.is_cq]
        self._by_id = {d.id: d for d in self._decodes}