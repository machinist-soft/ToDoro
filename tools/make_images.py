"""Рисует картинки для приложения: Тоторо, Котобус, цветные метки приоритета, галочки.

Запуск:  python tools/make_images.py images
Все фигуры заданы формулами (эллипсы, отрезки), картинка сглаживается
за счёт подсчёта 4×4 точек на каждый пиксель.
"""
import math
import struct
import sys
import zlib
from pathlib import Path

WHITE = (255, 255, 255)
OUTLINE = (40, 42, 48)

# --- Тоторо ---
T_BODY = (104, 110, 120)
T_BODY_DARK = (84, 89, 98)
T_BELLY = (232, 219, 184)
T_CLAW = (238, 232, 214)
T_LEAF = (52, 150, 84)

# --- Котобус ---
C_FUR = (230, 164, 76)
C_STRIPE = (164, 98, 42)
C_ROOF = (204, 136, 60)
C_WINDOW = (250, 236, 176)
C_EYE = (248, 230, 70)
C_NOSE = (226, 118, 118)
C_OUTLINE = (66, 42, 24)


# ---------- формулы фигур ----------

def rotate(dx, dy, angle):
    if not angle:
        return dx, dy
    a = math.radians(angle)
    return dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)


def sd_ellipse(u, v, cx, cy, rx, ry, angle=0.0):
    """Примерное расстояние до края эллипса: <0 внутри, >0 снаружи."""
    dx, dy = rotate(u - cx, v - cy, angle)
    return (math.hypot(dx / rx, dy / ry) - 1) * min(rx, ry)


def sd_segment(u, v, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((u - ax) * dx + (v - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(u - ax - t * dx, v - ay - t * dy)


def sd_round_rect(u, v, x1, y1, x2, y2, r):
    cx, cy, hx, hy = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) / 2, (y2 - y1) / 2
    qx, qy = abs(u - cx) - hx + r, abs(v - cy) - hy + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def smin(a, b, k):
    """Плавное объединение двух фигур (без резкого угла в месте стыка)."""
    h = max(k - abs(a - b), 0) / k
    return min(a, b) - h * h * k / 4


def outlined(d, fill, width, line=OUTLINE):
    """Фигура с контуром: цвет контура у края, заливка внутри."""
    if d > 0:
        return None
    return line if d > -width else fill


# ---------- Тоторо (сидит, вид спереди) ----------

T_CHEVRONS = [(0.41, 0.515), (0.50, 0.505), (0.59, 0.515),
              (0.36, 0.595), (0.453, 0.585), (0.547, 0.585), (0.64, 0.595)]
T_WHISKERS = [((0.37, 0.305), (0.10, 0.27)), ((0.37, 0.325), (0.08, 0.325)),
              ((0.37, 0.345), (0.10, 0.385))]


def totoro(u, v):
    ow = 0.011  # толщина контура
    # листок на голове
    if sd_segment(u, v, 0.5, 0.075, 0.5, 0.115) < 0.007:
        return OUTLINE
    leaf = sd_ellipse(u, v, 0.5, 0.06, 0.085, 0.03, -12)
    if leaf < 0:
        return outlined(leaf, T_LEAF, ow * 0.8)
    # усы
    for (ax, ay), (bx, by) in T_WHISKERS:
        if sd_segment(u, v, ax, ay, bx, by) < 0.0045 or sd_segment(u, v, 1 - ax, ay, 1 - bx, by) < 0.0045:
            return OUTLINE
    # нос
    if sd_ellipse(u, v, 0.5, 0.305, 0.032, 0.012) < 0:
        return OUTLINE
    # глаза
    for cx in (0.385, 0.615):
        px = cx + (0.008 if cx < 0.5 else -0.008)
        if sd_ellipse(u, v, px, 0.262, 0.019, 0.019) < 0:
            return OUTLINE
        eye = sd_ellipse(u, v, cx, 0.26, 0.042, 0.042)
        if eye < 0:
            return outlined(eye, WHITE, ow)
    # «галочки» на животе (дуги вверх)
    for cx, cy in T_CHEVRONS:
        r = math.hypot(u - cx, v - cy)
        if v < cy + 0.004 and abs(r - 0.032) < 0.0085:
            return T_BODY_DARK
    # живот
    belly = sd_ellipse(u, v, 0.5, 0.71, 0.33, 0.31)
    if belly < 0:
        return outlined(belly, T_BELLY, ow)
    # когти на лапах-ступнях
    for fx in (0.29, 0.71):
        for i, dx in enumerate((-0.05, 0.0, 0.05)):
            if sd_ellipse(u, v, fx + dx, 0.975 - (0.008 if i == 1 else 0), 0.016, 0.026) < 0:
                return T_CLAW
    # ступни
    for fx in (0.29, 0.71):
        foot = sd_ellipse(u, v, fx, 1.02, 0.135, 0.075)
        if foot < 0:
            return outlined(foot, T_BODY_DARK, ow)
    # когти на руках
    for ax, sign in ((0.085, 1), (0.915, -1)):
        for dx in (-0.02, 0.0, 0.02):
            if sd_ellipse(u, v, ax + dx * sign, 0.86, 0.009, 0.02) < 0:
                return T_CLAW
    # силуэт: голова + тело + уши + руки
    head = sd_ellipse(u, v, 0.5, 0.27, 0.25, 0.2)
    body = sd_ellipse(u, v, 0.5, 0.68, 0.43, 0.36)
    ears = min(sd_ellipse(u, v, 0.36, 0.1, 0.04, 0.11, -10),
               sd_ellipse(u, v, 0.64, 0.1, 0.04, 0.11, 10))
    arms = min(sd_ellipse(u, v, 0.1, 0.7, 0.07, 0.19, 12),
               sd_ellipse(u, v, 0.9, 0.7, 0.07, 0.19, -12))
    silhouette = min(smin(smin(head, body, 0.08), ears, 0.03), arms)
    if silhouette > 0:
        return None
    if silhouette > -ow:
        return OUTLINE
    if -ow < arms <= 0 and body < 0:
        return OUTLINE  # линия, отделяющая руку от тела
    shade = 0.92 + 0.08 * (1 - v)  # сверху чуть светлее
    return tuple(min(255, round(c * shade)) for c in T_BODY)


# ---------- Котобус (вид сбоку, голова слева) ----------

C_LEGS = [0.35, 0.46, 0.57, 0.68, 0.79]
C_WINDOWS = [0.41 + i * 0.09 for i in range(5)]


def catbus(u, v):
    ow = 0.008
    # усы
    for (ax, ay), (bx, by) in (((0.09, 0.36), (0.0, 0.33)), ((0.09, 0.385), (0.0, 0.39)),
                               ((0.09, 0.41), (0.01, 0.45))):
        if sd_segment(u, v, ax, ay, bx, by) < 0.004:
            return C_OUTLINE
    # зрачки-щёлочки и глаза
    for ex in (0.15, 0.255):
        if sd_ellipse(u, v, ex, 0.30, 0.008, 0.03) < 0:
            return C_OUTLINE
        eye = sd_ellipse(u, v, ex, 0.30, 0.041, 0.041)
        if eye < 0:
            return outlined(eye, C_EYE, ow, C_OUTLINE)
    # нос
    if sd_ellipse(u, v, 0.203, 0.352, 0.017, 0.011) < 0:
        return C_NOSE
    # улыбка с зубами
    grin = sd_ellipse(u, v, 0.203, 0.395, 0.125, 0.075)
    if grin < 0 and v >= 0.385:
        if grin > -ow or v < 0.385 + ow:
            return C_OUTLINE
        if any(abs(u - tx) < 0.0035 for tx in (0.13, 0.165, 0.203, 0.241, 0.276)):
            return C_OUTLINE
        return WHITE
    # полоски на лбу
    for sx, sy in ((0.203, 0.215), (0.172, 0.225), (0.234, 0.225)):
        if sd_ellipse(u, v, sx, sy, 0.011, 0.03) < 0:
            return C_STRIPE
    # голова с ушами
    head = smin(sd_ellipse(u, v, 0.203, 0.32, 0.155, 0.14),
                min(sd_ellipse(u, v, 0.09, 0.19, 0.035, 0.085, -28),
                    sd_ellipse(u, v, 0.315, 0.18, 0.035, 0.085, 24)), 0.03)
    if head < 0:
        return outlined(head, C_FUR, ow, C_OUTLINE)
    # окна
    for wx in C_WINDOWS:
        win = sd_round_rect(u, v, wx, 0.15, wx + 0.075, 0.29, 0.015)
        if win < 0:
            return outlined(win, C_WINDOW, ow * 1.3, C_OUTLINE)
    # полоски на боку
    for sx in (0.5, 0.63, 0.76):
        if sd_ellipse(u, v, sx, 0.4, 0.016, 0.06, 12) < 0 and v < 0.48:
            return C_STRIPE
    # кузов: скруглённый, с выгнутой крышей
    body = smin(sd_round_rect(u, v, 0.27, 0.12, 0.9, 0.49, 0.14),
                sd_ellipse(u, v, 0.6, 0.2, 0.31, 0.13), 0.06)
    if body < 0:
        if body > -ow:
            return C_OUTLINE
        return C_ROOF if v < 0.115 else C_FUR
    # лапы с подушечками, чуть наклонены — будто бежит
    for i, lx in enumerate(C_LEGS):
        tilt = 14 if i % 2 else -10
        leg = smin(sd_ellipse(u, v, lx, 0.525, 0.032, 0.075, tilt),
                   sd_ellipse(u, v, lx - 0.006, 0.595, 0.042, 0.022), 0.02)
        if leg < 0:
            if leg > -ow:
                return C_OUTLINE
            return C_STRIPE if 0.535 < v < 0.557 else C_FUR
    # пушистый хвост
    tail = sd_ellipse(u, v, 0.935, 0.23, 0.04, 0.11, -25)
    if tail < 0:
        if tail > -ow:
            return C_OUTLINE
        return C_STRIPE if int((v - 0.13) / 0.045) % 2 else C_FUR
    return None


# ---------- значки ----------

def dot(color):
    return lambda u, v: color if (u - 0.5) ** 2 + (v - 0.5) ** 2 <= 0.16 else None


def checkbox(on):
    accent, border = (37, 99, 235), (184, 192, 204)

    def shape(u, v):
        d = sd_round_rect(u, v, 0.03, 0.03, 0.97, 0.97, 0.2)
        if d > 0:
            return None
        if on:
            if sd_segment(u, v, 0.27, 0.52, 0.43, 0.68) < 0.065 or sd_segment(u, v, 0.43, 0.68, 0.74, 0.34) < 0.065:
                return WHITE
            return accent
        return border if d > -0.085 else WHITE
    return shape


# ---------- растеризация и PNG ----------

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
            row.append((r // n, g // n, b // n, round(255 * n / ss ** 2)) if n else (0, 0, 0, 0))
        rows.append(row)
    return rows


def png(pixels):
    h, w = len(pixels), len(pixels[0])
    raw = b"".join(b"\0" + bytes(c for p in row for c in p) for row in pixels)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main(out):
    out = Path(out)
    out.mkdir(exist_ok=True)
    for name, w in (("totoro.png", 170), ("totoro_small.png", 50)):
        (out / name).write_bytes(png(render(totoro, w, round(w * 1.1), 1.1)))
    # Котобус нарисован мордой влево, в приложении он едет вправо — отражаем
    (out / "catbus.png").write_bytes(png(render(lambda u, v: catbus(1 - u, v), 112, 72, 0.643)))
    for level, color in ((1, (239, 68, 68)), (2, (245, 158, 11)), (3, (59, 130, 246))):
        (out / f"priority_{level}.png").write_bytes(png(render(dot(color), 14, 14, 1.0)))
    for name, on in (("check_off.png", False), ("check_on.png", True)):
        (out / name).write_bytes(png(render(checkbox(on), 18, 18, 1.0)))


if __name__ == "__main__":
    main(sys.argv[1])
