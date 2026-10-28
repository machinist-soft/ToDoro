"""Оформление описания в окне (GitHub #12): показ в карточке справа (render_rich, TaskCard.show),
поле описания в форме (RichEditor: Ж/К/З, списки, Enter, вставка из Excel, Ctrl+B/I),
горячие клавиши полей (Ctrl+Z/Y/Shift+Z при любой раскладке, своя отмена у однострочных полей,
Ctrl+Backspace/Delete — стереть слово), описание без значков в письме и на карточке доски.
Настоящий Tk, окно за краем экрана; буфер обмена не трогается (clipboard_get подменён);
данные пользователя не трогаются (пути db — во временной папке)."""

import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0), (2, "Готово", "#22c55e", 1)]
TMP = None
T = None
ROOT = None


def setUpModule():
    global TMP, T, ROOT
    TMP = tempfile.mkdtemp()
    tmp = Path(TMP)
    patches = [mock.patch.object(db, "DATA_DIR", tmp),
               mock.patch.object(db, "DB_PATH", tmp / "todoro.db"),
               mock.patch.object(db, "LISTS_DIR", tmp / "lists"),
               mock.patch.object(db, "OLD_DB_PATHS", [])]
    for p in patches:
        p.start()
        unittest.addModuleCleanup(p.stop)
    import todoro
    T = todoro
    ROOT = tk.Tk()
    ROOT.geometry("400x600" + OFFSCREEN)
    todoro.setup_style(ROOT)
    todoro.setup_text_editing(ROOT)
    ROOT.update()


def tearDownModule():
    ROOT.destroy()
    shutil.rmtree(TMP, ignore_errors=True)


def noop(*args, **kwargs):
    pass


def tags_at(widget, index):
    return {t for t in widget.tag_names(index) if t.startswith("rich_")}


class RenderRichTests(unittest.TestCase):
    def setUp(self):
        self.text = tk.Text(ROOT)
        self.text.pack()
        self.addCleanup(self.text.destroy)

    def find(self, word):
        return self.text.search(word, "1.0", "end")

    def test_no_marks_and_styles(self):
        T.render_rich(self.text, "**жирный** *курсив* ~~зачёркнутый~~ **ж *и к***")
        shown = self.text.get("1.0", "end-1c")
        self.assertEqual(shown, "жирный курсив зачёркнутый ж и к")
        self.assertEqual(tags_at(self.text, self.find("жирный")), {"rich_bold"})
        self.assertEqual(tags_at(self.text, self.find("курсив")), {"rich_italic"})
        self.assertEqual(tags_at(self.text, self.find("зачёркнутый")), {"rich_strike"})
        self.assertEqual(tags_at(self.text, "end-2c"), {"rich_bold_italic"})  # «к» в конце

    def test_combined_tag_fonts(self):
        T.render_rich(self.text, "x")
        font = str(self.text.tag_cget("rich_bold_italic_strike", "font"))
        for word in ("bold", "italic", "overstrike"):
            self.assertIn(word, font)

    def test_lists(self):
        T.render_rich(self.text, "- первый\n  - вложенный\n3. третий")
        lines = self.text.get("1.0", "end-1c").split("\n")
        self.assertEqual(lines, ["•\tпервый", "•\tвложенный", "3.\tтретий"])
        self.assertIn("rich_list0", self.text.tag_names("1.0"))
        self.assertIn("rich_list1", self.text.tag_names("2.0"))
        self.assertIn("rich_list0", self.text.tag_names("3.0"))

    def test_deep_list_level_limited(self):
        T.render_rich(self.text, " " * 20 + "- глубоко")
        self.assertIn("rich_list3", self.text.tag_names("1.0"))

    def test_table_is_frame_with_labels(self):
        T.render_rich(self.text, "до\n| **a** | b |\n|---|---|\n| 1 | 2 |\nпосле")
        shown = self.text.get("1.0", "end-1c")
        self.assertNotIn("|", shown)
        self.assertNotIn("---", shown)
        self.assertIn("до", shown)
        self.assertIn("после", shown)
        tables = self.text.winfo_children()
        self.assertEqual(len(tables), 1)
        self.assertIsInstance(tables[0], tk.Frame)
        labels = tables[0].winfo_children()
        self.assertTrue(all(isinstance(l, tk.Label) for l in labels))
        self.assertEqual(sorted(l.cget("text") for l in labels), ["1", "2", "a", "b"])
        self.assertEqual(len(self.text.window_names()), 1)
        cells = {l.cget("text"): l for l in labels}
        self.assertEqual(int(cells["a"].grid_info()["row"]), 0)
        self.assertEqual(int(cells["2"].grid_info()["column"]), 1)
        self.assertEqual(str(cells["a"].cget("font")), str(cells["b"].cget("font")))  # заголовок
        self.assertNotEqual(str(cells["a"].cget("font")), str(cells["1"].cget("font")))

    def test_wheel_bound_on_table(self):
        seen = []
        T.render_rich(self.text, "| a | b |\n| 1 | 2 |", wheel=seen.append)
        label = self.text.winfo_children()[0].winfo_children()[0]
        self.assertTrue(label.bind("<MouseWheel>"))

    def test_plain_text_unchanged(self):
        T.render_rich(self.text, "Просто текст\n\n2 * 3 * 4")
        self.assertEqual(self.text.get("1.0", "end-1c"), "Просто текст\n\n2 * 3 * 4")


class TaskCardTests(unittest.TestCase):
    def setUp(self):
        extras = mock.MagicMock()
        extras.attachments.return_value = []
        extras.comments.return_value = []
        self.card = T.TaskCard(ROOT, noop, noop, noop, noop, noop, extras, noop)
        self.card.pack(fill="both", expand=True)
        self.addCleanup(self.card.destroy)

    def show(self, body, number=1):
        self.card.show(number, "Отчёт", body, "Новая", "#3b82f6", False, False, 4, "", "", "",
                       "01.10.2026")
        ROOT.update()

    def test_body_without_marks(self):
        self.show("**Важно:** сдать\n- пункт")
        self.assertEqual(self.card.body.get("1.0", "end-1c"), "Важно: сдать\n•\tпункт")
        self.assertEqual(str(self.card.body.cget("state")), "disabled")

    def test_second_show_destroys_old_tables(self):
        self.show("| a | b |\n| 1 | 2 |")
        old = self.card.body.winfo_children()
        self.assertEqual(len(old), 1)
        self.show("| x | y |\n| 3 | 4 |", number=2)
        new = self.card.body.winfo_children()
        self.assertEqual(len(new), 1)
        self.assertFalse(old[0].winfo_exists())
        self.assertEqual(sorted(l.cget("text") for l in new[0].winfo_children()), ["3", "4", "x", "y"])

    def test_empty_body_after_table(self):
        self.show("| a | b |\n| 1 | 2 |")
        self.show("", number=2)
        self.assertEqual(self.card.body.winfo_children(), [])
        self.assertIn("Описания нет", self.card.body.get("1.0", "end"))


class EditorCase(unittest.TestCase):
    def setUp(self):
        self.text = tk.Text(ROOT, undo=True)
        self.text.pack()
        self.addCleanup(self.text.destroy)
        self.rich = T.RichEditor(self.text)

    def set(self, value):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)

    def value(self):
        return self.text.get("1.0", "end-1c")

    def select(self, start, end):
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", start, end)

    def selected(self):
        return self.text.get("sel.first", "sel.last")


class ToggleTests(EditorCase):
    def test_wrap_selection(self):
        self.set("один два три")
        self.select("1.5", "1.8")
        self.rich.toggle("bold")
        self.assertEqual(self.value(), "один **два** три")
        self.assertEqual(self.selected(), "два")

    def test_unwrap_when_marks_around_selection(self):
        self.set("один **два** три")
        self.select("1.7", "1.10")
        self.rich.toggle("bold")
        self.assertEqual(self.value(), "один два три")
        self.assertEqual(self.selected(), "два")

    def test_unwrap_when_marks_selected(self):
        self.set("один ~~два~~ три")
        self.select("1.5", "1.12")
        self.rich.toggle("strike")
        self.assertEqual(self.value(), "один два три")
        self.assertEqual(self.selected(), "два")

    def test_italic_wrap_and_unwrap(self):
        self.set("слово")
        self.select("1.0", "1.end")
        self.rich.toggle("italic")
        self.assertEqual(self.value(), "*слово*")
        self.rich.toggle("italic")
        self.assertEqual(self.value(), "слово")

    def test_no_selection_inserts_pair(self):
        self.set("ab")
        self.text.mark_set("insert", "1.1")
        self.rich.toggle("bold")
        self.assertEqual(self.value(), "a****b")
        self.assertEqual(self.text.index("insert"), "1.3")
        self.text.insert("insert", "x")
        self.assertEqual(self.value(), "a**x**b")

    def test_undo_restores(self):
        self.set("слово")
        self.text.edit_reset()
        self.select("1.0", "1.end")
        self.rich.toggle("bold")
        self.text.edit_undo()
        self.assertEqual(self.value(), "слово")

    def test_highlight_after_toggle(self):
        self.set("один два")
        self.select("1.5", "1.8")
        self.rich.toggle("bold")
        self.assertEqual(tags_at(self.text, "1.5"), {"rich_mark"})
        self.assertEqual(tags_at(self.text, "1.7"), {"rich_bold"})


class ListTests(EditorCase):
    def test_bullets_on_several_lines(self):
        self.set("а\n\nб\nв")
        self.select("1.0", "4.1")
        self.rich.toggle_list(False)
        self.assertEqual(self.value(), "- а\n\n- б\n- в")

    def test_remove_bullets(self):
        self.set("- а\n- б")
        self.select("1.0", "2.end")
        self.rich.toggle_list(False)
        self.assertEqual(self.value(), "а\nб")

    def test_numbered(self):
        self.set("а\nб\nв")
        self.select("1.0", "3.end")
        self.rich.toggle_list(True)
        self.assertEqual(self.value(), "1. а\n2. б\n3. в")
        self.select("1.0", "3.end")
        self.rich.toggle_list(True)
        self.assertEqual(self.value(), "а\nб\nв")

    def test_bullets_to_numbers(self):
        self.set("- а\n- б")
        self.select("1.0", "2.end")
        self.rich.toggle_list(True)
        self.assertEqual(self.value(), "1. а\n2. б")

    def test_indent_kept(self):
        self.set("  а")
        self.text.mark_set("insert", "1.1")
        self.rich.toggle_list(False)
        self.assertEqual(self.value(), "  - а")

    def test_cursor_line_only(self):
        self.set("а\nб")
        self.text.mark_set("insert", "2.0")
        self.rich.toggle_list(False)
        self.assertEqual(self.value(), "а\n- б")

    def test_selection_to_next_line_start(self):
        self.set("а\nб")
        self.select("1.0", "2.0")
        self.rich.toggle_list(False)
        self.assertEqual(self.value(), "- а\nб")


class EnterTests(EditorCase):
    def enter_at_end(self, value):
        self.set(value)
        self.text.mark_set("insert", "end-1c")
        self.rich.enter()
        return self.value()

    def test_bullet_continues(self):
        self.assertEqual(self.enter_at_end("- пункт"), "- пункт\n- ")

    def test_indented_bullet_continues(self):
        self.assertEqual(self.enter_at_end("  • пункт"), "  • пункт\n  • ")

    def test_number_increments(self):
        self.assertEqual(self.enter_at_end("9. пункт"), "9. пункт\n10. ")

    def test_empty_item_ends_list(self):
        self.assertEqual(self.enter_at_end("- пункт\n- "), "- пункт\n")

    def test_empty_numbered_item_ends_list(self):
        self.assertEqual(self.enter_at_end("1. пункт\n2. "), "1. пункт\n")

    def test_two_enters_end_list(self):
        """Как пользователь: Enter в пункте, затем Enter в пустом пункте — список закончен."""
        self.set("- пункт")
        self.text.mark_set("insert", "end-1c")
        self.rich.enter()
        self.rich.enter()
        self.assertEqual(self.value(), "- пункт\n")

    def test_plain_line(self):
        self.assertEqual(self.enter_at_end("текст"), "текст\n")

    def test_cursor_inside_marker(self):
        self.set("- пункт")
        self.text.mark_set("insert", "1.0")
        self.rich.enter()
        self.assertEqual(self.value(), "\n- пункт")

    def test_replaces_selection(self):
        self.set("- пункт лишнее")
        self.select("1.7", "1.end")
        self.text.mark_set("insert", "1.end")
        self.rich.enter()
        self.assertEqual(self.value(), "- пункт\n- ")


class PasteTests(EditorCase):
    def clipboard(self, value):
        if isinstance(value, Exception):
            def get():
                raise value
        else:
            def get():
                return value
        self.text.clipboard_get = get  # настоящий буфер обмена не трогаем

    def test_tsv_becomes_table(self):
        self.set("до")
        self.text.mark_set("insert", "1.end")
        self.clipboard("a\tb\r\n1\t2\r\n")
        self.assertEqual(self.rich.paste(), "break")
        self.assertEqual(self.value(), "до\n| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertIn("rich_table", self.text.tag_names("2.0"))

    def test_tsv_in_middle_of_text(self):
        self.set("до после")
        self.text.mark_set("insert", "1.3")
        self.clipboard("a\tb")
        self.rich.paste()
        self.assertEqual(self.value(), "до \n| a | b |\nпосле")

    def test_tsv_into_empty_field(self):
        self.set("")
        self.clipboard("a\tb")
        self.rich.paste()
        self.assertEqual(self.value(), "| a | b |")

    def test_tsv_replaces_selection(self):
        self.set("старое")
        self.select("1.0", "1.end")
        self.text.mark_set("insert", "1.0")
        self.clipboard("a\tb")
        self.rich.paste()
        self.assertEqual(self.value(), "| a | b |")

    def test_plain_text_left_to_tk(self):
        self.set("x")
        self.clipboard("обычный текст")
        self.assertIsNone(self.rich.paste())
        self.assertEqual(self.value(), "x")

    def test_empty_clipboard(self):
        self.set("x")
        self.clipboard(tk.TclError("пусто"))
        self.assertIsNone(self.rich.paste())
        self.assertEqual(self.value(), "x")


class KeyTests(EditorCase):
    def event(self, keycode, state=0x4, keysym="??"):
        return SimpleNamespace(keycode=keycode, state=state, keysym=keysym, widget=self.text)

    def test_ctrl_b_any_layout(self):
        self.set("слово")
        self.select("1.0", "1.end")
        self.assertEqual(self.rich.key(self.event(66, keysym="Cyrillic_i")), "break")
        self.assertEqual(self.value(), "**слово**")

    def test_ctrl_i(self):
        self.set("слово")
        self.select("1.0", "1.end")
        self.assertEqual(self.rich.key(self.event(73, keysym="Cyrillic_sha")), "break")
        self.assertEqual(self.value(), "*слово*")

    def test_with_shift_or_other_key(self):
        self.set("слово")
        self.assertIsNone(self.rich.key(self.event(66, state=0x5)))
        self.assertIsNone(self.rich.key(self.event(67)))
        self.assertEqual(self.value(), "слово")

    def test_instance_binding(self):
        self.assertTrue(self.text.bind("<Control-KeyPress>"))


class HighlightTests(EditorCase):
    def test_marks_and_styles(self):
        self.set("**ж** *к* ~~з~~ 2 * 3")
        self.rich.highlight()
        self.assertEqual(tags_at(self.text, "1.0"), {"rich_mark"})
        self.assertEqual(tags_at(self.text, "1.2"), {"rich_bold"})
        self.assertEqual(tags_at(self.text, "1.7"), {"rich_italic"})
        self.assertEqual(tags_at(self.text, "1.12"), {"rich_strike"})
        self.assertEqual(tags_at(self.text, "1.18"), set())  # «2 * 3» — не курсив

    def test_nested(self):
        self.set("**а *б***")
        self.rich.highlight()
        self.assertEqual(tags_at(self.text, "1.2"), {"rich_bold"})
        self.assertEqual(tags_at(self.text, "1.4"), {"rich_mark"})
        self.assertEqual(tags_at(self.text, "1.5"), {"rich_bold_italic"})

    def test_table_lines(self):
        self.set("текст\n| a | **b** |\n|---|---|")
        self.rich.highlight()
        self.assertEqual(tags_at(self.text, "2.0"), {"rich_table"})
        self.assertEqual(tags_at(self.text, "3.0"), {"rich_table"})
        self.assertEqual(tags_at(self.text, "1.0"), set())

    def test_old_tags_removed(self):
        self.set("**ж**")
        self.rich.highlight()
        self.set("ж")
        self.rich.highlight()
        self.assertEqual(tags_at(self.text, "1.0"), set())

    def test_destroyed_widget(self):
        self.text.destroy()
        self.rich.highlight()  # не падает


class TaskFormTests(unittest.TestCase):
    def setUp(self):
        form_cls = T.TaskForm
        saved = (form_cls.desc_lines, form_cls.remember_desc)
        self.addCleanup(lambda: setattr(form_cls, "desc_lines", saved[0]))
        self.addCleanup(lambda: setattr(form_cls, "remember_desc", saved[1]))
        self.top = tk.Toplevel(ROOT)
        self.top.geometry("360x900" + OFFSCREEN)
        self.addCleanup(self.top.destroy)
        task = {"title": "Отчёт", "body": "**жирный** текст\n- пункт", "due_at": None,
                "remind_before": None, "urgent": 0, "important": 0, "status_id": 1,
                "assignee": None, "initiator": None, "unit_id": None, "version": 3}
        self.form = T.TaskForm(self.top, task, STATUSES, on_save=noop, on_cancel=noop)
        self.form.pack(fill="both", expand=True)
        ROOT.update()

    def test_body_kept_with_marks_and_highlighted(self):
        self.assertEqual(self.form.desc.get("1.0", "end-1c"), "**жирный** текст\n- пункт")
        self.assertEqual(tags_at(self.form.desc, "1.0"), {"rich_mark"})
        self.assertEqual(tags_at(self.form.desc, "1.3"), {"rich_bold"})

    def test_enter_continues_list(self):
        self.form.desc.mark_set("insert", "end-1c")
        self.form.desc.focus_force()
        ROOT.update()
        self.form.desc.event_generate("<Return>")
        self.assertEqual(self.form.desc.get("1.0", "end-1c"), "**жирный** текст\n- пункт\n- ")

    def test_use_steps_highlights(self):
        self.form.use_steps("*к*")
        self.assertEqual(tags_at(self.form.desc, "1.1"), {"rich_italic"})

    def test_toolbar_has_buttons(self):
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    texts.append(child.cget("text"))
                walk(child)
        walk(self.form)
        for label in ("Ж", "К", "З", "•", "1."):
            self.assertIn(label, texts)


class EditShortcutTests(unittest.TestCase):
    """Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z — по физической клавише (keycode) при любой раскладке."""

    def setUp(self):
        self.widget = mock.MagicMock()

    def press(self, keycode, keysym, state=0x4):
        return T.edit_shortcut(SimpleNamespace(keycode=keycode, keysym=keysym, state=state,
                                               widget=self.widget))

    def test_undo_russian_layout(self):
        self.assertEqual(self.press(90, "Cyrillic_ya"), "break")
        self.widget.event_generate.assert_called_once_with("<<Undo>>")

    def test_undo_english_layout_too(self):
        self.assertEqual(self.press(90, "z"), "break")
        self.widget.event_generate.assert_called_once_with("<<Undo>>")

    def test_redo_ctrl_y(self):
        self.assertEqual(self.press(89, "Cyrillic_en"), "break")
        self.widget.event_generate.assert_called_once_with("<<Redo>>")

    def test_redo_ctrl_shift_z(self):
        self.assertEqual(self.press(90, "Cyrillic_YA", state=0x5), "break")
        self.widget.event_generate.assert_called_once_with("<<Redo>>")

    def test_paste_russian_layout_still_works(self):
        self.assertEqual(self.press(86, "Cyrillic_em"), "break")
        self.widget.event_generate.assert_called_once_with("<<Paste>>")

    def test_paste_english_layout_left_to_tk(self):
        self.assertIsNone(self.press(86, "v"))
        self.widget.event_generate.assert_not_called()

    def test_other_key(self):
        self.assertIsNone(self.press(70, "Cyrillic_a"))


class EntryUndoTests(unittest.TestCase):
    def setUp(self):
        self.entry = ttk.Entry(ROOT)
        self.entry.pack()
        self.addCleanup(self.entry.destroy)

    def type(self, value):
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
        T.entry_remember(self.entry)

    def ev(self):
        return SimpleNamespace(widget=self.entry)

    def test_undo_redo_chain(self):
        T.entry_remember(self.entry)  # пустое — начало истории
        self.type("a")
        self.type("ab")
        self.type("abc")
        T.entry_undo(self.ev())
        self.assertEqual(self.entry.get(), "ab")
        T.entry_undo(self.ev())
        self.assertEqual(self.entry.get(), "a")
        T.entry_undo(self.ev())
        self.assertEqual(self.entry.get(), "")
        self.assertEqual(T.entry_undo(self.ev()), "break")  # дальше некуда
        self.assertEqual(self.entry.get(), "")
        T.entry_undo(self.ev(), step=1)
        T.entry_undo(self.ev(), step=1)
        self.assertEqual(self.entry.get(), "ab")
        T.entry_undo(self.ev(), step=1)
        T.entry_undo(self.ev(), step=1)
        self.assertEqual(self.entry.get(), "abc")

    def test_new_typing_after_undo_drops_redo(self):
        T.entry_remember(self.entry)
        self.type("a")
        self.type("ab")
        T.entry_undo(self.ev())
        self.type("ax")
        T.entry_undo(self.ev(), step=1)
        self.assertEqual(self.entry.get(), "ax")
        T.entry_undo(self.ev())
        self.assertEqual(self.entry.get(), "a")

    def test_unsaved_typing_can_be_undone_and_redone(self):
        """Набранное перед Ctrl+Z (ещё не запомненное) — отменяется и возвращается."""
        T.entry_remember(self.entry)
        self.entry.insert(0, "новое")
        T.entry_undo(self.ev())
        self.assertEqual(self.entry.get(), "")
        T.entry_undo(self.ev(), step=1)
        self.assertEqual(self.entry.get(), "новое")

    def test_virtual_events_bound(self):
        T.entry_remember(self.entry)
        self.type("один")
        self.entry.event_generate("<<Undo>>")
        self.assertEqual(self.entry.get(), "")
        self.entry.event_generate("<<Redo>>")
        self.assertEqual(self.entry.get(), "один")

    def test_history_size_limited(self):
        for i in range(T.ENTRY_HISTORY_SIZE + 50):
            self.type(str(i))
        states, pos = T.ENTRY_HISTORY[str(self.entry)]
        self.assertEqual(len(states), T.ENTRY_HISTORY_SIZE)
        self.assertEqual(pos, len(states) - 1)
        T.entry_undo(self.ev())
        self.assertEqual(self.entry.get(), str(T.ENTRY_HISTORY_SIZE + 48))

    def test_readonly_not_changed(self):
        T.entry_remember(self.entry)
        self.type("x")
        self.entry.state(["readonly"])
        self.assertEqual(T.entry_undo(self.ev()), "break")
        self.assertEqual(self.entry.get(), "x")

    def test_destroy_cleans_history(self):
        entry = tk.Entry(ROOT)
        T.entry_remember(entry)
        name = str(entry)
        self.assertIn(name, T.ENTRY_HISTORY)
        entry.destroy()
        self.assertNotIn(name, T.ENTRY_HISTORY)

    def test_remember_closed_entry(self):
        entry = tk.Entry(ROOT)
        entry.destroy()
        T.entry_remember(entry)  # не падает


class WordSizeTests(unittest.TestCase):
    def test_backward(self):
        self.assertEqual(T.word_size("один два", False), 3)
        self.assertEqual(T.word_size("один два  ", False), 5)
        self.assertEqual(T.word_size("слово...", False), 3)

    def test_forward(self):
        self.assertEqual(T.word_size("один два", True), 4)
        self.assertEqual(T.word_size("  два", True), 5)
        self.assertEqual(T.word_size("!!! два", True), 3)

    def test_empty_and_spaces(self):
        self.assertEqual(T.word_size("", True), 0)
        self.assertEqual(T.word_size("", False), 0)
        self.assertEqual(T.word_size("   ", True), 3)


class DeleteWordTests(unittest.TestCase):
    def ev(self, widget):
        return SimpleNamespace(widget=widget)

    def entry(self, value, cursor):
        entry = tk.Entry(ROOT)
        entry.pack()
        self.addCleanup(entry.destroy)
        entry.insert(0, value)
        entry.icursor(cursor)
        return entry

    def text(self, value, cursor):
        text = tk.Text(ROOT)
        text.pack()
        self.addCleanup(text.destroy)
        text.insert("1.0", value)
        text.mark_set("insert", cursor)
        return text

    def test_entry_backward(self):
        entry = self.entry("один два три", 8)
        self.assertEqual(T.delete_word(self.ev(entry)), "break")
        self.assertEqual(entry.get(), "один  три")

    def test_entry_forward(self):
        entry = self.entry("один два три", 4)
        T.delete_word(self.ev(entry), forward=True)
        self.assertEqual(entry.get(), "один три")

    def test_entry_at_edges(self):
        entry = self.entry("слово", 0)
        T.delete_word(self.ev(entry))
        self.assertEqual(entry.get(), "слово")
        entry.icursor("end")
        T.delete_word(self.ev(entry), forward=True)
        self.assertEqual(entry.get(), "слово")

    def test_entry_selection(self):
        entry = self.entry("один два три", 0)
        entry.select_range(5, 8)
        T.delete_word(self.ev(entry))
        self.assertEqual(entry.get(), "один  три")

    def test_entry_readonly(self):
        entry = self.entry("один", 4)
        entry.configure(state="readonly")
        T.delete_word(self.ev(entry))
        self.assertEqual(entry.get(), "один")

    def test_text_backward(self):
        text = self.text("один два\nтри", "1.8")
        T.delete_word(self.ev(text))
        self.assertEqual(text.get("1.0", "end-1c"), "один \nтри")

    def test_text_forward(self):
        text = self.text("один два\nтри", "1.0")
        T.delete_word(self.ev(text), forward=True)
        self.assertEqual(text.get("1.0", "end-1c"), " два\nтри")

    def test_text_line_start_joins_lines(self):
        text = self.text("один\nдва", "2.0")
        T.delete_word(self.ev(text))
        self.assertEqual(text.get("1.0", "end-1c"), "одиндва")

    def test_text_line_end_joins_lines(self):
        text = self.text("один\nдва", "1.end")
        T.delete_word(self.ev(text), forward=True)
        self.assertEqual(text.get("1.0", "end-1c"), "одиндва")

    def test_text_selection(self):
        text = self.text("один два три", "1.0")
        text.tag_add("sel", "1.4", "1.8")
        T.delete_word(self.ev(text))
        self.assertEqual(text.get("1.0", "end-1c"), "один три")

    def test_text_disabled(self):
        text = self.text("один", "1.4")
        text.configure(state="disabled")
        T.delete_word(self.ev(text))
        self.assertEqual(text.get("1.0", "end-1c"), "один")

    def test_class_bindings(self):
        for cls in ("Entry", "TEntry", "Text"):
            self.assertTrue(ROOT.bind_class(cls, "<Control-BackSpace>"), cls)
            self.assertTrue(ROOT.bind_class(cls, "<Control-Delete>"), cls)


class PlainOutsideTests(unittest.TestCase):
    def test_email_body_without_marks(self):
        body = "**Важно:** *сегодня*\n- пункт\n| a | b |\n|---|---|\n| 1 | 2 |"
        _, text = T.build_email(5, "Отчёт", "Новая", "", "", "", "16.10", False, body)
        self.assertIn("Описание:\nВажно: сегодня\n• пункт\na  b\n1  2\n", text.replace("\r\n", "\n"))
        self.assertNotIn("**", text)
        self.assertNotIn("|", text)

    def test_email_without_body(self):
        _, text = T.build_email(5, "Отчёт", "Новая", "", "", "", "16.10", False, "  ")
        self.assertNotIn("Описание:", text)

    def test_board_card_preview_without_marks(self):
        parent = tk.Frame(ROOT)
        self.addCleanup(parent.destroy)
        board = SimpleNamespace(
            app=SimpleNamespace(card_fields={"body"}, task_mark=lambda task_id: "",
                                assignees={}, unit_names={}, authors={}),
            show_priority=False, card_width=300, cards={}, set_mark=noop,
            on_press=noop, on_motion=noop, on_release=noop, card_tag="CardTest")
        row = (7, "Отчёт", 0, "01.10.2026", None, None, 0, 0, "**Важно:** ~~не~~ сдать\n- пункт", None)
        T.KanbanBoard.make_card(board, parent, row, "#3b82f6", False)
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    texts.append(child.cget("text"))
                walk(child)
        walk(board.cards[7])
        self.assertIn("Важно: не сдать • пункт", texts)
        self.assertFalse(any("**" in t or "~~" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
