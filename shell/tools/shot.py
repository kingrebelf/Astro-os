#!/usr/bin/env python3
import sys
from PyQt6.QtGui import QGuiApplication
app = QGuiApplication(sys.argv)
pm = app.primaryScreen().grabWindow(0)
if len(sys.argv) > 2:
    pm = pm.scaledToWidth(int(sys.argv[2]))
pm.save(sys.argv[1])
