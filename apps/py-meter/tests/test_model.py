import os

from idm207meter import model
from idm207meter import protocol as p

CAPTURE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "reverse-engineering", "capture.log")


def frame(hexstr):
    return p.decode(bytes.fromhex(hexstr))


VDC = "55 55 00 36 49 44 4D 32 30 37 20 20 30 33 36 30 30 39 31 36 30 2E 30 30 2E 30 36 01 00 00 01 23 32 00 B8 31 00 04 01 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 C4"


def test_read_capture_and_annunciators():
    frames = model.read_capture(open(CAPTURE).read())
    assert len(frames) > 600
    seen = set()
    for _, f in frames:
        seen |= model.annunciators(p.decode(f))
    # every annunciator except RS232 (SEND mode flag) is exercised by the capture
    assert seen >= set(model.ANNUNCIATORS) - {"RS232", "dB", "%"} | {"dBm", "REF", "MEM", "SETUP", "HI", "LO", "PEAK", "AH"}


def test_display_text_pretty_units():
    r = frame(VDC)
    assert model.display_text(r.main) == "12.728 V"
    for _, f in model.read_capture(open(CAPTURE).read()):
        r = p.decode(f)
        if r.main and r.main.unit == "kOhm" and not r.main.overload:
            assert model.display_text(r.main).endswith(" kΩ")
            break


def test_series_restarts_on_unit_change_and_stats():
    s = model.Series()
    r = frame(VDC)
    assert s.add(100.0, r) is True
    assert s.add(101.0, r) is False
    st = s.stats()
    assert st["count"] == 2 and st["min"] == st["max"] == 12.728
    t, v = s.window(0.5)
    assert t == [1.0] and v == [12.728]


def test_logger_interval_and_csv():
    lg = model.Logger(interval=1.0)
    r = frame(VDC)
    assert lg.offer(0.0, r) is False          # not running
    lg.start()
    times = [1000.0 + 0.5 * k for k in range(7)]   # 3 s of 2 Hz readings
    logged = [t for t in times if lg.offer(t, r)]
    assert logged == [1000.0, 1001.0, 1002.0, 1003.0]
    csv = lg.csv().splitlines()
    assert csv[0] == "iso_time," + p.CSV_HEADER
    assert csv[1].split(",", 1)[1] == p.csv_row(1000.0, r)
    lg.clear()
    lg.start()
    assert lg.offer(5.0, r, send_mode=True) and lg.offer(5.1, r, send_mode=True)  # SEND: every frame


def test_nice_ceil():
    assert [model.nice_ceil(x) for x in (0, 0.9, 1, 1.1, 2.1, 5, 5.1, 40, 0.03)] == [1, 1, 1, 2, 5, 5, 10, 50, 0.05]


def test_arc_scale():
    s = model.ArcScale()
    s.update(3.3)
    assert s.fs == 5 and not s.bipolar and s.fraction(2.5) == 0.5
    s.update(1.9)          # < 40 % of 5 -> shrink
    assert s.fs == 2
    s.update(0.9)
    assert s.fs == 2       # no flapping inside the hysteresis band
    s.update(-1.0)
    assert s.bipolar and s.fraction(0) == 0.5 and s.fraction(-2) == 0 and s.fraction(99) == 1
    s.reset()
    assert (s.fs, s.bipolar) == (1.0, False)
