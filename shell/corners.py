#!/usr/bin/env python3
"""Rounded window corners for ASTRO//OS, without a compositor.

Openbox only draws square frames, and a compositor costs too much on a server's
onboard video chip. So this small daemon does it with the X Shape extension:
every decorated window's frame gets a rounded outline cut into it, and four tiny
child windows are laid over the corners to redraw the border line as an arc.

Pure Xlib through ctypes (no Qt), so it stays at a few MB and sleeps until a
window is opened, resized, maximised or focused.

  ASTRO_CORNER_RADIUS   corner radius in pixels, overriding the theme setting (0 turns it off)
"""
import ctypes
import math
import os
import select
import signal
import sys
from ctypes import (CFUNCTYPE, POINTER, Structure, byref, c_char_p, c_int, c_long, c_short,
                    c_ubyte, c_uint, c_ulong, c_ushort, c_void_p, cast)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette

PAL = palette.current()
RADIUS = max(0, min(24, int(os.environ.get("ASTRO_CORNER_RADIUS", PAL.theme["corner_radius"]))))
LINE = 1.6                 # thickness of the redrawn border arc
ACTIVE = PAL.int(0x00FF8C)          # must match window.active.border.color in theme/build.py
INACTIVE = PAL.int(0x0B4D33)

ShapeBounding, ShapeInput, ShapeSet = 0, 2, 0
SubstructureNotifyMask, PropertyChangeMask = 1 << 19, 1 << 22
CWWinGravity, CWOverrideRedirect, CWBackPixel = 1 << 5, 1 << 9, 1 << 1
GRAVITY = (1, 3, 7, 9)     # NorthWest, NorthEast, SouthWest, SouthEast


class XRectangle(Structure):
    _fields_ = [("x", c_short), ("y", c_short), ("width", c_ushort), ("height", c_ushort)]


class SetAttrs(Structure):
    _fields_ = [("background_pixmap", c_ulong), ("background_pixel", c_ulong),
                ("border_pixmap", c_ulong), ("border_pixel", c_ulong),
                ("bit_gravity", c_int), ("win_gravity", c_int), ("backing_store", c_int),
                ("backing_planes", c_ulong), ("backing_pixel", c_ulong), ("save_under", c_int),
                ("event_mask", c_long), ("do_not_propagate_mask", c_long),
                ("override_redirect", c_int), ("colormap", c_ulong), ("cursor", c_ulong)]


class ShapeEvent(Structure):
    _fields_ = [("type", c_int), ("serial", c_ulong), ("send_event", c_int), ("display", c_void_p),
                ("window", c_ulong), ("kind", c_int), ("x", c_int), ("y", c_int),
                ("width", c_uint), ("height", c_uint), ("time", c_ulong), ("shaped", c_int)]


def insets(r):
    """How far each of the top r rows is pulled in from the side to trace a quarter circle."""
    out = []
    for y in range(r):
        dy = r - y - 0.5
        out.append(int(round(r - math.sqrt(max(0.0, r * r - dy * dy)))))
    return out


def arc_rects(r, corner):
    """Pixels of the border arc inside an r x r box, for corner 0..3 (NW, NE, SW, SE)."""
    rects = []
    for y in range(r):
        run = None
        for x in range(r + 1):
            d = math.hypot(r - x - 0.5, r - y - 0.5)
            on = x < r and r - LINE < d <= r + 0.35
            if on and run is None:
                run = x
            elif not on and run is not None:
                rects.append((run, y, x - run))
                run = None
    flip_x, flip_y = corner in (1, 3), corner in (2, 3)
    out = (XRectangle * len(rects))()
    for i, (x, y, w) in enumerate(rects):
        out[i] = XRectangle(r - x - w if flip_x else x, r - 1 - y if flip_y else y, w, 1)
    return out


class Corners:
    def __init__(self):
        x = self.x = ctypes.CDLL("libX11.so.6")
        self.xext = ctypes.CDLL("libXext.so.6")
        x.XOpenDisplay.restype = c_void_p
        x.XOpenDisplay.argtypes = [c_char_p]
        self.d = x.XOpenDisplay(None)
        if not self.d:
            sys.exit("corners: cannot open display")
        d = self.d
        x.XDefaultRootWindow.restype = c_ulong
        x.XDefaultRootWindow.argtypes = [c_void_p]
        x.XInternAtom.restype = c_ulong
        x.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
        x.XGetWindowProperty.argtypes = [c_void_p, c_ulong, c_ulong, c_long, c_long, c_int, c_ulong,
                                         POINTER(c_ulong), POINTER(c_int), POINTER(c_ulong),
                                         POINTER(c_ulong), POINTER(c_void_p)]
        x.XQueryTree.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                                 POINTER(c_void_p), POINTER(c_uint)]
        x.XGetGeometry.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_int), POINTER(c_int),
                                   POINTER(c_uint), POINTER(c_uint), POINTER(c_uint), POINTER(c_uint)]
        x.XCreateWindow.restype = c_ulong
        x.XCreateWindow.argtypes = [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint, c_uint, c_int,
                                    c_uint, c_void_p, c_ulong, POINTER(SetAttrs)]
        x.XSetWindowBackground.argtypes = [c_void_p, c_ulong, c_ulong]
        x.XClearWindow.argtypes = [c_void_p, c_ulong]
        x.XMoveWindow.argtypes = [c_void_p, c_ulong, c_int, c_int]
        for fn in (x.XMapRaised, x.XUnmapWindow, x.XDestroyWindow, x.XRaiseWindow):
            fn.argtypes = [c_void_p, c_ulong]
        x.XSelectInput.argtypes = [c_void_p, c_ulong, c_long]
        x.XNextEvent.argtypes = [c_void_p, c_void_p]
        x.XPending.argtypes = [c_void_p]
        x.XFlush.argtypes = [c_void_p]
        x.XSync.argtypes = [c_void_p, c_int]
        x.XFree.argtypes = [c_void_p]
        x.XConnectionNumber.argtypes = [c_void_p]
        e = self.xext
        e.XShapeQueryExtension.argtypes = [c_void_p, POINTER(c_int), POINTER(c_int)]
        e.XShapeCombineRectangles.argtypes = [c_void_p, c_ulong, c_int, c_int, c_int,
                                              POINTER(XRectangle), c_int, c_int, c_int]
        e.XShapeCombineMask.argtypes = [c_void_p, c_ulong, c_int, c_int, c_int, c_ulong, c_int]
        e.XShapeSelectInput.argtypes = [c_void_p, c_ulong, c_ulong]

        ev, err = c_int(), c_int()
        if not e.XShapeQueryExtension(d, byref(ev), byref(err)):
            sys.exit("corners: this X server has no Shape extension")
        self.shape_event = ev.value

        # windows come and go under us all the time: a BadWindow must never kill the daemon
        self._handler = CFUNCTYPE(c_int, c_void_p, c_void_p)(lambda *_: 0)
        x.XSetErrorHandler(self._handler)

        self.root = x.XDefaultRootWindow(d)
        self.atoms = {}
        self.inset = insets(RADIUS)
        self.arcs = [arc_rects(RADIUS, i) for i in range(4)]
        self.frames = {}          # frame window -> state dict
        x.XSelectInput(d, self.root, SubstructureNotifyMask | PropertyChangeMask)
        self.fd = x.XConnectionNumber(d)

    # ---------------------------------------------------------------- X helpers
    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = self.x.XInternAtom(self.d, name.encode(), 0)
        return self.atoms[name]

    def prop(self, win, name):
        t, f, n, left, data = c_ulong(), c_int(), c_ulong(), c_ulong(), c_void_p()
        if self.x.XGetWindowProperty(self.d, win, self.atom(name), 0, 4096, 0, 0, byref(t), byref(f),
                                     byref(n), byref(left), byref(data)) != 0 or not data:
            return []
        try:
            if f.value != 32:
                return []
            return list(cast(data, POINTER(c_ulong))[:n.value])
        finally:
            self.x.XFree(data)

    def frame_of(self, win):
        """The top-level window Openbox wrapped this client in (the child of the root)."""
        for _ in range(8):
            root, parent, kids, n = c_ulong(), c_ulong(), c_void_p(), c_uint()
            if not self.x.XQueryTree(self.d, win, byref(root), byref(parent), byref(kids), byref(n)):
                return 0
            if kids:
                self.x.XFree(kids)
            if parent.value in (0, root.value):
                return win
            win = parent.value
        return 0

    def size(self, win):
        r = c_ulong()
        gx, gy, w, h, b, dep = c_int(), c_int(), c_uint(), c_uint(), c_uint(), c_uint()
        if not self.x.XGetGeometry(self.d, win, byref(r), byref(gx), byref(gy), byref(w), byref(h),
                                   byref(b), byref(dep)):
            return 0, 0
        return w.value, h.value

    # ---------------------------------------------------------------- shaping
    def round_frame(self, frame, w, h):
        r = min(RADIUS, w // 2, h // 2)
        ins = self.inset if r == RADIUS else insets(r)
        rects = (XRectangle * (2 * r + 1))()
        for y in range(r):
            rects[y] = XRectangle(ins[y], y, w - 2 * ins[y], 1)
            rects[r + y] = XRectangle(ins[y], h - 1 - y, w - 2 * ins[y], 1)
        rects[2 * r] = XRectangle(0, r, w, max(0, h - 2 * r))
        self.xext.XShapeCombineRectangles(self.d, frame, ShapeBounding, 0, 0, rects, len(rects), ShapeSet, 0)

    def make_arcs(self, frame, w, h, color):
        r = RADIUS
        wins = []
        for i, (px, py) in enumerate(((0, 0), (w - r, 0), (0, h - r), (w - r, h - r))):
            a = SetAttrs()
            a.background_pixel, a.win_gravity, a.override_redirect = color, GRAVITY[i], 1
            win = self.x.XCreateWindow(self.d, frame, px, py, r, r, 0, 0, 1, None,
                                       CWBackPixel | CWWinGravity | CWOverrideRedirect, byref(a))
            arc = self.arcs[i]
            self.xext.XShapeCombineRectangles(self.d, win, ShapeBounding, 0, 0, arc, len(arc), ShapeSet, 0)
            # clicks fall through to the frame, so corner resizing still works
            self.xext.XShapeCombineRectangles(self.d, win, ShapeInput, 0, 0, None, 0, ShapeSet, 0)
            wins.append(win)
        return wins

    def wanted(self, client):
        """Round this client's frame? Only when it has a title bar and is not filling the screen."""
        ext = self.prop(client, "_NET_FRAME_EXTENTS")
        if len(ext) < 4 or ext[2] == 0:
            return False
        st = set(self.prop(client, "_NET_WM_STATE"))
        if self.atom("_NET_WM_STATE_FULLSCREEN") in st:
            return False
        if self.atom("_NET_WM_STATE_MAXIMIZED_VERT") in st and self.atom("_NET_WM_STATE_MAXIMIZED_HORZ") in st:
            return False
        return True

    def rescan(self):
        active = (self.prop(self.root, "_NET_ACTIVE_WINDOW") or [0])[0]
        seen = set()
        for client in self.prop(self.root, "_NET_CLIENT_LIST"):
            frame = self.frame_of(client)
            if not frame or frame == client:
                continue
            seen.add(frame)
            w, h = self.size(frame)
            if w < 2 or h < 2:
                continue
            st = self.frames.get(frame)
            if st is None:
                st = self.frames[frame] = {"size": None, "round": False, "arcs": [], "color": None}
                self.xext.XShapeSelectInput(self.d, frame, 1)     # tell us when Openbox resets the shape
            want = self.wanted(client) and min(w, h) >= 2 * RADIUS + 4
            color = ACTIVE if client == active else INACTIVE
            if want:
                if not st["round"] or st["size"] != (w, h):
                    self.round_frame(frame, w, h)
                if not st["arcs"]:
                    st["arcs"] = self.make_arcs(frame, w, h, color)
                    st["color"] = color
                    for a in st["arcs"]:
                        self.x.XMapRaised(self.d, a)
                elif st["size"] != (w, h) or not st["round"]:
                    r = RADIUS
                    for a, (px, py) in zip(st["arcs"], ((0, 0), (w - r, 0), (0, h - r), (w - r, h - r))):
                        self.x.XMoveWindow(self.d, a, px, py)
                        self.x.XMapRaised(self.d, a)
                if st["color"] != color:
                    st["color"] = color
                    for a in st["arcs"]:
                        self.x.XSetWindowBackground(self.d, a, color)
                        self.x.XClearWindow(self.d, a)
            elif st["round"]:
                self.xext.XShapeCombineMask(self.d, frame, ShapeBounding, 0, 0, 0, ShapeSet)
                for a in st["arcs"]:
                    self.x.XUnmapWindow(self.d, a)
            st["round"], st["size"] = want, (w, h)
        for frame in [f for f in self.frames if f not in seen]:
            del self.frames[frame]            # Openbox destroyed the frame, and our arcs with it
        self.x.XFlush(self.d)

    def clear(self):
        for frame, st in self.frames.items():
            if st["round"]:
                self.xext.XShapeCombineMask(self.d, frame, ShapeBounding, 0, 0, 0, ShapeSet)
            for a in st["arcs"]:
                self.x.XDestroyWindow(self.d, a)
        self.x.XSync(self.d, 0)

    # ---------------------------------------------------------------- loop
    def run(self):
        buf = ctypes.create_string_buffer(192)
        stop = []
        signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
        signal.signal(signal.SIGINT, lambda *_: stop.append(1))
        self.rescan()
        while not stop:
            if not self.x.XPending(self.d):
                try:
                    select.select([self.fd], [], [], 5.0)
                except InterruptedError:
                    continue
            dirty = False
            while self.x.XPending(self.d):
                self.x.XNextEvent(self.d, buf)
                kind = cast(buf, POINTER(c_int))[0]
                if kind == self.shape_event:
                    ev = cast(buf, POINTER(ShapeEvent))[0]
                    st = self.frames.get(ev.window)
                    if st and ev.kind == ShapeBounding and not ev.shaped and st["round"]:
                        st["round"] = False       # Openbox squared it off again (it does on every resize)
                        dirty = True
                else:
                    dirty = True
            if dirty:
                self.rescan()
        self.clear()


if __name__ == "__main__":
    if RADIUS <= 0:
        sys.exit(0)
    Corners().run()
