"""Рисует картинки для приложения: Тоторо (2 размера) и цветные метки приоритета."""
import math
import struct
import sys
import zlib
from pathlib import Path

BODY = (127, 135, 148)
BODY_DARK = (108, 116, 129)
BELLY = (243, 235, 216)
DARK = (31, 41, 55)
WHITE = (255, 255, 255)
LEAF = (34, 160, 107)


def ellipse(u, v, cx, cy, rx, ry, angle=0.0):
    dx, dy = u - cx, v - cy
    if angle:
        a = math.radians(angle)
        dx, dy = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
    return (dx / rx) ** 2 + (dy / ry) ** 2 <= 1


def segment(u, v, ax, ay, bx, by, w):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((u - ax) * dx + (v - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(u - ax - t * dx, v - ay - t * dy) <= w / 2


CHEVRONS = [(0.41, 0.555), (0.50, 0.555), (0.59, 0.555),
            (0.365, 0.635), (0.455, 0.635), (0.545, 0.635), (0.635, 0.635)]
WHISKERS = [((0.33, 0.415), (0.16, 0.385)), ((0.33, 0.44), (0.15, 0.44)),
            ((0.33, 0.465), (0.16, 0.495))]


def totoro(u, v):
    """Цвет точки (u, v) или None. Слои проверяются сверху вниз."""
    # лист на голове
    if segment(u, v, 0.5, 0.155, 0.5, 0.2, 0.012):
        return LEAF
    if ellipse(u, v, 0.5, 0.12, 0.11, 0.04, -18):
        return LEAF
    # усы
    for (ax, ay), (bx, by) in WHISKERS:
        if segment(u, v, ax, ay, bx, by, 0.009) or segment(u, v, 1 - ax, ay, 1 - bx, by, 0.009):
            return DARK
    # нос
    if ellipse(u, v, 0.5, 0.378, 0.036, 0.017):
        return DARK
    # глаза: зрачок, белок, обводка
    for cx, px in ((0.39, 0.402), (0.61, 0.598)):
        if ellipse(u, v, px, 0.343, 0.025, 0.025):
            return DARK
        if ellipse(u, v, cx, 0.34, 0.05, 0.05):
            return WHITE
        if ellipse(u, v, cx, 0.34, 0.058, 0.058):
            return DARK
    # «галочки» на животе
    for cx, cy in CHEVRONS:
        if (segment(u, v, cx - 0.032, cy + 0.02, cx, cy - 0.012, 0.017)
                or segment(u, v, cx, cy - 0.012, cx + 0.032, cy + 0.02, 0.017)):
            return BODY
    # живот
    if ellipse(u, v, 0.5, 0.745, 0.29, 0.29):
        return BELLY
    # лапы
    if ellipse(u, v, 0.135, 0.7, 0.07, 0.17, 12) or ellipse(u, v, 0.865, 0.7, 0.07, 0.17, -12):
        return BODY_DARK
    # тело, голова, уши
    if (ellipse(u, v, 0.5, 0.7, 0.42, 0.38) or ellipse(u, v, 0.5, 0.4, 0.3, 0.26)
            or ellipse(u, v, 0.33, 0.17, 0.06, 0.14, -12) or ellipse(u, v, 0.67, 0.17, 0.06, 0.14, 12)):
        return BODY
    return None


def render(shape, width, height, scale_v, ss=4):
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            r = g = b = n = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (x + (sx + 0.5) / ss) / width
                    v = (y + (sy + 0.5) / ss) / height * scale_v
                    c = shape(u, v)
                    if c:
                        r += c[0]; g += c[1]; b += c[2]; n += 1
            if n:
                row.append((r // n, g // n, b // n, round(255 * n / ss ** 2)))
            else:
                row.append((0, 0, 0, 0))
        rows.append(row)
    return rows


def png(pixels):
    h, w = len(pixels), len(pixels[0])
    raw = b"".join(b"\0" + bytes(c for p in row for c in p) for row in pixels)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def dot(color):
    return lambda u, v: color if (u - 0.5) ** 2 + (v - 0.5) ** 2 <= 0.16 else None


def rrect_dist(u, v, m, r):
    h = 0.5 - m
    qx, qy = abs(u - 0.5) - h + r, abs(v - 0.5) - h + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def checkbox(on):
    accent, border = (37, 99, 235), (184, 192, 204)

    def shape(u, v):
        d = rrect_dist(u, v, 0.03, 0.2)
        if d > 0:
            return None
        if on:
            if (segment(u, v, 0.27, 0.52, 0.43, 0.68, 0.13)
                    or segment(u, v, 0.43, 0.68, 0.74, 0.34, 0.13)):
                return WHITE
            return accent
        return border if d > -0.085 else WHITE
    return shape


def main(out):
    out = Path(out)
    out.mkdir(exist_ok=True)
    for name, w in (("totoro.png", 140), ("totoro_small.png", 46)):
        h = round(w * 1.1)
        (out / name).write_bytes(png(render(totoro, w, h, 1.1)))
    for level, color in ((1, (239, 68, 68)), (2, (245, 158, 11)), (3, (59, 130, 246))):
        (out / f"priority_{level}.png").write_bytes(png(render(dot(color), 14, 14, 1.0)))
    for name, on in (("check_off.png", False), ("check_on.png", True)):
        (out / name).write_bytes(png(render(checkbox(on), 18, 18, 1.0)))


if __name__ == "__main__":
    main(sys.argv[1])
