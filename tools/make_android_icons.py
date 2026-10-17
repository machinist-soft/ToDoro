"""Рисует значки приложения для Android (тот же рисунок, что и icon.ico) в android/app/src/main/res.

Запуск из папки проекта:  python tools/make_android_icons.py
"""
from pathlib import Path

from make_icon import icon_shape
from make_images import png, render

RES = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "res"
DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}


def main():
    for density, size in DENSITIES.items():
        folder = RES / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ic_launcher.png").write_bytes(png(render(icon_shape(size), size, size, 1.0)))


if __name__ == "__main__":
    main()
