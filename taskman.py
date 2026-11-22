#!/usr/bin/env python3
"""ASTRO//TASKS: the ASTRO//OS task manager."""
import os
import pwd
import signal
import sys
import threading
import time

from PyQt6.QtCore import QPointF, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (QHBoxLayout, QLineEdit, QMenu, QMessageBox, QPushButton, QVBoxLayout,
                             QWidget)

from common import (AMBER, CYAN, GREEN, GREEN_DARK, MAGENTA, WHITE, Stats, col, font, hud_panel, mix)
from ui import BG, Col, Table, TitleStrip, human_size, make_app

HZ = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")
ME = os.getuid()


class Scanner(threading.Thread):
    def __init__(self, on_data):
        super().__init__(daemon=True)
        self.on_data = on_data
        self.prev = {}
        self.cmd = {}
        self.users = {}
        self.t0 = time.time()
        self.paused = False
        self.wake = threading.Event()

    def user(self, uid):
        if uid not in self.users:
            try:
                self.users[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                self.users[uid] = str(uid)
        return self.users[uid]

    def scan(self):
        now = time.time()
        dt = max(now - self.t0, 0.1)
        self.t0 = now
        rows, cur = [], {}
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/stat") as f:
                    s = f.read()
                r = s.rindex(")")
                name = s[s.index("(") + 1:r]
                p = s[r + 2:].split()
                ticks = int(p[11]) + int(p[12])
                start = p[19]
                key = (pid, start)
                if key not in self.cmd:
                    try:
                        with open(f"/proc/{pid}/cmdline", "rb") as f:
                            c = f.read(400).replace(b"\0", b" ").decode("utf-8", "replace").strip()
                    except OSError:
                        c = ""
                    self.cmd[key] = (c, os.stat(f"/proc/{pid}").st_uid)
                cmdline, uid = self.cmd[key]
            except (OSError, ValueError, IndexError):
                continue
            cur[key] = ticks
            d = ticks - self.prev.get(key, ticks)
            rows.append({"id": int(pid), "pid": int(pid), "name": name, "cmd": cmdline or f"[{name}]",
                         "user": self.user(uid), "uid": uid, "cpu": d / HZ / dt * 100,
                         "mem": int(p[21]) * PAGE, "state": p[0], "thr": int(p[17]),
                         "time": ticks / HZ, "low": (name + " " + cmdline).lower()})
        self.prev = cur
        if len(self.cmd) > len(cur) * 3:
            self.cmd = {k: v for k, v in self.cmd.items() if k in cur}
        return rows

    def run(self):
        self.scan()
        time.sleep(0.5)
        while True:
            if not self.paused:
                self.on_data(self.scan())
            self.wake.wait(2.0)
            self.wake.clear()


class Gauges(QWidget):
    """Core heat grid, CPU / memory history and headline numbers."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(150)
        self.stats = Stats()
        self.cpu_hist = [0.0] * 120
        self.mem_hist = [0.0] * 120
        self.procs = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.timer.start(1000)

    def step(self):
        st = self.stats
        st.update()
        self.cpu_hist = self.cpu_hist[1:] + [st.total]
        self.mem_hist = self.mem_hist[1:] + [st.mem_used / st.mem_total]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), BG)
        st = self.stats
        # core grid
        n = max(1, len(st.cores))
        per = 12
        rows = (n + per - 1) // per
        cell = max(8, min(16, (H - 50) // max(1, rows) - 2))
        gw = per * (cell + 2) + 24
        hud_panel(p, 14, 16, gw, H - 30, f"CORES x{n}")
        for i, u in enumerate(st.cores):
            c = mix(GREEN_DARK, GREEN, u * 2) if u < 0.5 else mix(GREEN, MAGENTA, (u - 0.5) * 2)
            p.fillRect(26 + (i % per) * (cell + 2), 34 + (i // per) * (cell + 2), cell, cell,
                       col(c, 80 + 175 * min(1, u * 1.6 + 0.1)))
        # history graph
        gx = 14 + gw + 18
        nums_w = 250
        gwid = W - gx - nums_w - 28
        hud_panel(p, gx, 16, gwid, H - 30, "LOAD HISTORY // 120s", accent=CYAN)
        ix, iy, iw, ih = gx + 10, 30, gwid - 20, H - 54
        p.setPen(col(CYAN, 30))
        for k in range(1, 4):
            p.drawLine(ix, iy + ih * k // 4, ix + iw, iy + ih * k // 4)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for hist, c in ((self.mem_hist, CYAN), (self.cpu_hist, GREEN)):
            pen = QPen(c)
            pen.setWidthF(1.6)
            p.setPen(pen)
            prev = None
            m = len(hist)
            for i, v in enumerate(hist):
                pt = QPointF(ix + iw * i / (m - 1), iy + ih - 1 - (ih - 4) * min(1.0, v))
                if prev is not None:
                    p.drawLine(prev, pt)
                prev = pt
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # headline numbers
        nx = W - nums_w - 14
        hud_panel(p, nx, 16, nums_w, H - 30, "VITALS")
        up = int(getattr(st, "uptime", 0))
        items = (("CPU", f"{st.total * 100:5.1f} %", GREEN), ("MEM", f"{st.mem_used:.1f} / {st.mem_total:.0f} G", CYAN),
                 ("LOAD", str(getattr(st, "load", "0")), GREEN), ("TASKS", str(self.procs), GREEN),
                 ("UP", f"{up // 86400}d {up % 86400 // 3600:02d}:{up % 3600 // 60:02d}", GREEN))
        for i, (k, v, c) in enumerate(items):
            y = 42 + i * 20
            p.setFont(font(13, True, spacing=1.5))
            p.setPen(col(c, 170))
            p.drawText(nx + 14, y, k)
            p.setFont(font(15, True))
            p.setPen(WHITE if i < 2 else c)
            p.drawText(QRect(nx + 70, y - 15, nums_w - 84, 20), Qt.AlignmentFlag.AlignRight, v)


class Tasks(QWidget):
    data = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASTRO//TASKS")
        self.resize(1000, 720)
        self.all = []
        self.mine = False
        self.mem_total = 1
        try:
            with open("/proc/meminfo") as f:
                self.mem_total = int(f.readline().split()[1]) * 1024
        except (OSError, ValueError):
            pass

        self.title = TitleStrip("ASTRO//TASKS", "")
        self.gauges = Gauges()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("FILTER BY NAME, COMMAND, USER OR PID...")
        self.table = Table([
            Col("pid", "PID", 78, "r"),
            Col("user", "USER", 96),
            Col("cpu", "CPU %", 128, paint=self.paint_cpu),
            Col("mem", "MEMORY", 128, paint=self.paint_mem),
            Col("thr", "THR", 56, "r"),
            Col("state", "ST", 44, paint=self.paint_state),
            Col("name", "COMMAND", 0, paint=self.paint_cmd),
        ], sort_key="cpu", sort_rev=True)
        self.table.empty_text = "NO MATCHING TASKS"

        def btn(text, fn, tip=""):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(fn)
            return b

        self.b_mine = btn("MINE ONLY", self.toggle_mine, "Show only your own processes")
        self.b_pause = btn("PAUSE", self.toggle_pause, "Freeze the list")
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(6)
        bar.addWidget(self.filter, 1)
        bar.addWidget(self.b_mine)
        bar.addWidget(self.b_pause)
        bar.addWidget(btn("END TASK", lambda: self.kill(signal.SIGTERM), "Ask the process to quit (Del)"))
        b = btn("FORCE KILL", lambda: self.kill(signal.SIGKILL), "Kill immediately (Shift+Del)")
        b.setStyleSheet("QPushButton { border-color: #ff2bd6; color: #ff2bd6; } QPushButton:hover { background: #4a0a3d; color: #fff; }")
        bar.addWidget(b)
        self.msg = QLineEdit()
        self.msg.setReadOnly(True)
        self.msg.setFrame(False)
        self.msg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.msg.setStyleSheet("background: transparent; border: none; color: #00e5ff; padding: 4px 14px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.title)
        lay.addWidget(self.gauges)
        lay.addLayout(bar)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.msg)

        self.filter.textChanged.connect(self.apply)
        self.table.sortChanged.connect(self.apply)
        self.table.contextRequested.connect(self.context)
        self.data.connect(self.on_data)
        QShortcut(QKeySequence("Delete"), self, activated=lambda: self.kill(signal.SIGTERM))
        QShortcut(QKeySequence("Shift+Delete"), self, activated=lambda: self.kill(signal.SIGKILL))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.filter.setFocus)
        QShortcut(QKeySequence("Escape"), self, activated=lambda: (self.filter.clear(), self.table.setFocus()))
        self.scanner = Scanner(self.data.emit)
        self.scanner.start()
        self.table.setFocus()

    # ------------------------------------------------------------ data
    def on_data(self, rows):
        self.all = rows
        self.gauges.procs = len(rows)
        self.apply()

    def apply(self):
        flt = self.filter.text().lower().strip()
        rows = self.all
        if self.mine:
            rows = [r for r in rows if r["uid"] == ME]
        if flt:
            rows = [r for r in rows if flt in r["low"] or flt == str(r["pid"]) or flt == r["user"]]
        key = self.table.sort_key or "cpu"
        if key in ("name", "user", "state"):
            rows = sorted(rows, key=lambda r: (str(r[key]).lower(), r["pid"]), reverse=self.table.sort_rev)
        else:
            rows = sorted(rows, key=lambda r: (r[key], r["pid"]), reverse=self.table.sort_rev)
        self.table.set_rows(rows)
        busy = sum(1 for r in self.all if r["cpu"] > 1)
        self.title.set_subtitle(f"{len(rows)} OF {len(self.all)} TASKS // {busy} ACTIVE // "
                                f"{len(self.table.sel)} SELECTED" + (" // PAUSED" if self.scanner.paused else ""))

    # ------------------------------------------------------------ cells
    def bar_cell(self, p, r, frac, text, c, sel):
        bw = r.width() - 58
        y = r.top() + 10
        p.fillRect(r.left(), y, bw, 8, col(c, 36))
        p.fillRect(r.left(), y, int(bw * max(0.0, min(1.0, frac))), 8, c)
        p.setFont(font(13))
        p.setPen(WHITE if sel else c)
        p.drawText(QRect(r.right() - 56, r.top(), 56, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)

    def paint_cpu(self, p, r, row, sel):
        v = row["cpu"]
        c = MAGENTA if v > 80 else (AMBER if v > 25 else GREEN)
        self.bar_cell(p, r, v / 100, f"{v:5.1f}", c, sel)

    def paint_mem(self, p, r, row, sel):
        frac = row["mem"] / self.mem_total
        c = MAGENTA if frac > 0.3 else CYAN
        self.bar_cell(p, r, frac * 5, human_size(row["mem"]), c, sel)

    def paint_state(self, p, r, row, sel):
        s = row["state"]
        c = {"R": WHITE, "S": GREEN, "I": col(GREEN, 110), "Z": MAGENTA, "T": AMBER, "D": CYAN}.get(s, GREEN)
        if s == "R":
            p.fillRect(r.left() - 2, r.top() + 6, 18, 16, col(GREEN, 120))
        p.setFont(font(13, True))
        p.setPen(c)
        p.drawText(r, Qt.AlignmentFlag.AlignVCenter, s)

    def paint_cmd(self, p, r, row, sel):
        own = row["uid"] == ME
        p.setFont(font(14, True))
        fm = p.fontMetrics()
        name = row["name"]
        p.setPen(WHITE if sel else (GREEN if own else col(GREEN, 150)))
        nw = min(fm.horizontalAdvance(name) + 12, r.width())
        p.drawText(r, Qt.AlignmentFlag.AlignVCenter, fm.elidedText(name, Qt.TextElideMode.ElideRight, r.width()))
        rest = QRect(r.left() + nw, r.top(), r.width() - nw, r.height())
        if rest.width() > 40:
            p.setFont(font(12))
            p.setPen(col(WHITE if sel else CYAN, 150 if own else 100))
            p.drawText(rest, Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(row["cmd"], Qt.TextElideMode.ElideRight, rest.width()))

    # ------------------------------------------------------------ actions
    def say(self, text):
        self.msg.setText(text)
        QTimer.singleShot(7000, lambda t=text: self.msg.clear() if self.msg.text() == t else None)

    def toggle_mine(self):
        self.mine = not self.mine
        self.b_mine.setText("ALL USERS" if self.mine else "MINE ONLY")
        self.apply()

    def toggle_pause(self):
        self.scanner.paused = not self.scanner.paused
        self.b_pause.setText("RESUME" if self.scanner.paused else "PAUSE")
        self.scanner.wake.set()
        self.apply()

    def kill(self, sig):
        rows = self.table.selected_rows()
        if not rows:
            self.say("SELECT A TASK FIRST")
            return
        names = ", ".join(f"{r['name']} ({r['pid']})" for r in rows[:6]) + (" ..." if len(rows) > 6 else "")
        box = QMessageBox(self)
        box.setWindowTitle("TERMINATE")
        box.setText(("FORCE KILL" if sig == signal.SIGKILL else "END TASK") + f":\n\n{names}")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        ok, denied = 0, 0
        for r in rows:
            try:
                os.kill(r["pid"], sig)
                ok += 1
            except PermissionError:
                denied += 1
            except ProcessLookupError:
                pass
        self.say(f"SIGNAL SENT TO {ok} TASK(S)" + (f" // {denied} DENIED (NOT YOUR PROCESS)" if denied else ""))
        self.scanner.wake.set()

    def context(self, pos):
        rows = self.table.selected_rows()
        if not rows:
            return
        m = QMenu(self)
        m.addAction("END TASK", lambda: self.kill(signal.SIGTERM))
        m.addAction("FORCE KILL", lambda: self.kill(signal.SIGKILL))
        m.addSeparator()
        m.addAction("PAUSE PROCESS (STOP)", lambda: self.signal_quiet(signal.SIGSTOP))
        m.addAction("RESUME PROCESS (CONT)", lambda: self.signal_quiet(signal.SIGCONT))
        m.addSeparator()
        m.addAction("FILTER TO THIS NAME", lambda: self.filter.setText(rows[0]["name"]))
        m.exec(pos)

    def signal_quiet(self, sig):
        for r in self.table.selected_rows():
            try:
                os.kill(r["pid"], sig)
            except OSError:
                self.say("PERMISSION DENIED")
        self.scanner.wake.set()


def main():
    app = make_app(sys.argv)
    w = Tasks()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
