#!/usr/bin/env python3
"""Draw the installer's logo and welcome banner (run once while the image is built)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen

app = QGuiApplication(sys.argv)
here = os.path.dirname(os.path.abspath(__file__))
GREEN, CYAN, WHITE, BG = QColor(0, 255, 140), QColor(0, 229, 255), QColor(220, 255, 240), QColor(1, 7, 5)


def core(p, cx, cy, r):
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for rad, color, start, span, width in ((r, GREEN, 30, 250, r * 0.10), (r * 0.68, CYAN, 200, 220, r * 0.08)):
        pen = QPen(color)
        pen.setWidthF(width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawArc(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), start * 16, span * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawEllipse(QPointF(cx, cy), r * 0.26, r * 0.26)


logo = QImage(256, 256, QImage.Format.Format_ARGB32_Premultiplied)
logo.fill(0)
p = QPainter(logo)
core(p, 128, 128, 104)
p.end()
logo.save(os.path.join(here, "logo.png"))

w = QImage(760, 300, QImage.Format.Format_ARGB32_Premultiplied)
w.fill(BG)
p = QPainter(w)
core(p, 130, 150, 80)
f = QFont("Ubuntu Mono")
f.setPixelSize(64)
f.setBold(True)
f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6)
p.setFont(f)
p.setPen(WHITE)
p.drawText(250, 150, "ASTRO//OS")
f.setPixelSize(20)
f.setBold(False)
f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
p.setFont(f)
p.setPen(GREEN)
p.drawText(254, 190, "COMMAND DECK FOR YOUR MACHINE")
p.end()
w.save(os.path.join(here, "welcome.png"))

s = QImage(820, 480, QImage.Format.Format_ARGB32_Premultiplied)
s.fill(BG)
p = QPainter(s)
core(p, 410, 150, 70)
f.setPixelSize(30)
f.setBold(True)
p.setFont(f)
p.setPen(WHITE)
p.drawText(QRectF(0, 250, 820, 44), Qt.AlignmentFlag.AlignCenter, "INSTALLING ASTRO//OS")
f.setPixelSize(17)
f.setBold(False)
f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
p.setFont(f)
p.setPen(GREEN)
p.drawText(QRectF(0, 310, 820, 30), Qt.AlignmentFlag.AlignCenter, "Copying the system to disk. This takes a few minutes.")
p.drawText(QRectF(0, 340, 820, 30), Qt.AlignmentFlag.AlignCenter, "OpenCode is already on board: press {} CODE in the dock afterwards.")
p.end()
s.save(os.path.join(here, "slide.png"))
