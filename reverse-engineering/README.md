# WinDMM (ISO-TECH IDM207) reverse engineering

WinDMM.EXE is a LabVIEW 5.0.1 built application; the VIs are stored as
`CPRF` resources inside an embedded `APPL` resource file.

## Layout
- `scripts/` – tools (Python 3; `disasm.py`/`sw.py` need `pip install capstone`)
  - `carve.py EXE OUT` – extract compressed CPRF resources from WinDMM.EXE
  - `unz.py IN OUT` – decompress them (zero-suppression: u32 BE length,
    ceil(n/8) bitmask bytes LSB-first, 1 = take next literal, 0 = 0x00, then literals)
  - `rsrc.py FILE` – list resources in a LabVIEW v3 RSRC file
  - `dstm.py DSTM.bin` – dump the data-space type map entries
  - `disasm.py CODE.bin` – disassemble a VICD code blob (x86-32)
  - `sw.py CODE.bin TABLE_HEX N_HEX` – decode a compiled case-structure jump table
  - `poll.py PORT -l LOG --label TEXT` – raw capture tool (hex dump + rough decode)
  - `idm207.py PORT [--csv]` – **standalone reader** (pyserial only); `--listen` logs SEND presses; `--decode-log FILE` decodes captures offline;
    `--backup-cal FILE` saves the 256 calibration constants, `--compare-cal FILE` checks them against a backup (both read-only, cmd 0E)
- `vis_compressed/` – raw CPRF resources as carved from the EXE
- `vis_decompressed/` – decompressed VIs / run-time menus (standard LabVIEW RSRC files)
- `blocks/` – per-block extraction (via pylabview `readRSRC -x`) of Menu.vi, Data.vi, DC V.vi;
  `blocks/Menu/menu.asm` is the disassembly of Menu.vi's compiled code, `dstm.txt` its type map

## Re-running
    python3 scripts/carve.py ../Andrew/WinDMM.EXE vis_compressed
    python3 scripts/unz.py vis_compressed vis_decompressed

## Protocol (verified on a real IDM207, fw 0.00.06, 2026-10-17)
The IDM207 is the ISO-TECH-badged **APPA 207**. The handheld APPA 303 is a different device, but it shares the
same software (WinDMM) and therefore the same protocol, so the frame matches
`../WinDMM300-RS232-Protocol-Summary.md` byte for byte. Captures of every
rotary position are in `capture.log` (decode with `scripts/idm207.py --decode-log capture.log`).

- 9600 baud, 8N1. Poll `55 55 00 00 AA`; reply is 59 bytes, starting `55 55 00 36`.
  Sync on the header: the first read after opening the port may have a junk byte in front.
- Checksum (byte 58) = sum of bytes 0–57 mod 256 (not mod 100).

| Bytes | Field |
|---|---|
| 0–3 | header `55 55 00 36` |
| 4–11 / 12–19 / 20–26 | model / serial / firmware, ASCII |
| 27 | rotary: 1 V, 2 mV, 3 Ω, 4 diode, 5 mA, 6 A, 7 cap, 8 Hz, 9 temp |
| 28 | sub-mode (blue key): V/mV/mA/A 0 DC 1 AC 2 AC+DC; Ω 0/1 low-Ω; diode 0/1 continuity; Hz 0/1 duty; temp 0 °C 1 °F |
| 29 | key code, **momentary** (~1 s after a press, else 00): 01–04 F1–F4, 05 Light (+), 06 Bar (−), 07 Digit (←), 08 Range (→), 09 Circle (menu row), 0A Blue. Brackets = function when editing a value. All seen except 01/02 (F1/F2 presses fell between polls). |
| 30 | range: low 7 bits per APPA tables (depend on function *and* sub-mode); bit 7 set = not autoranging |
| 31–33 | A/D, raw |
| 34–39 / 40–45 / 46–51 | main / left / right display: lo, hi, sign, point, unit, sub-code |
| 52–54 / 55–57 | "DC" / "AC" fields, raw |
| 58 | checksum |

Display decoding:
- value = lo + 256·hi, **sign-magnitude**: sign byte `80` = negative (confirmed with reversed leads).
- point 00/01/02/04/08 = 0/1/2/3/4 decimal places.
- unit and sub-code follow the APPA tables (WinDMM's labels "status"/"unit" are really unit/sub-code).
  Seen: V, mV, A, mA, Ω, kΩ, MΩ, µF, %, Hz, ms, °C, °F; sub-codes input, frequency, period, ambient.
- **Overload** = full scale + 1 count, no flag: 40001 (Ω, 40 MΩ range), 2001 (continuity, 200.0 Ω),
  **4001 in 4000-count mode** (Ω open, `A1 0F 00 02 0C 01` = "40.01 MΩ"). 4001 is also a valid
  40000-count value, so the reader only treats it as OL when autoranging above the lowest range;
  in manual range a 4001 reading is ambiguous.
- **DIGIT** toggles 40000 / 4000 counts (manual 3.3). In 4000-count mode the point code drops one
  decimal (13.16 V on the 40 V range); the frame has no count-mode flag. Leaving PH and returning to
  autorange cleared bytes 52–57.
- Diode mode with open leads shows the open-circuit voltage (≈2.95 V), not OL.
- Unused display = all zeros. A secondary display with value 0 and point 00 is blank on the LCD
  (only the unit symbol shows), e.g. the period display in AC modes with no signal.
- Continuity: no beep flag anywhere in the frame; infer from the value.

Each Blue press cycles the sub-mode (V: DC → AC → AC+DC → DC) with key code 0A in the first frame.
The first frame after switching into AC can carry a stale frequency/period (e.g. 49.9 Hz, 243 Hz with
no input) before the secondary displays blank; skip one poll after a mode change if that matters.

Secondary displays by function:
- V/mV/mA/A AC: left = period (ms), right = frequency (Hz). AC+DC: both empty.
- Hz: left = period. Duty: main = %, left = period, right = Hz.
- Temp: right = meter's internal (cold-junction) ambient temperature.

Raw fields (31–33, 52–57) are not on the display's scale and should not be used as readings:
the AC raw value is ~1.12× low and carries sign byte `80` regardless of polarity; the DC field
is on the display scale in mA but ~4.2× high in A; cap/Hz/temp put unrelated counters there.

Bit 7 of the range code: set for single-range functions (mV AC/AC+DC, diode, continuity, duty, temp)
and capacitance (stays set after RANGE, which steps 83 → 84); the LCD shows no AUTO/MANU in any case.
In temp the range toggles 80/81 between polls.

## PC → meter commands (probed 2026-10-17)
Requests are framed `55 55 cmd len [data] chk` (chk = byte sum mod 256; the usual poll `55 55 00 00 AA`
is cmd 00). Bad checksum, bad sync or a truncated frame get no reply.

| cmd | reply (cmd, len, payload) |
|---|---|
| 00 | full 54-byte frame (len 00 or with extra data bytes) |
| 01 / 02 / 03 | model (8) / serial (8) / firmware (7) |
| 04 / 05 / 06 / 07 | rotary / sub-mode / key / range (1 each) |
| 08 | A/D (3) |
| 09 / 0A / 0B | main / left / right display (6 each) |
| 0C / 0D | DC / AC fields (3 each) |
| 0E | 3 bytes `00 FF FF`, constant (not a measurement) |
| 0F–7F | no reply |
| **80** | **write model name** (8 data bytes) → `55 55 7F 00 29` OK. With no data it wrote a stale buffer |
| 86 + data 0A | no reply, no effect (tried as "press Blue") |

**⚠ Do not send commands ≥ 0x80** without a calibration backup and a reason. After the scan (0F–7F, 80, then 86 0A) the meter's stored
**model name was overwritten** (since restored, see CalWin300 section) with `00 FF FF 00 00 00 00 00` (survives a full power-off).
Serial, firmware and measurements were unaffected. Which command did it is unknown: the full frames
between commands weren't logged. WinDMM only displays the model name, it doesn't check it.
APPA's generic protocol (sigrok `appa-dmm`) puts calibration/EEPROM writes at 0x85/0x87/0x8A,
CAL_EXIT at 0x8F, OTA firmware commands at 0xA0–0xA3. No key-press/set-mode command was found;
none is used by WinDMM.

sigrok's `appa-dmm` driver lists the 207 under the "300 series" legacy protocol as *assumed*; its
decoder (24-bit BE reading at frame bytes 33–35, overload bit in byte 45) does not match this meter.
It adds sub-codes 25 = blank ("space") and 27 = "Er".

## CalWin300 (APPA 300-series calibration software), static analysis only
`../CalWIN300/DATA.001` holds PKWARE-DCL "implode" streams (decompress with zlib's contrib/blast
from offset 0x114); member 3 is `CalWIN300.exe` (LabVIEW 5.1), copied to `calwin300/`. Its VIs are
CPRF resources in an LVAR library at 0xa800; `calwin300/vis_decompressed/` (via `scripts/unz.py`).
VI names: Write Password to meter, Write Codeing to meter, Get EEPROM, Get Value of codeing,
GainOffset(50), Serial Port Demessage for APPA300. Comm: 9600 baud, 500 ms timeouts.

Request frames found as constants (checksums verify where complete):
| cmd | frame | role (from VI name / context) |
|---|---|---|
| 00 | `55 55 00 00 AA` | "Get EEPROM" = normal read-all |
| 0E | `55 55 0E 01 <idx>` | read 24-bit calibration constant at index (57h/58h 60 Hz, 8Ah/8Bh 50 Hz in GainOffset) |
| 85, 87 | `55 55 85 …`, `55 55 87 …` | match APPA generic protocol: CAL write function / range code |
| 88, 89, 93, 94, 95, 98 | `55 55 cc …`; 89 also `55 55 89 02 00 03 38` | unknown calibration controls |
| 90 | `55 55 90 03 <s24>` | write calibration ("coding") value, no address |
| 91 | `55 55 91 01 0A 46` | write password 0x0A (unlock), expects 7F |
Main VI also holds the SCPI strings sent to a calibrator (e.g. `FUNC DC;:VOLT 3.6;:OUTP 1`) and the step
list (DCV/ACV/AC+DC/mV/Ω/LVΩ/cap/mA/A/temp offset & gain, each for 50 and 60 Hz line frequency).

CalWin300 never sends 0x80 or 0x86, so the model-name overwrite was not a calibration write.
Hypothesis: 0x80 = factory "write model name" (cf. APPA legacy-500 0x81 write model, 0x82 write serial);
sent with no data it stored a stale buffer (new model starts `00 FF FF`, the last 0E reply).
**Confirmed 2026-10-17:** `55 55 80 08 49 44 4D 32 30 37 20 20 E5` (0x80 + 8 bytes) replied `7F` and restored
the model name; `--compare-cal` showed only E1–E4 changed (FF00 00FF 0000 0000 → 4449 324D 3730 2020).
So **0x80 = write model name** (8 bytes, stored in calibration entries E1–E4); with no data it writes a stale buffer.

**Calibration constant backup** (2026-10-17, before any further experiments):
`calibration-backup-IDM207-03600916.txt`, read with `55 55 0E 01 <idx> cs` for idx 00–FF (works without
the password; reply payload = idx, value lo, value hi; `0E` with no data reads idx 00). Gains ≈ 0x2200–0x2800,
offsets small with bit 15 as sign, unused = FFFF. Entries DD–E8 hold text (little-endian byte pairs):
DD–E0 `APPA303R` (APPA's internal model string, from the shared 300-series firmware family), **E1–E4 = model name** (`IDM207  `; was overwritten, restored), E5–E8 = serial `03600916`. EA = `00 0A` (password 0A?).

## Menu functions (circle key selects row M1–M4, F1–F4 select column; see `LCD_Table.md`)
- **M1 STORE** (V AC): main = live input; left = memory location (no unit, sub 08 "number");
  right = value stored there (sub 09). Each STORE press saves the reading to the next location.
- **M1 RECALL**: left = location (sub 08), right = stored value with its unit (sub 0A). Stepping
  through locations on the meter changes the frame accordingly (4 → 1 read back 1.6047, 1.6047,
  1.6371, 1.6362 V). The PC cannot select a location; memory download means paging on the meter while polling.
- **M1 RESET** (F3): clears the stored readings; RECALL can't be entered afterwards. No RESET
  screen (sub 0B) was seen in the frames; the meter dropped straight back to normal V AC.
- **M2 MAX / MIN / MAX-MIN** (V DC): main stays live (sub 01). Right = recorded value with sub
  0D max / 0E min / 0F max-min. Left = time stamp in seconds (unit 14 s, sub 06) of the latest
  max/min event. One recording session runs from when MAX is first engaged; F1–F3 only change the view.
- **M2 PEAK HOLD** (V DC, manual 5.6): F4 toggles PH (LCD "PH"); 0.5 ms peak capture. The main display
  stays the live reading (sub 01). Range locks (01 → 81). Inside PH, **F1/F2/F3 select the view**:
  - right = peak max (sub 10) / peak min (sub 11) / peak max-min (sub 12), **2 decimals** (point 02);
  - left = time stamp in seconds (unit 14, sub 06) of the latest new peak, counted from the start of the
    peak session (blank while no peak has been recorded).
  - Peak min only tracks values below zero: 0.00 with a positive-only input; −17.97 V after reversing leads.
  - Max-min = max − min (14.37 − (−17.97) = 32.34 V).
  - A new session started once between captures (time stamps imply ~17:57:36), clearing the old 15.10 V max;
    trigger not identified.
  - **Bytes 52–54 / 55–57 = highest / lowest raw sample of the latest short peak window**, on the main count
    scale, updated alternately. Only non-zero while PH is on (they persisted while PH stayed on during other
    menu views), so they are the nearest thing to a PH flag in the frame. There is no explicit PH bit.
  Before F1–F3 are pressed, the left/right displays are empty.
- PEAK HOLD is a toggle that stays on while other menu views are used (PH still lit in AUTOHOLD).
- **M1 AUTOHOLD** (V DC): right = held value, sub 0C. Re-captures (with a beep) whenever the input settles
  at a new value; left is empty.
- **M3 REF** (V DC): main = reference value (sub 19), editable on the meter and sent live as it's
  edited (default 40.000 = range full scale); right = live input (sub 01).
- **M3 Delta** (press F3): main = input − REF (sub 17, unit stays V, not the 0E "Delta" unit),
  left = REF (sub 19), right = input (sub 01).
- **M3 %** (press F3 again): main = (input − REF)/REF × 100, unit 0D %, sub 18, 2 decimals
  (10.99 % with REF 11.000 V, input 12.209 V). **Overrange is sent as 0.00 %**, not full scale + 1;
  `idm207.py` flags it as OL when REF and input differ.
- **M3 HIGH** (V DC): main = live input (sub 01); left = text label only (`00 00 00 00 00 13`,
  "HISET" on the LCD); right = the high limit (sub 15). The value is set on the meter.
  That is only the *setting* screen. **Pressing F1 again activates the comparison** (manual 5.7):
  left = active limit (12.000 V, sub 15), right empty. The LCD then shows **HI** above the limit, but
  **the frame carries no HI/LO flag** (range, 52–57, sub-codes unchanged). `idm207.py` compares the
  reading against the limit (left or right display) and flags [HI]/[LO] itself.
  (A key code 05 seen at the crossing was the backlight button being pressed, not an event marker.)
- **M3 LOW** (F2): mirrors HIGH: left = label "set low" (sub 14), right = low limit (sub 16).
  The limit starts at −40.000 V (REF starts at +40.000); edited with +/− (Light/Bar) and ←/→ (Digit/Range),
  each press visible in key byte 29. With LOW 12.000 V and input 11.876 V the reader flags [LO];
  (setting screen only; compare not activated with a second F2 press).
  Bytes 52–57 were zero here (the stale peak-hold values had been cleared by then).
- **M4 SETUP**: pages are beep, A.P.O. (auto power-off; keep off for logging), backlight time,
  HAZ (hazard voltage warning), LFREQ (50/60 Hz), dBm load (600 Ω), reset — matching sub-codes
  1E–24. Page 1 frame: main [setup] (1D), left [setup], right [set beeper] (1E), all values 0.
  Toggling beep on/off changed nothing in the frame: **setting values are not transmitted**.
  All seven pages confirmed: right display 1E beep, 1F A.P.O., 20 backlight, 21 HAZ, 22 L.FrEq,
  23 LoAd, 24 rESEt (main/left stay 1D). +/− on any page only shows in the key code.
  One transitional frame on entering SETUP had a stray value (`2D 00 00 00 00 1D`); the reader treats
  any unitless display (other than a memory number) as a label.
- **M4 dBm** (V AC): main = dBm (unit 06, sub 1A, 2 decimals), left = load 600 Ω (unit 0A, sub 07),
  right = input V (sub 01). 6.52 dBm at 1.6477 V ≈ 20·log10(V/0.7746); dBm lags the V reading slightly.
- **M4 dB** (press F3 again): main = dB (unit 05, sub 1B), left empty, right = input.
  Reference is **1 V (dBV)**, not the M3 REF value: 4.35 dB at 1.6547 V.
- **M4 SEND** (F4): the meter transmits one frame **unsolicited** per F4 press (no poll needed).
  Same 59-byte frame, valid checksum, **key code byte 29 = 04 (F4)** (00 in polled frames);
  in V AC the left/right displays were empty. A stray byte (FE) may precede the first frame.
  `idm207.py PORT --listen` logs these.
- **ProbE** (lead in a current jack with a non-current function, manual 6.2): main = label only
  `00 00 00 00 00 26` (sub 26 probe); left/right, A/D and 52–57 all zero. FUSE (sub 28, manual 6.1)
  is expected to look the same; not tested.
- A display with value 0, unit 00 and a non-zero sub-code is a **text label** (e.g. HISET); the reader shows it as `[label]`.
- While in REF/Delta/% the range stays locked (81) and bytes 52–57 kept the same stale values seen
  under PEAK HOLD (`3D 30 00 56 30 00`), although PH was thought to be off; they had cleared by the LOW captures, so they were most likely leftover PH window samples.
- In Temp, PEAK HOLD changed nothing in the frame (probably not supported there).

## Deferred experiment: password unlock + read (not done; user decision 2026-10-17)
Goal: see whether CalWin300's "Get EEPROM" poll returns different data once the meter is unlocked,
and confirm the password. Benefit is understanding calibration internals only; nothing needed for logging.
Procedure (send nothing else in between):
1. `idm207.py PORT --compare-cal calibration-backup-IDM207-03600916-restored.txt` → expect 0 differences.
2. Send `55 55 91 01 0A 46` (0x91 password 0A). **Stop unless the reply is `55 55 7F 00 29`.**
3. Send `55 55 00 00 AA`; save and compare the reply with a normal 59-byte frame.
4. Power-cycle the meter fully (rear switch + mains) to leave calibration mode.
5. Run `--compare-cal` again → expect 0 differences.
Risks: low for the two frames (CalWin300's own first steps, no writes), but the meter is unlocked until the
power cycle, and unknown behaviour is possible (cf. 0x80). Never send 0x90 (write cal value) or 0x85/87/88/89/93/94/95/98.

## Still unverified
- Peak hold: what restarts a peak session.
- Fuse (28) and error (27) indications; HAZ warning (>60 V DC / 30 V AC).
- OL on other ranges / in manual range (e.g. mA/A over-range); range-code numbering in 4000-count manual range (saw 81/82 on the 40 V scale).
