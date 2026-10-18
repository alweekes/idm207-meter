# APPA DMM 301 / 303 / 305: RS-232 Protocol Summary

Summary of the 9-page "WinDMM300 Protocol" addendum (APPA RS-232 protocol for the DMM 301, 303 and 305, supplied with WinDMM300 software for Windows 95/98/NT). Written in my own words from the pages viewed on Scribd. Hex values and code tables are reproduced as technical data.

**Not covered here:** page 1 is mostly the WinDMM300 software license agreement, which I skipped. I did not see serial port settings (baud rate, parity, etc.) anywhere in the pages I read. Check the meter manual for those.

## 1. Exchange overview

1. The PC sends a 5-byte request.
2. The PC waits for the meter's reply. The time-out must be **longer than 450 ms**.
3. The meter replies with one fixed-layout data frame.

### Request (PC to meter)

| Byte | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Value | 55H | 55H | 00H | 00H | AAH |

### Response frame (meter to PC)

| Field | Size (bytes) | Notes |
|---|---|---|
| Header | 4 | `55H 55H 00H 36H` |
| Model name | 8 | ASCII |
| Series (serial) number | 8 | ASCII |
| S/W version | 7 | ASCII |
| Switch code | 1 | Rotary switch position (section 3.1) |
| Blue code | 1 | Blue-button / sub-mode (section 3.2) |
| Key code | 1 | Last key pressed (section 3.3) |
| Range code | 1 | Active range (section 3.4) |
| A/D converter reading | 3 | Signed value (section 4) |
| Main display data | 6 | Value, point, unit, sub-code (section 4) |
| Left display data | 6 | Same layout |
| Right display data | 6 | Same layout |
| DC reading (in AC+DC mode) | 3 | Signed value (section 4) |
| AC reading (in AC+DC mode) | 3 | Signed value (section 4) |
| Checksum | 1 | See section 6 |

The listed fields add up to 59 bytes. The header's `36H` equals 54, which is the frame length minus the 4 header bytes and the checksum. That match is my inference, not something the document says.

## 2. ID fields

The three ID fields hold ASCII characters, one per byte. The document gives an example for each:

- Model name `41 30 42 31 43 32 44 33` reads "A0B1C2D3".
- Series number `45 34 46 35 47 36 48 37` reads "E4F5G6H7".
- S/W version `30 2E 30 30 2E 30 36` reads "0.00.06".

## 3. Status codes

### 3.1 Switch code (rotary position)

| 00H | 01H | 02H | 03H | 04H | 05H | 06H | 07H | 08H | 09H |
|---|---|---|---|---|---|---|---|---|---|
| OFF | V | mV | Ohm | Diode | mA | A | Cap | Hz | Temp |

### 3.2 Blue code (sub-mode for each switch position)

| Blue | V | mV | Ohm | Diode | mA | A | Cap | Hz | Temp |
|---|---|---|---|---|---|---|---|---|---|
| 00H | DC | DC | Ohm | Diode | DC | DC | Cap | Hz | deg C |
| 01H | AC | AC | Low Ohm | Beeper | AC | AC | n/a | Duty factor | deg F |
| 02H | AC+DC | AC+DC | n/a | n/a | AC+DC | AC+DC | n/a | n/a | n/a |

### 3.3 Key code

| 01H | 02H | 03H | 04H | 05H | 06H | 07H | 08H | 09H | 0AH |
|---|---|---|---|---|---|---|---|---|---|
| F1 | F2 | F3 | F4 | Light | Bar | Digit | Range | (key shown as "O" on the page) | Blue |

### 3.4 Range code

Codes `00H`–`07H` are auto-range. Setting bit 7 (`80H`–`87H`) means the same range is selected manually. Not every code exists for every function.

**Voltage**

| Code | DC V | AC V | AC+DC V | DC mV | AC mV | AC+DC mV |
|---|---|---|---|---|---|---|
| 00H / 80H | 4 V | 4 V | 4 V | 40 mV | 400 mV | 400 mV |
| 01H / 81H | 40 V | 40 V | 40 V | 400 mV | n/a | n/a |
| 02H / 82H | 400 V | 400 V | 400 V | n/a | n/a | n/a |
| 03H / 83H | 1000 V | 750 V | 750 V | n/a | n/a | n/a |

**Current** (only two ranges, `00H`/`80H` and `01H`/`81H`)

| Code | DC / AC / AC+DC mA | DC / AC / AC+DC A |
|---|---|---|
| 00H / 80H | 40 mA | 4 A |
| 01H / 81H | 400 mA | 10 A |

**Ohm, low ohm, capacitance, frequency, diode, temperature**

| Code | Ohm | Low Ohm | Cap | Hz |
|---|---|---|---|---|
| 00H / 80H | 400 Ω | 4 kΩ | 4 nF | 400 Hz |
| 01H / 81H | 4 kΩ | 40 kΩ | 40 nF | 4 kHz |
| 02H / 82H | 40 kΩ | 400 kΩ | 400 nF | 40 kHz |
| 03H / 83H | 400 kΩ | 4 MΩ | 4 µF | 400 kHz |
| 04H / 84H | 4 MΩ | 40 MΩ | 40 µF | 4 MHz |
| 05H / 85H | 40 MΩ | n/a | 400 µF | n/a |
| 06H / 86H | n/a | n/a | 4 mF | n/a |
| 07H / 87H | n/a | n/a | 10 mF | n/a |

Diode and Temp are only used with code `00H` / `80H`.

## 4. Numeric fields

**A/D reading** (3 bytes): low byte, high byte, pole (sign) byte.

**Main, left and right display** (6 bytes each): low byte, high byte, pole byte, point code, unit code, sub-code.

Every 3-byte reading is decoded the same way:

- value = low + (high × 256)
- If the pole byte is **greater than 7FH**, the value is negative (multiply by −1).

### Point (decimal position) code

| Code | 00H | 01H | 02H | 04H | 08H |
|---|---|---|---|---|---|
| Meaning | none | point 1 | point 2 | point 3 | point 4 |

The document's example is `4.0.0.0.0`. Point 1 is the digit position nearest the right (rightmost decimal place) and point 4 is the leftmost.

### Unit code

| Code | Unit | Code | Unit |
|---|---|---|---|
| 00H | none | 0EH | Delta |
| 01H | V | 0FH | Hz |
| 02H | mV | 10H | kHz |
| 03H | A | 11H | MHz |
| 04H | mA | 12H | deg C |
| 05H | dB | 13H | deg F |
| 06H | dBm | 14H | s |
| 07H | nF | 15H | ns |
| 08H | µF | 16H | µs |
| 09H | mF | 17H | ms |
| 0AH | Ohm | | |
| 0BH | kOhm | | |
| 0CH | MOhm | | |
| 0DH | % | | |

### Sub-function code (meaning of what a display is showing)

| Code | Meaning | Code | Meaning |
|---|---|---|---|
| 00H | none | 15H | High |
| 01H | Input reading | 16H | Low |
| 02H | Frequency | 17H | Delta |
| 03H | Period | 18H | % |
| 04H | Duty factor | 19H | Ref |
| 05H | Ambient temperature | 1AH | dBm |
| 06H | Time stamp | 1BH | dB |
| 07H | Load | 1CH | Send |
| 08H | Number (store/recall) | 1DH | Setup indication |
| 09H | Store | 1EH | Set beeper indication |
| 0AH | Recall | 1FH | Set auto power-off indication |
| 0BH | Reset | 20H | Set backlight indication |
| 0CH | Auto hold | 21H | Set hazard indication |
| 0DH | Max | 22H | Set line frequency indication |
| 0EH | Min | 23H | Set dBm load indication |
| 0FH | Max-Min | 24H | Set reset indication |
| 10H | Peak hold max | 25H | (blank in the document) |
| 11H | Peak hold min | 26H | Probe indication |
| 12H | Peak hold max-min | 27H | Error indication |
| 13H | Set high indication | 28H | Fuse indication |
| 14H | Set low indication | | |

## 5. Dividing a frame into parts

Treat the frame as a flat byte array and decode in the order given in section 1. Strings are fixed-width ASCII. Each numeric display field is 6 bytes. The A/D, DC and AC readings are 3-byte signed values with no point or unit.

## 6. Checksum

The last byte is the sum of all other bytes in the frame, and the document says to use the **last two digits** of that sum. In the document's worked example the byte sum is 732 and the checksum is given as **32**.

The example writes its bytes as a mix of hex and decimal, so I can't tell whether the "last two digits" means decimal digits or the low hex byte. **Verified on an IDM207 (2026-10-17): the checksum is the sum of bytes 0–57 mod 256.** Serial settings are 9600 baud, 8N1.
