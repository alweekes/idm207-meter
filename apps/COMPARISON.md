# IDM207 virtual meter: PyQt6 vs TypeScript/Web Serial

Both apps implement the shared contract in `spec/` (protocol, UI spec, test vectors).

| | `py-meter` (PyQt6) | `web-meter` (TS + Web Serial) |
|---|---|---|
| Source lines (app code) | ~1,230 (7 modules + tests) | ~1,295 (6 modules + html/css + tests) |
| Runtime dependencies | PyQt6, pyqtgraph, pyserial (+ numpy) | uPlot only |
| Dev tooling | pytest | vite, vitest, typescript |
| Installed footprint | `.venv` 367 MB | `node_modules` 53 MB (dev only); `dist/` 80 KB |
| Distribution to users | Python env or PyInstaller bundle (not yet built) | Static files; any HTTPS/localhost host |
| Serial access | pyserial, any OS, works on `/dev/ttyS0` | Web Serial; Chrome/Edge only, user must pick port each session (or reuse a granted port) |
| Verified on live meter | Yes (re-tested: readings, log/CSV, cal compare) | Yes (readings, log/CSV, cal compare, reload reconnect) |

## Observations
- **Code size is a wash.** The protocol and model layers are near line-for-line equivalents; the
  spec + shared test vectors made the port mechanical.
- **Dependencies:** the web app ships a tiny runtime (80 KB); the Python app drags in Qt and numpy.
- **Packaging:** web is trivially deployable; Python needs PyInstaller per OS, and Qt bundles are large.
- **Serial reliability:** pyserial gives blocking reads with timeouts and works with any tty. Web
  Serial is stream-based; it needs reader-lock handling and only lists ports the browser can see.
- **Portability:** web runs on Windows/macOS/Linux/ChromeOS in Chrome/Edge, but not Firefox/Safari.
  Python/Qt runs everywhere Qt does, with no browser constraint.

## Web Serial live-test result
- **Port picker offers `ttyS0`: yes** (Chrome on Linux, user in `uucp`).
- **Picker labelling quirk:** the entries are labelled "Port 1", "Port 2" by Chrome, not by device
  name. After a second port (one with no hardware behind it) was added, `ttyS0` moved from
  "Port 1" to "Port 2". The user has to recognise the right port by position or trial, and the
  label is not stable. pyserial/PyQt takes an explicit device path (`/dev/ttyS0`), so it has no
  such ambiguity.
- **Live readings / logging / CSV export: OK** (rows were logged from the live meter and exported).
- **Calibration compare: worked** (read-only, against the restored backup).
- **Reload auto-reconnect: OK** (refresh reconnected without the picker, even with two ports granted).

## Verdict
Both apps do the job against the live meter, with the same protocol code, features and CSV format.

- **Choose the web app** if easy distribution matters: tiny runtime (80 KB build, uPlot only), nothing
  to install beyond a Chromium browser, same behaviour on Windows/macOS/Linux. Costs: Chrome/Edge only,
  a port picker with unstable "Port N" labels, and the user must grant the port.
- **Choose the PyQt app** if the user base is fixed machines or needs a robust serial setup: explicit
  device paths, no browser dependency, proven on the live meter. Costs: heavy dependencies (Qt, numpy)
  and per-OS PyInstaller builds (not yet done).
- Code size was equivalent (~1.2k lines each), so effort should not drive the choice; distribution
  and the browser constraint should.
