"""Shared bits for ASTRO//OS: palette, glyph atlas, X11 helpers, system stats."""
import ctypes
import os
import random
import time
from ctypes import (POINTER, Structure, byref, c_char_p, c_int, c_long,
                    c_ubyte, c_uint, c_ulong, c_void_p, cast)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap

HOME = os.path.expanduser("~")
ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "astro-os")

# ---------------------------------------------------------------- palette
BG = QColor(1, 6, 4)
GREEN = QColor(0, 255, 140)
GREEN_DIM = QColor(0, 140, 80)
GREEN_DARK = QColor(0, 60, 36)
CYAN = QColor(0, 229, 255)
MAGENTA = QColor(255, 43, 214)
AMBER = QColor(255, 190, 60)
WHITE = QColor(215, 255, 235)

UI_FONT = "Ubuntu Mono"
GLYPH_FONT = "Noto Sans Mono CJK JP"

KATAKANA = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
GLYPHS = KATAKANA + "0123456789" + "Z:.=*+-<>|"
SCRAMBLE = "ABCDEF0123456789#%&@$/\\<>[]{}=+*"


def col(c, a=255):
    c = QColor(c)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def font(size, bold=False, family=UI_FONT, spacing=0.0):
    f = QFont(family)
    f.setPixelSize(int(size))
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def scramble(text, progress, seed=0):
    """Decode effect: characters lock in left to right as progress goes 0..1."""
    n = len(text)
    locked = int(progress * (n + 1))
    rnd = random.Random(seed + int(time.time() * 18))
    out = []
    for i, ch in enumerate(text):
        if i < locked or ch == " ":
            out.append(ch)
        else:
            out.append(rnd.choice(SCRAMBLE))
    return "".join(out)


class GlyphAtlas:
    """Pre-rendered glyph pixmaps in N brightness levels (fast drawPixmap)."""

    def __init__(self, px, levels=8, hue=GREEN, glyphs=GLYPHS):
        self.px = px
        self.levels = levels
        self.glyphs = glyphs
        f = font(px, True, GLYPH_FONT)
        fm = QFontMetrics(f)
        self.w = max(fm.horizontalAdvance("ｱ"), fm.horizontalAdvance("0")) + 2
        self.h = fm.height()
        self.maps = []
        for lv in range(levels):
            t = lv / (levels - 1)
            if t < 0.8:
                c = mix(QColor(0, 0, 0), hue, 0.12 + t / 0.8 * 0.88)
            else:
                c = mix(hue, QColor(235, 255, 245), (t - 0.8) / 0.2)
            row = []
            for ch in glyphs:
                pm = QPixmap(self.w, self.h)
                pm.fill(Qt.GlobalColor.transparent)
                p = QPainter(pm)
                p.setFont(f)
                p.setPen(c)
                p.drawText(0, 0, self.w, self.h,
                           Qt.AlignmentFlag.AlignCenter, ch)
                p.end()
                row.append(pm)
            self.maps.append(row)
        self.n = len(glyphs)

    def get(self, idx, level):
        level = 0 if level < 0 else (self.levels - 1 if level >= self.levels else level)
        return self.maps[level][idx % self.n]


def hud_panel(p, x, y, w, h, title=None, alpha=1.0, accent=GREEN):
    """Translucent panel with corner brackets and a title tab."""
    p.fillRect(int(x), int(y), int(w), int(h), col(QColor(0, 14, 9), 150 * alpha))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(col(accent, 55 * alpha))
    p.drawRect(int(x), int(y), int(w), int(h))
    p.setPen(col(accent, 230 * alpha))
    L = 12
    x0, y0, x1, y1 = int(x), int(y), int(x + w), int(y + h)
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        p.drawLine(cx, cy, cx + dx * L, cy)
        p.drawLine(cx, cy, cx, cy + dy * L)
    if title:
        p.setFont(font(12, True, spacing=2))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(title) + 16
        p.fillRect(x0 + 14, y0 - 8, tw, 16, col(QColor(0, 20, 12), 255 * alpha))
        p.setPen(col(accent, 255 * alpha))
        p.drawText(x0 + 22, y0 + 4, title)


# ---------------------------------------------------------------- X11 helpers
class _ClientMessage(Structure):
    _fields_ = [("type", c_int), ("serial", c_ulong), ("send_event", c_int),
                ("display", c_void_p), ("window", c_ulong),
                ("message_type", c_ulong), ("format", c_int),
                ("data", c_long * 5), ("pad", c_long * 12)]


class X11:
    def __init__(self):
        x = ctypes.CDLL("libX11.so.6")
        x.XOpenDisplay.restype = c_void_p
        x.XOpenDisplay.argtypes = [c_char_p]
        x.XDefaultRootWindow.restype = c_ulong
        x.XDefaultRootWindow.argtypes = [c_void_p]
        x.XInternAtom.restype = c_ulong
        x.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
        x.XChangeProperty.argtypes = [c_void_p, c_ulong, c_ulong, c_ulong, c_int,
                                      c_int, c_void_p, c_int]
        x.XGetWindowProperty.argtypes = [c_void_p, c_ulong, c_ulong, c_long, c_long,
                                         c_int, c_ulong, POINTER(c_ulong),
                                         POINTER(c_int), POINTER(c_ulong),
                                         POINTER(c_ulong), POINTER(c_void_p)]
        x.XSendEvent.argtypes = [c_void_p, c_ulong, c_int, c_long, c_void_p]
        x.XFree.argtypes = [c_void_p]
        x.XFlush.argtypes = [c_void_p]
        x.XIconifyWindow.argtypes = [c_void_p, c_ulong, c_int]
        x.XQueryPointer.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong), POINTER(c_int),
                                    POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_uint)]
        x.XQueryTree.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong), POINTER(c_void_p),
                                 POINTER(c_uint)]
        x.XSetErrorHandler.restype = c_void_p
        self._handler = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)(lambda d, e: 0)
        x.XSetErrorHandler(self._handler)
        self.x = x
        self.d = x.XOpenDisplay(None)
        if not self.d:
            raise RuntimeError("cannot open X display")
        self.root = x.XDefaultRootWindow(self.d)
        self._atoms = {}

    def atom(self, name):
        a = self._atoms.get(name)
        if a is None:
            a = self._atoms[name] = self.x.XInternAtom(self.d, name.encode(), 0)
        return a

    def get_prop(self, win, name, length=4096):
        t, f, n, rest, data = c_ulong(), c_int(), c_ulong(), c_ulong(), c_void_p()
        r = self.x.XGetWindowProperty(self.d, win, self.atom(name), 0, length, 0, 0,
                                      byref(t), byref(f), byref(n), byref(rest),
                                      byref(data))
        if r != 0 or not data.value:
            return None
        try:
            if f.value == 32:
                return list(cast(data, POINTER(c_ulong))[:n.value])
            if f.value == 8:
                return ctypes.string_at(data.value, n.value)
            return None
        finally:
            self.x.XFree(data)

    def set_cardinals(self, win, name, values, type_="CARDINAL"):
        arr = (c_ulong * len(values))(*values)
        self.x.XChangeProperty(self.d, win, self.atom(name), self.atom(type_), 32, 0,
                               arr, len(values))
        self.x.XFlush(self.d)

    def set_strut_bottom(self, win, height, screen_w):
        self.set_cardinals(win, "_NET_WM_STRUT", [0, 0, 0, height])
        self.set_cardinals(win, "_NET_WM_STRUT_PARTIAL",
                           [0, 0, 0, height, 0, 0, 0, 0, 0, 0, 0, screen_w - 1])

    def all_desktops(self, win):
        self.set_cardinals(win, "_NET_WM_DESKTOP", [0xFFFFFFFF])

    def _message(self, win, name, *data):
        ev = _ClientMessage()
        ev.type = 33
        ev.send_event = 1
        ev.display = self.d
        ev.window = win
        ev.message_type = self.atom(name)
        ev.format = 32
        for i, v in enumerate(data):
            ev.data[i] = v
        self.x.XSendEvent(self.d, self.root, 0, (1 << 20) | (1 << 19), byref(ev))
        self.x.XFlush(self.d)

    def activate(self, win):
        self._message(win, "_NET_ACTIVE_WINDOW", 2, 0, 0)

    def close(self, win):
        self._message(win, "_NET_CLOSE_WINDOW", 0, 2)

    def iconify(self, win):
        self.x.XIconifyWindow(self.d, win, 0)
        self.x.XFlush(self.d)

    def pointer(self):
        """(top-level window under the pointer, button/modifier mask)."""
        r, ch = c_ulong(), c_ulong()
        rx, ry, wx, wy, mask = c_int(), c_int(), c_int(), c_int(), c_uint()
        self.x.XQueryPointer(self.d, self.root, byref(r), byref(ch), byref(rx), byref(ry),
                             byref(wx), byref(wy), byref(mask))
        return ch.value, mask.value

    def parent(self, win):
        r, par, kids, n = c_ulong(), c_ulong(), c_void_p(), c_uint()
        if self.x.XQueryTree(self.d, win, byref(r), byref(par), byref(kids), byref(n)):
            if kids.value:
                self.x.XFree(kids)
            return par.value
        return 0

    def active(self):
        v = self.get_prop(self.root, "_NET_ACTIVE_WINDOW")
        return v[0] if v else 0

    def clients(self):
        """[(window id, title, wm_class)] for normal task-bar windows."""
        out = []
        skip_tb = self.atom("_NET_WM_STATE_SKIP_TASKBAR")
        bad_types = {self.atom("_NET_WM_WINDOW_TYPE_" + t)
                     for t in ("DESKTOP", "DOCK", "SPLASH", "NOTIFICATION", "TOOLBAR", "MENU")}
        for w in self.get_prop(self.root, "_NET_CLIENT_LIST") or []:
            state = self.get_prop(w, "_NET_WM_STATE") or []
            if skip_tb in state:
                continue
            types = self.get_prop(w, "_NET_WM_WINDOW_TYPE") or []
            if any(t in bad_types for t in types):
                continue
            name = self.get_prop(w, "_NET_WM_NAME") or self.get_prop(w, "WM_NAME") or b""
            cls = self.get_prop(w, "WM_CLASS") or b""
            if isinstance(name, list) or isinstance(cls, list):
                continue
            cls = cls.split(b"\0")[0].decode("utf-8", "replace")
            out.append((w, name.decode("utf-8", "replace"), cls))
        return out


# ---------------------------------------------------------------- system stats
class Stats:
    def __init__(self, iface=None):
        self.prev_cpu = {}
        self.cores = []
        self.total = 0.0
        self.iface = iface or self._default_iface()
        self.prev_net = None
        self.rx = self.tx = 0.0
        self.mem_used = self.mem_total = 1.0
        self.update()

    @staticmethod
    def _default_iface():
        try:
            with open("/proc/net/route") as f:
                for line in f.readlines()[1:]:
                    p = line.split()
                    if p[1] == "00000000":
                        return p[0]
        except OSError:
            pass
        return "lo"

    def update(self):
        cores = []
        try:
            with open("/proc/stat") as f:
                for line in f:
                    if not line.startswith("cpu"):
                        break
                    p = line.split()
                    vals = list(map(int, p[1:9]))
                    idle = vals[3] + vals[4]
                    tot = sum(vals)
                    pi, pt = self.prev_cpu.get(p[0], (idle, tot))
                    dt = tot - pt
                    use = 0.0 if dt <= 0 else 1.0 - (idle - pi) / dt
                    self.prev_cpu[p[0]] = (idle, tot)
                    if p[0] == "cpu":
                        self.total = use
                    else:
                        cores.append(use)
            self.cores = cores
            mem = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":")
                    mem[k] = int(v.split()[0])
                    if len(mem) > 6:
                        break
            self.mem_total = mem["MemTotal"] / 1048576
            self.mem_used = (mem["MemTotal"] - mem["MemAvailable"]) / 1048576
            now = time.time()
            with open("/proc/net/dev") as f:
                for line in f:
                    if line.strip().startswith(self.iface + ":"):
                        p = line.split(":")[1].split()
                        rx, tx = int(p[0]), int(p[8])
                        if self.prev_net:
                            t0, r0, x0 = self.prev_net
                            d = max(now - t0, 1e-3)
                            self.rx, self.tx = (rx - r0) / d, (tx - x0) / d
                        self.prev_net = (now, rx, tx)
            with open("/proc/loadavg") as f:
                self.load = f.read().split()[0]
            with open("/proc/uptime") as f:
                self.uptime = float(f.read().split()[0])
        except (OSError, KeyError, ValueError):
            pass


def human_rate(b):
    for unit in ("B", "K", "M", "G"):
        if b < 1024:
            return f"{b:5.1f}{unit}/s"
        b /= 1024
    return f"{b:5.1f}T/s"


def local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"
