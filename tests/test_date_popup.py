"""Выпадающий календарь DatePicker не уходит под панель задач Windows: у нижнего края рабочей
области он открывается над полем, в середине — под полем, при листании месяца (5 ↔ 6 недель)
позиция пересчитывается. Окна — за краем экрана, рабочая область подменена (work_area)."""

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

    def test_month_change_replaces_popup(self):
        """Листание 5 ↔ 6 недель: высота меняется, календарь всё равно над полем и в рабочей области."""
        fx, fy, fw, fh = self.field()
        self.area = (fx - 600, fy - 800, 1600, 800 + fh + 30)
        five = self.open()
        self.picker.shift_month(1)  # март — 6 недель
        six = self.popup_box()
        self.assertGreater(six[3], five[3])
        for box in (five, six):
            self.assertLessEqual(box[1] + box[3], fy)
            self.assert_inside(box)
        self.assertLess(six[1], five[1])  # выше календарь — выше и его верх
        self.picker.shift_month(-1)  # обратно в февраль
        back = self.popup_box()
        self.assertEqual(back, five)

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
