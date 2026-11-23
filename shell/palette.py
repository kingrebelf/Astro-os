"""ASTRO//OS themes: one small settings file recolours the whole desktop.

Every colour in the shell was written for the original neon-green look. Rather
than rewrite each of them, a theme says where the five anchor colours go
(background, accent, second accent, alert, warning) and remap() moves any
original colour to the matching place in the new palette: a dark green panel
fill becomes a dark (or, in light mode, pale) tint of the new accent, pale
green text becomes the new text colour, and so on.

With no theme file, or the default one, remap() returns its input unchanged,
so the original look is exactly the original code path.

No Qt in here: the window-corner and window-mover daemons import it too.

Theme file: ~/.config/astro-os/theme.json, then /etc/astro-os/theme.json.
"""
import colorsys
import json
import os
import re

USER_FILE = os.path.expanduser("~/.config/astro-os/theme.json")
SYSTEM_FILE = "/etc/astro-os/theme.json"

DEFAULT = {
    "name": "Astro Green",
    "mode": "dark",              # dark | light
    "bg": "#010705",
    "accent": "#00ff8c",
    "accent2": "#00e5ff",
    "alert": "#ff2bd6",
    "warn": "#ffbe3c",
    "text": "#dcfff0",
    "corner_radius": 10,         # window corners, pixels (0 = square)
    "dock_radius": 8,            # dock buttons, pixels (0 = square)
    "dock_font": "Ubuntu",       # Ubuntu | Ubuntu Mono
    "dock_bold": True,
    "ui_font": "Ubuntu Mono",
    "clock_24h": True,
}

PRESETS = [
    DEFAULT,
    {"name": "Ice Blue", "mode": "dark", "bg": "#01050a", "accent": "#3db8ff", "accent2": "#7dffe8",
     "alert": "#ff4f9a", "warn": "#ffc24d", "text": "#e3f3ff"},
    {"name": "Amber Terminal", "mode": "dark", "bg": "#0a0500", "accent": "#ffb000", "accent2": "#ff7a1a",
     "alert": "#ff3d3d", "warn": "#fff06a", "text": "#fff1d6"},
    {"name": "Crimson", "mode": "dark", "bg": "#0a0203", "accent": "#ff3b4e", "accent2": "#ff9a3d",
     "alert": "#d94dff", "warn": "#ffd24d", "text": "#ffe6e8"},
    {"name": "Violet", "mode": "dark", "bg": "#05020a", "accent": "#a970ff", "accent2": "#4dd8ff",
     "alert": "#ff4fa3", "warn": "#ffc24d", "text": "#efe6ff"},
    {"name": "Graphite", "mode": "dark", "bg": "#0b0c0d", "accent": "#d5dbe0", "accent2": "#7fb7ff",
     "alert": "#ff5f6d", "warn": "#f2c14e", "text": "#ffffff"},
    {"name": "Daylight", "mode": "light", "bg": "#eef4f0", "accent": "#007a47", "accent2": "#006f8a",
     "alert": "#c0138f", "warn": "#a86400", "text": "#06140d"},
    {"name": "Paper Blue", "mode": "light", "bg": "#f1f4f8", "accent": "#1557c0", "accent2": "#00788a",
     "alert": "#c2185b", "warn": "#a86400", "text": "#0a1220"},
    {"name": "Sand", "mode": "light", "bg": "#f6f1e7", "accent": "#a14a00", "accent2": "#6b5b00",
     "alert": "#b3261e", "warn": "#8a5a00", "text": "#1f1408"},
]

# where the original look keeps its anchors
_OLD = {"bg": (1, 7, 5), "accent": (0, 255, 140), "accent2": (0, 229, 255),
        "alert": (255, 43, 214), "warn": (255, 190, 60), "text": (220, 255, 240)}


def parse(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hexs(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def load():
    theme = dict(DEFAULT)
    for path in (SYSTEM_FILE, USER_FILE):
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                theme.update({k: v for k, v in data.items() if k in DEFAULT})
        except (OSError, ValueError):
            pass
    for k in ("bg", "accent", "accent2", "alert", "warn", "text"):
        try:
            parse(theme[k])
        except (ValueError, IndexError, TypeError, AttributeError):
            theme[k] = DEFAULT[k]
    return theme


def save(theme):
    os.makedirs(os.path.dirname(USER_FILE), exist_ok=True)
    tmp = USER_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({k: theme.get(k, DEFAULT[k]) for k in DEFAULT}, f, indent=2)
    os.replace(tmp, USER_FILE)


class Palette:
    def __init__(self, theme=None):
        self.theme = theme or load()
        t = self.theme
        self.light = t["mode"] == "light"
        self.new = {k: parse(t[k]) for k in _OLD}
        self.identity = all(self.new[k] == _OLD[k] for k in _OLD) and not self.light
        bg = self.new["bg"]
        # what pure black turns into: the deepest surface (input fields, text on an accent-filled button)
        self.deep = (255, 255, 255) if self.light else tuple(v * 0.25 for v in bg)
        self._cache = {}

    def _family(self, h, s, v):
        """Which anchor an original colour belongs to, by hue."""
        if s < 0.22 or v < 0.02:
            return None
        d = h * 360
        if 95 <= d < 172:
            return "accent"
        if 172 <= d < 225:
            return "accent2"
        if 20 <= d < 70:
            return "warn"
        return "alert"                 # magenta, purple, red

    def remap(self, rgb):
        """Move one colour of the original look to its place in this theme."""
        if self.identity:
            return rgb
        rgb = tuple(rgb[:3])
        hit = self._cache.get(rgb)
        if hit is not None:
            return hit
        r, g, b = (c / 255.0 for c in rgb)
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        fam = self._family(h, s, v)
        bg, text = self.new["bg"], self.new["text"]
        if fam is None:                # greys: black -> deepest surface, white -> text
            out = _mix(self.deep, bg, v / 0.04) if v < 0.04 else _mix(bg, text, (v - 0.04) / 0.96)
        else:
            k = max(0.0, (v - 0.027) / 0.973)          # 0 at the original background's brightness
            base = _mix(bg, self.new[fam], k)          # how far from the background toward the anchor
            out = _mix(base, text, (1.0 - s) * k)      # washed-out versions lean toward the text colour
        out = tuple(int(round(c)) for c in out)
        self._cache[rgb] = out
        return out

    def hex(self, h):
        return hexs(self.remap(parse(h)))

    def int(self, value):
        r, g, b = self.remap(((value >> 16) & 255, (value >> 8) & 255, value & 255))
        return (r << 16) | (g << 8) | b

    def text(self, s):
        """Recolour a whole config file: #rrggbb, #rgb is left alone, and 38;2;R;G;B terminal escapes."""
        if self.identity:
            return s
        s = re.sub(r"#([0-9a-fA-F]{6})\b", lambda m: self.hex(m.group(1)), s)
        s = re.sub(r"([34]8;2;)(\d+);(\d+);(\d+)",
                   lambda m: m.group(1) + ";".join(str(c) for c in self.remap(tuple(int(m.group(i)) for i in (2, 3, 4)))), s)
        return s


_current = None


def current():
    global _current
    if _current is None:
        _current = Palette()
    return _current
