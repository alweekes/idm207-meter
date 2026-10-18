# Debugging: web app gets no data until reboot (Chrome Web Serial vs pyserial)

A record of how the "web app shows no data, only a reboot fixes it" problem was tracked down, including the dead
ends. Fixed in v1.0.2. Environment: Linux (CachyOS, kernel 7.2), Chrome 155, meter on the onboard `/dev/ttyS0`
(16550A UART), user in the `uucp` group.

(Note: This issue is now fixed in Chrome, from Chrome 156 onwards: https://issues.chromium.org/issues/559872992)

## Symptom
- The desktop app (PyQt, pyserial) and the CLI reader always worked.
- The web app (Web Serial) worked right after a boot, then at some point stopped getting data: the port opened,
  polls were sent, nothing came back. Reloading, reconnecting and restarting Chrome did not help. Only a reboot did.
- The web app's status bar eventually said "port open but no bytes received".

## Root cause (short version)
pyserial opens a port with terminal settings `VMIN=0, VTIME=0` and does not put them back. Linux **keeps a port's
terminal settings after the last close**, so the next program inherits them. With `VMIN=0`, an empty non-blocking
`read()` returns `0` instead of failing with `EAGAIN`. Chrome's serial code treats a 0-byte read as "device lost"
and reports `NetworkError`, so every Web Serial read failed within ~10 ms. After a reboot `VMIN` is back at its
default of 1, which is why a reboot "fixed" it, until the Python app or CLI was used again.

Quick fix without rebooting: `stty -F /dev/ttyS0 min 1 time 0` (port must not be open).
Permanent fix: `serialio.open_port()` restores the settings found at open and never leaves `VMIN=0`; the GUI and
CLI also close the port on SIGTERM/SIGINT.

## Timeline

### 1. First hunches (all wrong)
- *Does the PyQt app fail to release the port?* No process held `/dev/ttyS0` except Chrome itself (`fuser -v`), and
  the kernel closes a process's file descriptors when it exits, however it exits.
- *Stale Web Serial session after a page reload* (the Vite dev server reloads on every edit). Added a `pagehide`
  handler to close the port, a one-time retry on open, and an on-screen "no bytes received" message. Reasonable
  hardening, but the failure also happened without any reload.
- *DTR/RTS handling* (the meter's RS232 interface is powered from those lines). Added a "Diagnose port" button
  that tried all four DTR/RTS combinations and a close/reopen. Result: 0 bytes in every state. The input lines
  (CTS/DSR/DCD/RI) read 0 in Python on a *working* port too, so they were not a discriminator.

### 2. Is it the meter, the cable or the port? No.
- The Python CLI reader got live readings from the same port in the same boot, with Chrome disconnected.
- Terminal settings after a Chrome session and after a Python session looked identical in the fields I compared
  (9600 8N1, no flow control, `clocal`, `cread`). The one visible difference, `parmrk` in Chrome's input flags,
  turned out not to matter. (I did not compare `VMIN`/`VTIME` at this stage; that was the miss.)

### 3. The kernel sees the data
`/proc/tty/driver/serial_8250` (needs root; on this kernel the file is `serial_8250`, not `serial`) gave cumulative
counters. Sampled every 4 s while Chrome was connected and "silent":

```
0: uart:16550A port:000003F8 irq:4 tx:96541 rx:1123673 RTS|DTR
0: uart:16550A port:000003F8 irq:4 tx:96556 rx:1123909 RTS|DTR
0: uart:16550A port:000003F8 irq:4 tx:96576 rx:1124145 RTS|DTR
```
`rx` rose by exactly 236 bytes per window, which is 4 whole 59-byte frames, and `tx` by 15-20 bytes (3-4 polls). No
framing, parity or overrun errors were reported. So the meter answered and the kernel received every frame; the
loss was between the kernel and the web page.

### 4. Chrome fails with no app code involved
A snippet pasted into the DevTools console (open the granted port, send the standard `00` poll, read for 2 s):
`0 bytes, NetworkError`. Six variants (idle read with nothing sent, no `setSignals`, hardware flow control, buffer
sizes 64 and 4096) all failed **about 10 ms after opening**. So the app, the poll and the signals were all
irrelevant: Chrome's first read on this port failed instantly.

### 5. The system-call trace
`sudo strace -f -y -p <chrome browser pid> -e trace=read,write,ioctl,openat,close | grep ttyS0` (the `-y` flag prints
the path next to each file descriptor; without it, descriptor numbers are reused for unrelated files and the trace is
noise). Every open looked like this:

```
openat("/dev/ttyS0", O_RDWR|O_NOCTTY|O_NONBLOCK) = 147
ioctl(147</dev/ttyS0>, TIOCEXCL) = 0
ioctl(147</dev/ttyS0>, TCSETS2, {c_iflag=IGNPAR|PARMRK, ..., c_cflag=B9600|CS8|CREAD|HUPCL|CLOCAL}) = 0
ioctl(147</dev/ttyS0>, TIOCMBIS, [TIOCM_DTR]) = 0
read(147</dev/ttyS0>, "", 255) = 0          <-- 0 bytes, not EAGAIN
write(147</dev/ttyS0>, "UU\0\0\252", 5) = 5
```
A read of `0` straight after open, before any data could arrive, is the smoking gun. As far as I understand the Linux
tty layer (`n_tty_read`; not verified against the kernel source here), a non-blocking read of an empty buffer
returns `-EAGAIN` only when the line has a read timeout; with `VMIN=0, VTIME=0` it returns 0 first. The trace shows
Chrome reading the existing termios (`TCGETS2`) and writing it back (`TCSETS2`); it does not show the control
characters, but the behaviour is consistent with Chrome inheriting `VMIN`/`VTIME` from the previous program.
The step 6 experiment is what actually proves the cause.

### 6. Confirmation
`stty -F /dev/ttyS0 -a` showed `min = 0; time = 0` in the stuck state. `stty -F /dev/ttyS0 min 1 time 0` made the web
app work immediately, with no reboot. A deliberate round trip proved the cause: set `min 0`, open and close the port
with the old pyserial code, and it stays 0; with the fixed code it comes back as 1.

### 6b. It is not specific to the onboard UART
To check the problem was not a quirk of the 8250 driver, the same Web Serial read test was run on a USB serial
adapter: an Inside Out Networks Edgeport/2 (USB 0x1608:0x0205, kernel driver `edgeport_ti_2`, `/dev/ttyUSB0` and
`/dev/ttyUSB1`) with **nothing connected to either port**. The test only listens for 2 s, sends nothing, and was
run with the port closed and the terminal settings set beforehand with `stty`:

| Terminal setting | Web Serial read, both USB ports |
|---|---|
| `min 0 time 0` | `NetworkError` after ~150 ms, 0 bytes |
| `min 1 time 0` | waits the full 2 s, no error (`error=none`, ~2.1 s) |

(The onboard port fails in ~10 ms; USB is slower because of USB latency.) So the failure depends on the terminal
setting, not on the UART, the driver or the attached device, and it reproduces with nothing attached.

### 7. The fix
- `apps/py-meter/idm207meter/serialio.py`: `open_port()` returns a `serial.Serial` subclass that saves the termios
  settings before opening and restores them on close, forcing `VMIN` to 1 if it was 0 (guarded for platforms where
  `VMIN` and `VEOF` share a slot). First version had a bug caught by the new test: Python returns some control
  characters as `bytes`, and `b'\x00'` is truthy, so the check never fired.
- GUI (`__main__.py`) and CLI (`idm207.py`) close the port on SIGTERM/SIGINT; the CLI previously never closed it.
- `tests/test_serialio.py`: opens a pty with `VMIN` 0 and 1, runs `open_port()` and `close()`, and asserts the settings
  come back with `VMIN=1`.
- Web app: removed the temporary debug logging and the Diagnose button; the "no bytes received" message now names
  this cause and the `stty` fix.

## Lessons
- Compare *every* termios field (`stty -a`, including `min`/`time`), not just the ones that look relevant.
- Raw browser console snippets are a good way to separate "my app" from "the browser".
- Kernel serial counters (`/proc/tty/driver/serial_8250`) tell you whether bytes arrived at all.
- `strace -y` is essential in a multi-process program like Chrome.
- If you write a tool that uses a serial port on Linux, restore the terminal settings on close. Settings outlive the
  process.

## Not fixed
- A `kill -9` of the Python app cannot restore the settings. `reverse-engineering/scripts/poll.py` opens the port with
  raw pyserial and can leave `VMIN=0`; use `stty -F <port> min 1 time 0` afterwards.
- Chrome could arguably handle a 0-byte read on a tty better. Reproduced on two kernel drivers (8250 and
  `edgeport_ti_2`) with no device attached; worth reporting upstream (Chromium issue tracker, Web Serial / `Blink>Serial`).
