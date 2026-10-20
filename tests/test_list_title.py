"""Столбец значков в списке задач (TodoApp.list_marks, marks_order): 📧 из письма, 📎 с числом
файлов и 💬 с числом комментариев — отдельно от названия, и сортировка по этому столбцу.
Значки для доски/матрицы (extras_mark) — прежние.
Окна не открываются: методы вызываются на подставном объекте."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import todoro  # noqa: E402


def fake_app(counts=None, mail=(), column_sort=None):
    fake = SimpleNamespace(extra_counts=counts or {}, mail_ids=set(mail),
                           column_sort=column_sort, authors={}, assignees={}, unit_names={},
                           sort_key=lambda row: row[0])
    fake.marks_order = lambda task_id: todoro.TodoApp.marks_order(fake, task_id)
    return fake


def marks(task_id, counts=None, mail=()):
    return todoro.TodoApp.list_marks(fake_app(counts, mail), task_id)


def order(task_id, counts=None, mail=()):
    return todoro.TodoApp.marks_order(fake_app(counts, mail), task_id)


class ListMarksTests(unittest.TestCase):
    def test_nothing(self):
        self.assertEqual(marks(1), "")

    def test_zero_counts_empty(self):
        """Запись (0, 0) в extra_counts — как будто её нет."""
        self.assertEqual(marks(1, {1: (0, 0)}), "")

    def test_none_counts_empty(self):
        self.assertEqual(marks(1, {1: None}), "")

    def test_files_only(self):
        self.assertEqual(marks(1, {1: (2, 0)}), "📎 2")

    def test_comments_only(self):
        self.assertEqual(marks(1, {1: (0, 1)}), "💬 1")

    def test_mail_only(self):
        self.assertEqual(marks(7, mail={7}), "📧")

    def test_mail_files_comments(self):
        self.assertEqual(marks(7, {7: (3, 2)}, mail={7}), "📧  📎 3  💬 2")

    def test_mail_and_comments(self):
        self.assertEqual(marks(7, {7: (0, 4)}, mail={7}), "📧  💬 4")

    def test_files_and_comments(self):
        self.assertEqual(marks(5, {5: (1, 2)}), "📎 1  💬 2")

    def test_other_task_ignored(self):
        """Значки другой задачи (и её письмо) не попадают в строку."""
        self.assertEqual(marks(1, {2: (5, 5)}, mail={2}), "")

    def test_big_numbers(self):
        self.assertEqual(marks(1, {1: (1234, 99999)}), "📎 1234  💬 99999")

    def test_no_edge_spaces(self):
        """Без пробелов в начале и в конце — столбец узкий, текст начинается с края."""
        text = marks(1, {1: (2, 3)}, mail={1})
        self.assertEqual(text, text.strip())

    def test_title_method_removed(self):
        """Название задачи больше не склеивается со значками: list_title удалён."""
        self.assertFalse(hasattr(todoro.TodoApp, "list_title"))


class MarksOrderTests(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertIsNone(order(1))
        self.assertIsNone(order(1, {1: (0, 0)}))
        self.assertIsNone(order(1, {1: None}))
        self.assertIsNone(order(1, {2: (3, 3)}, mail={2}))

    def test_values(self):
        self.assertEqual(order(1, {1: (2, 3)}), (-2, -3, 0))
        self.assertEqual(order(1, {1: (0, 1)}), (0, -1, 0))
        self.assertEqual(order(1, mail={1}), (0, 0, -1))
        self.assertEqual(order(1, {1: (1, 0)}, mail={1}), (-1, 0, -1))

    def test_files_before_comments_before_mail(self):
        """Больше файлов — выше; при равных файлах — больше комментариев; потом письмо."""
        self.assertLess(order(1, {1: (2, 0)}), order(1, {1: (1, 99)}))
        self.assertLess(order(1, {1: (1, 5)}), order(1, {1: (1, 4)}))
        self.assertLess(order(1, {1: (1, 4)}, mail={1}), order(1, {1: (1, 4)}))


def row(task_id, title="Задача"):
    # (id, title, done, _, due_at, remind_before, urgent, important, _, status_id)
    return (task_id, title, False, None, None, None, False, False, None, 1)


class SortByMarksTests(unittest.TestCase):
    """sort_rows по столбцу «📎 💬»: пустые — всегда внизу."""

    counts = {1: (1, 0), 2: (3, 0), 4: (0, 2), 5: (3, 1)}
    mail = {6}
    statuses = [(1, "Новая")]

    def sort(self, descending):
        fake = fake_app(self.counts, self.mail, ["marks", descending])
        rows = [row(i) for i in (7, 3, 1, 6, 5, 4, 2)]
        return [r[0] for r in todoro.TodoApp.sort_rows(fake, rows, self.statuses)]

    def test_ascending(self):
        # 5 (3 файла, 1 комм.), 2 (3 файла), 1 (1 файл), 4 (2 комм.), 6 (письмо); потом 3, 7
        self.assertEqual(self.sort(False), [5, 2, 1, 4, 6, 3, 7])

    def test_descending(self):
        self.assertEqual(self.sort(True), [6, 4, 1, 2, 5, 3, 7])

    def test_equal_marks_by_number(self):
        """Одинаковые значки — по номеру задачи (сортировка устойчивая)."""
        fake = fake_app({3: (1, 1), 1: (1, 1), 2: (1, 1)}, (), ["marks", False])
        rows = [row(i) for i in (3, 1, 2)]
        self.assertEqual([r[0] for r in todoro.TodoApp.sort_rows(fake, rows, self.statuses)],
                         [1, 2, 3])

    def test_all_empty(self):
        fake = fake_app({}, (), ["marks", True])
        rows = [row(i) for i in (2, 1)]
        self.assertEqual([r[0] for r in todoro.TodoApp.sort_rows(fake, rows, self.statuses)],
                         [1, 2])

    def test_title_sort_ignores_marks(self):
        """Сортировка по «Задаче» — только по названию, значки на неё не влияют."""
        fake = fake_app({1: (9, 9)}, {1}, ["title", False])
        rows = [row(1, "Яблоко"), row(2, "арбуз")]
        self.assertEqual([r[0] for r in todoro.TodoApp.sort_rows(fake, rows, self.statuses)],
                         [2, 1])


class ExtrasMarkTests(unittest.TestCase):
    """extras_mark (доска и матрица) не менялась."""

    def test_all(self):
        self.assertEqual(todoro.extras_mark((2, 3), True), "   📧  📎 2  💬 3")

    def test_nothing(self):
        self.assertEqual(todoro.extras_mark(None), "")
        self.assertEqual(todoro.extras_mark((0, 0), False), "")

    def test_parts(self):
        self.assertEqual(todoro.extras_mark((2, 0)), "   📎 2")
        self.assertEqual(todoro.extras_mark((0, 3)), "   💬 3")
        self.assertEqual(todoro.extras_mark(None, True), "   📧")
        self.assertEqual(todoro.extras_mark((0, 1), True), "   📧  💬 1")


if __name__ == "__main__":
    unittest.main()
