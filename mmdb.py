"""Minimal pure-Python reader for MaxMind-format (.mmdb) databases."""
import ipaddress
import mmap
import struct

_MARK = b"\xab\xcd\xefMaxMind.com"


class MMDB:
    def __init__(self, path):
        f = open(path, "rb")
        self.d = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        i = self.d.rfind(_MARK)
        if i < 0:
            raise ValueError("not an mmdb file")
        self.base = 0
        meta, _ = self._decode(i + len(_MARK))
        self.nodes = meta["node_count"]
        self.rs = meta["record_size"]
        self.v = meta["ip_version"]
        self.tree = self.nodes * self.rs * 2 // 8
        self.base = self.tree + 16
        self.cache = {}

    def _rec(self, node, bit):
        d, o = self.d, node * self.rs * 2 // 8
        if self.rs == 24:
            b = d[o + bit * 3:o + bit * 3 + 3]
            return int.from_bytes(b, "big")
        if self.rs == 28:
            b = d[o:o + 7]
            if bit == 0:
                return ((b[3] & 0xF0) << 20) | int.from_bytes(b[0:3], "big")
            return ((b[3] & 0x0F) << 24) | int.from_bytes(b[4:7], "big")
        return int.from_bytes(d[o + bit * 4:o + bit * 4 + 4], "big")

    def lookup(self, ip):
        if ip in self.cache:
            return self.cache[ip]
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if a.version == 4:
            bits, n = int(a), 32
            if self.v == 6:
                n = 128
        else:
            if self.v == 4:
                return None
            bits, n = int(a), 128
        node = 0
        res = None
        for i in range(n - 1, -1, -1):
            node = self._rec(node, (bits >> i) & 1)
            if node >= self.nodes:
                break
        if node > self.nodes:
            res, _ = self._decode(node - self.nodes + self.tree)
        self.cache[ip] = res
        return res

    def _decode(self, p):
        d = self.d
        c = d[p]
        p += 1
        t = c >> 5
        if t == 1:                                   # pointer
            ss, v = (c >> 3) & 3, c & 7
            if ss == 0:
                ptr = (v << 8) | d[p]
            elif ss == 1:
                ptr = 2048 + ((v << 16) | int.from_bytes(d[p:p + 2], "big"))
            elif ss == 2:
                ptr = 526336 + ((v << 24) | int.from_bytes(d[p:p + 3], "big"))
            else:
                ptr = int.from_bytes(d[p:p + 4], "big")
            val, _ = self._decode(self.base + ptr)
            return val, p + ss + 1
        if t == 0:
            t = 7 + d[p]
            p += 1
        size = c & 0x1F
        if size == 29:
            size = 29 + d[p]
            p += 1
        elif size == 30:
            size = 285 + int.from_bytes(d[p:p + 2], "big")
            p += 2
        elif size == 31:
            size = 65821 + int.from_bytes(d[p:p + 3], "big")
            p += 3
        if t == 7:                                   # map
            out = {}
            for _ in range(size):
                k, p = self._decode(p)
                out[k], p = self._decode(p)
            return out, p
        if t == 11:                                  # array
            out = []
            for _ in range(size):
                v, p = self._decode(p)
                out.append(v)
            return out, p
        if t == 14:
            return bool(size), p
        raw = d[p:p + size]
        p += size
        if t == 2:
            return raw.decode("utf-8", "replace"), p
        if t == 3:
            return struct.unpack(">d", raw)[0], p
        if t == 15:
            return struct.unpack(">f", raw)[0], p
        if t == 8:
            return int.from_bytes(raw, "big", signed=True), p
        if t in (5, 6, 9, 10):
            return int.from_bytes(raw, "big"), p
        return raw, p
