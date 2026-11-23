#!/usr/bin/env python3
"""ASTRO//OS dock: launchers, open windows, telemetry, and the way back out."""
import math
import os
import subprocess
import sys
import time

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from common import (CLOCK_HM, THEME, tc, AMBER, CYAN, GREEN, GREEN_DIM, MAGENTA, ROOT, WHITE, X11,
                    Stats, col, font, scramble)

H = 46
CTL = os.path.join(ROOT, "astroctl")
# Standalone ASTRO//OS (the distro): there is no "normal desktop" underneath to go back to.
DISTRO = os.path.exists("/etc/astro-os/distro")
LIVE = os.path.isdir("/run/live/medium")


DOCK_FONT = THEME["dock_font"]      # default "Ubuntu": the heavy sans cut reads bolder than the mono face
DOCK_BOLD = bool(THEME["dock_bold"])
RADIUS = max(0, min(18, int(THEME["dock_radius"])))


def button(p, r, fill, edge):
    """One dock button: rounded, filled, with a 1px outline."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(edge, 1.2))
    p.setBrush(fill)
    p.drawRoundedRect(r.adjusted(0, 0, -1, -1), RADIUS, RADIUS)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)


def run(*cmd):
    subprocess.Popen(list(cmd), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


ACTIONS = {
    "term": lambda: run(CTL, "launch", "term"),
    "web": lambda: run(CTL, "launch", "web"),
    "files": lambda: run(CTL, "launch", "files"),
    "globe": lambda: run(CTL, "launch", "globe"),
    "tasks": lambda: run(CTL, "launch", "tasks"),
    "settings": lambda: run(CTL, "launch", "settings"),
    "reboot-ui": lambda: run(CTL, "restart"),
    "lock": lambda: run("xdg-screensaver", "lock"),
    "power": lambda: run("lxqt-leave"),
    "exit": lambda: run(CTL, "off"),
    "edit": lambda: run(CTL, "launch", "edit"),
    "opencode": lambda: run(CTL, "launch", "opencode"),
    "flow": lambda: run(CTL, "launch", "flow"),
    "network": lambda: run(CTL, "launch", "network"),
    "install": lambda: run(CTL, "launch", "install"),
    "look": lambda: run(CTL, "launch", "look"),
}

MENU = [
    ("term", ">_", "TERMINAL"),
    ("web", "@", "BROWSER"),
    ("files", "#", "FILES"),
    ("globe", "+", "NETWORK GLOBE"),
    ("tasks", "%", "TASK MANAGER"),
    ("look", "o", "APPEARANCE / THEMES"),
    ("settings", "*", "SYSTEM SETTINGS"),
    (None, "", ""),
    ("reboot-ui", "~", "REPLAY BOOT SEQUENCE"),
    ("lock", "!", "LOCK SCREEN"),
    ("power", "0", "POWER / LOG OUT"),
    (None, "", ""),
    ("exit", "<", "EXIT TO NORMAL DESKTOP"),
]
if DISTRO:
    MENU = [
        ("term", ">_", "TERMINAL"),
        ("web", "@", "BROWSER"),
        ("files", "#", "FILES"),
        ("edit", "=", "TEXT EDITOR"),
        ("opencode", "{}", "OPENCODE"),
        ("flow", "))", "WISPR FLOW"),
        (None, "", ""),
        ("globe", "+", "NETWORK GLOBE"),
        ("tasks", "%", "TASK MANAGER"),
        ("network", "~", "NETWORK / WI-FI"),
        ("look", "o", "APPEARANCE / THEMES"),
        ("settings", "*", "SYSTEM SETTINGS"),
        (None, "", ""),
    ] + ([("install", "v", "INSTALL TO DISK"), (None, "", "")] if LIVE else []) + [
        ("power", "0", "POWER / LOG OUT"),
    ]


class Menu(QWidget):
    ROW = 34

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setMouseTracking(True)
        self.hover = -1
        self.opened = 0.0
        rows = sum(self.ROW if k else 12 for k, _, _ in MENU)
        self.resize(300, rows + 58)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)

    def popup(self, pos):
        self.opened = time.time()
        self.move(pos.x(), pos.y() - self.height() - 6)
        self.show()
        self.timer.start(50)

    def hideEvent(self, _):
        self.timer.stop()

    def rows(self):
        y = 44
        for i, (k, ic, label) in enumerate(MENU):
            h = self.ROW if k else 12
            yield i, k, ic, label, QRect(8, y, self.width() - 16, h)
            y += h

    def mouseMoveEvent(self, e):
        self.hover = -1
        for i, k, _, _, r in self.rows():
            if k and r.contains(e.position().toPoint()):
                self.hover = i
        self.update()

    def mouseReleaseEvent(self, e):
        for i, k, _, _, r in self.rows():
            if k and r.contains(e.position().toPoint()):
                self.hide()
                ACTIONS[k]()
                return
        # a release outside the menu is just the tail of the click that opened it: stay open

    def paintEvent(self, _):
        t = time.time() - self.opened
        prog = min(1.0, t / 0.35)
        p = QPainter(self)
        w, h = self.width(), self.height()
        vis = int(h * min(1.0, t / 0.16))
        p.setClipRect(0, h - vis, w, vis)
        p.fillRect(0, 0, w, h, tc(0, 10, 6))
        p.setPen(col(GREEN, 200))
        p.drawRect(0, 0, w - 1, h - 1)
        p.fillRect(0, 0, w, 3, GREEN)
        p.setFont(font(15, True, spacing=3))
        p.setPen(WHITE)
        p.drawText(16, 28, scramble("ASTRO//OS :: COMMAND", prog, 3))
        p.setPen(col(GREEN, 90))
        p.drawLine(8, 38, w - 8, 38)
        for i, k, ic, label, r in self.rows():
            if not k:
                p.setPen(col(GREEN, 60))
                p.drawLine(r.left() + 8, r.center().y(), r.right() - 8, r.center().y())
                continue
            danger = k == "exit"
            c = MAGENTA if danger else GREEN
            if i == self.hover:
                p.fillRect(r, col(c, 50))
                p.fillRect(r.left(), r.top(), 3, r.height(), c)
            p.setFont(font(15, True, spacing=1))
            p.setPen(col(CYAN if not danger else MAGENTA, 255))
            p.drawText(r.left() + 14, r.top() + 22, ic)
            p.setPen(col(WHITE if i == self.hover else c, 255))
            p.setFont(font(14, i == self.hover, spacing=1.5))
            p.drawText(r.left() + 48, r.top() + 22, scramble(label, min(1.0, t / 0.3 - i * 0.05), i))


class Dock(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("astro-os-dock")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDock)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        g = QApplication.primaryScreen().geometry()
        self.W = g.width()
        self.setGeometry(g.x(), g.y() + g.height() - H, self.W, H)
        self.x11 = X11()
        self.stats = Stats()
        self.menu = Menu()
        self.items = []
        self.clients = []
        self.active = 0
        self.hover = None
        self.t0 = time.time()
        self.flash = {}
        self.n = 0
        self.sig = None
        self.frames = 0
        self.refresh()
        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh)
        self.poll.start(450)
        self.anim = QTimer(self)
        self.anim.timeout.connect(self.animate)
        self.trim = QTimer(self)
        self.trim.timeout.connect(self.trim_overlays)
        self.trim.start(2000)
        self.anim.start(50)

    def showEvent(self, _):
        wid = int(self.winId())
        self.x11.set_strut_bottom(wid, H, self.W)
        self.x11.all_desktops(wid)

    def refresh(self):
        self.n += 1
        try:
            self.clients = [c for c in self.x11.clients() if not c[1].startswith("astro-os-")]
            self.active = self.x11.active()
        except Exception:
            pass
        if self.n % 3 == 0:
            self.stats.update()
        self.layout_items()
        sig = (tuple(self.clients), self.active, time.strftime(CLOCK_HM),
               int(self.stats.total * 50), int(self.stats.mem_used * 10))
        if sig != self.sig:
            self.sig = sig
            self.update()

    def trim_overlays(self):
        """Keep OpenWhispr's floating windows from showing as black boxes (see overlay.py)."""
        try:
            import overlay
            overlay.run(self.x11)
        except Exception:
            pass

    def animate(self):
        """Only the moving bits repaint every frame; the rest waits for real changes."""
        self.frames += 1
        now = time.time()
        if now - self.t0 < 0.8 or any(now - v < 0.5 for v in self.flash.values()):
            self.update()
            return
        self.update(0, 0, self.W, 2)
        if self.frames % 2 == 0:
            self.update(12, 10, 30, H - 16)

    def layout_items(self):
        items = []
        x = 6
        items.append({"r": QRect(x, 6, 124, H - 10), "kind": "menu", "label": "ASTRO"})
        x += 132
        launchers = [("term", ">_ TERM"), ("web", "@ WEB"), ("files", "# FILES"), ("globe", "+ GLOBE")]
        if DISTRO:
            launchers += [("opencode", "{} CODE"), ("flow", ")) FLOW")]
            if LIVE:
                launchers.append(("install", "v INSTALL"))
        for key, label in launchers:
            w = 104 if key == "install" else 88
            items.append({"r": QRect(x, 6, w, H - 10), "kind": "launch", "key": key, "label": label})
            x += w + 6
        x += 10
        right = self.W - 6
        exit_w = 104 if DISTRO else 138
        items.append({"r": QRect(right - exit_w, 6, exit_w, H - 10), "kind": "exit",
                      "label": "0 POWER" if DISTRO else "< NORMAL OS"})
        self.info_x = right - exit_w - 250
        avail = self.info_x - x - 10
        if self.clients:
            tw = max(60, min(180, avail // len(self.clients) - 6))
            for wid, title, cls in self.clients:
                if x + tw > self.info_x - 4:
                    break
                items.append({"r": QRect(x, 6, tw, H - 10), "kind": "task", "wid": wid,
                              "label": title or cls, "cls": cls})
                x += tw + 6
        self.items = items

    def item_at(self, pos):
        for it in self.items:
            if it["r"].contains(pos):
                return it
        return None

    def mouseMoveEvent(self, e):
        it = self.item_at(e.position().toPoint())
        key = (it["kind"], it.get("wid", it.get("key"))) if it else None
        if key != self.hover:
            self.hover = key
            self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        it = self.item_at(e.position().toPoint())
        if not it:
            return
        self.flash[(it["kind"], it.get("wid", it.get("key")))] = time.time()
        k = it["kind"]
        if k == "menu":
            self.menu.popup(self.mapToGlobal(QPoint(6, 0)))
        elif k == "launch":
            ACTIONS[it["key"]]()
        elif k == "exit":
            ACTIONS["power" if DISTRO else "exit"]()
        elif k == "task":
            if e.button() == Qt.MouseButton.MiddleButton:
                self.x11.close(it["wid"])
            elif it["wid"] == self.active:
                self.x11.iconify(it["wid"])
            else:
                self.x11.activate(it["wid"])
            QTimer.singleShot(150, self.refresh)

    def paintEvent(self, _):
        t = time.time() - self.t0
        p = QPainter(self)
        W = self.W
        slide = min(1.0, t / 0.6)
        p.translate(0, int((1 - slide) ** 2 * H))
        p.fillRect(0, -H, W, 2 * H, tc(0, 9, 6))
        # top edge with travelling sweep
        p.fillRect(0, 0, W, 1, col(GREEN, 120))
        sx = (t * 260) % (W + 400) - 200
        g = QLinearGradient(sx - 160, 0, sx + 160, 0)
        g.setColorAt(0, col(GREEN, 0))
        g.setColorAt(0.5, col(WHITE, 255))
        g.setColorAt(1, col(GREEN, 0))
        p.fillRect(int(sx - 160), 0, 320, 2, g)

        now = time.time()
        for it in self.items:
            r = it["r"]
            key = (it["kind"], it.get("wid", it.get("key")))
            hov = key == self.hover
            fl = max(0.0, 1 - (now - self.flash.get(key, 0)) / 0.4)
            k = it["kind"]
            if k == "menu":
                pulse = 0.5 + 0.5 * math.sin(t * 2.2)
                button(p, r, col(GREEN, 40 + 40 * hov + 150 * fl), col(GREEN, 255))
                # little animated core icon
                cx, cy = r.left() + 20, r.center().y() + 1
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                pen = QPen(col(CYAN, 255))
                pen.setWidthF(1.6)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(cx - 10, cy - 10, 20, 20, int(t * 120 * 16) % 5760, 200 * 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col(WHITE, 150 + 105 * pulse))
                p.drawEllipse(cx - 4, cy - 4, 8, 8)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                p.setFont(font(17, DOCK_BOLD, DOCK_FONT, spacing=3))
                p.setPen(WHITE)
                p.drawText(r.left() + 40, r.top() + 24, it["label"])
            elif k == "launch":
                button(p, r, col(GREEN, 14 + 50 * hov + 160 * fl), col(GREEN, 110 + 145 * hov))
                p.setFont(font(14, DOCK_BOLD, DOCK_FONT, spacing=1))
                p.setPen(col(WHITE if hov else GREEN, 255))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, it["label"])
            elif k == "exit":
                button(p, r, col(MAGENTA, 22 + 70 * hov + 160 * fl), col(MAGENTA, 170 + 85 * hov))
                p.setFont(font(14, DOCK_BOLD, DOCK_FONT, spacing=1))
                p.setPen(col(WHITE if hov else MAGENTA, 255))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, it["label"])
            else:
                act = it["wid"] == self.active
                button(p, r, col(CYAN if act else GREEN, (46 if act else 10) + 40 * hov + 150 * fl), col(CYAN if act else GREEN_DIM, 255 if act else 150))
                if act:
                    p.fillRect(r.left() + RADIUS, r.bottom() - 2, r.width() - 2 * RADIUS, 3, CYAN)
                p.setFont(font(13, DOCK_BOLD, DOCK_FONT, spacing=0.5))
                fm = p.fontMetrics()
                p.setPen(col(WHITE if act or hov else GREEN, 255))
                p.drawText(r.left() + 8, r.top() + 23,
                           fm.elidedText(it["label"].upper(), Qt.TextElideMode.ElideRight, r.width() - 14))

        # telemetry + clock
        x = self.info_x
        st = self.stats
        mem = st.mem_used / st.mem_total
        p.setFont(font(12, True, spacing=1))
        for i, (label, v, c) in enumerate((("CPU", st.total, GREEN), ("MEM", mem, CYAN))):
            yy = 9 + i * 16
            p.setPen(col(c, 255))
            p.drawText(x, yy + 10, label)
            p.fillRect(x + 32, yy + 2, 80, 8, col(c, 40))
            p.fillRect(x + 32, yy + 2, int(80 * min(1, v)), 8, col(c, 255))
            p.drawText(x + 118, yy + 10, f"{v * 100:3.0f}%")
        p.setFont(font(22, True, spacing=2))
        p.setPen(WHITE)
        p.drawText(x + 162, 31, time.strftime(CLOCK_HM))
        p.end()


def main():
    app = QApplication(sys.argv)
    d = Dock()
    d.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
