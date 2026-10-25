// App logic without DOM: annunciators, unit names, chart series/stats, data logger, capture files.
// Port of apps/py-meter/idm207meter/model.py; behaviour per apps/spec/UI-SPEC.md.
import { CSV_HEADER, csvRow, Display, findFrame, Reading } from "./protocol";

const PRETTY_UNITS: Record<string, string> = {
  Ohm: "Ω", kOhm: "kΩ", MOhm: "MΩ", uF: "µF", us: "µs", degC: "°C", degF: "°F", Delta: "Δ",
};

export const ANNUNCIATORS = ["AUTO", "DC", "AC", "MAX", "MIN", "PEAK", "AH", "REF", "Δ", "%", "dB", "dBm", "MEM",
  "SETUP", "HI", "LO", "RS232"];

export const prettyUnit = (u: string) => PRETTY_UNITS[u] ?? u;

/** Display text as on the LCD (number/OL/----/[label]) with a pretty unit. */
export function displayText(d: Display | null): string {
  if (!d) return "";
  const s = d.text;
  return d.unit && s.endsWith(d.unit) ? s.slice(0, s.length - d.unit.length) + prettyUnit(d.unit) : s;
}

export function annunciators(r: Reading, sendMode = false): Set<string> {
  const subs = new Set([r.main, r.left, r.right].filter((d): d is Display => !!d).map((d) => d.sub));
  const on = new Set<string>();
  if (r.autorange) on.add("AUTO");
  if (r.function.includes("DC")) on.add("DC");
  if (r.function.includes("AC")) on.add("AC");
  if (subs.has("max") || subs.has("max-min")) on.add("MAX");
  if (subs.has("min") || subs.has("max-min")) on.add("MIN");
  if ([...subs].some((s) => s.startsWith("peak"))) on.add("PEAK");
  for (const [sub, name] of [["auto hold", "AH"], ["ref", "REF"], ["delta", "Δ"], ["%", "%"], ["dB", "dB"], ["dBm", "dBm"]]) {
    if (subs.has(sub)) on.add(name);
  }
  if (subs.has("store") || subs.has("recall") || subs.has("number")) on.add("MEM");
  if (subs.has("setup")) on.add("SETUP"); // SETUP menu pages (not the HISET/LOSET labels)
  if (r.limit) on.add(r.limit);
  if (sendMode) on.add("RS232");
  return on;
}

export interface Stats { min: number | null; max: number | null; mean: number | null; count: number; ol: number }

/** Smallest 1-2-5 x 10^n that is >= a (1 for a <= 0). */
export function niceCeil(a: number): number {
  if (a <= 0) return 1;
  const e = Math.floor(Math.log10(a));
  const m = a / 10 ** e;
  return [1, 2, 5, 10].find((s) => m <= s * (1 + 1e-9))! * 10 ** e;
}

/** Full scale for the arc meter: 1-2-5 steps, grows at once, shrinks below 40 % (no flapping).
 *  Zero-left until a negative value is seen, then zero-centred. Reset when the series restarts. */
export class ArcScale {
  fs = 1;
  bipolar = false;

  reset() {
    this.fs = 1;
    this.bipolar = false;
  }

  update(v: number | null) {
    if (v === null) return;
    const a = Math.abs(v);
    this.bipolar = this.bipolar || v < 0;
    if (a > this.fs || (a > 0 && a < 0.4 * this.fs)) this.fs = niceCeil(a);
  }

  /** Needle/bar position 0..1 along the arc (clamped). */
  fraction(v: number): number {
    const x = v / this.fs;
    return Math.min(1, Math.max(0, this.bipolar ? 0.5 + x / 2 : x));
  }

  /** Major ticks as [fraction, value]. */
  ticks(n = 5): [number, number][] {
    const lo = this.bipolar ? -this.fs : 0;
    return Array.from({ length: n + 1 }, (_, i) => [i / n, lo + ((this.fs - lo) * i) / n]);
  }
}

/** Main-value time series for the chart; restarts when function or unit changes. */
export class Series {
  key: string | null = null;
  t0: number | null = null;
  t: number[] = [];
  v: number[] = [];
  ol = 0;

  reset(key: string | null = null) {
    this.key = key;
    this.t0 = null;
    this.t = [];
    this.v = [];
    this.ol = 0;
  }

  /** Add a reading; returns true if a new series was started. */
  add(t: number, r: Reading): boolean {
    const key = `${r.function}|${r.main ? r.main.unit : ""}`;
    const started = key !== this.key;
    if (started) this.reset(key);
    if (this.t0 === null) this.t0 = t;
    const m = r.main;
    if (m && m.overload) this.ol++;
    const v = m?.value;
    if (m && v !== null && v !== undefined) {
      this.t.push(t - this.t0);
      this.v.push(v);
    }
    return started;
  }

  window(seconds: number | null): [number[], number[]] {
    if (!seconds || !this.t.length) return [this.t, this.v];
    const cut = this.t[this.t.length - 1] - seconds;
    let i = this.t.findIndex((x) => x >= cut);
    if (i < 0) i = this.t.length;
    return [this.t.slice(i), this.v.slice(i)];
  }

  stats(): Stats {
    if (!this.v.length) return { min: null, max: null, mean: null, count: 0, ol: this.ol };
    let min = Infinity, max = -Infinity, sum = 0;
    for (const x of this.v) {
      if (x < min) min = x;
      if (x > max) max = x;
      sum += x;
    }
    return { min, max, mean: sum / this.v.length, count: this.v.length, ol: this.ol };
  }
}

/** Local ISO-8601 time with milliseconds, like Python datetime.isoformat(timespec="milliseconds"). */
export function isoLocal(epochSeconds: number): string {
  const d = new Date(Math.round(epochSeconds * 1000));
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

export const HISTORY_ROWS = 2000; // rows kept in memory (and in the history list) while logging to a file
export const TICK_SLACK = 0.1; // s; a reading this much before the next tick still counts (timestamps jitter by ~1 ms)

export const csvHeader = () => "iso_time," + CSV_HEADER;
export const csvLine = (t: number, r: Reading) => `${isoLocal(t)},${csvRow(t, r)}`;

/** Data log (UI-SPEC.md: Logging). With a sink, every row is also passed to it as a CSV line and only the
 *  last HISTORY_ROWS stay in memory, so a file log can run for days. */
export class Logger {
  running = false;
  rows: [number, Reading][] = [];
  count = 0; // rows logged since the last clear (rows may be trimmed)
  sink: ((line: string) => void) | null = null;
  private lastTick = 0;
  private lastFrameT = -1;
  constructor(public interval = 1.0) {}

  start() {
    this.running = true;
    this.lastTick = 0;
  }
  stop() {
    this.running = false;
  }
  clear() {
    this.rows = [];
    this.count = 0;
    this.lastFrameT = -1;
  }

  /** Called for every new reading; records it if logging is running and the interval allows. */
  offer(t: number, r: Reading, sendMode = false): boolean {
    if (!this.running) return false;
    if (!sendMode) {
      if (t - this.lastTick < this.interval - TICK_SLACK) return false;
      // stay on the interval grid even if readings arrive a little early or late
      this.lastTick = t - this.lastTick > 2 * this.interval ? t : this.lastTick + this.interval;
    }
    if (t === this.lastFrameT) return false;
    this.lastFrameT = t;
    this.rows.push([t, r]);
    this.count++;
    if (this.sink) {
      this.sink(csvLine(t, r));
      if (this.rows.length > HISTORY_ROWS) this.rows.splice(0, this.rows.length - HISTORY_ROWS);
    }
    return true;
  }

  csv(): string {
    return [csvHeader(), ...this.rows.map(([t, r]) => csvLine(t, r))].join("\n") + "\n";
  }
}

/** Frames from a poll.py/capture.log file: [label, frame][]. */
export function readCapture(text: string): [string, Uint8Array][] {
  const out: [string, Uint8Array][] = [];
  for (const line of text.split(/\r?\n/)) {
    const parts = line.split("\t");
    if (parts.length < 3) continue;
    const hex = parts[2].trim();
    if (!/^([0-9A-Fa-f]{2}\s*)+$/.test(hex)) continue;
    const bytes = hex.split(/\s+/).map((h) => parseInt(h, 16));
    const f = findFrame(bytes);
    if (f) out.push([parts[1], f]);
  }
  return out;
}
