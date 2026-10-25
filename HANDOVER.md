# Handover: long-run logging (branch `log-to-file`)

State as of 2026-10-24. Work so far was done without a meter. Every test used replay data, so the next
step is testing on the real meter. Delete this file before merging to `main`.

## What changed on this branch

1. **Log to file** (both apps). Tick *Log to file*, then press Start: you're asked for a CSV file, the header is
   written, and every logged row is added to the file in the Export CSV format.
   - Desktop: each row is written to disk as it is logged (the file is line-buffered).
   - Web: rows are held and appended every 5 s, and again on Stop or when the page closes
     (`apps/web-meter/src/filelog.ts`, File System Access API).
   - While logging to a file, only the newest 2000 rows stay in memory and in the history list
     (`HISTORY_ROWS` in `model.py` / `model.ts`). The row counter reads `rows: N → <file>`.
   - A write error stops logging and shows a message. The checkbox is locked while logging.
2. **Longer intervals**: the interval dropdown goes up to 1 h (0.5 s … 30 s, 1/2/5/10/15/30 min, 1 h).
3. **CLAUDE.md** added (commands and architecture).

Spec (`apps/spec/UI-SPEC.md`, Logging section) and tests in both apps are updated.

## Verified so far (no meter)

- `pytest`: 488 passed. `npm test`: 493 passed. `npm run build` passes, including the typecheck.
- Desktop app run offscreen with replay: rows were on disk while logging was running, memory and the
  history list were trimmed, and Stop closed the file.
- Web app in headless Chrome with replay: the header was written on Start, rows at the 5 s mark and the rest on
  Stop, with no lost or duplicated rows. The save dialog was replaced by a browser-private (OPFS) file, so the
  real save dialog and writing to a real disk file are untested.

## To test on the meter

Setup: see `CLAUDE.md` → Commands. Use the branch, not the hosted web app (that only updates from `main`):
`git switch log-to-file`, then `npm run dev` in `apps/web-meter`.

Desktop app:
- [ ] Log to file at 1 s for a few minutes, then Stop. Open the CSV: the header plus one row per second, and the values
      match the LCD.
- [ ] While it runs, open the CSV in another program. The rows should already be there (not only after Stop).
- [ ] A long interval (e.g. 1 min) over ~10 min gives about 10 rows. The first row is logged right at Start.
- [ ] Unplug the cable or switch the meter off mid-run, then reconnect. Logging should carry on, and no rows are
      written while the meter isn't sending.
- [ ] Close the window while logging. The file should be complete, not truncated.
- [ ] Overnight run (0.5 s or 1 s). Check memory use stays flat (the chart is the exception, see below) and the
      file is complete.

Web app (Chrome / Edge):
- [ ] The real save dialog appears on Start. The file on disk grows every ~5 s while logging.
- [ ] Reloading or closing the tab while logging: at most the last 5 s should be missing.
- [ ] Brave: with the file-access flag off, Start with *Log to file* ticked should show the message about
      `brave://flags/#file-system-access-api`.
- [ ] A CSV from the web app and one from the desktop app have identical columns and formatting.

## Tested on the meter (2026-10-25, Temp C)

- Desktop, 10 s interval: header and first row at Start, rows on disk while running, no missing or doubled rows,
  no rows while the meter was off and logging carried on after, file complete after closing the window.
- Web (Chrome): real save dialog works, file grows every 5 s, columns and header identical to the desktop CSV,
  reload mid-run keeps the file intact (see page-close note below).
- Not yet: values checked against the LCD, 1 s and 1 min desktop runs, overnight run, Brave flag message.

## Known issues and ideas

- **Chart memory**: the chart (`Series`) still keeps every reading of the current run (~170k points a day at
  2 Hz), and the "all" window redraws all of them. Multi-day runs may get sluggish. Fix: cap or thin the series.
- **Rows off the grid / skipped at 0.5 s (fixed 2026-10-25, retest on the meter)**: on the meter at 1 s, about
  every 7 s one row was missing and an extra one was logged 0.5 s later. Cause (reproduced in a test): meter
  timestamps jitter by ~1 ms and `Logger.offer` compared against the tick with only 1e-6 s slack, so a reading
  1 ms early was rejected. Fix: `TICK_SLACK = 0.1` s in `model.py` / `model.ts`, tests in both suites, spec note.
- **Page-close flush probably doesn't run** (web, accepted as is): on two reloads during logging the last write
  was the regular 5 s one, with nothing at the reload. The async write started on `pagehide` (`main.ts`) is likely
  killed by Chrome. Loss stays within the 5 s documented above.
- **Blank `Ohm` row after power-on**: switching the meter off and on mid-run logged one row with function `Ohm`
  and no values, then normal readings. Probably the meter's start-up frame (raw frame not captured).
- **"Log saved to …" status disappears at once** when connected over serial: the 250 ms status update overwrites
  it. The same already happens to Export CSV's "Saved N rows" message.
- **Idea**: add min, max and mean columns for each interval (each row is currently a single reading taken at that
  moment, so short spikes between rows don't appear in the file).

## Notes for Claude on the other machine

- A personal instruction from `~/.claude/CLAUDE.md` on the original machine (not in this repo): never treat an
  unclear or mistyped message as an instruction or approval; always ask what was meant first. Recreate it on
  the new machine if wanted.
- Don't push or commit without being asked. Branch before committing if on `main`.
