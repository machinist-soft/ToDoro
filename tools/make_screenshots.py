"""Скриншоты ToDoro для README: docs/screenshots/*.png и анимация Котобуса catbus.gif.

Снимает на отдельной временной базе с примерами задач — данные пользователя не попадают в кадр.
Окно на время съёмки встаёт поверх остальных; мышь лучше не трогать (~15 секунд).
Запуск из папки проекта:  python tools/make_screenshots.py
Нужен Pillow:  pip install pillow
"""
import ctypes
import sys
import tempfile
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import db  # noqa: E402

work = Path(tempfile.mkdtemp(prefix="todoro-shots-"))
out = ROOT / "docs" / "screenshots"
out.mkdir(parents=True, exist_ok=True)
dbfile = work / "shots.db"
for suffix in ("", "-journal"):
    Path(str(dbfile) + suffix).unlink(missing_ok=True)
db.DB_PATH = dbfile
db.OLD_DB_PATHS = []

import todoro as T  # noqa: E402
from examples import make_examples  # noqa: E402

conn = db.connect()
db.add_examples(conn, make_examples())
for key, value in (("update_auto", "0"), ("start_mode", "window"), ("view", "list"),
                   ("update_checked", "2099-01-01")):
    db.set_setting(conn, key, value)
with conn:
    conn.execute("UPDATE tasks SET reminded = 1")  # чтобы окно напоминания не попало в кадр
ids = {title: tid for tid, title, *_ in db.list_tasks(conn)}
conn.close()

root = tk.Tk()
app = T.TodoApp(root)
T.center_on_screen(root, 1440, 800)  # пошире, чтобы названия задач не обрезались
root.attributes("-topmost", True)
T.updater.can_self_update = lambda: True  # на снимке окна обновления — кнопка «Обновить»


def frame_box():
    """Окно вместе с заголовком, без невидимой тени Windows 10."""
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def grab(name, box=None):
    root.update()
    time.sleep(0.25)
    root.update()
    ImageGrab.grab(box or frame_box(), include_layered_windows=True).save(out / name, optimize=True)
    print("saved", name)


def select(title):
    app.select_task(ids[title])
    root.update()


def run():
    # 1. Список с Тоторо
    app.clear_selection()
    grab("list.png")
    # 2. Карточка задачи справа
    select("Сдать квартальный отчёт")
    grab("card.png")
    # 3. Форма изменения задачи
    select("Подготовить презентацию для клиента")
    app.edit()
    grab("form.png")
    app.cancel_edit()
    app.clear_selection()
    # 4. Доска
    app.view.set("board")
    app.switch_view()
    grab("board.png")
    app.view.set("list")
    app.switch_view()
    app.clear_selection()
    # 5. Окно обновления: последний выпущенный раздел RELEASE_NOTES.md («Не выпущено» пропускаем),
    # «текущая» версия — предыдущий выпуск (подменяется только для снимка)
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    sections = [part for part in notes.split("\n## ")[1:] if part[:1].isdigit()]
    version, section = sections[0].split(" ", 1)[0], sections[0].split("\n", 1)[1]
    T.APP_VERSION = sections[1].split(" ", 1)[0] if len(sections) > 1 else "—"
    dialog = T.UpdateDialog(root, dict(version=version, notes=section, url="", asset_url="x"), lambda: None)
    dialog.attributes("-topmost", True)
    root.update()
    time.sleep(0.4)
    dialog.update()
    hwnd = ctypes.windll.user32.GetParent(dialog.winfo_id())
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    grab("update.png", (rect.left, rect.top, rect.right, rect.bottom))
    dialog.destroy()
    # 6. Котобус: отмечаем задачу выполненной и снимаем кадры в отдельном потоке
    select("Купить продукты на неделю")
    box = frame_box()
    frames = []
    stop = threading.Event()

    def shoot():
        while not stop.is_set():
            t = time.perf_counter()
            frames.append(ImageGrab.grab(box, include_layered_windows=True))
            time.sleep(max(0, 1 / 15 - (time.perf_counter() - t)))

    shooter = threading.Thread(target=shoot)
    shooter.start()
    root.after(400, app.toggle)

    def finish():
        stop.set()
        shooter.join()
        make_gif(frames)
        root.destroy()
    root.after(400 + 150 + 4500 + 900, finish)


def make_gif(frames):
    width = 960
    small = [f.resize((width, round(f.height * width / f.width)), Image.LANCZOS) for f in frames]
    # одна общая палитра на все кадры — меньше файл и нет мерцания цветов
    palette = small[len(small) // 2].quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    gif = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in small]
    duration = round(1000 * 5.95 / len(gif))
    gif[0].save(out / "catbus.gif", save_all=True, append_images=gif[1:], duration=duration,
                loop=0, optimize=True, disposal=1)
    print("saved catbus.gif", len(gif), "frames", (out / "catbus.gif").stat().st_size // 1024, "KB")


root.after(1200, run)
root.mainloop()
