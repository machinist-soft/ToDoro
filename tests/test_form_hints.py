"""Умные подсказки в форме задачи (TaskForm): режимы hints=True / "changed" / False, явные
«срочно/важно» отмечаются сразу (со ссылкой «Снять»), срок из названия не предлагается, если
он уже стоит. Настоящий Tk, окна за краем экрана; данные пользователя не трогаются."""

import sys
import tkinter as tk
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import smart  # noqa: E402
from tests.test_smart import row  # noqa: E402

OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0)]


def task(title="", urgent=0, important=0, due_at=None, body="", remind_before=None):
    return dict(title=title, body=body, due_at=due_at, remind_before=remind_before,
                urgent=urgent, important=important, status_id=1, assignee=None, version=3)


class FormHintsTests(unittest.TestCase):
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
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
        self.root.update()

    def form(self, data, hints="changed", history=()):
        def offscreen(window, *args, **kwargs):
            window.geometry(OFFSCREEN)

        with mock.patch.object(self.T, "center_on_screen", offscreen), \
                mock.patch.object(self.T, "bring_to_front"):
            dialog = self.T.TaskDialog(self.root, data, STATUSES, history=list(history),
                                       hints=hints)
        self.dialogs.append(dialog)
        dialog.update()
        return dialog.form

    def retitle(self, form, title):
        form.title_entry.delete(0, "end")
        form.title_entry.insert(0, title)
        form.update_hints()
        form.update()

    def rows(self, form):
        """Строки советов: [(текст, ссылка)]."""
        result = []
        for line in form.hints.winfo_children():
            labels = [w.cget("text") for w in line.winfo_children()]
            result.append((labels[0].removeprefix("✨ "), labels[1]))
        return result

    def click(self, form, action):
        for line in form.hints.winfo_children():
            link = line.winfo_children()[1]
            if link.cget("text") == action:
                link.event_generate("<Button-1>")
                form.update()
                return
        self.fail(f"нет ссылки «{action}»: {self.rows(form)}")

    def prio(self, form):
        return form.urgent.get(), form.important.get()

    # --- правка готовой задачи (hints="changed") ---

    def test_example_from_task_add_urgent_to_important(self):
        """Правка «купить Подарки на Новый год завтра» (Важно) → дописали «срочно » в начало."""
        title = "купить Подарки на Новый год завтра"
        form = self.form(task(title, important=1))
        self.assertEqual(self.rows(form), [])
        self.retitle(form, "срочно " + title)
        self.assertEqual(self.prio(form), (True, True))
        texts = self.rows(form)
        self.assertIn(("Отметил «Срочно» — так сказано в названии", "Снять"), texts)
        # срок «завтра» был и в прежнем названии — не предлагается снова
        self.assertFalse(any(link == "Поставить" for _, link in texts), texts)

    def test_changed_unchanged_title_gives_nothing(self):
        form = self.form(task("срочно позвонить завтра в 10"))
        form.update_hints()
        self.assertEqual(self.rows(form), [])
        self.assertEqual(self.prio(form), (False, False))
        # лишние пробелы по краям — тоже «не менялся»
        self.retitle(form, "  срочно позвонить завтра в 10  ")
        self.assertEqual(self.rows(form), [])
        self.assertEqual(self.prio(form), (False, False))

    def test_changed_explicit_word_already_in_old_title_not_marked(self):
        """«срочно» было в прежнем названии (и галочку сознательно не ставили) — не отмечаем."""
        form = self.form(task("срочно позвонить"))
        self.retitle(form, "срочно позвонить маме")
        self.assertEqual(self.prio(form), (False, False))
        self.assertFalse(any(link == "Снять" for _, link in self.rows(form)))

    def test_unchecked_by_hand_not_marked_again(self):
        """Нашу галочку сняли руками — дописали ещё текст, а она не вернулась."""
        form = self.form(task(""), hints=True)
        self.retitle(form, "срочно позвонить")
        self.assertEqual(self.prio(form), (True, False))
        form.urgent.set(False)
        form.priority_changed()
        self.retitle(form, "срочно позвонить маме")
        self.assertEqual(self.prio(form), (False, False))
        self.assertFalse(any(link == "Снять" for _, link in self.rows(form)))
        self.retitle(form, "срочно позвонить маме важно")  # другое слово — по-прежнему отмечаем
        self.assertEqual(self.prio(form), (False, True))

    def test_changed_each_word_separately(self):
        """«срочно» было в прежнем названии, дописали «важно» — отмечаем только «Важно»."""
        form = self.form(task("срочно позвонить"))
        self.retitle(form, "срочно позвонить важно")
        self.assertEqual(self.prio(form), (False, True))
        self.assertTrue(any(link == "Снять" for _, link in self.rows(form)))

    def test_changed_new_when_offered_old_when_not(self):
        form = self.form(task("позвонить завтра"))
        self.retitle(form, "позвонить маме завтра")
        self.assertFalse(any(link == "Поставить" for _, link in self.rows(form)))
        # дописали время — срок другой, предлагаем
        self.retitle(form, "позвонить маме завтра в 10")
        self.assertTrue(any(text.startswith("Срок в названии:") and link == "Поставить"
                            for text, link in self.rows(form)), self.rows(form))

    def test_changed_when_offered_and_applied(self):
        form = self.form(task("отчёт"))
        self.retitle(form, "отчёт завтра в 10")
        self.click(form, "Поставить")
        tomorrow = date.today() + timedelta(days=1)
        self.assertEqual(form.date.value, tomorrow)
        self.assertEqual((form.hour.get(), form.minute.get()), ("10", "00"))
        self.assertEqual(form.title_entry.get(), "отчёт завтра в 10")
        self.assertFalse(any(link == "Поставить" for _, link in self.rows(form)))

    def test_changed_when_already_set_not_offered(self):
        """Такой срок уже стоит в форме — совет не нужен."""
        tomorrow = date.today() + timedelta(days=1)
        form = self.form(task("отчёт", due_at=f"{tomorrow:%Y-%m-%d} 10:00", remind_before=15))
        self.retitle(form, "отчёт завтра в 10")
        self.assertFalse(any(link == "Поставить" for _, link in self.rows(form)), self.rows(form))
        # другое время — предлагаем
        self.retitle(form, "отчёт завтра в 11")
        self.assertTrue(any(link == "Поставить" for _, link in self.rows(form)))

    def test_when_day_only_already_set_any_time(self):
        """Только день («завтра») и срок на этот день уже стоит (в любое время) — не предлагаем."""
        tomorrow = date.today() + timedelta(days=1)
        form = self.form(task("отчёт", due_at=f"{tomorrow:%Y-%m-%d} 15:30"), hints=True)
        self.retitle(form, "отчёт завтра")
        self.assertFalse(any(link == "Поставить" for _, link in self.rows(form)), self.rows(form))

    def test_due_is(self):
        tomorrow = date.today() + timedelta(days=1)
        form = self.form(task("x", due_at=f"{tomorrow:%Y-%m-%d} 10:00"))
        self.assertTrue(form.due_is(smart.parse_when("x завтра в 10")))
        self.assertTrue(form.due_is(smart.parse_when("x завтра")))
        self.assertFalse(form.due_is(smart.parse_when("x завтра в 11")))
        self.assertFalse(form.due_is(smart.parse_when("x послезавтра")))
        empty = self.form(task("x"))
        self.assertFalse(empty.due_is(smart.parse_when("x завтра")))

    # --- явные слова: отметка сразу и «Снять» ---

    def test_new_task_explicit_urgent_marked_at_once(self):
        form = self.form(task(), hints=True)
        self.retitle(form, "срочно позвонить")
        self.assertEqual(self.prio(form), (True, False))
        self.assertIn(("Отметил «Срочно» — так сказано в названии", "Снять"), self.rows(form))
        self.assertNotIn("prio", form.hints_used)
        self.assertEqual(form.auto_marked, [True, False])

    def test_explicit_never_unchecks(self):
        """«важно» при уже стоящем «Срочно» — добавляет, ничего не снимая."""
        form = self.form(task(urgent=1), hints=True)
        self.retitle(form, "важно сдать отчёт")
        self.assertEqual(self.prio(form), (True, True))

    def test_explicit_already_checked_no_note(self):
        form = self.form(task(urgent=1), hints=True)
        self.retitle(form, "срочно позвонить")
        self.assertEqual(self.prio(form), (True, False))
        self.assertEqual(self.rows(form), [])

    def test_asap_and_both_words(self):
        form = self.form(task(), hints=True)
        self.retitle(form, "asap важно ответить")
        self.assertEqual(self.prio(form), (True, True))
        self.assertIn(("Отметил «Срочно» и «Важно» — так сказано в названии", "Снять"), self.rows(form))

    def test_undo_restores_and_not_marked_again(self):
        form = self.form(task(important=1))
        self.retitle(form, "срочно купить")
        self.assertEqual(self.prio(form), (True, True))
        self.click(form, "Снять")
        self.assertEqual(self.prio(form), (False, True))
        self.assertEqual(form.auto_marked, [False, False])
        self.assertTrue(form.prio_undone)
        self.assertEqual(self.rows(form), [])
        # дальше печатают — снова не отмечаем
        self.retitle(form, "срочно купить хлеб срочно")
        self.assertEqual(self.prio(form), (False, True))
        self.assertEqual(self.rows(form), [])

    def test_save_after_auto_mark(self):
        form = self.form(task("купить подарки", important=1))
        self.retitle(form, "срочно купить подарки")
        dialog = form.master
        form.save()
        self.assertEqual(dialog.result["title"], "срочно купить подарки")
        self.assertTrue(dialog.result["urgent"])
        self.assertTrue(dialog.result["important"])

    # --- случаи из ревью: каждое слово отдельно, стёрли слово — снимаем свою отметку ---

    def test_words_added_one_by_one(self):
        """«срочно позвонить», потом дописали « важно» — отмечены обе галочки."""
        form = self.form(task(), hints=True)
        self.retitle(form, "срочно позвонить")
        self.assertEqual(self.prio(form), (True, False))
        self.retitle(form, "срочно позвонить важно")
        self.assertEqual(self.prio(form), (True, True))
        self.assertIn(("Отметил «Срочно» и «Важно» — так сказано в названии", "Снять"),
                      self.rows(form))

    def test_urgent_already_set_then_important_added(self):
        """«Срочно» стояло само; дописали «важно» — строка только про «Важно»."""
        form = self.form(task(urgent=1), hints=True)
        self.retitle(form, "срочно позвонить")
        self.assertEqual(self.rows(form), [])
        self.retitle(form, "срочно позвонить важно")
        self.assertEqual(self.prio(form), (True, True))
        self.assertIn(("Отметил «Важно» — так сказано в названии", "Снять"), self.rows(form))
        # «Снять» снимает только свою отметку, чужое «Срочно» остаётся
        self.click(form, "Снять")
        self.assertEqual(self.prio(form), (True, False))

    def test_mark_implicit_then_explicit_important(self):
        """Нажали «Отметить» на «критичный…» («Важно»), потом дописали «срочно» — отмечено."""
        form = self.form(task(), hints=True)
        self.retitle(form, "критичный баг")
        self.click(form, "Отметить")
        self.assertEqual(self.prio(form), (False, True))
        self.retitle(form, "критичный баг срочно")
        self.assertEqual(self.prio(form), (True, True))
        self.assertIn(("Отметил «Срочно» — так сказано в названии", "Снять"), self.rows(form))

    def test_implicit_offer_hidden_when_explicit_word(self):
        """В заголовке есть явное слово — совета «Отметить» по словоформам нет."""
        form = self.form(task(), hints=True)
        self.retitle(form, "критичный баг срочно")
        self.assertFalse(any(link == "Отметить" for _, link in self.rows(form)), self.rows(form))
        self.assertEqual(self.prio(form), (True, False))

    def test_word_form_marked_in_form(self):
        """«срочный звонок» — форма слова тоже отмечается сразу; «несрочно» — нет."""
        form = self.form(task(), hints=True)
        self.retitle(form, "срочный звонок")
        self.assertEqual(self.prio(form), (True, False))
        self.assertIn(("Отметил «Срочно» — так сказано в названии", "Снять"), self.rows(form))
        self.retitle(form, "несрочно позвонить, неважно когда")
        self.assertEqual(self.prio(form), (False, False))
        self.assertEqual(self.rows(form), [])

    def test_erased_word_unmarks(self):
        """Стёрли дописанное «срочно» — своя галочка снята, строки нет."""
        form = self.form(task("позвонить"))
        self.retitle(form, "срочно позвонить")
        self.assertEqual(self.prio(form), (True, False))
        self.retitle(form, "позвонить маме")
        self.assertEqual(self.prio(form), (False, False))
        self.assertEqual(self.rows(form), [])

    def test_erased_word_keeps_foreign_mark(self):
        """Стёрли слово, но галочку ставили не мы — не трогаем."""
        form = self.form(task("позвонить", urgent=1))
        self.retitle(form, "срочно позвонить")
        self.retitle(form, "позвонить")
        self.assertEqual(self.prio(form), (True, False))

    def test_back_to_old_title_unmarks_and_not_dirty(self):
        """В правке вернули прежний заголовок — своя отметка снята, изменений нет."""
        form = self.form(task("купить подарки", important=1))
        self.retitle(form, "срочно купить подарки")
        self.assertTrue(form.dirty())
        self.retitle(form, "купить подарки")
        self.assertEqual(self.prio(form), (False, True))
        self.assertEqual(self.rows(form), [])
        self.assertFalse(form.dirty())

    def test_old_word_does_not_block_other_word(self):
        """В прежнем заголовке было «срочно» — дописанное «важно» всё равно отмечается."""
        form = self.form(task("срочно позвонить"))
        self.retitle(form, "срочно позвонить важно")
        self.assertEqual(self.prio(form), (False, True))
        self.assertIn(("Отметил «Важно» — так сказано в названии", "Снять"), self.rows(form))

    def test_after_undo_erasing_word_changes_nothing(self):
        form = self.form(task(), hints=True)
        self.retitle(form, "срочно позвонить")
        self.click(form, "Снять")
        self.retitle(form, "позвонить")
        self.retitle(form, "важно позвонить")
        self.assertEqual(self.prio(form), (False, False))
        self.assertEqual(self.rows(form), [])

    # --- неявные слова и похожие задачи: только ссылка «Отметить» ---

    def test_implicit_word_only_offered(self):
        form = self.form(task(), hints=True)
        self.retitle(form, "обязательные платежи")
        self.assertEqual(self.prio(form), (False, False))
        self.assertIn(("«Важно» — так подсказывают слова в названии", "Отметить"), self.rows(form))
        self.click(form, "Отметить")
        self.assertEqual(self.prio(form), (False, True))

    def test_similar_tasks_only_offered(self):
        history = [row(1, "Отчёт в налоговую за год", urgent=1, important=1),
                   row(2, "Отчёт в налоговую за квартал", urgent=1, important=1)]
        form = self.form(task(), hints=True, history=history)
        self.retitle(form, "Отчёт в налоговую")
        self.assertEqual(self.prio(form), (False, False))
        self.assertTrue(any(link == "Отметить" for _, link in self.rows(form)), self.rows(form))

    # --- выключено ---

    def test_hints_false_nothing(self):
        """Без подсказок набор текста советов не вызывает (update_hints не привязан)."""
        form = self.form(task("срочно позвонить завтра"), hints=False)
        form.title_entry.insert("end", " в 10")
        form.title_entry.event_generate("<KeyRelease>", keysym="0")
        form.update()
        self.assertIsNone(form.hints_job)
        self.assertEqual(self.rows(form), [])
        self.assertEqual(self.prio(form), (False, False))
        self.assertFalse(form.hints_on)

    def test_no_history_hints_off(self):
        def offscreen(window, *args, **kwargs):
            window.geometry(OFFSCREEN)

        with mock.patch.object(self.T, "center_on_screen", offscreen), \
                mock.patch.object(self.T, "bring_to_front"):
            dialog = self.T.TaskDialog(self.root, task("срочно"), STATUSES, hints=True)
        self.dialogs.append(dialog)
        self.assertFalse(dialog.form.hints_on)
        self.assertEqual(self.prio(dialog.form), (False, False))

    def test_empty_title_clears_hints(self):
        form = self.form(task(), hints=True)
        self.retitle(form, "срочно позвонить завтра")
        self.assertTrue(self.rows(form))
        self.retitle(form, "   ")
        self.assertEqual(self.rows(form), [])

    def test_new_task_with_explicit_word_marked_on_open(self):
        """Новая задача (например, из письма) уже с «срочно» в названии — отмечено при открытии."""
        form = self.form(task("срочно ответить клиенту"), hints=True)
        self.assertEqual(self.prio(form), (True, False))


if __name__ == "__main__":
    unittest.main()
