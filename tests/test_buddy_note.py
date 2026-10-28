"""Разовые сообщения Тоторо (GitHub #14): «Задача перенесена…» и «Общий список … удалил другой
участник» через BUDDY_NOTE_MS сменяются обычной подсказкой. И матрица (GitHub #15): карточки
уже, в четверть шириной ~630 точек встают три колонки."""

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import todoro  # noqa: E402
from tests.test_quick_add import WindowTestCase  # noqa: E402

T = todoro


class FakeRoot:
    """root.after / after_cancel без Tk: запоминает таймеры."""

    def __init__(self):
        self.jobs, self.cancelled, self.count = {}, [], 0

    def after(self, ms, func):
        self.count += 1
        job = f"after#{self.count}"
        self.jobs[job] = (ms, func)
        return job

    def after_cancel(self, job):
        self.cancelled.append(job)
        self.jobs.pop(job, None)


def fake_app(**extra):
    app = SimpleNamespace(root=FakeRoot(), buddy_note_job=None, BUDDY_NOTE_MS=T.TodoApp.BUDDY_NOTE_MS,
                          side=SimpleNamespace(totoro=mock.Mock()), update_buddy=mock.Mock())
    app.end_buddy_note = lambda: T.TodoApp.end_buddy_note(app)
    app.say_for_a_while = lambda *a, **k: T.TodoApp.say_for_a_while(app, *a, **k)
    for name, value in extra.items():
        setattr(app, name, value)
    return app


class SayForAWhileTests(unittest.TestCase):
    def test_delay_is_five_seconds(self):
        self.assertEqual(T.TodoApp.BUDDY_NOTE_MS, 5000)

    def test_shows_and_schedules_return(self):
        app = fake_app()
        app.say_for_a_while("Привет", mood="done")
        app.side.totoro.show.assert_called_once_with("Привет", mood="done")
        self.assertEqual(list(app.root.jobs), [app.buddy_note_job])
        ms, func = app.root.jobs[app.buddy_note_job]
        self.assertEqual(ms, 5000)
        app.update_buddy.assert_not_called()
        func()  # прошло 5 секунд
        app.update_buddy.assert_called_once_with()
        self.assertIsNone(app.buddy_note_job)

    def test_default_mood(self):
        app = fake_app()
        app.say_for_a_while("Текст")
        app.side.totoro.show.assert_called_once_with("Текст", mood="normal")

    def test_second_note_cancels_first_timer(self):
        """Второе сообщение подряд держится свои 5 секунд: таймер первого отменён."""
        app = fake_app()
        app.say_for_a_while("Первое")
        first = app.buddy_note_job
        app.say_for_a_while("Второе")
        self.assertEqual(app.root.cancelled, [first])
        self.assertNotEqual(app.buddy_note_job, first)
        self.assertEqual(list(app.root.jobs), [app.buddy_note_job])

    def test_after_timer_new_note_does_not_cancel_stale(self):
        """Таймер уже сработал — следующему сообщению отменять нечего."""
        app = fake_app()
        app.say_for_a_while("Первое")
        app.root.jobs.pop(app.buddy_note_job)[1]()
        app.say_for_a_while("Второе")
        self.assertEqual(app.root.cancelled, [])


class CallersTests(unittest.TestCase):
    def test_move_to_list_note_goes_away(self):
        app = fake_app(finish_editing=mock.Mock(), clear_selection=mock.Mock(), refresh=mock.Mock(),
                       conn="src", list_conn=lambda list_id: "dst",
                       lists=[{"id": "personal", "name": "Личный"}, {"id": "abc", "name": "Дом"}])
        with mock.patch.object(T.db, "move_task_to") as move:
            T.TodoApp.move_to_list(app, 7, "abc")
        move.assert_called_once_with("src", 7, "dst")
        app.side.totoro.show.assert_called_once_with("Задача перенесена в список «Дом».", mood="done")
        self.assertIsNotNone(app.buddy_note_job)
        app.refresh.assert_called_once()

    def probe_app(self, lists_after):
        app = fake_app(team_counter=5, list_id="shared1", lists=[], reminders_due=False,
                       forget_list=mock.Mock(), show_list_name=mock.Mock(), check_list_changed=mock.Mock(),
                       do_check_reminders=mock.Mock())
        app.load_lists = lambda: setattr(app, "lists", lists_after)
        app.switch_list = lambda list_id: setattr(app, "list_id", list_id)
        return app

    def test_shared_list_deleted_note_goes_away(self):
        app = self.probe_app([{"id": db.PERSONAL, "name": "Личный"}])
        T.TodoApp.on_fresh_probe(app, SimpleNamespace(team_counter=6))
        app.forget_list.assert_called_once_with("shared1")
        self.assertEqual(app.list_id, db.PERSONAL)
        app.side.totoro.show.assert_called_once_with(
            "Общий список, который был открыт, удалил другой участник.", mood="alert")
        self.assertIsNotNone(app.buddy_note_job)
        app.show_list_name.assert_not_called()

    def test_shared_list_still_there_no_note(self):
        app = self.probe_app([{"id": db.PERSONAL}, {"id": "shared1"}])
        T.TodoApp.on_fresh_probe(app, SimpleNamespace(team_counter=6))
        app.side.totoro.show.assert_not_called()
        self.assertIsNone(app.buddy_note_job)
        app.show_list_name.assert_called_once()

    def test_first_probe_no_note(self):
        app = self.probe_app([{"id": db.PERSONAL}])
        app.team_counter = None
        T.TodoApp.on_fresh_probe(app, SimpleNamespace(team_counter=6))
        app.side.totoro.show.assert_not_called()
        self.assertEqual(app.list_id, "shared1")


class BuddyNoteWindowTests(WindowTestCase):
    """Настоящее окно: перенос задачи в другой личный список — сообщение, потом обычная подсказка."""

    def wait(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def test_no_timer_at_start(self):
        self.assertIsNone(self.app.buddy_note_job)

    def test_move_note_then_usual_hint(self):
        app = self.app
        file = db.new_list_file()
        db.save_registry(app.prefs, db.list_registry(app.prefs) + [{"id": "home", "name": "Дом", "file": file}])
        app.load_lists()
        task_id = db.add_task(app.conn, "Купить хлеб")
        db.add_task(app.conn, "Позвонить")
        app.refresh()
        self.pump()
        usual = app.side.totoro.message
        with mock.patch.object(T.TodoApp, "BUDDY_NOTE_MS", 300):
            app.move_to_list(task_id, "home")
            self.pump()
            self.assertEqual(app.side.totoro.message[0], "Задача перенесена в список «Дом».")
            self.assertEqual(app.side.totoro.message[3], "done")
            self.assertIsNotNone(app.buddy_note_job)
            self.wait(0.6)
        self.assertIsNone(app.buddy_note_job)
        self.assertNotIn("перенесена", app.side.totoro.message[0])
        self.assertEqual(app.side.totoro.message[3], usual[3])
        self.assertEqual([t[1] for t in db.list_tasks(app.list_conn("home"))], ["Купить хлеб"])

    def test_two_notes_second_held_full_time(self):
        app = self.app
        with mock.patch.object(T.TodoApp, "BUDDY_NOTE_MS", 400):
            app.say_for_a_while("Первое")
            self.wait(0.25)
            app.say_for_a_while("Второе", mood="alert")
            self.wait(0.25)  # 500 мс от первого: его таймер сработал бы, но он отменён
            self.assertEqual(app.side.totoro.message[0], "Второе")
            self.wait(0.4)
        self.assertNotEqual(app.side.totoro.message[0], "Второе")
        self.assertIsNone(app.buddy_note_job)

    def test_close_window_with_pending_note(self):
        """Окно закрыли, пока висит сообщение, — таймер не мешает закрытию (без исключений)."""
        self.app.say_for_a_while("Пока")
        self.assertIsNotNone(self.app.buddy_note_job)


class MatrixColumnsTests(unittest.TestCase):
    def fake(self, inside):
        matrix = SimpleNamespace(CARD=T.EisenhowerMatrix.CARD, GAP=T.EisenhowerMatrix.GAP,
                                 inside_width=lambda: inside, drawn_columns=None)
        matrix.columns = lambda: T.EisenhowerMatrix.columns(matrix)
        return matrix

    def test_card_narrower_than_board(self):
        self.assertEqual(T.EisenhowerMatrix.CARD, 190)
        self.assertLess(T.EisenhowerMatrix.CARD, T.LANE_WIDTH - 20)

    def test_three_columns_in_632(self):
        """Четверть ~632 точки (экран 1920 с широкой боковой панелью) — три колонки;
        с прежней шириной карточки (LANE_WIDTH - 20) было две."""
        self.assertEqual(self.fake(632).columns(), 3)
        old = self.fake(632)
        old.CARD = T.LANE_WIDTH - 20
        self.assertEqual(old.columns(), 2)

    def test_columns_by_width(self):
        card, gap = T.EisenhowerMatrix.CARD, T.EisenhowerMatrix.GAP
        for inside, expected in ((0, 1), (-50, 1), (card - 1, 1), (card, 1), (2 * card + gap - 1, 1),
                                 (2 * card + gap, 2), (3 * card + 2 * gap, 3), (10 ** 6, 10 ** 6 // (card + gap))):
            self.assertEqual(self.fake(inside).columns(), expected, inside)

    def test_cards_stretch_to_fill(self):
        """Карточки растягиваются на всю четверть и не уже CARD."""
        for inside in (100, 190, 400, 632, 700, 1000):
            matrix = self.fake(inside)
            matrix.drawn_columns = matrix.columns()
            size = T.EisenhowerMatrix.card_size(matrix)
            self.assertGreaterEqual(size, T.EisenhowerMatrix.CARD, inside)
            if inside >= T.EisenhowerMatrix.CARD:
                used = size * matrix.drawn_columns + T.EisenhowerMatrix.GAP * (matrix.drawn_columns - 1)
                self.assertLessEqual(used, inside, inside)
                self.assertGreater(used, inside - matrix.drawn_columns, inside)


class MatrixWindowTests(WindowTestCase):
    def test_full_hd_window_three_columns(self):
        """Окно 1920 точек в ширину, вид «Матрица»: в четверть встают три карточки в ряд."""
        self.root.geometry("1920x1000" + "+-5000+-5000")
        for i in range(5):
            db.add_task(self.app.conn, f"Задача {i}")
        self.show("matrix")
        self.app.refresh()
        self.pump(10)
        matrix = self.app.matrix
        self.assertGreaterEqual(matrix.columns(), 3, matrix.inside_width())
        self.assertEqual(matrix.drawn_columns, matrix.columns())


if __name__ == "__main__":
    unittest.main()
