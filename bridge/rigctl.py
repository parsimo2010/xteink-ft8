"""Optional band / frequency control via Hamlib rigctld.

Uses rigctld's simple text protocol over TCP. If rigctld is not reachable the
caller degrades gracefully (the bridge reports `not_supported`).
"""

import socket

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4532
TIMEOUT = 2.0

# Approximate band centers (Hz) for the common HF bands. Used to translate a
# named band ("20m") into a frequency for rigctld.
BAND_CENTERS = {
    "160m": 1_830_000,
    "80m": 3_590_000,
    "60m": 5_377_000,
    "40m": 7_074_000,
    "30m": 10_138_000,
    "20m": 14_074_000,
    "17m": 18_100_000,
    "15m": 21_074_000,
    "12m": 24_915_000,
    "10m": 28_074_000,
    "6m": 50_313_000,
}


# Amateur allocations (Hz) the bridge will tune to by default. This is a
# footgun guard against a malformed or hostile qsy, not a licence check: it is
# deliberately generous (Region-2-ish edges) and can be switched off with
# --no-band-check for experimenters with an appropriate licence.
BAND_EDGES = [
    (1_800_000, 2_000_000),    # 160m
    (3_500_000, 4_000_000),    # 80m
    (5_100_000, 5_600_000),    # 60m (region dependent)
    (7_000_000, 7_300_000),    # 40m
    (10_100_000, 10_150_000),  # 30m
    (14_000_000, 14_350_000),  # 20m
    (18_068_000, 18_168_000),  # 17m
    (21_000_000, 21_450_000),  # 15m
    (24_890_000, 24_990_000),  # 12m
    (28_000_000, 29_700_000),  # 10m
    (50_000_000, 54_000_000),  # 6m
]


def freq_is_allowed(freq_hz):
    """True when freq_hz falls inside one of the amateur allocations above."""
    try:
        f = int(freq_hz)
    except (TypeError, ValueError):
        return False
    return any(lo <= f <= hi for lo, hi in BAND_EDGES)


def _parse_rprt(resp):
    """rigctld ends every command with 'RPRT <code>' (0 = success); a read command
    may echo values on the line(s) before it.

    Returns (ok, code). Anything unparseable is reported as a failure: treating "we
could not understand the rig" as "the rig complied" is how a rejected QSY ends up
looking successful on the device.
    """
    if not resp:
        return False, None
    for line in resp.decode("ascii", "replace").splitlines():
        parts = line.split()
        if parts and parts[0].upper() == "RPRT":
            try:
                code = int(parts[1])
            except (IndexError, ValueError):
                return False, None
            return code == 0, code
    return False, None


class RigCtl:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port

    def _request(self, cmd):
        try:
            with socket.create_connection((self.host, self.port), timeout=TIMEOUT) as s:
                s.sendall(cmd.encode("ascii"))
                s.shutdown(socket.SHUT_WR)
                chunks = []
                while True:
                    data = s.recv(4096)
                    if not data:
                        break
                    chunks.append(data)
            return b"".join(chunks)
        except OSError:
            return None

    def set_frequency(self, freq_hz):
        """Set the VFO frequency.

        Returns (state, detail) with state one of "ok", "rejected", "unreachable".
        "rejected" means rigctld answered with a non-zero RPRT - the rig did NOT
        change frequency - which must never be reported to the device as success.
        """
        resp = self._request("F %d;\n" % int(freq_hz))
        if resp is None:
            return "unreachable", "rigctld unreachable at %s:%d" % (self.host, self.port)
        ok, code = _parse_rprt(resp)
        if not ok:
            return "rejected", "rigctld rejected F %d: RPRT %s (reply %.60r)" % (
                int(freq_hz), code, resp)
        return "ok", ""

    def set_mode(self, mode="USB"):
        resp = self._request("M %s 500;\n" % mode)
        if resp is None:
            return "unreachable", "rigctld unreachable"
        ok, code = _parse_rprt(resp)
        if not ok:
            return "rejected", "rigctld rejected M %s: RPRT %s" % (mode, code)
        return "ok", ""

    @staticmethod
    def band_to_freq(band):
        return BAND_CENTERS.get(band)