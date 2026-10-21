"""Поле «Описание» в правой панели «Изменение задачи» (SidePanel.fit_description, сообщение #6)
занимает свободное место до кнопок «Сохранить / Отмена»: в высоком окне растёт и форма
помещается без прокрутки, в невысоком — 5 строк и прокрутка; пересчитывается при изменении
размера окна и при появлении советов под заголовком. Настоящий Tk, окно за краем экрана;
данные пользователя не трогаются (пути db — во временной папке)."""

import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0)]
TMP = None


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp()
    tmp = Path(TMP)
    patches = [mock.patch.object(db, "DATA_DIR", tmp),
               mock.patch.object(db, "DB_PATH", tmp / "todoro.db"),
               mock.patch.object(db, "LISTS_DIR", tmp / "lists"),
               mock.patch.object(db, "OLD_DB_PATHS", [])]
    for p in patches:
        p.start()
        unittest.addModuleCleanup(p.stop)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def task(title="позвонить", body=""):
    return dict(title=title, body=body, due_at=None, remind_before=None, urgent=0,
                important=0, status_id=1, assignee=None, version=3)


def noop(*args, **kwargs):
    pass


class SideDescFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("320x700" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.panel = self.T.SidePanel(self.root, noop, noop, noop, noop, noop, noop, {}, noop)
        self.panel.pack(fill="both", expand=True)
        self.line = self.T.tkfont.Font(font=self.T.FONT).metrics("linespace")

    def tearDown(self):
        self.panel.destroy()
        self.root.update()

    def resize(self, height):
        self.root.geometry(f"320x{height}" + OFFSCREEN)
        self.settle()

    def settle(self):
        for _ in range(5):  # Configure → after_idle → новая высота → снова Configure
            self.root.update()

    def open(self, data=None, history=None, hints=False):
        self.panel.show_form(data or task(), STATUSES, noop, noop, history=history, hints=hints)
        self.settle()
        return self.panel.form

    def area(self):
        return self.panel.form.master.master.master  # inner → canvas → ScrollArea

    def lines(self):
        return int(self.panel.form.desc.cget("height"))

    def free(self):
        area = self.area()
        return area.canvas.winfo_height() - area.inner.winfo_reqheight()

    def assert_fills(self):
        """Форма заполняет панель: без прокрутки и пустого места больше строки внизу нет."""
        free = self.free()
        self.assertGreaterEqual(free, 0, "форма не помещается — появилась прокрутка")
        self.assertLess(free, self.line, f"внизу осталось {free} px пустого места")
        self.assertFalse(self.area().bar.winfo_ismapped())

    # --- размеры окна ---

    def test_tall_window_grows_description(self):
        self.resize(990)
        self.open()
        self.assertGreater(self.lines(), self.T.SidePanel.DESC_MIN_LINES)
        self.assert_fills()

    def test_low_window_keeps_five_lines(self):
        self.resize(500)
        self.open()
        self.assertEqual(self.lines(), self.T.SidePanel.DESC_MIN_LINES)
        self.assertLess(self.free(), 0)  # форма длиннее панели — прокрутка
        self.assertTrue(self.area().bar.winfo_ismapped())

    def test_resize_both_ways(self):
        self.resize(700)
        self.open()
        small = self.lines()
        self.resize(1000)
        big = self.lines()
        self.assertGreater(big, small)
        self.assert_fills()
        self.resize(850)
        middle = self.lines()
        self.assertLess(middle, big)
        self.assertGreater(middle, small)
        self.assert_fills()
        self.resize(500)
        self.assertEqual(self.lines(), self.T.SidePanel.DESC_MIN_LINES)
        self.resize(1000)
        self.assertEqual(self.lines(), big)  # вернулись к прежнему размеру — та же высота

    def test_long_description_text_does_not_change_height(self):
        """Длинный текст в описании прокручивается в поле, а не растягивает форму."""
        self.resize(990)
        self.open(task(body="\n".join(f"строка {i}" for i in range(100))))
        self.assert_fills()

    # --- закрытие и смена формы до срабатывания after_idle ---

    def test_close_form_before_fit(self):
        self.resize(990)
        self.panel.show_form(task(), STATUSES, noop, noop)
        self.panel.show_totoro()  # форма закрыта, отложенная подгонка ещё не сработала
        self.assertIsNone(self.panel.form)
        with mock.patch.object(self.root, "report_callback_exception") as report:
            self.settle()
        report.assert_not_called()

    def test_open_other_task_before_fit(self):
        self.resize(990)
        with mock.patch.object(self.root, "report_callback_exception") as report:
            self.panel.show_form(task("первая"), STATUSES, noop, noop)
            self.root.update_idletasks()
            self.panel.show_form(task("вторая"), STATUSES, noop, noop)
            self.settle()
            self.resize(850)  # в 800 форма (с полем «Повторять») при 5 строках описания уже не помещается
        report.assert_not_called()
        self.assertEqual(self.panel.form.title_entry.get(), "вторая")
        self.assert_fills()

    def test_resize_after_form_closed(self):
        self.resize(990)
        self.open()
        self.panel.show_totoro()
        with mock.patch.object(self.root, "report_callback_exception") as report:
            self.resize(700)
            self.resize(1000)
        report.assert_not_called()

    # --- советы под заголовком ---

    def test_hints_shrink_description(self):
        self.resize(990)
        form = self.open(task("позвонить маме"), history=[], hints="changed")
        before = self.lines()
        self.assertEqual(form.hints.winfo_children(), [])
        form.title_entry.delete(0, "end")
        form.title_entry.insert(0, "срочно позвонить маме")
        form.update_hints()
        self.settle()
        self.assertTrue(form.hints.winfo_children(), "совет не появился")
        self.assertLess(self.lines(), before)
        self.assert_fills()  # форму не вытолкнуло — прокрутки нет
        # совет убрали («Снять») — поле снова растёт
        for row in form.hints.winfo_children():
            row.winfo_children()[1].event_generate("<Button-1>")
        self.settle()
        self.assertEqual(form.hints.winfo_children(), [])
        self.assertEqual(self.lines(), before)
        self.assert_fills()


if __name__ == "__main__":
    unittest.main()
