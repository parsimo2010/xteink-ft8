# xteink-ft8 — Release plan (future)

This documents how we will publish prebuilt releases so a ham operator can
install without building anything. **No release is published yet** — we are
waiting until the firmware has been validated on real hardware.

## Goal

A GitHub **Release** per version with ready-to-run artifacts:

| asset | what it is | who needs it |
|-------|-----------|--------------|
| `xteink-ft8-firmware-<ver>.zip` | bootloader + partitions + OTA stub + app (`.bin`) + `flash.sh` | anyone flashing the X4 Pro |
| `xteink-ft8-bridge-<ver>.zip` | the Python bridge + `scripts/` + README | Raspberry Pi |
| (Release notes) | what changed, install link to docs | everyone |

## How it's produced

`.github/workflows/release.yml` builds it automatically when a maintainer tags
a release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow (CI only; it does not run on normal commits):

1. Check out the repo with submodules.
2. Set up Python 3.12 (the Arduino-ESP32 toolchain rejects 3.14).
3. Install PlatformIO and run `pio run -e x4pro`.
4. Package the four firmware blobs + a `flash.sh` into a firmware zip.
5. Package `bridge/` (Python + scripts, minus `.pio`/`__pycache__`) into a
   bridge zip.
6. Create a GitHub Release and attach both zips with versioned file names.

## Before the first release (validation checklist)

- [x] Firmware boots on a real X4 Pro; e-ink panel and touch confirmed
      (2026-09-12 bring-up: portrait UI, GT911 tap feedback, page buttons, and
      hold-power deep-sleep all verified on hardware).
- [ ] X4 Pro joins the Pi AP and connects to the bridge.
- [ ] CQ decodes appear; tapping a CQ completes a QSO with WSJT-X.
- [ ] Headless Pi boot (power on → no keyboard/mouse/screen) brings up
      AP + WSJT-X + bridge.
- [ ] `flash.sh` works from a fresh download on Linux and Windows.
- [x] `test_bridge.py` passes (10/10; CI runs it too).

## Versioning

Semantic versioning on `main`:
* `v0.x.0` — prototype steps (0.1.0 = first field test).
* Bump the minor when the field workflow is stable.

Keep a `CHANGELOG.md` summarizing FTFI (fixed/tested/added) per version.

## Release process (maintainer)

```bash
# update CHANGELOG.md, bump firmware version in platformio.ini if needed
git add -A && git commit -m "Prepare v0.1.0"
git tag -a v0.1.0 -m "First field-test release"
git push origin main
git push origin v0.1.0        # triggers the release workflow
```

## Notes

* The bridge is pure Python 3 stdlib — the zip needs no `pip install`.
* The firmware zip is self-contained; flashing needs only `esptool` (or
  PlatformIO), never a compiler.
* FreeInk SDK is MIT; see the root `LICENSE`.