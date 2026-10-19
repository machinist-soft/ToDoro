"""Окно «Новая задача со снимка экрана» (TaskDialog) не выходит за край экрана (сообщение #1):
окно растёт под строку подсказки, на невысоком экране уменьшает картинку снимка, затем поле
«Описание», затем убирает картинку; появилось место — возвращает как было. Настоящий Tk,
окна прозрачные; рабочая область экрана подменяется (todoro.work_area); данные пользователя
не трогаются (пути db — во временной папке)."""

import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

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


def task():
    return dict(title="", body="", due_at=None, remind_before=None, urgent=False,
                important=False, status_id=1, assignee=None, version=None)


class DialogFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        from PIL import Image
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.withdraw()
        todoro.setup_style(cls.root)
        cls.image = Image.new("RGB", (1600, 900), "#88aacc")  # большой снимок — картинка 180 px
        cls.real_place = staticmethod(todoro.place_window)
        cls.real_work_area = staticmethod(todoro.work_area)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.dialogs = []
        self.area = (0, 0, 1920, 3000)

        def place(window, *args, **kwargs):
            window.attributes("-alpha", 0.0)  # окно показывается, но его не видно
            return self.real_place(window, *args, **kwargs)

        for p in (mock.patch.object(self.T, "work_area", lambda w: self.area),
                  mock.patch.object(self.T, "place_window", place),
                  mock.patch.object(self.T, "bring_to_front")):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        for dialog in self.dialogs:
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
        self.root.update()

    def settle(self, dialog):
        for _ in range(5):
            dialog.update()

    def dialog(self, area, image=True):
        self.area = area
        dialog = self.T.TaskDialog(
            self.root, task(), STATUSES, title="Новая задача со снимка экрана",
            note="Со снимка экрана, в список «Мои задачи». Снимок 1600 × 900 будет приложен.",
            standalone=True, image=self.image if image else None, history=[], hints=True)
        self.dialogs.append(dialog)
        self.settle(dialog)
        return dialog

    def retitle(self, dialog, title):
        dialog.form.title_entry.delete(0, "end")
        dialog.form.title_entry.insert(0, title)
        dialog.form.update_hints()
        self.settle(dialog)

    def hint_texts(self, dialog):
        return [line.winfo_children()[0].cget("text") for line in dialog.form.hints.winfo_children()]

    def outer_top(self, dialog):
        return dialog.winfo_y()

    def bottom(self, dialog):
        """Низ окна на экране (вместе с рамкой — с запасом в несколько пикселей не считаем)."""
        return dialog.winfo_rooty() + dialog.winfo_height()

    def assert_inside(self, dialog, area):
        left, top, width, height = area
        self.assertLessEqual(self.bottom(dialog), top + height,
                             "низ окна ушёл за рабочую область")
        self.assertGreaterEqual(self.outer_top(dialog), top, "верх окна выше рабочей области")
        # кнопки «Сохранить»/«Отмена» видны целиком: внутри окна
        for button in self.buttons(dialog):
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), self.bottom(dialog))
            self.assertTrue(button.winfo_ismapped())

    def buttons(self, dialog):
        found = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    text = child.cget("text")
                except tk.TclError:
                    text = None
                if text in ("Сохранить", "Отмена"):
                    found.append(child)
                walk(child)

        walk(dialog.form)
        self.assertEqual(len(found), 2, "не нашёл кнопки «Сохранить» и «Отмена»")
        return found

    def natural_height(self, image=True):
        """Высота окна на большом экране (картинка и описание полного размера)."""
        dialog = self.dialog((0, 0, 1920, 3000), image=image)
        height = dialog.winfo_height()
        title_bar = dialog.winfo_rooty() - dialog.winfo_y()
        dialog.grab_release()
        dialog.destroy()
        self.dialogs.remove(dialog)
        self.root.update()
        return height, title_bar

    # --- work_area ---

    def test_work_area_reasonable(self):
        left, top, width, height = self.real_work_area(self.root)
        self.assertGreater(width, 200)
        self.assertGreater(height, 200)
        self.assertLessEqual(width, self.root.winfo_screenwidth() * 4)  # с учётом масштаба
        self.assertGreaterEqual(left, -10000)
        self.assertGreaterEqual(top, -10000)

    def test_work_area_fallback_when_windows_fails(self):
        """Windows не ответил (или ответил пустым прямоугольником) — размер экрана из Tk."""
        work_area = self.real_work_area
        user32 = self.T.ctypes.windll.user32
        screen = (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        with mock.patch.object(user32, "SystemParametersInfoW", return_value=0):
            self.assertEqual(work_area(self.root), screen)
        with mock.patch.object(user32, "SystemParametersInfoW", side_effect=OSError):
            self.assertEqual(work_area(self.root), screen)
        with mock.patch.object(user32, "SystemParametersInfoW", return_value=1):
            # прямоугольник остался нулевым — тоже запасной вариант
            self.assertEqual(work_area(self.root), screen)

    # --- окно со снимком ---

    def test_big_screen_full_picture_and_description(self):
        dialog = self.dialog((0, 0, 1920, 3000))
        self.assertTrue(dialog.preview_label.winfo_ismapped())
        self.assertEqual(dialog.preview.height(), 180)
        self.assertEqual(dialog.desc_lines, 6)
        self.assertEqual(int(dialog.form.desc.cget("height")), 6)
        self.retitle(dialog, "срочно купить хлеб")
        self.assertTrue(any("Срочно" in t for t in self.hint_texts(dialog)))
        self.assertEqual(dialog.preview.height(), 180)
        self.assertEqual(dialog.desc_lines, 6)
        self.assert_inside(dialog, self.area)

    def test_window_grows_for_hint_on_big_screen(self):
        """Окно вытягивается под строку подсказки (раньше размер был зафиксирован)."""
        dialog = self.dialog((0, 0, 1920, 3000))
        before = dialog.winfo_height()
        self.retitle(dialog, "срочно купить хлеб")
        self.assertGreater(dialog.winfo_height(), before)
        self.assert_inside(dialog, self.area)
        self.retitle(dialog, "")
        self.assertEqual(dialog.winfo_height(), before)

    def test_small_screen_hint_keeps_buttons_on_screen(self):
        """Экран чуть выше окна: появилась подсказка «срочно» — низ окна не уходит за панель
        задач; стёрли заголовок — окно как было."""
        height, title_bar = self.natural_height()
        area = (0, 0, 1366, height + title_bar + self.T.TaskDialog.MARGIN + 4)
        dialog = self.dialog(area)
        self.assertEqual(dialog.preview.height(), 180)  # пока влезает целиком
        self.assertEqual(dialog.desc_lines, 6)
        before = (dialog.winfo_height(), dialog.winfo_y())
        self.assert_inside(dialog, area)
        self.retitle(dialog, "срочно купить хлеб")
        self.assertTrue(any("Срочно" in t for t in self.hint_texts(dialog)))
        self.assert_inside(dialog, area)
        self.assertLess(dialog.preview.height(), 180, "картинка должна была уменьшиться")
        self.assertEqual(dialog.desc_lines, 6, "сначала уменьшается картинка, а не описание")
        self.retitle(dialog, "")
        self.assertEqual(self.hint_texts(dialog), [])
        self.assertEqual(dialog.preview.height(), 180)
        self.assertEqual(dialog.desc_lines, 6)
        self.assertEqual(dialog.winfo_height(), before[0])
        self.assert_inside(dialog, area)

    def test_shifted_work_area_bottom_and_top(self):
        """Панель задач сверху (рабочая область начинается не с 0): окно не выше её верха."""
        height, title_bar = self.natural_height()
        area = (0, 120, 1366, height + title_bar + self.T.TaskDialog.MARGIN + 4)
        dialog = self.dialog(area)
        self.assert_inside(dialog, area)
        self.retitle(dialog, "срочно позвонить важно")
        self.assert_inside(dialog, area)

    def test_medium_screen_description_shrinks_after_picture(self):
        """Не хватает больше, чем даёт картинка (до 40 px), — укорачивается и «Описание»."""
        height, title_bar = self.natural_height()
        area = (0, 0, 1366, height + title_bar + self.T.TaskDialog.MARGIN - 160)
        dialog = self.dialog(area)
        self.assertTrue(dialog.preview_label.winfo_ismapped())
        self.assertEqual(dialog.preview.height(), 40)
        self.assertLess(dialog.desc_lines, 6)
        self.assertGreaterEqual(dialog.desc_lines, 2)
        self.assert_inside(dialog, area)
        self.retitle(dialog, "срочно купить хлеб")
        self.assert_inside(dialog, area)

    def test_very_small_screen_picture_removed(self):
        area = (0, 40, 1366, 420)
        dialog = self.dialog(area)
        self.assertEqual(dialog.preview_label.winfo_manager(), "", "картинка должна быть убрана")
        self.assertEqual(dialog.desc_lines, 2)
        self.assertGreaterEqual(dialog.winfo_y(), area[1], "верх окна выше рабочей области")
        self.retitle(dialog, "срочно купить хлеб")
        self.assertEqual(dialog.preview_label.winfo_manager(), "")
        self.assertGreaterEqual(dialog.winfo_y(), area[1])
        # стали больше места — картинка возвращается на своё место (над формой)
        self.area = (0, 0, 1920, 3000)
        dialog.keep_on_screen()
        self.settle(dialog)
        self.assertEqual(dialog.preview_label.winfo_manager(), "pack")
        self.assertEqual(dialog.preview.height(), 180)
        self.assertEqual(dialog.desc_lines, 6)
        packed = dialog.pack_slaves()
        self.assertLess(packed.index(dialog.preview_label), packed.index(dialog.form))

    def test_without_picture_small_screen(self):
        """Окно без снимка (например, из письма): не влезает — укорачивается только описание."""
        height, title_bar = self.natural_height(image=False)
        area = (0, 0, 1366, height + title_bar + self.T.TaskDialog.MARGIN - 40)
        dialog = self.dialog(area, image=False)
        self.assertIsNone(dialog.preview)
        self.assertLess(dialog.desc_lines, 6)
        self.assert_inside(dialog, area)
        self.retitle(dialog, "срочно купить хлеб")
        self.assert_inside(dialog, area)
        self.retitle(dialog, "")
        self.assert_inside(dialog, area)

    def test_hints_frame_shrinks_when_emptied(self):
        """После стирания подсказок пустая рамка не держит прежнюю высоту."""
        dialog = self.dialog((0, 0, 1920, 3000))
        empty = dialog.form.hints.winfo_height()
        self.retitle(dialog, "срочно купить хлеб")
        self.assertGreater(dialog.form.hints.winfo_height(), empty)
        self.retitle(dialog, "")
        self.assertLessEqual(dialog.form.hints.winfo_height(), max(empty, 1))

    def test_small_picture_not_enlarged(self):
        """Маленький снимок не растягивается до 180 px."""
        from PIL import Image
        small = Image.new("RGB", (300, 60))
        self.area = (0, 0, 1920, 3000)
        dialog = self.T.TaskDialog(self.root, task(), STATUSES, standalone=True, image=small,
                                   history=[], hints=True)
        self.dialogs.append(dialog)
        self.settle(dialog)
        self.assertEqual(dialog.preview.height(), 60)


if __name__ == "__main__":
    unittest.main()
