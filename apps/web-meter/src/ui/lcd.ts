// Virtual LCD as SVG: annunciator row, left/right secondary displays, large 7-segment main reading.
import { ANNUNCIATORS, displayText, prettyUnit } from "../model";
import { Reading } from "../protocol";

const W = 1000, H = 300;
const SEGMENTS: Record<string, string> = {
  "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
  "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", O: "abcdef", L: "fed", " ": "",
};

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const pts = (p: [number, number][]) => p.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

function digit(x: number, y: number, w: number, h: number, segs: string): string {
  const t = w * 0.16, hh = h / 2;
  const hseg = (cy: number): [number, number][] => [[x + t * 0.6, cy], [x + t * 1.1, cy - t / 2], [x + w - t * 1.1, cy - t / 2],
    [x + w - t * 0.6, cy], [x + w - t * 1.1, cy + t / 2], [x + t * 1.1, cy + t / 2]];
  const vseg = (cx: number, y0: number, y1: number): [number, number][] => [[cx, y0 + t * 0.6], [cx + t / 2, y0 + t * 1.1],
    [cx + t / 2, y1 - t * 1.1], [cx, y1 - t * 0.6], [cx - t / 2, y1 - t * 1.1], [cx - t / 2, y0 + t * 1.1]];
  const shapes: Record<string, [number, number][]> = {
    a: hseg(y + t / 2), g: hseg(y + hh), d: hseg(y + h - t / 2),
    f: vseg(x + t / 2, y, y + hh), b: vseg(x + w - t / 2, y, y + hh),
    e: vseg(x + t / 2, y + hh, y + h), c: vseg(x + w - t / 2, y + hh, y + h),
  };
  return Object.entries(shapes)
    .map(([n, p]) => `<polygon points="${pts(p)}" class="${segs.includes(n) ? "on" : "off"}"/>`)
    .join("");
}

export interface LcdState { reading: Reading | null; lit: Set<string>; key: string; stale: boolean }

export function renderLcd(el: HTMLElement, s: LcdState) {
  const r = s.reading;
  const parts: string[] = [];
  // annunciators
  let x = 20;
  for (const name of ANNUNCIATORS) {
    const lit = s.lit.has(name) && !s.stale;
    parts.push(`<text x="${x}" y="34" class="ann ${lit ? "on" : "off"}">${esc(name)}</text>`);
    x += name.length * 11 + 22;
  }
  if (s.key) parts.push(`<text x="${W - 20}" y="34" text-anchor="end" class="ann on">key ${esc(s.key)}</text>`);
  // secondary displays
  const sec = (d: Reading["left"], anchor: "start" | "end", tx: number) => {
    if (!d) return;
    const sub = d.labelOnly ? "" : `  ${d.sub}`;
    parts.push(`<text x="${tx}" y="82" text-anchor="${anchor}" class="sec">${esc(displayText(d) + sub)}</text>`);
  };
  sec(r?.left ?? null, "start", 22);
  sec(r?.right ?? null, "end", W - 22);
  // main reading
  const top = 104, dh = 124;
  const m = r?.main ?? null;
  if (!r && s.stale) {
    parts.push(`<text x="${W / 2}" y="${top + dh / 2 + 18}" text-anchor="middle" class="big">no reading</text>`);
  } else if (!m || m.labelOnly) {
    parts.push(`<text x="${W / 2}" y="${top + dh / 2 + 18}" text-anchor="middle" class="big">${m ? esc(`[${m.sub}]`) : ""}</text>`);
  } else {
    const text = m.blank ? "----" : m.overload ? " OL" : m.value!.toFixed(m.decimals);
    const unit = prettyUnit(m.unit);
    const dw = dh * 0.52;
    const n = [...text].filter((c) => c !== ".").length;
    const uw = unit.length * 30 + 16;
    let cx = Math.max(10, (W - n * dw * 1.25 - uw) / 2);
    for (const c of text) {
      if (c === ".") {
        parts.push(`<circle cx="${cx - dw * 0.12}" cy="${top + dh - dw * 0.08}" r="${dw * 0.09}" class="on"/>`);
        continue;
      }
      parts.push(c in SEGMENTS ? digit(cx, top, dw, dh, SEGMENTS[c])
        : `<text x="${cx + dw / 2}" y="${top + dh}" text-anchor="middle" class="big">${esc(c)}</text>`);
      cx += dw * 1.25;
    }
    parts.push(`<text x="${cx + 6}" y="${top + dh}" class="unit">${esc(unit)}</text>`);
  }
  // function name and main sub-label
  if (r) {
    parts.push(`<text x="22" y="${H - 26}" class="func">${esc(r.function)}</text>`);
    if (m && m.sub !== "input" && m.sub !== "" && !m.labelOnly) {
      parts.push(`<text x="${W - 22}" y="${H - 26}" text-anchor="end" class="func">${esc(m.sub)}</text>`);
    }
  }
  if (s.stale) parts.push(`<text x="${W / 2}" y="${H - 26}" text-anchor="middle" class="func">no reply</text>`);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="lcd ${s.stale ? "stale" : ""}" role="img" aria-label="meter display">
    <rect width="${W}" height="${H}" rx="14" class="bg"/>${parts.join("")}</svg>`;
}
