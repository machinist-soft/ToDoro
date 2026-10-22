"""Перенос срока перетаскиванием в календаре (GitHub #9): db.move_due (защита от чужой правки),
TodoApp.move_due (время сохраняется, сообщение при конфликте) и само перетаскивание в CalendarView.
Временные файлы; окна Tk — за краем экрана; ui.* подменены; данные пользователя не трогаются."""

import sys
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from tests.test_core import TempDir  # noqa: E402

OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0), (2, "Выполнено", "#22c55e", 1)]


def row(task_id, due, title=None):
    return (task_id, title or f"задача {task_id}", 0, "2026-01-01 00:00", due, None, 0, 0, "", 1)


class MoveDueDbTests(TempDir):
    def setUp(self):
        super().setUp()
        self.conn = db.connect(self.dir / "a.db")
        self.tid = db.add_task(self.conn, "отчёт")
        db.update_task(self.conn, self.tid, "отчёт", "2030-03-10 09:30", 15)

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def due(self):
        return db.get_task(self.conn, self.tid)[1]

    def test_moves_and_bumps_version_and_author(self):
        before = db.task_meta(self.conn, self.tid)["version"]
        self.assertTrue(db.move_due(self.conn, self.tid, "2030-03-10 09:30", "2030-03-20 09:30", by="Анна"))
        self.assertEqual(self.due(), "2030-03-20 09:30")
        meta = db.task_meta(self.conn, self.tid)
        self.assertEqual(meta["version"], before + 1)
        self.assertEqual(meta["updated_by"], "Анна")
        self.assertEqual(db.get_task(self.conn, self.tid)[2], 15)  # «напомнить за» не тронуто

    def test_resets_reminded(self):
        db.mark_reminded(self.conn, self.tid)
        db.move_due(self.conn, self.tid, "2030-03-10 09:30", "2030-03-11 09:30")
        reminded = self.conn.execute("SELECT reminded FROM tasks WHERE id = ?", (self.tid,)).fetchone()[0]
        self.assertEqual(reminded, 0)

    def test_changed_meanwhile_not_moved(self):
        """Другой участник успел поменять срок — перенос не затирает его правку."""
        db.update_task(self.conn, self.tid, "отчёт", "2030-04-01 12:00", None, by="Борис")
        before = db.task_meta(self.conn, self.tid)["version"]
        self.assertFalse(db.move_due(self.conn, self.tid, "2030-03-10 09:30", "2030-03-20 09:30", by="Анна"))
        self.assertEqual(self.due(), "2030-04-01 12:00")
        meta = db.task_meta(self.conn, self.tid)
        self.assertEqual((meta["version"], meta["updated_by"]), (before, "Борис"))

    def test_other_connection_sees_conflict(self):
        """Два «участника» с одним файлом: второй перенос по устаревшему сроку — False."""
        other = db.connect(self.dir / "a.db")
        try:
            self.assertTrue(db.move_due(other, self.tid, "2030-03-10 09:30", "2030-03-12 09:30", by="Борис"))
            self.assertFalse(db.move_due(self.conn, self.tid, "2030-03-10 09:30", "2030-03-15 09:30"))
            self.assertEqual(self.due(), "2030-03-12 09:30")
        finally:
            other.close()

    def test_missing_task(self):
        self.assertFalse(db.move_due(self.conn, 999, "2030-03-10 09:30", "2030-03-20 09:30"))

    def test_task_without_due(self):
        """old_due = None сравнивается через IS — задача без срока тоже находится."""
        tid = db.add_task(self.conn, "без срока")
        self.assertTrue(db.move_due(self.conn, tid, None, "2030-03-20 09:00"))
        self.assertEqual(db.get_task(self.conn, tid)[1], "2030-03-20 09:00")

    def test_deleted_task(self):
        db.delete_task(self.conn, self.tid)
        self.assertFalse(db.move_due(self.conn, self.tid, "2030-03-10 09:30", "2030-03-20 09:30"))


class TodoAppMoveDueTests(TempDir):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def setUp(self):
        super().setUp()
        self.conn = db.connect(self.dir / "a.db")
        self.tid = db.add_task(self.conn, "отчёт")
        self.calls = []
        self.app = SimpleNamespace(conn=self.conn, root=None,
                                   finish_editing=lambda: self.calls.append("finish"),
                                   created_by=lambda: "Анна",
                                   refresh=lambda select_id=None: self.calls.append(("refresh", select_id)))

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def move(self, old_due, day):
        with mock.patch.object(self.T.ui, "showinfo") as showinfo, \
                mock.patch.object(self.T.ui, "showerror") as showerror:
            self.T.TodoApp.move_due(self.app, self.tid, old_due, day)
        return showinfo, showerror

    def test_keeps_time(self):
        db.update_task(self.conn, self.tid, "отчёт", "2030-03-10 09:30", None)
        showinfo, showerror = self.move("2030-03-10 09:30", date(2030, 4, 2))
        self.assertEqual(db.get_task(self.conn, self.tid)[1], "2030-04-02 09:30")
        self.assertEqual(db.task_meta(self.conn, self.tid)["updated_by"], "Анна")
        self.assertEqual(self.calls, ["finish", ("refresh", self.tid)])
        showinfo.assert_not_called()
        showerror.assert_not_called()

    def test_date_only_due(self):
        db.update_task(self.conn, self.tid, "отчёт", "2030-03-10", None)
        self.move("2030-03-10", date(2030, 3, 11))
        self.assertEqual(db.get_task(self.conn, self.tid)[1], "2030-03-11")

    def test_conflict_shows_message(self):
        db.update_task(self.conn, self.tid, "отчёт", "2030-05-05 08:00", None, by="Борис")
        showinfo, _ = self.move("2030-03-10 09:30", date(2030, 4, 2))
        self.assertEqual(db.get_task(self.conn, self.tid)[1], "2030-05-05 08:00")
        showinfo.assert_called_once()
        self.assertEqual(showinfo.call_args[0][0], "Срок не перенесён")
        self.assertIn(("refresh", self.tid), self.calls)  # календарь показывает новый вид

    def test_db_error_shown_no_extra_message(self):
        self.conn.close()
        showinfo, showerror = self.move("2030-03-10 09:30", date(2030, 4, 2))
        showerror.assert_called_once()
        self.assertIn("Не удалось перенести срок", showerror.call_args[0][1])
        showinfo.assert_not_called()
        self.assertIn(("refresh", self.tid), self.calls)
        self.conn = db.connect(self.dir / "a.db")  # для tearDown

    def test_dragging_counts_calendar(self):
        idle = SimpleNamespace(drag=None)
        app = SimpleNamespace(board=idle, matrix=idle, calendar=SimpleNamespace(drag={"id": 1}))
        self.assertTrue(self.T.TodoApp.dragging(app))
        app.calendar = idle
        self.assertFalse(self.T.TodoApp.dragging(app))


class CalendarDragTests(unittest.TestCase):
    """Перетаскивание в CalendarView: события подаются прямо в обработчики (окно за краем экрана)."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("900x700" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.calls = []
        app = SimpleNamespace(repeats={}, root=self.root)
        app.select_task = lambda tid: self.calls.append(("select", tid))
        app.clear_selection = lambda: self.calls.append(("clear",))
        app.new_task_at = lambda place: self.calls.append(("new", place))
        app.new_task_menu = lambda place, x, y: self.calls.append(("new menu", place))
        app.edit = lambda: self.calls.append(("edit",))
        app.show_menu_for = lambda *a: self.calls.append(("menu",))
        app.move_due = lambda tid, old, day: self.calls.append(("move", tid, old, day))
        self.app = app
        self.view = self.T.CalendarView(self.root, app)
        self.view.pack(fill="both", expand=True)
        self.view.month = date(2030, 3, 1)
        self.view.render(STATUSES, [row(1, "2030-03-10 09:30"), row(2, None)], set())
        self.root.update()

    def tearDown(self):
        if self.view.drag and self.view.drag.get("ghost") is not None:
            self.view.drag["ghost"].destroy()
        self.view.destroy()
        self.root.update()

    def center(self, widget):
        return SimpleNamespace(x_root=widget.winfo_rootx() + widget.winfo_width() // 2,
                               y_root=widget.winfo_rooty() + widget.winfo_height() // 2)

    def cell(self, day):
        return dict(self.view.cells)[day]

    def drag_to(self, target_event, release=True):
        chip = self.view.chips[1][0]
        start = self.center(chip)
        self.view.on_press(start, 1, chip)
        self.view.on_motion(target_event)
        self.view.follow_mouse()
        if release:
            self.view.on_release(target_event)
            self.root.update()

    def moves(self):
        return [c for c in self.calls if c[0] == "move"]

    def test_due_of_and_cells(self):
        self.assertEqual(self.view.due_of, {1: "2030-03-10 09:30"})  # задача без срока не попала
        self.assertIn(date(2030, 3, 20), dict(self.view.cells))
        self.assertEqual(self.view.day_at(*vars(self.center(self.cell(date(2030, 3, 20)))).values()),
                         date(2030, 3, 20))

    def test_drop_on_other_day_moves(self):
        self.drag_to(self.center(self.cell(date(2030, 3, 20))))
        self.assertEqual(self.moves(), [("move", 1, "2030-03-10 09:30", date(2030, 3, 20))])
        self.assertIsNone(self.view.drag)
        self.assertEqual(str(self.view.cget("cursor")), "")
        for _, cell in self.view.cells:  # подсветка снята
            self.assertEqual(str(cell.cget("highlightbackground")), cell.bg)

    def test_ghost_follows_and_target_highlighted(self):
        target = date(2030, 3, 20)
        self.drag_to(self.center(self.cell(target)), release=False)
        ghost = self.view.drag["ghost"]
        self.assertTrue(ghost.winfo_exists())
        self.assertEqual(self.view.drag["target"], target)
        self.assertEqual(str(self.cell(target).cget("highlightbackground")), self.T.ACCENT)
        self.assertEqual(str(self.cell(date(2030, 3, 10)).cget("highlightbackground")),
                         self.cell(date(2030, 3, 10)).bg)
        self.assertTrue(self.T.TodoApp.dragging(SimpleNamespace(
            board=SimpleNamespace(drag=None), matrix=SimpleNamespace(drag=None), calendar=self.view)))
        self.view.on_release(self.center(self.cell(target)))
        self.root.update()
        self.assertFalse(ghost.winfo_exists())

    def test_drop_on_same_day_does_nothing(self):
        self.drag_to(self.center(self.cell(date(2030, 3, 10))))
        self.assertEqual(self.moves(), [])
        self.assertIsNone(self.view.drag)

    def test_drop_outside_days_does_nothing(self):
        far = SimpleNamespace(x_root=self.root.winfo_rootx() + 5000, y_root=self.root.winfo_rooty() + 5000)
        self.drag_to(far)
        self.assertEqual(self.moves(), [])
        self.assertIsNone(self.view.drag)

    def test_click_without_moving_only_selects(self):
        chip = self.view.chips[1][0]
        start = self.center(chip)
        self.view.on_press(start, 1, chip)
        near = SimpleNamespace(x_root=start.x_root + 2, y_root=start.y_root + 1)  # меньше 6 точек
        self.view.on_motion(near)
        self.assertIsNone(self.view.drag["ghost"])
        self.view.on_release(near)
        self.root.update()
        self.assertEqual(self.calls, [("select", 1)])
        self.assertIsNone(self.view.drag)

    def test_redraw_during_press_cancels_drag(self):
        chip = self.view.chips[1][0]
        start = self.center(chip)
        self.view.on_press(start, 1, chip)
        self.view.draw()  # календарь перерисовали (например, пришли изменения) — строки уже другие
        self.root.update()
        self.view.on_motion(self.center(self.cell(date(2030, 3, 20))))
        self.assertIsNone(self.view.drag)
        self.view.on_release(self.center(self.cell(date(2030, 3, 20))))
        self.assertEqual(self.moves(), [])

    def test_redraw_while_dragging_removes_ghost(self):
        """Месяц пролистали колёсиком посреди перетаскивания — копия строки не остаётся на экране."""
        self.drag_to(self.center(self.cell(date(2030, 3, 20))), release=False)
        ghost = self.view.drag["ghost"]
        self.view.draw()
        self.assertIsNone(self.view.drag)
        self.assertFalse(ghost.winfo_exists())
        self.assertEqual(str(self.view.cget("cursor")), "")

    def test_release_and_motion_without_press(self):
        event = self.center(self.cell(date(2030, 3, 20)))
        self.view.on_motion(event)
        self.view.on_release(event)
        self.view.follow_mouse()
        self.assertEqual(self.moves(), [])

    def test_projected_repeat_not_draggable(self):
        """Будущий повтор — не задача: щелчок только выбирает, перетаскивания нет."""
        self.app.repeats = {1: ("day", None, 0)}
        self.view.render(STATUSES, [row(1, "2030-03-10 09:30")], set())
        self.root.update()
        own = set(map(str, self.view.chips[1]))
        # плашка — рамка с надписью внутри (chip.label); повтор узнаём по значку в надписи
        projected = [w for _, cell in self.view.cells for w in cell.winfo_children()
                     if hasattr(w, "label") and self.T.REPEAT_MARK in str(w.label.cget("text"))]
        self.assertTrue(projected)
        for chip in projected:
            self.assertNotIn(str(chip), own)
            for part in (chip, *chip.winfo_children()):  # ни рамка, ни полоска, ни надпись
                self.assertEqual(part.bind("<B1-Motion>"), "")
                self.assertEqual(part.bind("<ButtonRelease-1>"), "")
                self.assertNotEqual(part.bind("<Button-1>"), "")  # щелчок — выбрать
        for chip in self.view.chips[1]:
            for part in (chip, *chip.winfo_children()):
                self.assertNotEqual(part.bind("<B1-Motion>"), "")

    def test_drop_on_day_of_other_month(self):
        """День соседнего месяца, видный в сетке (бледный), — тоже цель переноса."""
        other = self.view.cells[0][0]
        self.assertNotEqual(other.month, 3)
        self.drag_to(self.center(self.cell(other)))
        self.assertEqual(self.moves(), [("move", 1, "2030-03-10 09:30", other)])


if __name__ == "__main__":
    unittest.main()
