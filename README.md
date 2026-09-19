# xteink-ft8

Field FT8 operation from the pocket: a WSJT-X bridge on a Raspberry Pi + a
handheld "go-box" UI on an **Xteink X4 Pro** e-ink reader.

```
  [Transceiver]  <--CAT-->  [Raspberry Pi]
                                |  WSJT-X (decodes + QSO state machine)
                                |  xteink-bridge (Python)  <--UDP 2237/2238-->
                                |
                           WiFi AP (ad-hoc, no internet needed)
                                |
                          [Xteink X4 Pro]  (ESP32-S3 e-ink, touch)
```

You run WSJT-X with a connected radio in the field. The bridge listens to
WSJT-X's UDP messages, filters the FT8 **CQ** decodes, and relays them to the
X4 Pro over the Pi's own WiFi network. Tap a CQ on the e-ink screen to answer
it, send CQs yourself, change band, or halt TX — everything WSJT-X needs to
complete the contact is driven from your wrist.

No internet access point is required: the Pi creates its own WiFi network, so
this works from a mountain top or a park.

---

## Getting started

* **Raspberry Pi** — step-by-step setup (AP, WSJT-X, bridge, headless
  auto-start): [`docs/SETUP.md`](docs/SETUP.md)
* **X4 Pro** — building and flashing from stock firmware:
  [`docs/FLASHING.md`](docs/FLASHING.md)
* **Device ⇄ bridge protocol**: [`docs/PROTOCOL.md`](docs/PROTOCOL.md)
* **Future prebuilt releases**: [`docs/RELEASE.md`](docs/RELEASE.md)

> No release is published yet — hardware bring-up is done (the firmware boots
> and runs on a real X4 Pro) but the end-to-end field link is still being
> validated. If you build from source, you need **Python 3.10–3.13** for the
> firmware toolchain and the FreeInk SDK submodule
> (`git clone --recurse-submodules`).

---

## Project layout

```
xteink-ft8/
├── bridge/            Raspberry Pi middleware (Python 3, stdlib only)
│   ├── xteink_bridge.py   entry point
│   ├── wsjtx_udp.py       WSJT-X UDP protocol encode/decode (pure struct)
│   ├── device_server.py   TCP server the X4 Pro connects to
│   ├── qso_tracker.py     CQ decode tracking + QSO state
│   ├── rigctl.py          band change via Hamlib rigctld (QMX/QMX+ by default)
│   └── scripts/           systemd autostart, AP setup, WSJT-X preseed
├── firmware/          Xteink X4 Pro firmware (PlatformIO + FreeInk SDK)
│   ├── platformio.ini
│   ├── include/           config.h proto.h ui.h net_client.h font5x7.h ...
│   └── src/               main.cpp proto.cpp ui.cpp net_client.cpp
├── docs/
│   ├── SETUP.md           Raspberry Pi step-by-step deployment
│   ├── FLASHING.md        X4 Pro build + flash from stock
│   ├── PROTOCOL.md        device <-> bridge TCP protocol spec
│   └── RELEASE.md         future prebuilt-release plan
└── .github/workflows/     CI that builds firmware + bridge on version tags
```

## The two halves

### 1. Bridge (`bridge/`) — runs on the Raspberry Pi

* Receives WSJT-X **Outgoing** UDP messages (Heartbeat, Status, Decode,
  QSOLogged) on the configured UDP Server port.
* Maintains a rolling list of the latest FT8 **CQ / QRZ** decodes.
* Runs a TCP server that the X4 Pro connects to and pushes new decodes /
  status to it in real time.
* Acts on device commands by sending WSJT-X **Incoming** control messages
  (Reply, FreeText, HaltTx, Clear) back to WSJT-X's "Accept UDP requests" port.
* Changes band via Hamlib `rigctld` — enabled by default: `install.sh` sets up
  `xteink-rigctld.service`, which auto-detects a QRP Labs **QMX/QMX+** on USB
  and is shared with WSJT-X (Hamlib NET rigctl), so the X4 Pro's band buttons
  retune the whole station. Degrades to a `not_supported` reply if no rigctld.

Pure Python 3 stdlib — no third-party dependencies to install on the Pi.

### 2. Firmware (`firmware/`) — runs on the Xteink X4 Pro

Built on the **FreeInk SDK** (the same display/input stack CrossPoint uses),
targeted for the ESP32-S3 X4 Pro profile:

* **Display:** 800×480 SSD1677 e-paper (borrowed driver from FreeInk), driven
  in a **portrait** (480×800) logical layout via a software framebuffer
  transpose — the panel RAM is landscape-only.
* **Input:** GT911 capacitive touch (taps flash the control for feedback) +
  two page-turn buttons for scrolling + a power button (hold to deep-sleep).
* **Networking:** WiFi client that joins the Pi's AP and connects to the bridge
  TCP server; a framing error just drops + reconnects the socket (it can never
  permanently desync the link). Shows **NO-LINK** and stays fully re-flashable
  over USB whenever the Pi is absent.
* **UI:** a compact immediate-mode renderer with an embedded 5×7 bitmap font
  upscaled to 8×11 for readability on the 800×480 panel.

The e-ink panel is the key: it sips power, is readable in full sunlight, and
shows a live FT8 band map without draining the battery.

---

## Contact workflow (how it "completes contacts")

FT8 QSOs are handled by WSJT-X's built-in state machine once you "double click"
a CQ decode. The X4 Pro just needs to tell WSJT-X which decode to answer and
then display the progress:

1. The bridge parses each `Decode` message and keeps the ones whose text looks
   like `CQ <call> <grid>` (or `QRZ`).
2. The X4 Pro shows them as a scrollable list (call, grid, signal, offset).
3. Tapping a row sends `reply` with that decode's fields. The bridge encodes a
   WSJT-X `Reply` packet → WSJT-X starts the QSO: it replies with your call,
   exchanges signal reports, and finishes with `RR73` / `TU`.
4. The bridge forwards `Status` messages (current `tx_message`) and related
   decodes so the X4 Pro shows the QSO progressing.
5. A `CQ` button sends `send_cq` (WSJT-X `FreeText` with `CQ <you> <grid>`,
   send=1). `Band << >>` changes band via the shared rigctld (QMX/QMX+
   auto-detected). `Halt` stops TX.

So the device controls *which* station to work and *when* to transmit, while
WSJT-X does the FT8 protocol heavy lifting.

---

## Status

Hardware bring-up is **done**: as of 2026-09-12 the firmware has been flashed
and boots on a real X4 Pro — portrait e-ink rendering, GT911 touch (with
tap-flash feedback), page buttons, and hold-power deep sleep are all confirmed
on-device. Still being validated end-to-end: joining the Pi AP, receiving live
CQ decodes, and completing a real QSO via WSJT-X (see `docs/RELEASE.md`).

No prebuilt release is published yet — that waits for the Pi link + a real
QSO. Expect to tune:

* The bridge's WSJT-X UDP schema handling across WSJT-X versions.
* The `<<` / `>>` band-change ladder (currently a simple single-QSY stub).

See `docs/` for build and field-deployment instructions.

## License

MIT. The firmware links against the FreeInk SDK (MIT) and borrows its
architecture from CrossPoint (MIT).