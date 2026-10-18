# IDM207 virtual meter (TypeScript + Web Serial)

Same features as `../py-meter`, in the browser: virtual LCD, live chart (uPlot) and statistics, CSV
datalogging, SEND-key capture and read-only calibration backup/compare. Behaviour follows `../spec/UI-SPEC.md`.

## Run
```
npm install
npm run dev        # open the printed http://localhost:5173 in Chrome / Edge / Opera / Brave
npm test           # shared test vectors + app logic (Vitest)
npm run build      # static site in dist/ (serve over https or localhost for Web Serial)
```
**Ports:** the Port dropdown lists ports you have already allowed for this page; choose **Add port…**
(or Connect with it selected) to open Chrome's port picker the first time. Chrome exposes no device names,
so non-USB ports show as "Serial port N (onboard / non-USB)" (`/dev/ttyS0` / COM1) and USB adapters by
vendor:product id. The last-used port is remembered and reconnected automatically when the page loads.
`?replay=<url>` replays a capture log on load instead (e.g. `?replay=/@fs/<abs path>/capture.log` with `npm run dev`).

Web Serial needs a Chromium-based browser and a secure context (localhost or https). Firefox and
Safari can still use **Replay capture…** (e.g. `../../reverse-engineering/capture.log`).
Linux: your user needs access to the port (`uucp` group on Arch, `dialout` on Debian/Ubuntu).

## Layout
- `src/protocol.ts`: port of `idm207meter/protocol.py` (decode, tables, CSV, calibration file format,
  command allow-list: only 0x00 and 0x0E).
- `src/model.ts`: annunciators, unit names, chart series/stats, logger, capture parsing.
- `src/transport.ts`: `SerialSource` (Web Serial poll / SEND listen / calibration read), `ReplaySource`.
- `src/ui/lcd.ts`: SVG 7-segment LCD. `src/main.ts`: page wiring.
