"""ToDoro — список дел с Тоторо."""
import calendar
import csv
import ctypes
import math
import os
import re
import tempfile
import threading
import time as time_module
import tkinter as tk
import webbrowser
from email import policy as email_policy
from email.message import EmailMessage
from urllib.parse import quote
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

import db
import updater
from examples import make_examples
from help_text import HELP

APP_NAME = "ToDoro"  # ToDo + Totoro
APP_VERSION = "1.4"  # номер версии — меняется здесь (установщик берёт его отсюда)
APP_YEAR = 2026
COPYRIGHT_HOLDER = "Machinist"  # автор — имя меняется здесь и в файле LICENSE
COPYRIGHT = f"© {APP_YEAR} {COPYRIGHT_HOLDER}"
LICENSE_PATH = Path(__file__).with_name("LICENSE")
LICENSE_SUMMARY = (
    "Программа распространяется по лицензии MIT — это свободная лицензия открытого кода:\n"
    "• пользоваться можно бесплатно, в том числе в работе и в коммерческих целях;\n"
    "• можно копировать, изменять, дополнять и распространять — целиком или частями;\n"
    "• единственное условие: сохранять указание автора (строку «Copyright (c) "
    f"{APP_YEAR} {COPYRIGHT_HOLDER}») и текст лицензии во всех копиях;\n"
    "• программа предоставляется «как есть», без каких-либо гарантий."
)
GHIBLI_NOTE = (
    "Тоторо и Котобус — персонажи студии Ghibli (© Studio Ghibli). Их изображения "
    "в программе — любительские рисунки; лицензия MIT на самих персонажей не распространяется. "
    "Программа не связана со студией Ghibli и не одобрена ею."
)
PROJECT_URL = updater.PROJECT_URL  # страница проекта на GitHub
ICON_PATH = Path(__file__).with_name("icon.ico")
IMAGES_DIR = Path(__file__).with_name("images")

# Шрифты
FONT = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 11)
FONT_TITLE = ("Segoe UI Semibold", 20)

# Палитра
BG = "#f4f6fb"            # фон окна
SURFACE = "#ffffff"       # карточки, поля ввода
BORDER = "#e3e7ef"
TEXT = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
ACCENT_SOFT = "#e8efff"   # выделенная строка, наведение
DANGER = "#dc2626"
DONE = "#9ca3af"
SEGMENT_BG = "#e7ebf3"

# Варианты фильтра: подпись кнопки -> какие задачи показывать
FILTERS = {
    "Все": None,
    "Активные": False,
    "Выполненные": True,
    "Просроченные": "overdue",  # невыполненные с прошедшим сроком
}
EMPTY_TEXT = {
    "Все": "Задач пока нет — добавьте первую в поле выше",
    "Активные": "Все задачи выполнены 🎉",
    "Выполненные": "Выполненных задач пока нет",
    "Просроченные": "Просроченных задач нет — всё успеваете 🎉",
}
BUDDY_MAX_TASKS = 5  # сколько просроченных задач Тоторо называет в облачке

# Варианты напоминания: подпись -> за сколько минут до срока напомнить
REMIND_OPTIONS = {
    "Не напоминать": None,
    "за 5 минут": 5,
    "за 15 минут": 15,
    "за 30 минут": 30,
    "за 1 час": 60,
    "за 2 часа": 120,
    "за 1 день": 24 * 60,
    "за 2 дня": 2 * 24 * 60,
    "за 1 неделю": 7 * 24 * 60,
}
REMIND_LABELS = {minutes: label for label, minutes in REMIND_OPTIONS.items()}

# Приоритет по матрице Эйзенхауэра: из «срочно» и «важно» получается 4 уровня.
# 1 — срочно и важно, 2 — важно, 3 — срочно, 4 — ни то ни другое.
PRIORITY_NAMES = {1: "Срочно и важно", 2: "Важно", 3: "Срочно", 4: ""}
PRIORITY_HINTS = {
    1: "сделать в первую очередь",
    2: "запланировать",
    3: "сделать быстро или поручить",
    4: "можно отложить",
}


def priority_level(urgent, important):
    if urgent and important:
        return 1
    if important:
        return 2
    if urgent:
        return 3
    return 4


# Варианты сортировки
SORTS = ["По приоритету", "По сроку", "По порядку добавления"]

IMAGES = {}  # картинки из папки images: Тоторо и цветные метки приоритета


def load_images():
    for path in IMAGES_DIR.glob("*.png"):
        IMAGES[path.stem] = tk.PhotoImage(file=str(path))
    # Свои картинки для галочек: стандартная в этой теме выглядит как крестик.
    style = ttk.Style()
    if "check_on" in IMAGES and "Nice.indicator" not in style.element_names():
        style.element_create("Nice.indicator", "image", IMAGES["check_off"],
                             ("selected", IMAGES["check_on"]), sticky="w", width=26)
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Nice.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.label", {"side": "left", "sticky": "nswe"})]})])

DEFAULT_TIME = ("09", "00")  # время срока по умолчанию
CHECK_EVERY_MS = 30_000      # как часто проверять напоминания (30 секунд)

HOURS = [f"{h:02d}" for h in range(24)]
MINUTES = [f"{m:02d}" for m in range(0, 60, 5)]
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
          "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

PLACEHOLDER = "Заголовок новой задачи… (Enter — добавить)"
# Длиннее ссылку «создать письмо» (mailto:) почтовые программы могут не принять:
# Outlook ломался уже на ~1700 символах (русская буква в ссылке занимает 6 символов).
MAILTO_LIMIT = 1000
DRAFTS_DIR = Path(tempfile.gettempdir()) / APP_NAME  # временные черновики писем (.eml)


def setup_style(root):
    """Внешний вид всех элементов: плоские кнопки, светлый фон, акцентный синий."""
    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    root.option_add("*Menu.font", FONT_SMALL)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".", background=BG, foreground=TEXT, font=FONT,
        bordercolor=BORDER, lightcolor=BG, darkcolor=BG, focuscolor=BG,
        troughcolor=BG, selectbackground=ACCENT, selectforeground="white",
    )
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED, font=FONT_SMALL)
    style.configure("Muted.TLabel", foreground=MUTED, font=FONT_SMALL)
    style.configure("Title.TLabel", font=FONT_TITLE)
    style.configure("Empty.TLabel", background=SURFACE, foreground=MUTED, font=FONT)

    # Кнопки: основная (синяя), обычная (белая с рамкой), опасная (красный текст)
    flat = dict(borderwidth=1, relief="flat", padding=(14, 7), font=FONT_SMALL)
    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                    focuscolor=ACCENT, **flat)
    style.map("Accent.TButton",
              background=[("pressed", "#1e40af"), ("active", ACCENT_HOVER)],
              bordercolor=[("active", ACCENT_HOVER)],
              lightcolor=[("active", ACCENT_HOVER)], darkcolor=[("active", ACCENT_HOVER)],
              focuscolor=[("active", ACCENT_HOVER)])
    style.configure("TButton", background=SURFACE, foreground=TEXT,
                    lightcolor=SURFACE, darkcolor=SURFACE, focuscolor=SURFACE, **flat)
    style.map("TButton",
              background=[("pressed", "#e5e7eb"), ("active", "#f3f5f9")],
              lightcolor=[("active", "#f3f5f9")], darkcolor=[("active", "#f3f5f9")],
              focuscolor=[("active", "#f3f5f9")])
    style.configure("Danger.TButton", foreground=DANGER)
    for name, fg, bg, hover in (("AccentSoft", ACCENT, ACCENT_SOFT, "#dbe6ff"),
                                ("DangerSoft", DANGER, "#fdf0f0", "#fbe1e1")):
        style.configure(f"{name}.TButton", foreground=fg, background=bg, lightcolor=bg,
                        darkcolor=bg, bordercolor=bg, focuscolor=bg, padding=(12, 6),
                        font=FONT_SMALL)
        style.map(f"{name}.TButton", background=[("active", hover)], lightcolor=[("active", hover)],
                  darkcolor=[("active", hover)], bordercolor=[("active", hover)],
                  focuscolor=[("active", hover)])
    style.configure("Soft.TButton", background=BG, lightcolor=BG, darkcolor=BG,
                    bordercolor=BG, focuscolor=BG, padding=(12, 6))
    style.map("Soft.TButton", background=[("pressed", "#dfe4ec"), ("active", "#e9edf4")],
              lightcolor=[("active", "#e9edf4")], darkcolor=[("active", "#e9edf4")],
              bordercolor=[("active", "#e9edf4")], focuscolor=[("active", "#e9edf4")])

    # Галочки «Срочно» / «Важно»
    style.configure("TCheckbutton", background=BG, foreground=TEXT, font=FONT,
                    indicatorbackground=SURFACE, indicatorforeground="white",
                    upperbordercolor="#b8c0cc", lowerbordercolor="#b8c0cc",
                    focuscolor=BG, indicatormargin=(0, 0, 8, 0), padding=(0, 2))
    style.map("TCheckbutton",
              indicatorbackground=[("selected", ACCENT), ("active", ACCENT_SOFT)],
              upperbordercolor=[("selected", ACCENT)], lowerbordercolor=[("selected", ACCENT)],
              background=[("active", BG)])
    style.configure("Card.TCheckbutton", background=SURFACE)
    style.map("Card.TCheckbutton", background=[("active", SURFACE)])
    style.configure("Card.TRadiobutton", background=SURFACE)
    style.map("Card.TRadiobutton", background=[("active", SURFACE)])
    style.configure("Icon.TButton", padding=(6, 3), font=FONT)

    # Поля ввода и выпадающие списки
    style.configure("TEntry", fieldbackground=SURFACE, lightcolor=SURFACE,
                    darkcolor=SURFACE, padding=(8, 6), insertcolor=TEXT)
    style.map("TEntry",
              bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", SURFACE)])
    style.configure("Placeholder.TEntry", foreground=DONE)
    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE,
                    lightcolor=SURFACE, darkcolor=SURFACE, arrowcolor=MUTED, padding=(6, 4))
    style.map("TCombobox",
              fieldbackground=[("disabled", BG), ("readonly", SURFACE)],
              foreground=[("disabled", DONE)],
              background=[("disabled", BG), ("active", "#f3f5f9")],
              bordercolor=[("focus", ACCENT)],
              selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", TEXT)])

    # Переключатель фильтра в виде сегментов
    style.layout("Segment.TRadiobutton", [
        ("Radiobutton.padding", {"sticky": "nswe", "children": [
            ("Radiobutton.label", {"sticky": "nswe"})]})])
    style.configure("Segment.TRadiobutton", background=SEGMENT_BG, foreground=MUTED,
                    padding=(14, 5), font=FONT_SMALL, anchor="center")
    style.map("Segment.TRadiobutton",
              background=[("selected", SURFACE), ("active", "#dde3ee")],
              foreground=[("selected", ACCENT), ("active", TEXT)])
    style.configure("Segments.TFrame", background=SEGMENT_BG)

    # Таблица задач
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, rowheight=36, borderwidth=0, font=FONT)
    style.map("Treeview",
              background=[("selected", ACCENT_SOFT)], foreground=[("selected", TEXT)])
    # Тонкие линии между заголовками столбцов — видно, где тянуть, чтобы изменить ширину
    style.configure("Treeview.Heading", background=SURFACE, foreground=MUTED,
                    font=("Segoe UI Semibold", 9), relief="raised", borderwidth=1,
                    padding=(10, 8), bordercolor=SURFACE, lightcolor=SURFACE, darkcolor="#dfe3ea")
    style.map("Treeview.Heading", background=[("active", "#f6f8fc")])

    # Тонкая полоса прокрутки без стрелок
    style.layout("Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Vertical.TScrollbar", troughcolor=SURFACE, background="#d6dbe4",
                    bordercolor=SURFACE, lightcolor="#d6dbe4", darkcolor="#d6dbe4",
                    gripcount=0, width=8)
    style.map("Vertical.TScrollbar", background=[("active", "#b8c0cc")])
    style.layout("Horizontal.TScrollbar", [
        ("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
            ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Horizontal.TScrollbar", troughcolor=BG, background="#d6dbe4",
                    bordercolor=BG, lightcolor="#d6dbe4", darkcolor="#d6dbe4",
                    gripcount=0, width=8)
    style.map("Horizontal.TScrollbar", background=[("active", "#b8c0cc")])


def center_on_screen(window, width=None, height=None):
    """Ставит окно по центру экрана."""
    window.update_idletasks()
    width = width or window.winfo_reqwidth()
    height = height or window.winfo_reqheight()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"{width}x{height}+{x}+{max(y, 0)}")


def format_due(due_at):
    """'2026-10-16 09:00' -> '16.10.2026 09:00'."""
    return datetime.fromisoformat(due_at).strftime("%d.%m.%Y %H:%M") if due_at else ""


def short_text(text, limit=60):
    """Обрезает длинный текст по границе слова: «Очень длинная задача…»."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"


def build_email(number, title, status, priority, due, remind, created, urgent, body=""):
    """Тема и текст письма по задаче: в теме — заголовок, в тексте — описание и все поля."""
    subject = f"Задача из {APP_NAME}: {short_text(title)}"
    if urgent:
        subject = "СРОЧНО! " + subject
    level_hint = next((PRIORITY_HINTS[k] for k, v in PRIORITY_NAMES.items() if v and v == priority), "")
    lines = [f"Задача #{number}: {title}", ""]
    if body.strip():
        lines += ["Описание:", *body.strip().splitlines(), ""]
    lines += [
        f"Статус: {status}",
        f"Приоритет: {priority} — {level_hint}" if priority else "Приоритет: обычный",
        f"Срок: {due or 'не задан'}",
        f"Напоминание: {remind or 'нет'}",
        f"Создана: {created}",
        "",
        "—",
        f"Отправлено из {APP_NAME}",
    ]
    return subject, "\r\n".join(lines)


def write_draft(number, subject, body):
    """Сохраняет черновик письма в файл .eml и возвращает путь к нему.
    Заголовок X-Unsent: 1 говорит почтовой программе открыть его как новое письмо."""
    message = EmailMessage(policy=email_policy.SMTP)
    message["Subject"] = subject
    message["X-Unsent"] = "1"
    message.set_content(body.replace("\r\n", "\n"))
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFTS_DIR / f"Задача {number}.eml"
    path.write_bytes(message.as_bytes())
    return str(path)


# ---------- экспорт и импорт задач в CSV (таблица для Excel) ----------
# Разделитель — «;», кодировка — UTF-8 с меткой BOM: так русский Excel открывает файл
# двойным щелчком без «кракозябр». При импорте понимаем и «,», и кодировку Windows-1251
# (в ней сохраняет CSV русский Excel).

CSV_COLUMNS = ["№", "Заголовок", "Описание", "Статус", "Приоритет", "Срок", "Напомнить", "Создана"]
CSV_TEMPLATE_COLUMNS = ["Заголовок", "Описание", "Статус", "Приоритет", "Срок", "Напомнить"]
CSV_ALIASES = {  # заголовок столбца в файле (строчными) -> поле
    "№": "num", "номер": "num",
    "заголовок": "title", "задача": "title", "название": "title",
    "описание": "body",
    "статус": "status", "колонка": "status",
    "приоритет": "priority",
    "срок": "due",
    "напомнить": "remind", "напоминание": "remind",
    "создана": "created",
}
PRIORITY_FLAGS = {"срочно и важно": (1, 1), "важно": (0, 1), "срочно": (1, 0),
                  "обычный": (0, 0), "обычная": (0, 0), "": (0, 0)}
DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:[ T]+(\d{1,2}):(\d{2})(?::\d{2})?)?$")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]+(\d{1,2}):(\d{2})(?::\d{2})?)?$")


def parse_csv_date(text):
    """«16.10.2026 18:00», «16.10.2026» или «2026-10-16 18:00» -> datetime.
    Без времени — 09:00, как в форме задачи. Пусто -> None, ошибка -> ValueError."""
    text = text.strip()
    if not text:
        return None
    if m := DATE_RE.match(text):
        day, month, year, hour, minute = m.groups()
    elif m := ISO_DATE_RE.match(text):
        year, month, day, hour, minute = m.groups()
    else:
        raise ValueError(text)
    return datetime(int(year), int(month), int(day), int(hour or 9), int(minute or 0))


def parse_csv_remind(text):
    """«за 1 час» или число минут -> минуты; пусто или «Не напоминать» -> None."""
    text = text.strip()
    for label, minutes in REMIND_OPTIONS.items():
        if text.lower() == label.lower():
            return minutes
    if not text:
        return None
    if text.isdigit():
        return int(text)
    raise ValueError(text)


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";", lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)


def export_rows(conn):
    """Все задачи в виде строк CSV (в порядке номеров)."""
    statuses = {sid: name for sid, name, _, _ in db.list_statuses(conn)}
    rows = []
    for task_id, title, done, created, due_at, remind_before, urgent, important, body, status_id \
            in db.list_tasks(conn):
        remind = REMIND_LABELS.get(remind_before, remind_before or "") if due_at else ""
        if remind == "Не напоминать":
            remind = ""
        rows.append([task_id, title, body, statuses.get(status_id, ""),
                     PRIORITY_NAMES[priority_level(urgent, important)] or "Обычный",
                     format_due(due_at), remind, created])
    return rows


def template_rows():
    """Примеры строк для шаблона импорта."""
    soon = (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y")
    return [
        ["Купить продукты", "Молоко, хлеб, сыр", "Новая", "Срочно", f"{soon} 18:00", "за 1 час"],
        ["Подготовить отчёт", "", "В работе", "Срочно и важно", soon, ""],
        ["Позвонить маме", "", "Новая", "Обычный", "", ""],
    ]


def read_csv(path):
    """Читает файл CSV: [(номер строки, {поле: текст}), ...].
    Если нет столбца «Заголовок» — ValueError с понятным текстом."""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    first = text.split("\n", 1)[0]
    delimiter = max(";,\t", key=first.count)
    reader = csv.reader(text.splitlines(keepends=True), delimiter=delimiter)
    header = next(reader, [])
    fields = [CSV_ALIASES.get(h.strip().lower()) for h in header]
    if "title" not in fields:
        raise ValueError("В первой строке файла нет столбца «Заголовок».\n\n"
                         "Скачайте шаблон (☰ Меню → Экспорт и импорт → Шаблон для импорта) и заполните его.")
    result = []
    for line_no, cells in enumerate(reader, start=2):
        values = {}
        for field, cell in zip(fields, cells):
            if field and field not in values:
                values[field] = cell.strip()
        if any(values.values()):
            result.append((line_no, values))
    return result


def prepare_import(conn, records):
    """Проверяет строки файла. Возвращает (задачи для db.import_tasks, список замечаний)."""
    statuses = db.list_statuses(conn)
    by_name = {name.strip().lower(): sid for sid, name, _, _ in statuses}
    tasks, notes = [], []
    for line_no, v in records:
        title = v.get("title", "")
        if not title:
            notes.append(f"строка {line_no}: нет заголовка — пропущена")
            continue
        status_text = v.get("status", "")
        status_id = by_name.get(status_text.lower())
        if status_id is None:
            status_id = statuses[0][0]
            if status_text:
                notes.append(f"строка {line_no}: статуса «{status_text}» нет — задача в «{statuses[0][1]}»")
        priority_text = v.get("priority", "")
        flags = PRIORITY_FLAGS.get(priority_text.lower())
        if flags is None:
            flags = (0, 0)
            notes.append(f"строка {line_no}: приоритет «{priority_text}» непонятен — обычный")
        try:
            due = parse_csv_date(v.get("due", ""))
        except ValueError:
            due = None
            notes.append(f"строка {line_no}: срок «{v['due']}» непонятен — без срока")
        remind = None
        if due:
            try:
                remind = parse_csv_remind(v.get("remind", ""))
            except ValueError:
                notes.append(f"строка {line_no}: напоминание «{v['remind']}» непонятно — без напоминания")
        try:
            created = parse_csv_date(v.get("created", ""))
        except ValueError:
            created = None
        tasks.append(dict(
            title=title, body=v.get("body", ""), status_id=status_id,
            due_at=due.strftime("%Y-%m-%d %H:%M") if due else None, remind_before=remind,
            # если момент напоминания уже прошёл — не засыпаем пользователя напоминаниями
            reminded=bool(due and remind is not None
                          and due - timedelta(minutes=remind) <= datetime.now()),
            urgent=flags[0], important=flags[1],
            # дата создания хранится в базе по UTC
            created_at=created.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if created else None,
        ))
    return tasks, notes


def status_label(name, done, overdue=False):
    """Название статуса (колонки доски) со значком: ✔ выполнено, ⚠ просрочено, ○ остальное."""
    mark = "✔" if done else "⚠" if overdue else "○"
    return f"{mark}  {name}"


class DatePicker(ttk.Frame):
    """Поле даты с выпадающим календарём."""

    def __init__(self, parent, value=None, on_change=None):
        super().__init__(parent)
        self.value = value
        self.on_change = on_change
        self.popup = None
        self.text = tk.StringVar()

        self.entry = ttk.Entry(self, textvariable=self.text, font=FONT, width=11,
                               state="readonly", cursor="hand2")
        self.entry.pack(side="left")
        self.entry.bind("<Button-1>", lambda e: self.toggle_popup())
        ttk.Button(self, text="📅", style="Icon.TButton", width=3, cursor="hand2",
                   command=self.toggle_popup).pack(side="left", padx=(4, 0))
        self.show()

    def set(self, value):
        self.value = value
        self.show()
        self.close_popup()
        if self.on_change:
            self.on_change()

    def show(self):
        self.text.set(self.value.strftime("%d.%m.%Y") if self.value else "не задан")

    # --- выпадающий календарь ---

    def toggle_popup(self):
        if self.popup:
            self.close_popup()
            return
        self.month = (self.value or date.today()).replace(day=1)
        self.popup = tk.Toplevel(self)
        self.popup.overrideredirect(True)  # окно без рамки и заголовка
        self.popup.configure(bg=SURFACE, highlightthickness=1, highlightbackground="#cbd2dd")
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 4
        self.popup.geometry(f"+{x}+{y}")
        self.popup.bind("<Escape>", lambda e: self.close_popup())
        self.popup.bind("<FocusOut>", lambda e: self.after(150, self.close_if_unfocused))
        self.popup.bind("<MouseWheel>", lambda e: self.shift_month(-1 if e.delta > 0 else 1))
        self.draw_month()
        self.popup.focus_force()

    def close_popup(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def close_if_unfocused(self):
        """Закрывает календарь, если пользователь щёлкнул куда-то мимо него."""
        if self.popup is None:
            return
        try:
            focus = self.popup.focus_get()
        except KeyError:
            focus = None
        if focus is None or not str(focus).startswith(str(self.popup)):
            self.close_popup()

    def shift_month(self, step):
        month_index = self.month.year * 12 + self.month.month - 1 + step
        self.month = date(month_index // 12, month_index % 12 + 1, 1)
        self.draw_month()

    def clickable(self, parent, text, command, **style):
        """Надпись, которая работает как кнопка (не забирает фокус у календаря)."""
        bg = style.pop("bg", SURFACE)
        label = tk.Label(parent, text=text, bg=bg, cursor="hand2", **style)
        label.bind("<Button-1>", lambda e: command())
        label.bind("<Enter>", lambda e: label.configure(bg=ACCENT_SOFT) if bg == SURFACE else None)
        label.bind("<Leave>", lambda e: label.configure(bg=bg))
        return label

    def draw_month(self):
        for child in self.popup.winfo_children():
            child.destroy()
        frame = tk.Frame(self.popup, bg=SURFACE, padx=10, pady=8)
        frame.pack()

        header = tk.Frame(frame, bg=SURFACE)
        header.grid(row=0, column=0, columnspan=7, sticky="we", pady=(0, 6))
        self.clickable(header, "‹", lambda: self.shift_month(-1), fg=MUTED,
                       font=("Segoe UI", 14), width=2).pack(side="left")
        tk.Label(header, text=f"{MONTHS[self.month.month - 1]} {self.month.year}",
                 bg=SURFACE, fg=TEXT, font=FONT_BOLD).pack(side="left", expand=True)
        self.clickable(header, "›", lambda: self.shift_month(1), fg=MUTED,
                       font=("Segoe UI", 14), width=2).pack(side="right")

        for col, name in enumerate(WEEKDAYS):
            tk.Label(frame, text=name, bg=SURFACE, width=3, font=("Segoe UI", 9),
                     fg=DANGER if col >= 5 else MUTED).grid(row=1, column=col, pady=(0, 2))

        today = date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.month.year, self.month.month)
        for row, week in enumerate(weeks, start=2):
            for col, day in enumerate(week):
                style = {"font": FONT, "width": 3, "pady": 3, "fg": TEXT}
                if day == self.value:
                    style.update(bg=ACCENT, fg="white", font=FONT_BOLD)
                elif day.month != self.month.month:
                    style.update(fg="#c4c9d2")
                elif col >= 5:
                    style.update(fg=DANGER)
                if day == today and day != self.value:
                    style.update(fg=ACCENT, font=FONT_BOLD)
                self.clickable(frame, str(day.day), lambda d=day: self.set(d), **style).grid(
                    row=row, column=col, padx=1, pady=1)

        footer = tk.Frame(frame, bg=SURFACE)
        footer.grid(row=len(weeks) + 2, column=0, columnspan=7, sticky="we", pady=(8, 0))
        self.clickable(footer, "Сегодня", lambda: self.set(today),
                       fg=ACCENT, font=FONT_SMALL).pack(side="left")
        self.clickable(footer, "Без срока", lambda: self.set(None),
                       fg=MUTED, font=FONT_SMALL).pack(side="right")


class TaskForm(ttk.Frame):
    """Форма задачи: заголовок, описание, статус, срок, приоритет, напоминание.

    Встраивается в правую панель (compact=True) или в запасное окно TaskDialog.
    on_save получает словарь с новыми значениями, on_cancel вызывается при отмене.
    """

    def __init__(self, parent, task, statuses, on_save, on_cancel, compact=False):
        super().__init__(parent, style="Card.TFrame" if compact else "TFrame")
        self.on_save, self.on_cancel = on_save, on_cancel
        self.statuses = statuses  # [(id, название, цвет, выполнено)]
        style_bg = SURFACE if compact else BG
        label_style = "CardMuted.TLabel" if compact else "Muted.TLabel"

        def label(text, top=12):
            ttk.Label(self, text=text, style=label_style).pack(anchor="w", pady=(top, 4))

        label("Заголовок", top=0)
        self.title_entry = ttk.Entry(self, font=FONT, width=1 if compact else 48)
        self.title_entry.pack(fill="x")
        self.title_entry.insert(0, task["title"])

        label("Описание")
        desc_box = tk.Frame(self, bg=SURFACE, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT)
        desc_box.pack(fill="x")
        self.desc = tk.Text(desc_box, font=FONT, height=5 if compact else 6, width=1 if compact else 48,
                            wrap="word", relief="flat", borderwidth=0, padx=8, pady=6, bg=SURFACE,
                            fg=TEXT, insertbackground=TEXT, highlightthickness=0, undo=True)
        desc_scroll = ttk.Scrollbar(desc_box, orient="vertical", command=self.desc.yview)
        self.desc.configure(yscrollcommand=desc_scroll.set)
        desc_scroll.pack(side="right", fill="y")
        self.desc.pack(side="left", fill="both", expand=True)
        self.desc.insert("1.0", task["body"])
        # В описании Enter — новая строка; сохранить — Ctrl+Enter
        self.desc.bind("<Return>", lambda e: (self.desc.insert("insert", "\n"), "break")[1])

        label("Статус")
        self.status = ttk.Combobox(self, values=[s[1] for s in statuses], state="readonly",
                                   width=1 if compact else 24, font=FONT)
        self.status.pack(fill="x" if compact else None, anchor="w")
        current = next((s[1] for s in statuses if s[0] == task["status_id"]), statuses[0][1])
        self.status.set(current)

        due = datetime.fromisoformat(task["due_at"]) if task["due_at"] else None
        label("Срок выполнения")
        due_row = ttk.Frame(self, style=self["style"])
        due_row.pack(fill="x")
        self.date = DatePicker(due_row, due.date() if due else None, on_change=self.date_changed)
        self.date.configure(style=self["style"])
        self.date.pack(side="left")
        time_row =ttk.Frame(self, style=self["style"]) if compact else due_row
        if compact:
            time_row.pack(fill="x", pady=(6, 0))
        ttk.Label(time_row, text="время" if compact else "в",
                  style=label_style if compact else "TLabel").pack(
            side="left", padx=(0 if compact else 14, 8))
        self.hour = ttk.Combobox(time_row, values=HOURS, state="readonly", width=3, font=FONT)
        self.hour.pack(side="left")
        ttk.Label(time_row, text=":", style=label_style if compact else "TLabel").pack(side="left", padx=3)
        self.minute = ttk.Combobox(time_row, values=MINUTES, state="readonly", width=3, font=FONT)
        self.minute.pack(side="left")
        self.hour.set(due.strftime("%H") if due else DEFAULT_TIME[0])
        self.minute.set(due.strftime("%M") if due else DEFAULT_TIME[1])

        # Быстрый выбор срока — ссылками
        quick = tk.Frame(self, bg=style_bg)
        quick.pack(fill="x", pady=(6, 0))
        links = (("Сегодня", lambda: self.set_date(0)), ("Завтра", lambda: self.set_date(1)),
                 ("Через неделю", lambda: self.set_date(7)), ("Без срока", lambda: self.date.set(None)))
        for i, (text, command) in enumerate(links):
            link = tk.Label(quick, text=text, bg=style_bg, fg=ACCENT, font=FONT_SMALL, cursor="hand2")
            link.grid(row=i // 2 if compact else 0, column=i % 2 if compact else i,
                      sticky="w", padx=(0, 14), pady=1)
            link.bind("<Button-1>", lambda e, c=command: c())

        label("Приоритет")
        prio_row = ttk.Frame(self, style=self["style"])
        prio_row.pack(fill="x")
        self.urgent = tk.BooleanVar(value=bool(task["urgent"]))
        self.important = tk.BooleanVar(value=bool(task["important"]))
        check_style = "Card.TCheckbutton" if compact else "TCheckbutton"
        ttk.Checkbutton(prio_row, text="Срочно", variable=self.urgent, style=check_style,
                        command=self.priority_changed, cursor="hand2").pack(side="left")
        ttk.Checkbutton(prio_row, text="Важно", variable=self.important, style=check_style,
                        command=self.priority_changed, cursor="hand2").pack(side="left", padx=(18, 0))
        self.priority_label = ttk.Label(prio_row if not compact else self, style=label_style,
                                        compound="left")
        self.priority_label.pack(side="left" if not compact else "top", anchor="w",
                                 padx=(22, 0) if not compact else 0, pady=(4, 0) if compact else 0)
        self.priority_changed()

        label("Напоминание")
        self.remind = ttk.Combobox(self, values=list(REMIND_OPTIONS), state="readonly",
                                   width=1 if compact else 18, font=FONT)
        self.remind.pack(fill="x" if compact else None, anchor="w")
        self.remind.set(REMIND_LABELS.get(task["remind_before"], f"за {task['remind_before']} мин"))

        buttons = ttk.Frame(self, style=self["style"])
        buttons.pack(fill="x", pady=(18, 0))
        ttk.Button(buttons, text="Сохранить", style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Button(buttons, text="Отмена", style="Soft.TButton" if compact else "TButton",
                   command=on_cancel).pack(side="right", padx=(0, 8))

        self.date_changed()
        self.initial = self.values()
        bind_tree(self, "<Control-Return>", lambda e: (self.save(), "break")[1])
        bind_tree(self, "<Escape>", lambda e: (self.on_cancel(), "break")[1])
        self.title_entry.bind("<Return>", lambda e: self.save())

    def focus_title(self):
        self.title_entry.focus_set()
        self.title_entry.icursor("end")

    def set_date(self, days):
        self.date.set(date.today() + timedelta(days=days))

    def priority_changed(self):
        """Показывает, какой приоритет получился из галочек."""
        level = priority_level(self.urgent.get(), self.important.get())
        name = PRIORITY_NAMES[level] or "Обычная задача"
        self.priority_label.configure(
            text=f"  {name} — {PRIORITY_HINTS[level]}", image=IMAGES.get(f"priority_{level}", ""),
        )

    def date_changed(self):
        """Без даты время и напоминание выбирать нельзя."""
        has_date = self.date.value is not None
        for combo in (self.hour, self.minute, self.remind):
            combo.configure(state="readonly" if has_date else "disabled")
        if not has_date:
            self.remind.set("Не напоминать")

    def values(self):
        """Текущие значения формы (без проверки)."""
        due_at = None
        if self.date.value:
            due = datetime.combine(self.date.value, time(int(self.hour.get()), int(self.minute.get())))
            due_at = due.strftime("%Y-%m-%d %H:%M")
        status_id = next(s[0] for s in self.statuses if s[1] == self.status.get())
        return dict(title=self.title_entry.get().strip(), body=self.desc.get("1.0", "end-1c").strip(),
                    status_id=status_id, due_at=due_at,
                    remind_before=REMIND_OPTIONS.get(self.remind.get()),
                    urgent=self.urgent.get(), important=self.important.get())

    def dirty(self):
        """Есть ли несохранённые изменения."""
        return self.values() != self.initial

    def save(self):
        result = self.values()
        if not result["title"]:
            messagebox.showwarning("Задача", "Заголовок задачи не может быть пустым.", parent=self)
            return
        if result["remind_before"] is not None and result["due_at"] is None:
            messagebox.showwarning("Задача", "Чтобы напомнить о задаче, укажите срок.", parent=self)
            return
        self.on_save(result)


class TaskDialog(tk.Toplevel):
    """Запасное окно с формой задачи — когда правая панель скрыта (узкое окно)."""

    def __init__(self, parent, task, statuses):
        super().__init__(parent)
        self.result = None
        self.title("Задача")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.form = TaskForm(self, task, statuses, on_save=self.saved, on_cancel=self.destroy)
        self.form.configure(padding=(20, 18, 20, 18))
        self.form.pack(fill="both")
        center_on_screen(self)
        self.form.focus_title()
        self.grab_set()

    def saved(self, result):
        self.result = result
        self.destroy()


class HelpWindow(tk.Toplevel):
    """Окно справки: оформленный текст из help_text.py."""

    MARKUP = re.compile(r"(\*\*.+?\*\*|\[[^\]]+\]|\{p[123]\}|\{github\})")

    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"Справка — {APP_NAME}")
        self.configure(bg=SURFACE)
        self.minsize(520, 400)

        text = tk.Text(
            self, wrap="word", bg=SURFACE, fg=TEXT, font=FONT, relief="flat",
            borderwidth=0, highlightthickness=0, padx=32, pady=24, cursor="arrow",
            spacing1=2, spacing3=2,
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        text.pack(side="left", fill="both", expand=True)

        text.tag_configure("h1", font=("Segoe UI Semibold", 18), spacing3=6)
        text.tag_configure("h2", font=("Segoe UI Semibold", 13), foreground=ACCENT,
                           spacing1=16, spacing3=4)
        text.tag_configure("p", spacing3=4)
        text.tag_configure("li", lmargin1=8, lmargin2=26, spacing3=3)
        text.tag_configure("b", font=FONT_BOLD)
        text.tag_configure("key", font=("Segoe UI Semibold", 10), background=SEGMENT_BG)

        if "totoro_small" in IMAGES:
            text.image_create("end", image=IMAGES["totoro_small"], padx=0)
            text.insert("end", "\n")
        folder = str(db.DATA_DIR)
        for kind, line in HELP:
            line = line.replace("{folder}", folder)
            if kind == "li":
                text.insert("end", "•  ", "li")
            self.insert_marked(text, line, kind)
            text.insert("end", "\n", kind)

        # ссылка на страницу проекта: синяя, подчёркнутая, открывается в браузере
        text.tag_configure("link", foreground=ACCENT, underline=True)
        text.tag_bind("link", "<Button-1>", lambda e: webbrowser.open(PROJECT_URL))
        text.tag_bind("link", "<Enter>", lambda e: text.configure(cursor="hand2"))
        text.tag_bind("link", "<Leave>", lambda e: text.configure(cursor=""))
        text.tag_configure("copyright", foreground=MUTED, font=FONT_SMALL, spacing1=24)
        text.insert("end", f"{COPYRIGHT}. Лицензия MIT (☰ Меню → О программе → Лицензия).\n"
                           f"{GHIBLI_NOTE}", "copyright")

        text.configure(state="disabled")  # только для чтения
        self.bind("<Escape>", lambda e: self.destroy())
        center_on_screen(self, 680, 640)
        text.focus_set()

    def insert_marked(self, text, line, kind):
        """Вставляет строку, превращая **…**, […] и {pN} в оформление."""
        line = line.replace(" [", " [")  # клавиша переносится вместе с предыдущим словом
        for part in self.MARKUP.split(line):
            if not part:
                continue
            if part.startswith("**"):
                text.insert("end", part[2:-2], (kind, "b"))
            elif part.startswith("["):
                # неразрывные пробелы, чтобы клавиша не разрывалась переносом строки
                text.insert("end", f" {part[1:-1]} ", (kind, "key"))
            elif part.startswith("{p"):
                image = IMAGES.get(f"priority_{part[2]}")
                if image:
                    text.image_create("end", image=image, align="center")
            elif part == "{github}":
                text.insert("end", PROJECT_URL.removeprefix("https://"), (kind, "link"))
            else:
                text.insert("end", part, kind)


class AboutWindow(tk.Toplevel):
    """«О программе»: название, автор, лицензия, примечание о персонажах Ghibli."""

    def __init__(self, parent, on_license):
        super().__init__(parent)
        self.title(f"О программе {APP_NAME}")
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        body = tk.Frame(self, bg=SURFACE, padx=28, pady=22)
        body.pack(fill="both")
        top = tk.Frame(body, bg=SURFACE)
        top.pack(fill="x")
        if "totoro_small" in IMAGES:
            tk.Label(top, image=IMAGES["totoro_small"], bg=SURFACE).pack(side="left", padx=(0, 16))
        names = tk.Frame(top, bg=SURFACE)
        names.pack(side="left", anchor="center")
        tk.Label(names, text=APP_NAME, bg=SURFACE, fg=TEXT, font=FONT_TITLE).pack(anchor="w")
        tk.Label(names, text=f"Список дел с Тоторо · версия {APP_VERSION}", bg=SURFACE, fg=MUTED, font=FONT).pack(anchor="w")

        tk.Label(body, text=COPYRIGHT, bg=SURFACE, fg=TEXT, font=FONT_BOLD).pack(anchor="w", pady=(18, 2))
        link = tk.Label(body, text=PROJECT_URL.removeprefix("https://"), bg=SURFACE, fg=ACCENT,
                        font=(*FONT_SMALL, "underline"), cursor="hand2")
        link.pack(anchor="w", pady=(0, 10))
        link.bind("<Button-1>", lambda e: webbrowser.open(PROJECT_URL))
        for text, color, font in ((LICENSE_SUMMARY, TEXT, FONT_SMALL), (GHIBLI_NOTE, MUTED, FONT_SMALL)):
            tk.Label(body, text=text, bg=SURFACE, fg=color, font=font, justify="left",
                     wraplength=470).pack(anchor="w", pady=(0, 10))

        buttons = tk.Frame(body, bg=SURFACE)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Закрыть", style="Accent.TButton", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Текст лицензии…", style="Soft.TButton",
                   command=lambda: (self.destroy(), on_license())).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy())
        center_on_screen(self)
        self.focus_force()


class LicenseWindow(tk.Toplevel):
    """Полный текст лицензии из файла LICENSE (официальный текст MIT — на английском)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Лицензия MIT")
        self.configure(bg=SURFACE)
        tk.Label(self, text="Краткий пересказ — в окне «О программе». Ниже — официальный текст "
                            "лицензии MIT на английском, он имеет юридическую силу.",
                 bg=SURFACE, fg=MUTED, font=FONT_SMALL, wraplength=600, justify="left").pack(
            anchor="w", padx=24, pady=(18, 6))
        text = tk.Text(self, wrap="word", bg=SURFACE, fg=TEXT, font=("Consolas", 10), relief="flat",
                       highlightthickness=0, padx=24, pady=10, width=78, height=24)
        try:
            content = LICENSE_PATH.read_text(encoding="utf-8")
        except OSError:
            content = f"Файл лицензии не найден: {LICENSE_PATH}"
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())
        center_on_screen(self)
        self.focus_force()


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Прямоугольник со скруглёнными углами на холсте."""
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kw)


PANEL_WIDTH = 290


class TotoroPanel(tk.Frame):
    """Большой Тоторо и облачко с подсказкой по задачам (когда задача не выбрана)."""

    BUBBLE = {  # заливка и рамка облачка в зависимости от настроения
        "normal": (BG, BORDER, TEXT),
        "alert": ("#fdeeee", "#f3c4c4", DANGER),
        "done": ("#eaf7ef", "#bfe5cc", "#15803d"),
    }

    def __init__(self, parent, on_task_click):
        super().__init__(parent, bg=SURFACE)
        self.on_task_click = on_task_click
        self.canvas = tk.Canvas(self, width=PANEL_WIDTH, bg=SURFACE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.message = ("", (), "", "normal", "")

    def show(self, lead, tasks=(), tail="", mood="normal", stats=""):
        """tasks — задачи, которые назвать в облачке: [(заголовок, id), ...]; каждая кликается."""
        message = (lead, tuple(tasks), tail, mood, stats)
        if message != self.message:
            self.message = message
            self.draw()

    def draw(self):
        lead, tasks, tail, mood, stats = self.message
        c = self.canvas
        c.delete("all")
        width, height = c.winfo_width(), c.winfo_height()
        if width < 50:
            return
        fill, outline, task_color = self.BUBBLE[mood]
        pad, inner = 16, 14
        text_width = width - 2 * (pad + inner)
        cx = width // 2

        # Тексты облачка (сначала рисуем их, чтобы узнать высоту)
        y = 0
        items = []
        limit = 70 if len(tasks) == 1 else 45  # несколько задач — названия короче
        lines = [(lead, FONT_SMALL, MUTED, (), 6)]
        lines += [(f"«{short_text(title, limit)}»", FONT_BOLD, task_color, ("task", f"task{tid}"), 3)
                  for title, tid in tasks]
        lines.append((tail, FONT_SMALL, TEXT, (), 6))
        for text, font, color, tags, gap in lines:
            if not text:
                continue
            if tags and items and not c.gettags(items[-1]):
                y += 3  # отступ перед списком задач
            item = c.create_text(cx, y, text=text, font=font, fill=color, width=text_width,
                                 justify="center", anchor="n", tags=tags)
            x1, y1, x2, y2 = c.bbox(item)
            items.append(item)
            y = y2 + gap
        bubble_h = y - 6 + 2 * inner

        totoro = IMAGES.get("totoro")
        totoro_h = totoro.height() if totoro else 0
        stats_h = 24 if stats else 0
        total = bubble_h + 16 + totoro_h + stats_h
        top = max(pad, (height - total) // 2)

        # Облачко с «хвостиком» вниз, к Тоторо
        for item in items:
            c.move(item, 0, top + inner)
        y2 = top + bubble_h
        bubble = round_rect(c, pad, top, width - pad, y2, 16, fill=fill, outline=outline)
        tail_poly = c.create_polygon(cx - 10, y2 - 1, cx + 10, y2 - 1, cx, y2 + 14,
                                     fill=fill, outline=outline)
        joint = c.create_line(cx - 9, y2, cx + 9, y2, fill=fill, width=2)
        for shape in (joint, tail_poly, bubble):
            c.tag_lower(shape)

        if totoro:
            c.create_image(cx, y2 + 16, image=totoro, anchor="n")
        if stats:
            c.create_text(cx, y2 + 16 + totoro_h + 8, text=stats, font=FONT_SMALL,
                          fill=MUTED, anchor="n", width=width - 2 * pad, justify="center")

        for _, tid in tasks:
            c.tag_bind(f"task{tid}", "<Button-1>", lambda e, t=tid: self.on_task_click(t))
        c.tag_bind("task", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("task", "<Leave>", lambda e: c.configure(cursor=""))


class TaskCard(tk.Frame):
    """Карточка выбранной задачи: заголовок, описание и все поля."""

    def __init__(self, parent, on_close, on_edit, on_email, on_toggle, on_delete):
        super().__init__(parent, bg=SURFACE, padx=18, pady=14)
        wrap = PANEL_WIDTH - 40
        # ширину панели можно менять — заголовок переносится по её ширине
        self.bind("<Configure>", lambda e: self.title.configure(wraplength=max(e.width - 40, 100)))

        top = tk.Frame(self, bg=SURFACE)
        top.pack(fill="x")
        self.number = tk.Label(top, bg=BG, fg=MUTED, font=FONT_SMALL, padx=6)
        self.number.pack(side="left", padx=(0, 8))
        self.priority = tk.Label(top, bg=SURFACE, fg=MUTED, font=FONT_SMALL, compound="left")
        self.priority.pack(side="left")
        close = tk.Label(top, text="✕", bg=SURFACE, fg=MUTED, font=FONT, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: on_close())
        close.bind("<Enter>", lambda e: close.configure(fg=TEXT))
        close.bind("<Leave>", lambda e: close.configure(fg=MUTED))

        self.title = tk.Label(self, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 14),
                              wraplength=wrap, justify="left", anchor="w")
        self.title.pack(fill="x", pady=(6, 2))
        self.status = tk.Label(self, bg=SURFACE, font=FONT_SMALL, anchor="w")
        self.status.pack(fill="x")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=12)

        # Действия с задачей — внизу карточки, сроки и даты — над ними
        actions = tk.Frame(self, bg=SURFACE)
        actions.pack(side="bottom", fill="x", pady=(12, 0))
        actions.columnconfigure((0, 1), weight=1, uniform="actions")
        self.toggle_button = ttk.Button(actions, style="AccentSoft.TButton", command=on_toggle)
        self.toggle_button.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 6))
        ttk.Button(actions, text="✎  Изменить", style="Soft.TButton", command=on_edit).grid(
            row=1, column=0, sticky="we", padx=(0, 3))
        ttk.Button(actions, text="✉  Письмо", style="Soft.TButton", command=on_email).grid(
            row=1, column=1, sticky="we", padx=(3, 0))
        ttk.Button(actions, text="Удалить задачу", style="DangerSoft.TButton", command=on_delete).grid(
            row=2, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self.fields = tk.Frame(self, bg=SURFACE)
        self.fields.pack(side="bottom", fill="x")
        self.values = {}
        for row, (key, label) in enumerate((("due", "Срок"), ("remind", "Напомнить"),
                                            ("created", "Создана"))):
            tk.Label(self.fields, text=label, bg=SURFACE, fg=MUTED, font=FONT_SMALL).grid(
                row=row, column=0, sticky="w", pady=1)
            value = tk.Label(self.fields, bg=SURFACE, fg=TEXT, font=FONT_SMALL)
            value.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=1)
            self.values[key] = value
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x", pady=12)

        # Описание (только для чтения, с прокруткой колесом)
        tk.Label(self, text="Описание", bg=SURFACE, fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        body_box = tk.Frame(self, bg=SURFACE)
        body_box.pack(fill="both", expand=True)
        self.body_scroll = ttk.Scrollbar(body_box, orient="vertical")
        self.body = tk.Text(body_box, bg=SURFACE, fg=TEXT, font=FONT, wrap="word", relief="flat",
                            borderwidth=0, highlightthickness=0, height=4, width=1,
                            padx=0, pady=4, cursor="arrow", spacing3=4,
                            yscrollcommand=self.update_body_scroll)
        self.body_scroll.configure(command=self.body.yview)
        self.body.pack(side="left", fill="both", expand=True)
        self.body.tag_configure("empty", foreground=DONE, font=FONT_SMALL)

    def update_body_scroll(self, first, last):
        """Полоса прокрутки описания видна, только если текст не помещается."""
        needed = not (float(first) <= 0 and float(last) >= 1)
        if needed and not self.body_scroll.winfo_ismapped():
            self.body_scroll.pack(side="right", fill="y", before=self.body)
        elif not needed and self.body_scroll.winfo_ismapped():
            self.body_scroll.pack_forget()
        self.body_scroll.set(first, last)

    def show(self, number, title, body, status, status_color, overdue, done, priority_level_,
             priority_name, due, remind, created):
        shown = (number, title, body, status, status_color, overdue, done, priority_level_,
                 priority_name, due, remind, created)
        if shown == getattr(self, "shown", None):
            return  # ничего не изменилось — не трогаем, чтобы не сбросить прокрутку описания
        self.shown = shown
        self.number.configure(text=f"#{number}")
        self.toggle_button.configure(text="↺  Вернуть в работу" if done else "✔  Выполнено")
        self.priority.configure(
            image=IMAGES.get(f"priority_{priority_level_}", ""),
            text=f"  {priority_name}" if priority_name else "Обычный приоритет",
        )
        color = DANGER if overdue else DONE if done else TEXT
        self.title.configure(text=title, fg=color)
        self.status.configure(text=status, fg=status_color)
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        if body.strip():
            self.body.insert("1.0", body)
        else:
            self.body.insert("1.0", "Описания нет.\nНажмите «Изменить», чтобы его добавить.",
                             "empty")
        self.body.configure(state="disabled")
        self.values["due"].configure(text=due or "не задан", fg=DANGER if overdue else TEXT)
        self.values["remind"].configure(text=remind or "нет")
        self.values["created"].configure(text=created)


class ScrollArea(tk.Frame):
    """Прокручиваемая область: содержимое — во фрейме self.inner, ширина — по ширине области."""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.update_bar)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))

    def update_bar(self, first, last):
        needed = not (float(first) <= 0 and float(last) >= 1)
        if needed and not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.canvas)
        elif not needed and self.bar.winfo_ismapped():
            self.bar.pack_forget()
        self.bar.set(first, last)

    def bind_wheel(self, widget=None):
        """Колёсико прокручивает область (поле описания прокручивается само)."""
        widget = widget or self.inner
        if isinstance(widget, tk.Text):
            return
        widget.bind("<MouseWheel>", self.on_wheel)
        for child in widget.winfo_children():
            self.bind_wheel(child)

    def on_wheel(self, event):
        if self.bar.winfo_ismapped():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"  # и не меняем значение в выпадающих списках при прокрутке


class SidePanel(tk.Frame):
    """Правая панель: Тоторо, пока задача не выбрана, иначе — карточка задачи
    или форма её изменения."""

    def __init__(self, parent, on_task_click, on_close, on_edit, on_email, on_toggle, on_delete):
        super().__init__(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=BORDER, width=PANEL_WIDTH)
        self.pack_propagate(False)  # ширину задаёт разделитель, а не длина текста
        self.totoro = TotoroPanel(self, on_task_click)
        self.card = TaskCard(self, on_close, on_edit, on_email, on_toggle, on_delete)
        self.editor = None  # ScrollArea с формой, пока задача редактируется
        self.form = None
        self.mode = None
        self.show_totoro()

    def switch(self, mode, widget):
        if self.mode == mode:
            return
        for other in (self.totoro, self.card):
            other.pack_forget()
        if self.editor is not None and widget is not self.editor:
            self.editor.destroy()
            self.editor, self.form = None, None
        widget.pack(fill="both", expand=True)
        self.mode = mode

    def show_totoro(self):
        self.switch("totoro", self.totoro)

    def show_task(self, **task):
        self.card.show(**task)
        self.switch("task", self.card)

    def show_form(self, task, statuses, on_save, on_cancel):
        """Форма изменения задачи прямо в панели."""
        if self.editor is not None:
            self.editor.destroy()
        self.mode = None
        self.editor = ScrollArea(self, SURFACE)
        head = tk.Frame(self.editor.inner, bg=SURFACE)
        head.pack(fill="x", padx=18, pady=(14, 10))
        tk.Label(head, text="Изменение задачи", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        close = tk.Label(head, text="✕", bg=SURFACE, fg=MUTED, font=FONT, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: on_cancel())
        self.form = TaskForm(self.editor.inner, task, statuses, on_save, on_cancel, compact=True)
        self.form.pack(fill="x", padx=18, pady=(0, 16))
        self.editor.bind_wheel()
        self.switch("edit", self.editor)
        self.form.focus_title()


MENU_BORDER = "#d3d9e3"
MENU_FONT = ("Segoe UI", 10)


class PopupMenu:
    """Своё всплывающее меню в стиле приложения (вместо системного меню Windows).

    Пункты: command(...), separator(), submenu(...). Показать: popup(x, y).
    Клавиши: ↑ ↓ — выбор, Enter — выполнить, → / ← — открыть / закрыть подменю, Esc — закрыть.
    """

    def __init__(self):
        self.items = []

    def command(self, label, command, accel="", icon=None, enabled=True, checked=False, danger=False):
        self.items.append(dict(kind="command", label=label, command=command, accel=accel, icon=icon,
                               enabled=enabled, checked=checked, danger=danger))
        return self

    def separator(self):
        self.items.append(dict(kind="separator"))
        return self

    def submenu(self, label, menu, icon=None, enabled=True):
        self.items.append(dict(kind="submenu", label=label, menu=menu, icon=icon, enabled=enabled,
                               checked=False, accel="", danger=False))
        return self

    def popup(self, root, x, y, right_aligned=False):
        """right_aligned=True — x задаёт правый край меню (для кнопок у правого края окна)."""
        _MenuWindow(root, self, x, y, right_aligned=right_aligned)


class _MenuWindow(tk.Toplevel):
    def __init__(self, master, menu, x, y, parent=None, right_aligned=False):
        super().__init__(master)
        self.menu, self.parent, self.child = menu, parent, None
        self.top = parent.top if parent else self
        self.rows, self.active, self.open_after = [], None, None
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        frame = tk.Frame(self, bg=SURFACE, padx=5, pady=5, highlightthickness=1,
                         highlightbackground=MENU_BORDER)
        frame.pack()
        for item in menu.items:
            if item["kind"] == "separator":
                tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=6, pady=4)
                continue
            self.rows.append((self.make_row(frame, item), item))

        # Не выходим за край экрана
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if right_aligned:
            x -= w
        if x + w > sw:
            x = (parent.winfo_rootx() - w + 4) if parent else sw - w - 4
        if y + h > sh:
            y = max(sh - h - 4, 0)
        self.geometry(f"+{x}+{y}")
        self.deiconify()

        if parent is None:
            # Щелчок мимо меню закрывает его (пока меню открыто, все щелчки приходят сюда)
            self.grab_set()
            self.bind("<ButtonPress>", self.click_outside)
            self.bind("<FocusOut>", lambda e: self.after(120, self.check_focus))
            for key, action in (("<Escape>", self.key_escape), ("<Up>", lambda: self.move(-1)),
                                ("<Down>", lambda: self.move(1)), ("<Return>", self.key_enter),
                                ("<Right>", self.key_right), ("<Left>", self.key_left)):
                self.bind(key, lambda e, a=action: a())
            self.focus_force()

    def make_row(self, frame, item):
        enabled = item["enabled"]
        fg = DONE if not enabled else DANGER if item["danger"] else TEXT
        row = tk.Frame(frame, bg=SURFACE, padx=8, pady=5, cursor="hand2" if enabled else "")
        row.pack(fill="x")
        tk.Label(row, text="✓" if item["checked"] else "", width=2, bg=SURFACE, fg=ACCENT,
                 font=MENU_FONT).pack(side="left")
        if item["icon"] is not None:
            tk.Label(row, image=item["icon"], bg=SURFACE).pack(side="left", padx=(0, 8))
        tk.Label(row, text=item["label"], bg=SURFACE, fg=fg, font=MENU_FONT, anchor="w").pack(
            side="left", fill="x", expand=True)
        right = "›" if item["kind"] == "submenu" else item["accel"]
        tk.Label(row, text=right, bg=SURFACE, fg=MUTED if enabled else DONE,
                 font=("Segoe UI", 12) if item["kind"] == "submenu" else MENU_FONT).pack(
            side="right", padx=(24, 2))
        if enabled:
            bind_tree(row, "<Enter>", lambda e, r=row: self.hover(r))
            bind_tree(row, "<ButtonRelease-1>", lambda e, r=row: self.activate(r))
        return row

    def paint(self, row, bg):
        row.configure(bg=bg)
        for child in row.winfo_children():
            child.configure(bg=bg)

    def hover(self, row):
        if self.active is not None and self.active is not row:
            self.paint(self.active, SURFACE)
        self.active = row
        self.paint(row, ACCENT_SOFT)
        item = dict(self.rows)[row]
        if self.open_after:
            self.after_cancel(self.open_after)
            self.open_after = None
        if self.child and self.child.anchor_row is not row:
            self.close_child()
        if item["kind"] == "submenu" and not self.child:
            self.open_after = self.after(150, lambda: self.open_submenu(row))

    def open_submenu(self, row):
        self.open_after = None
        if self.child:
            return
        item = dict(self.rows)[row]
        self.child = _MenuWindow(self.top, item["menu"], row.winfo_rootx() + row.winfo_width() + 6,
                                 row.winfo_rooty() - 6, parent=self)
        self.child.anchor_row = row

    def close_child(self):
        if self.child:
            self.child.close_child()
            self.child.destroy()
            self.child = None

    def activate(self, row):
        item = dict(self.rows)[row]
        if item["kind"] == "submenu":
            self.open_submenu(row)
            return
        command = item["command"]
        root = self.top.master
        self.top.close()
        root.after(1, command)  # выполняем после закрытия меню

    def close(self):
        self.close_child()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def windows(self):
        win, result = self.top, []
        while win:
            result.append(win)
            win = win.child
        return result

    def click_outside(self, event):
        inside = any(w.winfo_rootx() <= event.x_root < w.winfo_rootx() + w.winfo_width()
                     and w.winfo_rooty() <= event.y_root < w.winfo_rooty() + w.winfo_height()
                     for w in self.windows())
        if not inside:
            self.close()

    def check_focus(self):
        try:
            focus = self.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        if focus is None and self.winfo_exists():
            self.close()

    # --- клавиатура (работает в самом глубоком открытом подменю) ---

    def deepest(self):
        return self.windows()[-1]

    def move(self, step):
        win = self.deepest()
        if not win.rows:
            return
        rows = [r for r, _ in win.rows]
        i = rows.index(win.active) + step if win.active in rows else (0 if step > 0 else -1)
        win.hover(rows[i % len(rows)])

    def key_enter(self):
        win = self.deepest()
        if win.active is not None:
            win.activate(win.active)

    def key_right(self):
        win = self.deepest()
        if win.active is not None and dict(win.rows)[win.active]["kind"] == "submenu":
            win.open_submenu(win.active)
            self.move(1)  # подсветить первый пункт подменю

    def key_left(self):
        win = self.deepest()
        if win.parent:
            win.parent.close_child()

    def key_escape(self):
        win = self.deepest()
        if win.parent:
            win.parent.close_child()
        else:
            self.close()


def menu_button(parent, text, build_menu):
    """Плоская кнопка, открывающая наше меню (вместо старой кнопки со стрелкой).
    Меню выравнивается по правому краю кнопки."""
    button = ttk.Button(parent, text=text, style="TButton", cursor="hand2")

    def show():
        x = button.winfo_rootx() + button.winfo_width()
        y = button.winfo_rooty() + button.winfo_height() + 4
        build_menu().popup(button.winfo_toplevel(), x, y, right_aligned=True)
    button.configure(command=show)
    return button


class ModernDialog(tk.Toplevel):
    """Основа для окон-диалогов в стиле приложения: белое поле, заголовок, кнопки справа."""

    def __init__(self, parent, title, heading, ok_text="Сохранить"):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        self.body = tk.Frame(self, bg=SURFACE, padx=26, pady=20)
        self.body.pack(fill="both", expand=True)
        tk.Label(self.body, text=heading, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 14)).pack(
            anchor="w", pady=(0, 14))
        self.content = tk.Frame(self.body, bg=SURFACE)
        self.content.pack(fill="both", expand=True)
        buttons = tk.Frame(self.body, bg=SURFACE)
        buttons.pack(fill="x", pady=(22, 0))
        ttk.Button(buttons, text=ok_text, style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(buttons, text="Отмена", style="Soft.TButton", command=self.destroy).pack(
            side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self.ok())

    def show(self):
        center_on_screen(self)
        self.grab_set()
        self.focus_force()
        self.wait_window()
        return self.result

    def ok(self):
        raise NotImplementedError


class LaneDialog(ModernDialog):
    """Создание или настройка колонки доски: название, цвет, «задачи здесь выполнены»."""

    def __init__(self, parent, name="", color=None, is_done=False, new=True):
        super().__init__(parent, "Новая колонка" if new else "Настройка колонки",
                         "Новая колонка" if new else "Настройка колонки",
                         "Создать" if new else "Сохранить")
        self.color = color or LANE_COLORS[0][1]

        tk.Label(self.content, text="Название", bg=SURFACE, fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self.name = ttk.Entry(self.content, font=FONT, width=34)
        self.name.pack(fill="x", pady=(4, 16))
        self.name.insert(0, name)

        tk.Label(self.content, text="Цвет", bg=SURFACE, fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self.swatches = tk.Canvas(self.content, bg=SURFACE, highlightthickness=0, height=40,
                                  width=len(LANE_COLORS) * 36)
        self.swatches.pack(anchor="w", pady=(6, 4))
        self.swatches.bind("<Button-1>", self.pick_swatch)
        other = tk.Label(self.content, text="Другой цвет…", bg=SURFACE, fg=ACCENT, font=FONT_SMALL,
                         cursor="hand2")
        other.pack(anchor="w", pady=(0, 16))
        other.bind("<Button-1>", lambda e: self.pick_custom())
        self.draw_swatches()

        self.done = tk.BooleanVar(value=bool(is_done))
        ttk.Checkbutton(self.content, text="Задачи здесь считаются выполненными",
                        variable=self.done, style="Card.TCheckbutton").pack(anchor="w")
        tk.Label(self.content, text="Такие задачи серые, не напоминают о себе\n"
                                    "и попадают в счётчик «выполнено».",
                 bg=SURFACE, fg=MUTED, font=FONT_SMALL, justify="left").pack(anchor="w", padx=(26, 0))
        self.name.focus_set()

    def draw_swatches(self):
        c = self.swatches
        c.delete("all")
        for i, (_, color) in enumerate(LANE_COLORS):
            x = 18 + i * 36
            if color == self.color:
                c.create_oval(x - 16, 4, x + 16, 36, outline=TEXT, width=2)
            c.create_oval(x - 12, 8, x + 12, 32, fill=color, outline=color)
        if self.color not in (col for _, col in LANE_COLORS):
            c.configure(width=(len(LANE_COLORS) + 1) * 36)
            x = 18 + len(LANE_COLORS) * 36
            c.create_oval(x - 16, 4, x + 16, 36, outline=TEXT, width=2)
            c.create_oval(x - 12, 8, x + 12, 32, fill=self.color, outline=self.color)

    def pick_swatch(self, event):
        i = event.x // 36
        if i < len(LANE_COLORS):
            self.color = LANE_COLORS[i][1]
            self.draw_swatches()

    def pick_custom(self):
        _, color = colorchooser.askcolor(self.color, title="Цвет колонки", parent=self)
        if color:
            self.color = color
            self.draw_swatches()

    def ok(self):
        name = self.name.get().strip()
        if not name:
            self.name.focus_set()
            return
        self.result = dict(name=name, color=self.color, is_done=self.done.get())
        self.destroy()


# Поля, которые можно показывать на карточках доски: ключ -> подпись
CARD_FIELDS = {
    "number": "Номер задачи",
    "priority": "Метка приоритета",
    "body": "Начало описания",
    "due": "Срок",
    "remind": "Напоминание",
    "created": "Дата создания",
}
DEFAULT_CARD_FIELDS = ["number", "priority", "body", "due"]


# Как открывать окно при запуске: значение настройки -> подпись
START_MODES = {"window": "Обычным окном", "maximized": "Развёрнутым на весь экран"}


class SettingsDialog(ModernDialog):
    """Настройки: запуск программы, поля карточек на доске, обновления.
    result — dict(start_mode, card_fields, update_auto) или None (отмена)."""

    def __init__(self, parent, start_mode, card_fields, update_auto):
        super().__init__(parent, "Настройки", "Настройки")

        self.section("Запуск программы", "Как открывать окно ToDoro.")
        self.start_mode = tk.StringVar(value=start_mode)
        for value, label in START_MODES.items():
            ttk.Radiobutton(self.content, text=label, value=value, variable=self.start_mode,
                            style="Card.TRadiobutton").pack(anchor="w", pady=2)

        self.section("Карточки на доске", "Что показывать на карточках. Заголовок виден всегда.")
        grid = tk.Frame(self.content, bg=SURFACE)
        grid.pack(anchor="w")
        self.fields = {}
        for i, (key, label) in enumerate(CARD_FIELDS.items()):
            var = tk.BooleanVar(value=key in card_fields)
            ttk.Checkbutton(grid, text=label, variable=var, style="Card.TCheckbutton").grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 28), pady=2)
            self.fields[key] = var

        self.section("Обновления", f"Установлена версия {APP_VERSION}. Проверить вручную: "
                     "☰ Меню → Проверить обновления.")
        self.update_auto = tk.BooleanVar(value=update_auto)
        ttk.Checkbutton(self.content, text="Проверять обновления автоматически (раз в день)",
                        variable=self.update_auto, style="Card.TCheckbutton").pack(anchor="w", pady=2)

    def section(self, title, hint):
        first = not self.content.winfo_children()
        tk.Label(self.content, text=title, bg=SURFACE, fg=TEXT, font=FONT_BOLD).pack(
            anchor="w", pady=(0 if first else 16, 0))
        tk.Label(self.content, text=hint, bg=SURFACE, fg=MUTED, font=FONT_SMALL, wraplength=420,
                 justify="left").pack(anchor="w", pady=(0, 6))

    def ok(self):
        self.result = dict(start_mode=self.start_mode.get(),
                           card_fields=[key for key, var in self.fields.items() if var.get()],
                           update_auto=self.update_auto.get())
        self.destroy()


class NameDialog(ModernDialog):
    """Ввод названия (например, списка задач). result — название или None."""

    def __init__(self, parent, title, heading, value="", hint="", ok_text="Сохранить"):
        super().__init__(parent, title, heading, ok_text)
        self.entry = ttk.Entry(self.content, font=FONT, width=34)
        self.entry.insert(0, value)
        self.entry.pack(fill="x", ipady=2)
        self.entry.select_range(0, "end")
        if hint:
            tk.Label(self.content, text=hint, bg=SURFACE, fg=MUTED, font=FONT_SMALL).pack(
                anchor="w", pady=(6, 0))
        self.after(50, self.entry.focus_set)

    def ok(self):
        name = " ".join(self.entry.get().split())
        if not name:
            messagebox.showwarning(self.title(), "Название не может быть пустым.", parent=self)
            return
        self.result = name
        self.destroy()


def in_background(root, work, done):
    """Выполняет work() в отдельном потоке (чтобы окно не «зависало»), а done(результат, ошибка)
    вызывает уже в основном потоке — Tk можно трогать только из него."""
    box = {}

    def run():
        try:
            box["result"] = work()
        except Exception as error:  # noqa: BLE001 — ошибку покажем пользователю
            box["error"] = error

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def poll():
        if thread.is_alive():
            root.after(100, poll)
        else:
            done(box.get("result"), box.get("error"))
    root.after(100, poll)


class UpdateDialog(tk.Toplevel):
    """«Вышла новая версия»: что нового и кнопка «Обновить» (скачать и установить)."""

    def __init__(self, parent, release, on_close_app):
        super().__init__(parent)
        self.release = release
        self.on_close_app = on_close_app
        self.title("Обновление ToDoro")
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        body = tk.Frame(self, bg=SURFACE, padx=26, pady=20)
        body.pack(fill="both", expand=True)

        top = tk.Frame(body, bg=SURFACE)
        top.pack(fill="x")
        if "totoro_small" in IMAGES:
            tk.Label(top, image=IMAGES["totoro_small"], bg=SURFACE).pack(side="left", padx=(0, 14))
        titles = tk.Frame(top, bg=SURFACE)
        titles.pack(side="left", anchor="center")
        tk.Label(titles, text=f"Вышла версия {release['version']}!", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI Semibold", 14)).pack(anchor="w")
        tk.Label(titles, text=f"У вас сейчас версия {APP_VERSION}. Ваши задачи при обновлении "
                 "сохранятся.", bg=SURFACE, fg=MUTED, font=FONT_SMALL, wraplength=380,
                 justify="left").pack(anchor="w")

        tk.Label(body, text="Что нового:", bg=SURFACE, fg=TEXT, font=FONT_BOLD).pack(anchor="w", pady=(16, 4))
        notes_box = tk.Frame(body, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        notes_box.pack(fill="both", expand=True)
        notes = tk.Text(notes_box, width=60, height=12, wrap="word", font=FONT_SMALL, bg=SURFACE,
                        fg=TEXT, relief="flat", padx=10, pady=8, borderwidth=0)
        scroll = ttk.Scrollbar(notes_box, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        notes.pack(side="left", fill="both", expand=True)
        # Описание выпуска — в разметке Markdown; убираем из него значки разметки
        text = re.sub(r"^#+\s*", "", release["notes"] or "Описание не указано.", flags=re.M)
        text = re.sub(r"^>[ \t]?", "", text, flags=re.M)        # цитаты «> …»
        text = re.sub(r"\n[ \t]+(?=\S)", " ", text)             # перенесённые строки пункта — в одну
        text = re.sub(r"\*\*|`", "", text).replace("\n- ", "\n• ")
        if text.startswith("- "):
            text = "• " + text[2:]
        notes.insert("1.0", text.split("\n---", 1)[0].strip())
        notes.configure(state="disabled")
        notes.mark_set("insert", "1.0")
        self.after(50, lambda: notes.yview_moveto(0))  # показывать с начала, а не с конца

        # Место под полосу прогресса и строку состояния отведено заранее: высота окна задана
        # при открытии, и без запаса появившаяся полоса вытеснила бы кнопки за край окна
        footer = tk.Frame(body, bg=SURFACE, height=64)
        footer.pack(fill="x", pady=(12, 0))
        footer.pack_propagate(False)
        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=100)
        self.status = tk.Label(footer, text="", bg=SURFACE, fg=MUTED, font=FONT_SMALL, anchor="nw",
                               justify="left", wraplength=440)
        self.status.pack(fill="x", side="bottom")

        buttons = tk.Frame(body, bg=SURFACE)
        buttons.pack(fill="x", pady=(8, 0))
        self.self_update = updater.can_self_update() and release.get("asset_url")
        self.ok_button = ttk.Button(
            buttons, text="Обновить" if self.self_update else "Открыть страницу выпуска",
            style="Accent.TButton", command=self.update_now)
        self.ok_button.pack(side="right")
        self.later_button = ttk.Button(buttons, text="Позже", style="Soft.TButton", command=self.destroy)
        self.later_button.pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy() if self.later_button.instate(["!disabled"]) else None)
        self.bind("<Return>", lambda e: self.update_now() if self.ok_button.instate(["!disabled"]) else None)
        center_on_screen(self)
        self.focus_force()

    def update_now(self):
        if not self.self_update:
            webbrowser.open(self.release["url"])
            self.destroy()
            return
        for button in (self.ok_button, self.later_button):
            button.state(["disabled"])
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # не закрывать посреди скачивания
        self.progress.pack(fill="x", side="top", pady=(4, 0))
        self.status.configure(text="Скачиваю обновление…")
        shown = {"done": 0, "total": 0}

        def progress(done, total):
            shown.update(done=done, total=total)

        def tick():
            # скачивание закончилось — не затираем сообщение об ошибке или «Устанавливаю…»
            if not self.winfo_exists() or not self.downloading:
                return
            if shown["total"]:
                self.progress["value"] = 100 * shown["done"] / shown["total"]
                self.status.configure(text=f"Скачиваю обновление… {shown['done'] // 1048576} из "
                                      f"{shown['total'] // 1048576} МБ")
            self.after(150, tick)

        def finished(path, error):
            self.downloading = False
            if error:
                self.protocol("WM_DELETE_WINDOW", self.destroy)
                for button in (self.ok_button, self.later_button):
                    button.state(["!disabled"])
                self.progress.pack_forget()
                message = str(error) if isinstance(error, updater.UpdateError) else f"Ошибка: {error}"
                self.status.configure(text=message, fg=DANGER)
                return
            self.status.configure(text="Устанавливаю… ToDoro закроется и откроется снова.")
            self.update_idletasks()
            try:
                updater.run_installer(path)
            except OSError as error:
                self.status.configure(text=f"Не удалось запустить установщик: {error}", fg=DANGER)
                return
            self.after(500, self.on_close_app)

        self.downloading = True
        tick()
        in_background(self, lambda: updater.download(self.release, progress), finished)


class CatbusRun(tk.Toplevel):
    """Котобус проезжает по низу окна и «увозит» выполненную задачу.

    Прозрачное окно поверх приложения: всё, что цвета KEY, Windows делает прозрачным.
    """

    KEY = "#f3f5fa"  # почти цвет фона — края рисунка на светлом интерфейсе не видны
    HEIGHT = 124
    ENTER, STOP, LEAVE = 1500, 1700, 1300  # въезд, остановка, отъезд — в миллисекундах

    def __init__(self, root, text):
        super().__init__(root)
        bus = IMAGES.get("catbus")
        if bus is None:
            self.destroy()
            return
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", self.KEY)
        except tk.TclError:  # не Windows — просто не показываем
            self.destroy()
            return
        width = root.winfo_width()
        x, y = root.winfo_rootx(), root.winfo_rooty() + root.winfo_height() - self.HEIGHT - 6
        self.geometry(f"{width}x{self.HEIGHT}+{x}+{y}")
        self.canvas = tk.Canvas(self, width=width, height=self.HEIGHT, bg=self.KEY, highlightthickness=0)
        self.canvas.pack()
        self.bus = self.canvas.create_image(-bus.width(), self.HEIGHT - 4, image=bus, anchor="sw")
        # табличка с названием задачи над Котобусом
        label = f"✔ Выполнено: {short_text(text, 40)}"
        self.sign_text = self.canvas.create_text(0, 0, text=label, font=FONT_BOLD, fill="#166534",
                                                 anchor="s")
        x1, y1, x2, y2 = self.canvas.bbox(self.sign_text)
        self.sign_w, self.sign_h = x2 - x1 + 20, y2 - y1 + 8
        self.sign = round_rect(self.canvas, 0, 0, self.sign_w, self.sign_h, 8,
                               fill="#e8f7ee", outline="#86d3a3")
        self.canvas.tag_raise(self.sign_text)
        self.width, self.bus_w, self.bus_h = width, bus.width(), bus.height()
        self.start = None
        self.after(16, self.step)

    def position(self, ms):
        """Где Котобус через ms миллисекунд: въезжает, стоит посередине, уезжает.
        Возвращает (x, бежит ли сейчас)."""
        middle = (self.width - self.bus_w) / 2
        if ms < self.ENTER:                      # въезжает и плавно тормозит
            t = ms / self.ENTER
            return -self.bus_w + (1 - (1 - t) ** 2) * (middle + self.bus_w), True
        ms -= self.ENTER
        if ms < self.STOP:                       # стоит, чтобы табличку успели прочитать
            return middle, False
        t = min((ms - self.STOP) / self.LEAVE, 1.0)  # плавно разгоняется и уезжает
        return middle + t * t * (self.width - middle + 40), True

    def step(self):
        now = time_module.perf_counter() * 1000
        if self.start is None:
            self.start = now
        elapsed = now - self.start
        x, running = self.position(elapsed)
        # бежит вприпрыжку, а стоя — чуть «дышит»
        bounce = abs(math.sin(elapsed / 90)) * 3 if running else abs(math.sin(elapsed / 400)) * 1.5
        y = self.HEIGHT - 4 - bounce
        self.canvas.coords(self.bus, x, y)
        sx = x + self.bus_w / 2 - self.sign_w / 2
        sy = y - self.bus_h - 6
        self.canvas.coords(self.sign, *self.rect_points(sx, sy - self.sign_h, sx + self.sign_w, sy, 8))
        self.canvas.coords(self.sign_text, sx + self.sign_w / 2, sy - 4)
        if elapsed < self.ENTER + self.STOP + self.LEAVE:
            self.after(15, self.step)
        else:
            self.destroy()

    @staticmethod
    def rect_points(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


LANE_WIDTH = 250
CARD_BORDER = "#e9ecf2"  # рамка карточки на доске (у выбранной — синяя)
# Готовые цвета для колонок доски
LANE_COLORS = [
    ("Синий", "#3b82f6"), ("Голубой", "#06b6d4"), ("Зелёный", "#22c55e"),
    ("Жёлтый", "#eab308"), ("Оранжевый", "#f59e0b"), ("Красный", "#ef4444"),
    ("Розовый", "#ec4899"), ("Фиолетовый", "#8b5cf6"), ("Серый", "#64748b"),
]


def tint(color, amount):
    """Светлый оттенок цвета: amount=0 — сам цвет, 1 — белый."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(c + (255 - c) * amount) for c in (r, g, b))


def swatch(color):
    """Квадратик цвета для меню."""
    key = f"swatch_{color}"
    if key not in IMAGES:
        img = tk.PhotoImage(width=14, height=14)
        img.put(color, to=(0, 0, 14, 14))
        IMAGES[key] = img
    return IMAGES[key]


def bind_tree(widget, sequence, func):
    """Привязывает событие к виджету и всем его вложенным элементам."""
    widget.bind(sequence, func, add="+")
    for child in widget.winfo_children():
        bind_tree(child, sequence, func)


class KanbanBoard(tk.Frame):
    """Канбан-доска: колонки-статусы и карточки задач, которые можно перетаскивать."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.selected_id = None
        self.drag = None
        self.lanes = []   # [(status_id, рамка колонки, цвет фона колонки)]
        self.cards = {}   # id задачи -> рамка карточки

        self.hbar = ttk.Scrollbar(self, orient="horizontal")
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, xscrollcommand=self.update_hbar)
        self.hbar.configure(command=self.canvas.xview)
        self.canvas.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.window, height=e.height))
        for widget in (self.canvas, self.inner):
            widget.bind("<Button-1>", lambda e: self.app.clear_selection())
            widget.bind("<Shift-MouseWheel>", self.scroll_x)

    def update_hbar(self, first, last):
        needed = not (float(first) <= 0 and float(last) >= 1)
        if needed and not self.hbar.winfo_ismapped():
            self.hbar.pack(side="bottom", fill="x", before=self.canvas)
        elif not needed and self.hbar.winfo_ismapped():
            self.hbar.pack_forget()
        self.hbar.set(first, last)

    def scroll_x(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

    # --- построение доски ---

    def render(self, statuses, rows, overdue_ids):
        for child in self.inner.winfo_children():
            child.destroy()
        self.lanes, self.cards = [], {}
        by_status = {}
        for row in rows:
            by_status.setdefault(row[9], []).append(row)
        for status_id, name, color, is_done in statuses:
            self.make_lane(status_id, name, color, is_done, by_status.get(status_id, []), overdue_ids)

        add = tk.Label(self.inner, text="＋  Колонка", bg=BG, fg=MUTED, font=FONT_SMALL,
                       cursor="hand2", padx=18, pady=10, highlightthickness=1,
                       highlightbackground="#cfd5df")
        add.pack(side="left", anchor="n", pady=(0, 4))
        add.bind("<Button-1>", lambda e: self.app.add_lane())
        add.bind("<Enter>", lambda e: add.configure(fg=ACCENT, highlightbackground=ACCENT))
        add.bind("<Leave>", lambda e: add.configure(fg=MUTED, highlightbackground="#cfd5df"))

        if self.selected_id not in self.cards:
            self.selected_id = None
        self.highlight_selected()

    def make_lane(self, status_id, name, color, is_done, rows, overdue_ids):
        lane_bg = tint(color, 0.9)
        # Толщина рамки всегда 2: при подсветке меняется только цвет, и ничего не «прыгает»
        lane = tk.Frame(self.inner, bg=lane_bg, width=LANE_WIDTH,
                        highlightthickness=2, highlightbackground=BORDER)
        lane.pack(side="left", fill="y", padx=(0, 12), pady=(0, 4))
        lane.pack_propagate(False)
        tk.Frame(lane, bg=color, height=5).pack(fill="x")

        # Заголовок колонки: за него колонку можно перетащить на другое место
        head = tk.Frame(lane, bg=lane_bg, cursor="fleur")
        head.pack(fill="x", padx=12, pady=(10, 8))
        tk.Label(head, text=name, bg=lane_bg, fg=TEXT, font=FONT_BOLD, cursor="fleur").pack(side="left")
        tk.Label(head, text=f" {len(rows)} ", bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                 cursor="fleur").pack(side="left", padx=(8, 0))
        if is_done:
            tk.Label(head, text="✔", bg=lane_bg, fg="#15803d", font=FONT_SMALL, cursor="fleur").pack(
                side="left", padx=(6, 0))
        bind_tree(head, "<ButtonPress-1>", lambda e: self.lane_press(e, status_id))
        bind_tree(head, "<B1-Motion>", self.lane_motion)
        bind_tree(head, "<ButtonRelease-1>", self.lane_release)
        menu_btn = tk.Label(head, text="⋯", bg=lane_bg, fg=MUTED, font=("Segoe UI", 14),
                            cursor="hand2")
        menu_btn.pack(side="right")
        menu_btn.bind("<Button-1>", lambda e: self.app.lane_menu(status_id, e.x_root, e.y_root))
        menu_btn.bind("<Enter>", lambda e: menu_btn.configure(fg=TEXT))
        menu_btn.bind("<Leave>", lambda e: menu_btn.configure(fg=MUTED))

        # Карточки — в прокручиваемой области
        area = tk.Canvas(lane, bg=lane_bg, highlightthickness=0)
        area.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 10))
        cards = tk.Frame(area, bg=lane_bg)
        area.create_window(0, 0, window=cards, anchor="nw", width=LANE_WIDTH - 20)
        cards.bind("<Configure>", lambda e: area.configure(scrollregion=area.bbox("all")))
        for row in rows:
            self.make_card(cards, row, color, row[0] in overdue_ids)
        if not rows:
            tk.Label(cards, text="Перетащите сюда задачу", bg=lane_bg, fg=DONE,
                     font=FONT_SMALL).pack(pady=24)

        for widget in (lane, area, cards):
            widget.bind("<Button-1>", lambda e: self.app.clear_selection())
        bind_tree(lane, "<MouseWheel>",
                  lambda e: area.yview_scroll(-1 if e.delta > 0 else 1, "units")
                  if area.bbox("all") and area.bbox("all")[3] > area.winfo_height() else None)
        bind_tree(lane, "<Shift-MouseWheel>", self.scroll_x)
        self.lanes.append((status_id, lane, lane_bg))

    def make_card(self, parent, row, lane_color, overdue):
        task_id, title, done, created, due_at, remind_before, urgent, important, body, _ = row
        fields = self.app.card_fields  # что показывать на карточке (☰ Меню → Настройки)
        card = tk.Frame(parent, bg=SURFACE, highlightthickness=2, highlightbackground=CARD_BORDER,
                        cursor="hand2")
        card.pack(fill="x", pady=(0, 8))
        tk.Frame(card, bg=lane_color, width=4).pack(side="left", fill="y")
        content = tk.Frame(card, bg=SURFACE)
        content.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        top = tk.Frame(content, bg=SURFACE)
        top.pack(fill="x")
        level = priority_level(urgent, important)
        if "priority" in fields and level < 4:
            tk.Label(top, image=IMAGES.get(f"priority_{level}", ""), bg=SURFACE).pack(
                side="left", anchor="n", pady=(4, 0), padx=(0, 6))
        if "number" in fields:
            tk.Label(top, text=f"#{task_id}", bg=SURFACE, fg=DONE, font=FONT_SMALL).pack(
                side="right", anchor="n", padx=(6, 0))
        color = DANGER if overdue else DONE if done else TEXT
        tk.Label(top, text=title, bg=SURFACE, fg=color, font=FONT_BOLD, justify="left",
                 anchor="w", wraplength=LANE_WIDTH - 95).pack(side="left", fill="x")
        if "body" in fields and body.strip():
            tk.Label(content, text=short_text(body, 90), bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                     justify="left", anchor="w", wraplength=LANE_WIDTH - 60).pack(fill="x", pady=(4, 0))
        if "due" in fields and due_at:
            due_text = datetime.fromisoformat(due_at).strftime("%d.%m %H:%M")
            tk.Label(content, text=("⚠ срок " if overdue else "срок ") + due_text, bg=SURFACE,
                     fg=DANGER if overdue else MUTED, font=FONT_SMALL, anchor="w").pack(
                fill="x", pady=(4, 0))
        extra = []
        if "remind" in fields and due_at and remind_before:
            extra.append("напомнить " + REMIND_LABELS.get(remind_before, f"за {remind_before} мин"))
        if "created" in fields:
            extra.append("создана " + created[:5])
        if extra:
            tk.Label(content, text=" · ".join(extra), bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                     anchor="w", justify="left", wraplength=LANE_WIDTH - 60).pack(fill="x", pady=(2, 0))

        bind_tree(card, "<ButtonPress-1>", lambda e: self.on_press(e, task_id))
        bind_tree(card, "<B1-Motion>", self.on_motion)
        bind_tree(card, "<ButtonRelease-1>", self.on_release)
        bind_tree(card, "<Double-Button-1>", lambda e: self.app.edit())
        bind_tree(card, "<Button-3>", lambda e: self.app.show_menu_for(task_id, e.x_root, e.y_root))
        self.cards[task_id] = card

    # --- выделение ---

    def select(self, task_id):
        self.selected_id = task_id
        self.highlight_selected()

    def highlight_selected(self):
        for task_id, card in self.cards.items():
            card.configure(highlightbackground=ACCENT if task_id == self.selected_id else CARD_BORDER)

    # --- перетаскивание карточек ---
    # Карточку «берут» за то место, где нажали; за курсором едет её полупрозрачная копия.
    # Движения мыши сглаживаются: окно-копия передвигается не чаще одного раза за кадр.

    def on_press(self, event, task_id):
        card = self.cards[task_id]
        self.drag = {"id": task_id, "start": (event.x_root, event.y_root),
                     "offset": (event.x_root - card.winfo_rootx(), event.y_root - card.winfo_rooty()),
                     "ghost": None, "target": None, "pos": None, "pending": False}
        self.app.select_task(task_id)

    def on_motion(self, event):
        drag = self.drag
        if not drag:
            return
        if drag["ghost"] is None:
            sx, sy = drag["start"]
            if abs(event.x_root - sx) + abs(event.y_root - sy) < 6:
                return  # ещё не тащим — это просто щелчок
            drag["ghost"] = self.make_ghost(drag["id"])
            self.cards[drag["id"]].configure(highlightbackground=ACCENT)
            self.configure(cursor="fleur")
        drag["pos"] = (event.x_root, event.y_root)
        if not drag["pending"]:
            drag["pending"] = True
            self.after(10, self.follow_mouse)

    def make_ghost(self, task_id):
        """Полупрозрачная копия карточки того же размера."""
        card = self.cards[task_id]
        title = db.get_task(self.app.conn, task_id)[0]
        status_color = next((c for sid, (n, c, d) in self.app.statuses.items()
                             if sid == self.app.task_info(task_id)["status_id"]), ACCENT)
        ghost = tk.Toplevel(self)
        ghost.withdraw()
        ghost.overrideredirect(True)
        ghost.attributes("-alpha", 0.9)
        ghost.attributes("-topmost", True)
        frame = tk.Frame(ghost, bg=SURFACE, highlightthickness=2, highlightbackground=ACCENT,
                         width=card.winfo_width(), height=card.winfo_height())
        frame.pack()
        frame.pack_propagate(False)
        tk.Frame(frame, bg=status_color, width=4).pack(side="left", fill="y")
        tk.Label(frame, text=title, bg=SURFACE, fg=TEXT, font=FONT_BOLD, justify="left",
                 anchor="nw", wraplength=card.winfo_width() - 40).pack(
            side="left", fill="both", expand=True, padx=10, pady=8)
        ox, oy = self.drag["offset"]
        sx, sy = self.drag["start"]
        ghost.geometry(f"+{sx - ox}+{sy - oy}")
        ghost.deiconify()
        return ghost

    def follow_mouse(self):
        drag = self.drag
        if not drag or drag["ghost"] is None:
            return
        drag["pending"] = False
        x, y = drag["pos"]
        ox, oy = drag["offset"]
        drag["ghost"].geometry(f"+{x - ox}+{y - oy}")
        target = self.lane_at(x, y)
        if target != drag["target"]:  # подсветку меняем, только когда сменилась колонка
            for status_id, lane, _ in self.lanes:
                if status_id in (target, drag["target"]):
                    lane.configure(highlightbackground=ACCENT if status_id == target else BORDER)
            drag["target"] = target

    def on_release(self, event):
        drag, self.drag = self.drag, None
        if not drag or drag["ghost"] is None:
            return
        drag["ghost"].destroy()
        self.configure(cursor="")
        for _, lane, _ in self.lanes:
            lane.configure(highlightbackground=BORDER)
        target = self.lane_at(event.x_root, event.y_root)
        if target is not None and target != self.app.task_info(drag["id"])["status_id"]:
            # Доску перестраиваем после выхода из обработчика события
            self.after_idle(lambda: self.app.move_task(drag["id"], target))
        else:
            self.highlight_selected()

    # --- перетаскивание колонок за заголовок ---

    def lane_press(self, event, status_id):
        self.lane_drag = {"id": status_id, "start": (event.x_root, event.y_root), "ghost": None,
                          "marker": None, "index": None, "pos": None, "pending": False}

    def lane_motion(self, event):
        drag = getattr(self, "lane_drag", None)
        if not drag:
            return
        if drag["ghost"] is None:
            sx, sy = drag["start"]
            if abs(event.x_root - sx) + abs(event.y_root - sy) < 6:
                return
            name, color, _ = self.app.statuses[drag["id"]]
            ghost = tk.Toplevel(self)
            ghost.overrideredirect(True)
            ghost.attributes("-alpha", 0.9)
            ghost.attributes("-topmost", True)
            frame = tk.Frame(ghost, bg=tint(color, 0.9), highlightthickness=2,
                             highlightbackground=ACCENT, width=LANE_WIDTH, height=46)
            frame.pack()
            frame.pack_propagate(False)
            tk.Frame(frame, bg=color, height=5).pack(fill="x")
            tk.Label(frame, text=name, bg=tint(color, 0.9), fg=TEXT, font=FONT_BOLD).pack(
                anchor="w", padx=12, pady=8)
            drag["ghost"] = ghost
            # синяя черта показывает, куда встанет колонка
            drag["marker"] = tk.Frame(self.inner, bg=ACCENT, width=4)
        drag["pos"] = (event.x_root, event.y_root)
        if not drag["pending"]:
            drag["pending"] = True
            self.after(10, self.lane_follow)

    def lane_follow(self):
        drag = getattr(self, "lane_drag", None)
        if not drag or drag["ghost"] is None:
            return
        drag["pending"] = False
        x, y = drag["pos"]
        drag["ghost"].geometry(f"+{x - 40}+{y - 20}")
        # место вставки — перед первой колонкой, середина которой правее курсора
        index = sum(1 for _, lane, _ in self.lanes if lane.winfo_rootx() + lane.winfo_width() / 2 < x)
        if index != drag["index"]:
            drag["index"] = index
            if index < len(self.lanes):
                mx = self.lanes[index][1].winfo_x() - 8
            else:
                last = self.lanes[-1][1]
                mx = last.winfo_x() + last.winfo_width() + 4
            drag["marker"].place(x=mx, y=0, relheight=1)

    def lane_release(self, event):
        drag, self.lane_drag = getattr(self, "lane_drag", None), None
        if not drag or drag["ghost"] is None:
            return
        drag["ghost"].destroy()
        drag["marker"].destroy()
        ids = [sid for sid, _, _ in self.lanes]
        old = ids.index(drag["id"])
        index = drag["index"] if drag["index"] is not None else old
        ids.pop(old)
        ids.insert(index - 1 if index > old else index, drag["id"])
        if ids != [sid for sid, _, _ in self.lanes]:
            self.after_idle(lambda: self.app.reorder_lanes(ids))

    def lane_at(self, x, y):
        for status_id, lane, _ in self.lanes:
            lx, ly = lane.winfo_rootx(), lane.winfo_rooty()
            if lx <= x < lx + lane.winfo_width() and ly <= y < ly + lane.winfo_height():
                return status_id
        return None


class TodoApp:
    def __init__(self, root):
        self.root = root
        # Окно прячем, пока всё не построено: иначе на секунду мелькает пустое чёрное окно
        root.withdraw()
        # self.prefs — основной файл: настройки и личный список; self.conn — текущий список задач
        self.prefs = db.connect()
        self.list_conns = {db.PERSONAL: self.prefs}  # открытые списки: id -> соединение
        self.lists = db.list_registry(self.prefs)
        self.list_id = db.get_setting(self.prefs, "current_list", db.PERSONAL)
        if not any(item["id"] == self.list_id for item in self.lists):
            self.list_id = db.PERSONAL
        self.conn = self.list_conn(self.list_id)
        self.due = {}         # id строки таблицы -> срок (для подсветки просроченных)
        self.row_status = {}  # id строки таблицы -> название статуса
        self.statuses = {}    # id статуса -> (название, цвет, выполнено ли)

        root.title(APP_NAME)
        if ICON_PATH.exists():
            root.iconbitmap(default=str(ICON_PATH))  # иконка для всех окон программы
        setup_style(root)
        load_images()
        center_on_screen(root, 1290, 720)
        root.minsize(820, 480)

        page = ttk.Frame(root, padding=(24, 14, 24, 20))
        page.pack(fill="both", expand=True)

        # Заголовок, счётчики-«таблетки», меню и справка
        header = ttk.Frame(page)
        header.pack(fill="x", pady=(4, 0))
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left")
        # Переключатель списков: «Личный ▾», «Команда ▾» …
        self.list_button = ttk.Button(header, style="TButton", cursor="hand2",
                                      command=self.show_lists_menu)
        self.list_button.pack(side="left", padx=(16, 0), pady=(4, 0))
        chips = ttk.Frame(header)
        chips.pack(side="left", padx=(18, 0), pady=(6, 0))
        self.chips = {}
        for key, bg, fg in (("active", "#eef1f6", MUTED), ("done", "#eef1f6", MUTED),
                            ("today", "#e8f7ee", "#15803d")):
            chip = tk.Label(chips, bg=bg, fg=fg, font=FONT_SMALL, padx=10, pady=3)
            chip.pack(side="left", padx=(0, 6))
            self.chips[key] = chip
        menu_button(header, "☰  Меню", self.build_main_menu).pack(side="right")

        # Поле ввода и кнопка «Добавить»
        add_row = ttk.Frame(page)
        add_row.pack(fill="x", pady=(16, 14))
        self.entry = ttk.Entry(add_row, font=FONT)
        self.entry.pack(side="left", fill="x", expand=True, ipady=2)
        self.entry.bind("<Return>", lambda e: self.add())
        self.entry.bind("<KeyPress>", self.on_entry_key)
        self.entry.bind("<<Paste>>", lambda e: self.hide_placeholder())
        self.entry.bind("<FocusIn>", lambda e: self.cursor_to_start())
        self.entry.bind("<Button-1>", lambda e: self.root.after_idle(self.cursor_to_start))
        self.entry.bind("<FocusOut>", lambda e: self.show_placeholder())
        ttk.Button(add_row, text="＋  Добавить", style="Accent.TButton",
                   command=self.add).pack(side="left", padx=(10, 0), ipady=2)

        # Вид (список или доска), фильтр и сортировка
        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(0, 12))
        self.view = tk.StringVar(value=db.get_setting(self.prefs, "view", "list"))
        views = ttk.Frame(toolbar, style="Segments.TFrame", padding=3)
        views.pack(side="left")
        for value, text in (("list", "☰  Список"), ("board", "▦  Доска")):
            ttk.Radiobutton(views, text=text, value=value, variable=self.view,
                            style="Segment.TRadiobutton", command=self.switch_view,
                            cursor="hand2").pack(side="left")
        filters = ttk.Frame(toolbar, style="Segments.TFrame", padding=3)
        filters.pack(side="left", padx=(12, 0))
        self.filter = tk.StringVar(value="Все")
        for name in FILTERS:
            button = ttk.Radiobutton(filters, text=name, value=name, variable=self.filter,
                                     style="Segment.TRadiobutton", command=self.refresh,
                                     cursor="hand2")
            button.pack(side="left")
        self.overdue_button = button  # последняя кнопка; на ней — число просроченных задач
        self.sort = ttk.Combobox(toolbar, values=SORTS, state="readonly", width=27, font=FONT_SMALL)
        self.sort.set(SORTS[0])
        self.sort.pack(side="right")
        self.sort.bind("<<ComboboxSelected>>", lambda e: self.sort_chosen())
        ttk.Label(toolbar, text="Сортировка:", style="Muted.TLabel").pack(side="right", padx=(0, 8))
        self.card_fields = db.get_json_setting(self.prefs, "card_fields", DEFAULT_CARD_FIELDS)
        self.toolbar = toolbar

        # Середина окна: таблица или доска, справа — Тоторо, карточка или форма задачи.
        # Между ними — разделитель: потянув его мышью, можно менять ширину правой панели.
        content = tk.PanedWindow(page, orient="horizontal", bg=BG, bd=0, sashwidth=12,
                                 sashrelief="flat", opaqueresize=True, sashcursor="sb_h_double_arrow")
        content.pack(fill="both", expand=True)
        self.paned = content
        self.side = SidePanel(content, on_task_click=self.reveal_task,
                              on_close=self.clear_selection, on_edit=self.edit, on_email=self.email,
                              on_toggle=self.toggle, on_delete=self.delete)
        self.panel_width = int(db.get_setting(self.prefs, "panel_width", PANEL_WIDTH))
        # В узком окне панель прячется, чтобы не теснить таблицу
        content.bind("<Configure>", self.fit_side_panel)
        content.bind("<ButtonRelease-1>", lambda e: self.save_panel_width())
        self.editing = None  # id задачи, которая сейчас редактируется в правой панели

        card = tk.Frame(content, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        self.table_card = card
        inner = ttk.Frame(card, style="Card.TFrame", padding=(6, 4, 4, 6))
        inner.pack(fill="both", expand=True)
        self.scrollbar = ttk.Scrollbar(inner, orient="vertical")
        columns = {
            "num": ("№", 52, False),
            "status": ("СТАТУС", 125, False),
            "title": ("ЗАДАЧА", 220, False),
            "priority": ("ПРИОРИТЕТ", 130, False),
            "due": ("СРОК", 125, False),
            "remind": ("НАПОМНИТЬ", 105, False),
            # Растягивается последний столбец: если бы растягивалась «Задача», Tk сразу
            # возвращал бы ей всё свободное место и её ширину нельзя было бы изменить.
            "created": ("СОЗДАНА", 125, True),
        }
        # Первый, узкий столбец (#0) — цветная метка приоритета.
        self.hscroll = ttk.Scrollbar(inner, orient="horizontal")
        self.tree = ttk.Treeview(
            inner, columns=list(columns), show=("tree", "headings"),
            selectmode="browse", yscrollcommand=self.update_scrollbar,
            xscrollcommand=self.update_hscroll,
        )
        self.hscroll.configure(command=self.tree.xview)
        self.tree.column("#0", width=30, minwidth=30, stretch=False)
        # Ширину столбцов можно менять, потянув за разделитель в заголовке; она запоминается
        # («_v2»: ширины из прошлой версии не годятся — там «Задача» растягивалась на всё место)
        widths = db.get_json_setting(self.prefs, "list_columns_v2", {})
        self.column_titles = {key: text for key, (text, _, _) in columns.items()}
        for key, (text, width, stretch) in columns.items():
            # Щелчок по заголовку столбца сортирует по нему, повторный — в обратном порядке
            self.tree.heading(key, text=text, anchor="w",
                              command=lambda k=key: self.sort_by_column(k))
            self.tree.column(key, width=widths.get(key, width), minwidth=40, stretch=stretch)
        # Сортировка по столбцу: [столбец, по убыванию ли] или None — тогда работает список «Сортировка»
        self.column_sort = db.get_json_setting(self.prefs, "list_sort", None)
        self.show_column_sort()
        # Пока ширины не настраивали — «Задача» занимает всё свободное место таблицы
        self.columns_fitted = bool(widths)
        self.tree.bind("<Configure>", self.fit_columns, add="+")
        self.resizing_column = False
        self.tree.bind("<ButtonPress-1>", lambda e: setattr(
            self, "resizing_column", self.tree.identify_region(e.x, e.y) == "separator"), add="+")
        self.tree.tag_configure("hover", background="#f6f8fc")
        self.hover_row = None
        self.tree.bind("<Motion>", self.tree_motion)
        self.tree.bind("<Leave>", lambda e: self.set_hover(None))
        self.tree.bind("<ButtonRelease-1>", self.save_column_widths, add="+")
        self.tree.tag_configure("done", foreground=DONE)
        self.tree.tag_configure("overdue", foreground=DANGER)
        # У обычных строк цвет тоже задан явно: иначе в Tk 9 красный цвет
        # просроченной строки «протекает» в правые столбцы остальных строк.
        self.tree.tag_configure("normal", foreground=TEXT)
        self.tree.pack(side="left", fill="both", expand=True)
        self.scrollbar.config(command=self.tree.yview)
        self.empty = ttk.Label(inner, style="Empty.TLabel", justify="center")
        self.tree.bind("<Double-Button-1>", lambda e: self.edit())
        self.tree.bind("<Button-3>", self.show_menu)  # правая кнопка мыши
        self.tree.bind("<App>", self.show_menu_for_selected)  # клавиша контекстного меню
        # Выбор задачи показывает её карточку справа; щелчок мимо строк — снова Тоторо
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_tree_select())
        self.tree.bind("<Button-1>", self.click_empty_space, add="+")

        self.board = KanbanBoard(content, self)

        # Клавиши работают и в списке, и на доске (но не во время набора текста)
        for sequence, action in (("<F2>", self.edit), ("<space>", self.toggle),
                                 ("<Delete>", self.delete), ("<Control-e>", self.email),
                                 ("<Control-E>", self.email), ("<Escape>", self.clear_selection)):
            root.bind(sequence, lambda e, a=action: self.key_action(e, a))
        root.bind("<F1>", lambda e: self.show_help())
        self.help_window = None

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_main_widget()
        self.show_list_name()
        self.refresh()
        # Всё построено — показываем окно сразу готовым
        root.update_idletasks()
        if db.get_setting(self.prefs, "start_mode", "window") == "maximized":
            root.state("zoomed")  # развёрнуто на весь экран; «восстановить» вернёт обычное окно
        else:
            root.deiconify()
        root.after(200, self.repaint)  # ещё раз, когда окно уже показано
        self.show_placeholder()
        self.entry.focus()
        root.after(1000, self.check_reminders)
        root.after(4000, self.auto_check_update)  # раз в день — нет ли новой версии

    # --- список или доска ---

    def main_widget(self):
        return self.board if self.view.get() == "board" else self.table_card

    def in_paned(self, widget):
        return str(widget) in (str(p) for p in self.paned.panes())

    # --- таблица: ширина столбцов и подсветка строки под мышью ---

    def tree_motion(self, event):
        region = self.tree.identify_region(event.x, event.y)
        # На разделителе столбцов курсор показывает, что ширину можно менять
        self.tree.configure(cursor="sb_h_double_arrow" if region == "separator" else "")
        self.set_hover(self.tree.identify_row(event.y) if region in ("cell", "tree") else None)

    def set_hover(self, row):
        if row == self.hover_row:
            return
        for item, add in ((self.hover_row, False), (row, True)):
            if item and self.tree.exists(item):
                tags = [t for t in self.tree.item(item, "tags") if t != "hover"]
                self.tree.item(item, tags=tags + (["hover"] if add else []))
        self.hover_row = row

    def fit_columns(self, event):
        if self.columns_fitted or event.width < 300:
            return
        others = sum(self.tree.column(c, "width") for c in self.tree["columns"] if c != "title")
        free = event.width - others - self.tree.column("#0", "width") - 4
        self.tree.column("title", width=max(free, 150))

    def save_column_widths(self, event=None):
        if event is not None and not self.resizing_column:
            return  # сохраняем только после того, как тянули разделитель в заголовке
        self.resizing_column = False
        self.columns_fitted = True
        widths = {key: self.tree.column(key, "width") for key in self.tree["columns"]}
        if widths != db.get_json_setting(self.prefs, "list_columns_v2", {}):
            db.set_json_setting(self.prefs, "list_columns_v2", widths)

    def show_main_widget(self):
        """Слева в разделителе — таблица или доска, справа — панель."""
        other = self.table_card if self.view.get() == "board" else self.board
        if self.in_paned(other):
            self.paned.forget(other)
        main = self.main_widget()
        if not self.in_paned(main):
            if self.in_paned(self.side):
                self.paned.add(main, before=self.side, stretch="always", minsize=420)
            else:
                self.paned.add(main, stretch="always", minsize=420)
        if not self.in_paned(self.side):
            self.paned.add(self.side, stretch="never", minsize=240, width=self.panel_width)

    def show_settings(self):
        result = SettingsDialog(self.root, db.get_setting(self.prefs, "start_mode", "window"),
                                self.card_fields, self.auto_update_enabled()).show()
        if result is None:
            return
        db.set_setting(self.prefs, "start_mode", result["start_mode"])
        db.set_setting(self.prefs, "update_auto", "1" if result["update_auto"] else "0")
        if result["card_fields"] != self.card_fields:
            self.card_fields = result["card_fields"]
            db.set_json_setting(self.prefs, "card_fields", self.card_fields)
            self.refresh(select_id=self.current_id())

    # Единственное меню «☰ Меню»: сверху действия, потом настройки, внизу справка и сведения
    def build_main_menu(self):
        examples = (PopupMenu()
                    .command("Добавить примеры задач", self.add_examples)
                    .command("Удалить примеры задач", self.delete_examples))
        data = (PopupMenu()
                .command("Экспорт задач в CSV…", self.export_csv)
                .command("Импорт задач из CSV…", self.import_csv)
                .command("Шаблон для импорта…", self.save_template))
        feedback = (PopupMenu()
                    .command("Сообщить об ошибке…", lambda: self.send_feedback("bug"))
                    .command("Предложить улучшение…", lambda: self.send_feedback("idea"))
                    .command("Все сообщения на GitHub…", lambda: webbrowser.open(updater.ISSUES_PAGE)))
        about = (PopupMenu()
                 .command("Что нового…", lambda: webbrowser.open(updater.RELEASES_LIST))
                 .command("Лицензия (MIT)…", self.show_license)
                 .command(f"О программе {APP_NAME}…", self.show_about))
        return (PopupMenu()
                .command("Добавить колонку на доску…", self.add_lane)
                .submenu("Экспорт и импорт", data)
                .submenu("Примеры задач", examples)
                .separator()
                .command("Настройки…", self.show_settings)
                .separator()
                .command("Справка", self.show_help, accel="F1")
                .command("Проверить обновления…", self.check_update_now)
                .submenu("Обратная связь", feedback)
                .submenu("О программе", about))

    def send_feedback(self, kind):
        """Открывает на GitHub форму сообщения об ошибке или идеи (раздел Issues)."""
        if not messagebox.askokcancel(
            "Обратная связь",
            "Откроется страница на сайте GitHub с готовой формой — номер версии ToDoro "
            "и Windows уже подставлены, ваши задачи никуда не отправляются.\n\n"
            "Чтобы отправить сообщение, нужно войти в GitHub (регистрация бесплатная).\n\n"
            "Сообщение будет видно всем — не пишите в нём личных данных.",
            parent=self.root,
        ):
            return
        webbrowser.open(updater.feedback_url(kind, APP_VERSION))

    def celebrate(self, task_id):
        """Задача выполнена — Котобус проезжает по низу окна и увозит её."""
        task = db.get_task(self.conn, task_id)
        if task:
            self.root.after(150, lambda: CatbusRun(self.root, task[0]))

    def switch_view(self):
        db.set_setting(self.prefs, "view", self.view.get())
        task_id = self.current_id()
        self.show_main_widget()
        self.refresh(select_id=task_id)

    def key_action(self, event, action):
        """Горячие клавиши не мешают печатать в полях ввода."""
        if isinstance(event.widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Button,
                                     ttk.Radiobutton, ttk.Checkbutton)):
            return None
        if action is not self.clear_selection and self.current_id() is None:
            return None
        action()
        return "break"

    # --- выбранная задача (одна и та же в списке и на доске) ---

    def current_id(self):
        if self.view.get() == "board":
            return self.board.selected_id
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def select_task(self, task_id):
        if self.tree.exists(str(task_id)):
            self.tree.selection_set(str(task_id))
            self.tree.see(str(task_id))
        self.board.select(task_id)
        self.update_side()

    def on_tree_select(self):
        sel = self.tree.selection()
        if self.view.get() == "list":
            self.board.select(int(sel[0]) if sel else None)
        self.update_side()

    def clear_selection(self):
        self.tree.selection_remove(*self.tree.selection())
        self.board.select(None)
        self.update_side()

    def click_empty_space(self, event):
        """Щелчок по пустому месту таблицы снимает выделение."""
        if not self.tree.identify_row(event.y) and self.tree.identify_region(event.x, event.y) != "heading":
            self.clear_selection()

    def reveal_task(self, task_id):
        """Щелчок по задаче в облачке Тоторо: показать и выделить её."""
        if not self.tree.exists(str(task_id)):
            self.filter.set("Все")
            self.refresh()
        self.select_task(task_id)
        if self.view.get() == "list" and self.tree.exists(str(task_id)):
            self.tree.focus(str(task_id))
            self.tree.focus_set()

    # --- правая панель: Тоторо или карточка задачи ---

    def fit_side_panel(self, event):
        wide_enough = event.width >= 1000
        shown = self.in_paned(self.side)
        if wide_enough and not shown:
            self.paned.add(self.side, stretch="never", minsize=240, width=self.panel_width)
        elif not wide_enough and shown:
            self.save_panel_width()
            self.paned.forget(self.side)

    def save_panel_width(self):
        """Ширина правой панели запоминается (её меняют, потянув за разделитель)."""
        if self.in_paned(self.side) and self.side.winfo_width() > 1:
            self.panel_width = self.side.winfo_width()
            db.set_setting(self.prefs, "panel_width", str(self.panel_width))

    # --- изменение задачи в правой панели ---

    def form_data(self, task_id):
        title, due_at, remind_before, urgent, important, body = db.get_task(self.conn, task_id)
        return dict(title=title, due_at=due_at, remind_before=remind_before, urgent=urgent,
                    important=important, body=body, status_id=self.task_info(task_id)["status_id"])

    def apply_edit(self, task_id, result, refresh=True):
        db.update_task(self.conn, task_id, result["title"], result["due_at"], result["remind_before"],
                       result["urgent"], result["important"], result["body"])
        if result["status_id"] != self.task_info(task_id)["status_id"]:
            if db.set_task_status(self.conn, task_id, result["status_id"]):
                self.celebrate(task_id)
        if refresh:
            self.refresh(select_id=task_id)

    def save_edit(self, task_id, result):
        self.editing = None
        self.apply_edit(task_id, result)

    def cancel_edit(self):
        self.editing = None
        self.update_side()

    def finish_editing(self):
        """Уходим из формы (выбрали другую задачу и т. п.): если есть несохранённые
        изменения — спрашиваем, сохранить ли их."""
        if self.editing is None:
            return
        task_id, form, self.editing = self.editing, self.side.form, None
        if not form or not form.dirty() or db.get_task(self.conn, task_id) is None:
            return
        result = form.values()
        if not result["title"]:
            return
        if result["due_at"] is None:
            result["remind_before"] = None
        if messagebox.askyesno("Сохранить изменения?",
                               f"В задаче «{short_text(result['title'], 50)}» есть несохранённые "
                               "изменения. Сохранить их?", parent=self.root):
            self.apply_edit(task_id, result, refresh=False)
            self.root.after_idle(lambda: self.refresh(select_id=self.current_id()))

    def task_info(self, task_id):
        """Всё о задаче для карточки справа и письма."""
        row = next((r for r in db.list_tasks(self.conn) if r[0] == task_id), None)
        if row is None:
            return None
        _, title, done, created, due_at, remind_before, urgent, important, body, status_id = row
        name, color, _ = self.statuses.get(status_id, ("—", MUTED, done))
        overdue = bool(due_at and not done and datetime.fromisoformat(due_at) < datetime.now())
        level = priority_level(urgent, important)
        remind = REMIND_LABELS.get(remind_before, f"за {remind_before} мин") if due_at and remind_before else ""
        return dict(title=title, body=body, done=bool(done), overdue=overdue, status_id=status_id,
                    status=status_label(name, done, overdue), status_name=name, status_color=color,
                    level=level, priority=PRIORITY_NAMES[level], due=format_due(due_at),
                    remind=remind, created=created, urgent=urgent)

    def update_side(self):
        """Выбрана задача — показываем её карточку, иначе — Тоторо.
        Если задача редактируется, форма остаётся на месте."""
        task_id = self.current_id()
        if self.editing is not None:
            if task_id == self.editing and self.side.mode == "edit":
                return
            self.finish_editing()
        info = self.task_info(task_id) if task_id is not None else None
        if not info:
            self.side.show_totoro()
            return
        self.side.show_task(
            number=task_id, title=info["title"], body=info["body"], status=info["status"],
            status_color=DANGER if info["overdue"] else info["status_color"],
            overdue=info["overdue"], done=info["done"],
            priority_level_=info["level"], priority_name=info["priority"],
            due=info["due"], remind=info["remind"], created=info["created"],
        )

    def update_buddy(self):
        """Выбирает, что скажет Тоторо: о просроченной задаче, о задачах на сегодня и т. д."""
        now = datetime.now()
        rows = db.list_tasks(self.conn)
        active = [r for r in rows if not r[2]]
        due = {r[0]: datetime.fromisoformat(r[4]) for r in active if r[4]}
        overdue = [r for r in active if r[0] in due and due[r[0]] < now]
        today = [r for r in active if r[0] in due and now <= due[r[0]] and due[r[0]].date() == now.date()]

        def most_important(tasks):
            return min(tasks, key=lambda r: (priority_level(r[6], r[7]), due.get(r[0], datetime.max), r[0]))

        done_today = db.count_done_today(self.conn)
        stats = " · ".join(text for count, text in (
            (len(overdue), f"просрочено: {len(overdue)}"),
            (len(today), f"на сегодня: {len(today)}"),
            (done_today, f"сегодня выполнено: {done_today}"),
        ) if count)

        panel = self.side.totoro
        if not rows:
            panel.show("Привет! Я Тоторо.", tail="Добавь первую задачу — я присмотрю за ней.")
        elif overdue:
            # все просроченные — самые важные сверху; если их много, показываем первые
            overdue.sort(key=lambda r: (priority_level(r[6], r[7]), due[r[0]], r[0]))
            shown = overdue[:BUDDY_MAX_TASKS]
            if len(overdue) == 1:
                tail = "Давай сделаем её первой?"
            elif len(overdue) > len(shown):
                tail = (f"И ещё {len(overdue) - len(shown)}. Все просроченные — "
                        "кнопка «Просроченные» вверху.")
            else:
                tail = "Давай начнём с первой?"
            n = len(overdue)
            word = "задачи" if n % 10 == 1 and n % 100 != 11 else "задач"  # у 21 задачи, у 3 задач
            panel.show("Ой! Срок уже прошёл:" if n == 1 else f"Ой! Срок прошёл у {n} {word}:",
                       [(r[1], r[0]) for r in shown], tail, "alert", stats)
        elif today:
            task = min(today, key=lambda r: due[r[0]])
            more = f" Всего на сегодня: {len(today)}." if len(today) > 1 else ""
            panel.show("Сегодня срок:", [(task[1], task[0])],
                       f"до {due[task[0]].strftime('%H:%M')}." + more, "normal", stats)
        elif active:
            task = most_important(active)
            panel.show("Начни с самого важного:", [(task[1], task[0])],
                       f"Активных задач: {len(active)}. Ты справишься!", "normal", stats)
        else:
            panel.show("Все задачи выполнены!",
                       tail="Можно отдохнуть под камфорным деревом.", mood="done", stats=stats)

    # --- колонки доски (статусы) ---

    def add_lane(self):
        used = {color for _, color, _ in self.statuses.values()}
        color = next((c for _, c in LANE_COLORS if c not in used), LANE_COLORS[0][1])
        result = LaneDialog(self.root, color=color).show()
        if not result:
            return
        status_id = db.add_status(self.conn, result["name"], result["color"])
        if result["is_done"]:
            db.set_status_done(self.conn, status_id, True)
        if self.view.get() != "board":
            self.view.set("board")
            self.switch_view()
        else:
            self.refresh(select_id=self.current_id())

    def edit_lane(self, status_id):
        name, color, is_done = self.statuses[status_id]
        result = LaneDialog(self.root, name, color, is_done, new=False).show()
        if not result:
            return
        db.rename_status(self.conn, status_id, result["name"])
        db.set_status_color(self.conn, status_id, result["color"])
        if result["is_done"] != is_done:
            db.set_status_done(self.conn, status_id, result["is_done"])
        self.refresh(select_id=self.current_id())

    def lane_menu(self, status_id, x, y):
        name, color, is_done = self.statuses[status_id]
        order = list(self.statuses)
        index = order.index(status_id)
        colors = PopupMenu()
        for label, value in LANE_COLORS:
            colors.command(label, lambda v=value: self.set_lane_color(status_id, v),
                           icon=swatch(value), checked=value == color)
        (PopupMenu()
         .command("Настроить колонку…", lambda: self.edit_lane(status_id))
         .submenu("Цвет", colors, icon=swatch(color))
         .separator()
         .command("Сдвинуть влево", lambda: self.move_lane(status_id, -1), accel="←",
                  enabled=index > 0)
         .command("Сдвинуть вправо", lambda: self.move_lane(status_id, 1), accel="→",
                  enabled=index < len(order) - 1)
         .separator()
         .command("Удалить колонку…", lambda: self.delete_lane(status_id),
                  enabled=len(order) > 1, danger=True)
         ).popup(self.root, x, y)

    def set_lane_color(self, status_id, color):
        db.set_status_color(self.conn, status_id, color)
        self.refresh(select_id=self.current_id())

    def move_lane(self, status_id, step):
        db.move_status(self.conn, status_id, step)
        self.refresh(select_id=self.current_id())

    def reorder_lanes(self, ids):
        """Новый порядок колонок после перетаскивания на доске."""
        db.reorder_statuses(self.conn, ids)
        self.refresh(select_id=self.current_id())

    def delete_lane(self, status_id):
        if len(self.statuses) < 2:
            return
        name = self.statuses[status_id][0]
        target = next(sid for sid in self.statuses if sid != status_id)
        count = db.count_in_status(self.conn, status_id)
        moved = (f"\n\nЗадачи из неё ({count}) перейдут в колонку «{self.statuses[target][0]}»."
                 if count else "")
        if messagebox.askyesno("Удалить колонку?", f"Удалить колонку «{name}»?{moved}",
                               icon="warning", default="no", parent=self.root):
            db.delete_status(self.conn, status_id, target)
            self.refresh(select_id=self.current_id())

    def move_task(self, task_id, status_id):
        self.finish_editing()
        if db.set_task_status(self.conn, task_id, status_id):
            self.celebrate(task_id)
        self.refresh(select_id=task_id)

    # --- примеры, справка, «О программе» ---

    def add_examples(self):
        """Добавляет примеры задач; старые примеры при этом заменяются свежими."""
        if db.count_examples(self.conn):
            if not messagebox.askyesno(
                APP_NAME, "Примеры уже есть в списке.\n\nЗаменить их свежими (со сроками от сегодняшнего дня)?",
                parent=self.root,
            ):
                return
            db.delete_examples(self.conn)
        examples = make_examples()
        db.add_examples(self.conn, examples)
        self.filter.set("Все")
        self.refresh()
        messagebox.showinfo(
            APP_NAME,
            f"Добавлено примеров: {len(examples)}.\n\n"
            "Убрать их можно в меню «☰ Меню» → «Примеры задач» → «Удалить примеры задач» — ваши задачи не пострадают.",
            parent=self.root,
        )

    # --- экспорт и импорт CSV ---

    def ask_save_csv(self, title, name):
        return filedialog.asksaveasfilename(
            parent=self.root, title=title, initialfile=name, defaultextension=".csv",
            filetypes=[("Таблица CSV", "*.csv"), ("Все файлы", "*.*")])

    def save_file(self, path, header, rows):
        try:
            write_csv(path, header, rows)
            return True
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Не удалось сохранить файл:\n{error}\n\n"
                                 "Если он открыт в Excel — закройте его и попробуйте снова.",
                                 parent=self.root)
            return False

    def export_csv(self):
        rows = export_rows(self.conn)
        if not rows:
            messagebox.showinfo(APP_NAME, "Задач пока нет — выгружать нечего.", parent=self.root)
            return
        name = re.sub(r'[\\/:*?"<>|]', "_", self.current_list()["name"])  # без запрещённых в имени файла знаков
        path = self.ask_save_csv("Экспорт задач", f"{APP_NAME} {name} {date.today():%d.%m.%Y}.csv")
        if path and self.save_file(path, CSV_COLUMNS, rows):
            messagebox.showinfo(APP_NAME, f"Выгружено задач: {len(rows)}.\n\n{path}\n\n"
                                "Файл открывается в Excel двойным щелчком.", parent=self.root)

    def save_template(self):
        path = self.ask_save_csv("Шаблон для импорта", f"{APP_NAME} шаблон импорта.csv")
        if path and self.save_file(path, CSV_TEMPLATE_COLUMNS, template_rows()):
            messagebox.showinfo(
                APP_NAME,
                f"Шаблон сохранён:\n{path}\n\n"
                "Откройте его в Excel, замените строки-примеры своими задачами и сохраните "
                "в том же формате (CSV). Затем: ☰ Меню → Экспорт и импорт → Импорт задач из CSV.\n\n"
                "Обязателен только «Заголовок». Статус — название колонки доски. "
                "Приоритет — «Срочно и важно», «Важно», «Срочно» или «Обычный». "
                "Срок — «16.10.2026 18:00» или просто дата (тогда 09:00). "
                "Напомнить — «за 15 минут», «за 1 час», «за 1 день» и т. п.",
                parent=self.root)

    def import_csv(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Импорт задач",
            filetypes=[("Таблица CSV", "*.csv"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            tasks, notes = prepare_import(self.conn, read_csv(path))
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Не удалось открыть файл:\n{error}", parent=self.root)
            return
        except (ValueError, csv.Error) as error:
            messagebox.showerror(APP_NAME, f"Файл не подходит для импорта.\n\n{error}", parent=self.root)
            return
        if not tasks:
            messagebox.showwarning(APP_NAME, "В файле не найдено ни одной задачи с заголовком.",
                                   parent=self.root)
            return
        text = (f"Добавить задач из файла: {len(tasks)} — в список «{self.current_list()['name']}»?"
                "\n\nУже имеющиеся задачи останутся, новые получат свои номера.")
        if notes:
            shown = "\n".join("• " + n for n in notes[:8])
            more = f"\n…и ещё замечаний: {len(notes) - 8}" if len(notes) > 8 else ""
            text += f"\n\nЗамечания:\n{shown}{more}"
        if not messagebox.askyesno("Импорт задач", text, parent=self.root):
            return
        db.import_tasks(self.conn, tasks)
        self.filter.set("Все")
        self.refresh()
        messagebox.showinfo(APP_NAME, f"Добавлено задач: {len(tasks)}.", parent=self.root)

    def delete_examples(self):
        count = db.count_examples(self.conn)
        if not count:
            messagebox.showinfo(APP_NAME, "Примеров задач в списке нет.", parent=self.root)
            return
        if messagebox.askyesno(
            "Удалить примеры?",
            f"Удалить примеры задач ({count} шт.)?\n\nВаши собственные задачи останутся.",
            icon="warning", default="no", parent=self.root,
        ):
            db.delete_examples(self.conn)
            self.refresh()

    def show_help(self):
        """Открывает справку (или поднимает уже открытое окно справки)."""
        if self.help_window and self.help_window.winfo_exists():
            self.help_window.deiconify()
            self.help_window.lift()
            self.help_window.focus_force()
            return
        self.help_window = HelpWindow(self.root)

    def show_about(self):
        AboutWindow(self.root, on_license=self.show_license)

    def show_license(self):
        LicenseWindow(self.root)

    # --- подсказка в пустом поле ввода ---

    def placeholder_shown(self):
        return self.entry.cget("style") == "Placeholder.TEntry"

    def show_placeholder(self):
        if not self.entry.get():
            self.entry.insert(0, PLACEHOLDER)
            self.entry.configure(style="Placeholder.TEntry")
            self.cursor_to_start()

    def hide_placeholder(self):
        if self.placeholder_shown():
            self.entry.delete(0, "end")
            self.entry.configure(style="TEntry")

    def cursor_to_start(self):
        if self.placeholder_shown():
            self.entry.selection_clear()
            self.entry.icursor(0)

    def on_entry_key(self, event):
        """Подсказка исчезает, как только пользователь начинает печатать."""
        if not self.placeholder_shown():
            return None
        if event.char and event.char.isprintable():
            self.hide_placeholder()
            return None
        if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Home", "End"):
            return "break"  # не даём стирать или двигаться по тексту подсказки
        return None

    def entry_text(self):
        if self.placeholder_shown():
            return ""
        return self.entry.get().strip()

    # --- таблица и доска ---

    def update_hscroll(self, first, last):
        """Горизонтальная прокрутка — если столбцы вместе шире таблицы."""
        needed = not (float(first) <= 0 and float(last) >= 1)
        if needed and not self.hscroll.winfo_ismapped():
            self.hscroll.pack(side="bottom", fill="x", before=self.tree)
        elif not needed and self.hscroll.winfo_ismapped():
            self.hscroll.pack_forget()
        self.hscroll.set(first, last)

    def update_scrollbar(self, first, last):
        """Полоса прокрутки видна, только если задачи не помещаются в окно."""
        needed = not (float(first) <= 0 and float(last) >= 1)
        if needed != self.scrollbar.winfo_ismapped():
            if needed:
                self.scrollbar.pack(side="right", fill="y", pady=4, before=self.tree)
            else:
                self.scrollbar.pack_forget()
        self.scrollbar.set(first, last)

    def repaint(self):
        """Перестраивает таблицу, когда окно уже на экране. Если строить её только
        до показа окна, в Tk 9 красный цвет просроченной строки может «протечь»
        в правые столбцы остальных строк."""
        self.refresh(select_id=self.current_id())

    def refresh(self, select_id=None):
        """Перечитывает задачи из базы (с учётом фильтра) и рисует таблицу и доску заново."""
        statuses = db.list_statuses(self.conn)
        self.statuses = {sid: (name, color, bool(done)) for sid, name, color, done in statuses}
        rows = db.list_tasks(self.conn)
        active = sum(1 for row in rows if not row[2])
        self.chips["active"].configure(text=f"активных  {active}")
        self.chips["done"].configure(text=f"выполнено  {len(rows) - active}")
        self.chips["today"].configure(text=f"✔ сегодня  {db.count_done_today(self.conn)}")

        wanted = FILTERS[self.filter.get()]
        now = datetime.now()
        late = {r[0] for r in rows if r[4] and not r[2] and datetime.fromisoformat(r[4]) < now}
        self.overdue_button.configure(text=f"Просроченные  {len(late)}" if late else "Просроченные")
        if wanted == "overdue":
            rows = [row for row in rows if row[0] in late]
        elif wanted is not None:
            rows = [row for row in rows if bool(row[2]) == wanted]
        rows = self.sort_rows(rows, statuses)
        now = datetime.now()
        overdue_ids = {r[0] for r in rows if r[4] and not r[2] and datetime.fromisoformat(r[4]) < now}

        self.tree.delete(*self.tree.get_children())
        self.due, self.row_status = {}, {}
        for task_id, title, done, created, due_at, remind_before, urgent, important, _, status_id in rows:
            remind = REMIND_LABELS.get(remind_before, f"за {remind_before} мин") if due_at else ""
            if remind == "Не напоминать":
                remind = ""
            level = priority_level(urgent, important)
            iid = str(task_id)
            name = self.statuses.get(status_id, ("—",))[0]
            self.row_status[iid] = name
            self.tree.insert(
                "", "end", iid=iid, image=IMAGES.get(f"priority_{level}", ""),
                values=(f"#{task_id}", status_label(name, done), title, PRIORITY_NAMES[level],
                        format_due(due_at), remind, created),
                tags=("done",) if done else ("normal",),
            )
            if due_at and not done:
                self.due[iid] = datetime.fromisoformat(due_at)
        self.mark_overdue()

        if self.tree.get_children():
            self.empty.place_forget()
        else:
            self.empty.configure(text=EMPTY_TEXT[self.filter.get()])
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

        if self.view.get() == "board":
            self.board.render(statuses, rows, overdue_ids)

        if select_id is not None:
            self.select_task(select_id)
        self.update_buddy()
        self.update_side()
        self.shown_state = self.time_state()

    def time_state(self):
        """То, что меняется само по себе, со временем: какие задачи уже просрочены и какой
        сегодня день (счётчик «сегодня»). Если это не изменилось, перерисовывать нечего."""
        now = datetime.now()
        overdue = frozenset(r[0] for r in db.list_tasks(self.conn, done=False)
                            if r[4] and datetime.fromisoformat(r[4]) < now)
        return overdue, date.today()

    def sort_rows(self, rows, statuses):
        """Сортировка по столбцу (щелчок по заголовку) или по списку «Сортировка».
        При сортировке по столбцу пустые значения (нет срока, напоминания) всегда внизу."""
        if not self.column_sort:
            return sorted(rows, key=self.sort_key)
        column, descending = self.column_sort
        position = {s[0]: i for i, s in enumerate(statuses)}

        def value(row):
            task_id, title, done, _, due_at, remind_before, urgent, important, _, status_id = row
            return {
                "num": task_id,
                "created": task_id,  # номера растут по порядку создания
                "status": position.get(status_id, len(position)),
                "title": title.casefold(),
                "priority": priority_level(urgent, important),
                "due": due_at,
                "remind": remind_before if due_at else None,
            }[column]

        rows = sorted(rows, key=lambda r: r[0])
        filled = sorted((r for r in rows if value(r) is not None), key=value, reverse=descending)
        return filled + [r for r in rows if value(r) is None]

    def sort_by_column(self, column):
        if self.column_sort and self.column_sort[0] == column:
            self.column_sort = [column, not self.column_sort[1]]
        else:
            self.column_sort = [column, False]
        db.set_json_setting(self.prefs, "list_sort", self.column_sort)
        self.show_column_sort()
        self.refresh(select_id=self.current_id())

    def sort_chosen(self):
        """Выбран вариант в списке «Сортировка» — сортировка по столбцу отменяется."""
        self.column_sort = None
        db.set_json_setting(self.prefs, "list_sort", None)
        self.show_column_sort()
        self.refresh(select_id=self.current_id())

    def show_column_sort(self):
        """Стрелка ▲/▼ у заголовка столбца, по которому отсортировано, и подпись в списке."""
        column, descending = self.column_sort or (None, False)
        arrow = "▼" if descending else "▲"
        for key, text in self.column_titles.items():
            self.tree.heading(key, text=f"{text}  {arrow}" if key == column else text)
        if column:
            self.sort.set(f"По столбцу «{self.column_titles[column].capitalize()}» {arrow}")
        elif self.sort.get() not in SORTS:
            self.sort.set(SORTS[0])

    def sort_key(self, row):
        """Выполненные всегда внизу; дальше — по выбранной сортировке."""
        task_id, _, done, _, due_at, _, urgent, important, _, _ = row
        level = priority_level(urgent, important)
        no_due = due_at is None
        due = due_at or ""
        mode = self.sort.get()
        if mode == "По приоритету":
            return (done, level, no_due, due, task_id)
        if mode == "По сроку":
            return (done, no_due, due, level, task_id)
        return (done, task_id)

    def mark_overdue(self):
        """Красным подсвечиваются невыполненные задачи с прошедшим сроком."""
        now = datetime.now()
        for iid, due in self.due.items():
            if self.tree.exists(iid):
                overdue = due < now
                tags = self.tree.item(iid, "tags")
                wanted = "overdue" if overdue else "normal"
                if wanted not in tags:  # меняем только то, что изменилось; подсветка под мышью остаётся
                    self.tree.item(iid, tags=[wanted] + (["hover"] if "hover" in tags else []))
                    self.tree.set(iid, "status", status_label(self.row_status[iid], False, overdue))

    def selected(self):
        """Возвращает (id, выполнена ли) выбранной задачи или None."""
        task_id = self.current_id()
        info = self.task_info(task_id) if task_id is not None else None
        if not info:
            where = "на доске" if self.view.get() == "board" else "в списке"
            messagebox.showinfo(APP_NAME, f"Сначала выберите задачу {where}.", parent=self.root)
            return None
        return task_id, info["done"]

    def add(self):
        title = self.entry_text()
        if not title:
            return
        task_id = db.add_task(self.conn, title)
        self.entry.delete(0, "end")
        self.show_placeholder()
        if FILTERS[self.filter.get()] not in (None, False):
            self.filter.set("Все")  # иначе новую задачу (без срока) не будет видно
        self.refresh(select_id=task_id)

    def edit(self):
        task = self.selected()
        if task is None:
            return
        task_id = task[0]
        statuses = db.list_statuses(self.conn)
        if self.in_paned(self.side):
            # Изменяем прямо в правой панели
            if self.editing == task_id:
                self.side.form.focus_title()
                return
            self.finish_editing()
            self.editing = task_id
            self.side.show_form(self.form_data(task_id), statuses,
                                on_save=lambda result: self.save_edit(task_id, result),
                                on_cancel=self.cancel_edit)
            return
        # Окно узкое и панель скрыта — открываем форму в отдельном окне
        dialog = TaskDialog(self.root, self.form_data(task_id), statuses)
        self.root.wait_window(dialog)
        if dialog.result:
            self.apply_edit(task_id, dialog.result)

    def toggle(self):
        task = self.selected()
        if task is None:
            return
        self.finish_editing()
        task_id, done = task[0], self.task_info(task[0])["done"]
        if not db.set_done(self.conn, task_id, not done):
            messagebox.showinfo(
                APP_NAME,
                "На доске нет колонки, куда можно перенести задачу.\n\n"
                "Отметьте одну из колонок как «Задачи здесь считаются выполненными» "
                "(меню «⋯» в заголовке колонки → «Настроить колонку…»).",
                parent=self.root,
            )
            return
        if not done:
            self.celebrate(task_id)
        self.refresh(select_id=task_id)

    def delete(self):
        task = self.selected()
        if task is None:
            return
        title = db.get_task(self.conn, task[0])[0]
        if not messagebox.askyesno(
            "Удалить задачу?",
            f"Удалить задачу «{title}»?\n\nВернуть её будет нельзя.",
            icon="warning", default="no", parent=self.root,
        ):
            return
        if self.editing == task[0]:
            self.editing = None  # задача удалена — сохранять в ней нечего
        db.delete_task(self.conn, task[0])
        self.clear_selection()
        self.refresh()

    # --- меню по правой кнопке мыши ---

    def show_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.focus(row)
        self.show_menu_for(int(row), event.x_root, event.y_root)

    def show_menu_for_selected(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        x, y, _, height = self.tree.bbox(sel[0])
        self.show_menu_for(int(sel[0]), self.tree.winfo_rootx() + x + 40,
                           self.tree.winfo_rooty() + y + height)

    def show_menu_for(self, task_id, x, y):
        self.select_task(task_id)
        self.build_menu(task_id).popup(self.root, x, y)

    def build_menu(self, task_id):
        title, due_at, remind_before, urgent, important, body = db.get_task(self.conn, task_id)
        info = self.task_info(task_id)

        statuses = PopupMenu()
        for sid, (name, color, _) in self.statuses.items():
            statuses.command(name, lambda s=sid: self.move_task(task_id, s), icon=swatch(color),
                             checked=sid == info["status_id"])

        priority = (PopupMenu()
                    .command("Срочно", lambda: self.quick_priority(task_id, not urgent, important),
                             checked=bool(urgent))
                    .command("Важно", lambda: self.quick_priority(task_id, urgent, not important),
                             checked=bool(important)))

        due = PopupMenu()
        for label, days in (("Сегодня", 0), ("Завтра", 1), ("Через неделю", 7)):
            due.command(label, lambda d=days: self.quick_due(task_id, d))
        due.separator()
        due.command("Выбрать дату и время…", self.edit)
        due.command("Убрать срок", lambda: self.quick_due(task_id, None), enabled=bool(due_at))

        remind = PopupMenu()
        for label, minutes in REMIND_OPTIONS.items():
            remind.command(label, lambda m=minutes: self.quick_remind(task_id, m),
                           checked=minutes == remind_before)

        lists = PopupMenu()
        for item in self.lists:
            if item["id"] != self.list_id:
                lists.command(item["name"], lambda i=item["id"]: self.move_to_list(task_id, i))

        return (PopupMenu()
                .command("Изменить…", self.edit, accel="F2")
                .command("Вернуть в работу" if info["done"] else "Отметить выполненной",
                         self.toggle, accel="Пробел")
                .submenu("Статус", statuses, icon=swatch(info["status_color"]))
                .separator()
                .submenu("Приоритет", priority,
                         icon=IMAGES.get(f"priority_{info['level']}"))
                .submenu("Срок", due)
                .submenu("Напомнить" if due_at else "Напомнить (сначала задайте срок)", remind,
                         enabled=bool(due_at))
                .separator()
                .command("Создать письмо…", self.email, accel="Ctrl+E")
                .command("Копировать текст", lambda: self.copy_text(f"{title}\n\n{body}".strip()))
                .submenu("Переместить в список", lists, enabled=len(self.lists) > 1)
                .separator()
                .command("Удалить", self.delete, accel="Del", danger=True))

    def quick_due(self, task_id, days):
        """Быстрая смена срока из меню. Время сохраняется прежним (или 09:00)."""
        self.finish_editing()
        title, due_at, remind_before, urgent, important, _ = db.get_task(self.conn, task_id)
        if days is None:
            due_at, remind_before = None, None
        else:
            old = datetime.fromisoformat(due_at).time() if due_at else time(*map(int, DEFAULT_TIME))
            due_at = datetime.combine(date.today() + timedelta(days=days), old).strftime("%Y-%m-%d %H:%M")
        db.update_task(self.conn, task_id, title, due_at, remind_before, urgent, important)
        self.refresh(select_id=task_id)

    def quick_remind(self, task_id, minutes):
        self.finish_editing()
        title, due_at, _, urgent, important, _ = db.get_task(self.conn, task_id)
        db.update_task(self.conn, task_id, title, due_at, minutes, urgent, important)
        self.refresh(select_id=task_id)

    def quick_priority(self, task_id, urgent, important):
        self.finish_editing()
        title, due_at, remind_before, _, _, _ = db.get_task(self.conn, task_id)
        db.update_task(self.conn, task_id, title, due_at, remind_before, urgent, important)
        self.refresh(select_id=task_id)

    def copy_text(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def email(self):
        """Открывает новое письмо в почтовой программе с данными выбранной задачи."""
        task = self.selected()
        if task is None:
            return
        info = self.task_info(task[0])
        subject, body = build_email(task[0], info["title"], info["status_name"], info["priority"],
                                    info["due"], info["remind"], info["created"],
                                    info["urgent"], info["body"])
        # Основной способ — черновик письма в файле .eml: Outlook открывает его как новое
        # письмо, и длина текста не ограничена (в отличие от ссылки mailto:).
        try:
            os.startfile(write_draft(task[0], subject, body))
            return
        except OSError:
            pass  # .eml открыть нечем — пробуем ссылку mailto:
        url = f"mailto:?subject={quote(subject, safe='')}&body={quote(body, safe='')}"
        too_long = len(url) > MAILTO_LIMIT
        if too_long:
            # Почтовые программы не принимают слишком длинные ссылки: откроем письмо
            # с темой, а текст положим в буфер обмена.
            url = f"mailto:?subject={quote(subject, safe='')}"
            self.copy_text(body)
        try:
            os.startfile(url)  # откроет почтовую программу по умолчанию (например, Outlook)
            if too_long:
                messagebox.showinfo(
                    APP_NAME,
                    "Описание задачи длинное, поэтому текст письма скопирован.\n\n"
                    "Щёлкните в тексте письма и нажмите Ctrl+V.",
                    parent=self.root,
                )
        except OSError:
            self.copy_text(f"{subject}\n\n{body}")
            messagebox.showwarning(
                APP_NAME,
                "Не удалось открыть почтовую программу.\n\n"
                "Тема и текст письма скопированы — вставьте их в письмо вручную (Ctrl+V).",
                parent=self.root,
            )

    # --- напоминания ---

    def check_reminders(self):
        """Раз в 30 секунд проверяет, не пора ли о чём-то напомнить."""
        # Перерисовываем, только если какая-то задача стала просроченной или наступил новый день:
        # иначе доска и список «вздрагивали» бы каждые 30 секунд
        if self.time_state() != self.shown_state and not self.board.drag:
            self.refresh(select_id=self.current_id())
        self.update_buddy()
        self.update_side()
        # Напоминания — по задачам из всех списков, не только из открытого
        lines = []
        for item in self.lists:
            conn = self.list_conn(item["id"])
            where = "" if item["id"] == self.list_id else f"  (список «{item['name']}»)"
            for task_id, title, due_at in db.due_reminders(conn):
                db.mark_reminded(conn, task_id)
                lines.append(f"• {title} — срок {format_due(due_at)}{where}")
        if lines:
            # Показываем окно поверх всех остальных, даже если оно было свёрнуто.
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.bell()
            messagebox.showinfo("Напоминание", "Напоминаю о задачах:\n\n" + "\n".join(lines), parent=self.root)
            self.root.attributes("-topmost", False)
        self.root.after(CHECK_EVERY_MS, self.check_reminders)

    # --- списки задач ---

    def list_conn(self, list_id):
        """Соединение с файлом списка (открывается один раз и потом переиспользуется)."""
        if list_id not in self.list_conns:
            item = next(i for i in self.lists if i["id"] == list_id)
            self.list_conns[list_id] = db.connect(db.list_path(item))
        return self.list_conns[list_id]

    def current_list(self):
        return next(i for i in self.lists if i["id"] == self.list_id)

    def show_list_name(self):
        name = self.current_list()["name"]
        self.list_button.configure(text=f"{name}  ▾")
        self.root.title(f"{APP_NAME} — {name}")

    def show_lists_menu(self):
        menu = PopupMenu()
        for item in self.lists:
            menu.command(item["name"], lambda i=item["id"]: self.switch_list(i),
                         checked=item["id"] == self.list_id)
        personal = self.list_id == db.PERSONAL
        (menu.separator()
             .command("Новый список…", self.new_list)
             .command("Переименовать список…", self.rename_list)
             .command("Удалить список…", self.delete_list, enabled=not personal, danger=True))
        b = self.list_button
        menu.popup(self.root, b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + 4)

    def switch_list(self, list_id):
        if list_id == self.list_id:
            return
        self.finish_editing()  # спросит, сохранить ли незаконченную правку задачи
        self.clear_selection()
        self.list_id = list_id
        self.conn = self.list_conn(list_id)
        db.set_setting(self.prefs, "current_list", list_id)
        self.show_list_name()
        self.refresh()

    def new_list(self):
        name = NameDialog(self.root, "Новый список", "Новый список", "",
                          "Например: «Команда», «Дом», «Проект Альфа».", "Создать").show()
        if not name:
            return
        file = db.new_list_file()
        item = {"id": file.removesuffix(".db"), "name": name, "file": file}
        self.lists.append(item)
        db.save_registry(self.prefs, self.lists)
        self.switch_list(item["id"])

    def rename_list(self):
        item = self.current_list()
        name = NameDialog(self.root, "Переименовать список", "Название списка", item["name"]).show()
        if name and name != item["name"]:
            item["name"] = name
            db.save_registry(self.prefs, self.lists)
            self.show_list_name()

    def delete_list(self):
        item = self.current_list()
        if item["id"] == db.PERSONAL:
            return
        count = db.count_tasks(self.conn)
        what = f"вместе с задачами ({count} шт.)" if count else "(задач в нём нет)"
        if not messagebox.askyesno(
            "Удалить список?",
            f"Удалить список «{item['name']}» {what}?\n\nВернуть его будет нельзя. Если задачи "
            "нужны — сначала перенесите их в другой список (правая кнопка мыши → «Переместить "
            "в список») или выгрузите в CSV.",
            icon="warning", default="no", parent=self.root,
        ):
            return
        self.switch_list(db.PERSONAL)
        self.list_conns.pop(item["id"]).close()
        self.lists.remove(item)
        db.save_registry(self.prefs, self.lists)
        try:
            db.list_path(item).unlink()
        except OSError:
            pass  # файл занят или уже удалён — список всё равно убран из программы

    def move_to_list(self, task_id, list_id):
        self.finish_editing()
        target = next(i for i in self.lists if i["id"] == list_id)
        db.move_task_to(self.conn, task_id, self.list_conn(list_id))
        self.clear_selection()
        self.refresh()
        self.side.totoro.show(f"Задача перенесена в список «{target['name']}».", mood="done")

    # --- обновления ---

    def auto_update_enabled(self):
        return db.get_setting(self.prefs, "update_auto", "1") == "1"

    def auto_check_update(self):
        """При запуске, не чаще раза в день. Без интернета — молча пропускаем."""
        today = date.today().isoformat()
        if not self.auto_update_enabled() or db.get_setting(self.prefs, "update_checked") == today:
            return

        def done(release, error):
            if error:
                return
            db.set_setting(self.prefs, "update_checked", today)
            if updater.is_newer(release["version"], APP_VERSION):
                UpdateDialog(self.root, release, self.close)
        in_background(self.root, updater.fetch_latest, done)

    def check_update_now(self):
        def done(release, error):
            if error:
                messagebox.showwarning(APP_NAME, str(error), parent=self.root)
            elif updater.is_newer(release["version"], APP_VERSION):
                UpdateDialog(self.root, release, self.close)
            else:
                messagebox.showinfo(APP_NAME, f"У вас последняя версия — {APP_VERSION}.", parent=self.root)
        in_background(self.root, updater.fetch_latest, done)

    def close(self):
        for conn in self.list_conns.values():
            conn.close()
        self.root.destroy()


if __name__ == "__main__":
    # Чтобы на панели задач была наша иконка, а не значок Python.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ToDoro.App")
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    TodoApp(root)
    root.mainloop()
