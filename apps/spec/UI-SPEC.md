# IDM207 virtual meter: shared behaviour spec

Both apps (`py-meter`, PyQt6, and `web-meter`, TypeScript + Web Serial) implement this spec, so they
can be compared like for like. Protocol details: `reverse-engineering/README.md`; decoder contract:
`test-vectors.json` (both test suites must pass all of it).

## Window layout
```
┌ toolbar ───────────────────────────────────────────────────────────────────────┐
│ Source: [port ▾] [Connect]  | [Replay capture…]  | Mode: (•) Poll ( ) SEND     │
│ status: Connected · IDM207 · s/n 03600916 · fw 0.00.06 · 2 polls/s · 0 errors  │
├ LCD ───────────────────────────────────────────────────────────────────────────┤
│ AUTO  DC  AC   MAX MIN PEAK AH REF Δ % dB dBm MEM SETUP  HI LO   RS232   key:F3 │
│   left:  20.0 ms  period                      right:  50.0 Hz  frequency        │
│                         -12.782  V                                             │
│ V DC                                                       (main sub-label)     │
├ chart ──────────────────────────────────────┬ stats ───────────────────────────┤
│ main value vs time (s)                      │ min / max / mean / count / OL    │
│                                             │ window: [1 min ▾]  [Reset]       │
├ logging ─────────────────────────────────────────────────────────────────────── ┤
│ interval [1 s ▾]  [Start] [Stop] [Clear]   rows: 123   [Export CSV…]            │
├ tools ─────────────────────────────────────────────────────────────────────────┤
│ [Backup calibration…]  [Compare calibration…]   progress / result              │
└────────────────────────────────────────────────────────────────────────────────┘
```

## Sources
- **Serial**: 9600 8N1, DTR and RTS raised (the meter's interface is powered from them; silent if both are low). Poll mode sends `55 55 00 00 AA` every 0.5 s (meter refreshes ~2×/s), with a
  1 s reply timeout. Count consecutive timeouts; status shows "No reply" after 3.
- **SEND mode**: no polling; display and log every frame the meter sends (one per F4 press, key = F4).
- **Replay**: load a `capture.log` (tab-separated `time  label  hex`); play each line containing a valid
  frame at 0.5 s per frame, looping. The label is shown in the status bar. Used for development, tests and
  side-by-side comparison of the two apps.
- **Allow-list**: only commands 0x00 and 0x0E can be sent. Anything else throws (unit-tested).

## LCD
- Main: `Display` text (number with the frame's decimals, `OL`, `----` blank, `[label]`), large 7-segment
  style; unit shown pretty (`Ohm`→`Ω`, `kOhm`→`kΩ`, `MOhm`→`MΩ`, `uF`→`µF`, `degC`→`°C`, `degF`→`°F`).
- Left / right: smaller, with unit and sub-code text; hidden when the display is unused (null).
- Function name from the rotary/sub-mode (e.g. `V DC`), bottom left; main sub-code if not `input`.
- Annunciators (lit/unlit), derived from the reading:
  - AUTO = autorange; DC / AC = from function name (`AC+DC` lights both).
  - MAX/MIN = any display sub `max` / `min` / `max-min`; PEAK = `peak *`; AH = `auto hold`;
    REF = `ref`; Δ = `delta`; % = `%`; dB/dBm = sub `dB` / `dBm`; MEM = `store`/`recall`/`number`;
    SETUP = `setup` (the SETUP menu; not the `set high`/`set low` limit labels).
  - HI / LO = `Reading.limit` (computed: the meter sends no flag).
  - RS232 = frame received in SEND mode; key = last non-empty key code (fades after 2 s).
- No decoded reading for 3 polls: LCD dims and shows "no reply".

## Arc meter
- Beside the LCD (about 60 / 40 width). A bar along a top semicircle, zero at the left end, with major
  tick labels (5 intervals), 50 minor ticks, and the main value + unit in the middle.
- Scale (`ArcScale`, tested in both apps): full scale is a 1-2-5 x 10^n value >= |value|; it grows at once
  and shrinks when |value| < 40 % of full scale (no flapping). After any negative value the arc is
  zero-centred (-FS..+FS, bar grows from the top centre) until the series restarts. The scale resets when
  the series restarts (function or unit change).
- OL: bar full in red, text `OL`. Blank/label readings: empty bar, `–`. Dimmed with the LCD when stale.

## Chart and stats
- Plot the main `value` (skip `None`: OL, blank, label) against seconds since the series start.
- A new series starts when function or main unit changes (mixing units makes no sense).
- Window: 1 min / 5 min / 30 min / all. Stats over the current series: min, max, mean, count, OL count.
- Reset clears the series and stats.

## Logging
- Interval 0.5 / 1 / 2 / 5 / 10 / 30 / 60 s: on each tick record the latest reading (if newer than the
  last recorded one). In SEND mode every received frame is recorded instead.
- Rows kept in memory (runs of minutes to hours). Start / Stop / Clear; row counter.
- History: scrolling list under the logging buttons (time `HH:MM:SS.mmm`, function, main value with unit),
  one line per logged row, stays at the newest row unless the user has scrolled up; Clear empties it.
- Export CSV: header `iso_time,` + `CSV_HEADER` from `test-vectors.json`, then
  `<ISO-8601 local time with ms>,` + `csv_row(epoch_seconds, reading)` (identical column formatting in both apps,
  e.g. `2026-10-17T20:18:33.950,1792264713.950,V DC,9.793,V,input,,,,,,,`).

## Tools (read-only)
- Backup calibration: pause polling, read entries 00–FF with `0E` (progress 0–256), show the three text
  fields (APPA model, model name, serial), save in the `calibration-backup-*.txt` format, resume polling.
- Compare calibration: load a backup file, read the meter, list differing entries `idx: old -> new`,
  show "N of 256 entries differ".
