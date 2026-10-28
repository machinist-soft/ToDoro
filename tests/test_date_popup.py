"""Выпадающий календарь DatePicker не уходит под панель задач Windows: у нижнего края рабочей
области он открывается над полем, в середине — под полем, при листании месяца (5 ↔ 6 недель)
календарь всегда в 6 недель и не меняет размер. Окна — за краем экрана, рабочая область подменена (work_area)."""

import re
import sys
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OFFSCREEN = "+-5000+-5000"


class DatePopupPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("300x200" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.top = tk.Toplevel(self.root)
        self.top.geometry("320x80" + OFFSCREEN)
        # февраль 2026 — 5 недель, март 2026 — 6 недель
        self.picker = self.T.DatePicker(self.top, date(2026, 2, 10), empty="без конца", clear="Без конца")
        self.picker.pack(padx=20, pady=20, anchor="w")
        self.picker.close_if_unfocused = lambda: None  # фокус в тестах может уйти — не закрываем
        self.top.update()
        self.area = None
        patches = [mock.patch.object(self.T, "work_area", lambda window: self.area),
                   mock.patch.object(self.T, "close_when_inactive", lambda *a, **k: None)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.picker.close_popup()
        self.top.destroy()
        self.root.update()

    def field(self):
        entry = self.picker.entry
        return entry.winfo_rootx(), entry.winfo_rooty(), entry.winfo_width(), entry.winfo_height()

    def popup_box(self):
        popup = self.picker.popup
        popup.update_idletasks()
        # «ШxВ+X+Y»; за краем экрана координаты отрицательные: «+-4972»
        match = re.fullmatch(r"\d+x\d+\+?(-?\d+)\+?(-?\d+)", popup.geometry())
        width, height = popup.winfo_reqwidth(), popup.winfo_reqheight()
        return int(match.group(1)), int(match.group(2)), width, height

    def assert_inside(self, box):
        x, y, width, height = box
        left, top, area_width, area_height = self.area
        self.assertGreaterEqual(x, left)
        self.assertGreaterEqual(y, top)
        self.assertLessEqual(x + width, left + area_width)
        self.assertLessEqual(y + height, top + area_height)

    def open(self):
        self.picker.toggle_popup()
        self.assertIsNotNone(self.picker.popup)
        return self.popup_box()

    def test_middle_opens_below(self):
        fx, fy, fw, fh = self.field()
        self.area = (fx - 600, fy - 800, 1600, 2000)
        box = self.open()
        self.assertGreaterEqual(box[1], fy + fh)  # под полем
        self.assertEqual(box[0], fx)
        self.assert_inside(box)

    def test_bottom_edge_opens_above(self):
        """Поле у нижнего края рабочей области (над панелью задач) — календарь над полем."""
        fx, fy, fw, fh = self.field()
        self.area = (fx - 600, fy - 800, 1600, 800 + fh + 30)
        x, y, width, height = box = self.open()
        self.assertLessEqual(y + height, fy)  # над полем
        self.assert_inside(box)

    def test_little_room_above_stays_in_area(self):
        """Ни снизу, ни сверху места не хватает — календарь не выше верха рабочей области."""
        fx, fy, fw, fh = self.field()
        self.area = (fx - 600, fy - 40, 1600, 40 + fh + 30)
        box = self.open()
        self.assertEqual(box[1], self.area[1])

    def test_right_edge(self):
        fx, fy, fw, fh = self.field()
        self.area = (fx - 600, fy - 800, 600 + 60, 2000)  # правый край рабочей области — рядом с полем
        x, y, width, height = box = self.open()
        self.assertLess(x, fx)
        self.assert_inside(box)

    def test_month_change_keeps_size_and_place(self):
        """Листание месяцев (в феврале 2026 — 5 недель, в марте — 6): календарь всегда в 6 недель,
        размер и место не меняются — он не «прыгает» (GitHub #13); над полем и в рабочей области."""
        fx, fy, fw, fh = self.field()
        self.area = (fx - 600, fy - 800, 1600, 800 + fh + 30)
        five = self.open()
        self.picker.shift_month(1)  # март — 6 недель
        six = self.popup_box()
        self.assertEqual((six[0], six[1], six[3]), (five[0], five[1], five[3]))  # место и высота
        for box in (five, six):
            self.assertLessEqual(box[1] + box[3], fy)
            self.assert_inside(box)
        self.picker.shift_month(-1)  # обратно в февраль
        self.assertEqual(self.popup_box(), five)

    def test_month_change_keeps_width(self):
        """Ширина календаря при листании тоже одна. В месяце с выбранным днём или с сегодняшним
        число набрано жирным, и колонка шире — календарь «прыгает» вправо на несколько точек."""
        self.area = (-10000, -10000, 20000, 20000)
        self.open()  # февраль 2026, выбрано 10-е (жирное)
        widths = {}
        for step in range(13):
            widths[f"{self.picker.month:%m.%Y}"] = self.popup_box()[2]
            self.picker.shift_month(1)
        self.assertEqual(len(set(widths.values())), 1, widths)

    def day_labels(self):
        """Числа в календаре: [(строка, колонка, дата-текст, цвет)] по порядку."""
        frame = self.picker.popup.winfo_children()[0]
        days = []
        for widget in frame.grid_slaves():
            info = widget.grid_info()
            if isinstance(widget, tk.Label) and 2 <= int(info["row"]) <= 7:
                days.append((int(info["row"]), int(info["column"]), widget.cget("text"), str(widget.cget("fg"))))
        return sorted(days)

    def test_every_month_same_size_six_weeks(self):
        """Все месяцы 2026 года и февраль 2021 (ровно 4 недели): 42 дня, одна высота.
        Недостающие недели — днями следующего месяца подряд, приглушённым цветом."""
        self.area = (-10000, -10000, 20000, 20000)
        self.picker.set(date(2021, 2, 10))
        size = None
        months = [(2021, 2)] + [(2026, m) for m in range(1, 13)]
        self.open()
        for year, month in months:
            self.picker.month = date(year, month, 1)
            self.picker.draw_month()
            height = self.popup_box()[3]
            if size is None:
                size = height
            self.assertEqual(height, size, f"{month}.{year}")
            days = self.day_labels()
            self.assertEqual(len(days), 42, f"{month}.{year}")
            self.assertEqual({(r, c) for r, c, *_ in days}, {(r, c) for r in range(2, 8) for c in range(7)})
        # февраль 2021: с понедельника 1-го по 28-е, дальше — 1…14 марта
        self.picker.month = date(2021, 2, 1)
        self.picker.draw_month()
        days = self.day_labels()
        self.assertEqual([int(t) for _, _, t, _ in days], list(range(1, 29)) + list(range(1, 15)))
        self.assertEqual({fg for _, _, _, fg in days[28:]}, {self.T.OTHER_MONTH})

    def test_month_change_in_middle_stays_below(self):
        fx, fy, fw, fh = self.field()
        self.area = (fx - 600, fy - 800, 1600, 2000)
        self.open()
        for step in (1, -1, 1):
            self.picker.shift_month(step)
            box = self.popup_box()
            self.assertGreaterEqual(box[1], fy + fh)
            self.assert_inside(box)


if __name__ == "__main__":
    unittest.main()
