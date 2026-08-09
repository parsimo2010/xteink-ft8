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
        """Set the VFO frequency. Returns (ok, detail)."""
        resp = self._request("F %d;\n" % int(freq_hz))
        if resp is None:
            return False, "rigctld unreachable at %s:%d" % (self.host, self.port)
        return True, ""

    def set_mode(self, mode="USB"):
        resp = self._request("M %s 500;\n" % mode)
        if resp is None:
            return False, "rigctld unreachable"
        return True, ""

    @staticmethod
    def band_to_freq(band):
        return BAND_CENTERS.get(band)