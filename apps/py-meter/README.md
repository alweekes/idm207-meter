# IDM207 virtual meter (Python + PyQt6)

Virtual LCD, live chart and statistics, CSV datalogging, SEND-key capture and read-only calibration
backup/compare for the ISO-TECH IDM207 over RS232. Behaviour follows `../spec/UI-SPEC.md`.

## Run
```
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'        # PyQt6, pyqtgraph, pyserial, pytest
.venv/bin/python -m idm207meter           # or: .venv/bin/idm207-meter
.venv/bin/python -m idm207meter --replay ../../reverse-engineering/capture.log   # no meter needed
```
Windows: `.venv\Scripts\python -m idm207meter`; pick the COM port in the toolbar.
Linux: your user needs access to the port (`uucp` group on Arch, `dialout` on Debian/Ubuntu).

## Layout
- `idm207meter/protocol.py`: frame decoding, tables, CSV, calibration file format, command allow-list
  (only 0x00 and 0x0E can be built). Also used by `reverse-engineering/scripts/idm207.py`.
- `idm207meter/serialio.py`: blocking pyserial helpers (poll, SEND listen, calibration read).
- `idm207meter/model.py`: Qt-free app logic: annunciators, unit names, chart series/stats, logger, capture parsing.
- `idm207meter/transport.py`: `SerialWorker` / `ReplayWorker` threads emitting raw frames.
- `idm207meter/ui/`: `LcdWidget` (painted 7-segment LCD) and `MainWindow`.

## Tests
`.venv/bin/python -m pytest` runs the shared vectors (`../spec/test-vectors.json`) plus app-logic tests.
