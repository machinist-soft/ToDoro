"""Рисует иконку приложения icon.ico: Тоторо, у которого живот — листок со списком дел.

Запуск:  python tools/make_icon.py icon.ico preview.png
Для маленьких размеров (16–24 px) рисунок упрощается: меньше деталей и строк в списке.
"""
import struct
import sys

from make_images import (OUTLINE, T_BODY, WHITE, outlined, png, render, sd_ellipse,
                         sd_round_rect, sd_segment, smin)

PAPER = (252, 250, 242)
LINE = (170, 176, 186)
CHECK = (34, 160, 90)


def icon_shape(size):
    small = size <= 24
    ow = 0.06 if small else 0.035 if size <= 48 else 0.022
    rows = (0.64, 0.82) if small else (0.6, 0.72, 0.84)

    def shape(u, v):
        # строки списка: квадратик с галочкой (или пустой) и линия текста
        for i, ry in enumerate(rows):
            checked = i < len(rows) - 1
            box = sd_round_rect(u, v, 0.29, ry - 0.045, 0.38, ry + 0.045, 0.015)
            if checked and (sd_segment(u, v, 0.30, ry, 0.33, ry + 0.035) < ow * 0.6
                            or sd_segment(u, v, 0.33, ry + 0.035, 0.40, ry - 0.05) < ow * 0.6):
                return CHECK
            if box < 0:
                return OUTLINE if box > -ow * 0.7 else PAPER
            if sd_segment(u, v, 0.45, ry, 0.70 - 0.06 * i, ry) < ow * 0.55:
                return LINE
        # листок-живот
        paper = sd_round_rect(u, v, 0.22, 0.5, 0.78, 0.93, 0.07)
        if paper < 0:
            return outlined(paper, PAPER, ow)
        # глаза и нос
        for cx in (0.37, 0.63):
            if not small and sd_ellipse(u, v, cx + (0.012 if cx < 0.5 else -0.012), 0.335, 0.03, 0.03) < 0:
                return OUTLINE
            eye = sd_ellipse(u, v, cx, 0.33, 0.065 if not small else 0.075, 0.065 if not small else 0.075)
            if eye < 0:
                return OUTLINE if small else outlined(eye, WHITE, ow * 0.8)
        if not small and sd_ellipse(u, v, 0.5, 0.41, 0.045, 0.02) < 0:
            return OUTLINE
        # силуэт Тоторо: голова, тело, уши
        head = sd_ellipse(u, v, 0.5, 0.42, 0.37, 0.3)
        body = sd_ellipse(u, v, 0.5, 0.7, 0.47, 0.29)
        ears = min(sd_ellipse(u, v, 0.31, 0.15, 0.065, 0.15, -12),
                   sd_ellipse(u, v, 0.69, 0.15, 0.065, 0.15, 12))
        silhouette = smin(smin(head, body, 0.1), ears, 0.05)
        if silhouette < 0:
            return outlined(silhouette, T_BODY, ow)
        return None
    return shape


def dib(pixels):
    """Картинка в формате BMP внутри .ico (для размеров меньше 256)."""
    h, w = len(pixels), len(pixels[0])
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    xor = b"".join(bytes((b, g, r, a)) for row in reversed(pixels) for (r, g, b, a) in row)
    and_mask = b"\0" * (((w + 31) // 32) * 4 * h)
    return header + xor + and_mask


def main(out_ico, out_png):
    sizes = [16, 20, 24, 32, 40, 48, 64, 256]
    images = []
    for s in sizes:
        pixels = render(icon_shape(s), s, s, 1.0)
        images.append(png(pixels) if s == 256 else dib(pixels))
        if s == 256:
            with open(out_png, "wb") as f:
                f.write(images[-1])
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(out_ico, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)) + entries + b"".join(images))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
