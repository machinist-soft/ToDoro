"""Рисует картинки приложения для Android в android/app/src/main/res: значок (тот же рисунок,
что и icon.ico) и Тоторо-помощника (те же рисунки, что в окне ToDoro, но в двойном размере —
на экране телефона точек больше).

Запуск из папки проекта:  python tools/make_android_icons.py
"""
from pathlib import Path

from make_icon import icon_shape
from make_images import png, render, totoro

RES = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "res"
DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
# выражения Тоторо — как в make_images.py (правая панель окна ToDoro)
FACES = {
    "totoro": {},
    "totoro_happy": dict(eyes="happy", mouth="smile", arms="up"),
    "totoro_worried": dict(eyes="wide", mouth="o"),
    "totoro_sleep": dict(eyes="closed"),
}


def main():
    for density, size in DENSITIES.items():
        folder = RES / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ic_launcher.png").write_bytes(png(render(icon_shape(size), size, size, 1.0)))
    folder = RES / "drawable-nodpi"
    folder.mkdir(parents=True, exist_ok=True)
    for name, face in FACES.items():
        (folder / f"{name}.png").write_bytes(
            png(render(lambda u, v, f=face: totoro(u, v, **f), 340, 374, 1.1)))


if __name__ == "__main__":
    main()
