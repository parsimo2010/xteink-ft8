# xteink-ft8 bridge (Raspberry Pi)

Pure-Python 3 middleware (stdlib only) that relays WSJT-X FT8 data to an
Xteink X4 Pro over WiFi/TCP.

## Run

```bash
python3 xteink_bridge.py --help
python3 xteink_bridge.py
```

Defaults:
* Receives WSJT-X outgoing UDP on `127.0.0.1:2238`
* Sends WSJT-X control messages to `127.0.0.1:2237` (enable *Accept UDP requests*)
* Device TCP server on `0.0.0.0:4510`

## Modules

| file | purpose |
|------|---------|
| `wsjtx_udp.py` | WSJT-X UDP protocol encode/decode (pure struct; answers WSJT-X heartbeats to negotiate schema 3) |
| `qso_tracker.py` | CQ decode tracking + WSJT-X message classification |
| `device_server.py` | length-framed JSON TCP server for the X4 Pro |
| `rigctl.py` | band change via Hamlib `rigctld` (on by default) |
| `xteink_bridge.py` | entry point tying it together |

## Test

```bash
python3 test_bridge.py
```

Simulates WSJT-X (UDP) and a device (TCP) over real sockets and asserts the
full flow: decode ingestion, CQ filtering, push to device, and `reply` ->
WSJT-X `Reply` packet.

## Band change

Band changes go to Hamlib `rigctld` on `127.0.0.1:4532` (bridge default).
`install.sh` sets up `xteink-rigctld.service`, which auto-detects a QRP Labs
**QMX/QMX+** on USB (hamlib ≥ 4.6.1 uses the native QMX backend, model 2057 —
`build_hamlib.sh` installs the latest hamlib into `/opt/hamlib` for Bookworm;
older hamlib falls back to the TS-480-compatible backend). WSJT-X connects to
the same rigctld as "Hamlib NET rigctl", so band changes propagate to the
WSJT-X session. Configure other rigs in `/etc/default/xteink-rigctld`.
Without any rigctld the `qsy` device command replies `not_supported`.

See **`../docs/SETUP.md`** for full field deployment (including headless
auto-start via systemd) and **`../docs/FLASHING.md`** for the X4 Pro. The
`scripts/` directory has the one-time installer and access-point setup.