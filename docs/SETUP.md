# Field deployment / setup

## 1. Raspberry Pi — WiFi AP (no internet required)

The Pi creates its own network so the X4 Pro can reach it in the field.

```bash
# install hostapd + dnsmasq
sudo apt install hostapd dnsmasq
```

Create `/etc/hostapd/hostapd.conf`:

```
interface=wlan0
driver=nl80211
ssid=XTEINK-FT8
hw_mode=g
channel=6
wmm_enabled=0
wpa=2
wpa_passphrase=ft8field
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

And configure a static IP on `wlan0` (e.g. `192.168.4.1/24`) and dnsmasq to
serve `192.168.4.2 - 192.168.4.20`. Any standard Pi hotspot guide works; the
bridge listens on `0.0.0.0:4510`, so the X4 Pro connects to `192.168.4.1:4510`.

## 2. WSJT-X configuration

Open **File → Settings → Reporting**:

* **UDP Server**: `127.0.0.1` port **2238**  ← where WSJT-X *sends* messages
  (the bridge binds this port to receive).
* **Accept UDP requests**: **checked**  ← WSJT-X *listens* on **2237** for the
  bridge's control messages (Reply / FreeText / HaltTx / Clear).

> Why two ports: WSJT-X sends *out* and listens *in* on the same port number by
> default. Since the bridge runs on the same host, we move the *outgoing*
> destination to 2238 so the two socket roles don't collide. The bridge receives
> on 2238 and sends controls to 127.0.0.1:2237.

* **Maximum number of harmonic decodes**: whatever you prefer.
* **Include non-default decode messages**: keep default (off) — the bridge only
  cares about CQ/QRZ anyway.
* Set your **Station Callsign** and **Grid** (used in the CQ message).

## 3. Run the bridge

```bash
cd bridge
python3 xteink_bridge.py --help
python3 xteink_bridge.py                # defaults: Rx 127.0.0.1:2238, controls to 127.0.0.1:2237, device on 0.0.0.0:4510
```

Use `--device-if` / `--listen` to bind the device server to a specific address
if needed. Run under `systemd` or `tmux` in the field.

### Optional: band change via rigctld

Start Hamlib `rigctld` (or point WSJT-X at it) and run the bridge with:

```bash
rigctld --model=<MODEL> --rig-file=/dev/ttyUSB0 --set-conf=... &
python3 xteink_bridge.py --rig-host 127.0.0.1 --rig-port 4532
```

If `rigctld` is unreachable the `qsy` command degrades to `not_supported`.

## 4. Firmware — build and flash

See `firmware/README.md`. Prereqs: PlatformIO Core.

```bash
cd firmware
pio run -e x4pro                       # compile
pio run -e x4pro -t upload             # flash over USB
```

Before flashing, set the WiFi credentials and bridge address in
`firmware/include/config.h` (SSID `XTEINK-FT8`, password, `BRIDGE_HOST
192.168.4.1`, `BRIDGE_PORT 4510`).

## 5. First run

1. Boot the Pi, verify the AP is up and the bridge shows `listening`.
2. Power the X4 Pro; it should join the AP and connect to the bridge (the home
   screen shows *Connected*).
3. Start WSJT-X; the X4 Pro fills with CQ decodes within a decode cycle.
4. Tap a CQ to answer it; WSJT-X drives the QSO to completion.

## Troubleshooting

* **Device shows *No link*:** check the AP is on, credentials match, and the
  bridge is listening on an address the device can reach.
* **No decodes:** check WSJT-X UDP Server port matches the bridge's `--rx-port`
  (default 2238) and that WSJT-X is receiving.
* **Tap does nothing:** confirm WSJT-X "Accept UDP requests" is checked and the
  controls port (2237) is reachable from the bridge.
* **Band change no-ops:** ensure `rigctld` is running and `--rig-host/--rig-port`
  are correct.