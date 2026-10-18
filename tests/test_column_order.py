"""Перестановка столбцов списка задач перетаскиванием заголовка: функции merge_column_order,
drop_index, move_column и настоящее окно TodoApp на временной базе (окно за краем экрана;
данные пользователя, трей, напоминания, обновления и тур не трогаются)."""

import gc
import shutil
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import todoro  # noqa: E402
from todoro import drop_index, merge_column_order, move_column  # noqa: E402

DEFAULT = ["num", "status", "marks", "title", "priority", "due", "remind",
           "assignee", "author", "created"]
PERSONAL = [c for c in DEFAULT if c not in ("assignee", "author")]


class MergeColumnOrderTests(unittest.TestCase):
    def test_nothing_saved_gives_default(self):
        for saved in (None, [], "", "мусор", 42, {"num": 1}, {}):
            with self.subTest(saved=saved):
                self.assertEqual(merge_column_order(saved, DEFAULT), DEFAULT)

    def test_saved_order_kept(self):
        saved = list(reversed(DEFAULT))
        self.assertEqual(merge_column_order(saved, DEFAULT), saved)

    def test_unknown_and_duplicates_dropped(self):
        saved = ["title", "чужой", "title", None, 5, ["num"], {"a": 1}, "num", "num"]
        result = merge_column_order(saved, ["num", "title"])
        self.assertEqual(result, ["title", "num"])

    def test_new_column_in_middle_goes_after_its_neighbour(self):
        """Столбец из новой версии встаёт сразу за тем, за кем стоит по умолчанию."""
        saved = ["title", "num", "due"]  # без «status», который по умолчанию за «num»
        self.assertEqual(merge_column_order(saved, ["num", "status", "title", "due"]),
                         ["title", "num", "status", "due"])

    def test_new_column_first_by_default_goes_first(self):
        saved = ["due", "title"]
        self.assertEqual(merge_column_order(saved, ["num", "title", "due"]),
                         ["num", "due", "title"])

    def test_several_new_columns_in_a_row(self):
        saved = ["due", "num"]
        self.assertEqual(merge_column_order(saved, ["num", "status", "marks", "title", "due"]),
                         ["due", "num", "status", "marks", "title"])

    def test_result_always_contains_every_default_once(self):
        for saved in (["created"], ["x", "y"], DEFAULT * 2, ["author", "num"]):
            with self.subTest(saved=saved):
                result = merge_column_order(saved, DEFAULT)
                self.assertEqual(sorted(result), sorted(DEFAULT))

    def test_does_not_change_arguments(self):
        saved, default = ["title", "num"], ["num", "status", "title"]
        merge_column_order(saved, default)
        self.assertEqual((saved, default), (["title", "num"], ["num", "status", "title"]))


class DropIndexTests(unittest.TestCase):
    lefts, widths = [30, 80, 180], [50, 100, 40]

    def test_left_of_everything_is_zero(self):
        self.assertEqual(drop_index(self.lefts, self.widths, -100), 0)
        self.assertEqual(drop_index(self.lefts, self.widths, 30), 0)

    def test_halves_of_column(self):
        # первый столбец 30…80, середина 55
        self.assertEqual(drop_index(self.lefts, self.widths, 54), 0)
        self.assertEqual(drop_index(self.lefts, self.widths, 55), 1)
        # второй 80…180, середина 130
        self.assertEqual(drop_index(self.lefts, self.widths, 129), 1)
        self.assertEqual(drop_index(self.lefts, self.widths, 131), 2)

    def test_right_of_everything_is_len(self):
        self.assertEqual(drop_index(self.lefts, self.widths, 205), 3)
        self.assertEqual(drop_index(self.lefts, self.widths, 10 ** 9), 3)

    def test_no_columns(self):
        self.assertEqual(drop_index([], [], 50), 0)

    def test_zero_width_column(self):
        self.assertEqual(drop_index([0, 10], [10, 0], 10), 2)


class MoveColumnTests(unittest.TestCase):
    order = ["a", "b", "c", "d"]

    def test_to_start(self):
        self.assertEqual(move_column(self.order, "c", 0, self.order), ["c", "a", "b", "d"])

    def test_to_end(self):
        self.assertEqual(move_column(self.order, "a", 3, self.order), ["b", "c", "d", "a"])
        self.assertEqual(move_column(self.order, "b", 99, self.order), ["a", "c", "d", "b"])

    def test_to_own_place(self):
        for i, column in enumerate(self.order):
            with self.subTest(column=column):
                self.assertEqual(move_column(self.order, column, i, self.order), self.order)

    def test_does_not_change_arguments(self):
        order, shown = list(self.order), list(self.order)
        move_column(order, "a", 2, shown)
        self.assertEqual((order, shown), (self.order, self.order))

    def test_hidden_columns_stay_with_neighbours(self):
        """Личный список: «Исполнитель» и «Автор» скрыты и остаются за «Напомнить»."""
        order = ["num", "title", "remind", "assignee", "author", "created"]
        shown = ["num", "title", "remind", "created"]
        # «Создана» в начало
        self.assertEqual(move_column(order, "created", 0, shown),
                         ["created", "num", "title", "remind", "assignee", "author"])
        # «№» в самый конец — за последним видимым, скрытые не трогаем
        self.assertEqual(move_column(order, "num", 3, shown),
                         ["title", "remind", "assignee", "author", "created", "num"])
        # «Напомнить» в начало — скрытые остаются между «Задачей» и «Создана»
        self.assertEqual(move_column(order, "remind", 0, shown),
                         ["remind", "num", "title", "assignee", "author", "created"])

    def test_to_end_when_last_shown_is_followed_by_hidden(self):
        order = ["num", "title", "assignee", "author"]
        shown = ["num", "title"]
        self.assertEqual(move_column(order, "num", 1, shown),
                         ["title", "num", "assignee", "author"])

    def test_only_one_shown_column(self):
        """Единственный видимый столбец некуда двигать — столбцы не теряются и не дублируются."""
        self.assertEqual(sorted(move_column(["a", "h"], "a", 0, ["a"])), ["a", "h"])

    def test_result_has_every_column_once(self):
        for column in DEFAULT:
            for place in range(len(PERSONAL) + 1):
                if column not in PERSONAL:
                    continue
                result = move_column(DEFAULT, column, place, PERSONAL)
                self.assertEqual(sorted(result), sorted(DEFAULT))


OFFSCREEN = "+-5000+-5000"


def close_root(root):
    """Закрывает окно, сначала отменив его отложенные вызовы (after) — иначе после destroy
    Tk печатает ошибки «invalid command name»."""
    try:
        jobs = root.tk.splitlist(root.tk.call("after", "info"))
    except tk.TclError:
        jobs = ()
    for job in jobs:
        # сам вызов Tcl, а не after_cancel: тот удаляет команду, и destroy виджета,
        # создавшего вызов, потом падает на повторном удалении
        try:
            root.tk.call("after", "cancel", job)
        except tk.TclError:
            pass
    try:
        root.destroy()
    except tk.TclError:
        pass


class ColumnDragWindowTests(unittest.TestCase):
    """Настоящий TodoApp на временной базе: перетаскивание заголовка, сортировка щелчком,
    сохранение порядка."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-test-"))
        patches = [
            mock.patch.object(db, "DATA_DIR", self.dir),
            mock.patch.object(db, "DB_PATH", self.dir / "todoro.db"),
            mock.patch.object(db, "LISTS_DIR", self.dir / "lists"),
            mock.patch.object(db, "OLD_DB_PATHS", []),
            mock.patch.object(todoro, "OUTLOOK_FLAG_FILE", self.dir / "from-outlook.flag"),
            mock.patch.object(todoro, "SNIP_FLAG_FILE", self.dir / "from-screen.flag"),
            # картинки привязаны к своему окну Tk: у каждого теста окно новое — грузим заново
            mock.patch.dict(todoro.IMAGES, clear=True),
            mock.patch.object(todoro, "clean_temp_files", lambda *a, **k: None),
            mock.patch.object(todoro, "bring_to_front", lambda *a, **k: None),
            mock.patch.object(todoro.TodoApp, "check_reminders", lambda self: None),
            mock.patch.object(todoro.TodoApp, "start_tray", lambda self: None),
            mock.patch.object(todoro.TodoApp, "auto_check_update", lambda self: None),
            mock.patch.object(todoro.TodoApp, "start_tour", lambda self: None),
            mock.patch.object(todoro.TodoApp, "watch_changes", lambda self: None),
            mock.patch("os.startfile", create=True),
            mock.patch("subprocess.Popen"),
            mock.patch("urllib.request.urlopen", side_effect=OSError("нет сети в тестах")),
        ]
        for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
                     "askyesnocancel"):
            if hasattr(todoro.ui, name):
                patches.append(mock.patch.object(todoro.ui, name, return_value=False))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        conn = db.connect(self.dir / "todoro.db")
        for title in ("Банан", "Апельсин", "Вишня"):
            db.add_task(conn, title)
        conn.close()
        self.roots = []
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            for conn in set(getattr(app, "list_conns", {}).values()):
                try:
                    conn.close()
                except Exception:
                    pass
        for root in self.roots:
            close_root(root)
        gc.collect()
        shutil.rmtree(self.dir, ignore_errors=True)

    def make_app(self):
        root = tk.Tk()
        self.roots.append(root)
        app = todoro.TodoApp(root)
        self.apps.append(app)
        root.deiconify()
        root.geometry("1500x600" + OFFSCREEN)
        for _ in range(10):
            root.update()
            time.sleep(0.02)
        self.assertEqual(app.view.get() if hasattr(app, "view") else "list", "list")
        return app

    def pump(self, app):
        for _ in range(3):
            app.root.update()

    def drag(self, app, column, to_x):
        tree = app.tree
        lefts, widths = app.column_edges()
        i = app.shown_columns().index(column)
        x0 = lefts[i] + widths[i] // 2
        tree.event_generate("<ButtonPress-1>", x=x0, y=10)
        step = 20 if to_x > x0 else -20
        for x in range(x0, to_x, step):
            tree.event_generate("<B1-Motion>", x=x, y=10, state=0x100)
        tree.event_generate("<B1-Motion>", x=to_x, y=10, state=0x100)
        tree.event_generate("<ButtonRelease-1>", x=to_x, y=10, state=0x100)
        self.pump(app)

    def click(self, app, column, shift=0):
        lefts, widths = app.column_edges()
        i = app.shown_columns().index(column)
        x = lefts[i] + widths[i] // 2 + shift
        app.tree.event_generate("<ButtonPress-1>", x=x, y=10)
        app.tree.event_generate("<ButtonRelease-1>", x=x, y=10, state=0x100)
        self.pump(app)

    def saved(self, app):
        return db.get_json_setting(app.prefs, "list_column_order", "нет настройки")

    def test_personal_list_hides_assignee_and_author(self):
        app = self.make_app()
        self.assertEqual(app.default_columns, DEFAULT)
        self.assertEqual(app.shown_columns(), PERSONAL)
        self.assertEqual(self.saved(app), "нет настройки")  # открытие ничего не пишет

    def test_drag_title_to_start_saves_order_without_sorting(self):
        app = self.make_app()
        sort_before = app.column_sort
        lefts, _ = app.column_edges()
        self.drag(app, "title", lefts[0] + 2)
        expected = ["title"] + [c for c in PERSONAL if c != "title"]
        self.assertEqual(app.shown_columns(), expected)
        self.assertEqual(app.column_sort, sort_before)  # отпускание заголовка не сортирует
        self.assertEqual(self.saved(app),
                         ["title"] + [c for c in DEFAULT if c != "title"])
        self.assertIsNone(app.column_drag)  # флаг «тянули» сброшен
        self.assertFalse(app.drop_line.winfo_ismapped())  # линия места спрятана

    def test_drag_to_end_keeps_hidden_columns_in_place(self):
        app = self.make_app()
        lefts, widths = app.column_edges()
        self.drag(app, "num", lefts[-1] + widths[-1] - 2)
        self.assertEqual(app.shown_columns(), PERSONAL[1:] + ["num"])
        saved = self.saved(app)
        self.assertEqual(saved[-1], "num")
        self.assertEqual(saved[saved.index("remind") + 1:saved.index("remind") + 3],
                         ["assignee", "author"])

    def test_small_jitter_is_click_and_sorts(self):
        """Сдвиг меньше 8 точек — это щелчок: сортирует, порядок не меняется."""
        app = self.make_app()
        lefts, widths = app.column_edges()
        i = PERSONAL.index("title")
        x0 = lefts[i] + widths[i] // 2
        app.tree.event_generate("<ButtonPress-1>", x=x0, y=10)
        app.tree.event_generate("<B1-Motion>", x=x0 + 5, y=10, state=0x100)
        app.tree.event_generate("<ButtonRelease-1>", x=x0 + 5, y=10, state=0x100)
        self.pump(app)
        self.assertEqual(app.shown_columns(), PERSONAL)
        self.assertEqual(app.column_sort, ["title", False])
        self.assertEqual(self.saved(app), "нет настройки")

    def test_drag_released_over_same_heading_does_not_sort(self):
        """Потянули больше 8 точек, но отпустили над тем же заголовком: Tk всё равно вызывает
        сортировку по нему — она должна промолчать, порядок прежний."""
        app = self.make_app()
        lefts, widths = app.column_edges()
        i = PERSONAL.index("title")
        x0 = lefts[i] + 20
        app.tree.event_generate("<ButtonPress-1>", x=x0, y=10)
        app.tree.event_generate("<B1-Motion>", x=x0 + 15, y=10, state=0x100)
        app.tree.event_generate("<B1-Motion>", x=x0 + 30, y=10, state=0x100)
        app.tree.event_generate("<ButtonRelease-1>", x=x0 + 30, y=10, state=0x100)
        self.pump(app)
        self.assertNotEqual(app.column_sort, ["title", False])
        self.assertEqual(app.shown_columns(), PERSONAL)
        self.assertEqual(self.saved(app), "нет настройки")
        self.assertIsNone(app.column_drag)

    def test_click_sorts_and_second_click_reverses(self):
        app = self.make_app()
        self.click(app, "title")
        self.assertEqual(app.column_sort, ["title", False])
        self.click(app, "title")
        self.assertEqual(app.column_sort, ["title", True])
        self.assertEqual(app.shown_columns(), PERSONAL)

    def test_click_after_drag_sorts_again(self):
        """После перетаскивания флаг сбрасывается — следующий щелчок снова сортирует."""
        app = self.make_app()
        lefts, _ = app.column_edges()
        self.drag(app, "due", lefts[0] + 2)
        self.click(app, "due")
        self.assertEqual(app.column_sort, ["due", False])

    def test_press_on_rows_does_not_drag(self):
        app = self.make_app()
        lefts, widths = app.column_edges()
        x0 = lefts[3] + 5
        app.tree.event_generate("<ButtonPress-1>", x=x0, y=60)
        self.assertIsNone(app.column_drag)
        app.tree.event_generate("<B1-Motion>", x=lefts[0], y=60, state=0x100)
        app.tree.event_generate("<ButtonRelease-1>", x=lefts[0], y=60, state=0x100)
        self.pump(app)
        self.assertEqual(app.shown_columns(), PERSONAL)
        self.assertEqual(self.saved(app), "нет настройки")

    def test_order_survives_restart(self):
        app = self.make_app()
        lefts, _ = app.column_edges()
        self.drag(app, "created", lefts[0] + 2)
        order = list(app.column_order)
        app.prefs.close()
        close_root(app.root)
        self.roots.remove(app.root)
        self.apps.remove(app)
        todoro.IMAGES.clear()
        app2 = self.make_app()
        self.assertEqual(app2.column_order, order)
        self.assertEqual(app2.shown_columns(), ["created"] + PERSONAL[:-1])

    def test_refresh_keeps_order(self):
        app = self.make_app()
        lefts, _ = app.column_edges()
        self.drag(app, "priority", lefts[0] + 2)
        shown = app.shown_columns()
        app.refresh()
        self.pump(app)
        self.assertEqual(app.shown_columns(), shown)

    def test_reset_to_default_saves_none(self):
        app = self.make_app()
        lefts, _ = app.column_edges()
        self.drag(app, "title", lefts[0] + 2)
        app.set_column_order(list(app.default_columns))
        self.assertIsNone(self.saved(app))
        self.assertEqual(app.shown_columns(), PERSONAL)

    def test_broken_setting_gives_default(self):
        conn = db.connect(self.dir / "todoro.db")
        db.set_setting(conn, "list_column_order", "{не json")
        conn.close()
        app = self.make_app()
        self.assertEqual(app.column_order, DEFAULT)

    def test_setting_from_older_version_gets_new_columns(self):
        """В сохранённом порядке нет «marks» — он встаёт за «status», как по умолчанию."""
        conn = db.connect(self.dir / "todoro.db")
        db.set_json_setting(conn, "list_column_order",
                            ["title", "num", "status", "priority", "due", "remind", "created",
                             "старый"])
        conn.close()
        app = self.make_app()
        self.assertEqual(app.column_order[:4], ["title", "num", "status", "marks"])
        self.assertEqual(sorted(app.column_order), sorted(DEFAULT))

    def test_heading_menu_offers_reset(self):
        app = self.make_app()
        calls = []

        class FakeMenu:
            def command(self, text, action, enabled=True, **_):
                calls.append((text, enabled, action))
                return self

            def popup(self, *args):
                pass

        with mock.patch.object(todoro, "PopupMenu", FakeMenu):
            event = mock.Mock(x=10, y=10, x_root=0, y_root=0)
            app.show_heading_menu(event)
            self.assertEqual(calls[-1][:2], ("Вернуть порядок столбцов", False))
            lefts, _ = app.column_edges()
            self.drag(app, "title", lefts[0] + 2)
            app.show_heading_menu(event)
            self.assertEqual(calls[-1][:2], ("Вернуть порядок столбцов", True))
            calls[-1][2]()
        self.assertEqual(app.shown_columns(), PERSONAL)
        self.assertIsNone(self.saved(app))

    def test_right_click_on_heading_opens_heading_menu(self):
        app = self.make_app()
        with mock.patch.object(todoro.TodoApp, "show_heading_menu") as menu:
            app.show_menu(mock.Mock(x=200, y=10, x_root=0, y_root=0))
        menu.assert_called_once()


if __name__ == "__main__":
    unittest.main()
