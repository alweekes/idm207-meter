"""Background workers: serial (poll / SEND listen / calibration read) and capture-file replay.
Frames are emitted raw; the UI thread decodes them."""
import time

from PyQt6.QtCore import QThread, pyqtSignal

from . import protocol as p
from . import serialio

POLL_PERIOD = 0.5   # meter refreshes ~2x/s
NO_REPLY_LIMIT = 3


class Worker(QThread):
    frame = pyqtSignal(float, bytes, bool)    # time, frame, came from SEND mode
    status = pyqtSignal(str)
    cal_progress = pyqtSignal(int)
    cal_done = pyqtSignal(dict, bytes)        # {idx: value|None}, identification frame (may be empty)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop = False
        self.send_mode = False
        self._cal_requested = False

    def stop(self):
        self._stop = True
        self.wait(3000)

    def request_cal(self):
        self._cal_requested = True


class SerialWorker(Worker):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.polls = 0
        self.errors = 0

    def run(self):
        try:
            ser = serialio.open_port(self.port)
        except Exception as e:  # noqa: BLE001 (show any open error to the user)
            self.failed.emit(f"Cannot open {self.port}: {e}")
            return
        misses = 0
        buf = b""
        try:
            while not self._stop:
                if self._cal_requested:
                    self._cal_requested = False
                    self.status.emit("Reading calibration…")
                    ident = serialio.poll_frame(ser) or b""
                    cal = serialio.read_all_cal(ser, self.cal_progress.emit, lambda: self._stop)
                    self.cal_done.emit(cal, ident)
                    continue
                if self.send_mode:
                    buf += ser.read(256)
                    f = p.find_frame(buf)
                    if f:
                        buf = buf[buf.index(f) + p.FRAME_LEN:]
                        self.frame.emit(time.time(), f, True)
                    elif len(buf) > 4 * p.FRAME_LEN:
                        buf = buf[-p.FRAME_LEN:]
                    continue
                buf = b""
                t = time.time()
                f = serialio.poll_frame(ser)
                self.polls += 1
                if f:
                    misses = 0
                    self.frame.emit(t, f, False)
                else:
                    misses += 1
                    self.errors += 1
                    if misses == NO_REPLY_LIMIT:
                        self.status.emit("No reply from meter")
                time.sleep(max(0.0, POLL_PERIOD - (time.time() - t)))
        finally:
            ser.close()


class ReplayWorker(Worker):
    """Plays (label, frame) pairs from a capture file at POLL_PERIOD, looping."""
    label = pyqtSignal(str)

    def __init__(self, frames, period=POLL_PERIOD):
        super().__init__()
        self.frames = frames
        self.period = period

    def run(self):
        if not self.frames:
            self.failed.emit("No valid frames in the capture file")
            return
        i = 0
        while not self._stop:
            if self._cal_requested:
                self._cal_requested = False
                self.failed.emit("Calibration tools need a live meter (not available in replay)")
            label, f = self.frames[i % len(self.frames)]
            self.label.emit(f"replay {i % len(self.frames) + 1}/{len(self.frames)}: {label}")
            self.frame.emit(time.time(), f, self.send_mode)
            i += 1
            end = time.time() + self.period
            while not self._stop and time.time() < end:
                time.sleep(0.02)
