"""Shared globe pieces for ASTRO//OS: connection scanner and globe drawing.

Used by the desktop (embedded globe) and by netglobe.py (the full-size app).
IP geolocation by DB-IP (https://db-ip.com), CC BY 4.0; lookups run offline.
"""
import ipaddress
import json
import math
import os
import re
import subprocess
import threading
import time

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF, QRadialGradient

from common import tc, AMBER, CYAN, GREEN, GREEN_DIM, MAGENTA, ROOT, WHITE, col, font
from mmdb import MMDB

CONF = os.path.expanduser("~/.config/astro-os")
SIDE = 372
USUAL_PORTS = {80, 443, 53, 853, 123, 22, 993, 995, 587, 465, 143, 5228, 5222, 5223, 3478, 1935, 8443}
RAD = math.pi / 180


def vec(lat, lon):
    la, lo = lat * RAD, lon * RAD
    return (math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo))


def load_config():
    cfg = {"home": [34.0, -42.0], "label": os.uname().nodename.upper()[:14]}
    try:
        with open(os.path.join(CONF, "globe.json")) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        os.makedirs(CONF, exist_ok=True)
        with open(os.path.join(CONF, "globe.json"), "w") as f:
            json.dump(cfg, f, indent=2)
    return cfg


def load_land():
    lines = []
    with open(os.path.join(ROOT, "data", "land.geojson")) as f:
        gj = json.load(f)
    for feat in gj["features"]:
        g = feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                lines.append([vec(lat, lon) for lon, lat in ring])
    return lines


def graticule():
    lines = []
    for lon in range(-180, 180, 30):
        lines.append([vec(lat, lon) for lat in range(-90, 91, 6)])
    for lat in range(-60, 61, 30):
        lines.append([vec(lat, lon) for lon in range(-180, 181, 6)])
    return lines


class NoDB:
    """Stands in for a location database that has not been downloaded: every lookup is unknown."""

    def lookup(self, ip):
        return None


def open_db(name):
    try:
        return MMDB(os.path.join(ROOT, "data", name))
    except (OSError, ValueError):
        return NoDB()


class Scanner(threading.Thread):
    """Reads the socket table every few seconds and geolocates the peers."""

    def __init__(self):
        super().__init__(daemon=True)
        self.city = open_db("dbip-city.mmdb")
        self.asn = open_db("dbip-asn.mmdb")
        self.groups = []
        self.local = 0
        self.total = 0
        self.version = 0
        self.seen_path = os.path.join(CONF, "globe_seen.json")
        try:
            with open(self.seen_path) as f:
                self.seen = set(json.load(f))
            self.baseline = False
        except (OSError, ValueError):
            self.seen = set()
            self.baseline = True          # first ever run: learn quietly
        self.started = time.time()
        self.first_seen = {}

    @staticmethod
    def split(addr):
        host, _, port = addr.rpartition(":")
        host = host.strip("[]").split("%")[0]
        return host, int(port) if port.isdigit() else 0

    def scan(self):
        listen = set()
        try:
            out = subprocess.run(["ss", "-tlnH"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                p = line.split()
                if len(p) > 3:
                    listen.add(self.split(p[3])[1])
            out = subprocess.run(["ss", "-tunpH"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return
        groups = {}
        local = total = 0
        for line in out.splitlines():
            p = line.split()
            if len(p) < 6 or p[1] not in ("ESTAB", "UNCONN"):
                continue
            ip, port = self.split(p[5])
            lport = self.split(p[4])[1]
            if not port or ip in ("*", "0.0.0.0", "::"):
                continue
            try:
                a = ipaddress.ip_address(ip)
            except ValueError:
                continue
            total += 1
            if a.is_private or a.is_loopback or a.is_link_local or a.is_multicast:
                local += 1
                continue
            m = re.search(r'\(\("([^"]+)"', line)
            proc = m.group(1) if m else "system"
            geo = self.city.lookup(ip) or {}
            loc = geo.get("location") or {}
            if "latitude" not in loc:
                continue
            cc = (geo.get("country") or {}).get("iso_code", "??")
            city = ((geo.get("city") or {}).get("names") or {}).get("en", "") or \
                   ((geo.get("country") or {}).get("names") or {}).get("en", "?")
            city = re.sub(r"\s*\(.*\)", "", city)
            org = (self.asn.lookup(ip) or {}).get("autonomous_system_organization", "")
            inbound = p[0] == "tcp" and lport in listen
            key = (round(loc["latitude"], 1), round(loc["longitude"], 1), inbound)
            g = groups.setdefault(key, {"lat": loc["latitude"], "lon": loc["longitude"], "city": city,
                                        "cc": cc, "org": org, "n": 0, "procs": set(), "ports": set(),
                                        "ips": set(), "inbound": inbound, "flag": ""})
            g["n"] += 1
            g["procs"].add(proc)
            g["ports"].add(lport if inbound else port)
            g["ips"].add(ip)
        now = time.time()
        new_seen = False
        for key, g in groups.items():
            self.first_seen.setdefault(key, now)
            g["age"] = now - self.first_seen[key]
            odd = [pt for pt in g["ports"] if pt not in USUAL_PORTS]
            if g["inbound"]:
                g["flag"] = "INBOUND"
            elif g["cc"] not in self.seen and not self.baseline:
                g["flag"] = "NEW REGION"
            elif odd:
                g["flag"] = f"ODD PORT {odd[0]}"
            if g["cc"] not in self.seen and (self.baseline or g["age"] > 600):
                self.seen.add(g["cc"])
                new_seen = True
        for key in list(self.first_seen):
            if key not in groups and now - self.first_seen[key] > 3600:
                del self.first_seen[key]
        if self.baseline and now - self.started > 20:
            self.baseline = False
        if new_seen:
            try:
                with open(self.seen_path, "w") as f:
                    json.dump(sorted(self.seen), f)
            except OSError:
                pass
        order = sorted(groups.values(), key=lambda g: (g["flag"] == "", -g["n"]))
        self.groups, self.local, self.total = order, local, total
        self.version += 1

    def run(self):
        while True:
            self.scan()
            time.sleep(3)


def flag_color(g, hot=False):
    if g["flag"] == "INBOUND":
        return MAGENTA
    if g["flag"]:
        return AMBER
    return CYAN if hot else GREEN


def projector(cx, cy, R, yaw, tilt):
    ya, ti = yaw * RAD, tilt * RAD
    cy_, sy_, ct, st = math.cos(ya), math.sin(ya), math.cos(ti), math.sin(ti)

    def proj(v, k=1.0):
        x, y, z = v
        x1 = x * cy_ - z * sy_
        z1 = x * sy_ + z * cy_
        y1 = y * ct - z1 * st
        z2 = y * st + z1 * ct
        return cx + x1 * R * k, cy - y1 * R * k, z2
    return proj


def paint_base(p, cx, cy, R, yaw, tilt, land, grat):
    """Sphere body, rim, graticule and coastlines (the part that only changes when you rotate)."""
    proj = projector(cx, cy, R, yaw, tilt)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    g = QRadialGradient(cx - R * 0.3, cy - R * 0.35, R * 1.5)
    g.setColorAt(0, tc(0, 46, 28))
    g.setColorAt(0.7, tc(0, 16, 10))
    g.setColorAt(1, tc(0, 6, 4))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), R, R)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for w_, al in ((9, 26), (5, 50), (1.6, 255)):
        pen = QPen(col(GREEN, al))
        pen.setWidthF(w_)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), R + 1, R + 1)
    for lines, pen in ((grat, QPen(col(GREEN, 38))), (land, QPen(col(GREEN, 235)))):
        pen.setWidthF(1.0 if lines is grat else 1.3)
        p.setPen(pen)
        for line in lines:
            run = []
            for v in line:
                sx, sy, z = proj(v)
                if z > 0.02:
                    run.append(QPointF(sx, sy))
                else:
                    if len(run) > 1:
                        p.drawPolyline(QPolygonF(run))
                    run = []
            if len(run) > 1:
                p.drawPolyline(QPolygonF(run))
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)


def paint_links(p, cx, cy, R, yaw, tilt, t, home, label, groups, hover=-1, lift_max=0.34):
    """Arcs, travelling pulses, city markers, home node and labels. Returns the area that animates."""
    proj = projector(cx, cy, R, yaw, tilt)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    labels = []
    for i, gr in enumerate(groups):
        hot = i == hover
        c = flag_color(gr, hot)
        d = vec(gr["lat"], gr["lon"])
        dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(home, d))))
        ang = math.acos(dot)
        n = 36
        lift = 0.10 + lift_max * ang / math.pi
        pts = []
        so = math.sin(ang) or 1e-6
        for k in range(n + 1):
            u = k / n
            a_, b_ = math.sin((1 - u) * ang) / so, math.sin(u * ang) / so
            v = tuple(a_ * h + b_ * e for h, e in zip(home, d))
            sx, sy, z = proj(v, 1 + lift * math.sin(math.pi * u))
            vis = z > 0 or math.hypot(sx - cx, sy - cy) > R
            pts.append((sx, sy, vis))
            if vis:
                x0, y0, x1, y1 = min(x0, sx), min(y0, sy), max(x1, sx), max(y1, sy)
        pen = QPen(col(c, 60))
        pen.setWidthF(4.5 if hot else 3.5)
        pen2 = QPen(col(c, 255))
        pen2.setWidthF(2.0 if hot else 1.2)
        for k in range(n):
            if pts[k][2] and pts[k + 1][2]:
                a_, b_ = QPointF(pts[k][0], pts[k][1]), QPointF(pts[k + 1][0], pts[k + 1][1])
                p.setPen(pen)
                p.drawLine(a_, b_)
                p.setPen(pen2)
                p.drawLine(a_, b_)
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(min(3, gr["n"])):
            u = (t * 0.45 + j / 3 + i * 0.17) % 1.0
            if gr["inbound"]:
                u = 1 - u
            k = u * n
            k0 = min(n - 1, int(k))
            f = k - k0
            if pts[k0][2] and pts[k0 + 1][2]:
                px_ = pts[k0][0] + (pts[k0 + 1][0] - pts[k0][0]) * f
                py_ = pts[k0][1] + (pts[k0 + 1][1] - pts[k0][1]) * f
                p.setBrush(col(c, 90))
                p.drawEllipse(QPointF(px_, py_), 5.5, 5.5)
                p.setBrush(WHITE)
                p.drawEllipse(QPointF(px_, py_), 2.2, 2.2)
        sx, sy, z = proj(d)
        if z > 0:
            pulse = (t * 0.9 + i * 0.3) % 1.0
            p.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(col(c, 255 * (1 - pulse)))
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.drawEllipse(QPointF(sx, sy), 4 + pulse * 14, 4 + pulse * 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(sx, sy), 3.6, 3.6)
            x0, y0, x1, y1 = min(x0, sx - 20), min(y0, sy - 20), max(x1, sx + 20), max(y1, sy + 20)
            labels.append((sx, sy, f"{gr['city'].upper()}, {gr['cc']}" + (f" x{gr['n']}" if gr["n"] > 1 else ""), c, hot))
    sx, sy, z = proj(home)
    if z > 0:
        pulse = (t * 0.7) % 1.0
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in (0, 0.5):
            q = (pulse + k) % 1.0
            pen = QPen(col(WHITE, 220 * (1 - q)))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawEllipse(QPointF(sx, sy), 5 + q * 22, 5 + q * 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(WHITE)
        p.drawEllipse(QPointF(sx, sy), 4.5, 4.5)
        x0, y0, x1, y1 = min(x0, sx - 30), min(y0, sy - 30), max(x1, sx + 30), max(y1, sy + 30)
        labels.append((sx, sy, f"[ {label} ]", WHITE, True))
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setBrush(Qt.BrushStyle.NoBrush)

    p.setFont(font(12, True, spacing=1))
    fm = p.fontMetrics()
    used = []
    for sx, sy, text, c, hot in sorted(labels, key=lambda l: -l[4]):
        r = QRect(int(sx) + 10, int(sy) - 20, fm.horizontalAdvance(text) + 10, 17)
        tries = 0
        while any(r.intersects(u) for u in used) and tries < 6:
            r.translate(0, 18)
            tries += 1
        if tries == 6:
            continue
        used.append(r)
        p.fillRect(r, tc(0, 10, 6, 215))
        p.setPen(col(c, 150))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.setPen(c)
        p.drawText(r.left() + 5, r.bottom() - 4, text)
    if x1 < x0:
        return QRect()
    return QRect(int(x0) - 8, int(y0) - 8, int(x1 - x0) + 16, int(y1 - y0) + 16)
