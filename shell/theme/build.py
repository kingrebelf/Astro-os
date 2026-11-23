#!/usr/bin/env python3
"""Generate ASTRO//OS theme assets: cursor theme + Openbox window theme."""
import math
import os
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPolygonF

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import palette

HOME = os.path.expanduser("~")
PAL = palette.current()          # the active theme recolours the cursor and the window borders too


def tc(r, g, b, a=255):
    return QColor(*PAL.remap((r, g, b)), a)


GREEN, CYAN, MAG, WHITE = tc(0, 255, 140), tc(0, 229, 255), tc(255, 43, 214), tc(225, 255, 240)
SZ = 48          # canvas; nominal size 32
app = QGuiApplication(sys.argv)


def canvas():
    img = QImage(SZ, SZ, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return img, p


def glow_path(p, path, color, fill=tc(0, 14, 9, 235), width=1.8, glow=1.0):
    for w, a in ((7, 28), (4.5, 60)):
        c = QColor(color)
        c.setAlpha(int(a * glow))
        pen = QPen(c)
        pen.setWidthF(w)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.setBrush(fill if fill else Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def poly(points):
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
    path.closeSubpath()
    return path


def arrow_path(ox=5, oy=4, s=1.0):
    pts = [(0, 0), (0, 25), (6.5, 19.5), (11, 29), (15, 27), (10.5, 18), (19, 18)]
    return poly([(ox + x * s, oy + y * s) for x, y in pts])


def frames_arrow(color=GREEN, extra=None, n=12):
    out = []
    for i in range(n):
        ph = 0.5 + 0.5 * math.sin(i / n * 2 * math.pi)
        img, p = canvas()
        glow_path(p, arrow_path(), color, glow=0.6 + 0.8 * ph)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(WHITE)
        p.drawEllipse(QPointF(5.8, 5.5), 1.6, 1.6)          # hot tip
        if extra:
            extra(p, i, n)
        p.end()
        out.append((img, 90))
    return out, (5, 4)


def spinner(p, cx, cy, r, i, n, color=CYAN):
    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(QColor(color.red(), color.green(), color.blue(), 70))
    pen.setWidthF(2.4)
    p.setPen(pen)
    p.drawEllipse(QPointF(cx, cy), r, r)
    pen = QPen(WHITE)
    pen.setWidthF(2.6)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(-i / n * 360 * 16), 100 * 16)
    pen.setColor(color)
    p.setPen(pen)
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int((-i / n * 360 + 180) * 16), 60 * 16)


def make_wait(n=16):
    out = []
    for i in range(n):
        img, p = canvas()
        spinner(p, 24, 24, 13, i, n)
        spinner(p, 24, 24, 7, n - i, n, GREEN)
        p.end()
        out.append((img, 45))
    return out, (24, 24)


def make_progress():
    return frames_arrow(GREEN, lambda p, i, n: spinner(p, 34, 34, 8, i, n), 16)


def make_pointer(n=12):
    out = []
    for i in range(n):
        ph = 0.5 + 0.5 * math.sin(i / n * 2 * math.pi)
        img, p = canvas()
        # targeting reticle with a centre dot
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = 11 + ph * 2
        for w, a in ((6, 40), (2, 255)):
            pen = QPen(QColor(CYAN.red(), CYAN.green(), CYAN.blue(), a))
            pen.setWidthF(w)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            for k in range(4):
                p.drawArc(QRectF(24 - r, 24 - r, 2 * r, 2 * r), int((k * 90 + 20 + i * 30 / n * 3) * 16), 50 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tc(0, 14, 9, 200))
        p.drawEllipse(QPointF(24, 24), 5, 5)
        p.setBrush(WHITE)
        p.drawEllipse(QPointF(24, 24), 2.6, 2.6)
        p.end()
        out.append((img, 70))
    return out, (24, 24)


def make_text():
    img, p = canvas()
    path = QPainterPath()
    for (x1, y1, x2, y2) in ((24, 10, 24, 38), (19, 9, 29, 9), (19, 39, 29, 39)):
        path.moveTo(x1, y1)
        path.lineTo(x2, y2)
    glow_path(p, path, GREEN, fill=None, width=2.0)
    p.end()
    return [(img, 0)], (24, 24)


def make_cross():
    img, p = canvas()
    path = QPainterPath()
    for (x1, y1, x2, y2) in ((24, 8, 24, 20), (24, 28, 24, 40), (8, 24, 20, 24), (28, 24, 40, 24)):
        path.moveTo(x1, y1)
        path.lineTo(x2, y2)
    glow_path(p, path, CYAN, fill=None, width=1.8)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawEllipse(QPointF(24, 24), 1.6, 1.6)
    p.end()
    return [(img, 0)], (24, 24)


def double_arrow(angle, four=False):
    img, p = canvas()
    p.translate(24, 24)
    p.rotate(angle)
    head = lambda s: [(s * 15, 0), (s * 8, -6), (s * 8, -2.2), (0, -2.2), (0, 2.2), (s * 8, 2.2), (s * 8, 6)]
    shape = head(1)[:4] + [(-8, -2.2), (-8, -6), (-15, 0), (-8, 6), (-8, 2.2), (8, 2.2), (8, 6)]
    path = poly(shape)
    if four:
        path2 = poly([(y, x) for x, y in shape])
        path = path.united(path2)
    glow_path(p, path, GREEN, width=1.5)
    p.end()
    return [(img, 0)], (24, 24)


def make_no():
    img, p = canvas()
    path = QPainterPath()
    path.addEllipse(QPointF(24, 24), 12, 12)
    path.moveTo(15.5, 15.5)
    path.lineTo(32.5, 32.5)
    glow_path(p, path, MAG, fill=None, width=2.4)
    p.end()
    return [(img, 0)], (24, 24)


CURSORS = {
    "left_ptr": (frames_arrow, "default arrow top_left_arrow"),
    "xterm": (make_text, "text ibeam"),
    "hand2": (make_pointer, "hand1 pointer pointing_hand hand"),
    "watch": (make_wait, "wait"),
    "left_ptr_watch": (make_progress, "progress half-busy"),
    "crosshair": (make_cross, "cross tcross"),
    "fleur": (lambda: double_arrow(0, True), "move all-scroll size_all grabbing closedhand grab openhand"),
    "sb_h_double_arrow": (lambda: double_arrow(0), "ew-resize h_double_arrow size_hor col-resize left_side right_side e-resize w-resize split_h"),
    "sb_v_double_arrow": (lambda: double_arrow(90), "ns-resize v_double_arrow size_ver row-resize top_side bottom_side n-resize s-resize split_v"),
    "bd_double_arrow": (lambda: double_arrow(45), "nwse-resize size_fdiag top_left_corner bottom_right_corner nw-resize se-resize"),
    "fd_double_arrow": (lambda: double_arrow(-45), "nesw-resize size_bdiag top_right_corner bottom_left_corner ne-resize sw-resize"),
    "not-allowed": (make_no, "crossed_circle forbidden no-drop circle"),
}


def build_cursors():
    dest = os.path.join(HOME, ".icons", "AstroOS")
    cur = os.path.join(dest, "cursors")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(cur)
    with open(os.path.join(dest, "index.theme"), "w") as f:
        f.write("[Icon Theme]\nName=AstroOS\nComment=ASTRO//OS neon cursors\nInherits=breeze_cursors\n")
    tmp = tempfile.mkdtemp()
    for name, (fn, aliases) in CURSORS.items():
        frames, (hx, hy) = fn()
        lines = []
        for i, (img, delay) in enumerate(frames):
            for size in (32, 48):
                scaled = img if size == 48 else img.scaled(32, 32, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation)
                fn_ = os.path.join(tmp, f"{name}_{size}_{i}.png")
                scaled.save(fn_)
                k = size / 48
                nominal = 24 if size == 32 else 36
                lines.append(f"{nominal} {int(hx * k)} {int(hy * k)} {fn_}" + (f" {delay}" if delay else ""))
        cfg = os.path.join(tmp, name + ".cfg")
        with open(cfg, "w") as f:
            f.write("\n".join(lines) + "\n")
        subprocess.run(["xcursorgen", cfg, os.path.join(cur, name)], check=True)
        for a in aliases.split():
            os.symlink(name, os.path.join(cur, a))
    shutil.rmtree(tmp)
    print("cursors ->", dest)


XBM = {
    "close": ["#......#", ".#....#.", "..#..#..", "...##...", "...##...", "..#..#..", ".#....#.", "#......#"],
    "max": ["########", "########", "#......#", "#......#", "#......#", "#......#", "#......#", "########"],
    "max_toggled": ["..######", "..#....#", "######.#", "#....#.#", "#....#.#", "#....###", "#....#..", "######.."],
    "iconify": ["........", "........", "........", "........", "........", "........", "########", "########"],
    "shade": ["########", "########", "........", "........", "........", "........", "........", "........"],
    "desk": ["##....##", "##....##", "........", "........", "........", "........", "##....##", "##....##"],
}

THEMERC = """
border.width: 1
padding.width: 7
padding.height: 5
window.handle.width: 0
window.client.padding.width: 0
window.client.padding.height: 0
window.label.text.justify: left

window.active.border.color: #00ff8c
window.inactive.border.color: #0b4d33
window.active.title.separator.color: #00ff8c
window.inactive.title.separator.color: #0b4d33
window.active.client.color: #010604
window.inactive.client.color: #010604

window.active.title.bg: flat gradient horizontal
window.active.title.bg.color: #00472a
window.active.title.bg.colorTo: #010805
window.inactive.title.bg: flat solid
window.inactive.title.bg.color: #010805

window.active.label.bg: parentrelative
window.active.label.text.color: #dcfff0
window.inactive.label.bg: parentrelative
window.inactive.label.text.color: #2f8a62

window.active.handle.bg: flat solid
window.active.handle.bg.color: #00ff8c
window.inactive.handle.bg: flat solid
window.inactive.handle.bg.color: #0b4d33
window.active.grip.bg: flat solid
window.active.grip.bg.color: #00e5ff
window.inactive.grip.bg: flat solid
window.inactive.grip.bg.color: #0b4d33

window.active.button.unpressed.bg: parentrelative
window.active.button.unpressed.image.color: #00ff8c
window.active.button.hover.bg: flat solid
window.active.button.hover.bg.color: #00ff8c
window.active.button.hover.image.color: #000000
window.active.button.pressed.bg: flat solid
window.active.button.pressed.bg.color: #00e5ff
window.active.button.pressed.image.color: #000000
window.active.button.toggled.unpressed.bg: parentrelative
window.active.button.toggled.unpressed.image.color: #00e5ff
window.active.button.toggled.hover.bg: flat solid
window.active.button.toggled.hover.bg.color: #00e5ff
window.active.button.toggled.hover.image.color: #000000
window.active.button.toggled.pressed.bg: flat solid
window.active.button.toggled.pressed.bg.color: #00ff8c
window.active.button.toggled.pressed.image.color: #000000
window.active.button.disabled.bg: parentrelative
window.active.button.disabled.image.color: #0b4d33

window.inactive.button.unpressed.bg: parentrelative
window.inactive.button.unpressed.image.color: #1f7350
window.inactive.button.hover.bg: flat solid
window.inactive.button.hover.bg.color: #1f7350
window.inactive.button.hover.image.color: #000000
window.inactive.button.pressed.bg: flat solid
window.inactive.button.pressed.bg.color: #00ff8c
window.inactive.button.pressed.image.color: #000000
window.inactive.button.toggled.unpressed.bg: parentrelative
window.inactive.button.toggled.unpressed.image.color: #1f7350
window.inactive.button.disabled.bg: parentrelative
window.inactive.button.disabled.image.color: #0b4d33

menu.border.width: 1
menu.border.color: #00ff8c
menu.overlap.x: -4
menu.separator.color: #0b4d33
menu.separator.width: 1
menu.separator.padding.width: 6
menu.separator.padding.height: 4
menu.title.bg: flat solid
menu.title.bg.color: #00472a
menu.title.text.color: #dcfff0
menu.title.text.justify: left
menu.items.bg: flat solid
menu.items.bg.color: #010805
menu.items.text.color: #00ff8c
menu.items.disabled.text.color: #1f7350
menu.items.active.bg: flat solid
menu.items.active.bg.color: #00ff8c
menu.items.active.text.color: #000000
menu.items.active.disabled.text.color: #0b4d33

osd.border.width: 1
osd.border.color: #00ff8c
osd.bg: flat solid
osd.bg.color: #010805
osd.label.bg: parentrelative
osd.label.text.color: #dcfff0
osd.hilight.bg: flat solid
osd.hilight.bg.color: #00ff8c
osd.unhilight.bg: flat solid
osd.unhilight.bg.color: #0b4d33
"""


def build_openbox():
    dest = os.path.join(HOME, ".themes", "AstroOS", "openbox-3")
    shutil.rmtree(os.path.dirname(dest), ignore_errors=True)
    os.makedirs(dest)
    with open(os.path.join(dest, "themerc"), "w") as f:
        f.write(PAL.text(THEMERC.lstrip()))
    for name, rows in XBM.items():
        data = []
        for row in rows:
            data.append(sum(1 << i for i, ch in enumerate(row) if ch == "#"))
        with open(os.path.join(dest, name + ".xbm"), "w") as f:
            f.write(f"#define {name}_width 8\n#define {name}_height 8\n"
                    f"static unsigned char {name}_bits[] = {{ " + ", ".join(f"0x{b:02x}" for b in data) + " };\n")
    print("openbox theme ->", dest)


if __name__ == "__main__":
    build_cursors()
    build_openbox()
