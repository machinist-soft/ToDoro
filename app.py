"""ToDoro — список дел с Тоторо."""
import calendar
import ctypes
import os
import re
import tkinter as tk
from urllib.parse import quote
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

import db
from help_text import HELP

APP_NAME = "ToDoro"  # ToDo + Totoro
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
    "В работе": False,
    "Выполненные": True,
}
EMPTY_TEXT = {
    "Все": "Задач пока нет — добавьте первую в поле выше",
    "В работе": "Все задачи выполнены 🎉",
    "Выполненные": "Выполненных задач пока нет",
}

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

PLACEHOLDER = "Новая задача… (Enter — добавить)"


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

    # Галочки «Срочно» / «Важно»
    style.configure("TCheckbutton", background=BG, foreground=TEXT, font=FONT,
                    indicatorbackground=SURFACE, indicatorforeground="white",
                    upperbordercolor="#b8c0cc", lowerbordercolor="#b8c0cc",
                    focuscolor=BG, indicatormargin=(0, 0, 8, 0), padding=(0, 2))
    style.map("TCheckbutton",
              indicatorbackground=[("selected", ACCENT), ("active", ACCENT_SOFT)],
              upperbordercolor=[("selected", ACCENT)], lowerbordercolor=[("selected", ACCENT)],
              background=[("active", BG)])
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
    style.configure("Treeview.Heading", background=SURFACE, foreground=MUTED,
                    font=("Segoe UI Semibold", 9), relief="flat", padding=(10, 8),
                    bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE)
    style.map("Treeview.Heading", background=[("active", SURFACE)])

    # Тонкая полоса прокрутки без стрелок
    style.layout("Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Vertical.TScrollbar", troughcolor=SURFACE, background="#d6dbe4",
                    bordercolor=SURFACE, lightcolor="#d6dbe4", darkcolor="#d6dbe4",
                    gripcount=0, width=8)
    style.map("Vertical.TScrollbar", background=[("active", "#b8c0cc")])


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


def build_email(title, status, priority, due, remind, created, urgent):
    """Тема и текст письма по задаче."""
    subject = f"Задача из {APP_NAME}: {short_text(title)}"
    if urgent:
        subject = "СРОЧНО! " + subject
    level_hint = next((PRIORITY_HINTS[k] for k, v in PRIORITY_NAMES.items() if v and v == priority), "")
    lines = [
        f"Задача: {title}",
        "",
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


def status_text(done, overdue=False):
    if done:
        return "✔  Выполнено"
    return "⚠  Просрочено" if overdue else "○  В работе"


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


class TaskDialog(tk.Toplevel):
    """Окно редактирования задачи: текст, срок и напоминание."""

    def __init__(self, parent, title, due_at, remind_before, urgent=False, important=False):
        super().__init__(parent)
        self.result = None
        self.title("Задача")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)

        body = ttk.Frame(self, padding=(20, 18, 20, 6))
        body.pack(fill="both")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="Задача", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.title_entry = ttk.Entry(body, font=FONT, width=48)
        self.title_entry.grid(row=1, column=0, sticky="we", pady=(4, 14))
        self.title_entry.insert(0, title)

        due = datetime.fromisoformat(due_at) if due_at else None
        ttk.Label(body, text="Срок выполнения", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        due_row = ttk.Frame(body)
        due_row.grid(row=3, column=0, sticky="w", pady=(4, 6))
        self.date = DatePicker(due_row, due.date() if due else None, on_change=self.date_changed)
        self.date.pack(side="left")
        ttk.Label(due_row, text="в").pack(side="left", padx=(14, 8))
        self.hour = ttk.Combobox(due_row, values=HOURS, state="readonly", width=3, font=FONT)
        self.hour.pack(side="left")
        ttk.Label(due_row, text=":").pack(side="left", padx=3)
        self.minute = ttk.Combobox(due_row, values=MINUTES, state="readonly", width=3, font=FONT)
        self.minute.pack(side="left")
        self.hour.set(due.strftime("%H") if due else DEFAULT_TIME[0])
        self.minute.set(due.strftime("%M") if due else DEFAULT_TIME[1])

        quick = ttk.Frame(body)
        quick.grid(row=4, column=0, sticky="w", pady=(2, 14))
        for text, days in (("Сегодня", 0), ("Завтра", 1), ("Через неделю", 7)):
            ttk.Button(quick, text=text, command=lambda d=days: self.set_date(d)).pack(
                side="left", padx=(0, 6))
        ttk.Button(quick, text="Без срока", command=lambda: self.date.set(None)).pack(side="left")

        ttk.Label(body, text="Приоритет", style="Muted.TLabel").grid(row=5, column=0, sticky="w")
        prio_row = ttk.Frame(body)
        prio_row.grid(row=6, column=0, sticky="w", pady=(4, 14))
        self.urgent = tk.BooleanVar(value=bool(urgent))
        self.important = tk.BooleanVar(value=bool(important))
        ttk.Checkbutton(prio_row, text="Срочно", variable=self.urgent,
                        command=self.priority_changed, cursor="hand2").pack(side="left")
        ttk.Checkbutton(prio_row, text="Важно", variable=self.important,
                        command=self.priority_changed, cursor="hand2").pack(side="left", padx=(18, 0))
        self.priority_label = ttk.Label(prio_row, style="Muted.TLabel", compound="left")
        self.priority_label.pack(side="left", padx=(22, 0))
        self.priority_changed()

        ttk.Label(body, text="Напоминание", style="Muted.TLabel").grid(row=7, column=0, sticky="w")
        self.remind = ttk.Combobox(body, values=list(REMIND_OPTIONS), state="readonly",
                                   width=18, font=FONT)
        self.remind.set(REMIND_LABELS.get(remind_before, f"за {remind_before} мин"))
        self.remind.grid(row=8, column=0, sticky="w", pady=(4, 0))

        buttons = ttk.Frame(self, padding=(20, 16, 20, 18))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Сохранить", style="Accent.TButton",
                   command=self.save).pack(side="right")
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.date_changed()
        self.title_entry.focus()
        self.title_entry.icursor("end")
        center_on_screen(self)
        self.grab_set()

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

    def save(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Задача", "Текст задачи не может быть пустым.", parent=self)
            return

        due_at = None
        if self.date.value:
            due = datetime.combine(self.date.value, time(int(self.hour.get()), int(self.minute.get())))
            due_at = due.strftime("%Y-%m-%d %H:%M")

        remind_before = REMIND_OPTIONS.get(self.remind.get())
        if remind_before is not None and due_at is None:
            messagebox.showwarning(
                "Задача", "Чтобы напомнить о задаче, укажите срок.", parent=self,
            )
            return

        self.result = (title, due_at, remind_before, self.urgent.get(), self.important.get())
        self.destroy()


class HelpWindow(tk.Toplevel):
    """Окно справки: оформленный текст из help_text.py."""

    MARKUP = re.compile(r"(\*\*.+?\*\*|\[[^\]]+\]|\{p[123]\})")

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
        folder = str(Path(__file__).parent)
        for kind, line in HELP:
            line = line.replace("{folder}", folder)
            if kind == "li":
                text.insert("end", "•  ", "li")
            self.insert_marked(text, line, kind)
            text.insert("end", "\n", kind)

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
            else:
                text.insert("end", part, kind)


class TodoApp:
    def __init__(self, root):
        self.root = root
        self.conn = db.connect()
        self.due = {}  # id задачи -> срок (для подсветки просроченных)

        root.title(APP_NAME)
        if ICON_PATH.exists():
            root.iconbitmap(default=str(ICON_PATH))  # иконка для всех окон программы
        setup_style(root)
        load_images()
        center_on_screen(root, 1000, 640)
        root.minsize(820, 440)

        page = ttk.Frame(root, padding=(24, 14, 24, 20))
        page.pack(fill="both", expand=True)

        # Заголовок, счётчик задач и Тоторо
        header = ttk.Frame(page)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left", anchor="s")
        self.counter = ttk.Label(header, style="Muted.TLabel")
        self.counter.pack(side="left", padx=(14, 0), pady=(0, 6), anchor="s")
        if "totoro_small" in IMAGES:
            ttk.Label(header, image=IMAGES["totoro_small"]).pack(side="right")
        ttk.Button(header, text="?  Справка", command=self.show_help).pack(
            side="right", padx=(0, 14), anchor="s", pady=(0, 4))

        # Поле ввода и кнопка «Добавить»
        add_row = ttk.Frame(page)
        add_row.pack(fill="x", pady=(10, 14))
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

        # Фильтр в виде сегментов и сортировка
        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(0, 12))
        filters = ttk.Frame(toolbar, style="Segments.TFrame", padding=3)
        filters.pack(side="left")
        self.filter = tk.StringVar(value="Все")
        for name in FILTERS:
            ttk.Radiobutton(filters, text=name, value=name, variable=self.filter,
                            style="Segment.TRadiobutton", command=self.refresh,
                            cursor="hand2").pack(side="left")
        self.sort = ttk.Combobox(toolbar, values=SORTS, state="readonly", width=22, font=FONT_SMALL)
        self.sort.set(SORTS[0])
        self.sort.pack(side="right")
        self.sort.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(toolbar, text="Сортировка:", style="Muted.TLabel").pack(side="right", padx=(0, 8))

        # Кнопки действий (размещаем до таблицы, чтобы таблица их не вытеснила)
        bottom = ttk.Frame(page)
        bottom.pack(side="bottom", fill="x", pady=(14, 0))
        ttk.Button(bottom, text="✔  Выполнено / не выполнено", command=self.toggle).pack(side="left")
        ttk.Button(bottom, text="✎  Изменить", command=self.edit).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="✉  Письмо", command=self.email).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Удалить", style="Danger.TButton",
                   command=self.delete).pack(side="right")
        ttk.Label(bottom, text="ПКМ — меню · F1 — справка",
                  style="Muted.TLabel").pack(side="right", padx=(0, 14))

        # Карточка с таблицей задач
        card = tk.Frame(page, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True)
        inner = ttk.Frame(card, style="Card.TFrame", padding=(6, 4, 4, 6))
        inner.pack(fill="both", expand=True)
        self.scrollbar = ttk.Scrollbar(inner, orient="vertical")
        columns = {
            "status": ("СТАТУС", 140, False),
            "title": ("ЗАДАЧА", 230, True),
            "priority": ("ПРИОРИТЕТ", 140, False),
            "due": ("СРОК", 135, False),
            "remind": ("НАПОМНИТЬ", 110, False),
            "created": ("СОЗДАНА", 135, False),
        }
        # Первый, узкий столбец (#0) — цветная метка приоритета.
        self.tree = ttk.Treeview(
            inner, columns=list(columns), show=("tree", "headings"),
            selectmode="browse", yscrollcommand=self.update_scrollbar,
        )
        self.tree.column("#0", width=30, minwidth=30, stretch=False)
        for key, (text, width, stretch) in columns.items():
            self.tree.heading(key, text=text, anchor="w")
            self.tree.column(key, width=width, stretch=stretch)
        self.tree.tag_configure("done", foreground=DONE)
        self.tree.tag_configure("overdue", foreground=DANGER)
        self.tree.pack(side="left", fill="both", expand=True)
        self.scrollbar.config(command=self.tree.yview)
        self.empty = ttk.Label(inner, style="Empty.TLabel", compound="top",
                               image=IMAGES.get("totoro", ""), justify="center")
        self.tree.bind("<Double-Button-1>", lambda e: self.edit())
        self.tree.bind("<F2>", lambda e: self.edit())
        self.tree.bind("<space>", lambda e: self.toggle())
        self.tree.bind("<Delete>", lambda e: self.delete())
        self.tree.bind("<Control-e>", lambda e: self.email())
        self.tree.bind("<Control-E>", lambda e: self.email())
        self.tree.bind("<Button-3>", self.show_menu)  # правая кнопка мыши
        self.tree.bind("<App>", self.show_menu_for_selected)  # клавиша контекстного меню

        root.bind("<F1>", lambda e: self.show_help())
        self.help_window = None

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.show_placeholder()
        self.entry.focus()
        root.after(1000, self.check_reminders)

    def show_help(self):
        """Открывает справку (или поднимает уже открытое окно справки)."""
        if self.help_window and self.help_window.winfo_exists():
            self.help_window.deiconify()
            self.help_window.lift()
            self.help_window.focus_force()
            return
        self.help_window = HelpWindow(self.root)

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

    # --- таблица ---

    def update_scrollbar(self, first, last):
        """Полоса прокрутки видна, только если задачи не помещаются в окно."""
        if float(first) <= 0 and float(last) >= 1:
            self.scrollbar.pack_forget()
        elif not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="right", fill="y", pady=4, before=self.tree)
        self.scrollbar.set(first, last)

    def refresh(self, select_id=None):
        """Перечитывает задачи из базы (с учётом фильтра) и рисует таблицу заново."""
        rows = db.list_tasks(self.conn)
        active = sum(1 for row in rows if not row[2])
        self.counter.configure(text=f"{active} в работе  ·  {len(rows) - active} выполнено")

        wanted = FILTERS[self.filter.get()]
        rows = [row for row in rows if wanted is None or bool(row[2]) == wanted]
        rows.sort(key=self.sort_key)

        self.tree.delete(*self.tree.get_children())
        self.due = {}
        for task_id, title, done, created, due_at, remind_before, urgent, important in rows:
            remind = REMIND_LABELS.get(remind_before, f"за {remind_before} мин") if due_at else ""
            if remind == "Не напоминать":
                remind = ""
            level = priority_level(urgent, important)
            iid = str(task_id)
            self.tree.insert(
                "", "end", iid=iid, image=IMAGES.get(f"priority_{level}", ""),
                values=(status_text(done), title, PRIORITY_NAMES[level],
                        format_due(due_at), remind, created),
                tags=("done",) if done else (),
            )
            if due_at and not done:
                self.due[iid] = datetime.fromisoformat(due_at)
        self.mark_overdue()

        if self.tree.get_children():
            self.empty.place_forget()
        else:
            self.empty.configure(text=EMPTY_TEXT[self.filter.get()])
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

        if select_id is not None and self.tree.exists(str(select_id)):
            self.tree.selection_set(str(select_id))
            self.tree.see(str(select_id))

    def sort_key(self, row):
        """Выполненные всегда внизу; дальше — по выбранной сортировке."""
        task_id, _, done, _, due_at, _, urgent, important = row
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
                self.tree.item(iid, tags=("overdue",) if overdue else ())
                self.tree.set(iid, "status", status_text(False, overdue))

    def selected(self):
        """Возвращает (id, выполнена ли) выбранной задачи или None."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Сначала выберите задачу в списке.")
            return None
        return int(sel[0]), "done" in self.tree.item(sel[0], "tags")

    def add(self):
        title = self.entry_text()
        if not title:
            return
        task_id = db.add_task(self.conn, title)
        self.entry.delete(0, "end")
        self.show_placeholder()
        self.refresh(select_id=task_id)

    def edit(self):
        task = self.selected()
        if task is None:
            return
        task_id = task[0]
        dialog = TaskDialog(self.root, *db.get_task(self.conn, task_id))
        self.root.wait_window(dialog)
        if dialog.result:
            db.update_task(self.conn, task_id, *dialog.result)
            self.refresh(select_id=task_id)

    def toggle(self):
        task = self.selected()
        if task is None:
            return
        task_id, done = task
        db.set_done(self.conn, task_id, not done)
        self.refresh(select_id=task_id)

    def delete(self):
        task = self.selected()
        if task is None:
            return
        title = self.tree.set(str(task[0]), "title")
        if not messagebox.askyesno(
            "Удалить задачу?",
            f"Удалить задачу «{title}»?\n\nВернуть её будет нельзя.",
            icon="warning", default="no", parent=self.root,
        ):
            return
        db.delete_task(self.conn, task[0])
        self.refresh()

    # --- меню по правой кнопке мыши ---

    def show_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        self.tree.focus(row)
        self.build_menu(int(row)).tk_popup(event.x_root, event.y_root)

    def show_menu_for_selected(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        x, y, _, height = self.tree.bbox(sel[0])
        self.build_menu(int(sel[0])).tk_popup(
            self.tree.winfo_rootx() + x + 40, self.tree.winfo_rooty() + y + height
        )

    def build_menu(self, task_id):
        title, due_at, remind_before, urgent, important = db.get_task(self.conn, task_id)
        done = "done" in self.tree.item(str(task_id), "tags")

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Изменить…", accelerator="F2", command=self.edit)
        menu.add_command(
            label="Снять отметку о выполнении" if done else "Отметить выполненной",
            accelerator="Пробел", command=self.toggle,
        )
        menu.add_separator()

        prio_menu = tk.Menu(menu, tearoff=0)
        self.urgent_choice = tk.BooleanVar(value=bool(urgent))
        self.important_choice = tk.BooleanVar(value=bool(important))
        prio_menu.add_checkbutton(label="Срочно", variable=self.urgent_choice,
                                  command=lambda: self.quick_priority(task_id))
        prio_menu.add_checkbutton(label="Важно", variable=self.important_choice,
                                  command=lambda: self.quick_priority(task_id))
        menu.add_cascade(label="Приоритет", menu=prio_menu)

        due_menu = tk.Menu(menu, tearoff=0)
        for label, days in (("Сегодня", 0), ("Завтра", 1), ("Через неделю", 7)):
            due_menu.add_command(label=label, command=lambda d=days: self.quick_due(task_id, d))
        due_menu.add_separator()
        due_menu.add_command(label="Выбрать дату и время…", command=self.edit)
        due_menu.add_command(
            label="Убрать срок", command=lambda: self.quick_due(task_id, None),
            state="normal" if due_at else "disabled",
        )
        menu.add_cascade(label="Срок", menu=due_menu)

        remind_menu = tk.Menu(menu, tearoff=0)
        self.remind_choice = tk.StringVar(value=REMIND_LABELS.get(remind_before, ""))
        for label, minutes in REMIND_OPTIONS.items():
            remind_menu.add_radiobutton(
                label=label, value=label, variable=self.remind_choice,
                command=lambda m=minutes: self.quick_remind(task_id, m),
            )
        menu.add_cascade(
            label="Напомнить" if due_at else "Напомнить (сначала задайте срок)",
            menu=remind_menu, state="normal" if due_at else "disabled",
        )

        menu.add_separator()
        menu.add_command(label="Создать письмо…", accelerator="Ctrl+E", command=self.email)
        menu.add_command(label="Копировать текст", command=lambda: self.copy_text(title))
        menu.add_command(label="Удалить", accelerator="Del", command=self.delete)
        return menu

    def quick_due(self, task_id, days):
        """Быстрая смена срока из меню. Время сохраняется прежним (или 09:00)."""
        title, due_at, remind_before, urgent, important = db.get_task(self.conn, task_id)
        if days is None:
            due_at, remind_before = None, None
        else:
            old = datetime.fromisoformat(due_at).time() if due_at else time(*map(int, DEFAULT_TIME))
            due_at = datetime.combine(date.today() + timedelta(days=days), old).strftime("%Y-%m-%d %H:%M")
        db.update_task(self.conn, task_id, title, due_at, remind_before, urgent, important)
        self.refresh(select_id=task_id)

    def quick_remind(self, task_id, minutes):
        title, due_at, _, urgent, important = db.get_task(self.conn, task_id)
        db.update_task(self.conn, task_id, title, due_at, minutes, urgent, important)
        self.refresh(select_id=task_id)

    def quick_priority(self, task_id):
        title, due_at, remind_before, _, _ = db.get_task(self.conn, task_id)
        db.update_task(self.conn, task_id, title, due_at, remind_before,
                       self.urgent_choice.get(), self.important_choice.get())
        self.refresh(select_id=task_id)

    def copy_text(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def email(self):
        """Открывает новое письмо в почтовой программе с данными выбранной задачи."""
        task = self.selected()
        if task is None:
            return
        task_id = task[0]
        _, _, _, urgent, _ = db.get_task(self.conn, task_id)
        values = self.tree.set(str(task_id))
        status = values["status"].split(None, 1)[-1]  # без значка ○ ✔ ⚠
        subject, body = build_email(values["title"], status, values["priority"], values["due"],
                                    values["remind"], values["created"], urgent)
        url = f"mailto:?subject={quote(subject, safe='')}&body={quote(body, safe='')}"
        try:
            os.startfile(url)  # откроет почтовую программу по умолчанию (например, Outlook)
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
        self.mark_overdue()
        due = db.due_reminders(self.conn)
        if due:
            for task_id, _, _ in due:
                db.mark_reminded(self.conn, task_id)
            lines = [f"• {title} — срок {format_due(due_at)}" for _, title, due_at in due]
            # Показываем окно поверх всех остальных, даже если оно было свёрнуто.
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.bell()
            messagebox.showinfo("Напоминание", "Напоминаю о задачах:\n\n" + "\n".join(lines), parent=self.root)
            self.root.attributes("-topmost", False)
        self.root.after(CHECK_EVERY_MS, self.check_reminders)

    def close(self):
        self.conn.close()
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
