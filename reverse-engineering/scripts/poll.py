#!/usr/bin/env python3
"""Poll an IDM207 over serial and hex-dump / decode the reply.

    pip install pyserial
    python3 poll.py /dev/cu.usbserial-XXXX            # one poll
    python3 poll.py PORT -n 0 -i 0.5                  # poll forever (Ctrl-C to stop)
    python3 poll.py PORT -l capture.log               # append every reply to a log
    python3 poll.py PORT --label "DC V, 5V range"     # tag log lines (use with -l)

Walk the rotary switch / sub-modes, running with --label each time, and note
what the LCD shows. Fields follow ../README.md (protocol summary).
"""
import argparse
import sys
import time

import serial

POLL = bytes([0x55, 0x55, 0x00, 0x00, 0xAA])


def decode_display(d):
    lo, mid, sign, dot, unit, sub = d
    mag = mid * 256 + lo
    val = -mag if sign > 0x7F else mag
    div = {0: 1, 1: 10, 2: 100, 4: 1000}.get(dot, 10000 if dot >= 8 else None)
    scaled = val / div if div else None
    return (f"lo={lo:02X} mid={mid:02X} sign={sign:02X} dot={dot:02X} "
            f"unit={unit:02X} sub={sub:02X} -> raw={val} scaled={scaled}")


def hexdump(b):
    return " ".join(f"{x:02X}" for x in b)


def read_reply(ser, quiet=0.3, total=2.0):
    """Read until the line goes quiet (length is an open question)."""
    buf = b""
    end = time.time() + total
    last = None
    while time.time() < end:
        chunk = ser.read(256)
        if chunk:
            buf += chunk
            last = time.time()
        elif last and time.time() - last > quiet:
            break
    return buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("-n", type=int, default=1, help="polls (0 = forever)")
    ap.add_argument("-i", type=float, default=1.0, help="interval seconds")
    ap.add_argument("-l", "--log", help="append raw hex replies to this file")
    ap.add_argument("--label", default="", help="note for log lines")
    a = ap.parse_args()

    ser = serial.Serial(a.port, 9600, bytesize=8, parity="N", stopbits=1, timeout=0.2)
    log = open(a.log, "a") if a.log else None
    i = 0
    try:
        while a.n == 0 or i < a.n:
            ser.reset_input_buffer()
            ser.write(POLL)
            r = read_reply(ser)
            print(f"[{i}] {len(r)} bytes")
            print(hexdump(r))
            if len(r) >= 52:
                print(f"  model={r[4:12]!r} serial={r[12:20]!r}")
                print(f"  b0-3={hexdump(r[0:4])} b20-26={hexdump(r[20:27])}")
                print(f"  rotary={r[27]:02X} submode={r[28]:02X} b30={r[30]:02X} b31-33={hexdump(r[31:34])}")
                for name, s in (("main", 34), ("2nd", 40), ("3rd", 46)):
                    print(f"  {name}: {decode_display(r[s:s + 6])}")
                if len(r) > 52:
                    print(f"  trailing: {hexdump(r[52:])}")
            elif not r:
                print("  no reply (check cable, baud, meter's PC-link mode)")
            if log:
                log.write(f"{time.strftime('%H:%M:%S')}\t{a.label}\t{hexdump(r)}\n")
                log.flush()
            i += 1
            if a.n == 0 or i < a.n:
                time.sleep(a.i)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
