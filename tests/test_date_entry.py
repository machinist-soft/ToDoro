"""Дату можно напечатать в поле (GitHub #13): parse_date, ввод в DatePicker (Enter, уход фокуса,
непонятный текст), форма задачи сохраняет напечатанную, но не применённую дату.
Окна Tk — за краем экрана."""

import sys
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import todoro  # noqa: E402

T = todoro
OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0), (2, "Выполнено", "#22c55e", 1)]
TODAY = date(2026, 10, 28)


class ParseDateTests(unittest.TestCase):
    def parse(self, text):
        return T.parse_date(text, today=TODAY)

    def test_full_and_short_year(self):
        self.assertEqual(self.parse("28.10.2026"), date(2026, 10, 28))
        self.assertEqual(self.parse("28.10.26"), date(2026, 10, 28))
        self.assertEqual(self.parse("1.2.27"), date(2027, 2, 1))
        self.assertEqual(self.parse("05.01.2030"), date(2030, 1, 5))

    def test_without_year_is_current_year(self):
        self.assertEqual(self.parse("28.10"), date(2026, 10, 28))
        self.assertEqual(self.parse("1.1"), date(2026, 1, 1))  # и в прошлом — тот же год
        self.assertEqual(T.parse_date("3.4", today=date(2031, 12, 31)), date(2031, 4, 3))

    def test_separators(self):
        for text in ("28.10.2026", "28/10/2026", "28-10-2026", "28,10,2026", "28 10 2026",
                     "28. 10. 2026", "  28.10.2026  ", "28.10.2026.", "28..10..2026"):
            self.assertEqual(self.parse(text), date(2026, 10, 28), text)
        for text in ("28/10", "28-10", "28,10", "28 10", "28.10."):
            self.assertEqual(self.parse(text), date(2026, 10, 28), text)

    def test_iso(self):
        self.assertEqual(self.parse("2026-10-28"), date(2026, 10, 28))
        self.assertEqual(self.parse("2027-1-5"), date(2027, 1, 5))

    def test_default_today(self):
        """Без today — год текущий."""
        self.assertEqual(T.parse_date("15.06"), date(date.today().year, 6, 15))

    def test_not_existing_dates(self):
        for text in ("31.02.2026", "29.02.2026", "30.02", "31.04", "0.10", "28.0", "28.13.2026",
                     "32.01", "2026-02-30", "2026-13-01"):
            self.assertIsNone(self.parse(text), text)
        self.assertEqual(self.parse("29.02.2028"), date(2028, 2, 29))  # високосный

    def test_year_must_be_two_or_four_digits(self):
        for text in ("28.10.2", "28.10.202", "28.10.20266", "28.10."+"9" * 30):
            self.assertIsNone(self.parse(text), text)

    def test_garbage(self):
        for text in ("", "   ", "...", "завтра", "28", "28.10.2026.1", "28.10.20x6", "a.b.c",
                     "Не задан", "без конца", "+28.10", "28.10 10:00", "²⁸.10"):
            self.assertIsNone(self.parse(text), text)

    def test_huge_numbers_do_not_crash(self):
        """Огромное число дня или месяца — «непонятно» (None), а не исключение: иначе Enter в поле
        или «Сохранить» в форме задачи падали бы с ошибкой."""
        for text in ("99999999999999999999.10", "1.99999999999999999999",
                     "99999999999999999999.99999999999999999999.2026"):
            with self.subTest(text=text):
                self.assertIsNone(self.parse(text))
        self.assertIsNone(self.parse("1." + "9" * 5000))  # длиннее предела int() из строки

    def test_year_far_from_today_is_typo(self):
        """«28.10.0026» — опечатка, а не срок 2000 лет назад; «31.12.9999» ломал бы календарь."""
        for text in ("28.10.0026", "0026-10-28", "31.12.9999", "9999-12-31", "1.1.1900"):
            with self.subTest(text=text):
                self.assertIsNone(self.parse(text))
        self.assertEqual(self.parse("1.1.2126"), date(2126, 1, 1))  # ровно 100 лет — можно
        self.assertEqual(self.parse("1.1.1926"), date(1926, 1, 1))

    def test_superscript_digits(self):
        self.assertIsNone(self.parse("2².10"))


class DatePickerTypingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("300x200" + OFFSCREEN)
        T.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.top = tk.Toplevel(self.root)
        self.top.geometry("320x80" + OFFSCREEN)
        self.changes = []
        for patch in (mock.patch.object(T, "close_when_inactive", lambda *a, **k: None),
                      mock.patch.object(T, "work_area", lambda window: (-10000, -10000, 20000, 20000))):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.top.destroy()
        self.root.update()

    def picker(self, value=None, **options):
        picker = T.DatePicker(self.top, value, on_change=lambda: self.changes.append(picker.value), **options)
        picker.pack()
        picker.bell = mock.Mock()
        picker.close_if_unfocused = lambda: None
        self.top.update()
        return picker

    def type(self, picker, text):
        picker.text.set(text)

    def test_field_is_editable(self):
        for button in (True, False):
            picker = self.picker(date(2026, 10, 20), button=button)
            self.assertNotIn(str(picker.entry.cget("state")), ("readonly", "disabled"))
            picker.entry.delete(0, "end")
            picker.entry.insert(0, "1.11.2026")  # печатать можно
            self.assertEqual(picker.text.get(), "1.11.2026")

    def test_commit_applies_typed_date(self):
        picker = self.picker(date(2026, 10, 20))
        self.type(picker, "5.11.26")
        picker.commit()
        self.assertEqual(picker.value, date(2026, 11, 5))
        self.assertEqual(picker.text.get(), "05.11.2026")  # показ — в обычном виде
        self.assertEqual(self.changes, [date(2026, 11, 5)])
        picker.bell.assert_not_called()

    def test_without_year(self):
        picker = self.picker()
        self.type(picker, "1.12")
        picker.commit()
        self.assertEqual(picker.value, date(date.today().year, 12, 1))

    def test_garbage_restores_previous(self):
        for typed in ("завтра", "31.02.2026", "28.10.202", "99999999999999999999.10"):
            with self.subTest(typed=typed):
                self.changes.clear()
                picker = self.picker(date(2026, 10, 20))
                self.type(picker, typed)
                picker.commit()
                self.assertEqual(picker.value, date(2026, 10, 20))
                self.assertEqual(picker.text.get(), "20.10.2026")
                self.assertEqual(self.changes, [])
                picker.bell.assert_called_once()
                picker.destroy()

    def test_garbage_in_empty_field(self):
        picker = self.picker(empty="без конца", clear="Без конца")
        self.type(picker, "abc")
        picker.commit()
        self.assertIsNone(picker.value)
        self.assertEqual(picker.text.get(), "без конца")
        self.assertEqual(self.changes, [])
        picker.bell.assert_called_once()

    def test_empty_text_clears_date(self):
        picker = self.picker(date(2026, 10, 20))
        self.type(picker, "   ")
        picker.commit()
        self.assertIsNone(picker.value)
        self.assertEqual(picker.text.get(), "Не задан")
        self.assertEqual(self.changes, [None])
        picker.bell.assert_not_called()

    def test_same_date_no_change(self):
        """Та же дата другим видом — on_change не зовётся, в поле — обычный вид."""
        picker = self.picker(date(2026, 10, 20))
        for typed in ("20.10.2026", "20.10.26", "2026-10-20", " 20/10/2026 "):
            self.type(picker, typed)
            picker.commit()
            self.assertEqual(picker.value, date(2026, 10, 20))
            self.assertEqual(picker.text.get(), "20.10.2026")
        self.assertEqual(self.changes, [])
        picker.bell.assert_not_called()

    def test_empty_stays_empty(self):
        picker = self.picker()
        for typed in ("Не задан", "", "  "):
            self.type(picker, typed)
            picker.commit()
            self.assertIsNone(picker.value)
            self.assertEqual(picker.text.get(), "Не задан")
        self.assertEqual(self.changes, [])
        picker.bell.assert_not_called()

    def test_enter_keys_and_focus_out_commit(self):
        picker = self.picker(date(2026, 10, 20))
        picker.entry.focus_force()  # клавиши Tk отдаёт полю с фокусом
        self.top.update()
        for event, typed, expected in (("<Return>", "1.11.2026", date(2026, 11, 1)),
                                       ("<FocusOut>", "3.11.2026", date(2026, 11, 3))):
            self.type(picker, typed)
            picker.entry.event_generate(event, when="now")
            self.assertEqual(picker.value, expected, event)
        self.assertEqual(self.changes, [date(2026, 11, 1), date(2026, 11, 3)])
        # Enter цифровой клавиатуры: Tk на Windows не умеет сгенерировать такое нажатие
        # («no keycode for keysym») — проверяем, что привязка есть
        self.assertIn("<Key-KP_Enter>", picker.entry.bind())

    def test_commit_returns_true_or_false(self):
        """commit(): True — дата понятная (или пусто, или та же); False — чепуха, дата прежняя."""
        cases = ((date(2026, 10, 20), "5.11.26", True), (date(2026, 10, 20), "20.10.2026", True),
                 (date(2026, 10, 20), "", True), (None, "Не задан", True), (None, "1.12", True),
                 (date(2026, 10, 20), "завтра", False), (date(2026, 10, 20), "31.02.2026", False),
                 (None, "abc", False), (date(2026, 10, 20), "9" * 5000, False))
        for value, typed, expected in cases:
            with self.subTest(typed=typed[:20], value=value):
                picker = self.picker(value)
                self.type(picker, typed)
                self.assertIs(picker.commit(), expected)
                if not expected:
                    self.assertEqual(picker.value, value)
                picker.destroy()

    def test_on_enter_none_by_default(self):
        picker = self.picker()
        self.assertIsNone(picker.on_enter)

    def test_enter_calls_on_enter_for_good_date(self):
        """Понятная дата — применена, затем on_enter (форма сохраняется); "break" — дальше Enter
        не идёт."""
        picker = self.picker(date(2026, 10, 20))
        calls = []
        picker.on_enter = lambda: calls.append(picker.value)
        self.type(picker, "5.11.2026")
        self.assertEqual(picker.enter(), "break")
        self.assertEqual(calls, [date(2026, 11, 5)])  # on_enter видит уже новую дату
        self.assertEqual(self.changes, [date(2026, 11, 5)])
        # пусто — тоже понятно: даты нет
        self.type(picker, "")
        self.assertEqual(picker.enter(), "break")
        self.assertEqual(calls, [date(2026, 11, 5), None])
        # та же дата — on_enter всё равно зовётся (Enter без правки сохраняет форму)
        picker.set(date(2026, 10, 20))
        self.assertEqual(picker.enter(), "break")
        self.assertEqual(calls[-1], date(2026, 10, 20))
        picker.bell.assert_not_called()

    def test_enter_with_garbage_does_not_call_on_enter(self):
        picker = self.picker(date(2026, 10, 20))
        picker.on_enter = mock.Mock()
        self.type(picker, "чепуха")
        self.assertIsNone(picker.enter())
        picker.on_enter.assert_not_called()
        self.assertEqual(picker.value, date(2026, 10, 20))
        self.assertEqual(picker.text.get(), "20.10.2026")
        picker.bell.assert_called_once()

    def test_enter_without_on_enter_just_commits(self):
        picker = self.picker(date(2026, 10, 20))
        self.type(picker, "1.11.2026")
        self.assertIsNone(picker.enter())
        self.assertEqual(picker.value, date(2026, 11, 1))

    def test_return_key_calls_on_enter(self):
        """Настоящее нажатие Enter в поле — on_enter один раз, с новой датой; при чепухе — ни разу."""
        picker = self.picker(date(2026, 10, 20))
        calls = []
        picker.on_enter = lambda: calls.append(picker.value)
        picker.entry.focus_force()
        self.top.update()
        self.type(picker, "7.11.2026")
        picker.entry.event_generate("<Return>", when="now")
        self.assertEqual(calls, [date(2026, 11, 7)])
        self.type(picker, "xx.yy")
        picker.entry.event_generate("<Return>", when="now")
        self.assertEqual(calls, [date(2026, 11, 7)])
        self.assertEqual(picker.value, date(2026, 11, 7))

    def test_focus_in_empty_clears_placeholder(self):
        picker = self.picker()
        self.assertEqual(picker.text.get(), "Не задан")
        picker.entry.event_generate("<FocusIn>")
        self.assertEqual(picker.text.get(), "")  # «Не задан» стёрто — печатать с чистого поля
        picker.entry.event_generate("<FocusOut>")  # ушли, ничего не напечатав
        self.assertEqual(picker.text.get(), "Не задан")
        self.assertIsNone(picker.value)
        self.assertEqual(self.changes, [])

    def test_focus_in_with_date_selects_it(self):
        picker = self.picker(date(2026, 10, 20))
        picker.entry.event_generate("<FocusIn>")
        self.assertEqual(picker.text.get(), "20.10.2026")
        self.assertTrue(picker.entry.selection_present())
        self.assertEqual((picker.entry.index("sel.first"), picker.entry.index("sel.last")), (0, 10))

    def test_click_on_field_does_not_open_calendar(self):
        picker = self.picker(date(2026, 10, 20))
        picker.entry.event_generate("<Button-1>", x=3, y=3)
        self.top.update()
        self.assertIsNone(picker.popup)

    def test_toggle_popup_applies_typed_first(self):
        """Напечатали дату и нажали 📅 — дата применена, календарь открыт на её месяце."""
        picker = self.picker(date(2026, 10, 20))
        self.type(picker, "5.1.2027")
        picker.toggle_popup()
        try:
            self.assertIsNotNone(picker.popup)
            self.assertEqual(picker.value, date(2027, 1, 5))
            self.assertEqual(picker.month, date(2027, 1, 1))
            self.assertEqual(self.changes, [date(2027, 1, 5)])
        finally:
            picker.close_popup()

    def test_toggle_popup_with_garbage_keeps_old(self):
        picker = self.picker(date(2026, 10, 20))
        self.type(picker, "чепуха")
        picker.toggle_popup()
        try:
            self.assertIsNotNone(picker.popup)
            self.assertEqual(picker.value, date(2026, 10, 20))
            self.assertEqual(picker.month, date(2026, 10, 1))
            self.assertEqual(picker.text.get(), "20.10.2026")
        finally:
            picker.close_popup()


class TaskFormTypedDateTests(unittest.TestCase):
    """«Сохранить» берёт дату, напечатанную в поле, даже если Enter не нажат и фокус не уходил."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("300x200" + OFFSCREEN)
        T.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.top = tk.Toplevel(self.root)
        self.top.geometry(OFFSCREEN)
        self.saved = []

    def tearDown(self):
        self.top.destroy()
        self.root.update()

    def form(self, due="2026-10-20 09:00", *, compact=False, **extra):
        task = dict(title="Отчёт", body="", due_at=due, remind_before=None, urgent=0, important=0,
                    status_id=1, assignee=None, initiator=None, version=3)
        task.update(extra)
        form = T.TaskForm(self.top, task, STATUSES, on_save=self.saved.append, on_cancel=lambda: None,
                          compact=compact)
        form.pack(fill="both")
        self.top.update()
        form.date.bell = form.until.bell = mock.Mock()
        return form

    def test_typed_due_saved(self):
        form = self.form()
        form.date.text.set("5.11.2026")
        form.save()
        self.assertEqual(self.saved[-1]["due_at"], "2026-11-05 09:00")
        self.assertEqual(form.date.value, date(2026, 11, 5))

    def test_typed_due_on_task_without_due(self):
        """Срока не было — напечатанный срок сохраняется (время по умолчанию)."""
        form = self.form(due=None)
        form.date.text.set("5.11.2026")
        values = form.values()
        self.assertTrue(values["due_at"].startswith("2026-11-05 "), values["due_at"])
        self.assertEqual(str(form.repeat.cget("state")), "readonly")  # срок есть — повтор доступен

    def test_typed_empty_due_clears(self):
        form = self.form(repeat="week", repeat_until="2026-12-31")
        form.date.text.set("")
        values = form.values()
        self.assertIsNone(values["due_at"])
        self.assertEqual((values["repeat"], values["repeat_until"]), (None, None))

    def test_typed_garbage_due_keeps_old(self):
        form = self.form()
        form.date.text.set("скоро")
        self.assertEqual(form.values()["due_at"], "2026-10-20 09:00")
        self.assertFalse(form.dirty())
        form.date.text.set("99999999999999999999.10")  # огромное число — тоже «непонятно»
        self.assertEqual(form.values()["due_at"], "2026-10-20 09:00")

    def test_typed_until_saved(self):
        form = self.form(repeat="month")
        form.until.text.set("31.12.27")
        form.save()
        self.assertEqual(self.saved[-1]["repeat"], "month")
        self.assertEqual(self.saved[-1]["repeat_until"], "2027-12-31")

    def test_typed_until_before_due_warns(self):
        form = self.form(repeat="month")
        form.until.text.set("1.10.2026")
        with mock.patch.object(T.ui, "showwarning") as warning:
            form.save()
        warning.assert_called_once()
        self.assertEqual(self.saved, [])

    def test_unchanged_form_not_dirty(self):
        for extra in ({}, {"due": None}, {"repeat": "week", "repeat_until": "2026-12-31"}):
            form = self.form(**extra)
            self.assertFalse(form.dirty(), extra)
            form.destroy()

    def test_typed_due_makes_dirty(self):
        form = self.form()
        form.date.text.set("21.10.2026")
        self.assertTrue(form.dirty())

    def press_enter(self, picker, text):
        """Фокус в поле даты, напечатать text, нажать Enter (настоящее событие Tk)."""
        picker.entry.focus_force()
        self.top.update()
        picker.text.set(text)
        picker.entry.event_generate("<Return>", when="now")

    def test_fields_save_on_enter(self):
        form = self.form()
        self.assertEqual(form.date.on_enter, form.save)
        self.assertEqual(form.until.on_enter, form.save)

    def test_enter_in_due_saves(self):
        """Жалоба «дата не применяется по Enter»: Enter в поле срока — задача сохранена с новым
        сроком (и в правой панели — compact, и в окне)."""
        for compact in (True, False):
            with self.subTest(compact=compact):
                self.saved.clear()
                form = self.form(compact=compact)
                self.press_enter(form.date, "5.12.2026")
                self.assertEqual(len(self.saved), 1)
                self.assertEqual(self.saved[0]["due_at"], "2026-12-05 09:00")
                self.assertEqual(self.saved[0]["title"], "Отчёт")
                form.destroy()

    def test_enter_in_due_on_task_without_due(self):
        form = self.form(due=None)
        self.press_enter(form.date, "1.12")
        self.assertEqual(len(self.saved), 1)
        self.assertTrue(self.saved[0]["due_at"].startswith(f"{date.today().year}-12-01 "))

    def test_enter_with_empty_due_saves_without_due(self):
        form = self.form(repeat="week", repeat_until="2026-12-31")
        self.press_enter(form.date, "")
        self.assertEqual(len(self.saved), 1)
        self.assertIsNone(self.saved[0]["due_at"])
        self.assertEqual((self.saved[0]["repeat"], self.saved[0]["repeat_until"]), (None, None))

    def test_enter_in_until_saves(self):
        for compact in (True, False):
            with self.subTest(compact=compact):
                self.saved.clear()
                form = self.form(compact=compact, repeat="month")
                self.press_enter(form.until, "31.12.27")
                self.assertEqual(len(self.saved), 1)
                self.assertEqual((self.saved[0]["repeat"], self.saved[0]["repeat_until"]),
                                 ("month", "2027-12-31"))
                self.assertEqual(self.saved[0]["due_at"], "2026-10-20 09:00")
                form.destroy()

    def test_enter_with_garbage_does_not_save(self):
        for field, extra in (("date", {}), ("until", {"repeat": "month", "repeat_until": "2026-12-31"})):
            with self.subTest(field=field):
                form = self.form(**extra)
                picker = getattr(form, field)
                picker.bell.reset_mock()
                for typed in ("скоро", "31.02.2026", "99999999999999999999.10"):
                    self.press_enter(picker, typed)
                self.assertEqual(self.saved, [])
                self.assertEqual(picker.bell.call_count, 3)
                self.assertFalse(form.dirty())  # прежняя дата осталась
                form.destroy()

    def test_enter_until_before_due_warns(self):
        form = self.form(repeat="month")
        with mock.patch.object(T.ui, "showwarning") as warning:
            self.press_enter(form.until, "1.10.2026")
        warning.assert_called_once()
        self.assertEqual(self.saved, [])

    def test_enter_with_empty_title_warns(self):
        form = self.form(title="")
        with mock.patch.object(T.ui, "showwarning") as warning:
            self.press_enter(form.date, "5.12.2026")
        warning.assert_called_once()
        self.assertEqual(self.saved, [])

    def test_until_field_fits_date(self):
        """Поле «до»: «28.10.2026» (и «без конца») по ширине шрифта с левым отступом помещается
        в поле до правого отступа стиля Date.TEntry, то есть не заходит под значок 📅."""
        import tkinter.font as tkfont
        for compact in (False, True):
            with self.subTest(compact=compact):
                form = self.form(compact=compact, repeat="month", repeat_until="2026-12-31")
                self.top.update()
                entry = form.until.entry
                self.assertEqual(str(entry.cget("style")), "Date.TEntry")
                raw = tk.ttk.Style(self.top).lookup("Date.TEntry", "padding")  # «(6, 6, 22, 6)» или «6 6 22 6»
                padding = [int(float(p)) for p in str(raw).replace("(", " ").replace(")", " ")
                           .replace(",", " ").split()]
                left, right = padding[0], padding[2] if len(padding) > 2 else padding[0]
                font = tkfont.Font(font=entry.cget("font"))
                icon = [w for w in entry.winfo_children() if w.cget("text") == "📅"][0]
                self.assertGreater(entry.winfo_width(), 1)
                for text in ("28.10.2026", "без конца"):
                    needed = left + font.measure(text)
                    self.assertLessEqual(needed, entry.winfo_width() - right, text)
                    # зазор хотя бы в 4 точки: при прежней ширине 9 дата упиралась в значок (1 точка)
                    self.assertLessEqual(needed + 4, icon.winfo_x(), f"{text} упирается в значок 📅")
                form.destroy()


class TaskDialogEnterTests(unittest.TestCase):
    """Окно TaskDialog (когда правая панель скрыта): Enter в поле срока или «до» сохраняет задачу
    и закрывает окно; при чепухе окно остаётся открытым."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("300x200" + OFFSCREEN)
        T.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        real_place = T.place_window

        def place(window, *args, **kwargs):
            window.attributes("-alpha", 0.0)  # окно показывается, но его не видно
            return real_place(window, *args, **kwargs)

        for patch in (mock.patch.object(T, "work_area", lambda w: (-6000, -6000, 1920, 3000)),
                      mock.patch.object(T, "place_window", place),
                      mock.patch.object(T, "bring_to_front")):
            patch.start()
            self.addCleanup(patch.stop)
        self.dialogs = []
        self.addCleanup(self.close_dialogs)

    def close_dialogs(self):
        for dialog in self.dialogs:
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
        self.root.update()

    def dialog(self, **extra):
        task = dict(title="Отчёт", body="", due_at="2026-10-20 09:00", remind_before=None, urgent=0,
                    important=0, status_id=1, assignee=None, initiator=None, version=3)
        task.update(extra)
        dialog = T.TaskDialog(self.root, task, STATUSES, title="Задача")
        self.dialogs.append(dialog)
        dialog.update()
        dialog.form.date.bell = dialog.form.until.bell = mock.Mock()
        return dialog

    def press_enter(self, dialog, picker, text):
        picker.entry.focus_force()
        dialog.update()
        picker.text.set(text)
        picker.entry.event_generate("<Return>", when="now")

    def test_enter_in_due_saves_and_closes(self):
        dialog = self.dialog()
        self.press_enter(dialog, dialog.form.date, "5.12.2026")
        self.assertIsNotNone(dialog.result)
        self.assertEqual(dialog.result["due_at"], "2026-12-05 09:00")
        self.assertFalse(dialog.winfo_exists())

    def test_enter_in_until_saves_and_closes(self):
        dialog = self.dialog(repeat="week")
        self.press_enter(dialog, dialog.form.until, "31.01.2027")
        self.assertEqual((dialog.result["repeat"], dialog.result["repeat_until"]), ("week", "2027-01-31"))
        self.assertFalse(dialog.winfo_exists())

    def test_enter_with_garbage_keeps_dialog(self):
        dialog = self.dialog(repeat="week", repeat_until="2026-12-31")
        for picker in (dialog.form.date, dialog.form.until):
            self.press_enter(dialog, picker, "чепуха")
        self.assertIsNone(dialog.result)
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(dialog.form.date.value, date(2026, 10, 20))
        self.assertEqual(dialog.form.until.value, date(2026, 12, 31))


if __name__ == "__main__":
    unittest.main()
