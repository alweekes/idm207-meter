// Arc bar meter as SVG: analogue-style bar along a semicircle, with a 1-2-5 auto scale (model.ArcScale).
import { ArcScale, prettyUnit } from "../model";
import { Reading } from "../protocol";

const W = 400, H = 250, CX = 200, CY = 205, R = 150, T = 22;
const pt = (frac: number, r: number): [number, number] => {
  const a = Math.PI * (1 - frac);
  return [CX + r * Math.cos(a), CY - r * Math.sin(a)];
};
const arc = (f0: number, f1: number) => {
  const [x0, y0] = pt(f0, R), [x1, y1] = pt(f1, R);
  return `M${x0.toFixed(1)},${y0.toFixed(1)} A${R},${R} 0 0 1 ${x1.toFixed(1)},${y1.toFixed(1)}`;
};

export const arcScale = new ArcScale();

export function renderArc(el: HTMLElement, r: Reading | null, stale: boolean) {
  const m = r?.main ?? null;
  const value = m ? m.value : null;
  const over = !!m?.overload;
  if (!stale) arcScale.update(value);
  const s = arcScale;
  const zero = s.bipolar ? 0.5 : 0;
  const end = over ? 1 : value !== null ? s.fraction(value) : zero;
  let svg = `<svg class="arc${stale ? " stale" : ""}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Arc meter">`;
  svg += `<path d="${arc(0, 1)}" class="track" stroke-width="${T}" fill="none"/>`;
  if (end !== zero) svg += `<path d="${arc(Math.min(zero, end), Math.max(zero, end))}" class="bar${over ? " over" : ""}" stroke-width="${T}" fill="none"/>`;
  for (let k = 0; k <= 50; k++) {
    const major = k % 10 === 0;
    const [x0, y0] = pt(k / 50, R + T / 2 + 2), [x1, y1] = pt(k / 50, R + T / 2 + (major ? 9 : 5));
    svg += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" class="tick"/>`;
  }
  for (const [f, v] of s.ticks()) {
    const [x, y] = pt(f, R - T / 2 - 14);
    svg += `<text x="${x.toFixed(1)}" y="${(y + 5).toFixed(1)}" text-anchor="middle" class="tl">${Number(v.toPrecision(3))}</text>`;
  }
  const txt = over ? "OL" : value === null ? "–" : String(Number(value.toPrecision(6)));
  svg += `<text x="${CX}" y="${CY - 50}" text-anchor="middle" class="val">${txt}</text>`;
  svg += `<text x="${CX}" y="${CY - 22}" text-anchor="middle" class="uni">${m ? prettyUnit(m.unit) : ""}</text></svg>`;
  el.innerHTML = svg;
}
