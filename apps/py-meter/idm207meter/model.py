"""App logic without Qt: annunciators, unit names, chart series/stats, data logger, capture files.
Behaviour follows apps/spec/UI-SPEC.md."""
import math
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import protocol as p

PRETTY_UNITS = {"Ohm": "Ω", "kOhm": "kΩ", "MOhm": "MΩ", "uF": "µF", "us": "µs", "degC": "°C", "degF": "°F",
                "Delta": "Δ"}

ANNUNCIATORS = ["AUTO", "DC", "AC", "MAX", "MIN", "PEAK", "AH", "REF", "Δ", "%", "dB", "dBm", "MEM", "SETUP",
                "HI", "LO", "RS232"]


def pretty_unit(unit):
    return PRETTY_UNITS.get(unit, unit)


def display_text(d):
    """Display text as on the LCD (number/OL/----/[label]) with a pretty unit."""
    if d is None:
        return ""
    s = str(d)
    return s[: len(s) - len(d.unit)] + pretty_unit(d.unit) if d.unit and s.endswith(d.unit) else s


def annunciators(r, send_mode=False):
    """Set of lit annunciators for a reading (see UI-SPEC.md)."""
    subs = {d.sub for d in (r.main, r.left, r.right) if d}
    on = set()
    if r.autorange:
        on.add("AUTO")
    if "DC" in r.function:
        on.add("DC")
    if "AC" in r.function:
        on.add("AC")
    if subs & {"max", "max-min"}:
        on.add("MAX")
    if subs & {"min", "max-min"}:
        on.add("MIN")
    if any(s.startswith("peak") for s in subs):
        on.add("PEAK")
    for sub, name in (("auto hold", "AH"), ("ref", "REF"), ("delta", "Δ"), ("%", "%"), ("dB", "dB"), ("dBm", "dBm")):
        if sub in subs:
            on.add(name)
    if subs & {"store", "recall", "number"}:
        on.add("MEM")
    if "setup" in subs:   # SETUP menu pages (not the HISET/LOSET labels)
        on.add("SETUP")
    if r.limit:
        on.add(r.limit)
    if send_mode:
        on.add("RS232")
    return on


class Series:
    """Main-value time series for the chart; restarts when function or unit changes."""

    def __init__(self):
        self.reset()

    def reset(self, key=None):
        self.key = key
        self.t0 = None
        self.t, self.v = [], []
        self.ol = 0

    def add(self, t, r):
        """Add a reading; returns True if a new series was started."""
        key = (r.function, r.main.unit if r.main else "")
        started = key != self.key
        if started:
            self.reset(key)
        if self.t0 is None:
            self.t0 = t
        m = r.main
        if m and m.overload:
            self.ol += 1
        if m and m.value is not None:
            self.t.append(t - self.t0)
            self.v.append(m.value)
        return started

    def window(self, seconds=None):
        if not seconds or not self.t:
            return self.t, self.v
        cut = self.t[-1] - seconds
        i = next((k for k, x in enumerate(self.t) if x >= cut), len(self.t))
        return self.t[i:], self.v[i:]

    def stats(self):
        if not self.v:
            return {"min": None, "max": None, "mean": None, "count": 0, "ol": self.ol}
        return {"min": min(self.v), "max": max(self.v), "mean": sum(self.v) / len(self.v),
                "count": len(self.v), "ol": self.ol}


def nice_ceil(a):
    """Smallest 1-2-5 x 10^n that is >= a (1 for a <= 0)."""
    if a <= 0:
        return 1.0
    e = math.floor(math.log10(a))
    m = a / 10 ** e
    return next(s for s in (1, 2, 5, 10) if m <= s * (1 + 1e-9)) * 10.0 ** e


class ArcScale:
    """Full scale for the arc meter: 1-2-5 steps, grows at once, shrinks below 40 % (no flapping).
    Zero-left until a negative value is seen, then zero-centred. Reset when the series restarts."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.fs, self.bipolar = 1.0, False

    def update(self, v):
        if v is None:
            return
        a = abs(v)
        self.bipolar = self.bipolar or v < 0
        if a > self.fs or (a > 0 and a < 0.4 * self.fs):
            self.fs = nice_ceil(a)

    def fraction(self, v):
        """Needle/bar position 0..1 along the arc (clamped)."""
        x = v / self.fs
        f = 0.5 + x / 2 if self.bipolar else x
        return min(1.0, max(0.0, f))

    def ticks(self, n=5):
        """[(fraction, value)] major ticks."""
        lo = -self.fs if self.bipolar else 0.0
        return [(i / n, lo + (self.fs - lo) * i / n) for i in range(n + 1)]


HISTORY_ROWS = 2000  # rows kept in memory (and in the history list) while logging to a file
TICK_SLACK = 0.1  # s; a reading this much before the next tick still counts (timestamps jitter by ~1 ms)


def csv_header():
    return "iso_time," + p.CSV_HEADER


def csv_line(t, r):
    return f"{datetime.fromtimestamp(t).isoformat(timespec='milliseconds')},{p.csv_row(t, r)}"


@dataclass
class Logger:
    """Data log (UI-SPEC.md: Logging). With a sink, every row is also passed to it as a CSV line and only the
    last HISTORY_ROWS stay in memory, so a file log can run for days."""
    interval: float = 1.0
    running: bool = False
    rows: list = field(default_factory=list)  # (epoch, Reading)
    count: int = 0                             # rows logged since the last clear (rows may be trimmed)
    sink: object = None                        # callable(csv_line) or None
    _last_tick: float = 0.0
    _last_frame_t: float = -1.0

    def start(self):
        self.running = True
        self._last_tick = 0.0

    def stop(self):
        self.running = False

    def clear(self):
        self.rows.clear()
        self.count = 0
        self._last_frame_t = -1.0

    def offer(self, t, r, send_mode=False):
        """Called for every new reading; records it if logging is running and the interval allows."""
        if not self.running:
            return False
        if not send_mode:
            if t - self._last_tick < self.interval - TICK_SLACK:
                return False
            # stay on the interval grid even if readings arrive a little early or late
            self._last_tick = t if t - self._last_tick > 2 * self.interval else self._last_tick + self.interval
        if t == self._last_frame_t:
            return False
        self._last_frame_t = t
        self.rows.append((t, r))
        self.count += 1
        if self.sink:
            self.sink(csv_line(t, r))
            if len(self.rows) > HISTORY_ROWS:
                del self.rows[: len(self.rows) - HISTORY_ROWS]
        return True

    def csv(self):
        lines = [csv_header()] + [csv_line(t, r) for t, r in self.rows]
        return "\n".join(lines) + "\n"


def read_capture(text):
    """Frames from a poll.py/capture.log file: [(label, frame_bytes)]."""
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            f = p.find_frame(bytes.fromhex(parts[2]))
        except ValueError:
            continue
        if f:
            out.append((parts[1], f))
    return out


def now():
    return time.time()
