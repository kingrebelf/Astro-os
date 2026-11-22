"""Shared toolkit for ASTRO//OS apps: themed app setup, title strip, and a custom-painted table."""
import os
import time

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication, QWidget

from common import CYAN, GREEN, GREEN_DIM, ROOT, WHITE, col, font, scramble

BG = QColor(1, 7, 5)
BG_ALT = QColor(3, 15, 10)


def make_app(argv):
    app = QApplication(argv)
    try:
        with open(os.path.join(ROOT, "theme", "astro.qss")) as f:
            app.setStyleSheet(f.read())
    except OSError:
        pass
    return app


def human_size(n):
    n = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class TitleStrip(QWidget):
    """Decoding title + subtitle, with a sweep line underneath."""

    def __init__(self, title, subtitle=""):
        super().__init__()
        self.title, self.subtitle = title, subtitle
        self.setFixedHeight(58)
        self.t0 = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.timer.start(60)

    def step(self):
        if time.time() - self.t0 > 1.3:
            self.timer.stop()
        self.update()

    def set_subtitle(self, s):
        if s != self.subtitle:
            self.subtitle = s
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), BG)
        t = time.time() - self.t0
        p.setFont(font(26, True, spacing=4))
        s = scramble(self.title, min(1.0, t / 1.0), 4)
        p.setPen(col(GREEN, 70))
        p.drawText(16, 32, s)
        p.setPen(WHITE)
        p.drawText(14, 30, s)
        p.setFont(font(12, False, spacing=2))
        p.setPen(col(GREEN, 210))
        p.drawText(16, 49, self.subtitle)
        p.fillRect(0, self.height() - 1, self.width(), 1, col(GREEN, 120))
        p.fillRect(0, self.height() - 2, 70, 2, GREEN)


class Col:
    def __init__(self, key, title, width=0, align="l", paint=None, text=None, sortable=True):
        self.key, self.title, self.width, self.align = key, title, width, align
        self.paint, self.text, self.sortable = paint, text, sortable


class Table(QAbstractScrollArea):
    """Rows are dicts with a unique 'id'. Selection survives refreshes."""
    activated = pyqtSignal(object)
    selectionChanged = pyqtSignal()
    contextRequested = pyqtSignal(QPoint)
    sortChanged = pyqtSignal()
    ROW, HEAD = 28, 28

    def __init__(self, cols, sort_key=None, sort_rev=False):
        super().__init__()
        self.cols = cols
        self.rows = []
        self.sel = set()
        self.cur = None
        self.anchor = None
        self.hover = -1
        self.sort_key, self.sort_rev = sort_key, sort_rev
        self.empty_text = "NOTHING HERE"
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(self.ROW)
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    # ---------------------------------------------------------------- data
    def set_rows(self, rows):
        self.rows = rows
        ids = {r["id"] for r in rows}
        self.sel &= ids
        if self.cur not in ids:
            self.cur = None
        self._range()
        self.viewport().update()

    def _range(self):
        vis = self.viewport().height() - self.HEAD
        self.verticalScrollBar().setPageStep(max(self.ROW, vis))
        self.verticalScrollBar().setRange(0, max(0, len(self.rows) * self.ROW - vis))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._range()

    def index_of(self, rid):
        for i, r in enumerate(self.rows):
            if r["id"] == rid:
                return i
        return -1

    def selected_rows(self):
        return [r for r in self.rows if r["id"] in self.sel]

    def select_only(self, rid):
        self.sel = {rid} if rid is not None else set()
        self.cur = self.anchor = rid
        i = self.index_of(rid)
        if i >= 0:
            self.ensure_visible(i)
        self.selectionChanged.emit()
        self.viewport().update()

    def ensure_visible(self, i):
        sb = self.verticalScrollBar()
        top = i * self.ROW
        vis = self.viewport().height() - self.HEAD
        if top < sb.value():
            sb.setValue(top)
        elif top + self.ROW > sb.value() + vis:
            sb.setValue(top + self.ROW - vis)

    # ---------------------------------------------------------------- layout
    def col_rects(self):
        w = self.viewport().width()
        fixed = sum(c.width for c in self.cols)
        x = 0
        out = []
        for c in self.cols:
            cw = c.width or max(120, w - fixed)
            out.append((x, cw))
            x += cw
        return out

    def row_at(self, y):
        if y < self.HEAD:
            return -1
        i = (y - self.HEAD + self.verticalScrollBar().value()) // self.ROW
        return i if 0 <= i < len(self.rows) else -1

    # ---------------------------------------------------------------- paint
    def paintEvent(self, _):
        p = QPainter(self.viewport())
        W, H = self.viewport().width(), self.viewport().height()
        dirty = _.rect()
        p.fillRect(dirty, BG)
        rects = self.col_rects()
        off = self.verticalScrollBar().value()
        first = max(off // self.ROW, (dirty.top() - self.HEAD + off) // self.ROW)
        last = min(len(self.rows), (dirty.bottom() - self.HEAD + off) // self.ROW + 1)
        p.setClipRect(dirty.intersected(QRect(0, self.HEAD, W, H - self.HEAD)))
        for i in range(max(0, first), last):
            row = self.rows[i]
            y = self.HEAD + i * self.ROW - off
            sel = row["id"] in self.sel
            if sel:
                p.fillRect(0, y, W, self.ROW, col(GREEN, 62))
                p.fillRect(0, y, 3, self.ROW, GREEN)
            elif i == self.hover:
                p.fillRect(0, y, W, self.ROW, col(GREEN, 28))
            elif i % 2:
                p.fillRect(0, y, W, self.ROW, BG_ALT)
            if row["id"] == self.cur and self.hasFocus():
                p.setPen(col(CYAN, 150))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(0, y, W - 1, self.ROW - 1)
            for c, (x, cw) in zip(self.cols, rects):
                r = QRect(x + 8, y, cw - 14, self.ROW)
                if c.paint:
                    p.save()
                    c.paint(p, r, row, sel)
                    p.restore()
                else:
                    s = c.text(row) if c.text else str(row.get(c.key, ""))
                    p.setFont(font(14))
                    p.setPen(WHITE if sel else col(GREEN, 225))
                    fl = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight if c.align == "r"
                                                          else Qt.AlignmentFlag.AlignLeft)
                    p.drawText(r, fl, p.fontMetrics().elidedText(s, Qt.TextElideMode.ElideRight, r.width()))
        if not self.rows:
            p.setFont(font(14, False, spacing=3))
            p.setPen(col(GREEN, 120))
            p.drawText(QRect(0, self.HEAD, W, 80), Qt.AlignmentFlag.AlignCenter, self.empty_text)
        p.setClipping(False)
        # header
        p.fillRect(0, 0, W, self.HEAD, QColor(2, 26, 16))
        p.fillRect(0, self.HEAD - 1, W, 1, GREEN)
        p.setFont(font(12, True, spacing=1.5))
        for c, (x, cw) in zip(self.cols, rects):
            title = c.title + ((" v" if self.sort_rev else " ^") if c.key == self.sort_key else "")
            p.setPen(WHITE if c.key == self.sort_key else CYAN)
            fl = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight if c.align == "r"
                                                  else Qt.AlignmentFlag.AlignLeft)
            p.drawText(QRect(x + 8, 0, cw - 14, self.HEAD), fl, title)
            p.setPen(col(GREEN_DIM, 150))
            p.drawLine(x + cw - 1, 5, x + cw - 1, self.HEAD - 6)

    # ---------------------------------------------------------------- input
    def _update_row(self, i):
        if i >= 0:
            y = self.HEAD + i * self.ROW - self.verticalScrollBar().value()
            self.viewport().update(0, y, self.viewport().width(), self.ROW)

    def mouseMoveEvent(self, e):
        h = self.row_at(int(e.position().y()))
        if h != self.hover:
            old, self.hover = self.hover, h
            self._update_row(old)          # repaint just the two rows involved
            self._update_row(h)

    def leaveEvent(self, _):
        old, self.hover = self.hover, -1
        self._update_row(old)

    def mousePressEvent(self, e):
        self.setFocus()
        x, y = int(e.position().x()), int(e.position().y())
        if y < self.HEAD:
            for c, (cx, cw) in zip(self.cols, self.col_rects()):
                if cx <= x < cx + cw and c.sortable:
                    if self.sort_key == c.key:
                        self.sort_rev = not self.sort_rev
                    else:
                        self.sort_key, self.sort_rev = c.key, False
                    self.sortChanged.emit()
            return
        i = self.row_at(y)
        mods = e.modifiers()
        if i < 0:
            if not mods:
                self.sel.clear()
                self.cur = None
        else:
            rid = self.rows[i]["id"]
            if e.button() == Qt.MouseButton.RightButton:
                if rid not in self.sel:
                    self.sel = {rid}
                self.cur = rid
            elif mods & Qt.KeyboardModifier.ControlModifier:
                self.sel ^= {rid}
                self.cur = self.anchor = rid
            elif mods & Qt.KeyboardModifier.ShiftModifier and self.anchor is not None:
                a = max(0, self.index_of(self.anchor))
                lo, hi = sorted((a, i))
                self.sel = {r["id"] for r in self.rows[lo:hi + 1]}
                self.cur = rid
            else:
                self.sel = {rid}
                self.cur = self.anchor = rid
        self.selectionChanged.emit()
        self.viewport().update()
        if e.button() == Qt.MouseButton.RightButton:
            self.contextRequested.emit(e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        i = self.row_at(int(e.position().y()))
        if i >= 0 and e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.rows[i]["id"])

    def keyPressEvent(self, e):
        k = e.key()
        n = len(self.rows)
        i = self.index_of(self.cur)
        page = max(1, (self.viewport().height() - self.HEAD) // self.ROW - 1)
        moves = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1, Qt.Key.Key_PageUp: -page, Qt.Key.Key_PageDown: page,
                 Qt.Key.Key_Home: -n, Qt.Key.Key_End: n}
        if k in moves and n:
            j = max(0, min(n - 1, (i if i >= 0 else (0 if moves[k] > 0 else n - 1)) + (moves[k] if i >= 0 else 0)))
            rid = self.rows[j]["id"]
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier and self.anchor is not None:
                a = max(0, self.index_of(self.anchor))
                lo, hi = sorted((a, j))
                self.sel = {r["id"] for r in self.rows[lo:hi + 1]}
            else:
                self.sel = {rid}
                self.anchor = rid
            self.cur = rid
            self.ensure_visible(j)
            self.selectionChanged.emit()
            self.viewport().update()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.cur is not None:
            self.activated.emit(self.cur)
        elif k == Qt.Key.Key_A and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.sel = {r["id"] for r in self.rows}
            self.selectionChanged.emit()
            self.viewport().update()
        else:
            e.ignore()
