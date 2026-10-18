"""ISO-TECH IDM207 (APPA 300-series) RS232 protocol: pure decoding, no I/O.

Verified against a real meter (fw 0.00.06) on 2026-10-17; see reverse-engineering/README.md.
The shared test vectors in apps/spec/test-vectors.json are generated from this module.
"""
import time
from dataclasses import dataclass, field

POLL = bytes([0x55, 0x55, 0x00, 0x00, 0xAA])
HEADER = bytes([0x55, 0x55, 0x00, 0x36])
FRAME_LEN = 59

FUNCTIONS = {
    # rotary: {sub-mode: name}
    0x01: {0: "V DC", 1: "V AC", 2: "V AC+DC"},
    0x02: {0: "mV DC", 1: "mV AC", 2: "mV AC+DC"},
    0x03: {0: "Ohm", 1: "Low Ohm"},
    0x04: {0: "Diode", 1: "Continuity"},
    0x05: {0: "mA DC", 1: "mA AC", 2: "mA AC+DC"},
    0x06: {0: "A DC", 1: "A AC", 2: "A AC+DC"},
    0x07: {0: "Capacitance"},
    0x08: {0: "Frequency", 1: "Duty cycle"},
    0x09: {0: "Temp C", 1: "Temp F"},
}

UNITS = {
    0x00: "", 0x01: "V", 0x02: "mV", 0x03: "A", 0x04: "mA", 0x05: "dB",
    0x06: "dBm", 0x07: "nF", 0x08: "uF", 0x09: "mF", 0x0A: "Ohm",
    0x0B: "kOhm", 0x0C: "MOhm", 0x0D: "%", 0x0E: "Delta", 0x0F: "Hz",
    0x10: "kHz", 0x11: "MHz", 0x12: "degC", 0x13: "degF", 0x14: "s",
    0x15: "ns", 0x16: "us", 0x17: "ms",
}

SUBCODES = {
    0x00: "", 0x01: "input", 0x02: "frequency", 0x03: "period", 0x04: "duty",
    0x05: "ambient", 0x06: "time stamp", 0x07: "load", 0x08: "number",
    0x09: "store", 0x0A: "recall", 0x0B: "reset", 0x0C: "auto hold",
    0x0D: "max", 0x0E: "min", 0x0F: "max-min", 0x10: "peak max",
    0x11: "peak min", 0x12: "peak max-min", 0x13: "set high", 0x14: "set low",
    0x15: "high", 0x16: "low", 0x17: "delta", 0x18: "%", 0x19: "ref",
    0x1A: "dBm", 0x1B: "dB", 0x1C: "send", 0x1D: "setup", 0x1E: "set beeper",
    0x1F: "set auto power-off", 0x20: "set backlight", 0x21: "set hazard",
    0x22: "set line frequency", 0x23: "set dBm load", 0x24: "set reset",
    0x25: "blank", 0x26: "probe", 0x27: "error", 0x28: "fuse",
}

# key code (byte 29): momentary, held for ~1 s after a press, otherwise 00
# names as on the IDM207 front panel (secondary function used when editing values in brackets)
KEYS = {0x01: "F1", 0x02: "F2", 0x03: "F3", 0x04: "F4", 0x05: "Light(+)", 0x06: "Bar(-)",
        0x07: "Digit(<)", 0x08: "Range(>)", 0x09: "Circle", 0x0A: "Blue"}

# point code -> number of decimal places
DECIMALS = {0x00: 0, 0x01: 1, 0x02: 2, 0x04: 3, 0x08: 4}

# Overload is sent as full scale + 1 count: 40001 (40000-count), 4001 (4000-count, DIGIT key),
# 2001 (continuity). 4001 is also a valid 40000-count value, so it's only treated as OL when
# autoranging above the lowest range (autorange would have stepped down for a real 4001-count reading).
OVERLOAD = {2001, 40001}
OVERLOAD_4000 = 4001

# Only these commands may ever be sent: 00 = read all, 0E = read calibration entry.
# Commands >= 0x80 write EEPROM (0x80 overwrote the model name once); 0x8x/0x9x are calibration writes.
ALLOWED_COMMANDS = {0x00, 0x0E}

# Calibration EEPROM: 256 16-bit entries, read with command 0E + index (read-only, no password needed;
# the same request CalWin300 uses). Entries DD-E8 hold text: APPA model code, model name, serial.
CAL_READ = 0x0E
CAL_REPLY_LEN = 8
CAL_TEXT = {"APPA model": (0xDD, 0xE0), "model name": (0xE1, 0xE4), "serial": (0xE5, 0xE8)}

CSV_HEADER = "time,function,main,main_unit,main_sub,main_flag,left,left_unit,left_sub,right,right_unit,right_sub"


def signed(lo, hi, pole):
    """Sign-magnitude 3-byte value: pole byte > 0x7F means negative."""
    mag = lo | hi << 8
    return -mag if pole > 0x7F else mag


@dataclass
class Display:
    raw: int
    decimals: int
    unit: str
    sub: str
    overload: bool
    blank: bool

    @property
    def value(self):
        if self.overload or self.blank or self.label_only:
            return None
        return self.raw / 10 ** self.decimals

    @property
    def label_only(self):
        """Display shows only a text label (e.g. HISET): no unit, just a sub-code.
        A stray value can appear for one frame while a label screen opens, so ignore it,
        except for 'number' (memory location) which is a unitless count."""
        return not self.unit and self.sub not in ("", "input", "number")

    def __str__(self):
        if self.label_only:
            return f"[{self.sub}]"
        if self.blank:
            return f"---- {self.unit}".strip()
        if self.overload:
            return f"OL {self.unit}".strip()
        return f"{self.value:.{self.decimals}f} {self.unit}".strip()


@dataclass
class Reading:
    model: str
    serial: str
    firmware: str
    function: str
    range_code: int
    autorange: bool
    key: str
    main: Display
    left: Display | None
    right: Display | None
    raw: dict = field(default_factory=dict)  # uncalibrated A/D, DC, AC fields

    @property
    def limit(self):
        """'HI'/'LO' when the main reading is beyond a HIGH/LOW limit (right display while
        setting it, left once compare is active). The frame itself carries no HI/LO flag."""
        m = self.main
        if not (m and m.value is not None and m.sub == "input"):
            return ""
        for d in (self.left, self.right):
            if d and d.value is not None:
                if d.sub == "high" and m.value > d.value:
                    return "HI"
                if d.sub == "low" and m.value < d.value:
                    return "LO"
        return ""


def decode_display(d, secondary):
    lo, hi, pole, point, unit, sub = d
    if unit == 0 and sub == 0 and lo == hi == 0:
        return None  # display not in use
    raw = signed(lo, hi, pole)
    return Display(
        raw=raw,
        decimals=DECIMALS.get(point, 4),
        unit=UNITS.get(unit, f"unit{unit:02X}"),
        sub=SUBCODES.get(sub, f"sub{sub:02X}"),
        overload=abs(raw) in OVERLOAD,
        # LCD shows only the unit symbol for a zero, point-less secondary value
        blank=secondary and raw == 0 and point == 0,
    )


def find_frame(buf):
    """Return the first complete, checksum-valid frame in buf, or None."""
    i = buf.find(HEADER)
    while i >= 0 and i + FRAME_LEN <= len(buf):
        f = buf[i:i + FRAME_LEN]
        if sum(f[:-1]) & 0xFF == f[-1]:
            return f
        i = buf.find(HEADER, i + 1)
    return None


def flag_percent_overrange(main, left, right):
    """In % mode the meter sends 0.00 for overrange; spot it from REF (left) and input (right)."""
    if main and main.sub == "%" and main.raw == 0 and left and right and left.sub == "ref" and left.raw:
        if left.value is None or right.value is None:
            return
        if abs((right.value - left.value) / left.value) >= 0.0001:
            main.overload = True


def decode(f):
    rotary, blue, range_code = f[27], f[28], f[30]
    func = FUNCTIONS.get(rotary, {}).get(blue, f"rotary{rotary:02X}/{blue:02X}")
    if rotary == 0:
        func = "OFF"
    main, left, right = decode_display(f[34:40], False), decode_display(f[40:46], True), decode_display(f[46:52], True)
    if main and abs(main.raw) == OVERLOAD_4000 and not range_code & 0x80 and range_code & 0x7F > 0:
        main.overload = True
    flag_percent_overrange(main, left, right)
    return Reading(
        model=f[4:12].decode("ascii", "replace").strip(),
        serial=f[12:20].decode("ascii", "replace").strip(),
        firmware=f[20:27].decode("ascii", "replace").strip(),
        function=func,
        range_code=range_code & 0x7F,
        autorange=not range_code & 0x80,
        key=KEYS.get(f[29], f"key{f[29]:02X}") if f[29] else "",
        main=main,
        left=left,
        right=right,
        raw={"ad": signed(*f[31:34]), "dc": signed(*f[52:55]), "ac": signed(*f[55:58])},
    )


def request(cmd, data=b""):
    """Build a request frame. Refuses anything but the read-only commands (see ALLOWED_COMMANDS)."""
    if cmd not in ALLOWED_COMMANDS:
        raise ValueError(f"command {cmd:#04x} is not allowed (read-only commands only: 00, 0E)")
    f = bytes([0x55, 0x55, cmd, len(data)]) + data
    return f + bytes([sum(f) & 0xFF])


def parse_cal_reply(buf, idx):
    """Value from a `55 55 0E 03 idx lo hi cs` reply in buf; None if absent/invalid, False if incomplete."""
    i = buf.find(bytes([0x55, 0x55, CAL_READ, 0x03]))
    if i < 0 or len(buf) < i + CAL_REPLY_LEN:
        return False
    f = buf[i:i + CAL_REPLY_LEN]
    if sum(f[:-1]) & 0xFF == f[-1] and f[4] == idx:
        return f[5] | f[6] << 8
    return None


def cal_text(cal, first, last):
    b = b"".join(bytes([cal[i] & 0xFF, cal[i] >> 8]) for i in range(first, last + 1) if cal.get(i) is not None)
    if all(32 <= c < 127 for c in b):
        return repr(b.decode("ascii"))
    return " ".join(f"{c:02X}" for c in b) + "  (not text)"


def cal_to_text(cal, frame=None, when=None):
    """Backup file contents (same format as reverse-engineering/calibration-backup-*.txt)."""
    when = when or time.strftime("%Y-%m-%d %H:%M:%S")
    ident = f"model {frame[4:12]!r} serial {frame[12:20]!r} fw {frame[20:27]!r}" if frame else ""
    lines = [f"# IDM207 calibration constants, read {when} with 55 55 0E 01 <idx> cs  {ident}",
             "# reply payload = idx, value lo, value hi. Columns: idx(hex) value(hex) value(dec) signed16 raw-frame"]
    for idx in range(256):
        v = cal.get(idx)
        if v is None:
            lines.append(f"{idx:02X} NO/BAD REPLY")
            continue
        reply = bytes([0x55, 0x55, CAL_READ, 0x03, idx, v & 0xFF, v >> 8])
        reply += bytes([sum(reply) & 0xFF])
        lines.append(f"{idx:02X} {v:04X} {v:5d} {v - 65536 if v & 0x8000 else v:6d}  {' '.join(f'{x:02X}' for x in reply)}")
    return "\n".join(lines) + "\n"


def cal_from_text(text):
    cal = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        p = line.split()
        cal[int(p[0], 16)] = None if p[1] == "NO/BAD" else int(p[1], 16)
    return cal


def cal_diff(old, new):
    """[(idx, old, new)] for entries that differ."""
    return [(i, old.get(i), new.get(i)) for i in range(256) if old.get(i) != new.get(i)]


def fmt(r):
    s = f"{r.function:<12} {str(r.main):>14}"
    if r.main and r.main.sub != "input" and not r.main.label_only:
        s += f" ({r.main.sub})"
    if r.limit:
        s += f" [{r.limit}]"
    for name, d in (("L", r.left), ("R", r.right)):
        if d:
            s += f"   {name}: {d}" + ("" if d.label_only else f" ({d.sub})")
    if r.key:
        s += f"   key={r.key}"
    return s


def csv_row(t, r):
    main_value = r.main.value if r.main else None
    cols = [f"{t:.3f}", r.function, "" if main_value is None else main_value, r.main.unit if r.main else "",
            r.main.sub if r.main else "", "OL" if r.main and r.main.overload else r.limit]
    for d in (r.left, r.right):
        cols += [d.value if d and d.value is not None else "", d.unit if d else "", d.sub if d else ""]
    return ",".join(str(c) for c in cols)
