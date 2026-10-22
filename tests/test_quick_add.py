"""Быстрое добавление задачи по месту (GitHub #11) и плашки задач в календаре (GitHub #10):
TodoApp.add(title, place), place_flags, строка «＋ Добавить задачу» (QuickAdd), новая задача
правой кнопкой (new_task_at / new_task_menu), Ctrl+N (quick_add_here) и цвета плашек.
Временные файлы; окна Tk — за краем экрана; ui.*, TaskDialog и меню подменены;
данные пользователя не трогаются."""

import gc
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import tkinter as tk
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import todoro  # noqa: E402
from tests.test_column_order import close_root  # noqa: E402
from tests.test_core import TempDir  # noqa: E402
from tests.test_smart import FakeBanner  # noqa: E402

T = todoro
OFFSCREEN = "+-5000+-5000"
QUADRANT = {q[0]: (q[1], q[2]) for q in T.EisenhowerMatrix.QUADRANTS}  # уровень -> (срочно, важно)


def call_binding(widget, sequence):
    """Вызывает то, что привязано к sequence у виджета, как будто событие случилось.
    event_generate тут не годится: двойной щелчок он не подаёт, а для латинских букв при
    русской раскладке нет кода клавиши."""
    script = widget.bind(sequence)
    found = re.search(r"\[(\S+)((?: %\S)*)\]", script)
    if found is None:
        raise AssertionError(f"к {sequence} ничего не привязано: {script!r}")
    fields = {"%A": "n", "%K": "n", "%W": str(widget), "%d": "", "%T": "2", "%s": "4"}
    return widget.tk.call(found.group(1), *[fields.get(f, "0") for f in found.group(2).split()])


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


# ---------- TodoApp.add(title, place) и place_flags без окна ----------

class PlaceAddTests(TempDir):
    """add() и smart_banner на временной базе: методы берём у TodoApp, рисование — заглушки."""

    def setUp(self):
        super().setUp()
        self.conn = db.connect(self.dir / "list.db")
        # колонки: обычные из новой базы + «Готово» (выполнено)
        self.done_id = next(sid for sid, _, _, done in db.list_statuses(self.conn) if done)
        self.first_id = db.list_statuses(self.conn)[0][0]

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def make_app(self, filter_name="Все", smart_on=True, banner_kind=None, has_action=False):
        test = self

        class App:
            add = T.TodoApp.add
            smart_banner = T.TodoApp.smart_banner
            smart_rows = T.TodoApp.smart_rows
            banner_busy = T.TodoApp.banner_busy
            place_flags = T.TodoApp.place_flags

            def created_by(self):
                return None

            def refresh(self, select_id=None):
                self.refreshed.append(select_id)
                self.all_rows = db.list_tasks(self.conn)

            def finish_editing(self):
                pass

        app = App()
        app.conn, app.smart_on = test.conn, smart_on
        app.statuses = {sid: (name, color, bool(done))
                        for sid, name, color, done in db.list_statuses(test.conn)}
        app.filter = FakeVar(filter_name)
        app.banner = FakeBanner(banner_kind, has_action)
        app.quick_priority = mock.Mock()
        app.all_rows, app.refreshed = [], []
        app.fresh_ids = []  # add() запоминает новые задачи — они первыми (fresh_first)
        return app

    def last(self):
        """(название, срок, срочно, важно, статус, выполнено) последней задачи."""
        t = db.list_tasks(self.conn)[-1]
        return t[1], t[4], t[6], t[7], t[9], t[2]

    # --- place_flags ---

    def test_place_flags(self):
        app = self.make_app()
        self.assertEqual(app.place_flags(None), (None, False, False))
        self.assertEqual(app.place_flags(("status", self.done_id)), (self.done_id, False, False))
        for level, (urgent, important) in QUADRANT.items():
            with self.subTest(level=level):
                self.assertEqual(app.place_flags(("level", level)), (None, urgent, important))
        self.assertEqual(app.place_flags(("day", date(2030, 1, 1))), (None, False, False))

    def test_place_flags_deleted_column(self):
        """Колонку удалили (другой участник), а строка ещё на экране — статус не подставляем."""
        app = self.make_app()
        self.assertEqual(app.place_flags(("status", 9999)), (None, False, False))

    # --- только что добавленные — первыми (fresh_first) ---

    def test_add_remembers_fresh(self):
        app = self.make_app()
        app.add("Первая")
        app.add("Вторая", ("level", 1))
        app.add("Третья", ("status", self.done_id))
        self.assertEqual(app.fresh_ids, [t[0] for t in db.list_tasks(self.conn)])

    def test_empty_title_not_fresh(self):
        app = self.make_app()
        app.add("   ")
        self.assertEqual(app.fresh_ids, [])

    # --- add() в список, колонку, четверть ---

    def test_add_to_list(self):
        app = self.make_app()
        app.add("Купить хлеб")
        self.assertEqual(self.last(), ("Купить хлеб", None, 0, 0, self.first_id, 0))
        self.assertEqual(app.refreshed[-1], db.list_tasks(self.conn)[-1][0])  # новая — выбрана

    def test_add_to_column_gets_its_status(self):
        app = self.make_app()
        other = db.list_statuses(self.conn)[1][0]
        app.add("Позвонить", ("status", other))
        self.assertEqual(self.last()[4:], (other, 0))

    def test_add_to_done_column_is_done_and_filter_switched(self):
        """В колонку «Готово» при фильтре «Активные» — задача выполнена, фильтр → «Все»."""
        app = self.make_app("Активные")
        app.add("Сделано раньше", ("status", self.done_id))
        self.assertEqual(self.last()[4:], (self.done_id, 1))
        self.assertEqual(app.filter.get(), "Все")

    def test_filter_kept_when_task_visible(self):
        for filter_name, place in (("Активные", None), ("Все", None),
                                   ("Выполненные", "done"), ("Все", "done")):
            with self.subTest(filter=filter_name, place=place):
                app = self.make_app(filter_name)
                app.add("Задача", ("status", self.done_id) if place else None)
                self.assertEqual(app.filter.get(), filter_name)

    def test_filter_switched_when_task_hidden(self):
        for filter_name in ("Выполненные", "Просроченные"):
            with self.subTest(filter=filter_name):
                app = self.make_app(filter_name)
                app.add("Задача без срока", ("status", self.first_id))
                self.assertEqual(app.filter.get(), "Все")

    def test_add_to_quadrant_sets_priority(self):
        for level, (urgent, important) in QUADRANT.items():
            with self.subTest(level=level):
                app = self.make_app()
                app.add(f"Дело {level}", ("level", level))
                self.assertEqual(self.last()[2:4], (int(urgent), int(important)))
                self.assertEqual(self.last()[4], self.first_id)

    def test_quadrant_priority_without_smart_hints(self):
        """Умные подсказки выключены или полоса занята — приоритет четверти всё равно ставится."""
        for smart_on, kind in ((False, None), (True, "alert")):
            with self.subTest(smart_on=smart_on, kind=kind):
                app = self.make_app(smart_on=smart_on, banner_kind=kind)
                app.add("Срочно позвонить завтра", ("level", 2))
                title, due, urgent, important, _, _ = self.last()
                self.assertEqual((due, urgent, important), (None, 0, 1))  # «срочно» и срок не поняли
                self.assertEqual(app.banner.shown, [])

    def test_quadrant_mixed_with_urgent_word(self):
        """«Важно, но не срочно» + «срочно» в названии → «Срочно и важно»; «Отменить» — к четверти."""
        app = self.make_app()
        app.add("Срочно сдать отчёт завтра в 10:30", ("level", 2))
        title, due, urgent, important, _, _ = self.last()
        tomorrow = (date.today() + timedelta(1)).strftime("%Y-%m-%d")
        self.assertEqual((due, urgent, important), (tomorrow + " 10:30", 1, 1))
        kind, text, button, undo = app.banner.shown[-1]
        self.assertEqual(button, "Отменить")
        undo()
        title, due, urgent, important, _, _ = self.last()
        self.assertEqual((title, due, urgent, important),
                         ("Срочно сдать отчёт завтра в 10:30", None, 0, 1))  # важность четверти осталась

    def test_undo_in_quadrant_keeps_both_flags(self):
        app = self.make_app()
        app.add("Сдать отчёт завтра", ("level", 1))
        app.banner.shown[-1][3]()
        self.assertEqual(self.last()[1:4], (None, 1, 1))

    def test_undo_in_list_resets_priority(self):
        """Вне матрицы «Отменить» по-прежнему снимает «срочно» из слов названия."""
        app = self.make_app()
        app.add("Срочно позвонить завтра")
        self.assertEqual(self.last()[2:4], (1, 0))
        app.banner.shown[-1][3]()
        self.assertEqual(self.last()[1:4], (None, 0, 0))

    def test_no_priority_advice_in_quadrant(self):
        """В четверти приоритет уже выбран — «Отметить как…» по похожим задачам не предлагаем."""
        for title in ("Отчёт для налоговой", "Отчёт в налоговую"):
            task_id = db.add_task(self.conn, title)
            db.update_task(self.conn, task_id, title, None, None, True, True)
        app = self.make_app()
        app.refresh()
        app.add("Отчёт налоговой", ("level", 3))
        self.assertEqual(self.last()[2:4], (1, 0))
        self.assertNotIn("Отметить", [s[2] for s in app.banner.shown])
        # а в столбце доски совет остаётся
        app = self.make_app()
        app.refresh()
        app.add("Отчёт налоговой", ("status", self.first_id))
        self.assertEqual(app.banner.shown[-1][2], "Отметить")

    def test_quadrant_priority_without_when_still_saved(self):
        """Ни срока, ни слов о приоритете — приоритет четверти всё равно записан (update_task)."""
        app = self.make_app()
        app.add("Купить 2 билета в 3 кассе", ("level", 3))
        self.assertEqual(self.last()[1:4], (None, 1, 0))
        self.assertEqual(app.banner.shown, [])

    def test_add_to_deleted_column_goes_to_first(self):
        app = self.make_app("Активные")
        app.add("Задача", ("status", 9999))
        self.assertEqual(self.last()[4:], (self.first_id, 0))
        self.assertEqual(app.filter.get(), "Активные")

    def test_empty_title_in_place(self):
        app = self.make_app()
        for place in (None, ("status", self.first_id), ("level", 1)):
            app.add("   ", place)
        self.assertEqual(db.list_tasks(self.conn), [])
        self.assertEqual(app.refreshed, [])


# ---------- QuickAdd: строка «＋ Добавить задачу» ----------

class QuickAddWidgetTests(unittest.TestCase):
    """QuickAdd с поддельным app: окно за краем экрана."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("500x300" + OFFSCREEN)
        T.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        close_root(cls.root)

    def setUp(self):
        self.added = []
        self.app = SimpleNamespace(root=self.root, quick_draft=None, smart_rows=lambda: [],
                                   add=lambda title, place: self.added.append((title, place)))
        self.frame = tk.Frame(self.root)
        self.frame.pack(fill="both", expand=True)
        self.place = ("status", 2)

    def tearDown(self):
        self.frame.destroy()
        self.root.update()

    def make(self, place=None):
        quick = T.QuickAdd(self.frame, self.app, self.place if place is None else place, "#ffffff")
        quick.pack(fill="x")
        self.root.update()
        return quick

    def test_closed_at_start(self):
        quick = self.make()
        self.assertIsNone(quick.entry)
        self.assertTrue(quick.link.winfo_ismapped())
        self.assertIn("Добавить задачу", quick.link.cget("text"))
        self.assertEqual(quick.text(), "")

    def test_click_opens(self):
        quick = self.make()
        quick.link.event_generate("<Button-1>", x=3, y=3)
        self.root.update()
        self.assertIsNotNone(quick.entry)
        self.assertFalse(quick.link.winfo_ismapped())
        self.assertEqual(self.app.quick_draft, dict(place=self.place, text="", focus=True))

    def test_open_twice_keeps_one_entry(self):
        quick = self.make()
        quick.open("раз")
        entry = quick.entry
        quick.open("два")
        self.assertIs(quick.entry, entry)
        self.assertEqual(entry.get(), "раз")

    def test_enter_adds_here_and_stays_open(self):
        quick = self.make()
        quick.open()
        quick.entry.insert(0, "  Позвонить маме ")
        self.assertEqual(quick.enter(), "break")
        self.assertEqual(self.added, [("Позвонить маме", self.place)])
        self.assertIsNotNone(quick.entry)
        self.assertEqual(quick.entry.get(), "")
        # черновик: поле открыто и пусто — после перерисовки доски оно откроется снова
        self.assertEqual(self.app.quick_draft, dict(place=self.place, text="", focus=True))
        again = self.make()
        self.assertIsNotNone(again.entry)
        self.assertEqual(again.entry.get(), "")

    def test_enter_empty_adds_nothing(self):
        quick = self.make()
        quick.open("   ")
        quick.enter()
        self.assertEqual(self.added, [])
        self.assertIsNotNone(quick.entry)

    def test_enter_with_chosen_suggestion_does_not_add(self):
        """Enter подставил вариант из списка похожих названий — задачу не добавляем."""
        quick = self.make()
        quick.open("Позв")
        with mock.patch.object(quick.suggest, "accept", return_value=True):
            quick.enter()
        self.assertEqual(self.added, [])
        with mock.patch.object(quick.suggest, "accept", return_value=False):
            quick.enter()
        self.assertEqual(self.added, [("Позв", self.place)])

    def test_close_clears_draft(self):
        quick = self.make()
        quick.open("недописано")
        quick.close()
        self.assertIsNone(quick.entry)
        self.assertIsNone(quick.suggest)
        self.assertIsNone(self.app.quick_draft)
        self.root.update()
        self.assertTrue(quick.link.winfo_ismapped())
        quick.close()  # повторно — без ошибок

    def test_close_keeps_draft_of_other_place(self):
        quick = self.make()
        quick.open()
        other = dict(place=("status", 99), text="чужое", focus=False)
        self.app.quick_draft = other
        quick.close()
        self.assertIs(self.app.quick_draft, other)

    def focus(self, quick):
        quick.entry.focus_force()
        self.root.update()
        self.assertIs(quick.entry.focus_get(), quick.entry, "окно за экраном не получило фокус")

    def test_escape_closes(self):
        quick = self.make()
        quick.open("текст")
        self.focus(quick)
        quick.entry.event_generate("<Escape>")
        self.root.update()
        self.assertIsNone(quick.entry)
        self.assertIsNone(self.app.quick_draft)

    def test_escape_first_closes_suggestions(self):
        """Открыт список похожих названий — первый Esc закрывает только его, поле остаётся."""
        quick = self.make()
        quick.open("Позв")
        self.focus(quick)
        quick.suggest.show(["Позвонить маме"])
        self.assertTrue(quick.suggest.shown())
        quick.entry.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(quick.suggest.shown())
        self.assertIsNotNone(quick.entry)
        quick.entry.event_generate("<Escape>")
        self.root.update()
        self.assertIsNone(quick.entry)

    def test_draft_restored_on_redraw(self):
        self.app.quick_draft = dict(place=self.place, text="недописано", focus=False)
        quick = self.make()
        self.assertIsNotNone(quick.entry)
        self.assertEqual(quick.entry.get(), "недописано")
        self.assertEqual(self.app.quick_draft["focus"], False)  # фокус не забираем
        other = self.make(("status", 3))
        self.assertIsNone(other.entry)  # черновик другой колонки здесь не открывается
        above_list = T.QuickAdd(self.frame, self.app, None, "#ffffff")  # над списком — тоже нет
        self.assertIsNone(above_list.entry)

    def test_list_draft_place_none(self):
        """Над списком place=None: его черновик восстанавливается только в строке списка."""
        self.place = None
        self.app.quick_draft = dict(place=None, text="список", focus=False)
        quick = T.QuickAdd(self.frame, self.app, None, "#ffffff")
        self.assertEqual(quick.entry.get(), "список")
        self.assertIsNone(self.make(("level", 1)).entry)

    def test_typing_remembered(self):
        quick = self.make()
        quick.open()
        self.focus(quick)
        quick.entry.insert(0, "Купить")
        quick.entry.event_generate("<KeyRelease>", keysym="BackSpace")
        self.assertEqual(self.app.quick_draft["text"], "Купить")

    def test_unfocused_empty_closes_with_text_stays(self):
        quick = self.make()
        quick.open("текст")
        with mock.patch.object(quick.entry, "focus_get", return_value=None):
            quick.unfocused()
        self.assertIsNotNone(quick.entry)
        self.assertEqual(self.app.quick_draft, dict(place=self.place, text="текст", focus=False))
        quick.entry.delete(0, "end")
        with mock.patch.object(quick.entry, "focus_get", return_value=None):
            quick.unfocused()
        self.assertIsNone(quick.entry)
        self.assertIsNone(self.app.quick_draft)

    def test_unfocused_while_still_focused_does_nothing(self):
        quick = self.make()
        quick.open()
        with mock.patch.object(quick.entry, "focus_get", return_value=quick.entry):
            quick.unfocused()
        self.assertIsNotNone(quick.entry)

    def test_unfocused_after_redraw_does_nothing(self):
        """Доску перерисовали раньше, чем сработал отложенный FocusOut, — старая строка молчит."""
        quick = self.make()
        quick.open("текст")
        draft = self.app.quick_draft
        quick.destroy()
        quick.unfocused()  # не падает
        self.assertIs(self.app.quick_draft, draft)


# ---------- new_task_at / new_task_menu / lane_menu без окна ----------

class FakeMenu:
    made = []

    def __init__(self):
        self.items = []
        FakeMenu.made.append(self)

    def command(self, label, command, **kw):
        self.items.append((label, command))
        return self

    def separator(self):
        return self

    def submenu(self, label, menu, **kw):
        return self

    def popup(self, root, x, y, right_aligned=False):
        self.shown_at = (x, y)


class FakeDialog:
    result = None
    calls = []

    def __init__(self, root, task, statuses, **kw):
        FakeDialog.calls.append((task, kw))
        self.result = FakeDialog.result


class NewTaskAtTests(TempDir):
    def setUp(self):
        super().setUp()
        self.conn = db.connect(self.dir / "list.db")
        self.statuses = db.list_statuses(self.conn)
        FakeDialog.calls, FakeDialog.result, FakeMenu.made = [], None, []
        self.calls = []
        app = SimpleNamespace(conn=self.conn, filter=FakeVar("Все"))
        app.root = mock.Mock(grab_current=mock.Mock(return_value=None))
        app.statuses = {sid: (n, c, bool(d)) for sid, n, c, d in self.statuses}
        app.place_flags = lambda place: T.TodoApp.place_flags(app, place)
        app.finish_editing = lambda: self.calls.append("finish")
        app.members = lambda: None
        app.current_list = lambda: {"name": "Работа"}
        app.smart_rows = lambda: []
        app.user_name = lambda: "Анна"
        app.created_by = lambda: None
        app.apply_edit = lambda tid, result, refresh=True: self.calls.append(("apply", tid, result))
        app.show_new_tasks = lambda ids: self.calls.append(("show", ids))
        app.new_task_at = lambda place: self.calls.append(("new", place))
        app.lane_menu = lambda sid, x, y: self.calls.append(("lane", sid, x, y))
        self.app = app
        patches = [mock.patch.object(T, "TaskDialog", FakeDialog),
                   mock.patch.object(T, "PopupMenu", FakeMenu),
                   mock.patch.object(T, "swatch", lambda color: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def open_at(self, place):
        T.TodoApp.new_task_at(self.app, place)
        task, kw = FakeDialog.calls[-1]
        return task, kw

    def test_day(self):
        task, kw = self.open_at(("day", date(2030, 3, 10)))
        hh, mm = T.DEFAULT_TIME[0], T.DEFAULT_TIME[1]
        self.assertEqual(task["due_at"], f"2030-03-10 {int(hh):02d}:{int(mm):02d}")
        self.assertEqual((task["urgent"], task["important"], task["status_id"]),
                         (False, False, self.statuses[0][0]))
        self.assertEqual(kw["note"], "Срок — 10.03.2030, в список «Работа».")
        self.assertEqual(kw["title"], "Новая задача")

    def test_status(self):
        second = self.statuses[1][0]
        task, kw = self.open_at(("status", second))
        self.assertEqual((task["status_id"], task["due_at"], task["urgent"], task["important"]),
                         (second, None, False, False))
        self.assertEqual(kw["note"], "В список «Работа».")

    def test_deleted_status_falls_back_to_first(self):
        task, _ = self.open_at(("status", 9999))
        self.assertEqual(task["status_id"], self.statuses[0][0])

    def test_level(self):
        for level, (urgent, important) in QUADRANT.items():
            with self.subTest(level=level):
                task, _ = self.open_at(("level", level))
                self.assertEqual((task["urgent"], task["important"], task["due_at"]),
                                 (urgent, important, None))

    def test_no_place(self):
        task, _ = self.open_at(None)
        self.assertEqual((task["due_at"], task["status_id"]), (None, self.statuses[0][0]))

    def test_cancel_adds_nothing(self):
        self.open_at(("level", 1))
        self.assertEqual(db.list_tasks(self.conn), [])
        self.assertEqual([c for c in self.calls if c != "finish"], [])

    def test_saved_task_added_with_dialog_status(self):
        second = self.statuses[1][0]
        FakeDialog.result = dict(title="Из формы", status_id=second)
        self.open_at(("status", second))
        rows = db.list_tasks(self.conn)
        self.assertEqual((rows[-1][1], rows[-1][9]), ("Из формы", second))
        self.assertEqual(self.calls[-1], ("show", [rows[-1][0]]))

    def test_other_window_open(self):
        self.app.root.grab_current.return_value = object()
        T.TodoApp.new_task_at(self.app, ("level", 1))
        self.assertEqual(FakeDialog.calls, [])

    def test_menu_for_day_and_level(self):
        for place in (("day", date(2030, 3, 10)), ("level", 2)):
            with self.subTest(place=place):
                FakeMenu.made = []
                T.TodoApp.new_task_menu(self.app, place, 10, 20)
                menu = FakeMenu.made[-1]
                self.assertEqual(menu.shown_at, (10, 20))
                self.assertEqual([label for label, _ in menu.items], ["＋  Новая задача…"])
                menu.items[0][1]()
                self.assertEqual(self.calls[-1], ("new", place))

    def test_menu_for_column_is_lane_menu(self):
        T.TodoApp.new_task_menu(self.app, ("status", 3), 5, 6)
        self.assertEqual(self.calls[-1], ("lane", 3, 5, 6))
        self.assertEqual(FakeMenu.made, [])

    def test_lane_menu_first_item_new_task(self):
        sid = self.statuses[1][0]
        T.TodoApp.lane_menu(self.app, sid, 1, 2)
        menu = FakeMenu.made[-1]  # последнее — само меню колонки (до него — подменю цвета)
        self.assertEqual(menu.items[0][0], "＋  Новая задача…")
        menu.items[0][1]()
        self.assertEqual(self.calls[-1], ("new", ("status", sid)))


# ---------- Плашки задач в календаре ----------

STATUSES = [(1, "Новая", "#3b82f6", 0), (2, "Выполнено", "#22c55e", 1)]


def crow(task_id, due, urgent=0, important=0, done=0, title=None):
    return (task_id, title or f"задача {task_id}", done, "2026-01-01 00:00", due, None,
            urgent, important, "", 2 if done else 1)


class CalendarChipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("1000x760" + OFFSCREEN)
        T.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        close_root(cls.root)

    def setUp(self):
        self.calls = []
        app = SimpleNamespace(repeats={}, root=self.root)
        app.select_task = lambda tid: self.calls.append(("select", tid))
        app.clear_selection = lambda: self.calls.append(("clear",))
        app.new_task_at = lambda place: self.calls.append(("new", place))
        app.new_task_menu = lambda place, x, y: self.calls.append(("new menu", place))
        app.edit = lambda: self.calls.append(("edit",))
        app.show_menu_for = lambda tid, x, y: self.calls.append(("menu", tid))
        app.move_due = lambda *a: self.calls.append(("move",) + a)
        self.app = app
        self.view = T.CalendarView(self.root, app)
        self.view.pack(fill="both", expand=True)
        self.view.month = date(2030, 3, 1)

    def tearDown(self):
        if self.view.drag and self.view.drag.get("ghost") is not None:
            self.view.drag["ghost"].destroy()
        self.view.destroy()
        self.root.update()

    def render(self, rows, overdue=()):
        self.view.render(STATUSES, rows, set(overdue))
        self.root.update()

    def chip(self, task_id):
        return self.view.chips[task_id][0]

    def stripe(self, chip):
        return chip.winfo_children()[0]

    def test_quick_adds_empty(self):
        self.assertEqual(self.view.quick_adds, [])

    def test_colors_by_priority(self):
        rows = [crow(1, "2030-03-10 09:00", 1, 1), crow(2, "2030-03-11 09:00", 0, 1),
                crow(3, "2030-03-12 09:00", 1, 0), crow(4, "2030-03-13 09:00", 0, 0)]
        self.render(rows)
        expected = {1: T.CalendarView.LEVEL_COLORS[1], 2: T.CalendarView.LEVEL_COLORS[2],
                    3: T.CalendarView.LEVEL_COLORS[3], 4: T.ACCENT}
        for task_id, color in expected.items():
            with self.subTest(task=task_id):
                chip = self.chip(task_id)
                self.assertEqual(str(self.stripe(chip).cget("bg")), color)
                self.assertEqual(str(chip.cget("bg")), T.tint(color, 0.86))
                self.assertEqual(chip.bg, T.tint(color, 0.86))
                self.assertEqual(str(chip.label.cget("bg")), chip.bg)
                self.assertEqual(str(chip.cget("highlightbackground")), T.tint(color, 0.55))
                self.assertEqual(str(chip.label.cget("fg")), T.TEXT)
                self.assertIn("09:00", chip.label.cget("text"))
                self.assertIn(f"задача {task_id}", chip.label.cget("text"))

    def test_level_colors_match_matrix(self):
        self.assertEqual(set(T.CalendarView.LEVEL_COLORS), {1, 2, 3})
        for level, *_, color in T.EisenhowerMatrix.QUADRANTS[:3]:
            self.assertEqual(T.CalendarView.LEVEL_COLORS[level], color)

    def test_overdue_is_red(self):
        self.render([crow(1, "2030-03-10 09:00", 0, 1)], overdue={1})
        chip = self.chip(1)
        self.assertEqual(str(self.stripe(chip).cget("bg")), T.DANGER)
        self.assertEqual(chip.bg, T.tint(T.DANGER, 0.86))
        self.assertEqual(str(chip.label.cget("fg")), T.DANGER)

    def test_done_is_pale(self):
        self.render([crow(1, "2030-03-10 09:00", 1, 1, done=1)])
        chip = self.chip(1)
        cell = dict(self.view.cells)[date(2030, 3, 10)]
        self.assertEqual(chip.bg, cell.bg)  # без заливки
        self.assertEqual(str(self.stripe(chip).cget("bg")), T.BORDER)
        self.assertEqual(chip.edge, T.BORDER)
        self.assertEqual(str(chip.label.cget("fg")), T.DONE)

    def test_projected_repeat_is_pale(self):
        self.app.repeats = {1: ("day", None, 0)}
        self.render([crow(1, "2030-03-10 09:00", 1, 1)])
        projected = [w for _, cell in self.view.cells for w in cell.winfo_children()
                     if hasattr(w, "label") and T.REPEAT_MARK in str(w.label.cget("text"))]
        self.assertTrue(projected)
        for chip in projected:
            self.assertEqual(str(self.stripe(chip).cget("bg")), T.BORDER)
            self.assertEqual(str(chip.label.cget("fg")), T.DONE)
            self.assertEqual(chip.bg, chip.master.bg)

    def test_selection_and_back(self):
        self.render([crow(1, "2030-03-10 09:00", 1, 0), crow(2, "2030-03-10 10:00")])
        one, two = self.chip(1), self.chip(2)
        self.view.select(1)
        self.assertEqual(str(one.cget("bg")), T.ACCENT_SOFT)
        self.assertEqual(str(one.label.cget("bg")), T.ACCENT_SOFT)
        self.assertEqual(str(one.cget("highlightbackground")), T.ACCENT)
        self.assertEqual(str(self.stripe(one).cget("bg")), T.CalendarView.LEVEL_COLORS[3])  # полоска та же
        self.assertEqual(str(two.cget("bg")), two.bg)  # другая — без выделения
        self.view.select(2)
        self.assertEqual(str(one.cget("bg")), one.bg)
        self.assertEqual(str(one.label.cget("bg")), one.bg)
        self.assertEqual(str(one.cget("highlightbackground")), one.edge)
        self.assertEqual(str(two.cget("highlightbackground")), T.ACCENT)

    def test_selection_survives_redraw(self):
        self.render([crow(1, "2030-03-10 09:00")])
        self.view.select(1)
        self.view.draw()
        self.root.update()
        self.assertEqual(str(self.chip(1).cget("bg")), T.ACCENT_SOFT)

    def test_mouse_on_label_inside_chip(self):
        """Привязки — на всей плашке: правая кнопка и двойной щелчок по надписи и полоске тоже."""
        self.render([crow(1, "2030-03-10 09:00")])
        chip = self.chip(1)
        for part in (chip, chip.label, self.stripe(chip)):
            with self.subTest(part=str(part)):
                self.calls.clear()
                part.event_generate("<Button-3>", x=1, y=1)
                self.assertEqual(self.calls, [("menu", 1)])  # не «новая задача» дня
                call_binding(part, "<Double-Button-1>")
                self.assertEqual(self.calls[1:], [("select", 1), ("edit",)])
                for sequence in ("<Double-Button-1>", "<Button-1>", "<B1-Motion>", "<ButtonRelease-1>"):
                    self.assertNotEqual(part.bind(sequence), "", sequence)

    def test_drag_from_label_moves(self):
        self.render([crow(1, "2030-03-10 09:00", 1, 1, title="Отчёт")])
        chip = self.chip(1)
        start = SimpleNamespace(x_root=chip.label.winfo_rootx() + 5, y_root=chip.label.winfo_rooty() + 5)
        self.view.on_press(start, 1, chip)
        target = dict(self.view.cells)[date(2030, 3, 20)]
        to = SimpleNamespace(x_root=target.winfo_rootx() + target.winfo_width() // 2,
                             y_root=target.winfo_rooty() + target.winfo_height() // 2)
        self.view.on_motion(to)
        ghost = self.view.drag["ghost"]
        texts = [w.cget("text") for w in ghost.winfo_children()[0].winfo_children()]
        self.assertIn(chip.label.cget("text"), texts)  # призрак — с текстом плашки
        self.view.on_release(to)
        self.root.update()
        self.assertEqual([c for c in self.calls if c[0] == "move"],
                         [("move", 1, "2030-03-10 09:00", date(2030, 3, 20))])

    def test_day_double_click_and_right_click(self):
        """Число и пустое место дня: правая кнопка — меню «Новая задача…» этого дня,
        двойной щелчок — сразу окно новой задачи на этот день."""
        self.render([])
        day = date(2030, 3, 15)
        cell = dict(self.view.cells)[day]
        number = cell.winfo_children()[0]
        for widget in (cell, number):
            with self.subTest(widget=str(widget)):
                self.calls.clear()
                widget.event_generate("<Button-3>", x=2, y=2)
                self.assertEqual(self.calls, [("new menu", ("day", day))])
                call_binding(widget, "<Double-Button-1>")
                self.assertEqual(self.calls[-1], ("new", ("day", day)))

    def test_chip_height_fits_constant(self):
        """Плашка с промежутком под ней (pady 2) не выше CHIP — иначе fit() обещает больше
        строк, чем влезает в день, и нижняя плашка обрезается."""
        self.render([crow(1, "2030-03-10 09:00")])
        chip = self.chip(1)
        self.assertLessEqual(chip.winfo_reqheight() + 2, T.CalendarView.CHIP)

    def test_fitted_chips_not_cut(self):
        """Сколько fit() разрешил, столько плашек целиком видно в дне (при разной высоте окна)."""
        try:
            for height in (600, 760, 900, 1000):
                with self.subTest(height=height):
                    self.root.geometry(f"1000x{height}" + OFFSCREEN)
                    self.render([])
                    rows = [crow(i, "2030-03-12 09:00") for i in range(1, self.view.fit() + 1)]
                    self.render(rows)
                    cell = dict(self.view.cells)[date(2030, 3, 12)]
                    last = cell.winfo_children()[-1]
                    self.assertTrue(hasattr(last, "label"))  # без «ещё N…» — все поместились
                    inner = cell.winfo_height() - 2  # рамка подсветки дня — 2 точки
                    self.assertLessEqual(last.winfo_y() + last.winfo_reqheight(), inner,
                                         f"fit={self.view.fit()}, день {cell.winfo_height()} точек")
        finally:
            self.root.geometry("1000x760" + OFFSCREEN)
            self.root.update()


# ---------- Настоящее окно TodoApp: строки в доске и матрице, Ctrl+N ----------

class WindowTestCase(unittest.TestCase):
    """Настоящий TodoApp на временной базе (окно за краем экрана; трей, напоминания,
    обновления, тур и сообщения подменены)."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-test-"))
        saved_desc = (T.TaskForm.desc_lines, T.TaskForm.remember_desc)
        self.addCleanup(lambda: (setattr(T.TaskForm, "desc_lines", saved_desc[0]),
                                 setattr(T.TaskForm, "remember_desc", saved_desc[1])))
        patches = [
            mock.patch.object(db, "DATA_DIR", self.dir),
            mock.patch.object(db, "DB_PATH", self.dir / "todoro.db"),
            mock.patch.object(db, "LISTS_DIR", self.dir / "lists"),
            mock.patch.object(db, "OLD_DB_PATHS", []),
            mock.patch.object(T, "OUTLOOK_FLAG_FILE", self.dir / "from-outlook.flag"),
            mock.patch.object(T, "SNIP_FLAG_FILE", self.dir / "from-screen.flag"),
            mock.patch.dict(T.IMAGES, clear=True),
            mock.patch.object(T, "clean_temp_files", lambda *a, **k: None),
            mock.patch.object(T, "bring_to_front", lambda *a, **k: None),
            mock.patch.object(T.TodoApp, "check_reminders", lambda self: None),
            mock.patch.object(T.TodoApp, "start_tray", lambda self: None),
            mock.patch.object(T.TodoApp, "auto_check_update", lambda self: None),
            mock.patch.object(T.TodoApp, "start_tour", lambda self: None),
            mock.patch.object(T.TodoApp, "watch_changes", lambda self: None),
            mock.patch("os.startfile", create=True),
            mock.patch("subprocess.Popen"),
            mock.patch("urllib.request.urlopen", side_effect=OSError("нет сети в тестах")),
        ]
        for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
                     "askyesnocancel"):
            if hasattr(T.ui, name):
                patches.append(mock.patch.object(T.ui, name, return_value=False))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.root = tk.Tk()
        self.app = T.TodoApp(self.root)
        self.root.deiconify()
        self.root.geometry("1500x800" + OFFSCREEN)
        self.pump(5)

    def tearDown(self):
        for conn in set(getattr(self.app, "list_conns", {}).values()) | {self.app.conn, self.app.prefs}:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        close_root(self.root)
        gc.collect()
        shutil.rmtree(self.dir, ignore_errors=True)

    def pump(self, times=3):
        for _ in range(times):
            self.root.update()
            time.sleep(0.01)

    def show(self, view):
        self.app.view.set(view)
        self.app.switch_view()
        self.pump()

    def tasks(self):
        return db.list_tasks(self.app.conn)

class QuickAddWindowTests(WindowTestCase):
    def test_old_entry_gone_list_has_quick_add(self):
        for name in ("entry", "add_row", "entry_text", "entry_enter", "title_suggest"):
            self.assertFalse(hasattr(self.app, name), name)
        self.assertIsInstance(self.app.list_quick, T.QuickAdd)
        self.assertIsNone(self.app.list_quick.place)
        self.assertIsNone(self.app.quick_draft)

    def test_list_quick_add(self):
        quick = self.app.list_quick
        quick.open()
        quick.entry.insert(0, "Из списка")
        quick.enter()
        self.pump()
        self.assertEqual(self.tasks()[-1][1], "Из списка")
        self.assertIs(self.app.list_quick, quick)
        self.assertIsNotNone(quick.entry)  # поле осталось открытым
        self.assertEqual(self.app.current_id(), self.tasks()[-1][0])

    def test_board_columns_have_quick_adds(self):
        self.show("board")
        board = self.app.board
        self.assertEqual([q.place for q in board.quick_adds],
                         [("status", sid) for sid, *_ in board.lanes])
        second = board.lanes[1][0]
        board.quick_adds[1].open()
        board.quick_adds[1].entry.insert(0, "Во вторую колонку")
        board.quick_adds[1].enter()
        self.pump()
        task = self.tasks()[-1]
        self.assertEqual((task[1], task[9]), ("Во вторую колонку", second))
        # доску перерисовали — поле во второй колонке снова открыто и пусто, в других — закрыто
        quick = self.app.board.quick_adds[1]
        self.assertIsNotNone(quick.entry)
        self.assertEqual(quick.entry.get(), "")
        self.assertIsNone(self.app.board.quick_adds[0].entry)
        self.assertIn(task[0], self.app.board.cards)

    def test_board_done_column_with_active_filter(self):
        self.show("board")
        self.app.filter.set("Активные")
        self.app.refresh()
        self.pump()
        done_id = next(sid for sid, (_, _, done) in self.app.statuses.items() if done)
        index = [sid for sid, *_ in self.app.board.lanes].index(done_id)
        quick = self.app.board.quick_adds[index]
        quick.open("Уже сделано")
        quick.enter()
        self.pump()
        self.assertEqual(self.app.filter.get(), "Все")
        task = self.tasks()[-1]
        self.assertEqual((task[2], task[9]), (1, done_id))
        self.assertIn(task[0], self.app.board.cards)  # видна на доске

    def test_draft_survives_board_redraw(self):
        self.show("board")
        quick = self.app.board.quick_adds[2]
        quick.open()
        quick.entry.insert(0, "недописано")
        quick.remember()
        self.app.refresh()
        self.pump()
        restored = self.app.board.quick_adds[2]
        self.assertIsNot(restored, quick)
        self.assertEqual(restored.entry.get(), "недописано")

    def test_switch_view_drops_draft(self):
        self.show("board")
        self.app.board.quick_adds[0].open("недописано")
        self.show("matrix")
        self.assertIsNone(self.app.quick_draft)
        self.show("board")
        self.assertIsNone(self.app.board.quick_adds[0].entry)

    def test_matrix_quadrants_have_quick_adds(self):
        self.show("matrix")
        matrix = self.app.matrix
        self.assertEqual([q.place for q in matrix.quick_adds],
                         [("level", q[0]) for q in T.EisenhowerMatrix.QUADRANTS])
        quick = matrix.quick_adds[2]  # «Срочно, но не важно»
        quick.open("В третью четверть")
        quick.enter()
        self.pump()
        task = self.tasks()[-1]
        self.assertEqual((task[1], task[6], task[7], task[2]), ("В третью четверть", 1, 0, 0))
        self.assertIn(task[0], self.app.matrix.cards)
        self.assertIsNotNone(self.app.matrix.quick_adds[2].entry)

    def test_ctrl_n(self):
        app = self.app
        app.quick_add_here()
        self.assertIsNotNone(app.list_quick.entry)
        app.list_quick.close()
        for view in ("board", "matrix"):
            with self.subTest(view=view):
                self.show(view)
                app.quick_add_here()
                quick_adds = app.cards_view().quick_adds
                self.assertIsNotNone(quick_adds[0].entry)
                self.assertTrue(all(q.entry is None for q in quick_adds[1:]))
        self.show("calendar")
        with mock.patch.object(app, "new_task_at") as new_task_at:
            app.quick_add_here()
        new_task_at.assert_called_once_with(("day", date.today()))

    def test_ctrl_n_key_bound(self):
        """Ctrl+N (и с Caps Lock — Ctrl+Shift+N) вызывает quick_add_here."""
        for key in ("<Control-n>", "<Control-N>"):
            with self.subTest(key=key), mock.patch.object(self.app, "quick_add_here") as here:
                self.assertEqual(call_binding(self.root, key), "break")
                here.assert_called_once_with()

    def test_tour_quick_add(self):
        self.assertIs(self.app.tour_quick_add(), self.app.list_quick)
        self.show("board")
        self.assertIs(self.app.tour_quick_add(), self.app.board.quick_adds[0])
        self.show("calendar")
        self.assertIs(self.app.tour_quick_add(), self.app.calendar)
        steps = {step[1]: step[0] for step in self.app.tour_steps()}
        self.assertIs(steps["Новая задача"].__func__, T.TodoApp.tour_quick_add)
        self.assertIs(steps["Из письма и со снимка"](), self.app.new_from)

    def test_mail_and_snip_buttons_in_header(self):
        self.assertIs(self.app.mail_button.master, self.app.new_from)
        self.assertIs(self.app.snip_button.master, self.app.new_from)

    def test_right_click_on_empty_lane(self):
        self.show("board")
        with mock.patch.object(self.app, "lane_menu") as lane_menu:
            sid, lane, _ = self.app.board.lanes[0]
            lane.event_generate("<Button-3>", x=3, y=3)
            self.pump(1)
        self.assertEqual(lane_menu.call_args[0][0], sid)

    def test_right_click_on_quadrant(self):
        self.show("matrix")
        with mock.patch.object(self.app, "new_task_menu") as menu:
            level, box, _ = self.app.matrix.lanes[1]
            box.event_generate("<Button-3>", x=3, y=3)
            self.pump(1)
        self.assertEqual(menu.call_args[0][0], ("level", level))

    def test_switch_list_drops_draft(self):
        """Открыли другой список — недописанное в колонке не переносится."""
        self.show("board")
        self.app.board.quick_adds[0].open("недописано")
        self.assertIsNotNone(self.app.quick_draft)
        item = {"id": "second", "name": "Второй", "file": db.new_list_file()}
        db.save_registry(self.app.prefs, db.list_registry(self.app.prefs) + [item])
        self.app.load_lists()
        self.app.switch_list("second")
        self.pump()
        self.assertEqual(self.app.list_id, "second")
        self.assertIsNone(self.app.quick_draft)
        self.assertTrue(all(q.entry is None for q in self.app.board.quick_adds))



# ---------- Только что добавленные задачи — первыми (TodoApp.fresh_first) ----------

def frow(task_id, title=None, done=0, due=None, urgent=0, important=0, status=1):
    """Строка задачи, как из db.list_tasks."""
    return (task_id, title or f"Задача {task_id}", done, "2030-01-01 10:00", due, None,
            urgent, important, "", status)


class FreshFirstTests(unittest.TestCase):
    """fresh_first и sort_rows без окна: методы TodoApp на простом объекте."""

    def make_app(self, fresh_ids=(), mode="По приоритету", column_sort=None):
        app = SimpleNamespace(fresh_ids=list(fresh_ids), sort=FakeVar(mode), column_sort=column_sort,
                              authors={}, assignees={}, unit_names={},
                              marks_order=lambda task_id: 0)
        app.sort_key = lambda row: T.TodoApp.sort_key(app, row)
        return app

    def ids(self, app, rows):
        statuses = [(1, "Сделать", "#000", 0), (2, "Готово", "#000", 1)]
        return [r[0] for r in T.TodoApp.fresh_first(app, T.TodoApp.sort_rows(app, rows, statuses))]

    def rows(self):
        return [frow(1, "Б", due="2030-01-05 10:00", urgent=1, important=1),
                frow(2, "А", due="2030-01-01 10:00"),
                frow(3, "В", urgent=1),
                frow(4, "Г", done=1),
                frow(5, "Д")]

    def test_no_fresh_keeps_order(self):
        app = self.make_app()
        rows = self.rows()
        self.assertIs(T.TodoApp.fresh_first(app, rows), rows)  # без свежих — тот же список
        self.assertEqual(T.TodoApp.fresh_first(self.make_app([5]), []), [])

    def test_one_fresh_first_rest_as_were(self):
        app = self.make_app([5])
        rows = self.rows()
        self.assertEqual([r[0] for r in T.TodoApp.fresh_first(app, rows)], [5, 1, 2, 3, 4])

    def test_several_fresh_newest_on_top(self):
        app = self.make_app([2, 5, 3])
        rows = self.rows()
        self.assertEqual([r[0] for r in T.TodoApp.fresh_first(app, rows)], [3, 5, 2, 1, 4])

    def test_fresh_not_in_rows_ignored(self):
        """Свежую задачу удалили или её скрыл фильтр — остальные на своих местах."""
        app = self.make_app([99, 5, 77])
        self.assertEqual([r[0] for r in T.TodoApp.fresh_first(app, self.rows())], [5, 1, 2, 3, 4])

    def test_with_every_sort(self):
        cases = {"По приоритету": [1, 3, 2, 4], "По сроку": [2, 1, 3, 4],
                 "По порядку добавления": [1, 2, 3, 4]}
        for mode, rest in cases.items():
            with self.subTest(mode=mode):
                self.assertEqual(self.ids(self.make_app([5], mode=mode), self.rows()), [5] + rest)

    def test_sort_without_fresh_unchanged(self):
        self.assertEqual(self.ids(self.make_app(mode="По приоритету"), self.rows()), [1, 3, 2, 5, 4])
        self.assertEqual(self.ids(self.make_app(mode="По сроку"), self.rows()), [2, 1, 3, 5, 4])

    def test_with_column_sort(self):
        for column_sort, rest in ((["title", False], [2, 1, 3, 4]), (["title", True], [4, 3, 1, 2]),
                                  (["due", True], [1, 2, 3, 4]), (["num", True], [4, 3, 2, 1])):
            with self.subTest(column_sort=column_sort):
                app = self.make_app([5], column_sort=column_sort)
                self.assertEqual(self.ids(app, self.rows()), [5] + rest)

    def test_fresh_done_task_first_among_done(self):
        """Выполненные всегда внизу: только что добавленная в «Готово» — первая среди них,
        а не над активными. При сортировке по столбцу — просто первая."""
        ids = self.ids(self.make_app([4]), self.rows())
        self.assertNotEqual(ids[0], 4)
        rows = {r[0]: r for r in self.rows()}
        done = [i for i in ids if rows[i][2]]
        self.assertEqual(done[0], 4)
        self.assertEqual(ids[:ids.index(4)], [i for i in ids if not rows[i][2]])
        self.assertEqual(self.ids(self.make_app([4], column_sort=["title", False]), self.rows())[0], 4)



class FreshWindowTests(WindowTestCase):
    """Только что добавленные — первыми в списке, колонке доски и четверти матрицы;
    строка «＋ Добавить задачу» — под заголовком, над карточками."""

    def make_old(self, title, urgent=False, important=False, status_id=None, due=None):
        """Задача, которая была в списке до открытия окна (не «свежая»)."""
        task_id = db.add_task(self.app.conn, title, status_id=status_id)
        db.update_task(self.app.conn, task_id, title, due, None, urgent, important)
        return task_id

    def tree_ids(self):
        return [int(iid) for iid in self.app.tree.get_children()]

    def lane_ids(self, board, task_id):
        """Задачи колонки (по порядку сверху вниз), в которой стоит карточка task_id."""
        ids = {card: tid for tid, card in board.cards.items()}
        return [ids[w] for w in board.cards[task_id].master.pack_slaves() if w in ids]

    def quadrant_ids(self, matrix, task_id):
        """Задачи четверти по порядку (слева направо, сверху вниз), где стоит карточка task_id."""
        cells = {}
        holder = matrix.cards[task_id].master.master  # карточка → ячейка → сетка карточек
        for tid, card in matrix.cards.items():
            cell = card.master
            if cell.master is holder:
                info = cell.grid_info()
                cells[(int(info["row"]), int(info["column"]))] = tid
        return [cells[key] for key in sorted(cells)]

    def quick_enter(self, quick, title):
        quick.open()  # поле могло остаться открытым после прошлой задачи
        quick.entry.delete(0, "end")
        quick.entry.insert(0, title)
        quick.enter()
        self.pump()
        return self.tasks()[-1][0]

    # --- список ---

    def test_list_new_task_first_despite_priority(self):
        """«По приоритету» новая задача без приоритета всё равно сверху, следующая — ещё выше."""
        self.app.sort.set("По приоритету")
        old = [self.make_old("Важная", True, True), self.make_old("Срочная", True)]
        self.app.refresh()
        first = self.quick_enter(self.app.list_quick, "Новая")
        self.assertEqual(self.app.fresh_ids, [first])
        self.assertEqual(self.tree_ids()[:3], [first] + old)
        second = self.quick_enter(self.app.list_quick, "Ещё новее")
        self.assertEqual(self.tree_ids()[:4], [second, first] + old)

    def test_list_fresh_first_by_due_and_column(self):
        old = [self.make_old("Б со сроком", due="2030-01-01 10:00"), self.make_old("А")]
        self.app.refresh()
        new = self.quick_enter(self.app.list_quick, "Я — новая")
        self.app.sort.set("По сроку")
        self.app.sort_chosen()
        self.pump()
        self.assertEqual(self.tree_ids()[:3], [new] + old)
        self.app.sort_by_column("title")  # по алфавиту «Я» была бы последней
        self.pump()
        self.assertEqual(self.tree_ids()[0], new)
        self.app.sort_by_column("title")  # обратный порядок
        self.pump()
        self.assertEqual(self.tree_ids()[0], new)

    # --- доска и матрица ---

    def test_board_new_task_first_in_lane(self):
        self.show("board")
        second = self.app.board.lanes[1][0]
        old = [self.make_old("Важная", True, True, second), self.make_old("Срочная", True, False, second)]
        self.app.refresh()
        self.pump()
        new = self.quick_enter(self.app.board.quick_adds[1], "Новая в колонке")
        self.assertEqual(self.lane_ids(self.app.board, new), [new] + old)
        newer = self.quick_enter(self.app.board.quick_adds[1], "Ещё новее")
        self.assertEqual(self.lane_ids(self.app.board, new), [newer, new] + old)

    def test_matrix_new_task_first_in_quadrant(self):
        old = [self.make_old(f"Старая {i}", True, True, due=f"2030-01-0{i} 10:00") for i in (1, 2, 3)]
        self.show("matrix")
        new = self.quick_enter(self.app.matrix.quick_adds[0], "Новая в четверти")
        self.assertEqual(self.quadrant_ids(self.app.matrix, new), [new] + old)

    # --- show_new_tasks и смена списка ---

    def test_show_new_tasks_fresh_and_not(self):
        self.app.sort.set("По приоритету")
        top = self.make_old("Важная", True, True)
        plain = self.make_old("Обычная")
        self.app.refresh()
        self.app.show_new_tasks([plain], fresh=False)  # уже была — место прежнее
        self.assertEqual(self.app.fresh_ids, [])
        self.assertEqual(self.tree_ids(), [top, plain])
        self.assertEqual(self.app.current_id(), plain)
        made = self.make_old("Из письма")
        self.app.show_new_tasks([made])
        self.assertEqual(self.app.fresh_ids, [made])
        self.assertEqual(self.tree_ids(), [made, top, plain])
        self.assertEqual(self.app.current_id(), made)
        self.app.show_new_tasks([])  # пусто — ничего
        self.assertEqual(self.app.fresh_ids, [made])

    def test_existing_mail_task_keeps_place(self):
        """Из письма, по которому задача уже есть, «Открыть её?» — «Да»: место прежнее."""
        self.app.sort.set("По приоритету")
        top = self.make_old("Важная", True, True)
        existing = self.make_old("По письму")
        db.set_mail_id(self.app.conn, existing, "mail-1")
        self.app.refresh()
        mail = dict(mail_id="mail-1", title="Письмо", body="", due_at=None, important=False,
                    files=[])
        with mock.patch.object(T.outlook, "read_selected", return_value=[mail]), \
                mock.patch.object(T.outlook, "mark_added", create=True), \
                mock.patch.object(T.ui, "askyesno", return_value=True), \
                mock.patch.object(self.app, "bring_to_front"):
            self.app.from_outlook()
        self.pump()
        self.assertEqual(self.app.fresh_ids, [])
        self.assertEqual(self.tree_ids(), [top, existing])
        self.assertEqual(self.app.current_id(), existing)

    def test_switch_list_drops_fresh(self):
        self.app.sort.set("По приоритету")
        top = self.make_old("Важная", True, True)
        self.app.refresh()
        new = self.quick_enter(self.app.list_quick, "Новая")
        self.assertEqual(self.tree_ids(), [new, top])
        item = {"id": "second", "name": "Второй", "file": db.new_list_file()}
        db.save_registry(self.app.prefs, db.list_registry(self.app.prefs) + [item])
        self.app.load_lists()
        self.app.switch_list("second")
        self.pump()
        self.assertEqual(self.app.fresh_ids, [])
        self.app.switch_list(db.PERSONAL)
        self.pump()
        self.assertEqual(self.tree_ids(), [top, new])  # вернулись — новая на обычном месте

    # --- строка «＋ Добавить задачу» над карточками ---

    def check_order(self, box, quick, name):
        slaves = box.pack_slaves()
        canvas = next(w for w in slaves if isinstance(w, tk.Canvas))
        index = slaves.index(quick)
        self.assertLess(index, slaves.index(canvas))
        head = slaves[index - 1]  # прямо перед строкой — заголовок с названием
        texts = [w.cget("text") for w in head.winfo_children() if isinstance(w, tk.Label)]
        self.assertIn(name, texts)
        self.assertEqual(quick.pack_info()["side"], "top")
        # на экране: строка ниже заголовка и выше карточек, целиком внутри рамки
        self.assertTrue(quick.winfo_ismapped())
        self.assertLessEqual(head.winfo_y() + head.winfo_height(), quick.winfo_y())
        self.assertLessEqual(quick.winfo_y() + quick.winfo_height(), canvas.winfo_y())
        self.assertLessEqual(quick.winfo_y() + quick.winfo_height(), box.winfo_height())

    def test_quick_add_above_cards_in_lane(self):
        first = db.list_statuses(self.app.conn)[0][0]
        for i in range(30):  # карточек больше, чем помещается, — строка всё равно видна
            self.make_old(f"Задача {i}", status_id=first)
        self.show("board")
        self.pump()
        board = self.app.board
        for (status_id, lane, _), quick in zip(board.lanes, board.quick_adds, strict=True):
            with self.subTest(status=status_id):
                self.check_order(lane, quick, self.app.statuses[status_id][0])

    def test_quick_add_above_cards_in_quadrant(self):
        for i in range(30):
            self.make_old(f"Задача {i}", True, True)
        self.show("matrix")
        self.pump()
        matrix = self.app.matrix
        names = {q[0]: q[3] for q in T.EisenhowerMatrix.QUADRANTS}
        for (level, box, _), quick in zip(matrix.lanes, matrix.quick_adds, strict=True):
            with self.subTest(level=level):
                self.check_order(box, quick, names[level])

if __name__ == "__main__":
    unittest.main()
