"""Arc bar meter: an analogue-style bar along a semicircle, with a 1-2-5 auto scale (model.ArcScale)."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .. import model

TRACK = QColor(128, 128, 128, 50)
BAR = QColor("#1f6feb")
OVER = QColor("#d93025")


class ArcMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.scale = model.ArcScale()
        self.value, self.over, self.unit, self.stale = None, False, "", True
        self.setMinimumSize(220, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def reset_scale(self):
        self.scale.reset()

    def show_reading(self, r):
        m = r.main
        self.value = m.value if m else None
        self.over = bool(m and m.overload)
        self.unit = model.pretty_unit(m.unit) if m else ""
        self.scale.update(self.value)
        self.stale = False
        self.update()

    def set_stale(self, stale):
        if stale != self.stale:
            self.stale = stale
            self.update()

    def paintEvent(self, _):  # noqa: N802 (Qt override)
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg = self.palette().text().color()
        w, h = self.width(), self.height()
        r = min(w / 2 - 28, h - 56)
        if r < 20:
            return
        c = QPointF(w / 2, h - 30)
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        thick = max(8.0, r * 0.14)
        qp.setOpacity(0.4 if self.stale else 1.0)

        pen = QPen(TRACK, thick, cap=Qt.PenCapStyle.FlatCap)
        qp.setPen(pen)
        qp.drawArc(rect, 0, 180 * 16)

        # bar: from zero (left, or top centre when bipolar) to the value; OL fills to the end
        s = self.scale
        zero = 0.5 if s.bipolar else 0.0
        end = 1.0 if self.over else (s.fraction(self.value) if self.value is not None else zero)
        if end != zero:
            pen.setColor(OVER if self.over else BAR)
            qp.setPen(pen)
            qp.drawArc(rect, int((180 - 180 * zero) * 16), int(-180 * (end - zero) * 16))

        # ticks and labels
        qp.setPen(QPen(fg, 1.5))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, r / 14))
        qp.setFont(f)
        for k in range(51):
            a = math.pi * (1 - k / 50)
            major = k % 10 == 0
            r0, r1 = r + thick / 2 + 2, r + thick / 2 + (9 if major else 5)
            qp.drawLine(QPointF(c.x() + r0 * math.cos(a), c.y() - r0 * math.sin(a)),
                        QPointF(c.x() + r1 * math.cos(a), c.y() - r1 * math.sin(a)))
        for frac, val in s.ticks():
            a = math.pi * (1 - frac)
            rl = r - thick / 2 - 14
            p = QPointF(c.x() + rl * math.cos(a), c.y() - rl * math.sin(a))
            qp.drawText(QRectF(p.x() - 30, p.y() - 9, 60, 18), Qt.AlignmentFlag.AlignCenter, f"{val:g}")

        # value readout
        f.setPointSizeF(max(9.0, r / 6))
        f.setBold(True)
        qp.setFont(f)
        txt = "OL" if self.over else ("–" if self.value is None else f"{self.value:.6g}")
        qp.drawText(QRectF(c.x() - r * 0.6, c.y() - r * 0.5, r * 1.2, r * 0.4), Qt.AlignmentFlag.AlignCenter, txt)
        f.setPointSizeF(max(7.0, r / 12))
        f.setBold(False)
        qp.setFont(f)
        qp.drawText(QRectF(c.x() - r * 0.6, c.y() - r * 0.15, r * 1.2, r * 0.25), Qt.AlignmentFlag.AlignCenter, self.unit)
