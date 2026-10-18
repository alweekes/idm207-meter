import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { calDiff, calFromText, calText, calToText, csvRow, CSV_HEADER, decode, Display, findFrame, parseCalReply, request } from "../src/protocol";

const root = new URL("../../..", import.meta.url).pathname;
const vectors: { frames: any[]; buffers: any[]; csv_header: string } = JSON.parse(readFileSync(`${root}apps/spec/test-vectors.json`, "utf8"));
const bytes = (hex: string) => Uint8Array.from(hex.split(/\s+/).map((h) => parseInt(h, 16)));
const hex = (b: Uint8Array) => Array.from(b, (c) => c.toString(16).toUpperCase().padStart(2, "0")).join(" ");

const asDict = (d: Display | null) =>
  d && { raw: d.raw, decimals: d.decimals, unit: d.unit, sub: d.sub, overload: d.overload, blank: d.blank,
    label_only: d.labelOnly, value: d.value, text: d.text };

describe("shared test vectors", () => {
  it.each(vectors.frames.map((v: any) => [v.label, v] as [string, any]))("%s", (_label, vec) => {
    const f = bytes(vec.hex);
    expect(findFrame(f)).toEqual(f);
    const r = decode(f);
    expect({
      model: r.model, serial: r.serial, firmware: r.firmware, function: r.function, range_code: r.rangeCode,
      autorange: r.autorange, key: r.key, limit: r.limit, raw: r.raw, main: asDict(r.main), left: asDict(r.left),
      right: asDict(r.right), csv: csvRow(0, r),
    }).toEqual(vec.expected);
  });

  it.each(vectors.buffers.map((v: any) => [v.label, v] as [string, any]))("buffer %s", (_label, vec) => {
    const f = findFrame(bytes(vec.hex));
    expect(f ? hex(f) : null).toBe(vec.frame);
  });

  it("CSV header", () => expect(CSV_HEADER).toBe(vectors.csv_header));
});

describe("allow-list", () => {
  it("builds the read-only requests", () => {
    expect(hex(request(0x00))).toBe("55 55 00 00 AA");
    expect(hex(request(0x0e, [0x57]))).toBe("55 55 0E 01 57 10");
  });
  it.each([0x01, 0x80, 0x86, 0x90, 0x91, 0xff])("refuses 0x%s", (cmd) => {
    expect(() => request(cmd)).toThrow(/not allowed/);
  });
});

describe("calibration", () => {
  it("parses replies", () => {
    expect(parseCalReply(bytes("55 55 0E 03 58 DD 26 16"), 0x58)).toBe(0x26dd);
    expect(parseCalReply(bytes("55 55 0E 03 58 DD 26 17"), 0x58)).toBeNull();
    expect(parseCalReply(bytes("55 55 0E 03 58"), 0x58)).toBeUndefined();
  });
  it("round-trips the backup file format identically to Python", () => {
    const text = readFileSync(`${root}reverse-engineering/calibration-backup-IDM207-03600916-restored.txt`, "utf8");
    const cal = calFromText(text);
    expect(cal.size).toBe(256);
    expect(calText(cal, 0xe1, 0xe4)).toBe("'IDM207  '");
    const body = (s: string) => s.split("\n").filter((l) => !l.startsWith("#")).join("\n");
    expect(body(calToText(cal, null, "x"))).toBe(body(text));
    expect(calDiff(cal, calFromText(calToText(cal, null, "x")))).toEqual([]);
  });
});
