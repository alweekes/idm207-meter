// ISO-TECH IDM207 (APPA 300-series) RS232 protocol: pure decoding, no I/O.
// Port of apps/py-meter/idm207meter/protocol.py; both must pass apps/spec/test-vectors.json.

export const FRAME_LEN = 59;
export const HEADER = [0x55, 0x55, 0x00, 0x36];

export const FUNCTIONS: Record<number, Record<number, string>> = {
  0x01: { 0: "V DC", 1: "V AC", 2: "V AC+DC" },
  0x02: { 0: "mV DC", 1: "mV AC", 2: "mV AC+DC" },
  0x03: { 0: "Ohm", 1: "Low Ohm" },
  0x04: { 0: "Diode", 1: "Continuity" },
  0x05: { 0: "mA DC", 1: "mA AC", 2: "mA AC+DC" },
  0x06: { 0: "A DC", 1: "A AC", 2: "A AC+DC" },
  0x07: { 0: "Capacitance" },
  0x08: { 0: "Frequency", 1: "Duty cycle" },
  0x09: { 0: "Temp C", 1: "Temp F" },
};

export const UNITS: Record<number, string> = {
  0x00: "", 0x01: "V", 0x02: "mV", 0x03: "A", 0x04: "mA", 0x05: "dB",
  0x06: "dBm", 0x07: "nF", 0x08: "uF", 0x09: "mF", 0x0a: "Ohm",
  0x0b: "kOhm", 0x0c: "MOhm", 0x0d: "%", 0x0e: "Delta", 0x0f: "Hz",
  0x10: "kHz", 0x11: "MHz", 0x12: "degC", 0x13: "degF", 0x14: "s",
  0x15: "ns", 0x16: "us", 0x17: "ms",
};

export const SUBCODES: Record<number, string> = {
  0x00: "", 0x01: "input", 0x02: "frequency", 0x03: "period", 0x04: "duty",
  0x05: "ambient", 0x06: "time stamp", 0x07: "load", 0x08: "number",
  0x09: "store", 0x0a: "recall", 0x0b: "reset", 0x0c: "auto hold",
  0x0d: "max", 0x0e: "min", 0x0f: "max-min", 0x10: "peak max",
  0x11: "peak min", 0x12: "peak max-min", 0x13: "set high", 0x14: "set low",
  0x15: "high", 0x16: "low", 0x17: "delta", 0x18: "%", 0x19: "ref",
  0x1a: "dBm", 0x1b: "dB", 0x1c: "send", 0x1d: "setup", 0x1e: "set beeper",
  0x1f: "set auto power-off", 0x20: "set backlight", 0x21: "set hazard",
  0x22: "set line frequency", 0x23: "set dBm load", 0x24: "set reset",
  0x25: "blank", 0x26: "probe", 0x27: "error", 0x28: "fuse",
};

// key code (byte 29): momentary, held for ~1 s after a press; names as on the IDM207 front panel
export const KEYS: Record<number, string> = {
  0x01: "F1", 0x02: "F2", 0x03: "F3", 0x04: "F4", 0x05: "Light(+)", 0x06: "Bar(-)",
  0x07: "Digit(<)", 0x08: "Range(>)", 0x09: "Circle", 0x0a: "Blue",
};

const DECIMALS: Record<number, number> = { 0x00: 0, 0x01: 1, 0x02: 2, 0x04: 3, 0x08: 4 };

// Overload = full scale + 1 count. 4001 only counts as OL when autoranging above range 0.
const OVERLOAD = new Set([2001, 40001]);
const OVERLOAD_4000 = 4001;

// Only these commands may ever be sent: 00 = read all, 0E = read calibration entry.
// Commands >= 0x80 write EEPROM (0x80 overwrote the model name once); 0x8x/0x9x are calibration writes.
export const ALLOWED_COMMANDS = new Set([0x00, 0x0e]);

export const CAL_READ = 0x0e;
export const CAL_REPLY_LEN = 8;
export const CAL_TEXT: Record<string, [number, number]> = {
  "APPA model": [0xdd, 0xe0], "model name": [0xe1, 0xe4], serial: [0xe5, 0xe8],
};

export const CSV_HEADER =
  "time,function,main,main_unit,main_sub,main_flag,left,left_unit,left_sub,right,right_unit,right_sub";

const hex2 = (n: number) => n.toString(16).toUpperCase().padStart(2, "0");

export function signed(lo: number, hi: number, pole: number): number {
  const mag = lo | (hi << 8);
  return pole > 0x7f && mag !== 0 ? -mag : mag; // never -0 (Python ints have no negative zero)
}

export class Display {
  constructor(
    public raw: number,
    public decimals: number,
    public unit: string,
    public sub: string,
    public overload: boolean,
    public blank: boolean,
  ) {}

  /** Display shows only a text label (e.g. HISET); 'number' (memory location) is a unitless count. */
  get labelOnly(): boolean {
    return !this.unit && !["", "input", "number"].includes(this.sub);
  }

  get value(): number | null {
    if (this.overload || this.blank || this.labelOnly) return null;
    return this.raw / 10 ** this.decimals;
  }

  get text(): string {
    if (this.labelOnly) return `[${this.sub}]`;
    if (this.blank) return `---- ${this.unit}`.trim();
    if (this.overload) return `OL ${this.unit}`.trim();
    return `${this.value!.toFixed(this.decimals)} ${this.unit}`.trim();
  }
}

export interface Reading {
  model: string;
  serial: string;
  firmware: string;
  function: string;
  rangeCode: number;
  autorange: boolean;
  key: string;
  main: Display | null;
  left: Display | null;
  right: Display | null;
  raw: { ad: number; dc: number; ac: number };
  limit: string;
}

export function decodeDisplay(d: ArrayLike<number>, secondary: boolean): Display | null {
  const [lo, hi, pole, point, unit, sub] = Array.from(d);
  if (unit === 0 && sub === 0 && lo === 0 && hi === 0) return null; // display not in use
  const raw = signed(lo, hi, pole);
  return new Display(
    raw,
    DECIMALS[point] ?? 4,
    UNITS[unit] ?? `unit${hex2(unit)}`,
    SUBCODES[sub] ?? `sub${hex2(sub)}`,
    OVERLOAD.has(Math.abs(raw)),
    secondary && raw === 0 && point === 0, // LCD shows only the unit symbol
  );
}

function indexOf(buf: ArrayLike<number>, pat: number[], from = 0): number {
  outer: for (let i = from; i <= buf.length - pat.length; i++) {
    for (let k = 0; k < pat.length; k++) if (buf[i + k] !== pat[k]) continue outer;
    return i;
  }
  return -1;
}

const checksumOk = (f: ArrayLike<number>) => {
  let s = 0;
  for (let i = 0; i < f.length - 1; i++) s += f[i];
  return (s & 0xff) === f[f.length - 1];
};

/** First complete, checksum-valid frame in buf, with its start index; null if none. */
export function findFrameAt(buf: ArrayLike<number>): { frame: Uint8Array; index: number } | null {
  let i = indexOf(buf, HEADER);
  while (i >= 0 && i + FRAME_LEN <= buf.length) {
    const f = Uint8Array.from(Array.prototype.slice.call(buf, i, i + FRAME_LEN) as number[]);
    if (checksumOk(f)) return { frame: f, index: i };
    i = indexOf(buf, HEADER, i + 1);
  }
  return null;
}

export const findFrame = (buf: ArrayLike<number>) => findFrameAt(buf)?.frame ?? null;

function flagPercentOverrange(main: Display | null, left: Display | null, right: Display | null) {
  // In % mode the meter sends 0.00 for overrange; spot it from REF (left) and input (right).
  if (main && main.sub === "%" && main.raw === 0 && left && right && left.sub === "ref" && left.raw) {
    const l = left.value, r = right.value;
    if (l === null || r === null) return;
    if (Math.abs((r - l) / l) >= 0.0001) main.overload = true;
  }
}

/** Python str.strip() whitespace (the identification fields may contain control bytes). */
const pyStrip = (s: string) => s.replace(/^[ \t\n\r\x0b\x0c\x1c-\x1f]+|[ \t\n\r\x0b\x0c\x1c-\x1f]+$/g, "");
/** Python bytes.decode("ascii", "replace"). */
const ascii = (b: Uint8Array) => Array.from(b, (c) => (c < 128 ? String.fromCharCode(c) : "�")).join("");

function limitOf(main: Display | null, left: Display | null, right: Display | null): string {
  // 'HI'/'LO' when the main reading is beyond a HIGH/LOW limit; the frame itself carries no flag.
  const m = main?.value;
  if (!main || m === null || m === undefined || main.sub !== "input") return "";
  for (const d of [left, right]) {
    const v = d?.value;
    if (d && v !== null && v !== undefined) {
      if (d.sub === "high" && m > v) return "HI";
      if (d.sub === "low" && m < v) return "LO";
    }
  }
  return "";
}

export function decode(f: Uint8Array): Reading {
  const rotary = f[27], blue = f[28], rangeCode = f[30];
  let func = FUNCTIONS[rotary]?.[blue] ?? `rotary${hex2(rotary)}/${hex2(blue)}`;
  if (rotary === 0) func = "OFF";
  const main = decodeDisplay(f.subarray(34, 40), false);
  const left = decodeDisplay(f.subarray(40, 46), true);
  const right = decodeDisplay(f.subarray(46, 52), true);
  if (main && Math.abs(main.raw) === OVERLOAD_4000 && !(rangeCode & 0x80) && (rangeCode & 0x7f) > 0) {
    main.overload = true;
  }
  flagPercentOverrange(main, left, right);
  return {
    model: pyStrip(ascii(f.subarray(4, 12))),
    serial: pyStrip(ascii(f.subarray(12, 20))),
    firmware: pyStrip(ascii(f.subarray(20, 27))),
    function: func,
    rangeCode: rangeCode & 0x7f,
    autorange: !(rangeCode & 0x80),
    key: f[29] ? (KEYS[f[29]] ?? `key${hex2(f[29])}`) : "",
    main, left, right,
    raw: { ad: signed(f[31], f[32], f[33]), dc: signed(f[52], f[53], f[54]), ac: signed(f[55], f[56], f[57]) },
    limit: limitOf(main, left, right),
  };
}

/** Build a request frame. Refuses anything but the read-only commands (see ALLOWED_COMMANDS). */
export function request(cmd: number, data: number[] = []): Uint8Array {
  if (!ALLOWED_COMMANDS.has(cmd)) {
    throw new Error(`command 0x${hex2(cmd)} is not allowed (read-only commands only: 00, 0E)`);
  }
  const f = [0x55, 0x55, cmd, data.length, ...data];
  f.push(f.reduce((a, b) => a + b, 0) & 0xff);
  return Uint8Array.from(f);
}

/** Value from a `55 55 0E 03 idx lo hi cs` reply; null if invalid, undefined if incomplete. */
export function parseCalReply(buf: ArrayLike<number>, idx: number): number | null | undefined {
  const i = indexOf(buf, [0x55, 0x55, CAL_READ, 0x03]);
  if (i < 0 || buf.length < i + CAL_REPLY_LEN) return undefined;
  const f = Array.prototype.slice.call(buf, i, i + CAL_REPLY_LEN) as number[];
  if (checksumOk(f) && f[4] === idx) return f[5] | (f[6] << 8);
  return null;
}

export type Cal = Map<number, number | null>;

export function calText(cal: Cal, first: number, last: number): string {
  const b: number[] = [];
  for (let i = first; i <= last; i++) {
    const v = cal.get(i);
    if (v !== null && v !== undefined) b.push(v & 0xff, v >> 8);
  }
  if (b.every((c) => c >= 32 && c < 127)) return `'${String.fromCharCode(...b)}'`;
  return b.map(hex2).join(" ") + "  (not text)";
}

const pyBytesRepr = (b: Uint8Array) =>
  "b'" + Array.from(b, (c) => (c >= 32 && c < 127 && c !== 0x27 && c !== 0x5c ? String.fromCharCode(c) : `\\x${c.toString(16).padStart(2, "0")}`)).join("") + "'";

/** Backup file contents (same format as reverse-engineering/calibration-backup-*.txt). */
export function calToText(cal: Cal, frame: Uint8Array | null, when: string): string {
  const ident = frame
    ? `model ${pyBytesRepr(frame.subarray(4, 12))} serial ${pyBytesRepr(frame.subarray(12, 20))} fw ${pyBytesRepr(frame.subarray(20, 27))}`
    : "";
  const lines = [
    `# IDM207 calibration constants, read ${when} with 55 55 0E 01 <idx> cs  ${ident}`,
    "# reply payload = idx, value lo, value hi. Columns: idx(hex) value(hex) value(dec) signed16 raw-frame",
  ];
  for (let idx = 0; idx < 256; idx++) {
    const v = cal.get(idx);
    if (v === null || v === undefined) {
      lines.push(`${hex2(idx)} NO/BAD REPLY`);
      continue;
    }
    const reply = [0x55, 0x55, CAL_READ, 0x03, idx, v & 0xff, v >> 8];
    reply.push(reply.reduce((a, b) => a + b, 0) & 0xff);
    const s16 = v & 0x8000 ? v - 65536 : v;
    lines.push(`${hex2(idx)} ${v.toString(16).toUpperCase().padStart(4, "0")} ${String(v).padStart(5)} ${String(s16).padStart(6)}  ${reply.map(hex2).join(" ")}`);
  }
  return lines.join("\n") + "\n";
}

export function calFromText(text: string): Cal {
  const cal: Cal = new Map();
  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith("#") || !line.trim()) continue;
    const p = line.trim().split(/\s+/);
    cal.set(parseInt(p[0], 16), p[1] === "NO/BAD" ? null : parseInt(p[1], 16));
  }
  return cal;
}

export function calDiff(old: Cal, now: Cal): [number, number | null | undefined, number | null | undefined][] {
  const out: [number, number | null | undefined, number | null | undefined][] = [];
  for (let i = 0; i < 256; i++) if (old.get(i) !== now.get(i)) out.push([i, old.get(i), now.get(i)]);
  return out;
}

/** Python str() of a float, for CSV cells identical to the Python app. */
export function pyFloat(v: number): string {
  if (Number.isInteger(v)) return v.toFixed(1);
  const s = String(v);
  const m = /^(-?\d)(?:\.(\d+))?e([+-])(\d+)$/.exec(s);
  if (m) return `${m[1]}${m[2] ? "." + m[2] : ""}e${m[3]}${m[4].padStart(2, "0")}`; // 1e-7 -> 1e-07
  return s;
}

const cell = (v: number | null | undefined) => (v === null || v === undefined ? "" : pyFloat(v));

export function csvRow(t: number, r: Reading): string {
  const m = r.main;
  const cols: string[] = [t.toFixed(3), r.function, m ? cell(m.value) : "", m ? m.unit : "", m ? m.sub : "",
    m && m.overload ? "OL" : r.limit];
  for (const d of [r.left, r.right]) cols.push(d ? cell(d.value) : "", d ? d.unit : "", d ? d.sub : "");
  return cols.join(",");
}
