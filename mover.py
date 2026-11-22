#!/usr/bin/env python3
"""Outline window dragging for ASTRO//OS.

Moving a whole window every mouse step saturates the display server on the
onboard video chip, which leaves trails on screen. Instead, the title-bar drag
binding in Openbox sends this daemon SIGUSR1; a thin neon frame then follows
the pointer and the real window is moved once, on release.
"""
import ctypes
import signal
import threading
import time
from ctypes import POINTER, Structure, byref, c_int, c_long, c_uint, c_ulong, c_void_p

from common import X11

GREEN = 0x00FF8C
CYAN = 0x00E5FF
T = 2            # outline thickness


class SetAttrs(Structure):
    _fields_ = [("background_pixmap", c_ulong), ("background_pixel", c_ulong),
                ("border_pixmap", c_ulong), ("border_pixel", c_ulong),
                ("bit_gravity", c_int), ("win_gravity", c_int), ("backing_store", c_int),
                ("backing_planes", c_ulong), ("backing_pixel", c_ulong), ("save_under", c_int),
                ("event_mask", c_long), ("do_not_propagate_mask", c_long),
                ("override_redirect", c_int), ("colormap", c_ulong), ("cursor", c_ulong)]


class Mover:
    def __init__(self):
        self.x = X11()
        x, d = self.x.x, self.x.d
        x.XCreateSimpleWindow.restype = c_ulong
        x.XCreateSimpleWindow.argtypes = [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint, c_uint,
                                          c_ulong, c_ulong]
        x.XChangeWindowAttributes.argtypes = [c_void_p, c_ulong, c_ulong, POINTER(SetAttrs)]
        x.XMoveResizeWindow.argtypes = [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint]
        x.XMapRaised.argtypes = [c_void_p, c_ulong]
        x.XUnmapWindow.argtypes = [c_void_p, c_ulong]
        x.XGetGeometry.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_int), POINTER(c_int),
                                   POINTER(c_uint), POINTER(c_uint), POINTER(c_uint), POINTER(c_uint)]
        x.XDisplayWidth.argtypes = [c_void_p, c_int]
        x.XDisplayHeight.argtypes = [c_void_p, c_int]
        self.sw, self.sh = x.XDisplayWidth(d, 0), x.XDisplayHeight(d, 0)
        attrs = SetAttrs()
        attrs.override_redirect = 1
        self.bars = []
        for i in range(8):                   # 4 edges + 4 brighter corner ticks
            w = x.XCreateSimpleWindow(d, self.x.root, -50, -50, 4, 4, 0, 0, GREEN if i < 4 else CYAN)
            x.XChangeWindowAttributes(d, w, 1 << 9, byref(attrs))
            self.bars.append(w)
        x.XFlush(d)
        self.go = threading.Event()
        signal.signal(signal.SIGUSR1, lambda *_: self.go.set())

    def geometry(self, win):
        r = c_ulong()
        gx, gy, w, h, b, dep = c_int(), c_int(), c_uint(), c_uint(), c_uint(), c_uint()
        if not self.x.x.XGetGeometry(self.x.d, win, byref(r), byref(gx), byref(gy), byref(w), byref(h),
                                     byref(b), byref(dep)):
            return None
        return gx.value, gy.value, w.value + 2 * b.value, h.value + 2 * b.value

    def frame_of(self, win):
        """Topmost ancestor below the root: the window manager's frame."""
        cur = win
        for _ in range(8):
            par = self.x.parent(cur)
            if not par or par == self.x.root:
                return cur
            cur = par
        return cur

    def place(self, fx, fy, w, h):
        x, d, b = self.x.x, self.x.d, self.bars
        L = 18
        for win, (a, c, e, f) in zip(b, ((fx, fy, w, T), (fx, fy + h - T, w, T), (fx, fy, T, h), (fx + w - T, fy, T, h),
                                         (fx, fy, L, 4), (fx + w - L, fy, L, 4),
                                         (fx, fy + h - 4, L, 4), (fx + w - L, fy + h - 4, L, 4))):
            x.XMoveResizeWindow(d, win, a, c, e, f)

    def drag(self):
        x, d = self.x.x, self.x.d
        child, mask = self.x.pointer()
        if not mask & 0x100:
            return
        win = self.x.active()
        if not win:
            return
        state = self.x.get_prop(win, "_NET_WM_STATE") or []
        if self.x.atom("_NET_WM_STATE_FULLSCREEN") in state:
            return
        frame = self.frame_of(win)
        if child and child != frame:
            return                           # pointer is not on the active window's frame
        geo = self.geometry(frame)
        if not geo:
            return
        fx, fy, w, h = geo
        px0, py0 = self.pointer_xy()
        self.place(fx, fy, w, h)
        for b in self.bars:
            x.XMapRaised(d, b)
        x.XFlush(d)
        nx, ny = fx, fy
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(1 / 60)
            _, mask = self.x.pointer()
            px, py = self.pointer_xy()
            tx = fx + px - px0
            ty = max(0, min(self.sh - 80, fy + py - py0))
            if (tx, ty) != (nx, ny):
                nx, ny = tx, ty
                self.place(nx, ny, w, h)
                x.XFlush(d)
            if not mask & 0x100:
                break
        for b in self.bars:
            x.XUnmapWindow(d, b)
        if (nx, ny) != (fx, fy):
            maxed = (self.x.atom("_NET_WM_STATE_MAXIMIZED_VERT") in state
                     or self.x.atom("_NET_WM_STATE_MAXIMIZED_HORZ") in state)
            if maxed:                        # dragging a maximised window restores it first
                self.x._message(win, "_NET_WM_STATE", 0, self.x.atom("_NET_WM_STATE_MAXIMIZED_VERT"),
                                self.x.atom("_NET_WM_STATE_MAXIMIZED_HORZ"), 2)
            # gravity NorthWest (1) | x | y | source=pager: coordinates are the frame's top-left
            self.x._message(win, "_NET_MOVERESIZE_WINDOW", 1 | (1 << 8) | (1 << 9) | (2 << 12), nx, ny)
        x.XFlush(d)

    def pointer_xy(self):
        r, ch = c_ulong(), c_ulong()
        rx, ry, wx, wy, mask = c_int(), c_int(), c_int(), c_int(), c_uint()
        self.x.x.XQueryPointer(self.x.d, self.x.root, byref(r), byref(ch), byref(rx), byref(ry),
                               byref(wx), byref(wy), byref(mask))
        return rx.value, ry.value

    def run(self):
        while True:
            self.go.wait()
            self.go.clear()
            try:
                self.drag()
            except Exception as e:           # never die: dragging depends on this process
                print("drag failed:", e, flush=True)


if __name__ == "__main__":
    Mover().run()
