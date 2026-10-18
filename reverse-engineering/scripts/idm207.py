#!/usr/bin/env python3
"""Read an ISO-TECH IDM207 (APPA 207, shares the APPA 300-series protocol) over RS232.

    pip install pyserial
    python3 idm207.py /dev/ttyS0                 # print readings once a second
    python3 idm207.py /dev/ttyS0 -i 0.5 --csv    # CSV to stdout
    python3 idm207.py /dev/ttyS0 --listen        # log one reading per SEND (M4/F4) press
    python3 idm207.py --decode-log ../capture.log  # decode a poll.py log offline
    python3 idm207.py /dev/ttyS0 --backup-cal cal.txt   # save the 256 calibration constants
    python3 idm207.py /dev/ttyS0 --compare-cal cal.txt  # check them against a saved backup

Verified against a real meter (fw 0.00.06) on 2026-10-17; see ../README.md.
The protocol code lives in apps/py-meter/idm207meter (shared with the GUI); this is the CLI.
"""
import argparse
import atexit
import os
import signal
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "py-meter"))
from idm207meter.protocol import *  # noqa: E402,F401,F403  (keeps `import idm207; idm207.decode(...)` working)
from idm207meter import protocol as p  # noqa: E402
from idm207meter import serialio  # noqa: E402

poll = serialio.poll
listen = serialio.listen
read_cal = serialio.read_cal


def decode_log(path):
    for line in open(path):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3:
            continue
        f = p.find_frame(bytes.fromhex(parts[2]))
        print(f"{parts[0]} {parts[1]:<28} " + (p.fmt(p.decode(f)) if f else "no valid frame"))


def cal_command(ser, a):
    frame = serialio.poll_frame(ser)
    progress = lambda n: n % 32 == 0 and print(f"read {n}/256 calibration entries", file=sys.stderr, flush=True)
    cal = serialio.read_all_cal(ser, progress)
    missing = [i for i, v in cal.items() if v is None]
    for name, (first, last) in p.CAL_TEXT.items():
        print(f"{name:11s}: {p.cal_text(cal, first, last)}")
    if missing:
        print(f"no reply for {len(missing)} entries: {' '.join(f'{i:02X}' for i in missing)}", file=sys.stderr)
    if a.backup_cal:
        with open(a.backup_cal, "w") as fh:
            fh.write(p.cal_to_text(cal, frame))
        print(f"saved {256 - len(missing)} entries to {a.backup_cal}")
    if a.compare_cal:
        diff = p.cal_diff(p.cal_from_text(open(a.compare_cal).read()), cal)
        for i, o, n in diff:
            print(f"  {i:02X}: {'----' if o is None else f'{o:04X}'} -> {'----' if n is None else f'{n:04X}'}")
        print(f"{len(diff)} of 256 entries differ from {a.compare_cal}")
        return 1 if diff else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", nargs="?")
    ap.add_argument("-i", type=float, default=1.0, help="interval seconds (default 1)")
    ap.add_argument("-n", type=int, default=0, help="number of readings (0 = forever)")
    ap.add_argument("--csv", action="store_true", help="CSV output")
    ap.add_argument("--listen", action="store_true",
                    help="don't poll; log frames sent by the meter's SEND key (M4/F4)")
    ap.add_argument("--decode-log", metavar="FILE", help="decode a poll.py capture log and exit")
    ap.add_argument("--backup-cal", metavar="FILE",
                    help="read all 256 calibration constants (read-only) and save them to FILE")
    ap.add_argument("--compare-cal", metavar="FILE",
                    help="read the calibration constants and list differences from a saved backup")
    a = ap.parse_args()

    if a.decode_log:
        return decode_log(a.decode_log)
    if not a.port:
        ap.error("port required")

    ser = serialio.open_port(a.port)
    # Close the port on every exit path (incl. SIGTERM) so its terminal settings are restored (see serialio).
    atexit.register(ser.close)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if a.backup_cal or a.compare_cal:
        return cal_command(ser, a)
    if a.csv:
        print(p.CSV_HEADER, flush=True)
    out = lambda t, r: print(p.csv_row(t, r) if a.csv else f"{time.strftime('%H:%M:%S')}  {p.fmt(r)}", flush=True)
    i = 0
    try:
        if a.listen:
            for r in serialio.listen(ser):
                out(time.time(), r)
                i += 1
                if a.n and i >= a.n:
                    break
            return
        while a.n == 0 or i < a.n:
            t = time.time()
            r = serialio.poll(ser)
            if r is None:
                print("no reply", file=sys.stderr)
            else:
                out(t, r)
            i += 1
            time.sleep(max(0, a.i - (time.time() - t)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
