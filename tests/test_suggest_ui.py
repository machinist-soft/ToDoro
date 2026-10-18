"""Выпадающий список вариантов названия (TitleSuggest) — с настоящим Tk, окно за краем экрана.

Список должен быть рамкой внутри окна поля, а не отдельным окном: отдельное окно Windows
показывало в углу экрана, делало активным, и список тут же закрывался."""

import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_smart import row  # noqa: E402

ROWS = [row(1, "Позвонить в бухгалтерию"), row(2, "Позвонить маме"), row(3, "Позвонить врачу")]
OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#888888", 0), (2, "Выполнено", "#00aa00", 1)]


def task(title=""):
    return dict(title=title, due_at=None, remind_before=None, urgent=0, important=0, body="",
                status_id=1, assignee=None, version=1)


class SuggestUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("640x360" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.frame = tk.Frame(self.root)
        self.frame.pack(fill="both", expand=True)
        self.entry = tk.Entry(self.frame, width=20)
        self.entry.pack(padx=30, pady=(40, 0), anchor="w")
        self.root.update()
        self.suggest = self.T.TitleSuggest(self.entry, self.entry.get, lambda: ROWS)

    def tearDown(self):
        self.suggest.close()
        self.frame.destroy()
        self.root.update()

    def wait(self, ms):
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def popups(self, top):
        return [w for w in top.winfo_children() if w.winfo_class() == "Frame" and w is not self.frame]

    def test_popup_is_frame_in_entry_window(self):
        self.suggest.show(["Позвонить маме", "Позвонить врачу"])
        popup = self.suggest.popup
        self.assertIsInstance(popup, tk.Frame)
        self.assertNotIsInstance(popup, tk.Toplevel)
        self.assertIs(popup.master, self.entry.winfo_toplevel())
        self.assertTrue(self.suggest.shown())

    def test_popup_placed_under_entry(self):
        self.suggest.show(["Позвонить маме"])
        self.root.update()
        info = self.suggest.popup.place_info()
        x = self.entry.winfo_rootx() - self.root.winfo_rootx()
        y = self.entry.winfo_rooty() - self.root.winfo_rooty() + self.entry.winfo_height() + 2
        self.assertEqual((int(info["x"]), int(info["y"])), (x, y))
        self.assertEqual(int(info["width"]), max(self.entry.winfo_width(), 260))
        # рамка правда видна там же, где поле, — не в углу экрана
        self.assertTrue(self.suggest.popup.winfo_ismapped())
        self.assertEqual(self.suggest.popup.winfo_rootx(), self.entry.winfo_rootx())
        self.assertEqual(self.suggest.popup.winfo_rooty(),
                         self.entry.winfo_rooty() + self.entry.winfo_height() + 2)

    def test_width_not_past_right_edge(self):
        top = tk.Toplevel(self.root)
        top.geometry("200x200" + OFFSCREEN)
        entry = tk.Entry(top, width=5)
        entry.pack(padx=(30, 0), pady=20, anchor="w")
        top.update()
        suggest = self.T.TitleSuggest(entry, entry.get, lambda: ROWS)
        suggest.show(["Позвонить маме"])
        x = int(suggest.popup.place_info()["x"])
        self.assertEqual(int(suggest.popup.place_info()["width"]), max(top.winfo_width() - x - 4, 120))
        self.assertLessEqual(x + int(suggest.popup.place_info()["width"]), top.winfo_width())
        top.destroy()

    def test_stays_open_while_entry_focused(self):
        self.entry.focus_force()
        self.root.update()
        self.suggest.show(["Позвонить маме"])
        self.wait(400)  # раньше список закрывался через 200 мс
        self.assertTrue(self.suggest.shown())
        self.assertTrue(self.suggest.popup.winfo_exists())
        if self.entry.focus_get() is self.entry:  # Windows может не дать фокус окну за экраном
            self.suggest.close_if_unfocused()
            self.assertTrue(self.suggest.shown())

    def test_closes_when_focus_elsewhere(self):
        other = tk.Entry(self.frame)
        other.pack()
        self.suggest.show(["Позвонить маме"])
        with mock.patch.object(self.entry, "focus_get", return_value=other):
            self.suggest.close_if_unfocused()
        self.assertFalse(self.suggest.shown())

    def test_typed_then_update_shows(self):
        self.entry.insert(0, "Позв")
        self.suggest.typed(mock.Mock(keysym="v"))
        self.assertFalse(self.suggest.shown())  # считает не сразу, а через 120 мс
        self.wait(300)
        self.assertTrue(self.suggest.shown())
        self.assertEqual(self.suggest.items[0], "Позвонить врачу")
        self.assertEqual(len(self.suggest.items), 3)

    def test_typed_arrows_ignored_and_nothing_found_closes(self):
        self.entry.insert(0, "Позв")
        self.suggest.typed(mock.Mock(keysym="Down"))
        self.wait(200)
        self.assertFalse(self.suggest.shown())
        self.suggest.show(["Позвонить маме"])
        self.entry.delete(0, "end")
        self.entry.insert(0, "Купить")
        self.suggest.update()
        self.assertFalse(self.suggest.shown())

    def test_close_cancels_pending_update(self):
        self.entry.insert(0, "Позв")
        self.suggest.typed(mock.Mock(keysym="v"))
        self.suggest.close()
        self.wait(250)
        self.assertFalse(self.suggest.shown())

    def test_move_and_accept(self):
        self.suggest.show(["Позвонить маме", "Позвонить врачу"])
        popup = self.suggest.popup
        self.assertEqual(self.suggest.move(1), "break")
        self.assertEqual(self.suggest.move(1), "break")
        self.assertEqual(self.suggest.index, 1)
        self.assertEqual(self.suggest.move(1), "break")
        self.assertEqual(self.suggest.index, 0)  # по кругу
        self.assertTrue(self.suggest.accept())
        self.assertEqual(self.entry.get(), "Позвонить маме")
        self.assertFalse(self.suggest.shown())
        self.assertFalse(popup.winfo_exists())

    def test_up_first_goes_to_last(self):
        self.suggest.show(["a1", "a2", "a3"])
        self.suggest.move(-1)
        self.assertEqual(self.suggest.index, 2)
        self.assertTrue(self.suggest.accept())
        self.assertEqual(self.entry.get(), "a3")

    def test_accept_without_choice(self):
        self.entry.insert(0, "Позв")
        self.suggest.show(["Позвонить маме"])
        popup = self.suggest.popup
        self.assertFalse(self.suggest.accept())
        self.assertEqual(self.entry.get(), "Позв")
        self.assertFalse(popup.winfo_exists())
        self.assertFalse(self.suggest.accept())  # и без списка — не падает
        self.assertIsNone(self.suggest.move(1))

    def test_pick_by_click(self):
        self.entry.insert(0, "Позв")
        self.suggest.show(["Позвонить маме", "Позвонить врачу"])
        self.suggest.pick(1)
        self.assertEqual(self.entry.get(), "Позвонить врачу")
        self.assertFalse(self.suggest.shown())

    def test_escape_and_close_remove_frame(self):
        self.entry.focus_force()
        self.root.update()
        self.suggest.show(["Позвонить маме"])
        popup = self.suggest.popup
        # клавиши Tk доставляет только полю с фокусом
        self.assertIs(self.entry.focus_get(), self.entry, "окно за экраном не получило фокус")
        self.entry.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(popup.winfo_exists())
        self.assertFalse(self.suggest.shown())
        self.suggest.show(["Позвонить маме"])
        popup = self.suggest.popup
        self.suggest.close()
        self.assertFalse(popup.winfo_exists())
        self.suggest.close()  # повторно — не падает

    def test_repeated_show_one_frame(self):
        before = len(self.popups(self.root))
        for items in (["a1"], ["a1", "a2"], ["b1", "b2", "b3"]):
            self.suggest.show(items)
        self.root.update()
        self.assertEqual(len(self.popups(self.root)), before + 1)
        self.assertEqual(len(self.suggest.labels), 3)
        self.suggest.close()
        self.assertEqual(len(self.popups(self.root)), before)

    def assert_under(self, suggest, entry):
        popup = suggest.popup
        self.assertIsNotNone(popup, "список закрылся")
        self.assertEqual(popup.winfo_rootx(), entry.winfo_rootx())
        self.assertEqual(popup.winfo_rooty(), entry.winfo_rooty() + entry.winfo_height() + 2)

    def test_follows_when_neighbor_appears_and_hides(self):
        """Над полем появилась и исчезла полоса — список переезжает за полем, не закрываясь."""
        self.suggest.show(["Позвонить маме"])
        self.root.update()
        self.assert_under(self.suggest, self.entry)
        start = self.entry.winfo_rooty()
        neighbor = tk.Frame(self.frame, height=50, width=10)
        neighbor.pack(before=self.entry)
        self.wait(350)
        self.assertNotEqual(self.entry.winfo_rooty(), start)  # поле правда сдвинулось
        self.assert_under(self.suggest, self.entry)
        neighbor.destroy()
        self.wait(350)
        self.assertEqual(self.entry.winfo_rooty(), start)
        self.assert_under(self.suggest, self.entry)

    def test_follows_entry_resize(self):
        self.suggest.show(["Позвонить маме"])
        self.root.update()
        self.entry.configure(width=60)
        self.wait(350)
        self.assertTrue(self.suggest.shown())
        self.assert_under(self.suggest, self.entry)
        x = int(self.suggest.popup.place_info()["x"])
        self.assertEqual(int(self.suggest.popup.place_info()["width"]),
                         min(max(self.entry.winfo_width(), 260), max(self.root.winfo_width() - x - 4, 120)))

    def test_follows_window_resize(self):
        """Окно стало ниже — список (снизу больше не влезает) переезжает над полем."""
        top = tk.Toplevel(self.root)
        top.geometry("400x200" + OFFSCREEN)
        frame = tk.Frame(top)
        frame.pack(side="top", fill="x")
        entry = tk.Entry(frame)
        entry.pack(pady=(150, 0))
        top.update()
        suggest = self.T.TitleSuggest(entry, entry.get, lambda: ROWS)
        top.geometry("400x600")
        top.update()
        suggest.show(["a1", "a2", "a3"])
        top.update()
        self.assert_under(suggest, entry)
        top.geometry("400x220")
        self.wait(350)
        self.assertTrue(suggest.shown())
        self.assertEqual(suggest.popup.winfo_rooty() + suggest.popup.winfo_reqheight() + 2,
                         entry.winfo_rooty())
        suggest.close()
        top.destroy()

    def test_low_window_popup_above(self):
        top = tk.Toplevel(self.root)
        top.geometry("400x300" + OFFSCREEN)
        entry = tk.Entry(top)
        entry.pack(side="bottom", pady=(0, 10))
        top.update()
        suggest = self.T.TitleSuggest(entry, entry.get, lambda: ROWS)
        suggest.show(["a1", "a2", "a3"])
        top.update()
        popup = suggest.popup
        entry_y = entry.winfo_rooty() - top.winfo_rooty()
        self.assertEqual(int(popup.place_info()["y"]), entry_y - popup.winfo_reqheight() - 2)
        self.assertGreaterEqual(int(popup.place_info()["y"]), 0)
        self.assertEqual(popup.winfo_rooty() + popup.winfo_reqheight() + 2, entry.winfo_rooty())
        suggest.close()
        top.destroy()

    def test_no_room_anywhere_stays_below(self):
        """Ни сверху, ни снизу не помещается — рамка под полем (не уходит выше окна)."""
        top = tk.Toplevel(self.root)
        top.geometry("400x60" + OFFSCREEN)
        entry = tk.Entry(top)
        entry.pack(pady=(10, 0))
        top.update()
        suggest = self.T.TitleSuggest(entry, entry.get, lambda: ROWS)
        suggest.show(["a1", "a2", "a3", "a4", "a5"])
        top.update()
        y = entry.winfo_rooty() - top.winfo_rooty() + entry.winfo_height() + 2
        self.assertEqual(int(suggest.popup.place_info()["y"]), y)
        suggest.close()
        top.destroy()

    def test_close_cancels_follow(self):
        self.suggest.show(["Позвонить маме"])
        job = self.suggest.follow_job
        self.assertIsNotNone(job)
        self.suggest.show(["Позвонить врачу"])  # повторный show не заводит вторую слежку
        self.assertEqual(self.suggest.follow_job, job)
        self.suggest.close()
        self.assertIsNone(self.suggest.follow_job)
        self.assertNotIn(job, self.root.tk.splitlist(self.root.tk.call("after", "info")))
        self.suggest.follow()  # уже закрыт — ничего не делает и не заводит новую
        self.assertIsNone(self.suggest.follow_job)

    def test_follow_keeps_running_while_open(self):
        self.suggest.show(["Позвонить маме"])
        first = self.suggest.follow_job
        self.wait(400)
        self.assertIsNotNone(self.suggest.follow_job)
        self.assertNotEqual(self.suggest.follow_job, first)

    def test_follow_after_window_destroyed(self):
        top = tk.Toplevel(self.root)
        top.geometry("300x200" + OFFSCREEN)
        entry = tk.Entry(top)
        entry.pack(pady=20)
        top.update()
        suggest = self.T.TitleSuggest(entry, entry.get, lambda: ROWS)
        suggest.show(["a1"])
        with mock.patch.object(self.root, "report_callback_exception") as errors:
            top.destroy()
            self.wait(350)
            errors.assert_not_called()
        self.assertIsNone(suggest.follow_job)
        # слежка сработала, когда окна уже нет, а список ещё числится открытым — не падает
        suggest.popup = mock.Mock()
        suggest.follow()
        self.assertIsNone(suggest.follow_job)
        suggest.popup = None

    def test_entry_destroyed(self):
        self.suggest.show(["Позвонить маме"])
        popup = self.suggest.popup
        self.entry.destroy()
        self.root.update()
        self.assertFalse(popup.winfo_exists())
        self.suggest.update()  # отложенный подсчёт после закрытия формы — не падает


class TaskFormSuggestTests(unittest.TestCase):
    """В форме задачи список тоже — рамка в окне формы."""

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

    def test_task_form_in_own_window(self):
        top = tk.Toplevel(self.root)
        top.geometry(OFFSCREEN)
        history = ROWS + [row(4, "Позвонить завтра в налоговую")]
        form = self.T.TaskForm(top, task(), STATUSES, on_save=lambda r: None, on_cancel=lambda: None,
                               history=history, hints=True)
        form.pack(fill="both")
        top.update()
        form.title_entry.insert(0, "Позвонить завтра")
        form.suggest.update()
        popup = form.suggest.popup
        self.assertIsInstance(popup, tk.Frame)
        self.assertIs(popup.master, top)
        self.assertIsNot(popup.master, self.root)
        # советы под заголовком (срок из названия) не закрывают список
        form.update_hints()
        top.update()
        self.assertTrue(form.suggest.shown())
        self.assertTrue(popup.winfo_exists())
        top.destroy()

    def test_task_form_without_history(self):
        top = tk.Toplevel(self.root)
        top.geometry(OFFSCREEN)
        form = self.T.TaskForm(top, task(), STATUSES, on_save=lambda r: None, on_cancel=lambda: None)
        self.assertIsNone(form.suggest)
        top.destroy()

    def test_task_dialog(self):
        def offscreen(window, *args, **kwargs):
            window.geometry(OFFSCREEN)

        with mock.patch.object(self.T, "center_on_screen", offscreen), \
                mock.patch.object(self.T, "bring_to_front"):
            dialog = self.T.TaskDialog(self.root, task(), STATUSES, history=ROWS, hints=True)
        try:
            dialog.update()
            form = dialog.form
            form.suggest.show(["Позвонить маме"])
            dialog.update()
            popup = form.suggest.popup
            self.assertIs(popup.master, dialog)
            x = form.title_entry.winfo_rootx() - dialog.winfo_rootx()
            self.assertEqual(int(popup.place_info()["x"]), x)
            self.assertTrue(form.suggest.accept() is False)
            form.suggest.show(["Позвонить маме"])
            form.suggest.move(1)
            self.assertTrue(form.suggest.accept())
            self.assertEqual(form.title_entry.get(), "Позвонить маме")
        finally:
            dialog.grab_release()
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
