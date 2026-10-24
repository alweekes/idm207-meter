import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { ANNUNCIATORS, annunciators, ArcScale, csvLine, HISTORY_ROWS, niceCeil, displayText, Logger, readCapture, Series } from "../src/model";
import { csvRow, CSV_HEADER, decode } from "../src/protocol";

const root = new URL("../../..", import.meta.url).pathname;
const capture = readFileSync(`${root}reverse-engineering/capture.log`, "utf8");
const VDC = "55 55 00 36 49 44 4D 32 30 37 20 20 30 33 36 30 30 39 31 36 30 2E 30 30 2E 30 36 01 00 00 01 23 32 00 B8 31 00 04 01 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 C4";
const frame = (h: string) => decode(Uint8Array.from(h.split(" ").map((x) => parseInt(x, 16))));

describe("model", () => {
  it("reads the capture and lights the annunciators", () => {
    const frames = readCapture(capture);
    expect(frames.length).toBeGreaterThan(600);
    const seen = new Set<string>();
    for (const [, f] of frames) for (const a of annunciators(decode(f))) seen.add(a);
    for (const a of ANNUNCIATORS.filter((x) => !["RS232", "dB", "%"].includes(x))) expect(seen).toContain(a);
  });

  it("formats display text with pretty units", () => {
    expect(displayText(frame(VDC).main)).toBe("12.728 V");
  });

  it("series restarts on change and computes stats", () => {
    const s = new Series();
    const r = frame(VDC);
    expect(s.add(100, r)).toBe(true);
    expect(s.add(101, r)).toBe(false);
    const st = s.stats();
    expect([st.count, st.min, st.max]).toEqual([2, 12.728, 12.728]);
    expect(s.window(0.5)).toEqual([[1], [12.728]]);
  });

  it("logger keeps the interval grid and exports CSV like Python", () => {
    const lg = new Logger(1);
    const r = frame(VDC);
    expect(lg.offer(0, r)).toBe(false);
    lg.start();
    const logged = [0, 1, 2, 3, 4, 5, 6].map((k) => 1000 + 0.5 * k).filter((t) => lg.offer(t, r));
    expect(logged).toEqual([1000, 1001, 1002, 1003]);
    const csv = lg.csv().trim().split("\n");
    expect(csv[0]).toBe("iso_time," + CSV_HEADER);
    expect(csv[1].slice(csv[1].indexOf(",") + 1)).toBe(csvRow(1000, r));
    lg.clear();
    lg.start();
    expect(lg.offer(5, r, true) && lg.offer(5.1, r, true)).toBe(true);
  });

  it("logger with a long interval logs once per interval", () => {
    const lg = new Logger(300);
    lg.start();
    const r = frame(VDC);
    const logged = Array.from({ length: 2 * 1200 }, (_, k) => 1000 + 0.5 * k).filter((t) => lg.offer(t, r)); // 20 min at 2 Hz
    expect(logged).toEqual([1000, 1300, 1600, 1900]);
  });

  it("logger with a sink writes every row and keeps only the last HISTORY_ROWS in memory", () => {
    const lines: string[] = [];
    const lg = new Logger();
    lg.sink = (l) => lines.push(l);
    lg.start();
    const r = frame(VDC);
    const n = HISTORY_ROWS + 5;
    for (let k = 0; k < n; k++) lg.offer(1000 + k, r, true);
    expect([lg.count, lines.length, lg.rows.length, lg.rows[0][0]]).toEqual([n, n, HISTORY_ROWS, 1005]);
    expect(lines[0].slice(lines[0].indexOf(",") + 1)).toBe(csvRow(1000, r));
    expect(lines[n - 1]).toBe(csvLine(1000 + n - 1, r));
    expect(lg.csv().trim().split("\n").at(-1)).toBe(lines[n - 1]);
    lg.clear();
    expect([lg.count, lg.rows.length]).toEqual([0, 0]);
  });
});

describe("arc scale", () => {
  it("rounds up to 1-2-5", () => {
    expect([0, 0.9, 1, 1.1, 2.1, 5, 5.1, 40, 0.03].map(niceCeil)).toEqual([1, 1, 1, 2, 5, 5, 10, 50, 0.05]);
  });
  it("grows, shrinks with hysteresis, goes bipolar", () => {
    const s = new ArcScale();
    s.update(3.3);
    expect([s.fs, s.bipolar, s.fraction(2.5)]).toEqual([5, false, 0.5]);
    s.update(1.9);
    expect(s.fs).toBe(2);
    s.update(0.9);
    expect(s.fs).toBe(2);
    s.update(-1);
    expect([s.bipolar, s.fraction(0), s.fraction(-2), s.fraction(99)]).toEqual([true, 0.5, 0, 1]);
    s.reset();
    expect([s.fs, s.bipolar]).toEqual([1, false]);
  });
});
