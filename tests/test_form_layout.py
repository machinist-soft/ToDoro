"""Форма задачи: поля под «Описанием» — блоками (TaskForm.layout_fields) — в правой панели шире
TaskForm.WIDE встают в две колонки, в окне TaskDialog — всегда одна; ручка под описанием меняет
его высоту, высота запоминается для следующих форм — отдельно для правой панели и для окна — и в
настройках «desc_lines_panel» / «desc_lines_window» (TodoApp).
Настоящий Tk, окна за краем экрана или прозрачные; данные пользователя не трогаются (пути db —
во временной папке), трей, напоминания, обновления и тур в TodoApp подменены."""

import contextlib
import gc
import shutil
import sqlite3
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db

OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0), (2, "Готово", "#22c55e", 1)]
UNITS = [(1, "Отдел продаж"), (2, "Склад")]
MEMBERS = ["Аня", "Борис"]
TMP = None

NARROW_ALL = ["status", "unit", "initiator", "assignee", "due", "prio", "remind", "repeat"]


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


def task(body=""):
    return {"title": "Отчёт", "body": body, "due_at": None, "remind_before": None, "urgent": 0,
            "important": 0, "status_id": 1, "assignee": None, "initiator": None,
            "unit_id": None, "version": 3}


def noop(*args, **kwargs):
    pass


class FormCase(unittest.TestCase):
    """Общее: окно Tk, восстановление атрибутов класса TaskForm после каждого теста."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("300x200" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()
        cls.line = todoro.tkfont.Font(font=todoro.FONT).metrics("linespace")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        form_cls = self.T.TaskForm
        saved = (form_cls.desc_lines, form_cls.remember_desc)

        def restore():
            form_cls.desc_lines, form_cls.remember_desc = saved

        self.addCleanup(restore)
        form_cls.desc_lines, form_cls.remember_desc = {}, None
        self.top = tk.Toplevel(self.root)
        self.top.geometry("320x900" + OFFSCREEN)
        self.addCleanup(self.close_top)

    def close_top(self):
        with contextlib.suppress(tk.TclError):
            self.top.destroy()
        self.root.update()

    def settle(self, widget=None):
        for _ in range(5):
            (widget or self.root).update()

    def form(self, compact=False, members=None, units=None, width=320, body=""):
        self.top.geometry(f"{width}x900" + OFFSCREEN)
        form = self.T.TaskForm(self.top, task(body), STATUSES, on_save=noop, on_cancel=noop,
                               compact=compact, members=members, units=units)
        form.pack(fill="both", expand=True)
        self.settle()
        return form

    def resize(self, width):
        self.top.geometry(f"{width}x900" + OFFSCREEN)
        self.settle()

    def layout(self, form):
        """{имя блока: (row, column, columnspan)} по grid_info."""
        result = {}
        for name, frame in form.blocks.items():
            info = frame.grid_info()
            result[name] = (int(info["row"]), int(info["column"]), int(info["columnspan"]))
        return result

    def padx(self, frame):
        text = str(frame.grid_info()["padx"]).strip("()").replace(",", " ")
        return [int(x) for x in text.split()]

    def height(self, form):
        return int(form.desc.cget("height"))

    def press(self, form, y=1000):
        form.grip_pressed(SimpleNamespace(y_root=y))

    def move(self, form, y):
        form.grip_moved(SimpleNamespace(y_root=y))

    def release(self, form, y=0):
        form.grip_released(SimpleNamespace(y_root=y))

    def recorder(self):
        """remember_desc, который записывает вызовы (compact, строк) в список."""
        calls = []
        self.T.TaskForm.remember_desc = lambda compact, lines: calls.append((compact, lines))
        return calls


class LayoutTests(FormCase):
    """Расстановка блоков полей в одну и две колонки."""

    def narrow_expected(self, names):
        return {name: (row, 0, 2) for row, name in enumerate(names)}

    def test_blocks_present(self):
        cases = ((None, None, {"status", "due", "prio", "remind", "repeat"}),
                 (None, UNITS, {"status", "unit", "due", "prio", "remind", "repeat"}),
                 (MEMBERS, None, {"status", "initiator", "assignee", "due", "prio", "remind",
                                  "repeat"}),
                 ([], None, {"status", "initiator", "assignee", "due", "prio", "remind",
                             "repeat"}),
                 (MEMBERS, UNITS, set(NARROW_ALL)),
                 (None, [], {"status", "due", "prio", "remind", "repeat"}))
        for members, units, expected in cases:
            with self.subTest(members=members, units=units):
                form = self.form(members=members, units=units)
                self.assertEqual(set(form.blocks), expected)
                form.destroy()

    def test_narrow_order_shared_list(self):
        """Одна колонка: все блоки друг под другом, по порядку, во всю ширину."""
        for compact in (False, True):
            with self.subTest(compact=compact):
                form = self.form(compact=compact, members=MEMBERS, units=UNITS, width=320)
                self.assertFalse(form.wide)
                self.assertEqual(self.layout(form), self.narrow_expected(NARROW_ALL))
                form.destroy()

    def test_narrow_order_personal_list(self):
        form = self.form(compact=True, width=320)
        self.assertFalse(form.wide)
        self.assertEqual(self.layout(form), self.narrow_expected(
            ["status", "due", "prio", "remind", "repeat"]))

    def test_narrow_no_padding(self):
        form = self.form(compact=True, members=MEMBERS, units=UNITS, width=320)
        for name, frame in form.blocks.items():
            with self.subTest(name=name):
                self.assertIn(self.padx(frame), ([0], [0, 0]))

    def test_wide_shared_list(self):
        """Блок без пары («Напоминание») — в левой колонке, на полширины."""
        form = self.form(compact=True, members=MEMBERS, units=UNITS, width=700)
        self.assertTrue(form.wide)
        self.assertEqual(self.layout(form), {
            "status": (0, 0, 1), "unit": (0, 1, 1),
            "initiator": (1, 0, 1), "assignee": (1, 1, 1),
            "remind": (2, 0, 1),
            "due": (3, 0, 1), "prio": (3, 1, 1),
            "repeat": (4, 0, 2)})

    def test_wide_personal_list(self):
        form = self.form(compact=True, width=700)
        self.assertTrue(form.wide)
        self.assertEqual(self.layout(form), {
            "status": (0, 0, 1), "remind": (0, 1, 1),
            "due": (1, 0, 1), "prio": (1, 1, 1),
            "repeat": (2, 0, 2)})

    def test_wide_units_only_and_members_only(self):
        form = self.form(compact=True, units=UNITS, width=700)
        self.assertEqual(self.layout(form), {
            "status": (0, 0, 1), "unit": (0, 1, 1), "remind": (1, 0, 1),
            "due": (2, 0, 1), "prio": (2, 1, 1), "repeat": (3, 0, 2)})
        form.destroy()
        form = self.form(compact=True, members=MEMBERS, width=700)
        self.assertEqual(self.layout(form), {
            "status": (0, 0, 1), "initiator": (0, 1, 1), "assignee": (1, 0, 1),
            "remind": (1, 1, 1), "due": (2, 0, 1), "prio": (2, 1, 1), "repeat": (3, 0, 2)})

    def test_wide_pairs_padding(self):
        """Пары — с отступом между колонками; блок без пары — как левый в паре; без отступа,
        во всю ширину, — только повтор."""
        form = self.form(compact=True, members=MEMBERS, units=UNITS, width=700)
        pad = {n: self.padx(f) for n, f in form.blocks.items()}
        self.assertEqual(pad["status"], [0, 8])
        self.assertEqual(pad["unit"], [8, 0])
        self.assertEqual(pad["due"], [0, 8])
        self.assertEqual(pad["prio"], [8, 0])
        self.assertEqual(pad["remind"], [0, 8])
        self.assertIn(pad["repeat"], ([0], [0, 0]))

    def test_wide_back_to_narrow_resets_single_block(self):
        """Блок без пары после возврата в одну колонку снова во всю ширину и без отступа."""
        form = self.form(compact=True, members=MEMBERS, units=UNITS, width=700)
        self.assertEqual(self.layout(form)["remind"], (2, 0, 1))
        form.layout_fields(False)
        self.assertEqual(self.layout(form), self.narrow_expected(NARROW_ALL))
        self.assertIn(self.padx(form.blocks["remind"]), ([0], [0, 0]))
        self.assertIn(self.padx(form.blocks["status"]), ([0], [0, 0]))

    def test_compact_switches_by_width_both_ways(self):
        form = self.form(compact=True, members=MEMBERS, units=UNITS, width=320)
        self.assertFalse(form.wide)
        self.resize(700)
        self.assertGreaterEqual(form.fields.winfo_width(), self.T.TaskForm.WIDE)
        self.assertTrue(form.wide)
        self.assertEqual(self.layout(form)["unit"], (0, 1, 1))
        self.resize(320)
        self.assertLess(form.fields.winfo_width(), self.T.TaskForm.WIDE)
        self.assertFalse(form.wide)
        self.assertEqual(self.layout(form), self.narrow_expected(NARROW_ALL))
        # блоков в сетке ровно столько, сколько полей, — ничего не задвоилось
        self.assertEqual(len(form.fields.grid_slaves()), len(form.blocks))

    def test_wide_threshold(self):
        """Граница — ровно TaskForm.WIDE пикселей: 439 — одна колонка, 440 — две."""
        form = self.form(compact=True, width=320)
        wide = self.T.TaskForm.WIDE
        form.fields.event_generate("<Configure>", width=wide - 1, height=300)
        self.assertFalse(form.wide)
        form.fields.event_generate("<Configure>", width=wide, height=300)
        self.assertTrue(form.wide)
        form.fields.event_generate("<Configure>", width=wide - 1, height=300)
        self.assertFalse(form.wide)

    def test_dialog_form_always_one_column(self):
        """Форма окна (compact=False) — одна колонка даже в широком окне."""
        form = self.form(compact=False, members=MEMBERS, units=UNITS, width=1200)
        self.assertGreaterEqual(form.fields.winfo_width(), self.T.TaskForm.WIDE)
        self.assertFalse(form.wide)
        self.assertEqual(self.layout(form), self.narrow_expected(NARROW_ALL))
        form.fields.event_generate("<Configure>", width=2000, height=300)
        self.assertFalse(form.wide)

    def test_layout_same_mode_does_nothing(self):
        form = self.form(compact=True, width=320)
        with mock.patch.object(form.blocks["status"], "grid") as grid:
            form.layout_fields(False)
        grid.assert_not_called()

    def test_fields_still_saved_in_wide_mode(self):
        """В две колонки поля работают как раньше: значения доходят до сохранения."""
        saved = []
        self.top.geometry("700x900" + OFFSCREEN)
        form = self.T.TaskForm(self.top, task(), STATUSES, on_save=saved.append, on_cancel=noop,
                               compact=True, members=MEMBERS, units=UNITS)
        form.pack(fill="both", expand=True)
        self.settle()
        self.assertTrue(form.wide)
        form.status.set("Готово")
        form.unit.set("Склад")
        form.assignee.set("Борис")
        form.save()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["status_id"], 2)
        self.assertEqual(saved[0]["unit_id"], 2)
        self.assertEqual(saved[0]["assignee"], "Борис")


class GripTests(FormCase):
    """Ручка под описанием."""

    def test_grip_widget_bound(self):
        form = self.form(compact=True)
        grips = [w for w in form.winfo_children()
                 if isinstance(w, tk.Canvas) and str(w.cget("cursor")) == "sb_v_double_arrow"]
        self.assertEqual(len(grips), 1)
        grip = grips[0]
        for sequence in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>",
                         "<Double-Button-1>"):
            self.assertTrue(grip.bind(sequence), sequence)
        # ручка — сразу под полем описания, до блоков полей
        packed = form.pack_slaves()
        self.assertEqual(packed.index(grip) + 1, packed.index(form.fields))

    def test_default_heights(self):
        form = self.form(compact=False)
        self.assertEqual(self.height(form), 6)
        self.assertIsNone(form.desc_user)
        form.destroy()
        form = self.form(compact=True)
        self.assertEqual(self.height(form), 5)
        self.assertIsNone(form.desc_user)

    def test_drag_down_and_up(self):
        form = self.form(compact=False)
        start = self.height(form)
        self.press(form, 1000)
        self.move(form, 1000 + 3 * self.line)
        self.assertEqual(self.height(form), start + 3)
        self.assertEqual(form.desc_user, start + 3)
        self.move(form, 1000 - 2 * self.line)  # от точки нажатия, а не от прошлого движения
        self.assertEqual(self.height(form), start - 2)
        self.assertEqual(form.desc_user, start - 2)

    def test_less_than_half_line_no_change(self):
        form = self.form(compact=False)
        start = self.height(form)
        self.press(form, 1000)
        self.move(form, 1000 + self.line // 2 - 1)
        self.assertEqual(self.height(form), start)
        self.assertIsNone(form.desc_user, "дрожание мыши на ручке — не выбор высоты")
        self.release(form)
        self.assertEqual(self.T.TaskForm.desc_lines, {})

    def test_limits(self):
        form = self.form(compact=False)
        cls = self.T.TaskForm
        self.press(form, 1000)
        self.move(form, 1000 + 500 * self.line)
        self.assertEqual(self.height(form), cls.DESC_LINES_MAX)
        self.assertEqual(form.desc_user, 60)
        self.move(form, 1000 - 500 * self.line)
        self.assertEqual(self.height(form), cls.DESC_LINES_MIN)
        self.assertEqual(form.desc_user, 2)
        self.move(form, 10 ** 9)  # огромное значение — всё равно не больше 60
        self.assertEqual(self.height(form), 60)

    def test_release_remembers_height(self):
        for compact in (True, False):
            with self.subTest(compact=compact):
                self.T.TaskForm.desc_lines = {}
                calls = self.recorder()
                form = self.form(compact=compact)
                self.press(form, 500)
                self.move(form, 500 + 7 * self.line)
                self.assertEqual(self.T.TaskForm.desc_lines, {},
                                 "до отпускания ничего не запоминается")
                self.assertEqual(calls, [])
                self.release(form)
                lines = form.desc_user
                self.assertEqual(self.T.TaskForm.desc_lines, {compact: lines})
                self.assertEqual(calls, [(compact, lines)])
                form.destroy()

    def test_release_keeps_other_kind(self):
        """Запомнили высоту в окне — высота панели остаётся; прежний словарь не меняется на месте."""
        old = {True: 25}
        self.T.TaskForm.desc_lines = old
        calls = self.recorder()
        form = self.form(compact=False)
        self.press(form, 500)
        self.move(form, 500 + 3 * self.line)
        self.release(form)
        self.assertEqual(self.T.TaskForm.desc_lines, {True: 25, False: 9})
        self.assertEqual(old, {True: 25})
        self.assertEqual(calls, [(False, 9)])

    def test_release_without_change_not_saved(self):
        calls = self.recorder()
        form = self.form(compact=True)
        self.press(form)
        self.release(form)  # нажали и отпустили, не двигая
        self.assertEqual(self.T.TaskForm.desc_lines, {})
        self.assertEqual(calls, [])

    def test_click_with_desc_user_set_not_saved(self):
        """Щелчок по ручке без движения ничего не запоминает, даже если у формы уже есть
        своя высота (другая форма тем временем запомнила другую)."""
        self.T.TaskForm.desc_lines = {False: 12}
        form = self.form(compact=False)
        self.assertEqual(form.desc_user, 12)
        self.T.TaskForm.desc_lines = {False: 20}
        calls = self.recorder()
        self.press(form, 500)
        self.move(form, 500 + 1)  # мышь дрогнула
        self.release(form)
        self.assertEqual(self.T.TaskForm.desc_lines, {False: 20})
        self.assertEqual(calls, [])
        self.assertEqual(self.height(form), 12)

    def test_second_drag_starts_unchanged(self):
        """После настоящего перетаскивания следующий щелчок без движения ничего не сохраняет."""
        calls = self.recorder()
        form = self.form(compact=False)
        self.press(form, 500)
        self.move(form, 500 + 3 * self.line)
        self.release(form)
        self.assertEqual(calls, [(False, 9)])
        self.T.TaskForm.desc_lines = {False: 30}  # другая форма запомнила своё
        self.press(form, 700)
        self.release(form)
        self.assertEqual(calls, [(False, 9)])
        self.assertEqual(self.T.TaskForm.desc_lines, {False: 30})

    def test_drag_away_and_back_counts_as_change(self):
        """Потянули и вернули на место — это выбор высоты: она запоминается."""
        calls = self.recorder()
        form = self.form(compact=False)
        start = self.height(form)
        self.press(form, 500)
        self.move(form, 500 + 2 * self.line)
        self.move(form, 500)
        self.assertEqual(self.height(form), start)
        self.release(form)
        self.assertEqual(calls, [(False, start)])
        self.assertEqual(self.T.TaskForm.desc_lines, {False: start})

    def test_release_without_press(self):
        """Отпускание без нажатия (нажали вне ручки) не падает и ничего не сохраняет."""
        form = self.form(compact=False)
        self.release(form)
        self.assertEqual(self.T.TaskForm.desc_lines, {})

    def test_release_same_as_saved_not_saved_again(self):
        self.T.TaskForm.desc_lines = {False: 12}
        calls = self.recorder()
        form = self.form(compact=False)
        self.assertEqual(self.height(form), 12)
        self.press(form, 500)
        self.move(form, 500 + 2 * self.line)
        self.move(form, 500)  # вернули на место
        self.release(form)
        self.assertEqual(self.T.TaskForm.desc_lines, {False: 12})
        self.assertEqual(calls, [])

    def test_release_without_remember_callback(self):
        """remember_desc не задан (форма вне TodoApp) — высота всё равно запоминается в классе."""
        form = self.form(compact=False)
        self.press(form, 500)
        self.move(form, 500 + self.line * 4)
        self.release(form)
        self.assertEqual(self.T.TaskForm.desc_lines, {False: 10})

    def test_new_form_uses_remembered_height(self):
        """Каждая форма берёт свою высоту: панель — ключ True, окно — False."""
        self.T.TaskForm.desc_lines = {True: 17, False: 11}
        for compact, lines in ((True, 17), (False, 11)):
            with self.subTest(compact=compact):
                form = self.form(compact=compact)
                self.assertEqual(form.desc_user, lines)
                self.assertEqual(self.height(form), lines)
                form.destroy()

    def test_only_other_kind_remembered(self):
        """Запомнена высота только панели — форма окна обычная (6 строк), и наоборот."""
        self.T.TaskForm.desc_lines = {True: 17}
        form = self.form(compact=False)
        self.assertIsNone(form.desc_user)
        self.assertEqual(self.height(form), 6)
        form.destroy()
        self.T.TaskForm.desc_lines = {False: 11}
        form = self.form(compact=True)
        self.assertIsNone(form.desc_user)
        self.assertEqual(self.height(form), 5)

    def test_double_click_without_remembered_no_call(self):
        """Двойной щелчок, когда высота не запомнена, — remember_desc не вызывается."""
        for compact in (True, False):
            with self.subTest(compact=compact):
                self.T.TaskForm.desc_lines = {not compact: 14}
                calls = self.recorder()
                form = self.form(compact=compact)
                form.grip_reset()
                self.assertEqual(calls, [])
                self.assertEqual(self.T.TaskForm.desc_lines, {not compact: 14})
                self.assertEqual(self.height(form), 5 if compact else 6)
                form.destroy()

    def test_double_click_resets_form_outside_panel(self):
        """Форма без панели и окна (on_desc_resize не задан): обычная высота ставится сама."""
        for compact, lines in ((True, 5), (False, 6)):
            with self.subTest(compact=compact):
                self.T.TaskForm.desc_lines = {compact: 30}
                calls = self.recorder()
                form = self.form(compact=compact)
                self.assertEqual(self.height(form), 30)
                form.grip_reset()
                self.assertIsNone(form.desc_user)
                self.assertEqual(self.height(form), lines)
                self.assertEqual(self.T.TaskForm.desc_lines, {})
                self.assertEqual(calls, [(compact, None)])
                form.destroy()

    def test_double_click_without_remember_callback(self):
        self.T.TaskForm.desc_lines = {False: 30}
        form = self.form(compact=False)
        form.grip_reset()  # remember_desc не задан — не падает
        self.assertEqual(self.T.TaskForm.desc_lines, {})

    def test_on_desc_resize_replaces_direct_change(self):
        form = self.form(compact=False)
        got = []
        form.on_desc_resize = got.append
        start = self.height(form)
        self.press(form, 500)
        self.move(form, 500 + 2 * self.line)
        self.move(form, 500 + 2 * self.line + 1)  # та же высота — второй раз не зовётся
        self.assertEqual(got, [start + 2])
        self.assertEqual(self.height(form), start, "высоту ставит on_desc_resize, а не форма")

    def test_real_mouse_events(self):
        """Настоящие события мыши на ручке (event_generate) меняют высоту и запоминают её."""
        calls = self.recorder()
        form = self.form(compact=False)
        grip = next(w for w in form.winfo_children() if isinstance(w, tk.Canvas)
                    and str(w.cget("cursor")) == "sb_v_double_arrow")
        start = self.height(form)
        grip.event_generate("<ButtonPress-1>", x=5, y=2, rootx=5, rooty=100)
        grip.event_generate("<B1-Motion>", x=5, y=2, rootx=5, rooty=100 + 3 * self.line,
                            state=0x100)
        grip.event_generate("<ButtonRelease-1>", x=5, y=2, rootx=5, rooty=100 + 3 * self.line,
                            state=0x100)
        self.assertEqual(self.height(form), start + 3)
        self.assertEqual(calls, [(False, start + 3)])


class SidePanelGripTests(FormCase):
    """Правая панель: высота, выбранная ручкой, держится ровно (и меньше, и больше подгонки);
    без неё поле само занимает свободное место; двойной щелчок по ручке возвращает подгонку."""

    def setUp(self):
        super().setUp()
        self.root.geometry("320x500" + OFFSCREEN)
        self.panel = self.T.SidePanel(self.root, noop, noop, noop, noop, noop, noop, {}, noop)
        self.panel.pack(fill="both", expand=True)
        self.addCleanup(self.panel.destroy)

    def open(self, height):
        self.root.geometry(f"320x{height}" + OFFSCREEN)
        self.settle()
        self.panel.show_form(task(), STATUSES, noop, noop)
        self.settle()
        return self.panel.form

    def test_low_panel_keeps_remembered_height(self):
        """В невысоком окне запомненные 20 строк не урезаются до 5 — форма прокручивается."""
        self.T.TaskForm.desc_lines = {True: 20}
        form = self.open(500)
        self.assertEqual(self.height(form), 20)
        area = form.master.master.master
        self.assertTrue(area.bar.winfo_ismapped(), "форма длиннее панели — нужна прокрутка")

    def test_low_panel_without_remembered_height(self):
        form = self.open(500)
        self.assertEqual(self.height(form), self.T.SidePanel.DESC_MIN_LINES)

    def test_window_height_not_used_in_panel(self):
        """Высота, запомненная в окне TaskDialog, на панель не влияет."""
        self.T.TaskForm.desc_lines = {False: 40}
        form = self.open(500)
        self.assertIsNone(form.desc_user)
        self.assertEqual(self.height(form), self.T.SidePanel.DESC_MIN_LINES)

    def free(self, form):
        area = form.master.master.master
        return area.canvas.winfo_height() - area.inner.winfo_reqheight()

    def test_tall_panel_keeps_remembered_small(self):
        """Запомнили 2 строки, а места много — поле ровно 2 строки, под формой пусто."""
        self.T.TaskForm.desc_lines = {True: 2}
        form = self.open(1000)
        self.assertEqual(self.height(form), 2)
        self.assertGreater(self.free(form), self.line)

    def test_tall_panel_fills_without_remembered(self):
        form = self.open(1000)
        self.assertGreater(self.height(form), self.T.SidePanel.DESC_MIN_LINES)
        self.assertGreaterEqual(self.free(form), 0)
        self.assertLess(self.free(form), self.line)

    def test_shrink_in_tall_panel(self):
        """Ошибка: в высокой панели поле, уменьшенное ручкой, тут же растягивалось обратно.
        Теперь уменьшается и остаётся таким после пересчёта панели."""
        form = self.open(1000)
        big = self.height(form)
        self.assertGreater(big, 8)
        self.press(form, 500)
        self.move(form, 500 - 4 * self.line)
        self.settle()
        self.assertEqual(self.height(form), big - 4)
        self.release(form)
        self.settle()
        self.assertEqual(self.height(form), big - 4)
        self.root.geometry("330x1010" + OFFSCREEN)  # панель пересчитывает высоту описания
        self.settle()
        self.assertEqual(self.height(form), big - 4)
        self.assertGreater(self.free(form), self.line)  # под формой пусто — так и задумано

    def test_double_click_in_panel_restores_fit(self):
        """Двойной щелчок по ручке: поле снова заполняет панель, высота панели забыта
        (высота окна остаётся), remember_desc(True, None)."""
        self.T.TaskForm.desc_lines = {True: 3, False: 9}
        calls = self.recorder()
        form = self.open(1000)
        self.assertEqual(self.height(form), 3)
        form.grip_reset()
        self.settle()
        self.assertIsNone(form.desc_user)
        self.assertGreater(self.height(form), self.T.SidePanel.DESC_MIN_LINES)
        self.assertGreaterEqual(self.free(form), 0)
        self.assertLess(self.free(form), self.line)
        self.assertEqual(self.T.TaskForm.desc_lines, {False: 9})
        self.assertEqual(calls, [(True, None)])

    def test_double_click_after_drag_restores_fit(self):
        """Потянули (ничего не запомнено), затем двойной щелчок — подгонка вернулась,
        remember_desc не вызывается."""
        calls = self.recorder()
        form = self.open(1000)
        fitted = self.height(form)
        self.press(form, 500)
        self.move(form, 500 - 3 * self.line)
        self.settle()
        self.assertEqual(self.height(form), fitted - 3)
        form.grip_reset()
        self.settle()
        self.assertEqual(self.height(form), fitted)
        self.assertEqual(calls, [])
        self.assertEqual(self.T.TaskForm.desc_lines, {})

    def test_drag_in_panel_survives_refit(self):
        form = self.open(500)
        start = self.height(form)
        self.press(form, 500)
        self.move(form, 500 + 10 * self.line)
        self.settle()
        self.assertEqual(self.height(form), start + 10)
        self.root.geometry("330x520" + OFFSCREEN)  # панель пересчитывает высоту описания
        self.settle()
        self.assertEqual(self.height(form), start + 10)

    def test_drag_in_panel_remembered_for_panel_only(self):
        self.T.TaskForm.desc_lines = {False: 9}
        calls = self.recorder()
        form = self.open(500)
        start = self.height(form)
        self.press(form, 500)
        self.move(form, 500 + 10 * self.line)
        self.release(form)
        self.assertEqual(self.T.TaskForm.desc_lines, {True: start + 10, False: 9})
        self.assertEqual(calls, [(True, start + 10)])


class DialogGripTests(FormCase):
    """Окно TaskDialog: ручка вытягивает окно, но не за край экрана."""

    def setUp(self):
        super().setUp()
        self.area = (0, 0, 1920, 3000)
        real_place = self.T.place_window

        def place(window, *args, **kwargs):
            window.attributes("-alpha", 0.0)  # окно показывается, но его не видно
            return real_place(window, *args, **kwargs)

        for p in (mock.patch.object(self.T, "work_area", lambda w: self.area),
                  mock.patch.object(self.T, "place_window", place),
                  mock.patch.object(self.T, "bring_to_front")):
            p.start()
            self.addCleanup(p.stop)
        self.dialogs = []
        self.addCleanup(self.close_dialogs)

    def close_dialogs(self):
        for dialog in self.dialogs:
            with contextlib.suppress(tk.TclError):
                dialog.grab_release()
                dialog.destroy()
        self.root.update()

    def dialog(self, area):
        self.area = area
        dialog = self.T.TaskDialog(self.root, task(), STATUSES, title="Задача",
                                   members=MEMBERS, units=UNITS)
        self.dialogs.append(dialog)
        self.settle(dialog)
        return dialog

    def assert_inside(self, dialog, area):
        _, top, _, height = area
        self.assertLessEqual(dialog.winfo_rooty() + dialog.winfo_height(), top + height,
                             "низ окна ушёл за рабочую область")
        self.assertGreaterEqual(dialog.winfo_y(), top)

    def test_dialog_form_one_column(self):
        dialog = self.dialog((0, 0, 1920, 3000))
        self.assertFalse(dialog.form.wide)
        self.assertEqual(self.layout(dialog.form)["unit"], (1, 0, 2))

    def test_drag_grows_dialog_on_big_screen(self):
        dialog = self.dialog((0, 0, 1920, 3000))
        self.assertEqual(dialog.desc_max, self.T.TaskDialog.DESC_LINES)
        before = dialog.winfo_height()
        self.press(dialog.form, 500)
        self.move(dialog.form, 500 + 10 * self.line)
        self.settle(dialog)
        self.assertEqual(dialog.desc_max, 16)
        self.assertEqual(dialog.desc_lines, 16)
        self.assertEqual(self.height(dialog.form), 16)
        self.assertGreater(dialog.winfo_height(), before)
        self.assert_inside(dialog, self.area)
        # и обратно меньше обычного
        self.move(dialog.form, 500 - 10 * self.line)
        self.settle(dialog)
        self.assertEqual(self.height(dialog.form), 2)
        self.assertLess(dialog.winfo_height(), before)

    def test_drag_to_max_stays_on_screen(self):
        """Потянули до 60 строк на обычном экране — окно не уходит за край, поле ниже."""
        area = (0, 0, 1366, 900)
        dialog = self.dialog(area)
        self.assert_inside(dialog, area)
        self.press(dialog.form, 500)
        self.move(dialog.form, 500 + 500 * self.line)
        self.settle(dialog)
        self.assertEqual(dialog.form.desc_user, 60)
        self.assertLess(self.height(dialog.form), 60)
        self.assertGreaterEqual(self.height(dialog.form), self.T.TaskDialog.MIN_DESC_LINES)
        self.assert_inside(dialog, area)

    def test_remembered_height_used_and_fits_screen(self):
        self.T.TaskForm.desc_lines = {False: 60}
        area = (0, 0, 1366, 900)
        dialog = self.dialog(area)
        self.assertEqual(dialog.desc_max, 60)
        self.assertLess(dialog.desc_lines, 60)
        self.assert_inside(dialog, area)
        # места стало больше — поле вырастает, но не выше запомненного
        self.area = (0, 0, 1920, 4000)
        dialog.keep_on_screen()
        self.settle(dialog)
        self.assertEqual(dialog.desc_lines, 60)
        self.assert_inside(dialog, self.area)

    def test_remembered_small_height(self):
        self.T.TaskForm.desc_lines = {False: 3}
        dialog = self.dialog((0, 0, 1920, 3000))
        self.assertEqual(dialog.desc_max, 3)
        self.assertEqual(self.height(dialog.form), 3)  # место есть, но выше выбранного не растёт

    def test_panel_height_does_not_affect_dialog(self):
        """Высота, выбранная ручкой в правой панели (40 строк), окну не передаётся: окно
        открывается с обычными 6 строками."""
        self.T.TaskForm.desc_lines = {True: 40}
        dialog = self.dialog((0, 0, 1920, 3000))
        self.assertIsNone(dialog.form.desc_user)
        self.assertEqual(dialog.desc_max, self.T.TaskDialog.DESC_LINES)
        self.assertEqual(self.height(dialog.form), self.T.TaskDialog.DESC_LINES)

    def test_double_click_in_dialog_restores_six_lines(self):
        """Двойной щелчок в окне: 6 строк, окно сжимается, высота окна забыта, панели — нет."""
        self.T.TaskForm.desc_lines = {False: 20, True: 7}
        calls = self.recorder()
        dialog = self.dialog((0, 0, 1920, 3000))
        self.assertEqual(self.height(dialog.form), 20)
        before = dialog.winfo_height()
        dialog.form.grip_reset()
        self.settle(dialog)
        self.assertEqual(self.height(dialog.form), self.T.TaskDialog.DESC_LINES)
        self.assertEqual(dialog.desc_max, self.T.TaskDialog.DESC_LINES)
        self.assertEqual(dialog.desc_lines, self.T.TaskDialog.DESC_LINES)
        self.assertLess(dialog.winfo_height(), before)
        self.assertEqual(self.T.TaskForm.desc_lines, {True: 7})
        self.assertEqual(calls, [(False, None)])
        self.assert_inside(dialog, self.area)

    def test_double_click_in_dialog_without_remembered(self):
        calls = self.recorder()
        dialog = self.dialog((0, 0, 1920, 3000))
        dialog.form.grip_reset()
        self.settle(dialog)
        self.assertEqual(self.height(dialog.form), self.T.TaskDialog.DESC_LINES)
        self.assertEqual(calls, [])

    def test_drag_in_dialog_remembered_for_window_only(self):
        self.T.TaskForm.desc_lines = {True: 40}
        calls = self.recorder()
        dialog = self.dialog((0, 0, 1920, 3000))
        self.press(dialog.form, 500)
        self.move(dialog.form, 500 + 4 * self.line)
        self.release(dialog.form)
        self.assertEqual(self.T.TaskForm.desc_lines, {True: 40, False: 10})
        self.assertEqual(calls, [(False, 10)])


def close_root(root):
    """Закрывает окно, сначала отменив его отложенные вызовы (как в test_column_order)."""
    try:
        jobs = root.tk.splitlist(root.tk.call("after", "info"))
    except tk.TclError:
        jobs = ()
    for job in jobs:
        with contextlib.suppress(tk.TclError):
            root.tk.call("after", "cancel", job)
    with contextlib.suppress(tk.TclError):
        root.destroy()


class AppSettingTests(unittest.TestCase):
    """TodoApp читает настройки «desc_lines_panel» / «desc_lines_window» и сохраняет в них
    высоту из ручки — каждую в свою."""

    def setUp(self):
        import todoro
        self.T = todoro
        form_cls = todoro.TaskForm
        saved = (form_cls.desc_lines, form_cls.remember_desc)

        def restore():
            form_cls.desc_lines, form_cls.remember_desc = saved

        self.addCleanup(restore)
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-test-"))
        patches = [
            mock.patch.object(db, "DATA_DIR", self.dir),
            mock.patch.object(db, "DB_PATH", self.dir / "todoro.db"),
            mock.patch.object(db, "LISTS_DIR", self.dir / "lists"),
            mock.patch.object(db, "OLD_DB_PATHS", []),
            mock.patch.object(todoro, "OUTLOOK_FLAG_FILE", self.dir / "from-outlook.flag"),
            mock.patch.object(todoro, "SNIP_FLAG_FILE", self.dir / "from-screen.flag"),
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
        self.roots, self.apps = [], []

    def tearDown(self):
        self.close_apps()
        shutil.rmtree(self.dir, ignore_errors=True)

    def close_apps(self):
        for app in self.apps:
            for conn in set(getattr(app, "list_conns", {}).values()):
                with contextlib.suppress(sqlite3.Error):
                    conn.close()
        for root in self.roots:
            close_root(root)
        self.roots, self.apps = [], []
        gc.collect()

    def make_app(self, **settings):
        conn = db.connect(self.dir / "todoro.db")
        for key, value in settings.items():
            db.set_setting(conn, key, value)
        conn.close()
        root = tk.Tk()
        root.geometry("1200x600" + OFFSCREEN)
        self.roots.append(root)
        app = self.T.TodoApp(root)
        self.apps.append(app)
        for _ in range(3):
            root.update()
            time.sleep(0.01)
        return app

    def fresh(self):
        """Закрыть окно и начать с пустой базой (для нескольких запусков в одном тесте)."""
        self.close_apps()
        (self.dir / "todoro.db").unlink(missing_ok=True)

    def setting(self, app, key):
        return db.get_setting(app.prefs, key, "нет настройки")

    def test_no_setting(self):
        self.T.TaskForm.desc_lines = {True: 33}  # от прошлого окна — сбрасывается
        app = self.make_app()
        self.assertEqual(self.T.TaskForm.desc_lines, {})
        for key in ("desc_lines_panel", "desc_lines_window"):
            self.assertEqual(self.setting(app, key), "нет настройки")  # запуск ничего не пишет

    def test_values(self):
        cases = (("15", 15), ("2", 2), ("60", 60), ("0", 2), ("1", 2), ("61", 60),
                 ("999999999999", 60), ("", None), ("abc", None), ("-5", 2), ("7.5", None),
                 (" 9", 9), ("²", None), ("1e3", None), ("None", None))
        for key, compact in (("desc_lines_panel", True), ("desc_lines_window", False)):
            for saved, expected in cases:
                with self.subTest(key=key, saved=saved):
                    self.fresh()
                    self.T.TaskForm.desc_lines = {}
                    self.make_app(**{key: saved})
                    want = {} if expected is None else {compact: expected}
                    self.assertEqual(self.T.TaskForm.desc_lines, want)

    def test_both_settings_separately(self):
        self.make_app(desc_lines_panel="30", desc_lines_window="abc")
        self.assertEqual(self.T.TaskForm.desc_lines, {True: 30})
        self.fresh()
        self.make_app(desc_lines_panel="30", desc_lines_window="8")
        self.assertEqual(self.T.TaskForm.desc_lines, {True: 30, False: 8})
        self.fresh()
        self.make_app(desc_lines_window="44")
        self.assertEqual(self.T.TaskForm.desc_lines, {False: 44})

    def test_old_setting_ignored(self):
        """Прежняя общая настройка «desc_lines» больше не читается."""
        self.make_app(desc_lines="25")
        self.assertEqual(self.T.TaskForm.desc_lines, {})

    def test_remember_writes_own_setting(self):
        app = self.make_app()
        self.assertTrue(callable(self.T.TaskForm.remember_desc))
        self.T.TaskForm.remember_desc(True, 23)
        self.assertEqual(self.setting(app, "desc_lines_panel"), "23")
        self.assertEqual(self.setting(app, "desc_lines_window"), "нет настройки")
        self.T.TaskForm.remember_desc(False, 9)
        self.assertEqual(self.setting(app, "desc_lines_window"), "9")
        self.assertEqual(self.setting(app, "desc_lines_panel"), "23")
        self.assertEqual(self.setting(app, "desc_lines"), "нет настройки")

    def test_forget_writes_empty_and_skipped_on_start(self):
        """remember_desc(..., None) (двойной щелчок по ручке) пишет пустую строку; при следующем
        запуске такая настройка пропускается."""
        app = self.make_app(desc_lines_panel="23", desc_lines_window="9")
        self.assertEqual(self.T.TaskForm.desc_lines, {True: 23, False: 9})
        self.T.TaskForm.remember_desc(True, None)
        self.assertEqual(self.setting(app, "desc_lines_panel"), "")
        self.assertEqual(self.setting(app, "desc_lines_window"), "9")
        self.close_apps()
        self.make_app()
        self.assertEqual(self.T.TaskForm.desc_lines, {False: 9})

    def test_saved_heights_used_by_forms(self):
        """После перезапуска формы открываются каждая со своей сохранённой высотой."""
        self.make_app(desc_lines_panel="21", desc_lines_window="7")
        for compact, lines in ((True, 21), (False, 7)):
            form = self.T.TaskForm(self.roots[0], task(), STATUSES, on_save=noop, on_cancel=noop,
                                   compact=compact)
            self.assertEqual(int(form.desc.cget("height")), lines)
            form.destroy()


if __name__ == "__main__":
    unittest.main()
