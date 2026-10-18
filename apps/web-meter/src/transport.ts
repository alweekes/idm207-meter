// Sources of frames: Web Serial (poll / SEND listen / calibration read) and capture-file replay.
// Every request goes through protocol.request(), which only allows the read-only commands 00 and 0E.
import { Cal, CAL_READ, FRAME_LEN, findFrameAt, parseCalReply, request } from "./protocol";

export const POLL_PERIOD = 0.5; // s; meter refreshes ~2x/s
export const NO_REPLY_LIMIT = 3;

export interface SourceEvents {
  frame(t: number, frame: Uint8Array, fromSend: boolean): void;
  status(msg: string): void;
  failed(msg: string): void;
}

export interface Source {
  sendMode: boolean;
  start(ev: SourceEvents): void;
  stop(): Promise<void>;
  readAllCal?(progress: (n: number) => void): Promise<{ cal: Cal; ident: Uint8Array | null }>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const now = () => Date.now() / 1000;

export class SerialSource implements Source {
  sendMode = false;
  polls = 0;
  errors = 0;
  rxBytes = 0; // total bytes received since open; 0 after several polls means a silent port
  private buf: number[] = [];
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private stopped = false;
  private busy: Promise<unknown> = Promise.resolve(); // serialises poll loop and calibration reads
  private calActive = false;
  private loopDone: Promise<void> = Promise.resolve();

  constructor(public port: SerialPort) {}

  static supported(): boolean {
    return typeof navigator !== "undefined" && "serial" in navigator;
  }

  /** Ask the user to pick a port (browser dialog), then open it at 9600 8N1. */
  static async choose(): Promise<SerialSource> {
    const port = await navigator.serial.requestPort();
    return new SerialSource(port);
  }

  start(ev: SourceEvents) {
    this.loopDone = this.run(ev).catch((e) => ev.failed(String(e?.message ?? e)));
  }

  /** Open at 9600 8N1; retry once after a short pause (a previous page or app may still be releasing the port). */
  private async openPort() {
    const opts = { baudRate: 9600, dataBits: 8, parity: "none", stopBits: 1, flowControl: "none" } as const;
    try {
      await this.port.open(opts);
    } catch (e) {
      if ((e as DOMException)?.name === "InvalidStateError") return; // already open: reuse it
      await sleep(500);
      await this.port.open(opts);
    }
  }

  private async run(ev: SourceEvents) {
    await this.openPort();
    // The meter's RS232 interface is powered from DTR/RTS (silent with both low); pyserial raises them on open.
    await this.port.setSignals({ dataTerminalReady: true, requestToSend: true });
    await sleep(300);
    void this.readLoop();
    let misses = 0;
    while (!this.stopped) {
      if (this.calActive) {
        await sleep(50);
        continue;
      }
      if (this.sendMode) {
        const hit = findFrameAt(this.buf);
        if (hit) {
          this.buf.splice(0, hit.index + FRAME_LEN);
          ev.frame(now(), hit.frame, true);
        } else {
          if (this.buf.length > 4 * FRAME_LEN) this.buf.splice(0, this.buf.length - FRAME_LEN);
          await sleep(50);
        }
        continue;
      }
      const t = now();
      const f = (await (this.busy = this.pollFrame())) as Uint8Array | null;
      this.polls++;
      if (f) {
        misses = 0;
        ev.frame(t, f, false);
      } else {
        misses++;
        this.errors++;
        if (misses === NO_REPLY_LIMIT) ev.status("No reply from meter");
      }
      await sleep(Math.max(0, POLL_PERIOD - (now() - t)) * 1000);
    }
  }

  private async readLoop() {
    while (!this.stopped && this.port.readable) {
      this.reader = this.port.readable.getReader();
      try {
        for (;;) {
          const { value, done } = await this.reader.read();
          if (done) break;
          if (value) {
            this.rxBytes += value.length;
            for (const b of value) this.buf.push(b);
          }
        }
      } catch {
        // port error or cancelled by stop(); fall through
      } finally {
        this.reader.releaseLock();
        this.reader = null;
      }
    }
  }

  private async write(bytes: Uint8Array) {
    const w = this.port.writable!.getWriter();
    try {
      await w.write(bytes);
    } finally {
      w.releaseLock();
    }
  }

  /** Send the poll and wait (<= timeout) for a valid 59-byte frame. */
  private async pollFrame(timeout = 1.0): Promise<Uint8Array | null> {
    this.buf.length = 0;
    await this.write(request(0x00));
    const end = now() + timeout;
    while (now() < end) {
      const hit = findFrameAt(this.buf);
      if (hit) return hit.frame;
      await sleep(20);
    }
    return null;
  }

  private async readCal(idx: number, timeout = 1.0): Promise<number | null> {
    this.buf.length = 0;
    await this.write(request(CAL_READ, [idx]));
    const end = now() + timeout;
    while (now() < end) {
      const v = parseCalReply(this.buf, idx);
      if (v !== undefined) return v;
      await sleep(10);
    }
    return null;
  }

  /** Read all 256 calibration entries (read-only); polling pauses meanwhile. */
  async readAllCal(progress: (n: number) => void) {
    this.calActive = true;
    try {
      await this.busy;
      const ident = await this.pollFrame();
      const cal: Cal = new Map();
      for (let idx = 0; idx < 256 && !this.stopped; idx++) {
        cal.set(idx, await this.readCal(idx));
        progress(idx + 1);
      }
      return { cal, ident };
    } finally {
      this.calActive = false;
    }
  }

  async stop() {
    this.stopped = true;
    try {
      await this.reader?.cancel();
    } catch {
      /* already closed */
    }
    await this.loopDone;
    try {
      await this.port.close();
    } catch {
      /* not open */
    }
  }
}

/** Plays [label, frame] pairs from a capture file at POLL_PERIOD, looping. */
export class ReplaySource implements Source {
  sendMode = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  constructor(public frames: [string, Uint8Array][], public period = POLL_PERIOD) {}

  start(ev: SourceEvents) {
    if (!this.frames.length) {
      ev.failed("No valid frames in the capture file");
      return;
    }
    let i = 0;
    const step = () => {
      const [label, f] = this.frames[i % this.frames.length];
      ev.status(`replay ${(i % this.frames.length) + 1}/${this.frames.length}: ${label}`);
      ev.frame(now(), f, this.sendMode);
      i++;
    };
    step();
    this.timer = setInterval(step, this.period * 1000);
  }

  async stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
