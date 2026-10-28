"""Быстрая доска и матрица: события карточек одной подпиской на метку (tag_tree,
setup_card_events, owner, card_id, wheel), не больше DONE_SHOWN выполненных в колонке/четверти
(visible_rows, «Показать остальные выполненные», expand), db.done_times.
Временные файлы; окна Tk — за краем экрана; ui.*, правка задачи и меню подменены;
данные пользователя не трогаются."""

import re
import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from tests.test_core import TempDir  # noqa: E402
from tests.test_quick_add import T, WindowTestCase  # noqa: E402

SHOWN = T.KanbanBoard.DONE_SHOWN


def row(task_id, done=0):
    """Строка задачи как в list_tasks: (id, название, выполнена, ..., статус)."""
    return (task_id, f"Задача {task_id}", done, "01.10.2026", None, None, 0, 0, "", 1)


def fake_board(list_id=None, times=None, selected=None, query=""):
    """Объект с полями, которые нужны KanbanBoard.visible_rows."""
    return SimpleNamespace(DONE_SHOWN=SHOWN, expanded=set(), expanded_list=None, selected_id=selected,
                           app=SimpleNamespace(list_id=list_id, done_times=times or {},
                                               search_query=query))


def labels(widget):
    """Все метки внутри виджета."""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            found.append(child)
        found.extend(labels(child))
    return found


def call_class(widget, tag, sequence):
    """Вызывает то, что привязано к метке tag, как будто событие случилось над widget
    (двойной щелчок event_generate не подаёт)."""
    script = widget.bind_class(tag, sequence)
    found = re.search(r"\[(\S+)((?: %\S)*)\]", script)
    if found is None:
        raise AssertionError(f"к {sequence} у {tag} ничего не привязано: {script!r}")
    fields = {"%W": str(widget), "%d": "", "%T": "4", "%A": "", "%K": "", "%s": "0"}
    return widget.tk.call(found.group(1), *[fields.get(f, "0") for f in found.group(2).split()])


# ---------- visible_rows без окна ----------

class VisibleRowsTests(unittest.TestCase):
    def visible(self, board, key, rows):
        return T.KanbanBoard.visible_rows(board, key, rows)

    def test_few_done_all_shown(self):
        rows = [row(i, done=1) for i in range(1, SHOWN + 1)] + [row(100)]
        self.assertEqual(self.visible(fake_board(), 1, rows), (rows, 0))

    def test_empty(self):
        self.assertEqual(self.visible(fake_board(), 1, []), ([], 0))

    def test_only_freshest_done_and_all_active(self):
        """Выполненных больше 30 — показываются 30 самых свежих по done_at, невыполненные —
        все, порядок показа прежний."""
        done = [row(i, done=1) for i in range(1, 41)]
        active = [row(i) for i in range(41, 141)]
        # самые свежие — с меньшими id (чтобы не совпало с сортировкой по id)
        times = {i: f"2026-10-{28 - i // 2:02d} 10:{60 - i:02d}" for i in range(1, 41)}
        rows = []
        for a, d in zip(active, done):  # вперемешку
            rows += [d, a]
        rows += active[len(done):]
        shown, hidden = self.visible(fake_board(times=times), 1, rows)
        self.assertEqual(hidden, 10)
        self.assertEqual({r[0] for r in shown if r[2]}, set(range(1, 31)))
        self.assertEqual([r for r in shown if not r[2]], active)
        self.assertEqual(shown, [r for r in rows if r in shown])  # порядок не изменился

    def test_old_tasks_without_done_at(self):
        """У задач из старых версий done_at нет (None) — они «старше» всех, между собой — по id."""
        rows = [row(i, done=1) for i in range(1, 36)]
        times = {i: None for i in range(1, 36)}
        times[1] = "2026-10-01 09:00"
        shown, hidden = self.visible(fake_board(times=times), 1, rows)
        self.assertEqual(hidden, 5)
        self.assertEqual({r[0] for r in shown}, {1} | set(range(7, 36)))

    def test_selected_old_done_task_stays_visible(self):
        """Выбранная задача (например, выбрали в списке и перешли на доску) видна, даже если
        она не из 30 самых свежих."""
        rows = [row(i, done=1) for i in range(1, 41)]
        times = {i: f"2026-10-01 10:{i:02d}" for i in range(1, 41)}  # id 1 — самая старая
        shown, hidden = self.visible(fake_board(times=times, selected=1), 1, rows)
        self.assertIn(1, [r[0] for r in shown])
        self.assertEqual((len(shown), hidden), (SHOWN + 1, 40 - SHOWN - 1))

    def test_search_shows_all_found(self):
        """При поиске показывается всё найденное: иначе нашлось бы, но спряталось."""
        rows = [row(i, done=1) for i in range(1, 41)]
        self.assertEqual(self.visible(fake_board(query="задача"), 1, rows), (rows, 0))

    def test_done_times_missing_ids(self):
        """В done_times нет задачи (не успели обновить) — не падает."""
        rows = [row(i, done=1) for i in range(1, 33)]
        shown, hidden = self.visible(fake_board(times={}), 1, rows)
        self.assertEqual((len(shown), hidden), (SHOWN, 2))
        self.assertEqual({r[0] for r in shown}, set(range(3, 33)))

    def test_expanded_shows_all_until_list_changes(self):
        rows = [row(i, done=1) for i in range(1, 41)]
        board = fake_board(list_id="a")
        self.assertEqual(self.visible(board, 1, rows)[1], 10)
        board.expanded.add(1)
        self.assertEqual(self.visible(board, 1, rows), (rows, 0))
        self.assertEqual(self.visible(board, 2, rows)[1], 10)  # другая колонка не раскрыта
        board.app.list_id = "b"
        self.assertEqual(self.visible(board, 1, rows)[1], 10)
        self.assertEqual(board.expanded, set())
        self.assertEqual(board.expanded_list, "b")


class DoneTimesTests(TempDir):
    def test_done_times(self):
        conn = db.connect(self.dir / "list.db")
        try:
            a, b, c = (db.add_task(conn, t) for t in ("а", "б", "в"))
            db.set_done(conn, a, True)
            db.set_done(conn, c, True)
            with conn:
                conn.execute("UPDATE tasks SET done_at = NULL WHERE id = ?", (c,))
            times = db.done_times(conn)
            self.assertEqual(set(times), {a, c})
            self.assertTrue(times[a])
            self.assertIsNone(times[c])
            db.set_done(conn, a, False)
            self.assertEqual(set(db.done_times(conn)), {c})
        finally:
            conn.close()

    def test_done_times_empty(self):
        conn = db.connect(self.dir / "list.db")
        try:
            self.assertEqual(db.done_times(conn), {})
        finally:
            conn.close()


# ---------- настоящее окно ----------

class BoardWindowTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.conn = self.app.conn
        self.done_status = next(sid for sid, (_, _, done) in self.app.statuses.items() if done)
        self.first_status = next(sid for sid, (_, _, done) in self.app.statuses.items() if not done)

    def add(self, title, urgent=0, important=0, due=None):
        tid = db.add_task(self.conn, title)
        with self.conn:
            self.conn.execute("UPDATE tasks SET urgent = ?, important = ?, due_at = ? WHERE id = ?",
                              (urgent, important, due, tid))
        return tid

    def add_done(self, count, urgent=0, important=0):
        """count выполненных; done_at растёт с номером — самые свежие последние."""
        ids = []
        for n in range(count):
            tid = self.add(f"Сделано {n}", urgent, important)
            db.set_done(self.conn, tid, True)
            with self.conn:
                self.conn.execute("UPDATE tasks SET done_at = ? WHERE id = ?",
                                  (f"2026-10-{1 + n // 24:02d} {n % 24:02d}:00:00", tid))
            ids.append(tid)
        return ids

    def show(self, view):
        super().show(view)
        self.app.refresh()
        self.pump()

    def lane(self, view, key):
        return next(lane for k, lane, _ in view.lanes if k == key)

    def part(self, card, text_start):
        return next(l for l in labels(card) if str(l.cget("text")).startswith(text_start))

    def press_release(self, widget):
        widget.event_generate("<ButtonPress-1>", x=3, y=3)
        widget.event_generate("<ButtonRelease-1>", x=3, y=3)
        self.pump(1)

    # --- метки событий ---

    def test_tags_differ_and_all_parts_tagged(self):
        board, matrix = self.app.board, self.app.matrix
        self.assertNotEqual(board.card_tag, matrix.card_tag)
        self.assertNotEqual(board.wheel_tag, matrix.wheel_tag)
        self.assertNotEqual(board.card_tag, board.wheel_tag)
        self.add("Карточка")
        self.show("board")
        card = next(iter(board.cards.values()))
        for widget in [card, *labels(card)]:
            self.assertIn(board.card_tag, widget.bindtags())
            self.assertIn(board.wheel_tag, widget.bindtags())  # колесо — от колонки
        self.assertTrue(board.bind_class(board.wheel_tag, "<Shift-MouseWheel>"))
        self.assertFalse(matrix.bind_class(matrix.wheel_tag, "<Shift-MouseWheel>"))

    def test_tag_tree_puts_tag_first(self):
        frame = tk.Frame(self.root)
        inner = tk.Label(tk.Frame(frame))
        T.tag_tree(frame, "Проба")
        self.assertEqual(frame.bindtags()[0], "Проба")
        self.assertEqual(inner.bindtags()[0], "Проба")
        frame.destroy()

    def test_click_on_any_part_selects_its_task(self):
        first = self.add("Первая")
        second = self.add("Вторая", due="2030-01-02 10:00")
        db.add_attachment(self.conn, second, "a.txt", b"abc")
        for view_name in ("board", "matrix"):
            with self.subTest(view=view_name):
                self.show(view_name)
                view = self.app.cards_view()
                card = view.cards[second]
                self.assertEqual(card.task_id, second)
                for part in (self.part(card, "Вторая"), self.part(card, "Срок"), card.mark, card):
                    self.press_release(view.cards[first])
                    self.assertEqual(self.app.current_id(), first)
                    self.press_release(part)
                    self.assertEqual(self.app.current_id(), second, part.cget("text") if
                                     isinstance(part, tk.Label) else "рамка")
                self.assertIn("📎", card.mark.cget("text"))

    def test_double_click_and_right_click(self):
        first = self.add("Первая")
        second = self.add("Вторая")
        for view_name in ("board", "matrix"):
            with self.subTest(view=view_name):
                self.show(view_name)
                view = self.app.cards_view()
                title = self.part(view.cards[second], "Вторая")
                self.press_release(title)
                with mock.patch.object(self.app, "edit") as edit:
                    call_class(title, view.card_tag, "<Double-Button-1>")
                edit.assert_called_once_with()
                with mock.patch.object(self.app, "show_menu_for") as menu:
                    self.part(view.cards[first], "Первая").event_generate("<Button-3>", x=2, y=2)
                    self.pump(1)
                self.assertEqual(menu.call_args[0][0], first)

    def drag(self, view, card, target):
        """Перетаскивает карточку на середину виджета target."""
        x0, y0 = card.winfo_rootx() + 5, card.winfo_rooty() + 5
        tx = target.winfo_rootx() + target.winfo_width() // 2
        ty = target.winfo_rooty() + target.winfo_height() // 2
        card.event_generate("<ButtonPress-1>", x=5, y=5, rootx=x0, rooty=y0)
        for k in (1, 2, 3):
            x, y = x0 + (tx - x0) * k // 3, y0 + (ty - y0) * k // 3
            card.event_generate("<B1-Motion>", x=x - card.winfo_rootx(), y=y - card.winfo_rooty(),
                                rootx=x, rooty=y, state=0x100)
            self.pump(1)
        card.event_generate("<ButtonRelease-1>", x=tx - card.winfo_rootx(), y=ty - card.winfo_rooty(),
                            rootx=tx, rooty=ty, state=0x100)
        self.pump()

    def test_drag_to_other_lane(self):
        tid = self.add("Тащу")
        self.show("board")
        board = self.app.board
        target_id = next(k for k, _, _ in board.lanes if k != self.first_status)
        self.drag(board, self.part(board.cards[tid], "Тащу"), self.lane(board, target_id))
        self.assertEqual(db.list_tasks(self.conn)[-1][9], target_id)
        self.assertIsNone(board.drag)

    def test_drag_to_other_quadrant(self):
        tid = self.add("Тащу")  # «Отложить»
        self.show("matrix")
        matrix = self.app.matrix
        self.drag(matrix, self.part(matrix.cards[tid], "Тащу"), self.lane(matrix, 1))
        task = db.list_tasks(self.conn)[-1]
        self.assertEqual((task[6], task[7]), (1, 1))

    # --- колесо ---

    def test_wheel_scrolls_only_lane_under_pointer_when_overflowing(self):
        many = [self.add(f"Много {n}") for n in range(40)]
        other = self.first_status
        board = self.app.board
        with self.conn:  # одна задача — в другой колонке
            second_status = next(sid for sid, (_, _, done) in self.app.statuses.items()
                                 if sid != other and not done)
            lone = self.add("Одна")
            self.conn.execute("UPDATE tasks SET status_id = ? WHERE id = ?", (second_status, lone))
        self.show("board")
        full = self.lane(board, other).scroll_area
        short = self.lane(board, second_status).scroll_area
        full.yview_scroll = mock.Mock()
        short.yview_scroll = mock.Mock()
        self.part(board.cards[many[0]], "Много 0").event_generate("<MouseWheel>", delta=-120)
        self.pump(1)
        full.yview_scroll.assert_called_once_with(1, "units")
        short.yview_scroll.assert_not_called()
        full.yview_scroll.reset_mock()
        self.part(board.cards[lone], "Одна").event_generate("<MouseWheel>", delta=120)
        self.pump(1)
        full.yview_scroll.assert_not_called()
        short.yview_scroll.assert_not_called()  # всё помещается — не листаем
        # Shift+колесо — доска вбок
        board.canvas.xview_scroll = mock.Mock()
        self.part(board.cards[lone], "Одна").event_generate("<Shift-MouseWheel>", delta=120)
        self.pump(1)
        board.canvas.xview_scroll.assert_called_once_with(-1, "units")

    def test_wheel_in_matrix_quadrant(self):
        many = [self.add(f"Много {n}", urgent=1, important=1) for n in range(60)]
        self.show("matrix")
        matrix = self.app.matrix
        area = self.lane(matrix, 1).scroll_area
        self.root.update()
        self.assertGreater(area.bbox("all")[3], area.winfo_height(), "четверть должна переполниться")
        area.yview_scroll = mock.Mock()
        self.part(matrix.cards[many[0]], "Много 0").event_generate("<MouseWheel>", delta=120)
        self.pump(1)
        area.yview_scroll.assert_called_once_with(-1, "units")

    def test_wheel_outside_lane_does_nothing(self):
        """owner не нашёл колонки — колесо ничего не делает и не падает."""
        event = SimpleNamespace(widget=self.root, delta=120)
        self.assertIsNone(self.app.board.wheel(event))

    # --- выполненные: 30 самых свежих и «Показать остальные» ---

    def more_links(self, view):
        return [l for l in labels(view) if str(l.cget("text")).startswith("Показать остальные выполненные")]

    def test_board_done_lane_shows_freshest_and_expands(self):
        done = self.add_done(SHOWN + 7)
        active = self.add("Невыполненная")
        self.show("board")
        board = self.app.board
        self.assertEqual(set(self.app.done_times), set(done))
        cards = set(board.cards)
        self.assertIn(active, cards)
        self.assertEqual(cards & set(done), set(done[7:]))  # самые свежие — последние
        links = self.more_links(board)
        self.assertEqual([l.cget("text") for l in links], ["Показать остальные выполненные (7)"])
        lane = self.lane(board, self.done_status)
        self.assertIn(f" {SHOWN + 7} ", [l.cget("text") for l in labels(lane)])  # в заголовке — все
        self.press_release(board.cards[done[-1]])  # выделение сохранится после раскрытия
        links[0].event_generate("<Button-1>", x=2, y=2)
        self.pump(5)
        self.assertTrue(set(done) <= set(self.app.board.cards))
        self.assertEqual(self.more_links(self.app.board), [])
        self.assertEqual(self.app.current_id(), done[-1])
        # перерисовка — раскрытие сохраняется
        self.app.refresh()
        self.pump()
        self.assertTrue(set(done) <= set(self.app.board.cards))

    def test_board_exactly_limit_no_link(self):
        self.add_done(SHOWN)
        self.show("board")
        self.assertEqual(self.more_links(self.app.board), [])
        self.assertEqual(len(self.app.board.cards), SHOWN)

    def test_matrix_quadrant_limit_and_expand(self):
        done = self.add_done(SHOWN + 3, urgent=1, important=1)
        self.add_done(2)  # в «Отложить» — меньше предела
        self.show("matrix")  # матрица сама ставит «Активные» — выполненные видны при «Все»
        self.app.filter.set("Все")
        self.app.refresh()
        self.pump()
        matrix = self.app.matrix
        self.assertEqual(set(matrix.cards) & set(done), set(done[3:]))
        links = self.more_links(matrix)
        self.assertEqual([l.cget("text") for l in links], ["Показать остальные выполненные (3)"])
        self.assertIn(f" {SHOWN + 3} ", [l.cget("text") for l in labels(self.lane(matrix, 1))])
        links[0].event_generate("<Button-1>", x=2, y=2)
        self.pump(5)
        self.assertTrue(set(done) <= set(self.app.matrix.cards))
        self.assertEqual(self.more_links(self.app.matrix), [])
        self.assertEqual(self.app.matrix.expanded, {1})

    def test_expand_resets_on_other_list(self):
        self.add_done(SHOWN + 1)
        self.show("board")
        board = self.app.board
        board.expanded.add(self.done_status)
        board.expanded_list = self.app.list_id
        old = self.app.list_id
        self.app.list_id = "другой"  # смена списка (как в switch_list) — без настоящего списка
        try:
            shown, hidden = board.visible_rows(self.done_status,
                                               [r for r in db.list_tasks(self.conn) if r[2]])
        finally:
            self.app.list_id = old
        self.assertEqual(hidden, 1)
        self.assertEqual(board.expanded, set())


if __name__ == "__main__":
    unittest.main()
