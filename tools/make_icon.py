"""Рисует иконку (синяя плитка с белой галочкой) и сохраняет icon.ico + preview.png."""
import math
import struct
import sys
import zlib

TOP = (0x4F, 0x8D, 0xF7)
BOTTOM = (0x1D, 0x4E, 0xD8)
CHECK = [(0.28, 0.53), (0.44, 0.69), (0.74, 0.36)]


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def rrect_dist(px, py, m, r):
    # signed distance to rounded square [m, 1-m]
    cx = cy = 0.5
    h = 0.5 - m
    qx, qy = abs(px - cx) - h + r, abs(py - cy) - h + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def render(size):
    ss = 4
    thick = 0.095 if size >= 32 else 0.12
    m = 0.04 if size >= 32 else 0.0
    rad = 0.22
    px = []
    for y in range(size):
        row = []
        for x in range(size):
            cov_bg = cov_ck = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (x + (sx + 0.5) / ss) / size
                    v = (y + (sy + 0.5) / ss) / size
                    if rrect_dist(u, v, m, rad) <= 0:
                        cov_bg += 1
                        d = min(seg_dist(u, v, *CHECK[0], *CHECK[1]),
                                seg_dist(u, v, *CHECK[1], *CHECK[2]))
                        if d <= thick / 2:
                            cov_ck += 1
            n = ss * ss
            if cov_bg == 0:
                row.append((0, 0, 0, 0))
                continue
            t = (y + 0.5) / size
            base = [TOP[i] + (BOTTOM[i] - TOP[i]) * t for i in range(3)]
            k = cov_ck / cov_bg
            col = [round(base[i] * (1 - k) + 255 * k) for i in range(3)]
            row.append((*col, round(255 * cov_bg / n)))
        px.append(row)
    return px


def png(pixels):
    h, w = len(pixels), len(pixels[0])
    raw = b"".join(b"\0" + bytes(c for p in row for c in p) for row in pixels)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def dib(pixels):
    h, w = len(pixels), len(pixels[0])
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    xor = b"".join(bytes((b, g, r, a)) for row in reversed(pixels) for (r, g, b, a) in row)
    and_mask = b"\0" * (((w + 31) // 32) * 4 * h)
    return header + xor + and_mask


def main(out_ico, out_png):
    sizes = [16, 20, 24, 32, 40, 48, 64, 256]
    images = []
    for s in sizes:
        p = render(s)
        images.append(png(p) if s == 256 else dib(p))
        if s == 256:
            open(out_png, "wb").write(images[-1])
    offset = 6 + 16 * len(sizes)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    open(out_ico, "wb").write(head + entries + b"".join(images))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
