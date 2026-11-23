#!/usr/bin/env python3
"""ASTRO//FILES: the ASTRO//OS file manager."""
import os
import shutil
import stat
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImageReader, QKeySequence, QPainter, QPen, QPixmap, QPolygon, QShortcut
from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLineEdit, QMenu, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)

from common import PAL, tc, AMBER, CYAN, GREEN, GREEN_DIM, MAGENTA, ROOT, WHITE, col, font, hud_panel
from ui import BG, Col, Table, TitleStrip, human_size, make_app

HOME = os.path.expanduser("~")
CODE = {".py", ".sh", ".js", ".ts", ".c", ".h", ".cpp", ".rs", ".go", ".json", ".toml", ".yaml", ".yml",
        ".xml", ".html", ".css", ".qss", ".conf", ".ini", ".md", ".txt", ".log", ".cfg", ".desktop"}
IMG = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}
ARC = {".zip", ".tar", ".gz", ".xz", ".bz2", ".7z", ".rar", ".deb", ".zst", ".tgz"}
MEDIA = {".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mkv", ".webm", ".avi", ".mov"}
KIND_COLOR = {"dir": CYAN, "code": GREEN, "image": MAGENTA, "archive": AMBER, "media": tc(199, 125, 255),
              "exec": WHITE, "file": tc(120, 200, 160), "link": CYAN}


def kind_of(name, mode, is_dir):
    if is_dir:
        return "dir"
    ext = os.path.splitext(name)[1].lower()
    if ext in IMG:
        return "image"
    if ext in ARC:
        return "archive"
    if ext in MEDIA:
        return "media"
    if ext in CODE:
        return "code"
    if mode & 0o111:
        return "exec"
    return "file"


def draw_icon(p, x, y, kind, sel=False):
    """Small vector icon, 18x18 at (x, y)."""
    c = WHITE if sel else KIND_COLOR.get(kind, GREEN)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setPen(QPen(c, 1))
    if kind == "dir":
        p.setBrush(col(c, 60))
        p.drawPolygon(QPolygon([QPoint(x, y + 3), QPoint(x + 6, y + 3), QPoint(x + 8, y + 5), QPoint(x + 17, y + 5),
                                QPoint(x + 17, y + 15), QPoint(x, y + 15)]))
    else:
        p.setBrush(col(c, 30))
        p.drawPolygon(QPolygon([QPoint(x + 3, y + 1), QPoint(x + 11, y + 1), QPoint(x + 15, y + 5),
                                QPoint(x + 15, y + 16), QPoint(x + 3, y + 16)]))
        p.drawLine(x + 11, y + 1, x + 11, y + 5)
        p.drawLine(x + 11, y + 5, x + 15, y + 5)
        if kind == "code":
            for i, w in enumerate((6, 8, 4)):
                p.drawLine(x + 5, y + 8 + i * 3, x + 5 + w, y + 8 + i * 3)
        elif kind == "image":
            p.drawPolyline(QPolygon([QPoint(x + 5, y + 13), QPoint(x + 8, y + 9), QPoint(x + 10, y + 11),
                                     QPoint(x + 13, y + 8)]))
        elif kind == "archive":
            for i in range(4):
                p.drawPoint(x + 8 + i % 2, y + 7 + i * 2)
        elif kind == "exec":
            p.drawText(x + 5, y + 14, ">")
        elif kind == "media":
            p.drawPolygon(QPolygon([QPoint(x + 7, y + 8), QPoint(x + 12, y + 11), QPoint(x + 7, y + 14)]))
    p.setBrush(Qt.BrushStyle.NoBrush)


def trash(path):
    """Freedesktop trash: move into ~/.local/share/Trash with an info record."""
    base = os.path.join(HOME, ".local/share/Trash")
    os.makedirs(os.path.join(base, "files"), exist_ok=True)
    os.makedirs(os.path.join(base, "info"), exist_ok=True)
    name = os.path.basename(path.rstrip("/"))
    dest, n = name, 1
    while os.path.lexists(os.path.join(base, "files", dest)):
        n += 1
        dest = f"{name}.{n}"
    with open(os.path.join(base, "info", dest + ".trashinfo"), "w") as f:
        f.write(f"[Trash Info]\nPath={path}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    shutil.move(path, os.path.join(base, "files", dest))


class Crumbs(QWidget):
    """Clickable path segments; click the empty part to type a path."""
    go = pyqtSignal(str)
    edit = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.path = "/"
        self.segs = []
        self.hover = -1
        self.setFixedHeight(32)
        self.setMouseTracking(True)

    def set_path(self, path):
        self.path = path
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), tc(0, 0, 0))
        p.setPen(col(GREEN_DIM, 255))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        parts = [x for x in self.path.split("/") if x]
        items = [("/", "/")]
        acc = ""
        for part in parts:
            acc += "/" + part
            items.append((part, acc))
        p.setFont(font(14, True, spacing=0.5))
        fm = p.fontMetrics()
        # drop leading segments if the path is too long
        while len(items) > 2 and sum(fm.horizontalAdvance(t) + 26 for t, _ in items) > self.width() - 20:
            items.pop(1)
        x = 8
        self.segs = []
        for i, (text, target) in enumerate(items):
            w = fm.horizontalAdvance(text) + 14
            r = QRect(x, 4, w, 24)
            last = i == len(items) - 1
            if i == self.hover:
                p.fillRect(r, col(GREEN, 60))
            p.setPen(WHITE if last else (GREEN if i != self.hover else WHITE))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            self.segs.append((r, target))
            x += w
            if not last:
                p.setPen(col(CYAN, 200))
                p.drawText(x, 21, ">")
                x += 12

    def mouseMoveEvent(self, e):
        h = -1
        for i, (r, _) in enumerate(self.segs):
            if r.contains(e.position().toPoint()):
                h = i
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        for r, target in self.segs:
            if r.contains(e.position().toPoint()):
                self.go.emit(target)
                return
        self.edit.emit()


class Sidebar(QWidget):
    go = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(196)
        self.setMouseTracking(True)
        self.current = ""
        self.hover = -1
        self.rows = []
        self.places = [(n, p) for n, p in (
            ("HOME", HOME), ("DESKTOP", HOME + "/Desktop"), ("DOCUMENTS", HOME + "/Documents"),
            ("DOWNLOADS", HOME + "/Downloads"), ("PICTURES", HOME + "/Pictures"),
            ("ASTRO-OS", ROOT), ("TRASH", HOME + "/.local/share/Trash/files"), ("ROOT /", "/"),
        ) if os.path.isdir(p)]
        self.mounts = []
        self.scan_mounts()

    def scan_mounts(self):
        out = []
        try:
            with open("/proc/mounts") as f:
                for line in f:
                    dev, mnt, fs = line.split()[:3]
                    if mnt == "/" or mnt.startswith(("/media/", "/mnt/", "/run/media/")):
                        try:
                            u = shutil.disk_usage(mnt)
                            out.append((mnt, u.used / u.total if u.total else 0, u.free))
                        except OSError:
                            pass
        except OSError:
            pass
        self.mounts = out

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), BG)
        p.setPen(col(GREEN_DIM, 255))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        self.rows = []
        y = 12
        p.setFont(font(11, True, spacing=2))
        p.setPen(CYAN)
        p.drawText(14, y + 10, "PLACES")
        y += 20
        for i, (name, path) in enumerate(self.places):
            r = QRect(6, y, self.width() - 14, 27)
            active = os.path.normpath(self.current) == os.path.normpath(path)
            if active:
                p.fillRect(r, col(GREEN, 62))
                p.fillRect(r.left(), r.top(), 3, r.height(), GREEN)
            elif len(self.rows) == self.hover:
                p.fillRect(r, col(GREEN, 28))
            p.setFont(font(14, active, spacing=1))
            p.setPen(WHITE if active else GREEN)
            p.drawText(r.left() + 14, r.top() + 19, name)
            self.rows.append((r, path))
            y += 28
        y += 14
        p.setFont(font(11, True, spacing=2))
        p.setPen(CYAN)
        p.drawText(14, y + 10, "VOLUMES")
        y += 20
        for mnt, frac, free in self.mounts:
            r = QRect(6, y, self.width() - 14, 44)
            if len(self.rows) == self.hover:
                p.fillRect(r, col(GREEN, 28))
            p.setFont(font(13, True, spacing=0.5))
            p.setPen(GREEN)
            name = "SYSTEM" if mnt == "/" else os.path.basename(mnt).upper()
            p.drawText(r.left() + 14, r.top() + 16, p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 100))
            p.setFont(font(11))
            p.setPen(col(GREEN, 170))
            p.drawText(QRect(r.left(), r.top() + 3, r.width() - 6, 16), Qt.AlignmentFlag.AlignRight,
                       human_size(free) + " FREE")
            bw = r.width() - 24
            p.fillRect(r.left() + 14, r.top() + 26, bw, 6, col(GREEN, 40))
            p.fillRect(r.left() + 14, r.top() + 26, int(bw * frac), 6, MAGENTA if frac > 0.9 else GREEN)
            self.rows.append((r, mnt))
            y += 48

    def mouseMoveEvent(self, e):
        h = -1
        for i, (r, _) in enumerate(self.rows):
            if r.contains(e.position().toPoint()):
                h = i
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        for r, path in self.rows:
            if r.contains(e.position().toPoint()):
                self.go.emit(path)


class Info(QWidget):
    """Details + preview of the selection."""

    def __init__(self):
        super().__init__()
        self.setFixedWidth(250)
        self.rows = []
        self.folder = ("", 0, 0)
        self.preview = None
        self.preview_for = None
        self.text = []

    def show_rows(self, rows, folder):
        self.rows, self.folder = rows, folder
        self.text, pm = [], None
        if len(rows) == 1 and not rows[0]["dir"]:
            r = rows[0]
            try:
                if r["kind"] == "image" and r["size"] < 30_000_000:
                    rd = QImageReader(r["path"])
                    sz = rd.size()
                    if sz.isValid():
                        k = min(1.0, 220 / max(1, sz.width()), 170 / max(1, sz.height()))
                        rd.setScaledSize(sz * k)
                    img = rd.read()
                    if not img.isNull():
                        pm = QPixmap.fromImage(img)
                elif r["kind"] in ("code", "file", "exec") and r["size"] < 5_000_000:
                    with open(r["path"], "rb") as f:
                        chunk = f.read(1600)
                    if b"\0" not in chunk:
                        self.text = chunk.decode("utf-8", "replace").expandtabs(2).splitlines()[:16]
            except OSError:
                pass
        self.preview = pm
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), BG)
        p.setPen(col(GREEN_DIM, 255))
        p.drawLine(0, 0, 0, H)
        x, w = 14, W - 28
        rows = self.rows
        if not rows:
            path, n, total = self.folder
            hud_panel(p, x, 18, w, 96, "LOCATION")
            p.setFont(font(15, True))
            p.setPen(WHITE)
            p.drawText(x + 12, 46, p.fontMetrics().elidedText(os.path.basename(path) or "/", Qt.TextElideMode.ElideMiddle, w - 24))
            p.setFont(font(13))
            p.setPen(GREEN)
            p.drawText(x + 12, 70, f"{n} ITEMS")
            p.drawText(x + 12, 92, f"{human_size(total)} IN FILES")
            return
        if len(rows) > 1:
            hud_panel(p, x, 18, w, 76, "SELECTION", accent=CYAN)
            p.setFont(font(15, True))
            p.setPen(WHITE)
            p.drawText(x + 12, 46, f"{len(rows)} ITEMS")
            p.setFont(font(13))
            p.setPen(GREEN)
            p.drawText(x + 12, 70, human_size(sum(r["size"] for r in rows if not r["dir"])))
            return
        r = rows[0]
        c = KIND_COLOR.get(r["kind"], GREEN)
        hud_panel(p, x, 18, w, 168, "TARGET", accent=c)
        p.setFont(font(15, True))
        p.setPen(WHITE)
        fm = p.fontMetrics()
        name = r["name"]
        p.drawText(x + 12, 46, fm.elidedText(name, Qt.TextElideMode.ElideMiddle, w - 24))
        p.setFont(font(13))
        lines = [("TYPE", ("FOLDER" if r["dir"] else r["kind"].upper()) + (" (LINK)" if r["link"] else "")),
                 ("SIZE", "--" if r["dir"] else human_size(r["size"])),
                 ("MODIFIED", time.strftime("%Y-%m-%d %H:%M", time.localtime(r["mtime"]))),
                 ("ACCESS", stat.filemode(r["mode"])),
                 ("OWNER", r.get("owner", ""))]
        for i, (k, v) in enumerate(lines):
            yy = 72 + i * 22
            p.setPen(col(c, 170))
            p.drawText(x + 12, yy, k)
            p.setPen(GREEN)
            p.drawText(x + 92, yy, p.fontMetrics().elidedText(v, Qt.TextElideMode.ElideRight, w - 100))
        y = 210
        if self.preview is not None:
            hud_panel(p, x, y, w, self.preview.height() + 26, "PREVIEW", accent=MAGENTA)
            p.drawPixmap(x + (w - self.preview.width()) // 2, y + 14, self.preview)
        elif self.text:
            h = min(H - y - 16, 20 + len(self.text) * 15)
            hud_panel(p, x, y, w, h, "PREVIEW")
            p.setFont(font(11))
            p.setPen(col(GREEN, 210))
            p.setClipRect(x + 2, y + 2, w - 4, h - 4)
            for i, line in enumerate(self.text):
                p.drawText(x + 8, y + 24 + i * 15, line[:60])
            p.setClipping(False)


class Files(QWidget):
    loaded = pyqtSignal(str, list, str)
    job_done = pyqtSignal(str)

    def __init__(self, start):
        super().__init__()
        self.setWindowTitle("ASTRO//FILES")
        self.resize(1060, 700)
        self.path = ""
        self.back, self.fwd = [], []
        self.hidden = False
        self.clip = ([], "copy")
        self.entries = []
        self.type_buf, self.type_time = "", 0.0
        self.owners = {}

        self.title = TitleStrip("ASTRO//FILES", "")
        self.crumbs = Crumbs()
        self.path_edit = QLineEdit()
        self.path_edit.hide()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("FILTER...")
        self.filter.setFixedWidth(170)
        self.table = Table([
            Col("name", "NAME", 0, paint=self.paint_name),
            Col("size", "SIZE", 96, "r", text=lambda r: "--" if r["dir"] else human_size(r["size"])),
            Col("kind", "TYPE", 92, text=lambda r: "FOLDER" if r["dir"] else r["kind"].upper()),
            Col("mtime", "MODIFIED", 150, text=lambda r: time.strftime("%Y-%m-%d %H:%M", time.localtime(r["mtime"]))),
        ], sort_key="name")
        self.table.empty_text = "EMPTY DIRECTORY"
        self.side = Sidebar()
        self.info = Info()
        self.status = QWidget()

        def btn(text, fn, tip):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(fn)
            return b

        nav = QHBoxLayout()
        nav.setContentsMargins(12, 8, 12, 8)
        nav.setSpacing(6)
        self.b_back = btn("<", self.go_back, "Back (Alt+Left)")
        self.b_fwd = btn(">", self.go_fwd, "Forward (Alt+Right)")
        for b in (self.b_back, self.b_fwd, btn("^", self.go_up, "Up (Backspace)"), btn("R", self.reload, "Reload (F5)")):
            b.setFixedWidth(38)
            b.setStyleSheet("padding: 6px 0;")
            nav.addWidget(b)
        nav.addWidget(self.crumbs, 1)
        nav.addWidget(self.path_edit, 1)
        nav.addWidget(self.filter)

        acts = QHBoxLayout()
        acts.setContentsMargins(12, 6, 12, 8)
        acts.setSpacing(6)
        for text, fn, tip in (("+ DIR", self.new_dir, "New folder (Ctrl+Shift+N)"), ("+ FILE", self.new_file, "New empty file"),
                              ("RENAME", self.rename, "Rename (F2)"), ("COPY", lambda: self.set_clip("copy"), "Ctrl+C"),
                              ("CUT", lambda: self.set_clip("cut"), "Ctrl+X"), ("PASTE", self.paste, "Ctrl+V"),
                              ("DELETE", self.delete, "Move to trash (Del)"), ("HIDDEN", self.toggle_hidden, "Show hidden (Ctrl+H)"),
                              ("TERM", self.term_here, "Open terminal here")):
            acts.addWidget(btn(text, fn, tip))
        acts.addStretch(1)
        self.msg = QLineEdit()
        self.msg.setReadOnly(True)
        self.msg.setFrame(False)
        self.msg.setStyleSheet(PAL.text("background: transparent; border: none; color: #00e5ff;"))
        self.msg.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.msg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.msg.setMinimumWidth(260)
        acts.addWidget(self.msg)

        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)
        mid.addWidget(self.side)
        mid.addWidget(self.table, 1)
        mid.addWidget(self.info)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.title)
        lay.addLayout(nav)
        lay.addLayout(mid, 1)
        lay.addLayout(acts)

        self.crumbs.go.connect(self.navigate)
        self.crumbs.edit.connect(self.edit_path)
        self.path_edit.returnPressed.connect(self.path_entered)
        self.path_edit.editingFinished.connect(self.end_edit)
        self.side.go.connect(self.navigate)
        self.filter.textChanged.connect(self.apply)
        self.table.activated.connect(self.open_item)
        self.table.selectionChanged.connect(self.selection)
        self.table.sortChanged.connect(self.apply)
        self.table.contextRequested.connect(self.context)
        self.loaded.connect(self.on_loaded)
        self.job_done.connect(self.on_job)
        for seq, fn in (("F5", self.reload), ("F2", self.rename), ("Delete", self.delete), ("Ctrl+C", lambda: self.set_clip("copy")),
                        ("Ctrl+X", lambda: self.set_clip("cut")), ("Ctrl+V", self.paste), ("Ctrl+H", self.toggle_hidden),
                        ("Ctrl+L", self.edit_path), ("Alt+Left", self.go_back), ("Alt+Right", self.go_fwd),
                        ("Alt+Up", self.go_up), ("Ctrl+Shift+N", self.new_dir), ("Ctrl+F", self.filter.setFocus)):
            QShortcut(QKeySequence(seq), self, activated=fn)
        self.navigate(start, record=False)
        self.table.setFocus()

    # ------------------------------------------------------------ loading
    def navigate(self, path, record=True):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            self.say(f"NOT A DIRECTORY: {path}")
            return
        if record and self.path and path != self.path:
            self.back.append(self.path)
            self.fwd.clear()
        self.path = path
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.blockSignals(False)
        self.crumbs.set_path(path)
        self.side.current = path
        self.side.update()
        self.reload()

    def reload(self):
        path = self.path
        threading.Thread(target=self.scan, args=(path,), daemon=True).start()

    def scan(self, path):
        rows, err = [], ""
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                        link = e.is_symlink()
                        is_dir = e.is_dir()
                        if link:
                            try:
                                st2 = e.stat()
                                size, mode = st2.st_size, st2.st_mode
                            except OSError:
                                size, mode = 0, st.st_mode
                        else:
                            size, mode = st.st_size, st.st_mode
                        rows.append({"id": e.name, "name": e.name, "path": e.path, "dir": is_dir, "link": link,
                                     "size": size, "mode": mode, "mtime": st.st_mtime, "uid": st.st_uid,
                                     "kind": kind_of(e.name, mode, is_dir), "low": e.name.lower()})
                    except OSError:
                        continue
        except OSError as ex:
            err = ex.strerror or str(ex)
        self.loaded.emit(path, rows, err)

    def on_loaded(self, path, rows, err):
        if path != self.path:
            return
        for r in rows:
            uid = r["uid"]
            if uid not in self.owners:
                try:
                    import pwd
                    self.owners[uid] = pwd.getpwuid(uid).pw_name
                except (KeyError, ImportError):
                    self.owners[uid] = str(uid)
            r["owner"] = self.owners[uid]
        self.entries = rows
        self.apply()
        if err:
            self.say("ACCESS DENIED: " + err.upper())
        self.b_back.setEnabled(bool(self.back))
        self.b_fwd.setEnabled(bool(self.fwd))

    def apply(self):
        flt = self.filter.text().lower()
        rows = [r for r in self.entries if (self.hidden or not r["name"].startswith(".")) and flt in r["low"]]
        key = self.table.sort_key or "name"
        if key == "name":
            rows.sort(key=lambda r: r["low"], reverse=self.table.sort_rev)
        else:
            rows.sort(key=lambda r: (r[key], r["low"]), reverse=self.table.sort_rev)
        rows.sort(key=lambda r: not r["dir"])           # folders first (stable)
        self.table.set_rows(rows)
        self.selection()

    def selection(self):
        rows = self.table.selected_rows()
        shown = self.table.rows
        self.info.show_rows(rows, (self.path, len(shown), sum(r["size"] for r in shown if not r["dir"])))
        try:
            free = shutil.disk_usage(self.path).free
        except OSError:
            free = 0
        self.title.set_subtitle(f"{len(shown)} ITEMS // {len(rows)} SELECTED // {human_size(free)} FREE"
                                + (" // HIDDEN SHOWN" if self.hidden else ""))

    def paint_name(self, p, r, row, sel):
        draw_icon(p, r.left(), r.top() + 5, row["kind"], sel)
        c = WHITE if sel else KIND_COLOR.get(row["kind"], GREEN)
        if row["name"].startswith(".") and not sel:
            c = col(c, 120)
        p.setFont(font(14, row["dir"]))
        p.setPen(c)
        tr = QRect(r.left() + 26, r.top(), r.width() - 26, r.height())
        text = row["name"] + (" ->" if row["link"] else "")
        p.drawText(tr, Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, tr.width()))

    # ------------------------------------------------------------ navigation
    def go_back(self):
        if self.back:
            self.fwd.append(self.path)
            self.navigate(self.back.pop(), record=False)

    def go_fwd(self):
        if self.fwd:
            self.back.append(self.path)
            self.navigate(self.fwd.pop(), record=False)

    def go_up(self):
        parent = os.path.dirname(self.path)
        if parent != self.path:
            old = os.path.basename(self.path)
            self.navigate(parent)
            QTimer.singleShot(120, lambda: self.table.select_only(old) if self.table.index_of(old) >= 0 else None)

    def edit_path(self):
        self.crumbs.hide()
        self.path_edit.setText(self.path)
        self.path_edit.show()
        self.path_edit.setFocus()
        self.path_edit.selectAll()

    def path_entered(self):
        self.navigate(self.path_edit.text())
        self.table.setFocus()

    def end_edit(self):
        self.path_edit.hide()
        self.crumbs.show()

    def open_item(self, rid):
        i = self.table.index_of(rid)
        if i < 0:
            return
        r = self.table.rows[i]
        if r["dir"]:
            self.navigate(r["path"])
        else:
            subprocess.Popen(["xdg-open", r["path"]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.say("OPENING " + r["name"].upper())

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Backspace:
            self.go_up()
        elif k == Qt.Key.Key_Escape:
            self.filter.clear()
            self.table.setFocus()
        elif e.text() and e.text().isprintable() and not e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            now = time.time()                       # type-ahead: jump to the first matching name
            self.type_buf = (self.type_buf if now - self.type_time < 0.9 else "") + e.text().lower()
            self.type_time = now
            for r in self.table.rows:
                if r["low"].startswith(self.type_buf):
                    self.table.select_only(r["id"])
                    break
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------ actions
    def say(self, text):
        self.msg.setText(text)
        QTimer.singleShot(6000, lambda t=text: self.msg.clear() if self.msg.text() == t else None)

    def ask(self, title, label, text=""):
        dlg = QInputDialog(self)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)
        dlg.setTextValue(text)
        dlg.resize(420, 120)
        return dlg.textValue().strip() if dlg.exec() else ""

    def new_dir(self):
        name = self.ask("NEW FOLDER", "FOLDER NAME:")
        if name:
            try:
                os.mkdir(os.path.join(self.path, name))
                self.after_change(name)
            except OSError as ex:
                self.say("FAILED: " + (ex.strerror or "").upper())

    def new_file(self):
        name = self.ask("NEW FILE", "FILE NAME:")
        if name:
            try:
                with open(os.path.join(self.path, name), "x"):
                    pass
                self.after_change(name)
            except OSError as ex:
                self.say("FAILED: " + (ex.strerror or "").upper())

    def after_change(self, select=None):
        self.reload()
        if select:
            QTimer.singleShot(200, lambda: self.table.select_only(select) if self.table.index_of(select) >= 0 else None)

    def rename(self):
        rows = self.table.selected_rows()
        if len(rows) != 1:
            return
        new = self.ask("RENAME", "NEW NAME:", rows[0]["name"])
        if new and new != rows[0]["name"]:
            dest = os.path.join(self.path, new)
            if os.path.lexists(dest):
                self.say("NAME ALREADY EXISTS")
                return
            try:
                os.rename(rows[0]["path"], dest)
                self.after_change(new)
            except OSError as ex:
                self.say("FAILED: " + (ex.strerror or "").upper())

    def set_clip(self, mode):
        rows = self.table.selected_rows()
        if rows:
            self.clip = ([r["path"] for r in rows], mode)
            self.say(f"{len(rows)} ITEM(S) READY TO {'MOVE' if mode == 'cut' else 'COPY'}")

    def paste(self):
        paths, mode = self.clip
        if not paths:
            return
        dest_dir = self.path
        self.say(("MOVING" if mode == "cut" else "COPYING") + f" {len(paths)} ITEM(S)...")

        def work():
            done, err = 0, ""
            for src in paths:
                name = os.path.basename(src.rstrip("/"))
                dest = os.path.join(dest_dir, name)
                base, ext = os.path.splitext(name)
                n = 1
                while os.path.lexists(dest):
                    n += 1
                    dest = os.path.join(dest_dir, f"{base} ({n}){ext}")
                try:
                    if mode == "cut":
                        shutil.move(src, dest)
                    elif os.path.isdir(src) and not os.path.islink(src):
                        shutil.copytree(src, dest, symlinks=True)
                    else:
                        shutil.copy2(src, dest, follow_symlinks=False)
                    done += 1
                except (OSError, shutil.Error) as ex:
                    err = str(getattr(ex, "strerror", "") or ex)
            self.job_done.emit(f"{done} ITEM(S) {'MOVED' if mode == 'cut' else 'COPIED'}" + (f" // ERROR: {err.upper()}" if err else ""))

        if mode == "cut":
            self.clip = ([], "copy")
        threading.Thread(target=work, daemon=True).start()

    def on_job(self, text):
        self.say(text)
        self.reload()
        self.side.scan_mounts()
        self.side.update()

    def delete(self):
        rows = self.table.selected_rows()
        if not rows:
            return
        in_trash = self.path.startswith(HOME + "/.local/share/Trash")
        what = rows[0]["name"] if len(rows) == 1 else f"{len(rows)} items"
        box = QMessageBox(self)
        box.setWindowTitle("DELETE")
        box.setText(f"{'PERMANENTLY DELETE' if in_trash else 'MOVE TO TRASH'}:\n\n{what}")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        paths = [r["path"] for r in rows]

        def work():
            done, err = 0, ""
            for path in paths:
                try:
                    if in_trash:
                        if os.path.isdir(path) and not os.path.islink(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                        info = os.path.join(HOME, ".local/share/Trash/info", os.path.basename(path) + ".trashinfo")
                        if os.path.exists(info):
                            os.remove(info)
                    else:
                        trash(path)
                    done += 1
                except (OSError, shutil.Error) as ex:
                    err = str(getattr(ex, "strerror", "") or ex)
            self.job_done.emit(f"{done} ITEM(S) {'DELETED' if in_trash else 'TRASHED'}" + (f" // ERROR: {err.upper()}" if err else ""))

        threading.Thread(target=work, daemon=True).start()

    def toggle_hidden(self):
        self.hidden = not self.hidden
        self.apply()

    def term_here(self):
        subprocess.Popen([os.path.join(ROOT, "astroctl"), "launch", "term"], cwd=self.path, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def context(self, pos):
        m = QMenu(self)
        rows = self.table.selected_rows()
        if rows:
            m.addAction("OPEN", lambda: self.open_item(rows[0]["id"]))
            m.addAction("RENAME", self.rename)
            m.addAction("COPY", lambda: self.set_clip("copy"))
            m.addAction("CUT", lambda: self.set_clip("cut"))
            m.addAction("DELETE", self.delete)
            m.addSeparator()
        if self.clip[0]:
            m.addAction(f"PASTE {len(self.clip[0])} ITEM(S)", self.paste)
        m.addAction("NEW FOLDER", self.new_dir)
        m.addAction("NEW FILE", self.new_file)
        m.addAction("TERMINAL HERE", self.term_here)
        m.exec(pos)


def main():
    app = make_app(sys.argv)
    start = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else HOME
    w = Files(start)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
