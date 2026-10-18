#!/usr/bin/env python3
"""Generate test-vectors.json: every distinct frame in reverse-engineering/capture.log with the
fields the reference decoder (idm207meter.protocol) produces. Both apps test against this file.

    python3 make_vectors.py            # rewrites test-vectors.json next to this script

Regenerate only on purpose (e.g. after a verified decoder fix); the JSON is the shared contract.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "apps", "py-meter"))
from idm207meter import protocol as p  # noqa: E402


def display(d):
    if d is None:
        return None
    return {"raw": d.raw, "decimals": d.decimals, "unit": d.unit, "sub": d.sub, "overload": d.overload,
            "blank": d.blank, "label_only": d.label_only, "value": d.value, "text": str(d)}


def reading(r):
    return {"model": r.model, "serial": r.serial, "firmware": r.firmware, "function": r.function,
            "range_code": r.range_code, "autorange": r.autorange, "key": r.key, "limit": r.limit,
            "raw": r.raw, "main": display(r.main), "left": display(r.left), "right": display(r.right),
            "csv": p.csv_row(0.0, r)}


def main():
    seen, frames, buffers = set(), [], []
    for line in open(os.path.join(ROOT, "reverse-engineering", "capture.log")):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3 or not parts[2].strip():
            continue
        buf = bytes.fromhex(parts[2])
        f = p.find_frame(buf)
        if f is None or f != buf:
            # buffers with junk around the frame, or no valid frame at all
            key = ("buf", buf)
            if key not in seen and len(buffers) < 40:
                seen.add(key)
                buffers.append({"label": parts[1], "hex": buf.hex(" ").upper(),
                                "frame": f.hex(" ").upper() if f else None})
        if f is None or ("f", f) in seen:
            continue
        seen.add(("f", f))
        frames.append({"label": parts[1], "hex": f.hex(" ").upper(), "expected": reading(p.decode(f))})
    out = {"source": "reverse-engineering/capture.log", "csv_header": p.CSV_HEADER,
           "frames": frames, "buffers": buffers}
    with open(os.path.join(HERE, "test-vectors.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"{len(frames)} frames, {len(buffers)} buffer cases")


if __name__ == "__main__":
    main()
