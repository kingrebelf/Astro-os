#!/usr/bin/env python3
"""ASTRO//OS live desktop: connection globe on top, system panels below, a small voice-reactive core.

Drawing is deliberately frugal: the onboard video chip is slow, so every panel is cached and
only the regions that actually change are repainted.
"""
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from common import (CLOCK_HMS, tc, AMBER, CYAN, GREEN, GREEN_DARK, MAGENTA, ROOT, WHITE, GlyphAtlas, Stats, col, font,
                    hud_panel, human_rate, local_ip, mix, scramble)
from globe import Scanner, flag_color, graticule, load_config, load_land, paint_base, paint_links, vec
from voice import Mic, Watcher

DOCK_H = 46
BG = tc(1, 6, 4)
PAD = (-3, -11, 3, 3)          # room around a panel for its title tab and corner brackets

class ProcFeed(threading.Thread):
    """Top processes by CPU, sampled in a separate process (procfeed.py)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.top = []
        self.count = 0

    def run(self):
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "procfeed.py")],
                                stdout=subprocess.PIPE, text=True)
        for line in proc.stdout:
            try:
                d = json.loads(line)
                self.top = [tuple(r) for r in d["top"]]
                self.count = d["count"]
            except ValueError:
                pass


def gpu_cards():
    """Short names of the NVIDIA cards on the bus, whether or not a driver is loaded."""
    try:
        out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    names = []
    for line in out.splitlines():
        if "NVIDIA" in line and ("VGA" in line or "3D controller" in line):
            m = re.search(r"\[([^\]]+)\]", line.split("NVIDIA", 1)[1])
            names.append((m.group(1) if m else "NVIDIA").replace("GeForce ", "").upper()[:14])
    return names[:4]


class GpuFeed(threading.Thread):
    """Live NVIDIA GPU readings (utilisation, memory, temperature) when nvidia-smi exists."""

    def __init__(self):
        super().__init__(daemon=True)
        self.gpus = []
        self.version = 0

    def run(self):
        import shutil
        fake = os.environ.get("ASTRO_FAKE_GPU")
        if not fake and not shutil.which("nvidia-smi"):
            return
        while True:
            rows = []
            try:
                if fake:
                    rows = [{"name": "Tesla V100-PCIE-32GB", "util": random.randint(0, 100),
                             "used": random.uniform(1, 32), "total": 32.0, "temp": random.randint(40, 80)}
                            for _ in range(4)]
                else:
                    out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,"
                                          "memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
                                         capture_output=True, text=True, timeout=8).stdout
                    for line in out.strip().splitlines():
                        f = [x.strip() for x in line.split(",")]
                        rows.append({"name": f[0], "util": float(f[1]), "used": float(f[2]) / 1024,
                                     "total": float(f[3]) / 1024, "temp": float(f[4])})
            except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                pass
            self.gpus = rows
            self.version += 1
            time.sleep(2)


class Desktop(QWidget):
    def __init__(self, boot=True):
        super().__init__()
        self.setWindowTitle("astro-os-desktop")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDesktop)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        g = QApplication.primaryScreen().geometry()
        if os.environ.get("ASTRO_SIZE"):                 # layout testing: ASTRO_SIZE=1400x1050
            sw, sh = map(int, os.environ["ASTRO_SIZE"].split("x"))
            g = QRect(0, 0, sw, sh)
        self.setGeometry(g)
        self.W, self.H = W, H = g.width(), g.height()
        self.t0 = time.time() - (0 if boot else 100)
        self.last = time.time()
        self.n = 0

        # --- quiet background: faint dot grid, drawn once
        self.bg = QPixmap(W, H)
        self.bg.fill(BG)
        p = QPainter(self.bg)
        p.setPen(col(GREEN, 26))
        for y in range(16, H, 32):
            for x in range(16, W, 32):
                p.drawPoint(x, y)
        p.end()

        # --- data sources
        self.stats = Stats()
        self.ip = local_ip()
        self.host = os.uname().nodename
        self.net_hist = [(0.0, 0.0)] * 90
        self.cores_smooth = [0.0] * max(1, len(self.stats.cores))
        self.feed = ProcFeed()
        self.feed.start()
        import shutil
        has_gpu = bool(shutil.which("nvidia-smi"))
        self.gpu_cards = gpu_cards()
        self.boot_lines = [
            f"[  OK  ] cold start :: {self.host.lower()} kernel handshake",
            f"[  OK  ] {os.cpu_count()} logic threads online",
            f"[  OK  ] link {self.stats.iface} up :: tracing connections",
            "[  OK  ] gpu array online" if has_gpu else "[ WARN ] gpu bay :: no nvidia driver loaded",
            "[  OK  ] voice cortex listening",
            "[ DONE ] welcome back, operator",
        ]
        self.gpufeed = GpuFeed()
        self.gpufeed.start()
        self.gpu_seen = 0
        self.mic = Mic()
        self.mic.start()
        self.watch = Watcher()
        self.watch.start()
        self.voice = 0.0
        self.dictating = False
        self.voice_state = ""
        self.stat_timer = 0.0

        # --- connection globe (top of the screen)
        self.cfg = load_config()
        self.home = vec(*self.cfg["home"])
        self.land = load_land()
        self.grat = graticule()
        self.scan = Scanner()
        self.scan.start()
        self.scan_seen = -1
        self.yaw0 = self.cfg["home"][1] - 26
        self.yaw, self.tilt = self.yaw0, 22.0
        self.gdrag = None
        self.last_touch = 0.0
        self.link_next = 0.0
        self.rows = []
        self.hover = -1

        # --- core sphere (bottom-left, small: it repaints every frame)
        self.small = GlyphAtlas(10)
        self.small_c = GlyphAtlas(10, hue=CYAN)
        self.small_m = GlyphAtlas(10, hue=MAGENTA)
        self.sphere = []
        n = 240
        for i in range(n):
            y = 1 - 2 * (i + 0.5) / n
            r = math.sqrt(1 - y * y)
            a = i * 2.399963
            self.sphere.append((math.cos(a) * r, y, math.sin(a) * r, random.randrange(999),
                                random.random() * 6.28))
        self.spin = 0.0

        # --- layout: (key, panel rect, refresh seconds, painter, dirty rect or None)
        # everything is derived from the screen size, so the same code fits any monitor
        gap, ph = 12, 190
        pw = (W - 56 - 2 * gap) // 3
        bx = (28, 28 + pw + gap, 28 + 2 * (pw + gap))
        y2 = H - DOCK_H - 10 - ph
        y1 = y2 - ph - 14
        trace_w = 432
        gx0, gx1, gy0, gy1 = 258, W - 28 - trace_w - 16, 8, y1 - 18
        self.globe_rect = QRect(gx0, gy0, gx1 - gx0, gy1 - gy0)
        self.gcx, self.gcy = (gx0 + gx1) / 2, (gy0 + gy1) / 2 + 2
        self.gR = min(gx1 - gx0, gy1 - gy0) / 2 / 1.275
        self.link_box = QRect(self.globe_rect)
        self.core_panel = QRect(bx[0], y2, 190, ph)
        self.ccx, self.ccy, self.cR = bx[0] + 95.0, y2 + 100.0, 62.0
        cr = int(self.cR * 1.18 + 9)
        self.core_rect = QRect(int(self.ccx) - cr, int(self.ccy) - cr, cr * 2, cr * 2)
        voice_r = QRect(bx[1], y2, pw, ph)
        self.trace_rect = QRect(W - 28 - trace_w, 22, trace_w, y1 - 48)
        self.panels = [
            ("clock", QRect(28, 22, 222, 104), 1.0, self.paint_clock, None),
            ("status", QRect(28, 148, 222, 150), 1e9, self.paint_status, None),
            ("hint", QRect(28, 320, 222, 110), 1e9, self.paint_hint, None),
            ("globe", self.globe_rect, 1e9, self.paint_globe_base, None),
            ("trace", self.trace_rect, 1e9, self.paint_trace, None),
            ("cpu", QRect(bx[0], y1, pw, ph), 1.0, self.paint_cpu, None),
            ("net", QRect(bx[1], y1, pw, ph), 1.0, self.paint_net, None),
            ("proc", QRect(bx[2], y1, pw, ph * 2 + 14), 2.5, self.paint_proc, None),
            ("corepanel", self.core_panel, 1e9, self.paint_core_panel, None),
            ("gpu", QRect(bx[0] + 202, y2, pw - 202, ph), 1e9, self.paint_gpu, None),
            ("voice", voice_r, 0.066, self.paint_voice,
             QRect(voice_r.x() + 8, voice_r.y() + 38, pw - 16, ph - 44)),
        ]
        if 320 + 110 > y1 - 12:        # short screen: the legend would run into the panel row below it
            self.panels = [pn for pn in self.panels if pn[0] != "hint"]
        self.cache, self.pool, self.fresh = {}, {}, {}
        self.ripples = []
        self.covered = False
        self.x11 = None
        self.own = set()
        self.setMouseTracking(True)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)

    # ------------------------------------------------------------ housekeeping
    def dragging(self):
        """True while a mouse button is held over some other window (a drag in progress)."""
        try:
            if self.x11 is None:
                from common import X11
                self.x11 = X11()
                wid = int(self.winId())
                self.own = {wid, self.x11.parent(wid)}
            child, mask = self.x11.pointer()
            return bool(mask & 0x100) and child not in self.own and child != 0
        except Exception:
            return False

    def is_covered(self):
        try:
            if self.x11 is None:
                self.dragging()
            x = self.x11
            win = x.active()
            if not win:
                return False
            state = x.get_prop(win, "_NET_WM_STATE") or []
            return (x.atom("_NET_WM_STATE_FULLSCREEN") in state
                    or (x.atom("_NET_WM_STATE_MAXIMIZED_VERT") in state
                        and x.atom("_NET_WM_STATE_MAXIMIZED_HORZ") in state))
        except Exception:
            return False

    def invalidate(self, *keys):
        for key, rect, _, _, _ in self.panels:
            if key in keys:
                self.cache.pop(key, None)
                self.update(rect.adjusted(*PAD))

    # ------------------------------------------------------------ simulation
    def tick(self):
        now = time.time()
        dt = min(now - self.last, 0.15)
        self.last = now
        self.n += 1
        t = now - self.t0
        booting = t < 3.4
        if self.n % 20 == 0:
            self.covered = self.is_covered()
        if not booting and (self.covered or
                            (not os.environ.get("ASTRO_NO_DRAG_PAUSE") and self.dragging())):
            return

        self.stat_timer += dt
        if self.stat_timer >= 1.0:
            self.stat_timer = 0
            self.stats.update()
            self.net_hist = self.net_hist[1:] + [(self.stats.rx, self.stats.tx)]
            if len(self.cores_smooth) != len(self.stats.cores):
                self.cores_smooth = [0.0] * len(self.stats.cores)
            for i, v in enumerate(self.stats.cores):
                self.cores_smooth[i] += (v - self.cores_smooth[i]) * 0.6

        target = self.mic.level
        self.voice += (target - self.voice) * (0.6 if target > self.voice else 0.14)
        self.dictating = self.watch.recording
        vs = "DICTATING" if self.dictating else ("SIGNAL" if self.voice > 0.08 else "QUIET")
        if vs != self.voice_state:
            self.voice_state = vs
            self.invalidate("voice", "corepanel")

        if self.gpufeed.version != self.gpu_seen:
            self.gpu_seen = self.gpufeed.version
            self.invalidate("gpu")

        if self.scan.version != self.scan_seen:
            self.scan_seen = self.scan.version
            self.invalidate("trace", "status")
            self.link_box = QRect(self.globe_rect)
            self.update(self.globe_rect)

        # the globe eases back to its home view a while after you let go of it
        if self.gdrag is None and now - self.last_touch > 8 and (abs(self.yaw - self.yaw0) > 0.3
                                                                 or abs(self.tilt - 22) > 0.3):
            self.yaw += (self.yaw0 - self.yaw) * 0.12
            self.tilt += (22 - self.tilt) * 0.12
            self.invalidate("globe")

        for r in self.ripples:
            r[2] += dt
        if self.ripples:
            for x, y, age in self.ripples:
                rr = int(age * 200) + 8
                self.update(int(x) - rr, int(y) - rr, rr * 2, rr * 2)
            self.ripples = [r for r in self.ripples if r[2] < 0.9]

        if booting:
            self.cache.clear()
            self.update()
            return
        for key, rect, interval, _, dirty in self.panels:
            if now - self.fresh.get(key, 0) >= interval:
                self.fresh[key] = now
                self.cache.pop(key, None)
                self.update(dirty or rect.adjusted(*PAD))
        self.update(self.core_rect)
        # link animation: repaint only where arcs are, and slow down if that area is large
        if now >= self.link_next and not self.link_box.isEmpty():
            area = self.link_box.width() * self.link_box.height()
            self.link_next = now + max(0.05, min(0.25, area / 1.4e6))
            self.update(self.link_box)

    # ------------------------------------------------------------ input
    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if e.button() != Qt.MouseButton.LeftButton:
            return
        for i, r in self.rows:
            if r.contains(pos):
                g = self.scan.groups[i] if i < len(self.scan.groups) else None
                if g:
                    self.yaw = g["lon"] * 0.6 + self.cfg["home"][1] * 0.4
                    self.tilt = max(-50, min(60, g["lat"] * 0.6))
                    self.last_touch = time.time()
                    self.invalidate("globe")
                return
        if math.hypot(pos.x() - self.gcx, pos.y() - self.gcy) <= self.gR + 10:
            self.gdrag = (pos, self.yaw, self.tilt)
            return
        self.ripples.append([pos.x(), pos.y(), 0.0])

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self.gdrag:
            p0, y0, t0 = self.gdrag
            self.yaw = y0 - (pos.x() - p0.x()) * 0.35
            self.tilt = max(-85, min(85, t0 + (pos.y() - p0.y()) * 0.35))
            self.last_touch = time.time()
            self.invalidate("globe")
            return
        hov = -1
        for i, r in self.rows:
            if r.contains(pos):
                hov = i
        if hov != self.hover:
            self.hover = hov
            self.invalidate("trace")
            self.update(self.globe_rect)

    def mouseReleaseEvent(self, _):
        self.gdrag = None

    def mouseDoubleClickEvent(self, e):
        pos = e.position().toPoint()
        if math.hypot(pos.x() - self.gcx, pos.y() - self.gcy) <= self.gR:
            subprocess.Popen([os.path.join(ROOT, "astroctl"), "launch", "globe"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ------------------------------------------------------------ painting
    def blit(self, p, key, rect, fn, t):
        r = rect.adjusted(*PAD)
        pm = self.cache.get(key)
        if pm is None:
            pm = self.pool.get(key) or QPixmap(r.width(), r.height())
            self.pool[key] = pm
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.translate(-r.x(), -r.y())
            fn(q, rect, t)
            q.end()
            self.cache[key] = pm
        p.drawPixmap(r.x(), r.y(), pm)

    def paintEvent(self, ev):
        t = time.time() - self.t0
        p = QPainter(self)
        region = ev.region()
        hit = region.intersects
        br = ev.rect()                  # Qt already clips this to the dirty region
        p.drawPixmap(br, self.bg, br)
        boot = max(0.0, min(1.0, (t - 2.0) / 1.2))
        a = boot * boot * (3 - 2 * boot)
        if a > 0.01:
            p.setOpacity(a)
            for key, rect, _, fn, _d in self.panels:
                if hit(rect.adjusted(*PAD)):
                    self.blit(p, key, rect, fn, t)
            if hit(self.globe_rect):
                p.save()
                p.setClipRect(self.globe_rect)
                box = paint_links(p, self.gcx, self.gcy, self.gR, self.yaw, self.tilt, t, self.home,
                                  self.cfg["label"], self.scan.groups, self.hover, lift_max=0.2)
                p.restore()
                self.link_box = box.intersected(self.globe_rect)
            if hit(self.core_rect):
                self.paint_core(p, t)
            p.setOpacity(1.0)
        if t < 3.4:
            self.paint_boot(p, t, 1 - a)
        if self.ripples:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for x, y, age in self.ripples:
                pen = QPen(col(CYAN, 255 * (1 - age / 0.9)))
                pen.setWidthF(2)
                p.setPen(pen)
                p.drawEllipse(QPointF(x, y), age * 200, age * 200)
        p.end()

    # --- top: clock, link status, globe, trace log
    def paint_clock(self, p, r, t):
        now = time.localtime()
        p.setFont(font(44, True, spacing=2))
        s = time.strftime(CLOCK_HMS, now)
        p.setPen(col(GREEN, 60))
        p.drawText(r.x() + 2, r.y() + 46, s)
        p.setPen(WHITE)
        p.drawText(r.x(), r.y() + 44, s)
        p.setFont(font(13, False, spacing=3))
        p.setPen(col(GREEN, 220))
        p.drawText(r.x() + 2, r.y() + 74, time.strftime("%A %d %b %Y", now).upper())
        p.setPen(col(CYAN, 200))
        p.setFont(font(12, False, spacing=1))
        p.drawText(r.x() + 2, r.y() + 96, p.fontMetrics().elidedText(
            f"{self.host.upper()} // {self.ip}", Qt.TextElideMode.ElideMiddle, r.width()))

    def paint_status(self, p, r, t):
        groups = self.scan.groups
        flagged = sum(1 for g in groups if g["flag"])
        hud_panel(p, r.x(), r.y(), r.width(), r.height(), "LINK STATUS", 1.0, MAGENTA if flagged else GREEN)
        rows = (("SOCKETS", self.scan.total, GREEN), ("REMOTE", sum(g["n"] for g in groups), CYAN),
                ("LOCAL NET", self.scan.local, GREEN), ("FLAGGED", flagged, MAGENTA if flagged else GREEN))
        for i, (k, v, c) in enumerate(rows):
            y = r.y() + 36 + i * 30
            p.setFont(font(13, True, spacing=2))
            p.setPen(col(c, 190))
            p.drawText(r.x() + 14, y, k)
            p.setFont(font(22, True))
            p.setPen(WHITE if (k == "FLAGGED" and flagged) else c)
            p.drawText(QRect(r.x(), y - 22, r.width() - 14, 28), Qt.AlignmentFlag.AlignRight, str(v))

    def paint_hint(self, p, r, t):
        p.setFont(font(12, False, spacing=1.5))
        for i, (c, s) in enumerate(((GREEN, "NORMAL LINK"), (AMBER, "NEW REGION / ODD PORT"),
                                    (MAGENTA, "INBOUND FROM INTERNET"))):
            y = r.y() + 14 + i * 22
            p.fillRect(r.x() + 2, y - 9, 16, 4, c)
            p.setPen(col(c, 220))
            p.drawText(r.x() + 28, y, s)
        p.setPen(col(GREEN, 130))
        p.drawText(r.x() + 2, r.y() + 84, "DRAG GLOBE TO ROTATE")
        p.drawText(r.x() + 2, r.y() + 104, "DOUBLE-CLICK TO EXPAND")

    def paint_globe_base(self, p, r, t):
        paint_base(p, self.gcx, self.gcy, self.gR, self.yaw, self.tilt, self.land, self.grat)

    def paint_trace(self, p, r, t):
        groups = self.scan.groups
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        hud_panel(p, x, y, w, h, "TRACE LOG // LIVE CONNECTIONS", 1.0)
        self.rows = []
        yy = y + 18
        row_h = 55
        for i, g in enumerate(groups):
            if yy + row_h > y + h - 8:
                p.setPen(col(GREEN, 150))
                p.setFont(font(12, False, spacing=1))
                p.drawText(x + 16, yy + 14, f"+ {len(groups) - i} MORE DESTINATIONS")
                break
            rr = QRect(x + 6, yy, w - 12, row_h - 6)
            self.rows.append((i, rr))
            c = flag_color(g)
            if i == self.hover:
                p.fillRect(rr, col(c, 40))
            p.fillRect(rr.left(), rr.top(), 3, rr.height(), c)
            p.setFont(font(14, True, spacing=0.5))
            fm = p.fontMetrics()
            p.setPen(WHITE if i == self.hover else c)
            p.drawText(rr.left() + 12, rr.top() + 15,
                       fm.elidedText(f"{g['city'].upper()}, {g['cc']}", Qt.TextElideMode.ElideRight, w - 150))
            tag = g["flag"] or ("IN" if g["inbound"] else "OUT")
            p.setFont(font(11, True, spacing=1))
            tw = p.fontMetrics().horizontalAdvance(tag) + 10
            p.fillRect(rr.right() - tw - 2, rr.top() + 3, tw, 15, col(c, 255 if g["flag"] else 40))
            p.setPen(tc(0, 0, 0) if g["flag"] else c)
            p.drawText(rr.right() - tw + 3, rr.top() + 14, tag)
            p.setFont(font(12))
            fm = p.fontMetrics()
            p.setPen(col(CYAN, 230))
            p.drawText(rr.left() + 12, rr.top() + 30,
                       fm.elidedText(g["org"] or "UNKNOWN NETWORK", Qt.TextElideMode.ElideRight, w - 40))
            p.setPen(col(GREEN, 170))
            ports = ",".join(str(pt) for pt in sorted(g["ports"])[:3])
            p.drawText(rr.left() + 12, rr.top() + 44,
                       fm.elidedText(f"{'/'.join(sorted(g['procs']))[:26]}  :{ports}  x{g['n']}",
                                     Qt.TextElideMode.ElideRight, w - 40))
            yy += row_h
        if not groups:
            p.setPen(col(GREEN, 160))
            p.setFont(font(13, False, spacing=1))
            p.drawText(x + 16, y + 40, "NO REMOTE LINKS ACTIVE")

    # --- bottom: system panels
    def bar(self, p, x, y, w, label, frac, text):
        frac = max(0.0, min(1.0, frac))
        p.setFont(font(13, True, spacing=1))
        p.setPen(GREEN)
        p.drawText(x, y + 12, label)
        bx, bw = x + 42, w - 42 - 104
        seg = 6
        n = bw // seg
        on = int(n * frac + 0.5)
        for i in range(n):
            c = GREEN if i < n * 0.7 else (AMBER if i < n * 0.9 else MAGENTA)
            p.fillRect(bx + i * seg, y + 2, seg - 2, 11, col(c, 235 if i < on else 36))
        p.setPen(WHITE)
        p.drawText(QRect(x + w - 100, y - 2, 100, 18), Qt.AlignmentFlag.AlignRight, text)

    def paint_cpu(self, p, r, t):
        st = self.stats
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        n = len(self.cores_smooth)
        hud_panel(p, x, y, w, h, f"CORE MATRIX // {n} THREADS", 1.0)
        per, gap = 18, 3
        cell = (w - 24) // per - gap
        gx, gy = x + 12, y + 20
        for i, u in enumerate(self.cores_smooth):
            c = mix(GREEN_DARK, GREEN, u * 2) if u < 0.5 else mix(GREEN, MAGENTA, (u - 0.5) * 2)
            p.fillRect(gx + (i % per) * (cell + gap), gy + (i // per) * (cell + gap), cell, cell,
                       col(c, 70 + 185 * min(1, u * 1.6 + 0.12)))
        rows = (n + per - 1) // per
        yy = gy + rows * (cell + gap) + 8
        self.bar(p, x + 12, yy, w - 24, "CPU", st.total, f"{st.total * 100:5.1f}%")
        self.bar(p, x + 12, yy + 22, w - 24, "MEM", st.mem_used / st.mem_total,
                 f"{st.mem_used:4.1f}/{st.mem_total:.0f}G")
        up = int(getattr(st, "uptime", 0))
        p.setFont(font(12, False, spacing=1))
        p.setPen(col(GREEN, 190))
        p.drawText(x + 12, y + h - 10, f"LOAD {getattr(st, 'load', '0')}    UP {up // 86400}d "
                                       f"{up % 86400 // 3600:02d}:{up % 3600 // 60:02d}")

    def paint_net(self, p, r, t):
        st = self.stats
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        hud_panel(p, x, y, w, h, f"NET LINK // {st.iface.upper()}", 1.0, CYAN)
        p.setFont(font(13, True, spacing=1))
        p.setPen(GREEN)
        p.drawText(x + 14, y + 30, f"RX {human_rate(st.rx)}")
        p.setPen(MAGENTA)
        p.drawText(x + 170, y + 30, f"TX {human_rate(st.tx)}")
        gx, gy, gw, gh = x + 12, y + 42, w - 24, h - 54
        p.setPen(col(CYAN, 30))
        for i in range(1, 4):
            p.drawLine(gx, gy + gh * i // 4, gx + gw, gy + gh * i // 4)
        peak = max(1024.0, max(max(a, b) for a, b in self.net_hist))
        n = len(self.net_hist)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for idx, c in ((0, GREEN), (1, MAGENTA)):
            pen = QPen(c)
            pen.setWidthF(1.4)
            p.setPen(pen)
            prev = None
            for i, v in enumerate(self.net_hist):
                pt = QPointF(gx + gw * i / (n - 1), gy + gh - 2 - (gh - 6) * math.sqrt(v[idx] / peak))
                if prev is not None:
                    p.drawLine(prev, pt)
                prev = pt
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def paint_proc(self, p, r, t):
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        hud_panel(p, x, y, w, h, f"PROCESS FEED // {self.feed.count} TASKS", 1.0)
        p.setFont(font(13, False, spacing=0.5))
        p.setPen(col(CYAN, 200))
        p.drawText(x + 14, y + 28, "PID       CPU%   TASK")
        for i, (cpu, pid, name) in enumerate(self.feed.top[:(h - 60) // 21]):
            c = MAGENTA if cpu > 80 else (AMBER if cpu > 30 else GREEN)
            yy = y + 50 + i * 21
            p.fillRect(x + 222, yy - 9, int(min(1.0, cpu / 100) * (w - 240)), 9, col(c, 60))
            p.setPen(col(c, 255 - i * 9))
            p.drawText(x + 14, yy, f"{pid:<8} {cpu:6.1f}   {name[:22]}")

    def paint_gpu(self, p, r, t):
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        gpus = self.gpufeed.gpus
        cards = self.gpu_cards
        slots = min(4, max(len(cards), len(gpus), 1))
        ok = len(gpus) >= slots
        hud_panel(p, x, y, w, h, f"GPU BAY {len(gpus)}/{slots}", 1.0, GREEN if ok else AMBER)
        for i in range(slots):
            sy = y + 22 + i * 39
            g = gpus[i] if i < len(gpus) else None
            p.setBrush(Qt.BrushStyle.NoBrush)
            if g is None:
                pen = QPen(col(AMBER, 130))
                pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawRect(x + 12, sy, w - 24, 30)
                p.setFont(font(12, True, spacing=1))
                p.setPen(col(AMBER, 200))
                p.drawText(x + 20, sy + 13, f"SLOT {i}")
                p.drawText(x + 20, sy + 26, cards[i] if i < len(cards) else "EMPTY")
                continue
            u = g["util"] / 100
            c = MAGENTA if (u > 0.9 or g["temp"] >= 85) else (AMBER if u > 0.6 else GREEN)
            p.setPen(col(c, 200))
            p.drawRect(x + 12, sy, w - 24, 30)
            p.fillRect(x + 14, sy + 2, int((w - 27) * u), 27, col(c, 60))
            mem = g["used"] / max(0.1, g["total"])
            p.fillRect(x + 14, sy + 26, int((w - 27) * mem), 3, CYAN)
            p.setFont(font(12, True, spacing=0.5))
            p.setPen(WHITE)
            p.drawText(x + 20, sy + 13, f"GPU {i}  {g['util']:3.0f}%   {g['temp']:.0f}C")
            p.setPen(col(CYAN, 230))
            p.drawText(x + 20, sy + 25, f"{g['used']:4.1f} / {g['total']:.0f} G")

    def paint_core_panel(self, p, r, t):
        c = MAGENTA if self.dictating else (CYAN if self.voice_state == "SIGNAL" else GREEN)
        hud_panel(p, r.x(), r.y(), r.width(), r.height(), "CORE", 1.0, c)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k, start, span, wd, cc in ((1.24, 30, 110, 1.6, c), (1.24, 200, 120, 1.6, c), (1.36, 110, 70, 1.0, CYAN)):
            pen = QPen(col(cc, 200))
            pen.setWidthF(wd)
            p.setPen(pen)
            rr = self.cR * k
            p.drawArc(int(self.ccx - rr), int(self.ccy - rr), int(rr * 2), int(rr * 2), start * 16, span * 16)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def paint_core(self, p, t):
        """Glyph sphere: breathes with CPU load, flares and changes colour with the microphone."""
        cx, cy, R = self.ccx, self.ccy, self.cR
        load = min(1.0, self.stats.total * 2.5)
        v = self.voice
        alt = self.small_m if self.dictating else self.small_c
        if v > 0.03:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col(MAGENTA if self.dictating else CYAN, 80 * v))
            p.drawEllipse(QPointF(cx, cy), R * (0.9 + 0.12 * v), R * (0.9 + 0.12 * v))
            p.setBrush(Qt.BrushStyle.NoBrush)
        self.spin += (0.32 + 0.9 * v) * 0.05
        ca, sa = math.cos(self.spin), math.sin(self.spin)
        cb, sb = math.cos(0.38), math.sin(0.38)
        sm = self.small
        hw, hh = sm.w / 2, sm.h / 2
        beat = int(t * 3)
        tint = int(v * 120) + (25 if self.dictating else 0)
        boost = v * 3
        pts = []
        for x, y, z, gi, ph in self.sphere:
            x1 = x * ca + z * sa
            z1 = -x * sa + z * ca
            y1 = y * cb - z1 * sb
            z2 = y * sb + z1 * cb
            rr = R * (1 + 0.05 * load * math.sin(t * 5 + ph) + 0.015 * math.sin(t * 1.3 + ph)
                      + v * (0.03 + 0.09 * math.sin(t * 11 + ph * 5)))
            k = 1 / (1.9 - z2 * 0.3)
            pts.append((z2, cx + x1 * rr * k * 1.75, cy + y1 * rr * k * 1.75, gi))
        pts.sort()
        for z2, sx, sy, gi in pts:
            lv = int(1.2 + (z2 + 1) * 2.6 + boost)
            if (gi + beat) % 23 == 0:
                lv = 7
            at_ = alt if gi % 100 < tint else sm
            p.drawPixmap(int(sx - hw), int(sy - hh), at_.get(gi + (beat + gi) // 7, lv))

    def paint_voice(self, p, r, t):
        """Oscilloscope of what the microphone hears; idles as a slow ripple when the room is quiet."""
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        v = self.voice
        if self.dictating:
            c = mix(MAGENTA, WHITE, v * 0.6)
        else:
            c = mix(GREEN, CYAN, min(1.0, v * 2.5)) if v < 0.6 else mix(CYAN, WHITE, (v - 0.6) / 0.4)
        frame = MAGENTA if self.dictating else (CYAN if self.voice_state == "SIGNAL" else GREEN)
        hud_panel(p, x, y, w, h, "VOICE CORTEX // MIC", 1.0, frame)
        p.setFont(font(13, True, spacing=2))
        p.setPen(frame)
        p.drawText(x + 14, y + 30, f"STATE  {self.voice_state}")
        segs = (w - 28) // 10
        on = int(v * segs + 0.5)
        for i in range(segs):
            p.fillRect(x + 14 + i * 10, y + h - 20, 7, 8, col(c if i < on else GREEN, 255 if i < on else 40))
        wave = self.mic.wave
        n = len(wave)
        blend = min(1.0, v * 3.0)
        mid = y + h / 2 + 6
        span = w - 28
        p.setPen(col(GREEN, 28))
        p.drawLine(x + 14, int(mid), x + 14 + span, int(mid))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for cc, al, wd in ((c, 70, 4.0), (c, 255, 1.6)):
            pen = QPen(col(cc, al))
            pen.setWidthF(wd)
            p.setPen(pen)
            prev = None
            for i in range(n):
                u = i / (n - 1)
                env = math.sin(u * math.pi)
                idle = math.sin(u * 22 + t * 2.5) * math.sin(u * 5 - t * 1.7) * 6
                live = max(-1.0, min(1.0, wave[i] * 1.3)) * 48
                pt = QPointF(x + 14 + span * u, mid + (idle * (1 - blend) + live * blend) * env)
                if prev is not None:
                    p.drawLine(prev, pt)
                prev = pt
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def paint_boot(self, p, t, a):
        if a <= 0.01:
            return
        p.setFont(font(15, False, spacing=1))
        x, y = int(self.W / 2 - 230), int(self.H * 0.5)
        for i, line in enumerate(self.boot_lines):
            start = 0.2 + i * 0.25
            if t < start:
                break
            c = AMBER if "WARN" in line else (WHITE if "DONE" in line else GREEN)
            p.setPen(col(c, 255 * a))
            p.drawText(x, y + i * 22, line[:int((t - start) * 120)])
        p.setFont(font(64, True, spacing=10))
        title = scramble("ASTRO//OS", min(1.0, t / 1.6), 7)
        w = p.fontMetrics().horizontalAdvance(title)
        p.setPen(col(GREEN, 70 * a))
        p.drawText(int(self.W / 2 - w / 2) + 3, int(self.H * 0.36) + 3, title)
        p.setPen(col(WHITE, 255 * a))
        p.drawText(int(self.W / 2 - w / 2), int(self.H * 0.36), title)
        bw = 500
        bx, by = int(self.W / 2 - bw / 2), int(self.H * 0.36) + 30
        p.setPen(col(GREEN, 160 * a))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(bx, by, bw, 8)
        p.fillRect(bx + 2, by + 2, int((bw - 3) * min(1.0, t / 2.0)), 5, col(GREEN, 255 * a))


def main():
    app = QApplication(sys.argv)
    w = Desktop(boot="--no-boot" not in sys.argv)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
