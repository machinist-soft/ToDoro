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

    def form(self, due="2026-10-20 09:00", **extra):
        task = dict(title="Отчёт", body="", due_at=due, remind_before=None, urgent=0, important=0,
                    status_id=1, assignee=None, initiator=None, version=3)
        task.update(extra)
        form = T.TaskForm(self.top, task, STATUSES, on_save=self.saved.append, on_cancel=lambda: None)
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


if __name__ == "__main__":
    unittest.main()
