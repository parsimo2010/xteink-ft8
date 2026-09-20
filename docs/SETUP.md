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
* **WSJT-X_improved** (the enhanced WSJT-X fork by DG2YCB) — `install.sh`
  fetches the *latest* Raspberry Pi build from SourceForge and falls back to
  the distro `wsjtx-improved`/`wsjtx` package. It is a drop-in replacement:
  same `wsjtx` binary, same config file, same UDP protocol.
* **Hamlib** — the latest release is built into a private prefix
  (`/opt/hamlib`) so the native **QRP Labs QMX/QMX+** backend (rig model
  2057) is available even on Bookworm (whose distro hamlib predates it).
  The distro `libhamlib-utils` is kept as a fallback.
* WiFi access point: **NetworkManager** (Bookworm default — no extra packages)
  or `hostapd` + `dnsmasq` + `dhcpcd` on older Raspberry Pi OS.
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

# 1) Install systemd units + dependencies. This now also:
#    - installs the LATEST wsjtx-improved Pi .deb (fallback: distro wsjtx),
#    - builds the LATEST hamlib into /opt/hamlib (QMX backend, model 2057),
#    - installs xteink-rigctld.service: rigctld auto-detects the QRP Labs
#      QMX/QMX+ on USB and shares it between WSJT-X and the bridge, so the
#      X4 Pro's << / >> band buttons work,
#    - adds the service user to the 'dialout' group (serial access).
#    Derives the service user from SUDO_USER and the repo path from the
#    script location, so plain `sudo bash ...` does the right thing.
#    (Offline or in a hurry? SKIP_HAMLIB_BUILD=1 and/or SKIP_WSJTX_INSTALL=1.)
sudo bash bridge/scripts/install.sh

# 2) Configure the WiFi access point (SSID XTEINK-FT8 / pass ft8field,
#    network 192.168.4.1/24). Optionally override with AP_SSID/AP_PASS.
#    On Bookworm+ this creates a NetworkManager "shared" hotspot that
#    auto-connects at boot; on older OS it falls back to hostapd+dnsmasq.
sudo bash bridge/scripts/setup_ap.sh

# 3) Optional convenience: prefill callsign/grid + UDP ports into WSJT-X.
#    Everything else (rig, PTT, audio, Auto Seq) is set manually once in
#    the WSJT-X GUI - see step 4. Run as the desktop user (NOT sudo) with
#    WSJT-X CLOSED (it rewrites its INI on exit and would undo the changes).
#    Note: wsjtx-improved / WSJT-X 3.x keep the config at ~/.config/WSJT-X.ini
#    (WSJT-X 2.x used ~/.config/WSJT-X/WSJT-X.ini).
WSJTXCALL=W9XYZ WSJTXGRID=EM48 bash bridge/scripts/preseed_wsjtx.sh
```

If both automatic WSJT-X installs fail (no internet during setup), install a
`.deb` from the [wsjtx-improved files page](https://sourceforge.net/projects/wsjt-x-improved/files/)
(or the plain WSJT-X release page), then re-run `install.sh` (or just start
the services).

> **Note:** bringing up the AP disconnects the Pi from any home WiFi on the
> same adapter. Do the one-time install while on Ethernet (or before step 2),
> and use Ethernet or the AP itself for later SSH sessions.

---

## 4. Configure WSJT-X (one-time, over VNC)

The Pi runs WSJT-X on a virtual display (`:1`), so to see its window you
attach a VNC server to that display **once at home**:

```bash
# If x11vnc isn't installed yet:
sudo apt install -y x11vnc

# Start WSJT-X on the virtual display via its service, then attach VNC to it:
sudo systemctl start xteink-wsjtx.service
x11vnc -display :1 &
# -> VNC to the Pi's IP, display :0 port 5900. Over SSH use a tunnel:
#    ssh -L 5900:localhost:5900 pi@xteink
```

> Don't launch a second `wsjtx` by hand while the service is running — one
> instance owns the config and the audio device. Edit WSJT-X settings in this
> VNC session, or stop the service first
> (`sudo systemctl stop xteink-wsjtx`) before running `preseed_wsjtx.sh`.

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
* **Rig** — set to **Hamlib NET rigctl** with Network Server
  **127.0.0.1:4532** and PTT Method **CAT**, then press **Test CAT** (turns
  green once the QMX is plugged in and `xteink-rigctld` is running).
  ⚠ `xteink-rigctld` **owns the QMX's serial port** — do NOT point WSJT-X
  directly at `/dev/ttyACM0` while that service runs (two processes cannot
  open the port; Test CAT will never go green). If you prefer direct serial
  CAT, run `sudo systemctl disable --now xteink-rigctld` first — the X4 Pro's
  band buttons then stop working (`qsy` replies `not_supported`).
* **Audio** — select the **QMX USB sound card** for both input and output
  (it appears as a normal USB audio device in the dropdowns; `aplay -l`
  shows it as a card). Do NOT force `snd_usb_audio index=0` or pin
  `/etc/asound.conf` to it — on the Pi the HDMI/vc4 card claims index 0 and
  the QMX probe fails with error -16 ("cannot create card instance").
* **Auto Seq** — enable for hands-free completion of FT8 QSOs.
* **Include non-default decode messages**: keep default (off); the bridge only
  cares about CQ/QRZ.

> **Band change works by default** with the QRP Labs **QMX/QMX+**:
> `xteink-rigctld.service` runs one `rigctld` that owns the radio's USB serial
> port, and *both* WSJT-X (as "Hamlib NET rigctl") and the bridge talk to it
> on `127.0.0.1:4532`. The X4 Pro's `<<`/`>>` buttons therefore retune the
> radio *and* the WSJT-X session — no extra steps. The rig is auto-detected
> (QMX backend 2057 on hamlib ≥ 4.6.1 — `install.sh` builds the latest hamlib
> into `/opt/hamlib` for exactly this; older hamlib falls back to the
> TS-480-compatible backend, which the QMX's CAT protocol also satisfies).
> A different radio? Edit `/etc/default/xteink-rigctld`
> (`RIG_MODEL`/`RIG_FILE`) and `sudo systemctl restart xteink-rigctld`.
> With no radio attached the buttons simply report `not_supported` (harmless).

---

## 5. Start the services & verify

```bash
sudo systemctl enable xteink-bridge.service xteink-wsjtx.service xteink-rigctld.service
sudo systemctl start  xteink-bridge.service xteink-wsjtx.service xteink-rigctld.service

# Watch startup / errors:
sudo journalctl -u xteink-bridge -f
sudo journalctl -u xteink-wsjtx -f
sudo journalctl -u xteink-rigctld -f
```

The bridge logs `bridge ready: rx=127.0.0.1:2238 ... device=0.0.0.0:4510`.

---

## 6. First run (field)

1. Power the Pi. It boots the AP + WSJT-X + bridge automatically (~1–2 min).
2. Power the X4 Pro. It joins the AP and connects to `192.168.4.1:4510`.
   Until the first successful link it shows a **NET DIAGNOSTIC** screen: SSID,
   WiFi status code, whether its own scan sees the AP (with RSSI), its DHCP IP,
   and TCP try/fail counts — then it auto-switches to decodes. Afterwards the
   status bar shows: **NO-SSID**/**NO-WIFI** (not associated), **`192.168.4.x`
   NO-LINK** (on WiFi, bridge unreachable), or no tag (link up).
3. The X4 Pro fills with CQ decodes after the first decode cycle.
4. Tap a CQ to answer it; WSJT-X drives the QSO to completion. Use the bottom
   bar for **CQ / band << >> / re-fetch / Halt**.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Device shows **NO-WIFI / NO-SSID** | Not associated to the AP. `NO-SSID` = AP not even visible: AP up? (Bookworm: `nmcli con show xteink-ap`; legacy: `hostapd` running). Credentials/SSID in firmware `config.h` match `setup_ap.sh`? 2.4 GHz? Re-flash after any config.h change. |
| Diagnostic shows **LINK ... last drop 211** | `NO_AP_FOUND_IN_AUTHMODE_THRESHOLD`: the ESP32 refuses APs below WPA2-PSK — the NM hotspot came up with weaker/mixed security. Re-run `sudo bash bridge/scripts/setup_ap.sh` (now pins `proto rsn` + CCMP + `pmf disable`) and reconnect. Verify: `nmcli -f 802-11-wireless-security.key-mgmt,802-11-wireless-security.proto,802-11-wireless-security.pmf con show xteink-ap`. |
| Device shows **`<ip>` NO-LINK** | WiFi + DHCP are fine (IP shown); the bridge TCP (port 4510) is unreachable: `systemctl status xteink-bridge`, and `sudo journalctl -u xteink-bridge -e`. Bridge listening on 0.0.0.0:4510? |
| Bridge logs **unsupported schema 2** repeatedly | Fixed in current code (the bridge answers WSJT-X heartbeats to negotiate schema 3). `cd ~/xteink-ft8 && git pull && sudo systemctl restart xteink-bridge`. |
| AP not up after reboot | Bookworm: `sudo nmcli con up xteink-ap` and check `nmcli -f NAME,AUTOCONNECT con show`. Legacy: `systemctl status hostapd dnsmasq dhcpcd`. |
| **No decodes** on the X4 Pro | WSJT-X UDP Server port must match the bridge `--rx-port` (default **2238**). |
| **Tap/CQ does nothing** (bridge logs the send, radio stays silent) | WSJT-X "Accept UDP requests" must be checked AND listening: `sudo ss -lunp \| grep 2237` should show the wsjtx process. Watch the WSJT-X Tx5 field while tapping CQ — if the text appears, the packet arrived. Then `sudo systemctl restart xteink-bridge` to pick up the send-from-rx-socket fix. |
| **Band change no-ops** | `systemctl status xteink-rigctld`; QMX plugged in (`ls /dev/serial/by-id/` shows a `QRP_Labs` entry)? Service user in `dialout`? Try `sudo journalctl -u xteink-rigctld -e`. Override in `/etc/default/xteink-rigctld`. |
| **No audio / TX silent** | QMX card visible in `aplay -l`? If dmesg shows "cannot create card instance" / probe error -16, remove any `snd_usb_audio index=0` modprobe file and `/etc/asound.conf` pin, reboot, then pick the QMX device in WSJT-X Settings → Audio. |
| WSJT-X "Test CAT" red | If Rig is a *direct serial* rig (e.g. QRP Labs QMX on /dev/ttyACM0): `xteink-rigctld` is holding the port — either set Rig to *Hamlib NET rigctl* @ `127.0.0.1:4532` (recommended; band buttons keep working) or `sudo systemctl disable --now xteink-rigctld`. Check `sudo journalctl -u xteink-rigctld -e`. |
| WSJT-X service fails: **EXEC spawn ... permission denied** | Script lost its exec bit (old checkout). `git pull` (scripts are committed 755 now) or `chmod +x ~/xteink-ft8/bridge/scripts/*.sh && sudo systemctl restart xteink-wsjtx`. |
| Bridge won't start | `sudo journalctl -u xteink-bridge -e` for the traceback. |
| WSJT-X not on the virtual display | `systemctl status xteink-wsjtx`; confirm `xvfb` installed and `DISPLAY=:1` is free. |

---

## Manual (non-systemd) run

For testing without the service units:

```bash
cd ~/xteink-ft8/bridge
python3 xteink_bridge.py --help
python3 xteink_bridge.py
# defaults: rx 127.0.0.1:2238, controls to 127.0.0.1:2237, device on 0.0.0.0:4510,
#           rigctld on 127.0.0.1:4532 (--rig-host "" disables band control)
```