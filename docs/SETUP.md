# xteink-ft8 — Raspberry Pi setup

Step-by-step guide to turn a Raspberry Pi into the field FT8 brain: WiFi access
point + WSJT-X + the xteink-ft8 bridge. After the **one-time home setup**
below, the Pi boots headless in the field and automatically brings up the
access point, WSJT-X, and the bridge.

> For building/flashing the X4 Pro, see [FLASHING.md](FLASHING.md).
> For the future compiled-release plan, see [RELEASE.md](RELEASE.md).

---

## 0. What you need

**Hardware**
* A Raspberry Pi (3B+/4/5 recommended) with a fresh **Raspberry Pi OS (64-bit,
  "Bookworm" or newer)**.
* A USB sound interface / interface cable for your transceiver (this is the
  usual FT8 audio + rig-control setup).
* An **Xteink X4 Pro** e-ink reader.
* A computer (Windows/Linux/macOS) with a USB cable to build & flash the X4 Pro
  firmware once.

**Software (installed below)**
* WSJT-X 2.6+ (headless via Xvfb — no screen needed in the field).
* Hamlib (`rigctld`) for rig/band control.
* `hostapd` + `dnsmasq` for the WiFi access point.
* `xvfb` for the virtual display.
* The xteink-ft8 bridge (pure Python 3, no extra pip packages).

---

## 1. Prepare the Raspberry Pi OS

1. Flash Raspberry Pi OS (64-bit) to an SD card with the official Imager.
2. Enable **SSH** and set a hostname (e.g. `xteink`) in Imager's settings.
3. Boot the Pi with a keyboard/monitor **once** (or plug it into your router
   and SSH in). You need internet for the one-time install below.
4. Update:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y git python3 python3-venv
   ```

---

## 2. Get the software

```bash
cd ~
git clone --recurse-submodules https://github.com/parsimo2010/xteink-ft8.git
cd xteink-ft8
```

> `--recurse-submodules` pulls the FreeInk SDK used by the firmware. If you
> forgot it, run `git submodule update --init --recursive` inside the repo.

---

## 3. One-time headless auto-start install

Everything (deps, AP, systemd units) is set up by two scripts. Run them with
your call and grid:

```bash
cd ~/xteink-ft8

# 1) Install systemd units + dependencies (xvfb, wsjtx, hamlib).
sudo bash bridge/scripts/install.sh

# 2) Configure the WiFi access point (SSID XTEINK-FT8 / pass ft8field,
#    network 192.168.4.1/24). Optionally override with AP_SSID/AP_PASS.
sudo bash bridge/scripts/setup_ap.sh

# 3) Best-effort prefill of your callsign/grid + UDP ports into WSJT-X.
WSJTXCALL=W9XYZ WSJTXGRID=EM48 bash bridge/scripts/preseed_wsjtx.sh
```

If `apt` can't find `wsjtx`, install it from the WSJT-X release page
(`.deb`/`.rpm`), then re-run `install.sh` (or just start the services).

---

## 4. Configure WSJT-X (one-time, over VNC)

The Pi runs WSJT-X on a virtual display, so to see its window you connect over
VNC **once at home**:

```bash
# If x11vnc isn't installed yet:
sudo apt install -y x11vnc
# Start WSJT-X on the virtual display and view it:
export DISPLAY=:1
x11vnc -display :1 &
wsjtx        # or: systemctl start xteink-wsjtx.service
```

Then in **Settings → Reporting** set:
* **UDP Server**: `127.0.0.1` port **2238**  ← where WSJT-X *sends* messages
  (the bridge listens here).
* **Accept UDP requests**: **checked**  ← WSJT-X *listens* on **2237** for the
  bridge's control messages (Reply / FreeText / HaltTx / Clear).

> **Why two ports:** WSJT-X sends *out* and listens *in* on the same port by
> default. Because the bridge runs on the same host, we move the *outgoing*
> destination to **2238** so the two socket roles don't collide. The bridge
> receives on 2238 and sends controls to 127.0.0.1:2237.

Also in WSJT-X settings:
* **Station Callsign** and **Grid** — this is the single source of truth for
  your identity (the bridge and the X4 Pro pull it from here).
* **Rig** (Hamlib) → select your radio and audio device so WSJT-X can transmit.
* **Auto Seq** — enable for hands-free completion of FT8 QSOs.
* **Include non-default decode messages**: keep default (off); the bridge only
  cares about CQ/QRZ.

> **Optional band change:** to let the X4 Pro's `<<`/`>>` buttons change band,
> run WSJT-X and the bridge against the **same** `rigctld`:
> ```bash
> rigctld --model=<MODEL> --rig-file=/dev/ttyUSB0 --set-conf=... &
> ```
> and start the bridge with `--rig-host 127.0.0.1 --rig-port 4532`. Because
> both WSJT-X and the bridge talk to that one rigctld, band changes propagate.
> Without it, the `<<`/`>>` buttons reply `not_supported` (harmless).

---

## 5. Start the services & verify

```bash
sudo systemctl enable xteink-bridge.service xteink-wsjtx.service
sudo systemctl start  xteink-bridge.service xteink-wsjtx.service

# Watch startup / errors:
sudo journalctl -u xteink-bridge -f
sudo journalctl -u xteink-wsjtx -f
```

The bridge logs `bridge ready: rx=127.0.0.1:2238 ... device=0.0.0.0:4510`.

---

## 6. First run (field)

1. Power the Pi. It boots the AP + WSJT-X + bridge automatically (~1–2 min).
2. Power the X4 Pro. It joins the AP and connects to `192.168.4.1:4510`.
3. The X4 Pro fills with CQ decodes after the first decode cycle.
4. Tap a CQ to answer it; WSJT-X drives the QSO to completion. Use the bottom
   bar for **CQ / band << >> / re-fetch / Halt**.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Device shows **No link** | AP up? (`iw dev` / `hostapd` running). Credentials in `config.h` match `setup_ap.sh`? Bridge listening on an address the device can reach? |
| **No decodes** on the X4 Pro | WSJT-X UDP Server port must match the bridge `--rx-port` (default **2238**). |
| **Tap does nothing** | WSJT-X "Accept UDP requests" must be checked; controls port **2237** reachable from the bridge. |
| **Band change no-ops** | Ensure `rigctld` is running and the bridge was started with `--rig-host/--rig-port`. |
| Bridge won't start | `sudo journalctl -u xteink-bridge -e` for the traceback. |
| WSJT-X not on the virtual display | `systemctl status xteink-wsjtx`; confirm `xvfb` installed and `DISPLAY=:1` is free. |

---

## Manual (non-systemd) run

For testing without the service units:

```bash
cd ~/xteink-ft8/bridge
python3 xteink_bridge.py --help
python3 xteink_bridge.py
# defaults: rx 127.0.0.1:2238, controls to 127.0.0.1:2237, device on 0.0.0.0:4510
```