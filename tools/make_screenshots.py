"""Скриншоты ToDoro для README: docs/screenshots/*.png и анимация Котобуса catbus.gif.

Снимает на отдельных временных данных: личный список и общий список «Команда» с примерами задач
во временной «общей папке» — данные пользователя не попадают в кадр.
Окно на время съёмки встаёт поверх остальных; мышь лучше не трогать (~20 секунд).
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

DARK = "dark" in sys.argv[1:]  # python tools/make_screenshots.py dark — только снимок тёмной темы
MATRIX = "matrix" in sys.argv[1:]  # python tools/make_screenshots.py matrix — только снимок матрицы
work = Path(tempfile.mkdtemp(prefix="todoro-shots-"))
out = ROOT / "docs" / "screenshots"
out.mkdir(parents=True, exist_ok=True)
db.DATA_DIR = work
db.DB_PATH = work / "todoro.db"
db.LISTS_DIR = work / "lists"
db.OLD_DB_PATHS = []

# тема читается при загрузке todoro.py — записываем её до этого
db.set_setting(db.connect(), "theme", "dark" if DARK else "light")
import team  # noqa: E402
import todoro as T  # noqa: E402
from examples import make_examples  # noqa: E402

ME = "Андрей"
TEAM = ["Мария", "Олег", "Светлана"]
# кто создал и кому поручено (по заголовку примера); остальные — без исполнителя
PEOPLE = {
    "Оплатить интернет": ("Мария", ME),
    "Сдать квартальный отчёт": (ME, ME),
    "Подготовить презентацию для клиента": ("Олег", "Мария"),
    "Продлить страховку автомобиля": (ME, "Олег"),
    "Записаться к стоматологу": ("Светлана", None),
    "Ответить на письмо от бухгалтерии": ("Мария", "Светлана"),
    "Купить продукты на неделю": (ME, ME),
    "Разобрать фотографии с отпуска": ("Олег", None),
    "Подарки на Новый год": ("Светлана", "Мария"),
    "Позвонить маме": (ME, ME),
    "Забрать посылку на почте": ("Мария", "Олег"),
}

# Личный список (основной файл) — с примерами; ещё один личный список «Дом»
prefs = db.connect()
db.add_examples(prefs, make_examples())
db.save_registry(prefs, db.list_registry(prefs) + [{"id": "home", "name": "Дом", "file": "home.db"}])
db.connect(db.LISTS_DIR.mkdir(parents=True, exist_ok=True) or db.LISTS_DIR / "home.db").close()

# Общий список «Команда» во временной общей папке
share = team.Team(work / "share")
for name in [ME] + TEAM:
    share.touch_member(name)
item = share.add_list("Команда", ME)
share.add_list("Проект «Альфа»", "Мария")
shared = db.connect(share.path(item))
db.add_examples(shared, make_examples())
with shared:
    for title, (author, assignee) in PEOPLE.items():
        shared.execute("UPDATE tasks SET created_by = ?, assignee = ?, updated_by = ?, "
                       "updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime', '-1 hour') "
                       "WHERE title = ?", (author, assignee, author, title))
    shared.execute("UPDATE tasks SET reminded = 1")
ids = {title: tid for tid, title, *_ in db.list_tasks(shared)}
shared.close()
share.close()

for key, value in (("update_auto", "0"), ("start_mode", "window"), ("view", "list"),
                   ("update_checked", "2099-01-01"), ("shared_folder", str(work / "share")),
                   ("user_name", ME), ("current_list", item["id"]),
                   ("theme", "dark" if DARK else "light"), ("tour_show", "0")):
    db.set_setting(prefs, key, value)
# уже «видели» все назначенные задачи — чтобы окно «Вам назначены задачи» не попало в кадр
db.set_json_setting(prefs, "assigned_seen_lists", [item["id"]])
db.set_json_setting(prefs, "known_assigned", [f"{item['id']}|{tid}" for tid in ids.values()])
with prefs:
    prefs.execute("UPDATE tasks SET reminded = 1")
prefs.close()

T.TodoApp.check_reminders = lambda self: None  # окна напоминаний не должны попасть в кадр
root = tk.Tk()
app = T.TodoApp(root)
app.side.totoro.animate = False  # на снимках Тоторо не должен попасть моргающим
T.center_on_screen(root, 1560, 860)  # пошире, чтобы названия задач и все столбцы помещались
# ширины столбцов для снимка: место — названию задачи, остальным — по содержимому
for column, width in (("num", 48), ("status", 112), ("title", 268), ("priority", 128), ("due", 122),
                      ("remind", 112), ("assignee", 124), ("author", 90), ("created", 116)):
    app.tree.column(column, width=width)
app.columns_fitted = True
root.attributes("-topmost", True)
T.updater.can_self_update = lambda: True  # на снимке окна обновления — кнопка «Обновить»


def frame_box(window=None):
    """Окно вместе с заголовком, без невидимой тени Windows 10."""
    hwnd = ctypes.windll.user32.GetParent((window or root).winfo_id())
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def grab(name, box=None, window=None):
    """Снимок окна (по умолчанию главного). Координаты берём уже после того, как окно
    появилось на экране — иначе в кадр попадёт то, что под ним."""
    for _ in range(3):
        root.update()
        time.sleep(0.25)
    ImageGrab.grab(box or frame_box(window), include_layered_windows=True).save(out / name, optimize=True)
    print("saved", name)


def select(title):
    app.select_task(ids[title])
    root.update()


def run_dark():
    """Тёмная тема: доска общего списка."""
    for _ in range(6):
        root.update()
        time.sleep(0.2)
    app.view.set("board")
    app.switch_view()
    grab("dark.png")
    root.destroy()


def run_matrix():
    """Только матрица Эйзенхауэра."""
    for _ in range(6):
        root.update()
        time.sleep(0.2)
    app.view.set("matrix")
    app.switch_view()
    grab("matrix.png")
    root.destroy()


def run():
    # 1. Общий список команды с Тоторо: исполнители, авторы
    app.clear_selection()
    for _ in range(6):  # даём окну полностью перерисоваться после смены размера
        root.update()
        time.sleep(0.2)
    grab("list.png")
    # 2. Меню списков: личные и общие
    app.show_lists_menu()
    root.update()
    menu = [w for w in root.winfo_children() if isinstance(w, T._MenuWindow)][-1]
    menu.update()
    left, top, _, _ = frame_box()
    grab("lists.png", (left, top, left + 620, menu.winfo_rooty() + menu.winfo_height() + 16))
    menu.close()
    # 3. Карточка задачи справа
    select("Сдать квартальный отчёт")
    grab("card.png")
    # 4. Форма изменения задачи (с исполнителем)
    select("Подготовить презентацию для клиента")
    app.edit()
    grab("form.png")
    app.cancel_edit()
    app.clear_selection()
    # 5. Доска
    app.view.set("board")
    app.switch_view()
    grab("board.png")
    # 5б. Матрица Эйзенхауэра
    app.view.set("matrix")
    app.switch_view()
    grab("matrix.png")
    app.view.set("list")
    app.switch_view()
    app.clear_selection()
    # 6. Настройки — раздел «Совместная работа»
    dialog = T.SettingsDialog(root, "window", app.card_fields, True, r"\\server\Общая\ToDoro", ME,
                              ("ok", "Подключено. Участники: " + ", ".join([ME] + TEAM)), "sharing",
                              check_folder=app.check_folder, check_update=app.check_update_inline)
    T.center_on_screen(dialog)
    dialog.attributes("-topmost", True)
    grab("settings.png", window=dialog)
    dialog.destroy()
    # 7. Окно обновления: последний выпущенный раздел RELEASE_NOTES.md («Не выпущено» пропускаем),
    # «текущая» версия — предыдущий выпуск (подменяется только для снимка)
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    sections = [part for part in notes.split("\n## ")[1:] if part[:1].isdigit()]
    version, section = sections[0].split(" ", 1)[0], sections[0].split("\n", 1)[1]
    T.APP_VERSION = sections[1].split(" ", 1)[0] if len(sections) > 1 else "—"
    dialog = T.UpdateDialog(root, dict(version=version, notes=section, url="", asset_url="x"), lambda: None)
    dialog.attributes("-topmost", True)
    grab("update.png", window=dialog)
    dialog.destroy()
    # 8. Котобус: отмечаем задачу выполненной и снимаем кадры в отдельном потоке
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


root.after(1200, run_dark if DARK else run_matrix if MATRIX else run)
root.mainloop()
