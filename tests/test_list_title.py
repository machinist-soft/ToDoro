"""Заголовок задачи в списке (TodoApp.list_title): 📧 и 📎 с числом файлов — в начале строки,
💬 с числом комментариев — в конце. И значки для доски/матрицы (extras_mark) — прежние.
Окна не открываются: метод вызывается на подставном объекте."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import todoro  # noqa: E402


def title(task_id, text, counts=None, mail=()):
    fake = SimpleNamespace(extra_counts=counts or {}, mail_ids=set(mail))
    return todoro.TodoApp.list_title(fake, task_id, text)


class ListTitleTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(title(1, "Купить хлеб"), "Купить хлеб")

    def test_zero_counts_plain(self):
        """Запись (0, 0) в extra_counts — как будто её нет."""
        self.assertEqual(title(1, "Купить хлеб", {1: (0, 0)}), "Купить хлеб")

    def test_none_counts_plain(self):
        self.assertEqual(title(1, "Купить хлеб", {1: None}), "Купить хлеб")

    def test_files_only_in_front(self):
        self.assertEqual(title(1, "Отчёт", {1: (2, 0)}), "📎 2  Отчёт")

    def test_comments_only_at_end(self):
        self.assertEqual(title(1, "Отчёт", {1: (0, 1)}), "Отчёт   💬 1")

    def test_mail_files_comments(self):
        self.assertEqual(title(7, "Ответить", {7: (3, 1)}, mail={7}), "📧 📎 3  Ответить   💬 1")

    def test_mail_only(self):
        self.assertEqual(title(7, "Ответить", mail={7}), "📧 Ответить")

    def test_mail_and_comments(self):
        self.assertEqual(title(7, "Ответить", {7: (0, 4)}, mail={7}), "📧 Ответить   💬 4")

    def test_files_and_comments(self):
        self.assertEqual(title(5, "Х", {5: (1, 2)}), "📎 1  Х   💬 2")

    def test_other_task_counts_ignored(self):
        """Значки другой задачи (и её письмо) не попадают в заголовок."""
        self.assertEqual(title(1, "Моя", {2: (5, 5)}, mail={2}), "Моя")

    def test_big_numbers(self):
        self.assertEqual(title(1, "Т", {1: (1234, 99999)}), "📎 1234  Т   💬 99999")

    def test_empty_title(self):
        self.assertEqual(title(1, "", {1: (2, 1)}, mail={1}), "📧 📎 2     💬 1")

    def test_files_not_repeated_at_end(self):
        """Скрепка — только в начале, в конце строки её больше нет."""
        text = title(1, "Отчёт", {1: (2, 3)}, mail={1})
        self.assertEqual(text.count("📎"), 1)
        self.assertEqual(text.count("📧"), 1)
        self.assertTrue(text.startswith("📧 📎 2  "))
        self.assertTrue(text.endswith("   💬 3"))


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
