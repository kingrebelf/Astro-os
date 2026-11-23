#!/usr/bin/env python3
"""Send QMP commands (one JSON object per line on stdin) to the test VM.   qmp.py SOCKET"""
import json, socket, sys
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); f = s.makefile("rw")
f.readline(); f.write('{"execute":"qmp_capabilities"}\n'); f.flush(); f.readline()
for line in sys.stdin.read().splitlines():
    if not line.strip():
        continue
    f.write(line + "\n"); f.flush()
    while True:
        r = json.loads(f.readline())
        if "return" in r or "error" in r:
            if "error" in r:
                print(r, file=sys.stderr)
            break
