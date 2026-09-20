"""WSJT-X UDP protocol encode/decode.

Implements the WSJT-X "UDP" protocol (schema 3, Qt_5_4 QDataStream encoding)
for the message types this bridge cares about. All integers are big-endian.

Header (every message):
    magic  quint32 0xadbccbda
    schema quint32 3
    type   quint32 (enum)
    id     QByteArray (4-byte length + utf8 bytes)

Outgoing (WSJT-X -> us): Heartbeat, Status, Decode, QSOLogged, Clear.
Incoming (us -> WSJT-X): Reply, FreeText, HaltTx, Clear, Close.

Reference: WSJT-X source `Network/NetworkMessage.hpp` (message layout) and
`Network/NetworkMessage.cpp` (header serialization).
"""

import struct

MAGIC = 0xADBCCBDA
SCHEMA = 3

# Message type enum (NetworkMessage.hpp)
HEARTBEAT = 0
STATUS = 1
DECODE = 2
CLEAR = 3
REPLY = 4
QSO_LOGGED = 5
CLOSE = 6
REPLAY = 7
HALT_TX = 8
FREE_TEXT = 9
WSPR_DECODE = 10
LOCATION = 11
LOGGED_ADIF = 12
HIGHLIGHT_CALLSIGN = 13
SWITCH_CONFIGURATION = 14
CONFIGURE = 15
ANNOTATION_INFO = 16

UDP_PORT_DEFAULT = 2237


class ProtocolError(Exception):
    """Raised when a datagram is not a valid WSJT-X UDP message."""


def _pack_string(value):
    """QByteArray: 4-byte big-endian length + utf8 bytes (no terminator)."""
    if value is None:
        return struct.pack(">L", 0xFFFFFFFF)  # null QByteArray
    data = value.encode("utf-8")
    return struct.pack(">L", len(data)) + data


def _unpack_string(buf, offset):
    """Read a QByteArray; returns (value, new_offset). value is None for null."""
    (length,) = struct.unpack_from(">L", buf, offset)
    offset += 4
    if length == 0xFFFFFFFF:
        return None, offset
    value = buf[offset : offset + length].decode("utf-8", "replace")
    offset += length
    return value, offset


def _pack_header(msg_type, client_id=""):
    """Header: magic + schema + type + id."""
    return struct.pack(">LLL", MAGIC, SCHEMA, msg_type) + _pack_string(client_id)


def _unpack_header(buf):
    """Returns (msg_type, client_id, offset_after_header).

    Accepts schema 2 as well as 3: WSJT-X sends schema-2 messages until a
    client answers its Heartbeat with a schema-3 Heartbeat (negotiation).
    Schema 2 differs only in float/QDateTime encoding, so at schema 2 only
    HEARTBEAT (ints + byte arrays, identical in both schemas) is parseable.
    """
    if len(buf) < 12:
        raise ProtocolError("datagram too short")
    magic, schema, msg_type = struct.unpack_from(">LLL", buf, 0)
    if magic != MAGIC:
        raise ProtocolError("bad magic 0x%08X" % magic)
    if schema not in (2, SCHEMA):
        raise ProtocolError("unsupported schema %d" % schema)
    client_id, offset = _unpack_string(buf, 12)
    if schema != SCHEMA and msg_type != HEARTBEAT:
        raise ProtocolError(
            "schema %d message type %d not parseable (heartbeat negotiation "
            "pending or failed)" % (schema, msg_type)
        )
    return msg_type, client_id, offset


# ---------------------------------------------------------------------------
# Outgoing messages (WSJT-X -> us)
# ---------------------------------------------------------------------------

def parse_message(datagram):
    """Parse a raw UDP datagram into (msg_type, client_id, payload_dict).

    payload_dict keys depend on msg_type. Unknown/unparseable messages raise
    ProtocolError.
    """
    msg_type, client_id, off = _unpack_header(datagram)

    if msg_type == HEARTBEAT:
        (max_schema,) = struct.unpack_from(">L", datagram, off)
        off += 4
        version, off = _unpack_string(datagram, off)
        revision, off = _unpack_string(datagram, off)
        return msg_type, client_id, {
            "max_schema": max_schema,
            "version": version,
            "revision": revision,
        }

    if msg_type == STATUS:
        return msg_type, client_id, _parse_status(datagram, off)

    if msg_type in (DECODE, WSPR_DECODE, REPLAY):
        return msg_type, client_id, _parse_decode(datagram, off)

    if msg_type == REPLY:
        return msg_type, client_id, _parse_reply(datagram, off)

    if msg_type == CLEAR:
        (window,) = struct.unpack_from(">B", datagram, off)
        return msg_type, client_id, {"window": window}

    if msg_type == QSO_LOGGED:
        return msg_type, client_id, _parse_qso_logged(datagram, off)

    # Types we don't act on: return a stub so the caller can ignore them.
    return msg_type, client_id, {}


def _parse_status(buf, off):
    d = {}
    (d["dial_frequency"],) = struct.unpack_from(">Q", buf, off)
    off += 8
    d["mode"], off = _unpack_string(buf, off)
    d["dx_call"], off = _unpack_string(buf, off)
    d["report"], off = _unpack_string(buf, off)
    d["tx_mode"], off = _unpack_string(buf, off)
    (d["tx_enabled"],) = struct.unpack_from(">?", buf, off)
    off += 1
    (d["transmitting"],) = struct.unpack_from(">?", buf, off)
    off += 1
    (d["decoding"],) = struct.unpack_from(">?", buf, off)
    off += 1
    (d["rx_df"],) = struct.unpack_from(">L", buf, off)
    off += 4
    (d["tx_df"],) = struct.unpack_from(">L", buf, off)
    off += 4
    d["de_call"], off = _unpack_string(buf, off)
    d["de_grid"], off = _unpack_string(buf, off)
    d["dx_grid"], off = _unpack_string(buf, off)
    (d["tx_watchdog"],) = struct.unpack_from(">?", buf, off)
    off += 1
    d["sub_mode"], off = _unpack_string(buf, off)
    (d["fast_mode"],) = struct.unpack_from(">?", buf, off)
    off += 1
    (d["special_operation_mode"],) = struct.unpack_from(">B", buf, off)
    off += 1
    (d["frequency_tolerance"],) = struct.unpack_from(">L", buf, off)
    off += 4
    (d["tr_period"],) = struct.unpack_from(">L", buf, off)
    off += 4
    d["configuration_name"], off = _unpack_string(buf, off)
    d["tx_message"], off = _unpack_string(buf, off)
    return d


def _parse_decode(buf, off, is_wspr=False):
    d = {}
    (d["new_decode"],) = struct.unpack_from(">?", buf, off)
    off += 1
    (d["time"],) = struct.unpack_from(">L", buf, off)  # ms since midnight
    off += 4
    (d["snr"],) = struct.unpack_from(">l", buf, off)
    off += 4
    (d["delta_time"],) = struct.unpack_from(">d", buf, off)  # float as double
    off += 8
    (d["delta_freq"],) = struct.unpack_from(">L", buf, off)
    off += 4
    d["mode"], off = _unpack_string(buf, off)
    d["message"], off = _unpack_string(buf, off)
    (d["low_confidence"],) = struct.unpack_from(">?", buf, off)
    off += 1
    if is_wspr:
        (d["off_air"],) = struct.unpack_from(">?", buf, off)
    else:
        (d["off_air"],) = struct.unpack_from(">?", buf, off)
    off += 1
    return d


def _parse_reply(buf, off):
    """Reply packet layout (no leading 'new_decode', 'modifiers' instead of 'off_air')."""
    d = {}
    (d["time"],) = struct.unpack_from(">L", buf, off)
    off += 4
    (d["snr"],) = struct.unpack_from(">l", buf, off)
    off += 4
    (d["delta_time"],) = struct.unpack_from(">d", buf, off)
    off += 8
    (d["delta_freq"],) = struct.unpack_from(">L", buf, off)
    off += 4
    d["mode"], off = _unpack_string(buf, off)
    d["message"], off = _unpack_string(buf, off)
    (d["low_confidence"],) = struct.unpack_from(">?", buf, off)
    off += 1
    (d["modifiers"],) = struct.unpack_from(">B", buf, off)
    off += 1
    return d


def _unpack_qdatetime(buf, off):
    """QDateTime per QDataStream Qt_5_4 (see NetworkMessage.hpp):
    qint64 julian day + quint32 ms + quint8 timespec [+ qint32 offset only
    when timespec==2]. WSJT-X never uses timespec==3 (time zone)."""
    jd, msecs, timespec = struct.unpack_from(">qLB", buf, off)
    off += 13
    offset = None
    if timespec == 2:  # OffsetFromUTC
        (offset,) = struct.unpack_from(">l", buf, off)
        off += 4
    elif timespec == 3:  # TimeZone - not produced by WSJT-X
        raise ProtocolError("QDateTime with time zone not supported")
    return {"julian_day": jd, "msecs": msecs, "timespec": timespec, "utc_offset": offset}, off


def _parse_qso_logged(buf, off):
    d = {}
    d["time_off"], off = _unpack_qdatetime(buf, off)
    d["dx_call"], off = _unpack_string(buf, off)
    d["dx_grid"], off = _unpack_string(buf, off)
    (d["tx_freq"],) = struct.unpack_from(">Q", buf, off)
    off += 8
    d["mode"], off = _unpack_string(buf, off)
    d["report_sent"], off = _unpack_string(buf, off)
    d["report_received"], off = _unpack_string(buf, off)
    d["tx_power"], off = _unpack_string(buf, off)
    d["comments"], off = _unpack_string(buf, off)
    d["name"], off = _unpack_string(buf, off)
    d["time_on"], off = _unpack_qdatetime(buf, off)
    d["op_call"], off = _unpack_string(buf, off)
    d["my_call"], off = _unpack_string(buf, off)
    d["my_grid"], off = _unpack_string(buf, off)
    d["exchange_sent"], off = _unpack_string(buf, off)
    d["exchange_received"], off = _unpack_string(buf, off)
    d["adif_propagation_mode"], off = _unpack_string(buf, off)
    # Newer WSJT-X appends satellite/satmode/freq_rx fields; per the protocol's
    # backward-compatibility rule, trailing fields we don't know are ignored.
    return d


# ---------------------------------------------------------------------------
# Incoming messages (us -> WSJT-X)
# ---------------------------------------------------------------------------

def build_heartbeat(client_id, max_schema=SCHEMA, version="xteink-bridge", revision="1"):
    """Client Heartbeat: declares the highest schema we can parse.

    WSJT-X negotiates per client: it streams schema-2 messages to a UDP
    server until that server answers a Heartbeat with this packet, after
    which WSJT-X upgrades the client to schema 3.
    """
    payload = struct.pack(">L", max_schema)
    payload += _pack_string(version) + _pack_string(revision)
    return _pack_header(HEARTBEAT, client_id) + payload


def build_reply(client_id, decode):
    """Build a Reply packet from a decode dict (the WSJT-X 'double click')."""
    parts = [struct.pack(">L", decode["time"])]
    parts.append(struct.pack(">l", decode["snr"]))
    parts.append(struct.pack(">d", decode["delta_time"]))
    parts.append(struct.pack(">L", decode["delta_freq"]))
    parts.append(_pack_string(decode["mode"]))
    parts.append(_pack_string(decode["message"]))
    parts.append(struct.pack(">?", decode["low_confidence"]))
    parts.append(struct.pack(">B", 0))  # modifiers: none
    payload = b"".join(parts)
    return _pack_header(REPLY, client_id) + payload


def build_freetext(client_id, text, send):
    """Build a FreeText packet (sets Tx5 message; send optionally transmits)."""
    payload = _pack_string(text) + struct.pack(">?", send)
    return _pack_header(FREE_TEXT, client_id) + payload


def build_halt_tx(client_id, auto_tx_only):
    return _pack_header(HALT_TX, client_id) + struct.pack(">?", auto_tx_only)


def build_clear(client_id, window):
    return _pack_header(CLEAR, client_id) + struct.pack(">B", window)