#!/usr/bin/env python3
"""Tap a key via XTest: key.py F8 [hold_seconds]"""
import ctypes, sys, time
x = ctypes.CDLL("libX11.so.6"); t = ctypes.CDLL("libXtst.so.6")
x.XOpenDisplay.restype = ctypes.c_void_p
x.XStringToKeysym.restype = ctypes.c_ulong
x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
t.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
x.XFlush.argtypes = [ctypes.c_void_p]
d = x.XOpenDisplay(None)
kc = x.XKeysymToKeycode(d, x.XStringToKeysym(sys.argv[1].encode()))
t.XTestFakeKeyEvent(d, kc, 1, 0); x.XFlush(d)
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 0.05)
t.XTestFakeKeyEvent(d, kc, 0, 0); x.XFlush(d)
