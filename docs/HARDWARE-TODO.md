# Hardware validation TODO — the 2026-10-27 review fixes

Everything in `fix/review-2026-10-27` (12 commits, now on `main`) was verified by
**tests and a compile**, not by hardware. This file lists exactly what still needs a
real Pi / X4 Pro / Sticky / QMX in front of you, and what "good" looks like for each.

Issues **#1, #2, #3, #4, #6** were closed on the strength of automated tests.
Issues **#5, #7, #8, #10, #11, #12 stay open** until the matching check below passes.
Report results in any shape — paste a `journalctl` excerpt, say "fine", or say "it did
X instead" and I will pick it up.

Version under test: firmware `-DXTEINK_FW_VERSION='"0.1.0-dev"'` (shown on the device),
bridge from `main`.

---

## 1. Bridge survives a device that stops reading — issue 1

*Why it matters:* this was the Blocker. Before, one powered-off device blocked the
single WSJT-X receive thread and the whole station silently went deaf while systemd
reported healthy.

```bash
# terminal A
sudo journalctl -u xteink-bridge -f
# terminal B
systemctl is-active xteink-bridge
```

1. Link the device, watch decodes arrive.
2. **Power the device off completely** (not sleep — battery out / off).
3. Wait 3–5 min. Then look for: the bridge **still running**, no traceback, and after
   the idle reap one line like
   `('192.168.4.x', 5xxxx) silent for 120s (no ping?); reaping link`.
4. Power the device back on → it must rejoin WiFi, reconnect TCP and show decodes
   again within ~60 s (5 s reconnect interval + WiFi association).
5. With two devices: keep one decoding while the other is powered off. **The live one
   must never stutter.** This is the actual regression the fix buys.

Record: did the idle-reap line appear, did the device come back, did decodes keep
flowing throughout.

## 2. Idle link must NOT be reaped while healthy — issue 1 (new behaviour, watch this one)

The bridge now drops a connection that has been **silent for 120 s**. The firmware
pings every 20 s, so a healthy link has ~6x margin — but this is the one place where
the fix can create a new symptom.

1. Link up, then **touch nothing for 10 minutes** (station decoding, nobody taps the
   screen).
2. Expect: no repeated `reaping link` / reconnect cycle. The status bar keeps its IP
   with no `NO-LINK`.
3. If you see a reconnect roughly every 2 minutes, the ping is not being sent or not
   reaching the bridge — that is a real bug; capture the device serial log
   (`[net] ...` @115200) and the bridge log for one cycle.

## 3. Framing never desyncs under real traffic — issues 7 and 8

Changes: static 16 KB rx scratch (no per-frame `new[]`), chunked reads, rx queue 6
frames / 24 KB, `write_all()` + peek-then-commit on TX.

```bash
# device serial @115200 — the three lines that mean trouble:
#   [net] rx queue full, dropped a N byte frame
#   [net] write failed mid-frame; dropping link to re-sync
#   [net] bridge link DOWN
```

1. Leave the device linked and decoding for **2+ hours** (a busy FT8 band; a real
   contest band if you have one). Every decode is a receive through the new buffer.
2. Check the bridge log for `bad frame length` — it should now be **absent**. Before
   the change, a partial write produced exactly that plus a socket close.
3. Check the device serial for the three lines above. Occasional `rx queue full` under
   a heavy push is acceptable and self-heals; `write failed mid-frame` means the new
   TX path hit a real wall — keep the log.
4. Heap: static RAM went **51.6 KB → 67.9 KB** by design (that 16 KB is the point), so
   the boot memory line looking bigger is expected and not a regression. The thing we
   were removing is *unbounded* per-frame heap churn — the practical symptom of the old
   bug was decodes stopping hours in with the link still UP. **If decodes ever stop
   while `<ip>` shows no `NO-LINK`, capture serial immediately** — that is the failure
   this change targets.
5. Optional, would make this measurable instead of inferred: print `ESP.getFreeHeap()`
   on the NET DIAGNOSTIC screen. Say the word and I will add it.

## 4. QSY failure is now reported honestly — issue 5

`RPRT` is parsed and a rejection answers `qsy_failed` instead of `ok_dispatch`.
Simulated in tests; needs a real rigctld + QMX to confirm the reply shape and that the
device behaves.

```bash
sudo journalctl -u xteink-bridge -f | grep -i qsy
systemctl status xteink-rigctld
```

1. Normal case: tap `>>` / `<<` on the device → log shows `qsy to <freq> Hz` and the
   QMX + WSJT-X follow. If it works, the parser accepts a real `RPRT 0`.
2. Failure case, pick the easiest you have:
   - unplug the QMX USB, then tap a band → expect
     `qsy to ...: rigctld unreachable ...` → device gets `not_supported`;
   - or stop the service (`sudo systemctl stop xteink-rigctld`) and tap a band;
   - or point the bridge at a wrong port (`--rig-port 4599`).
3. A genuine **rig rejection** (`RPRT` non-zero → `qsy_failed`) is the interesting one
   and the hardest to provoke: try a band the rig cannot reach, or issue QSY while the
   rig is in a menu/TX state. If you cannot provoke it, that is fine — say so, and we
   close #5 on the simulated evidence.
4. Known gap, not a regression: the **firmware ignores `qsy_failed`** today, so a
   refused QSY leaves the old band on screen. On-screen reporting is a follow-up
   firmware change.

## 5. Headless audio group — issue 11 (you said you'd do this one)

`install.sh` now grants `audio` as well as `dialout`, and the units set
`AuxGroups=audio dialout`. Run on a representative Pi (after `git pull` +
`sudo bash bridge/scripts/install.sh` + `sudo systemctl daemon-reload`):

```bash
ls -l /dev/snd                        # group/mode of pcmC* controlC*
getent group audio dialout
id pi
systemctl show -p User,auxGroups xteink-wsjtx
sudo -u pi aplay -l && sudo -u pi arecord -l
journalctl -u xteink-wsjtx | grep -iE 'alsa|cannot open|permission denied'
```

Pass = the QMX card is listed by `sudo -u pi arecord -l` **and** WSJT-X decodes
headless. If it already worked before this change, say so — the change is additive and
harmless, and we close on that.

## 6. Release artifacts — issue 10 (first tag only)

`release.yml` now fails the job instead of shipping a zip with a missing
`boot_app0.bin`. Only exercisable by cutting a tag, which per `docs/RELEASE.md` waits
for the checks above.

1. Push a `v0.1.0` tag, open the workflow run, and confirm in the log:
   the four `test -s` assertions ran and each `unzip -l` listing shows
   `bootloader.bin partitions.bin boot_app0.bin firmware.bin flash.sh`.
2. Confirm the bridge zip contains `test_bridge.py` and that the job executed it
   from inside the staged directory.
3. Download both firmware zips and run `flash.sh` on **Linux and Windows** once each
   (docs/FLASHING.md). Note whether `esptool.py` exists on your install — the scripts
   call `esptool.py`, which is the deprecated alias and is **not** created by every
   esptool 5.x install (this Windows venv only has `esptool`). Worth a look before you
   hand a zip to anyone.

## 7. Field regressions worth watching while you are out there

Not tied to one issue; each is a place where these commits could show up in use.

- [ ] **CQ button keys the radio** — still the standing open field bug from
      `AGENTS.md`, untouched by this batch. Watch the WSJT-X Tx5 field when you tap CQ.
- [ ] **`CQ DX …` and `CQ POTA …` stations now appear in the list** (issue 4). If the
      list looks wrong or a station's callsign looks off, that is the new classifier —
      tell me the exact decoded string.
- [ ] **Tapping a decode never returns `no_such_decode`** (issue 2, the race). If you
      see it once, note the time; a one-off is now evidence, not a mystery.
- [ ] **A 6-character callsign station**: `CQ <call> <grid>` is 14 chars, so the CQ
      button returns `text_rejected` by design. If that bites in practice, add
      `--max-text 14` to `ExecStart` in `/etc/systemd/system/xteink-bridge.service`.
- [ ] **Sticky (`env:sticky`) first boot** — never flashed, so everything in
      `docs/RELEASE.md` item 6 applies, plus: NET DIAGNOSTIC must read
      `DEV sticky rot 3 fw 0.1.0-dev`.
- [ ] **Device selection guard works**: `pio run -e <a env without -DFREEINK_DEVICE_*>`
      should now fail with "No device selected" instead of building X4 Pro pins.

## What was deliberately NOT done (so nobody mistakes silence for tested)

- No authentication handshake on TCP 4510 (tracked as **issue 13**) — needs protocol
  changes on both ends. The port validates input but still trusts the network: keep it
  on the private AP and never expose it beyond that.
- No systemd `PrivateTmp=` / `ProtectSystem=` hardening: `PrivateTmp` would break the
  documented x11vnc workflow (X11 socket in `/tmp`) and `ProtectSystem=strict` would
  stop WSJT-X writing its INI in `$HOME`. Needs a Pi to get right.
- No `CHANGELOG.md`; WiFi credentials are still literals in `config.h`.
- `Replay` / WSPR decode payloads are stubbed, not parsed — their real layouts were not
  guessed.
