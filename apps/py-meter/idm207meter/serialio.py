"""Blocking serial I/O for the IDM207 (pyserial). Used by the CLI and the GUI's worker thread.

Every request goes through protocol.request(), which only allows the read-only commands 00 and 0E.
"""
import time

from . import protocol as p

BAUD = 9600


def _saved_termios(port):
    """The port's terminal settings before we touch them (POSIX), with VMIN fixed up; None if unavailable."""
    try:
        import os
        import termios
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            attrs = termios.tcgetattr(fd)
        finally:
            os.close(fd)
    except (ImportError, OSError):
        return None
    # pyserial sets VMIN=0 and the kernel keeps it after close. With VMIN=0 an empty read returns 0 instead of
    # EAGAIN, which Chrome's Web Serial treats as "device lost" (NetworkError). Never hand that state on.
    if termios.VMIN != termios.VEOF:  # on some platforms the two share a slot; then leave it alone
        vmin = attrs[6][termios.VMIN]
        if (vmin[0] if isinstance(vmin, bytes) else vmin) == 0:
            attrs[6][termios.VMIN] = 1
    return attrs


def open_port(port):
    """Open the meter's port at 9600 8N1. Closing it puts the terminal settings back as we found them."""
    import serial

    class RestoringSerial(serial.Serial):
        _saved = None

        def open(self):
            self._saved = _saved_termios(self.port)
            super().open()

        def close(self):
            if self.is_open and self._saved is not None:
                try:
                    import termios
                    termios.tcsetattr(self.fd, termios.TCSANOW, self._saved)
                except (ImportError, OSError):
                    pass
            super().close()

    return RestoringSerial(port, BAUD, bytesize=8, parity="N", stopbits=1, timeout=0.1)


def poll_frame(ser, timeout=1.0):
    """Send the poll and return the raw 59-byte frame, or None."""
    ser.reset_input_buffer()
    ser.write(p.request(0x00))
    buf = b""
    end = time.time() + timeout
    while time.time() < end:
        buf += ser.read(p.FRAME_LEN)
        f = p.find_frame(buf)
        if f:
            return f
    return None


def poll(ser, timeout=1.0):
    f = poll_frame(ser, timeout)
    return p.decode(f) if f else None


def listen_frames(ser, stop=lambda: False):
    """Yield raw frames the meter sends by itself (SEND mode: one frame per F4 press)."""
    buf = b""
    while not stop():
        buf += ser.read(256)
        f = p.find_frame(buf)
        if f:
            buf = buf[buf.index(f) + p.FRAME_LEN:]
            yield f
        elif len(buf) > 4 * p.FRAME_LEN:
            buf = buf[-p.FRAME_LEN:]


def listen(ser):
    for f in listen_frames(ser):
        yield p.decode(f)


def read_cal(ser, idx, timeout=1.0):
    """Read one calibration entry; returns the 16-bit value or None."""
    ser.reset_input_buffer()
    ser.write(p.request(p.CAL_READ, bytes([idx])))
    buf = b""
    end = time.time() + timeout
    while time.time() < end:
        buf += ser.read(p.CAL_REPLY_LEN)
        v = p.parse_cal_reply(buf, idx)
        if v is not False:
            return v
    return None


def read_all_cal(ser, progress=None, stop=lambda: False):
    """Read all 256 entries; returns {index: value or None}. progress(done) is called after each."""
    cal = {}
    for idx in range(256):
        if stop():
            break
        cal[idx] = read_cal(ser, idx)
        if progress:
            progress(idx + 1)
    return cal
