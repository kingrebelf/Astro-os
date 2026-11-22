#!/usr/bin/env python3
"""Trim OpenWhispr's floating overlay windows while ASTRO//OS is on.

Without a compositor their transparent parts show as black boxes, so the
mic button is cut down to its circle and the dictation pill is hidden
(ECHO takes its place).   overlay.py apply | reset
"""
import ctypes
import math
import sys
from ctypes import POINTER, Structure, byref, c_int, c_short, c_uint, c_ulong, c_ushort, c_void_p

from common import X11


class XRect(Structure):
    _fields_ = [("x", c_short), ("y", c_short), ("w", c_ushort), ("h", c_ushort)]


_ext = ctypes.CDLL("libXext.so.6")
_ext.XShapeCombineRectangles.argtypes = [c_void_p, c_ulong, c_int, c_int, c_int, POINTER(XRect),
                                         c_int, c_int, c_int]
_ext.XShapeCombineMask.argtypes = [c_void_p, c_ulong, c_int, c_int, c_int, c_ulong, c_int]


def circle(cx, cy, r):
    rects = []
    for dy in range(-r, r + 1):
        half = int(math.sqrt(r * r - dy * dy))
        rects.append(XRect(cx - half, cy + dy, half * 2, 1))
    return rects


def windows(x):
    x.x.XQueryTree.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                               POINTER(POINTER(c_ulong)), POINTER(c_uint)]
    r, par, kids, n = c_ulong(), c_ulong(), POINTER(c_ulong)(), c_uint()
    if not x.x.XQueryTree(x.d, x.root, byref(r), byref(par), byref(kids), byref(n)):
        return
    ids = [kids[i] for i in range(n.value)]
    if n.value:
        x.x.XFree(kids)
    for w in ids:
        cls = x.get_prop(w, "WM_CLASS")
        if not isinstance(cls, bytes) or b"whispr" not in cls.lower():
            continue
        name = x.get_prop(w, "_NET_WM_NAME") or x.get_prop(w, "WM_NAME") or b""
        yield w, name.decode("utf-8", "replace") if isinstance(name, bytes) else ""


def run(x, reset=False):
    for w, name in windows(x):
        if name not in ("Voice Recorder", "OpenWhispr"):
            continue
        if reset:
            _ext.XShapeCombineMask(x.d, w, 0, 0, 0, 0, 0)
        elif name == "Voice Recorder":
            rects = circle(176, 88, 23)
            arr = (XRect * len(rects))(*rects)
            _ext.XShapeCombineRectangles(x.d, w, 0, 0, 0, arr, len(rects), 0, 0)
        else:
            _ext.XShapeCombineRectangles(x.d, w, 0, 0, 0, None, 0, 0, 0)
    x.x.XFlush(x.d)


if __name__ == "__main__":
    run(X11(), reset=len(sys.argv) > 1 and sys.argv[1] == "reset")
