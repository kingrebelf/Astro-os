#!/usr/bin/env python3
"""Drag a window around at a given pointer event rate and grab a frame mid-drag: dragtest.py TITLE RATE OUT.png"""
import ctypes, math, re, subprocess, sys, time
title, rate, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
x = ctypes.CDLL("libX11.so.6"); t = ctypes.CDLL("libXtst.so.6")
x.XOpenDisplay.restype = ctypes.c_void_p
d = x.XOpenDisplay(None)
t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
x.XFlush.argtypes = [ctypes.c_void_p]
geo = subprocess.run(["xwininfo", "-name", title], capture_output=True, text=True).stdout
ax = int(re.search(r"Absolute upper-left X:\s+(-?\d+)", geo).group(1))
ay = int(re.search(r"Absolute upper-left Y:\s+(-?\d+)", geo).group(1))
sx, sy = ax + 300, ay - 12
t.XTestFakeMotionEvent(d, -1, sx, sy, 0); x.XFlush(d); time.sleep(.2)
t.XTestFakeButtonEvent(d, 1, 1, 0); x.XFlush(d); time.sleep(.1)
t0 = time.time(); shot = None
while time.time() - t0 < 4:
    a = (time.time() - t0) * 2.5
    t.XTestFakeMotionEvent(d, -1, int(sx + 130 * math.sin(a)), int(sy + 100 * math.sin(a * 1.3)), 0); x.XFlush(d)
    time.sleep(1 / rate)
    if shot is None and time.time() - t0 > 2.5:
        shot = subprocess.Popen([sys.executable, "/home/astro/astro-os/tools/shot.py", out])
t.XTestFakeMotionEvent(d, -1, sx, sy, 0); x.XFlush(d); time.sleep(.1)
t.XTestFakeButtonEvent(d, 1, 0, 0); x.XFlush(d)
shot.wait()
