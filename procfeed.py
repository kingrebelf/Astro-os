#!/usr/bin/env python3
"""Top processes by CPU as JSON lines. Runs as its own process so the scan never stalls an animation."""
import json
import os
import sys
import time

hz = os.sysconf("SC_CLK_TCK")
prev, t0 = {}, time.time()
while True:
    cur = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/stat") as f:
                s = f.read()
            r = s.rindex(")")
            p = s[r + 2:].split()
            cur[pid] = (int(p[11]) + int(p[12]), s[s.index("(") + 1:r])
        except (OSError, ValueError, IndexError):
            continue
    now = time.time()
    dt = max(now - t0, 0.1)
    t0 = now
    rows = sorted(((t - prev[p][0]) / hz / dt * 100, p, n) for p, (t, n) in cur.items()
                  if p in prev and t > prev[p][0])
    prev = cur
    try:
        print(json.dumps({"top": rows[-16:][::-1], "count": len(cur)}), flush=True)
    except (BrokenPipeError, OSError):
        sys.exit(0)
    if os.getppid() == 1:
        sys.exit(0)
    time.sleep(2.5)
