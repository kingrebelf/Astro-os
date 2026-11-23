#!/usr/bin/env python3
"""Simulated mouse click: click.py X Y [count] [button]"""
import ctypes, sys, time
x = ctypes.CDLL("libX11.so.6"); t = ctypes.CDLL("libXtst.so.6")
x.XOpenDisplay.restype = ctypes.c_void_p
d = x.XOpenDisplay(None)
t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
x.XFlush.argtypes = [ctypes.c_void_p]
X, Y = int(sys.argv[1]), int(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
b = int(sys.argv[4]) if len(sys.argv) > 4 else 1
t.XTestFakeMotionEvent(d, -1, X, Y, 0); x.XFlush(d); time.sleep(0.15)
for _ in range(n):
    t.XTestFakeButtonEvent(d, b, 1, 0); x.XFlush(d); time.sleep(0.04)
    t.XTestFakeButtonEvent(d, b, 0, 0); x.XFlush(d); time.sleep(0.08)
