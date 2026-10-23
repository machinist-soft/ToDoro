"""ToDoro — список дел с Тоторо."""
import calendar
import csv
import ctypes
import errno
import math
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time as time_module
import tkinter as tk
import webbrowser
from email import policy as email_policy
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import quote
from ctypes import wintypes
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tkinter import colorchooser, filedialog, font as tkfont, ttk

import db
import outlook
import phone
import richtext
import smart
import snip
import team
import tray
import updater
from examples import make_examples
from help_text import HELP

APP_NAME = "ToDoro"  # ToDo + Totoro
APP_VERSION = "2.25"  # номер версии — меняется здесь (установщик берёт его отсюда)
APP_YEAR = 2026
COPYRIGHT_HOLDER = "Machinist"  # автор — имя меняется здесь и в файле LICENSE
COPYRIGHT = f"© {APP_YEAR} {COPYRIGHT_HOLDER}"
LICENSE_PATH = Path(__file__).with_name("LICENSE")
RELEASE_NOTES_PATH = Path(__file__).with_name("RELEASE_NOTES.md")  # окно «Что нового»
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
FONT_SMALL_BOLD = ("Segoe UI Semibold", 10)
FONT_TITLE = ("Segoe UI Semibold", 20)

# Палитры: светлая и тёмная. Все цвета интерфейса берутся отсюда по имени.
# Тема выбирается в настройках и применяется при запуске программы.
PALETTES = {
    "light": dict(
        BG="#f4f6fb",               # фон окна
        SURFACE="#ffffff",          # карточки, поля ввода
        BORDER="#e3e7ef",
        TEXT="#1f2937",
        MUTED="#6b7280",
        DONE="#9ca3af",             # выполненные задачи, подсказки
        ACCENT="#2563eb", ACCENT_HOVER="#1d4ed8", ACCENT_PRESSED="#1e40af",
        ACCENT_SOFT="#e8efff",      # выделенная строка, выбранный раздел
        ACCENT_SOFT_HOVER="#dbe6ff",
        DANGER="#dc2626", DANGER_SOFT="#fdf0f0", DANGER_SOFT_HOVER="#fbe1e1",
        SEGMENT_BG="#e7ebf3", SEGMENT_HOVER="#dde3ee",
        HOVER="#e9edf4",            # наведение на мягкие кнопки и пункты
        BUTTON_HOVER="#f3f5f9", BUTTON_PRESSED="#e5e7eb", SOFT_PRESSED="#dfe4ec",
        ROW_HOVER="#f6f8fc", HEADING_LINE="#dfe3ea",
        SCROLL="#d6dbe4", SCROLL_ACTIVE="#b8c0cc", CHECK_BORDER="#b8c0cc",
        POPUP_BORDER="#cbd2dd", MENU_BORDER="#d3d9e3", DASHED="#cfd5df",
        OTHER_MONTH="#c4c9d2", FOUND="#fff1a8",
        ALERT_BG="#fdeeee", ALERT_BORDER="#f3c4c4",
        GOOD_BG="#eaf7ef", GOOD_BORDER="#bfe5cc", GOOD_TEXT="#15803d",
        CHIP_BG="#eef1f6", CHIP_GOOD_BG="#e8f7ee",
        OK_DOT="#16a34a", WARN="#d97706", BUSY="#f59e0b",
        CARD_BORDER="#e9ecf2",      # рамка карточки на доске (у выбранной — синяя)
        CATBUS_KEY="#f3f5fa",       # «прозрачный» цвет окна Котобуса — почти цвет фона
        SIGN_TEXT="#166534", SIGN_BG="#e8f7ee", SIGN_BORDER="#86d3a3",
        TINT_BASE="#ffffff",        # к какому цвету «разбавляются» цвета колонок доски
        BRAND="#00978c",            # бирюзовый цвет значка ToDoro (логотип вверху окна)
    ),
    "dark": dict(
        BG="#15181e",
        SURFACE="#1e222a",
        BORDER="#2e3440",
        TEXT="#e5e7eb",
        MUTED="#9aa3b2",
        DONE="#6b7280",
        ACCENT="#4f8cff", ACCENT_HOVER="#6a9dff", ACCENT_PRESSED="#3b74e0",
        ACCENT_SOFT="#22324f",
        ACCENT_SOFT_HOVER="#2a3d60",
        DANGER="#f87171", DANGER_SOFT="#3a2226", DANGER_SOFT_HOVER="#4a2a2f",
        SEGMENT_BG="#262b34", SEGMENT_HOVER="#30363f",
        HOVER="#2a303a",
        BUTTON_HOVER="#272c35", BUTTON_PRESSED="#323844", SOFT_PRESSED="#323844",
        ROW_HOVER="#242933", HEADING_LINE="#363d4a",
        SCROLL="#3a404c", SCROLL_ACTIVE="#4b5262", CHECK_BORDER="#5b6372",
        POPUP_BORDER="#3a404c", MENU_BORDER="#3a404c", DASHED="#4b5262",
        OTHER_MONTH="#4b5262", FOUND="#5c4a10",
        ALERT_BG="#3a2226", ALERT_BORDER="#5c2f35",
        GOOD_BG="#1f3329", GOOD_BORDER="#2f5a41", GOOD_TEXT="#4ade80",
        CHIP_BG="#262b34", CHIP_GOOD_BG="#1f3329",
        OK_DOT="#22c55e", WARN="#f59e0b", BUSY="#f59e0b",
        CARD_BORDER="#2a303a",
        CATBUS_KEY="#16191f",
        SIGN_TEXT="#86efac", SIGN_BG="#1f3329", SIGN_BORDER="#2f5a41",
        TINT_BASE="#1e222a",
        BRAND="#2bb8ac",
    ),
}
THEMES = {"light": "Светлая", "dark": "Тёмная", "system": "Как в Windows"}


def windows_dark_mode():
    """Включена ли в Windows тёмная тема для приложений."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


THEME_SETTING = db.peek_setting("theme", "light")  # light, dark или system
THEME = ("dark" if windows_dark_mode() else "light") if THEME_SETTING == "system" else THEME_SETTING
if THEME not in PALETTES:
    THEME = "light"
globals().update(PALETTES[THEME])  # BG, SURFACE, TEXT, … — цвета выбранной темы

# Варианты фильтра: подпись кнопки -> какие задачи показывать
FILTERS = {
    "Все": None,
    "Активные": False,
    "Выполненные": True,
    "Просроченные": "overdue",  # невыполненные с прошедшим сроком
}
EMPTY_TEXT = {
    "Все": "Задач пока нет — нажмите «＋ Добавить задачу» выше",
    "Активные": "Все задачи выполнены 🎉",
    "Выполненные": "Выполненных задач пока нет",
    "Просроченные": "Просроченных задач нет — всё успеваете 🎉",
}
BUDDY_MAX_TASKS = 5  # сколько просроченных задач Тоторо называет в облачке
REMINDERS_MAX = 12  # сколько задач помещается в окне напоминаний

# Варианты напоминания: подпись -> за сколько минут до срока напомнить
REMIND_OPTIONS = {
    "Не напоминать": None,
    "За 5 минут": 5,
    "За 15 минут": 15,
    "За 30 минут": 30,
    "За 1 час": 60,
    "За 2 часа": 120,
    "За 1 день": 24 * 60,
    "За 2 дня": 2 * 24 * 60,
    "За 1 неделю": 7 * 24 * 60,
}
REMIND_LABELS = {minutes: label for label, minutes in REMIND_OPTIONS.items()}

# Повтор задачи (db.REPEATS): пункт выпадающего списка → ключ в базе
REPEAT_OPTIONS = {"Не повторять": None, "Ежедневно": "day", "Еженедельно": "week",
                  "Ежемесячно": "month", "Ежеквартально": "quarter", "Раз в полгода": "halfyear",
                  "Ежегодно": "year"}
REPEAT_LABELS = {key: label for label, key in REPEAT_OPTIONS.items()}


def remind_label(minutes):
    """Подпись напоминания: «За 1 час»; своё время (например, из файла CSV) — «За 1 ч 30 мин»."""
    if minutes in REMIND_LABELS:
        return REMIND_LABELS[minutes]
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = [f"{n} {unit}" for n, unit in ((days, "дн"), (hours, "ч"), (mins, "мин")) if n]
    return "За " + " ".join(parts or ["0 мин"])

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
    suffix = "_dark" if THEME == "dark" and "check_on_dark" in IMAGES else ""
    if "check_on" in IMAGES and "Nice.indicator" not in style.element_names():
        style.element_create("Nice.indicator", "image", IMAGES["check_off" + suffix],
                             ("selected", IMAGES["check_on" + suffix]), sticky="w", width=26)
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Nice.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.label", {"side": "left", "sticky": "nswe"})]})])

DEFAULT_TIME = ("09", "00")  # время срока по умолчанию
CHECK_EVERY_MS = 30_000      # как часто проверять напоминания (30 секунд)
WATCH_EVERY_MS = 300         # как часто смотреть на результат фоновой проверки общей папки

HOURS = [f"{h:02d}" for h in range(24)]
MINUTES = [f"{m:02d}" for m in range(0, 60, 5)]
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
          "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

SEARCH_HINT = "Поиск задач  (Ctrl+F)"
# Длиннее ссылку «создать письмо» (mailto:) почтовые программы могут не принять:
# Outlook ломался уже на ~1700 символах (русская буква в ссылке занимает 6 символов).
MAILTO_LIMIT = 1000
# временные черновики писем (.eml) и копии открытых файлов задач; старше недели — удаляются при запуске
DRAFTS_DIR = Path(tempfile.gettempdir()) / APP_NAME
TEMP_MAX_AGE = 7 * 24 * 3600  # секунд: неделя — копию файла могут держать открытой несколько дней


APP_CHECK_MS = 200  # как часто открытый выпадающий список проверяет, активна ли ещё ToDoro
_watched_popups = set()  # окна (имена в Tk), за которыми сейчас следит close_when_inactive


def app_is_active():
    """Активное окно Windows — одно из окон ToDoro (этого процесса)? Если активного окна нет
    (Windows как раз переключает окна) — считаем, что да, чтобы ничего не закрыть зря."""
    if os.name != "nt":
        return True
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == os.getpid()
    except (AttributeError, OSError):
        return True


def close_when_inactive(widget, close, path=None):
    """Пока всплывающее окно открыто, следит, активна ли ToDoro: переключились в другую
    программу (щелчок в Excel, Alt+Tab) — вызывает close(). Нужно потому, что такие окна
    закрываются по потере фокуса, а на Windows фокус они получают не всегда — и тогда окно
    оставалось висеть поверх чужих программ (issue #4).
    path — имя окна в Tk, если окно создал сам Tk (у Python для него нет объекта): тогда
    widget — любое живое окно программы, через него и спрашиваем."""
    path = path or str(widget)
    if path in _watched_popups:
        return  # список закрыли и снова открыли быстрее проверки — прежняя слежка ещё идёт
    # Проверку ставим через главное окно: команда, заведённая через само всплывающее окно,
    # исчезает вместе с ним, и ожидающая проверка падала бы с «invalid command name»
    root = widget._root()
    _watched_popups.add(path)

    def check():
        try:
            if not int(root.tk.eval(f"expr {{[winfo exists {path}] && [winfo ismapped {path}]}}")):
                _watched_popups.discard(path)
                return  # уже закрыто — слежка кончается сама
        except tk.TclError:
            _watched_popups.discard(path)
            return
        if app_is_active():
            root.after(APP_CHECK_MS, check)
        else:
            _watched_popups.discard(path)
            close()
    root.after(APP_CHECK_MS, check)



def watch_combobox_popdowns(root):
    """Выпадающие списки ttk.Combobox (статус, напоминание, часы…) во всех окнах закрываются,
    когда ToDoro перестаёт быть активной программой. Значение при этом не меняется."""
    def mapped(event):
        popdown = str(event.widget)  # окно списка создаёт сам Tk: «<поле>.popdown»
        combobox = popdown.rsplit(".", 1)[0]

        def unpost():
            try:
                root.tk.call("ttk::combobox::Unpost", combobox)
            except tk.TclError:
                pass

        close_when_inactive(root, unpost, popdown)
    root.bind_class("ComboboxPopdown", "<Map>", mapped, add="+")


def setup_style(root):
    """Внешний вид всех элементов: плоские кнопки, светлый фон, акцентный синий."""
    root.configure(bg=BG)
    watch_combobox_popdowns(root)
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
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
              background=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
              bordercolor=[("active", ACCENT_HOVER)],
              lightcolor=[("active", ACCENT_HOVER)], darkcolor=[("active", ACCENT_HOVER)],
              focuscolor=[("active", ACCENT_HOVER)])
    style.configure("TButton", background=SURFACE, foreground=TEXT,
                    lightcolor=SURFACE, darkcolor=SURFACE, focuscolor=SURFACE, **flat)
    style.map("TButton",
              background=[("pressed", BUTTON_PRESSED), ("active", BUTTON_HOVER)],
              lightcolor=[("active", BUTTON_HOVER)], darkcolor=[("active", BUTTON_HOVER)],
              focuscolor=[("active", BUTTON_HOVER)])
    style.configure("Danger.TButton", foreground=DANGER)
    for name, fg, bg, hover in (("AccentSoft", ACCENT, ACCENT_SOFT, ACCENT_SOFT_HOVER),
                                ("DangerSoft", DANGER, DANGER_SOFT, DANGER_SOFT_HOVER)):
        style.configure(f"{name}.TButton", foreground=fg, background=bg, lightcolor=bg,
                        darkcolor=bg, bordercolor=bg, focuscolor=bg, padding=(12, 6),
                        font=FONT_SMALL)
        style.map(f"{name}.TButton", background=[("active", hover)], lightcolor=[("active", hover)],
                  darkcolor=[("active", hover)], bordercolor=[("active", hover)],
                  focuscolor=[("active", hover)])
    style.configure("Soft.TButton", background=BG, lightcolor=BG, darkcolor=BG,
                    bordercolor=BG, focuscolor=BG, padding=(12, 6))
    style.map("Soft.TButton", background=[("pressed", SOFT_PRESSED), ("active", HOVER)],
              lightcolor=[("active", HOVER)], darkcolor=[("active", HOVER)],
              bordercolor=[("active", HOVER)], focuscolor=[("active", HOVER)])

    # Галочки «Срочно» / «Важно»
    style.configure("TCheckbutton", background=BG, foreground=TEXT, font=FONT,
                    indicatorbackground=SURFACE, indicatorforeground="white",
                    upperbordercolor=CHECK_BORDER, lowerbordercolor=CHECK_BORDER,
                    focuscolor=BG, indicatormargin=(0, 0, 8, 0), padding=(0, 2))
    style.map("TCheckbutton",
              indicatorbackground=[("selected", ACCENT), ("active", ACCENT_SOFT)],
              upperbordercolor=[("selected", ACCENT)], lowerbordercolor=[("selected", ACCENT)],
              background=[("active", BG)])
    style.configure("Card.TCheckbutton", background=SURFACE)
    style.map("Card.TCheckbutton", background=[("active", SURFACE)])
    style.configure("Tour.TCheckbutton", background=SURFACE, foreground=MUTED, font=FONT_SMALL)
    style.map("Tour.TCheckbutton", background=[("active", SURFACE)])
    style.configure("Card.TRadiobutton", background=SURFACE)
    style.map("Card.TRadiobutton", background=[("active", SURFACE)])
    style.configure("Icon.TButton", padding=(6, 3), font=FONT)

    # Поля ввода и выпадающие списки
    style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT, lightcolor=SURFACE,
                    darkcolor=SURFACE, padding=(8, 6), insertcolor=TEXT)
    style.map("TEntry",
              bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", SURFACE)])
    style.configure("Date.TEntry", padding=(6, 6, 22, 6))  # справа — место под значок 📅 (DatePicker)
    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE, foreground=TEXT,
                    lightcolor=SURFACE, darkcolor=SURFACE, arrowcolor=MUTED, padding=(6, 4),
                    insertcolor=TEXT)  # курсор в списке, куда можно вписать своё (инициатор)
    style.map("TCombobox",
              fieldbackground=[("disabled", BG), ("readonly", SURFACE)],
              foreground=[("disabled", DONE)],
              background=[("disabled", BG), ("active", BUTTON_HOVER)],
              bordercolor=[("focus", ACCENT)],
              selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", TEXT)])

    # Переключатель фильтра в виде сегментов
    style.layout("Segment.TRadiobutton", [
        ("Radiobutton.padding", {"sticky": "nswe", "children": [
            ("Radiobutton.label", {"sticky": "nswe"})]})])
    style.configure("Segment.TRadiobutton", background=SEGMENT_BG, foreground=MUTED,
                    padding=(14, 5), font=FONT_SMALL, anchor="center")
    style.map("Segment.TRadiobutton",
              background=[("selected", SURFACE), ("active", SEGMENT_HOVER)],
              foreground=[("selected", ACCENT), ("active", TEXT)])
    style.configure("Segments.TFrame", background=SEGMENT_BG)
    # Вкладки карточки задачи — те же сегменты, только поуже
    style.layout("Tab.TRadiobutton", style.layout("Segment.TRadiobutton"))
    style.configure("Tab.TRadiobutton", background=SEGMENT_BG, foreground=MUTED,
                    padding=(4, 3), font=FONT_SMALL, anchor="center")
    style.map("Tab.TRadiobutton",
              background=[("selected", SURFACE), ("active", SEGMENT_HOVER)],
              foreground=[("selected", ACCENT), ("active", TEXT)])
    style.layout("Segment.TCheckbutton", [
        ("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})])
    style.configure("Segment.TCheckbutton", background=SEGMENT_BG, foreground=MUTED,
                    padding=(14, 5), font=FONT_SMALL, anchor="center")
    style.map("Segment.TCheckbutton",
              background=[("selected", SURFACE), ("active", SEGMENT_HOVER)],
              foreground=[("selected", ACCENT), ("active", TEXT)])

    # Таблица задач
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, rowheight=36, borderwidth=0, font=FONT)
    style.map("Treeview",
              background=[("selected", ACCENT_SOFT)], foreground=[("selected", TEXT)])
    # Тонкие линии между заголовками столбцов — видно, где тянуть, чтобы изменить ширину
    style.configure("Treeview.Heading", background=SURFACE, foreground=MUTED,
                    font=("Segoe UI Semibold", 9), relief="raised", borderwidth=1,
                    padding=(10, 8), bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=HEADING_LINE)
    style.map("Treeview.Heading", background=[("active", ROW_HOVER)])

    # Тонкая полоса прокрутки без стрелок
    style.layout("Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Vertical.TScrollbar", troughcolor=SURFACE, background=SCROLL,
                    bordercolor=SURFACE, lightcolor=SCROLL, darkcolor=SCROLL,
                    gripcount=0, width=8)
    style.map("Vertical.TScrollbar", background=[("active", SCROLL_ACTIVE)])
    style.layout("Horizontal.TScrollbar", [
        ("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
            ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Horizontal.TScrollbar", troughcolor=BG, background=SCROLL,
                    bordercolor=BG, lightcolor=SCROLL, darkcolor=SCROLL,
                    gripcount=0, width=8)
    style.map("Horizontal.TScrollbar", background=[("active", SCROLL_ACTIVE)])


def tint(color, amount, base=None):
    """Смесь цвета с base (по умолчанию — цвет-основа темы: белый в светлой, тёмный в тёмной):
    amount=0 — сам цвет, 1 — base. В тёмной теме колонки доски получаются тёмными с оттенком."""
    base = base or TINT_BASE
    if THEME == "dark" and base == TINT_BASE:
        amount = min(amount, 0.86)  # на тёмном фоне оттенок должен оставаться заметным, но не ярким
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    br, bgc, bb = (int(base[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(c + (t - c) * amount) for c, t in ((r, br), (g, bgc), (b, bb)))


def dark_titlebar(window):
    """В тёмной теме — тёмная полоса заголовка окна (Windows 10 2004+ и Windows 11)."""
    if THEME != "dark":
        return
    try:
        hwnd = int(window.wm_frame(), 16)  # рамка окна (создаётся, даже если окно ещё не показано)
        on = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (новые и старые сборки)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(on),
                                                          ctypes.sizeof(on)) == 0:
                break
        # перерисовать рамку окна, иначе цвет заголовка сменится только после переключения окон
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
    except (AttributeError, OSError, tk.TclError):
        pass


def hide_new_window(window):
    """Прячет только что созданное окно, пока его не поставили на место (см. place_window).
    Возвращает True, если спрятали."""
    if (isinstance(window, tk.Toplevel) and not window.winfo_ismapped()
            and window.state() == "normal"):
        window.withdraw()
        return True
    return False


def place_window(window, x, y, width=None, height=None, show=False):
    """Ставит окно на место (x, y). show=True — окно было спрятано hide_new_window: показываем
    его уже на месте и с тёмным заголовком, иначе оно мелькает в углу, а в тёмной теме
    заголовок остаётся белым."""
    size = f"{width}x{height}" if width and height else ""
    window.geometry(f"{size}+{max(x, 0)}+{max(y, 0)}")
    if show:
        dark_titlebar(window)  # тёмный заголовок — ещё до показа окна
        window.deiconify()


def bring_to_front(window):
    window.lift()
    window.attributes("-topmost", True)  # иначе Windows может только мигнуть кнопкой на панели задач
    window.after(200, lambda: window.winfo_exists() and window.attributes("-topmost", False))
    window.focus_force()


def center_on_screen(window, width=None, height=None):
    """Ставит окно по центру экрана."""
    hidden = hide_new_window(window)
    window.update_idletasks()
    width = width or window.winfo_reqwidth()
    height = height or window.winfo_reqheight()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    place_window(window, x, y, width, height, show=hidden)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def work_area(window):
    """Часть экрана без панели задач Windows: (x, y, ширина, высота) — того монитора, где стоит
    окно (ещё не показанное окно — основного)."""
    try:
        user32 = ctypes.windll.user32
        rect = None
        if window.winfo_ismapped():
            user32.MonitorFromWindow.restype = wintypes.HMONITOR
            hwnd = wintypes.HWND(user32.GetParent(window.winfo_id()))
            monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                rect = info.rcWork
        if rect is None:
            rect = wintypes.RECT()
            if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                rect = None
        if rect is not None and rect.right > rect.left and rect.bottom > rect.top:
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except (AttributeError, OSError, ctypes.ArgumentError):
        pass
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight()


def format_due(due_at):
    """'2026-10-16 09:00' -> '16.10.2026 09:00'."""
    return datetime.fromisoformat(due_at).strftime("%d.%m.%Y %H:%M") if due_at else ""


IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
# Вложения, которые при открытии запускаются как программа, — перед открытием спрашиваем
RISKY_TYPES = {".exe", ".com", ".bat", ".cmd", ".msi", ".msp", ".scr", ".pif", ".cpl", ".js", ".jse",
               ".vbs", ".vbe", ".wsf", ".wsh", ".ps1", ".psm1", ".hta", ".lnk", ".reg", ".jar", ".appref-ms",
               ".ws", ".wsc", ".sct", ".vb", ".url", ".scf", ".inf", ".msc", ".chm", ".gadget",
               ".application", ".appinstaller", ".msix", ".appx", ".diagcab", ".xll",
               ".settingcontent-ms", ".library-ms", ".search-ms", ".py", ".pyw", ".pyz",
               # образы дисков: Windows подключает их как диск, и программы внутри — без предупреждений
               ".iso", ".img", ".vhd", ".vhdx"}


def file_name_for_disk(name):
    """Имя для временной копии вложения — такое, каким его на самом деле сохранит Windows:
    без запрещённых знаков, без точек и пробелов в конце (Windows их молча убирает, и
    «отчёт.exe.» стал бы «отчёт.exe»)."""
    return re.sub(r'[\\/:*?"<>|]', "_", name or "").strip().rstrip(". ") or "файл"


def temp_copy(folder, name, data, tries=10):
    """Кладёт копию вложения во временную папку и возвращает путь к ней. Копия того же файла
    уже есть — её и отдаём, не перезаписывая: Outlook держит открытое письмо .msg занятым,
    и запись поверх давала «Permission denied». Занятую копию с другим содержимым не трогаем —
    новая ляжет рядом, в подпапку «2», «3»… (имя файла остаётся прежним)."""
    safe = file_name_for_disk(name)
    folder = Path(folder)
    for attempt in range(1, tries + 1):
        place = folder if attempt == 1 else folder / str(attempt)
        path = place / safe
        try:
            if path.read_bytes() == data:
                try:  # копию только что открыли — clean_temp_files не должна счесть её старой
                    os.utime(path)
                except OSError:
                    pass
                return path
        except OSError:
            pass  # копии нет или её не прочитать — пишем заново
        try:
            place.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path
        except PermissionError:
            if attempt == tries:
                raise


ERROR_REASONS = {  # errno -> понятная причина (Python пишет их по-английски)
    errno.EACCES: "нет доступа — файл занят другой программой или защищён от записи",
    errno.EPERM: "нет доступа — файл занят другой программой или защищён от записи",
    errno.ENOENT: "файл или папка не найдены",
    errno.EEXIST: "такой файл уже есть",
    errno.ENOSPC: "на диске закончилось место",
    errno.EROFS: "диск только для чтения",
    errno.EISDIR: "это папка, а не файл",
    errno.EINVAL: "недопустимое имя файла",
}


def error_text(error):
    """Текст ошибки для окна сообщения. str(OSError) показывает путь с удвоенными «\\\\»
    и причину по-английски — здесь причина по-русски, а путь — как в Проводнике."""
    if not isinstance(error, OSError) or not error.errno and not error.strerror:
        return str(error)
    # У ошибок Windows (winerror) свой точный текст на языке Windows, а errno у многих из них —
    # «на всякий случай» EINVAL (сеть пропала, нет программы для файла…): берём текст Windows
    if getattr(error, "winerror", None) and error.strerror:
        reason = error.strerror
    else:
        reason = ERROR_REASONS.get(error.errno) or error.strerror or str(error)
    paths = [str(p) for p in (error.filename, error.filename2) if p not in (None, "")]
    return "\n".join([reason[:1].upper() + reason[1:]] + paths)


def is_risky_file(name):
    """Вложение запустится как программа, если его открыть, — перед открытием спрашиваем."""
    return Path(file_name_for_disk(name)).suffix.lower() in RISKY_TYPES


def small_picture(data, size=56):
    """Уменьшенная копия картинки (PIL) для превью или None — нет данных, нет Pillow, не картинка.
    Можно звать из фонового потока (Tk здесь не трогается)."""
    if not data:
        return None
    try:
        from io import BytesIO
        from PIL import Image
        image = Image.open(BytesIO(data))
        image.thumbnail((size, size))
        return image
    except Exception:  # noqa: BLE001 — испорченный файл, слишком большая картинка или нет Pillow
        return None


def format_size(size):
    for unit in ("байт", "КБ", "МБ"):
        if size < 1024 or unit == "МБ":
            return f"{size} {unit}" if unit == "байт" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024


class _SHFileInfo(ctypes.Structure):
    _fields_ = [("hIcon", ctypes.c_void_p), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80)]


class _BitmapHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class _Guid(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _shell_icon_handle(ext):
    """Значок типа файла из Проводника: (HICON, размер) или (None, 0). Сам файл не нужен —
    Windows смотрит только на расширение."""
    shell32 = ctypes.WinDLL("shell32")
    shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(_SHFileInfo),
                                       wintypes.UINT, wintypes.UINT]
    shell32.SHGetFileInfoW.restype = ctypes.c_size_t
    shell32.SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHGetImageList.restype = ctypes.c_long
    ctypes.WinDLL("ole32").CoInitialize(None)
    use_attributes, sys_index, icon_flag = 0x10, 0x4000, 0x100
    info = _SHFileInfo()
    if shell32.SHGetFileInfoW("file" + ext, 0x80, ctypes.byref(info), ctypes.sizeof(info),
                              use_attributes | sys_index):
        # большой значок 48×48 (как «Крупные значки» в Проводнике) — через IImageList::GetIcon
        iid = _Guid(0x46EB5926, 0x582E, 0x4017, (ctypes.c_ubyte * 8)(0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))
        images = ctypes.c_void_p()
        if shell32.SHGetImageList(2, ctypes.byref(iid), ctypes.byref(images)) == 0 and images:
            table = ctypes.cast(images, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            get_icon = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, wintypes.UINT,
                                          ctypes.POINTER(ctypes.c_void_p))(table[10])
            release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(table[2])
            icon = ctypes.c_void_p()
            ok = get_icon(images, info.iIcon, 1, ctypes.byref(icon)) == 0 and icon.value
            release(images)
            if ok:
                return icon.value, 48
    info = _SHFileInfo()
    if shell32.SHGetFileInfoW("file" + ext, 0x80, ctypes.byref(info), ctypes.sizeof(info),
                              use_attributes | icon_flag) and info.hIcon:
        return info.hIcon, 32
    return None, 0


def _draw_icon(icon, size, fill):
    """Рисует значок на квадрате цвета fill (0 — чёрный, 255 — белый); байты BGRA."""
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    user32.DrawIconEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    header = _BitmapHeader(ctypes.sizeof(_BitmapHeader), size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
    dc = gdi32.CreateCompatibleDC(None)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    try:
        if not bitmap or not bits.value:
            return None
        old = gdi32.SelectObject(dc, bitmap)
        ctypes.memset(bits, fill, size * size * 4)
        user32.DrawIconEx(dc, 0, 0, icon, size, size, 0, None, 3)
        gdi32.GdiFlush()
        data = ctypes.string_at(bits, size * size * 4)
        gdi32.SelectObject(dc, old)
        return data
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)


def file_type_icon(name):
    """Значок типа файла таким, как его показывает Проводник Windows (картинка PIL RGBA),
    или None — не Windows, нет Pillow или Windows не дала значок."""
    if sys.platform != "win32":
        return None
    ext = Path(file_name_for_disk(name)).suffix.lower()
    if not re.fullmatch(r"\.[\w\-]{1,15}", ext):
        ext = ".file"
    try:
        from PIL import Image
        icon, size = _shell_icon_handle(ext)
        if not icon:
            return None
        try:
            black, white = _draw_icon(icon, size, 0), _draw_icon(icon, size, 255)
        finally:
            ctypes.WinDLL("user32").DestroyIcon(ctypes.c_void_p(icon))
        if not black or not white:
            return None
        # прозрачность узнаём по разнице рисунка на чёрном и на белом — так верно и для
        # новых значков с полупрозрачными краями, и для старых с маской
        pixels = bytearray(size * size * 4)
        for i in range(0, len(black), 4):
            alpha = 255 - max(0, min(255, white[i + 1] - black[i + 1]))
            if alpha:
                pixels[i] = min(255, black[i + 2] * 255 // alpha)
                pixels[i + 1] = min(255, black[i + 1] * 255 // alpha)
                pixels[i + 2] = min(255, black[i] * 255 // alpha)
                pixels[i + 3] = alpha
        return Image.frombytes("RGBA", (size, size), bytes(pixels))
    except Exception:  # noqa: BLE001 — значок лишь украшение: без него покажем плашку с расширением
        return None


def short_time(stamp):
    """'2026-10-17 14:05:33' -> '17.10 14:05' (год — только если не нынешний)."""
    when = datetime.fromisoformat(stamp)
    return when.strftime("%d.%m %H:%M" if when.year == datetime.now().year else "%d.%m.%Y %H:%M")


MAIL_MARK = "📧"  # значок задачи, созданной из письма Outlook
REPEAT_MARK = "🔁"  # значок повторяющейся задачи


def extras_mark(counts, from_mail=False, repeat=False):
    """'   🔁  📧  📎 2  💬 3' — задача повторяется, создана из письма Outlook, сколько у неё файлов
    и комментариев (или '', если ничего нет)."""
    files, comments = counts or (0, 0)
    parts = ([REPEAT_MARK] if repeat else []) + ([MAIL_MARK] if from_mail else []) + (
        [f"📎 {files}"] if files else []) + (
        [f"💬 {comments}"] if comments else [])
    return "   " + "  ".join(parts) if parts else ""


def merge_column_order(saved, default):
    """Порядок столбцов списка из настройки: известные столбцы — в сохранённом порядке,
    неизвестные и повторы выбрасываем, а новые (появились в новой версии) ставим на их
    обычное место — сразу после того столбца, за которым они стоят по умолчанию."""
    order = []
    for key in saved if isinstance(saved, list) else []:
        if key in default and key not in order:
            order.append(key)
    for i, key in enumerate(default):
        if key not in order:
            before = default[i - 1] if i else None
            order.insert(order.index(before) + 1 if before in order else 0, key)
    return order


def drop_index(lefts, widths, x):
    """Куда встанет перетаскиваемый столбец: номер места (0…len) по координате мыши x.
    lefts/widths — левые края и ширины видимых столбцов."""
    for i, (left, width) in enumerate(zip(lefts, widths)):
        if x < left + width / 2:
            return i
    return len(lefts)


def move_column(order, column, place, shown):
    """Новый порядок столбцов: column встаёт на место place среди видимых столбцов shown
    (скрытые столбцы — например «Инициатор» в личном списке — остаются рядом с прежними соседями)."""
    shown = [c for c in shown if c != column]
    target = shown[place] if place < len(shown) else None
    order = [c for c in order if c != column]
    if target is None:  # в самый конец — за последним видимым столбцом
        order.insert(order.index(shown[-1]) + 1 if shown else len(order), column)
    else:
        order.insert(order.index(target), column)
    return order


def paint_tree(widget, bg):
    """Меняет фон у виджета и всех вложенных (кроме превью-картинок и значков)."""
    if not (isinstance(widget, tk.Label) and widget.cget("bg") == BG):
        widget.configure(bg=bg)
    for child in widget.winfo_children():
        paint_tree(child, bg)


def short_text(text, limit=60):
    """Обрезает длинный текст по границе слова: «Очень длинная задача…»."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"


def build_email(number, title, status, priority, due, remind, created, urgent, body="", author="",
                assignee="", unit="", repeat=""):
    """Тема и текст письма по задаче: в теме — заголовок, в тексте — описание и все поля."""
    subject = f"Задача из {APP_NAME}: {short_text(title)}"
    if urgent:
        subject = "СРОЧНО! " + subject
    level_hint = next((PRIORITY_HINTS[k] for k, v in PRIORITY_NAMES.items() if v and v == priority), "")
    lines = [f"Задача #{number}: {title}", ""]
    if body.strip():
        lines += ["Описание:", *richtext.plain(body).strip().splitlines(), ""]
    lines += [
        f"Статус: {status}",
        f"Приоритет: {priority} — {level_hint}" if priority else "Приоритет: обычный",
        f"Срок: {due or 'не задан'}",
        f"Напоминание: {remind or 'нет'}",
        *([f"Повтор: {repeat}"] if repeat else []),
        f"Создана: {created}",
        *([f"Инициатор: {author}"] if author else []),
        *([f"Исполнитель: {assignee}"] if assignee else []),
        *([f"Бизнес-единица: {unit}"] if unit else []),
        "",
        "—",
        f"Отправлено из {APP_NAME}",
    ]
    return subject, "\r\n".join(lines)


def write_draft(number, subject, body, to=""):
    """Сохраняет черновик письма в файл .eml и возвращает путь к нему.
    Заголовок X-Unsent: 1 говорит почтовой программе открыть его как новое письмо.
    to — адресат (у задачи из письма Outlook — отправитель того письма)."""
    message = EmailMessage(policy=email_policy.SMTP)
    if to:
        message["To"] = to
    message["Subject"] = subject
    message["X-Unsent"] = "1"
    message.set_content(body.replace("\r\n", "\n"))
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFTS_DIR / f"Задача {number}.eml"
    path.write_bytes(message.as_bytes())
    return str(path)


def clean_temp_files(folder=None, max_age=TEMP_MAX_AGE):
    """Удаляет из временной папки ToDoro черновики писем и копии открытых файлов задач,
    которых не трогали дольше max_age секунд. Свежие не трогаем: файл может быть ещё открыт
    в почте или в Word. Файл, занятый другой программой, просто пропускаем."""
    folder = Path(folder or DRAFTS_DIR)
    limit = time_module.time() - max_age
    try:
        items = list(folder.iterdir())
    except OSError:
        return
    for item in items:
        try:
            if item.is_dir():
                times = [f.stat().st_mtime for f in item.rglob("*")] + [item.stat().st_mtime]
                if max(times) < limit:
                    shutil.rmtree(item, ignore_errors=True)
            elif item.stat().st_mtime < limit:
                item.unlink()
        except OSError:
            pass


# ---------- экспорт и импорт задач в CSV (таблица для Excel) ----------
# Разделитель — «;», кодировка — UTF-8 с меткой BOM: так русский Excel открывает файл
# двойным щелчком без «кракозябр». При импорте понимаем и «,», и кодировку Windows-1251
# (в ней сохраняет CSV русский Excel).

CSV_COLUMNS = ["№", "Заголовок", "Описание", "Статус", "Приоритет", "Срок", "Напомнить", "Создана",
               "Автор", "Инициатор", "Исполнитель", "Бизнес-единица"]
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
    "инициатор": "initiator", "автор": "author",
    "исполнитель": "assignee",
    "бизнес-единица": "unit", "бизнес единица": "unit",
}
NO_UNIT = "— не указана —"  # бизнес-единица задачи не выбрана
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
    """«За 1 час» или число минут -> минуты; пусто или «Не напоминать» -> None."""
    text = text.strip()
    for label, minutes in REMIND_OPTIONS.items():
        if text.lower() == label.lower():
            return minutes
    if not text:
        return None
    if text.isdigit() and int(text) <= db.MAX_REMIND_MINUTES:
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
    initiators, assignees = db.task_people(conn)
    # и автор (кто создал), и инициатор: при загрузке файла обратно автор сохранится, и
    # напоминания по задачам без исполнителя не уйдут другому человеку
    authors = dict(conn.execute("SELECT id, created_by FROM tasks WHERE created_by IS NOT NULL"))
    units = dict(db.list_units(conn))
    task_unit = db.task_units(conn)
    rows = []
    for task_id, title, _done, created, due_at, remind_before, urgent, important, body, status_id \
            in db.list_tasks(conn):
        remind = REMIND_LABELS.get(remind_before, remind_before or "") if due_at else ""
        if remind == "Не напоминать":
            remind = ""
        rows.append([task_id, title, body, statuses.get(status_id, ""),
                     PRIORITY_NAMES[priority_level(urgent, important)] or "Обычный",
                     format_due(due_at), remind, created, authors.get(task_id, ""),
                     initiators.get(task_id, ""), assignees.get(task_id, ""),
                     units.get(task_unit.get(task_id), "")])
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
    new_units = set()  # единицы, которых нет в справочнике (замечание — один раз на единицу)
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
        unit = " ".join(v.get("unit", "").split())
        if unit and db.unit_by_name(conn, unit) is None and unit.casefold() not in new_units:
            new_units.add(unit.casefold())
            notes.append(f"строка {line_no}: бизнес-единицы «{unit}» нет в справочнике — она будет добавлена")
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
            created_by=v.get("author") or None,
            initiator=v.get("initiator") or None,
            unit=unit or None,
            assignee=v.get("assignee") or None,
        ))
    return tasks, notes


def search_stems(query):
    """Слова поиска без окончаний: «исполнитель» найдёт и «исполнителя», «исполнителю»."""
    return [w[:max(4, len(w) - 2)] if len(w) >= 5 else w for w in query.lower().split()]


def status_label(name, done, overdue=False):
    """Название статуса (колонки доски) со значком: ✔ выполнено, ⚠ просрочено, ○ остальное."""
    mark = "✔" if done else "⚠" if overdue else "○"
    return f"{mark}  {name}"


class AlertDialog(tk.Toplevel):
    """Сообщение или вопрос в стиле программы (вместо стандартных серых окон Windows)."""

    # значок (шрифт Segoe MDL2 Assets) и его цвет
    KINDS = {"info": ("", ACCENT), "warning": ("", WARN),
             "error": ("", DANGER), "question": ("", ACCENT)}

    def __init__(self, parent, title, message, kind, buttons, default, cancel, links=()):
        """buttons — [(подпись, значение, стиль)], default — значение кнопки для Enter,
        cancel — значение для Esc и закрытия окна, links — [(текст, значение)]: строки-ссылки
        под сообщением, щелчок по строке закрывает окно с этим значением."""
        super().__init__(parent)
        self.result = cancel
        self.title(title)
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.standalone = parent is None  # отдельное окно, а не поверх окна ToDoro
        if parent is not None:
            self.transient(parent)
        body = tk.Frame(self, bg=SURFACE, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        icon, color = self.KINDS[kind]
        tk.Label(body, text=icon, bg=SURFACE, fg=color, font=("Segoe MDL2 Assets", 22)).pack(
            side="left", anchor="n", padx=(0, 16), pady=(2, 0))
        text = tk.Frame(body, bg=SURFACE)
        text.pack(side="left", fill="both", expand=True)
        tk.Label(text, text=title, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 12),
                 justify="left", anchor="w").pack(anchor="w", pady=(0, 6))
        tk.Label(text, text=message, bg=SURFACE, fg=TEXT, font=FONT_SMALL, justify="left",
                 anchor="w", wraplength=420).pack(anchor="w")
        for line, value in links:
            if value is None:  # подзаголовок между ссылками
                tk.Label(text, text=line, bg=SURFACE, fg=TEXT, font=FONT_SMALL, justify="left",
                         anchor="w", wraplength=420).pack(anchor="w", pady=(12, 0))
                continue
            link = tk.Label(text, text=line, bg=SURFACE, fg=ACCENT, font=FONT_SMALL, justify="left",
                            anchor="w", wraplength=420, cursor="hand2")
            link.pack(anchor="w", pady=(4, 0))
            link.bind("<Button-1>", lambda e, v=value: self.finish(v))
            link.bind("<Enter>", lambda e, w=link: w.configure(font=(*FONT_SMALL, "underline")))
            link.bind("<Leave>", lambda e, w=link: w.configure(font=FONT_SMALL))

        bar =tk.Frame(self, bg=BG, highlightthickness=1, highlightbackground=BORDER)
        bar.pack(fill="x", side="bottom")
        focus, made = None, []
        for label, value, style in reversed(buttons):  # pack справа налево — сначала крайняя
            button = ttk.Button(bar, text=label, style=style, cursor="hand2",
                                command=lambda v=value: self.finish(v))
            button.pack(side="right", padx=(0, 8 if made else 10), pady=12)
            made.append(button)
            if value == default:
                focus = button
        for button in reversed(made):  # Tab — слева направо
            button.lift()
        self.bind("<Escape>", lambda e: self.finish(cancel))
        self.bind("<Return>", lambda e: self.finish(default))
        self.protocol("WM_DELETE_WINDOW", lambda: self.finish(cancel))
        self.focus_button = focus

    def finish(self, value):
        self.result = value
        self.destroy()

    def show(self):
        parent = None if self.standalone else self.master
        hidden = hide_new_window(self)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if parent is not None and parent.winfo_viewable():  # по центру окна, из которого спросили
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
        else:
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 2
        place_window(self, x, y, show=hidden)
        if self.standalone:  # отдельное сообщение (например, из значка в трее) — поверх других программ
            bring_to_front(self)
        previous = self.grab_current()  # окно-диалог, из которого спросили, снова станет модальным
        self.grab_set()
        self.lift()
        self.focus_force()
        if self.focus_button is not None:
            self.focus_button.focus_set()
        self.wait_window()
        if previous is not None:
            try:
                if previous.winfo_exists():
                    previous.grab_set()
            except tk.TclError:
                pass
        return self.result


class ui:
    """Сообщения и вопросы в стиле программы. Те же вызовы, что у tkinter.messagebox:
    ui.showinfo(заголовок, текст, parent=…), ui.askyesno(…, icon="warning", default="no") и т. д."""

    YES, NO = ("Да", True, "Accent.TButton"), ("Нет", False, "TButton")

    @staticmethod
    def _show(title, message, kind, buttons, default, cancel, parent=None):
        return AlertDialog(parent, title, message, kind, buttons, default, cancel).show()

    @staticmethod
    def showinfo(title, message, parent=None, **_):
        ui._show(title, message, "info", [("OK", True, "Accent.TButton")], True, True, parent)

    @staticmethod
    def showwarning(title, message, parent=None, **_):
        ui._show(title, message, "warning", [("OK", True, "Accent.TButton")], True, True, parent)

    @staticmethod
    def showerror(title, message, parent=None, **_):
        ui._show(title, message, "error", [("OK", True, "Accent.TButton")], True, True, parent)

    @staticmethod
    def askyesno(title, message, parent=None, icon="question", default="yes", **_):
        danger = icon == "warning"  # опасное действие (удаление) — «Да» красная
        yes = ("Да", True, "DangerSoft.TButton" if danger else "Accent.TButton")
        return ui._show(title, message, "warning" if danger else "question", [yes, ui.NO],
                        default != "no", False, parent)

    @staticmethod
    def askokcancel(title, message, parent=None, **_):
        return ui._show(title, message, "info", [("Продолжить", True, "Accent.TButton"),
                                                 ("Отмена", False, "TButton")],
                        True, False, parent)


class DatePicker(ttk.Frame):
    """Поле даты с выпадающим календарём."""

    def __init__(self, parent, value=None, on_change=None, empty="Не задан", clear="Без срока",
                 button=True, width=11):
        """empty — надпись в поле, пока дата не выбрана; clear — ссылка «убрать дату» в календаре;
        button=False — значок 📅 не отдельной кнопкой, а внутри поля (для тесных мест)."""
        super().__init__(parent)
        self.value = value
        self.on_change = on_change
        self.empty, self.clear = empty, clear
        self.popup = None
        self.text = tk.StringVar()

        self.entry = ttk.Entry(self, textvariable=self.text, font=FONT, width=width,
                               state="readonly", cursor="hand2", style="TEntry" if button else "Date.TEntry")
        self.entry.pack(side="left")
        # "break": иначе поле после щелчка забирает фокус у календаря, и тот сразу закрывается
        self.entry.bind("<Button-1>", lambda e: (self.toggle_popup(), "break")[1])
        if button:
            ttk.Button(self, text="📅", style="Icon.TButton", width=3, cursor="hand2",
                       command=self.toggle_popup).pack(side="left", padx=(4, 0))
        else:  # тесно — значок внутри поля, у правого края
            icon = tk.Label(self.entry, text="📅", bg=SURFACE, fg=MUTED, font=FONT_SMALL, cursor="hand2")
            icon.place(relx=1, rely=0.5, x=-4, anchor="e")
            icon.bind("<Button-1>", lambda e: (self.toggle_popup(), "break")[1])
        self.show()

    def set(self, value):
        self.value = value
        self.show()
        self.close_popup()
        if self.on_change:
            self.on_change()

    def show(self):
        self.text.set(self.value.strftime("%d.%m.%Y") if self.value else self.empty)

    # --- выпадающий календарь ---

    def toggle_popup(self):
        if self.popup:
            self.close_popup()
            return
        self.month = (self.value or date.today()).replace(day=1)
        self.popup = tk.Toplevel(self)
        self.popup.overrideredirect(True)  # окно без рамки и заголовка
        self.popup.configure(bg=SURFACE, highlightthickness=1, highlightbackground=POPUP_BORDER)
        self.popup.bind("<Escape>", lambda e: self.close_popup())
        self.popup.bind("<FocusOut>", lambda e: self.after(150, self.close_if_unfocused))
        self.popup.bind("<MouseWheel>", lambda e: self.shift_month(-1 if e.delta > 0 else 1))
        self.draw_month()
        self.popup.focus_force()
        close_when_inactive(self.popup, self.close_popup)

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
                    style.update(fg=OTHER_MONTH)
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
        self.clickable(footer, self.clear, lambda: self.set(None),
                       fg=MUTED, font=FONT_SMALL).pack(side="right")
        self.place_popup()

    def place_popup(self):
        """Календарь — под полем; если внизу экрана места нет (поле у панели задач Windows) —
        над полем. По ширине не выходит за правый край."""
        self.popup.update_idletasks()
        width, height = self.popup.winfo_reqwidth(), self.popup.winfo_reqheight()
        left, top, area_width, area_height = work_area(self.winfo_toplevel())
        x = min(self.entry.winfo_rootx(), left + area_width - width)
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 4
        if y + height > top + area_height:
            y = max(top, self.entry.winfo_rooty() - height - 4)
        self.popup.geometry(f"+{max(x, left)}+{y}")


class TitleSuggest:
    """Выпадающий список вариантов названия под полем ввода (умные подсказки, smart.py).

    ↓/↑ — выбрать вариант, Enter или Tab — подставить, Esc — закрыть. Enter поля по-прежнему
    обрабатывает его хозяин: сначала спрашивает accept() — если вариант подставлен, дальше
    ничего не делает (задачу не добавляет и форму не сохраняет)."""

    def __init__(self, entry, get_text, rows):
        self.entry, self.get_text, self.rows = entry, get_text, rows  # rows() — прошлые задачи
        self.popup, self.items, self.index, self.job = None, [], -1, None
        self.follow_job, self.spot = None, None  # слежка за положением поля, где оно было
        entry.bind("<KeyRelease>", self.typed, add="+")
        entry.bind("<Down>", lambda e: self.move(1), add="+")
        entry.bind("<Up>", lambda e: self.move(-1), add="+")
        entry.bind("<Tab>", lambda e: "break" if self.accept() else None, add="+")
        entry.bind("<Escape>", lambda e: (self.close(), "break")[1] if self.popup else None, add="+")
        entry.bind("<FocusOut>", lambda e: entry.after(200, self.close_if_unfocused), add="+")
        entry.bind("<Destroy>", lambda e: self.close(), add="+")

    def shown(self):
        return self.popup is not None

    def typed(self, event):
        if event.keysym in ("Up", "Down", "Return", "KP_Enter", "Escape", "Tab"):
            return
        if self.job:  # считаем, когда пальцы остановились: в большом списке это заметные мс
            self.entry.after_cancel(self.job)
        self.job = self.entry.after(120, self.update)

    def update(self):
        self.job = None
        if not self.entry.winfo_exists():
            return
        text = self.get_text()
        found = smart.suggest_titles(text, self.rows()) if text else []
        if found:
            self.show(found)
        else:
            self.close()

    def show(self, items):
        """Список — рамка внутри того же окна (place поверх остального), а не отдельное окно:
        отдельное окно Windows сначала показывало в углу экрана и делало активным — поле ввода
        теряло фокус, и список тут же закрывался."""
        self.items, self.index = items, -1
        top = self.entry.winfo_toplevel()
        if self.popup is None:
            self.popup = tk.Frame(top, bg=BORDER)
        for child in self.popup.winfo_children():
            child.destroy()
        box = tk.Frame(self.popup, bg=SURFACE)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(box, text="Похожие задачи — ↓ выбрать, Enter подставить", bg=SURFACE, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(fill="x", padx=10, pady=(5, 2))
        self.labels = []
        for i, title in enumerate(items):
            label = tk.Label(box, text=short_text(title, 90), bg=SURFACE, fg=TEXT, font=FONT,
                             anchor="w", padx=10, pady=3, cursor="hand2")
            label.pack(fill="x")
            label.bind("<Enter>", lambda e, i=i: self.highlight(i))
            label.bind("<Button-1>", lambda e, i=i: self.pick(i))
            self.labels.append(label)
        tk.Frame(box, bg=SURFACE, height=4).pack()
        self.entry.update_idletasks()
        self.place_popup()
        if self.follow_job is None:
            self.follow_job = self.entry.after(150, self.follow)

    def place_popup(self):
        """Ставит список под полем (не помещается до низа окна — над полем)."""
        top = self.entry.winfo_toplevel()
        x = self.entry.winfo_rootx() - top.winfo_rootx()
        y = self.entry.winfo_rooty() - top.winfo_rooty()
        height = self.popup.winfo_reqheight()
        below = y + self.entry.winfo_height() + 2
        if below + height > top.winfo_height() and y - height - 2 >= 0:
            below = y - height - 2
        width = min(max(self.entry.winfo_width(), 260), max(top.winfo_width() - x - 4, 120))
        self.popup.place(x=x, y=below, width=width)
        self.popup.lift()
        self.spot = (self.entry.winfo_rootx(), self.entry.winfo_rooty(), self.entry.winfo_width(),
                     top.winfo_height())

    def entry_visible(self):
        """Поле на экране: не спрятано и не уехало за край прокручиваемой панели (Canvas)."""
        if not self.entry.winfo_viewable():
            return False
        widget = self.entry.master
        while widget is not None and not isinstance(widget, tk.Canvas):
            widget = widget.master
        if widget is None:
            return True
        y = self.entry.winfo_rooty()
        return widget.winfo_rooty() <= y and y + self.entry.winfo_height() <= (
            widget.winfo_rooty() + widget.winfo_height())

    def follow(self):
        """Поле сдвинулось без изменения размера (спряталась полоса над ним, прокрутили
        панель) — список переезжает за ним."""
        self.follow_job = None
        if self.popup is None:
            return
        try:
            top = self.entry.winfo_toplevel()
            spot = (self.entry.winfo_rootx(), self.entry.winfo_rooty(), self.entry.winfo_width(),
                    top.winfo_height())
            if not self.entry_visible():  # поле спрятали или прокрутили за край панели
                self.close()
                return
            if spot != self.spot:
                self.place_popup()
        except tk.TclError:  # окно закрыли
            return
        self.follow_job = self.entry.after(150, self.follow)

    def highlight(self, index):
        self.index = index
        for i, label in enumerate(self.labels):
            label.configure(bg=HOVER if i == index else SURFACE)

    def move(self, step):
        if self.popup is None:
            return None
        self.highlight((self.index + step) % len(self.items) if self.index >= 0 or step > 0
                       else len(self.items) - 1)
        return "break"

    def pick(self, index):
        self.entry.delete(0, "end")
        self.entry.insert(0, self.items[index])
        self.entry.icursor("end")
        self.entry.focus_set()
        self.close()

    def accept(self):
        """Enter/Tab: подставляет выбранный стрелками вариант. True — подставили."""
        if self.popup is None or self.index < 0:
            self.close()
            return False
        self.pick(self.index)
        return True

    def close_if_unfocused(self):
        try:
            if self.entry.focus_get() is not self.entry:
                self.close()
        except (KeyError, tk.TclError):  # фокус в уже закрытом окне
            self.close()

    def close(self):
        for name in ("job", "follow_job"):
            if getattr(self, name):
                try:
                    self.entry.after_cancel(getattr(self, name))
                except tk.TclError:
                    pass
                setattr(self, name, None)
        if self.popup is not None:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass
        self.popup, self.items, self.index = None, [], -1


RICH_STYLES = ("bold", "italic", "strike")
RICH_TABLE_ROWS, RICH_TABLE_COLUMNS = 60, 10  # таблица больше — в карточке простым текстом


def rich_tags(widget, font=FONT):
    """Теги оформления описания в поле tk.Text: «rich_bold», «rich_bold_italic» и т. д. —
    у Tk шрифты тегов не складываются, поэтому на каждое сочетание свой тег."""
    family, size = font[0], font[1]
    for mask in range(1, 8):
        styles = [s for i, s in enumerate(RICH_STYLES) if mask & (1 << i)]
        extra = [{"bold": "bold", "italic": "italic", "strike": "overstrike"}[s] for s in styles]
        widget.tag_configure("rich_" + "_".join(styles), font=(family, size, *extra))


def rich_tag(styles):
    return "rich_" + "_".join(s for s in RICH_STYLES if s in styles) if styles else ()


def render_rich(widget, text, wheel=None):
    """Показывает описание оформленным (без значков): жирный, курсив, зачёркнутый, списки
    с отступом, таблицы — сеткой с линиями. Поле должно быть в состоянии «normal».
    wheel — что делать с колёсиком над таблицей (сама сетка его не прокручивает)."""
    if "rich_bold" not in widget.tag_names():  # теги оформления — при первом показе
        rich_tags(widget)
        for level in range(4):
            indent = 6 + level * 18
            widget.tag_configure(f"rich_list{level}", lmargin1=indent, lmargin2=indent + 18,
                                 tabs=(indent + 18,))
    for index, block in enumerate(richtext.blocks(text)):
        if index:
            widget.insert("end", "\n")
        kind = block[0]
        if kind == "table":
            widget.window_create("end", window=rich_table(widget, block[1], block[2], wheel), pady=4)
            continue
        if kind == "text":
            line, prefix, level = block[1], "", None
        elif kind == "bullet":
            line, prefix, level = block[1], "•\t", min(block[2], 3)
        else:
            line, prefix, level = block[2], f"{block[1]}.\t", min(block[3], 3)
        start = widget.index("end-1c")
        widget.insert("end", prefix)
        for part, styles in richtext.inline(line):
            widget.insert("end", part, rich_tag(styles))
        if level is not None:
            widget.tag_add(f"rich_list{level}", start, "end-1c")


def rich_table(widget, rows, header, wheel=None):
    """Таблица описания — сетка подписей с тонкими линиями между ячейками. Ширина ячеек — по
    ширине поля; очень большая таблица (много строк или столбцов) — строками текста."""
    columns = max(len(row) for row in rows)
    if len(rows) > RICH_TABLE_ROWS or columns > RICH_TABLE_COLUMNS:
        text = "\n".join("   ".join("".join(t for t, _ in richtext.inline(c)) for c in row) for row in rows)
        label = tk.Label(widget, text=text, bg=SURFACE, fg=TEXT, font=FONT_SMALL, justify="left",
                         anchor="nw")
        if wheel:
            label.bind("<MouseWheel>", wheel)
        return label
    room = widget.winfo_width() - 2 * int(widget.cget("padx")) - 8
    wrap = max(60, min(220, room // columns - 14)) if room > 100 else 220
    grid = tk.Frame(widget, bg=BORDER, padx=1, pady=1)
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            head = header and r == 0
            text = "".join(t for t, _ in richtext.inline(cell))
            bold = head or any("bold" in s for _, s in richtext.inline(cell))
            tk.Label(grid, text=text, bg=ACCENT_SOFT if head else SURFACE, fg=TEXT, anchor="nw",
                     justify="left", wraplength=wrap, padx=6, pady=2,
                     font=FONT_SMALL_BOLD if bold else FONT_SMALL).grid(
                row=r, column=c, sticky="nsew", padx=(0, 1 if c < len(row) - 1 else 0),
                pady=(0, 1 if r < len(rows) - 1 else 0))
    if wheel:
        bind_tree(grid, "<MouseWheel>", wheel)
    return grid


class RichEditor:
    """Оформление в поле описания (tk.Text): кнопки и Ctrl+B / Ctrl+I ставят и снимают
    значки **жирный**, *курсив*, ~~зачёркнутый~~, «- » и «1. » у строк; значки видны бледно,
    а текст между ними — уже оформленным. Вставка ячеек из Excel — таблицей (richtext)."""

    MARKERS = {"bold": "**", "italic": "*", "strike": "~~"}

    def __init__(self, text):
        self.text, self.job = text, None
        rich_tags(text)
        text.tag_configure("rich_mark", foreground=DONE)
        text.tag_configure("rich_table", font=("Consolas", 10))
        text.bind("<KeyRelease>", lambda e: self.later(), add="+")
        text.bind("<<Paste>>", self.paste)
        # Ctrl+B / Ctrl+I — по физической клавише, при любой раскладке; «break» — чтобы Ctrl+B
        # не свернул правую панель
        text.bind("<Control-KeyPress>", self.key)

    def key(self, event):
        style = {66: "bold", 73: "italic"}.get(event.keycode)
        if style is None or event.state & 0x1:  # с Shift — не наше
            return None
        self.toggle(style)
        return "break"

    def later(self):
        if self.job is None:
            self.job = self.text.after_idle(self.highlight)

    def highlight(self):
        """Подсветка: значки — бледно, текст между ними — жирным/курсивом/зачёркнутым,
        строки таблицы — моноширинным шрифтом (столбцы ровнее)."""
        self.job = None
        text = self.text
        if not text.winfo_exists():
            return
        for tag in text.tag_names():
            if tag.startswith("rich_"):
                text.tag_remove(tag, "1.0", "end")
        for number, line in enumerate(text.get("1.0", "end-1c").split("\n"), start=1):
            if richtext.TABLE_LINE.match(line):
                text.tag_add("rich_table", f"{number}.0", f"{number}.end")
                continue
            styles = [set() for _ in line]
            for start, end, kind in richtext.marks(line):
                for i in range(start, end):
                    styles[i].add("mark" if kind == "mark" else kind)
            i = 0
            while i < len(line):
                j = i
                while j < len(line) and styles[j] == styles[i]:
                    j += 1
                if "mark" in styles[i]:
                    text.tag_add("rich_mark", f"{number}.{i}", f"{number}.{j}")
                elif styles[i]:
                    text.tag_add(rich_tag(styles[i]), f"{number}.{i}", f"{number}.{j}")
                i = j

    def toggle(self, style):
        """Кнопка «Ж»/«К»/«З»: выделенный текст — в значки (или из значков, если уже в них);
        без выделения — пара значков, курсор между ними."""
        text, marker = self.text, self.MARKERS[style]
        size = len(marker)
        text.edit_separator()
        try:
            start, end = text.index("sel.first"), text.index("sel.last")
        except tk.TclError:
            text.insert("insert", marker * 2)
            text.mark_set("insert", f"insert-{size}c")
        else:
            chosen = text.get(start, end)
            if len(chosen) > 2 * size and chosen.startswith(marker) and chosen.endswith(marker):
                text.delete(f"{end}-{size}c", end)
                text.delete(start, f"{start}+{size}c")
                end = f"{end}-{2 * size}c"
            elif (text.get(f"{start}-{size}c", start) == marker
                  and text.get(end, f"{end}+{size}c") == marker):
                text.delete(end, f"{end}+{size}c")
                text.delete(f"{start}-{size}c", start)
                start, end = f"{start}-{size}c", f"{end}-{size}c"
            else:
                text.insert(end, marker)
                text.insert(start, marker)
                start, end = f"{start}+{size}c", f"{end}+{size}c"
            text.tag_remove("sel", "1.0", "end")
            text.tag_add("sel", start, end)
            text.mark_set("insert", end)
        text.edit_separator()
        text.focus_set()
        self.highlight()

    def toggle_list(self, numbered):
        """Кнопки «•» и «1.»: строки с выделением (или строка с курсором) — пунктами списка;
        если они уже такие — снова обычными строками."""
        text = self.text
        try:
            first, last = text.index("sel.first"), text.index("sel.last")
        except tk.TclError:
            first = last = text.index("insert")
        top, bottom = int(first.split(".")[0]), int(last.split(".")[0])
        if bottom > top and last.endswith(".0"):
            bottom -= 1  # выделение до начала следующей строки — её не трогаем
        lines = [text.get(f"{n}.0", f"{n}.end") for n in range(top, bottom + 1)]
        mine = richtext.NUMBER if numbered else richtext.BULLET
        remove = all(mine.match(line) for line in lines if line.strip())
        text.edit_separator()
        number = 0  # номер пункта — только по непустым строкам
        for i, n in enumerate(range(top, bottom + 1)):
            line = lines[i]
            m = richtext.BULLET.match(line) or richtext.NUMBER.match(line)
            body = line[m.end():] if m else line.lstrip()
            indent = m.group(1) if m else line[:len(line) - len(line.lstrip())]
            if remove:
                new = indent + body
            elif not line.strip():
                continue
            else:
                number += 1
                new = indent + (f"{number}. " if numbered else "- ") + body
            text.delete(f"{n}.0", f"{n}.end")
            text.insert(f"{n}.0", new)
        text.edit_separator()
        text.focus_set()
        self.highlight()

    def enter(self):
        """Enter в пункте списка начинает следующий пункт («- » или номер +1); Enter в пустом
        пункте убирает значок списка — список закончен."""
        text = self.text
        try:
            text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        line = text.get("insert linestart", "insert lineend")
        m = richtext.BULLET.match(line) or richtext.NUMBER.match(line)
        empty = re.match(r"(\s*)([-•–*]|\d{1,3}[.)])\s+$", line)  # пункт без текста: «- », «2. »
        if empty:
            text.delete("insert linestart", "insert lineend")
            text.insert("insert", empty.group(1))
        elif m and text.compare("insert", ">=", f"insert linestart+{m.end()}c"):
            prefix = (f"{m.group(1)}{int(m.group(2)) + 1}. " if m.re is richtext.NUMBER
                      else line[:m.end()])
            text.insert("insert", "\n" + prefix)
        else:
            text.insert("insert", "\n")
        text.see("insert")
        self.later()

    def paste(self, event=None):
        """Ячейки из Excel (столбцы через табуляцию) вставляются таблицей на отдельных строках."""
        try:
            table = richtext.tsv_to_table(self.text.clipboard_get())
        except tk.TclError:
            table = None
        if table is None:
            self.later()
            return None  # обычная вставка
        text = self.text
        text.edit_separator()
        try:
            text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        before = "" if text.compare("insert", "==", "insert linestart") else "\n"
        after = "" if text.compare("insert", "==", "insert lineend") and text.compare(
            "insert", "==", "end-1c") else "\n"
        text.insert("insert", before + table + after)
        text.edit_separator()
        self.highlight()
        return "break"

    def toolbar(self, parent, bg):
        """Кнопки оформления: Ж, К, З, • список, 1. список. Это надписи, а не кнопки Tk —
        щелчок по ним не забирает фокус и выделение у поля."""
        bar = tk.Frame(parent, bg=bg)
        items = (("Ж", (FONT[0], 10, "bold"), lambda: self.toggle("bold")),        # Ctrl+B
                 ("К", (FONT[0], 10, "italic"), lambda: self.toggle("italic")),    # Ctrl+I
                 ("З", (FONT[0], 10, "overstrike"), lambda: self.toggle("strike")),
                 ("•", FONT_SMALL_BOLD, lambda: self.toggle_list(False)),
                 ("1.", FONT_SMALL, lambda: self.toggle_list(True)))
        for text, font, command in items:
            button = tk.Label(bar, text=text, bg=bg, fg=MUTED, font=font, width=2, cursor="hand2",
                              padx=2)
            button.pack(side="left", padx=(0, 2))
            button.bind("<Button-1>", lambda e, c=command: c())
            button.bind("<Enter>", lambda e, b=button: b.configure(fg=ACCENT, bg=HOVER))
            button.bind("<Leave>", lambda e, b=button: b.configure(fg=MUTED, bg=bg))
        return bar


def apply_when(when):
    """Срок, найденный в названии (smart.parse_when), — в значения формы: due_at и напоминание.
    Время сказано явно — напоминаем за 15 минут; только день — срок в 9:00 без напоминания."""
    _, day, clock = when
    moment = datetime.combine(day, clock or time(int(DEFAULT_TIME[0]), int(DEFAULT_TIME[1])))
    return moment.strftime("%Y-%m-%d %H:%M"), (15 if clock else None)


class TaskForm(ttk.Frame):
    """Форма задачи: заголовок, описание, статус, срок, приоритет, напоминание.

    Встраивается в правую панель (compact=True) или в запасное окно TaskDialog.
    on_save получает словарь с новыми значениями, on_cancel вызывается при отмене.
    """

    def __init__(self, parent, task, statuses, on_save, on_cancel, compact=False, members=None,
                 history=None, hints=False, units=None):
        """history — прошлые задачи списка (строки db.list_tasks) для умных подсказок, None —
        подсказки выключены. hints — показывать под заголовком советы (срок из названия,
        приоритет и шаги похожих задач): True — для новой задачи, "changed" — для правки готовой
        (советы только по тому, что дописали в заголовок).
        units — справочник бизнес-единиц списка [(id, название)]; пустой — поля в форме нет."""
        super().__init__(parent, style="Card.TFrame" if compact else "TFrame")
        self.on_save, self.on_cancel = on_save, on_cancel
        self.history = history
        self.statuses = statuses  # [(id, название, цвет, выполнено)]
        self.members = members    # участники общего списка; None — личный список, исполнителя нет
        style_bg = SURFACE if compact else BG
        label_style = "CardMuted.TLabel" if compact else "Muted.TLabel"

        def label(text, top=12, parent=self):
            ttk.Label(parent, text=text, style=label_style).pack(anchor="w", pady=(top, 4))

        label("Заголовок", top=0)
        self.title_entry = ttk.Entry(self, font=FONT, width=1 if compact else 48)
        self.title_entry.pack(fill="x")
        self.title_entry.insert(0, task["title"])
        self.suggest = None
        if history is not None:
            self.suggest = TitleSuggest(self.title_entry, self.title_entry.get, lambda: self.history)
        # Советы умных подсказок — строками со ссылкой «применить» под заголовком
        self.hints = tk.Frame(self, bg=style_bg)
        self.hints.pack(fill="x")
        self.hints_on, self.hints_used, self.hints_job = hints and history is not None, set(), None
        # hints == "changed" — правка готовой задачи: советуем только по тому, что дописали в
        # заголовок (слова, которые были в нём и раньше, уже учтены или сознательно не учтены)
        self.hints_changed_only = hints == "changed"
        self.initial_title = task["title"]
        self.auto_marked = [False, False]  # «срочно», «важно», отмеченные по словам в заголовке
        self.prio_undone = False           # нажали «Снять» — сами больше не отмечаем
        self.refused = [False, False]      # нашу галочку сняли руками — её больше не ставим
        self.hint_bg, self.hint_wrap = style_bg, 250 if compact else 380

        # «Описание» и справа — кнопки оформления (Ж, К, З, списки; RichEditor)
        desc_head = ttk.Frame(self, style=self["style"])
        desc_head.pack(fill="x", pady=(12, 4))
        ttk.Label(desc_head, text="Описание", style=label_style).pack(side="left", anchor="s")
        desc_box = tk.Frame(self, bg=SURFACE, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT)
        desc_box.pack(fill="x")
        self.desc_user = TaskForm.desc_lines.get(compact)  # высота из ручки под полем (None — обычная)
        self.desc = tk.Text(desc_box, font=FONT, height=self.desc_user or (5 if compact else 6),
                            width=1 if compact else 48,
                            wrap="word", relief="flat", borderwidth=0, padx=8, pady=6, bg=SURFACE,
                            fg=TEXT, insertbackground=TEXT, highlightthickness=0, undo=True)
        desc_scroll = ttk.Scrollbar(desc_box, orient="vertical", command=self.desc.yview)
        self.desc.configure(yscrollcommand=desc_scroll.set)
        desc_scroll.pack(side="right", fill="y")
        self.desc.pack(side="left", fill="both", expand=True)
        self.desc.insert("1.0", task["body"])
        self.rich = RichEditor(self.desc)
        self.rich.toolbar(desc_head, style_bg).pack(side="right")
        self.rich.highlight()
        # В описании Enter — новая строка (в списке — следующий пункт); сохранить — Ctrl+Enter
        self.desc.bind("<Return>", lambda e: (self.rich.enter(), "break")[1])
        # Ручка под описанием: потянуть вниз — поле выше, вверх — ниже; высота запоминается
        self.on_desc_resize = None  # TaskDialog подменяет: окну нужно не уйти за край экрана
        grip = tk.Canvas(self, bg=style_bg, height=9, highlightthickness=0, cursor="sb_v_double_arrow")
        grip.pack(fill="x")
        grip.bind("<Configure>", lambda e: (grip.delete("all"), grip.create_line(
            e.width // 2 - 14, 4, e.width // 2 + 14, 4, fill=BORDER, width=2)))
        grip.bind("<ButtonPress-1>", self.grip_pressed)
        grip.bind("<B1-Motion>", self.grip_moved)
        grip.bind("<ButtonRelease-1>", self.grip_released)
        grip.bind("<Double-Button-1>", self.grip_reset)

        # Поля под описанием — блоками «подпись + поле». В правой панели шире WIDE блоки встают
        # парами в две колонки (layout_fields), в узкой панели и в окне — друг под другом
        self.compact, self.blocks, self.wide = compact, {}, None
        self.fields = ttk.Frame(self, style=self["style"])
        self.fields.pack(fill="x")
        self.fields.columnconfigure((0, 1), weight=1, uniform="field")

        def block(name):
            frame = ttk.Frame(self.fields, style=self["style"])
            self.blocks[name] = frame
            return frame

        box = block("status")
        label("Статус", parent=box)
        self.status = ttk.Combobox(box, values=[s[1] for s in statuses], state="readonly",
                                   width=1 if compact else 24, font=FONT)
        self.status.pack(fill="x" if compact else None, anchor="w")
        current = next((s[1] for s in statuses if s[0] == task["status_id"]), statuses[0][1])
        self.status.set(current)

        # Бизнес-единица — из справочника списка (☰ Меню → Бизнес-единицы); необязательна
        self.unit_id = task.get("unit_id")  # остаётся как была, если поля нет
        self.unit, self.unit_ids = None, {}
        if units:
            box = block("unit")
            label("Бизнес-единица", parent=box)
            self.unit_ids = {name: uid for uid, name in units or []}
            names = [NO_UNIT] + list(self.unit_ids)
            self.unit = ttk.Combobox(box, values=names, state="readonly", width=1 if compact else 24,
                                     font=FONT)
            self.unit.pack(fill="x" if compact else None, anchor="w")
            self.unit.set(next((n for n, uid in self.unit_ids.items() if uid == self.unit_id), NO_UNIT))

        self.assignee = self.initiator = None
        if members is not None:
            # Инициатор — по умолчанию автор задачи; можно выбрать участника или вписать любое имя
            # (например, руководителя, который ToDoro не пользуется)
            box = block("initiator")
            label("Инициатор", parent=box)
            known = sorted(set(members) | ({task.get("initiator")} - {None, ""}), key=str.casefold)
            self.initiator = ttk.Combobox(box, values=known, width=1 if compact else 24, font=FONT)
            self.initiator.pack(fill="x" if compact else None, anchor="w")
            self.initiator.insert(0, task.get("initiator") or "")
            box = block("assignee")
            label("Исполнитель", parent=box)
            names = sorted(set(members) | ({task.get("assignee")} - {None, ""}), key=str.casefold)
            self.assignee = ttk.Combobox(box, values=["— не назначен —"] + names, state="readonly",
                                         width=1 if compact else 24, font=FONT)
            self.assignee.pack(fill="x" if compact else None, anchor="w")
            self.assignee.set(task.get("assignee") or "— не назначен —")

        due = datetime.fromisoformat(task["due_at"]) if task["due_at"] else None
        box = block("due")
        label("Срок выполнения", parent=box)
        due_row = ttk.Frame(box, style=self["style"])
        due_row.pack(fill="x")
        self.date = DatePicker(due_row, due.date() if due else None, on_change=self.date_changed)
        self.date.configure(style=self["style"])
        self.date.pack(side="left")
        time_row = ttk.Frame(box, style=self["style"]) if compact else due_row
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
        quick = tk.Frame(box, bg=style_bg)
        quick.pack(fill="x", pady=(6, 0))
        links = (("Сегодня", lambda: self.set_date(0)), ("Завтра", lambda: self.set_date(1)),
                 ("Через неделю", lambda: self.set_date(7)), ("Без срока", lambda: self.date.set(None)))
        for i, (text, command) in enumerate(links):
            link = tk.Label(quick, text=text, bg=style_bg, fg=ACCENT, font=FONT_SMALL, cursor="hand2")
            link.grid(row=i // 2 if compact else 0, column=i % 2 if compact else i,
                      sticky="w", padx=(0, 14), pady=1)
            link.bind("<Button-1>", lambda e, c=command: c())

        box = block("prio")
        label("Приоритет", parent=box)
        prio_row = ttk.Frame(box, style=self["style"])
        prio_row.pack(fill="x")
        self.urgent = tk.BooleanVar(value=bool(task["urgent"]))
        self.important = tk.BooleanVar(value=bool(task["important"]))
        check_style = "Card.TCheckbutton" if compact else "TCheckbutton"
        ttk.Checkbutton(prio_row, text="Срочно", variable=self.urgent, style=check_style,
                        command=self.priority_clicked, cursor="hand2").pack(side="left")
        ttk.Checkbutton(prio_row, text="Важно", variable=self.important, style=check_style,
                        command=self.priority_clicked, cursor="hand2").pack(side="left", padx=(18, 0))
        self.priority_label = ttk.Label(prio_row if not compact else box, style=label_style,
                                        compound="left", justify="left")
        self.priority_label.pack(side="left" if not compact else "top", anchor="w",
                                 padx=(22, 0) if not compact else 0, pady=(4, 0) if compact else 0)
        if compact:  # в колонке пояснение переносится по словам, а не обрезается
            box.bind("<Configure>", lambda e: self.priority_label.configure(
                wraplength=max(e.width - 4, 120)), add="+")
        self.priority_changed()

        box = block("remind")
        label("Напоминание", parent=box)
        # Своё время напоминания (например, «90» из файла CSV) — отдельным пунктом, иначе при
        # сохранении формы оно молча пропало бы
        self.remind_options = dict(REMIND_OPTIONS)
        if task["remind_before"] not in REMIND_LABELS:
            self.remind_options[remind_label(task["remind_before"])] = task["remind_before"]
        self.remind = ttk.Combobox(box, values=list(self.remind_options), state="readonly",
                                   width=1 if compact else 18, font=FONT)
        self.remind.pack(fill="x" if compact else None, anchor="w")
        self.remind.set(next(label for label, minutes in self.remind_options.items()
                             if minutes == task["remind_before"]))

        # Повтор: выполнили задачу — появляется такая же со следующим сроком (db.repeat_task).
        # «Повторять» и «до» — в одной строке, по половине ширины; «до» видно, только если повтор выбран
        repeat_row = ttk.Frame(block("repeat"), style=self["style"])
        repeat_row.pack(fill="x" if compact else None, anchor="w", pady=(12, 0))
        repeat_row.columnconfigure(0, weight=1)  # «Повторять» берёт место, которое не заняла дата
        ttk.Label(repeat_row, text="Повторять", style=label_style).grid(row=0, column=0, sticky="w",
                                                                       pady=(0, 4))
        self.repeat = ttk.Combobox(repeat_row, values=list(REPEAT_OPTIONS), state="readonly",
                                   width=1 if compact else 14, font=FONT)
        self.repeat.grid(row=1, column=0, sticky="we", padx=(0, 4))
        self.repeat.set(REPEAT_LABELS.get(task.get("repeat"), "Не повторять"))
        self.repeat.bind("<<ComboboxSelected>>", lambda e: self.repeat_changed())
        until = task.get("repeat_until")
        try:
            until = date.fromisoformat(until) if until else None
        except ValueError:
            until = None
        self.until_label = ttk.Label(repeat_row, text="До", style=label_style)
        self.until = DatePicker(repeat_row, until, empty="без конца", clear="Без конца", button=False,
                                width=9)  # дата целиком; значок 📅 — в отступе справа (Date.TEntry)
        self.until.configure(style=self["style"])
        self.until_parts = ((self.until_label, dict(row=0, column=1, sticky="w", pady=(0, 4))),
                            (self.until, dict(row=1, column=1, sticky="w")))
        self.repeat_changed()
        self.layout_fields(False)
        if compact:
            self.fields.bind("<Configure>", lambda e: self.layout_fields(e.width >= self.WIDE),
                             add="+")

        if not compact:  # в правой панели кнопки — в нижней строке панели (SidePanel.show_form)
            buttons = ttk.Frame(self, style=self["style"])
            buttons.pack(fill="x", pady=(18, 0))
            # кнопки справа: «Сохранить», затем «Отмена» (pack справа налево — сначала крайняя)
            cancel = ttk.Button(buttons, text="Отмена", style="TButton", command=on_cancel)
            cancel.pack(side="right")
            ttk.Button(buttons, text="Сохранить", style="Accent.TButton", command=self.save).pack(
                side="right", padx=(0, 8))
            cancel.lift()  # Tab: сначала «Сохранить», потом «Отмена»

        self.date_changed()
        self.initial = self.values()
        bind_tree(self, "<Control-Return>", lambda e: (self.save(), "break")[1])
        bind_tree(self, "<Escape>", lambda e: (self.on_cancel(), "break")[1]
                  if not (self.suggest and self.suggest.shown()) else "break")
        self.title_entry.bind("<Return>", lambda e: None if self.suggest and self.suggest.accept()
                              else self.save())
        if self.hints_on:
            self.title_entry.bind("<KeyRelease>", lambda e: self.hints_later(), add="+")
            self.update_hints()

    # высота «Описания», выбранная ручкой, строк: {True: в правой панели, False: в окне} — у панели
    # поле занимает всё свободное место, поэтому её высота окну не подходит, и наоборот
    desc_lines = {}
    remember_desc = None  # TodoApp: запомнить её в настройках, remember_desc(compact, строк)
    DESC_LINES_MIN, DESC_LINES_MAX = 2, 60  # пределы ручки, строк
    WIDE = 440            # форма в правой панели шире (пикселей) — поля в две колонки

    def layout_fields(self, wide):
        """Расставляет блоки полей: wide — парами в две колонки (срок рядом с приоритетом,
        остальные по порядку, повтор — во всю ширину), иначе — друг под другом."""
        if wide == self.wide:
            return
        self.wide = wide
        order = ("status", "unit", "initiator", "assignee", "remind")
        if wide:
            single = [self.blocks[n] for n in order if n in self.blocks]
            rows = [single[i:i + 2] for i in range(0, len(single), 2)]
            rows += [[self.blocks["due"], self.blocks["prio"]], [self.blocks["repeat"]]]
        else:
            names = ("status", "unit", "initiator", "assignee", "due", "prio", "remind", "repeat")
            rows = [[self.blocks[n]] for n in names if n in self.blocks]
        full = (self.blocks["repeat"],) if wide else tuple(self.blocks.values())  # во всю ширину
        for row, frames in enumerate(rows):
            for column, frame in enumerate(frames):
                pad = (0, 0) if frame in full else ((0, 8) if column == 0 else (8, 0))
                frame.grid(row=row, column=column, columnspan=2 if frame in full else 1,
                           sticky="nwe" if self.compact else "nw", padx=pad)

    # --- ручка под описанием ---

    def grip_pressed(self, event):
        self.grip_start = (event.y_root, int(self.desc.cget("height")))
        self.grip_changed = False  # просто щёлкнули по ручке — высоту не запоминаем

    def grip_moved(self, event):
        y, start = self.grip_start
        line = tkfont.Font(font=FONT).metrics("linespace")
        lines = start + round((event.y_root - y) / line)
        lines = min(max(lines, self.DESC_LINES_MIN), self.DESC_LINES_MAX)
        if lines == self.desc_user or (lines == start and not self.grip_changed):
            return
        self.grip_changed = True
        self.desc_user = lines
        if self.on_desc_resize:
            self.on_desc_resize(lines)
        else:
            self.desc.configure(height=lines)

    def grip_released(self, event):
        """Отпустили ручку — эту высоту получат и следующие формы, она запоминается."""
        if getattr(self, "grip_changed", False) and self.desc_user != TaskForm.desc_lines.get(self.compact):
            TaskForm.desc_lines = {**TaskForm.desc_lines, self.compact: self.desc_user}
            if TaskForm.remember_desc:
                TaskForm.remember_desc(self.compact, self.desc_user)

    def grip_reset(self, event=None):
        """Двойной щелчок по ручке — обычная высота: в правой панели поле снова само занимает
        свободное место до кнопок, в окне — DESC_LINES строк. Выбранная высота забывается."""
        self.desc_user = None
        lines = 5 if self.compact else TaskDialog.DESC_LINES
        if self.on_desc_resize:
            self.on_desc_resize(lines)
        else:
            self.desc.configure(height=lines)
        if self.compact in TaskForm.desc_lines:
            TaskForm.desc_lines = {k: v for k, v in TaskForm.desc_lines.items() if k != self.compact}
            if TaskForm.remember_desc:
                TaskForm.remember_desc(self.compact, None)

    def focus_title(self):
        self.title_entry.focus_set()
        self.title_entry.icursor("end")

    # --- умные подсказки (smart.py) ---

    def hints_later(self):
        if self.hints_job:
            self.after_cancel(self.hints_job)
        self.hints_job = self.after(300, self.update_hints)

    def update_hints(self):
        """Под заголовком — советы: срок, найденный в названии; приоритет похожих задач; шаги
        из похожей задачи. Каждый совет, который применили, больше не предлагается."""
        self.hints_job = None
        for child in self.hints.winfo_children():
            child.destroy()
        self.hints.configure(height=1)  # иначе пустая рамка сохраняет прежнюю высоту (особенность Tk)
        title = self.title_entry.get().strip()
        if not title:
            return
        found = []
        changed_only = self.hints_changed_only
        if changed_only and title == self.initial_title.strip():
            title = ""  # в правке заголовок не меняли — советовать нечего
        old_when = smart.parse_when(self.initial_title) if changed_only else None
        when = smart.parse_when(title) if title and "when" not in self.hints_used else None
        clean = when[0] if when else title
        # в правке: срок, который был в заголовке и раньше, не предлагаем — только новый
        if when and (old_when is None or old_when[1:] != when[1:]) and not self.due_is(when):
            found.append(("when", f"Срок в названии: {smart.describe_when(when[1], when[2])}",
                          "Поставить", lambda: self.use_when(when)))
        found += self.explicit_priority(clean)
        explicit = smart.suggest_priority(clean, []) if clean else None
        prio = (smart.suggest_priority(clean, self.history)
                if clean and "prio" not in self.hints_used and not (explicit and explicit[3]) else None)
        if prio and (prio[0], prio[1]) != (self.urgent.get(), self.important.get()):
            name = PRIORITY_NAMES[priority_level(prio[0], prio[1])]
            found.append(("prio", f"«{name}» — {prio[2]}", "Отметить", lambda: self.use_priority(prio)))
        steps = None
        if title and "steps" not in self.hints_used and not self.desc.get("1.0", "end-1c").strip():
            steps = smart.suggest_steps(clean, self.history)
        if steps:
            found.append(("steps", f"Шаги из похожей задачи «{short_text(steps[0], 40)}»",
                          "Вставить в описание", lambda: self.use_steps(steps[1])))
        for kind, text, action, command in found:
            row = tk.Frame(self.hints, bg=self.hint_bg)
            row.pack(fill="x", pady=(4, 0))
            tk.Label(row, text="✨ " + text, bg=self.hint_bg, fg=MUTED, font=FONT_SMALL,
                     anchor="w", justify="left", wraplength=self.hint_wrap).pack(side="left")
            link = tk.Label(row, text=action, bg=self.hint_bg, fg=ACCENT, font=FONT_SMALL_BOLD,
                            cursor="hand2")
            link.pack(side="left", padx=(8, 0))
            link.bind("<Button-1>", lambda e, k=kind, c=command: (self.hints_used.add(k), c(),
                                                                   self.update_hints()))

    def due_is(self, when):
        """Такой срок в форме уже стоит."""
        due = datetime.fromisoformat(apply_when(when)[0])
        if self.date.value != due.date():
            return False
        return when[2] is None or (self.hour.get(), self.minute.get()) == (due.strftime("%H"),
                                                                          due.strftime("%M"))

    def explicit_priority(self, clean):
        """«срочно / asap / важно», дописанные в заголовок, отмечаем сразу, каждое слово
        отдельно и ничего не снимая; стёрли слово — снимаем свою же отметку. Слова, которые
        были в прежнем заголовке (правка задачи), не считаем. Возвращает строку-совет «Отметил…
        — Снять» для update_hints (или ничего)."""
        said = smart.suggest_priority(clean, []) if clean else None
        said = (said[0], said[1]) if said and said[3] else (False, False)
        old = smart.suggest_priority(self.initial_title, []) if self.hints_changed_only else None
        was = (old[0], old[1]) if old and old[3] else (False, False)
        if not self.prio_undone:
            for k, var in enumerate((self.urgent, self.important)):
                new = said[k] and not was[k]
                if self.auto_marked[k] and not var.get():  # нашу галочку сняли руками — отказ
                    self.auto_marked[k], self.refused[k] = False, True
                if new and not var.get() and not self.refused[k]:
                    var.set(True)
                    self.auto_marked[k] = True
                elif self.auto_marked[k] and not new:  # слово стёрли — снимаем свою отметку
                    var.set(False)
                    self.auto_marked[k] = False
            self.priority_changed()
        names = [n for n, marked in zip(("«Срочно»", "«Важно»"), self.auto_marked) if marked]
        if not names:
            return []
        return [("prio_note", f"Отметил {' и '.join(names)} — так сказано в названии", "Снять",
                 self.undo_priority)]

    def undo_priority(self):
        """«Снять»: убираем свои отметки и больше сами не отмечаем."""
        for k, var in enumerate((self.urgent, self.important)):
            if self.auto_marked[k]:
                var.set(False)
        self.auto_marked, self.prio_undone = [False, False], True
        self.priority_changed()

    def use_when(self, when):
        due_at, remind = apply_when(when)
        due = datetime.fromisoformat(due_at)
        self.date.set(due.date())  # название не трогаем — пусть остаётся, как написали
        self.date_changed()
        self.hour.set(due.strftime("%H"))
        self.minute.set(due.strftime("%M"))
        if remind is not None:
            self.remind.set(next(label for label, minutes in self.remind_options.items()
                                 if minutes == remind))

    def use_priority(self, prio):
        self.urgent.set(prio[0])
        self.important.set(prio[1])
        self.priority_changed()

    def use_steps(self, body):
        self.desc.delete("1.0", "end")
        self.desc.insert("1.0", body)
        self.rich.highlight()

    def set_date(self, days):
        self.date.set(date.today() + timedelta(days=days))

    def priority_clicked(self):
        """Галочку поставили или сняли руками — советы под заголовком тоже пересчитываем."""
        self.priority_changed()
        if self.hints_on:
            self.hints_later()

    def priority_changed(self):
        """Показывает, какой приоритет получился из галочек."""
        level = priority_level(self.urgent.get(), self.important.get())
        name = PRIORITY_NAMES[level] or "Обычная задача"
        self.priority_label.configure(
            text=f"  {name} — {PRIORITY_HINTS[level]}", image=IMAGES.get(f"priority_{level}", ""),
        )

    def date_changed(self):
        """Без даты время, напоминание и повтор выбирать нельзя (повтор отсчитывается от срока)."""
        has_date = self.date.value is not None
        for combo in (self.hour, self.minute, self.remind, self.repeat):
            combo.configure(state="readonly" if has_date else "disabled")
        if not has_date:
            self.remind.set("Не напоминать")
            self.repeat.set("Не повторять")
        self.repeat_changed()

    def repeat_changed(self):
        """Строка «до …» видна, только когда задача повторяется."""
        shown = bool(REPEAT_OPTIONS.get(self.repeat.get()))
        for widget, place in self.until_parts:
            if shown and not widget.winfo_manager():
                widget.grid(**place)
            elif not shown:
                widget.grid_remove()

    def values(self):
        """Текущие значения формы (без проверки)."""
        due_at = None
        if self.date.value:
            due = datetime.combine(self.date.value, time(int(self.hour.get()), int(self.minute.get())))
            due_at = due.strftime("%Y-%m-%d %H:%M")
        status_id = next(s[0] for s in self.statuses if s[1] == self.status.get())
        assignee = None
        if self.assignee is not None and self.assignee.get() != "— не назначен —":
            assignee = self.assignee.get()
        initiator = (self.initiator.get().strip() or None) if self.initiator is not None else None
        unit_id = self.unit_ids.get(self.unit.get()) if self.unit is not None else self.unit_id
        repeat = REPEAT_OPTIONS.get(self.repeat.get()) if due_at else None
        until = self.until.value.isoformat() if repeat and self.until.value else None
        return dict(title=self.title_entry.get().strip(), body=self.desc.get("1.0", "end-1c").strip(),
                    status_id=status_id, due_at=due_at,
                    remind_before=self.remind_options.get(self.remind.get()),
                    urgent=self.urgent.get(), important=self.important.get(), assignee=assignee,
                    initiator=initiator, unit_id=unit_id, repeat=repeat, repeat_until=until)

    def dirty(self):
        """Есть ли несохранённые изменения."""
        return self.values() != self.initial

    def save(self):
        result = self.values()
        if not result["title"]:
            ui.showwarning("Задача", "Заголовок задачи не может быть пустым.", parent=self)
            return
        if result["remind_before"] is not None and result["due_at"] is None:
            ui.showwarning("Задача", "Чтобы напомнить о задаче, укажите срок.", parent=self)
            return
        if result["repeat_until"] and result["repeat_until"] < result["due_at"][:10]:
            ui.showwarning("Задача", "«Повторять до» раньше срока задачи — выберите дату позже срока "
                                     "или «Без конца».", parent=self)
            return
        self.on_save(result)


class TaskDialog(tk.Toplevel):
    """Запасное окно с формой задачи — когда правая панель скрыта (узкое окно)."""

    def __init__(self, parent, task, statuses, members=None, title="Задача", note="",
                 standalone=False, image=None, history=None, hints=False, units=None):
        """standalone — отдельное окно (своя кнопка на панели задач): главное окно ToDoro скрыто
        или позади, а форма должна появиться поверх Outlook.
        image — картинка Pillow (снимок экрана), её уменьшенная копия показывается над формой."""
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        if not standalone:
            self.transient(parent)
        self.form = TaskForm(self, task, statuses, on_save=self.saved, on_cancel=self.destroy,
                             members=members, history=history, hints=hints, units=units)
        self.form.configure(padding=(20, 18, 20, 18))
        if note:  # например, «Из письма Outlook; будут приложены: …»
            ttk.Label(self, text=note, style="Muted.TLabel", wraplength=520, justify="left").pack(
                fill="x", padx=20, pady=(16, 0))
            self.form.configure(padding=(20, 10, 20, 18))
        self.image, self.preview, self.preview_label = image, None, None
        # высота описания: обычная или выбранная ручкой; не влезает окно — поле ниже (fit_description)
        self.desc_max = self.form.desc_user or self.DESC_LINES
        self.desc_lines = self.desc_max
        self.form.on_desc_resize = self.desc_dragged
        self.fit_job = None
        if image is not None:
            self.full_preview = min(self.PREVIEW_HEIGHT, round(image.height * min(
                1, self.PREVIEW_WIDTH / max(image.width, 1))))
            self.preview_label = tk.Label(self, bg=BORDER, bd=0, padx=1, pady=1)
            self.preview_label.pack(anchor="w", padx=20, pady=(10, 0))
            self.show_preview(self.full_preview)
        self.form.pack(fill="both")
        # Размер окна не задаём: оно само вытягивается, когда в форме появляется строка
        # (например, «Отметил „Срочно“…» под заголовком), а keep_on_screen не даёт ему уйти
        # за край экрана — иначе кнопки «Сохранить» и «Отмена» обрезаются (сообщение #1)
        hidden = hide_new_window(self)
        self.keep_on_screen(place=False)
        left, top, width, height = work_area(self)
        x = left + max((width - self.winfo_reqwidth()) // 2, 0)
        y = top + max((height - self.winfo_reqheight() - self.TITLE_BAR) // 2, 0)
        place_window(self, x, y, show=hidden)
        self.form.bind("<Configure>", lambda e: self.fit_later(), add="+")
        if standalone:
            bring_to_front(self)
        self.form.focus_title()
        self.grab_set()

    PREVIEW_WIDTH, PREVIEW_HEIGHT, MIN_PREVIEW = 520, 180, 40  # картинка снимка над формой
    PREVIEW_PAD = 12                    # отступ над картинкой и её рамка
    DESC_LINES, MIN_DESC_LINES = 6, 2   # высота поля «Описание», строк
    TITLE_BAR, MARGIN = 32, 8           # заголовок окна (до показа) и запас снизу, пикселей

    def show_preview(self, height):
        """Уменьшенная копия снимка высотой не больше height. Сам снимок к задаче
        прикладывается целиком — уменьшается только картинка в окне."""
        from PIL import ImageTk
        preview = self.image.copy()
        preview.thumbnail((self.PREVIEW_WIDTH, height))
        self.preview = ImageTk.PhotoImage(preview, master=self)  # иначе Tk картинку «забудет»
        self.preview_label.configure(image=self.preview)

    def preview_space(self):
        """Сколько по высоте сейчас занимает картинка снимка вместе с отступом (0 — убрана)."""
        return self.preview.height() + self.PREVIEW_PAD if self.preview_label.winfo_manager() else 0

    def fit_later(self):
        if self.fit_job is None:
            self.fit_job = self.after_idle(self.keep_on_screen)

    def keep_on_screen(self, place=True):
        """Окно не должно выходить за край экрана: если не влезает по высоте — сначала
        уменьшаем картинку снимка, потом поле «Описание» (появится место — возвращаем как было);
        если низ уходит за панель задач — сдвигаем окно вверх, но не выше верха экрана."""
        self.fit_job = None
        if not self.winfo_exists():
            return
        self.update_idletasks()
        _, top, _, height = work_area(self)
        title_bar = self.winfo_rooty() - self.winfo_y() if self.winfo_ismapped() else 0
        title_bar = title_bar if title_bar > 0 else self.TITLE_BAR
        room = height - title_bar - self.MARGIN    # сколько окну можно занять по высоте
        extra = self.winfo_reqheight() - room      # на сколько не влезает (меньше 0 — есть запас)
        if extra < 0:  # место появилось — сначала возвращаем строки описания, потом картинку
            extra = self.fit_description(extra)
        if self.preview is not None:  # картинка — не меньше MIN_PREVIEW
            now = self.preview_space()
            want = max(min(self.full_preview, now - extra - self.PREVIEW_PAD),
                       min(self.MIN_PREVIEW, self.full_preview))
            if not now or want != self.preview.height():
                self.show_preview(want)
                if not now:
                    self.preview_label.pack(anchor="w", padx=20, pady=(10, 0), before=self.form)
            extra -= now - self.preview_space()
        extra = self.fit_description(extra)
        if extra > 0 and self.preview is not None:  # и так не влезает — убираем картинку совсем
            extra -= self.preview_space()
            self.preview_label.pack_forget()
            self.fit_description(extra)  # освободилось место — описанию, сколько можно
        if not place:
            return
        self.update_idletasks()
        y = self.winfo_y()
        bottom = top + height - self.MARGIN - title_bar - self.winfo_reqheight()
        new_y = max(min(y, bottom), top)
        if new_y != y:
            self.geometry(f"+{self.winfo_x()}+{new_y}")

    def fit_description(self, extra):
        """Поле «Описание» короче (extra > 0) или снова длиннее (extra < 0), но в пределах
        MIN_DESC_LINES…DESC_LINES строк. Возвращает, на сколько окно ещё не влезает."""
        line = tkfont.Font(font=FONT).metrics("linespace")
        lines = max(min(self.desc_max, self.desc_lines - math.ceil(extra / line)),
                    self.MIN_DESC_LINES)
        extra -= (self.desc_lines - lines) * line
        if lines != self.desc_lines:
            self.desc_lines = lines
            self.form.desc.configure(height=lines)
        return extra

    def desc_dragged(self, lines):
        """Потянули ручку под описанием: окно вытягивается или сжимается вместе с полем,
        но за край экрана не уходит (keep_on_screen)."""
        self.desc_max = self.desc_lines = lines
        self.form.desc.configure(height=lines)
        self.fit_later()

    def saved(self, result):
        self.result = result
        self.form_initial = self.form.initial
        self.destroy()


FOLDER_HINT = r"%APPDATA%\ToDoro"  # папка с задачами, как её пишут в Windows


class HelpWindow(tk.Toplevel):
    """Справка: слева — поиск и темы по разделам, справа — выбранная тема (текст из help_text.py)."""

    MARKUP = re.compile(r"(\*\*.+?\*\*|\[[^\]]+\]|\{p[123]\}|\{github\}|\{folder\})")
    ICON_FONT = ("Segoe MDL2 Assets", 11)
    SEARCH_HINT = "Поиск по справке"

    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"Справка — {APP_NAME}")
        self.configure(bg=BG)
        self.minsize(780, 480)
        self.topics = self.parse(HELP)
        self.current = 0
        self.query = ""

        # --- левая колонка: поиск и темы ---
        nav = tk.Frame(self, bg=BG, width=270)
        nav.pack(side="left", fill="y", padx=(14, 0), pady=16)
        nav.pack_propagate(False)
        tk.Label(nav, text="Справка", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 15)).pack(
            anchor="w", padx=8, pady=(0, 10))
        search = tk.Frame(nav, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                          highlightcolor=ACCENT)
        search.pack(fill="x", padx=(4, 8), pady=(0, 10))
        tk.Label(search, text="", bg=SURFACE, fg=MUTED, font=self.ICON_FONT).pack(
            side="left", padx=(8, 4))
        self.search = tk.Entry(search, relief="flat", bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                               insertbackground=TEXT, highlightthickness=0, borderwidth=0)
        self.search.pack(side="left", fill="x", expand=True, ipady=6)
        self.search.insert(0, self.SEARCH_HINT)
        self.search.bind("<FocusIn>", self.search_focus)
        self.search.bind("<FocusOut>", self.search_blur)
        self.search.bind("<KeyRelease>", lambda e: self.after_idle(self.run_search))
        self.search.bind("<Escape>", lambda e: (self.clear_search(), "break")[1])
        self.search.bind("<Return>", lambda e: self.open_first_match())

        self.nav_area = ScrollArea(nav, BG)
        self.nav_area.pack(fill="both", expand=True)
        self.nav_rows = []  # (рамка, номер темы или None для заголовка раздела, виджеты)
        self.build_nav()
        tk.Label(nav, text=f"{COPYRIGHT} · MIT", bg=BG, fg=DONE, font=("Segoe UI", 9)).pack(
            anchor="w", padx=8, pady=(8, 0))

        # --- справа: выбранная тема ---
        page = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        page.pack(side="left", fill="both", expand=True, padx=(10, 16), pady=16)
        bottom = tk.Frame(page, bg=SURFACE)
        bottom.pack(side="bottom", fill="x", padx=24, pady=(4, 14))
        self.prev_link = self.nav_link(bottom, "left")
        self.next_link = self.nav_link(bottom, "right")
        tk.Frame(page, bg=BORDER, height=1).pack(side="bottom", fill="x", padx=24)

        text = tk.Text(page, wrap="word", bg=SURFACE, fg=TEXT, font=FONT, relief="flat",
                       borderwidth=0, highlightthickness=0, padx=34, pady=26, cursor="arrow",
                       spacing1=2, spacing3=2, tabs=("230",))
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        text.pack(side="left", fill="both", expand=True)
        self.text = text
        text.tag_configure("group", font=("Segoe UI Semibold", 9), foreground=MUTED, spacing3=2)
        text.tag_configure("h1", font=("Segoe UI Semibold", 18), spacing3=12)
        text.tag_configure("p", spacing1=4, spacing3=6)
        text.tag_configure("li", lmargin1=6, lmargin2=24, spacing3=5)
        text.tag_configure("step", lmargin1=6, lmargin2=32, spacing3=6)
        text.tag_configure("num", font=("Segoe UI Semibold", 10), foreground=ACCENT)
        text.tag_configure("tip", lmargin1=16, lmargin2=16, rmargin=16, spacing1=14, spacing3=14,
                           background=ACCENT_SOFT, foreground=TEXT)
        text.tag_configure("keyrow", lmargin1=6, lmargin2=230, spacing3=7)
        text.tag_configure("links", spacing1=18, foreground=MUTED, font=FONT_SMALL)
        text.tag_configure("b", font=FONT_BOLD)
        text.tag_configure("key", font=("Segoe UI Semibold", 10), background=SEGMENT_BG)
        text.tag_configure("link", foreground=ACCENT, underline=True)
        text.tag_configure("found", background=FOUND)
        text.tag_bind("link", "<Button-1>", lambda e: webbrowser.open(PROJECT_URL))
        # папка с задачами: щелчок открывает её в Проводнике
        text.tag_configure("folder", foreground=ACCENT, underline=True)
        text.tag_bind("folder", "<Button-1>", lambda e: os.startfile(db.DATA_DIR))
        for tag in ("link", "goto", "folder"):
            text.tag_bind(tag, "<Enter>", lambda e: text.configure(cursor="hand2"))
            text.tag_bind(tag, "<Leave>", lambda e: text.configure(cursor="arrow"))
        text.tag_configure("goto", foreground=ACCENT, font=FONT_SMALL)

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Control-f>", lambda e: self.search.focus_set())
        self.bind("<Control-F>", lambda e: self.search.focus_set())
        self.nav_area.bind_wheel()
        center_on_screen(self, 1020, 700)
        self.show_topic(0)
        text.focus_set()

    # --- данные ---

    @staticmethod
    def parse(help_rows):
        """Строки help_text.HELP -> темы: [dict(group, icon, title, rows)]."""
        topics, group, icon = [], "", ""
        for kind, line in help_rows:
            if kind == "group":
                icon, group = line.split("|", 1)
            elif kind == "h2":
                topics.append(dict(group=group, icon=icon, title=line, rows=[]))
            elif topics:
                topics[-1]["rows"].append((kind, line))
        return topics

    @staticmethod
    def plain(line):
        """Текст без разметки — для поиска."""
        return re.sub(r"\*\*|\[|\]|\{p[123]\}", "", line).replace("{github}", "github") \
            .replace("{folder}", FOLDER_HINT)

    def stems(self):
        return search_stems(self.query)

    def matches(self, topic):
        if not self.query:
            return True
        haystack = " ".join([topic["title"]] + [self.plain(line) for _, line in topic["rows"]]).lower()
        return all(stem in haystack for stem in self.stems())

    # --- левая колонка ---

    def build_nav(self):
        inner = self.nav_area.inner
        group = None
        for index, topic in enumerate(self.topics):
            if topic["group"] != group:
                group = topic["group"]
                head = tk.Frame(inner, bg=BG)
                mark = tk.Label(head, text=topic["icon"], bg=BG, fg=MUTED, font=self.ICON_FONT)
                mark.pack(side="left", padx=(8, 6))
                tk.Label(head, text=group.upper(), bg=BG, fg=MUTED,
                         font=("Segoe UI Semibold", 8)).pack(side="left")
                self.nav_rows.append((head, None, group))
            row = tk.Label(inner, text=topic["title"], bg=BG, fg=TEXT, font=FONT_SMALL, anchor="w",
                           padx=34, pady=5, cursor="hand2")
            row.bind("<Button-1>", lambda e, i=index: self.show_topic(i))
            row.bind("<Enter>", lambda e, i=index: self.paint_row(i, hover=True))
            row.bind("<Leave>", lambda e, i=index: self.paint_row(i))
            self.nav_rows.append((row, index, group))
        self.empty = tk.Label(inner, text="Ничего не найдено.\nПопробуйте другое слово.", bg=BG,
                              fg=MUTED, font=FONT_SMALL, justify="left")
        self.layout_nav()

    def layout_nav(self):
        visible = {i for i, t in enumerate(self.topics) if self.matches(t)}
        groups = {self.topics[i]["group"] for i in visible}
        for widget, *_ in self.nav_rows:
            widget.pack_forget()
        self.empty.pack_forget()
        for widget, index, group in self.nav_rows:
            if index is None and group in groups:
                widget.pack(fill="x", pady=(10, 2))
            elif index is not None and index in visible:
                widget.pack(fill="x")
        if not visible:
            self.empty.pack(anchor="w", padx=8, pady=10)
        for i in range(len(self.topics)):
            self.paint_row(i)

    def row_widget(self, index):
        return next(w for w, i, _ in self.nav_rows if i == index)

    def paint_row(self, index, hover=False):
        row = self.row_widget(index)
        if index == self.current:
            row.configure(bg=ACCENT_SOFT, fg=ACCENT, font=("Segoe UI Semibold", 10))
        else:
            row.configure(bg=HOVER if hover else BG, fg=TEXT, font=FONT_SMALL)

    # --- поиск ---

    def search_focus(self, event=None):
        if self.search.get() == self.SEARCH_HINT:
            self.search.delete(0, "end")
        self.search.configure(fg=TEXT)

    def search_blur(self, event=None):
        if not self.search.get():
            self.search.insert(0, self.SEARCH_HINT)
            self.search.configure(fg=MUTED)

    def run_search(self):
        text = self.search.get()
        query = "" if text == self.SEARCH_HINT else " ".join(text.lower().split())
        if query == self.query:
            return
        self.query = query
        self.layout_nav()
        if not query:
            self.show_topic(self.current)
            return
        # сначала — тема, в названии которой есть искомое слово; иначе первая подходящая
        stems = self.stems()
        best = next((i for i, t in enumerate(self.topics)
                     if self.matches(t) and any(st in t["title"].lower() for st in stems)), None)
        if best is not None:
            self.show_topic(best)
        elif self.matches(self.topics[self.current]):
            self.show_topic(self.current)
        elif not self.open_first_match():
            self.highlight()  # ничего не найдено — убрать старую подсветку

    def open_first_match(self):
        first = next((i for i, t in enumerate(self.topics) if self.matches(t)), None)
        if first is not None:
            self.show_topic(first)
        return first is not None

    def clear_search(self):
        self.search.delete(0, "end")
        self.run_search()
        self.text.focus_set()

    # --- правая часть ---

    def nav_link(self, parent, side):
        link = tk.Label(parent, bg=SURFACE, fg=ACCENT, font=FONT_SMALL, cursor="hand2")
        link.pack(side=side)
        return link

    def show_topic(self, index):
        old, self.current = self.current, index
        self.paint_row(old)
        self.paint_row(index)
        topic = self.topics[index]
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        for tag in text.tag_names():
            if tag.startswith("goto") and tag != "goto":
                text.tag_delete(tag)
        text.insert("end", topic["group"].upper() + "\n", "group")
        if index == 0 and "totoro_small" in IMAGES:
            text.image_create("end", image=IMAGES["totoro_small"], padx=0)
            text.insert("end", "  ", "h1")
        text.insert("end", topic["title"] + "\n", "h1")
        step = 0
        for kind, line in topic["rows"]:
            if kind == "step":
                step += 1
                text.insert("end", f"{step}.  ", ("step", "num"))
                self.insert_marked(text, line, "step")
            elif kind == "li":
                text.insert("end", "•   ", "li")
                self.insert_marked(text, line, "li")
            elif kind == "tip":
                text.insert("end", "💡  ", "tip")
                self.insert_marked(text, line, "tip")
            elif kind == "key":
                keys, what = line.split("|", 1)
                self.insert_marked(text, keys, "keyrow")
                text.insert("end", "\t" + what, "keyrow")
            elif kind == "links":
                text.insert("end", "Смотрите также:   ", "links")
                for n, title in enumerate(line.split("|")):
                    target = next((i for i, t in enumerate(self.topics) if t["title"] == title), None)
                    if target is None:
                        continue
                    tag = f"goto{target}"
                    text.tag_bind(tag, "<Button-1>", lambda e, i=target: self.show_topic(i))
                    text.insert("end", ("   ·   " if n else "") , "links")
                    text.insert("end", title, ("links", "goto", tag))
            else:
                self.insert_marked(text, line, kind)
            text.insert("end", "\n", kind if kind != "key" else "keyrow")
        self.highlight()
        text.configure(state="disabled")
        text.yview_moveto(0)
        # «← Назад / Далее →»
        for link, target in ((self.prev_link, index - 1), (self.next_link, index + 1)):
            if 0 <= target < len(self.topics):
                title = self.topics[target]["title"]
                link.configure(text=f"← {title}" if link is self.prev_link else f"{title} →")
                link.bind("<Button-1>", lambda e, i=target: self.show_topic(i))
            else:
                link.configure(text="")
                link.unbind("<Button-1>")

    def highlight(self):
        """Подсвечивает найденные слова в открытой теме."""
        self.text.tag_remove("found", "1.0", "end")
        for stem in self.stems():
            start = "1.0"
            while True:
                pos = self.text.search(stem, start, "end", nocase=True)
                if not pos:
                    break
                end = self.text.index(f"{pos} wordend")  # подсвечиваем слово целиком
                self.text.tag_add("found", pos, end)
                start = end

    def insert_marked(self, text, line, kind):
        """Вставляет строку, превращая **…**, […] и {pN} в оформление."""
        line = line.replace(" [", " [")  # клавиша переносится вместе с предыдущим словом
        for part in self.MARKUP.split(line):
            if not part:
                continue
            if part.startswith("**"):
                text.insert("end", part[2:-2], (kind, "b"))
            elif part.startswith("["):
                # неразрывные пробелы, чтобы клавиша не разрывалась переносом строки
                text.insert("end", f" {part[1:-1]} ", (kind, "key"))
            elif part.startswith("{p"):
                image = IMAGES.get(f"priority_{part[2]}")
                if image:
                    text.image_create("end", image=image, align="center")
            elif part == "{github}":
                text.insert("end", PROJECT_URL.removeprefix("https://"), (kind, "link"))
            elif part == "{folder}":
                # без полного пути: в нём имя пользователя Windows, а снимки справки публикуются
                text.insert("end", FOLDER_HINT, (kind, "folder"))
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

        # Автор: логотип machinist-soft слева от копирайта и ссылки на проект.
        author = tk.Frame(body, bg=SURFACE)
        author.pack(fill="x", pady=(18, 10))
        logo = IMAGES.get("machinist_dark" if THEME == "dark" else "machinist")
        if logo:
            tk.Label(author, image=logo, bg=SURFACE).pack(side="left", padx=(0, 12))
        credits = tk.Frame(author, bg=SURFACE)
        credits.pack(side="left", anchor="center")
        tk.Label(credits, text=COPYRIGHT, bg=SURFACE, fg=TEXT, font=FONT_BOLD).pack(anchor="w", pady=(0, 2))
        link = tk.Label(credits, text=PROJECT_URL.removeprefix("https://"), bg=SURFACE, fg=ACCENT,
                        font=(*FONT_SMALL, "underline"), cursor="hand2")
        link.pack(anchor="w")
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


class WhatsNewWindow(tk.Toplevel):
    """«Что нового»: изменения всех версий из файла RELEASE_NOTES.md (он ставится вместе
    с программой — интернет не нужен)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"Что нового — {APP_NAME}")
        self.configure(bg=BG)
        self.minsize(560, 400)

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=24, pady=(18, 10))
        if "totoro_small" in IMAGES:
            tk.Label(head, image=IMAGES["totoro_small"], bg=BG).pack(side="left", padx=(0, 14))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", anchor="center")
        tk.Label(titles, text="Что нового", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(titles, text=f"У вас версия {APP_VERSION}. Новые изменения — сверху.", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(anchor="w")

        bar = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        bar.pack(fill="x", side="bottom")
        ttk.Button(bar, text="Закрыть", style="Accent.TButton", command=self.destroy).pack(
            side="right", padx=(0, 18), pady=12)
        ttk.Button(bar, text="Все выпуски на GitHub…", style="Soft.TButton",
                   command=lambda: webbrowser.open(updater.RELEASES_LIST)).pack(side="right", padx=(0, 8))

        page = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        page.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        text = tk.Text(page, wrap="word", bg=SURFACE, fg=TEXT, font=FONT_SMALL, relief="flat",
                       borderwidth=0, highlightthickness=0, padx=26, pady=18, cursor="arrow",
                       spacing1=1, spacing3=1, width=80, height=26)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        text.pack(side="left", fill="both", expand=True)
        text.tag_configure("version", font=("Segoe UI Semibold", 14), spacing1=18, spacing3=2)
        text.tag_configure("first", spacing1=0)
        text.tag_configure("date", font=FONT_SMALL, foreground=MUTED)
        text.tag_configure("current", font=FONT_SMALL_BOLD, foreground=GOOD_TEXT)
        text.tag_configure("soon", font=FONT_SMALL_BOLD, foreground=WARN)
        text.tag_configure("group", font=FONT_SMALL_BOLD, foreground=ACCENT, spacing1=10, spacing3=4)
        text.tag_configure("li", lmargin1=4, lmargin2=20, spacing3=5)
        text.tag_configure("p", spacing3=5)
        text.tag_configure("note", lmargin1=12, lmargin2=12, rmargin=12, spacing1=4, spacing3=4,
                           background=ACCENT_SOFT)
        text.tag_configure("b", font=FONT_SMALL_BOLD)
        self.fill(text)
        text.configure(state="disabled")

        self.bind("<Escape>", lambda e: self.destroy())
        center_on_screen(self, 760, 660)
        self.focus_force()

    @staticmethod
    def blocks(markdown):
        """Разметка RELEASE_NOTES.md -> [(вид, текст)]: version, group, li, note, p.
        Строки-продолжения пункта (с отступом) склеиваются с ним."""
        blocks = []
        started = False
        for line in markdown.splitlines():
            if line.startswith("## "):
                started = True
                blocks.append(("version", line[3:].strip()))
            elif not started or not line.strip():
                continue
            elif line.startswith("### "):
                blocks.append(("group", line[4:].strip()))
            elif line.startswith("- "):
                blocks.append(("li", line[2:].strip()))
            elif line.startswith(">"):
                body = line[1:].strip()
                if blocks and blocks[-1][0] == "note":
                    blocks[-1] = ("note", blocks[-1][1] + " " + body)
                else:
                    blocks.append(("note", body))
            elif line.startswith(" ") and blocks and blocks[-1][0] in ("li", "p"):
                blocks[-1] = (blocks[-1][0], blocks[-1][1] + " " + line.strip())
            else:
                blocks.append(("p", line.strip()))
        return blocks

    def fill(self, text):
        path = RELEASE_NOTES_PATH
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError:
            text.insert("end", "Файл с описанием изменений не найден. Все выпуски — на GitHub "
                               "(кнопка внизу).", "p")
            return
        first = True
        for kind, line in self.blocks(markdown):
            if kind == "version":
                version, _, when = line.partition(" — ")
                tags = ("version", "first") if first else ("version",)
                first = False
                if version == "Не выпущено":
                    text.insert("end", "Скоро", tags)
                    text.insert("end", "   ещё не выпущено\n", ("soon",))
                    continue
                text.insert("end", f"Версия {version}", tags)
                if when:
                    text.insert("end", f"   {when}", "date")
                if version == APP_VERSION:
                    text.insert("end", "   ✔ у вас эта версия", "current")
                text.insert("end", "\n")
                continue
            if kind == "li":
                text.insert("end", "•  ", "li")
            for i, part in enumerate(re.split(r"\*\*", line.replace("`", ""))):
                text.insert("end", part, (kind, "b") if i % 2 else kind)
            text.insert("end", "\n", kind)


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
        "alert": (ALERT_BG, ALERT_BORDER, DANGER),
        "done": (GOOD_BG, GOOD_BORDER, GOOD_TEXT),
        "sleep": (GOOD_BG, GOOD_BORDER, GOOD_TEXT),  # всё сделано — Тоторо спит
    }

    # Анимация: Тоторо «дышит» (чуть покачивается), моргает, радуется, когда на него наводят
    # мышь или щёлкают, волнуется, когда есть просроченные задачи, и спит, когда всё сделано.
    FRAME_MS = 50            # кадр анимации
    BREATH = {"normal": (2.0, 2400), "alert": (1.5, 1500), "sleep": (2.5, 4200)}  # размах px, период мс
    JUMP_MS, JUMP_PX = 480, 22

    def __init__(self, parent, on_task_click):
        super().__init__(parent, bg=SURFACE)
        self.on_task_click = on_task_click
        self.canvas = tk.Canvas(self, width=PANEL_WIDTH, bg=SURFACE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.message = ("", (), "", "normal", "")
        self.animate = True           # выключается в настройках
        self.totoro_item = None       # картинка Тоторо на холсте и её «спокойное» положение
        self.totoro_x = self.totoro_y = 0
        self.shown = (None, None)     # что сейчас на экране: (картинка, сдвиг по высоте)
        self.hover = False
        self.next_blink = self.now() + 2500
        self.blink_until = self.second_blink = 0
        self.happy_until = self.jump_start = 0
        self.zzz = []                 # всплывающие «z» над спящим Тоторо: (id, когда появилась)
        self.next_z = 0
        self.after(1000, self.tick)

    @staticmethod
    def now():
        return time_module.perf_counter() * 1000

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

        self.totoro_item = None
        self.zzz = []
        if totoro:
            self.totoro_x, self.totoro_y = cx, y2 + 16
            self.totoro_item = c.create_image(cx, y2 + 16, image=totoro, anchor="n", tags=("totoro",))
            self.shown = ("totoro", 0)
            c.tag_bind("totoro", "<Enter>", lambda e: self.set_hover(True))
            c.tag_bind("totoro", "<Leave>", lambda e: self.set_hover(False))
            c.tag_bind("totoro", "<Button-1>", lambda e: self.cheer())
        if stats:
            c.create_text(cx, y2 + 16 + totoro_h + 8, text=stats, font=FONT_SMALL,
                          fill=MUTED, anchor="n", width=width - 2 * pad, justify="center")

        for _, tid in tasks:
            c.tag_bind(f"task{tid}", "<Button-1>", lambda e, t=tid: self.on_task_click(t))
        c.tag_bind("task", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("task", "<Leave>", lambda e: c.configure(cursor=""))
        self.render_frame(force=True)

    # --- анимация ---

    def set_hover(self, hover):
        self.hover = hover and self.animate
        self.canvas.configure(cursor="hand2" if self.hover else "")

    def cheer(self):
        """Тоторо радуется и подпрыгивает (щелчок по нему или выполненная задача)."""
        if self.animate:
            self.happy_until = self.now() + 1300
            self.jump_start = self.now()

    def tick(self):
        """Кадр анимации. Пока панель не видна (открыта карточка задачи, окно свёрнуто)
        или анимация выключена — ничего не делаем и проверяем реже."""
        try:
            visible = (self.animate and self.totoro_item is not None and self.winfo_ismapped()
                       and self.winfo_toplevel().state() != "iconic")
        except tk.TclError:
            return  # окно закрыто
        if visible:
            self.render_frame()
        self.after(self.FRAME_MS if visible else 400, self.tick)

    def face(self, t, mood):
        """Какую картинку показать сейчас."""
        if t < self.happy_until or self.hover:
            return "totoro_happy"
        if mood == "sleep":
            return "totoro_sleep"
        if t >= self.next_blink:  # пора моргнуть; иногда — дважды подряд
            self.blink_until = t + 130
            self.second_blink = t + 330 if random.random() < 0.25 else 0
            self.next_blink = t + random.uniform(2500, 6000)
        if self.second_blink and t >= self.second_blink:
            self.blink_until, self.second_blink = t + 120, 0
        if t < self.blink_until:
            return "totoro_blink"
        return "totoro_worried" if mood == "alert" else "totoro"

    def render_frame(self, force=False):
        if self.totoro_item is None:
            return
        mood = self.message[3]
        t = self.now()
        if not self.animate:
            name, dy = "totoro", 0
        else:
            name = self.face(t, mood)
            amplitude, period = self.BREATH.get(mood, self.BREATH["normal"])
            dy = amplitude * math.sin(2 * math.pi * t / period)
            if t - self.jump_start < self.JUMP_MS:  # прыжок по параболе
                p = (t - self.jump_start) / self.JUMP_MS
                dy -= self.JUMP_PX * 4 * p * (1 - p)
            dy = round(dy)
        if name not in IMAGES:
            name = "totoro"
        if force or (name, dy) != self.shown:  # перерисовываем, только если кадр изменился
            self.canvas.itemconfigure(self.totoro_item, image=IMAGES[name])
            self.canvas.coords(self.totoro_item, self.totoro_x, self.totoro_y + dy)
            self.shown = (name, dy)
        if self.animate and mood == "sleep":
            self.float_zzz(t)
        elif self.zzz:
            for item, _ in self.zzz:
                self.canvas.delete(item)
            self.zzz = []

    ZZZ_LIFE = 2600
    ZZZ_COLORS = []  # от приглушённого цвета текста к цвету фона (заполняется после tint)

    def float_zzz(self, t):
        """Над спящим Тоторо всплывают и тают буквы «z»."""
        c = self.canvas
        if t >= self.next_z:
            self.next_z = t + 900
            size = random.choice((10, 12, 14))
            item = c.create_text(self.totoro_x + 48, self.totoro_y + 30, text="z",
                                 font=("Segoe UI Semibold", size), fill=self.ZZZ_COLORS[0])
            self.zzz.append((item, t))
        alive = []
        for item, born in self.zzz:
            age = (t - born) / self.ZZZ_LIFE
            if age >= 1:
                c.delete(item)
                continue
            c.coords(item, self.totoro_x + 48 + 10 * age + 4 * math.sin(age * 6),
                     self.totoro_y + 30 - 55 * age)
            c.itemconfigure(item, fill=self.ZZZ_COLORS[min(int(age * len(self.ZZZ_COLORS)),
                                                           len(self.ZZZ_COLORS) - 1)])
            alive.append((item, born))
        self.zzz = alive


TotoroPanel.ZZZ_COLORS = [tint(MUTED, k / 6, SURFACE) for k in range(7)]


class TaskCard(tk.Frame):
    """Карточка выбранной задачи: заголовок, описание и все поля."""

    def __init__(self, parent, on_close, on_edit, on_email, on_toggle, on_delete, extras, on_collapse):
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
        # «📧 Из Outlook» — задача создана из письма (видна только у таких задач)
        self.from_mail = tk.Label(top, text=MAIL_MARK + " Из Outlook", bg=SURFACE, fg=ACCENT, font=FONT_SMALL)
        close = tk.Label(top, text="✕", bg=SURFACE, fg=MUTED, font=FONT, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: on_close())
        close.bind("<Enter>", lambda e: close.configure(fg=TEXT))
        close.bind("<Leave>", lambda e: close.configure(fg=MUTED))
        collapse_button(top, on_collapse).pack(side="right", padx=(0, 10))

        self.title = tk.Label(self, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 14),
                              wraplength=wrap, justify="left", anchor="w")
        self.title.pack(fill="x", pady=(6, 2))
        self.status = tk.Label(self, bg=SURFACE, font=FONT_SMALL, anchor="w")
        self.status.pack(fill="x")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=12)

        # Действия с задачей — внизу карточки, сроки и даты — над ними
        actions = self.actions = tk.Frame(self, bg=SURFACE)
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
        self.captions = {}
        for row, (key, label) in enumerate((("important", "Важность"), ("urgent", "Срочность"),
                                            ("due", "Срок"), ("remind", "Напомнить"), ("repeat", "Повтор"),
                                            ("created", "Создана"), ("author", "Инициатор"),
                                            ("assignee", "Исполнитель"), ("unit", "Бизнес-единица"),
                                            ("updated", "Изменена"))):
            caption = tk.Label(self.fields, text=label, bg=SURFACE, fg=MUTED, font=FONT_SMALL)
            caption.grid(row=row, column=0, sticky="w", pady=1)
            value = tk.Label(self.fields, bg=SURFACE, fg=TEXT, font=FONT_SMALL)
            value.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=1)
            self.values[key], self.captions[key] = value, caption
        self.fields_line = tk.Frame(self, bg=BORDER, height=1)
        self.fields_line.pack(side="bottom", fill="x", pady=12)

        # Вкладки: описание, вложенные файлы, комментарии
        self.extras = extras
        self.task_id = None
        self.tab = tk.StringVar(value="body")
        tabs = ttk.Frame(self, style="Segments.TFrame", padding=2)
        tabs.pack(fill="x", pady=(0, 8))
        self.tab_buttons = {}
        for column, (key, text) in enumerate((("body", "Описание"), ("files", "Файлы"),
                                              ("comments", "Комментарии"))):
            button = ttk.Radiobutton(tabs, text=text, value=key, variable=self.tab,
                                     style="Tab.TRadiobutton", command=self.show_tab, cursor="hand2")
            button.grid(row=0, column=column, sticky="we")
            tabs.columnconfigure(column, weight=1)
            self.tab_buttons[key] = button
        self.pages = {}

        # Описание (только для чтения, с прокруткой колесом)
        body_box = self.pages["body"] = tk.Frame(self, bg=SURFACE)
        self.body_scroll = ttk.Scrollbar(body_box, orient="vertical")
        self.body = tk.Text(body_box, bg=SURFACE, fg=TEXT, font=FONT, wrap="word", relief="flat",
                            borderwidth=0, highlightthickness=0, height=4, width=1,
                            padx=0, pady=4, cursor="arrow", spacing3=4,
                            yscrollcommand=self.update_body_scroll)
        self.body_scroll.configure(command=self.body.yview)
        self.body.pack(side="left", fill="both", expand=True)
        self.body.tag_configure("empty", foreground=DONE, font=FONT_SMALL)

        # Файлы: список с превью картинок, внизу — «Добавить», «Вставить» и «Снимок» (области экрана)
        page = self.pages["files"] = tk.Frame(self, bg=SURFACE)
        buttons = tk.Frame(page, bg=SURFACE)
        buttons.pack(side="bottom", fill="x", pady=(8, 0))
        buttons.columnconfigure((0, 1, 2), weight=1, uniform="files")
        ttk.Button(buttons, text="＋  Добавить", style="Soft.TButton", cursor="hand2",
                   command=lambda: extras.add_files(self.task_id)).grid(
            row=0, column=0, sticky="we", padx=(0, 3))
        ttk.Button(buttons, text="Вставить", style="Soft.TButton", cursor="hand2",
                   command=self.paste).grid(row=0, column=1, sticky="we", padx=3)
        ttk.Button(buttons, text="✂  Снимок", style="Soft.TButton", cursor="hand2",
                   command=lambda: extras.snip_to_task(self.task_id)).grid(
            row=0, column=2, sticky="we", padx=(3, 0))
        self.files_area = ScrollArea(page, SURFACE)
        self.files_area.pack(fill="both", expand=True)
        self.thumbs = {}  # (файл списка, id вложения) -> картинка-превью (иначе Tk её «забудет»)
        self.file_previews = {}
        self.type_icons = {}  # расширение -> значок типа файла из Проводника (или None)
        self.file_labels = []
        self.files_area.inner.bind("<Configure>", lambda e: [
            label.configure(wraplength=max(e.width - 80, 120)) for label in self.file_labels], add="+")

        # Комментарии: лента сверху, поле для нового комментария снизу
        page = self.pages["comments"] = tk.Frame(self, bg=SURFACE)
        write = tk.Frame(page, bg=SURFACE)
        write.pack(side="bottom", fill="x", pady=(8, 0))
        box = tk.Frame(write, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                       highlightcolor=ACCENT)
        box.pack(fill="x")
        self.comment_entry = tk.Text(box, bg=SURFACE, fg=TEXT, insertbackground=TEXT, font=FONT_SMALL,
                                     wrap="word", relief="flat", borderwidth=0, highlightthickness=0,
                                     height=2, width=1, padx=8, pady=6, undo=True)
        self.comment_entry.pack(fill="x")
        for key in ("<Control-Return>", "<Control-KP_Enter>"):
            self.comment_entry.bind(key, lambda e: (self.send_comment(), "break")[1])
        send_row = tk.Frame(write, bg=SURFACE)
        send_row.pack(fill="x", pady=(6, 0))
        ttk.Button(send_row, text="Отправить", style="Accent.TButton", cursor="hand2",
                   command=self.send_comment).pack(side="right")
        tk.Label(send_row, text="Ctrl+Enter", bg=SURFACE, fg=DONE,
                 font=FONT_SMALL).pack(side="left")
        self.comments_area = ScrollArea(page, SURFACE)
        self.comments_area.pack(fill="both", expand=True)
        self.comments_area.inner.bind("<Configure>", self.wrap_comments, add="+")
        self.comment_labels = []
        self.extras_shown = None
        self.show_tab()

    # --- вкладки ---

    def show_tab(self):
        for key, page in self.pages.items():
            if key == self.tab.get():
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        # поля задачи (важность, срок…) — только с описанием: файлам и комментариям нужно место
        if self.tab.get() == "body":
            self.fields.pack(side="bottom", fill="x", after=self.actions)
            self.fields_line.pack(side="bottom", fill="x", pady=12, after=self.fields)
        else:
            self.fields.pack_forget()
            self.fields_line.pack_forget()
        if self.tab.get() == "comments":
            self.scroll_comments_down()

    def load_extras(self, task_id):
        """Перечитывает файлы и комментарии задачи; перерисовывает, только если они изменились."""
        files, comments = self.extras.attachments(task_id), self.extras.comments(task_id)
        self.tab_buttons["files"].configure(text=f"Файлы  {len(files)}" if files else "Файлы")
        self.tab_buttons["comments"].configure(
            text=f"Комментарии  {len(comments)}" if comments else "Комментарии")
        shown = (task_id, files, comments)
        if shown == self.extras_shown:
            return
        new_task = task_id != self.task_id
        self.task_id, self.extras_shown = task_id, shown
        if new_task:
            self.comment_entry.delete("1.0", "end")
        self.draw_files(files)
        self.draw_comments(comments)

    def draw_files(self, files):
        inner = self.files_area.inner
        for child in inner.winfo_children():
            child.destroy()
        ids = {f[0] for f in files}
        self.thumbs = {k: v for k, v in self.thumbs.items() if k[1] in ids}
        self.file_previews = {}  # (файл списка, id вложения) -> место превью — для фонового чтения
        source = self.extras.preview_source() if files else None
        self.file_labels = []
        if not files:
            tk.Label(inner, text="Файлов нет.\nДобавьте документ или картинку — или вставьте\n"
                                 "снимок экрана из буфера обмена (Ctrl+V).",
                     bg=SURFACE, fg=DONE, font=FONT_SMALL, justify="left", anchor="w").pack(
                fill="x", pady=4)
        for attachment_id, name, size, added_by, added_at in files:
            row = tk.Frame(inner, bg=SURFACE, cursor="hand2")
            row.pack(fill="x", pady=(0, 6))
            thumb = self.thumbnail(attachment_id, name, source) or self.type_icon(name)
            if thumb:
                preview = tk.Label(row, image=thumb, bg=SURFACE, width=56, height=56)
            else:
                ext = Path(name).suffix[1:].upper()[:4] or "FILE"
                preview = tk.Label(row, text=ext, bg=BG, fg=MUTED, font=FONT_SMALL_BOLD,
                                   width=5, height=2)
            preview.pack(side="left", padx=(0, 10))
            if source is not None:
                self.file_previews[(source[0], attachment_id)] = preview
            text = tk.Frame(row, bg=SURFACE)
            text.pack(side="left", fill="x", expand=True)
            label = tk.Label(text, text=name, bg=SURFACE, fg=TEXT, font=FONT_SMALL, anchor="w",
                             justify="left", wraplength=max(inner.winfo_width() - 80, 120))
            label.pack(fill="x")
            self.file_labels.append(label)
            info = [format_size(size), short_time(added_at)] + ([added_by] if added_by else [])
            tk.Label(text, text=" · ".join(info), bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                     anchor="w").pack(fill="x")
            bind_tree(row, "<Button-1>", lambda e, a=attachment_id: self.extras.open_file(a))
            bind_tree(row, "<Button-3>",
                      lambda e, a=attachment_id: self.extras.file_menu(a, e.x_root, e.y_root))
            bind_tree(row, "<Enter>", lambda e, r=row: paint_tree(r, HOVER))
            bind_tree(row, "<Leave>", lambda e, r=row: paint_tree(r, SURFACE))
        self.files_area.bind_wheel()
        self.files_area.canvas.yview_moveto(0)

    def thumbnail(self, attachment_id, name, source):
        """Превью картинки для списка файлов, если оно уже готово; иначе None (пока — значок типа
        файла). Картинка читается и уменьшается в фоне: в общем списке через VPN большой файл
        читается секундами, и окно бы «зависло». Готовое превью встаёт на место само.
        source — откуда читать (extras.preview_source()); None — общая папка сейчас недоступна,
        попробуем при следующей отрисовке."""
        if source is None or Path(name).suffix.lower() not in IMAGE_TYPES:
            return None
        key = (source[0], attachment_id)  # id вложений в разных списках совпадают
        if key not in self.thumbs:
            self.thumbs[key] = None  # уже читается (или не вышло) — второй раз не запускаем
            path, timeout = source
            in_background(self._root(),
                          lambda: small_picture(db.read_attachment(path, attachment_id, timeout)),
                          lambda image, error: self.thumbnail_ready(key, image, error))
        return self.thumbs[key]

    def thumbnail_ready(self, key, image, error=None):
        """Фоновое чтение закончилось: ставим превью на место значка (если файл ещё на экране).
        error — чтение сорвалось (файл занят, оборвалась связь): попробуем при следующей отрисовке."""
        if error is not None:
            self.thumbs.pop(key, None)
            return
        if image is None or not self.winfo_exists():
            return
        try:
            from PIL import ImageTk
            thumb = ImageTk.PhotoImage(image, master=self)
        except Exception:  # noqa: BLE001 — нет Pillow или картинка испорчена: остаётся значок
            return
        self.thumbs[key] = thumb
        label = self.file_previews.get(key)
        if label is not None and label.winfo_exists():
            label.configure(image=thumb, text="", bg=SURFACE, width=56, height=56)

    def type_icon(self, name):
        """Значок типа файла, как в Проводнике (или None — покажем плашку с расширением)."""
        ext = Path(file_name_for_disk(name)).suffix.lower()
        if ext not in self.type_icons:
            icon = file_type_icon(name)
            try:
                from PIL import ImageTk
                self.type_icons[ext] = ImageTk.PhotoImage(icon) if icon else None
            except Exception:  # noqa: BLE001 — нет Pillow: без значка
                self.type_icons[ext] = None
        return self.type_icons[ext]

    def paste(self):
        if self.task_id is not None:
            self.extras.paste_files(self.task_id)

    def draw_comments(self, comments):
        inner = self.comments_area.inner
        for child in inner.winfo_children():
            child.destroy()
        self.comment_labels = []
        if not comments:
            tk.Label(inner, text="Комментариев пока нет.", bg=SURFACE, fg=DONE,
                     font=FONT_SMALL, anchor="w").pack(fill="x", pady=4)
        for comment_id, author, text, created_at in comments:
            item = tk.Frame(inner, bg=SURFACE)
            item.pack(fill="x", pady=(0, 10))
            head = tk.Frame(item, bg=SURFACE)
            head.pack(fill="x")
            if author:
                tk.Label(head, text=author, bg=SURFACE, fg=TEXT, font=FONT_SMALL_BOLD).pack(
                    side="left", padx=(0, 6))
            tk.Label(head, text=short_time(created_at), bg=SURFACE, fg=MUTED,
                     font=FONT_SMALL).pack(side="left")
            label = tk.Label(item, text=text, bg=SURFACE, fg=TEXT, font=FONT_SMALL, anchor="w",
                             justify="left", wraplength=max(inner.winfo_width() - 8, 150))
            label.pack(fill="x")
            self.comment_labels.append(label)
            bind_tree(item, "<Button-3>", lambda e, c=comment_id, a=author, t=text:
                      self.extras.comment_menu(c, a, t, e.x_root, e.y_root))
        self.comments_area.bind_wheel()
        self.scroll_comments_down()

    def scroll_comments_down(self):
        """К последнему комментарию (сначала пусть Tk узнает новую высоту ленты)."""
        canvas = self.comments_area.canvas
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.yview_moveto(1)

    def wrap_comments(self, event):
        for label in self.comment_labels:
            label.configure(wraplength=max(event.width - 8, 150))

    def send_comment(self):
        text = self.comment_entry.get("1.0", "end").strip()
        if text and self.task_id is not None and self.extras.add_comment(self.task_id, text):
            self.comment_entry.delete("1.0", "end")

    def update_body_scroll(self, first, last):
        """Полоса прокрутки описания видна, только если текст не помещается."""
        needed = not (float(first) <= 0 and float(last) >= 1)
        if needed and not self.body_scroll.winfo_ismapped():
            self.body_scroll.pack(side="right", fill="y", before=self.body)
        elif not needed and self.body_scroll.winfo_ismapped():
            self.body_scroll.pack_forget()
        self.body_scroll.set(first, last)

    def show(self, number, title, body, status, status_color, overdue, done, priority_level_,
             priority_name, due, remind, created, author="", assignee="", updated="",
             urgent=False, important=False, from_mail=False, unit="", repeat=""):
        self.load_extras(number)
        shown = (number, title, body, status, status_color, overdue, done, priority_level_,
                 priority_name, due, remind, created, author, assignee, updated, urgent, important,
                 from_mail, unit, repeat)
        if shown == getattr(self, "shown", None):
            return  # ничего не изменилось — не трогаем, чтобы не сбросить прокрутку описания
        self.shown = shown
        self.number.configure(text=f"#{number}")
        if from_mail:
            self.from_mail.pack(side="left", padx=(12, 0), after=self.priority)
        else:
            self.from_mail.pack_forget()
        self.toggle_button.configure(text="↺  Вернуть в работу" if done else "✔  Выполнено")
        self.priority.configure(
            image=IMAGES.get(f"priority_{priority_level_}", ""),
            text=f"  {priority_name}" if priority_name else "Обычный приоритет",
        )
        color = DANGER if overdue else DONE if done else TEXT
        self.title.configure(text=title, fg=color)
        self.status.configure(text=status, fg=status_color)
        self.body.configure(state="normal")
        for table in self.body.winfo_children():  # таблицы прошлого описания (render_rich)
            table.destroy()
        self.body.delete("1.0", "end")
        if body.strip():
            # оформленным: жирный, списки, таблицы (значки **, «- », «| |» не видны)
            render_rich(self.body, body, wheel=lambda e: (
                self.body.yview_scroll(-2 if e.delta > 0 else 2, "units"), "break")[1])
        else:
            self.body.insert("1.0", "Описания нет.\nНажмите «Изменить», чтобы его добавить.",
                             "empty")
        self.body.configure(state="disabled")
        # важность и срочность отдельными строками; просроченная задача — срочная (как в матрице)
        self.values["important"].configure(text="Важно" if important else "Не важно",
                                           fg=TEXT if important else MUTED,
                                           font=FONT_SMALL_BOLD if important else FONT_SMALL)
        urgent_text = ("Срочно" if urgent else "Срочно — задача просрочена" if overdue
                       else "Не срочно")
        self.values["urgent"].configure(text=urgent_text,
                                        fg=DANGER if overdue else TEXT if urgent else MUTED,
                                        font=FONT_SMALL_BOLD if urgent or overdue else FONT_SMALL)
        self.values["due"].configure(text=due or "Не задан", fg=DANGER if overdue else TEXT)
        self.values["remind"].configure(text=remind or "Нет")
        self.values["created"].configure(text=created)
        # инициатор, исполнитель и «кто изменил» есть только в общих списках — в личных строк нет
        # бизнес-единица и повтор — только если указаны
        for key, value in (("repeat", repeat), ("author", author), ("assignee", assignee), ("unit", unit),
                           ("updated", updated)):
            self.values[key].configure(text=value)
            for widget in (self.values[key], self.captions[key]):
                widget.grid() if value else widget.grid_remove()


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


def collapse_button(parent, command, text="»"):
    """Кнопка «»» — свернуть правую панель в полоску («« — развернуть обратно)."""
    button = tk.Label(parent, text=text, bg=SURFACE, fg=MUTED, font=("Segoe UI", 13), cursor="hand2")
    button.bind("<Button-1>", lambda e: command())
    button.bind("<Enter>", lambda e: button.configure(fg=TEXT))
    button.bind("<Leave>", lambda e: button.configure(fg=MUTED))
    return button


class SideStrip(tk.Frame):
    """Свёрнутая правая панель: узкая полоска; щелчок по ней разворачивает панель."""

    WIDTH = 28

    def __init__(self, parent, on_expand):
        super().__init__(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=BORDER, width=self.WIDTH, cursor="hand2")
        self.pack_propagate(False)
        button = collapse_button(self, on_expand, text="«")
        button.pack(side="top", pady=(10, 0))
        self.bind("<Button-1>", lambda e: on_expand())
        self.bind("<Enter>", lambda e: button.configure(fg=TEXT))
        self.bind("<Leave>", lambda e: button.configure(fg=MUTED))


class Banner(tk.Frame):
    """Полоса-уведомление под заголовком окна: «нет связи с общей папкой», «связь
    восстановлена». Её видно всегда — в отличие от облачка Тоторо, которое прячется
    вместе с правой панелью и сменяется другими подсказками."""
    COLORS = {"alert": (ALERT_BG, ALERT_BORDER, DANGER), "good": (GOOD_BG, GOOD_BORDER, GOOD_TEXT),
              "wait": (GOOD_BG, GOOD_BORDER, GOOD_TEXT),
              "hint": (ACCENT_SOFT, ACCENT_SOFT_HOVER, ACCENT)}
    ICONS = {"alert": "⚠", "good": "✔", "wait": "⏳", "hint": "✨"}

    def __init__(self, parent, before):
        super().__init__(parent, highlightthickness=1, bd=0)
        self.before = before  # виджет, над которым показывается полоса
        self.icon = tk.Label(self, font=FONT_SMALL_BOLD, bd=0)
        self.icon.pack(side="left", padx=(12, 8), pady=8)
        # крестик и кнопка раскладываются раньше текста — длинный текст переносится, а не
        # выталкивает их за край окна
        self.close_x = tk.Label(self, text="✕", font=FONT_SMALL, fg=MUTED, cursor="hand2", bd=0)
        self.close_x.pack(side="right", padx=(8, 12))
        self.text = tk.Label(self, font=FONT_SMALL, fg=TEXT, bd=0, anchor="w", justify="left")
        self.text.pack(side="left", fill="x", expand=True, pady=8)
        self.close_x.bind("<Button-1>", lambda e: self.hide())
        self.action = tk.Label(self, font=FONT_SMALL_BOLD, fg=ACCENT, cursor="hand2", bd=0)
        self.action.bind("<Button-1>", lambda e: self.command and self.command())
        self.text.bind("<Configure>", lambda e: self.text.configure(wraplength=max(e.width, 200)))
        self.command = None
        self.hide_job = None
        self.kind = None  # что показано сейчас; None — полоса скрыта
        self.has_action = False

    def show(self, kind, text, action=None, command=None, hide_after=None):
        self.kind = kind
        bg, border, accent = self.COLORS[kind]
        self.configure(bg=bg, highlightbackground=border, highlightcolor=border)
        self.icon.configure(text=self.ICONS[kind], bg=bg, fg=accent)
        self.text.configure(text=text, bg=bg)
        self.close_x.configure(bg=bg)
        self.action.configure(bg=bg)
        self.command = command
        self.has_action = bool(action)
        if action:
            self.action.configure(text=action)
            self.action.pack(side="right", padx=(16, 4), before=self.text)
        else:
            self.action.pack_forget()
        if not self.winfo_ismapped():
            self.pack(fill="x", pady=(14, 0), before=self.before)
        if self.hide_job:
            self.after_cancel(self.hide_job)
            self.hide_job = None
        if hide_after:
            self.hide_job = self.after(hide_after, self.hide)

    def hide(self):
        if self.hide_job:
            self.after_cancel(self.hide_job)
            self.hide_job = None
        self.kind = None
        self.pack_forget()


class SidePanel(tk.Frame):
    """Правая панель: Тоторо, пока задача не выбрана, иначе — карточка задачи
    или форма её изменения. Кнопкой «»» (или Ctrl+B) сворачивается в полоску."""

    def __init__(self, parent, on_task_click, on_close, on_edit, on_email, on_toggle, on_delete, extras,
                 on_collapse):
        super().__init__(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=BORDER, width=PANEL_WIDTH)
        self.pack_propagate(False)  # ширину задаёт разделитель, а не длина текста
        self.on_collapse = on_collapse
        self.totoro = TotoroPanel(self, on_task_click)
        self.card = TaskCard(self, on_close, on_edit, on_email, on_toggle, on_delete, extras, on_collapse)
        # У Тоторо своей строки с кнопками нет — кнопка «»» лежит в правом верхнем углу
        self.totoro_collapse = collapse_button(self, on_collapse)
        self.editor = None  # форма задачи (с прокруткой и кнопками внизу), пока задача редактируется
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
        if mode == "totoro":
            self.totoro_collapse.place(relx=1, x=-8, y=4, anchor="ne")
            self.totoro_collapse.lift()
        else:
            self.totoro_collapse.place_forget()
        self.mode = mode

    def show_totoro(self):
        self.switch("totoro", self.totoro)

    def show_task(self, **task):
        self.card.show(**task)
        self.switch("task", self.card)

    def show_form(self, task, statuses, on_save, on_cancel, members=None, history=None, hints=False,
                  units=None):
        """Форма изменения задачи прямо в панели."""
        if self.editor is not None:
            self.editor.destroy()
        self.mode = None
        # Поля формы прокручиваются, а кнопки «Сохранить / Отмена» внизу видны всегда
        self.editor = tk.Frame(self, bg=SURFACE)
        footer = tk.Frame(self.editor, bg=SURFACE)
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg=BORDER, height=1).pack(fill="x")
        buttons = tk.Frame(footer, bg=SURFACE)
        buttons.pack(fill="x", padx=18, pady=10)
        area = ScrollArea(self.editor, SURFACE)
        area.pack(fill="both", expand=True)
        head = tk.Frame(area.inner, bg=SURFACE)
        head.pack(fill="x", padx=18, pady=(14, 10))
        tk.Label(head, text="Изменение задачи", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        close = tk.Label(head, text="✕", bg=SURFACE, fg=MUTED, font=FONT, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: on_cancel())
        collapse_button(head, self.on_collapse).pack(side="right", padx=(0, 10))
        self.form = TaskForm(area.inner, task, statuses, on_save, on_cancel, compact=True,
                             members=members, history=history, hints=hints, units=units)
        self.form.pack(fill="x", padx=18, pady=(0, 16))
        cancel = ttk.Button(buttons, text="Отмена", style="Soft.TButton", cursor="hand2",
                            command=on_cancel)
        cancel.pack(side="right")
        ttk.Button(buttons, text="Сохранить", style="Accent.TButton", cursor="hand2",
                   command=self.form.save).pack(side="right", padx=(0, 8))
        cancel.lift()  # Tab: сначала «Сохранить», потом «Отмена»
        area.bind_wheel()
        self.fit_description(area)
        self.switch("edit", self.editor)
        self.form.focus_title()

    DESC_MIN_LINES = 5  # меньше поле «Описание» не делаем: остальное — прокруткой формы

    def fit_description(self, area):
        """Поле «Описание» занимает всё свободное место панели до кнопок «Сохранить / Отмена»:
        высота подбирается при каждом изменении размера панели и содержимого формы (например,
        появились советы под заголовком). Места нет — остаётся DESC_MIN_LINES строк. Если
        высоту выбрали ручкой под полем, поле ровно такое (ниже — под формой пусто, выше — форма
        прокручивается); двойной щелчок по ручке возвращает подгонку."""
        form, line = self.form, tkfont.Font(font=FONT).metrics("linespace")
        job = [None]

        def fit():
            job[0] = None
            if self.form is not form or not area.winfo_exists():
                return  # форму уже закрыли или открыли другую
            free = area.canvas.winfo_height() - area.inner.winfo_reqheight()
            lines = int(form.desc.cget("height"))
            if form.desc_user:  # высоту выбрали ручкой — она и остаётся, хоть меньше, хоть больше
                wanted = form.desc_user
            else:
                wanted = max(self.DESC_MIN_LINES, lines + free // line)
            if wanted != lines:
                form.desc.configure(height=wanted)

        def later(event=None):
            if job[0] is None:  # одна подгонка на пачку событий
                job[0] = self.after_idle(fit)

        area.canvas.bind("<Configure>", later, add="+")
        area.inner.bind("<Configure>", later, add="+")


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
        opened = _MenuWindow.current
        if opened is not None:
            opened.close()
            if opened.opened_at == (x, y):  # повторное нажатие на ту же кнопку закрывает меню
                return
        _MenuWindow(root, self, x, y, right_aligned=right_aligned)


class _MenuWindow(tk.Toplevel):
    current = None  # открытое сейчас меню (верхнее окно)

    def __init__(self, master, menu, x, y, parent=None, right_aligned=False):
        self.opened_at = (x, y)
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
        # фокус ушёл из меню (и из подменю) в другое окно — закрываем
        self.bind("<FocusOut>", lambda e: self.top.after(120, self.top.check_focus))

        if parent is None:
            # Меню из окна-диалога захватывает щелчки (иначе диалог, который модальный, не дал
            # бы щёлкнуть по меню): щелчок мимо меню закрывает его, захват потом возвращаем
            # диалогу. Меню главного окна не захватывает — иначе Windows не даёт свернуть или
            # закрыть окно, пока меню открыто; оно закрывается, когда фокус уходит из меню.
            self.previous_grab = self.grab_current()
            self.previous_focus = self.focus_get()
            if self.previous_grab is not None:
                self.grab_set()
                self.bind("<ButtonPress>", self.click_outside)
            _MenuWindow.current = self
            for key, action in (("<Escape>", self.key_escape), ("<Up>", lambda: self.move(-1)),
                                ("<Down>", lambda: self.move(1)), ("<Return>", self.key_enter),
                                ("<Right>", self.key_right), ("<Left>", self.key_left)):
                self.bind(key, lambda e, a=action: a())
            self.focus_force()
            close_when_inactive(self, self.close)  # подменю закрываются вместе с ним

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
        if _MenuWindow.current is self:
            _MenuWindow.current = None
        self.close_child()
        try:
            self.grab_release()
            previous = getattr(self, "previous_grab", None)
            if previous is not None and previous.winfo_exists():
                previous.grab_set()  # диалог, из которого открыли меню, снова модальный
            focus = getattr(self, "previous_focus", None)
            if focus is not None and focus.winfo_exists():
                focus.focus_set()
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
        try:
            if not self.winfo_exists():
                return
            if focus is None or focus.winfo_toplevel() not in self.windows():
                self.close()
        except tk.TclError:
            pass

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


# Буфер обмена в полях ввода. В Tk сочетания Ctrl+C/V/X/A работают только в английской
# раскладке, а меню по правой кнопке у полей ввода нет вовсе — добавляем и то и другое.
EDIT_CLASSES = ("TEntry", "Entry", "Text")
EDIT_KEYCODES = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>", 65: "select_all",  # V C X A
                 90: "<<Undo>>", 89: "<<Redo>>"}                                     # Z Y
ENTRY_HISTORY = {}  # однострочное поле -> [значения, номер текущего]: в Tk у полей нет отмены
ENTRY_HISTORY_SIZE = 100


def select_all(widget):
    if isinstance(widget, tk.Text):
        widget.tag_add("sel", "1.0", "end-1c")
    else:
        widget.select_range(0, "end")
        widget.icursor("end")


def editable(widget):
    try:
        state = str(widget.cget("state"))
    except tk.TclError:
        return False
    return state == "normal" and not (isinstance(widget, ttk.Entry) and widget.instate(["readonly"]))


def has_selection(widget):
    if isinstance(widget, tk.Text):
        return bool(widget.tag_ranges("sel"))
    return widget.selection_present()


def clipboard_has_text(widget):
    try:
        return bool(widget.clipboard_get())
    except tk.TclError:
        return False


def edit_shortcut(event):
    """Ctrl+C/V/X/A в поле ввода — по физической клавише, при любой раскладке."""
    action = EDIT_KEYCODES.get(event.keycode)
    if action is None:
        return None
    if action == "select_all":  # в Tk Ctrl+A — «в начало строки»; в Windows привычнее «выделить всё»
        select_all(event.widget)
        return "break"
    if action in ("<<Undo>>", "<<Redo>>"):
        # отмена — сами при любой раскладке; Ctrl+Shift+Z — как Ctrl+Y, вернуть отменённое
        event.widget.event_generate("<<Redo>>" if event.state & 0x1 else action)
        return "break"
    if event.keysym.lower() in ("v", "c", "x"):
        return None  # английская раскладка — Tk справляется сам
    event.widget.event_generate(action)
    return "break"


def entry_remember(widget):
    """Запомнить значение однострочного поля для отмены (после набора, вставки, вырезания)."""
    try:
        value = widget.get()
    except tk.TclError:  # поле уже закрыто
        return
    states, pos = ENTRY_HISTORY.setdefault(str(widget), [[value], 0])
    if states[pos] == value:
        return
    del states[pos + 1:]  # после отмены набрали новое — «вернуть» больше нечего
    states.append(value)
    del states[:-ENTRY_HISTORY_SIZE]
    ENTRY_HISTORY[str(widget)][1] = len(states) - 1


def entry_focus(event):
    """Поле получило фокус: его значение (в том числе вписанное программой) — начало истории."""
    entry_remember(event.widget)


def entry_undo(event, step=-1):
    """Ctrl+Z / Ctrl+Y в однострочном поле: прошлое или отменённое значение."""
    widget = event.widget
    if not editable(widget):
        return "break"
    entry_remember(widget)  # набранное перед Ctrl+Z тоже можно вернуть
    states, pos = ENTRY_HISTORY[str(widget)]
    if 0 <= pos + step < len(states):
        ENTRY_HISTORY[str(widget)][1] = pos + step
        widget.delete(0, "end")
        widget.insert(0, states[pos + step])
        widget.icursor("end")
    return "break"


def word_size(text, forward):
    """Сколько знаков стирает Ctrl+Backspace (назад) или Ctrl+Delete (вперёд): пробелы
    и слово целиком — или подряд идущие знаки препинания."""
    text = text if forward else text[::-1]
    size = re.match(r"\s*(\w+|[^\w\s]+)?", text).end()
    return size or min(len(text), 1)


def delete_word(event, forward=False):
    widget = event.widget
    if not editable(widget):
        return "break"
    if has_selection(widget):
        widget.delete("sel.first", "sel.last")
    elif isinstance(widget, tk.Text):
        if forward:
            size = word_size(widget.get("insert", "insert lineend"), True) or 1  # в конце строки — склеить
            widget.delete("insert", f"insert+{size}c")
        else:
            size = word_size(widget.get("insert linestart", "insert"), False) or 1
            widget.delete(f"insert-{size}c", "insert")
    else:
        pos, value = widget.index("insert"), widget.get()
        if forward:
            widget.delete(pos, pos + word_size(value[pos:], True))
        else:
            size = word_size(value[:pos], False)
            widget.delete(pos - size, pos)
    return "break"


def edit_menu(event):
    """Меню по правой кнопке в поле ввода: вырезать, копировать, вставить, выделить всё."""
    w = event.widget
    w.focus_set()
    can_edit = editable(w)
    (PopupMenu()
     .command("Отменить", lambda: w.event_generate("<<Undo>>"), accel="Ctrl+Z", enabled=can_edit)
     .separator()
     .command("Вырезать", lambda: w.event_generate("<<Cut>>"), accel="Ctrl+X",
              enabled=can_edit and has_selection(w))
     .command("Копировать", lambda: w.event_generate("<<Copy>>"), accel="Ctrl+C",
              enabled=has_selection(w))
     .command("Вставить", lambda: w.event_generate("<<Paste>>"), accel="Ctrl+V",
              enabled=can_edit and clipboard_has_text(w))
     .separator()
     .command("Выделить всё", lambda: select_all(w), accel="Ctrl+A")
     ).popup(w.winfo_toplevel(), event.x_root, event.y_root)
    return "break"


def setup_text_editing(root):
    for cls in EDIT_CLASSES:
        root.bind_class(cls, "<Control-KeyPress>", edit_shortcut, add="+")
        root.bind_class(cls, "<Button-3>", edit_menu, add="+")
        # Ctrl+Backspace / Ctrl+Delete — стереть слово (Tk стирал бы один знак)
        root.bind_class(cls, "<Control-BackSpace>", delete_word)
        root.bind_class(cls, "<Control-Delete>", lambda e: delete_word(e, forward=True))
    for cls in ("TEntry", "Entry"):  # у многострочных полей (Text) отмена своя, undo=True
        root.bind_class(cls, "<<Undo>>", entry_undo)
        root.bind_class(cls, "<<Redo>>", lambda e: entry_undo(e, step=1))
        root.bind_class(cls, "<FocusIn>", entry_focus, add="+")
        for sequence in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
            root.bind_class(cls, sequence, lambda e: root.after_idle(entry_remember, e.widget),
                            add="+")
        root.bind_class(cls, "<Destroy>", lambda e: ENTRY_HISTORY.pop(str(e.widget), None), add="+")


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
        self.buttons = buttons
        # главная кнопка слева, «Отмена» справа (pack справа налево — сначала крайняя)
        self.cancel_button = ttk.Button(buttons, text="Отмена", style="Soft.TButton",
                                        command=self.destroy)
        self.cancel_button.pack(side="right")
        self.ok_button = ttk.Button(buttons, text=ok_text, style="Accent.TButton", command=self.ok)
        self.ok_button.pack(side="right", padx=(0, 8))
        self.cancel_button.lift()  # Tab: сначала главная кнопка, потом «Отмена»
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


class ConflictDialog(ModernDialog):
    """Задачу изменил другой участник, пока вы её правили: чей вариант оставить?"""

    def __init__(self, parent, title, who, when, changed, can_return):
        super().__init__(parent, "Задачу изменили", "Задачу уже изменили", "Сохранить мой вариант")
        what = ", ".join(changed) if changed else "задачу"
        text = (f"Пока вы правили «{title}», {who}{' в ' + when if when else ''} изменил(а): "
                f"{what}.\n\n«Сохранить мой вариант» — ваши правки запишутся поверх.\n"
                f"«Оставить вариант {who}» — ваши правки не сохранятся.")
        if can_return:
            text += "\n«Вернуться к правке» — продолжить редактировать (форма останется открытой)."
        tk.Label(self.content, text=text, bg=SURFACE, fg=TEXT, font=FONT_SMALL, justify="left",
                 wraplength=440).pack(anchor="w")
        # кнопки: [Сохранить мой] [Оставить их] [Вернуться к правке]
        self.cancel_button.configure(text=f"Оставить вариант {who}", command=self.theirs)
        if can_return:
            self.ok_button.pack_forget()
            self.cancel_button.pack_forget()
            back = ttk.Button(self.buttons, text="Вернуться к правке", style="Soft.TButton",
                              command=self.destroy)
            back.pack(side="right")
            self.cancel_button.pack(side="right", padx=(0, 8))
            self.ok_button.pack(side="right", padx=(0, 8))
            back.lift()
        self.result = "back" if can_return else "theirs"

    def ok(self):
        self.result = "mine"
        self.destroy()

    def theirs(self):
        self.result = "theirs"
        self.destroy()


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
    "author": "Инициатор (в общих списках)",
    "assignee": "Исполнитель (в общих списках)",
    "unit": "Бизнес-единица",
}
DEFAULT_CARD_FIELDS = ["number", "priority", "body", "due", "author", "assignee"]


class Toggle(tk.Canvas):
    """Переключатель «вкл/выкл» (как в Windows 11 и телефонах) вместо галочки."""

    W, H = 40, 22

    def __init__(self, parent, variable, command=None, bg=SURFACE):
        super().__init__(parent, width=self.W, height=self.H, bg=bg, highlightthickness=0,
                         cursor="hand2", takefocus=True)
        self.variable, self.command = variable, command
        self.bind("<Button-1>", lambda e: self.flip())
        self.bind("<space>", lambda e: self.flip())
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())
        variable.trace_add("write", lambda *a: self.draw())
        self.draw()

    def flip(self):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def draw(self):
        self.delete("all")
        on = self.variable.get()
        focus = self.focus_get() is self
        round_rect(self, 1, 1, self.W - 1, self.H - 1, (self.H - 2) // 2,
                   fill=ACCENT if on else DASHED, outline=ACCENT_HOVER if focus else "")
        x = self.W - self.H // 2 - 1 if on else self.H // 2
        self.create_oval(x - 7, self.H // 2 - 7, x + 7, self.H // 2 + 7, fill="white", outline="")


class SettingsDialog(tk.Toplevel):
    """Настройки в стиле Windows 11: слева разделы, справа — карточки с настройками.
    result — dict(start_mode, card_fields, update_auto, shared_folder, user_name) или None."""

    # Значки — из шрифта Windows «Segoe MDL2 Assets» (так нарисованы значки в настройках Windows)
    ICON_FONT = ("Segoe MDL2 Assets", 12)
    PAGES = [("general", "", "Общие"), ("board", "", "Доска"),
             ("sharing", "", "Совместная работа"), ("updates", "", "Обновления")]

    def __init__(self, parent, start_mode, card_fields, update_auto, shared_folder="", user_name="",
                 team_status=None, page="general", check_folder=None, check_update=None,
                 animate=True, theme="light", tour=True, tray_on=False, smart_on=True):
        super().__init__(parent)
        self.result = None
        self.update_found = None  # найденная новая версия: откроется после закрытия настроек
        self.check_folder, self.check_update = check_folder, check_update
        self.title("Настройки")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)

        self.start_mode = tk.StringVar(value=start_mode)
        self.fields = {key: tk.BooleanVar(value=key in card_fields) for key in CARD_FIELDS}
        self.update_auto = tk.BooleanVar(value=update_auto)
        self.animate = tk.BooleanVar(value=animate)
        self.theme = tk.StringVar(value=theme)
        self.tour = tk.BooleanVar(value=tour)
        self.tray_on = tk.BooleanVar(value=tray_on)
        self.smart_on = tk.BooleanVar(value=smart_on)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        nav = tk.Frame(body, bg=BG, width=200)
        nav.pack(side="left", fill="y", padx=(14, 0), pady=16)
        nav.pack_propagate(False)
        tk.Label(nav, text="Настройки", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 15)).pack(
            anchor="w", padx=10, pady=(0, 14))
        self.nav_items = {}
        for key, icon, label in self.PAGES:
            item = tk.Frame(nav, bg=BG, cursor="hand2", padx=10, pady=7)
            item.pack(fill="x", pady=1)
            mark = tk.Label(item, text=icon, bg=BG, fg=MUTED, font=self.ICON_FONT, width=2)
            mark.pack(side="left")
            text = tk.Label(item, text=label, bg=BG, fg=TEXT, font=FONT_SMALL)
            text.pack(side="left", padx=(8, 0))
            for widget in (item, mark, text):
                widget.bind("<Button-1>", lambda e, k=key: self.show_page(k))
                widget.bind("<Enter>", lambda e, k=key: self.paint_nav(k, hover=True))
                widget.bind("<Leave>", lambda e, k=key: self.paint_nav(k))
            self.nav_items[key] = (item, mark, text)

        self.content = tk.Frame(body, bg=BG, width=560, height=560)
        self.content.pack(side="left", fill="both", expand=True, padx=(10, 22), pady=16)
        self.content.pack_propagate(False)
        self.pages = {
            "general": self.page_general(),
            "board": self.page_board(),
            "sharing": self.page_sharing(shared_folder, user_name, team_status),
            "updates": self.page_updates(),
        }

        bar = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        bar.pack(fill="x", side="bottom")
        cancel = ttk.Button(bar, text="Отмена", style="Soft.TButton", command=self.destroy)
        cancel.pack(side="right", padx=(0, 18), pady=12)
        ttk.Button(bar, text="Сохранить", style="Accent.TButton", command=self.ok).pack(
            side="right", padx=(0, 8), pady=12)
        cancel.lift()  # Tab: сначала «Сохранить», потом «Отмена»

        self.page = None
        self.show_page(page)
        self.bind("<Escape>", lambda e: self.destroy())

    # --- оформление ---

    def paint_nav(self, key, hover=False):
        item, mark, text = self.nav_items[key]
        if key == self.page:
            bg, fg, font = ACCENT_SOFT, ACCENT, ("Segoe UI Semibold", 10)
        else:
            bg, fg, font = (HOVER if hover else BG), TEXT, FONT_SMALL
        for widget in (item, mark, text):
            widget.configure(bg=bg)
        mark.configure(fg=ACCENT if key == self.page else MUTED)
        text.configure(fg=fg, font=font)

    def show_page(self, key):
        if self.page:
            self.pages[self.page].pack_forget()
        self.page = key
        self.pages[key].pack(fill="both", expand=True)
        for k in self.nav_items:
            self.paint_nav(k)

    def new_page(self, title, hint):
        page = tk.Frame(self.content, bg=BG)
        tk.Label(page, text=title, bg=BG, fg=TEXT, font=("Segoe UI Semibold", 13)).pack(anchor="w")
        tk.Label(page, text=hint, bg=BG, fg=MUTED, font=FONT_SMALL, wraplength=540,
                 justify="left").pack(anchor="w", pady=(2, 12))
        return page

    def card(self, parent, **pack):
        frame = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="x", **pack)
        return frame

    def row(self, card, title, hint="", first=False):
        """Строка карточки: название и пояснение слева; возвращает фрейм для элемента справа."""
        if not first:
            tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=14)
        line = tk.Frame(card, bg=SURFACE)
        line.pack(fill="x", padx=14, pady=9)
        text = tk.Frame(line, bg=SURFACE)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, bg=SURFACE, fg=TEXT, font=FONT_SMALL).pack(anchor="w")
        if hint:
            tk.Label(text, text=hint, bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), wraplength=360,
                     justify="left").pack(anchor="w")
        control = tk.Frame(line, bg=SURFACE)
        control.pack(side="right")
        return control

    # --- страницы ---

    def page_general(self):
        page = self.new_page("Общие", "Окно программы, тема оформления и Тоторо.")
        card = self.card(page)
        control = self.row(card, "Запуск программы", "Каким открывать окно ToDoro при запуске.",
                           first=True)
        segments = ttk.Frame(control, style="Segments.TFrame", padding=3)
        segments.pack()
        for value, label in (("window", "Окном"), ("maximized", "На весь экран")):
            ttk.Radiobutton(segments, text=label, value=value, variable=self.start_mode,
                            style="Segment.TRadiobutton", cursor="hand2").pack(side="left")
        control = self.row(card, "Тема оформления", "Сменится после перезапуска программы.")
        segments = ttk.Frame(control, style="Segments.TFrame", padding=3)
        segments.pack()
        for value, label in THEMES.items():
            ttk.Radiobutton(segments, text=label, value=value, variable=self.theme,
                            style="Segment.TRadiobutton", cursor="hand2").pack(side="left")
        control = self.row(card, "Оживлять Тоторо",
                           "Тоторо дышит, моргает, радуется, волнуется о просроченных задачах "
                           "и спит, когда всё сделано.")
        Toggle(control, self.animate).pack()
        control = self.row(card, "Ознакомительный тур при запуске",
                           "Показывать при запуске программы тур по её главным возможностям. "
                           "Пройти его в любой момент: «☰ Меню» → «Ознакомительный тур».")
        Toggle(control, self.tour).pack()
        control = self.row(card, "Умные подсказки",
                           "Варианты названия из ваших прошлых задач, срок из слов «завтра в 10», "
                           "приоритет и шаги похожих задач. Работают без интернета.")
        Toggle(control, self.smart_on).pack()
        control = self.row(card, "Значок в трее при входе в Windows",
                           f"Значок возле часов: {OUTLOOK_HOTKEY_NAME} в Outlook делает задачу из письма, "
                           f"{SNIP_HOTKEY_NAME} — задачу со снимка экрана, даже если ToDoro не открыт.")
        Toggle(control, self.tray_on).pack()
        return page

    def page_board(self):
        page = self.new_page("Доска", "Что показывать на карточках задач (на доске и в матрице). "
                                      "Заголовок виден всегда.")
        columns = tk.Frame(page, bg=BG)
        columns.pack(fill="both", expand=True)
        card = self.card(columns, side="left", anchor="n")
        card.pack_configure(fill="none")
        for i, (key, label) in enumerate(CARD_FIELDS.items()):
            control = self.row(card, label.replace(" (в общих списках)", ""),
                               "только в общих списках" if key in ("author", "assignee") else "",
                               first=i == 0)
            Toggle(control, self.fields[key], command=self.update_preview).pack()
        # Образец карточки справа — сразу видно, как будет выглядеть
        side = tk.Frame(columns, bg=BG)
        side.pack(side="left", anchor="n", padx=(18, 0))
        tk.Label(side, text="Образец", bg=BG, fg=MUTED, font=FONT_SMALL).pack(anchor="w", pady=(0, 6))
        self.preview = tk.Frame(side, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                                width=210)
        self.preview.pack(anchor="w")
        self.update_preview()
        return page

    def update_preview(self):
        for child in self.preview.winfo_children():
            child.destroy()
        on = {key for key, var in self.fields.items() if var.get()}
        holder = tk.Frame(self.preview, bg=SURFACE)
        holder.pack(fill="both")
        tk.Frame(holder, bg=LANE_COLORS[0][1], width=4).pack(side="left", fill="y")
        inner = tk.Frame(holder, bg=SURFACE, padx=12, pady=10)
        inner.pack(side="left", fill="both")
        top = tk.Frame(inner, bg=SURFACE)
        top.pack(fill="x")
        if "priority" in on and "priority_1" in IMAGES:
            tk.Label(top, image=IMAGES["priority_1"], bg=SURFACE).pack(side="left", padx=(0, 6))
        tk.Label(top, text="Сдать отчёт", bg=SURFACE, fg=TEXT, font=FONT_BOLD).pack(side="left")
        if "number" in on:
            tk.Label(top, text="#12", bg=SURFACE, fg=DONE, font=FONT_SMALL).pack(side="right",
                                                                               padx=(16, 0))
        if "body" in on:
            tk.Label(inner, text="Свести продажи по регионам\nи добавить графики…", bg=SURFACE,
                     fg=MUTED, font=FONT_SMALL, justify="left").pack(anchor="w", pady=(4, 0))
        extra = [text for key, text in (("due", "Срок 17.10 18:00"), ("remind", "Напомнить за 1 час"),
                                        ("created", "Создана 16.10"), ("unit", "Розница"),
                                        ("author", "Инициатор Мария"))
                 if key in on]
        if "assignee" in on:
            extra.insert(0, "Исполнитель Олег")
        if extra:
            tk.Label(inner, text="\n".join(extra), bg=SURFACE, fg=MUTED, font=("Segoe UI", 9),
                     justify="left").pack(anchor="w", pady=(6, 0))

    def page_sharing(self, shared_folder, user_name, team_status):
        page = self.new_page("Совместная работа",
                             "Общие списки хранятся в сетевой папке, которую видят все участники. "
                             "Укажите её и своё имя — его увидят другие.")
        card = self.card(page)
        status = tk.Frame(card, bg=SURFACE)
        status.pack(fill="x", padx=14, pady=(12, 10))
        self.status_dot = tk.Label(status, text="●", bg=SURFACE, font=("Segoe UI", 14))
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(status, bg=SURFACE, fg=TEXT, font=FONT_SMALL, wraplength=470,
                                    justify="left", anchor="w")
        self.status_text.pack(side="left", padx=(6, 0), fill="x")
        self.set_status(*(team_status or ("off", "Не подключено")))

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=14)
        form = tk.Frame(card, bg=SURFACE)
        form.pack(fill="x", padx=14, pady=12)
        form.columnconfigure(1, weight=1)
        tk.Label(form, text="Общая папка", bg=SURFACE, fg=TEXT, font=FONT_SMALL).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.folder = ttk.Entry(form, font=FONT_SMALL)
        self.folder.insert(0, shared_folder)
        self.folder.xview_moveto(0)
        self.folder.grid(row=0, column=1, sticky="we")
        ttk.Button(form, text="Обзор…", style="Soft.TButton", cursor="hand2",
                   command=self.browse).grid(row=0, column=2, padx=(6, 0))
        tk.Label(form, text="Например: \\\\сервер\\общая папка", bg=SURFACE, fg=DONE,
                 font=("Segoe UI", 9)).grid(row=1, column=1, sticky="w", pady=(2, 8))
        tk.Label(form, text="Ваше имя", bg=SURFACE, fg=TEXT, font=FONT_SMALL).grid(
            row=2, column=0, sticky="w", padx=(0, 12))
        self.name = ttk.Entry(form, font=FONT_SMALL)
        self.name.insert(0, user_name)
        self.name.grid(row=2, column=1, sticky="we")

        buttons = tk.Frame(page, bg=BG)
        buttons.pack(fill="x", pady=(10, 0))
        self.check_button = ttk.Button(buttons, text="Проверить подключение", style="TButton",
                                       cursor="hand2", command=self.run_folder_check)
        self.check_button.pack(side="left")
        if not self.check_folder:
            self.check_button.state(["disabled"])
        return page

    def set_status(self, kind, text):
        color = {"ok": OK_DOT, "error": DANGER, "busy": BUSY}.get(kind, DONE)
        self.status_dot.configure(fg=color)
        self.status_text.configure(text=text)

    def run_folder_check(self):
        folder = self.folder.get().strip()
        if not folder:
            self.set_status("error", "Укажите общую папку.")
            return
        self.set_status("busy", "Проверяю…")
        self.check_button.state(["disabled"])

        def done(status):
            if self.winfo_exists():
                self.check_button.state(["!disabled"])
                self.set_status(*status)
        self.check_folder(folder, done)

    def page_updates(self):
        page = self.new_page("Обновления", "ToDoro сам узнаёт о новых версиях и предлагает "
                             "обновиться — задачи при этом сохраняются.")
        card = self.card(page)
        control = self.row(card, f"Установлена версия {APP_VERSION}", "", first=True)
        self.update_button = ttk.Button(control, text="Проверить сейчас", style="Soft.TButton",
                                        cursor="hand2", command=self.run_update_check)
        self.update_button.pack()
        if not self.check_update:
            self.update_button.state(["disabled"])
        control = self.row(card, "Проверять обновления автоматически",
                           "При запуске программы, не чаще раза в день.")
        Toggle(control, self.update_auto).pack()
        self.update_text = tk.Label(page, text="", bg=BG, fg=MUTED, font=FONT_SMALL, wraplength=540,
                                    justify="left")
        self.update_text.pack(anchor="w", pady=(10, 0))
        return page

    def run_update_check(self):
        self.update_button.state(["disabled"])
        self.update_text.configure(text="Проверяю…", fg=MUTED)

        def done(text, release=None):
            if not self.winfo_exists():
                return
            self.update_button.state(["!disabled"])
            self.update_text.configure(text=text, fg=ACCENT if release else MUTED)
            self.update_found = release
        self.check_update(done)

    # --- кнопки ---

    def browse(self):
        folder = filedialog.askdirectory(parent=self, title="Общая папка для списков",
                                         initialdir=self.folder.get() or None)
        if folder:
            self.folder.delete(0, "end")
            self.folder.insert(0, str(Path(folder)))

    def ok(self):
        folder, name = self.folder.get().strip(), " ".join(self.name.get().split())
        if folder and not name:
            self.show_page("sharing")
            ui.showwarning("Настройки", "Укажите своё имя — по нему другие участники "
                                   "увидят, кто создал или изменил задачу.", parent=self)
            self.name.focus_set()
            return
        self.result = dict(start_mode=self.start_mode.get(),
                           card_fields=[key for key, var in self.fields.items() if var.get()],
                           update_auto=self.update_auto.get(), shared_folder=folder, user_name=name,
                           animate=self.animate.get(), theme=self.theme.get(),
                           tour=self.tour.get(), tray=self.tray_on.get(),
                           smart=self.smart_on.get())
        self.destroy()

    def show(self):
        center_on_screen(self)
        self.grab_set()
        self.focus_force()
        self.wait_window()
        return self.result


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
            ui.showwarning(self.title(), "Название не может быть пустым.", parent=self)
            return
        self.result = name
        self.destroy()


class NewListDialog(NameDialog):
    """Новый список: название и где он живёт — только у меня или общий для команды.
    result — (название, общий ли) или None."""

    def __init__(self, parent, can_share):
        super().__init__(parent, "Новый список", "Новый список", "",
                         "Например: «Команда», «Дом», «Проект Альфа».", "Создать")
        self.shared = tk.BooleanVar(value=False)
        box = tk.Frame(self.content, bg=SURFACE)
        box.pack(anchor="w", pady=(14, 0))
        ttk.Radiobutton(box, text="Только у меня", value=False, variable=self.shared,
                        style="Card.TRadiobutton").pack(anchor="w", pady=2)
        shared = ttk.Radiobutton(box, text="Общий — видят и меняют все участники", value=True,
                                 variable=self.shared, style="Card.TRadiobutton")
        shared.pack(anchor="w", pady=2)
        if not can_share:
            shared.state(["disabled"])
            tk.Label(box, text="Чтобы создавать общие списки, укажите общую папку:\n"
                     "☰ Меню → Настройки → Совместная работа.", bg=SURFACE, fg=MUTED,
                     font=FONT_SMALL, justify="left").pack(anchor="w", padx=(22, 0))

    def ok(self):
        super().ok()
        if self.result:
            self.result = (self.result, self.shared.get())


def close_quietly(conns):
    """Закрывает соединения с базами (вызывается в фоновом потоке)."""
    for conn in conns:
        try:
            conn.close()
        except sqlite3.Error:
            pass


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


def open_team(folder, user):
    """Открывает общую папку и отмечает в ней участника. Можно звать из фонового потока:
    соединение team.Team разрешено передавать между потоками."""
    group = team.Team(folder)
    try:
        group.touch_member(user)
    except BaseException:
        group.close()
        raise
    return group


class UnitDeleteDialog(ModernDialog):
    """Удаление бизнес-единицы, которая уже стоит у задач: что поставить этим задачам."""

    def __init__(self, parent, name, count, others):
        super().__init__(parent, "Удалить бизнес-единицу", "Удалить бизнес-единицу", "Удалить")
        tk.Label(self.content, text=f"«{name}» указана у задач: {count}. Что поставить им вместо неё?",
                 bg=SURFACE, fg=TEXT, font=FONT_SMALL, justify="left", wraplength=380).pack(anchor="w")
        self.choices = {NO_UNIT: None, **{n: uid for uid, n in others}}
        self.choice = ttk.Combobox(self.content, values=list(self.choices), state="readonly", width=34,
                                   font=FONT)
        self.choice.set(NO_UNIT)
        self.choice.pack(fill="x", pady=(10, 0))

    def ok(self):
        self.result = ("ok", self.choices[self.choice.get()])
        self.destroy()


class UnitsDialog(tk.Toplevel):
    """Справочник бизнес-единиц списка: добавить, переименовать, удалить, поменять порядок,
    взять из другого списка. Изменения записываются сразу. units_from(id списка) — соединение
    с другим списком (может бросить sqlite3.Error или OSError, если список недоступен)."""

    def __init__(self, parent, conn, list_name, by, other_lists, units_from):
        super().__init__(parent)
        self.conn, self.by, self.other_lists, self.units_from = conn, by, other_lists, units_from
        self.title("Бизнес-единицы")
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        body = tk.Frame(self, bg=SURFACE, padx=26, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Бизнес-единицы", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI Semibold", 14)).pack(anchor="w")
        tk.Label(body, text=f"Справочник списка «{list_name}». Бизнес-единицу задачи выбирают\n"
                            "в форме задачи; поле необязательное.",
                 bg=SURFACE, fg=MUTED, font=FONT_SMALL, justify="left").pack(anchor="w", pady=(2, 12))
        row = tk.Frame(body, bg=SURFACE)
        row.pack(fill="both", expand=True)
        box = tk.Frame(row, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        box.pack(side="left", fill="both", expand=True)
        self.listbox = tk.Listbox(box, font=FONT, width=30, height=10, bg=SURFACE, fg=TEXT,
                                  selectbackground=ACCENT, selectforeground="white", relief="flat",
                                  borderwidth=0, highlightthickness=0, activestyle="none",
                                  exportselection=False)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.listbox.bind("<Double-Button-1>", lambda e: self.safely(self.rename)())
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.update_buttons())
        self.listbox.bind("<Delete>", lambda e: self.safely(self.delete)())
        actions = tk.Frame(row, bg=SURFACE)
        actions.pack(side="left", fill="y", padx=(12, 0))
        self.buttons = {}
        for key, text, command in (("add", "Добавить…", self.add), ("rename", "Переименовать…", self.rename),
                                   ("delete", "Удалить…", self.delete), ("up", "↑  Выше", lambda: self.move(-1)),
                                   ("down", "↓  Ниже", lambda: self.move(1))):
            command = self.safely(command)
            button = ttk.Button(actions, text=text, style="Soft.TButton", command=command, width=18)
            button.pack(fill="x", pady=(0, 6))
            self.buttons[key] = button
        self.buttons["copy"] = ttk.Button(actions, text="Взять из списка…", style="Soft.TButton",
                                          command=self.copy_menu, width=18)
        self.buttons["copy"].pack(fill="x", pady=(12, 0))
        if not other_lists:
            self.buttons["copy"].state(["disabled"])
        bottom = tk.Frame(body, bg=SURFACE)
        bottom.pack(fill="x", pady=(18, 0))
        ttk.Button(bottom, text="Закрыть", style="Accent.TButton", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self.load()

    def show(self):
        center_on_screen(self)
        self.grab_set()
        self.focus_force()
        self.listbox.focus_set()
        self.wait_window()

    def safely(self, action):
        """Файл списка стал недоступен (общая папка, VPN) — сообщаем и закрываем окно,
        а не оставляем кнопки, которые молча перестали работать."""
        def run():
            try:
                action()
            except sqlite3.Error as error:
                ui.showwarning("Бизнес-единицы", "Не удалось изменить справочник — файл списка "
                               f"сейчас недоступен.\n\nПодробности: {error}", parent=self)
                self.destroy()
        return run

    def load(self, select_id=None):
        self.units = db.list_units(self.conn)
        self.listbox.delete(0, "end")
        for _, name in self.units:
            self.listbox.insert("end", name)
        index = next((i for i, (uid, _) in enumerate(self.units) if uid == select_id), None)
        if index is not None:
            self.listbox.selection_set(index)
            self.listbox.see(index)
        self.update_buttons()

    def selected(self):
        chosen = self.listbox.curselection()
        return self.units[chosen[0]] if chosen else None

    def update_buttons(self):
        chosen = self.listbox.curselection()
        for key in ("rename", "delete", "up", "down"):
            self.buttons[key].state(["!disabled"] if chosen else ["disabled"])
        if chosen:
            if chosen[0] == 0:
                self.buttons["up"].state(["disabled"])
            if chosen[0] == len(self.units) - 1:
                self.buttons["down"].state(["disabled"])

    def ask_name(self, title, value="", unit_id=None):
        """Название новой или переименованной единицы; повтор названия не допускаем."""
        while True:
            name = NameDialog(self, title, title, value=value, ok_text="Сохранить").show()
            if not name:
                return None
            if db.unit_key(name) == db.unit_key(NO_UNIT):
                ui.showwarning(title, f"Название «{NO_UNIT}» занято: так в форме обозначается задача "
                                      "без бизнес-единицы.", parent=self)
                continue
            same = db.unit_by_name(self.conn, name)
            if same is None or same == unit_id:
                return name
            ui.showwarning(title, f"Бизнес-единица «{name}» уже есть в справочнике.", parent=self)
            value = name

    def add(self):
        name = self.ask_name("Новая бизнес-единица")
        if name:
            self.load(select_id=db.add_unit(self.conn, name))

    def rename(self):
        unit = self.selected()
        if unit is None:
            return
        name = self.ask_name("Переименовать бизнес-единицу", unit[1], unit[0])
        if name and name != unit[1]:
            db.rename_unit(self.conn, unit[0], name)
            self.load(select_id=unit[0])

    def delete(self):
        unit = self.selected()
        if unit is None:
            return
        count = db.count_in_unit(self.conn, unit[0])
        if count:
            answer = UnitDeleteDialog(self, unit[1], count,
                                      [u for u in self.units if u[0] != unit[0]]).show()
            if not answer:
                return
            move_to = answer[1]
        elif ui.askyesno("Удалить бизнес-единицу", f"Удалить «{unit[1]}» из справочника?", parent=self):
            move_to = None
        else:
            return
        db.delete_unit(self.conn, unit[0], move_to, by=self.by)
        self.load()

    def move(self, step):
        unit = self.selected()
        if unit is not None:
            db.move_unit(self.conn, unit[0], step)
            self.load(select_id=unit[0])

    def copy_menu(self):
        menu = PopupMenu()
        for list_id, name in self.other_lists:
            menu.command(name, lambda i=list_id, n=name: self.copy_from(i, n))
        button = self.buttons["copy"]
        menu.popup(self, button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def copy_from(self, list_id, name):
        """Добавляет единицы из справочника другого списка (те, которых здесь ещё нет)."""
        try:
            added = db.copy_units(self.units_from(list_id), self.conn)
        except (sqlite3.Error, OSError) as error:
            ui.showwarning("Бизнес-единицы", f"Не удалось прочитать список «{name}»:\n{error_text(error)}", parent=self)
            return
        self.load()
        ui.showinfo("Бизнес-единицы", f"Добавлено из списка «{name}»: {added}." if added
                    else f"Все бизнес-единицы списка «{name}» здесь уже есть.", parent=self)


class PhoneDialog(tk.Toplevel):
    """«Подключить телефон»: QR-код с адресом компьютера и ключом для приложения на телефоне.
    Сам отвечает телефону значок ToDoro в трее (phone.py) — окно только включает связь,
    показывает код и проверяет, что значок отвечает."""
    PING_EVERY_MS = 1500

    def __init__(self, parent, prefs):
        super().__init__(parent)
        self.prefs = prefs
        self.title("Подключить телефон")
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        self.body = tk.Frame(self, bg=SURFACE, padx=28, pady=22)
        self.body.pack(fill="both")
        self.status = None
        self.pinging = False
        self.failed_pings = 0
        self.qr_mode = "pair"  # какой QR-код показан: "pair" — подключить, "install" — скачать приложение
        self.build()
        self.bind("<Escape>", lambda e: self.destroy())
        center_on_screen(self)
        self.focus_force()
        self.after(200, self.check_server)

    def build(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.status = None
        token = phone.get_token(self.prefs)
        tk.Label(self.body, text="Задачи на телефоне", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", pady=(0, 10))
        if token:
            self.build_on(token)
        else:
            self.build_off()

    def text(self, parent, text, color=None, pady=(0, 8), width=440):
        label = tk.Label(parent, text=text, bg=SURFACE, fg=color or TEXT, font=FONT_SMALL,
                         justify="left", wraplength=width)
        label.pack(anchor="w", pady=pady)
        return label

    def build_off(self):
        self.text(self.body, "С телефона на Android можно смотреть и менять задачи — личные и "
                  "общие. Телефон берёт их у этого компьютера, поэтому:")
        self.text(self.body, "• компьютер должен быть включён, а в трее (возле часов) — значок ToDoro;\n"
                  "• телефон должен быть в той же сети Wi-Fi или подключён к VPN.")
        self.text(self.body, "Подключить телефон сможет только тот, кто увидит QR-код в этом окне: "
                  "в нём секретный ключ.", MUTED)
        buttons = tk.Frame(self.body, bg=SURFACE)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Закрыть", style="Soft.TButton", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Включить связь с телефоном", style="Accent.TButton",
                   command=self.enable).pack(side="right", padx=(0, 8))

    def build_on(self, token):
        hosts = phone.addresses()
        tabs = tk.Frame(self.body, bg=SURFACE)
        tabs.pack(anchor="w", pady=(0, 12))
        for mode, label in (("install", "1. Установить приложение"), ("pair", "2. Подключить телефон")):
            ttk.Button(tabs, text=label, style="Accent.TButton" if mode == self.qr_mode else "Soft.TButton",
                       command=lambda m=mode: self.show_qr(m)).pack(side="left", padx=(0, 8))
        row = tk.Frame(self.body, bg=SURFACE)
        row.pack(fill="x")
        install = self.qr_mode == "install"
        text = updater.APK_URL if install else phone.pairing_text(token, hosts)
        self.draw_qr(row, text).pack(side="left", anchor="n", padx=(0, 20))
        info = tk.Frame(row, bg=SURFACE)
        info.pack(side="left", anchor="n", fill="y")
        if install:
            self.text(info, "Наведите камеру телефона на этот код и откройте ссылку — с GitHub "
                      "скачается приложение ToDoro.apk.", width=300)
            self.text(info, "Откройте скачанный файл. Телефон спросит, разрешить ли установку "
                      "из браузера, — разрешите.", width=300)
            self.text(info, "Потом нажмите «2. Подключить телефон».", width=300)
            link = tk.Label(info, text="Ссылка на файл", bg=SURFACE, fg=ACCENT,
                            font=(*FONT_SMALL, "underline"), cursor="hand2")
            link.pack(anchor="w", pady=(6, 0))
            link.bind("<Button-1>", lambda e: webbrowser.open(updater.APK_URL))
        else:
            self.text(info, "В приложении ToDoro на телефоне нажмите «Сканировать QR-код» и "
                      "наведите камеру на этот код. Можно и обычной камерой телефона.", width=300)
            if hosts:
                self.text(info, "Проверить, видит ли телефон компьютер: откройте в браузере телефона",
                          MUTED, pady=(10, 2), width=300)
                tk.Label(info, text=f"http://{hosts[0]}:{phone.PORT}", bg=SURFACE, fg=ACCENT,
                         font=FONT_SMALL_BOLD).pack(anchor="w")
                self.text(info, "— должно появиться «ToDoro работает». Через VPN — тоже.", MUTED,
                          pady=(2, 8), width=300)
            else:
                self.text(info, "Компьютер сейчас не в сети — подключите его к Wi-Fi или кабелю.",
                          DANGER, pady=(10, 8), width=300)
        line = tk.Frame(self.body, bg=SURFACE)
        line.pack(fill="x", pady=(14, 0))
        self.dot = tk.Label(line, text="●", bg=SURFACE, fg=MUTED, font=FONT_SMALL)
        self.dot.pack(side="left")
        self.status = tk.Label(line, text="Проверяю, отвечает ли значок ToDoro в трее…", bg=SURFACE,
                               fg=TEXT, font=FONT_SMALL, justify="left", wraplength=360)
        self.status.pack(side="left", padx=(6, 0))
        self.fix_button = ttk.Button(line, text="Запустить значок", style="Soft.TButton",
                                     command=self.restart_tray)
        self.text(self.body, "Если Windows спросит, разрешить ли ToDoro доступ к сети, — нажмите "
                  "«Разрешить» (частные сети).", MUTED, pady=(10, 0))
        buttons = tk.Frame(self.body, bg=SURFACE)
        buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Закрыть", style="Accent.TButton", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Отключить телефон", style="Soft.TButton",
                   command=self.disable).pack(side="right", padx=(0, 8))
        ttk.Button(buttons, text="Новый ключ", style="Soft.TButton",
                   command=self.renew).pack(side="right", padx=(0, 8))

    def show_qr(self, mode):
        self.qr_mode = mode
        self.build()
        self.geometry("")  # у кодов разное оформление — окно подстраивает размер, оставаясь на месте

    def draw_qr(self, parent, text):
        """QR-код на холсте: всегда чёрный на белом (и в тёмной теме) — так его читают камеры."""
        try:
            import segno
        except ImportError:
            return tk.Label(parent, text=text, bg=SURFACE, fg=TEXT, font=FONT_SMALL, wraplength=240)
        rows = list(segno.make(text, error="m").matrix_iter(scale=1, border=4))
        cell = max(3, 260 // len(rows))
        size = cell * len(rows)
        canvas = tk.Canvas(parent, width=size, height=size, bg="#ffffff", highlightthickness=0)
        for y, modules in enumerate(rows):
            for x, dark in enumerate(modules):
                if dark:
                    canvas.create_rectangle(x * cell, y * cell, (x + 1) * cell, (y + 1) * cell,
                                            fill="#000000", width=0)
        return canvas

    # --- действия ---

    def enable(self):
        phone.new_token(self.prefs)
        tray.start()  # телефону отвечает значок в трее
        self.failed_pings = 0
        self.build()
        center_on_screen(self)

    def renew(self):
        if ui.askyesno("Новый ключ", "Телефоны, подключённые раньше, перестанут видеть задачи — "
                       "их нужно будет подключить заново по новому QR-коду.\n\nСделать новый ключ?",
                       parent=self):
            phone.new_token(self.prefs)
            self.build()

    def disable(self):
        if ui.askyesno("Отключить телефон", "Телефон перестанет видеть задачи, а компьютер — "
                       "отвечать по сети.\n\nОтключить?", parent=self):
            phone.disable(self.prefs)
            self.build()
            center_on_screen(self)

    def restart_tray(self):
        self.fix_button.state(["disabled"])
        self.failed_pings = 0

        def work():
            tray.stop()
            tray.start()
        in_background(self, work, lambda result, error: None)

    # --- отвечает ли значок в трее ---

    def check_server(self):
        if not self.winfo_exists():
            return
        if self.status is not None and not self.pinging:
            self.pinging = True
            in_background(self, phone.ping, self.show_server)
        self.after(self.PING_EVERY_MS, self.check_server)

    def show_server(self, ok, error):
        self.pinging = False
        if self.status is None or not self.status.winfo_exists():
            return
        if ok:
            self.failed_pings = 0
            self.dot.configure(fg=OK_DOT)
            self.status.configure(text="Компьютер готов отвечать телефону.")
            self.fix_button.pack_forget()
            return
        self.failed_pings += 1
        if self.failed_pings < 4:  # значок мог только что запуститься: связь включается за пару секунд
            return
        self.dot.configure(fg=DANGER)
        if tray.is_running():
            self.status.configure(text="Значок ToDoro в трее не отвечает — возможно, он запущен "
                                       "из прошлой версии.")
            self.fix_button.configure(text="Перезапустить значок")
        else:
            self.status.configure(text="Значок ToDoro в трее не запущен — без него телефон не "
                                       "увидит задачи.")
            self.fix_button.configure(text="Запустить значок")
        self.fix_button.state(["!disabled"])
        if not self.fix_button.winfo_ismapped():
            self.fix_button.pack(side="right")


class CheckingDialog(tk.Toplevel):
    """Маленькое окно «Проверяю обновления…» с бегущей полосой и кнопкой «Отмена»."""

    def __init__(self, parent):
        super().__init__(parent)
        self.cancelled = False
        self.title("Обновление ToDoro")
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        body = tk.Frame(self, bg=SURFACE, padx=26, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Проверяю, есть ли новая версия…", bg=SURFACE, fg=TEXT,
                 font=FONT_BOLD).pack(anchor="w")
        tk.Label(body, text="В медленной сети это может занять до минуты.", bg=SURFACE, fg=MUTED,
                 font=FONT_SMALL).pack(anchor="w", pady=(2, 10))
        self.bar = ttk.Progressbar(body, mode="indeterminate", length=320)
        self.bar.pack(fill="x")
        self.bar.start(15)
        ttk.Button(body, text="Отмена", style="Soft.TButton", command=self.cancel).pack(
            anchor="e", pady=(14, 0))
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())
        center_on_screen(self)
        self.focus_force()
        try:
            self.grab_set()  # пока ждём ответа, второй раз проверку не запустить
        except tk.TclError:
            pass

    def cancel(self):
        self.cancelled = True
        self.close()

    def close(self):
        if self.winfo_exists():
            self.bar.stop()
            self.destroy()


class UpdateDialog(tk.Toplevel):
    """«Вышла новая версия»: что нового и кнопка «Обновить» (скачать и установить)."""

    # Столько секунд без единого байта — скачивание «подвисло», останавливаем. С запасом: неудачная
    # попытка скачать .exe (напрямую 30 с, через Windows ещё 30 с) не должна помешать перейти к .zip
    STALL_S = 90

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
        self.later_button = ttk.Button(buttons, text="Позже", style="Soft.TButton", command=self.destroy)
        self.later_button.pack(side="right")
        self.ok_button.pack(side="right", padx=(0, 8))
        self.later_button.lift()  # Tab: сначала «Обновить», потом «Позже»
        # Esc — то же, что «Позже», а во время скачивания — «Отмена»
        self.bind("<Escape>", lambda e: self.later_button.invoke() if self.later_button.instate(["!disabled"]) else None)
        self.bind("<Return>", lambda e: self.update_now() if self.ok_button.instate(["!disabled"]) else None)
        center_on_screen(self)
        self.focus_force()

    def update_now(self):
        if not self.self_update:
            webbrowser.open(self.release["url"])
            self.destroy()
            return
        # Пока качается, «Позже» становится «Отменой», а окно можно закрыть: если сеть «подвисла»,
        # пользователь не должен оставаться перед окном, которое ничего не делает
        self.ok_button.state(["disabled"])
        self.later_button.configure(text="Отмена", command=self.cancel_download)
        self.protocol("WM_DELETE_WINDOW", self.close_during_download)
        self.progress.configure(value=0)
        self.progress.pack(fill="x", side="top", pady=(4, 0))
        self.status.configure(text="Скачиваю обновление…", fg=MUTED)
        # Своя «отмена» у каждой попытки: прошлая, если её поток ещё ждёт сеть, на новую не влияет
        cancel = self.cancel_event = threading.Event()
        shown = {"done": 0, "total": 0, "moved": time_module.monotonic()}

        def progress(done, total):
            shown.update(done=done, total=total, moved=time_module.monotonic())

        def tick():
            # скачивание закончилось — не затираем сообщение об ошибке или «Устанавливаю…»
            if not self.winfo_exists() or not self.downloading or cancel.is_set():
                return
            if time_module.monotonic() - shown["moved"] > self.STALL_S:
                self.cancel_download("Обновление не скачивается: полторы минуты не приходит ни "
                                     "одного байта. Проверьте интернет и попробуйте ещё раз — или "
                                     "скачайте установщик со страницы выпуска.")
                return
            if shown["total"]:
                self.progress["value"] = 100 * shown["done"] / shown["total"]
                self.status.configure(text=f"Скачиваю обновление… {shown['done'] // 1048576} из "
                                      f"{shown['total'] // 1048576} МБ")
            self.master.after(150, tick)  # через главное окно: это окно могут закрыть

        def finished(path, error):
            if cancel.is_set() or not self.winfo_exists():
                return  # попытку отменили — окно уже вернулось в обычный вид или закрыто
            self.downloading = False
            if error:
                self.restore_buttons()
                if isinstance(error, updater.BlockedError):
                    self.status.configure(text="Обновление не скачалось — возможно, его не пропускает фильтр сети.",
                                          fg=DANGER)
                    self.explain_blocked(error)
                    return
                message = str(error) if isinstance(error, updater.UpdateError) else f"Ошибка: {error}"
                self.status.configure(text=message, fg=DANGER)
                return
            self.later_button.state(["disabled"])  # установщик уже не отменить
            self.protocol("WM_DELETE_WINDOW", lambda: None)
            self.status.configure(text="Устанавливаю… ToDoro закроется и откроется снова.")
            self.update_idletasks()
            tray.stop()  # иначе установщик не сможет заменить ToDoro.exe, занятый значком в трее
            try:
                updater.run_installer(path)
            except OSError as error:
                self.restore_buttons()  # не оставлять окно, которое нельзя закрыть
                self.status.configure(text=f"Не удалось запустить установщик: {error}", fg=DANGER)
                return
            self.after(500, self.on_close_app)

        self.downloading = True
        tick()
        # Ждём поток через главное окно: это окно могут закрыть, пока файл ещё качается
        in_background(self.master, lambda: updater.download(self.release, progress,
                                                            cancelled=cancel.is_set), finished)

    def restore_buttons(self):
        """Окно снова в обычном виде: «Обновить» и «Позже» доступны, полосы прогресса нет."""
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.ok_button.state(["!disabled"])
        self.later_button.state(["!disabled"])
        self.later_button.configure(text="Позже", command=self.destroy)
        self.progress.pack_forget()

    def cancel_download(self, message="Скачивание отменено."):
        """«Отмена» во время скачивания (или файл перестал приходить): поток в фоне бросит
        работу при первой возможности, а окно сразу снова готово — «Обновить» или «Позже»."""
        self.cancel_event.set()
        self.downloading = False
        self.restore_buttons()
        self.status.configure(text=message, fg=MUTED if message == "Скачивание отменено." else DANGER)

    def close_during_download(self):
        self.cancel_event.set()
        self.downloading = False
        self.destroy()

    def explain_blocked(self, error):
        """Обновление не дал скачать фильтр сети: что делать — и адреса для администратора."""
        choice = AlertDialog(
            self, "Обновление не скачалось", str(error), "warning",
            [("Скопировать адреса", "copy", "TButton"),
             ("Открыть страницу выпуска", "page", "Accent.TButton"),
             ("Закрыть", None, "TButton")], "page", None).show()
        if choice == "copy":
            self.clipboard_clear()
            self.clipboard_append("\n".join(updater.DOWNLOAD_HOSTS))
            self.status.configure(text="Адреса для администратора скопированы — вставьте их в письмо.",
                                  fg=MUTED)
        elif choice == "page":
            webbrowser.open(self.release["url"])


class CatbusRun(tk.Toplevel):
    """Котобус проезжает по низу окна и «увозит» выполненную задачу.

    Прозрачное окно поверх приложения: всё, что цвета KEY, Windows делает прозрачным.
    """

    KEY = CATBUS_KEY  # почти цвет фона — края рисунка на интерфейсе не видны
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
        self.sign_text = self.canvas.create_text(0, 0, text=label, font=FONT_BOLD, fill=SIGN_TEXT,
                                                 anchor="s")
        x1, y1, x2, y2 = self.canvas.bbox(self.sign_text)
        self.sign_w, self.sign_h = x2 - x1 + 20, y2 - y1 + 8
        self.sign = round_rect(self.canvas, 0, 0, self.sign_w, self.sign_h, 8,
                               fill=SIGN_BG, outline=SIGN_BORDER)
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


class GuideTour:
    """Ознакомительный тур: окошко с подсказкой у нужной части окна и синяя рамка вокруг неё.

    steps — [(функция, возвращающая виджет или None, заголовок, текст)]. Без виджета подсказка
    стоит посередине окна (приветствие и последний шаг). Шаги, чей виджет сейчас не виден
    (например, правая панель в узком окне), пропускаются.
    on_close(show_next_time) — тур закрыт; аргумент — показывать ли его при следующем запуске.
    """

    KEY = "#ff00fe"   # этот цвет Windows делает прозрачным: от окна рамки остаётся только рамка
    PAD, GAP = 6, 14  # отступ рамки от виджета и подсказки от рамки
    WIDTH = 420

    def __init__(self, root, steps, on_close, hide_next_time=False):
        self.root, self.steps, self.on_close = root, steps, on_close
        self.index, self.shown_box = 0, None
        self.hide_next = tk.BooleanVar(value=hide_next_time)

        # рамка вокруг показываемой части окна (если Windows умеет прозрачные окна)
        self.frame = tk.Toplevel(root)
        self.frame.withdraw()
        self.frame.overrideredirect(True)
        self.frame.transient(root)
        try:
            self.frame.attributes("-transparentcolor", self.KEY)
            self.frame.configure(bg=self.KEY)
            self.ring = tk.Canvas(self.frame, bg=self.KEY, highlightthickness=0)
            self.ring.pack(fill="both", expand=True)
        except tk.TclError:
            self.frame.destroy()
            self.frame = None

        self.tip = tk.Toplevel(root)
        self.tip.withdraw()
        self.tip.overrideredirect(True)
        self.tip.transient(root)
        box = tk.Frame(self.tip, bg=SURFACE, padx=20, pady=16, highlightthickness=1,
                       highlightbackground=POPUP_BORDER)
        box.pack(fill="both", expand=True)
        top = tk.Frame(box, bg=SURFACE)
        top.pack(fill="x")
        self.picture = tk.Label(top, bg=SURFACE)
        self.picture.pack(side="left", anchor="n", padx=(0, 14))
        text = tk.Frame(top, bg=SURFACE)
        text.pack(side="left", fill="both", expand=True)
        self.counter = tk.Label(text, bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.counter.pack(fill="x")
        self.heading = tk.Label(text, bg=SURFACE, fg=TEXT, font=("Segoe UI Semibold", 13),
                                anchor="w", justify="left")
        self.heading.pack(fill="x", pady=(0, 4))
        self.text = tk.Label(text, bg=SURFACE, fg=TEXT, font=FONT_SMALL, anchor="w",
                             justify="left")
        self.text.pack(fill="x")

        ttk.Checkbutton(box, text="Не показывать тур при следующем запуске",
                        variable=self.hide_next, style="Tour.TCheckbutton",
                        cursor="hand2").pack(anchor="w", pady=(14, 0))
        bar = tk.Frame(box, bg=SURFACE)
        bar.pack(fill="x", pady=(10, 0))
        self.skip = ttk.Button(bar, text="Пропустить", style="Soft.TButton", cursor="hand2",
                               command=self.close)
        self.next_button = ttk.Button(bar, style="Accent.TButton", cursor="hand2",
                                      command=lambda: self.go(1))
        self.next_button.pack(side="right")
        self.back_button = ttk.Button(bar, text="Назад", style="Soft.TButton", cursor="hand2",
                                      command=lambda: self.go(-1))
        for key, action in (("<Escape>", self.close), ("<Return>", lambda: self.go(1)),
                            ("<Right>", lambda: self.go(1)), ("<Left>", lambda: self.go(-1))):
            self.tip.bind(key, lambda e, a=action: a())

        self.show_step()
        self.follow()

    def target(self, index):
        """Виджет шага, если он сейчас виден на экране, иначе None."""
        widget = self.steps[index][0]()
        if widget is not None and widget.winfo_exists() and widget.winfo_viewable():
            return widget
        return None

    def go(self, step):
        index = self.index + step
        # шаги с невидимым сейчас виджетом пропускаем (приветствие и конец — без виджета)
        while 0 < index < len(self.steps) - 1 and self.target(index) is None:
            index += step
        if index >= len(self.steps):
            self.close()
        elif index >= 0:
            self.index = index
            self.show_step()

    def show_step(self):
        _, heading, text = self.steps[self.index]
        first, last = self.index == 0, self.index == len(self.steps) - 1
        self.counter.configure(text="" if first or last else
                               f"Шаг {self.index} из {len(self.steps) - 2}")
        self.heading.configure(text=heading)
        self.text.configure(text=text)
        image = "totoro_happy" if first or last else "totoro_small"
        self.picture.configure(image=IMAGES.get(image, ""))
        for label in (self.heading, self.text):
            label.configure(wraplength=self.WIDTH - (240 if first or last else 120))
        self.next_button.configure(text="Начать тур" if first else
                                   "Начать работу" if last else "Далее  →")
        if first:
            self.back_button.pack_forget()
        else:
            self.back_button.pack(side="right", padx=(0, 8))
        if last:
            self.skip.pack_forget()
        else:
            self.skip.pack(side="left")
        self.shown_box = None
        self.place()
        self.tip.focus_force()
        self.next_button.focus_set()

    def place(self):
        """Ставит рамку и подсказку по текущему положению окна и виджета."""
        root = self.root
        if root.state() in ("iconic", "withdrawn"):
            self.tip.withdraw()
            if self.frame:
                self.frame.withdraw()
            self.shown_box = None
            return
        widget = self.target(self.index)
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        target = widget and (widget.winfo_rootx(), widget.winfo_rooty(),
                             widget.winfo_width(), widget.winfo_height())
        box = (rx, ry, rw, rh, target)
        if box == self.shown_box:
            return
        self.shown_box = box
        self.tip.update_idletasks()
        tw, th = self.WIDTH, self.tip.winfo_reqheight()
        if not target:
            x, y = rx + (rw - tw) // 2, ry + (rh - th) // 2
            if self.frame:
                self.frame.withdraw()
        else:
            x, y, w, h = target
            pad = self.PAD
            fx, fy, fw, fh = x - pad, y - pad, w + 2 * pad, h + 2 * pad
            if self.frame:
                self.frame.geometry(f"{fw}x{fh}+{fx}+{fy}")
                self.ring.delete("all")
                round_rect(self.ring, 2, 2, fw - 2, fh - 2, 10, outline=ACCENT, width=3,
                           fill=self.KEY)
                self.frame.deiconify()
                self.frame.lift()
            # подсказка под рамкой; не помещается — над ней, потом слева, потом справа
            if fy + fh + self.GAP + th <= ry + rh:
                x, y = fx, fy + fh + self.GAP
            elif fy - self.GAP - th >= ry:
                x, y = fx, fy - self.GAP - th
            elif fx - self.GAP - tw >= rx:
                x, y = fx - self.GAP - tw, fy
            else:
                x, y = fx + fw + self.GAP, fy
            x = max(rx + 8, min(x, rx + rw - tw - 8))
            y = max(ry + 8, min(y, ry + rh - th - 8))
        self.tip.geometry(f"{tw}x{th}+{x}+{y}")
        self.tip.deiconify()
        self.tip.lift()

    def follow(self):
        """Окно двигают, меняют его размер, сворачивают — подсказка едет за ним."""
        try:
            if not self.tip.winfo_exists():
                return
            self.place()
        except tk.TclError:
            return
        self.tip.after(250, self.follow)

    def close(self):
        if not self.tip.winfo_exists():
            return
        self.tip.destroy()
        if self.frame:
            self.frame.destroy()
        self.on_close(not self.hide_next.get())


LANE_WIDTH = 250
# Готовые цвета для колонок доски
LANE_COLORS = [
    ("Синий", "#3b82f6"), ("Голубой", "#06b6d4"), ("Зелёный", "#22c55e"),
    ("Жёлтый", "#eab308"), ("Оранжевый", "#f59e0b"), ("Красный", "#ef4444"),
    ("Розовый", "#ec4899"), ("Фиолетовый", "#8b5cf6"), ("Серый", "#64748b"),
]


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


class QuickAdd(tk.Frame):
    """Строка «＋ Добавить задачу» над списком, в колонке доски и в четверти матрицы.
    Щелчок — раскрывается поле для названия; Enter добавляет задачу сюда (статус колонки,
    приоритет четверти), и поле остаётся открытым для следующей; Esc или пустое поле без
    фокуса — снова строка. Доска перерисовывается целиком (после своих и чужих изменений) —
    поэтому недописанный текст хранится в app.quick_draft и поле открывается заново с ним."""

    def __init__(self, parent, app, place, bg):
        super().__init__(parent, bg=bg)
        self.app, self.place = app, place
        self.entry = self.suggest = None
        self.link = tk.Label(self, text="＋  Добавить задачу", bg=bg, fg=MUTED, font=FONT_SMALL,
                             anchor="w", cursor="hand2", padx=6, pady=4)
        self.link.pack(fill="x")
        self.link.bind("<Button-1>", lambda e: self.open())
        self.link.bind("<Enter>", lambda e: self.link.configure(fg=ACCENT))
        self.link.bind("<Leave>", lambda e: self.link.configure(fg=MUTED))
        draft = app.quick_draft
        if draft and draft["place"] == place:
            # фокус возвращаем, только если пользователь не ушёл печатать в другое поле
            # (доску могли перерисовать, пока поле ещё не узнало, что фокус ушёл)
            try:
                busy = isinstance(app.root.focus_get(), (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox))
            except (KeyError, tk.TclError):  # фокус был в уже удалённом поле
                busy = False
            self.open(draft["text"], focus=draft["focus"] and not busy)

    def open(self, text="", focus=True):
        if self.entry is None:
            self.link.pack_forget()
            self.entry = ttk.Entry(self, font=FONT)
            self.entry.pack(fill="x", ipady=1)
            self.entry.insert(0, text)
            self.suggest = TitleSuggest(self.entry, self.text, lambda: self.app.smart_rows() or [])
            self.entry.bind("<Return>", self.enter)
            self.entry.bind("<KP_Enter>", self.enter)
            # Esc сначала закрывает список похожих названий (TitleSuggest), потом — само поле
            self.entry.bind("<Escape>", lambda e: (self.close(), "break")[1], add="+")
            self.entry.bind("<KeyRelease>", lambda e: self.remember(), add="+")
            self.entry.bind("<FocusOut>", lambda e: self.app.root.after(250, self.unfocused), add="+")
        self.remember(focus)
        if focus:
            self.entry.focus_set()
            self.entry.icursor("end")

    def text(self):
        return self.entry.get().strip() if self.entry is not None else ""

    def remember(self, focus=True):
        if self.entry is not None:
            self.app.quick_draft = dict(place=self.place, text=self.entry.get(), focus=focus)

    def enter(self, event=None):
        if not self.suggest.accept():  # Enter подставил вариант названия — не добавляем
            title = self.text()
            if title:
                self.entry.delete(0, "end")
                self.remember()
                self.app.add(title, self.place)  # доска перерисуется — поле откроется снова, пустым
        return "break"

    def unfocused(self):
        """Ушли из поля: пустое сворачивается, с текстом — остаётся (без фокуса)."""
        try:
            if self.entry is None or not self.entry.winfo_exists():
                return  # строку уже перерисовали
            if self.entry.focus_get() is self.entry:
                return
        except (KeyError, tk.TclError):  # фокус в уже закрытом окне
            pass
        if self.text():
            self.remember(focus=False)
        else:
            self.close()

    def close(self):
        draft = self.app.quick_draft
        if draft and draft["place"] == self.place:
            self.app.quick_draft = None
        if self.entry is not None:
            self.entry.destroy()  # список похожих названий закроется сам (TitleSuggest)
            self.entry = self.suggest = None
            self.link.pack(fill="x")


class KanbanBoard(tk.Frame):
    """Канбан-доска: колонки-статусы и карточки задач, которые можно перетаскивать."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.selected_id = None
        self.drag = None
        self.lanes = []   # [(status_id, рамка колонки, цвет фона колонки)]
        self.cards = {}   # id задачи -> рамка карточки
        self.quick_adds = []  # «＋ Добавить задачу» в колонках, слева направо
        self.card_width = LANE_WIDTH
        self.show_priority = True

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
        self.lanes, self.cards, self.quick_adds = [], {}, []
        by_status = {}
        for row in rows:
            by_status.setdefault(row[9], []).append(row)
        for status_id, name, color, is_done in statuses:
            self.make_lane(status_id, name, color, is_done, by_status.get(status_id, []), overdue_ids)

        add = tk.Label(self.inner, text="＋  Колонка", bg=BG, fg=MUTED, font=FONT_SMALL,
                       cursor="hand2", padx=18, pady=10, highlightthickness=1,
                       highlightbackground=DASHED)
        add.pack(side="left", anchor="n", pady=(0, 4))
        add.bind("<Button-1>", lambda e: self.app.add_lane())
        add.bind("<Enter>", lambda e: add.configure(fg=ACCENT, highlightbackground=ACCENT))
        add.bind("<Leave>", lambda e: add.configure(fg=MUTED, highlightbackground=DASHED))

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
            tk.Label(head, text="✔", bg=lane_bg, fg=GOOD_TEXT, font=FONT_SMALL, cursor="fleur").pack(
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

        # Под заголовком — «＋ Добавить задачу», ниже — карточки в прокручиваемой области
        quick = QuickAdd(lane, self.app, ("status", status_id), lane_bg)
        quick.pack(fill="x", padx=10, pady=(0, 6))
        self.quick_adds.append(quick)
        area = tk.Canvas(lane, bg=lane_bg, highlightthickness=0)
        area.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 10))
        cards = tk.Frame(area, bg=lane_bg)
        area.create_window(0, 0, window=cards, anchor="nw", width=LANE_WIDTH - 20)
        cards.bind("<Configure>", lambda e: area.configure(scrollregion=area.bbox("all")))
        for row in rows:
            self.make_card(cards, row, color, row[0] in overdue_ids)
        empty = []
        if not rows:
            empty.append(tk.Label(cards, text="Перетащите сюда задачу", bg=lane_bg, fg=DONE,
                                  font=FONT_SMALL))
            empty[0].pack(pady=24)

        for widget in (lane, area, cards, *empty):
            widget.bind("<Button-1>", lambda e: self.app.clear_selection())
            # правая кнопка по пустому месту колонки — её меню, первым пунктом «Новая задача…»
            widget.bind("<Button-3>", lambda e: self.app.lane_menu(status_id, e.x_root, e.y_root))
        bind_tree(head, "<Button-3>", lambda e: self.app.lane_menu(status_id, e.x_root, e.y_root))
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
        if "priority" in fields and level < 4 and self.show_priority:
            tk.Label(top, image=IMAGES.get(f"priority_{level}", ""), bg=SURFACE).pack(
                side="left", anchor="n", pady=(4, 0), padx=(0, 6))
        if "number" in fields:
            tk.Label(top, text=f"#{task_id}", bg=SURFACE, fg=DONE, font=FONT_SMALL).pack(
                side="right", anchor="n", padx=(6, 0))
        color = DANGER if overdue else DONE if done else TEXT
        tk.Label(top, text=title, bg=SURFACE, fg=color, font=FONT_BOLD, justify="left",
                 anchor="w", wraplength=self.card_width - 95).pack(side="left", fill="x")
        if "body" in fields and body.strip():
            tk.Label(content, text=short_text(richtext.plain(body), 90), bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                     justify="left", anchor="w", wraplength=self.card_width - 60).pack(fill="x", pady=(4, 0))
        if "due" in fields and due_at:
            due_text = datetime.fromisoformat(due_at).strftime("%d.%m %H:%M")
            tk.Label(content, text=("⚠ Срок " if overdue else "Срок ") + due_text, bg=SURFACE,
                     fg=DANGER if overdue else MUTED, font=FONT_SMALL, anchor="w").pack(
                fill="x", pady=(4, 0))
        extra = []
        if "remind" in fields and due_at and remind_before:
            extra.append("Напомнить " + remind_label(remind_before).lower())
        if "created" in fields:
            extra.append("Создана " + created[:5])
        if "assignee" in fields and self.app.assignees.get(task_id):
            extra.insert(0, "Исполнитель " + self.app.assignees[task_id])
        if "unit" in fields and self.app.unit_names.get(task_id):
            extra.append(self.app.unit_names[task_id])
        if "author" in fields and self.app.authors.get(task_id):
            extra.append("Инициатор " + self.app.authors[task_id])
        if extra:
            # неразрывные пробелы внутри пары: строка переносится только между «· …», а не
            # так, что «Инициатор» остаётся в конце строки, а имя уезжает на следующую
            tk.Label(content, text=" · ".join(part.replace(" ", " ") for part in extra), bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                     anchor="w", justify="left", wraplength=self.card_width - 60).pack(fill="x", pady=(2, 0))
        # 📎 и 💬 — отдельной строкой: её можно обновить, не перерисовывая доску
        card.mark = tk.Label(content, bg=SURFACE, fg=MUTED, font=FONT_SMALL, anchor="w")
        self.cards[task_id] = card
        self.set_mark(task_id, self.app.task_mark(task_id))

        bind_tree(card, "<ButtonPress-1>", lambda e: self.on_press(e, task_id))
        bind_tree(card, "<B1-Motion>", self.on_motion)
        bind_tree(card, "<ButtonRelease-1>", self.on_release)
        bind_tree(card, "<Double-Button-1>", lambda e: self.app.edit())
        bind_tree(card, "<Button-3>", lambda e: self.app.show_menu_for(task_id, e.x_root, e.y_root))

    def set_mark(self, task_id, mark):
        label = getattr(self.cards.get(task_id), "mark", None)
        if label is None:
            return
        label.configure(text=mark.strip())
        if mark and not label.winfo_ismapped():
            label.pack(fill="x", pady=(2, 0))
        elif not mark:
            label.pack_forget()

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


class EisenhowerMatrix(KanbanBoard):
    """Матрица Эйзенхауэра: четыре четверти по «срочно» и «важно».
    Карточку можно перетащить в другую четверть — у задачи поменяется приоритет.
    Просроченная задача всегда срочная: она стоит в левой колонке, пока не перенесут срок."""

    # уровень приоритета (priority_level), срочно, важно, название, подсказка, цвет
    QUADRANTS = [
        (1, True, True, "Сделать сейчас", "Срочно и важно", "#ef4444"),
        (2, False, True, "Запланировать", "Важно, но не срочно", "#f59e0b"),
        (3, True, False, "Поручить или сделать быстро", "Срочно, но не важно", "#3b82f6"),
        (4, False, False, "Отложить", "Не срочно и не важно", "#9ca3af"),
    ]

    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=BG)
        self.app = app
        self.selected_id = None
        self.drag = None
        self.lanes = []   # [(уровень приоритета, рамка четверти, цвет фона)]
        self.cards = {}
        self.quick_adds = []  # «＋ Добавить задачу» в четвертях, по порядку QUADRANTS
        self.show_priority = False  # приоритет и так виден по четверти
        self.card_width = LANE_WIDTH  # переносы текста на карточке — как на доске
        self.shown = None           # что нарисовано — чтобы перерисовать при смене ширины
        self.drawn_columns = None
        self.redraw_job = None

        self.columnconfigure(1, weight=1, uniform="q")
        self.columnconfigure(2, weight=1, uniform="q")
        self.rowconfigure(1, weight=1, minsize=self.MIN_ROW)  # высоту строк задаёт render
        self.rowconfigure(2, weight=1, minsize=self.MIN_ROW)
        # подписи осей: сверху «Срочно / Не срочно», слева (повёрнуто) «Важно / Не важно»
        for column, text in ((1, "Срочно"), (2, "Не срочно")):
            tk.Label(self, text=text, bg=BG, fg=MUTED, font=FONT_SMALL).grid(
                row=0, column=column, pady=(0, 4))
        for row, text in ((1, "Важно"), (2, "Не важно")):
            side = tk.Canvas(self, bg=BG, width=22, height=1, highlightthickness=0)  # высоту задаёт строка
            side.grid(row=row, column=0, sticky="ns", padx=(0, 4))
            label = side.create_text(11, 0, text=text, angle=90, fill=MUTED, font=FONT_SMALL)
            side.bind("<Configure>", lambda e, c=side, i=label: c.coords(i, 11, e.height / 2))
        self.quadrants = {}
        for index, quadrant in enumerate(self.QUADRANTS):
            frame = tk.Frame(self, bg=BG)
            frame.grid(row=1 + index // 2, column=1 + index % 2, sticky="nsew",
                       padx=(0, 10) if index % 2 == 0 else 0,
                       pady=(0, 10) if index < 2 else (0, 4))
            frame.pack_propagate(False)
            self.quadrants[quadrant[0]] = frame
        self.bind("<Button-1>", lambda e: self.app.clear_selection())
        self.bind("<Configure>", self.resized)

    CARD = LANE_WIDTH - 20  # ширина карточки — как на доске
    GAP = 8                 # промежуток между карточками
    MIN_ROW = 140           # высота строки четвертей, даже если в ней нет задач

    def resized(self, event):
        # карточки стоят сеткой: если в четверть теперь помещается другое число колонок,
        # рисуем заново (не сразу: пока тянут край окна, событий много)
        if self.shown and self.columns() != self.drawn_columns:
            if self.redraw_job:
                self.after_cancel(self.redraw_job)
            self.redraw_job = self.after(150, lambda: self.render(*self.shown))
        elif self.shown and self.card_size() + 20 != self.card_width:  # та же сетка, другая ширина
            if self.redraw_job:
                self.after_cancel(self.redraw_job)
            self.redraw_job = self.after(150, lambda: self.render(*self.shown))

    def inside_width(self):
        """Ширина четверти, которую могут занять карточки."""
        width = self.winfo_width()
        quadrant = (width - 36) // 2 if width > 100 else 500
        return quadrant - 30  # рамка, отступы и место под полосу прокрутки

    def columns(self):
        """Сколько карточек помещается в ряд в одной четверти."""
        return max(1, (self.inside_width() + self.GAP) // (self.CARD + self.GAP))

    def card_size(self):
        """Ширина карточки: карточки растягиваются на всю ширину четверти, чтобы справа не
        пустовало место (на небольшом экране — одна широкая колонка вместо узкой)."""
        columns = self.drawn_columns
        return max(self.CARD, (self.inside_width() - self.GAP * (columns - 1)) // columns)

    def level(self, task_id, urgent, important):
        """Четверть задачи: просроченная считается срочной."""
        overdue = self.shown is not None and task_id in self.shown[2]
        return priority_level(urgent or overdue, important)

    def render(self, statuses, rows, overdue_ids):
        self.redraw_job = None
        self.shown = (statuses, rows, overdue_ids)
        self.drawn_columns = self.columns()
        self.card_width = self.card_size() + 20  # переносы текста — по настоящей ширине карточки
        colors = {sid: color for sid, _, color, _ in statuses}
        by_level = {}
        for row in rows:
            by_level.setdefault(self.level(row[0], row[6], row[7]), []).append(row)
        # Высота строк — по числу рядов карточек: где задач больше, там больше места
        # (на небольшом экране пустые четверти не отнимают его у заполненных)
        for grid_row, levels in ((1, (1, 2)), (2, (3, 4))):
            card_rows = max(-(-len(by_level.get(level, [])) // self.drawn_columns) for level in levels)
            self.rowconfigure(grid_row, weight=max(1, card_rows))
        self.lanes, self.cards, self.quick_adds = [], {}, []
        for level, _, _, name, hint, color in self.QUADRANTS:
            self.make_quadrant(level, name, hint, color, by_level.get(level, []), colors, overdue_ids)
        if self.selected_id not in self.cards:
            self.selected_id = None
        self.highlight_selected()

    def make_quadrant(self, level, name, hint, color, rows, colors, overdue_ids):
        holder = self.quadrants[level]
        for child in holder.winfo_children():
            child.destroy()

        def new_task(event):
            self.app.new_task_menu(("level", level), event.x_root, event.y_root)
        bg = tint(color, 0.9)
        # толщина рамки всегда 2: при подсветке меняется только цвет
        box = tk.Frame(holder, bg=bg, highlightthickness=2, highlightbackground=BORDER)
        box.pack(fill="both", expand=True)
        tk.Frame(box, bg=color, height=5).pack(fill="x")
        head = tk.Frame(box, bg=bg)
        head.pack(fill="x", padx=12, pady=(8, 6))
        tk.Label(head, text=name, bg=bg, fg=TEXT, font=FONT_BOLD).pack(side="left")
        tk.Label(head, text=f" {len(rows)} ", bg=SURFACE, fg=MUTED, font=FONT_SMALL).pack(
            side="left", padx=(8, 0))
        tk.Label(head, text=hint, bg=bg, fg=MUTED, font=FONT_SMALL).pack(side="right")

        # карточки — сеткой в прокручиваемой области; цветная полоска карточки — цвет её статуса.
        # Не поместились (маленький экран) — справа появляется полоса прокрутки.
        bar_style = f"Quadrant{level}.Vertical.TScrollbar"
        ttk.Style().configure(bar_style, troughcolor=bg, bordercolor=bg)
        area = tk.Canvas(box, bg=bg, highlightthickness=0)
        bar = ttk.Scrollbar(box, orient="vertical", command=area.yview, style=bar_style)
        area.configure(yscrollcommand=lambda first, last: self.update_bar(bar, area, first, last))
        quick = QuickAdd(box, self.app, ("level", level), bg)  # под заголовком, как в колонке доски
        quick.pack(fill="x", padx=10, pady=(0, 6))
        self.quick_adds.append(quick)
        area.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 10))
        cards = tk.Frame(area, bg=bg)
        area.create_window(0, 0, window=cards, anchor="nw")
        cards.bind("<Configure>", lambda e: area.configure(scrollregion=area.bbox("all")))
        columns = self.drawn_columns
        for column in range(columns):
            cards.columnconfigure(column, minsize=self.card_width - 20, uniform="card")
        for index, row in enumerate(rows):
            cell = tk.Frame(cards, bg=bg)
            cell.grid(row=index // columns, column=index % columns, sticky="nsew",
                      padx=(0, self.GAP if index % columns < columns - 1 else 0))
            cell.bind("<Button-1>", lambda e: self.app.clear_selection())
            cell.bind("<Button-3>", new_task)
            self.make_card(cell, row, colors.get(row[9], color), row[0] in overdue_ids)
        empty = []
        if not rows:
            empty.append(tk.Label(cards, text="Перетащите сюда задачу", bg=bg, fg=DONE,
                                  font=FONT_SMALL))
            empty[0].grid(row=0, column=0, columnspan=columns, pady=24)
        for widget in (box, head, area, cards, *empty):
            widget.bind("<Button-1>", lambda e: self.app.clear_selection())
        # правая кнопка по пустому месту четверти — «Новая задача…» с её приоритетом
        for widget in (box, area, cards, *empty):
            widget.bind("<Button-3>", new_task)
        bind_tree(head, "<Button-3>", new_task)
        bind_tree(box, "<MouseWheel>",
                  lambda e: area.yview_scroll(-1 if e.delta > 0 else 1, "units")
                  if area.bbox("all") and area.bbox("all")[3] > area.winfo_height() else None)
        self.lanes.append((level, box, bg))

    @staticmethod
    def update_bar(bar, area, first, last):
        """Полоса прокрутки четверти — только когда карточки в неё не помещаются."""
        needed = not (float(first) <= 0 and float(last) >= 1)
        if needed and not bar.winfo_ismapped():
            bar.pack(side="right", fill="y", padx=(0, 4), pady=(0, 10), before=area)
            area.pack_configure(padx=(10, 2))
        elif not needed and bar.winfo_ismapped():
            bar.pack_forget()
            area.pack_configure(padx=(10, 6))
        bar.set(first, last)

    def on_release(self, event):
        drag, self.drag = self.drag, None
        if not drag or drag["ghost"] is None:
            return
        drag["ghost"].destroy()
        self.configure(cursor="")
        for _, box, _ in self.lanes:
            box.configure(highlightbackground=BORDER)
        target = self.lane_at(event.x_root, event.y_root)
        info = self.app.task_info(drag["id"])
        current = info and self.level(drag["id"], info["urgent"], info["level"] in (1, 2))
        if target is None or not info or target == current:
            self.highlight_selected()
            return
        _, urgent, important, *_ = next(q for q in self.QUADRANTS if q[0] == target)
        if info["overdue"] and not urgent:
            self.highlight_selected()
            ui.showinfo("Срок уже прошёл",
                        f"«{short_text(info['title'])}» просрочена, поэтому она остаётся среди срочных.\n\n"
                        "Чтобы задача перестала быть срочной, перенесите её срок или отметьте её "
                        "выполненной.", parent=self.app.root)
            return
        if info["overdue"]:  # срочной её делает просрочка — свой флажок «срочно» не трогаем
            urgent = bool(info["urgent"])
        # матрицу перестраиваем после выхода из обработчика события
        self.after_idle(lambda: self.app.quick_priority(drag["id"], urgent, important))


class CalendarView(tk.Frame):
    """Календарь на месяц: задача стоит в дне своего срока. Следующие сроки повторяющихся задач
    показаны бледно, со значком 🔁 — видно расписание вперёд. Щелчок по задаче — карточка справа,
    двойной щелчок — изменить, двойной щелчок по дню — новая задача с этим сроком. Задачу можно
    перетащить на другой день — срок переносится, время остаётся прежним."""

    CHIP = 27  # высота плашки с задачей в дне (25) вместе с промежутком под ней (2)
    MAX_PROJECTED = 45  # больше повторов одной задачи на экране не бывает (6 недель каждый день — 42)
    # цвет полоски на плашке — цвет приоритета, как четверти матрицы; обычная задача — акцентный
    LEVEL_COLORS = {level: color for level, *_, color in EisenhowerMatrix.QUADRANTS if level < 4}

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.selected_id = None
        self.drag = None             # задачу тащат на другой день (см. on_press)
        self.cells = []              # (день, его клетка) — куда можно бросить задачу
        self.due_of = {}             # id задачи -> срок, как он показан (для переноса)
        self.month = date.today().replace(day=1)
        self.shown = None            # (статусы, задачи, просроченные) — для перерисовки
        self.chips = {}              # id задачи -> [плашки с ней в днях месяца]
        self.quick_adds = []         # строки «＋ Добавить задачу» нет: новая задача — по дню
        self.drawn_fit = None        # сколько задач помещалось в день при последней отрисовке
        self.redraw_job = None

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", pady=(0, 8))
        ttk.Button(head, text="‹", style="Icon.TButton", width=3, cursor="hand2",
                   command=lambda: self.shift_month(-1)).pack(side="left")
        ttk.Button(head, text="›", style="Icon.TButton", width=3, cursor="hand2",
                   command=lambda: self.shift_month(1)).pack(side="left", padx=(4, 0))
        self.title = tk.Label(head, bg=BG, fg=TEXT, font=FONT_BOLD)
        self.title.pack(side="left", padx=(12, 0))
        ttk.Button(head, text="Сегодня", style="Soft.TButton", cursor="hand2",
                   command=self.go_today).pack(side="left", padx=(12, 0))
        self.note = tk.Label(head, bg=BG, fg=MUTED, font=FONT_SMALL)
        self.note.pack(side="right")

        self.days = tk.Frame(self, bg=BORDER)  # линии между днями — цвет фона в щелях сетки
        self.days.pack(fill="both", expand=True)
        for column in range(7):
            self.days.columnconfigure(column, weight=1, uniform="day")
        self.days.bind("<Configure>", self.resized)
        bind_tree(self, "<MouseWheel>", self.wheel)  # дни создаются в draw — там привязываем и их

    # --- месяц ---

    def shift_month(self, step):
        """Листать месяцы. Колёсико (особенно тачпад) даёт много событий подряд — название
        месяца меняется сразу, а дни рисуются, когда прокрутка остановилась."""
        index = self.month.year * 12 + self.month.month - 1 + step
        self.month = date(index // 12, index % 12 + 1, 1)
        self.title.configure(text=f"{MONTHS[self.month.month - 1]} {self.month.year}")
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
        self.redraw_job = self.after(120, self.draw)

    def wheel(self, event):
        self.shift_month(-1 if event.delta > 0 else 1)
        return "break"

    def go_today(self):
        self.month = date.today().replace(day=1)
        self.draw()

    def resized(self, event):
        # поменялась высота — в день помещается другое число задач: рисуем заново, но не сразу
        if self.shown and self.fit() != self.drawn_fit:
            if self.redraw_job:
                self.after_cancel(self.redraw_job)
            self.redraw_job = self.after(150, self.draw)

    def weeks(self):
        return calendar.Calendar(firstweekday=0).monthdatescalendar(self.month.year, self.month.month)

    def fit(self):
        """Сколько строк с задачами помещается в один день."""
        height = self.days.winfo_height()
        if height < 100:  # ещё не показан на экране
            return 3
        cell = (height - 24) // len(self.weeks())
        return max(1, (cell - 32) // self.CHIP)  # 32 — число дня сверху и запас снизу

    # --- отрисовка ---

    def render(self, statuses, rows, overdue_ids):
        self.shown = (statuses, rows, overdue_ids)
        self.draw()

    def entries(self, rows, overdue_ids, first, last):
        """{день: [(время, уровень, id, заголовок, выполнена, просрочена, будущий повтор)]}."""
        by_day = {}
        now = datetime.now()
        for task_id, title, done, _, due_at, _, urgent, important, _, _ in rows:
            if not due_at:
                continue
            try:
                due = datetime.fromisoformat(due_at)
            except ValueError:
                continue
            level = priority_level(urgent, important)
            if first <= due.date() <= last:
                by_day.setdefault(due.date(), []).append(
                    (due.strftime("%H:%M"), level, task_id, title, bool(done), task_id in overdue_ids, False))
            repeat, until, has_next = self.app.repeats.get(task_id, (None, None, False))
            if not repeat or done or has_next:
                continue  # следующий срок — уже отдельная задача, её повторы рисуются от неё
            # как в db.next_due: прошедшие сроки при выполнении пропускаются — их не показываем;
            # первый шаг считаем сразу от начала показанных недель (месяц может быть далеко от срока)
            after = max(now, datetime.combine(first, time.min) - timedelta(microseconds=1))
            try:
                first_step = db.first_step_after(due, repeat, after)
                for step in range(first_step, first_step + self.MAX_PROJECTED):
                    when = db.add_period(due, repeat, step)
                    if when.date() > last or (until and when.date().isoformat() > until):
                        break
                    by_day.setdefault(when.date(), []).append(
                        (when.strftime("%H:%M"), level, task_id, title, False, False, True))
            except (OverflowError, ValueError):  # дошли до конца календаря (9999 год)
                pass
        for items in by_day.values():
            items.sort(key=lambda item: (item[6], item[0], item[1], item[2]))
        return by_day

    def draw(self):
        if self.drag:  # строку, которую тащат, сейчас удалим — отпускания кнопки она не дождётся
            if self.drag["ghost"] is not None:
                self.drag["ghost"].destroy()
                self.configure(cursor="")
            self.drag = None
        if self.redraw_job:  # отложенная перерисовка (колёсико, размер окна) уже не нужна
            self.after_cancel(self.redraw_job)
        self.redraw_job = None
        for child in self.days.winfo_children():
            child.destroy()
        self.chips, self.cells = {}, []
        self.title.configure(text=f"{MONTHS[self.month.month - 1]} {self.month.year}")
        if self.shown is None:
            return
        _, rows, overdue_ids = self.shown
        self.due_of = {r[0]: r[4] for r in rows if r[4]}
        weeks = self.weeks()
        by_day = self.entries(rows, overdue_ids, weeks[0][0], weeks[-1][-1])
        self.drawn_fit = fit = self.fit()
        no_due = sum(1 for r in rows if not r[4] and not r[2])
        self.note.configure(text=f"Без срока: {no_due} — такие задачи видны в списке" if no_due else "")

        for column, name in enumerate(WEEKDAYS):
            tk.Label(self.days, text=name, bg=BG, fg=DANGER if column >= 5 else MUTED,
                     font=FONT_SMALL).grid(row=0, column=column, sticky="nsew", pady=(0, 1))
        self.days.rowconfigure(0, weight=0)
        today = date.today()
        for row, week in enumerate(weeks, start=1):
            self.days.rowconfigure(row, weight=1, uniform="week")
            for column, day in enumerate(week):
                self.make_day(day, row, column, by_day.get(day, []), fit, today)
        for row in range(len(weeks) + 1, 8):  # от прошлого месяца могла остаться лишняя неделя
            self.days.rowconfigure(row, weight=0, uniform="")
        for child in self.days.winfo_children():  # сама рамка self.days привязана в __init__
            bind_tree(child, "<MouseWheel>", self.wheel)
        self.highlight_selected()

    def make_day(self, day, row, column, items, fit, today):
        own = day.month == self.month.month
        bg = SURFACE if own else BG
        # рамка цвета дня не видна; когда над днём тащат задачу, она становится акцентной
        cell = tk.Frame(self.days, bg=bg, highlightthickness=2, highlightbackground=bg,
                        highlightcolor=bg)
        cell.bg = bg
        self.cells.append((day, cell))
        cell.grid(row=row, column=column, sticky="nsew", padx=(1 if column == 0 else 0, 1), pady=(0, 1))
        cell.pack_propagate(False)
        number = tk.Label(cell, text=str(day.day), bg=bg, font=FONT_SMALL_BOLD if day == today else FONT_SMALL,
                          fg=OTHER_MONTH if not own else DANGER if column >= 5 else TEXT, padx=4)
        if day == today:
            number.configure(bg=ACCENT, fg="white")
        number.pack(anchor="ne", padx=4, pady=(3, 1))
        shown = items if len(items) <= fit else items[:max(fit - 1, 0)]
        for time_text, level, task_id, title, done, overdue, projected in shown:
            self.make_chip(cell, bg, time_text, level, task_id, title, done, overdue, projected)
        if len(shown) < len(items):
            more = tk.Label(cell, text=f"ещё {len(items) - len(shown)}…", bg=bg, fg=ACCENT,
                            font=FONT_SMALL, anchor="w", cursor="hand2", padx=4)
            more.pack(fill="x", padx=2)
            more.bind("<Button-1>", lambda e, i=items: self.day_menu(i, e.x_root, e.y_root))
        for widget in (cell, number):
            widget.bind("<Button-1>", lambda e: self.app.clear_selection())
            widget.bind("<Double-Button-1>", lambda e, d=day: self.app.new_task_at(("day", d)))
            widget.bind("<Button-3>", lambda e, d=day: self.app.new_task_menu(("day", d), e.x_root, e.y_root))

    def make_chip(self, cell, bg, time_text, level, task_id, title, done, overdue, projected):
        """Задача в дне — плашка: светлый фон, рамка и полоска слева цвета приоритета
        (просроченная — красная). Выполненные и будущие повторы — бледные, без заливки."""
        text = f"{REPEAT_MARK} {time_text}  {title}" if projected else f"{time_text}  {title}"
        pale = done or projected
        color = DANGER if overdue else self.LEVEL_COLORS.get(level, ACCENT)
        fill = bg if pale else tint(color, 0.86)
        edge = BORDER if pale else tint(color, 0.55)
        chip = tk.Frame(cell, bg=fill, highlightthickness=1, highlightbackground=edge,
                        highlightcolor=edge, cursor="hand2")
        chip.pack(fill="x", padx=3, pady=(0, 2))
        tk.Frame(chip, bg=BORDER if pale else color, width=3, cursor="hand2").pack(side="left", fill="y")
        # width=1: длинный заголовок обрезается по ширине дня, а не раздвигает столбец
        label = tk.Label(chip, text=text, bg=fill, fg=DANGER if overdue else DONE if pale else TEXT,
                         font=FONT_SMALL, anchor="w", width=1, cursor="hand2", padx=4)
        label.pack(side="left", fill="x", expand=True)
        chip.bg, chip.edge, chip.label = fill, edge, label
        bind_tree(chip, "<Double-Button-1>", lambda e: (self.app.select_task(task_id), self.app.edit()))
        bind_tree(chip, "<Button-3>", lambda e: self.app.show_menu_for(task_id, e.x_root, e.y_root))
        if projected:  # будущий повтор — не отдельная задача, переносить нечего
            bind_tree(chip, "<Button-1>", lambda e: self.app.select_task(task_id))
            return
        bind_tree(chip, "<Button-1>", lambda e: self.on_press(e, task_id, chip))
        bind_tree(chip, "<B1-Motion>", self.on_motion)
        bind_tree(chip, "<ButtonRelease-1>", self.on_release)
        self.chips.setdefault(task_id, []).append(chip)

    def day_menu(self, items, x, y):
        """«ещё N…»: все задачи дня списком."""
        menu = PopupMenu()
        for time_text, _, task_id, title, _, _, projected in items:
            label = f"{REPEAT_MARK + ' ' if projected else ''}{time_text}  {short_text(title, 50)}"
            menu.command(label, lambda t=task_id: self.app.select_task(t))
        menu.popup(self.app.root, x, y)

    # --- выделение ---

    def select(self, task_id):
        self.selected_id = task_id
        self.highlight_selected()

    def highlight_selected(self):
        for task_id, chips in self.chips.items():
            for chip in chips:
                if chip.winfo_exists():
                    chosen = task_id == self.selected_id
                    chip.configure(bg=ACCENT_SOFT if chosen else chip.bg,
                                   highlightbackground=ACCENT if chosen else chip.edge)
                    chip.label.configure(bg=ACCENT_SOFT if chosen else chip.bg)

    def set_mark(self, task_id, mark):
        """Значков 📎 💬 в календаре нет — места в дне мало."""

    # --- перетаскивание задачи на другой день ---
    # Как на доске: за курсором едет полупрозрачная копия строки, день под курсором подсвечен.

    def on_press(self, event, task_id, chip):
        self.drag = {"id": task_id, "chip": chip, "start": (event.x_root, event.y_root),
                     "offset": (event.x_root - chip.winfo_rootx(), event.y_root - chip.winfo_rooty()),
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
            if not drag["chip"].winfo_exists():  # календарь успели перерисовать
                self.drag = None
                return
            drag["ghost"] = self.make_ghost(drag["chip"])
            self.configure(cursor="fleur")
        drag["pos"] = (event.x_root, event.y_root)
        if not drag["pending"]:
            drag["pending"] = True
            self.after(10, self.follow_mouse)

    def make_ghost(self, chip):
        """Полупрозрачная копия строки с задачей."""
        ghost = tk.Toplevel(self)
        ghost.withdraw()
        ghost.overrideredirect(True)
        ghost.attributes("-alpha", 0.9)
        ghost.attributes("-topmost", True)
        frame = tk.Frame(ghost, bg=SURFACE, highlightthickness=2, highlightbackground=ACCENT,
                         width=max(chip.winfo_width(), 120), height=chip.winfo_height() + 6)
        frame.pack()
        frame.pack_propagate(False)
        tk.Label(frame, text=chip.label.cget("text"),
                 bg=SURFACE, fg=TEXT, font=FONT_SMALL, anchor="w", width=1, padx=4).pack(
            fill="both", expand=True)
        ox, oy = self.drag["offset"]
        sx, sy = self.drag["start"]
        ghost.geometry(f"+{sx - ox}+{sy - oy}")
        ghost.deiconify()
        return ghost

    def day_at(self, x, y):
        """День, над которым курсор (экранные координаты), или None."""
        for day, cell in self.cells:
            if not cell.winfo_exists():
                continue
            left, top = cell.winfo_rootx(), cell.winfo_rooty()
            if left <= x < left + cell.winfo_width() and top <= y < top + cell.winfo_height():
                return day
        return None

    def mark_day(self, target):
        for day, cell in self.cells:
            if cell.winfo_exists():
                color = ACCENT if day == target else cell.bg
                cell.configure(highlightbackground=color, highlightcolor=color)

    def follow_mouse(self):
        drag = self.drag
        if not drag or drag["ghost"] is None:
            return
        drag["pending"] = False
        x, y = drag["pos"]
        ox, oy = drag["offset"]
        drag["ghost"].geometry(f"+{x - ox}+{y - oy}")
        target = self.day_at(x, y)
        if target != drag["target"]:  # подсветку меняем, только когда сменился день
            self.mark_day(target)
            drag["target"] = target

    def on_release(self, event):
        drag, self.drag = self.drag, None
        if not drag or drag["ghost"] is None:
            return
        drag["ghost"].destroy()
        self.configure(cursor="")
        self.mark_day(None)
        target = self.day_at(event.x_root, event.y_root)
        due = self.due_of.get(drag["id"])
        if target is None or not due or due[:10] == target.isoformat():
            self.highlight_selected()
            return
        # календарь перерисуется после выхода из обработчика события
        self.after_idle(lambda: self.app.move_due(drag["id"], due, target))


class TodoApp:
    # настройки высоты «Описания», выбранной ручкой: в правой панели и в отдельном окне
    DESC_KEYS = {True: "desc_lines_panel", False: "desc_lines_window"}

    def __init__(self, root, hidden=False):
        """hidden — не показывать главное окно: запустили только ради задачи из письма или снимка."""
        self.root = root
        self.hidden = hidden
        # Окно прячем, пока всё не построено: иначе на секунду мелькает пустое чёрное окно
        root.withdraw()
        # self.prefs — основной файл: настройки и личный список; self.conn — текущий список задач
        self.prefs = db.connect()
        self.smart_on = db.get_setting(self.prefs, "smart_hints", "1") == "1"  # умные подсказки
        # высота «Описания» в форме задачи, выбранная ручкой под полем
        TaskForm.desc_lines = {}  # отдельно для правой панели и для окна
        for compact, key in self.DESC_KEYS.items():
            try:
                saved = int(db.get_setting(self.prefs, key, "") or "-")
            except ValueError:  # настройки нет или в ней не число
                continue
            TaskForm.desc_lines[compact] = min(max(saved, TaskForm.DESC_LINES_MIN),
                                               TaskForm.DESC_LINES_MAX)
        TaskForm.remember_desc = lambda compact, lines: db.set_setting(  # None — забыть
            self.prefs, self.DESC_KEYS[compact], str(lines) if lines else "")
        self.list_conns = {db.PERSONAL: self.prefs}  # открытые списки: id -> соединение
        self.team, self.team_error = None, None      # общая папка (team.Team), если подключена
        self.probe = None      # фоновая проверка связи с общей папкой (team.Probe)
        self.lost_list = None  # общий список, который был открыт, когда пропала связь
        self.reconnect_at = 0  # раньше этого времени (monotonic) не пытаемся переподключиться
        self.connecting = False  # общую папку из настроек сейчас открывают в фоне
        self.connect_attempt = 0  # номер последней такой попытки (ответы прежних — не в счёт)
        # что видела фоновая проверка (team.Probe) в прошлый раз — чтобы заметить чужие изменения
        self.seen_seq, self.team_counter, self.list_counter = None, None, None
        self.own_credit, self.credit_until = 0, 0  # свои записи, ещё не замеченные проверкой
        # список на этом компьютере мог изменить телефон (через значок в трее) — см. check_local_changes
        self.local_version, self.local_check_at = None, 0
        self.reminders_due = False  # пора проверить напоминания в общих списках
        self.connect_team(wait=True)
        self.load_lists()
        self.list_id = db.get_setting(self.prefs, "current_list", db.PERSONAL)
        self.all_rows = []   # все задачи открытого списка (читаются в refresh)
        self.done_today = 0
        self.authors = {}    # id задачи -> инициатор (в общих списках)
        self.units, self.unit_names = {}, {}  # справочник бизнес-единиц; id задачи -> её единица
        self.extra_counts = {}  # id задачи -> (файлов, комментариев)
        self.mail_ids = set()   # задачи, созданные из писем Outlook (значок 📧)
        self.repeats = {}       # повторяющиеся задачи: id -> (повтор, до, есть следующая) (значок 🔁)
        self.assignees = {}  # id задачи -> исполнитель (в общих списках)
        try:
            self.conn = self.list_conn(self.list_id)
            db.list_statuses(self.conn)
        except (StopIteration, sqlite3.Error):  # списка больше нет или общая папка недоступна
            self.forget_list(self.list_id)
            if self.team is None:  # общий список — предложим открыть, когда связь появится
                self.lost_list = self.list_id
            self.list_id, self.conn = db.PERSONAL, self.prefs
        self.due = {}         # id строки таблицы -> срок (для подсветки просроченных)
        self.row_status = {}  # id строки таблицы -> название статуса
        self.statuses = {}    # id статуса -> (название, цвет, выполнено ли)

        root.title(APP_NAME)
        if ICON_PATH.exists():
            root.iconbitmap(default=str(ICON_PATH))  # иконка для всех окон программы
        setup_style(root)
        setup_text_editing(root)
        # тёмная тема — тёмные заголовки у главного окна и у всех остальных окон программы
        root.bind_class("Toplevel", "<Map>", lambda e: dark_titlebar(e.widget)
                        if isinstance(e.widget, tk.Toplevel) else None, add="+")
        load_images()
        center_on_screen(root, 1290, 720)
        root.minsize(820, 480)

        page = ttk.Frame(root, padding=(24, 14, 24, 20))
        page.pack(fill="both", expand=True)

        # Заголовок, счётчики-«таблетки», меню и справка
        header = ttk.Frame(page)
        header.pack(fill="x", pady=(4, 0))
        # Логотип: значок программы и название. Игра слов ToDo + Totoro: «ToDo» — обычным цветом,
        # «ro» — фирменным бирюзовым цветом значка
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        if "logo" in IMAGES:
            tk.Label(brand, image=IMAGES["logo"], bg=BG, bd=0).pack(side="left", padx=(0, 10))
        for part, color in (("ToDo", TEXT), ("ro", BRAND)):
            tk.Label(brand, text=part, bg=BG, fg=color, font=("Segoe UI Semibold", 20), bd=0,
                     padx=0, pady=0).pack(side="left")
        # Переключатель списков: «Личный ▾», «Команда ▾» …
        self.list_button = ttk.Button(header, style="TButton", cursor="hand2",
                                      command=self.show_lists_menu)
        self.list_button.pack(side="left", padx=(16, 0), pady=(4, 0))
        chips = ttk.Frame(header)
        chips.pack(side="left", padx=(18, 0), pady=(6, 0))
        self.chips = {}
        for key, bg, fg in (("active", CHIP_BG, MUTED), ("done", CHIP_BG, MUTED),
                            ("today", CHIP_GOOD_BG, GOOD_TEXT)):
            chip = tk.Label(chips, bg=bg, fg=fg, font=FONT_SMALL, padx=10, pady=3)
            chip.pack(side="left", padx=(0, 6))
            self.chips[key] = chip
        self.menu_button = menu_button(header, "☰  Меню", self.build_main_menu)
        self.menu_button.pack(side="right")
        # Задача из письма Outlook или со снимком экрана (сама задача добавляется строкой
        # «＋ Добавить задачу» в колонке, четверти или над списком)
        new_from = ttk.Frame(header)
        new_from.pack(side="right", padx=(0, 10), pady=(4, 0))
        self.new_from = new_from
        self.mail_button = ttk.Button(new_from, text="✉  Из письма", style="TButton",
                                      command=self.from_outlook, cursor="hand2")
        self.mail_button.pack(side="left")
        self.snip_button = ttk.Button(new_from, text="✂  Снимок", style="TButton",
                                      command=self.from_screen, cursor="hand2")
        self.snip_button.pack(side="left", padx=(8, 0))
        self.quick_draft = None  # недописанная задача в «＋ Добавить задачу» (см. QuickAdd)
        self.fresh_ids = []  # задачи, добавленные, пока окно открыто, — стоят первыми (fresh_first)

        # Вид (список, доска или матрица), фильтр и сортировка
        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(16, 12))
        # Полоса-уведомление над видами (связь с общей папкой, умные подсказки); обычно скрыта
        self.banner = Banner(page, before=toolbar)
        self.view = tk.StringVar(value=db.get_setting(self.prefs, "view", "list"))
        views = ttk.Frame(toolbar, style="Segments.TFrame", padding=3)
        views.pack(side="left")
        self.views_frame = views
        for value, text in (("list", "☰  Список"), ("board", "▦  Доска"), ("matrix", "⊞  Матрица"),
                            ("calendar", "▤  Календарь")):
            ttk.Radiobutton(views, text=text, value=value, variable=self.view,
                            style="Segment.TRadiobutton", command=self.switch_view,
                            cursor="hand2").pack(side="left")
        filters = ttk.Frame(toolbar, style="Segments.TFrame", padding=3)
        filters.pack(side="left", padx=(12, 0))
        self.filter = tk.StringVar(value="Активные" if self.view.get() == "matrix" else "Все")
        for name in FILTERS:
            button = ttk.Radiobutton(filters, text=name, value=name, variable=self.filter,
                                     style="Segment.TRadiobutton", command=self.refresh,
                                     cursor="hand2")
            button.pack(side="left")
        self.overdue_button = button  # последняя кнопка; на ней — число просроченных задач
        # «Мои задачи» — только назначенные на меня (виден в общих списках)
        self.only_mine = tk.BooleanVar(value=False)
        self.mine_frame = ttk.Frame(toolbar, style="Segments.TFrame", padding=3)
        ttk.Checkbutton(self.mine_frame, text="Мои задачи", variable=self.only_mine,
                        style="Segment.TCheckbutton", command=self.refresh,
                        cursor="hand2").pack(side="left")
        self.filters_frame = filters
        # Поиск задач по тексту (Ctrl+F): заголовок, описание, номер, инициатор, исполнитель
        self.search_query = ""
        self.search_after = None
        search = tk.Frame(toolbar, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                          highlightcolor=ACCENT)
        tk.Label(search, text="\uE721", bg=SURFACE, fg=MUTED, font=("Segoe MDL2 Assets", 10)).pack(
            side="left", padx=(8, 2))
        self.search = tk.Entry(search, relief="flat", bg=SURFACE, fg=DONE, font=FONT_SMALL, width=20,
                               insertbackground=TEXT, highlightthickness=0, borderwidth=0)
        self.search.pack(side="left", ipady=5, padx=(2, 4))
        self.search_clear = tk.Label(search, text="✕", bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                                     cursor="hand2")
        self.search_clear.bind("<Button-1>", lambda e: self.clear_search())
        self.search.insert(0, SEARCH_HINT)
        self.search.bind("<FocusIn>", lambda e: self.search_focus())
        self.search.bind("<FocusOut>", lambda e: self.search_blur())
        self.search.bind("<KeyRelease>", lambda e: self.search_typed())
        self.search.bind("<Escape>", lambda e: (self.clear_search(), "break")[1])
        self.search.bind("<Return>", lambda e: self.search_typed(now=True))
        self.search_box = search
        self.sort = ttk.Combobox(toolbar, values=SORTS, state="readonly", width=27, font=FONT_SMALL)
        self.sort.set(SORTS[0])
        self.sort.pack(side="right")
        self.sort.bind("<<ComboboxSelected>>", lambda e: self.sort_chosen())
        ttk.Label(toolbar, text="Сортировка:", style="Muted.TLabel").pack(side="right", padx=(0, 8))
        search.pack(side="right", padx=(0, 16))
        self.card_fields = db.get_json_setting(self.prefs, "card_fields", DEFAULT_CARD_FIELDS)
        for key in ("author", "assignee"):  # поля появились в 1.5 — включаем их один раз
            if not db.get_setting(self.prefs, f"card_{key}_added"):
                if key not in self.card_fields:
                    self.card_fields.append(key)
                    db.set_json_setting(self.prefs, "card_fields", self.card_fields)
                db.set_setting(self.prefs, f"card_{key}_added", "1")
        self.toolbar = toolbar

        # Середина окна: таблица или доска, справа — Тоторо, карточка или форма задачи.
        # Между ними — разделитель: потянув его мышью, можно менять ширину правой панели.
        content = tk.PanedWindow(page, orient="horizontal", bg=BG, bd=0, sashwidth=12,
                                 sashrelief="flat", opaqueresize=True, sashcursor="sb_h_double_arrow")
        content.pack(fill="both", expand=True)
        self.paned = content
        # Над разделителем Tk включает курсор ⟷ для всей средней части окна, а вернуть обычный
        # может «забыть» — например, если при запуске разделитель проехал под неподвижной мышью.
        # Тогда ⟷ виден над всеми задачами и кнопками. Возвращаем обычный курсор сами, как
        # только мышь ушла с разделителя (в том числе на задачи и панель).
        content.bind("<Leave>", lambda e: self.reset_cursor(), add="+")
        self.side = SidePanel(content, on_task_click=self.reveal_task,
                              on_close=self.clear_selection, on_edit=self.edit, on_email=self.email,
                              on_toggle=self.toggle, on_delete=self.delete, extras=self,
                              on_collapse=self.toggle_side_panel)
        self.panel_width = int(db.get_setting(self.prefs, "panel_width", PANEL_WIDTH))
        # Панель можно свернуть в узкую полоску (кнопка «»», Ctrl+B или разделитель — к краю окна)
        self.side_strip = SideStrip(content, on_expand=self.toggle_side_panel)
        self.side_collapsed = db.get_setting(self.prefs, "panel_collapsed", "0") == "1"
        self.side_room = True  # окно достаточно широкое для панели
        self.side.totoro.animate = db.get_setting(self.prefs, "totoro_animate", "1") == "1"
        # В узком окне панель прячется, чтобы не теснить таблицу
        content.bind("<Configure>", self.fit_side_panel)
        content.bind("<ButtonRelease-1>", self.sash_released)
        self.editing = None  # id задачи, которая сейчас редактируется в правой панели

        card = tk.Frame(content, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        self.table_card = card
        inner = ttk.Frame(card, style="Card.TFrame", padding=(6, 4, 4, 6))
        inner.pack(fill="both", expand=True)
        self.list_quick = QuickAdd(inner, self, None, SURFACE)
        self.list_quick.pack(side="top", fill="x", padx=(2, 4), pady=(2, 4))
        self.scrollbar = ttk.Scrollbar(inner, orient="vertical")
        columns = {
            "num": ("№", 52, False),
            "status": ("СТАТУС", 140, False),
            "marks": ("📎 💬", 100, False),  # 📧 из письма, 📎 файлы, 💬 комментарии
            "title": ("ЗАДАЧА", 220, False),
            "priority": ("ПРИОРИТЕТ", 130, False),
            "due": ("СРОК", 125, False),
            "remind": ("НАПОМНИТЬ", 105, False),
            # Растягивается последний столбец: если бы растягивалась «Задача», Tk сразу
            # возвращал бы ей всё свободное место и её ширину нельзя было бы изменить.
            "assignee": ("ИСПОЛНИТЕЛЬ", 120, False),  # виден только в общих списках
            "author": ("ИНИЦИАТОР", 124, False),          # тоже
            "unit": ("БИЗНЕС-ЕДИНИЦА", 150, False),       # виден, если справочник списка не пуст
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
        if widths and "marks" not in widths and "title" in widths:
            # столбец значков появился после 2.18: место для него берём у «Задачи», а не у окна
            widths["title"] = max(widths["title"] - columns["marks"][1], 150)
        self.column_titles = {key: text for key, (text, _, _) in columns.items()}
        # Столбцы можно переставлять, перетащив заголовок; порядок запоминается
        self.default_columns = list(columns)
        self.column_order = merge_column_order(
            db.get_json_setting(self.prefs, "list_column_order", None), self.default_columns)
        self.tree["displaycolumns"] = self.column_order
        self.column_drag = None  # перетаскиваемый столбец: dict(column, x, moved)
        self.drop_line = tk.Frame(self.tree, bg=ACCENT, width=3)
        for key, (text, width, stretch) in columns.items():
            # Щелчок по заголовку столбца сортирует по нему, повторный — в обратном порядке
            self.tree.heading(key, text=text, anchor="w",
                              command=lambda k=key: self.sort_by_column(k))
            self.tree.column(key, width=widths.get(key, width), minwidth=40, stretch=stretch)
        # Сортировка по столбцу: [столбец, по убыванию ли] или None — тогда работает список «Сортировка»
        self.column_sort = db.get_json_setting(self.prefs, "list_sort", None)
        if not (isinstance(self.column_sort, list) and len(self.column_sort) == 2
                and self.column_sort[0] in self.column_titles):
            self.column_sort = None  # столбца больше нет (или настройка испорчена) — обычная сортировка
        self.show_column_sort()
        # Пока ширины не настраивали — «Задача» занимает всё свободное место таблицы
        self.columns_fitted = bool(widths)
        self.tree.bind("<Configure>", self.fit_columns, add="+")
        self.resizing_column = False
        self.tree.bind("<ButtonPress-1>", lambda e: setattr(
            self, "resizing_column", self.tree.identify_region(e.x, e.y) == "separator"), add="+")
        self.tree.tag_configure("hover", background=ROW_HOVER)
        self.hover_row = None
        self.tree.bind("<Motion>", self.tree_motion)
        self.tree.bind("<Leave>", lambda e: (self.set_hover(None), self.hide_title_tip()))
        # подсказка с полным названием задачи, если оно не помещается в столбец
        self.tree_font = tkfont.Font(root=root, font=FONT)
        self.tip_row = self.tip_job = self.tip_window = None
        for sequence in ("<ButtonPress-1>", "<ButtonPress-3>", "<MouseWheel>", "<KeyPress>"):
            self.tree.bind(sequence, self.hide_title_tip, add="+")
        self.tree.bind("<ButtonRelease-1>", self.save_column_widths, add="+")
        self.tree.bind("<ButtonPress-1>", self.column_drag_start, add="+")
        self.tree.bind("<B1-Motion>", self.column_drag_move, add="+")
        self.tree.bind("<ButtonRelease-1>", self.column_drag_end, add="+")
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
        self.matrix = EisenhowerMatrix(content, self)
        self.calendar = CalendarView(content, self)

        # Клавиши работают и в списке, и на доске (но не во время набора текста)
        for sequence, action in (("<F2>", self.edit), ("<space>", self.toggle),
                                 ("<Delete>", self.delete), ("<Control-e>", self.email),
                                 ("<Control-E>", self.email), ("<Escape>", self.clear_selection)):
            root.bind(sequence, lambda e, a=action: self.key_action(e, a))
        root.bind("<F1>", lambda e: self.show_help())
        root.bind("<Control-KeyPress>", self.paste_key, add="+")
        root.bind("<Control-KeyPress>", self.side_panel_key, add="+")
        for key in ("<Control-f>", "<Control-F>"):
            root.bind(key, lambda e: (self.search.focus_set(), "break")[1])
        for key in ("<Control-n>", "<Control-N>"):
            root.bind(key, lambda e: (self.quick_add_here(), "break")[1])
        self.help_window = None

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self.on_error
        self.show_main_widget()
        self.show_list_name()
        self.refresh()
        self.tour = None
        if not hidden:
            self.show_window()
        root.after(1000, self.check_reminders)
        start_hotkey(root, [(OUTLOOK_HOTKEY, lambda: self.from_outlook(quiet=True)),  # Ctrl+Alt+T
                            (SNIP_HOTKEY, lambda: self.from_screen(quiet=True))])     # Ctrl+Alt+S
        self.start_tray()
        threading.Thread(target=clean_temp_files, daemon=True).start()  # старые черновики и копии файлов
        root.after(WATCH_EVERY_MS, self.watch_changes)  # изменения других участников в общих списках
        if self.team is None and db.get_setting(self.prefs, "shared_folder", ""):
            self.show_offline_banner()  # запустились без связи с общей папкой

    def show_window(self):
        """Показывает главное окно — при запуске или позже, если программу запустили скрытой."""
        root = self.root
        self.hidden = False
        # Всё построено — показываем окно сразу готовым
        root.update_idletasks()
        dark_titlebar(root)  # тёмный заголовок — ещё до показа окна, иначе он остаётся белым
        if db.get_setting(self.prefs, "start_mode", "window") == "maximized":
            root.state("zoomed")  # развёрнуто на весь экран; «восстановить» вернёт обычное окно
        else:
            root.deiconify()
        # После обновления ToDoro запускает установщик и сразу закрывается — Windows тогда
        # открывает окно позади других (или свёрнутым). Выводим его вперёд сами.
        root.after(150, self.raise_on_start)
        root.after(200, self.repaint)  # ещё раз, когда окно уже показано
        root.after(600, self.reset_cursor)  # и обычный курсор — на случай, если ⟷ «залип» при запуске
        root.after(4000, self.auto_check_update)  # раз в день — нет ли новой версии
        if db.get_setting(self.prefs, "tour_show", "1") == "1":
            root.after(700, self.start_tour)  # первый запуск (или тур не отключили) — тур

    def raise_on_start(self):
        root = self.root
        if root.state() == "iconic":
            maximized = db.get_setting(self.prefs, "start_mode", "window") == "maximized"
            root.state("zoomed" if maximized else "normal")
        bring_to_front(root)

    # --- список, доска или матрица ---

    def main_widget(self):
        return self.cards_view() or self.table_card

    def cards_view(self):
        """Доска, матрица или календарь, если показан один из них, иначе (список) None."""
        return {"board": self.board, "matrix": self.matrix, "calendar": self.calendar}.get(self.view.get())

    def dragging(self):
        return bool(self.board.drag or self.matrix.drag or self.calendar.drag)

    def in_paned(self, widget):
        return str(widget) in (str(p) for p in self.paned.panes())

    # --- таблица: ширина столбцов и подсветка строки под мышью ---

    def tree_motion(self, event):
        region = self.tree.identify_region(event.x, event.y)
        # На разделителе столбцов курсор показывает, что ширину можно менять
        self.tree.configure(cursor="sb_h_double_arrow" if region == "separator" else "")
        self.set_hover(self.tree.identify_row(event.y) if region in ("cell", "tree") else None)
        self.title_tip(event, region)

    def title_tip(self, event, region):
        """Название задачи не помещается в столбец — через полсекунды под мышью появится
        подсказка с полным названием."""
        row = self.tree.identify_row(event.y) if region == "cell" else ""
        column = self.tree.identify_column(event.x)
        shown = self.tree["displaycolumns"]
        shown = self.tree["columns"] if tuple(shown) == ("#all",) else shown
        index = int(column[1:]) - 1 if column[1:].isdigit() else -1
        key = row if row and 0 <= index < len(shown) and shown[index] == "title" else None
        if key == self.tip_row:
            return
        self.hide_title_tip()
        self.tip_row = key
        if key is None:
            return
        text = self.tree.set(key, "title")
        if self.tree_font.measure(text) + 14 > self.tree.column("title", "width"):
            self.tip_job = self.root.after(500, lambda: self.show_title_tip(text))

    def show_title_tip(self, text):
        self.tip_job = None
        tip = self.tip_window = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(tip, text=text, bg=SURFACE, fg=TEXT, font=FONT_SMALL, justify="left",
                 wraplength=520, padx=10, pady=6, highlightthickness=1,
                 highlightbackground=POPUP_BORDER).pack()
        tip.geometry(f"+{self.root.winfo_pointerx() + 12}+{self.root.winfo_pointery() + 20}")

    def hide_title_tip(self, event=None):
        self.tip_row = None
        if self.tip_job:
            self.root.after_cancel(self.tip_job)
            self.tip_job = None
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None

    def set_hover(self, row):
        if row == self.hover_row:
            return
        for item, add in ((self.hover_row, False), (row, True)):
            if item and self.tree.exists(item):
                tags = [t for t in self.tree.item(item, "tags") if t != "hover"]
                self.tree.item(item, tags=tags + (["hover"] if add else []))
        self.hover_row = row

    # --- перестановка столбцов перетаскиванием заголовка ---

    def shown_columns(self):
        shown = self.tree["displaycolumns"]
        return list(self.tree["columns"] if tuple(shown) == ("#all",) else shown)

    def column_edges(self):
        """Левые края и ширины видимых столбцов в координатах таблицы (с учётом прокрутки)."""
        shown = self.shown_columns()
        widths = [self.tree.column(c, "width") for c in shown]
        total = self.tree.column("#0", "width") + sum(widths)
        left = self.tree.column("#0", "width") - round(self.tree.xview()[0] * total)
        lefts = []
        for width in widths:
            lefts.append(left)
            left += width
        return lefts, widths

    def column_drag_start(self, event):
        self.column_drag = None
        self.drop_line.place_forget()  # на случай, если прошлое отпускание мыши потерялось
        self.tree.configure(cursor="")
        if self.tree.identify_region(event.x, event.y) != "heading":
            return
        column = self.tree.identify_column(event.x)  # '#1', '#2'… — номер среди видимых
        shown = self.shown_columns()
        index = int(column[1:]) - 1 if column[1:].isdigit() else -1
        if 0 <= index < len(shown):
            self.column_drag = dict(column=shown[index], x=event.x, moved=False)

    def column_drag_move(self, event):
        drag = self.column_drag
        if not drag:
            return
        if not drag["moved"] and abs(event.x - drag["x"]) < 8:
            return  # дрогнула рука при щелчке — это ещё не перетаскивание
        drag["moved"] = True
        self.tree.configure(cursor="fleur")
        lefts, widths = self.column_edges()
        place = drop_index(lefts, widths, self.visible_x(event.x))
        x = lefts[place] if place < len(lefts) else lefts[-1] + widths[-1]
        self.drop_line.place(x=max(x - 1, 0), y=0, relheight=1)
        self.drop_line.lift()

    def column_drag_end(self, event):
        drag = self.column_drag
        if not drag or not drag["moved"]:
            self.column_drag = None
            return
        self.drop_line.place_forget()
        self.tree.configure(cursor="")
        lefts, widths = self.column_edges()
        shown = self.shown_columns()
        place = drop_index(lefts, widths, self.visible_x(event.x))
        # место считаем без самого перетаскиваемого столбца
        if place > shown.index(drag["column"]):
            place -= 1
        order = move_column(self.column_order, drag["column"], place, shown)
        if order != self.column_order:
            self.set_column_order(order)
        # щелчок по заголовку (сортировка) срабатывает после отпускания — пусть он увидит
        # «тянули», а потом флаг сбросится
        self.root.after_idle(lambda: setattr(self, "column_drag", None))

    def visible_x(self, x):
        """Мышь за краем таблицы считаем у края: столбец не должен встать туда, где его не видно."""
        return min(max(x, 0), self.tree.winfo_width())

    def set_column_order(self, order):
        self.column_order = order
        shown = set(self.shown_columns())
        self.tree["displaycolumns"] = [c for c in order if c in shown]
        db.set_json_setting(self.prefs, "list_column_order",
                            None if order == self.default_columns else order)

    def show_heading_menu(self, event):
        """Правая кнопка по заголовку таблицы: вернуть обычный порядок столбцов."""
        (PopupMenu()
         .command("Вернуть порядок столбцов", lambda: self.set_column_order(list(self.default_columns)),
                  enabled=self.column_order != self.default_columns)
         ).popup(self.root, event.x_root, event.y_root)

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
        """Слева в разделителе — таблица, доска или матрица, справа — панель."""
        main = self.main_widget()
        for other in (self.table_card, self.board, self.matrix, self.calendar):
            if other is not main and self.in_paned(other):
                self.paned.forget(other)
        if not self.in_paned(main):
            right = [w for w in (self.side, self.side_strip) if self.in_paned(w)]
            if right:
                self.paned.add(main, before=right[0], stretch="always", minsize=420)
            else:
                self.paned.add(main, stretch="always", minsize=420)
        self.place_side()

    def show_settings(self, page="general"):
        if self.team and not self.share_online():  # связь пропала, а watch_changes ещё не заметил
            self.go_offline()
        if self.team:
            try:
                status = ("ok", "Подключено. Участники: " + ", ".join(self.team.members()))
            except sqlite3.Error as error:
                status = ("error", " ".join(str(error).split()))
        elif self.team_error:
            status = ("error", " ".join(self.team_error.split()))
        else:
            status = ("off", "Не подключено — общие списки недоступны.")
        dialog = SettingsDialog(
            self.root, db.get_setting(self.prefs, "start_mode", "window"), self.card_fields,
            self.auto_update_enabled(), db.get_setting(self.prefs, "shared_folder", ""),
            db.get_setting(self.prefs, "user_name", "") or os.environ.get("USERNAME", ""),
            status, page, check_folder=self.check_folder, check_update=self.check_update_inline,
            animate=self.side.totoro.animate, theme=THEME_SETTING,
            tour=db.get_setting(self.prefs, "tour_show", "1") == "1",
            tray_on=tray.autostart_enabled(), smart_on=self.smart_on)
        result = dialog.show()
        if dialog.update_found:  # нашли новую версию кнопкой в настройках
            UpdateDialog(self.root, dialog.update_found, self.close)
        if result is None:
            return
        db.set_setting(self.prefs, "start_mode", result["start_mode"])
        db.set_setting(self.prefs, "update_auto", "1" if result["update_auto"] else "0")
        db.set_setting(self.prefs, "totoro_animate", "1" if result["animate"] else "0")
        db.set_setting(self.prefs, "tour_show", "1" if result["tour"] else "0")
        db.set_setting(self.prefs, "smart_hints", "1" if result["smart"] else "0")
        self.smart_on = result["smart"]
        if result["tray"] != tray.autostart_enabled():
            if not tray.set_autostart(result["tray"]):
                ui.showerror("Значок в трее", "Не удалось изменить автозапуск в реестре Windows.",
                             parent=self.root)
            elif result["tray"]:
                tray.start()
            else:
                tray.stop()
        self.side.totoro.animate = result["animate"]
        self.side.totoro.render_frame(force=True)
        if result["theme"] != THEME_SETTING:
            db.set_setting(self.prefs, "theme", result["theme"])
            if ui.askyesno("Тема оформления", f"Тема «{THEMES[result['theme']]}» включится после "
                           "перезапуска программы.\n\nПерезапустить сейчас? Задачи и правки "
                           "сохранятся.", parent=self.root):
                self.restart()
                return
        if result["card_fields"] != self.card_fields:
            self.card_fields = result["card_fields"]
            db.set_json_setting(self.prefs, "card_fields", self.card_fields)
            self.refresh(select_id=self.current_id())
        old = (db.get_setting(self.prefs, "shared_folder", ""), db.get_setting(self.prefs, "user_name", ""))
        if (result["shared_folder"], result["user_name"]) != old:
            db.set_setting(self.prefs, "shared_folder", result["shared_folder"])
            db.set_setting(self.prefs, "user_name", result["user_name"])
            for item in [i for i in self.lists if i["shared"]]:
                if item["id"] != self.list_id:
                    self.forget_list(item["id"])
            if result["shared_folder"].strip():
                self.banner.show("wait", "Подключаюсь к общей папке… Можно работать дальше.")
            self.connect_team_in_background(self.team_connected)

    def team_connected(self, error):
        """Общая папка из настроек подключилась (или нет) — см. connect_team_in_background."""
        self.load_lists()
        if not any(i["id"] == self.list_id for i in self.lists):  # открытый общий список пропал
            self.forget_list(self.list_id)
            self.list_id = None
            self.switch_list(db.PERSONAL)
        self.banner.hide()
        if error:
            ui.showerror(APP_NAME, error, parent=self.root)
            self.show_offline_banner()  # подключимся сами, когда папка станет доступна
        elif self.team:
            ui.showinfo(APP_NAME, "Общая папка подключена. Общие списки — в меню "
                                "списков (кнопка с названием списка вверху).", parent=self.root)

    def check_folder(self, folder, done):
        """Кнопка «Проверить подключение» в настройках: открывается ли папка и кто в ней."""
        def work():
            test = team.Team(folder)
            try:
                return test.members()
            finally:
                test.close()

        def finished(members, error):
            if error:
                done(("error", " ".join(str(error).split())))
            elif members:
                done(("ok", "Папка доступна. Участники: " + ", ".join(members)))
            else:
                done(("ok", "Папка доступна. Участников пока нет — вы будете первым."))
        in_background(self.root, work, finished)

    def check_update_inline(self, done):
        """Кнопка «Проверить сейчас» в настройках."""
        def finished(release, error):
            if error:
                done(str(error))
            elif updater.is_newer(release["version"], APP_VERSION):
                done(f"Доступна версия {release['version']}. Окно обновления откроется, когда вы "
                     "закроете настройки.", release)
            else:
                done(f"У вас последняя версия — {APP_VERSION}.")
        in_background(self.root, updater.fetch_latest, finished)

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
                 .command("Что нового…", self.show_whats_new)
                 .command("Лицензия (MIT)…", self.show_license)
                 .command(f"О программе {APP_NAME}…", self.show_about))
        return (PopupMenu()
                .command("Напоминания и просроченные…", self.show_reminders)
                .separator()
                .command("Задача из письма Outlook", self.from_outlook, accel=OUTLOOK_HOTKEY_NAME)
                .command("Задача со снимка экрана", self.from_screen, accel=SNIP_HOTKEY_NAME)
                .command("Добавить колонку на доску…", self.add_lane)
                .command("Бизнес-единицы…", self.show_units)
                .command("Подключить телефон…", self.show_phone)
                .command("Развернуть правую панель" if self.side_collapsed else "Свернуть правую панель",
                         self.toggle_side_panel, accel="Ctrl+B", enabled=self.side_room)
                .submenu("Экспорт и импорт", data)
                .submenu("Примеры задач", examples)
                .separator()
                .command("Настройки…", self.show_settings)
                .separator()
                .command("Справка", self.show_help, accel="F1")
                .command("Ознакомительный тур", self.start_tour)
                .command("Проверить обновления…", self.check_update_now)
                .submenu("Обратная связь", feedback)
                .submenu("О программе", about))

    # --- ознакомительный тур ---

    def tour_steps(self):
        """Шаги тура: (какой виджет обвести, заголовок, текст). Первый и последний — без виджета."""
        return [
            (lambda: None, f"Добро пожаловать в {APP_NAME}!",
             "Привет! Я Тоторо и помогу не забывать о делах.\n\n"
             "За минуту покажу главное. Тур можно пропустить и открыть потом: "
             "«☰ Меню» → «Ознакомительный тур»."),
            (self.tour_quick_add, "Новая задача",
             "Нажмите «＋ Добавить задачу» (или Ctrl+N), впишите название и нажмите Enter. "
             "Такая строка есть над списком, в каждой колонке доски и в каждой четверти "
             "матрицы — задача сразу попадает туда. Правая кнопка мыши по пустому месту "
             "колонки, четверти или дня календаря — «Новая задача…» с полной формой.\n\n"
             "Срок и «срочно» можно написать прямо в названии: «Сдать отчёт завтра в 10 "
             "срочно». Я подскажу похожие названия из ваших прошлых задач."),
            (lambda: self.new_from, "Из письма и со снимка",
             "Поручение пришло письмом? Выделите его в Outlook и нажмите Ctrl+Alt+T "
             "(или «Из письма» здесь) — задача заполнится по письму. Ctrl+Alt+S (или «Снимок») — "
             "задача со снимком выделенной области экрана."),
            (self.main_widget, "Ваши задачи",
             "Щелчок по задаче открывает её карточку справа, двойной щелчок или F2 — изменить, "
             "пробел — отметить выполненной. Правая кнопка мыши — быстрые действия: срок, "
             "важность, срочность, письмо. Значки 📎 и 💬 — у задачи есть файлы и комментарии, "
             "📧 — задача создана из письма Outlook."),
            (lambda: self.side, "Карточка задачи и Тоторо",
             "Справа — карточка выбранной задачи: важность, срочность, срок, напоминание "
             "и описание. На вкладке «Файлы» можно приложить документы и картинки "
             "(снимок экрана — Ctrl+V), на вкладке «Комментарии» — обсудить задачу. "
             "Пока задача не выбрана, Тоторо подсказывает, с чего начать, "
             "и волнуется о просроченных делах. Кнопка «»» (или Ctrl+B) сворачивает "
             "панель в узкую полоску."),
            (lambda: self.views_frame, "Список, доска, матрица и календарь",
             "Список — таблица задач. Доска — колонки по статусам, задачи перетаскиваются "
             "мышью. Матрица Эйзенхауэра раскладывает задачи по важности и срочности. "
             "Календарь показывает задачи по срокам на месяц вперёд — перетащите задачу на "
             "другой день, и срок перенесётся."),
            (lambda: self.filters_frame, "Фильтры",
             "Показывают все задачи, только активные, выполненные или просроченные. "
             "На кнопке «Просроченные» — сколько их сейчас."),
            (lambda: self.search_box, "Поиск",
             "Ищет по названию, описанию и номеру задачи. Быстро открыть — Ctrl+F."),
            (lambda: self.list_button, "Списки задач",
             "Разделяйте дела по спискам: личный, рабочий, домашний… "
             "Общие списки для команды подключаются в настройках."),
            (lambda: self.menu_button, "Меню",
             "Напоминания и просроченные задачи, настройки, задачи на телефоне, экспорт и импорт, "
             "примеры задач, "
             "справка (F1), обновления и "
             "«Что нового» в каждой версии. "
             "Отсюда же можно снова пройти этот тур."),
            (lambda: None, "Всё готово!",
             "Добавьте первую задачу — а я буду рядом. Напомню о сроках, а выполненные "
             "задачи увезёт Котобус."),
        ]

    def start_tour(self):
        if self.tour is not None and self.tour.tip.winfo_exists():
            self.tour.tip.lift()
            return
        if self.editing is not None:
            self.finish_editing()
        hide = db.get_setting(self.prefs, "tour_show", "1") == "0"
        self.tour = GuideTour(self.root, self.tour_steps(), self.tour_closed, hide_next_time=hide)

    def tour_closed(self, show_next_time):
        db.set_setting(self.prefs, "tour_show", "1" if show_next_time else "0")
        self.tour = None

    def send_feedback(self, kind):
        """Открывает на GitHub форму сообщения об ошибке или идеи (раздел Issues)."""
        if not ui.askokcancel(
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
            self.side.totoro.cheer()

    def switch_view(self):
        db.set_setting(self.prefs, "view", self.view.get())
        self.quick_draft = None  # недописанное в колонке не переезжает в другой вид
        if self.view.get() == "matrix":
            self.filter.set("Активные")  # выполненным в матрице делать нечего
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
        if self.cards_view():
            return self.cards_view().selected_id
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def select_task(self, task_id):
        if self.tree.exists(str(task_id)):
            self.tree.selection_set(str(task_id))
            self.tree.see(str(task_id))
        for view in (self.board, self.matrix, self.calendar):
            view.select(task_id)
        self.update_side()

    def on_tree_select(self):
        sel = self.tree.selection()
        if self.view.get() == "list":
            for view in (self.board, self.matrix, self.calendar):
                view.select(int(sel[0]) if sel else None)
        self.update_side()

    def clear_selection(self):
        self.tree.selection_remove(*self.tree.selection())
        for view in (self.board, self.matrix, self.calendar):
            view.select(None)
        self.update_side()

    def click_empty_space(self, event):
        """Щелчок по пустому месту таблицы снимает выделение."""
        if not self.tree.identify_row(event.y) and self.tree.identify_region(event.x, event.y) != "heading":
            self.clear_selection()

    def reveal_task(self, task_id):
        """Щелчок по задаче в облачке Тоторо: показать и выделить её."""
        if not self.tree.exists(str(task_id)):
            self.filter.set("Все")
            self.only_mine.set(False)
            self.clear_search(refresh=False)
            self.refresh()
        self.select_task(task_id)
        if self.view.get() == "list" and self.tree.exists(str(task_id)):
            self.tree.focus(str(task_id))
            self.tree.focus_set()

    # --- правая панель: Тоторо или карточка задачи ---

    def reset_cursor(self):
        """Обычный курсор в средней части окна (см. комментарий у self.paned)."""
        try:
            self.paned.configure(cursor="")
        except tk.TclError:
            pass  # окно уже закрыто

    def fit_side_panel(self, event):
        self.side_room = event.width >= 1000
        if not self.side_room:
            self.save_panel_width()
        self.place_side()

    def place_side(self):
        """Справа в разделителе — панель, полоска (панель свёрнута) или ничего (окно узкое)."""
        want = None if not self.side_room else self.side_strip if self.side_collapsed else self.side
        for widget in (self.side, self.side_strip):
            if widget is not want and self.in_paned(widget):
                self.paned.forget(widget)
        if want is self.side and not self.in_paned(self.side):
            self.paned.add(self.side, stretch="never", minsize=240, width=self.panel_width)
        elif want is self.side_strip and not self.in_paned(self.side_strip):
            self.paned.add(self.side_strip, stretch="never", minsize=SideStrip.WIDTH,
                           width=SideStrip.WIDTH)

    def toggle_side_panel(self, save_width=True):
        """Свернуть правую панель в полоску или развернуть её обратно (Ctrl+B)."""
        if not self.side_room:
            return  # в узком окне панели нет вовсе
        if not self.side_collapsed:
            if save_width:
                self.save_panel_width()
            self.finish_editing()  # несохранённые изменения в форме — спросим, сохранить ли
        self.side_collapsed = not self.side_collapsed
        db.set_setting(self.prefs, "panel_collapsed", "1" if self.side_collapsed else "0")
        self.place_side()
        if not self.side_collapsed:
            self.update_side()
        self.reset_cursor()

    def sash_released(self, event):
        """Отпустили разделитель. Утянули его почти к правому краю — панель сворачивается,
        потянули полоску влево — разворачивается. Иначе запоминаем новую ширину панели."""
        edge = self.paned.winfo_width() - event.x
        if self.in_paned(self.side) and edge < 150:
            self.toggle_side_panel(save_width=False)  # развернётся прежней ширины
        elif self.in_paned(self.side_strip):
            if edge > SideStrip.WIDTH + 80:
                self.toggle_side_panel()
            else:  # потянули чуть-чуть — полоска возвращается к своей ширине
                self.paned.forget(self.side_strip)
                self.place_side()
        else:
            self.save_panel_width()

    def save_panel_width(self):
        """Ширина правой панели запоминается (её меняют, потянув за разделитель)."""
        if self.in_paned(self.side) and self.side.winfo_width() > 1:
            self.panel_width = self.side.winfo_width()
            db.set_setting(self.prefs, "panel_width", str(self.panel_width))

    # --- изменение задачи в правой панели ---

    def form_data(self, task_id):
        title, due_at, remind_before, urgent, important, body = db.get_task(self.conn, task_id)
        meta = db.task_meta(self.conn, task_id)
        repeat, until = db.get_repeat(self.conn, task_id)
        return dict(title=title, due_at=due_at, remind_before=remind_before, urgent=urgent,
                    important=important, body=body, status_id=self.task_info(task_id)["status_id"],
                    assignee=meta["assignee"], initiator=meta["initiator"], unit_id=meta["unit_id"],
                    repeat=repeat, repeat_until=until, version=meta["version"])

    def apply_edit(self, task_id, result, refresh=True, version=None):
        """Сохраняет правку. version — номер версии на момент открытия формы (в общих списках):
        если задачу с тех пор изменил кто-то другой, ничего не сохраняет и возвращает False."""
        by = self.created_by()
        if not db.update_task(self.conn, task_id, result["title"], result["due_at"],
                              result["remind_before"], result["urgent"], result["important"],
                              result["body"], by=by, version=version):
            return False
        meta = db.task_meta(self.conn, task_id) or {}
        if "unit_id" in result and result["unit_id"] != meta.get("unit_id"):
            unit_id = result["unit_id"]
            if unit_id is not None and unit_id not in dict(db.list_units(self.conn)):
                unit_id = None  # пока форма была открыта, единицу удалили из справочника
            db.set_task_unit(self.conn, task_id, unit_id, by=by)
        if "repeat" in result and (result["repeat"], result.get("repeat_until")) != db.get_repeat(self.conn, task_id):
            db.set_repeat(self.conn, task_id, result["repeat"], result.get("repeat_until"), by=by)
        if self.members() is not None:
            if result.get("assignee") != meta.get("assignee"):
                db.set_assignee(self.conn, task_id, result.get("assignee"), by=by)
            # пустое поле — инициатором снова считается автор
            if (result.get("initiator") or meta.get("author")) != meta.get("initiator"):
                initiator = result.get("initiator")
                db.set_initiator(self.conn, task_id, None if initiator == meta.get("author") else initiator,
                                 by=by)
        if result["status_id"] != self.task_info(task_id)["status_id"]:
            if db.set_task_status(self.conn, task_id, result["status_id"], by=by):
                self.celebrate(task_id)
        if refresh:
            self.refresh(select_id=task_id)
        return True

    def save_edit(self, task_id, result):
        form = self.side.form
        version = self.edit_version if self.created_by() else None
        if self.apply_edit(task_id, result, refresh=False, version=version):
            self.editing = None
            self.refresh(select_id=task_id)
            return
        choice = self.resolve_conflict(task_id, result, form.initial if form else None, can_return=True)
        if choice == "mine":
            self.editing = None
            self.apply_edit(task_id, result)
        elif choice == "theirs":
            self.editing = None
            self.refresh(select_id=task_id)
        else:  # вернуться к правке; следующее «Сохранить» запишет поверх
            meta = db.task_meta(self.conn, task_id)
            if meta is None:
                self.editing = None
                self.refresh()
            else:
                self.edit_version = meta["version"]

    CHANGED_NAMES = {"title": "заголовок", "body": "описание", "status_id": "статус",
                     "due_at": "срок", "remind_before": "напоминание", "urgent": "«срочно»",
                     "important": "«важно»", "assignee": "исполнителя", "initiator": "инициатора",
                     "unit_id": "бизнес-единицу", "repeat": "повтор", "repeat_until": "«повторять до»"}

    def resolve_conflict(self, task_id, mine, initial, can_return):
        """Задачу, которую вы правили, тем временем изменил другой участник.
        Возвращает "mine" (сохранить мой вариант), "theirs" (оставить их) или "back"."""
        meta = db.task_meta(self.conn, task_id)
        if meta is None:
            ui.showwarning(APP_NAME, "Пока вы правили задачу, её удалил другой участник. "
                                   "Ваши изменения не сохранены.", parent=self.root)
            return "theirs"
        now = self.form_data(task_id)
        changed = [name for key, name in self.CHANGED_NAMES.items()
                   if initial is not None and (now.get(key) or None) != (initial.get(key) or None)
                   and not (key in ("urgent", "important") and bool(now.get(key)) == bool(initial.get(key)))]
        who = meta.get("updated_by") or "другой участник"
        when = datetime.fromisoformat(meta["updated_at"]).strftime("%H:%M") if meta.get("updated_at") else ""
        return ConflictDialog(self.root, short_text(mine["title"], 60), who, when, changed,
                              can_return).show()

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
        if ui.askyesno("Сохранить изменения?",
                               f"В задаче «{short_text(result['title'], 50)}» есть несохранённые "
                               "изменения. Сохранить их?", parent=self.root):
            version = self.edit_version if self.created_by() else None
            if not self.apply_edit(task_id, result, refresh=False, version=version):
                if self.resolve_conflict(task_id, result, form.initial, can_return=False) == "mine":
                    self.apply_edit(task_id, result, refresh=False)
            self.root.after_idle(lambda: self.refresh(select_id=self.current_id()))

    def task_info(self, task_id):
        """Всё о задаче для карточки справа и письма."""
        row = db.get_task_row(self.conn, task_id)
        if row is None:
            return None
        _, title, done, created, due_at, remind_before, urgent, important, body, status_id = row
        name, color, _ = self.statuses.get(status_id, ("—", MUTED, done))
        overdue = bool(due_at and not done and datetime.fromisoformat(due_at) < datetime.now())
        level = priority_level(urgent, important)
        remind = remind_label(remind_before) if due_at and remind_before else ""
        return dict(title=title, body=body, done=bool(done), overdue=overdue, status_id=status_id,
                    status=status_label(name, done, overdue), status_name=name, status_color=color,
                    level=level, priority=PRIORITY_NAMES[level], due=format_due(due_at),
                    remind=remind, created=created, urgent=urgent, important=important,
                    **self.people(task_id))

    def people(self, task_id):
        """Инициатор (по умолчанию — автор), исполнитель и «кто когда изменил» — для карточки и
        письма."""
        meta = db.task_meta(self.conn, task_id) or {}
        shared = bool(self.list_id and self.current_list()["shared"])
        updated = ""
        if shared and meta.get("updated_by"):
            when = datetime.fromisoformat(meta["updated_at"]).strftime("%d.%m %H:%M")
            updated = f"{when}, {meta['updated_by']}"
        return dict(author=meta.get("initiator") or "", assignee=meta.get("assignee") or "",
                    updated=updated, shared=shared, unit=self.unit_names.get(task_id, ""),
                    repeat=db.repeat_text(*self.repeats.get(task_id, (None, None))[:2]))

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
            due=info["due"], remind=info["remind"], created=info["created"], author=info["author"],
            assignee=info["assignee"] or ("Не назначен" if info["shared"] else ""),
            updated=info["updated"], urgent=bool(info["urgent"]), important=bool(info["important"]),
            from_mail=task_id in self.mail_ids, unit=info["unit"], repeat=info["repeat"].capitalize(),
        )

    def update_buddy(self):
        """Выбирает, что скажет Тоторо: о просроченной задаче, о задачах на сегодня и т. д."""
        now = datetime.now()
        rows = self.all_rows  # прочитаны в refresh
        active = [r for r in rows if not r[2]]
        due = {r[0]: datetime.fromisoformat(r[4]) for r in active if r[4]}
        overdue = [r for r in active if r[0] in due and due[r[0]] < now]
        today = [r for r in active if r[0] in due and now <= due[r[0]] and due[r[0]].date() == now.date()]

        def most_important(tasks):
            return min(tasks, key=lambda r: (priority_level(r[6], r[7]), due.get(r[0], datetime.max), r[0]))

        done_today = self.done_today
        stats = " · ".join(text for count, text in (
            (len(overdue), f"Просрочено: {len(overdue)}"),
            (len(today), f"На сегодня: {len(today)}"),
            (done_today, f"Сегодня выполнено: {done_today}"),
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
                       tail="Можно отдохнуть под камфорным деревом.", mood="sleep", stats=stats)

    # --- колонки доски (статусы) ---

    def add_lane(self):
        used = {color for _, color, _ in self.statuses.values()}
        color = next((c for _, c in LANE_COLORS if c not in used), LANE_COLORS[0][1])
        result = LaneDialog(self.root, color=color).show()
        if not result:
            return
        status_id = db.add_status(self.conn, result["name"], result["color"])
        if result["is_done"]:
            db.set_status_done(self.conn, status_id, True, by=self.created_by())
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
            db.set_status_done(self.conn, status_id, result["is_done"], by=self.created_by())
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
         .command("＋  Новая задача…", lambda: self.new_task_at(("status", status_id)))
         .separator()
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
        if ui.askyesno("Удалить колонку?", f"Удалить колонку «{name}»?{moved}",
                               icon="warning", default="no", parent=self.root):
            db.delete_status(self.conn, status_id, target, by=self.created_by())
            self.refresh(select_id=self.current_id())

    def move_task(self, task_id, status_id):
        self.finish_editing()
        if db.set_task_status(self.conn, task_id, status_id, by=self.created_by()):
            self.celebrate(task_id)
        self.refresh(select_id=task_id)

    # --- примеры, справка, «О программе» ---

    def add_examples(self):
        """Добавляет примеры задач; старые примеры при этом заменяются свежими."""
        if db.count_examples(self.conn):
            if not ui.askyesno(
                APP_NAME, "Примеры уже есть в списке.\n\nЗаменить их свежими (со сроками от сегодняшнего дня)?",
                parent=self.root,
            ):
                return
            db.delete_examples(self.conn)
        examples = make_examples()
        db.add_examples(self.conn, examples)
        self.filter.set("Все")
        self.refresh()
        ui.showinfo(
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
            ui.showerror(APP_NAME, f"Не удалось сохранить файл:\n{error_text(error)}\n\n"
                                 "Если он открыт в Excel — закройте его и попробуйте снова.",
                                 parent=self.root)
            return False

    def export_csv(self):
        rows = export_rows(self.conn)
        if not rows:
            ui.showinfo(APP_NAME, "Задач пока нет — выгружать нечего.", parent=self.root)
            return
        name = re.sub(r'[\\/:*?"<>|]', "_", self.current_list()["name"])  # без запрещённых в имени файла знаков
        path = self.ask_save_csv("Экспорт задач", f"{APP_NAME} {name} {date.today():%d.%m.%Y}.csv")
        if path and self.save_file(path, CSV_COLUMNS, rows):
            ui.showinfo(APP_NAME, f"Выгружено задач: {len(rows)}.\n\n{path}\n\n"
                                "Файл открывается в Excel двойным щелчком.", parent=self.root)

    def save_template(self):
        path = self.ask_save_csv("Шаблон для импорта", f"{APP_NAME} шаблон импорта.csv")
        if path and self.save_file(path, CSV_TEMPLATE_COLUMNS, template_rows()):
            ui.showinfo(
                APP_NAME,
                f"Шаблон сохранён:\n{path}\n\n"
                "Откройте его в Excel, замените строки-примеры своими задачами и сохраните "
                "в том же формате (CSV). Затем: ☰ Меню → Экспорт и импорт → Импорт задач из CSV.\n\n"
                "Обязателен только «Заголовок». Статус — название колонки доски. "
                "Приоритет — «Срочно и важно», «Важно», «Срочно» или «Обычный». "
                "Срок — «16.10.2026 18:00» или просто дата (тогда 09:00). "
                "Напомнить — «За 15 минут», «За 1 час», «За 1 день» и т. п.",
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
            ui.showerror(APP_NAME, f"Не удалось открыть файл:\n{error_text(error)}", parent=self.root)
            return
        except (ValueError, csv.Error) as error:
            ui.showerror(APP_NAME, f"Файл не подходит для импорта.\n\n{error}", parent=self.root)
            return
        if not tasks:
            ui.showwarning(APP_NAME, "В файле не найдено ни одной задачи с заголовком.",
                                   parent=self.root)
            return
        text = (f"Добавить задач из файла: {len(tasks)} — в список «{self.current_list()['name']}»?"
                "\n\nУже имеющиеся задачи останутся, новые получат свои номера.")
        if notes:
            shown = "\n".join("• " + n for n in notes[:8])
            more = f"\n…и ещё замечаний: {len(notes) - 8}" if len(notes) > 8 else ""
            text += f"\n\nЗамечания:\n{shown}{more}"
        if not ui.askyesno("Импорт задач", text, parent=self.root):
            return
        db.import_tasks(self.conn, tasks, created_by=self.created_by())
        self.filter.set("Все")
        self.refresh()
        ui.showinfo(APP_NAME, f"Добавлено задач: {len(tasks)}.", parent=self.root)

    def delete_examples(self):
        count = db.count_examples(self.conn)
        if not count:
            ui.showinfo(APP_NAME, "Примеров задач в списке нет.", parent=self.root)
            return
        if ui.askyesno(
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

    def show_phone(self):
        PhoneDialog(self.root, self.prefs)

    def show_about(self):
        AboutWindow(self.root, on_license=self.show_license)

    def show_license(self):
        LicenseWindow(self.root)

    def show_whats_new(self):
        WhatsNewWindow(self.root)

    # --- поиск задач ---

    def search_focus(self):
        if self.search.get() == SEARCH_HINT:
            self.search.delete(0, "end")
        self.search.configure(fg=TEXT)

    def search_blur(self):
        if not self.search.get():
            self.search.insert(0, SEARCH_HINT)
            self.search.configure(fg=DONE)

    def search_typed(self, now=False):
        """Ищем, когда пользователь перестал печатать (через 0,25 с), а не на каждую букву."""
        if self.search_after:
            self.root.after_cancel(self.search_after)
        self.search_after = self.root.after(0 if now else 250, self.run_task_search)

    def run_task_search(self):
        self.search_after = None
        text = self.search.get()
        query = "" if text == SEARCH_HINT else " ".join(text.split())
        if query == self.search_query:
            return
        self.search_query = query
        if query:
            self.search_clear.pack(side="left", padx=(0, 8))
        else:
            self.search_clear.pack_forget()
        self.refresh(select_id=self.current_id())

    def clear_search(self, refresh=True):
        self.search.delete(0, "end")
        self.search_clear.pack_forget()
        if self.root.focus_get() is not self.search:
            self.search_blur()
        changed = bool(self.search_query)
        self.search_query = ""
        if refresh and changed:
            self.refresh(select_id=self.current_id())

    def found(self, row):
        """Подходит ли задача под поиск: все слова — в номере, заголовке, описании, инициаторе
        или исполнителе (без учёта окончаний)."""
        task_id, title, *_, body, _ = row
        haystack = " ".join((f"#{task_id}", title, body, self.authors.get(task_id, ""),
                             self.assignees.get(task_id, ""), self.unit_names.get(task_id, ""))).lower()
        return all(stem in haystack for stem in search_stems(self.search_query))

    def tour_quick_add(self):
        """Что обвести в туре на шаге «Новая задача»: строку добавления в открытом виде."""
        view = self.cards_view()
        if view is None:
            return self.list_quick
        return view.quick_adds[0] if view.quick_adds else view

    def quick_add_here(self):
        """Ctrl+N: раскрыть «＋ Добавить задачу» в том виде, что открыт (в доске — первая
        колонка, в матрице — «Сделать сейчас»); в календаре — окно новой задачи на сегодня."""
        if self.view.get() == "calendar":
            self.new_task_at(("day", date.today()))
            return
        view = self.cards_view()
        quick_adds = view.quick_adds if view else [self.list_quick]
        if quick_adds:
            quick_adds[0].open()

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
        # Список задач читаем из базы один раз — Тоторо, счётчики и проверка сроков берут его отсюда
        # (в общих списках каждое чтение — поход по сети)
        rows = self.all_rows = db.list_tasks(self.conn)
        self.done_today = db.count_done_today(self.conn)
        self.authors, self.assignees = db.task_people(self.conn)
        self.units = dict(db.list_units(self.conn))  # id -> название бизнес-единицы
        self.unit_names = {tid: self.units[uid] for tid, uid in db.task_units(self.conn).items()
                           if uid in self.units}  # id задачи -> название её единицы
        self.extra_counts = db.extras_counts(self.conn)  # id задачи -> (файлов, комментариев)
        self.mail_ids = db.mail_task_ids(self.conn)
        self.repeats = db.repeat_infos(self.conn)  # id задачи -> (повтор, до, есть следующая)
        shared = bool(self.list_id and self.current_list()["shared"])
        # столбцы «Исполнитель» и «Инициатор» — только в общих списках (в личном всё ваше)
        columns = [c for c in self.column_order if shared or c not in ("assignee", "author")]
        if not self.units and not self.unit_names:  # справочник пуст — столбец не нужен
            columns.remove("unit")
        self.tree["displaycolumns"] = columns
        if shared and self.only_mine.get():
            me = self.user_name()
            rows = [r for r in rows if self.assignees.get(r[0]) == me]
        active = sum(1 for row in rows if not row[2])
        self.chips["active"].configure(text=f"Активных  {active}")
        self.chips["done"].configure(text=f"Выполнено  {len(rows) - active}")
        self.chips["today"].configure(text=f"✔ Сделано сегодня  {self.done_today}")

        wanted = FILTERS[self.filter.get()]
        now = datetime.now()
        late = {r[0] for r in rows if r[4] and not r[2] and datetime.fromisoformat(r[4]) < now}
        self.overdue_button.configure(text=f"Просроченные  {len(late)}" if late else "Просроченные")
        if wanted == "overdue":
            rows = [row for row in rows if row[0] in late]
        elif wanted is not None:
            rows = [row for row in rows if bool(row[2]) == wanted]
        if self.search_query:
            rows = [r for r in rows if self.found(r)]
        rows = self.fresh_first(self.sort_rows(rows, statuses))
        overdue_ids = late & {r[0] for r in rows}

        self.hide_title_tip()
        self.tree.delete(*self.tree.get_children())
        self.due, self.row_status = {}, {}
        for task_id, title, done, created, due_at, remind_before, urgent, important, _, status_id in rows:
            remind = remind_label(remind_before) if due_at and remind_before is not None else ""
            level = priority_level(urgent, important)
            iid = str(task_id)
            name = self.statuses.get(status_id, ("—",))[0]
            self.row_status[iid] = name
            self.tree.insert(
                "", "end", iid=iid, image=IMAGES.get(f"priority_{level}", ""),
                values=(f"#{task_id}", status_label(name, done), self.list_marks(task_id), title,
                        PRIORITY_NAMES[level],
                        format_due(due_at), remind, self.assignees.get(task_id, ""),
                        self.authors.get(task_id, ""), self.unit_names.get(task_id, ""), created),
                tags=("done",) if done else ("normal",),
            )
            if due_at and not done:
                self.due[iid] = datetime.fromisoformat(due_at)
        self.mark_overdue()

        if self.tree.get_children():
            self.empty.place_forget()
        else:
            if self.search_query:
                text = f"Ничего не найдено по запросу «{self.search_query}»"
            elif shared and self.only_mine.get():
                text = "На вас пока ничего не назначено"
            else:
                text = EMPTY_TEXT[self.filter.get()]
            self.empty.configure(text=text)
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

        if self.cards_view():
            self.cards_view().render(statuses, rows, overdue_ids)

        if select_id is not None:
            self.select_task(select_id)
        self.update_buddy()
        self.update_side()
        self.shown_state = self.time_state(self.all_rows)

    def time_state(self, rows=None):
        """То, что меняется само по себе, со временем: какие задачи уже просрочены и какой
        сегодня день (счётчик «сегодня»). Если это не изменилось, перерисовывать нечего.
        rows — уже прочитанные задачи (иначе читаем из базы)."""
        now = datetime.now()
        if rows is None:
            rows = db.list_tasks(self.conn, done=False)
        overdue = frozenset(r[0] for r in rows
                            if r[4] and not r[2] and datetime.fromisoformat(r[4]) < now)
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
                "author": (self.authors.get(task_id) or "").casefold() or None,
                "assignee": (self.assignees.get(task_id) or "").casefold() or None,
                "unit": (self.unit_names.get(task_id) or "").casefold() or None,
                "status": position.get(status_id, len(position)),
                "title": title.casefold(),
                "marks": self.marks_order(task_id),
                "priority": priority_level(urgent, important),
                "due": due_at,
                "remind": remind_before if due_at else None,
            }[column]

        rows = sorted(rows, key=lambda r: r[0])
        filled = sorted((r for r in rows if value(r) is not None), key=value, reverse=descending)
        return filled + [r for r in rows if value(r) is None]

    def fresh_first(self, rows):
        """Только что добавленные задачи — первыми (самая новая выше), при любой сортировке:
        добавили — сразу видно под строкой «＋ Добавить задачу». После перезапуска или смены
        списка они встают на обычное место."""
        if not self.fresh_ids:
            return rows
        order = {task_id: i for i, task_id in enumerate(reversed(self.fresh_ids))}
        if self.column_sort:  # по столбцу выполненные не опускаются вниз — свежие просто первые
            return sorted(rows, key=lambda row: order.get(row[0], len(order)))  # остальные — как были
        # обычная сортировка держит выполненные внизу: свежая выполненная — первая среди них
        return sorted(rows, key=lambda row: (bool(row[2]), order.get(row[0], len(order))))

    def sort_by_column(self, column):
        if self.column_drag and self.column_drag["moved"]:
            return  # заголовок тянули, а не щёлкнули — сортировать не нужно
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
            where = {"board": "на доске", "matrix": "в матрице",
                     "calendar": "в календаре"}.get(self.view.get(), "в списке")
            ui.showinfo(APP_NAME, f"Сначала выберите задачу {where}.", parent=self.root)
            return None
        return task_id, info["done"]

    def banner_busy(self):
        """На полосе важное: связь с общей папкой или кнопка «Открыть список» — не перекрываем."""
        return self.banner.kind in ("alert", "wait") or (self.banner.kind == "good"
                                                          and self.banner.has_action)

    def add(self, title, place=None):
        """Быстрое добавление задачи по названию (строка «＋ Добавить задачу»). place — куда:
        ("status", id) колонка доски, ("level", n) четверть матрицы, None — над списком."""
        title = title.strip()
        if not title:
            return
        status_id, urgent, important = self.place_flags(place)
        base = (urgent, important)  # приоритет четверти — его не отменяет «Отменить» на полосе
        history = self.smart_rows()
        # Что поняли из названия, применяем, только если можем сказать об этом на полосе
        # (с кнопкой «Отменить»); иначе задача добавляется как написана
        when = smart.parse_when(title) if history is not None and not self.banner_busy() else None
        # Название сохраняем, как написали (пользователь так захотел); слова о сроке не
        # учитываем только при поиске похожих задач
        name = when[0] if when else title
        prio = smart.suggest_priority(name, history) if history is not None else None
        # «срочно/важно» сказали в названии
        told = prio if prio and prio[3] and not self.banner_busy() else None
        if told and (urgent or not told[0]) and (important or not told[1]):
            told = None  # четверть уже такая — «Отменить» на полосе было бы не о чем
        task_id = db.add_task(self.conn, title, status_id=status_id, created_by=self.created_by())
        self.fresh_ids.append(task_id)
        # Срок из названия и «срочно/важно» из его слов ставим сразу — их сказали явно;
        # приоритет и шаги похожих задач — только предлагаем в полосе над окном
        urgent, important = urgent or bool(told and told[0]), important or bool(told and told[1])
        if told:  # на полосе — итоговый приоритет (вместе с приоритетом четверти)
            told = (urgent, important, *told[2:])
        if when or urgent or important:
            due_at, remind = apply_when(when) if when else (None, None)
            db.update_task(self.conn, task_id, title, due_at, remind, urgent, important,
                           by=self.created_by())
        wanted = FILTERS[self.filter.get()]
        done = bool(status_id and self.statuses[status_id][2])  # добавили в колонку «Готово»
        if wanted is not None and wanted is not done:
            self.filter.set("Все")  # иначе новую задачу не будет видно
        self.refresh(select_id=task_id)
        if history is not None:
            # в четверти матрицы приоритет уже выбран — советовать его незачем
            advice = None if told or any(base) else prio
            self.smart_banner(task_id, title, when, told, advice, history, base)

    def smart_banner(self, task_id, title, when, told, prio, history, base=(False, False)):
        """После быстрого добавления: что умные подсказки поняли из названия (с «Отменить»)
        или совет по похожим задачам. Сообщение о связи с общей папкой не перекрываем."""
        if self.banner_busy():
            return
        name = when[0] if when else title
        conn = self.conn  # кнопки полосы — только для этого списка, не для открытого позже

        def same_list():
            if self.conn is conn:
                return True
            self.banner.hide()
            return False
        if when or told:
            parts = []
            if when:
                parts.append("срок " + smart.describe_when(when[1], when[2]) +
                             (", напомню за 15 минут" if when[2] else ""))
            if told:
                parts.append("приоритет «" + PRIORITY_NAMES[priority_level(told[0], told[1])] + "»")
            version = (db.task_meta(self.conn, task_id) or {}).get("version")

            def undo():
                if not same_list():
                    return
                self.banner.hide()
                self.finish_editing()
                # задачу с тех пор меняли (вы или другой участник) — не трогаем
                if db.update_task(self.conn, task_id, title, None, None, *base,
                                  by=self.created_by(), version=version):
                    self.refresh(select_id=task_id)
                else:
                    self.banner.show("hint", "Задачу уже изменили — отменять не стал.",
                                     hide_after=6_000)
            self.banner.show("hint", "Понял из названия: " + "; ".join(parts) + ".", "Отменить",
                             undo, hide_after=12_000)
            return
        if prio:
            urgent, important = prio[0], prio[1]

            def mark():
                if not same_list():
                    return
                self.banner.hide()
                if db.get_task(self.conn, task_id) is not None:
                    self.quick_priority(task_id, urgent, important)
            self.banner.show("hint", f"Отметить новую задачу как «{PRIORITY_NAMES[priority_level(urgent, important)]}»? "
                             f"Так {prio[2].removeprefix('так ')}.", "Отметить", mark, hide_after=15_000)
            return
        steps = smart.suggest_steps(name, history)
        if steps:
            def insert():
                if not same_list():
                    return
                self.banner.hide()
                self.finish_editing()
                task = db.get_task(self.conn, task_id)
                if task is None:
                    return
                title_, due_at, remind_before, urgent, important, body = task
                if not (body or "").strip():
                    db.update_task(self.conn, task_id, title_, due_at, remind_before, urgent,
                                   important, steps[1], by=self.created_by())
                self.refresh(select_id=task_id)
            self.banner.show("hint", f"У похожей задачи «{short_text(steps[0], 50)}» есть список "
                             "шагов. Вставить их в описание новой?", "Вставить шаги", insert,
                             hide_after=15_000)

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
            data = self.form_data(task_id)
            self.edit_version = data["version"]
            self.side.show_form(data, statuses,
                                on_save=lambda result: self.save_edit(task_id, result),
                                on_cancel=self.cancel_edit, members=self.members(),
                                history=self.smart_rows(), hints="changed", units=db.list_units(self.conn))
            return
        # Окно узкое и панель скрыта — открываем форму в отдельном окне
        data = self.form_data(task_id)
        dialog = TaskDialog(self.root, data, statuses, members=self.members(),
                            history=self.smart_rows(), hints="changed", units=db.list_units(self.conn))
        self.root.wait_window(dialog)
        if dialog.result:
            version = data["version"] if self.created_by() else None
            if not self.apply_edit(task_id, dialog.result, version=version):
                if self.resolve_conflict(task_id, dialog.result, dialog.form_initial, False) == "mine":
                    self.apply_edit(task_id, dialog.result)
                self.refresh(select_id=task_id)

    def toggle(self):
        task = self.selected()
        if task is None:
            return
        self.finish_editing()
        task_id, done = task
        if not db.set_done(self.conn, task_id, not done, by=self.created_by()):
            ui.showinfo(
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
        if not ui.askyesno(
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
        if self.tree.identify_region(event.x, event.y) == "heading":
            self.show_heading_menu(event)
            return
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

        people = None
        if self.members() is not None:
            current = self.assignees.get(task_id)
            people = PopupMenu()
            for name in self.members():
                people.command(name + ("  (я)" if name == self.user_name() else ""),
                               lambda n=name: self.quick_assignee(task_id, n), checked=name == current)
            people.separator()
            people.command("Не назначен", lambda: self.quick_assignee(task_id, None), checked=not current)

        lists = PopupMenu()
        for item in self.lists:
            if item["id"] != self.list_id:
                lists.command(item["name"], lambda i=item["id"]: self.move_to_list(task_id, i))

        return (PopupMenu()
                .command("Изменить…", self.edit, accel="F2")
                .command("Вернуть в работу" if info["done"] else "Отметить выполненной",
                         self.toggle, accel="Пробел")
                .submenu("Статус", statuses, icon=swatch(info["status_color"]))
                .submenu("Исполнитель", people or PopupMenu(), enabled=people is not None)
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
        db.update_task(self.conn, task_id, title, due_at, remind_before, urgent, important,
                       by=self.created_by())
        self.refresh(select_id=task_id)

    def quick_assignee(self, task_id, name):
        self.finish_editing()
        db.set_assignee(self.conn, task_id, name, by=self.created_by())
        self.refresh(select_id=task_id)

    def quick_remind(self, task_id, minutes):
        self.finish_editing()
        title, due_at, _, urgent, important, _ = db.get_task(self.conn, task_id)
        db.update_task(self.conn, task_id, title, due_at, minutes, urgent, important,
                       by=self.created_by())
        self.refresh(select_id=task_id)

    def move_due(self, task_id, old_due, day):
        """Задачу перетащили в календаре на другой день: дата срока — новая, время — прежнее."""
        self.finish_editing()
        try:
            moved = db.move_due(self.conn, task_id, old_due, day.isoformat() + old_due[10:],
                                by=self.created_by())
        except sqlite3.Error as error:
            ui.showerror(APP_NAME, f"Не удалось перенести срок:\n{error_text(error)}", parent=self.root)
            moved = True  # показываем, что в файле на самом деле
        self.refresh(select_id=task_id)
        if not moved:
            ui.showinfo("Срок не перенесён",
                        "Срок задачи уже успел измениться (в форме задачи или у другого участника) — "
                        "в календаре теперь её новый вид. Перетащите её ещё раз, если срок всё ещё "
                        "нужно перенести.",
                        parent=self.root)

    def quick_priority(self, task_id, urgent, important):
        self.finish_editing()
        title, due_at, remind_before, _, _, _ = db.get_task(self.conn, task_id)
        db.update_task(self.conn, task_id, title, due_at, remind_before, urgent, important,
                       by=self.created_by())
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
                                    info["urgent"], info["body"], info["author"], info["assignee"],
                                    info["unit"], info["repeat"])
        to = db.mail_from(self.conn, task[0])  # задача из письма — отвечаем его отправителю
        # Основной способ — черновик письма в файле .eml: Outlook открывает его как новое
        # письмо, и длина текста не ограничена (в отличие от ссылки mailto:).
        try:
            os.startfile(write_draft(task[0], subject, body, to))
            return
        except OSError:
            pass  # .eml открыть нечем — пробуем ссылку mailto:
        address = quote(parseaddr(to)[1], safe="@")
        url = f"mailto:{address}?subject={quote(subject, safe='')}&body={quote(body, safe='')}"
        too_long = len(url) > MAILTO_LIMIT
        if too_long:
            # Почтовые программы не принимают слишком длинные ссылки: откроем письмо
            # с темой, а текст положим в буфер обмена.
            url = f"mailto:{address}?subject={quote(subject, safe='')}"
            self.copy_text(body)
        try:
            os.startfile(url)  # откроет почтовую программу по умолчанию (например, Outlook)
            if too_long:
                ui.showinfo(
                    APP_NAME,
                    "Описание задачи длинное, поэтому текст письма скопирован.\n\n"
                    "Щёлкните в тексте письма и нажмите Ctrl+V.",
                    parent=self.root,
                )
        except OSError:
            self.copy_text(f"{subject}\n\n{body}")
            ui.showwarning(
                APP_NAME,
                "Не удалось открыть почтовую программу.\n\n"
                "Тема и текст письма скопированы — вставьте их в письмо вручную (Ctrl+V).",
                parent=self.root,
            )

    # --- напоминания ---

    # --- файлы и комментарии задачи (вкладки карточки справа) ---

    def extras_changed(self, task_id):
        """Добавили или убрали файл или комментарий: обновляем карточку справа и значки 📎 💬
        только у этой задачи — без перерисовки всего списка (иначе окно «дёргается»)."""
        try:
            self.extra_counts = db.extras_counts(self.conn)
        except sqlite3.Error:
            return
        mark = self.task_mark(task_id)
        iid = str(task_id)
        if self.tree.exists(iid):
            self.tree.set(iid, "marks", self.list_marks(task_id))
        if self.cards_view():
            self.cards_view().set_mark(task_id, mark)
        if self.side.mode == "task" and self.side.card.task_id == task_id:
            self.side.card.load_extras(task_id)

    def task_mark(self, task_id):
        """Значки карточки на доске: 🔁 (повторяется), 📧 (из письма Outlook), 📎 файлы, 💬 комментарии."""
        return extras_mark(self.extra_counts.get(task_id), task_id in self.mail_ids, task_id in self.repeats)

    def list_marks(self, task_id):
        """Столбец значков в списке: '🔁  📧  📎 3  💬 2' (или '', если ничего нет) — отдельно от
        названия, чтобы названия задач стояли ровно."""
        return extras_mark(self.extra_counts.get(task_id), task_id in self.mail_ids,
                           task_id in self.repeats).strip()

    def marks_order(self, task_id):
        """Сортировка по столбцу значков: больше файлов, потом комментариев — выше; без значков — None."""
        files, comments = self.extra_counts.get(task_id) or (0, 0)
        mail = task_id in self.mail_ids
        repeat = task_id in self.repeats
        return (-files, -comments, -mail, -repeat) if files or comments or mail or repeat else None

    def attachments(self, task_id):
        try:
            return db.list_attachments(self.conn, task_id)
        except sqlite3.Error:
            return []

    def comments(self, task_id):
        try:
            return db.list_comments(self.conn, task_id)
        except sqlite3.Error:
            return []

    def file_data(self, attachment_id):
        return db.attachment_data(self.conn, attachment_id)

    def preview_source(self):
        """Откуда фоновый поток прочитает картинки для превью: (файл открытого списка, сколько
        ждать, если файл занят) или None — общий список сейчас без связи с общей папкой."""
        item = self.current_list()
        if item["shared"]:
            return (self.team.path(item), team.TIMEOUT) if self.share_online() else None
        return db.list_path(item), 5

    def attach(self, task_id, items):
        """items — [(имя, содержимое в байтах)]. Слишком большие файлы не добавляются."""
        big = [name for name, data in items if len(data) > db.MAX_ATTACHMENT]
        if big:
            ui.showwarning(APP_NAME, "Слишком большой файл (можно до "
                           f"{db.MAX_ATTACHMENT // (1024 * 1024)} МБ):\n" + "\n".join(big),
                           parent=self.root)
        try:
            for name, data in items:
                if len(data) <= db.MAX_ATTACHMENT:
                    db.add_attachment(self.conn, task_id, name, data, by=self.created_by())
        except sqlite3.Error as error:
            ui.showerror(APP_NAME, f"Не удалось добавить файл:\n{error}", parent=self.root)
        self.extras_changed(task_id)

    def read_files(self, paths):
        items = []
        for path in paths:
            try:
                items.append((Path(path).name, Path(path).read_bytes()))
            except OSError as error:
                ui.showerror(APP_NAME, f"Не удалось прочитать файл:\n{error_text(error)}", parent=self.root)
        return items

    def add_files(self, task_id):
        if task_id is None:
            return
        paths = filedialog.askopenfilenames(parent=self.root, title="Добавить файлы к задаче")
        items = self.read_files(paths)
        if items:
            self.attach(task_id, items)

    def paste_files(self, task_id):
        """Снимок экрана или скопированные в Проводнике файлы из буфера обмена."""
        try:
            from PIL import ImageGrab
            content = ImageGrab.grabclipboard()
        except Exception:  # noqa: BLE001 — буфер занят другой программой или нет Pillow
            content = None
        if isinstance(content, list):  # файлы, скопированные в Проводнике
            items = self.read_files([path for path in content if os.path.isfile(path)])
            if items:
                self.attach(task_id, items)
                return
        elif content is not None:  # картинка (например, снимок экрана)
            from io import BytesIO
            buffer = BytesIO()
            content.save(buffer, "PNG")
            name = datetime.now().strftime("Снимок %d.%m.%Y %H-%M-%S.png")
            self.attach(task_id, [(name, buffer.getvalue())])
            return
        ui.showinfo(APP_NAME, "В буфере обмена нет картинки или файлов.\n\n"
                    "Сделайте снимок экрана (Win+Shift+S) или скопируйте файл в Проводнике, "
                    "а потом нажмите «Вставить».", parent=self.root)

    def side_panel_key(self, event):
        """Ctrl+B (в любой раскладке) сворачивает и разворачивает правую панель."""
        if event.keycode != 66:
            return None
        self.toggle_side_panel()
        return "break"

    def paste_key(self, event):
        """Ctrl+V при открытой вкладке «Файлы» (в любой раскладке) вставляет из буфера."""
        card = self.side.card
        if (event.keycode != 86 or self.side.mode != "task" or card.tab.get() != "files"
                or isinstance(event.widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox))):
            return None
        card.paste()
        return "break"

    def attachment_name(self, attachment_id):
        row = self.conn.execute("SELECT name FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        return row[0] if row else None

    def open_file(self, attachment_id):
        """Открывает вложение в программе Windows для этого типа файлов (через временную копию)."""
        try:
            name, data = self.attachment_name(attachment_id), self.file_data(attachment_id)
        except sqlite3.Error as error:
            ui.showerror(APP_NAME, f"Не удалось прочитать файл:\n{error}", parent=self.root)
            return
        if data is None:
            return
        if is_risky_file(name) and not ui.askyesno(
                "Запустить программу?",
                f"«{name}» — программа или сценарий: при открытии он запустится на этом "
                "компьютере.\n\nОткрывайте, только если доверяете тому, кто приложил файл. "
                "Запустить?", icon="warning", default="no", parent=self.root):
            return
        try:
            os.startfile(temp_copy(DRAFTS_DIR / f"{self.list_id}-{attachment_id}", name, data))
        except OSError as error:
            ui.showerror(APP_NAME, f"Не удалось открыть файл:\n{error_text(error)}", parent=self.root)

    def save_attachment(self, attachment_id):
        name = self.attachment_name(attachment_id)
        path = filedialog.asksaveasfilename(parent=self.root, title="Сохранить файл", initialfile=name,
                                            defaultextension=Path(name).suffix)
        if path:
            try:
                Path(path).write_bytes(self.file_data(attachment_id))
            except (OSError, sqlite3.Error) as error:
                ui.showerror(APP_NAME, f"Не удалось сохранить файл:\n{error_text(error)}", parent=self.root)

    def delete_attachment(self, attachment_id):
        name = self.attachment_name(attachment_id)
        if not ui.askyesno(APP_NAME, f"Удалить файл «{name}» из задачи?", parent=self.root,
                           icon="warning", default="no"):
            return
        try:
            db.delete_attachment(self.conn, attachment_id)
        except sqlite3.Error as error:
            ui.showerror(APP_NAME, f"Не удалось удалить файл:\n{error}", parent=self.root)
        self.extras_changed(self.current_id())

    def file_menu(self, attachment_id, x, y):
        (PopupMenu()
         .command("Открыть", lambda: self.open_file(attachment_id))
         .command("Сохранить как…", lambda: self.save_attachment(attachment_id))
         .separator()
         .command("Удалить файл", lambda: self.delete_attachment(attachment_id), danger=True)
         ).popup(self.root, x, y)

    def add_comment(self, task_id, text):
        try:
            db.add_comment(self.conn, task_id, text, by=self.created_by())
        except sqlite3.Error as error:
            ui.showerror(APP_NAME, f"Не удалось сохранить комментарий:\n{error}", parent=self.root)
            return False
        self.extras_changed(task_id)
        return True

    def comment_menu(self, comment_id, author, text, x, y):
        # в общем списке удалить можно только свой комментарий
        mine = not author or author == self.user_name()
        (PopupMenu()
         .command("Копировать текст", lambda: self.copy_text(text))
         .separator()
         .command("Удалить комментарий", lambda: self.delete_comment(comment_id), danger=True,
                  enabled=mine)
         ).popup(self.root, x, y)

    def delete_comment(self, comment_id):
        if not ui.askyesno(APP_NAME, "Удалить этот комментарий?", parent=self.root,
                           icon="warning", default="no"):
            return
        try:
            db.delete_comment(self.conn, comment_id)
        except sqlite3.Error as error:
            ui.showerror(APP_NAME, f"Не удалось удалить комментарий:\n{error}", parent=self.root)
        self.extras_changed(self.current_id())

    def check_reminders(self):
        """Раз в 30 секунд: не пора ли о чём-то напомнить. Если подключены общие списки,
        проверяем сразу после удачной фоновой проверки связи (on_fresh_probe) — иначе
        обрыв сети в этот момент «повесил» бы окно."""
        if self.team:
            self.reminders_due = True
        else:
            self.do_check_reminders()
        self.root.after(CHECK_EVERY_MS, self.check_reminders)

    def do_check_reminders(self):
        # Перерисовываем, только если какая-то задача стала просроченной или наступил новый день:
        # иначе доска и список «вздрагивали» бы каждые 30 секунд
        try:
            offline = self.current_list()["shared"] and not self.share_online()
            if not offline and self.time_state() != self.shown_state and not self.dragging():
                self.refresh(select_id=self.current_id())
        except sqlite3.Error:
            pass  # общая папка недоступна — проверим в следующий раз
        # Напоминания — по задачам из всех списков, не только из открытого
        lines = []
        reminded = set(db.get_json_setting(self.prefs, "shared_reminded", []))
        for item in self.lists:
            where = "" if item["id"] == self.list_id else f"  (список «{item['name']}»)"
            if item["shared"] and not self.share_online():
                continue  # нет связи с общей папкой — напомним, когда появится
            try:
                conn = self.list_conn(item["id"])
                if not item["shared"]:
                    for task_id, title, due_at in db.due_reminders(conn):
                        db.mark_reminded(conn, task_id)
                        lines.append((f"• {title} — срок {format_due(due_at)}{where}",
                                      (item["id"], task_id)))
                    continue
                # Общий список: напоминаем о задачах, которые создал этот участник;
                # о чём уже напомнили — помним у себя (флаг в общем файле один на всех)
                for key, task_id, title, due_at in db.shared_reminders(conn, self.user_name()):
                    if f"{item['id']}|{key}" not in reminded:
                        reminded.add(f"{item['id']}|{key}")
                        lines.append((f"• {title} — срок {format_due(due_at)}{where}",
                                      (item["id"], task_id)))
            except (sqlite3.Error, StopIteration):
                continue  # общая папка сейчас недоступна — напомним, когда появится связь
        if lines:
            db.set_json_setting(self.prefs, "shared_reminded", sorted(reminded)[-500:])
        self.check_assigned()
        if lines:
            # Показываем окно поверх всех остальных, даже если оно было свёрнуто.
            self.root.deiconify()
            self.root.lift()
            self.root.bell()
            self.show_reminders(lines, topmost=True)

    def collect_pending(self, skip=()):
        """Задачи из всех списков, у которых прошёл срок или пришло время напоминания:
        [(текст, (id списка, id задачи))]. В общих списках — только мои задачи."""
        lines = []
        for item in self.lists:
            where = "" if item["id"] == self.list_id else f"  (список «{item['name']}»)"
            if item["shared"] and not self.share_online():
                continue
            try:
                tasks = db.pending_tasks(self.list_conn(item["id"]),
                                         self.user_name() if item["shared"] else None)
            except (sqlite3.Error, StopIteration):
                continue  # общая папка сейчас недоступна
            for task_id, title, due_at in tasks:
                if (item["id"], task_id) not in skip:
                    lines.append((f"• {title} — срок {format_due(due_at)}{where}",
                                  (item["id"], task_id)))
        return lines

    def show_reminders(self, new=(), topmost=False):
        """Окно напоминаний: новые напоминания (new) и все остальные задачи, которые ждут
        внимания. Открывается само, когда пришло время, или из меню."""
        rest = self.collect_pending(skip={value for _, value in new})
        if not new and not rest:
            ui.showinfo("Напоминания", "Сейчас напоминать не о чем: просроченных задач нет, "
                        "и время напоминаний ещё не пришло.", parent=self.root)
            return
        links = []
        if new:
            links += [("Пришло время:", None)] + list(new)
        if rest:
            links += [("Ещё ждут — срок прошёл или скоро:", None)] if new else []
            links += rest
        tasks = [link for link in links if link[1] is not None]
        if len(tasks) > REMINDERS_MAX:  # длинное окно не влезет на экран — показываем первые
            hidden = {value for _, value in tasks[REMINDERS_MAX:]}
            links = [link for link in links if link[1] not in hidden]
            links.append((f"…и ещё {len(tasks) - REMINDERS_MAX}. Все просроченные — кнопка "
                          "«Просроченные» вверху окна.", None))
        if len(tasks) == 1:
            buttons = [("Открыть задачу", tasks[0][1], "Accent.TButton"), ("Закрыть", None, "TButton")]
            hint = ""
        else:
            buttons = [("Закрыть", None, "Accent.TButton")]
            hint = "\n\nЩёлкните по задаче, чтобы открыть её."
        message = ("Напоминаю о задачах:" if new else
                   "Задачи, у которых прошёл срок или пришло время напоминания:") + hint
        if topmost:
            self.root.attributes("-topmost", True)
        chosen = AlertDialog(self.root, "Напоминания", message, "info", buttons, buttons[0][1],
                             None, links=links).show()
        if topmost:
            self.root.attributes("-topmost", False)
        if chosen:
            self.open_task(*chosen)

    def ask_open_task(self, title, message, lines):
        """Сообщение о задачах, где каждую можно открыть щелчком.
        lines — [(текст, (id списка, id задачи))]. Возвращает выбранную пару или None."""
        if len(lines) == 1:
            buttons = [("Открыть задачу", lines[0][1], "Accent.TButton"), ("Закрыть", None, "TButton")]
            hint = ""
        else:
            buttons = [("Закрыть", None, "Accent.TButton")]
            hint = "\n\nЩёлкните по задаче, чтобы открыть её."
        return AlertDialog(self.root, title, message + hint, "info", buttons, buttons[0][1], None,
                           links=lines).show()

    def open_task(self, list_id, task_id):
        """Открывает задачу из напоминания: переключает список, показывает и выделяет её."""
        if list_id != self.list_id:
            self.switch_list(list_id)
            if list_id != self.list_id:
                return  # список не открылся — об этом уже сказали
        self.reveal_task(task_id)

    # --- списки задач ---
    # Личные списки хранятся у себя (self.prefs + папка lists), общие — в сетевой папке (self.team).

    def connect_team(self, wait=False):
        """Подключает общую папку из настроек. Возвращает текст ошибки или None.
        wait — сначала дождаться фоновой проверки связи (при запуске программы): если сети
        нет, не подключаемся, а то окно повиснет; подключимся сами, когда связь появится."""
        folder = self.reset_team()
        if not folder:
            return None
        if wait:
            deadline = time_module.monotonic() + team.Probe.HANG + 0.5
            while self.probe.ok is None and time_module.monotonic() < deadline:
                time_module.sleep(0.05)
            if not self.probe.online():
                self.team_error = self.offline_text(folder)
                return self.team_error
        try:
            self.use_team(open_team(folder, self.user_name()))
        except (team.TeamError, sqlite3.Error, OSError) as error:
            self.team, self.team_error = None, str(error)
        return self.team_error

    def connect_team_in_background(self, done):
        """Как connect_team, но саму папку открывает в фоновом потоке. Нужно после «Сохранить»
        в настройках: связь с новой папкой ещё никто не проверял, и недоступная папка (нет VPN,
        опечатка в адресе) «повесила» бы окно на десятки секунд. (Дождаться фоновой проверки,
        как при запуске, нельзя: в новой пустой папке ещё нет team.db, и проверка решила бы,
        что связи нет.) done(текст ошибки или None) вызывается в основном потоке."""
        folder = self.reset_team()
        if not folder:
            done(None)
            return
        self.connecting = True
        self.connect_attempt += 1
        attempt = self.connect_attempt
        user = self.user_name()

        def finished(group, error):
            if attempt != self.connect_attempt:  # пока подключались, настройки сохранили снова
                if group:
                    group.close()
                return
            self.connecting = False
            if self.team is not None or folder != db.get_setting(self.prefs, "shared_folder", ""):
                if group:
                    group.close()
                self.banner.hide()
                return
            if error:
                self.team_error = str(error)
            else:
                self.use_team(group)
            done(self.team_error)
        in_background(self.root, lambda: open_team(folder, user), finished)

    def reset_team(self):
        """Закрывает прежнее подключение к общей папке и заводит фоновую проверку связи для
        папки из настроек. Возвращает эту папку («» — не задана)."""
        if self.team:
            self.team.close()
        self.team, self.team_error = None, None
        folder = db.get_setting(self.prefs, "shared_folder", "")
        if self.probe and self.probe.folder != folder:
            self.probe.stop()
            self.probe = None
        if folder and self.probe is None:
            self.probe = team.Probe(folder)
        return folder

    def use_team(self, group):
        self.team = group
        self.seen_seq, self.team_counter, self.list_counter = None, None, None
        in_background(self.root, self.team.backup_daily, lambda result, error: None)

    @staticmethod
    def offline_text(folder):
        return (f"Нет связи с общей папкой\n{folder}\n\nПроверьте сеть (VPN). Когда связь "
                "появится, программа подключится сама.")

    def share_online(self):
        """Можно ли сейчас обращаться к общей папке, не рискуя «повесить» окно."""
        return self.team is not None and self.probe is not None and self.probe.online()

    def go_offline(self):
        """Пропала связь с общей папкой: убираем общие списки и, если был открыт общий,
        открываем личный. Когда связь вернётся, watch_changes подключится снова.
        Возвращает название общего списка, который был открыт (или None)."""
        name = None
        # Файлы в сетевой папке закрываем в фоне: без связи закрытие тоже может «повиснуть»
        closing = [self.list_conns.pop(i["id"]) for i in self.lists
                   if i["shared"] and i["id"] in self.list_conns]
        if self.team:
            closing.append(self.team.conn)
        for conn in closing:
            if isinstance(conn, db.SharedConnection):
                conn.reading = False  # отложенный end_reading больше не трогает соединение
        if self.list_id and self.current_list()["shared"]:
            self.lost_list, name = self.list_id, self.current_list()["name"]
            self.list_id = None
            self.editing = None
            self.switch_list(db.PERSONAL)
        threading.Thread(target=close_quietly, args=(closing,), daemon=True).start()
        self.team = None
        self.team_error = self.offline_text(db.get_setting(self.prefs, "shared_folder", ""))
        self.load_lists()
        self.show_offline_banner(name)
        return name

    def show_offline_banner(self, lost_name=None, again=False):
        """Полоса «нет связи» — висит, пока связь не вернётся."""
        if again:
            text = "Связи с общей папкой по-прежнему нет. Проверьте Wi-Fi или VPN."
        else:
            text = "Нет связи с общей папкой (сеть, VPN) — общие списки пока недоступны."
        if lost_name:
            text += f" Список «{lost_name}» закрыт, открыт личный."
        text += " Когда связь появится, программа подключится сама."
        self.banner.show("alert", text, "Подключиться снова", self.try_reconnect)

    def reconnect_team(self):
        """Связь с общей папкой вернулась — подключаемся и сообщаем об этом. Список, который
        был открыт до обрыва, сами не открываем (человек мог уже работать в другом) —
        предлагаем кнопкой на полосе."""
        if self.connecting:  # папку из настроек сейчас открывают в фоне
            return
        if self.connect_team():
            self.reconnect_at = time_module.monotonic() + 30  # не вышло — попробуем позже
            return
        self.load_lists()
        lost, self.lost_list = self.lost_list, None
        item = next((i for i in self.lists if i["id"] == lost), None)
        if item and item["id"] != self.list_id:
            self.banner.show("good", "Связь с общей папкой восстановлена — общие списки снова "
                             "доступны.", f"Открыть «{item['name']}»",
                             lambda: (self.banner.hide(), self.switch_list(item["id"])),
                             hide_after=20_000)
        else:
            self.banner.show("good", "Связь с общей папкой восстановлена — общие списки снова "
                             "доступны.", hide_after=10_000)

    def user_name(self):
        return db.get_setting(self.prefs, "user_name", "") or os.environ.get("USERNAME", "Я")

    def load_lists(self):
        """Все списки: сначала личные, потом общие."""
        lists = [dict(item, shared=False) for item in db.list_registry(self.prefs)]
        if self.team:
            try:
                shared = self.team.lists()
                lists += shared
                # запоминаем, какие общие списки есть, — чтобы показывать их в меню и без связи
                seen = {"folder": self.team.folder,
                        "lists": [{"id": i["id"], "name": i["name"]} for i in shared]}
                if seen != db.get_json_setting(self.prefs, "shared_lists_seen", {}):
                    db.set_json_setting(self.prefs, "shared_lists_seen", seen)
            except sqlite3.Error as error:
                self.team, self.team_error = None, str(error)
        self.lists = lists

    def unreachable_lists(self):
        """Общие списки, которые были в общей папке при последней связи с ней."""
        seen = db.get_json_setting(self.prefs, "shared_lists_seen", {})
        folder = db.get_setting(self.prefs, "shared_folder", "")
        return seen.get("lists", []) if folder and seen.get("folder") == folder.strip() else []

    def try_reconnect(self):
        """Пункт меню «Подключиться снова»."""
        self.reconnect_at = 0
        if self.probe and self.probe.online():
            self.reconnect_team()
        if self.team is None:
            lost = next((i["name"] for i in self.unreachable_lists() if i["id"] == self.lost_list), None)
            self.show_offline_banner(lost, again=True)

    def show_units(self):
        """☰ Меню → Бизнес-единицы: справочник текущего списка."""
        self.finish_editing()
        others = [(i["id"], i["name"]) for i in self.lists if i["id"] != self.list_id]
        UnitsDialog(self.root, self.conn, self.current_list()["name"], self.created_by(), others,
                    self.units_list_conn).show()
        self.refresh(select_id=self.current_id())

    def units_list_conn(self, list_id):
        """Соединение с другим списком — взять из него бизнес-единицы."""
        item = next(i for i in self.lists if i["id"] == list_id)
        if item["shared"] and not self.share_online():
            raise OSError("общая папка сейчас недоступна")
        return self.list_conn(list_id)

    def list_conn(self, list_id):
        """Соединение с файлом списка (открывается один раз и потом переиспользуется)."""
        if list_id not in self.list_conns:
            item = next(i for i in self.lists if i["id"] == list_id)
            if item["shared"]:
                conn = db.connect(self.team.path(item), timeout=team.TIMEOUT, shared=True)
                conn.root = self.root  # чтения одного действия — одним обращением к сети
                self.list_conns[list_id] = conn
            else:
                self.list_conns[list_id] = db.connect(db.list_path(item))
        return self.list_conns[list_id]

    def forget_list(self, list_id):
        conn = self.list_conns.pop(list_id, None)
        if conn is not None and conn is not self.prefs:
            conn.close()

    def current_list(self):
        return next(i for i in self.lists if i["id"] == self.list_id)

    def smart_rows(self):
        """Прошлые задачи списка для умных подсказок (уже прочитанные refresh — по сети заново
        не ходим) или None, если подсказки выключены в настройках."""
        if not self.smart_on:
            return None
        return getattr(self, "all_rows", None) or []

    def created_by(self):
        """Кто создаёт или меняет задачу: в общем списке — имя участника, в личном — никто."""
        return self.user_name() if self.list_id and self.current_list()["shared"] else None

    def members(self):
        """Участники для выбора исполнителя (None — личный список)."""
        if not (self.list_id and self.current_list()["shared"]):
            return None
        names = set(self.assignees.values()) | {self.user_name()}
        try:
            names |= set(self.team.members()) if self.share_online() else set()
        except sqlite3.Error:
            pass
        return sorted(names, key=str.casefold)

    def show_list_name(self):
        item = self.current_list()
        # «Мои задачи» имеет смысл только в общем списке
        if item["shared"]:
            self.mine_frame.pack(side="left", padx=(12, 0), after=self.filters_frame)
        else:
            self.mine_frame.pack_forget()
            self.only_mine.set(False)
        mark = "  · общий" if item["shared"] else ""
        self.list_button.configure(text=f"{item['name']}{mark}  ▾")
        self.root.title(f"{APP_NAME} — {item['name']}{' (общий)' if item['shared'] else ''}")

    def show_lists_menu(self):
        if self.share_online():  # вдруг кто-то добавил общий список
            self.load_lists()
        elif self.team:  # связь только что пропала, а watch_changes ещё не заметил
            self.go_offline()
        menu = PopupMenu()
        menu.command("Мои списки", None, enabled=False)
        for item in self.lists:
            if not item["shared"]:
                menu.command(item["name"], lambda i=item["id"]: self.switch_list(i),
                             checked=item["id"] == self.list_id)
        menu.separator()
        offline = self.team is None and bool(db.get_setting(self.prefs, "shared_folder", ""))
        menu.command("Общие списки — нет связи" if offline else "Общие списки", None, enabled=False)
        if offline:
            # списки не прячем: видно, что они есть, но сейчас недоступны
            for item in self.unreachable_lists():
                menu.command(item["name"], None, accel="нет связи", enabled=False)
            menu.command("Подключиться снова", self.try_reconnect)
            menu.command("Настройки общей папки…", lambda: self.show_settings("sharing"))
        elif self.team:
            shared = [i for i in self.lists if i["shared"]]
            for item in shared:
                menu.command(item["name"], lambda i=item["id"]: self.switch_list(i),
                             checked=item["id"] == self.list_id)
            if not shared:
                menu.command("пока нет — создайте первый", None, enabled=False)
        else:
            menu.command("Подключить общие списки…", lambda: self.show_settings("sharing"))
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
        if self.banner.kind == "hint":  # совет был про задачу прежнего списка
            self.banner.hide()
        if self.list_id is not None:
            self.finish_editing()  # спросит, сохранить ли незаконченную правку задачи
            self.clear_selection()
        try:
            if any(i["id"] == list_id and i["shared"] for i in self.lists) and not self.share_online():
                raise sqlite3.OperationalError("нет связи с общей папкой")  # не ждём сеть зря
            conn = self.list_conn(list_id)
            db.list_statuses(conn)  # проверка, что файл читается
        except (sqlite3.Error, StopIteration) as error:
            self.forget_list(list_id)
            item = next((i for i in self.lists if i["id"] == list_id), None)
            if item is None or item["shared"]:
                text = ("Не удалось открыть общий список — общая папка сейчас недоступна. "
                        "Проверьте сеть (VPN) и попробуйте ещё раз.")
            else:
                text = (f"Не удалось открыть список «{item['name']}».\n\n{error}\n\n"
                        f"Файл списка: {db.list_path(item)}")
            ui.showerror(APP_NAME, text, parent=self.root)
            return
        self.list_id, self.conn = list_id, conn
        self.quick_draft = None  # колонки другого списка — другие
        self.fresh_ids = []
        self.list_counter = None
        db.set_setting(self.prefs, "current_list", list_id)
        self.show_list_name()
        self.refresh()

    def new_list(self):
        result = NewListDialog(self.root, can_share=self.team is not None).show()
        if not result:
            return
        name, shared = result
        if shared:
            try:
                item = self.team.add_list(name, self.user_name())
            except (sqlite3.Error, OSError):
                ui.showerror(APP_NAME, "Не удалось создать общий список — общая папка "
                                     "недоступна.", parent=self.root)
                return
        else:
            file = db.new_list_file()
            item = {"id": file.removesuffix(".db"), "name": name, "file": file}
            db.save_registry(self.prefs, db.list_registry(self.prefs) + [item])
        self.load_lists()
        self.switch_list(item["id"])

    def rename_list(self):
        item = self.current_list()
        name = NameDialog(self.root, "Переименовать список", "Название списка", item["name"]).show()
        if not name or name == item["name"]:
            return
        if item["shared"] and self.team_missing():
            return
        if item["shared"]:
            self.team.rename_list(item["id"], name)
        else:
            registry = db.list_registry(self.prefs)
            next(i for i in registry if i["id"] == item["id"])["name"] = name
            db.save_registry(self.prefs, registry)
        self.load_lists()
        self.show_list_name()

    def team_missing(self):
        """Общая папка сейчас не подключена (подключается в фоне или нет связи) — говорим об
        этом и возвращаем True: переименовать или удалить общий список пока нельзя."""
        if self.team is not None:
            return False
        if self.connecting:
            text = "Общая папка ещё подключается. Попробуйте через минуту."
        else:
            text = "Нет связи с общей папкой — общий список сейчас нельзя изменить."
        ui.showerror(APP_NAME, text, parent=self.root)
        return True

    def delete_list(self):
        item = self.current_list()
        if item["id"] == db.PERSONAL or (item["shared"] and self.team_missing()):
            return
        count = db.count_tasks(self.conn)
        what = f"вместе с задачами ({count} шт.)" if count else "(задач в нём нет)"
        everyone = "\n\nЭто общий список — он пропадёт у всех участников." if item["shared"] else ""
        if not ui.askyesno(
            "Удалить список?",
            f"Удалить список «{item['name']}» {what}?{everyone}\n\nЕсли задачи нужны — сначала "
            "перенесите их в другой список (правая кнопка мыши → «Переместить в список») или "
            "выгрузите в CSV.",
            icon="warning", default="no", parent=self.root,
        ):
            return
        self.switch_list(db.PERSONAL)
        self.forget_list(item["id"])
        if item["shared"]:
            self.team.delete_list(item)
        else:
            db.save_registry(self.prefs, [i for i in db.list_registry(self.prefs) if i["id"] != item["id"]])
            try:
                db.list_path(item).unlink()
            except OSError:
                pass  # файл занят или уже удалён — список всё равно убран из программы
        self.load_lists()

    def move_to_list(self, task_id, list_id):
        self.finish_editing()
        target = next(i for i in self.lists if i["id"] == list_id)
        db.move_task_to(self.conn, task_id, self.list_conn(list_id))
        self.clear_selection()
        self.refresh()
        self.side.totoro.show(f"Задача перенесена в список «{target['name']}».", mood="done")

    def check_assigned(self):
        """Кто-то назначил на меня задачу в общем списке — сообщаем (один раз на задачу).
        Задачи, которые были назначены до первого подключения к списку, не показываем."""
        known = set(db.get_json_setting(self.prefs, "known_assigned", []))
        seen_lists = set(db.get_json_setting(self.prefs, "assigned_seen_lists", []))
        me, lines, now_known = self.user_name(), [], set()
        for item in [i for i in self.lists if i["shared"]]:
            if not self.share_online():
                now_known |= {k for k in known if k.startswith(item["id"] + "|")}
                continue
            try:
                tasks = db.assigned_to(self.list_conn(item["id"]), me)
            except (sqlite3.Error, StopIteration):
                now_known |= {k for k in known if k.startswith(item["id"] + "|")}
                continue
            for task_id, title, by in tasks:
                key = f"{item['id']}|{task_id}"
                now_known.add(key)
                if key not in known and item["id"] in seen_lists and by and by != me:
                    lines.append((f"• {title} — назначил(а) {by}  (список «{item['name']}»)",
                                  (item["id"], task_id)))
            seen_lists.add(item["id"])
        if now_known != known:
            db.set_json_setting(self.prefs, "known_assigned", sorted(now_known))
        if seen_lists != set(db.get_json_setting(self.prefs, "assigned_seen_lists", [])):
            db.set_json_setting(self.prefs, "assigned_seen_lists", sorted(seen_lists))
        if lines:
            self.root.deiconify()
            self.root.lift()
            self.root.bell()
            chosen = self.ask_open_task("Вам назначены задачи", "Вам назначены задачи:", lines)
            if chosen:
                self.open_task(*chosen)
            elif self.list_id and self.current_list()["shared"]:
                self.refresh(select_id=self.current_id())

    def on_error(self, kind, error, trace):
        """Ошибка во время работы. Если пропала связь с общей папкой — объясняем и открываем
        личный список, чтобы можно было продолжать работать."""
        if isinstance(error, sqlite3.Error) and self.list_id and self.current_list()["shared"]:
            name = self.go_offline()
            ui.showerror(
                APP_NAME, f"Пропала связь с общим списком «{name}» — общая папка недоступна "
                "(сеть, VPN) или файл занят слишком долго.\n\nОткрыт личный список. Последнее "
                "действие в общем списке могло не сохраниться — проверьте его, когда связь "
                "появится.", parent=self.root)
            return
        tk.Tk.report_callback_exception(self.root, kind, error, trace)

    def watch_changes(self):
        """Раз в несколько секунд: не изменил ли кто-то открытый общий список или перечень
        общих списков. Перерисовываем, только если что-то изменилось.
        Заодно следит за связью с общей папкой: пропала — убираем общие списки,
        вернулась — подключаемся снова."""
        probe = self.probe
        if self.team and not self.share_online():
            self.go_offline()
        elif self.team is None:
            if probe and probe.online() and time_module.monotonic() >= self.reconnect_at:
                self.reconnect_team()
        elif probe.seq != self.seen_seq:
            # Только что была удачная проверка связи: сеть точно есть — можно читать.
            # Само окно к сетевой папке ходит только в такие моменты (и когда вы что-то делаете).
            self.seen_seq = probe.seq
            try:
                self.on_fresh_probe(probe)
            except sqlite3.Error:
                pass  # связь пропала — проверка это заметит
        if self.team and probe:
            probe.watch = self.team.path(self.current_list()) if self.current_list()["shared"] else None
        self.check_local_changes()
        self.root.after(WATCH_EVERY_MS, self.watch_changes)

    def check_local_changes(self):
        """Раз в секунду: не изменил ли открытый список на этом компьютере кто-то другой —
        телефон (через значок в трее). PRAGMA data_version меняется, только когда файл
        записало другое соединение, — свои правки окна не в счёт."""
        now = time_module.monotonic()
        if now < self.local_check_at or self.list_id is None or self.current_list()["shared"]:
            return
        self.local_check_at = now + 1
        if self.dragging():
            return  # перерисуем после перетаскивания
        try:
            version = (self.list_id, self.conn.execute("PRAGMA data_version").fetchone()[0])
        except sqlite3.Error:
            return
        seen, self.local_version = self.local_version, version
        if seen and seen[0] == version[0] and seen[1] != version[1]:
            self.refresh(select_id=self.current_id())

    def on_fresh_probe(self, probe):
        """Фоновая проверка только что дочиталась до папки: смотрим, не поменял ли кто-то
        перечень общих списков или открытый список, и не пора ли о чём-то напомнить."""
        if probe.team_counter != self.team_counter:
            first = self.team_counter is None
            self.team_counter = probe.team_counter
            if not first:
                self.load_lists()
                if not any(i["id"] == self.list_id for i in self.lists):
                    self.forget_list(self.list_id)
                    self.list_id = None
                    self.switch_list(db.PERSONAL)
                    self.side.totoro.show("Общий список, который был открыт, удалил другой "
                                          "участник.", mood="alert")
                else:
                    self.show_list_name()
        self.check_list_changed(probe)
        if self.reminders_due:
            self.reminders_due = False
            self.do_check_reminders()

    def check_list_changed(self, probe):
        """Перерисовывает открытый общий список, если его поменял кто-то другой."""
        if not (self.current_list()["shared"] and probe.list_counter) or self.dragging():
            return
        path, counter = probe.list_counter
        if path != self.team.path(self.current_list()):
            return  # проверка ещё смотрела на прежний список
        seen, self.list_counter = self.list_counter, (path, counter)
        # Свои записи, которых проверка ещё могла не увидеть (она читает файл
        # параллельно с окном), — «в зачёт»; через несколько секунд зачёт сгорает
        if self.conn.own_writes:
            self.own_credit += self.conn.own_writes
            self.conn.own_writes = 0
            self.credit_until = time_module.monotonic() + 5
        elif time_module.monotonic() > self.credit_until:
            self.own_credit = 0
        if not (seen and seen[0] == path):  # первая проверка этого списка — точка отсчёта
            self.own_credit = 0
            return
        grown = counter - seen[1]
        if grown > self.own_credit:  # список менял кто-то ещё
            self.own_credit = 0
            self.refresh(select_id=self.current_id())
        else:
            self.own_credit -= grown

    # --- обновления ---

    def auto_update_enabled(self):
        return db.get_setting(self.prefs, "update_auto", "1") == "1"

    def auto_check_update(self):
        """При запуске, не чаще раза в день. Без интернета — молча пропускаем."""
        if self.tour is not None:
            self.root.after(5000, self.auto_check_update)  # не мешаем туру — проверим после
            return
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
        """Пункт меню «Проверить обновления…»: сразу показывает окошко «Проверяю…» с «Отменой» —
        в медленной сети ответа GitHub можно ждать долго, и без окошка кажется, что всё зависло."""
        waiting = CheckingDialog(self.root)

        def done(release, error):
            if waiting.cancelled:
                return  # пользователь передумал ждать — ответ уже не нужен
            waiting.close()
            if error:
                ui.showwarning(APP_NAME, str(error), parent=self.root)
            elif updater.is_newer(release["version"], APP_VERSION):
                UpdateDialog(self.root, release, self.close)
            else:
                ui.showinfo(APP_NAME, f"У вас последняя версия — {APP_VERSION}.", parent=self.root)
        in_background(self.root, updater.fetch_latest, done)

    def restart(self):
        """Перезапуск программы (например, чтобы включить другую тему)."""
        if getattr(sys, "frozen", False):  # установленный ToDoro.exe
            command = [sys.executable, RESTART_FLAG]
        else:  # запуск из исходного кода: тот же Python (pythonw — без чёрного окна)
            command = [sys.executable, str(Path(__file__).resolve()), RESTART_FLAG]
        try:
            subprocess.Popen(command, close_fds=True)
        except OSError as error:
            ui.showerror(APP_NAME, f"Не удалось перезапустить программу:\n{error_text(error)}\n\n"
                         "Закройте и откройте её сами.", parent=self.root)
            return
        self.close()

    # --- значок в трее ---

    def start_tray(self):
        """Значок в трее с Ctrl+Alt+T запускается вместе с Windows (выключается в настройках).
        При первом запуске версии со значком включаем его сами и показываем прямо сейчас."""
        if os.name != "nt":
            return
        if not db.get_setting(self.prefs, "tray_offered"):
            tray.set_autostart(True)
            db.set_setting(self.prefs, "tray_offered", "1")
        if tray.autostart_enabled():
            tray.set_autostart(True)  # путь к программе мог смениться (переустановка в другую папку)
            tray.start()

    # --- задача из письма Outlook ---

    def mail_task(self, mail):
        """Значения формы новой задачи по письму: исполнитель — тот, кто создаёт задачу."""
        members = self.members()
        return dict(title=mail["title"], body=mail["body"], due_at=mail["due_at"], remind_before=None,
                    urgent=False, important=mail["important"],
                    status_id=db.list_statuses(self.conn)[0][0],
                    assignee=self.user_name() if members is not None else None,
                    initiator=self.user_name() if members is not None else None, version=None)

    def from_outlook(self, quiet=False):
        """Задача из письма, выделенного в Outlook. Кнопка «Из письма» — форма поверх окна ToDoro;
        quiet (Ctrl+Alt+T, значок в трее) — только форма поверх Outlook, главное окно не выходит вперёд."""
        grab = self.root.grab_current()
        if grab is not None:  # открыто другое окно (настройки, форма) — сначала его нужно закрыть
            if grab is not self.root:
                bring_to_front(grab)
            return
        if not quiet:
            self.bring_to_front()
        parent = None if quiet else self.root  # без окна-родителя форма — отдельное окно по центру экрана
        self.finish_editing()
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            mails = outlook.read_selected()
        except outlook.OutlookError as error:
            ui.showinfo("Задача из письма", str(error), parent=parent)
            return self.mail_done()
        finally:
            self.root.configure(cursor="")
        list_name = self.current_list()["name"]
        if len(mails) > 1:
            if not ui.askyesno("Задачи из писем", f"В Outlook выделено писем: {len(mails)}.\n\n"
                               f"Создать по задаче из каждого в списке «{list_name}»?",
                               parent=parent):
                return self.mail_done()
            created, skipped = [], 0
            for mail in mails:
                if db.find_by_mail(self.conn, mail["mail_id"]):
                    skipped += 1
                else:
                    created.append(self.create_from_mail(mail, self.mail_task(mail)))
            self.show_new_tasks(created)
            if skipped or quiet:
                ui.showinfo("Задачи из писем", f"Создано задач: {len(created)} в списке «{list_name}»."
                            + (f"\nПропущено писем: {skipped} — по ним задачи уже есть." if skipped else ""),
                            parent=parent)
            return self.mail_done()
        mail = mails[0]
        existing = db.find_by_mail(self.conn, mail["mail_id"])
        if existing and ui.askyesno("Задача из письма", "По этому письму уже есть задача "
                                    f"№{existing} в списке «{list_name}». Открыть её?\n\n"
                                    "«Нет» — создать ещё одну.", parent=parent):
            self.show_new_tasks([existing], fresh=False)  # задача старая — место прежнее
            self.bring_to_front()  # открыть задачу — значит показать окно ToDoro
            return
        note = f"Из письма Outlook, в список «{list_name}»."
        if mail["files"]:
            note += " Будут приложены: " + ", ".join(name for name, _ in mail["files"])
        dialog = TaskDialog(self.root, self.mail_task(mail), db.list_statuses(self.conn),
                            members=self.members(), title="Новая задача из письма", note=note,
                            standalone=quiet, history=self.smart_rows(), hints=True,
                            units=db.list_units(self.conn))
        self.root.wait_window(dialog)
        if dialog.result:
            self.show_new_tasks([self.create_from_mail(mail, dialog.result)])
        self.mail_done()

    def mail_done(self):
        """ToDoro запустили только ради задачи из письма или снимка (окно так и не показали) —
        закрываемся."""
        if self.hidden:
            self.close()

    # --- задача со снимка области экрана ---

    def take_snip(self, hide):
        """Выделение области экрана мышью. hide — сначала убрать окно ToDoro, чтобы оно не
        закрывало то, что снимают. Возвращает (картинка, [(имя файла, PNG)]) или None."""
        shown = hide and not self.hidden and self.root.state() == "normal"
        if shown:
            self.root.withdraw()
            self.root.update()
            time_module.sleep(0.25)  # Windows убирает окно с экрана с небольшой анимацией
        try:
            image = snip.select_area(self.root)
        except Exception as error:  # noqa: BLE001 — нет Pillow, не удалось снять экран
            image = None
            ui.showerror(APP_NAME, f"Не удалось сделать снимок экрана:\n{error_text(error)}",
                         parent=None if self.hidden else self.root)
        finally:
            if shown:
                self.root.deiconify()
                self.bring_to_front()
        if image is None:
            return None
        from io import BytesIO
        buffer = BytesIO()
        image.save(buffer, "PNG")
        name = datetime.now().strftime("Снимок %d.%m.%Y %H-%M-%S.png")
        return image, [(name, buffer.getvalue())]

    def from_screen(self, quiet=False):
        """Новая задача со снимком выделенной области экрана. Кнопка «Снимок» — окно ToDoro
        прячется на время выделения; quiet (Ctrl+Alt+S, значок в трее) — главное окно не выходит
        вперёд, форма появляется отдельным окном поверх остальных программ."""
        grab = self.root.grab_current()
        if grab is not None:  # открыто другое окно (настройки, форма) — сначала его нужно закрыть
            if grab is not self.root:
                bring_to_front(grab)
            return
        self.finish_editing()
        snap = self.take_snip(hide=not quiet)
        if snap is None:
            return self.mail_done()
        image, files = snap
        members = self.members()
        statuses = db.list_statuses(self.conn)
        task = dict(title="", body="", due_at=None, remind_before=None, urgent=False,
                    important=False, status_id=statuses[0][0],
                    assignee=self.user_name() if members is not None else None,
                    initiator=self.user_name() if members is not None else None, version=None)
        note = (f"Со снимка экрана, в список «{self.current_list()['name']}». "
                f"Снимок {image.width} × {image.height} будет приложен к задаче.")
        dialog = TaskDialog(self.root, task, statuses, members=members,
                            title="Новая задача со снимка экрана", note=note,
                            standalone=quiet or self.hidden, image=image,
                            history=self.smart_rows(), hints=True, units=db.list_units(self.conn))
        self.root.wait_window(dialog)
        if dialog.result:
            task_id = db.add_task(self.conn, dialog.result["title"],
                                  status_id=dialog.result["status_id"], created_by=self.created_by())
            self.apply_edit(task_id, dialog.result, refresh=False)
            self.attach(task_id, files)
            self.show_new_tasks([task_id])
        self.mail_done()

    def snip_to_task(self, task_id):
        """Кнопка «Снимок» на вкладке «Файлы»: приложить к задаче снимок области экрана."""
        if task_id is None:
            return
        snap = self.take_snip(hide=True)
        if snap is not None:
            self.attach(task_id, snap[1])

    def create_from_mail(self, mail, result):
        task_id = db.add_task(self.conn, result["title"], status_id=result["status_id"],
                              created_by=self.created_by())
        self.apply_edit(task_id, result, refresh=False)
        db.set_mail_id(self.conn, task_id, mail["mail_id"], mail["mail_from"])
        self.mail_ids.add(task_id)
        if mail["files"]:
            self.attach(task_id, mail["files"])
        outlook.mark_added(mail["entry_id"], mail["store_id"])  # категория «В ToDoro» в Outlook
        return task_id

    def place_flags(self, place):
        """Что задаёт место, куда добавляют задачу: (статус или None, срочно, важно).
        place — ("status", id) колонка доски, ("level", n) четверть матрицы, иначе None."""
        if place and place[0] == "level":
            _, urgent, important, *_ = next(q for q in EisenhowerMatrix.QUADRANTS if q[0] == place[1])
            return None, urgent, important
        if place and place[0] == "status" and place[1] in self.statuses:
            return place[1], False, False
        return None, False, False

    def new_task_menu(self, place, x, y):
        """Правая кнопка по пустому месту колонки, четверти или дня календаря."""
        if place[0] == "status":
            self.lane_menu(place[1], x, y)
            return
        PopupMenu().command("＋  Новая задача…", lambda: self.new_task_at(place)).popup(self.root, x, y)

    def new_task_at(self, place):
        """Окно новой задачи, уже заполненное по месту: день календаря (двойной щелчок или
        правая кнопка) — срок в этот день; колонка доски — её статус; четверть — приоритет."""
        if self.root.grab_current() is not None:
            return  # открыто другое окно
        self.finish_editing()
        members = self.members()
        statuses = db.list_statuses(self.conn)
        status_id, urgent, important = self.place_flags(place)
        due_at, where = None, f"В список «{self.current_list()['name']}»."
        if place and place[0] == "day":
            day = place[1]
            due_at = datetime.combine(day, time(int(DEFAULT_TIME[0]), int(DEFAULT_TIME[1])))
            due_at = due_at.strftime("%Y-%m-%d %H:%M")
            where = f"Срок — {day:%d.%m.%Y}, в список «{self.current_list()['name']}»."
        task = dict(title="", body="", due_at=due_at, remind_before=None,
                    urgent=urgent, important=important, status_id=status_id or statuses[0][0],
                    assignee=self.user_name() if members is not None else None,
                    initiator=self.user_name() if members is not None else None, version=None)
        dialog = TaskDialog(self.root, task, statuses, members=members, title="Новая задача",
                            note=where, history=self.smart_rows(), hints=True,
                            units=db.list_units(self.conn))
        self.root.wait_window(dialog)
        if dialog.result:
            task_id = db.add_task(self.conn, dialog.result["title"],
                                  status_id=dialog.result["status_id"], created_by=self.created_by())
            self.apply_edit(task_id, dialog.result, refresh=False)
            self.show_new_tasks([task_id])

    def show_new_tasks(self, task_ids, fresh=True):
        if not task_ids:
            return
        if fresh:
            self.fresh_ids.extend(task_ids)  # новые — первыми в колонке и списке
        if FILTERS[self.filter.get()] not in (None, False):
            self.filter.set("Все")  # иначе новую задачу может быть не видно
        if self.search_query:
            self.clear_search(refresh=False)
        self.only_mine.set(False)
        if self.view.get() == "calendar":  # новая задача со сроком в другом месяце — листаем к ней
            due = db.get_task(self.conn, task_ids[-1])
            try:
                if due and due[1]:
                    self.calendar.month = datetime.fromisoformat(due[1]).date().replace(day=1)
            except ValueError:
                pass  # испорченный срок — остаёмся в том же месяце
        self.refresh(select_id=task_ids[-1])

    def watch_show_requests(self, event):
        """Кто-то запустил ToDoro ещё раз — показываем это окно (см. single_instance)."""
        try:
            asked = ctypes.windll.kernel32.WaitForSingleObject(event, 0) == 0
        except (AttributeError, OSError):
            return
        if OUTLOOK_FLAG_FILE.exists():  # «ToDoro.exe --outlook» или значок в трее — задача из письма
            try:
                OUTLOOK_FLAG_FILE.unlink()
            except OSError:
                pass
            self.root.after_idle(lambda: self.from_outlook(quiet=True))
        elif SNIP_FLAG_FILE.exists():  # «ToDoro.exe --snip» или значок в трее — задача со снимка
            try:
                SNIP_FLAG_FILE.unlink()
            except OSError:
                pass
            self.root.after_idle(lambda: self.from_screen(quiet=True))
        elif asked:
            self.bring_to_front()
        self.root.after(400, lambda: self.watch_show_requests(event))

    def bring_to_front(self):
        if self.hidden:  # запустили скрытой ради задачи из письма или снимка, а теперь просят окно
            self.show_window()
        elif self.root.state() in ("withdrawn", "iconic"):
            self.root.deiconify()
        bring_to_front(self.root)

    def close(self):
        self.finish_editing()  # есть несохранённая правка задачи — спросим, сохранить ли её
        for conn in self.list_conns.values():
            conn.close()
        if self.team:
            self.team.close()
        self.root.destroy()


# Программа работает в одном экземпляре: повторный запуск только показывает уже открытое окно
INSTANCE_MUTEX = "Local\\ToDoro-single-instance"
SHOW_EVENT = "Local\\ToDoro-show-window"
RESTART_FLAG = "--restart"  # перезапуск самой программой: подождать, пока закроется старая копия
# «ToDoro.exe --outlook» — задача из письма, выделенного в Outlook (например, из макроса Outlook).
# Уже открытой копии об этом сообщает файл-флажок: она проверяет его вместе с просьбой показать окно.
OUTLOOK_FLAG = "--outlook"
OUTLOOK_FLAG_FILE = db.DATA_DIR / "from-outlook.flag"
SNIP_FLAG = "--snip"  # «ToDoro.exe --snip» — задача со снимка области экрана
SNIP_FLAG_FILE = db.DATA_DIR / "from-screen.flag"

# Сочетание клавиш «задача из письма» работает во всей Windows, пока ToDoro открыт
OUTLOOK_HOTKEY = (0x0002 | 0x0001 | 0x4000, ord("T"))  # MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, T
OUTLOOK_HOTKEY_NAME = "Ctrl+Alt+T"
SNIP_HOTKEY = (0x0002 | 0x0001 | 0x4000, ord("S"))  # задача со снимка области экрана
SNIP_HOTKEY_NAME = "Ctrl+Alt+S"


def start_hotkey(root, hotkeys):
    """Регистрирует сочетания клавиш для всей Windows: hotkeys — [(сочетание, действие)].
    Нажатия ловит отдельный поток (у него своя очередь сообщений Windows), а действие
    выполняется в главном потоке окна. Сочетание занято (обычно значком ToDoro в трее — он сам
    разбудит это окно) — поток пробует снова каждые 5 секунд: значок закроют — сочетания
    продолжат работать."""
    pressed = [threading.Event() for _ in hotkeys]

    def listen():
        try:
            user32 = ctypes.windll.user32
            waiting = set(range(len(hotkeys)))
            timer = user32.SetTimer(None, 0, 5000, None)

            def register():
                for index in sorted(waiting):
                    if user32.RegisterHotKey(None, index + 1, *hotkeys[index][0]):
                        waiting.discard(index)
                if not waiting:
                    user32.KillTimer(None, timer)

            register()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and 1 <= msg.wParam <= len(hotkeys):  # WM_HOTKEY
                    pressed[msg.wParam - 1].set()
                elif msg.message == 0x0113 and waiting:  # WM_TIMER
                    register()
        except (AttributeError, OSError):
            pass

    threading.Thread(target=listen, daemon=True).start()

    def poll():
        for event, (_, action) in zip(pressed, hotkeys):
            if event.is_set():
                event.clear()
                action()
        root.after(150, poll)

    poll()


def wake_app(flag_file=None):
    """Для значка в трее: показать окно ToDoro; flag_file — ещё и сделать задачу (из письма
    Outlook или со снимка экрана). ToDoro открыт — будим его (как при повторном запуске),
    не открыт — запускаем."""
    if flag_file:
        try:
            flag_file.parent.mkdir(parents=True, exist_ok=True)
            flag_file.touch()
        except OSError:
            pass
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    # Значок только что получил нажатие — разрешаем окну ToDoro выйти на передний план
    ctypes.windll.user32.AllowSetForegroundWindow(wintypes.DWORD(-1).value)  # ASFW_ANY
    event = kernel32.OpenEventW(0x0002, False, SHOW_EVENT)  # EVENT_MODIFY_STATE
    if event:
        kernel32.SetEvent(event)
        kernel32.CloseHandle(event)
    else:
        flag = {OUTLOOK_FLAG_FILE: OUTLOOK_FLAG, SNIP_FLAG_FILE: SNIP_FLAG}.get(flag_file)
        tray.launch(*([flag] if flag else []))


def run_tray():
    tray.run(ICON_PATH, f"{APP_NAME}\n{OUTLOOK_HOTKEY_NAME} — задача из письма Outlook\n"
                        f"{SNIP_HOTKEY_NAME} — задача со снимка экрана",
             open_app=wake_app, actions=[
                 (OUTLOOK_HOTKEY, OUTLOOK_HOTKEY_NAME, "Задача из письма Outlook",
                  lambda: wake_app(OUTLOOK_FLAG_FILE)),
                 (SNIP_HOTKEY, SNIP_HOTKEY_NAME, "Задача со снимка экрана",
                  lambda: wake_app(SNIP_FLAG_FILE))],
             on_start=lambda: phone.start_in_background(APP_VERSION))  # связь с телефоном


def single_instance(wait_ms=0):
    """Занимает метку «ToDoro уже запущен». Возвращает событие, по которому другие копии
    просят показать окно, или None, если ToDoro уже работает (ей отправлена просьба)."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = kernel32.CreateEventW.restype = wintypes.HANDLE
        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetEvent.argtypes = kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        mutex = kernel32.CreateMutexW(None, False, INSTANCE_MUTEX)
        if not mutex:
            return 0  # не получилось проверить — просто запускаемся
        # 0 — метка наша, 0x80 — прошлая копия завершилась аварийно; 0x102 — занято
        if kernel32.WaitForSingleObject(mutex, wait_ms) in (0, 0x80):
            return kernel32.CreateEventW(None, False, False, SHOW_EVENT) or 0
        event = kernel32.OpenEventW(0x0002, False, SHOW_EVENT)  # EVENT_MODIFY_STATE
        if event:
            ctypes.windll.user32.AllowSetForegroundWindow(wintypes.DWORD(-1).value)  # ASFW_ANY
            kernel32.SetEvent(event)
            kernel32.CloseHandle(event)
        return None
    except (AttributeError, OSError):
        return 0  # не Windows


if __name__ == "__main__":
    if tray.TRAY_FLAG in sys.argv:  # значок в трее (запускается вместе с Windows)
        run_tray()
        sys.exit(0)
    if tray.TRAY_QUIT_FLAG in sys.argv:  # установщик просит закрыть значок
        tray.stop()
        sys.exit(0)
    quiet_task = next((flag for flag in (OUTLOOK_FLAG, SNIP_FLAG) if flag in sys.argv), None)
    if quiet_task:  # только задача из письма или со снимка — открытой копии скажет файл-флажок
        flag_file = OUTLOOK_FLAG_FILE if quiet_task == OUTLOOK_FLAG else SNIP_FLAG_FILE
        try:
            flag_file.parent.mkdir(parents=True, exist_ok=True)
            flag_file.touch()
        except OSError:
            pass
    show_event = single_instance(15000 if RESTART_FLAG in sys.argv else 0)
    if show_event is None:
        sys.exit(0)  # ToDoro уже открыт — его окно само выйдет вперёд
    # Чтобы на панели задач была наша иконка, а не значок Python.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ToDoro.App")
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    app = TodoApp(root, hidden=bool(quiet_task))  # только задача из письма или снимка — без окна
    if show_event:
        app.watch_show_requests(show_event)
    root.mainloop()
