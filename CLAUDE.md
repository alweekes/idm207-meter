# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Virtual meter, datalogger and reverse-engineered RS232 protocol for the ISO-TECH IDM207 (= APPA 207, same
protocol as the APPA 300 series / WinDMM software). Two interchangeable apps implement one shared spec.

## Safety: never send meter commands ≥ 0x80

Commands from 0x80 up are **writes** to the meter (0x80 once overwrote the meter's model name). Both apps may only
build commands `0x00` (read frame) and `0x0E` (read one calibration constant); this allow-list is enforced in
`protocol.py` / `protocol.ts` and unit-tested. Do not widen it, and keep `reverse-engineering/scripts/idm207.py`
read-only.

## Commands

Desktop app (`apps/py-meter`, Python ≥3.10, PyQt6 + pyqtgraph + pyserial):
```
cd apps/py-meter
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest                                   # all tests
.venv/bin/python -m pytest tests/test_model.py::test_logger_long_interval   # one test
.venv/bin/python -m idm207meter --replay ../../reverse-engineering/capture.log  # run without a meter
```
For headless runs (CI, scripted checks) set `QT_QPA_PLATFORM=offscreen`.

Web app (`apps/web-meter`, TypeScript + Vite + uPlot + Web Serial, Chromium browsers only):
```
cd apps/web-meter
npm ci
npm test                       # vitest run
npx vitest run -t "long interval"   # tests matching a name
npm run typecheck              # tsc --noEmit (also part of npm run build)
npm run dev                    # http://localhost:5173; add ?replay=/@fs/<abs path>/capture.log to replay
npm run build                  # static site in dist/
```

There is no linter configured.

## Architecture

**The contract lives in `apps/spec/`**, and both apps must match it:
- `UI-SPEC.md` defines behaviour (layout, sources, LCD, chart/stats, logging, calibration tools). A feature
  change goes into the spec and **both** apps, with matching tests in both suites.
- `test-vectors.json` holds 454 captured frames with their expected decodes plus the CSV header. Both test suites
  run all of it. `make_vectors.py` regenerates it from `reverse-engineering/capture.log` using the Python
  decoder. Regenerate only after a verified decoder fix, because the JSON is the reference.
- The CSV format must be byte-identical between the apps (`csv_row` / `csvRow`, `csv_line` / `csvLine`).

**Each app has the same layers, mirrored almost line for line** (Python module ↔ TS module):
- `protocol.py` ↔ `protocol.ts`: frame decode (59-byte frames starting `55 55 00 36`, checksum = sum of the first
  58 bytes mod 256, sign-magnitude values, overload = full scale + 1 count), tables, CSV, calibration file format,
  the command allow-list. The Python version is the reference implementation, and `reverse-engineering/scripts/idm207.py`
  also uses it.
- `model.py` ↔ `model.ts`: UI-free app logic (annunciators, unit prettifying, chart `Series` + stats, `ArcScale`,
  `Logger`, capture-file parsing). Most unit tests target this layer.
- `transport.py` (+ `serialio.py`) ↔ `transport.ts`: sources that emit raw frames: serial (poll every 0.5 s,
  SEND-mode listen, calibration read) and replay of a `capture.log`. Python uses QThread workers emitting Qt
  signals; web uses async `SerialSource` / `ReplaySource` with callbacks.
- `ui/main_window.py` ↔ `main.ts` + `index.html`: wiring. A 250 ms UI tick updates the status, row counter and
  history list; frames are decoded and fed to `Series`, `Logger`, LCD and arc on arrival.
- Web-only: `filelog.ts` (Log to file through the File System Access API, buffered and appended every 5 s).

**Replay mode** (`reverse-engineering/capture.log`, tab-separated `time  label  hex`) lets you test either app
end to end without hardware.

**Protocol notes**: `reverse-engineering/README.md` (full write-up) and `WinDMM300-RS232-Protocol-Summary.md`.
The vendor software and manuals are not in the repo, so paths to them in those notes only exist on the author's machine.

## Releases and deployment

- The version is in two places, `apps/py-meter/pyproject.toml` and `apps/web-meter/package.json`; keep them in step.
- A `v*` tag triggers `.github/workflows/release.yml`: tests, PyInstaller builds for Linux/Windows/macOS
  (arm64 + x86_64) and a zipped web build, all attached to a GitHub release.
- A push to `main` that touches `apps/web-meter/**` redeploys the hosted web app to GitHub Pages (`pages.yml`).
