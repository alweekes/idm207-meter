"""The port's terminal settings must survive a run of the app (see serialio._saved_termios)."""
import os

import pytest

termios = pytest.importorskip("termios")

from idm207meter import serialio  # noqa: E402


def _cc(attrs, i):
    v = attrs[6][i]
    return v[0] if isinstance(v, bytes) else v


@pytest.mark.parametrize("vmin", [0, 1])
def test_close_restores_terminal_settings(vmin):
    master, slave = os.openpty()
    try:
        path = os.ttyname(slave)
        attrs = termios.tcgetattr(slave)
        attrs[6][termios.VMIN], attrs[6][termios.VTIME] = vmin, 0
        termios.tcsetattr(slave, termios.TCSANOW, attrs)

        ser = serialio.open_port(path)
        fd = ser.fd
        assert _cc(termios.tcgetattr(fd), termios.VMIN) == 0  # pyserial's own setting while open
        ser.close()

        after = termios.tcgetattr(slave)
        assert _cc(after, termios.VMIN) == 1  # never left at 0, even if it was 0 before
        assert _cc(after, termios.VTIME) == 0
        assert after[2] & termios.CSIZE == attrs[2] & termios.CSIZE
    finally:
        os.close(master)
        os.close(slave)
