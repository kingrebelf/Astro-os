#!/usr/bin/env python3
"""ASTRO//GLOBE: where this machine's live connections go, drawn on a globe.

Locations come from an offline database (data/dbip-*.mmdb), so the list of
addresses you talk to never leaves this machine.
IP geolocation by DB-IP (https://db-ip.com), CC BY 4.0.
"""
import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF, QRadialGradient
from PyQt6.QtWidgets import QApplication, QWidget

from common import (tc, AMBER, CYAN, GREEN, GREEN_DARK, GREEN_DIM, MAGENTA, ROOT, WHITE,
                    col, font, hud_panel, mix, scramble)
from globe import Scanner, graticule, load_config, load_land, paint_base, paint_links, vec

SIDE = 372


class Globe(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASTRO//GLOBE")
        self.resize(1080, 740)
        self.setMinimumSize(820, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.cfg = load_config()
        self.home = vec(*self.cfg["home"])
        self.land = load_land()
        self.grat = graticule()
        self.scan = Scanner()
        self.scan.start()
        self.version = -1
        self.yaw = self.cfg["home"][1] - 28          # view centre (degrees)
        self.tilt = 24.0
        self.zoom = 1.0
        self.drag = None
        self.last_touch = 0.0
        self.focus = None
        self.hover = -1
        self.rows = []
        self.t0 = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)

    # ------------------------------------------------------------ interaction
    def globe_rect(self):
        return QRect(0, 0, self.width() - SIDE, self.height())

    def tick(self):
        now = time.time()
        if self.focus is not None:
            ty, tt = self.focus
            dy = (ty - self.yaw + 180) % 360 - 180
            self.yaw += dy * 0.18
            self.tilt += (tt - self.tilt) * 0.18
            if abs(dy) < 0.4:
                self.focus = None
        elif now - self.last_touch > 6 and not self.drag:
            target = self.cfg["home"][1] - 28 + 30 * math.sin((now - self.t0) * 0.07)
            self.yaw += ((target - self.yaw + 180) % 360 - 180) * 0.02
            self.tilt += (24 - self.tilt) * 0.02
        if self.scan.version != self.version:
            self.version = self.scan.version
            self.update()
        else:
            self.update(self.globe_rect())

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if self.globe_rect().contains(pos):
            self.drag = (pos, self.yaw, self.tilt)
            self.focus = None
        else:
            for i, r in self.rows:
                if r.contains(pos):
                    g = self.scan.groups[i]
                    self.focus = (g["lon"] * 0.6 + self.cfg["home"][1] * 0.4, max(-50, min(60, g["lat"] * 0.6)))
        self.last_touch = time.time()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self.drag:
            p0, y0, t0 = self.drag
            self.yaw = y0 - (pos.x() - p0.x()) * 0.35 / self.zoom
            self.tilt = max(-85, min(85, t0 + (pos.y() - p0.y()) * 0.35 / self.zoom))
            self.last_touch = time.time()
            return
        hov = -1
        for i, r in self.rows:
            if r.contains(pos):
                hov = i
        if hov != self.hover:
            self.hover = hov
            self.update()

    def mouseReleaseEvent(self, _):
        self.drag = None

    def wheelEvent(self, e):
        self.zoom = max(0.7, min(3.0, self.zoom * (1.12 if e.angleDelta().y() > 0 else 0.89)))
        self.last_touch = time.time()

    def paintEvent(self, ev):
        p = QPainter(self)
        W, H = self.width(), self.height()
        p.fillRect(ev.rect(), tc(1, 6, 4))
        gw = W - SIDE
        t = time.time() - self.t0
        cx, cy = gw / 2, H / 2 + 14
        R = min(gw, H - 90) * 0.43 * self.zoom
        p.setClipRect(0, 0, gw, H)
        paint_base(p, cx, cy, R, self.yaw, self.tilt, self.land, self.grat)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for k, sp, span, c in ((1.09, 14, 70, CYAN), (1.09, 14, -110, GREEN_DIM), (1.15, -9, 40, GREEN)):
            pen = QPen(col(c, 190))
            pen.setWidthF(1.4)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            r = R * k
            p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int((t * sp % 360) * 16), span * 16)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        paint_links(p, cx, cy, R, self.yaw, self.tilt, t, self.home, self.cfg["label"],
                    self.scan.groups, self.hover)

        # header
        p.setFont(font(26, True, spacing=4))
        title = scramble("ASTRO//GLOBE", min(1.0, t / 1.0), 9)
        p.setPen(col(GREEN, 70))
        p.drawText(22, 42, title)
        p.setPen(WHITE)
        p.drawText(20, 40, title)
        p.setFont(font(12, False, spacing=2))
        p.setPen(col(GREEN, 210))
        p.drawText(22, 60, "LIVE CONNECTION TRACE // DRAG TO ROTATE // SCROLL TO ZOOM")
        p.setPen(col(GREEN, 110))
        p.drawText(22, H - 14, "IP GEOLOCATION BY DB-IP // LOOKUPS RUN OFFLINE ON THIS NODE")
        p.setClipping(False)

        if ev.region().intersects(QRect(gw, 0, SIDE, H)):
            self.paint_side(p, gw, W, H, t)
        p.end()

    def paint_side(self, p, x0, W, H, t):
        groups = self.scan.groups
        flagged = sum(1 for g in groups if g["flag"])
        p.fillRect(x0, 0, W - x0, H, tc(0, 9, 6))
        p.setPen(col(GREEN, 120))
        p.drawLine(x0, 0, x0, H)
        x, w = x0 + 16, SIDE - 32
        hud_panel(p, x, 22, w, 78, "LINK STATUS", 1.0, MAGENTA if flagged else GREEN)
        p.setFont(font(26, True, spacing=1))
        for i, (label, val, c) in enumerate((("SOCKETS", self.scan.total, GREEN),
                                             ("REMOTE", sum(g["n"] for g in groups), CYAN),
                                             ("FLAGGED", flagged, MAGENTA if flagged else GREEN_DIM))):
            cx_ = x + 14 + i * (w - 20) // 3
            p.setFont(font(28, True))
            p.setPen(c)
            p.drawText(cx_, 66, str(val))
            p.setFont(font(11, True, spacing=1.5))
            p.setPen(col(c, 190))
            p.drawText(cx_, 86, label)
        y = 128
        hud_panel(p, x, y, w, H - y - 20, "TRACE LOG", 1.0)
        self.rows = []
        yy = y + 18
        row_h = 58
        for i, g in enumerate(groups):
            if yy + row_h > H - 54:
                p.setPen(col(GREEN, 150))
                p.setFont(font(12, False, spacing=1))
                p.drawText(x + 14, yy + 14, f"+ {len(groups) - i} MORE DESTINATIONS")
                break
            r = QRect(x + 6, yy, w - 12, row_h - 6)
            self.rows.append((i, r))
            c = MAGENTA if g["flag"] == "INBOUND" else (AMBER if g["flag"] else GREEN)
            if i == self.hover:
                p.fillRect(r, col(c, 36))
            p.fillRect(r.left(), r.top(), 3, r.height(), c)
            p.setFont(font(14, True, spacing=0.5))
            p.setPen(WHITE if i == self.hover else c)
            fm = p.fontMetrics()
            head = f"{g['city'].upper()}, {g['cc']}"
            p.drawText(r.left() + 12, r.top() + 15, fm.elidedText(head, Qt.TextElideMode.ElideRight, w - 110))
            tag = g["flag"] or ("OUT" if not g["inbound"] else "IN")
            p.setFont(font(11, True, spacing=1))
            tw = p.fontMetrics().horizontalAdvance(tag) + 10
            p.fillRect(r.right() - tw - 2, r.top() + 3, tw, 15, col(c, 255 if g["flag"] else 40))
            p.setPen(tc(0, 0, 0) if g["flag"] else c)
            p.drawText(r.right() - tw + 3, r.top() + 14, tag)
            p.setFont(font(12, False))
            fm = p.fontMetrics()
            p.setPen(col(CYAN, 230))
            p.drawText(r.left() + 12, r.top() + 31, fm.elidedText(g["org"] or "UNKNOWN NETWORK",
                                                                 Qt.TextElideMode.ElideRight, w - 40))
            p.setPen(col(GREEN, 170))
            ports = ",".join(str(pt) for pt in sorted(g["ports"])[:3])
            info = f"{'/'.join(sorted(g['procs']))[:22]}  :{ports}  x{g['n']}"
            p.drawText(r.left() + 12, r.top() + 46, fm.elidedText(info, Qt.TextElideMode.ElideRight, w - 40))
            yy += row_h
        if not groups:
            p.setPen(col(GREEN, 160))
            p.setFont(font(13, False, spacing=1))
            p.drawText(x + 16, y + 40, "NO REMOTE LINKS ACTIVE")
        p.setPen(col(GREEN, 130))
        p.setFont(font(12, False, spacing=1))
        p.drawText(x + 14, H - 32, f"LOCAL NETWORK LINKS (NOT DRAWN): {self.scan.local}")


def main():
    app = QApplication(sys.argv)
    w = Globe()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
