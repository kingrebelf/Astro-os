#!/usr/bin/env python3
"""ASTRO//LOOK: themes, accent colours, light mode, corner rounding and fonts.

Pick a preset or build your own, watch the preview, press APPLY. The choice is
saved to ~/.config/astro-os/theme.json and the whole desktop reloads with it:
dashboard, dock, window borders, cursor, terminal, file manager, Firefox.
"""
import colorsys
import os
import subprocess
import sys

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QListWidget, QPushButton, QSlider, QVBoxLayout, QWidget)

import palette
from common import ROOT
from ui import make_app

COLOURS = [("bg", "BACKGROUND"), ("accent", "ACCENT"), ("accent2", "SECOND ACCENT"),
           ("alert", "ALERT"), ("warn", "WARNING"), ("text", "TEXT")]
DOCK_FONTS = ["Ubuntu", "Ubuntu Mono", "DejaVu Sans"]
UI_FONTS = ["Ubuntu Mono", "DejaVu Sans Mono"]


def flip_mode(theme, mode):
    """Switch a theme between dark and light, keeping its hues."""
    if theme["mode"] == mode:
        return
    theme["mode"] = mode
    for key in ("accent", "accent2", "alert", "warn"):
        r, g, b = (c / 255 for c in palette.parse(theme[key]))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        # bright neon reads on black; on a pale background the same hue has to be deeper
        v, s = (min(v, 0.52), max(s, 0.85)) if mode == "light" else (max(v, 0.95), s)
        theme[key] = palette.hexs(tuple(c * 255 for c in colorsys.hsv_to_rgb(h, s, v)))
    h = colorsys.rgb_to_hsv(*(c / 255 for c in palette.parse(theme["accent"])))[0]
    if mode == "light":
        theme["bg"] = palette.hexs(tuple(c * 255 for c in colorsys.hsv_to_rgb(h, 0.035, 0.955)))
        theme["text"] = palette.hexs(tuple(c * 255 for c in colorsys.hsv_to_rgb(h, 0.6, 0.09)))
    else:
        theme["bg"] = palette.hexs(tuple(c * 255 for c in colorsys.hsv_to_rgb(h, 0.8, 0.028)))
        theme["text"] = palette.hexs(tuple(c * 255 for c in colorsys.hsv_to_rgb(h, 0.12, 1.0)))


class Preview(QWidget):
    """A small mock of the desktop drawn with the theme being edited."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(430, 300)
        self.theme = dict(palette.DEFAULT)

    def set_theme(self, theme):
        self.theme = dict(theme)
        self.update()

    def paintEvent(self, _):
        t = self.theme
        pal = palette.Palette(dict(t))
        c = lambda r, g, b, a=255: QColor(*pal.remap((r, g, b)), a)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, c(1, 6, 4))
        mono = QFont(t["ui_font"])
        # clock + a dashboard panel
        mono.setPixelSize(26)
        mono.setBold(True)
        p.setFont(mono)
        p.setPen(c(215, 255, 235))
        p.drawText(14, 34, "07:59:46" if t["clock_24h"] else "07:59:46 AM")
        p.fillRect(14, 50, 150, 74, c(0, 14, 9, 150))
        p.setPen(c(0, 255, 140, 60))
        p.drawRect(14, 50, 150, 74)
        mono.setPixelSize(11)
        p.setFont(mono)
        for i, (label, col, val) in enumerate((("SOCKETS", (0, 255, 140), "10"), ("REMOTE", (0, 229, 255), "7"),
                                              ("FLAGGED", (255, 43, 214), "1"), ("NEW REGION", (255, 190, 60), "2"))):
            p.setPen(c(*col))
            p.drawText(22, 67 + i * 16, label)
            p.drawText(140, 67 + i * 16, val)
        # a window
        r = max(0, min(20, int(t["corner_radius"])))
        wx, wy, ww, wh = 180, 26, W - 196, H - 96
        p.setPen(QPen(c(0, 255, 140), 1.2))
        p.setBrush(c(1, 6, 4))
        p.drawRoundedRect(QRectF(wx, wy, ww, wh), r, r)
        p.save()
        p.setClipRect(wx, wy, ww, 22)
        g = QLinearGradient(wx, 0, wx + ww, 0)
        g.setColorAt(0, c(0, 71, 42))
        g.setColorAt(1, c(1, 8, 5))
        p.setBrush(g)
        p.drawRoundedRect(QRectF(wx, wy, ww, wh), r, r)
        p.restore()
        p.setPen(c(0, 255, 140))
        p.drawLine(wx, wy + 22, wx + ww, wy + 22)
        p.setPen(c(220, 255, 240))
        p.drawText(wx + 12, wy + 15, "ASTRO//TERM")
        mono.setPixelSize(12)
        p.setFont(mono)
        p.setPen(c(125, 255, 192))
        p.drawText(wx + 12, wy + 44, "$ opencode --version")
        p.setPen(c(0, 229, 255))
        p.drawText(wx + 12, wy + 62, "tester@astro")
        p.setPen(c(0, 255, 140))
        p.drawText(wx + 12, wy + 80, "normal text in the accent colour")
        p.fillRect(wx + 12, wy + 92, 96, 22, c(2, 26, 16))
        p.setPen(c(0, 255, 140))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(wx + 12, wy + 92, 96, 22)
        p.drawText(QRectF(wx + 12, wy + 92, 96, 22), Qt.AlignmentFlag.AlignCenter, "BUTTON")
        p.fillRect(wx + 118, wy + 92, 96, 22, c(0, 255, 140))
        p.setPen(c(0, 0, 0))
        p.drawText(QRectF(wx + 118, wy + 92, 96, 22), Qt.AlignmentFlag.AlignCenter, "SELECTED")
        # dock
        dy = H - 44
        p.fillRect(0, dy, W, 44, c(0, 9, 6))
        p.fillRect(0, dy, W, 1, c(0, 255, 140, 120))
        dr = max(0, min(16, int(t["dock_radius"])))
        f = QFont(t["dock_font"])
        f.setPixelSize(13)
        f.setBold(bool(t["dock_bold"]))
        p.setFont(f)
        x = 8
        for label, col in (("ASTRO", (0, 255, 140)), (">_ TERM", (0, 255, 140)), ("@ WEB", (0, 255, 140)),
                           ("{} CODE", (0, 255, 140))):
            p.setPen(QPen(c(*col, 170), 1.2))
            p.setBrush(c(*col, 22))
            p.drawRoundedRect(QRectF(x, dy + 8, 78, 28), dr, dr)
            p.setPen(c(*col))
            p.drawText(QRectF(x, dy + 8, 78, 28), Qt.AlignmentFlag.AlignCenter, label)
            x += 84
        p.setPen(QPen(c(255, 43, 214, 200), 1.2))
        p.setBrush(c(255, 43, 214, 30))
        p.drawRoundedRect(QRectF(W - 86, dy + 8, 78, 28), dr, dr)
        p.setPen(c(255, 43, 214))
        p.drawText(QRectF(W - 86, dy + 8, 78, 28), Qt.AlignmentFlag.AlignCenter, "0 POWER")


class Look(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASTRO//LOOK")
        self.theme = palette.load()
        self.swatches = {}
        self.loading = False

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(18)

        left = QVBoxLayout()
        left.addWidget(self.head("THEMES"))
        self.presets = QListWidget()
        self.presets.setFixedWidth(190)
        for pr in palette.PRESETS:
            self.presets.addItem(("  " if pr.get("mode") == "dark" else "  ") + pr["name"].upper()
                                 + ("   (LIGHT)" if pr.get("mode") == "light" else ""))
        self.presets.currentRowChanged.connect(self.pick_preset)
        left.addWidget(self.presets, 1)
        root.addLayout(left)

        mid = QVBoxLayout()
        mid.setSpacing(10)
        mid.addWidget(self.head("COLOURS"))
        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        self.mode = QComboBox()
        self.mode.addItems(["DARK", "LIGHT"])
        self.mode.currentIndexChanged.connect(self.mode_changed)
        grid.addWidget(QLabel("MODE"), 0, 0)
        grid.addWidget(self.mode, 0, 1)
        for i, (key, label) in enumerate(COLOURS, 1):
            b = QPushButton()
            b.setFixedSize(150, 28)
            b.clicked.connect(lambda _, k=key: self.pick_colour(k))
            self.swatches[key] = b
            grid.addWidget(QLabel(label), i, 0)
            grid.addWidget(b, i, 1)
        mid.addLayout(grid)

        mid.addWidget(self.rule())
        mid.addWidget(self.head("SHAPE AND TYPE"))
        g2 = QGridLayout()
        g2.setVerticalSpacing(8)
        self.corner = self.slider(0, 20, "corner_radius")
        self.dockr = self.slider(0, 16, "dock_radius")
        self.dock_font = self.combo(DOCK_FONTS, "dock_font")
        self.ui_font = self.combo(UI_FONTS, "ui_font")
        self.bold = self.check("BOLD DOCK LABELS", "dock_bold")
        self.clock = self.check("24-HOUR CLOCK", "clock_24h")
        for i, (label, w) in enumerate((("WINDOW CORNERS", self.corner[0]), ("DOCK BUTTONS", self.dockr[0]),
                                        ("DOCK FONT", self.dock_font), ("TEXT FONT", self.ui_font))):
            g2.addWidget(QLabel(label), i, 0)
            g2.addWidget(w, i, 1)
        g2.addWidget(self.corner[1], 0, 2)
        g2.addWidget(self.dockr[1], 1, 2)
        mid.addLayout(g2)
        mid.addWidget(self.bold)
        mid.addWidget(self.clock)
        mid.addStretch(1)
        root.addLayout(mid)

        right = QVBoxLayout()
        right.addWidget(self.head("PREVIEW"))
        self.preview = Preview()
        right.addWidget(self.preview, 1)
        self.note = QLabel("APPLY reloads the desktop. Open terminals and the browser pick it up when restarted.")
        self.note.setWordWrap(True)
        right.addWidget(self.note)
        row = QHBoxLayout()
        reset = QPushButton("RESET TO DEFAULT")
        apply_ = QPushButton("APPLY")
        apply_.setDefault(True)
        close = QPushButton("CLOSE")
        reset.clicked.connect(self.reset)
        apply_.clicked.connect(self.apply)
        close.clicked.connect(self.close)
        row.addWidget(reset)
        row.addStretch(1)
        row.addWidget(apply_)
        row.addWidget(close)
        right.addLayout(row)
        root.addLayout(right, 1)
        self.show_theme()
        # highlight the saved theme in the list without that counting as "the user picked a preset"
        self.loading = True
        names = [pr["name"] for pr in palette.PRESETS]
        self.presets.setCurrentRow(names.index(self.theme["name"]) if self.theme["name"] in names else -1)
        self.loading = False
        apply_.setFocus()

    # ---------------------------------------------------------------- small builders
    def head(self, text):
        lab = QLabel(text)
        lab.setStyleSheet("font-weight: bold; letter-spacing: 2px;")
        return lab

    def rule(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    def slider(self, lo, hi, key):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setFixedWidth(150)
        val = QLabel()
        val.setFixedWidth(40)
        s.valueChanged.connect(lambda v: (val.setText(f"{v} px"), self.changed(key, v)))
        return s, val

    def combo(self, items, key):
        c = QComboBox()
        c.addItems(items)
        c.setFixedWidth(150)
        c.currentTextChanged.connect(lambda v: self.changed(key, v))
        return c

    def check(self, text, key):
        c = QCheckBox(text)
        c.toggled.connect(lambda v: self.changed(key, bool(v)))
        return c

    # ---------------------------------------------------------------- state
    def show_theme(self):
        """Push self.theme into every control."""
        self.loading = True
        t = self.theme
        self.mode.setCurrentIndex(1 if t["mode"] == "light" else 0)
        for key, b in self.swatches.items():
            r, g, bl = palette.parse(t[key])
            fg = "#000000" if (r * 299 + g * 587 + bl * 114) / 1000 > 140 else "#ffffff"
            b.setText(t[key].upper())
            b.setStyleSheet(f"QPushButton {{ background-color: {t[key]}; color: {fg}; border: 1px solid {fg}; }}")
        self.corner[0].setValue(int(t["corner_radius"]))
        self.corner[1].setText(f"{int(t['corner_radius'])} px")
        self.dockr[0].setValue(int(t["dock_radius"]))
        self.dockr[1].setText(f"{int(t['dock_radius'])} px")
        for combo, key in ((self.dock_font, "dock_font"), (self.ui_font, "ui_font")):
            if combo.findText(t[key]) < 0:
                combo.addItem(t[key])
            combo.setCurrentText(t[key])
        self.bold.setChecked(bool(t["dock_bold"]))
        self.clock.setChecked(bool(t["clock_24h"]))
        self.loading = False
        self.preview.set_theme(t)

    def changed(self, key, value):
        if self.loading:
            return
        self.theme[key] = value
        self.preview.set_theme(self.theme)

    def pick_preset(self, row):
        if row < 0 or self.loading or not self.presets.hasFocus():
            return
        keep = {k: self.theme[k] for k in ("corner_radius", "dock_radius", "dock_font", "dock_bold", "ui_font", "clock_24h")}
        self.theme = dict(palette.DEFAULT)
        self.theme.update(keep)
        self.theme.update(palette.PRESETS[row])
        self.show_theme()

    def mode_changed(self, idx):
        if self.loading:
            return
        flip_mode(self.theme, "light" if idx == 1 else "dark")
        self.theme["name"] = "Custom"
        self.show_theme()

    def pick_colour(self, key):
        col = QColorDialog.getColor(QColor(self.theme[key]), self, "ASTRO//LOOK")
        if col.isValid():
            self.theme[key] = col.name()
            self.theme["name"] = "Custom"
            self.show_theme()

    def reset(self):
        self.theme = dict(palette.DEFAULT)
        self.show_theme()

    def apply(self):
        palette.save(self.theme)
        self.note.setText("Applying...")
        self.repaint()
        subprocess.run([os.path.join(ROOT, "astroctl"), "theme", "apply"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # start again so this window wears the new theme too
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])


def main():
    app = make_app(sys.argv)
    w = Look()
    w.resize(1010, 520)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
