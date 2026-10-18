"""Main window: source toolbar, LCD, chart + stats, logging, calibration tools (apps/spec/UI-SPEC.md)."""
import os
import time
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import model
from .. import protocol as p
from ..transport import ReplayWorker, SerialWorker
from .arc import ArcMeter
from .lcd import LcdWidget

WINDOWS = [("1 min", 60), ("5 min", 300), ("30 min", 1800), ("all", None)]
INTERVALS = [0.5, 1, 2, 5, 10, 30, 60]
KEY_HOLD = 2.0     # seconds a key code stays shown
STALE_AFTER = 3    # missed polls before the LCD dims


def _real_uart(dev):
    """Linux lists 32 legacy /dev/ttyS* nodes; keep only those with a UART behind them."""
    name = os.path.basename(dev)
    if not name.startswith("ttyS"):
        return True
    try:
        return open(f"/sys/class/tty/{name}/type").read().strip() != "0"
    except OSError:
        return True


def list_ports():
    try:
        from serial.tools import list_ports as lp
        ports = sorted(x.device for x in lp.comports())
    except Exception:  # noqa: BLE001
        ports = []
    if os.path.exists("/dev/ttyS0") and "/dev/ttyS0" not in ports:
        ports.append("/dev/ttyS0")
    ports = [d for d in ports if _real_uart(d)]
    # onboard ports first (this meter is on ttyS0), then USB adapters
    return sorted(ports, key=lambda d: (not os.path.basename(d).startswith("ttyS"), d))


def fmt_num(v):
    return "–" if v is None else f"{v:.6g}"


class MainWindow(QMainWindow):
    def __init__(self, replay_path=None):
        super().__init__()
        self.setWindowTitle("IDM207 Virtual Meter (PyQt6)")
        self.worker = None
        self.reading = None
        self.ident = ""
        self.last_frame_t = 0.0
        self.key, self.key_t = "", 0.0
        self.series = model.Series()
        self.logger = model.Logger()
        self.cal_mode = None      # "backup" | "compare"
        self.compare_to = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.addLayout(self._toolbar())
        top = QHBoxLayout()
        self.lcd = LcdWidget()
        self.arc = ArcMeter()
        top.addWidget(self.lcd, 3)
        top.addWidget(self.arc, 2)
        root.addLayout(top, 3)
        mid = QHBoxLayout()
        mid.addWidget(self._chart(), 3)
        mid.addWidget(self._stats(), 1)
        root.addLayout(mid, 3)
        bottom = QHBoxLayout()
        bottom.addWidget(self._logging(), 1)
        bottom.addWidget(self._tools(), 1)
        root.addLayout(bottom)
        self.statusBar().showMessage("Not connected")

        self.ui_timer = QTimer(self, interval=250, timeout=self._tick)
        self.ui_timer.start()
        self.resize(1000, 820)
        if replay_path:
            self._start_replay(replay_path)

    # ---- layout -------------------------------------------------------------------------------
    def _toolbar(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Port:"))
        self.port_box = QComboBox(editable=True)
        self.port_box.addItems(list_ports())
        self.port_box.setMinimumWidth(160)
        row.addWidget(self.port_box)
        self.connect_btn = QPushButton("Connect", clicked=self._toggle_connect)
        row.addWidget(self.connect_btn)
        row.addWidget(QPushButton("Replay capture…", clicked=self._choose_replay))
        row.addSpacing(20)
        row.addWidget(QLabel("Mode:"))
        self.poll_radio = QRadioButton("Poll", checked=True)
        self.send_radio = QRadioButton("SEND (F4)")
        grp = QButtonGroup(self)
        for b in (self.poll_radio, self.send_radio):
            grp.addButton(b)
            row.addWidget(b)
        self.send_radio.toggled.connect(self._mode_changed)
        row.addStretch()
        return row

    def _chart(self):
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "time", units="s")
        self.curve = self.plot.plot([], [], pen=pg.mkPen("#1f6feb", width=2))
        return self.plot

    def _stats(self):
        box = QGroupBox("Statistics")
        form = QFormLayout(box)
        self.stat_labels = {k: QLabel("–") for k in ("min", "max", "mean", "count", "ol")}
        for k, name in (("min", "Min"), ("max", "Max"), ("mean", "Mean"), ("count", "Count"), ("ol", "OL")):
            form.addRow(name, self.stat_labels[k])
        self.window_box = QComboBox()
        self.window_box.addItems([w for w, _ in WINDOWS])
        form.addRow("Window", self.window_box)
        form.addRow(QPushButton("Reset", clicked=self._reset_series))
        return box

    def _logging(self):
        box = QGroupBox("Logging")
        outer = QVBoxLayout(box)
        lay = QHBoxLayout()
        outer.addLayout(lay)
        self.history = QTableWidget(0, 3)
        self.history.setHorizontalHeaderLabels(["Time", "Function", "Value"])
        self.history.horizontalHeader().setStretchLastSection(True)
        self.history.verticalHeader().setVisible(False)
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.setMinimumHeight(130)
        outer.addWidget(self.history, 1)
        lay.addWidget(QLabel("Interval"))
        self.interval_box = QComboBox()
        self.interval_box.addItems([f"{i} s" for i in INTERVALS])
        self.interval_box.setCurrentIndex(1)
        lay.addWidget(self.interval_box)
        self.start_btn = QPushButton("Start", clicked=self._log_start)
        self.stop_btn = QPushButton("Stop", clicked=self._log_stop, enabled=False)
        lay.addWidget(self.start_btn)
        lay.addWidget(self.stop_btn)
        lay.addWidget(QPushButton("Clear", clicked=self._log_clear))
        self.rows_label = QLabel("rows: 0")
        lay.addWidget(self.rows_label)
        lay.addWidget(QPushButton("Export CSV…", clicked=self._log_export))
        return box

    def _tools(self):
        box = QGroupBox("Calibration tools (read-only)")
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self.backup_btn = QPushButton("Backup calibration…", clicked=lambda: self._cal_start("backup"))
        self.compare_btn = QPushButton("Compare calibration…", clicked=lambda: self._cal_start("compare"))
        row.addWidget(self.backup_btn)
        row.addWidget(self.compare_btn)
        lay.addLayout(row)
        self.cal_bar = QProgressBar(maximum=256)
        lay.addWidget(self.cal_bar)
        self.cal_text = QPlainTextEdit(readOnly=True)
        self.cal_text.setMaximumHeight(90)
        lay.addWidget(self.cal_text)
        return box

    # ---- sources ------------------------------------------------------------------------------
    def _attach(self, worker):
        self._detach()
        self.worker = worker
        worker.send_mode = self.send_radio.isChecked()
        worker.frame.connect(self._on_frame)
        worker.status.connect(self.statusBar().showMessage)
        worker.failed.connect(self._on_failed)
        worker.cal_progress.connect(self.cal_bar.setValue)
        worker.cal_done.connect(self._cal_done)
        worker.start()
        self.connect_btn.setText("Disconnect")

    def _detach(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.connect_btn.setText("Connect")
        self.lcd.set_stale(True)
        self.arc.set_stale(True)

    def _toggle_connect(self):
        if self.worker:
            self._detach()
            self.statusBar().showMessage("Disconnected")
            return
        port = self.port_box.currentText().strip()
        if not port:
            return
        self.statusBar().showMessage(f"Connecting to {port}…")
        self._attach(SerialWorker(port))

    def _choose_replay(self):
        path, _ = QFileDialog.getOpenFileName(self, "Replay capture log", "", "Capture logs (*.log *.txt);;All files (*)")
        if path:
            self._start_replay(path)

    def _start_replay(self, path):
        frames = model.read_capture(open(path, errors="replace").read())
        w = ReplayWorker(frames)
        w.label.connect(self.statusBar().showMessage)
        self._attach(w)

    def _mode_changed(self, send):
        if self.worker:
            self.worker.send_mode = send

    def _on_failed(self, msg):
        if self.cal_mode:
            self.cal_mode = None
            self._set_cal_buttons(True)
        QMessageBox.warning(self, "IDM207", msg)
        if isinstance(self.worker, SerialWorker) and not self.worker.isRunning():
            self._detach()

    # ---- readings -----------------------------------------------------------------------------
    def _on_frame(self, t, f, from_send):
        r = p.decode(f)
        self.reading, self.last_frame_t = r, t
        self.ident = f"{r.model} · s/n {r.serial} · fw {r.firmware}"
        if r.key:
            self.key, self.key_t = r.key, t
        if self.series.add(t, r):
            self.plot.setLabel("left", r.function, units=None)
            self.arc.reset_scale()
        self.logger.interval = INTERVALS[self.interval_box.currentIndex()]
        self.logger.offer(t, r, send_mode=from_send)
        self.lcd.show_reading(r, model.annunciators(r, from_send), self.key)
        self.arc.show_reading(r)
        self._update_chart()

    def _tick(self):
        now = time.time()
        if self.key and now - self.key_t > KEY_HOLD:
            self.key = ""
        if self.worker and self.reading and now - self.last_frame_t > STALE_AFTER * 0.5 and not self.send_radio.isChecked():
            self.lcd.set_stale(True)
            self.arc.set_stale(True)
        self.rows_label.setText(f"rows: {len(self.logger.rows)}")
        self._sync_history()
        if isinstance(self.worker, SerialWorker) and self.worker.isRunning() and not self.cal_mode:
            w = self.worker
            state = "SEND mode, waiting for F4" if self.send_radio.isChecked() else f"{w.polls} polls · {w.errors} no-reply"
            self.statusBar().showMessage(f"Connected {w.port} · {self.ident} · {state}")

    def _update_chart(self):
        secs = WINDOWS[self.window_box.currentIndex()][1]
        t, v = self.series.window(secs)
        self.curve.setData(t, v)
        st = self.series.stats()
        unit = model.pretty_unit(self.reading.main.unit) if self.reading and self.reading.main else ""
        for k in ("min", "max", "mean"):
            self.stat_labels[k].setText(f"{fmt_num(st[k])} {unit}" if st[k] is not None else "–")
        self.stat_labels["count"].setText(str(st["count"]))
        self.stat_labels["ol"].setText(str(st["ol"]))

    def _reset_series(self):
        self.series.reset()
        self._update_chart()

    # ---- logging ------------------------------------------------------------------------------
    def _log_start(self):
        self.logger.interval = INTERVALS[self.interval_box.currentIndex()]
        self.logger.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _log_stop(self):
        self.logger.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _log_clear(self):
        self.logger.clear()
        self._sync_history()

    def _sync_history(self):
        """Mirror logger.rows into the history table (append new rows, keep scrolled to the end)."""
        rows, n = self.logger.rows, self.history.rowCount()
        if n > len(rows):
            self.history.setRowCount(0)
            n = 0
        if n == len(rows):
            return
        bar = self.history.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 2
        self.history.setUpdatesEnabled(False)
        self.history.setRowCount(len(rows))
        for i in range(n, len(rows)):
            t, r = rows[i]
            m = r.main
            val = model.display_text(m) if m else ""
            for col, text in enumerate((datetime.fromtimestamp(t).strftime("%H:%M:%S.%f")[:-3], r.function, val)):
                self.history.setItem(i, col, QTableWidgetItem(text))
        self.history.setUpdatesEnabled(True)
        if follow:
            self.history.scrollToBottom()

    def _log_export(self):
        if not self.logger.rows:
            QMessageBox.information(self, "IDM207", "Nothing logged yet.")
            return
        name = time.strftime("idm207-log-%Y%m%d-%H%M%S.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", name, "CSV (*.csv)")
        if path:
            with open(path, "w", newline="") as fh:
                fh.write(self.logger.csv())
            self.statusBar().showMessage(f"Saved {len(self.logger.rows)} rows to {path}", 5000)

    # ---- calibration tools --------------------------------------------------------------------
    def _set_cal_buttons(self, enabled):
        self.backup_btn.setEnabled(enabled)
        self.compare_btn.setEnabled(enabled)

    def _cal_start(self, mode):
        if not self.worker:
            QMessageBox.information(self, "IDM207", "Connect to the meter first.")
            return
        if mode == "compare":
            path, _ = QFileDialog.getOpenFileName(self, "Calibration backup to compare against", "", "Backups (*.txt);;All files (*)")
            if not path:
                return
            self.compare_to = (path, p.cal_from_text(open(path).read()))
        self.cal_mode = mode
        self._set_cal_buttons(False)
        self.cal_bar.setValue(0)
        self.cal_text.setPlainText("Reading 256 calibration entries (read-only)…")
        self.worker.request_cal()

    def _cal_done(self, cal, ident):
        mode, self.cal_mode = self.cal_mode, None
        self._set_cal_buttons(True)
        missing = [i for i, v in cal.items() if v is None]
        lines = [f"{name}: {p.cal_text(cal, a, b)}" for name, (a, b) in p.CAL_TEXT.items()]
        if missing:
            lines.append(f"no reply for {len(missing)} entries")
        if mode == "backup":
            name = time.strftime("calibration-backup-IDM207-%Y%m%d-%H%M%S.txt")
            path, _ = QFileDialog.getSaveFileName(self, "Save calibration backup", name, "Backups (*.txt)")
            if path:
                with open(path, "w") as fh:
                    fh.write(p.cal_to_text(cal, ident or None))
                lines.append(f"saved {256 - len(missing)} entries to {path}")
        elif mode == "compare" and self.compare_to:
            path, old = self.compare_to
            diff = p.cal_diff(old, cal)
            lines += [f"{i:02X}: {'----' if o is None else f'{o:04X}'} -> {'----' if n is None else f'{n:04X}'}" for i, o, n in diff]
            lines.append(f"{len(diff)} of 256 entries differ from {os.path.basename(path)}")
        self.cal_text.setPlainText("\n".join(lines))

    def closeEvent(self, e):  # noqa: N802 (Qt override)
        self._detach()
        super().closeEvent(e)
