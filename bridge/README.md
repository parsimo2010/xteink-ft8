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
| `wsjtx_udp.py` | WSJT-X UDP protocol encode/decode (pure struct) |
| `qso_tracker.py` | CQ decode tracking + WSJT-X message classification |
| `device_server.py` | length-framed JSON TCP server for the X4 Pro |
| `rigctl.py` | optional band change via Hamlib `rigctld` |
| `xteink_bridge.py` | entry point tying it together |

## Test

```bash
python3 test_bridge.py
```

Simulates WSJT-X (UDP) and a device (TCP) over real sockets and asserts the
full flow: decode ingestion, CQ filtering, push to device, and `reply` ->
WSJT-X `Reply` packet.

## Band change

Band changes need Hamlib `rigctld` running (independent of WSJT-X's own rig
link). Start `rigctld` and pass `--rig-host/--rig-port`. Without it the `qsy`
device command replies `not_supported`.

See **`../docs/SETUP.md`** for full field deployment (including headless
auto-start via systemd) and **`../docs/FLASHING.md`** for the X4 Pro. The
`scripts/` directory has the one-time installer and access-point setup.