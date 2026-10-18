"""Скриншоты ToDoro для README: docs/screenshots/*.png и анимация Котобуса catbus.gif.

Снимает на отдельных временных данных: личный список и общий список «Команда» с примерами задач
во временной «общей папке» — данные пользователя не попадают в кадр.
Окно на время съёмки встаёт поверх остальных; мышь лучше не трогать (~20 секунд).
Запуск из папки проекта:  python tools/make_screenshots.py
Нужен Pillow:  pip install pillow
"""
import ctypes
import io
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import db  # noqa: E402

DARK = "dark" in sys.argv[1:]  # python tools/make_screenshots.py dark — только снимок тёмной темы
MATRIX = "matrix" in sys.argv[1:]  # python tools/make_screenshots.py matrix — только снимок матрицы
WHATSNEW = "whatsnew" in sys.argv[1:]  # python tools/make_screenshots.py whatsnew — только «Что нового»
REMINDERS = "reminders" in sys.argv[1:]  # python tools/make_screenshots.py reminders — только напоминания
PHONE = "phone" in sys.argv[1:]  # python tools/make_screenshots.py phone — только «Подключить телефон»
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
# окно и так держится поверх всех на время съёмки; вывод вперёд при запуске снял бы это
T.TodoApp.raise_on_start = lambda self: None
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
# файлы и комментарии у задачи «Подготовить презентацию для клиента»
EXTRAS_TASK = "Подготовить презентацию для клиента"
with shared:  # вместо файлов и комментариев из примеров — командная переписка с именами
    shared.execute("DELETE FROM attachments")
    shared.execute("DELETE FROM comments")
sketch = Image.new("RGB", (640, 400), "#eef3fb")
for i, (height, color) in enumerate(((150, "#5b8def"), (240, "#7cc68d"), (190, "#f2b84b"), (300, "#e5735c"))):
    sketch.paste(color, (80 + i * 130, 360 - height, 160 + i * 130, 360))
board = Image.new("RGB", (640, 420), "#fdf6e3")
for i, color in enumerate(("#f7d26a", "#9fd3f5", "#f5a3a3", "#b6e3a8", "#d7b8f3", "#f7d26a")):
    board.paste(color, (60 + (i % 3) * 190, 50 + (i // 3) * 180, 210 + (i % 3) * 190, 190 + (i // 3) * 180))
for name, picture in (("Макет слайдов.png", sketch), ("Доска со встречи.png", board)):
    buffer = io.BytesIO()
    picture.save(buffer, "PNG")
    db.add_attachment(shared, ids[EXTRAS_TASK], name, buffer.getvalue(), "Олег")
db.add_attachment(shared, ids[EXTRAS_TASK], "Презентация для клиента.pptx", b"0" * 2_400_000, "Мария")
db.add_attachment(shared, ids[EXTRAS_TASK], "Смета.xlsx", b"0" * 48_000, ME)
for author, text in (("Олег", "Набросал макет слайдов — посмотрите, пожалуйста, во вкладке «Файлы»."),
                     ("Мария", "Хорошо! Добавлю цифры за квартал и пришлю к вечеру."),
                     (ME, "Смету приложил. Клиент просил уложиться в 15 минут.")):
    db.add_comment(shared, ids[EXTRAS_TASK], text, author)
# задача из письма Outlook — со значком 📧 в списке и на доске
db.set_mail_id(shared, ids["Ответить на письмо от бухгалтерии"], "<demo-buh@example.com>",
               "Бухгалтерия <buh@example.com>")
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


def shoot_whatsnew():
    """Окно «Что нового» (☰ Меню → О программе → Что нового)."""
    dialog = T.WhatsNewWindow(root)
    dialog.attributes("-topmost", True)
    grab("whatsnew.png", window=dialog)
    dialog.destroy()


def shoot_reminders():
    """Окно напоминаний (☰ Меню → Напоминания и просроченные): первая задача — «новое» напоминание.
    Окно модальное, поэтому вместо показа снимаем его и сразу закрываем."""
    show = T.AlertDialog.show

    def shoot(dialog):
        T.center_on_screen(dialog)
        dialog.attributes("-topmost", True)
        grab("reminders.png", window=dialog)
        dialog.destroy()
    T.AlertDialog.show = shoot
    # только открытый общий список: в личном — те же примеры, в кадре были бы одинаковые названия
    lists, app.lists = app.lists, [app.current_list()]
    # «завтра утром» — чтобы в окне было несколько задач, а не одна
    pending = db.pending_tasks
    T.db.pending_tasks = lambda conn, user=None: pending(conn, user, datetime.now() + timedelta(days=1))
    try:
        app.show_reminders(new=app.collect_pending()[:1])
    finally:
        T.AlertDialog.show = show
        T.db.pending_tasks = pending
        app.lists = lists


def shoot_phone():
    """☰ Меню → Подключить телефон, вкладка «1. Установить приложение». В кадре — QR-код со
    ссылкой на GitHub, а не код подключения: в том — адрес и имя компьютера и ключ."""
    T.phone.new_token(app.prefs)  # ключ во временной базе: окно показывает включённую связь
    dialog = T.PhoneDialog(root, app.prefs)
    dialog.show_qr("install")
    T.center_on_screen(dialog)
    dialog.attributes("-topmost", True)
    grab("phone.png", window=dialog)
    dialog.destroy()


def run_phone():
    for _ in range(4):
        root.update()
        time.sleep(0.2)
    shoot_phone()
    root.destroy()


def run_reminders():
    for _ in range(4):
        root.update()
        time.sleep(0.2)
    shoot_reminders()
    root.destroy()


def run_whatsnew():
    for _ in range(4):
        root.update()
        time.sleep(0.2)
    shoot_whatsnew()
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
    # 4б. Вкладки «Файлы» и «Комментарии» в карточке задачи
    select(EXTRAS_TASK)
    card = app.side.card
    for tab, name in (("files", "files.png"), ("comments", "comments.png")):
        card.tab.set(tab)
        card.show_tab()
        grab(name)
    card.tab.set("body")
    card.show_tab()
    app.clear_selection()
    # 4в. Новая задача из письма Outlook (письмо выдуманное — настоящий Outlook не нужен)
    friday = T.date.today() + T.timedelta(days=(4 - T.date.today().weekday()) % 7 or 7)
    mail = dict(title="Согласовать договор с поставщиком", important=True,
                body="От: Ирина Ковалёва <i.kovaleva@example.com>, " + T.date.today().strftime("%d.%m.%Y")
                     + " 09:14\n\nДобрый день!\n\nПросьба согласовать договор поставки до пятницы. "
                       "Проект договора — во вложении.\n\nС уважением,\nИрина",
                due_at=friday.strftime("%Y-%m-%d 18:00"), mail_id="<demo@example.com>", entry_id="",
                store_id="", mail_from="Ирина Ковалёва <i.kovaleva@example.com>",
                files=[("Согласовать договор с поставщиком.msg", b"0"), ("Договор поставки.docx", b"0")])
    T.outlook.read_selected = lambda: [mail]

    def shoot_mail():
        dialog = next((w for w in root.winfo_children() if isinstance(w, T.TaskDialog)), None)
        if dialog is None:
            root.after(100, shoot_mail)
            return
        dialog.attributes("-topmost", True)
        grab("outlook.png", window=dialog)
        dialog.destroy()  # «Отмена»: задачу не создаём

    root.after(300, shoot_mail)
    app.from_outlook()
    root.attributes("-topmost", True)
    # 4г. Новая задача со снимка экрана: «снимок» — кусок списка задач этого же окна
    for _ in range(4):  # окно письма из прошлого шага должно успеть исчезнуть с экрана
        root.update()
        time.sleep(0.25)
    x, y = app.main_widget().winfo_rootx(), app.main_widget().winfo_rooty()
    picture = ImageGrab.grab((x, y, x + 760, y + 230))
    T.snip.select_area = lambda master: picture

    def shoot_snip():
        dialog = next((w for w in root.winfo_children() if isinstance(w, T.TaskDialog)), None)
        if dialog is None:
            root.after(100, shoot_snip)
            return
        dialog.form.title_entry.insert(0, "Проверить сроки задач команды")
        dialog.attributes("-topmost", True)
        grab("snip.png", window=dialog)
        dialog.destroy()  # «Отмена»: задачу не создаём

    root.after(300, shoot_snip)
    app.from_screen()
    root.attributes("-topmost", True)
    # 4д. Умные подсказки: варианты названия из прошлых задач под полем ввода
    app.entry.focus_force()
    app.hide_placeholder()
    app.entry.insert(0, "По")
    app.title_suggest.update()
    app.title_suggest.move(1)
    popup = app.title_suggest.popup
    popup.update()
    left, top, right, _ = frame_box()
    grab("smart.png", (left, top, right, popup.winfo_rooty() + popup.winfo_height() + 16))
    app.title_suggest.close()
    app.entry.delete(0, "end")
    app.show_placeholder()
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
    # 5в. Ознакомительный тур: шаг «Список, доска и матрица»
    app.start_tour()
    tour = app.tour
    for window in (tour.tip, tour.frame):
        if window:
            window.attributes("-topmost", True)  # главное окно на время съёмки — поверх всех
    tour.hide_next.set(False)  # на снимке — как при первом запуске: галочка не стоит
    tour.index = next(i for i, step in enumerate(tour.steps) if step[1] == "Список, доска и матрица")
    tour.show_step()
    grab("tour.png")
    tour.hide_next.set(True)  # не меняем настройку: в базе для снимков тур и так выключен
    tour.close()
    # 6. Настройки — раздел «Совместная работа»
    dialog = T.SettingsDialog(root, "window", app.card_fields, True, r"\\server\Общая\ToDoro", ME,
                              ("ok", "Подключено. Участники: " + ", ".join([ME] + TEAM)), "sharing",
                              check_folder=app.check_folder, check_update=app.check_update_inline)
    T.center_on_screen(dialog)
    dialog.attributes("-topmost", True)
    grab("settings.png", window=dialog)
    dialog.destroy()
    # 6б. «О программе»: логотип Machinist Soft (снимаем до шага 7 — там подменяется APP_VERSION)
    dialog = T.AboutWindow(root, lambda: None)
    dialog.attributes("-topmost", True)
    grab("about.png", window=dialog)
    dialog.destroy()
    shoot_whatsnew()
    shoot_reminders()
    shoot_phone()
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


root.after(1200, run_dark if DARK else run_matrix if MATRIX else run_whatsnew if WHATSNEW
           else run_reminders if REMINDERS else run_phone if PHONE else run)
root.mainloop()
