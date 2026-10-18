// Wiring: sources, LCD, chart + stats, logging, calibration tools (apps/spec/UI-SPEC.md).
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { annunciators, displayText, Logger, prettyUnit, readCapture, Series } from "./model";
import { CAL_TEXT, calDiff, calFromText, calText, calToText, decode, Reading } from "./protocol";
import { ReplaySource, SerialSource, Source } from "./transport";
import { arcScale, renderArc } from "./ui/arc";
import { renderLcd } from "./ui/lcd";

const KEY_HOLD = 2; // s a key code stays shown
const STALE_AFTER = 1.5; // s without a frame (3 polls) before the LCD dims

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const statusEl = $("status");
const setStatus = (msg: string) => (statusEl.textContent = msg);

let source: Source | null = null;
let reading: Reading | null = null;
let ident = "";
let lastFrameT = 0;
let key = "", keyT = 0;
let fromSend = false;
let calBusy = false;
const series = new Series();
const logger = new Logger();

// ---- LCD ---------------------------------------------------------------------------------
function drawLcd(stale = false) {
  renderLcd($("lcd"), { reading, lit: reading ? annunciators(reading, fromSend) : new Set(), key, stale });
  renderArc($("arc"), reading, stale);
}
drawLcd(true);

// ---- chart -------------------------------------------------------------------------------
const chartEl = $("chart");
const plot = new uPlot(
  {
    width: chartEl.clientWidth || 600,
    height: 260,
    scales: { x: { time: false } },
    axes: [
      { label: "time (s)" },
      // enough significant digits that adjacent ticks differ (default rounding shows 1.76 five times)
      { label: "", size: 70, values: (_u, vals) => vals.map((v) => String(Number(v.toPrecision(6)))) },
    ],
    series: [{}, { label: "main", stroke: "#1f6feb", width: 2, points: { show: false } }],
    legend: { show: false },
  },
  [[], []],
  chartEl,
);
new ResizeObserver(() => plot.setSize({ width: chartEl.clientWidth, height: 260 })).observe(chartEl);

const fmtNum = (v: number | null) => (v === null ? "–" : String(Number(v.toPrecision(6))));

function updateChart() {
  const secs = Number(($("window") as HTMLSelectElement).value) || null;
  const [t, v] = series.window(secs);
  plot.setData([t, v]);
  const st = series.stats();
  const unit = reading?.main ? prettyUnit(reading.main.unit) : "";
  for (const k of ["min", "max", "mean"] as const) $(`st-${k}`).textContent = st[k] === null ? "–" : `${fmtNum(st[k])} ${unit}`;
  $("st-count").textContent = String(st.count);
  $("st-ol").textContent = String(st.ol);
}
$("reset").onclick = () => {
  series.reset();
  updateChart();
};
$("window").onchange = updateChart;

// ---- frames ------------------------------------------------------------------------------
function onFrame(t: number, f: Uint8Array, send: boolean) {
  const r = decode(f);
  reading = r;
  lastFrameT = t;
  fromSend = send;
  const id = `${r.model} · s/n ${r.serial} · fw ${r.firmware}`;
  if (id !== ident) {
    ident = id;
    $("ident").textContent = `Meter: ${id}`;
  }
  if (r.key) {
    key = r.key;
    keyT = t;
  }
  if (series.add(t, r)) {
    plot.axes[1].label = r.function;
    arcScale.reset();
  }
  logger.interval = Number(($("interval") as HTMLSelectElement).value);
  logger.offer(t, r, send);
  drawLcd();
  updateChart();
}

setInterval(() => {
  const now = Date.now() / 1000;
  if (key && now - keyT > KEY_HOLD) {
    key = "";
    drawLcd();
  }
  const sendMode = source?.sendMode ?? false;
  if (source && reading && now - lastFrameT > STALE_AFTER && !sendMode) drawLcd(true);
  $("rows").textContent = `rows: ${logger.rows.length}`;
  syncHistory();
  if (source instanceof SerialSource && !calBusy) {
    const silent = !sendMode && source.polls >= 4 && source.rxBytes === 0;
    const state = sendMode
      ? "SEND mode, waiting for F4"
      : silent
        ? "port open but no bytes received: check meter power and cable, and close other tabs or apps using this port"
        : `${source.polls} polls · ${source.errors} no-reply`;
    setStatus(`Connected · ${ident || "waiting for meter"} · ${state}`);
  }
}, 250);

// ---- sources -----------------------------------------------------------------------------
async function attach(s: Source) {
  await detach();
  source = s;
  s.sendMode = sendRadio().checked;
  s.start({
    frame: onFrame,
    status: setStatus,
    failed: (msg) => {
      setStatus(msg);
      alert(msg);
    },
  });
  $("connect").textContent = "Disconnect";
}

// Release the serial port when the page goes away (reload, navigation, tab close) so the next page can open it.
addEventListener("pagehide", () => void source?.stop());

async function detach() {
  if (source) await source.stop();
  source = null;
  $("connect").textContent = "Connect";
  drawLcd(true);
}

const sendRadio = () => document.querySelector<HTMLInputElement>('input[name="mode"][value="send"]')!;

// ---- port selection ----------------------------------------------------------------------
// A page can only see ports the user has allowed once through Chrome's picker; those are listed
// in the dropdown (Chrome exposes no device path, only USB ids). The last-used one is remembered.
const portSelect = $("port") as HTMLSelectElement;
let ports: SerialPort[] = [];
const LAST_PORT = "idm207.lastPort";
const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
};

function portLabel(p: SerialPort, n: number): string {
  const info = p.getInfo();
  const h4 = (x: number) => x.toString(16).padStart(4, "0");
  if (info.usbVendorId !== undefined) return `USB serial ${h4(info.usbVendorId)}:${h4(info.usbProductId ?? 0)}`;
  return `Serial port ${n} (onboard / non-USB)`;
}
const portKey = (p: SerialPort, i: number) => {
  const info = p.getInfo();
  return `${info.usbVendorId ?? "-"}:${info.usbProductId ?? "-"}:${i}`;
};

async function refreshPorts(select?: SerialPort) {
  if (!SerialSource.supported()) return;
  ports = await navigator.serial.getPorts();
  const want = select ? ports.indexOf(select) : ports.findIndex((p, i) => portKey(p, i) === store.get(LAST_PORT));
  portSelect.innerHTML = "";
  ports.forEach((p, i) => portSelect.add(new Option(portLabel(p, i + 1), String(i))));
  portSelect.add(new Option("Add port…", "add"));
  portSelect.value = want >= 0 ? String(want) : ports.length ? "0" : "add";
}

async function connectSelected() {
  let port: SerialPort;
  if (portSelect.value === "add") {
    port = (await SerialSource.choose()).port; // Chrome's picker (needs a user click)
    await refreshPorts(port);
  } else {
    port = ports[Number(portSelect.value)];
  }
  store.set(LAST_PORT, portKey(port, ports.indexOf(port)));
  await attach(new SerialSource(port));
}

if (!SerialSource.supported()) {
  $("unsupported").hidden = false;
  ($("connect") as HTMLButtonElement).disabled = true;
  portSelect.disabled = true;
} else {
  navigator.serial.addEventListener("connect", () => refreshPorts());
  navigator.serial.addEventListener("disconnect", () => refreshPorts());
}

$("connect").onclick = async () => {
  if (source) {
    await detach();
    setStatus("Disconnected");
    return;
  }
  try {
    await connectSelected();
  } catch (e) {
    setStatus(`Not connected (${(e as Error).message})`);
  }
};
// choosing "Add port…" while disconnected opens the picker straight away
portSelect.onchange = () => {
  if (!source && portSelect.value === "add") $("connect").click();
};

($("replay") as HTMLInputElement).onchange = async (ev) => {
  const file = (ev.target as HTMLInputElement).files?.[0];
  if (!file) return;
  await attach(new ReplaySource(readCapture(await file.text())));
  (ev.target as HTMLInputElement).value = "";
};

// ?replay=<url> starts replaying a capture log on load (demos, testing without a meter);
// otherwise reconnect to the last-used port if Chrome still allows it (no picker needed)
const replayUrl = new URLSearchParams(location.search).get("replay");
if (replayUrl) {
  fetch(replayUrl)
    .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`${r.status} ${r.statusText}`))))
    .then((text) => attach(new ReplaySource(readCapture(text))))
    .catch((e) => setStatus(`Cannot load replay ${replayUrl}: ${e.message}`));
} else {
  refreshPorts().then(() => {
    const last = store.get(LAST_PORT);
    if (last && portSelect.value !== "add" && portKey(ports[Number(portSelect.value)], Number(portSelect.value)) === last) {
      setStatus("Reconnecting to the last-used port…");
      connectSelected().catch((e) => setStatus(`Not connected (${(e as Error).message})`));
    }
  });
}

for (const radio of document.querySelectorAll<HTMLInputElement>('input[name="mode"]')) {
  radio.onchange = () => {
    if (source) source.sendMode = sendRadio().checked;
  };
}

// ---- logging -----------------------------------------------------------------------------
$("log-start").onclick = () => {
  logger.interval = Number(($("interval") as HTMLSelectElement).value);
  logger.start();
  ($("log-start") as HTMLButtonElement).disabled = true;
  ($("log-stop") as HTMLButtonElement).disabled = false;
};
$("log-stop").onclick = () => {
  logger.stop();
  ($("log-start") as HTMLButtonElement).disabled = false;
  ($("log-stop") as HTMLButtonElement).disabled = true;
};
$("log-clear").onclick = () => {
  logger.clear();
  syncHistory();
};

/** Mirror logger.rows into the history list (append new rows, stay scrolled to the end). */
let shown = 0;
function syncHistory() {
  const el = $("history");
  const rows = logger.rows;
  if (shown > rows.length) {
    el.replaceChildren();
    shown = 0;
  }
  if (shown === rows.length) return;
  const follow = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
  const frag = document.createDocumentFragment();
  for (; shown < rows.length; shown++) {
    const [t, r] = rows[shown];
    const row = document.createElement("div");
    for (const text of [new Date(t * 1000).toTimeString().slice(0, 8) + "." + String(Math.round(t * 1000) % 1000).padStart(3, "0"),
                        r.function, displayText(r.main)]) {
      const cell = document.createElement("span");
      cell.textContent = text;
      row.append(cell);
    }
    frag.append(row);
  }
  el.append(frag);
  if (follow) el.scrollTop = el.scrollHeight;
}

const stamp = () => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
};

async function saveText(name: string, text: string, mime: string) {
  // File System Access API where available (Chromium), otherwise a download
  const picker = (window as unknown as { showSaveFilePicker?: (o: object) => Promise<FileSystemFileHandle> }).showSaveFilePicker;
  if (picker) {
    try {
      const h = await picker({ suggestedName: name });
      const w = await h.createWritable();
      await w.write(text);
      await w.close();
      return true;
    } catch (e) {
      if ((e as Error).name === "AbortError") return false;
    }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: mime }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
  return true;
}

$("log-export").onclick = async () => {
  if (!logger.rows.length) return alert("Nothing logged yet.");
  if (await saveText(`idm207-log-${stamp()}.csv`, logger.csv(), "text/csv")) setStatus(`Saved ${logger.rows.length} rows`);
};

// ---- calibration tools -------------------------------------------------------------------
const calOut = $("cal-text");
const calBar = $("cal-progress") as HTMLProgressElement;

async function readCal() {
  if (!(source instanceof SerialSource)) {
    alert(source ? "Calibration tools need a live meter (not available in replay)." : "Connect to the meter first.");
    return null;
  }
  calBusy = true;
  setStatus("Reading calibration…");
  calOut.textContent = "Reading 256 calibration entries (read-only)…";
  try {
    const res = await source.readAllCal((n) => (calBar.value = n));
    const missing = [...res.cal.values()].filter((v) => v === null).length;
    const lines = Object.entries(CAL_TEXT).map(([name, [a, b]]) => `${name}: ${calText(res.cal, a, b)}`);
    if (missing) lines.push(`no reply for ${missing} entries`);
    return { ...res, lines, missing };
  } finally {
    calBusy = false;
  }
}

$("cal-backup").onclick = async () => {
  const res = await readCal();
  if (!res) return;
  const d = new Date();
  const when = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${d.toTimeString().slice(0, 8)}`;
  if (await saveText(`calibration-backup-IDM207-${stamp()}.txt`, calToText(res.cal, res.ident, when), "text/plain")) {
    res.lines.push(`saved ${256 - res.missing} entries`);
  }
  calOut.textContent = res.lines.join("\n");
};

($("cal-compare") as HTMLInputElement).onchange = async (ev) => {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  const old = calFromText(await file.text());
  const res = await readCal();
  if (!res) return;
  const hex = (v: number | null | undefined) => (v === null || v === undefined ? "----" : v.toString(16).toUpperCase().padStart(4, "0"));
  const diff = calDiff(old, res.cal);
  for (const [i, o, n] of diff) res.lines.push(`${i.toString(16).toUpperCase().padStart(2, "0")}: ${hex(o)} -> ${hex(n)}`);
  res.lines.push(`${diff.length} of 256 entries differ from ${file.name}`);
  calOut.textContent = res.lines.join("\n");
};
