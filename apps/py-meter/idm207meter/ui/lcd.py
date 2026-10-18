"""Virtual LCD: annunciator row, left/right secondary displays, large 7-segment main reading."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .. import model

BG = QColor("#b9c4a8")
ON = QColor("#1b2216")
OFF = QColor(27, 34, 22, 28)

# segments a b c d e f g
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
    "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", "O": "abcdef", "L": "fed", " ": "",
}


def draw_digit(qp, x, y, w, h, segs, color):
    """Draw one 7-segment digit with its box at (x, y, w, h)."""
    t = w * 0.16           # segment thickness
    hh = h / 2
    def hseg(cy):
        return QPolygonF([QPointF(x + t * 0.6, cy), QPointF(x + t * 1.1, cy - t / 2), QPointF(x + w - t * 1.1, cy - t / 2),
                          QPointF(x + w - t * 0.6, cy), QPointF(x + w - t * 1.1, cy + t / 2), QPointF(x + t * 1.1, cy + t / 2)])
    def vseg(cx, y0, y1):
        return QPolygonF([QPointF(cx, y0 + t * 0.6), QPointF(cx + t / 2, y0 + t * 1.1), QPointF(cx + t / 2, y1 - t * 1.1),
                          QPointF(cx, y1 - t * 0.6), QPointF(cx - t / 2, y1 - t * 1.1), QPointF(cx - t / 2, y0 + t * 1.1)])
    shapes = {"a": hseg(y + t / 2), "g": hseg(y + hh), "d": hseg(y + h - t / 2),
              "f": vseg(x + t / 2, y, y + hh), "b": vseg(x + w - t / 2, y, y + hh),
              "e": vseg(x + t / 2, y + hh, y + h), "c": vseg(x + w - t / 2, y + hh, y + h)}
    for name, poly in shapes.items():
        qp.setBrush(color if name in segs else OFF)
        qp.drawPolygon(poly)


class LcdWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.reading = None
        self.lit = set()
        self.key = ""
        self.stale = True
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def show_reading(self, r, lit, key=""):
        self.reading, self.lit, self.key, self.stale = r, lit, key, False
        self.update()

    def set_stale(self, stale=True):
        self.stale = stale
        self.update()

    def paintEvent(self, _):  # noqa: N802 (Qt override)
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(BG)
        qp.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)
        r = self.reading
        ink = QColor(ON)
        if self.stale:
            ink.setAlpha(90)

        # annunciator row
        f = QFont("Sans", max(8, int(h * 0.05)), QFont.Weight.Bold)
        qp.setFont(f)
        x = 12
        for name in model.ANNUNCIATORS:
            qp.setPen(ink if name in self.lit and not self.stale else OFF)
            br = qp.boundingRect(QRectF(x, 6, 200, h * 0.1), Qt.AlignmentFlag.AlignLeft, name)
            qp.drawText(br, Qt.AlignmentFlag.AlignLeft, name)
            x = br.right() + 10
        if self.key:
            qp.setPen(ink)
            qp.drawText(QRectF(0, 6, w - 12, h * 0.1), Qt.AlignmentFlag.AlignRight, f"key {self.key}")

        # secondary displays
        f2 = QFont("Monospace", max(9, int(h * 0.07)), QFont.Weight.Bold)
        qp.setFont(f2)
        qp.setPen(ink)
        for d, align, x0 in ((r and r.left, Qt.AlignmentFlag.AlignLeft, 14), (r and r.right, Qt.AlignmentFlag.AlignRight, 0)):
            if d:
                sub = "" if d.label_only else f"  {d.sub}"
                qp.drawText(QRectF(x0, h * 0.16, w - 28, h * 0.14), align | Qt.AlignmentFlag.AlignVCenter,
                            model.display_text(d) + sub)

        # main reading
        top, dh = h * 0.34, h * 0.42
        if self.stale and r is None:
            qp.setFont(QFont("Sans", int(h * 0.12), QFont.Weight.Bold))
            qp.drawText(QRectF(0, top, w, dh), Qt.AlignmentFlag.AlignCenter, "no reading")
            return
        m = r.main if r else None
        if m is None or m.label_only:
            qp.setFont(QFont("Sans", int(h * 0.14), QFont.Weight.Bold))
            qp.drawText(QRectF(0, top, w, dh), Qt.AlignmentFlag.AlignCenter, f"[{m.sub}]" if m else "")
        else:
            if m.blank:
                text = "----"
            elif m.overload:
                text = " OL"
            else:
                text = f"{m.value:.{m.decimals}f}"
            unit = model.pretty_unit(m.unit)
            dw = dh * 0.52
            digits = [c for c in text if c != "."]
            total = len(digits) * dw * 1.25
            qp.setFont(QFont("Sans", int(h * 0.13), QFont.Weight.Bold))
            uw = qp.fontMetrics().horizontalAdvance(unit) + 16
            x = max(10.0, (w - total - uw) / 2)
            qp.setPen(Qt.PenStyle.NoPen)
            for i, c in enumerate(text):
                if c == ".":
                    qp.setBrush(ink)
                    qp.drawEllipse(QPointF(x - dw * 0.12, top + dh - dw * 0.08), dw * 0.09, dw * 0.09)
                    continue
                if c in SEGMENTS:
                    draw_digit(qp, x, top, dw, dh, SEGMENTS[c], ink)
                else:
                    qp.setPen(ink)
                    qp.drawText(QRectF(x, top, dw, dh), Qt.AlignmentFlag.AlignCenter, c)
                    qp.setPen(Qt.PenStyle.NoPen)
                x += dw * 1.25
            qp.setPen(ink)
            qp.drawText(QRectF(x + 6, top, uw, dh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, unit)

        # function name and main sub-label
        qp.setPen(ink)
        qp.setFont(QFont("Sans", max(9, int(h * 0.07)), QFont.Weight.Bold))
        bottom = QRectF(14, h * 0.8, w - 28, h * 0.16)
        if r:
            qp.drawText(bottom, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, r.function)
            if m and m.sub not in ("input", "") and not m.label_only:
                qp.drawText(bottom, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, m.sub)
        if self.stale:
            qp.drawText(bottom, Qt.AlignmentFlag.AlignCenter, "no reply")
