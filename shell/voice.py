"""Microphone level + dictation detection for the desktop sphere.

Only a loudness number is computed from the audio; nothing is recorded or stored.
"""
import array
import json
import subprocess
import threading
import time


def _die_with_parent():
    """Ask the kernel to stop the recorder if the desktop process goes away (no orphans)."""
    import ctypes
    import signal
    ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)      # PR_SET_PDEATHSIG


class Mic(threading.Thread):
    """Continuous mic level, 0..1, with an adaptive noise floor so room hum stays at zero."""

    def __init__(self):
        super().__init__(daemon=True)
        self.level = 0.0
        self.floor = 200.0
        self.peak = 2500.0
        self.wave = [0.0] * 72

    def run(self):
        while True:
            proc = None
            try:
                proc = subprocess.Popen(
                    ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16",
                     "--latency", "40ms", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    preexec_fn=_die_with_parent)
                while True:
                    buf = proc.stdout.read(1280)                 # 40 ms
                    if not buf:
                        break
                    a = array.array("h", buf[:len(buf) // 2 * 2])
                    if not a:
                        continue
                    amp = max(max(a), -min(a))                   # peak, computed in C
                    self.wave = [a[i] / self.peak for i in range(0, len(a), 9)]   # ~70 points for the scope
                    # floor follows quiet quickly and loud slowly; peak decays slowly
                    self.floor += (amp - self.floor) * (0.2 if amp < self.floor else 0.004)
                    self.peak = max(self.peak * 0.9995, amp, self.floor * 6, 1500.0)
                    gate = self.floor * 2.2 + 120
                    self.level = max(0.0, min(1.0, (amp - gate) / max(1.0, self.peak - gate))) ** 0.6
            except OSError:
                pass
            finally:
                if proc:
                    proc.kill()
            self.level = 0.0
            time.sleep(3)                                        # mic missing or unplugged: retry


class Watcher(threading.Thread):
    """True while the dictation app (OpenWhispr) holds a capture stream."""

    def __init__(self, match="whispr"):
        super().__init__(daemon=True)
        self.match = match
        self.recording = False

    def run(self):
        while True:
            found = False
            try:
                out = subprocess.run(["pw-dump"], capture_output=True, timeout=3).stdout
                for o in json.loads(out):
                    props = (o.get("info") or {}).get("props") or {}
                    if props.get("media.class") != "Stream/Input/Audio":
                        continue
                    ident = " ".join(str(props.get(k, "")) for k in
                                     ("application.name", "application.process.binary", "node.name")).lower()
                    if self.match in ident:
                        found = True
                        break
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            self.recording = found
            time.sleep(0.4)
