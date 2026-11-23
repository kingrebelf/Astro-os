#!/usr/bin/env python3
"""ECHO: a voice avatar made of code glyphs.

Materialises whenever the dictation app (OpenWhispr) opens the microphone,
reacts to your voice while it listens, then dissolves when it stops.
Run with --demo to preview it without speaking.
"""
import array
import json
import math
import os
import random
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QRadialGradient, QRegion
from PyQt6.QtWidgets import QApplication, QWidget

from common import (tc, CYAN, GREEN, MAGENTA, STATE, WHITE, GlyphAtlas, col, font,
                    mix, scramble)

WIN_W, WIN_H = 470, 590
DOCK_H = 46
MATCH = os.environ.get("ASTRO_ECHO_MATCH", "whispr").lower()


# ------------------------------------------------------------------ audio
class Mic(threading.Thread):
    """Reads mic level only while the avatar is listening."""

    def __init__(self):
        super().__init__(daemon=True)
        self.want = False
        self.level = 0.0
        self.peak = 600.0
        self.proc = None

    def run(self):
        while True:
            if not self.want:
                self.level *= 0.8
                time.sleep(0.05)
                continue
            try:
                self.proc = subprocess.Popen(
                    ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16",
                     "--latency", "20ms", "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                while self.want:
                    buf = self.proc.stdout.read(640)       # 20 ms
                    if not buf:
                        break
                    a = array.array("h", buf[:len(buf) // 2 * 2])
                    if not a:
                        continue
                    rms = math.sqrt(sum(v * v for v in a) / len(a))
                    self.peak = max(self.peak * 0.999, rms, 600.0)
                    self.level = min(1.0, (rms / self.peak) ** 0.7)
            except OSError:
                time.sleep(1)
            finally:
                if self.proc:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                    self.proc = None


class Watcher(threading.Thread):
    """Polls PipeWire for a capture stream owned by the dictation app."""

    def __init__(self, mic):
        super().__init__(daemon=True)
        self.mic = mic
        self.recording = False

    def run(self):
        while True:
            found = False
            try:
                out = subprocess.run(["pw-dump"], capture_output=True, timeout=3).stdout
                for o in json.loads(out):
                    props = (o.get("info") or {}).get("props") or {}
                    if props.get("media.class") != "Stream/Input/Audio":
                        continue
                    ident = " ".join(str(props.get(k, "")) for k in
                                     ("application.name", "application.process.binary",
                                      "node.name")).lower()
                    if MATCH in ident:
                        found = True
                        break
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            self.recording = found
            time.sleep(0.2)


# ------------------------------------------------------------------ geometry
def build_head():
    """Point cloud of a stylised head + shoulders. Returns list of dicts."""
    pts = []
    n = 1250
    for i in range(n):
        dy = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - dy * dy)
        ang = i * 2.399963
        dx, dz = math.cos(ang) * r, math.sin(ang) * r
        x, y, z = dx * 0.80, dy * 1.06, dz * 0.92
        if dy < 0:                                   # jaw taper
            k = (-dy) ** 1.5
            x *= 1 - 0.30 * k
            z *= 1 - 0.16 * k
        shade = 0.0
        kind = "skin"
        if dz > 0:
            ax = abs(x)
            eye = math.exp(-(((ax - 0.29) / 0.15) ** 2 + ((y - 0.16) / 0.085) ** 2))
            nose = math.exp(-((x / 0.085) ** 2 + ((y + 0.07) / 0.2) ** 2))
            tip = math.exp(-((x / 0.12) ** 2 + ((y + 0.2) / 0.07) ** 2))
            brow = math.exp(-(((ax - 0.29) / 0.22) ** 2 + ((y - 0.31) / 0.05) ** 2))
            lips = math.exp(-((x / 0.2) ** 2 + ((y + 0.46) / 0.05) ** 2))
            cheek = math.exp(-(((ax - 0.42) / 0.14) ** 2 + ((y + 0.1) / 0.14) ** 2))
            z += 0.17 * nose + 0.10 * tip + 0.05 * brow + 0.05 * lips + 0.03 * cheek - 0.10 * eye
            shade += 3.2 * nose + 2.6 * tip + 3.0 * brow + 1.3 * cheek + 1.5 * lips
            if eye > 0.28:
                continue                              # hollow sockets, eyes added below
            if abs(x) < 0.21 and -0.53 < y < -0.40:
                continue                              # mouth opening, lips added below
        pts.append({"p": (x, y, z), "shade": shade, "kind": kind, "jaw": max(0.0, -y - 0.38)})

    # eyes: glowing rings + pupil
    for sx in (-1, 1):
        for k in range(10):
            a = k / 10 * 6.283
            pts.append({"p": (sx * 0.29 + math.cos(a) * 0.12, 0.16 + math.sin(a) * 0.05, 0.78),
                        "shade": 9, "kind": "eye", "jaw": 0})
        for k in range(2):
            a = k / 2 * 6.283
            pts.append({"p": (sx * 0.29 + math.cos(a) * 0.012, 0.16, 0.80),
                        "shade": 9, "kind": "pupil", "jaw": 0})
    # lips: upper + lower line
    for k in range(9):
        u = k / 8 * 2 - 1
        curve = (1 - u * u)
        pts.append({"p": (u * 0.2, -0.425 + 0.012 * curve, 0.80 + 0.06 * curve),
                    "shade": 9, "kind": "lip_up", "jaw": 0})
        pts.append({"p": (u * 0.2, -0.50 - 0.012 * curve, 0.78 + 0.06 * curve),
                    "shade": 9, "kind": "lip_lo", "jaw": 0, "curve": curve})
    # neck
    for i in range(110):
        a = random.uniform(0, 6.283)
        y = random.uniform(-1.42, -0.92)
        r = 0.33 + 0.05 * (-(y + 0.92))
        pts.append({"p": (math.cos(a) * r, y, math.sin(a) * r * 0.9 - 0.08), "shade": 2.4,
                    "kind": "body", "jaw": 0})
    # shoulders
    for i in range(260):
        u = random.uniform(-1, 1)
        v = random.uniform(0, 1)
        x = u * 1.45
        top = -1.38 - 0.22 * abs(u) ** 1.6
        y = top - v * 0.26
        z = math.cos(u * 1.2) * 0.42 * (1 - v * 0.2) - 0.1
        pts.append({"p": (x, y, z), "shade": 3.6 - v * 2.6 + (1.5 if v < 0.12 else 0), "kind": "body", "jaw": 0})
    for q in pts:
        q["g"] = random.randrange(999)
        q["ph"] = random.random() * 6.283
        q["delay"] = random.random()
        q["fall"] = random.uniform(0.6, 1.6)
    return pts


class Avatar(QWidget):
    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.setWindowTitle("astro-os-echo")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                            | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        g = QApplication.primaryScreen().geometry()
        self.setGeometry(g.x() + (g.width() - WIN_W) // 2,
                         g.y() + g.height() - DOCK_H - WIN_H - 60, WIN_W, WIN_H)

        self.atlas = GlyphAtlas(11, levels=10)
        self.atlas_c = GlyphAtlas(11, levels=10, hue=CYAN)
        self.atlas_m = GlyphAtlas(11, levels=10, hue=MAGENTA)
        self.pts = build_head()
        self.state = "idle"            # idle | in | listen | think | out
        self.since = time.time()
        self.level = 0.0
        self.hist = [0.0] * 64
        self.rain = [[random.uniform(0, WIN_W), random.uniform(-WIN_H, WIN_H),
                      random.uniform(90, 240), random.randrange(999)] for _ in range(26)]

        # window shape: a round portal plus a caption plate (works without a compositor)
        self.PR = 226
        self.pcx, self.pcy = WIN_W // 2, 232
        self.plate = (WIN_W // 2 - 190, WIN_H - 104, 380, 86)
        shape = QRegion(self.pcx - self.PR, self.pcy - self.PR, self.PR * 2, self.PR * 2,
                        QRegion.RegionType.Ellipse)
        shape = shape.united(QRegion(*self.plate))
        self.setMask(shape)
        self.back = QPixmap(WIN_W, WIN_H)
        self.back.fill(tc(0, 7, 4))
        p = QPainter(self.back)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gr = QRadialGradient(self.pcx, self.pcy, self.PR)
        gr.setColorAt(0, tc(0, 34, 20))
        gr.setColorAt(0.7, tc(0, 12, 7))
        gr.setColorAt(1, tc(0, 4, 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gr))
        p.drawEllipse(QPointF(self.pcx, self.pcy), self.PR, self.PR)
        p.end()

        self.mic = Mic()
        self.mic.start()
        self.watch = Watcher(self.mic)
        if not demo:
            self.watch.start()

        self.anim = QTimer(self)
        self.anim.timeout.connect(self.tick)
        self.idle = QTimer(self)
        self.idle.timeout.connect(self.check)
        self.idle.start(120)
        self.demo_t0 = time.time()
        self.trim = QTimer(self)
        self.trim.timeout.connect(self.trim_overlays)
        self.trim.start(2000)
        self.trim_overlays()
        self.set_state('idle')

    def trim_overlays(self):
        try:
            if not hasattr(self, 'x11'):
                import overlay
                from common import X11
                self.x11, self.overlay = X11(), overlay
            self.overlay.run(self.x11)
        except Exception:
            pass

    # ---------------------------------------------------------------- state
    def set_state(self, s):
        self.state = s
        self.since = time.time()
        try:
            os.makedirs(STATE, exist_ok=True)
            with open(os.path.join(STATE, "echo"), "w") as f:
                f.write(s)
        except OSError:
            pass

    def recording(self):
        if self.demo:
            return (time.time() - self.demo_t0) % 12 < 7.5
        return self.watch.recording

    def check(self):
        rec = self.recording()
        if self.state == "idle" and rec:
            self.mic.want = not self.demo
            self.set_state("in")
            self.show()
            self.raise_()
            self.anim.start(45)

    def tick(self):
        rec = self.recording()
        el = time.time() - self.since
        if self.state == "in" and el > 0.9:
            self.set_state("listen")
        elif self.state in ("in", "listen") and not rec:
            self.mic.want = False
            self.set_state("think")
        elif self.state == "think":
            if rec:
                self.mic.want = not self.demo
                self.set_state("listen")
            elif el > 1.3:
                self.set_state("out")
        elif self.state == "out" and el > 0.9:
            self.set_state("idle")
            self.anim.stop()
            self.hide()
            return
        if self.demo:
            t = time.time()
            target = max(0.0, math.sin(t * 9) * math.sin(t * 2.3) * 0.8 + 0.2 * math.sin(t * 23)) \
                if self.state == "listen" else 0.0
        else:
            target = self.mic.level if self.state in ("in", "listen") else 0.0
        self.level += (target - self.level) * (0.55 if target > self.level else 0.22)
        self.hist.pop(0)
        self.hist.append(self.level)
        self.update()

    # ---------------------------------------------------------------- paint
    def paintEvent(self, _):
        now = time.time()
        t = now
        el = now - self.since
        st = self.state
        if st == "idle":
            return
        p = QPainter(self)
        if st == "in":
            vis = min(1.0, el / 0.9)
        elif st == "out":
            vis = max(0.0, 1 - el / 0.9)
        else:
            vis = 1.0
        lvl = self.level
        think = st == "think"

        p.drawPixmap(0, 0, self.back)
        p.setClipRegion(QRegion(self.pcx - self.PR, self.pcy - self.PR, self.PR * 2, self.PR * 2,
                                QRegion.RegionType.Ellipse))

        cx, cy = float(self.pcx), float(self.pcy) - 8
        S = 138 + lvl * 5

        # falling code behind the head
        at = self.atlas
        for r in self.rain:
            r[1] += r[2] * 0.045 * (1.0 + lvl * 2.5)
            if r[1] > WIN_H:
                r[0], r[1] = random.uniform(20, WIN_W - 20), random.uniform(-200, -20)
            edge = 1 - abs(r[0] - cx) / (WIN_W / 2)
            for k in range(7):
                yy = r[1] - k * 13
                if 0 < yy < WIN_H - 100:
                    p.setOpacity(vis * max(0.0, edge) * (1 - k / 7) * 0.55)
                    p.drawPixmap(int(r[0]), int(yy), at.get(r[3] + k + int(t * 6), 6 if k else 9))
        p.setOpacity(1.0)

        # rings + circular voice waveform
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(Qt.BrushStyle.NoBrush)
        accent = CYAN if think else GREEN
        R = 212
        for i, (rk, sp, span, w) in enumerate(((1.0, 50, 100, 2.0), (1.0, 50, 100, 2.0),
                                               (1.07, -30, 60, 1.2), (1.07, -30, 200, 1.2))):
            pen = QPen(col(accent, 190 * vis))
            pen.setWidthF(w)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            start = (t * sp * (3.0 if think else 1.0) + i * 180) % 360
            rr = R * rk * (0.6 + 0.4 * vis)
            p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), int(start * 16), int(span * 16))
        nb = len(self.hist)
        pen = QPen()
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        for i in range(nb):
            v = self.hist[(i * 5 + int(t * 12)) % nb] * 0.6 + self.hist[-1 - (i % 8)] * 0.4
            a = i / nb * 6.283 - 1.5708
            r0 = R * 0.86
            r1 = r0 - 3 - v * 34
            pen.setColor(col(mix(accent, WHITE, v), (70 + 185 * min(1, v * 1.5)) * vis))
            p.setPen(pen)
            c_, s_ = math.cos(a), math.sin(a)
            p.drawLine(QPointF(cx + c_ * r0, cy + s_ * r0), QPointF(cx + c_ * r1, cy + s_ * r1))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # the head
        yaw = 0.42 * math.sin(t * 0.7) + (t * 5.0 if False else 0)
        pitch = 0.07 * math.sin(t * 0.9 + 1) - 0.05
        ca, sa = math.cos(yaw), math.sin(yaw)
        cb, sb = math.cos(pitch), math.sin(pitch)
        jaw = lvl * 0.16
        beat = int(t * 4)
        hw, hh = at.w / 2, at.h / 2
        lx, ly, lz = -0.45, 0.5, 0.74          # light direction
        out = []
        for q in self.pts:
            x, y, z = q["p"]
            kind = q["kind"]
            if kind == "lip_lo":
                y -= jaw * (0.4 + 0.6 * q["curve"])
            elif q["jaw"] > 0:
                y -= jaw * min(1.0, q["jaw"] * 4) * 0.55
            elif kind == "lip_up":
                y += jaw * 0.08
            x1 = x * ca + z * sa
            z1 = -x * sa + z * ca
            y1 = y * cb - z1 * sb
            z2 = y * sb + z1 * cb
            k = 1 / (1 - z2 * 0.16)
            sx = cx + x1 * S * k
            sy = cy - y1 * S * k + 22
            if kind in ("eye", "pupil", "lip_up", "lip_lo"):
                if z2 < 0.25:
                    continue
                if kind == "pupil":
                    lv = 9
                elif kind == "eye":
                    lv = 7 + int(lvl * 2.5)
                else:
                    lv = 7 + int(lvl * 2.5)
                which = 1
            else:
                if kind == "body":
                    lv = q["shade"] + 0.8 * math.sin(t * 2 + q["ph"]) + lvl
                else:
                    if z2 < -0.02:
                        continue
                    rr = math.sqrt(x1 * x1 + y1 * y1 + z2 * z2) + 1e-6
                    rim = (1 - z2 / rr) ** 2.2
                    nl = (x1 * lx + y1 * ly + z2 * lz) / rr
                    lv = 1.7 + 5.5 * rim + q["shade"] + max(0.0, nl) * 1.3 + lvl * 1.3
                if (q["g"] + beat) % 41 == 0:
                    lv += 3
                lv = int(lv)
                if lv < 1:
                    continue
                which = 2 if think and (q["g"] + beat) % 3 == 0 else 0
            # materialise / dissolve
            if st == "in":
                e = (el / 0.9 - q["delay"] * 0.55) / 0.45
                if e <= 0:
                    continue
                if e < 1:
                    sy -= (1 - e) ** 2 * 380 * q["fall"]
                    lv = 9 if e > 0.8 else lv
            elif st == "out":
                e = el / 0.9 - q["delay"] * 0.4
                if e > 0:
                    sy += e * e * 520 * q["fall"]
                    sx += math.sin(q["ph"]) * e * 30
                    lv = max(1, int(lv * (1 - e * 0.8)))
            out.append((z2, sx, sy, q["g"], lv, which))
        out.sort()
        atl = (self.atlas, self.atlas_c, self.atlas_m)
        for z2, sx, sy, g, lv, which in out:
            a_ = atl[1] if (which == 2) else atl[which]
            p.drawPixmap(int(sx - hw), int(sy - hh), a_.get(g + (beat + g) // 9, lv))

        # portal rim + caption plate
        p.setClipping(False)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for w_, al in ((7, 70), (2.5, 255)):
            pen = QPen(col(accent, al))
            pen.setWidthF(w_)
            p.setPen(pen)
            p.drawEllipse(QPointF(self.pcx, self.pcy), self.PR - 4, self.PR - 4)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        px_, py_, pw_, ph_ = self.plate
        p.fillRect(px_, py_, pw_, ph_, tc(0, 9, 6))
        p.setPen(col(accent, 255))
        p.drawRect(px_, py_, pw_ - 1, ph_ - 1)
        p.fillRect(px_, py_, pw_, 3, accent)
        # caption
        label = {"in": "ECHO // WAKING", "listen": "ECHO // LISTENING",
                 "think": "ECHO // TRANSCRIBING", "out": "ECHO // STANDBY"}[st]
        p.setFont(font(19, True, spacing=5))
        s = scramble(label, min(1.0, el / 0.45), 5)
        fm = p.fontMetrics()
        tx = int(cx - fm.horizontalAdvance(s) / 2)
        ty = WIN_H - 62
        p.setPen(col(accent, 70 * vis))
        p.drawText(tx + 2, ty + 2, s)
        p.setPen(col(WHITE, 255 * vis))
        p.drawText(tx, ty, s)
        # linear level meter under caption
        n = 40
        bw = 7
        x0 = int(cx - n * bw / 2)
        for i in range(n):
            d = abs(i - (n - 1) / 2) / (n / 2)
            v = self.hist[-1 - int(d * 30)]
            hgt = 2 + int(v * 20 * (1 - d * 0.5))
            p.fillRect(x0 + i * bw, ty + 22 - hgt // 2, bw - 3, hgt,
                       col(mix(accent, WHITE, v), (90 + 165 * v) * vis))
        p.end()


def main():
    app = QApplication(sys.argv)
    a = Avatar(demo="--demo" in sys.argv)
    app.avatar = a
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
