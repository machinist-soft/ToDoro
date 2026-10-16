"""Рисует иконку приложения icon.ico в стиле Arduino IDE: бирюзовый закруглённый квадрат,
в нём белый силуэт Тоторо, на животе — галочка (список дел).

Запуск:  python tools/make_icon.py icon.ico preview.png
Для маленьких размеров (16–24 px) рисунок упрощается: без усов, галочка толще.
"""
import struct
import sys

from make_images import png, render, sd_ellipse, sd_round_rect, sd_segment, smin

BG = (0, 151, 140)      # бирюзовый фон
WHITE = (255, 255, 255)


def icon_shape(size):
    small = size <= 24
    check_w = 0.045 if small else 0.032

    def shape(u, v):
        if sd_round_rect(u, v, 0.03, 0.03, 0.97, 0.97, 0.2) >= 0:
            return None  # прозрачные углы
        # силуэт Тоторо: голова, тело, острые ушки
        head = sd_ellipse(u, v, 0.5, 0.42, 0.24, 0.19)
        body = sd_ellipse(u, v, 0.5, 0.64, 0.33, 0.25)
        ears = min(sd_ellipse(u, v, 0.37, 0.235, 0.038, 0.085, -10),
                   sd_ellipse(u, v, 0.63, 0.235, 0.038, 0.085, 10))
        silhouette = smin(smin(head, body, 0.08), ears, 0.03)
        if silhouette < 0:
            # живот — «окошко» цвета фона, в нём белая галочка
            if sd_ellipse(u, v, 0.5, 0.68, 0.2, 0.15) < 0:
                check = min(sd_segment(u, v, 0.41, 0.68, 0.475, 0.745),
                            sd_segment(u, v, 0.475, 0.745, 0.6, 0.61))
                return WHITE if check < check_w else BG
            # глаза
            if min(sd_ellipse(u, v, 0.42, 0.39, 0.03, 0.03), sd_ellipse(u, v, 0.58, 0.39, 0.03, 0.03)) < 0:
                return BG
            return WHITE
        # усы
        if not small:
            whiskers = min(sd_segment(u, v, 0.30, 0.44, 0.13, 0.41), sd_segment(u, v, 0.30, 0.48, 0.13, 0.50),
                           sd_segment(u, v, 0.70, 0.44, 0.87, 0.41), sd_segment(u, v, 0.70, 0.48, 0.87, 0.50))
            if whiskers < 0.012:
                return WHITE
        return BG
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
