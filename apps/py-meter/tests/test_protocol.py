import json
import os

import pytest

from idm207meter import protocol as p

VECTORS = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "spec", "test-vectors.json")))


def as_dict(d):
    if d is None:
        return None
    return {"raw": d.raw, "decimals": d.decimals, "unit": d.unit, "sub": d.sub, "overload": d.overload,
            "blank": d.blank, "label_only": d.label_only, "value": d.value, "text": str(d)}


@pytest.mark.parametrize("vec", VECTORS["frames"], ids=lambda v: v["label"][:40])
def test_frame_vectors(vec):
    f = bytes.fromhex(vec["hex"])
    assert p.find_frame(f) == f
    r = p.decode(f)
    e = vec["expected"]
    got = {"model": r.model, "serial": r.serial, "firmware": r.firmware, "function": r.function,
           "range_code": r.range_code, "autorange": r.autorange, "key": r.key, "limit": r.limit, "raw": r.raw,
           "main": as_dict(r.main), "left": as_dict(r.left), "right": as_dict(r.right), "csv": p.csv_row(0.0, r)}
    assert got == e


@pytest.mark.parametrize("vec", VECTORS["buffers"], ids=lambda v: v["label"][:40])
def test_buffer_vectors(vec):
    f = p.find_frame(bytes.fromhex(vec["hex"]))
    assert (f.hex(" ").upper() if f else None) == vec["frame"]


def test_csv_header():
    assert p.CSV_HEADER == VECTORS["csv_header"]


def test_allow_list():
    assert p.request(0x00) == p.POLL
    assert p.request(0x0E, b"\x57") == bytes.fromhex("55 55 0E 01 57 10")
    for cmd in (0x01, 0x80, 0x86, 0x90, 0x91, 0xFF):
        with pytest.raises(ValueError):
            p.request(cmd)


def test_cal_reply_and_text():
    assert p.parse_cal_reply(bytes.fromhex("55 55 0E 03 58 DD 26 16"), 0x58) == 0x26DD
    assert p.parse_cal_reply(bytes.fromhex("55 55 0E 03 58 DD 26 17"), 0x58) is None  # bad checksum
    assert p.parse_cal_reply(bytes.fromhex("55 55 0E 03 58"), 0x58) is False  # incomplete
    cal = {0xE1: 0x4449, 0xE2: 0x324D, 0xE3: 0x3730, 0xE4: 0x2020}
    assert p.cal_text(cal, 0xE1, 0xE4) == "'IDM207  '"
    backup = os.path.join(os.path.dirname(__file__), "..", "..", "spec", "cal-fixture.txt")
    cal = p.cal_from_text(open(backup).read())
    assert len(cal) == 256 and p.cal_diff(cal, p.cal_from_text(p.cal_to_text(cal))) == []
